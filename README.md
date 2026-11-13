# Flylab

Fly.io services for my homelab. [Gatus](gatus/README.md) provides external
service and infrastructure monitoring derived from Homelab and Kubelab.

## Credentials

Set `OP_SERVICE_ACCOUNT_TOKEN` in GitHub Actions with read-only access to the
Flylab vault and the application vaults it needs. Keep the service account's
recovery copy in `Homelab/Connect Token: fly`.

## Deployment

Pushes to `main` deploy through the [deployment workflow](.github/workflows/deploy.yaml),
which removes Fly secrets not declared in the rendered `fnox.toml`.

Run the workflow manually without revision inputs after rotating a secret to
force deployment, even when the rendered configuration is unchanged.

## Development

Install the [shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks:

```shell
mise install
mise run check
mise run render
```

Rendering doesn't resolve secrets or deploy. It prints its output directory, a
new temporary directory unless `FLYLAB_RENDER_DIRECTORY` is set.

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
