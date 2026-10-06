import copy
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
        "group": "Media",
        "monitor": "https://media.example.com",
        "name": "Media",
        "source": "HTTPRoute/media/media",
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
                RENDER.endpoints([route(), entry], {}, ["example.com"])

    def test_empty_and_unsupported_inventories_fail(self):
        for inventory in (
            [],
            [route(type="homepage")],
            [route(), route(type="unknown")],
            [route(cluster=None)],
            [route(name="")],
        ):
            with self.subTest(inventory=inventory), self.assertRaises(ValueError):
                RENDER.endpoints(inventory, {}, ["example.com"])

    def test_equivalent_duplicates_are_collapsed(self):
        self.assertEqual(
            len(RENDER.endpoints([route(), route()], {}, ["example.com"])), 1
        )

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
                RENDER.endpoints([route(monitor=url)], {}, ["example.com"])

    def test_override_keeps_secret_reference_and_disabled_alerts(self):
        overrides = {
            "https://media.example.com": {
                "alerts": [],
                "headers": {"X-Gatus-Token": "${GATUS_HEADER_EXAMPLE}"},
            }
        }
        before = copy.deepcopy(overrides)
        probe = RENDER.endpoints([route()], overrides, ["example.com"])[0]
        self.assertEqual(probe["alerts"], [])
        self.assertEqual(probe["headers"], overrides[probe["url"]]["headers"])
        self.assertEqual(overrides, before)

    def test_overrides_cannot_change_identity(self):
        with self.assertRaises(ValueError):
            RENDER.endpoints(
                [route()],
                {route()["monitor"]: {"url": "http://other"}},
                ["example.com"],
            )

    def test_route_and_static_monitor_conditions(self):
        probes = RENDER.endpoints(
            [
                route(),
                route(
                    cluster=None,
                    group="Appliances",
                    monitor="http://nas.example.com:8080",
                    name="NAS",
                    type="homepage",
                ),
            ],
            {},
            ["example.com"],
        )
        self.assertEqual(
            [probe["group"] for probe in probes], ["example.com", "example.com"]
        )
        self.assertFalse(any("CERTIFICATE" in item for item in probes[1]["conditions"]))
        self.assertIn("[CERTIFICATE_EXPIRATION] > 168h", probes[0]["conditions"])
        self.assertEqual(probes[1]["alerts"], [{"type": "email"}])


class InfrastructureTest(unittest.TestCase):
    def test_homelab_identity_reachability_and_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            (repository / "data").mkdir()
            (repository / "data/domains.yaml").write_text(
                "domains:\n  infrastructure: example.net\n"
            )
            machines = {
                "mbk": {
                    "backup": {"type": "backup", "public_ipv4": "192.0.2.1"},
                    "desktop": {"type": "server"},
                    "laptop": {"platform": "macos"},
                    "sensor": {"type": "appliance", "tailscale": {"enabled": False}},
                    "server": {
                        "hostname": "renamed",
                        "type": "vm",
                        "tailscale": {"network_prefix": False},
                    },
                },
            }
            (repository / "data/machines.yaml").write_text(
                yaml.safe_dump({"machines": machines})
            )
            probes = RENDER.infrastructure_endpoints(
                repository,
                {
                    "icmp://desktop.mbk.example.net": {"enabled": False},
                },
            )
            self.assertEqual(
                [probe["url"] for probe in probes],
                [
                    "icmp://192.0.2.1",
                    "icmp://backup.mbk.example.net",
                    "icmp://renamed.mbk.example.net",
                ],
            )
            self.assertEqual(probes[0]["group"], "External (Servers)")
            self.assertEqual(probes[2]["name"], "renamed (mbk)")
            self.assertEqual(
                probes[2]["conditions"],
                ["[CONNECTED] == true", "[RESPONSE_TIME] < 5000"],
            )


class MonitoringCredentialsTest(unittest.TestCase):
    def test_discovery_follows_waf_and_external_secret_references(self):
        inventory = [
            route(
                namespace="example",
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
            # Never send the credential to an unrelated monitor host.
            unrelated = [dict(inventory[0], monitor="https://elsewhere.example.com")]
            self.assertEqual(
                RENDER.monitoring_credentials(unrelated, manifests), ({}, {})
            )
            private = [dict(inventory[0], cloudflareProxied="false")]
            self.assertEqual(
                RENDER.monitoring_credentials(private, manifests), ({}, {})
            )
            resources[2]["spec"]["rule"]["enabled"] = False
            apps.write_text(yaml.safe_dump_all(resources[1:]))
            self.assertEqual(
                RENDER.monitoring_credentials(inventory, manifests), ({}, {})
            )
            resources[2]["spec"]["rule"]["enabled"] = True
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
                route(name="Actual", monitor="https://actual.example.com"),
                route(name="AI", monitor="https://ai.example.com"),
                route(name="Private", monitor="https://private.example.net"),
            ],
            {},
            ["example.com", "example.net"],
        )
        self.assertEqual(
            [(p["group"], p["name"]) for p in probes],
            [
                ("example.com", "Actual (mbk)"),
                ("example.com", "AI (mbk)"),
                ("example.com", "Media (mbk)"),
                ("example.com", "Media (syd)"),
                ("example.net", "Private (mbk)"),
            ],
        )
