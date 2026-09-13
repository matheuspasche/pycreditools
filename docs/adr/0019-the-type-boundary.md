# ADR 0019 — The type boundary: four declared types, and free functions execute

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the partition of today's `CreditPolicy` — how many types the v0.6 surface has,
  what each one carries, what each is called, and who runs a simulation. Excludes the fields
  of any one type (#118 for the schema, #119 and #155 for the premise, #129 for the stage).
- **Tickets:** #117 (this ADR). Consumes #83, #111, #116.
- **Spec:** the living engine spec, §4.0 (the four types), §4.1 (`DataSchema`), §4.2
  (`CreditPolicy`), §2.1 (*"method declares, free function computes"*).
- **Amended by:** #118 (the *"sole owner of column names"* line is not literal), #155 (the
  contract axis is a premise field, so no stage declares an axis), #152 and #139 (the two
  premise types collapse into one `Premise`).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The critique that opened the map (#83) measured one defect: `CreditPolicy` fuses four things
that change for four different reasons — the **data schema** (`applicant_id_col`,
`score_cols`, `current_approval_col`, `actual_default_col`, `time_col`, `current_hired_col`,
`estimated_default_col`), the **rules** (`stages`), the **study premises**
(`stress_scenarios`, `calibration_*`, `rating_recipe`) and **engine behaviour**
(`.simulate()`, `.export()`, `.validate()` — a config object that also executes).

A bank's credit policy does not contain *"multiply PD by 1.5"*. That sentence is the whole
argument: the object's name was lying about three quarters of its contents.

This is the axis card of the map — *"quase tudo depois depende dele"*. Every later card
either fills one of its boxes or moves a field between them.

## Decision 1 — four declared types, and the base is not one of them

| type | carries | which part of the critique it answers |
|---|---|---|
| `DataSchema` | which column plays which **role** | takes the data bind out of the policy |
| `CreditPolicy` | the rules, and only them | the 23-method god object becomes one role |
| the premise | what is assumed about the **unobserved** | takes the study out of the policy |
| `Study` | the meeting of the three; the base enters the verb | gives a type to what has none today |

`CreditPolicy` **keeps its name**. After the partition it is only rules, so the name stops
lying — and it is safe to keep because the class receives *today* exactly the kwargs that
migrate away (`applicant_id_col`, `score_cols`, `current_*_col`). Old code therefore raises
`TypeError` on an unexpected kwarg: a **loud, immediate break, never a silent change of
meaning**. That is the property being bought, not the word.

**The base enters the verb, never the type.** This is what makes a policy portable across
books, and what removes any reason to cache something derived from a bind.

## Decision 2 — free functions execute

`simulate`, `tradeoff`, `choose`, `export_*`, the reading verbs and the suggesters are **free
functions**, not methods. **No method on the meeting reads only one part**; derivation is
`dataclasses.replace`.

**Why.** The fourth item of #83's critique is *"a config object that also executes"*. A method
on `Study` would re-create it one level up: the object would again be both the declaration and
the runner, and the only thing achieved would be moving the fusion. The spine the owner later
froze in #152 states the same rule from the other side — *"method declares, free function
computes; no method touches the base"* — which is why this decision survived every later
amendment untouched.

**The premise is never `None`.** Omitting it does not build silence; the `Study` requires it.
What may be omitted is a *field* of it, and then the default is **literal in the signature**,
readable in `help()`. This is the ladder of remedies applied to construction: a silently
absent premise is an inference, and inference is what the map exists to kill.

## Decision 3 — a variation of premise is another study, never another dimension

This single rule closed three separate forks in the deciding session (the lens, `stress` under
`vary`, and an aggregator over inflations). It holds because two points computed under
different premises **are not comparable** — putting them on one grid invites exactly the
mistake the grid exists to prevent.

Its corollaries, all decided here:

- **One inflation, no aggregator.** `max(pd×1.3, pd×1.8) = pd×1.8` always. `WorstCase` dies;
  N hypotheses are N studies.
- **Inflation lives inside the member that admits it**, so inflating an externally observed
  outcome is *unexpressible by construction* — rung 1 of the ladder — rather than policed at
  runtime.
- **`vary` takes the whole meeting** and may override any declared point — rule, schema or
  premise — but only by **derivation**, and the result is disposable: it gives a dimension of
  impact, it does not become config. Which is why `sweep.py:164` — sweeping aggravation
  *discards* the scenario tuple and puts an `AggravationStress` in its place, unannounced —
  and #133 are **the same reconstruction bug**. *Rebuilding is not varying.*

## Rejected

- **Schema and data as one type.** Rejected by the principle that fell three times in one
  session (sweep vocabulary, `segment_col`, OOT/vintage): *an axis of experiment or analysis is
  an argument of the verb; a role in the funnel is schema.* A funnel role is finite and the
  engine always reads it; an analysis axis is open and per call. Fusing them makes the open set
  a field, which is how `segment_col` came to be **guessed** from `["region","loja","safra"]`
  (`simulation.py:271`).
- **Splitting `Study` into premises + execution.** The execution half would be an object whose
  only job is to run — the god object again, smaller.
- **A method `study.simulate(df)`.** Same objection as Decision 2, and it hands the user a
  computation path that skips the bind.
- **Renaming `CreditPolicy`.** The rename buys a truer word and loses the `TypeError`: renamed,
  the old symbol simply disappears and the break stops being diagnosable at the call site.

## Consequences, and what later cards moved

- **#118** amended the phrase *"sole owner of column names"*, which read literally would
  forbid `.filter(col("score_5") >= 700)` — a form this same resolution kept. The standing
  line is **role ≠ reference**: the schema owns the names the engine reads *by role*
  (approved, hired, outcome); the policy names the columns its *rules reference* (score,
  income, PD).
- **#155** completed the partition by its own logic: the **contract axis** was left split —
  its knobs (`bins`, later `calibrate_on`) had already moved to the premise while the
  declaration that the axis exists stayed as a `RateStage` inside the policy. With `take_up`
  a premise field, **no stage declares an axis any more**: every stage feeds `decision`, and
  the premise declares both estimated axes.
- **#139 and #152** collapsed the two premise members (`Parcelling`/`External`) into one
  `Premise` with modes. The *partition* decided here is untouched by that; what changed is how
  many classes the third box needs.
- **#118**'s question *"what happens when the anchor is not declared"* dissolves — nobody
  points at a score, and `resolve_calibration_score_col` goes away without a replacement. Read
  narrowly: it is the **cascade** that died, not the risk axis (§9.4).
- **#120** inherits the construction surface and the *classitis in the builder* warning; this
  card deliberately decided none of it, and recorded that the old 15/16/17/18-line measurement
  is void because it was taken over dead forms (`calibrate_by=`, `ScoreBins(score=)`).
