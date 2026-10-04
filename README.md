# Homelab Fly.io

This repository owns the Fly.io service implementations deployed by the
[homelab](https://github.com/maxexcloo/homelab) configuration. Each service
lives in a root-level directory with its Fly configuration, templates, and
application files.

GitHub Actions renders deployments, resolves secrets through a read-only
1Password service account, and reconciles Fly apps without writing resolved
secrets to the repository or workflow artefacts.

`PLAN.md` contains only unfinished work.

## Deployment Flow

1. The homelab repository publishes non-secret Fly config through the
   `CONFIG` repository variable.
2. Pushes to `main` select every configured deployment; manual runs may select
   one deployment by key or app name.
3. Templates are rendered with gomplate, certificates and secrets are
   reconciled, and `flyctl` deploys and scales the app.
4. Manual runs may explicitly delete an app instead of deploying it.

## Repository Layout

- `.render/` — ephemeral rendered output; never committed.
- `<service>/` — application files and gomplate templates for one service.
- `.github/scripts/fly.py` — renders and reconciles Fly apps.
- `.github/scripts/select-deployments.py` — validates config and selects work.
- `.github/workflows/deploy.yaml` — checks and runs selected deployments.

The selected deployment is available to templates through `DEPLOYMENT`. Gatus
receives its generated endpoint configuration under `custom.gatus`.

## Development

```bash
mise run setup    # Install Git hooks
mise run check    # Run all repository checks
mise run fmt      # Format supported files
mise run cleanup  # Remove generated output and caches
```

To add a service, create its root directory, add its application and template
files, and configure the deployment in the homelab repository. Shared selection
and deployment code should remain service-agnostic.

## Licence

AGPL-3.0 - see [LICENSE](LICENSE).
