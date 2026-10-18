import importlib.util
import json
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


class DeploymentSelectionTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "selection",
            Path(__file__).parents[1] / ".github/scripts/select-deployments.py",
        )
        self.selection = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"fly": FLY}):
            spec.loader.exec_module(self.selection)
        self.deployments = [{"app": "example-app", "key": "example-key"}]

    def select(self, action, selection):
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory) / "event.json"
            output = Path(directory) / "output"
            event.write_text(
                json.dumps({"inputs": {"action": action, "deployment": selection}})
            )
            with (
                patch.dict(
                    os.environ,
                    {"GITHUB_EVENT_PATH": str(event), "GITHUB_OUTPUT": str(output)},
                ),
                patch.object(
                    self.selection, "load_deployments", return_value=self.deployments
                ),
            ):
                self.selection.main()
            return json.loads(output.read_text().removeprefix("deployments="))

    def test_ambiguous_selection_fails_for_both_actions(self):
        self.deployments.append({"app": "other-app", "key": "example-app"})
        for action in ("delete", "deploy"):
            with self.subTest(action=action), self.assertRaises(SystemExit):
                self.select(action, "example-app")

    def test_deletion_accepts_retired_app_names(self):
        self.assertEqual(
            self.select("delete", "retired-app"),
            [{"app": "retired-app", "key": "retired-app", "action": "delete"}],
        )

    def test_deletion_rejects_invalid_app_names(self):
        for selection in ("--help", "Retired-App", "retired app"):
            with (
                self.subTest(selection=selection),
                self.assertRaisesRegex(SystemExit, "one matching Fly deployment"),
            ):
                self.select("delete", selection)

    def test_deletion_requires_explicit_selection(self):
        with self.assertRaisesRegex(SystemExit, "required for deletion"):
            self.select("delete", "")

    def test_keys_and_app_names_resolve_consistently(self):
        for action in ("delete", "deploy"):
            for selection in ("example-app", "example-key"):
                with self.subTest(action=action, selection=selection):
                    self.assertEqual(
                        self.select(action, selection),
                        [dict(self.deployments[0], action=action)],
                    )

    def test_unknown_deployments_fail(self):
        with self.assertRaisesRegex(SystemExit, "one matching Fly deployment"):
            self.select("deploy", "unknown")


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


class RenderingTest(unittest.TestCase):
    def test_render_all_discovers_services_and_runs_optional_renderers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("alpha", "bravo"):
                service = root / name
                service.mkdir()
                (service / "deployment.toml").write_text(
                    f'certificates = []\nkey = "{name}"\nmachine_count = 1\n'
                )
                (service / "fly.toml").write_text(
                    f'app = "{name}"\n[[http_service.checks]]\npath = "/health"\n'
                )
            (root / "alpha/render.py").touch()
            (root / "alpha/requirements.txt").write_text("example==1.0\n")
            with (
                patch.object(FLY, "Path", side_effect=lambda value: root / value),
                patch("sys.argv", ["fly.py", "--render-all"]),
                patch.object(FLY.subprocess, "run") as run,
            ):
                FLY.main()
            self.assertEqual(run.call_count, 1)
            self.assertIn(str(root / "alpha/requirements.txt"), run.call_args.args[0])
            self.assertIn(str(root / "alpha/render.py"), run.call_args.args[0])
            for name in ("alpha", "bravo"):
                self.assertTrue((root / ".render" / name / "fly.toml").is_file())


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
