# ADR 0024 — The optimiser needs no business parameter: there is no concept, so there is no type

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** whether *"target"*, *"constraint"*, *"metric to optimise"* and *"tie-break rule"*
  are a type — and where selection lives if they are not. The **normative** half, *"the choice
  criterion is not the package's"*, is ADR 0025; the shape and count of the selection verbs is
  ADR 0013/0014.
- **Tickets:** #122 (this ADR). Consumes #83, #92, #113, #118, #123, #128, #140, #143,
  ADR 0004.
- **Spec:** the living engine spec, §4.8 (grid and selection).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The card was filed by the owner as **an open question, not a decision**: if a policy uses a
`tune()` marker to say *where* to sweep, something has to say *what is good* — and none of that
was determined.

What was known, measured:

- That *something* exists today **scattered as unnamed kwargs**: `target_default_rate=` on
  `optimize_cutoffs`, and #92 proposes four more (`targets=` per group, `target_metric=`,
  `target="incumbent"`, `target=lambda g: ...`). Several parameters fighting over a concept
  that has no type is a **signal** — not a proof — of a missing concept.
- In tidymodels the equivalent piece is separate from the spec and lives on the experiment side
  (`metric_set` + `select_best`).
- The fair-comparison argument (#83's family): comparing policy A and B is only sound if the
  choice criterion is identical for both. If the criterion travels inside each policy, the
  comparison mixes a delta of *rule* with a delta of *target* and nobody notices.

And one observation any shape had to accommodate: **the target is always in transformation.**
Each decision generates swap-ins, which move the resulting approval, which moves the default.
Not a bug — an implicit equation, which the sweep solves by search.

## Decision 1 — there is no concept to name, so no type is created

*Target*, *constraint*, *metric to optimise* and *tie-break rule* do not become one type, nor
four. **Appetite belongs to the human, not to the policy.** The several competing kwargs were a
symptom of responsibility in the wrong place, not of a missing type.

## Decision 2 — one engine; selection is a table→table layer

Owner's decision: `tradeoff` and `optimize` become one thing. One verb produces the grid (the
engine was already unified in v0.5 — both call `run_sweep`). **Selection receives the finished
grid and filters**: it does not see a `Study`, does not see the base, does not run a simulation,
and is testable without data.

With that, the engine parameters that leak into `optimize` today (`cutoff_steps`, `method`,
`parallel`) go away **by construction** — which is the real reason this split is a decision and
not tidiness.

## Decision 3 — the edge cases dissolve into filter semantics

They are not behaviour to specify:

- **No feasible point** → an empty table, with the full grid still available upstream, so *"how
  close did it get"* stays readable.
- **Several points tie** → several rows.

No special error, no *"signalled best effort"*, no analogue of `select_by_one_std_err`.

## Decision 4 — a relative target needs neither a type nor a callable

The owner's *"the target is always in transformation"* already has a working solution in
section 6 of the masterclass: τ is a target derived from the result itself, solved by the
**user's own bisection over the cached grid**, without re-simulating. No callable enters a
serialisable object, so the defect that breaks `CustomStress.to_dict()` (#83) is not
reproduced.

## Decision 5 — the grid is a cache; adaptive search is a different cost

The owner raised that an optimiser need not be greedy — a binary search would be cheaper.
Measured against the real use case:

- Section 6 uses `optimize_cutoffs` **as a grid generator**, not as a chooser; the code's own
  comment says the grid is a cache and *"the reallocation search reads off the cache — no
  re-simulation inside the loop"*.
- 5 regions × 40 points = **200 simulations**, paid once. Pure bisection would be ~7 per region
  (35) — but it returns **one point for a fixed target**, and τ changes on every iteration of the
  outer loop. Nesting the two searches costs ≈ 7(τ) × 5 regions × ~7(inner) ≈ **245
  simulations**: more expensive than the grid, and it still loses the curve to plot.

**Conclusion:** a grid amortises when the curve is consulted more than once or plotted; adaptive
search only wins for a **single point with an expensive grid** (`k^N` when sweeping hard filters
and scores together). That is #123's matter, not this card's.

## Decision 6 — per-group target creates no type either

A desired, **optional** capability: given a default appetite, optimise per region / store — a
`group by`. It is the same grid carrying the group column, plus `groupby` and the same appetite
filter.

Cost, measured at the time (300k rows, real `run_sweep`, 20-point grid, `parallel=False`):

| scenario | time | ratio |
|---|---|---|
| global, 20 points | 0.63s | — |
| per group, 20 pts × 5 regions | 0.62s | **0.98×** |
| global, 20 points | 0.53s | — |
| per group, 20 pts × 300 stores (~1k rows each) | 7.32s | **13.9×** |

**The number of groups does not cost.** The work is linear in rows × points, and the group-by
partitions the same population (G grids over N/G rows = one grid over N rows). What costs is
**fixed per-sweep-call overhead** — negligible for a large group, dominant for a small one.

Design constraint that follows: `by=` as a Python loop over groups serves *"5 regions"* and rots
at *"300 stores"* — it must be a **single pass with a group key**. That graduated to its own
card (#142, ADR 0031).

## Rejected

- **A target/constraint type** (any of: scalar target on a metric; `maximize=` + `subject_to=`
  with N hard constraints as a type; a strategy object). Rejected by Decision 1 — there is no
  single concept underneath, and naming one would fix the wrong boundary.
- **A callable target.** Rejected for the reason that already killed `CustomStress`: a callable
  does not serialise. Decision 4 shows it is not needed.
- **Adaptive search replacing the grid**, rejected for this card's use case by the count in
  Decision 5; kept alive as a named requirement for #123.

## Consequences

- **The frontier of this card:** the *role* of the three verbs (`sweep`/`tradeoff`/`optimize`)
  stayed with #123 and the vocabulary cleanup with #128. This card only fixed that **the
  business parameter enters none of them**.
- **Left open by this card, and deliberately:** the **shape and count of the selection verbs**.
  Pareto is the only piece of today's `optimize` that survives, and the owner raised treating it
  as *one kind of optimisation*. Three forms were on the table (small sibling verbs ×
  `optimize(kind=)` × a strategy object) with UX as the declared criterion. Settled later by
  ADR 0014.
- **Cost amendment, measured on 2026-08-16 while resolving #140.** *"The grid is a cache"* was
  costed in `run_sweep`'s **fast regime** — and that regime **gives the wrong number**: at 3M
  rows the default is off by up to **0.58 p.p. absolute** (12.05% against 11.49% at cutoff 611),
  against **0.018 p.p.** of sampling noise measured at the same point — **32× the noise**, and it
  does not shrink with n. Approval matches exactly. If the fast path dies for being incorrect,
  the grid's price rises to the re-simulation regime and the cache argument must be redone at
  that level. **The central decision does not depend on the grid's cost**, so the amendment is
  about price, not shape. (See #143 and ADR 0032.)
