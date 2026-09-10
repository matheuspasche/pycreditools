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

### ADRs the v0.6 roadmap promises — declare what you decide

Gate 4 of the v0.6 release enumerates every promised ADR and checks the tree for
it, because three artifacts were once recorded as present by citation and all
three were absent. `scripts/check_artifact_gate.py` is that list. It does not
accept a mention: a card number appearing in prose, or in another ADR's
`Consumes` line, is not that ADR. Measured before the check was written, `#117`
appeared in `docs/adr/` five times, in all five as a card some *other* ADR
consumes, and zero times as an ADR deciding it.

**So an ADR must declare its promise, in one of two forms:**

- `- **Tickets:** #131 (this ADR). Consumes …` — the house style already in use
  (ADRs 0010, 0012, 0013, 0014). Use it for any ADR that has a card.
- `- **Decides:** layout` — for the two promises with no card of their own: the
  layout ADR (whose number 0012 the output contract took) and the ADR of *"the
  choice criterion is not the package's"*.

Ticket 1 (#157) writes seventeen of these. Run
`python3 scripts/check_artifact_gate.py` to see which are still missing —
without the declaration line, a written ADR still reads as absent.

### Domain docs

Single-context layout — one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
