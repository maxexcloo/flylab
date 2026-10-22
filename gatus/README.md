# Gatus

External monitoring for my homelab, running on Fly.io at `status.excloo.com`.
The [Images repository](https://github.com/maxexcloo/images) builds the shared
Gatus/Tailscale base; Flylab adds the generated monitoring configuration and a
startup script.

## Inventory

`render.py` generates `services.yaml`, `infrastructure.yaml` and
`providers.yaml` in `app/config/`:

- Kubelab routes opt in with `monitoring.excloo.dev/enabled: "true"`, through
  Kubelab's `scripts/render_service_inventory.sh`.
- Homelab machine services opt in with `services.<name>.monitoring: true` in
  `data/machines.yaml`; typed machines get ICMP checks.
- Homelab `data/providers.yaml` entries with `conditions` or `dns` get provider
  probes.

Names and groups match Homepage. `settings.yaml` holds mail alerting and UI
settings.

## Credentials

Kubelab routes can declare monitoring headers with
`monitoring.excloo.dev/headers`. Kubelab resolves each Secret reference to a
1Password reference, and Flylab imports it as a hashed Fly secret.

`gatus/secrets.env` references the `Resend` and `Tailscale OAuth Client` items in
the Flylab vault, both managed by Homelab. Tailscale runs in the container so
Gatus can reach private services, registering an ephemeral `tag:fly` client on
each start.

Homelab and Kubelab dispatch this workflow after each validated push using the
Actions secret `HOMELAB_FLY_DEPLOY_TOKEN` (reference copy at
`op://Homelab/GitHub Actions/homelab-fly-deploy-token`; update both repositories
when rotating it). It only needs Actions write access to `maxexcloo/flylab`.

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
