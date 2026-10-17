# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import json
import os
from pathlib import Path

from fly import load_deployments


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    inputs = event.get("inputs", {})
    action = inputs.get("action", "deploy")
    selection = inputs.get("deployment", "")

    if action not in {"delete", "deploy"}:
        raise SystemExit(f"Invalid action: {action}")

    if action == "delete" and not selection:
        raise SystemExit("An app is required for deletion")

    configured_deployments = load_deployments()
    if selection:
        deployments = [
            deployment
            for deployment in configured_deployments
            if selection in {deployment["key"], deployment["app"]}
        ]
        if not deployments and action == "delete":
            deployments = [{"app": selection, "key": selection}]
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
