import json
import os
import subprocess
import tomllib
from pathlib import Path


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def reconcile_certificates(app, desired):
    current = {
        certificate["hostname"] for certificate in fly_json(["certs", "list"], app)
    }
    desired = set(desired)

    for hostname in sorted(current - desired):
        subprocess.run(
            ["flyctl", "certs", "remove", hostname, "--app", app, "--yes"],
            check=True,
        )
    for hostname in sorted(desired - current):
        subprocess.run(
            ["flyctl", "certs", "add", hostname, "--app", app],
            check=True,
        )


def reconcile_secrets(app, deployment_path):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Resolve 1Password references only in GitHub Actions")
    config_path = deployment_path / "fnox.toml"
    desired = sorted(tomllib.loads(config_path.read_text())["secrets"])
    # fnox also loads the user's global configuration, so keep only the declared names.
    values = json.loads(
        subprocess.check_output(
            [
                "fnox",
                "--config",
                str(config_path),
                "export",
                "--all",
                "--format",
                "json",
            ],
            text=True,
        )
    )["secrets"]
    missing = [name for name in desired if not values.get(name)]
    if missing:
        raise ValueError(f"Unresolved secrets: {', '.join(missing)}")

    current = {secret["name"] for secret in fly_json(["secrets", "list"], app)}
    stale = sorted(current - set(desired))
    if stale:
        subprocess.run(
            ["flyctl", "secrets", "unset", *stale, "--app", app, "--stage"],
            check=True,
        )
    subprocess.run(
        ["flyctl", "secrets", "import", "--app", app, "--stage"],
        check=True,
        input="".join(f"{name}={values[name]}\n" for name in desired),
        text=True,
    )


def reconcile_volumes(app, config):
    # Deploy only creates volumes for new machines, so create one for each mount first.
    current = {volume["name"] for volume in fly_json(["volumes", "list"], app)}
    for mount in config.get("mounts", []):
        if mount["source"] not in current:
            subprocess.run(
                [
                    "flyctl",
                    "volumes",
                    "create",
                    mount["source"],
                    "--app",
                    app,
                    "--region",
                    config["primary_region"],
                    "--yes",
                ],
                check=True,
            )


def main():
    deployment_path = Path(os.environ["FLYLAB_RENDER_DIRECTORY"])
    config = tomllib.loads((deployment_path / "fly.toml").read_text())
    app = config["app"]
    deployment = tomllib.loads((deployment_path / "deployment.toml").read_text())

    apps = json.loads(
        subprocess.check_output(["flyctl", "apps", "list", "--json"], text=True)
    )
    if not any(candidate["Name"] == app for candidate in apps):
        subprocess.run(["flyctl", "apps", "create", app], check=True)

    reconcile_certificates(app, deployment["certificates"])
    reconcile_secrets(app, deployment_path)
    reconcile_volumes(app, config)
    # Deploy waits for native health checks; --ha=false keeps a new app to one machine.
    subprocess.run(
        [
            "flyctl",
            "deploy",
            str(deployment_path),
            "--app",
            app,
            "--config",
            str(deployment_path / "fly.toml"),
            "--ha=false",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
