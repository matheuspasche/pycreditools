# ADR 0005 — Suggestion-first Bancada and the "scores em jogo" short-list

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` (Score Evaluation gate + Bancada), `studio/analyses.py` (optimization as suggestion engine). No engine change.
- **Supersedes (partially):** PRD 07 (Cutoff Optimization) — no longer a standalone page.

## Context

The product principle the owner stated: *"our idea is always to suggest a policy and
the client tweaks our suggestions and picks the one they want."* And a compute
principle: after KS evaluation, only **2-3** of the ~10 candidate scores are
interesting (isolated or combined); it makes no sense to refine / spend compute on
all 10. Simulation, trade-off and optimization all serve **the same business pain**
(find a reasonable cutoff / scenario and see what happens).

## Decision

1. **Score short-list gate.** Score Evaluation lets the user mark **2-3 "scores em
   jogo"**. Only these flow into the Bancada and into any optimization/suggestion;
   the rest stay out of heavy compute.
2. **Suggestion-first Bancada.** Entering the Bancada with the scores em jogo, it
   **opens with 2-3 suggested policy scenarios** (e.g. conservative / neutral /
   aggressive, or by target default/approval) that the user selects and tweaks
   live. Manual calibration stays fully available.
3. **Optimization becomes the engine behind the suggestions** (grid search run
   **only on the scores em jogo**), not a standalone page.

## Consequences

- Resolves critiques **2.4** (Optimization "doesn't run / unsure if needed") and the
  "always suggest, client tweaks" concept.
- Bounds compute cost: heavy search runs on ≤3 scores, not 10.
- The Bancada needs a clear "these are suggestions — adjust freely" affordance so it
  is opinionated without being rigid.

## Related

ADR 0001, 0003, 0004.
