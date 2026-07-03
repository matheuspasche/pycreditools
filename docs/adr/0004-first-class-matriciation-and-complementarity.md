# ADR 0004 — Matriciation & complementarity as a first-class capability

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` (Score Evaluation + Risk Grouping pages), `studio/analyses.py` orchestration. No engine change.

## Context

In the real workflow a new score rarely **replaces** the vigente score immediately;
it first enters **matriciated** (repechage / matrix) alongside it. Reasons: (1)
**risk** — a higher-KS score from a new vendor may carry modelling bias; (2)
**contractual cost** of switching. So the owner must evaluate **complementarity**,
not isolated KS: two scores can both be strong yet so correlated that keeping the
vigente is better; a lower-KS score built on auxiliary information can complement
the existing view and raise final discriminatory power.

Technically, "matriciating" two scores in this package = **pairwise risk grouping**
(`fit_pairwise_risk_groups`): score1 × score2 → cells/ratings → approve/repechage by
cell. This is the same surface as critique 2.5 (open 5×5 matrix, select cells and
group by hand). So "should I matriciate?" and "build the matrix" are the two ends of
one thread.

## Decision

Treat matriciation as **first-class, realised across the two deep-dives**:

1. **Score Evaluation** gains a **complementarity mode** vs the vigente/in-use
   score: correlation, isolated KS vs combined KS, marginal lift, and a verdict
   hint (repechage / matriciate / replace).
2. **Risk Grouping** becomes the **editable matrix**: an open quantile grid (e.g.
   5×5) where the user can **select cells and group them by hand** (Excel-like) or
   run the algorithm. Matrices are shown **open**, not only clustered.
3. The resulting matrix/recipe **feeds the Bancada cutoffs** (the policy decides by
   cell/rating).

## Consequences

- Resolves critiques **2.5** and the score-comparison gap in the Concept section.
- Risk Grouping stops being clusters-only; the open matrix + manual grouping is new
  UI work over `RiskGroupResult` / `GroupingRecipe`.
- Complementarity metrics run **only on the short-list** ("scores em jogo", ADR
  0005) to bound compute.

## Related

ADR 0003, 0005.
