# Gatus

External monitoring for my homelab at [status.excloo.com](https://status.excloo.com).
The [Images repository](https://github.com/maxexcloo/images) owns the shared
Gatus/Tailscale image.

## Inventory

Monitoring is configured in the source repositories:

- Kubelab routes opt in with `monitoring.excloo.dev/enabled: "true"`.
- Homelab machine services opt in with `services.<name>.monitoring: true` in
  `data/machines.yaml`; typed machines get ICMP checks.
- Homelab `data/providers.yaml` entries get provider probes unless they set
  `monitoring: false`. Entries declaring `dns` also get DNS probes.

Service names and groups match Homepage. Certificate coverage is derived from
Kubelab certificates and Homelab ACME services by the [renderer](render.py).
Gatus keeps its history in SQLite on a Fly volume, pinning it to one machine.

## Alerting

Email alerting, storage and UI settings live in
[`settings.yaml`](app/config/settings.yaml). Probe conditions, including
certificate expiry checks, live in the [renderer](render.py).

## Credentials

Kubelab routes can declare monitoring headers with
`monitoring.excloo.dev/headers`, using Secret references backed by 1Password.
Routes behind a Kubelab Cloudflare Access application use the
`Cloudflare Access Service Token` item, which Homelab manages.

[`fnox.toml`](fnox.toml) references the `Resend` and `Tailscale OAuth Client`
items in the Flylab vault, both managed by Homelab. Tailscale lets Gatus reach
private services.

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
