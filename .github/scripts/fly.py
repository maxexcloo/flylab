import json
import os
import re
import shutil
import subprocess
from pathlib import Path

SECRET_PATTERN = re.compile(r"^([A-Z0-9_]+)=.*$")


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


def delete(app):
    if app_exists(app):
        subprocess.run(["flyctl", "apps", "destroy", app, "--yes"], check=True)
    else:
        print(f"{app} does not exist")


def deploy(deployment):
    app = deployment["app"]
    deployment_path = render(deployment["service"])

    if not app_exists(app):
        subprocess.run(["flyctl", "apps", "create", app], check=True)

    reconcile_certificates(app, deployment["certificates"])
    reconcile_secrets(app, deployment_path)
    subprocess.run(
        ["flyctl", "deploy", "--app", app, "--config", "fly.toml"],
        check=True,
        cwd=deployment_path,
    )
    subprocess.run(
        ["flyctl", "scale", "count", str(deployment["machine_count"]), "--app", app],
        check=True,
    )


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def reconcile_certificates(app, desired):
    current = {
        hostname
        for certificate in fly_json(["certs", "list"], app)
        if (hostname := certificate.get("Hostname") or certificate.get("hostname"))
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
    env_path = deployment_path / ".env"
    lines = [line for line in env_path.read_text().splitlines() if line]
    matches = [SECRET_PATTERN.fullmatch(line) for line in lines]
    if not all(matches):
        raise ValueError("Invalid .env")

    desired = {match.group(1) for match in matches}
    if len(desired) != len(matches):
        raise ValueError("Duplicate secret in .env")

    current = {
        name
        for secret in fly_json(["secrets", "list"], app)
        if (name := secret.get("Name") or secret.get("name"))
    }
    stale = sorted(current - desired)
    if stale:
        subprocess.run(
            ["flyctl", "secrets", "unset", *stale, "--app", app, "--stage"],
            check=True,
        )

    injected = subprocess.run(
        ["op", "inject", "--in-file", env_path],
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


def render(service):
    service_path = Path(service)
    if not service_path.is_dir():
        raise FileNotFoundError(f"Service not found: {service}")

    render_path = Path(".render") / service
    if render_path.exists():
        shutil.rmtree(render_path)
    shutil.copytree(
        service_path,
        render_path,
        ignore=shutil.ignore_patterns("*.tmpl"),
    )

    for template in sorted(service_path.rglob("*.tmpl")):
        output_path = render_path / template.relative_to(service_path).with_suffix("")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["gomplate", "--file", template, "--out", output_path],
            check=True,
        )

    return render_path


def main():
    deployment = json.loads(os.environ["DEPLOYMENT"])
    action = deployment["action"]

    if action == "delete":
        delete(deployment["app"])
    elif action == "deploy":
        deploy(deployment)
    else:
        raise ValueError(f"Invalid action: {action}")


if __name__ == "__main__":
    main()
