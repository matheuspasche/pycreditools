# ADR 0027 — There is no fit/predict protocol: rating is a standalone suggester

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the four `predict()`s, the declared-versus-fitted split, where the declared rating
  ruler lives, and what production actually runs. Excludes the verbs' names (#128, #152) and
  `suggest_hard_filters`' signature (ADR 0018).
- **Tickets:** #126 (this ADR). Consumes #113, #117, #118, #119, #120, #122, #125, ADR 0007.
- **Spec:** the living engine spec, §4.9 (suggesters, rating and deployment), §4.6 (the engine —
  half 1 as the production boundary).
- **Amends:** ADR 0022 / #120 — the rating ruler is an **optional**, uncoupled part of the
  deploy artifact, not a structural one.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The fit/predict pattern is scattered, half-built and inconsistent.

- **Four `predict()` with no shared interface**: `GroupingRecipe.predict` (`grouping.py`),
  `RiskGroupResult.predict`, `ScreeningResult.predict` (`screening.py`),
  `DeploymentPolicy.predict` (`deployment.py`) — with different signatures
  (`predict(new_data)` versus `predict(new_data, variable, base_risk_col)`).
- **The declared-versus-fitted split exists with no rule**: `GroupingRecipe` is the declared
  recipe **and** has `predict`; `RiskGroupResult` is the fitted result **and** has `predict`.
  Two families, two designs.
- Free fit functions (`fit_risk_groups`, `fit_pairwise_risk_groups`, `fit_risk_segments`) plus
  dead aliases (`find_risk_groups`, `screen_risk_segments`).

And two inputs arrived from closed cards: #119 overturned #117's dispatch of `rating_recipe`
without saying where the declared ruler lives, because answering that is answering *what exactly
is deployed* — point 5 of this card; and #120 fixed the deploy artifact as `stages` + the rating
ruler.

## Decision 1 — the card is not about fit/predict

**Rating is a standalone suggester**, in the same advisory posture #122 fixed for the optimiser:
**base in, suggestion out, the human uses it or not.**
`suggest_hard_filters`/`HardFilterSuggestion` (`screening.py:243`, `:388`) already had that
shape; `fit_risk_groups` was **the same act dressed as fit/predict** — returning an object that
applies itself.

## Decision 2 — two verbs, against nine surfaces today

```python
suggest_rating(df, *, score, by=None, ...) -> RatingRule
apply_rating(rule, df, *, seed=None) -> DataFrame
```

- **`score=` scalar or tuple = cross the scores into a grid.** **Comparing N candidates is a
  `for`, not an argument** — giving the tuple that second meaning would make *"cross primary ×
  challenger, for each of 3 challengers"* **inexpressible**. That is the silent overload #118
  killed, and it is not reintroduced here.
- **`by=` covers segment and tier, and with it `screening` collapses into this verb**:
  `ScreeningRecipe` holds `boundaries: dict[tier, cuts]` and `sub_mappings`
  (`screening.py:20-23`), which **is** rating's `segmented_intervals` form (`grouping.py:21`)
  with the partition coming from the tier.
- **`seed` is an argument of `apply_rating`, ignored by whoever is deterministic.** This was a
  decided fork: **drawing does not split the verbs**, because the UX ruler (dplyr chaining)
  outweighs marking random state in a name.
- **The suggester does not require a schema.** Measured: `fit_risk_groups` reads exactly **two**
  role columns from the base — `default_col` and `time_col` (`grouping.py:141-151`) — and
  touches neither `approved` nor `hired`. So **#118's `DataSchema` stays intact** and `time_col`
  stays out of it: whoever consumes the date is not the funnel.
- **The policy's rules enter as an optional filter** (cluster only the survivors), which
  resolves what the Studio does today by workaround, without coupling the suggester to the
  policy.

`suggest_hard_filters` stays intact — it suggests a rejection threshold, with budget and lift.
Product of a policy, not of a score.

## Decision 3 — the output is the rule, as its own type

Two forms: **cut** (1 score: `A > 800`) and **grid** (2+ scores: cell → rating).
`quantile_breaks` and `cluster_mapping` become internal to the algorithm and **never escape**.

**The exported rule is a pure cut.** Pushing a rejected applicant into a reserved rating is the
**human's composition** (apply policy, apply ruler), not content of the rule — otherwise the
rule references the policy and stops being independent.

**What that fixes, measured.** Today `GroupingRecipe` has **three mutually exclusive forms**
(`intervals`, `segmented_intervals`, `quantile_breaks`+`cluster_mapping`) and `predict` is an
if/elif/else over which one is filled (`grouping.py:64-108`). **Only the third comes out of the
fit** — the first, which is the readable rule, **only enters by imported JSON**. To export the
rule from a fit, `deployment.py:376-390` runs `for s in range(0, 1001)`: a brute-force integer
sweep that **assumes a 0–1000 score domain** and silently exports the wrong rule for any other
range.

## Decision 4 — declared-versus-fitted does not become a rule of the package

There is no declared spec to type: **the suggester is the verb, the rule is the product.**

`params: dict` dies — measured **write-only** (written at `grouping.py:347` and
`screening.py:230`, and the only reader in the repo is its own `to_dict`) and **incomplete**
(`fit_risk_groups` accepts `max_crossings` and does not record it). And `fit` is a **free
function**, not a method.

