import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml

SPEC = importlib.util.spec_from_file_location(
    "render", Path(__file__).parents[1] / "render.py"
)
RENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDER)


def route(**changes):
    return {
        "cluster": "mbk",
        "monitor": "https://media.example.com",
        "name": "Media",
        "type": "route",
        **changes,
    }


class EndpointsTest(unittest.TestCase):
    def test_conflicting_names_and_urls_fail(self):
        for entry in (
            route(monitor="https://other.example.com"),
            route(name="Other"),
            route(cluster="syd"),
        ):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                RENDER.endpoints([route(), entry], ["example.com"])

    def test_empty_and_unsupported_inventories_fail(self):
        for inventory in (
            [],
            [route(type="machine")],
            [route(), route(type="unknown")],
            [route(cluster=None)],
            [route(name="")],
        ):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                RENDER.endpoints(inventory, ["example.com"])

    def test_equivalent_duplicates_are_collapsed(self):
        self.assertEqual(len(RENDER.endpoints([route(), route()], ["example.com"])), 1)

    def test_invalid_urls_fail(self):
        for url in (
            "",
            "https://",
            "ftp://media.example.com",
            "https://user:password@media.example.com",
            "https://media.example.com/a b",
            "https://media.example.com:70000",
            "https://media.example.com/#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                RENDER.endpoints([route(monitor=url)], ["example.com"])

    def test_alert_policy_comes_from_inventory(self):
        probe = RENDER.endpoints([route(alerts="false")], ["example.com"])[0]
        self.assertEqual(probe["alerts"], [])
        self.assertEqual(
            RENDER.endpoints([route(alerts="true")], ["example.com"])[0]["alerts"],
            [{"type": "email"}],
        )
        with self.assertRaises(ValueError):
            RENDER.endpoints([route(alerts="typo")], ["example.com"])

    def test_route_and_static_monitor_conditions(self):
        probes = RENDER.endpoints(
            [
                route(),
                route(
                    cluster=None,
                    monitor="http://nas.example.com:8080",
                    name="NAS",
                    type="machine",
                ),
            ],
            ["example.com"],
        )
        self.assertEqual(
            [probe["group"] for probe in probes], ["example.com", "example.com"]
        )
        self.assertFalse(any("CERTIFICATE" in item for item in probes[1]["conditions"]))
        self.assertIn("[CERTIFICATE_EXPIRATION] > 168h", probes[0]["conditions"])
        self.assertEqual(probes[1]["alerts"], [{"type": "email"}])


class InfrastructureTest(unittest.TestCase):
    def test_provider_public_node_uses_owning_cluster_dns(self):
        inventory = {
            "machines": {
                "new": {
                    "worker": {
                        "oci": {"assign_public_ip": True},
                        "type": "vm",
                    }
                }
            },
            "types": {"vm": "Servers"},
        }
        probes = RENDER.infrastructure_endpoints(
            inventory,
            "example.net",
            {"new": {"api_node": "control", "public_node": "worker"}},
            "example.dev",
        )
        self.assertEqual(
            [(p["group"], p["name"], p["url"]) for p in probes],
            [
                (
                    RENDER.CATEGORY_GROUP_PREFIX + "Servers (External)",
                    "new-worker",
                    "icmp://public.new.example.dev",
                ),
                (
                    RENDER.CATEGORY_GROUP_PREFIX + "Servers (Internal)",
                    "new-worker",
                    "icmp://worker.new.example.net",
                ),
            ],
        )

    def test_homelab_identity_reachability_and_exclusions(self):
        machines = {
            "mbk": {
                "backup": {"type": "backup", "public_ipv4": "192.0.2.1"},
                "desktop": {"type": "server", "monitoring": False},
                "laptop": {"platform": "macos"},
                "sensor": {"type": "appliance", "tailscale": {"enabled": False}},
                "server": {"hostname": "renamed", "type": "custom"},
            }
        }
        inventory = {
            "machines": machines,
            "types": {
                "appliance": "Appliances",
                "backup": "Servers",
                "custom": "Custom",
                "server": "Servers",
            },
        }
        probes = RENDER.infrastructure_endpoints(
            inventory, "example.net", {}, "example.dev"
        )
        self.assertEqual(
            [probe["url"] for probe in probes],
            [
                "icmp://renamed.mbk.example.net",
                "icmp://192.0.2.1",
                "icmp://backup.mbk.example.net",
            ],
        )
        self.assertEqual(
            probes[1]["group"], RENDER.CATEGORY_GROUP_PREFIX + "Servers (External)"
        )
        self.assertEqual(
            probes[0]["group"], RENDER.CATEGORY_GROUP_PREFIX + "Custom (Internal)"
        )
        self.assertEqual(probes[0]["name"], "mbk-renamed")
        self.assertEqual(
            probes[1]["conditions"], ["[CONNECTED] == true", "[RESPONSE_TIME] < 5000"]
        )


class MachineServicesTest(unittest.TestCase):
    def test_only_declared_services_are_monitored(self):
        inventory = {
            "machines": {
                "lab": {
                    "storage": {
                        "hostname": "renamed",
                        "services": {
                            "management": {
                                "monitoring": True,
                                "name": "Console",
                                "port": 8443,
                                "scheme": "https",
                            },
                            "sync": {
                                "hostname": "sync.renamed.lab.example.net",
                                "name": "Sync",
                                "monitoring": True,
                                "scheme": "http",
                                "port": 80,
                            },
                            "hidden": {"scheme": "http", "port": 1234},
                        },
                    },
                    "offline": {
                        "monitoring": False,
                        "services": {
                            "management": {
                                "monitoring": True,
                                "port": 443,
                                "scheme": "https",
                            }
                        },
                    },
                }
            }
        }
        entries = RENDER.machine_service_inventory(inventory["machines"], "example.net")
        self.assertEqual(
            {entry["name"]: entry["monitor"] for entry in entries},
            {
                "Console": "https://renamed.lab.example.net:8443",
                "Sync": "http://sync.renamed.lab.example.net",
            },
        )
        self.assertFalse(any(entry["type"] == "homepage" for entry in entries))


class MonitoringCredentialsTest(unittest.TestCase):
    def test_explicit_headers_follow_external_secret_references(self):
        inventory = [
            route(
                namespace="example",
                headers={
                    "x-gatus-token": {"name": "credentials", "key": "monitoring-token"}
                },
                cloudflareProxied="true",
                hostnames=["media.example.com"],
            )
        ]
        resources = [
            {
                "kind": "ClusterSecretStore",
                "metadata": {"name": "onepassword"},
                "spec": {"provider": {"onepassword": {"vaults": {"vault-id": 1}}}},
            },
            {
                "kind": "ExternalSecret",
                "metadata": {"name": "source", "namespace": "example"},
                "spec": {
                    "secretStoreRef": {
                        "kind": "ClusterSecretStore",
                        "name": "onepassword",
                    },
                    "target": {"name": "credentials"},
                    "data": [
                        {
                            "secretKey": "monitoring-token",
                            "remoteRef": {
                                "key": "Example App",
                                "property": "monitoring-token",
                            },
                        }
                    ],
                },
            },
            {
                "kind": "CloudflareWAFPolicy",
                "metadata": {"name": "example", "namespace": "example"},
                "spec": {
                    "rule": {
                        "enabled": True,
                        "expression": 'not any(http.request.headers["x-gatus-token"][*] eq "{{ example:credentials:monitoring-token }}")',
                    }
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            manifests = Path(directory)
            apps = manifests / "apps/overlays/mbk.yaml"
            platform = manifests / "clusters/mbk/platform.yaml"
            apps.parent.mkdir(parents=True)
            platform.parent.mkdir(parents=True)
            apps.write_text(yaml.safe_dump_all(resources[1:]))
            platform.write_text(yaml.safe_dump(resources[0]))
            headers, secrets = RENDER.monitoring_credentials(inventory, manifests)
            self.assertEqual(
                list(secrets.values()), ["op://vault-id/Example App/monitoring-token"]
            )
            self.assertEqual(
                headers[route()["monitor"]]["x-gatus-token"],
                "${" + next(iter(secrets)) + "}",
            )
            # A different app is discovered from declarations without a Fly-side entry.
            resources[1]["spec"]["data"][0]["remoteRef"]["key"] = "Another App"
            apps.write_text(yaml.safe_dump_all(resources[1:]))
            _, changed = RENDER.monitoring_credentials(inventory, manifests)
            self.assertEqual(
                list(changed.values()), ["op://vault-id/Another App/monitoring-token"]
            )
            self.assertNotEqual(set(secrets), set(changed))
            # Header credentials cannot leave the declaring route's hostnames.
            unrelated = [dict(inventory[0], monitor="https://elsewhere.example.com")]
            with self.assertRaises(ValueError):
                RENDER.monitoring_credentials(unrelated, manifests)
            # Private routes can explicitly request credentials too; WAF syntax is irrelevant.
            private = [dict(inventory[0], cloudflareProxied="false")]
            self.assertEqual(
                RENDER.monitoring_credentials(private, manifests)[1], changed
            )
            resources[2]["spec"]["rule"]["expression"] = "arbitrary WAF policy"
            resources[2]["spec"]["rule"]["enabled"] = False
            apps.write_text(yaml.safe_dump_all(resources[1:]))
            self.assertEqual(
                RENDER.monitoring_credentials(inventory, manifests)[1], changed
            )
            self.assertEqual(
                RENDER.monitoring_credentials(
                    [dict(inventory[0], headers={})], manifests
                ),
                ({}, {}),
            )
            resources[1]["spec"]["target"]["template"] = {
                "data": {"token": "transformed"}
            }
            apps.write_text(yaml.safe_dump_all(resources[1:]))
            with self.assertRaises(ValueError):
                RENDER.monitoring_credentials(inventory, manifests)


class OrderingTest(unittest.TestCase):
    def test_domain_boundary_and_longest_matching_zone(self):
        self.assertEqual(
            RENDER.domain_group(
                "https://app.sub.example.com", ["example.com", "sub.example.com"]
            ),
            "sub.example.com",
        )
        with self.assertRaises(ValueError):
            RENDER.domain_group("https://notexample.com", ["example.com"])

    def test_domains_and_names_are_sorted_and_clusters_distinguish_names(self):
        probes = RENDER.endpoints(
            [
                route(cluster="syd", monitor="https://media.syd.example.com"),
                route(),
                route(name="Actual (MBK)", monitor="https://actual.example.com"),
                route(name="AI", monitor="https://ai.example.com"),
                route(name="Private", monitor="https://private.example.net"),
            ],
            ["example.com", "example.net"],
        )
        self.assertEqual(
            [(p["group"], p["name"]) for p in probes],
            [
                ("example.com", "Actual (MBK)"),
                ("example.com", "AI (MBK)"),
                ("example.com", "Media (MBK)"),
                ("example.com", "Media (SYD)"),
                ("example.net", "Private (MBK)"),
            ],
        )


class ProviderEndpointsTest(unittest.TestCase):
    def test_provider_urls_resolvers_and_domain_come_from_homelab(self):
        providers = {
            "providers": {
                "example": {
                    "name": "Example",
                    "url": "https://provider.example.com",
                    "conditions": ["[STATUS] == 200"],
                    "dns": {"query-type": "A", "url": "192.0.2.53"},
                }
            }
        }
        probes = RENDER.provider_endpoints(providers["providers"], "example.net")
        self.assertEqual(
            [probe["name"] for probe in probes], ["Example", "Example DNS"]
        )
        self.assertEqual(probes[0]["url"], "https://provider.example.com")
        self.assertEqual(probes[0]["conditions"], ["[STATUS] == 200"])
        self.assertEqual(probes[1]["url"], "192.0.2.53")
        self.assertEqual(
            probes[1]["dns"], {"query-name": "example.net", "query-type": "A"}
        )
        providers = {
            "providers": {
                "different": {
                    "name": "Different",
                    "url": "https://different.example.com",
                    "conditions": ["[STATUS] == 200"],
                }
            }
        }
        self.assertEqual(
            [
                probe["name"]
                for probe in RENDER.provider_endpoints(
                    providers["providers"], "example.net"
                )
            ],
            ["Different"],
        )
