# AGENTS.md

## Secrets

- Resolve 1Password references only in GitHub Actions.

## Structure

- Keep each service implementation and its `README.md` in `<service>/`.
- Keep repository tooling generic; adding a service must not require changing shared workflow logic.
- Treat `$FLYLAB_RENDER_DIRECTORY` (a temporary directory) as ephemeral deployment output.

## Style

- Keep Python `main()` and its execution guard last.

## Verification

- `mise run check:static` checks repository files and runs tests offline.
- `mise run check:render` fetches public Homelab and Kubelab `main` and renders every service.
- `mise run check` runs both.
