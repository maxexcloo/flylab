# AGENTS.md

## Secrets

- Resolve 1Password references only in GitHub Actions.

## Structure

- Keep the Gatus implementation and its `README.md` in `gatus/`.
- Treat `$FLYLAB_RENDER_DIRECTORY` (a temporary directory) as ephemeral deployment output.

## Style

- Keep Python `main()` and its execution guard last.

## Verification

- `mise run check` checks repository files offline.
- `mise run check:render` fetches public Homelab and Kubelab `main` and renders Gatus.
