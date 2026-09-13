# ADR 0021 — Study premises: what leaves the policy, and the two things called rating

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the field-by-field dispatch of today's 13-field `CreditPolicy` (`policy.py:21-33`),
  the fate of `rating_recipe`, and whether comparing N policies needs a container type.
  Excludes the shape of the premise object itself (§4.4, ADRs 0030 and 0034).
- **Tickets:** #119 (this ADR). Consumes #83, #113, #116, #117, #118, ADR 0003, ADR 0004,
  ADR 0007.
- **Spec:** the living engine spec, §4.2 (`CreditPolicy` — `stages`, and nothing else), §4.0
  (the four types), §4.4 (`Premise`).
- **Amended by:** #155 (`stages` keeps **one** verb and **one** vector), #152 and §9.1 item 1
  (comparing-N needs no verb at all — `simulate` takes a collection and `delta_table` reads).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

#117 drew the boundary between the four types. This card does the inventory: **which of the
13 fields actually leaves, and where each one lands** — because a partition that names boxes
without emptying the old object is a diagram, not a decision.

Three costs of the current fusion, measured:

- **Silent semantic collision.** A present `estimated_default_col` makes the stress be ignored
  with no noise (`simulation.py:551`). The collision exists *only* because two unrelated
  concepts share one object.
- **`policy.stress(1.5)` does not create a new policy — it creates a new study**, and the type
  has nowhere to say so. The API forces cloning the policy once per scenario.
- **Optimisation under stress is unexpressible.** *"Pick the cutoff that survives stress_30"*
  needs premises orthogonal to the policy being swept. With stress fused in, every sweep runs
  either contaminated or blue-sky, never chosen.

A consolidation audit on 2026-08-14, asked for by the owner with explicit caution before
closing, kept the card open: two items were still alive. That caution paid — one of them
turned out to be a **misdispatch by #117**.

## Decision 1 — `CreditPolicy` keeps `stages`, and nothing else

