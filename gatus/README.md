# Gatus

External monitoring for the homelab, deployed on Fly.io. Homelab owns
infrastructure and status-page DNS; Kubelab owns application routes and service
metadata. See the [Flylab README](../README.md) for shared deployment tooling.

## Credentials

Monitoring headers are explicitly declared on Kubelab routes with
`monitoring.excloo.dev/headers`, a JSON mapping of header names to namespace-local
Secret `name` and `key` references. Direct ExternalSecret mappings and their
SecretStore identify the 1Password item and vault. WAF expressions are not parsed.
Credentials are restricted to the declaring route’s hostnames; transformed Secret
templates are rejected. Only GitHub Actions resolves values.

- **1Password**: `OP_SERVICE_ACCOUNT_TOKEN` reads the app vaults discovered from
  Kubelab. Give it read-only access to Flylab and the cluster vaults; new apps within those
  vaults need no service-account changes.
- **GitHub dispatch**: both source repositories use the Actions secret
  `HOMELAB_FLY_DEPLOY_TOKEN`. Keep its reference copy at
  `op://Homelab/GitHub Actions/homelab-fly-deploy-token` and update both repository
  secrets when rotating it. The token needs Actions write access only to
  `maxexcloo/flylab`; it is not a Fly credential.
- **Runtime**: `gatus/secrets.env` references the `Resend` and `Tailscale OAuth Client`
  items in the Flylab vault. Homelab manages the sending-only `RESEND_API_KEY` and scoped
  `TAILSCALE_OAUTH_CLIENT_SECRET`. Deployment imports both into Fly secrets.
  Tailscale obtains registration keys automatically for `tag:flylab`.

Tailscale runs in the Fly container for private reachability. Deploying a new
inventory still requires working DNS, Tailscale grants and valid credentials;
an offline render cannot verify those. Startup waits up to 60 seconds for Tailscale
to connect before starting Gatus; connection failure stops startup.

## Deployment

After a validated Homelab or Kubelab push, its workflow dispatches this repo with
that repository's exact commit SHA. Manual deployments accept `homelab_revision` and `kubelab_revision`;
blank inputs use current `main`. Source workflows refresh external monitoring
only; Homelab never applies infrastructure from CI. This tracks desired Git
configuration, not Flux readiness.

## Inventory

`gatus/render.py` runs Kubelab's `scripts/render_service_inventory.sh`.
Routes opt into monitoring with `monitoring.excloo.dev/enabled: "true"`, independently
of Homepage visibility. HTTPS checks derive from the primary route hostname;
optional `monitoring.excloo.dev/path` and `/url` override the probe target.
Homelab machine services opt in with `management.monitoring: true` or
`services.<name>.monitoring: true`; their scheme, port and optional display name
live beside the endpoint. Gatus's own hostname comes from `deployment.toml`.
No Homepage configuration, running cluster API or OpenTofu state is read.
Services are grouped by the longest matching Homelab DNS zone. Route names retain
cluster suffixes. Invalid URLs, conflicting duplicates and an empty route inventory
stop deployment.

Homelab's `data/machines.yaml` supplies machine identities, network locations,
types, display groups, monitoring eligibility, Tailscale eligibility and declared public addresses. `data/domains.yaml`
supplies the infrastructure DNS suffix; `data/dns/*.yaml` supplies service groups.
Typed, Tailscale-enabled machines receive internal ICMP checks using Homelab's
`<hostname>.<network>.<infrastructure-domain>` convention. Declared public IPs
receive separate external checks, preferring IPv4 when both families are present.
No OpenTofu state, provider credentials or resolved device addresses are read.
Untyped personal devices and Tailscale-disabled private devices are excluded;
machines with `monitoring: false` are also excluded. The `types` mapping in
Homelab supplies the display group for each machine type.

Homelab's `data/providers.yaml` supplies provider names, website URLs and optional
DNS resolver addresses. Kubelab uses the same entries for Homepage bookmarks.
DNS checks query Homelab's infrastructure domain. Provider website checks accept
HTTP 200, 401 or 403; resolver checks require a successful DNS response.

## Monitoring

The default UI sort is `group`: domain groups first, then `External (...)`,
`Internal (...)` and `Providers`, alphabetically within each section. This order
comes from the group names, not the order of YAML files. The browser can retain a
user-selected sort or filter. Renaming groups or endpoints changes Gatus history
keys; memory-only storage also resets on restart.

Gatus generates `infrastructure.yaml`, `providers.yaml` and `services.yaml` from
Homelab and Kubelab. Local configuration controls mail delivery, thresholds and
UI settings. HTTPS service probes check certificate expiry; HTTP probes omit
that condition. Mail alerts require five consecutive failures or recoveries.
Kubelab routes can set `monitoring.excloo.dev/alerts: "false"` to suppress their
alerts. Explicit header references are independent of the alert setting.

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

Display names use uppercase cluster suffixes for apps and lowercase
`network-hostname` names for machines. Probe targets retain their native DNS names.
