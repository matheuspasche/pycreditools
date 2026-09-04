## Agent skills

### Issue tracker

Issues live in GitHub Issues for `matheuspasche/pycreditools` (uses the `gh` CLI); external PRs are not a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Standard label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Output vocabulary

The engine speaks English — every emitted column name and every non-presentational value.
pt-BR is presentation and lives outside the core. Dead pt-BR names and the `Rating`/`rating`
duplicate are listed in `CONTEXT.md` § Language of the code.

## Tests

`pip install -e ".[dev]"` then `pytest tests --ignore=tests/studio` runs the engine
suite: **209 passed, 5 xfailed**. The five xfails are `strict` and pin the confirmed
`base_rate` rebuild bug (#133) — they are expected to stay red until the fix lands.

The Studio suite needs `pip install -e ".[dev,studio]"` (streamlit); `pytest tests`
then runs everything: **594 passed, 5 xfailed**, about 90s.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
