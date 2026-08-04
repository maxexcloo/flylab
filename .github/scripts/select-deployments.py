import json
import os
import re

DEPLOYMENT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def main():
    selection = os.environ.get("SELECTION", "")
    catalog = json.loads(os.environ["HOMELAB_CATALOG"])

    if catalog.get("repository") != "fly" or catalog.get("version") != 2:
        raise SystemExit("Expected Fly catalog version 2")
    if selection and not DEPLOYMENT_PATTERN.fullmatch(selection):
        raise SystemExit(f"Invalid deployment: {selection}")

    if selection:
        matches = [
            deployment
            for deployment in catalog.get("deployments", [])
            if selection in {deployment["key"], deployment["app"]}
        ]
        if len(matches) == 1:
            deployments = matches
        else:
            raise SystemExit("Expected one matching Fly deployment")
    else:
        deployments = catalog["deployments"]

    with open(os.environ["GITHUB_OUTPUT"], "a") as output_file:
        output_file.write(
            f"deployments={json.dumps(deployments, separators=(',', ':'))}\n"
        )


if __name__ == "__main__":
    main()
