# Flylab

Independent Fly.io services for my homelab. Each service has its own top-level
directory with its native Fly configuration, deployment settings, application
files and README.

## Credentials

The only credential GitHub Actions stores is `OP_SERVICE_ACCOUNT_TOKEN`. With
it, the workflow reads the Fly deployment token from `op://Flylab/Fly.io/password`
and resolves each service's 1Password references. Give the service account
read-only access to the Flylab vault and the application vaults it needs. Only the
deployment tooling uses the Fly token, and it's never passed into applications.
Keep the service account's recovery copy in `Homelab/Connect Token: fly`.

## Deployment

1. Pushes to `main`, except Markdown-only changes, deploy every directory
   containing `deployment.toml`. Manual runs can select a service directory or Fly
   app name, or explicitly delete an app.
   Pull requests render every configured service. Deployment runs check the
   repository files, then render each selected service once from the requested
   inventory revisions before resolving credentials. Deletion skips inventory
   rendering.
2. Each service is copied into `$FLYLAB_RENDER_DIRECTORY`, isolated per CI job.
   A service can have its own `render.py` to generate application files without
   deployment credentials, plus a `requirements.txt` for the renderer's
   dependencies.
3. GitHub Actions resolves `secrets.env` references through 1Password. Values go
   straight to Fly over standard input and are never written to files or
   workflow artefacts.
4. Deployment reconciles certificates and secrets, deploys, then reconciles the
   machine count. It waits for native Fly health checks to pass on every machine,
   including machines added after deployment. Secrets missing from `secrets.env`
   are staged for removal.

Fly settings live in `<service>/fly.toml`, and `deployment.toml` declares the
certificates and machine count. Adding a service doesn't need any changes to the
shared workflow. Document its inputs, credentials and operating requirements in
`<service>/README.md`.

## Development

Install the [shared Mise configuration](https://github.com/maxexcloo/dotfiles#shared-tools--tasks)
before running local Mise tasks:

```shell
mise install
mise run check
mise run render <service>
```

Each service declares native HTTP service health checks in `fly.toml`.

Rendering doesn't resolve secrets or change deployments. Output goes to
a unique system temporary directory, printed after rendering. Set
`FLYLAB_RENDER_DIRECTORY` explicitly to reuse a chosen output directory;
`FLYLAB_RENDER_DIRECTORY=<output-directory> mise run cleanup` removes it.
Rendering checks clean up their output automatically. Use `mise run fmt` to format supported files. See
each service's README for its rendering inputs.

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).

## Services

- [Gatus](gatus/README.md): external service and infrastructure monitoring derived
  from Homelab and Kubelab.
