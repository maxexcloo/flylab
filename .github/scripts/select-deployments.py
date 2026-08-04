import json
import os


def main():
    action = os.environ["ACTION"]
    selection = os.environ.get("SELECTION", "")

    if action not in {"delete", "deploy"}:
        raise SystemExit(f"Invalid action: {action}")

    if action == "delete":
        if not selection:
            raise SystemExit("An app is required for deletion")
        deployments = [{"app": selection, "key": selection}]
    else:
        catalog = json.loads(os.environ["HOMELAB_CATALOG"])
        if catalog.get("repository") != "fly" or catalog.get("version") != 2:
            raise SystemExit("Expected Fly catalog version 2")

        if selection:
            deployments = [
                deployment
                for deployment in catalog["deployments"]
                if selection in {deployment["key"], deployment["app"]}
            ]
            if len(deployments) != 1:
                raise SystemExit("Expected one matching Fly deployment")
        else:
            deployments = catalog["deployments"]

    with open(os.environ["GITHUB_OUTPUT"], "a") as output_file:
        output_file.write(
            f"action={action}\n"
            f"deployments={json.dumps(deployments, separators=(',', ':'))}\n"
        )


if __name__ == "__main__":
    main()
