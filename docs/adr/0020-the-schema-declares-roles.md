# ADR 0020 — The schema declares roles, not references — and `score_cols` dies whole

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** `DataSchema` — which roles it carries, what the bind checks, and where the three
  jobs of `score_cols` go. Excludes the partition itself (ADR 0019 / #117) and what a stage
  does with a column it references (#129).
- **Tickets:** #118 (this ADR). Consumes #81, #116, #117, #132, and `architecture-critique.md`
  §5 and §13.
- **Spec:** the living engine spec, §4.1 (`DataSchema`, the bind rules) and §4.6 (the engine,
  on validation).
- **Amends:** ADR 0019 / #117 — the phrase *"sole owner of column names"* is not literal.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

Two measured defects, both of them silent inference.

**(a) The calibration anchor was a three-level cascade that announced nothing.**
`resolve_calibration_score_col` (`stages.py:158`) resolved explicit `calibration_score_col` →
the **last** `CutoffStage` whose score is in the frame → the **last** element of `score_cols`.
With more than one score, *which column anchors the swap-in's PD calibration depended on
declaration order*. A silent error that changes the result of the experiment.

And the cascade **tends to the worst case**, not merely to an arbitrary one: its first fallback
is a score the policy **cuts on** — therefore the score most likely to have had its support
destroyed by selection. #139's prototype measured 92.4% of swap-ins outside the keep-ins'
support on that axis.

**(b) `score_cols` did three jobs from one field** (#81): a presence role (`validate()`,
`policy.py:167`), the sweep vocabulary for `optimize_cutoffs`, and the calibration anchor.
Consequences already identified: mandatory even for a policy that only filters and cuts; and no
superset invariant — a cutoff on `score_2` outside `score_cols` is a hard filter that happens
to be a score, and the sweep never treats it as frozen.

**One of the three jobs died before this card was decided.** #117 ruled that there *is* no
anchor: what is called "calibration" is reject inference, and the discretisation is a config of
the premise, not a pointer at a column. So the card's own question 2 — *"hard error or a
derivable, announced rule?"* — dissolved for want of an object.

## Decision 1 — three fields, and nothing else

```python
DataSchema(approved: str | None = None, hired: str | None = None, outcome: str | None = None)
```

`approved` — if declared, `hired` becomes mandatory (#116's entry tie). `outcome` accepts null,
because **null is the unobserved**.

**Dead from the schema:** `score_cols`, `applicant_id`, `time_col`, `estimated_default_col`,
`segment_col` (which never arrived), and every `calibration_*`.

Each death has its own evidence, and the shape of the evidence is the same each time — *a
field the engine does not read, or reads by guessing*:

- **`score_cols`** — the only real consumer measured in the engine is `optimize_cutoffs`
  (`optimization.py:131`); `sweep.py`, `simulation.py` and `analysis.py` have **zero** reads.
  (`GroupingRecipe.score_cols` is its own field, not this one.) The presence job is redundant —
  the columns the stages cite are already validated — and the sweep vocabulary moves to the
  verb. Consequence: the filter-only policy stops being forced to declare a score, and the
  "cutoff outside `score_cols`" defect goes away **by construction**, because there is no
  longer a set to be outside of.
- **`applicant_id`** — mandatory today (`policy.py:22`), yet the engine uses it only to **count
  rows** (`performance.py:66`), and `deployment` **fabricates** it with `range(len(df))` when
  it is absent (`deployment.py:422`). A mandatory field the package invents for itself carries
  no information. A row is an applicant; counting is `len`.
- **`time_col`** — **zero** consumers in `simulation.py`, `sweep.py`, `performance.py`,
  `analysis.py`. It appears only in `grouping`, where it is already the function's own argument
  (`grouping.py:149`).
- **`estimated_default_col`** — another silent cascade (`simulation.py:548`): declared column →
  else the **last** `RateStage` → else `NaN`, switching a `use_stochastic_draw` on from the
  side. The two branches are different things: a PD column is a model's prediction, a
  `RateStage` is a rule of the policy. One path replaces both, the cascade dies by
  construction, and the hidden mode goes with it.
- **`segment_col`** — the role is declared in the Studio (`studio/models.py:17`) while the
  engine **guesses** it from `["region","loja","safra"]` (`simulation.py:271`). The role was on
  the wrong side of the boundary. The heuristic dies; the segment becomes an argument of
  whoever segments.

## Decision 2 — role ≠ reference

> **The schema owns the names the engine reads BY ROLE** — approved, hired, outcome.
> **The policy names the columns its RULES REFERENCE** — score, income, PD.

#117 had written that the schema is the *"sole owner of column names"*. Read literally that
forbids `.cutoff("score_1", 600)` and `col("renda") > 1000`, which the same resolution kept —
so it never could have been literal. Recorded here, and amended onto #117, so no future session
reopens the decision through the literal version of the sentence.

## Decision 3 — the principle that decided three fields in one sitting

> **An axis of experiment or analysis is an argument of the verb. A role in the funnel is
> schema.**

A funnel role is **finite and always read by the engine**; an analysis axis is **open and
per call**. The owner's stated reason: *"the guy may want to run countless analyses, with
countless columns — he'll run an experiment, look, and take it up (or not)."*

The same principle decided the sweep vocabulary, `segment_col`, and OOT/vintage, in the same
session, in the same form. That is why it is recorded as a principle and not as three rulings.

## Decision 4 — bind checks presence and domain, and coerces nothing

The base enters the verb (#117), so the bind happens at the call, not at construction.

1. Declared column absent → **hard error**, naming the role *and* the column.
2. A value outside `{0, 1}` in `approved`/`hired` → **hard error**.
3. `outcome` accepts null, and the **coverage of the marking becomes a reported number** in the
   result — not an overloaded `NaN` (#116, which closes #101).
4. **No silent coercion.** `bool`, `"S"/"N"`, `"sim"/"não"` are not converted: converting
   automatically would reintroduce inference immediately after killing it.

Reuse across books needs no mechanism — a three-field schema is `dataclasses.replace`.

## Rejected

- **"Sweep what is declared"** — the sweep defaults to the cutoffs the policy declares.
  Rejected by the owner: it forces the user **to write a number that is a lie**,
  `.cutoff("score_1", 600)` where 600 is a placeholder. Same disease as `score_cols`: one
  field, two jobs.
- **A `tune()` marker plus `finalize()`** — the policy declares what is *not* decided. It does
  fix the lying number, and was rejected for what it implies: two states of a policy, and a
  path to automatic adoption.

Both rejections rest on one ruling, and it is the reason the optimiser has no `best`:
**optimisation is always advisory.** *"It's there to show scenarios, and the guy picks what he
wants."* It does not choose, does not finalise, does not adopt. The user runs the experiment,
looks, and **recomposes the policy by hand** at the point they wanted.

## Consequences

- **N scores, N curves** is a `for` over N `Study` — which works precisely because `Study` is an
  immutable value and the verbs are free functions (#117). §9.1 item 8 later corrected the
  card's own snippet, which ran the `for` over `ranges` while reusing one study: that cuts by
  A, B and C under a single lens. The text was right; the example was not.
- **Scale is not this card's problem.** The grid stays an exhaustive cartesian product
  (`optimization.py:177` × `sweep.py:276`): 20 steps × 3 scores = 8,000 points; 5 scores =
  3,200,000. Search strategy is #123.
- **#132** loses its three concrete cases (score, PD baseline, segment) — all dead by
  construction here — and keeps only the general rule of where convenience ends and silence
  begins.
- **#137** has no architectural fix left to make: the anchor no longer exists. It becomes a
  proof of the bug plus an entry in #124's parity whitelist.
- **#125** becomes a real prerequisite for overlaying N curves: the output has to carry who
  produced it.
- **#129** inherits `.rate` taking a PD column reference, and the death of `use_stochastic_draw`
  as an implicit mode. (Both were moved again later: #155 and #152 put the outcome axis on the
  premise as `outcome_from`, and §9.1 item 5 records that **no card decided to kill that path**
  — it was lost to friction between three correct decisions.)
- **The Studio's third spelling dies.** `ColumnRoles` (`studio/models.py:17`) goes; the Studio
  builds a `DataSchema`; `studio/detection.py` stays as a **form suggestion for a human to
  confirm**, never inference that reaches the engine.
