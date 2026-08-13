import json
import os
from pathlib import Path

REQUIRED_DEPLOYMENT_FIELDS = {
    "app": str,
    "certificates": list,
    "cpu_kind": str,
    "cpus": int,
    "custom": dict,
    "force_https": bool,
    "image": str,
    "key": str,
    "machine_count": int,
    "memory_mb": int,
    "region": str,
    "service": dict,
    "target": str,
    "template": str,
}


def validate_config(config):
    if config.get("repository") != "fly":
        raise SystemExit("Expected Fly config")

    deployments = config.get("deployments")
    if not isinstance(deployments, list):
        raise SystemExit("Expected Fly deployments")

    apps = set()
    keys = set()
    for deployment in deployments:
        if not isinstance(deployment, dict):
            raise SystemExit("Expected each Fly deployment to be an object")
        for field, expected_type in REQUIRED_DEPLOYMENT_FIELDS.items():
            value = deployment.get(field)
            if type(value) is not expected_type or (
                expected_type is str and not value and field != "image"
            ):
                raise SystemExit(f"Invalid Fly deployment field: {field}")

        backend = deployment["service"]["routing"]["default"]["backend"]
        if type(backend.get("port")) is not int:
            raise SystemExit("Invalid Fly deployment field: backend.port")
        if any(
            type(certificate) is not str or not certificate
            for certificate in deployment["certificates"]
        ):
            raise SystemExit("Invalid Fly deployment field: certificates")

        app = deployment["app"]
        key = deployment["key"]
        if app in apps:
            raise SystemExit(f"Duplicate Fly app: {app}")
        if key in keys:
            raise SystemExit(f"Duplicate Fly deployment key: {key}")
        apps.add(app)
        keys.add(key)

    return deployments


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    inputs = event.get("inputs", {})
    action = inputs.get("action", "deploy")
    selection = inputs.get("deployment", "")

    if action not in {"delete", "deploy"}:
        raise SystemExit(f"Invalid action: {action}")

    if action == "delete":
        if not selection:
            raise SystemExit("An app is required for deletion")
        deployments = [{"app": selection, "key": selection}]
    else:
        config = json.loads(os.environ["CONFIG"])
        configured_deployments = validate_config(config)

        if selection:
            deployments = [
                deployment
                for deployment in configured_deployments
                if selection in {deployment["key"], deployment["app"]}
            ]
            if len(deployments) != 1:
                raise SystemExit("Expected one matching Fly deployment")
        else:
            deployments = configured_deployments

    deployments = [dict(deployment, action=action) for deployment in deployments]

    with open(os.environ["GITHUB_OUTPUT"], "a") as output_file:
        output_file.write(
            f"deployments={json.dumps(deployments, separators=(',', ':'))}\n"
        )


if __name__ == "__main__":
    main()
