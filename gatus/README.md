# Gatus

External monitoring for my homelab, running on Fly.io. Infrastructure and
status-page DNS come from Homelab, and application routes and service metadata
come from Kubelab. The [Flylab README](../README.md) covers the shared deployment
tooling.

The [Images repository](https://github.com/maxexcloo/images) builds the shared
Gatus/Tailscale base. Flylab pins its published release tag and adds the
generated monitoring configuration and a startup script that handles
credentials.

## Credentials

Kubelab routes declare monitoring headers with `monitoring.excloo.dev/headers`,
a JSON map of header names to Secret `name` and `key` references in the same
namespace. Kubelab's service inventory follows each reference through its
ExternalSecret and SecretStore to a 1Password reference, and only sends those
headers to the declaring route's hostnames. Flylab stores each reference as a
hashed Fly secret name. WAF expressions aren't parsed. Only GitHub Actions
resolves the values.

`OP_SERVICE_ACCOUNT_TOKEN` reads the app vaults discovered from Kubelab. Give it
read-only access to Flylab and the cluster vaults; new apps in those vaults don't
need any service account changes.

For GitHub dispatch, both source repositories use the Actions secret
`HOMELAB_FLY_DEPLOY_TOKEN`. Keep its reference copy at
`op://Homelab/GitHub Actions/homelab-fly-deploy-token` and update both repository
secrets when you rotate it. The token only needs Actions write access to
`maxexcloo/flylab`. It isn't a Fly credential.

At runtime, `gatus/secrets.env` references the `Resend` and
`Tailscale OAuth Client` items in the Flylab vault. Homelab manages the
sending-only `RESEND_API_KEY` and the scoped `TAILSCALE_OAUTH_CLIENT_SECRET`, and
deployment imports both into Fly secrets. Tailscale gets registration keys for
`tag:fly` automatically.

Tailscale runs in the Fly container so Gatus can reach private services. Each
deployment registers an ephemeral client, and Tailscale removes old clients once
they go offline. Client addresses can change, and deployments can briefly overlap
in the admin console. Deploying a new inventory still needs working DNS,
Tailscale grants and valid credentials, which an offline render can't check.
Startup waits up to 60 seconds for Tailscale to connect before starting Gatus and
stops if it can't connect.

## Deployment

After a validated Homelab or Kubelab push, that repository's workflow dispatches
this one with its exact commit SHA. Manual deployments accept `homelab_revision`
and `kubelab_revision`, and blank inputs use the current `main`. The source
workflows only refresh external monitoring; Homelab never applies infrastructure
from CI. Monitoring follows the desired configuration in Git, so it doesn't wait
for Flux to be ready.

## Inventory

`gatus/render.py` runs Kubelab's `scripts/render_service_inventory.sh`.
Routes opt into monitoring with `monitoring.excloo.dev/enabled: "true"`, separately
from Homepage visibility. HTTPS checks use the primary route hostname, and the
optional `monitoring.excloo.dev/path` and `/url` override the probe target.
Homelab machine services opt in with `services.<name>.monitoring: true`, with
their scheme, port and optional display name beside the endpoint. Management
consoles use `services.management`. Gatus's own hostname comes from
`deployment.toml`. The render doesn't read Homepage configuration, a running
cluster API or OpenTofu state.

Services use their Homepage group, so Gatus and Homepage share categories, and
Gatus itself appears under `Operations`. Names end with Homepage's location tag:
`<cluster>/<node>` for routes, `<network>-<hostname>` for machine services and
`fly` for Gatus. Route placement comes from required workload node selectors and
affinity, using Homelab's `external` public node and `internal` other nodes.
Routes that only prefer a node keep the bare cluster tag. Invalid URLs,
conflicting duplicates or an empty route inventory stop the deployment.

Homelab's `data/machines.yaml` supplies machine identities, network locations,
types, display groups, whether a machine is monitored or on Tailscale, and
declared public addresses. `data/domains.yaml` supplies the infrastructure DNS
suffix.

Typed machines with Tailscale get internal ICMP checks using Homelab's
`<hostname>.<network>.<infrastructure-domain>` convention. Declared public IPs get
separate external checks, preferring IPv4 when a machine has both. Public cluster
nodes with provider-assigned addresses use Homelab's
`public.<cluster>.<service-domain>` DNS record, which follows the cluster's public
node selection. OpenTofu state, provider credentials and resolved device
addresses aren't read. Untyped personal devices, private devices without
Tailscale and machines with `monitoring: false` are left out. Machine checks share
the `Servers` group, matching Homepage's tab, and use Homepage's
`network-hostname` group names. External checks add an `(External)` suffix.

Homelab's `data/providers.yaml` holds provider bookmarks, widget templates and
native Gatus probe settings in top-level `alerts`, `conditions` and `dns` fields.
A provider with `conditions` gets a website probe using its name and URL. `dns`
declares a separate DNS probe, and the query name defaults to Homelab's
infrastructure domain. Kubelab uses the same inventory for Homepage.

## Monitoring

The default UI sort is `group`, which orders groups alphabetically by name
instead of by YAML file order. The browser can remember a sort or filter you
picked. Renaming groups or endpoints changes Gatus history keys, and memory-only
storage resets on restart anyway.

Gatus generates `infrastructure.yaml`, `providers.yaml` and `services.yaml` from
Homelab and Kubelab. Local configuration controls mail delivery, thresholds and
UI settings. HTTPS service probes check certificate expiry, and HTTP probes skip
that condition. Mail alerts need five failures or recoveries in a row. Kubelab
routes can set `monitoring.excloo.dev/alerts: "false"` to silence their alerts.
Explicit header references work regardless of the alert setting.

## Rendering

Run these commands from the repository root.

Rendering fetches the public Homelab and Kubelab `main` branches into temporary
directories and records both commit SHAs in the output. To pin revisions or use
local checkouts:

```shell
mise run render gatus
HOMELAB_REVISION=<full-commit-sha> KUBELAB_REVISION=<full-commit-sha> mise run render gatus
HOMELAB_DIRECTORY=../homelab KUBELAB_DIRECTORY=../kubelab mise run render gatus
```

Rendering from local checkouts includes uncommitted changes. Probe targets keep
their native DNS names.
