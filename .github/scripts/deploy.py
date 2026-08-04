import json
import os
import re
import subprocess
from pathlib import Path

SECRET_PATTERN = re.compile(r"^([A-Z0-9_]+)=")


def app_exists(app):
    return (
        subprocess.run(
            ["flyctl", "apps", "info", app],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def reconcile_certificates(app, deployment_path):
    current = {
        certificate.get("Hostname", certificate.get("hostname"))
        for certificate in fly_json(["certs", "list"], app)
    }
    certs_file = deployment_path / ".certs"
    desired = (
        {line for line in certs_file.read_text().splitlines() if line}
        if certs_file.is_file()
        else set()
    )

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
    secrets_path = deployment_path / "secrets.env"
    desired = {
        match.group(1)
        for line in secrets_path.read_text().splitlines()
        if (match := SECRET_PATTERN.match(line))
    }
    current = {
        secret.get("Name", secret.get("name"))
        for secret in fly_json(["secrets", "list"], app)
    }
    stale = sorted(current - desired)
    if stale:
        subprocess.run(
            ["flyctl", "secrets", "unset", *stale, "--app", app, "--stage"],
            check=True,
        )

    injected = subprocess.run(
        ["op", "inject", "--in-file", secrets_path],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
    if injected:
        subprocess.run(
            ["flyctl", "secrets", "import", "--app", app, "--stage"],
            check=True,
            input=injected,
            text=True,
        )


def main():
    app = os.environ["APP"]
    deployment_path = Path(os.environ["DEPLOYMENT_PATH"])
    os.environ["FLY_API_TOKEN"]
    os.environ["OP_SERVICE_ACCOUNT_TOKEN"]

    if not app_exists(app):
        subprocess.run(["flyctl", "apps", "create", app], check=True)

    reconcile_secrets(app, deployment_path)
    reconcile_certificates(app, deployment_path)
    subprocess.run(
        ["flyctl", "deploy", "--app", app, "--config", "fly.toml"],
        check=True,
        cwd=deployment_path,
    )

    machine_count_path = deployment_path / ".machine-count"
    if machine_count_path.is_file():
        machine_count = machine_count_path.read_text().strip()
        if machine_count:
            subprocess.run(
                ["flyctl", "scale", "count", machine_count, "--app", app],
                check=True,
            )


if __name__ == "__main__":
    main()
