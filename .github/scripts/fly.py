import json
import os
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

REFERENCE_NAME_PATTERN = re.compile(r"[A-Za-z0-9 ._-]+")


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def fnox_reference_ids(config):
    """Replace vault and item titles that 1Password secret references cannot express with IDs."""
    providers = config["providers"]
    for provider in providers.values():
        if not REFERENCE_NAME_PATTERN.fullmatch(provider["vault"]):
            provider["vault"] = op_json(["vault", "get", provider["vault"]])["id"]
    for secret in config["secrets"].values():
        item, field = secret["value"].split("/")
        if not REFERENCE_NAME_PATTERN.fullmatch(field):
            raise ValueError(f"Unsupported characters in 1Password field: {field}")
        if not REFERENCE_NAME_PATTERN.fullmatch(item):
            vault = providers[secret["provider"]]["vault"]
            items = [
                candidate["id"]
                for candidate in op_json(["item", "list", "--vault", vault])
                if candidate["title"] == item
            ]
            if len(items) != 1:
                raise ValueError(f"Expected one 1Password item titled {item}")
            secret["value"] = f"{items[0]}/{field}"
    return config


def fnox_toml(config):
    lines = []
    for name, provider in sorted(config["providers"].items()):
        lines += [f"[providers.{name}]"]
        lines += [
            f"{key} = {json.dumps(value)}" for key, value in sorted(provider.items())
        ]
        lines += [""]
    lines += ["[secrets]"]
    lines += [
        f"{name} = {{ provider = {json.dumps(secret['provider'])}, "
        f"value = {json.dumps(secret['value'])} }}"
        for name, secret in sorted(config["secrets"].items())
    ]
    return "\n".join(lines) + "\n"


def op_json(arguments):
    return json.loads(
        subprocess.check_output(["op", *arguments, "--format", "json"], text=True)
    )


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
    config = tomllib.loads((deployment_path / "fnox.toml").read_text())
    desired = sorted(config["secrets"])
    with tempfile.TemporaryDirectory() as directory:
        config_path = Path(directory) / "fnox.toml"
        config_path.write_text(fnox_toml(fnox_reference_ids(config)))
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


def main():
    deployment_path = Path(os.environ["FLYLAB_RENDER_DIRECTORY"])
    app = tomllib.loads((deployment_path / "fly.toml").read_text())["app"]
    deployment = tomllib.loads((deployment_path / "deployment.toml").read_text())

    apps = json.loads(
        subprocess.check_output(["flyctl", "apps", "list", "--json"], text=True)
    )
    if not any(candidate["Name"] == app for candidate in apps):
        subprocess.run(["flyctl", "apps", "create", app], check=True)

    reconcile_certificates(app, deployment["certificates"])
    reconcile_secrets(app, deployment_path)
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
