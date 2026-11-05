# Gatus

External monitoring for my homelab, running on Fly.io at `status.excloo.com`.
The [Images repository](https://github.com/maxexcloo/images) builds the shared
Gatus/Tailscale base; Flylab adds the generated monitoring configuration and a
startup script.

## Inventory

`render.py` generates `services.yaml`, `infrastructure.yaml`,
`providers.yaml` and `certificates.yaml` in `app/config/`:

- Kubelab routes opt in with `monitoring.excloo.dev/enabled: "true"`, through
  Kubelab's `scripts/render_service_inventory.sh`.
- Homelab machine services opt in with `services.<name>.monitoring: true` in
  `data/machines.yaml`; typed machines get ICMP checks.
- Homelab `data/providers.yaml` entries get provider probes unless they set
  `monitoring: false`, plus DNS probes when they declare `dns`.

Names and groups match Homepage. `settings.yaml` holds mail alerting, storage
and UI settings. Gatus keeps its history in SQLite on the `gatus_data` Fly
volume, which Flylab creates before deploying. The volume pins Gatus to one
machine.

## Alerting

`settings.yaml` emails after 10 consecutive failures and clears after 10
consecutive successes. Reminders stay disabled, so a check that stays down
alerts once. Response times must stay under 10 seconds. Provider probes also
accept `429`, so rate limits do not alert.

Every HTTPS probe checks certificate expiry with
`[CERTIFICATE_EXPIRATION] > 168h`. `certificates.yaml` adds `Certificate: <host>`
probes for certificates no service probe reaches: concrete dnsNames from
Kubelab's cert-manager `Certificate` resources, and HTTPS services on ACME
machines in Homelab that do not opt into monitoring.

## Credentials

Kubelab routes can declare monitoring headers with
`monitoring.excloo.dev/headers`. Kubelab resolves each Secret reference to a
1Password reference; rendering adds it to `fnox.toml` under a hashed name, and
Flylab imports it as a Fly secret. Routes behind a Kubelab Cloudflare Access application
also send the `Cloudflare Access Service Token` item, which Homelab manages.

`gatus/fnox.toml` references the `Resend` and `Tailscale OAuth Client` items in
the Flylab vault, both managed by Homelab. Tailscale runs in the container so
Gatus can reach private services, registering an ephemeral `tag:fly` client on
each start.

Homelab and Kubelab dispatch `deploy.yaml` after each validated push using the
Actions secret `FLYLAB_DISPATCH_TOKEN`, a fine-grained token with only Actions
write access to `maxexcloo/flylab`; update both repositories when rotating it.

## Rendering

Rendering fetches the public Homelab and Kubelab `main` branches. To pin
revisions or use local checkouts, which include uncommitted changes:

```shell
mise run render
HOMELAB_REVISION=<full-commit-sha> KUBELAB_REVISION=<full-commit-sha> mise run render
HOMELAB_DIRECTORY=../homelab KUBELAB_DIRECTORY=../kubelab mise run render
```

Manual workflow runs accept the same revisions as `homelab_revision` and
`kubelab_revision`.
