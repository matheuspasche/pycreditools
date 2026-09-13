# ADR 0031 — The segmented grid: `by=` is a reading argument, and the single pass is one machine with the fast path

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** what `by=` may and may not change, and where the single pass with a group key
  enters. Excludes the grid verb's signature and coordinate contract (#146, ADR 0013) and the
  selection criteria themselves (#141, ADR 0014).
- **Tickets:** #142 (this ADR). Consumes #92, #122, #124, #132, #136, #139, #141, #145, #146.
- **Spec:** the living engine spec, §4.8 (grid and selection), §4.6 (the engine — never slice
  the base), §6 (the DoDs).
- **Amends:** #146's grid output contract (the two denominators per `(group, point)`) and #124's
  parity whitelist (the notebook's regional cutoffs).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The card was filed as a **performance** question behind an already-published signature: *"where
does the single pass with a group key go, so that `by=` does not rot with many groups?"*

Measured design constraint (300k rows, real `run_sweep`, 20-point grid, `parallel=False`):

| scenario | time | ratio |
|---|---|---|
| global, 20 points | 0.63s | — |
| per group, 20 pts × 5 regions | 0.62s | **0.98×** |
| global, 20 points | 0.53s | — |
| per group, 20 pts × 300 stores (~1k rows each) | 7.32s | **13.9×** |

**The number of groups does not cost.** The work is linear in rows × points, and the group-by
partitions the same population — G grids over N/G rows *is* one grid over N rows, and the
multiplier cancels against the slice. What costs is **fixed per-sweep-call overhead**, paid G
times.

**And then the session found that the premise making this cheap was false.** *"It's only
swapping the internals behind the signature"* is not true, because **the internals are not
number-neutral**. The naive loop calls the sweep on `data[data.region == r]`, and the imputation
ruler is learned *inside* the simulation: `_calibrate_swap_in_pd` takes the keep-ins **from the
slice** (`simulation.py:685`), `_resolve_bin_edges` learns the edges with `qcut` **over the
slice** (`_kernels/calibration.py:18`), and the 50-keep-in floor and the `global_pd` fallback
are **of the slice** (`simulation.py:728-731`).

**So the loop calibrates one ruler per group and the single pass calibrates one** — and nobody
had decided which is right. The card therefore closes with a **modelling decision upstream of
the mechanism**.

## Decision 1 — the decile edges are global: one measurement, over the whole base

Owner's ruling: **once only, over the whole base.** Every group is measured with the same tape.

Consequences that fall out with it:

- the range problem measured in #136 (percentiles leaving the plateau outside the grid) does
  **not** multiply by G, with each group on a different range;
- the 50-keep-in floor does not fire per slice in a long tail — which would be the *"silent fall
  back to global"* #132 forbids, happening 300 times **by construction**.

## Decision 2 — the per-bin rates are global too, so `by=` is a reading argument

With global edges, *"each group teaches its own PD inside the common deciles"* was still a
coherent option — same scale, heterogeneity preserved. **Owner's ruling: one table, because of
volume.**

**Why.** In the long tail #92 names (300 stores of ~1k rows), each decile of each store has ~100
rows, of which only the contracted-and-observed count. A PD estimated over a few dozen rows
swings several p.p. by sample, and that noise **becomes that group's ruler** — contaminating
every grid point of it. **The small store's curve would be drawn by the luck of 30 people**: the
pattern #132 forbade, a wrong answer wearing a right one's face.

> **`by=` may not change what the engine computes.** It answers *how I read the result*. If it
> also answered *what risk the engine models*, two apparently orthogonal arguments would be
> coupled underneath — the class of pathology this map undoes.

**Reading consequence:** the consolidated number and the sum of the per-group numbers tell the
**same story**. With a per-group ruler they would not match, and the difference would not come
from reality — it would come from the ruler having changed midway.

**If between-group heterogeneity is real and matters, the honest way to say it is to declare it**
— another `Study`, another premise, a stage addressing the segment — not as the side effect of an
aggregation argument.

## Decision 3 — one mechanism, not two, and it is a reform *underneath*

The card offered two ways out for its item 5 (reform the internals; or a layer above).
**Neither.** It is a reform of the piece that *counts*.

- the base is sorted once; a cutoff stops being a scan and becomes **a position**
  (`searchsorted`);
- `_metrics`' sums become **running totals**, read by position — one pass answers the whole grid,
  instead of one pass per point;
- **the group is one more axis of the same counter.** Each row is visited once and contributes to
  its own group's total. **300 groups cost the same pass as one.**

**Owner's correction, and it is of the mechanism, not of the prose: the running totals go in both
directions.** The sweep direction is declared (`gte`/`lte`); under `gte` the approved set is the
suffix, under `lte` it is the prefix. The counter keeps both.

**And each direction is computed on its own scan — never derived by subtraction**
(`suffix = total − prefix`). Where the slice is small, subtracting two large numbers eats the
decimals, and the third DoD requires a reference computed outside the engine matching at the
border. Two scans are still **one** pass over the base: same cost, precision preserved.

**This is the same machine #124 recorded as the fast path's target** (base sorted once, a mask
becoming a contiguous slice, metrics becoming prefix aggregates). One uses *position in the
score* as its axis, the other uses *group*. **Decided as one mechanism** — done in different
releases they would be the same work twice, the second on top of settled code.

> **Never slice the base. Always sweep the whole population, and separate by group only when
> counting.**

On the re-simulating path (sweeping a rate, which moves every row's number and has no fixed
table to accumulate) `by=` is also nearly free, for a different reason: the simulation already
runs over the whole base, so the group is just how the final sum is split. **One rule, two
implementations.**

## Decision 4 — selection holds within each group, with the group declared

With `by=`, *"hold today's approval"* (#141) was ambiguous: **within each group** (each store
anchors on its own incumbent) or **over the consolidated book** (the total holds and the mix
moves).

**Decided: within each group.** It falls out of the table for free — the grid already carries the
group's own incumbent as a column (#146 item 6), measured and not simulated. Zero new machinery.

**Sub-decision:** the selection verb receives the group **declared**
(`choose(grid, criterion=..., by="loja")`), never sniffing a group column out of the table. The
same rule #118 and #129 already applied — no derived default, zero coercion.

## Decision 5 — the grid carries the denominators, not only the rates

**Percentages do not add.** A store of 40k applications approving 71% and one of 900 approving
64% do not average to the company's approval rate. To consolidate across groups you need what is
under the division: the **group size** and the **weight of the population entering the default
calculation** — which varies by point, because who contracts changes when the cutoff changes
(in `_metrics`: `n` and `contracted_w` masked by `outcome_known`).

Per `(group, point)` row, the grid carries both. **Cost: the counter already computes them in
order to divide — today it throws them away after dividing.** With them, any cross-group
consolidation is exact and done in pandas.

This matches what #132 already required (the group column carries size and coverage alongside the
result) and **makes the portfolio case expressible with no new verb**.

