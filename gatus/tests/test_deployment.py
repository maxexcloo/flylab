import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "fly", Path(__file__).parents[2] / ".github/scripts/fly.py"
)
FLY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FLY)


class DeploymentTest(unittest.TestCase):
    def test_stopped_machines_start_before_health_verification(self):
        deployment = {
            "app": "example",
            "certificates": [],
            "directory": "example",
            "machine_count": 1,
            "port": 8080,
        }
        calls = Mock()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / ".render/example").mkdir(parents=True)
            (path / ".render/example/fly.toml").touch()
            with (
                patch.object(FLY, "Path", side_effect=lambda value: path / value),
                patch.object(FLY, "app_exists", return_value=True),
                patch.object(FLY, "reconcile_certificates"),
                patch.object(FLY, "reconcile_secrets"),
                patch.object(
                    FLY,
                    "fly_json",
                    return_value=[
                        {"id": "cold", "state": "stopped"},
                        {"id": "warm", "state": "started"},
                    ],
                ),
                patch.object(FLY.subprocess, "run", calls.run),
                patch.object(FLY, "verify", calls.verify),
            ):
                FLY.deploy(deployment)
        self.assertEqual(
            [call.args[0] for call in calls.run.call_args_list],
            [
                ["flyctl", "deploy", "--app", "example", "--config", "fly.toml"],
                ["flyctl", "scale", "count", "1", "--app", "example", "--yes"],
                ["flyctl", "machine", "start", "cold", "--app", "example"],
            ],
        )
        self.assertEqual(
            calls.mock_calls[-1], unittest.mock.call.verify("example", 8080)
        )


class SecretReconciliationTest(unittest.TestCase):
    def test_missing_native_secret_stops_before_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}),
                patch.object(FLY, "fly_json", return_value=[]),
                patch.object(FLY.subprocess, "run") as run,
                self.assertRaisesRegex(ValueError, "MAIL_PASSWORD"),
            ):
                FLY.reconcile_secrets("example", Path(directory), ["MAIL_PASSWORD"])
            run.assert_not_called()

    def test_native_secrets_are_preserved_and_stale_generated_secrets_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "secrets.env").write_text("NEW={{ op://vault/item/field }}\n")
            with (
                patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}),
                patch.object(
                    FLY,
                    "fly_json",
                    return_value=[{"Name": "MAIL_PASSWORD"}, {"Name": "OLD"}],
                ),
                patch.object(
                    FLY.subprocess,
                    "run",
                    return_value=Mock(stdout="NEW=test-fixture\n"),
                ) as run,
            ):
                FLY.reconcile_secrets("example", path, ["MAIL_PASSWORD"])
            self.assertEqual(
                run.call_args_list[1].args[0],
                ["flyctl", "secrets", "unset", "OLD", "--app", "example", "--stage"],
            )
            self.assertEqual(
                run.call_args_list[2].kwargs["input"], "NEW=test-fixture\n"
            )

    def test_secret_resolution_is_refused_outside_github_actions(self):
        with (
            patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}),
            patch.object(FLY.subprocess, "run") as run,
            self.assertRaises(RuntimeError),
        ):
            FLY.reconcile_secrets("example", Path("unused"), [])
        run.assert_not_called()
