# Flylab

Fly.io services for my homelab. [Gatus](gatus/README.md) provides external
service and infrastructure monitoring derived from Homelab and Kubelab.

## Credentials

The only credential GitHub Actions stores is `OP_SERVICE_ACCOUNT_TOKEN`. With
it, the workflow reads the Fly deployment token from `op://Flylab/Fly.io/password`
and resolves `gatus/secrets.env`. Give the service account read-only access to
the Flylab vault and the application vaults it needs. Keep the service account's
recovery copy in `Homelab/Connect Token: fly`.

## Deployment

Pull requests check and render Gatus. Pushes to `main`, except Markdown-only
changes, also deploy it: the workflow renders before resolving credentials,
reconciles certificates from `gatus/deployment.toml` and secrets from
`gatus/secrets.env`, then runs `flyctl deploy`. Secret values go straight to Fly
over standard input, and secrets missing from `secrets.env` are removed.

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