## Decision 6 — the portfolio case leaves as named backlog, with **two** criteria recorded

The owner raised both uses as equally real. What dissolved the impasse: **the portfolio case is
not an optimiser** — it is the per-group case plus a scalar turned from outside: fix a number
common to all groups; **each group chooses alone** the point that is best at that number; sum and
compare with the aggregate target; bisect until it matches. Step 2 **is** the per-group case, so
the portfolio case is a thin shell over the grid, writable in pandas today (given Decision 5's
denominators).

**And there are two criteria, not one** — found by reading the foundational notebook (§6,
cell 19):

| criterion | what it equalises across groups | answers |
|---|---|---|
| **common target (τ)** — the notebook's | the **level** of risk | *"every group carries the same risk"* (fairness / audit) |
| **common price (λ)** | risk **at the margin** | *"lowest total default at the same approval"* (optimum) |

They are **different answers**: if loosening brings 3 defaults per 100 approvals in one group and
9 in another, the common price tightens the second and loosens the first *even leaving them at
different levels*; the common target forces both to the same level *even if one pays dearly*. The
notebook uses τ and **is right for what it wants** — §6's own text says the value there is the
audit, not the rebalancing.

**There is no *the* portfolio criterion — there are at least two, and choosing between them is a
business question, not an engine one.** Which confirms backlog (#154) over v0.6.0.

**Product question left open in the backlog item:** when the portfolio holds the total and the
groups move, **is there a limit to how far one group may move?** In the pure arithmetic a group
can fall from 64% to 30% approval because the maths said so. Whether that is acceptable is a
commercial decision — and not something to discover in the middle of the package's largest
break.

## Decision 7 — the two-stage flow is a usage pattern, not an engine feature

The owner's actual flow: run global, reach a known scenario, **use the post-policy default rate
as the new target**, and re-optimise per region with a much narrower target and grid.

Confirmed in the notebook, which already validates this session's architecture — cell 19 reads:
*"Cache each region's cutoff → (approval, default) frontier with ONE fine sweep, then the
reallocation search reads off the cache — no re-simulation inside the loop."* That is *"the grid
is a cache"* (#122) working in practice.

**But the reason to narrow changes.** One narrowed because of **cost**. With the group axis free,
that reason evaporates. What remains is better and permanent: **resolution** — 30 points spread
over the whole range give 30 mostly useless points; 30 points on the band that decides give 30
useful ones.

**Decided: two stages is a usage pattern, documented in the spec, with no engine feature.**
Narrow by resolution, never by cost; and the range is **always declared** (`ranges=`, #118). If
the engine derived the second stage's range per group, it would inherit #136's measured problem G
times — the grid stopping before the plateau, each group on a different range.

## Consequences

- **Release blocker, in v0.6.0** — moved there by the owner's ruling in #124's session, on the
  argument that the single pass and the fast path are one machine.
- **The additive tail of #124 shrinks** from three items to two (#130 and the lazy import of
  `visualization.py`).
- **Parity whitelist entry, correcting this card's own body.** The body said *"does not alter
  #124's parity whitelist — `by=` changes no policy's number"*. That became false in this
  session — not from the mechanism, but from Decisions 1 and 2. §6 of the notebook calls the
  sweep on each region's slice, so it **calibrates one ruler per region today**. Under a global
  ruler, **the five regional cutoffs move**. And they are not loose numbers: `validation/README.md`
  reports them by name (**752 / 785 / 732 / 694 / 680**) as *"identical across the 5 regions"*
  between engines — a line of #91's parity verdict. **A modelling change, not a sweep change:**
  it diverges in every segmented simulation. Same family as the entry #139 opened.
- **Amendment to #146:** the grid's output contract gains the two denominators per
  `(group, point)`.
- **Execution note:** cell 19 uses `target_default_rate=` and `min_approval_rate=`, both killed by
  #122. The section will be rewritten anyway — and it **shrinks**: one grid call with
  `by="region"` plus the bisection loop in pandas, replacing the loop that sweeps region by
  region.