**Symptom this erases:** the declared spec was already duplicated and divergent —
`derive_survivor_rating` (`studio/analyses.py:96-104`) retypes `bins=10, max_groups=5,
min_vol_ratio=0.02` against the fit's own defaults (`bins=20`, `min_vol_ratio=0.05`,
`grouping.py:144-146`).

## Decision 5 — swap-in calibration stays outside

`calibrate_by_score_bins` (`_kernels/calibration.py:32`) is a **pure kernel** — it fits and
applies in the same call, with no persisted object. It is the premise of #117: something that
runs **inside the study** and recommends nothing to anybody. The card's point 4 closes by
inheritance.

The consolidation comment had already sharpened the question: with two premise members and only
one of them fitting anything, the question stopped being *"is this a `Fittable`?"* and became
**whether a protocol only half a type's members implement is a useful protocol**. It is not; the
right fit is the member declaring what it needs from the base **at the bind**, which is the
validation pattern #117 established.

## Decision 6 — production runs half 1 and stops

`DeploymentPolicy.predict` **mocks** `applicant_id`, `approved` and `default`
(`deployment.py:419-434`), because the deploy artifact carries the study's `CreditPolicy` and
`validate` (`policy.py:167-174`) requires every declared column to be present.

**The mocks are not inert.** `approved = 1` **chooses a code path** (`simulation.py:466`
branches on a null field) and declares *"everybody was approved before"* — every rejection
becomes a swap-out and swap-in is empty; `default = 0` zeroes the keep-in's baseline PD
(`:686`, `:712`, `:725-736`); `applicant_id` has zero consumers in the engine. And it is silent:
the columns are merely dropped from the output (`:441`, `:468`).

`run_simulation` already has the seam, just undeclared:

- **Half 1** (`simulation.py:414-457` plus the `decision`/`reason` block at `:474-491`): the
  stage loop, `pass_prob`, decision and reason — reads only the columns the stages reference.
- **Half 2** (`:465-472`, `_classify_scenarios:505`, `_assign_simulated_defaults:615`,
  `_estimate_swap_in_baseline_pd:674`): quadrants, simulated outcome, baseline PD — all of it
  needs the three roles plus the premise.

**Production runs half 1 and stops.** Not a separate engine and not duplication: it is the same
half 1 the study runs before continuing. **Both reasons for the mock disappear on their own** —
`validate` demanding a study column dies with #118 (the schema is not in the deploy artifact, so
there is no name to demand), and the `current_approval_col is None` branch dies with #117/#125.
**The mock becomes unexpressible, not avoided.**

## Decision 7 — rating is two objects, and only the ruler was in dispute

Settled in #119 and confirmed here by measurement: `rating_recipe` **does not touch the funnel**
— it does not filter, cut or rate. It appears only in `to_decision_dataframe`
(`simulation.py:160`) and in `export()`/`DeploymentPolicy` (`policy.py:286`,
`deployment.py:269-464`). **Both objects carry the ruler today** (`policy.py:28`,
`deployment.py:21`) and `export()` merely copies one into the other — duplication, not a role.

A decision `predict` needs column names + rules + ruler, and **does not need a premise**.
Consequence recorded: if the deploy artifact were the `Study`, it would force declaring a
premise in order to make a decision that uses no premise at all.

## Rejected

- **A `Fittable`/`Predictable` `Protocol`.** Decision 1 removes the thing it would abstract:
  there is no shared act, only one act (suggest) wearing two costumes.
- **`fit` as a method** (the sklearn shape). It reintroduces the object that applies itself,
  which is exactly what Decision 1 removes; and #117 already put execution in free functions.
- **Splitting `suggest_rating` and `apply_rating` by whether they draw.** Rejected in
  Decision 2: the UX ruler wins.
- **A rating rule that reserves a band for rejects.** Rejected in Decision 3 — it couples the
  rule to the policy.

## Consequences

- **What dies:** the four `predict`s; `fit_risk_groups`, `fit_pairwise_risk_groups` (measured as
  a `for` over challengers with `score_cols=[primary, challenger]`, `grouping.py:404-431`),
  `fit_risk_segments`, `ScreeningRecipe`, `ScreeningResult`, the `find_risk_groups` /
  `screen_risk_segments` shims, the `for s in range(0,1001)` sweep and its 0–1000 assumption,
  the `deployment.py:419-434` mocks, the divergent literals of `studio/analyses.py:96-104`, and
  `params: dict`.
- **And the `.get(rat, 5)` ceiling** (`grouping.py:69`, `:81`), which **collapses any label past
  "E" into 5** while the output remaps 1..26 → A..Z (`chr(64 + i)`) — a six-band ruler comes back
  with five.
- **Amendment to #120:** the deploy artifact is `stages` + an **optional** rating ruler, not
  coupled. With rating standalone, the ruler is exportable on its own and travels along only when
  the user wants decision and score in the same JSON.
- **Out of this card:** the verbs' names (#128, later #152); rebuilding the Studio's matrix
  editor on the readable rule instead of micro-bins (`studio/analyses.py:1166-1247`); and the
  home of the candidate-metrics table (`screening.py:230`) inside the single suggester.
- **ADR 0018** later removed `suggest_hard_filters`' `policy` parameter; what the function *is*,
  as fixed here, was not in question there.
