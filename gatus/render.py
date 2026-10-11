# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.3"]
# ///

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import tempfile
import tomllib
from contextlib import ExitStack, contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import yaml


def domain_group(url, zones):
    hostname = urlsplit(url).hostname
    matches = [
        zone for zone in zones if hostname == zone or hostname.endswith("." + zone)
    ]
    if not matches:
        raise ValueError(f"Monitoring URL has no Homelab DNS zone: {url}")
    return max(matches, key=len)


def endpoints(inventory, zones):
    if not isinstance(inventory, list) or not any(
        entry.get("type") == "route" for entry in inventory
    ):
        raise ValueError("Expected a non-empty route inventory")
    probes = {}
    urls = {}
    for entry in inventory:
        if entry.get("type") not in {"machine", "route", "fly"}:
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
            suffix = f" ({cluster.upper()})"
            if not name.endswith(suffix):
                name += suffix
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
        alerts = entry.get("alerts", "true")
        if alerts not in {"false", "true"}:
            raise ValueError(f"Invalid monitoring alerts setting: {alerts}")
        if alerts == "false":
            probe["alerts"] = []
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


def infrastructure_endpoints(repository):
    inventory = yaml.safe_load((repository / "data/machines.yaml").read_text())
    machines = inventory["machines"]
    groups = inventory["types"]
    domain = yaml.safe_load((repository / "data/domains.yaml").read_text())["domains"][
        "infrastructure"
    ]
    probes = []
    for network, entries in sorted(machines.items()):
        for name, machine in sorted(entries.items()):
            machine_type = machine.get("type")
            monitoring = machine.get("monitoring", True)
            if type(monitoring) is not bool:
                raise ValueError(f"Invalid monitoring setting: {name}")
            if machine_type is None or not monitoring:
                continue
            if machine_type not in groups:
                raise ValueError(f"Unsupported machine type: {machine_type}")
            hostname = machine.get("hostname", name)
            targets = {}
            if machine.get("tailscale", {}).get("enabled", True):
                targets["Internal"] = f"{hostname}.{network}.{domain}"
            address = machine.get("public_ipv4") or machine.get("public_ipv6")
            if address:
                targets["External"] = str(ipaddress.ip_address(address))
            for scope, target in targets.items():
                probes.append(
                    {
                        "group": f"{scope} ({groups[machine_type]})",
                        "name": f"{network}-{hostname}",
                        "url": f"icmp://{target}",
                        "alerts": [{"type": "email"}],
                        "conditions": ["[CONNECTED] == true", "[RESPONSE_TIME] < 5000"],
                    }
                )
    if not probes:
        raise ValueError("Expected a non-empty Homelab infrastructure inventory")
    return sorted(
        probes, key=lambda probe: (probe["group"].casefold(), probe["name"].casefold())
    )


def machine_service_inventory(repository):
    """Read explicit machine-service checks without importing dashboard configuration."""
    machines = yaml.safe_load((repository / "data/machines.yaml").read_text())[
        "machines"
    ]
    domain = yaml.safe_load((repository / "data/domains.yaml").read_text())["domains"][
        "infrastructure"
    ]
    entries = []
    for network, hosts in machines.items():
        for name, machine in hosts.items():
            if machine.get("monitoring", True) is False:
                continue
            for service_name, service in machine.get("services", {}).items():
                monitoring = service.get("monitoring", False)
                if type(monitoring) is not bool:
                    raise ValueError(
                        f"Invalid service monitoring setting: {name}/{service_name}"
                    )
                if not monitoring:
                    continue
                scheme, port = service["scheme"], service["port"]
                if (
                    scheme not in {"http", "https"}
                    or type(port) is not int
                    or not 1 <= port <= 65535
                ):
                    raise ValueError(
                        f"Invalid machine service endpoint: {name}/{service_name}"
                    )
                host = f"{machine.get('hostname', name)}.{network}.{domain}"
                suffix = (
                    ""
                    if (scheme, port) in {("http", 80), ("https", 443)}
                    else f":{port}"
                )
                entries.append(
                    {
                        "group": "Infrastructure",
                        "monitor": f"{scheme}://{host}{suffix}",
                        "name": service.get("name", f"{name} {service_name}"),
                        "source": f"Homelab/{network}/{name}/{service_name}",
                        "type": "machine",
                    }
                )
    return entries


