# /// script
# dependencies = ["pyyaml"]
# ///
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import yaml

# Gatus reaches public routes through Cloudflare, so Access-protected ones need
# Homelab's monitoring service token.
CLOUDFLARE_ACCESS_HEADERS = {
    "cf-access-client-id": "op://Flylab/Cloudflare Access Service Token/username",
    "cf-access-client-secret": "op://Flylab/Cloudflare Access Service Token/password",
}


def endpoints(inventory):
    if not any(entry["type"] == "route" for entry in inventory):
        raise ValueError("Expected a non-empty route inventory")
    by_url = {}
    for entry in inventory:
        url = entry["monitor"]
        group = entry["group"]
        name = entry["name"]
        if entry["type"] == "route":
            location = entry["cluster"]
            if placement := re.search(rf" \(({re.escape(location)}-[^\s()]+)\)", name):
                location = placement[1]
                name = name[: placement.start()] + name[placement.end() :]
        else:
            location = entry["location"]
            if entry["type"] == "machine":
                name = name.removesuffix(f" ({entry['host_name']})")
        status = entry.get("expected_status", "any(200, 401)")
        conditions = ["[RESPONSE_TIME] < 10000", f"[STATUS] == {status}"]
        if body_pattern := entry.get("expected_body"):
            conditions.append(f"[BODY] == pat({body_pattern})")
        probe = {
            "group": group,
            "name": name,
            "url": url,
            "alerts": [] if entry.get("alerts") == "false" else [{"type": "email"}],
            "conditions": conditions,
        }
        if url in by_url and by_url[url] != (probe, location):
            raise ValueError(f"Conflicting monitoring URL: {url}")
        by_url[url] = (probe, location)

    counts = Counter((probe["group"], probe["name"]) for probe, _ in by_url.values())
    probes = {}
    for probe, location in by_url.values():
        group, name = probe["group"], probe["name"]
        if counts[group, name] > 1:
            probe["name"] = f"{name} ({location})"
        identity = (group, probe["name"])
        if identity in probes:
            raise ValueError(f"Conflicting endpoint: {identity}")
        probes[identity] = probe
    return [
        probes[key]
        for key in sorted(
            probes, key=lambda item: (item[0].casefold(), item[1].casefold())
        )
    ]


def infrastructure_endpoints(machines):
    probes = []
    for machine in machines.values():
        if machine["type"] is None:
            continue
        targets = {}
        if machine["tailscale"]:
            targets["Internal"] = machine["fqdn"]
        if machine["public_fqdn"]:
            targets["External"] = machine["public_fqdn"]
        for scope, target in targets.items():
            probes.append(
                {
                    "group": "Servers",
                    "name": machine["location"]
                    + (" (External)" if scope == "External" else ""),
                    "url": f"icmp://{target}",
                    "alerts": [{"type": "email"}] if machine["monitoring"] else [],
                    "conditions": ["[CONNECTED] == true", "[RESPONSE_TIME] < 10000"],
                }
            )
    if not probes:
        raise ValueError("Expected a non-empty Homelab infrastructure inventory")
    return sorted(probes, key=lambda probe: probe["name"].casefold())


def machine_service_inventory(machines, services):
    return [
        {
            **service.get("probe", {}),
            "alerts": (
                "true"
                if machines[service["machine"]]["monitoring"] and service["monitoring"]
                else "false"
            ),
            "group": service.get("group") or "Infrastructure",
            "host_name": machines[service["machine"]]["name"],
            "location": machines[service["machine"]]["location"],
            "monitor": service["url"],
            "name": service["name"],
            "type": "machine",
        }
        for service in services.values()
    ]


def monitoring_credentials(inventory):
    headers = {}
    secrets = {}
    for entry in inventory:
        entry_headers = dict(entry["headers"])
        if entry.get("cloudflareAccess"):
            entry_headers.update(CLOUDFLARE_ACCESS_HEADERS)
        for header, reference in entry_headers.items():
            name = (
                "GATUS_HEADER_"
                + hashlib.sha256(reference.encode()).hexdigest()[:16].upper()
            )
            value = "${" + name + "}"
            endpoint_headers = headers.setdefault(entry["monitor"], {})
            if endpoint_headers.get(header.lower(), value) != value:
                raise ValueError(f"Conflicting monitoring header: {entry['monitor']}")
            endpoint_headers[header.lower()] = value
            secrets[name] = reference
    return headers, secrets


