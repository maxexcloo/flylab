import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "fly", Path(__file__).parents[1] / ".github/scripts/fly.py"
)
FLY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FLY)


class DeploymentTest(unittest.TestCase):
    def test_native_health_checks_are_required_without_restricting_their_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = root / "example"
            service.mkdir()
            (service / "deployment.toml").write_text(
                'certificates = []\nkey = "example"\nmachine_count = 1\n'
            )
            config = service / "fly.toml"
            with patch.object(FLY, "Path", side_effect=lambda value: root / value):
                config.write_text(
                    'app = "example"\n[http_service]\ninternal_port = 9090\n'
                    '[[http_service.checks]]\npath = "/ready"\nmethod = "HEAD"\n'
                    'protocol = "https"\nheaders = { X-Health = "example" }\n'
                )
                self.assertEqual(FLY.load_deployments()[0]["app"], "example")
                config.write_text(
                    'app = "example"\n[http_service]\ninternal_port = 9090\n'
                )
                with self.assertRaisesRegex(ValueError, "native Fly health checks"):
                    FLY.load_deployments()

    def test_native_health_wait_requires_every_machine_and_check(self):
        passing = {"status": "passing"}
        results = [
            {},
            {"one": [passing]},
            {"one": [passing], "two": []},
            {"one": [passing], "two": [passing, {"status": "critical"}]},
            {"one": [passing], "two": [passing]},
        ]
        with (
            patch.object(FLY, "fly_json", side_effect=results) as checks,
            patch.object(FLY.time, "sleep") as sleep,
        ):
            FLY.verify("example", 2)
        self.assertEqual(checks.call_count, 5)
        checks.assert_called_with(["checks", "list"], "example")
        self.assertEqual(sleep.call_count, 4)

    def test_unhealthy_machines_fail_deployment_after_bounded_wait(self):
        with (
            patch.object(FLY, "fly_json", return_value={"one": []}),
            patch.object(FLY.time, "sleep") as sleep,
            self.assertRaisesRegex(RuntimeError, "every example machine"),
        ):
            FLY.verify("example", 1)
        self.assertEqual(sleep.call_count, 59)

    def test_stopped_machines_start_before_health_verification(self):
        deployment = {
            "app": "example",
            "certificates": [],
            "directory": "example",
            "machine_count": 1,
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
        self.assertEqual(calls.mock_calls[-1], unittest.mock.call.verify("example", 1))


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


class ServiceSuitesTest(unittest.TestCase):
    def test_discovery_uses_each_services_dependencies(self):
        spec = importlib.util.spec_from_file_location(
            "suites", Path(__file__).parents[1] / ".github/scripts/test.py"
        )
        suites = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"fly": FLY}):
            spec.loader.exec_module(suites)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            for service in ("alpha", "bravo"):
                (root / service / "tests").mkdir(parents=True)
                (root / service / "deployment.toml").touch()
            (root / "alpha/requirements.txt").write_text("example==1.0\n")
            with (
                patch.object(suites, "Path", side_effect=lambda value: root / value),
                patch.object(suites.subprocess, "run") as run,
            ):
                suites.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(
                [command[-1] for command in commands],
                [str(root / path) for path in ("tests", "alpha/tests", "bravo/tests")],
            )
            self.assertIn(str(root / "alpha/requirements.txt"), commands[1])
            self.assertNotIn("--with-requirements", commands[0])
            self.assertNotIn("--with-requirements", commands[2])
