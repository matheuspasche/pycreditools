# ADR 0014 — The selection layer: one verb with a named criterion, and the bracket instead of the band

- **Status:** Accepted
- **Date:** 2026-09-03
- **Scope:** the selection layer over the grid table — the verb that narrows the grid to the
  points answering a named question. Excludes the grid-producing verb (ADR 0013), the appetite
  cut (the reader's own `df[...]`, #122), and the axis declaration rule (#132).
- **Builds on:** ADR 0012 (output data contract — single assembly point, declared schema,
  English names), ADR 0013 (the grid verb — the incumbent travels as `baseline_*` columns).
- **Tickets:** #141 (this ADR). Consumes #122, #125, #127, #131, #132, #140, #143, #146.
  Feeds the roadmap #124.
- **Spec touched:** the living engine spec (selection layer section).
- **Measured against:** `release/v0.6` (`185396c`).

## Context

After ADR 0013 the grid is a plain table with one row per (group, grid point), carrying three
metric columns — `approval_rate`, `take_up_rate`, `default_rate` — and their three measured
twins `baseline_*`. What was still undecided was the layer *above* it: the surface that answers
the questions a reader asks of that table.

Three questions were declared:

| question | anchored to the incumbent? |
|---|---|
| which points are rationally defensible at all? (Pareto) | no |
| holding today's approval, which point lowers default? | yes |
| holding today's default, which point raises approval? | yes |

Two facts framed the design. **The frontier is not a shortlist**: measured on the masterclass
section 6 book, Pareto alone returns 43.3% of the grid at 30 steps and **88.4% at 45 steps** —
it grows toward the whole grid as the simulation improves. And **the only real consumer reads
two views at once**: `visualization.py:291-295` plots every point in grey with the frontier
highlighted, while the carrier that used to hold both — `OptimizationResult` — died with
ADR 0013.

The shipped iso-approval selector was `OptimizationResult.find_equivalent`
(`optimization.py:43-68`): a tolerance band around a passed-in number, with a silent
`.head(1)` fallback when the band came back empty (`:63-66`).

## Decisions

### 1. One verb, `choose`, with the question named by a `criterion=` argument

```python
choose(grid, *, criterion, maximize="approval_rate", minimize="default_rate")
```

`criterion` takes one of a closed, validated set — `"pareto"`, `"hold_approval"`,
`"hold_default"` — and the verb returns **the rows that passed**, keeping the selection a
table→table layer as #122 fixed. Narrowing by appetite stays the reader's own
`df[df.default_rate <= 0.12]`, also per #122.

The alternative shape — a sibling verb per question, each annotating a boolean column instead
of filtering — was worked through and rejected by the owner. It bought two things: three exact
signatures with no inert arguments, and a single table serving both plot views. It cost the
thing the owner's ruler asks for first: *fewer verbs, as intuitive as possible*. One verb puts
the whole menu of questions in one `help()`, which is the strongest answer to the real
discovery problem here — a reader does not know which questions the layer can answer.

**Names checked on `release/v0.6`** before choosing: `candidates` is taken by the funnel (the
applicant entering a stage, `simulation.py:51,100,110`), `screen` by `screening.py`, and
`select` was refused because in dplyr and polars it picks **columns** — the same word on the
opposite axis. `choose` has no occurrence in the package.

**Declared price of the name.** `choose` reads as picking *one*, and this verb returns a set —
199 of 225 rows on the measured book. The owner chose it with that objection recorded, on the
same footing as `tradeoff` over `sweep` in ADR 0013. What bounds the damage is structural
rather than editorial: **nothing in this layer can return a single row by its own judgement**.
#122 killed every best-pick mechanism (the magic weight, the `.iloc[0]`, the silent fallback),
and decision 3 below leaves no silent path. The spec must state that the return is a set.

**Declared price of the shape.** The signature is a union: `maximize=` and `minimize=` are
meaningful only for `criterion="pareto"`, and passing them with an incumbent-anchored criterion
is a hard error at the call. This is the cost of one verb over three, it is explicit rather
than inferred, and it is not the silent inference #132 governs. Chaining two criteria
(`choose(choose(grid, criterion="pareto"), criterion="hold_approval")`) works but drops the
rows the first pass removed; a reader wanting both views keeps the grid.

### 2. The incumbent-anchored criteria bracket; they do not band

`"hold_approval"` and `"hold_default"` keep the **two grid points that straddle the incumbent**
on their axis — the nearest point below and the nearest above.

A tolerance band was measured and rejected. On the section 6 book (45 steps, 5 regions):

| tolerance | regions returning nothing |
|---|---|
| 0.10% | **5 of 5** |
| 0.25% | 3 of 5 |
| 0.50% | 2 of 5 |
| 1.00% | 0 of 5 — but **exactly one row** in each |
| 2.00% | 2–3 rows |

The median grid step on the approval axis is **1.53%–1.71%**. The tolerance therefore competes
with the grid step: below it the band is empty, and the first value that returns anything
returns a single point. The row count is governed by the sweep's resolution, not by the
question being asked — and the reader's natural repair is to widen the tolerance until
something appears, which tunes it against the sweep rather than against the business. This is
the mechanism that put the `.head(1)` fallback inside `find_equivalent`: empty was the common
case.

Defaulting the tolerance to the grid step would repair it, and is forbidden: #132 ruled that a
default derived from scanning the table *"would change its answer according to the data"* — the
silent inference that card killed. Bracketing needs no parameter at all. It is a rule, not a
tuned value.

Measured, same book — 2 rows in 5 of 5 regions, never empty:

| region | incumbent approval | bracket (approval) | bracket (default) | incumbent default |
|---|---|---|---|---|
| Centro-Oeste | 17.68% | 17.16% – 19.30% | 0.00% – 0.00% | 2.35% |
| Nordeste | 17.57% | 17.44% – 19.16% | 4.18% – 4.83% | 6.34% |
| Norte | 17.17% | 16.82% – 18.79% | 11.04% – 14.32% | 14.86% |
| Sudeste | 21.95% | 21.21% – 23.06% | 2.33% – 2.92% | 4.64% |
| Sul | 21.68% | 21.48% – 23.64% | 6.48% – 7.14% | 8.60% |

The bracket also **exposes the grid's resolution instead of hiding it**: its width on the
default axis runs from 0.0 p.p. to 3.3 p.p. across these regions. A reader wanting a finer
answer adds grid steps — a decision that a chosen tolerance conceals.

*(The 0.00% figures are an artefact of the synthetic generator, where `score_5` is near-perfect
at high cutoffs. They are not a claim about a real book.)*

### 3. The empty case: one failure mode, and it is a hard error

- **Pareto is never empty.** A non-empty grid always has at least one non-dominated point
  (88.4% of the grid on the measured book). There is nothing to protect.
- **The bracketing criteria are never empty in the ordinary case** — measured 2 rows in 5 of 5
  regions. They have exactly one failure mode: **the incumbent lies outside the swept range**.
  That is a hard error, and it is explainable in the reader's own terms (*"you swept
  3.6%–76.7% approval and your book sits at 17.7%"*). It is the wrong sweep, not a tolerance
  artefact. This is step 2 of the #132 ladder — a hard error at the boundary — under the ruler
  declared there: *expect adequate input*.

So #122 point 5 (*empty result is an empty table, no special error*) and the #141 requirement
(*"no acceptable solution" must be an explicit error*) both stand, and neither is revoked: the
ordinary path never goes empty, so #122's tolerance is never exercised here, and the one real
failure is the hard error the requirement asked for.

**Declared limit.** #141 decided the appetite gets no verb, so when the appetite cut yields
nothing the package **has nowhere to raise from** — it is the reader's own `df[...]`. "No
acceptable solution" is therefore protected where the verb runs (an out-of-range incumbent) and
unprotected where it does not (the appetite), where the reader receives an empty frame from
their own filter. That is legible — the whole grid is in their hand, with its minimum default
visible — but it is a limit, not a guarantee, and the spec states it rather than letting it
pass in silence.

### 4. Criterion names: the question, not the mechanism — and the family rule

`"pareto"`, `"hold_approval"`, `"hold_default"`.

`hold_*` states the question the criterion answers rather than the algorithm behind it, and does
not promise optimality — which matters because #140 measured the fast path mis-stating default
by up to 0.58 p.p., so nothing here may read as *"I found the best"*.

**The family is deliberately irregular**, and the rule must be written down: a criterion
anchored to the incumbent is `hold_<metric>`; a criterion that is not takes its algorithm's own
name. Pareto is genuinely not their sibling — it ignores the `baseline_` columns that define
the other two, which is also why `maximize=`/`minimize=` belong to it alone.

**Declared limit of the name.** `hold_approval` says the approval is held; decision 2 returns
two points that *straddle* it, neither holding it exactly. Nothing is concealed — the reader
gets both rows and can see they straddle, with no fallback and no hidden pick — but the spec
must state that the answer is a bracket, not an equality. The alternatives (`iso_`, `at_`)
promise exactness just as strongly; only naming the mechanism (`bracket_approval`) would be
literal, at the cost of naming the machinery instead of the question.

Checked on `release/v0.6`: `hold` appears nowhere as an identifier (7 prose sites only), and
`pareto` exists solely in `pareto_frontier` / `find_pareto_frontier`
(`optimization.py:26,212,229`), both dying with ADR 0013.

### 5. The plot takes the grid and the criterion, not two tables

Because `choose` filters, the two-view plot cannot be served by one returned table — the
obligation ADR 0013 transferred to this card. It is discharged by giving the plot the same
shape as the verb:

```python
plot_tradeoff(grid, *, highlight="pareto")
```

The plot receives the **whole grid** and the criterion name, and narrows internally. No row
correspondence between two tables has to be maintained by the package or by the reader, and the
highlighted set is by construction the same set `choose` returns for that criterion.

## Consequences

- `find_equivalent` dies as a method together with its silent fallback, and with its Studio
  re-export (`studio/analyses.py:1036`). Its replacement is `choose(grid,
  criterion="hold_approval")`, which brackets.
- `find_pareto_frontier` (`optimization.py:229`) survives as the dominance kernel behind the
  `"pareto"` criterion, but stops being public surface.
- `plot_optimization` (`visualization.py:280-340`) is replaced by `plot_tradeoff` per
  decision 5.
- The grid table's declared schema is unchanged by this layer — `choose` returns a subset of
  rows, adding no column.
- Public breaks for the roadmap (#124): `find_equivalent` (method and Studio re-export),
  `plot_optimization`, and `OptimizationResult` — already listed by ADR 0013.

## Alternatives rejected

- **Sibling verbs that annotate a boolean column** (`pareto`, `hold_approval`, `hold_default`,
  each returning the grid plus a declared flag). Exact signatures with no inert argument, one
  table serving both plot views, and every narrowing done by the reader's `df[...]`. Rejected
  by the owner against *fewer verbs, as intuitive as possible*: three verbs a reader must know
  to look for, against one verb whose `help()` lists the whole menu.
- **Strategy objects** (`choose(grid, Pareto(...))`). Buys honest per-strategy signatures at the
  cost of N+1 concepts, and ADR 0012 decision 1 already refused the shape: *"an object with
  accessors is more verb, not less"*.
- **The incumbent-anchored questions as the reader's plain pandas**, by analogy with the
  appetite. Rejected on measurement: the appetite is a half-plane whose result scales with the
  question, while the iso band is an interval competing with the grid step — empty in 5 of 5
  regions at a 0.10% tolerance. Different geometry, different answer.
- **A tolerance band with a default derived from the grid step.** Rejected by #132: a default
  read off the data is the silent inference that card killed.
- **`method=` as the argument name.** Rejected on collision: #140 kills `method` (analytical vs
  stochastic) out of 39 signatures in this same release, and reusing the word with a new sense
  is the duplicate ADR 0012 killed in `rating`/`Rating` and `scenario`/`quadrant`.
