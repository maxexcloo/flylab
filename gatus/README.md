# Gatus

External monitoring for the homelab, deployed on Fly.io. Homelab owns
infrastructure and status-page DNS; Kubelab owns application routes and service
metadata. See the [Flylab README](../README.md) for shared deployment tooling.

## Credentials

Monitoring credentials are discovered from enabled `CloudflareWAFPolicy` header
comparisons and direct `ExternalSecret` data mappings in the rendered cluster
manifests. The corresponding `ClusterSecretStore` or `SecretStore` identifies the
1Password vault. Headers are added only to proxied routes in the policy's namespace
whose monitor hostname belongs to that route. Generated environment-variable names
and secret references live only in `.render/`; adding a protected app needs no
Fly-side credential entry. Secret-store selection must identify one vault, and
transformed Secret templates are rejected. Only GitHub Actions resolves values.

- **1Password**: `OP_SERVICE_ACCOUNT_TOKEN` reads the app vaults discovered from
  Kubelab. Give it read-only access to the cluster vaults; new apps within those
  vaults need no service-account changes.
- **GitHub dispatch**: both source repositories use the Actions secret
  `HOMELAB_FLY_DEPLOY_TOKEN`. Keep its reference copy at
  `op://Homelab/GitHub Actions/homelab-fly-deploy-token` and update both repository
  secrets when rotating it. The token needs Actions write access only to
  `maxexcloo/flylab`; it is not a Fly credential.
- **Runtime**: `MAIL_PASSWORD` and `TAILSCALE_AUTH_KEY` are native Fly secrets,
  declared in `gatus/deployment.toml`. Deployment requires and preserves them.
  Keep the mail credential sending-only.

Tailscale runs in the Fly container for private reachability. Deploying a new
inventory still requires working DNS, Tailscale grants and valid credentials;
an offline render cannot verify those. See [remaining activation checks](../docs/plan.md).

## Deployment

After a validated Homelab or Kubelab push, its workflow dispatches this repo with
that repository's exact commit SHA. Manual deployments accept `homelab_revision` and `kubelab_revision`;
blank inputs use current `main`. Source workflows refresh external monitoring
only; Homelab never applies infrastructure from CI. This tracks desired Git
configuration, not Flux readiness.

## Inventory

`gatus/render.py` runs Kubelab's `scripts/render_service_inventory.sh --include-static`.
The inventory derives monitors from rendered HTTPRoutes, supported HelmRelease
routes and Homepage's static `siteMonitor` entries. Kubelab's Homepage resolver
expands machine references using the same Homelab checkout selected for this
deployment, so links, widget URLs and checks share Homelab's endpoint declarations. No running cluster or Homepage
API is required. Services are grouped by their longest matching Homelab DNS zone.
Route names include their current cluster, for example `Grafana (mbk)` and
`Grafana (syd)`. Missing metadata, unknown DNS zones, invalid URLs, conflicting
duplicates and an empty route inventory stop deployment.

Homelab's `data/machines.yaml` supplies machine identities, network locations,
types, Tailscale eligibility and declared public addresses. `data/domains.yaml`
supplies the infrastructure DNS suffix; `data/dns/*.yaml` supplies service groups.
Typed, Tailscale-enabled machines receive internal ICMP checks using Homelab's
`<hostname>.<network>.<infrastructure-domain>` convention. Declared public IPs
receive separate external checks, preferring IPv4 when both families are present.
No OpenTofu state, provider credentials or resolved device addresses are read.
Untyped personal devices and Tailscale-disabled private devices are excluded;
Mandu is explicitly disabled in the overrides because it is an optional workstation.
The current baseline is eight internal machines and one external check.

## Monitoring

The default UI sort is `group`: domain groups first, then `External (...)`,
`Internal (...)` and `Providers`, alphabetically within each section. This order
comes from the group names, not the order of YAML files. The browser can retain a
user-selected sort or filter. Renaming groups or endpoints changes Gatus history
keys; memory-only storage also resets on restart.

Gatus combines generated `infrastructure.yaml` and `services.yaml` with checked-in provider/DNS checks,
mail alerting and UI settings. URL-keyed `gatus/overrides.yaml` applies native Gatus
endpoint fields before generation; omitted URLs simply stop producing probes.
Overrides cannot rename or redirect a probe. HTTPS probes check certificate expiry;
HTTP probes omit that condition. Mail alerts require five consecutive failures or recoveries. Redlib has disabled
alerts and uses the `X-Gatus-Token` bypass.

## Rendering

Run these commands from the repository root.

Rendering fetches public Homelab and Kubelab `main` into temporary directories and
records both commit SHAs in the output. To pin revisions or use local checkouts:

```shell
mise run render gatus
HOMELAB_REVISION=<full-commit-sha> KUBELAB_REVISION=<full-commit-sha> mise run render gatus
HOMELAB_DIRECTORY=../homelab KUBELAB_DIRECTORY=../kubelab mise run render gatus
```

Local checkout rendering includes uncommitted changes. These commands resolve no
secrets and make no deployment changes. Generated output stays under `.render/`;
`mise run cleanup` removes it. Use `mise run fmt` to format supported files.
