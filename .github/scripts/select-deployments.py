import json
import os
from pathlib import Path


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
