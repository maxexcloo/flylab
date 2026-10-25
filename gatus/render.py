# /// script
# dependencies = ["pyyaml>=6.0.3"]
# ///
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import tomllib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def endpoints(inventory):
    if not any(entry["type"] == "route" for entry in inventory):
        raise ValueError("Expected a non-empty route inventory")
    probes = {}
    urls = {}
    for entry in inventory:
        url = entry["monitor"]
        group = entry["group"]
        name = entry["name"]
        location = entry["cluster"] if entry["type"] == "route" else entry["location"]
        # Match the location tag Homepage shows on the card; per-node routes carry
        # `(<cluster>/<node>)` already.
        if f" ({location}" not in name:
            name += f" ({location})"
        conditions = ["[RESPONSE_TIME] < 5000", "[STATUS] == any(200, 401)"]
        if urlsplit(url).scheme == "https":
            conditions.insert(0, "[CERTIFICATE_EXPIRATION] > 168h")
        probe = {
            "group": group,
            "name": name,
            "url": url,
            "alerts": [] if entry.get("alerts") == "false" else [{"type": "email"}],
            "conditions": conditions,
        }
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


def infrastructure_endpoints(machines, domain):
    probes = []
    for network, name, hostname, host, machine in monitored_machines(machines, domain):
        if machine.get("type") is None:
            continue
        targets = {}
        if machine.get("tailscale", {}).get("enabled", True):
            targets["Internal"] = host
        # Homelab publishes each public address as public.<machine FQDN>.
        if (
            machine.get("public_ipv4")
            or machine.get("public_ipv6")
            or machine.get("oci", {}).get("assign_public_ip")
        ):
            targets["External"] = f"public.{host}"
        for scope, target in targets.items():
            probes.append(
                {
                    "group": "Servers",
                    "name": f"{network}-{hostname}"
                    + (" (External)" if scope == "External" else ""),
                    "url": f"icmp://{target}",
                    "alerts": [{"type": "email"}],
                    "conditions": ["[CONNECTED] == true", "[RESPONSE_TIME] < 5000"],
                }
            )
    if not probes:
        raise ValueError("Expected a non-empty Homelab infrastructure inventory")
    return sorted(probes, key=lambda probe: probe["name"].casefold())


def machine_service_inventory(machines, domain):
    """Read explicit machine-service checks without importing dashboard configuration."""
    entries = []
    for network, name, hostname, host, machine in monitored_machines(machines, domain):
        for service_name, service in machine.get("services", {}).items():
            if not service.get("monitoring", False):
                continue
            scheme, port = service["scheme"], service["port"]
            service_host = service.get("hostname", host)
            suffix = (
                "" if (scheme, port) in {("http", 80), ("https", 443)} else f":{port}"
            )
            entries.append(
                {
                    "group": service["group"],
                    "location": f"{network}-{hostname}",
                    "monitor": f"{scheme}://{service_host}{suffix}",
                    "name": service.get("name", f"{name} {service_name}"),
                    "type": "machine",
                }
            )
    return entries


def monitored_machines(machines, domain):
    for network, hosts in sorted(machines.items()):
        for name, machine in sorted(hosts.items()):
            if machine.get("monitoring", True):
                hostname = machine.get("hostname", name)
                yield network, name, hostname, f"{hostname}.{network}.{domain}", machine


def monitoring_credentials(inventory):
    headers = {}
    secrets = {}
    for entry in inventory:
        for header, reference in entry["headers"].items():
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


def provider_endpoints(providers, domain):
    probes = []
    for provider in providers.values():
        name = provider["name"]
        if provider.get("monitoring", True):
            probes.append(
                {
                    "group": "Providers",
                    "name": name,
                    "url": provider["url"],
                    "alerts": [{"type": "email"}],
                    # Provider consoles may ask for sign-in; any answer means they are up.
                    "conditions": [
                        "[STATUS] == any(200, 401, 403)",
                        "[RESPONSE_TIME] < 5000",
                    ],
                }
            )
        if "dns" in provider:
            resolver = provider["dns"]
            probes.append(
                {
                    "group": "Providers",
                    "name": resolver.get("name", f"{name} DNS"),
                    "url": resolver["url"],
                    "dns": {
                        "query-name": resolver.get("query-name", domain),
                        "query-type": resolver["query-type"],
                    },
                    "alerts": [{"type": "email"}],
                    "conditions": [
                        "[CONNECTED] == true",
                        "[DNS_RCODE] == NOERROR",
                        "[RESPONSE_TIME] < 5000",
                    ],
                }
            )
    return sorted(probes, key=lambda probe: probe["name"].casefold())


def render(repository, homelab, output):
    inventory = json.loads(
        subprocess.check_output(
            ["bash", "scripts/render_service_inventory.sh"],
            cwd=repository,
            env=dict(os.environ, HOMELAB_DIRECTORY=str(homelab)),
            text=True,
        )
    )
    headers, secrets = monitoring_credentials(inventory)
    machines = yaml.safe_load((homelab / "data/machines.yaml").read_text())["machines"]
    domains = yaml.safe_load((homelab / "data/domains.yaml").read_text())["domains"]
    domain = domains["infrastructure"]
    providers = yaml.safe_load((homelab / "data/providers.yaml").read_text())[
        "providers"
    ]
    inventory.extend(machine_service_inventory(machines, domain))
    deployment = tomllib.loads((Path(__file__).parent / "deployment.toml").read_text())
    inventory.extend(
        {
            "group": "Operations",
            "location": "fly",
            "monitor": f"https://{hostname}",
            "name": "Gatus",
            "type": "fly",
        }
        for hostname in deployment["certificates"]
    )
    probes = endpoints(inventory)
    for probe in probes:
        if probe["url"] in headers:
            probe["headers"] = headers[probe["url"]]
    write_fnox_secrets(output / "fnox.toml", secrets)
    infrastructure = infrastructure_endpoints(machines, domain)
    providers = provider_endpoints(providers, domain)
    config_directory = output / "app/config"
    (config_directory / "services.yaml").write_text(
        yaml.safe_dump({"endpoints": probes}, sort_keys=False)
    )
    (config_directory / "infrastructure.yaml").write_text(
        yaml.safe_dump({"endpoints": infrastructure}, sort_keys=False)
    )
    (config_directory / "providers.yaml").write_text(
        yaml.safe_dump({"endpoints": providers}, sort_keys=False)
    )
    print(
        f"Rendered {len(probes)} service, {len(infrastructure)} infrastructure "
        f"and {len(providers)} provider probes"
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
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with (
        source_repository("homelab") as homelab,
        source_repository("kubelab") as kubelab,
    ):
        render(kubelab, homelab, args.output)


if __name__ == "__main__":
    main()
