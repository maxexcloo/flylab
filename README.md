# Homelab Fly.io

Independent Fly.io services for the homelab. Each service owns its native Fly
configuration, deployment settings and application files in a root directory.
`homelab` owns infrastructure and status-page DNS; `kubelab` owns application
routes and service metadata.

## Deployment Flow

1. Pushes to `main` deploy every directory containing `deployment.toml`. Manual
   runs can select a deployment key or Fly app name, or explicitly delete an app.
2. Each service is copied into `.render/`. An optional service-local `render.py`
   prepares generated application files without deployment credentials.
3. GitHub Actions resolves `secrets.env` references through a read-only 1Password
   service account. Values pass directly to Fly over standard input; they are
   never written to files or workflow artefacts.
4. The deployment reconciles certificates and secrets, deploys, checks health and
   reconciles machine count. Removed secret names are staged for removal.

Fly settings live in `<service>/fly.toml`; `deployment.toml` contains only its
selection key, certificates, machine count and required native Fly secret names. Adding a service does not require
changing shared workflow logic. The old `CONFIG` repository variable is unused.

## Development

Install jq separately (`brew install jq` on macOS), then use the pinned Mise tools:

```shell
mise install
mise run setup
mise run check
mise run render gatus
```

Rendering fetches public Homelab and Kubelab `main` into temporary directories and
records both commit SHAs in the output. To pin revisions or use local checkouts:

```shell
HOMELAB_REVISION=<full-commit-sha> KUBELAB_REVISION=<full-commit-sha> mise run render gatus
HOMELAB_DIRECTORY=../homelab KUBELAB_DIRECTORY=../kubelab mise run render gatus
```

Local checkout rendering includes uncommitted changes. These commands resolve no
secrets and make no deployment changes. Generated output stays under `.render/`;
`mise run cleanup` removes it. Use `mise run fmt` to format supported files.

## Gatus

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

The default UI sort remains `group`: domain groups first, then `External (...)`,
`Internal (...)` and `Providers`, alphabetically within each section. This order
comes from the group names, not the order of YAML files. The browser can retain a
user-selected sort or filter. Renaming groups or endpoints changes Gatus history
keys; the existing memory-only storage also resets on restart.

Gatus combines generated `infrastructure.yaml` and `services.yaml` with checked-in provider/DNS checks,
mail alerting and UI settings. URL-keyed `gatus/overrides.yaml` applies native Gatus
endpoint fields before generation; omitted URLs simply stop producing probes.
Overrides cannot rename or redirect a probe. HTTPS probes check certificate expiry;
HTTP probes omit that condition. Existing five-failure/five-recovery mail thresholds
are retained. Redlib retains its disabled alerts and `X-Gatus-Token` bypass.

Monitoring credentials are discovered from enabled `CloudflareWAFPolicy` header
comparisons and direct `ExternalSecret` data mappings in the rendered cluster
manifests. The corresponding `ClusterSecretStore` or `SecretStore` identifies the
1Password vault. Headers are added only to proxied routes in the policy's namespace
whose monitor hostname belongs to that route. Generated environment-variable names
and secret references live only in `.render/`; adding a protected app needs no
Fly-side credential entry. Secret-store selection must identify one vault, and
transformed Secret templates are rejected. Only GitHub Actions resolves values.
Obsolete catalogue URLs and old infrastructure names are no longer generated.

After a validated Homelab or Kubelab push, its workflow dispatches this repo with
that repository's exact commit SHA. Manual deployments accept `homelab_revision` and `kubelab_revision`;
blank inputs use current `main`. Source workflows refresh external monitoring
only; Homelab never applies infrastructure from CI. This tracks desired Git
configuration, not Flux readiness.

### Credentials & Activation

- **Fly**: `FLY_API_TOKEN` is a GitHub Actions secret here.
- **GitHub dispatch**: source workflows load `GH_WORKFLOW_TOKEN` from
  `op://Homelab/GitHub Actions/workflow-token` through the standard 1Password
  Action. Each source repo needs `OP_SERVICE_ACCOUNT_TOKEN` with read access to
  that vault. The GitHub token needs Actions write access only to
  `maxexcloo/homelab-fly`; it is not a Fly credential. Install this receiving
  workflow before the source-repository changes.
- **1Password**: `OP_SERVICE_ACCOUNT_TOKEN` reads the app vaults discovered from
  Kubelab. Give it read-only access to the cluster vaults; new apps within those
  vaults need no service-account changes.
- **Runtime**: `MAIL_PASSWORD` and `TAILSCALE_AUTH_KEY` are native Fly secrets,
  declared in `gatus/deployment.toml`. Deployment requires and preserves them.
  They are not fetched from the deleted legacy vault. Keep the mail credential
  sending-only.

Tailscale remains in the Fly container for private reachability. Deploying a new
inventory still requires working DNS, Tailscale grants and valid credentials;
an offline render cannot verify those. See [remaining activation checks](docs/plan.md).

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
