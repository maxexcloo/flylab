# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

SECRET_PATTERN = re.compile(r"^([A-Z0-9_]+)=.*$")
SERVICE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def app_exists(app):
    apps = json.loads(
        subprocess.check_output(
            ["flyctl", "apps", "list", "--json"],
            text=True,
        )
    )
    return any(
        app == (candidate.get("Name") or candidate.get("name")) for candidate in apps
    )


def delete(app):
    if app_exists(app):
        subprocess.run(["flyctl", "apps", "destroy", app, "--yes"], check=True)
    else:
        print(f"{app} does not exist")


def deploy(deployment):
    app = deployment["app"]
    deployment_path = Path(".render") / deployment["directory"]
    if not (deployment_path / "fly.toml").is_file():
        raise ValueError("Render the deployment before deploying")

    if not app_exists(app):
        subprocess.run(["flyctl", "apps", "create", app], check=True)

    reconcile_certificates(app, deployment["certificates"])
    reconcile_secrets(app, deployment_path, deployment.get("required_secrets", []))
    subprocess.run(
        ["flyctl", "deploy", "--app", app, "--config", "fly.toml"],
        check=True,
        cwd=deployment_path,
    )
    subprocess.run(
        [
            "flyctl",
            "scale",
            "count",
            str(deployment["machine_count"]),
            "--app",
            app,
            "--yes",
        ],
        check=True,
    )
    for machine in fly_json(["machines", "list"], app):
        if machine["state"] in {"stopped", "suspended"}:
            subprocess.run(
                ["flyctl", "machine", "start", machine["id"], "--app", app],
                check=True,
            )
    verify(app, deployment["port"], deployment["health_paths"])


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def load_deployments():
    deployments = []
    apps = set()
    keys = set()
    for path in sorted(Path(".").glob("*/deployment.toml")):
        deployment = tomllib.loads(path.read_text())
        config = tomllib.loads((path.parent / "fly.toml").read_text())
        deployment.update(
            app=config["app"],
            directory=path.parent.name,
            health_paths=[check["path"] for check in config["http_service"]["checks"]],
            port=config["http_service"]["internal_port"],
        )
        if not SERVICE_PATTERN.fullmatch(deployment["app"]):
            raise ValueError("Invalid Fly app")
        if not SERVICE_PATTERN.fullmatch(deployment["key"]):
            raise ValueError("Invalid deployment key")
        if (
            type(deployment["machine_count"]) is not int
            or deployment["machine_count"] < 1
        ):
            raise ValueError("Expected a positive machine count")
        if type(deployment["port"]) is not int or not 1 <= deployment["port"] <= 65535:
            raise ValueError("Invalid internal port")
        if not deployment["health_paths"] or any(
            check.get("method", "GET") != "GET"
            or check.get("protocol", "http") != "http"
            or check.get("headers")
            for check in config["http_service"]["checks"]
        ):
            raise ValueError(
                "Health verification requires HTTP GET checks without headers"
            )
        for health_path in deployment["health_paths"]:
            parsed = urlsplit(health_path)
            if (
                not health_path.startswith("/")
                or parsed.netloc
                or parsed.fragment
                or any(character.isspace() for character in health_path)
            ):
                raise ValueError("Invalid health check path")
        required = deployment.get("required_secrets", [])
        if not isinstance(required, list) or any(
            not isinstance(name, str) or not re.fullmatch(r"[A-Z0-9_]+", name)
            for name in required
        ):
            raise ValueError("Invalid required secret names")
        certificates = deployment["certificates"]
        if not isinstance(certificates, list) or any(
            not isinstance(host, str) or not host or host.startswith("-")
            for host in certificates
        ):
            raise ValueError("Invalid certificates")
        if deployment["app"] in apps or deployment["key"] in keys:
            raise ValueError("Duplicate Fly app or deployment key")
        apps.add(deployment["app"])
        keys.add(deployment["key"])
        deployments.append(deployment)
    if not deployments:
        raise ValueError("No deployments configured")
    return deployments


def python_command(service_path):
    command = ["uv", "run", "--no-project", "--python", "python"]
    requirements = service_path / "requirements.txt"
    if requirements.is_file():
        command.extend(["--with-requirements", str(requirements)])
    return command


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


def reconcile_secrets(app, deployment_path, required):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Resolve 1Password references only in GitHub Actions")
    env_path = deployment_path / "secrets.env"
    lines = (
        [line for line in env_path.read_text().splitlines() if line]
        if env_path.exists()
        else []
    )
    matches = [SECRET_PATTERN.fullmatch(line) for line in lines]
    if not all(matches):
        raise ValueError("Invalid secrets.env")

    desired = {match.group(1) for match in matches}
    if len(desired) != len(matches):
        raise ValueError("Duplicate secret in secrets.env")

    injected = (
        subprocess.run(
            ["op", "inject", "--in-file", env_path],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        if lines
        else ""
    )

    current = {
        name
        for secret in fly_json(["secrets", "list"], app)
        if (name := secret.get("Name") or secret.get("name"))
    }
    missing = set(required) - current - desired
    if missing:
        raise ValueError(
            f"Required Fly secrets are missing: {', '.join(sorted(missing))}"
        )
    stale = sorted(current - desired - set(required))
    if stale:
        subprocess.run(
            ["flyctl", "secrets", "unset", *stale, "--app", app, "--stage"],
            check=True,
        )

    if injected:
        subprocess.run(
            ["flyctl", "secrets", "import", "--app", app, "--stage"],
            check=True,
            input=injected,
            text=True,
        )


def render(service):
    if not SERVICE_PATTERN.fullmatch(service):
        raise ValueError(f"Invalid service: {service}")

    service_path = Path(service)
    if not service_path.is_dir():
        raise FileNotFoundError(f"Service not found: {service}")

    render_path = Path(".render") / service
    if render_path.exists():
        shutil.rmtree(render_path)
    shutil.copytree(
        service_path,
        render_path,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    renderer = service_path / "render.py"
    if renderer.is_file():
        subprocess.run(
            [*python_command(service_path), str(renderer), str(render_path.resolve())],
            check=True,
        )

    return render_path


def verify(app, port, paths):
    checks = " && ".join(
        shlex.join(
            [
                "wget",
                "--output-document=-",
                "--timeout=5",
                f"http://127.0.0.1:{port}{path}",
            ]
        )
        for path in paths
    )
    command = (
        f"for attempt in $(seq 1 30); do {checks} && exit 0; sleep 3; done; exit 1"
    )
    subprocess.run(
        [
            "flyctl",
            "ssh",
            "console",
            "--app",
            app,
            "--command",
            shlex.join(["sh", "-c", command]),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", metavar="SERVICE")
    args = parser.parse_args()
    if args.render:
        print(render(args.render))
        return
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
