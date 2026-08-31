# ADR 0013 — The grid verb: one name, a plain table, and the incumbent as a column

- **Status:** Accepted
- **Date:** 2026-08-31
- **Scope:** the grid-producing surface — `sweep.py`, `analysis.py`, `optimization.py` — and
  the public names they export. Excludes the selection layer over the grid (#141) and the
  segmented grid's implementation (#142).
- **Amends:** ADR 0008 (metric contract) on the emitted metric names. Builds on ADR 0012
  (output data contract) for naming rules and the single assembly point.
- **Tickets:** #146 (this ADR). Consumes #116, #117, #118, #120, #122, #125, #129, #131,
  #140, #143. Feeds #141, #142, #149 and the roadmap #124.
- **Spec touched:** the living engine spec (grid verb + grid table sections).
- **Measured against:** `release/v0.6` (`f15b284`).

## Context

Three public surfaces produced or consumed the same grid, over one already-unified backend:

- **`run_sweep`** (`sweep.py`) — the engine. Cartesian product of the swept dimensions,
  re-simulate or mask, measure. Returns a `DataFrame` whose coordinate column is named after
  the score column itself (`row = dict(combo)`, `sweep.py:209` and `:305`) — so `score_a`
  holds a threshold, not a score.
- **`run_tradeoff_analysis` / `TradeoffAnalyzer`** (`analysis.py`) — calls `run_sweep` and
  renames columns (`:108-111`). Two real contents: the metric renames
  (`overall_approval_rate` → `approval_rate`) and the coordinate disambiguation
  (`{col}` → `{col}_cutoff`).
- **`optimize_cutoffs` / `OptimizationResult`** (`optimization.py`) — calls `run_sweep`, then
  picks a "best" point. #122 already killed that pick: the magic weight
  `approval − 5·default`, the `.iloc[0]`, and the silent fallback.

Decisions closed before this one had already hollowed all three out. #122 made selection a
table→table layer. #131 fixed a single assembly point that emits final names, so the metric
rename has nothing left to rename. #129 killed `.cutoff` as a stage, so the word `cutoff` left
the vocabulary. #140 killed the analytical method, leaving one calculation path. #118 fixed
sweeping as `ranges=` on the verb, so the fluent `vary_*` builder is a dictionary constructor
wearing a type's name.

Two measured facts framed the session:

- **`TradeoffAnalyzer` never forwarded `method`** to the engine (`analysis.py:97`), so the
  stochastic mode was unreachable from the top. Two surfaces for one act had already diverged
  in behaviour on their own.
- **`OptimizationResult.find_equivalent`** (`optimization.py:43-68`) *is* the iso-approval
  selector, already shipped, with the reference passed as a number
  (`target_value=0.20`) and a silent fallback (`if matches.empty: … head(1)`, `:63-66`),
  re-exported by the Studio (`studio/analyses.py:1036`). The "passed reference" design was not
  hypothetical — it was in production, and had already slid from *reference* into *target*.

## Decisions

### 1. The incumbent scenario travels as columns of the grid table

The incumbent — the policy running today — is **measured, not simulated**: it comes from the
three schema roles of #118 (`approved`, `hired`, `outcome`) over the bound base, never from the
engine. It reaches its consumers as columns on the grid table, not as an argument to the
selectors.

This does **not** reopen ADR 0012 decision 1. What that decision removed was a *result type
with accessors* standing in for the contract. Columns are not accessors: the grid stays a plain
`DataFrame` and the table stays the interface.

Rationale, in order of weight:

- **The segmented grid settles it.** #142's declared requirement is that a grouped grid compares
  against the incumbent *of the same group*. As an argument that becomes a `dict[group, float]`
  the caller assembles alongside an already-keyed table; as columns the key is on the row.
- **A passed reference is the door the target comes back through.** At the signature level,
  `reference=0.302` is indistinguishable from `target_default_rate=0.08`, the business argument
  #122 removed from the engine. As a column the confusion is inexpressible; appetite stays
  `df[df[col] <= x]`, the human's filter.
- **It homogenises the three selectors of #141** — all take only the table; the two iso-*
  selectors read the twins, Pareto ignores them.

**Accepted costs, declared:** two provenances now share one table — simulated columns beside
measured ones. The incumbent cannot be a *row* for exactly that reason (same shape, different
provenance, a row that does not obey the law of the others); as columns the mixture moves to the
horizontal axis, and the spec must state it rather than leave it implicit.

### 2. The incumbent is an internal derivation, not a type

It does not become a fifth piece beside `DataSchema` / `CreditPolicy` / assumption / `Study`
(#117). It declares nothing: the user states no part of it, and the candidate content the ticket
proposed — `(base, current_approval_col, actual_default_col)` — is, after #118, just
`(base, schema)`, which the `Study` already holds when the verb runs.

The load-bearing reason is correctness, not elegance: the incumbent's metrics must use **the
same definitions** as the grid's columns (approval pre-take-up over the whole base;
default weighted by the contracted population, ADR 0008), or "iso-approval" compares two
different quantities. Computing it inside the same assembly point makes that coherence
structural instead of documented. It also removes a live duplication: `performance.py` computes
the same thing by hand in five places (`:28`, `:148`, `:305-342`, `:466`).

The domain chain is ADR 0012's, not a new rule: `decision → contract → outcome`, so default is
computed only over the contracted and conversion only over the approved.

**Storage is the column itself.** There is nowhere to cache it between calls — #117 put the base
on the verb, not on the `Study`, and #120 refused to keep a fingerprint of the base in the
study. So it is measured once per verb call (once per group under `by=`).

Measured (numpy/pandas, 3 M rows, the three schema columns):

| scope | time |
|---|---|
| whole base | **45 ms** |
| per group, 5 regions | 158 ms |
| per group, 300 stores | 230 ms |

Against ~712 ms for a 900-point grid on the fast path (55 ms fixed + 0.73 ms/point, #143) and
~74 s on the re-simulation path. Once per call is 6% of the fast path; per grid point it would
be 900 × 45 ms = 40 s, alone 57× the whole fast grid.

### 3. `OptimizationResult` dies whole

None of its five fields survives as content of its own: `best_combination` and `metrics` were
killed by #122; `all_results` **is** the table; `pareto_frontier` becomes a selector's output
(#141); `params` carries two arguments killed by #122, a `method` killed by #140, and a
`cutoff_steps` replaced by `ranges=` in #118. `to_dict`, `__repr__`, `plot` (presentation moves
to the border, #127) and `find_equivalent` go with it, and so do the columns `optimize_cutoffs`
hangs on the grid: `combination_id`, `constraints_met`, `tradeoff_score`.

The only measured argument for keeping a carrier is `visualization.py:291-295`, which reads
`all_results` **and** `pareto_frontier` together. The cheaper answer is #141's open question: if
the selector *annotates* a boolean column instead of filtering, one table serves both views.
**Obligation transferred to #141:** if it chooses to filter, it must say how the plot joins the
two views.

### 4. One grid verb, named `tradeoff`

`sweep` and `tradeoff` collapse into one public verb. The backend was already unified in v0.5;
of the two real contents of the `tradeoff` layer, the metric rename evaporated with ADR 0012
(the single assembly point emits the final names) and the coordinate disambiguation becomes the
single verb's responsibility.

The name is `tradeoff` — the domain's word — **against the session's recommendation of `sweep`**.
The cost is declared and accepted: it is a noun in a verb's position, so the package takes that
one departure from the dplyr grammar (where every verb is a verb) in exchange for speaking the
user's language. `CONTEXT.md` had no term for this at all, so nothing was overruled. `sweep`
survives as the internal engine name.

### 5. The fluent `TradeoffAnalyzer` dies

It is not a type: its three `vary_*` methods fill dictionary entries that `ranges=` receives
directly (#118), and `.run(data)` forwards. No state, no invariant, nothing hidden — interface
added over nothing. Consistent with #117 (execution is free functions), #118, and #127 (the four
`print_*` become free functions, not methods).

### 6. The coordinate carries the bare label

`ranges={"score_a": [600, 650, 700]}` returns a column `score_a` holding the value used at each
point. No suffix.

`_cutoff` would be dead vocabulary: #129 killed `.cutoff`, leaving `.filter` over the AST, where
what gets swept is the literal of a comparison. The bare label also gives key-in/key-out
symmetry, which #129 already built by making the label address `ranges=`. The score/threshold
ambiguity does not materialise, because the grid table carries no per-applicant column.

A collision between a swept label and a `by=` group column is a **hard error**, matching #125 and
#129.

### 7. Three metric columns, and three `baseline_` twins

The grid table publishes `approval_rate`, `take_up_rate` and `default_rate` — the `overall_`
prefix drops, since it only ever distinguished these from per-row columns that no longer coexist
here.

Take-up is the third column **against the session's recommendation of two**, and it closes a real
hole: the grid publishes approval *pre-take-up* and default *among the contracted*, two different
populations, and without take-up the contracted volume is not derivable from the table. It aligns
the grid with ADR 0008 and with the `decision → contract → outcome` chain.

The declared cost, transferred to #141: the list of Pareto axis candidates goes from two to
three, and one possible pair — (approval, take-up) — is meaningless in business terms. ADR 0012
decision 6 had kept that list deliberately short; declaring the axes therefore stops being a
convenience and becomes a requirement.

The incumbent's twins are `baseline_approval_rate`, `baseline_take_up_rate` and
`baseline_default_rate`. The word is `baseline` because #125 already named this concept that way
in the comparison verb ("baseline default = the current scenario, from the schema's `approved`
column"); `incumbent` — the word `CONTEXT.md` uses in prose — would create a second spelling for
one role, the duplication ADR 0012 removed in `rating`/`Rating`.

**Rule for the spec:** every metric column of the grid has a `baseline_` twin holding the value
measured on the incumbent scenario.

### 8. `by=` is reserved *and* functional from v0.6.0

The verb's signature carries `by=` in the breaking release, and it works — implemented as a plain
loop over groups. #142 later replaces the innards with a single keyed pass, an internal change
that does not touch the signature.

Reserving it was the owner's call **against the session's recommendation** of adding it later;
making it functional removes the objection, because the parameter is not dead surface and the
group column enters the public contract in the version that may break it. The published cost:
0.98× with 5 regions, **13.9× with 300 stores** (~1k rows each) — the documentation must say
where it rots.

This also settles #142's item 3 for free: the grid is the same for every group, by construction,
since #118 killed derived defaults and fixed `ranges=` as explicit.

### 9. The fast path's defect is a release gate for v0.6.0

v0.6.0 does not ship with the fast path computing the wrong default rate. Either calibration
follows the mask, or the verb re-simulates always and pays the ~112× of #143. #124 turns this
into a gate of the implementation map.

Why it became a gate here rather than a note: #140 left one calculation path and this ADR leaves
one verb, so the caller neither chooses nor knows which internal path ran — and `default_rate`
and `baseline_default_rate` would mean different things depending on it, inside one public
contract. Measured in #140: up to **0.58 p.p.** of error against 0.018 p.p. of sampling noise
(**32× the noise**), not shrinking with *n*, always upward, peaking in the middle of the 15–45%
decision band. The `this is exact` comment (`sweep.py:284`) is false.

The price of the fix is not yet known, and #149 was opened to measure it — the cost per point of
"mask + recalibration". Note for whoever reads the roadmap: method (analytical × stochastic) and
grid path (fast × re-simulation) are **orthogonal axes**. Killing the analytical method cost
+7.9% serial / +5.5% parallel (#140) and neither created nor changed this defect, which is older
and independent.

## The resulting contract

One row per (group, grid point):

| column | role |
|---|---|
| `study` | study identity (#125) |
| `{label}`, one per swept dimension | the coordinate — the value used at that point |
| group column (with `by=`) | the group key |
| `approval_rate` | approval, pre take-up, over the whole base |
| `take_up_rate` | conversion from approved to contracted |
| `default_rate` | default weighted by the contracted population |
| `baseline_approval_rate` · `baseline_take_up_rate` · `baseline_default_rate` | the same three, measured on the incumbent scenario |

Dead: `overall_approval_rate`, `overall_default_rate`, `{col}_cutoff`, `combination_id`,
`constraints_met`, `tradeoff_score`.

## Consequences

- **Public breakage for v0.6.0** (#124): `run_sweep`, `run_tradeoff_analysis`,
  `TradeoffAnalyzer`, `optimize_cutoffs`, `OptimizationResult`, `find_equivalent` (method and
  Studio re-export), `plot_optimization` in its current shape, plus the column renames above.
- **The silent fallback disappears** with `find_equivalent`; #141 already requires an explicit
  error for "no acceptable solution".
- **#142 becomes a performance decision**, inheriting: a long table with the group column; the
  six metric columns per group, twins included; hard error on label/group collision; the same
  grid for all groups; and an already-functional `by=`.
- **The Studio adapts**, it does not vote — it is a frozen consumer by the map's ruling, and it
  holds `OptimizationResult` in cache (`gui/session.py:205`).
- **Documentation gains one acceptance criterion**, beside the one ADR 0012 already set: say
  where `by=` rots.

## Alternatives rejected

- **Passing the incumbent to the selectors** — the shipped design. Rejected: it re-opens the
  target-as-engine-argument door #122 closed, and it does not survive `by=` without a parallel
  keyed structure.
- **A first-class `Baseline`/`Incumbent` type.** Rejected: it would declare nothing the schema
  and the bound base do not already determine, and add a fifth type to a spec already declared
  too long.
- **Keeping a thin carrier** for the grid plus the frontier. Rejected: an annotated column
  serves both views of the plot, and holding two tables in two variables is an ordinary dplyr
  move, not a reason for a type.
- **A separate verb that measures the incumbent** and returns a one-row table for the user to
  join. Rejected: one more verb against the UX rule, and a `merge` in the user's lap on every
  iso-* analysis.
- **`sweep` as the public name** (the session's recommendation). Overruled by the owner in
  favour of the domain word.
- **Two metric columns** (the session's recommendation). Overruled by the owner in favour of
  closing the contracted-volume hole.
