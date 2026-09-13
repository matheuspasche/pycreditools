# ADR 0023 — The desk is a probabilistic **decision**: determinism and vector are two axes

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the semantics of a stage that decides by drawing — the desk, the greyzone,
  take-up — plus the eligibility contract and what the analytical path does with a draw.
  Excludes the verb's name and signature (#129, #145, ADR 0029).
- **Tickets:** #121 (this ADR). Consumes #93, #95, #97, #103, #105, #106, #116, #117, ADR 0011.
- **Spec:** the living engine spec, §4.2 (`.filter(expr, draw=True)`), §4.6 (the engine — the
  funnel), §4.4 (`take_up`).
- **Amended by:** #155 (§1's mechanism gets cheaper; §3 stops governing the contract axis).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The owner's real case: 20% of those approved at the cutoff are **referred to the desk** —
because they are in the greyzone, or because collateralised security needs analysis. Whoever
reaches the desk has a probability of approval, flat or a function of the score. In practice
that is a `.rate`, and today there is no way for it to enter as a stage of a policy.

#105 had already found the pattern, twice, with the **same structure**:

| stage | has a 0/1 value | null means | unobserved population |
|---|---|---|---|
| hire / take-up | approved keep-in | not eligible | swap-in, estimated rate |
| desk approval | whoever reached the desk | did not reach the desk | swap-in, estimated rate |

In both: whoever has an observed outcome uses the real 0/1; whoever does not has the rate
estimated. And **null must be null, not 0** — otherwise the rate inflates. It is the same
denominator contract as the #95/#97/#93 fixes.

`RateStage`'s measured defects: `observed_col` mixes *"keep-in's observed take-up"* with *"the
stage rate estimated for swap-ins"* in one field; null is implicit (it depends on the caller
putting `NaN` in the right place — `.mean()` skips `NaN` at `stages.py:390`, but the guarantee
is fragile); and nothing documents or validates *"0/1 = reached the stage, null = not
eligible"*.

## Decision 1 — determinism and vector are two axes, not one

Today `.filter` and `.rate` differ in **two things glued together**: predicate-versus-probability
and decision-versus-contract. Pulled apart, *probabilistic* becomes **how** a stage decides,
while the verb keeps naming **which vector** it feeds.

This **preserves #116 instead of amending it**: *"the funnel splits by kind of stage"* is read by
**declared vector**, not by class. `isinstance(stage, RateStage)` at `simulation.py:438` dies as
a partitioning mechanism.

## Decision 2 — two chained stages, and eligibility comes for free

Referral-to-the-desk (greyzone, collateral) is a **deterministic predicate**, already
expressible. Approval-at-the-desk is a **probabilistic stage** over whoever is left.

Consequence: **eligibility is a position in the funnel, not a declared mask.** The hardcoded
`policy.current_approval_col` at `stages.py:388` dies — the stage stops having a second
filtering path running parallel to the funnel, which is exactly the *"one primitive with two
owners"* #105 pointed at.

This exposes that today's code confuses **two distinct masks**:

- **who was observed** — who went to the desk in the old book (a fact of the data);
- **who is eligible** — whom the *new* policy's funnel refers to the desk.

They do not coincide. A keep-in eligible under the new policy who never went to the desk in the
old book is a case for **estimation**, not for a zero.

## Decision 3 — the observed column's name lives in the stage

#118's role≠reference amendment, applied: the schema owns the names read **by role**; the policy
names the columns its **rules reference**. A desk outcome is the reference of a specific rule of
that book — it lives in the stage. `DataSchema` stays at three fields, untouched.

**This dissolves #105 by construction**: `hired` is a role (schema), a desk outcome is a
reference (stage) — different species, no two owners. And take-up's `observed_col` **dies**:
take-up reads `hired` from the schema and names no column at all.

## Decision 4 — bind: hard error, and coverage as a number

- Values outside `{0, 1, null}` → **hard error**.
- A non-null observation requires `approved == 1` → **hard error**. Whoever was never approved
  in the old book cannot have a desk outcome. Same tied-entry pattern as #116; it catches a real
  class of spurious zeros — **not all of them**, since a 0-in-place-of-null inside the domain is
  undetectable.
