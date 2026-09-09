## Agent skills

### Issue tracker

Issues live in GitHub Issues for `matheuspasche/pycreditools` (uses the `gh` CLI); external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Standard label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Output vocabulary

The engine speaks English — every emitted column name and every non-presentational value.
pt-BR is presentation and lives outside the core. Dead pt-BR names and the `Rating`/`rating`
duplicate are listed in `CONTEXT.md` § Language of the code.

### Branch and PR flow for the v0.6 map

**One ticket per branch, and every branch ends in a PR against `release/v0.6`.**
Never commit a ticket straight onto `release/v0.6`. This is the default for the
whole of `docs/engine/spec/v06-tickets.md`, not a per-ticket choice — owner's
ruling, 2026-09-09.

`release/v0.6` is the integration branch for the version; `main` carries the
released line. A ticket branch is cut from `release/v0.6`, and if it needs
anything that only `main` has, it merges `main` in rather than rebasing onto it.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
