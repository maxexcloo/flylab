import json
import os
import re

DEPLOYMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def main():
    action = os.environ["ACTION"]
    event_name = os.environ["EVENT_NAME"]
    selection = os.environ.get("SELECTION", "")
    catalog = json.loads(os.environ["HOMELAB_CATALOG"])

    if action not in {"delete", "deploy"}:
        raise SystemExit(f"Invalid action: {action}")
    if action == "deploy" and (
        catalog.get("repository") != "fly" or catalog.get("version") != 2
    ):
        raise SystemExit("Expected Fly catalog version 2")
    if selection and not DEPLOYMENT_PATTERN.fullmatch(selection):
        raise SystemExit(f"Invalid deployment: {selection}")

    if event_name == "workflow_dispatch" and selection:
        matches = [
            deployment
            for deployment in catalog.get("deployments", [])
            if selection in {deployment["key"], deployment["app"]}
        ]
        if action == "delete":
            deployment = matches[0] if matches else {"app": selection, "key": selection}
            deployments = [{"app": deployment["app"], "key": deployment["key"]}]
        elif len(matches) == 1:
            deployments = matches
        else:
            raise SystemExit("Expected one matching Fly deployment")
    elif action == "delete":
        raise SystemExit("A deployment is required for deletion")
    else:
        deployments = catalog["deployments"]

    with open(os.environ["GITHUB_OUTPUT"], "a") as output_file:
        output_file.write(
            f"action={action}\n"
            f"deployments={json.dumps(deployments, separators=(',', ':'))}\n"
        )


if __name__ == "__main__":
    main()