- **Coverage becomes a number** in the result (how many eligible without an observation), as
  #116 did when it killed the `notna()` proxy.

The `.fillna(0.0)` at `stages.py:449` and `:463` dies — today null becomes 0 and inflates the
denominator, same family as #95/#97/#93.

## Decision 5 — `decision` stays hard 0/1: the desk draws even on the analytical path

A probabilistic decision stage would make `decision` fractional on the analytical path and
seed-dependent on the stochastic one. Owner's ruling: **keep 0/1**, drawing the desk stage on
the analytical path too.

**Why.** `decision` is used as a **mask** downstream — who enters the denominator, who
contracts. A fractional decision multiplying into `contract` and `outcome` is literally the
weighting mechanic that produced the #95/#97/#93 family. Keeping it 0/1 closes that door by
construction.

**Price accepted, declared:** *"analytical"* now means **deterministic given the seed**, not
seed-free. The seed is already mandatory under #116, so #124's parity stays reproducible — it is
simply no longer seed-free. A declared amendment to #116's invariant, which was measured over
hard stages only, where it remains true.

This opened a new card: *does the analytical method die?* (#140). Input already measured in
#116: drawing costs 12–15% (5M rows: 6.35s vs 7.08s). The strong argument is not time — it is
the mesh of tests that exists only to prove the two paths agree for large enough n.

## Decision 6 — the desk estimates in the same premise, without inflating

The desk is one more axis with no marking: it uses the same `bins` (#117 — *"one config serves
every axis"*) and estimates a baseline over whoever went to the desk in the old book. **The
inflation does not apply** — stress is a premise about *default*, not about propensity to be
approved. Zero new fields on the premise.

## Decision 7 — the published approval rate includes the desk

The desk feeds `decision`, so rejected-at-the-desk is rejected, and the published number says
so. `approved_pre_rate` had already died in #116; the definition *"before any rate stage"* goes
away together with the by-class criterion.

## Rejected

- **A new type for the probabilistic stage.** #105 argued explicitly against it — adapt what
  exists. Decision 1 is the cheaper form: an axis, not a class.
- **Eligibility as a declared mask.** It duplicates the funnel, and the duplicate is where the
  two masks above get confused.
- **A fractional `decision`.** Rejected in Decision 5; it reopens the denominator family.

## Consequences, and what #155 moved

- **§1 survives intact — and it was the statement that defeated the criterion the owner took
  into #155** (*"the policy is trending towards deterministic"*): the desk is
  `.filter(expr, draw=True)` (#145), feeds `decision`, and Decision 5 makes it draw on the
  analytical path too. Drawing and vector stay two axes, and after v0.6 there is drawing on both
  sides of the partition.
- **The mechanism got cheaper.** This card decided to kill `isinstance(stage, RateStage)` by
  **replacing** it with a partition by declared vector. With the contract axis out of the list,
  the 5 sites (`simulation.py:79`, `:229`, `:438`, `:475`, `:552`) **vanish with no
  replacement**: `stages` is homogeneous and there is nothing left to partition. The two vectors
  are computed in different places by construction — `decision` in the funnel, and
  `contract = decision × take_up` applied once by the engine.
- **§3 is amended.** It was the decision the 2026-09-05 ruling used to justify *not* moving the
  axis, and #155 measured that reason's price at **zero**: today the take-up stage's position is
  **inert** — the funnel accumulates by product, which is commutative (`simulation.py:434`),
  partitions by type test rather than position (`:438`), the stochastic `min` is order-invariant
  (`:446`), and reason assignment already excludes `RateStage` (`:475`). The prototype
  (`docs/research/prototype-155-contract-axis.py`) moved take-up to the **front** of the list
  for `|Δ contract| = 0` and `|Δ decision| = 0`. §3 still governs the `decision` vector; it no
  longer governs the contract axis, whose eligibility **is** the decision vector.
- **§4 is confirmed by measurement:** today's implicit funnel take-up is, on keep-ins,
  **exactly** the observed `hired` column (`|Δ| = 0`). Identity, not analogy — and that is what
  makes `calibrate_on="keep_in"`/`"hired"` the right name (#152).
