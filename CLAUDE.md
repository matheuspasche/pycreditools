## Agent skills

### Issue tracker

Issues live in GitHub Issues for `matheuspasche/pycreditools` (uses the `gh` CLI); external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Standard label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Output vocabulary

The engine speaks English — every emitted column name and every non-presentational value.
pt-BR is presentation and lives outside the core. Dead pt-BR names and the `Rating`/`rating`
duplicate are listed in `CONTEXT.md` § Language of the code.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
