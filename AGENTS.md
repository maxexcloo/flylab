# AGENTS.md

## Structure

- Keep each service implementation and its `README.md` in `<service>/`.
- Keep repository-wide documentation in the root `AGENTS.md` and `README.md`;
  keep service documentation in its README.
- Keep repository tooling generic; adding a service must not require changing shared workflow logic.
- Treat `.render/` as ephemeral deployment output.

## Secrets

- Resolve 1Password references only in GitHub Actions.
- Never write resolved secrets to logs, artefacts, or commits.

## Style

- Keep Python helpers and constants sorted; keep `main()` and its execution guard last.
