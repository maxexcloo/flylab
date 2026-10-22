import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

REFERENCE_NAME_PATTERN = re.compile(r"[A-Za-z0-9 ._-]+")
REFERENCE_PATTERN = re.compile(r"\{\{\s*op://([^/{}]+)/([^/{}]+)/([^/{}]+?)\s*\}\}")
SECRET_PATTERN = re.compile(r"^([A-Z0-9_]+)=.*$")


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def op_reference_ids(template):
    """Replace vault and item titles that secret references cannot express with IDs."""
    vaults = {}

    def replace(match):
        vault, item, field = match.groups()
        if not REFERENCE_NAME_PATTERN.fullmatch(vault):
            if vault not in vaults:
                vaults[vault] = op_json(["vault", "get", vault])["id"]
            vault = vaults[vault]
        if not REFERENCE_NAME_PATTERN.fullmatch(item):
            items = [
                candidate["id"]
                for candidate in op_json(["item", "list", "--vault", vault])
                if candidate["title"] == item
            ]
            if len(items) != 1:
                raise ValueError(f"Expected one 1Password item titled {item}")
            item = items[0]
        if not REFERENCE_NAME_PATTERN.fullmatch(field):
            raise ValueError(f"Unsupported characters in 1Password field: {field}")
        return f"{{{{ op://{vault}/{item}/{field} }}}}"

    return REFERENCE_PATTERN.sub(replace, template)


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
    lines = [
        line
        for line in (deployment_path / "secrets.env").read_text().splitlines()
        if line
    ]
    matches = [SECRET_PATTERN.fullmatch(line) for line in lines]
    if not all(matches):
        raise ValueError("Invalid secrets.env")
    desired = {match.group(1) for match in matches}

    injected = subprocess.run(
        ["op", "inject"],
        check=True,
        input=op_reference_ids("\n".join(lines) + "\n"),
        stdout=subprocess.PIPE,
        text=True,
    ).stdout

    current = {secret["name"] for secret in fly_json(["secrets", "list"], app)}
    stale = sorted(current - desired)
    if stale:
        subprocess.run(
            ["flyctl", "secrets", "unset", *stale, "--app", app, "--stage"],
            check=True,
        )
    subprocess.run(
        ["flyctl", "secrets", "import", "--app", app, "--stage"],
        check=True,
        input=injected,
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
