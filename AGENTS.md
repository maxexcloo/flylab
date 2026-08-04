# AGENTS.md

## Structure

- Keep each service implementation in `<service>/`.
- Keep repository tooling generic; adding a service must not require changing shared workflow logic.
- Treat `.render/` as ephemeral deployment output.

## Secrets

- Resolve 1Password references only in GitHub Actions.
- Never write resolved secrets to logs, artifacts, or commits.

## Style

- Keep Python helpers and constants sorted; keep `main()` and its execution guard last.
- Prefer direct code and standard tools over repository-specific abstractions.
- Sort mise tools, tasks, workflow structure, Renovate rules, and Prek hooks consistently with the homelab repository.
- Use `.yaml`, never `.yml`.

## Verification

- Run `mise run check` before handoff.
