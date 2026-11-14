# Gatus

External monitoring for my homelab at [status.excloo.com](https://status.excloo.com).

## Inventory

Services opt in to monitoring in their source repositories:

- Kubelab routes opt in with `monitoring.excloo.dev/enabled: "true"`.
- Homelab machine services opt in with `services.<name>.monitoring: true` in
  `data/machines.yaml`; typed machines get ICMP checks.
- Homelab `data/providers.yaml` entries get provider probes unless they set
  `monitoring: false`. Entries declaring `dns` also get DNS probes.

## Credentials

Kubelab routes can declare monitoring headers with
`monitoring.excloo.dev/headers`, using Secret references backed by 1Password.
Routes behind a Kubelab Cloudflare Access application use the
`Cloudflare Access Service Token` item, which Homelab manages.

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
