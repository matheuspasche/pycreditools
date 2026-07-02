# ADR 0007 — Automatic Re-fit of the Risk Rating over Survivors

- **Status:** Accepted
- **Date:** 2026-07-02
- **Scope:** `studio/analyses.py` + `gui/pages/3_Bancada.py`. **MUST NOT touch the package engine.**
- **Clarifies:** ADR 0001 ("you cluster whoever survives the filters")

## Context

ADR 0001 established that the Bancada's risk clustering must operate on the population
that actually survives the filters, not the raw base. The first implementation
(issue #33) carried the risk rating as a **static recipe** fitted once in the Risk
Grouping page and stored in `StudioState.rating_result`. Moving a cutoff updated the
funnel and approval/default readouts, but the rating distribution still reflected the
original Risk Grouping population — not the current survivors. The loop promised by
ADR 0001 was incomplete.

## Decision

After every Bancada simulation, **re-derive the risk grouping automatically on the
survivors** (`survivor_population(sim)`) via `derive_survivor_rating(sim, roles)`.

- The new function lives in `studio/analyses.py` (no `import streamlit`) and calls
  the existing `fit_groups()` on the survivors with observed defaults.
- Returns `None` when preconditions are unmet (no `actual_default_col`, no score cols,
  fewer than 30 observed-default survivors, or if the clustering engine raises), so
  the Bancada degrades gracefully.
- `_render_depth_section` in the Bancada skin now uses the re-derived rating (and its
  labels, re-computed via `label_ratings_by_pd`) instead of `state.rating_result`.
- A badge caption clarifies that the rating labels (A, B, …) are **relative to the
  current survivor population**, so the user understands that "A" in one filter
  configuration is not the same cohort as "A" in another.

## Consequences

- **Rating labels are population-relative.** "Rating A" now means "lowest-PD tier
  among the current survivors", not a fixed tier anchored to the Risk Grouping page's
  population. Comparing two policies by rating label is misleading; comparisons
  should use approval rate and default rate instead.
- **No extra button.** The re-fit is silent and automatic; moving any cutoff or filter
  triggers a re-simulation which in turn triggers a re-fit.
- **The static `state.rating_result`** from Risk Grouping is no longer used for the
  Bancada's risk tier distribution. It is retained for other flows (deployment,
  decision preview) that rely on a stable, pre-approved recipe.
- **Performance:** re-fitting on survivors adds a `fit_groups()` call per simulation.
  With the default `bins=10, max_groups=5` the overhead is small on typical
  sample sizes.

## Related

- ADR 0001 (central Bancada), ADR 0004 (open matrix / matriciation).
- Implementation: `studio/analyses.py:derive_survivor_rating`,
  `gui/pages/3_Bancada.py:_render_depth_section`.
- Parity tests: `tests/studio/parity/test_bancada.py` — `derive_survivor_rating_*` group.