def monitoring_credentials(inventory, manifests):
    headers = {}
    secrets = {}
    clusters = sorted(
        {entry["cluster"] for entry in inventory if entry["type"] == "route"}
    )
    for cluster in clusters:
        resources = []
        for target in (
            f"apps/overlays/{cluster}.yaml",
            f"clusters/{cluster}/platform.yaml",
        ):
            resources.extend(
                resource
                for resource in yaml.safe_load_all((manifests / target).read_text())
                if resource
            )
        external_secrets = {}
        stores = {}
        for resource in resources:
            kind = resource["kind"]
            metadata = resource["metadata"]
            if kind in {"ClusterSecretStore", "SecretStore"}:
                namespace = (
                    metadata.get("namespace", "") if kind == "SecretStore" else ""
                )
                stores[(kind, namespace, metadata["name"])] = resource
            elif kind == "ExternalSecret":
                target = (
                    resource["spec"].get("target", {}).get("name", metadata["name"])
                )
                key = (metadata["namespace"], target)
                if key in external_secrets:
                    raise ValueError(f"Multiple ExternalSecrets target {key}")
                external_secrets[key] = resource
        for entry in inventory:
            if entry.get("cluster") != cluster or not entry.get("headers"):
                continue
            if urlsplit(entry["monitor"]).hostname not in entry["hostnames"]:
                raise ValueError(
                    "Monitoring credentials must target the declaring route"
                )
            namespace = entry["namespace"]
            if not isinstance(entry["headers"], dict):
                raise TypeError(
                    "Monitoring headers must map names to Secret references"
                )
            for header, reference in entry["headers"].items():
                if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9a-zA-Z-]+", header):
                    raise ValueError("Invalid monitoring header name")
                if not isinstance(reference, dict) or set(reference) != {"name", "key"}:
                    raise ValueError(
                        "Monitoring headers require a namespace-local Secret name and key"
                    )
                secret_name, field = reference["name"], reference["key"]
                resource = external_secrets[(namespace, secret_name)]
                spec = resource["spec"]
                if spec.get("target", {}).get("template"):
                    raise ValueError(
                        "Monitoring secrets must use direct ExternalSecret data mappings"
                    )
                store = spec["secretStoreRef"]
                kind = store.get("kind", "SecretStore")
                store_namespace = namespace if kind == "SecretStore" else ""
                vaults = stores[(kind, store_namespace, store["name"])]["spec"][
                    "provider"
                ]["onepassword"]["vaults"]
                if len(vaults) != 1:
                    raise ValueError(
                        "Monitoring secrets require exactly one 1Password vault"
                    )
                mappings = [
                    data for data in spec.get("data", []) if data["secretKey"] == field
                ]
                if len(mappings) != 1 or "sourceRef" in mappings[0]:
                    raise ValueError(
                        f"Unsupported monitoring secret mapping: {namespace}/{secret_name}/{field}"
                    )
                remote = mappings[0]["remoteRef"]
                reference = (
                    f"op://{next(iter(vaults))}/{remote['key']}/{remote['property']}"
                )
                if not re.fullmatch(r"op://[a-zA-Z0-9_./ -]+", reference):
                    raise ValueError(
                        "Unsupported characters in monitoring secret reference; use item IDs"
                    )
                name = (
                    "GATUS_HEADER_"
                    + hashlib.sha256(reference.encode()).hexdigest()[:16].upper()
                )
                value = "${" + name + "}"
                endpoint_headers = headers.setdefault(entry["monitor"], {})
                if (
                    header.lower() in endpoint_headers
                    and endpoint_headers[header.lower()] != value
                ):
                    raise ValueError(
                        f"Conflicting monitoring header: {entry['monitor']}"
                    )
                endpoint_headers[header.lower()] = value
                secrets[name] = reference
    return headers, secrets


def provider_endpoints(repository):
    providers = yaml.safe_load((repository / "data/providers.yaml").read_text())[
        "providers"
    ]
    domain = yaml.safe_load((repository / "data/domains.yaml").read_text())["domains"][
        "infrastructure"
    ]
    probes = []
    for provider in providers.values():
        name = provider["name"]
        if "conditions" in provider:
            validate_url(provider["url"])
            probes.append(
                {
                    "group": "Providers",
                    "name": name,
                    "url": provider["url"],
                    **{
                        key: provider[key]
                        for key in ("alerts", "conditions")
                        if key in provider
                    },
                }
            )
        if "dns" in provider:
            resolver = provider["dns"]
            probes.append(
                {
                    "group": "Providers",
                    "name": resolver.get("name", f"{name} DNS"),
                    "url": str(ipaddress.ip_address(resolver["url"])),
                    "dns": {
                        "query-name": resolver.get("query-name", domain),
                        "query-type": resolver["query-type"],
                    },
                    **{
                        key: resolver[key]
                        for key in ("alerts", "conditions")
                        if key in resolver
                    },
                }
            )
    return sorted(probes, key=lambda probe: probe["name"].casefold())


def render(repository, homelab, output):
    with tempfile.TemporaryDirectory(prefix="gatus-manifests-") as directory:
        manifests = Path(directory)
        subprocess.run(
            ["bash", "scripts/render_manifests.sh", directory],
            cwd=repository,
            check=True,
        )
        inventory = json.loads(
            subprocess.check_output(
                [
                    "bash",
                    "scripts/render_service_inventory.sh",
                    "--manifest-directory",
                    directory,
                ],
                cwd=repository,
                env=dict(os.environ, HOMELAB_DIRECTORY=str(homelab)),
                text=True,
            )
        )
        headers, secrets = monitoring_credentials(inventory, manifests)
    zones = [
        yaml.safe_load(path.read_text())["name"]
        for path in sorted((homelab / "data/dns").glob("*.yaml"))
    ]
    inventory.extend(machine_service_inventory(homelab))
    deployment = tomllib.loads((Path(__file__).parent / "deployment.toml").read_text())
    inventory.extend(
        {
            "group": "Operations",
            "monitor": f"https://{hostname}",
            "name": "Gatus",
            "source": "Flylab/gatus/deployment.toml",
            "type": "fly",
        }
        for hostname in deployment["certificates"]
    )
    probes = endpoints(inventory, zones)
    for probe in probes:
        if probe["url"] in headers:
            probe["headers"] = dict(probe.get("headers", {}), **headers[probe["url"]])
    with (output / "secrets.env").open("a") as secret_file:
        for name, reference in sorted(secrets.items()):
            secret_file.write(f"{name}={{{{ {reference} }}}}\n")
    infrastructure = infrastructure_endpoints(homelab)
    providers = provider_endpoints(homelab)
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
