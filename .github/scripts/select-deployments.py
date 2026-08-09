import json
import os
from pathlib import Path


def normalize_config(config):
    version = config.get("version")
    if version == 2:
        deployments = []
        for deployment in config["deployments"]:
            custom = dict(deployment.get("custom", {}))
            if deployment["service"] == "gatus":
                environment = {
                    "MAIL_PASSWORD": (
                        f"op://{config['vault_id']}/{deployment['item']}/mail_password"
                    ),
                    "TAILSCALE_AUTH_KEY": (
                        f"op://{config['vault_id']}/{deployment['item']}/tailscale_auth_key"
                    ),
                }
                probes = []
                for service in config["services"]:
                    key = service["key"].upper().replace("-", "_")
                    environment[f"MONITORING_TOKEN_{key}"] = (
                        f"op://{config['vault_id']}/{service['item']}/monitoring_token"
                    )
                    if service["features"]["oidc_forward_auth"]:
                        environment[f"MONITORING_BASIC_{key}"] = (
                            f"op://{config['vault_id']}/{service['item']}/monitoring_basic"
                        )
                    for url in service["urls"]:
                        endpoint = {
                            "conditions": [
                                "[CERTIFICATE_EXPIRATION] > 168h",
                                "[RESPONSE_TIME] < 5000",
                                (
                                    "[STATUS] == 200"
                                    if service["features"]["oidc_forward_auth"]
                                    else "[STATUS] == any(200, 401)"
                                ),
                            ],
                            "group": f" {url['host']}",
                            "headers": {
                                "X-Gatus-Token": f"${{MONITORING_TOKEN_{key}}}"
                            },
                            "name": f"{service['title']} ({service['target']})",
                            "url": url["href"],
                        }
                        if service["features"]["monitoring_alerts"]:
                            endpoint["alerts"] = [{"type": "email"}]
                        if service["features"]["oidc_forward_auth"]:
                            endpoint["headers"]["Authorization"] = (
                                f"Basic ${{MONITORING_BASIC_{key}}}"
                            )
                        probes.append(endpoint)

                gatus = dict(config["gatus"])
                gatus["environment"] = environment
                gatus["probes"] = probes + gatus["probes"]
                custom["gatus"] = gatus
            deployments.append(deployment | {"custom": custom})

        config = dict(config)
        config["deployments"] = deployments
        config["version"] = 3
    return config


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
        config = normalize_config(json.loads(os.environ["CONFIG"]))
        if config.get("repository") != "fly" or config.get("version") != 3:
            raise SystemExit("Expected Fly config version 3")

        if selection:
            deployments = [
                deployment
                for deployment in config["deployments"]
                if selection in {deployment["key"], deployment["app"]}
            ]
            if len(deployments) != 1:
                raise SystemExit("Expected one matching Fly deployment")
        else:
            deployments = config["deployments"]

    deployments = [dict(deployment, action=action) for deployment in deployments]

    with open(os.environ["GITHUB_OUTPUT"], "a") as output_file:
        output_file.write(
            f"deployments={json.dumps(deployments, separators=(',', ':'))}\n"
        )


if __name__ == "__main__":
    main()