def provider_endpoints(providers):
    probes = []
    for provider in providers.values():
        if provider["monitoring"]:
            probes.append(
                {
                    "group": "Providers",
                    "name": provider["name"],
                    "url": provider["url"],
                    "alerts": [{"type": "email"}],
                    # Provider consoles may ask for sign-in; any answer means they are up.
                    "conditions": [
                        "[STATUS] == any(200, 401, 403, 429)",
                        "[RESPONSE_TIME] < 10000",
                    ],
                }
            )
        if "dns" in provider:
            resolver = provider["dns"]
            probes.append(
                {
                    "group": "Providers",
                    "name": resolver["name"],
                    "url": resolver["url"],
                    "dns": {
                        "query-name": resolver["query-name"],
                        "query-type": resolver["query-type"],
                    },
                    "alerts": [{"type": "email"}],
                    "conditions": [
                        "[CONNECTED] == true",
                        "[DNS_RCODE] == NOERROR",
                        "[RESPONSE_TIME] < 10000",
                    ],
                }
            )
    return sorted(probes, key=lambda probe: probe["name"].casefold())


def render(kubelab, homelab, output):
    inventory = json.loads(
        subprocess.check_output(
            ["bash", "scripts/render_service_inventory.sh"],
            cwd=kubelab,
            text=True,
        )
    )
    headers, secrets = monitoring_credentials(inventory)
    homelab_inventory = json.loads((homelab / "inventory.json").read_text())
    machines = homelab_inventory["machines"]
    services = homelab_inventory["services"]
    tailnet_hosts = sorted(
        {
            (machines[service["machine"]]["location"], service["hostname"])
            for service in services.values()
            if service.get("dns_tailscale", False)
        }
    )
    (output / "app/tailnet-hosts").write_text(
        "".join(f"{machine} {hostname}\n" for machine, hostname in tailnet_hosts)
    )
    inventory.extend(machine_service_inventory(machines, services))
    gatus = homelab_inventory["providers"]["gatus"]
    inventory.append(
        {
            "alerts": "true" if gatus["monitoring"] else "false",
            "group": gatus["group"],
            "location": "fly",
            "monitor": gatus["url"],
            "name": gatus["name"],
            "type": "fly",
        }
    )
    probes = endpoints(inventory)
    for probe in probes:
        if probe["url"] in headers:
            probe["headers"] = headers[probe["url"]]
            # A rejected token redirects to the Access login page, which would pass.
            if "cf-access-client-id" in probe["headers"]:
                probe["client"] = {"ignore-redirect": True}
    write_fnox_secrets(output / "fnox.toml", secrets)
    infrastructure = infrastructure_endpoints(machines)
    providers = provider_endpoints(homelab_inventory["providers"])
    for name, entries in {
        "infrastructure": infrastructure,
        "providers": providers,
        "services": probes,
    }.items():
        (output / f"app/config/{name}.yaml").write_text(
            yaml.safe_dump({"endpoints": entries}, sort_keys=False)
        )
    print(
        f"Rendered {len(probes)} service, {len(infrastructure)} infrastructure "
        f"and {len(providers)} provider probes"
    )


@contextmanager
def source_repository(name):
    local_repository = os.environ.get(f"{name.upper()}_DIRECTORY")
    revision = os.environ.get(f"{name.upper()}_REVISION", "")
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
                    "--depth=1",
                    "--quiet",
                    f"https://github.com/maxexcloo/{name}.git",
                    revision or "main",
                ],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "checkout", "--detach", "--quiet", "FETCH_HEAD"],
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


def write_fnox_secrets(path, secrets):
    """Append monitoring header secrets, and providers for their vaults, to fnox.toml."""
    providers = {
        provider["vault"]: name
        for name, provider in tomllib.loads(path.read_text())["providers"].items()
    }
    lines = []
    for name, reference in sorted(secrets.items()):
        vault, item, field = reference.removeprefix("op://").split("/")
        if vault not in providers:
            providers[vault] = re.sub(r"[^a-z0-9]+", "-", vault.lower()).strip("-")
            lines += [
                f"\n[providers.{providers[vault]}]",
                'type = "1password"',
                f"vault = {json.dumps(vault)}",
            ]
        lines += [
            f"\n[secrets.{name}]",
            f"provider = {json.dumps(providers[vault])}",
            f"value = {json.dumps(f'{item}/{field}')}",
        ]
    with path.open("a") as file:
        file.write("".join(f"{line}\n" for line in lines))


def main():
    with (
        source_repository("homelab") as homelab,
        source_repository("kubelab") as kubelab,
    ):
        render(kubelab, homelab, Path(sys.argv[1]))


if __name__ == "__main__":
    main()
