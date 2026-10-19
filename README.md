# Flylab

Independent Fly.io services for the homelab. Each service keeps its native Fly
configuration, deployment settings, application files and README in its own
root-level directory.

## Credentials

GitHub Actions keeps only `OP_SERVICE_ACCOUNT_TOKEN` as its bootstrap credential.
It reads the Fly deployment token from `op://Flylab/Fly.io/password` and resolves
service-specific 1Password references. Give the service account read-only access
to the Flylab vault and the required application vaults. The Fly token is used
only by deployment tooling; it is never passed into applications. Keep the
service-account recovery copy in `Homelab/Connect Token: fly`.
Services can also declare required native Fly secrets that deployment preserves.

## Deployment

1. Pushes to `main`, except Markdown-only changes, deploy every directory
   containing `deployment.toml`. Manual runs can select a service directory or Fly
   app name, or explicitly delete an app.
   Pull requests render every configured service. Deployment runs check repository
   files and tests, then render each selected service once using the requested
   inventory revisions before resolving credentials. Deletion skips inventory rendering.
2. Each service is copied into `$FLYLAB_RENDER_DIRECTORY` (set in `.mise.toml`).
   An optional service-local `render.py` prepares generated application files
   without deployment credentials. Its optional `requirements.txt` supplies renderer
   dependencies and is also used by its service tests.
3. GitHub Actions resolves `secrets.env` references through 1Password. Values pass
   directly to Fly over standard input; they are never written to files or
   workflow artefacts.
4. Deployment reconciles certificates and secrets, deploys and reconciles machine
   count. It waits for native Fly health checks to pass on every machine, including
   machines added after deployment. Secrets absent from
   both the generated references and required native secrets are staged for removal.

Fly settings live in `<service>/fly.toml`; `deployment.toml` declares the
certificates, machine count and required native Fly secret names. Adding a
service does not require changing shared workflow logic. Document its inputs,
credentials and operating requirements in `<service>/README.md`.

## Development

Install the [shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks:

```shell
mise install
mise run check
mise run render <service>
```

Checks discover shared tests in `tests/` and each configured service’s `tests/`,
using that service’s optional `requirements.txt`. Each service declares native
HTTP service health checks in `fly.toml`.

Rendering resolves no secrets and makes no deployment changes. Generated output
goes to `~/.cache/flylab/render/<service>`, outside the repository; `mise run cleanup`
removes it. Use `mise run fmt` to format supported files. See each service's README
for its rendering inputs.

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).

## Services

- [Gatus](gatus/README.md): external service and infrastructure monitoring derived
  from Homelab and Kubelab.
