# AGENTS.md

## Structure

- Keep each service implementation in `<service>/`.
- Keep only `AGENTS.md` and `README.md` as root Markdown files; put other project
  documentation in `docs/`.
- Keep repository tooling generic; adding a service must not require changing shared workflow logic.
- Treat `.render/` as ephemeral deployment output.

## Secrets

- Resolve 1Password references only in GitHub Actions.
- Never write resolved secrets to logs, artefacts, or commits.

## Style

- Keep Python helpers and constants sorted; keep `main()` and its execution guard last.
- Prefer direct code and standard tools over repository-specific abstractions.
- Sort unordered peer entries by value shape: simple or single-line values first,
  then structured or multiline values, alphabetically within each group.
- Sort unordered peer headings, lists, and table rows alphabetically. Preserve
  narrative, procedural, dependency, interface, priority, and chronological order.
- Sort mise tools, tasks, workflow structure, Renovate rules, and Prek hooks
  consistently with the homelab repository.
- Use `.yaml`, never `.yml`, for project-owned YAML files unless external tooling
  requires a fixed filename.
- Preserve `LICENSE` and its legal text; never relicense without explicit approval.
- Use Australian English throughout authored prose and every project-owned name,
  including identifiers, configuration keys, environment variables, paths, CLI
  commands, and options. Update every producer and consumer together; preserve only
  externally defined names and terminology.

## Verification

- Run `mise run check` before handoff.
