# Flylab

Fly.io services for my homelab. [Gatus](gatus/README.md) provides external
service and infrastructure monitoring derived from Homelab and Kubelab.

## Credentials

Set `OP_SERVICE_ACCOUNT_TOKEN` in GitHub Actions with read-only access to the
Flylab vault and the application vaults it needs. Keep the service account's
recovery copy in `Homelab/Connect Token: fly`. Credential references live in
[`fnox.toml`](fnox.toml) and [`gatus/fnox.toml`](gatus/fnox.toml).

## Deployment

The [deployment workflow](.github/workflows/deploy.yaml) checks pull requests and
deploys pushes to `main`, except Markdown-only changes. Deployment removes Fly
secrets not declared in the rendered `fnox.toml`.

Run the workflow manually without revision inputs after rotating a secret to
force deployment, even when the rendered configuration is unchanged.

## Development

Install the [shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks:

```shell
mise install
mise run check
mise run check:render
mise run render
```

Rendering doesn't resolve secrets or deploy. It prints its output directory, a
new temporary directory unless `FLYLAB_RENDER_DIRECTORY` is set.

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
