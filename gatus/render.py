# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///

import argparse
import copy
import ipaddress
import json
import os
import re
import subprocess
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MACHINE_GROUPS = {
    "appliance": "Appliances",
    "backup": "Servers",
    "router": "Routers",
    "server": "Servers",
    "storage": "Servers",
    "vm": "VMs",
}


def apply_override(probe, overrides):
    override = overrides.get(probe["url"], {})
    if not isinstance(override, dict) or any(
        key in override for key in ("group", "name", "url")
    ):
        raise ValueError(f"Invalid override: {probe['url']}")
    return dict(probe, **copy.deepcopy(override))


def domain_group(url, zones):
    hostname = urlsplit(url).hostname
    matches = [
        zone for zone in zones if hostname == zone or hostname.endswith("." + zone)
    ]
    if not matches:
        raise ValueError(f"Monitoring URL has no Homelab DNS zone: {url}")
    return max(matches, key=len)


def endpoints(inventory, overrides, zones):
    if not isinstance(inventory, list) or not any(
        entry.get("type") == "route" for entry in inventory
    ):
        raise ValueError("Expected a non-empty route inventory")
    probes = {}
    urls = {}
    for entry in inventory:
        if entry.get("type") not in {"homepage", "route"}:
            raise ValueError("Unsupported inventory entry")
        for field in ("group", "monitor", "name", "source"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Missing inventory field: {field}")
        url = entry["monitor"]
        validate_url(url)
        group = domain_group(url, zones)
        name = entry["name"]
        if entry["type"] == "route":
            cluster = entry.get("cluster")
            if not isinstance(cluster, str) or not cluster:
                raise ValueError("Route is missing its cluster")
            name = f"{name} ({cluster})"
        conditions = ["[RESPONSE_TIME] < 5000", "[STATUS] == any(200, 401)"]
        if urlsplit(url).scheme == "https":
            conditions.insert(0, "[CERTIFICATE_EXPIRATION] > 168h")
        probe = {
            "group": group,
            "name": name,
            "url": url,
            "alerts": [{"type": "email"}],
            "conditions": conditions,
        }
        probe = apply_override(probe, overrides)
        identity = (group, name)
        if identity in probes and probes[identity] != probe:
            raise ValueError(f"Conflicting endpoint: {identity}")
        if url in urls and urls[url] != identity:
            raise ValueError(f"Conflicting monitoring URL: {url}")
        probes[identity] = probe
        urls[url] = identity
    return [
        probes[key]
        for key in sorted(
            probes, key=lambda item: (item[0].casefold(), item[1].casefold())
        )
    ]


def infrastructure_endpoints(repository, overrides):
    machines = yaml.safe_load((repository / "data/machines.yaml").read_text())[
        "machines"
    ]
    domain = yaml.safe_load((repository / "data/domains.yaml").read_text())["domains"][
        "infrastructure"
    ]
    probes = []
    for network, entries in sorted(machines.items()):
        for name, machine in sorted(entries.items()):
            machine_type = machine.get("type")
            if machine_type is None:
                continue
            if machine_type not in MACHINE_GROUPS:
                raise ValueError(f"Unsupported machine type: {machine_type}")
            hostname = machine.get("hostname", name)
            targets = {}
            if machine.get("tailscale", {}).get("enabled", True):
                targets["Internal"] = f"{hostname}.{network}.{domain}"
            address = machine.get("public_ipv4") or machine.get("public_ipv6")
            if address:
                targets["External"] = str(ipaddress.ip_address(address))
            for scope, target in targets.items():
                probe = apply_override(
                    {
                        "group": f"{scope} / {MACHINE_GROUPS[machine_type]}",
                        "name": f"{hostname} ({network})",
                        "url": f"icmp://{target}",
                        "alerts": [{"type": "email"}],
                        "conditions": ["[CONNECTED] == true", "[RESPONSE_TIME] < 5000"],
                    },
                    overrides,
                )
                if probe.get("enabled", True):
                    probes.append(probe)
    if not probes:
        raise ValueError("Expected a non-empty Homelab infrastructure inventory")
    return sorted(
        probes, key=lambda probe: (probe["group"].casefold(), probe["name"].casefold())
    )


def render(repository, homelab, output):
    inventory = json.loads(
        subprocess.check_output(
            ["bash", "scripts/render_service_inventory.sh", "--include-static"],
            cwd=repository,
            text=True,
        )
    )
    overrides = yaml.safe_load(Path(__file__).with_name("overrides.yaml").read_text())
    zones = [
        yaml.safe_load(path.read_text())["name"]
        for path in sorted((homelab / "data/dns").glob("*.yaml"))
    ]
    probes = endpoints(inventory, overrides, zones)
    infrastructure = infrastructure_endpoints(homelab, overrides)
    config_directory = output / "app/config"
    for path in sorted(config_directory.glob("*.yaml")):
        if path.name in {"infrastructure.yaml", "services.yaml"}:
            continue
        for probe in yaml.safe_load(path.read_text()).get("endpoints", []):
            if any(
                probe["url"] == generated["url"]
                or (probe["group"], probe["name"])
                == (generated["group"], generated["name"])
                for generated in probes + infrastructure
            ):
                raise ValueError(f"Static endpoint conflicts with inventory: {path}")
    (config_directory / "services.yaml").write_text(
        yaml.safe_dump({"endpoints": probes}, sort_keys=False)
    )
    (config_directory / "infrastructure.yaml").write_text(
        yaml.safe_dump({"endpoints": infrastructure}, sort_keys=False)
    )
    print(
        f"Rendered {len(probes)} service and {len(infrastructure)} infrastructure probes"
    )


@contextmanager
def source_repository(name):
    local_repository = os.environ.get(f"{name.upper()}_DIRECTORY")
    revision = os.environ.get(f"{name.upper()}_REVISION", "")
    if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError(f"{name.upper()}_REVISION must be a full commit SHA")
    if local_repository and revision:
        raise ValueError(f"Choose {name.upper()}_DIRECTORY or {name.upper()}_REVISION")
    with tempfile.TemporaryDirectory(prefix=f"gatus-{name}-") as directory:
        repository = (
            Path(local_repository).resolve() if local_repository else Path(directory)
        )
        if not local_repository:
            subprocess.run(["git", "init", "--quiet", directory], check=True)
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "--depth=1",
                    f"https://github.com/maxexcloo/{name}.git",
                    revision or "main",
                ],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--quiet", "--detach", "FETCH_HEAD"],
                cwd=repository,
                check=True,
            )
        resolved_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True
        ).strip()
        print(
            f"Reading {name} {resolved_revision}"
            + (" (local checkout)" if local_repository else "")
        )
        yield repository


def validate_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(character.isspace() for character in url)
    ):
        raise ValueError(f"Invalid monitoring URL: {url}")
    # Accessing port also rejects malformed and out-of-range ports.
    if parsed.port == 0:
        raise ValueError(f"Invalid monitoring port: {url}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with ExitStack() as stack:
        homelab = stack.enter_context(source_repository("homelab"))
        kubelab = stack.enter_context(source_repository("kubelab"))
        render(kubelab, homelab, args.output)


if __name__ == "__main__":
    main()