| field | dispatch | source |
|---|---|---|
| `applicant_id_col` | dies — fabricated with `range(len(df))` (`deployment.py:422`) | #118 |
| `score_cols` | dies whole | #118 |
| `time_col` | dies — zero consumers in the core | #118 |
| `estimated_default_col` | dies — becomes the outcome axis of the premise | #118 |
| `calibration_score_col` | dies, with no replacement | #117 |
| `current_approval_col` | `DataSchema.approved` | #118 |
| `current_hired_col` | `DataSchema.hired` | #118 |
| `actual_default_col` | `DataSchema.outcome` | #118 |
| `stress_scenarios` | the inflation, inside the premise | #117 |
| `calibration_bins` | `bins` on the premise | #117 |
| `calibration_base` | premise config (later `calibrate_on`, #139) | #117 |
| `rating_recipe` | **deferred → #126** | this card |
| `stages` | **stays — it is the policy** | #117 |

It closes clean: every field either dies or has a named home, and exactly one deferral remains,
addressed rather than left open.

**Seed** was sent to #127 by the audit, but #116 had already ruled that `method` + `seed` are a
**premise of the study, with the seed mandatory**. The home was decided; what is left to #127 is
the *mechanism* (killing the global `random` in the core), not the dispatch.

## Decision 2 — rating is two different objects with the same name

|  | the declared recipe (`GroupingRecipe`) | the population-relative label |
|---|---|---|
| lives in | the engine: `policy.py:28`, `deployment.py:21` | the Studio: `studio/analyses.py:96` (`derive_survivor_rating`) |
| when it fits | once, declared, serialised | refits **every run**, over the survivors |
| touches the funnel | **no** | **no** |
| origin | ADR 0004 | ADR 0007 (`MUST NOT touch the package engine`) |

**Why this overturns #117's dispatch.** #117 split `rating_recipe`'s three roles and sent
*rating post-processing* and *deploy artifact* to **the rules**. Measured: `rating_recipe` does
not filter, does not cut, does not rate. It appears only in `to_decision_dataframe`
(`simulation.py:160`, the `rating` column) and in `export()`/`DeploymentPolicy`
(`policy.py:286`, `deployment.py:269-464`).

> **A rule is what changes who passes. The recipe changes no one.**

So the recipe is not a rule, and the dispatch falls. And the **population-relative label** is
*derived from the bind* — computed over the survivors of the run — which puts it in the
category the owner fixed on 2026-07-26: *"derived from the bind: an invisible internal object,
computed once"*. It stays in the Studio, under its own name, and **never enters the engine**.

ADR 0007 already recognised both without naming them as two: it retains the static
`state.rating_result` *"for deployment, decision preview"* while the bench label is re-derived.
Its own consequence line — *"comparing two policies by rating label is misleading"* — is the
same fact seen from #125: identity and comparison-by-rating-label are not the same thing.

**Where the declared recipe lives is left open on purpose.** Answering it requires knowing
*what exactly is deployed* under the decomposition — a question that already has an owner,
**#126 point 5**. Delivered to #126 as a declared input: **both objects carry the recipe today**
(`CreditPolicy.rating_recipe` and `DeploymentPolicy.rating_recipe`) and `export()` merely
copies one into the other — that is duplication, not a role. And `predict()` lives on
`DeploymentPolicy` (`deployment.py:414`), not on the policy: a decision `predict` needs column
names + rules + recipe, and **does not need a premise**.

## Decision 3 — the object carries ONE policy; comparing N is a verb, not a container

Already denied twice by table — #117 (`vary` takes ONE meeting) and #118 (*"N curves = a `for`
over N `Study`"*). This card closes the remaining half: comparing N is a first-class **verb**
over a collection of `Study`, returning a **long table, one row per study**.

**No container type.** `workflow_set` does not port — #113 measured that sklearn has no
analogue — and a type that aggregates N policies contradicts #117 and #118 directly.

**Consequence recorded: #125 (identity) is a prerequisite for the shape of that verb.** Without
a proper name the output reproduces today's `Old`/`New 1`/`New 2`:
`compare_policies(sim_new: ... | list, sim_old)` (`performance.py:127-142`) already takes a
list, already recurses by position, and already writes literal columns. The new verb must not
be born with that defect.

## Rejected

- **`rating_recipe` as a rule of the policy** (#117's dispatch) — falls on the measurement
  above: it changes nobody's decision.
- **`rating_recipe` as a study premise** — it is not an assumption about the unobserved either;
  it is a declared ruler that is deployed. Neither box fits, which is the signal that there were
  two objects.
- **A container type over N policies** (`workflow_set`) — no analogue in the precedent read
  (#113), and it re-fuses what #117 just split.

## Consequences

- **§4.2 keeps the answer to "is a list of one verb still a type?"** — yes. After #155 cut
  `stages` down to a single verb (`.filter`) declaring a single vector (`decision`),
  `CreditPolicy` still is not a `list[Filter]`, because it carries three things a list does not:
  the **labels** (key of `ranges=` in #118, grid coordinate in #146), **composition validation
  without a base** (the first of #117's two validation moments), and the **deploy unit** (#120).
- **Collateral, measured in #155:** the 5 `isinstance(stage, RateStage)` sites
  (`simulation.py:79`, `:229`, `:438`, `:475`, `:552`) **vanish with no replacement** — the list
  becomes homogeneous and there is nothing left to partition. That is *less* machinery than
  #121 §1 had decided to install in their place.
- **The three measured collisions all fall out.** `estimated_default_col` silencing the stress
  stops being a collision (inflating an externally observed outcome is a hard error, §4.4);
  `policy.stress(1.5)` becomes sayable, because the study has a type; and optimisation under
  stress becomes expressible, because the premise is orthogonal.
- **Later amendment, recorded rather than silently merged:** §9.1 item 1 took Decision 3 one
  step further — comparing-N needs **no verb of its own**. `simulate` accepts a collection and
  `delta_table(results, baseline=)` reads; `compare` is never born. The *content* of this
  decision survives intact (a long table, one row per study, no container type); what changed is
  **which verb produces it**. See ADR 0036.
