# ADR 0003 — Score-in-use is contextual; cutoff axis and PD calibration are bound together

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` + `studio/policy_builder.py`. No engine change.

## Context

Today there is a fixed `primary_score_col` role ("score principal") configured in
Ingestion. The owner's objection (critique 1.4): *"for each score I am evaluating,
the principal score is the one being evaluated right now. It makes no sense to
compute swap-in using score 5's cutoff with score 3's PDs."*

This is a real modelling hazard. The engine estimates swap-in PD via
`_estimate_swap_in_baseline_pd`, which calibrates on `policy.calibration_score_col`
(falling back to the active cutoff score). If the cutoff axis and
`calibration_score_col` diverge, the swap-in default rate is computed from a
**different** score than the one being cut — exactly the mistake the owner flags.

## Decision

- **Remove the fixed "score principal" role** from Ingestion.
- The **score-in-use is contextual**: it is whichever score is currently being
  evaluated/cut in the Bancada or a deep-dive, drawn from the "scores em jogo"
  short-list (ADR 0005).
- When a score is put in use, the studio **binds the cutoff axis and
  `calibration_score_col` together** to that same score — they can never diverge
  silently. (Builder responsibility; the engine already honours
  `calibration_score_col`.)
- Add an **optional** `vigente_score` role: the score the current policy runs on
  today, used purely as a comparison/complementarity reference (ADR 0004), not as
  the PD source for the candidate.

## Consequences

- Resolves critique **1.4**; eliminates the "score 5 cutoff with score 3 PD" class
  of error by construction.
- "Vigente" and "in use" are now clearly different concepts.
- The builder must set `calibration_score_col` whenever it sets/changes a cutoff
  score; covered by a unit test in `studio/`.

## Related

ADR 0002, 0004, 0005.
