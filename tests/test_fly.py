import contextlib
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fly", ROOT / ".github/scripts/fly.py")
fly = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fly)


class DeploymentTests(unittest.TestCase):
    def test_only_skip_healthy_matching_deployments(self):
        with tempfile.TemporaryDirectory() as directory:
            deployment = Path(directory)
            for name in ("deployment.toml", "fly.toml"):
                (deployment / name).write_bytes((ROOT / "gatus" / name).read_bytes())
            digest = fly.rendered_digest(deployment)
            healthy = {
                "state": "started",
                "checks": [{"status": "passing"}],
                "config": {"env": {"FLYLAB_RENDER_DIGEST": digest}},
            }
            failing = copy.deepcopy(healthy)
            failing["checks"] = [{"status": "critical"}]
            cases = [
                ("healthy", [healthy], "true", False),
                ("all healthy", [healthy, healthy], "true", False),
                ("failed deployment", [failing], "true", True),
                ("one unhealthy", [healthy, failing], "true", True),
                (
                    "pending check",
                    [healthy | {"checks": [{"status": "warning"}]}],
                    "true",
                    True,
                ),
                ("no checks", [healthy | {"checks": []}], "true", True),
                (
                    "missing checks",
                    [{k: v for k, v in healthy.items() if k != "checks"}],
                    "true",
                    True,
                ),
                ("stopped", [healthy | {"state": "stopped"}], "true", True),
                (
                    "new configuration",
                    [healthy | {"config": {"env": {"FLYLAB_RENDER_DIGEST": "old"}}}],
                    "true",
                    True,
                ),
                ("no digest", [healthy | {"config": {"env": {}}}], "true", True),
                ("no machines", [], "true", True),
                ("forced deployment", [healthy], "false", True),
            ]
            for name, machines, skip, should_deploy in cases:
                with (
                    self.subTest(name=name),
                    patch.dict(
                        os.environ,
                        FLYLAB_RENDER_DIRECTORY=directory,
                        FLYLAB_SKIP_UNCHANGED=skip,
                    ),
                    patch.object(
                        fly.subprocess,
                        "check_output",
                        return_value=json.dumps([{"Name": "excloo-gatus"}]),
                    ),
                    patch.object(fly, "fly_json", return_value=machines),
                    patch.object(fly, "reconcile_certificates"),
                    patch.object(fly, "reconcile_secrets"),
                    patch.object(fly, "reconcile_volumes"),
                    patch.object(fly.subprocess, "run") as run,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    fly.main()
                    if should_deploy:
                        run.assert_called_once()
                        self.assertEqual(
                            run.call_args.args[0][:2], ["flyctl", "deploy"]
                        )
                    else:
                        run.assert_not_called()
