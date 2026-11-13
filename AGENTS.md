# AGENTS.md

## Secrets

- Resolve 1Password references only in GitHub Actions.

## Structure

- Keep the Gatus implementation and its `README.md` in `gatus/`.

## Style

- Keep Python `main()` and its execution guard last.

## Verification

- `mise run check` checks repository files offline.
- `mise run render` renders Gatus, which needs network access.
