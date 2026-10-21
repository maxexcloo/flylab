import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

DEPLOYMENT_KEYS = {"certificates", "machine_count"}
REFERENCE_NAME_PATTERN = re.compile(r"[A-Za-z0-9 ._-]+")
REFERENCE_PATTERN = re.compile(r"\{\{\s*op://([^/{}]+)/([^/{}]+)/([^/{}]+?)\s*\}\}")
SECRET_PATTERN = re.compile(r"^([A-Z0-9_]+)=.*$")
SERVICE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def app_exists(app):
    apps = json.loads(
        subprocess.check_output(
            ["flyctl", "apps", "list", "--json"],
            text=True,
        )
    )
    return any(candidate["Name"] == app for candidate in apps)


def delete(app):
    if app_exists(app):
        subprocess.run(["flyctl", "apps", "destroy", app, "--yes"], check=True)
    else:
        print(f"{app} does not exist")


def deploy(deployment):
    app = deployment["app"]
    deployment_path = (
        Path(os.environ["FLYLAB_RENDER_DIRECTORY"]) / deployment["directory"]
    )
    if not (deployment_path / "fly.toml").is_file():
        raise ValueError("Render the deployment before deploying")

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
    verify(app, deployment["machine_count"])


def fly_json(arguments, app):
    result = subprocess.check_output(
        ["flyctl", *arguments, "--app", app, "--json"],
        text=True,
    )
    return json.loads(result)


def load_deployments():
    deployments = []
    apps = set()
    for path in sorted(Path(".").glob("*/deployment.toml")):
        deployment = tomllib.loads(path.read_text())
        unknown = set(deployment) - DEPLOYMENT_KEYS
        if unknown:
            raise ValueError(f"Unknown deployment keys: {', '.join(sorted(unknown))}")
        config = tomllib.loads((path.parent / "fly.toml").read_text())
        deployment.update(
            app=config["app"],
            directory=path.parent.name,
        )
        if not SERVICE_PATTERN.fullmatch(deployment["app"]):
            raise ValueError("Invalid Fly app")
        if (
            type(deployment["machine_count"]) is not int
            or deployment["machine_count"] < 1
        ):
            raise ValueError("Expected a positive machine count")
        if not config.get("http_service", {}).get("checks"):
            raise ValueError("Configure native Fly health checks in fly.toml")
        certificates = deployment["certificates"]
        if not isinstance(certificates, list) or any(
            not isinstance(host, str) or not host or host.startswith("-")
            for host in certificates
        ):
            raise ValueError("Invalid certificates")
        if deployment["app"] in apps:
            raise ValueError("Duplicate Fly app")
        apps.add(deployment["app"])
        deployments.append(deployment)
    if not deployments:
        raise ValueError("No deployments configured")
    return deployments


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


def python_command(service_path):
    command = ["uv", "run", "--no-project", "--python", "python"]
    requirements = service_path / "requirements.txt"
    if requirements.is_file():
        command.extend(["--with-requirements", str(requirements)])
    return command


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
            ["op", "inject"],
            check=True,
            input=op_reference_ids("\n".join(lines) + "\n"),
            stdout=subprocess.PIPE,
            text=True,
        ).stdout
        if lines
        else ""
    )

    current = {secret["name"] for secret in fly_json(["secrets", "list"], app)}
    stale = sorted(current - desired)
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

    render_path = Path(os.environ["FLYLAB_RENDER_DIRECTORY"]) / service
    if render_path.exists():
        shutil.rmtree(render_path)
    shutil.copytree(
        service_path,
        render_path,
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    renderer = service_path / "render.py"
    if renderer.is_file():
        subprocess.run(
            [*python_command(service_path), str(renderer), str(render_path.resolve())],
            check=True,
        )

    return render_path


def verify(app, machine_count):
    # Scaling happens after deploy's native health wait.
    for _ in range(60):
        machines = fly_json(["checks", "list"], app)
        if len(machines) == machine_count and all(
            checks and all(check["status"] == "passing" for check in checks)
            for checks in machines.values()
        ):
            return
        time.sleep(5)
    raise RuntimeError(f"Native Fly health checks did not pass on every {app} machine")


def main():
    parser = argparse.ArgumentParser()
    rendering = parser.add_mutually_exclusive_group()
    rendering.add_argument("--render", metavar="SERVICE")
    rendering.add_argument("--render-all", action="store_true")
    args = parser.parse_args()
    if args.render or args.render_all:
        services = (
            [args.render]
            if args.render
            else [deployment["directory"] for deployment in load_deployments()]
        )
        temporary_output = None
        if "FLYLAB_RENDER_DIRECTORY" not in os.environ:
            temporary_output = tempfile.mkdtemp(prefix="flylab-render-")
            os.environ["FLYLAB_RENDER_DIRECTORY"] = temporary_output
        try:
            for service in services:
                print(render(service))
        finally:
            if args.render_all and temporary_output:
                shutil.rmtree(temporary_output)
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
