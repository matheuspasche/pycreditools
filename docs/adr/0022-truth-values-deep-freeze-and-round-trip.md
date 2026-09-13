# ADR 0022 — Truth values: deep freeze, total round-trip, and the callable is unexpressible

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the value types of the new surface — how deep the freeze goes, what serialisation
  guarantees, which builder movements exist, and what the two serialisation units carry.
  Excludes *which* types exist (ADR 0019 / #117) and the units' field lists in detail (#126 for
  the rating ruler).
- **Tickets:** #120 (this ADR). Consumes #77, #83, #116, #117, #125, #133, #134.
- **Spec:** the living engine spec, §4.10 (serialisation and identity), §4.2 (builder movements
  and stage identity), §4.3 (the AST).
- **Amended by:** ADR 0015 (which tree is the frozen one — the frozen mirror in
  `engine/_nodes.py`, not the builder). The 2026-09-05 exclusion rule about the `contract`
  vector was **revoked** by #155, not amended; see Consequences.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

Four defects, all measured in #83, and they are one defect seen from four sides: **the types
claim to be values and are not.**

- **Façade immutability.** `CreditPolicy` is `@dataclass(frozen=True)`, yet `_replace` does a
  `copy.deepcopy` before `dataclasses.replace` (`policy.py:90-97`). A real value object never
  needs a deepcopy. It is there because the children are mutable: the stress classes are plain
  classes with free attributes (`stress.py:53`), and `GroupingRecipe` carries fitted state.
- **Round-trip broken by construction.** `CustomStress.to_dict()` returns `str(fn)`
  (`stress.py:126`); `from_dict` raises on that case *on purpose*. The portable rule set has a
  non-portable member.
- **A missing builder movement.** The builders only append (`add_stage`). Deriving *"same
  policy, different cutoff"* — the most common challenger that exists — requires rebuilding the
  whole chain.
- **A default in the shape of a bug.** `AggravationStress.factor_col`:
  `if self.factor_col and self.factor_col in df.columns` (`stress.py:63`). Mistype the column
  name and the semantics silently switch to the scalar factor.

And the mechanism this card owns is a **prerequisite of a decision already taken**: #117 ruled
that `vary` overrides any declared point *by derivation, never by reconstruction*. That is only
implementable with deep freeze and value equality.

> **Rebuilding preserves only what the author remembered to copy; deriving preserves everything
> that was not asked for.**

`sweep.py:164-167` is the proof — sweeping aggravation **discards** the scenario tuple and
substitutes an `AggravationStress`, with no warning; #133 is the same pattern (sweeping
`base_rate` rebuilds `RateStage` with 4 of its 6 fields and drops `observed_col`). Measured
cause: `CreditPolicy` is already a frozen dataclass and `dataclasses.replace` already works on
it (`sweep.py:75`, `:166`, `:169`) — but **no `Stage` is a dataclass** (#134 Q7). Without frozen
children, deriving is impossible and rebuilding is the only way out.

## Decision 1 — deep freeze, in stdlib

Every value type becomes a **frozen dataclass, leaves included**, and `__post_init__` normalises
received `dict`/`list` into `MappingProxyType`/`tuple`. The user keeps passing a plain `dict`;
the conversion is internal.

This is the **only** path on which the `deepcopy` really dies: a shallow freeze still lets
`p.stages[0].cutoffs["score_a"] = 500` through, which is exactly the façade immutability this
card exists to kill.

**Rejected: defensive copy on read** — it allocates on the sweep's hot path, which reads
`cutoffs` once per grid point. `MappingProxyType` does not allocate on read.

No pydantic: the package's dependencies are pandas/numpy/matplotlib/seaborn, and stdlib
suffices.

## Decision 2 — total round-trip by construction: a callable is unexpressible

A stage **does not accept an opaque function**. A rule is declared as an expression or a string,
full stop. No branch of `to_dict` can degrade, so an identical round-trip is guaranteed **by
construction, not by discipline**.

Dead: `CustomStress`, its `to_dict` returning `str(fn)` (`stress.py:126`) and its deliberately
raising `from_dict` (`stress.py:44`) — plus **the twin degradation the card did not catalogue**:
`FilterStage.to_dict` swaps a callable for `{"name": fn.__name__}` (`stages.py:247-256`) and
`from_dict` rebuilds a string/`Expression`, never the function (`stages.py:68-75`). One
pathology, two places.

**Why unexpressible rather than "refuse loudly in `to_dict`".** Deploy is engine
parameterisation: a rule that does not become data is not a rule, it is notebook code. Refusing
only at serialisation creates the policy that simulates beautifully and fails at export — that
is, it surfaces the defect **after** the business decision has already been made on top of it.
Failing in the constructor is failing early.

**Measured cost: zero.** A sweep of the whole repo (`src`, `tests`, `validation`, `docs`) found
**no** `.filter` with a callable. The only live callable is `CustomStress(angled_by_rating)` in
the masterclass (`tutorial_masterclass.ipynb:1103`), and under #117's premise (one inflation)
rating-angled inflation is expressible as a per-row column.

**The escape hatch does not disappear, it moves** — and the new place is *data*, which
serialises: compute the column on the base, filter by the expression. It is the dplyr movement
(`mutate` first, `filter` after), which is what the map's UX ruler asks for.

**Hard tie to #129:** expression/string becomes the **only** path for a condition. What
`Expression`/`df.eval` covers stops being a convenience and becomes a requirement.

## Decision 3 — two serialisation units, distinct purposes

The question *"what does serialisation carry"* was ill-posed: these are **two artifacts with two
purposes**, not one with modes.

- **Deploy = engine parameterisation.** Carries `stages` + the rating ruler, and nothing else.
  The three `DataSchema` roles are vocabulary of a **retrospective** study — in production there
  is no outcome and no approval history. The columns the rules actually read already travel
  **inside the stage itself**, by #118's role≠reference line.
- **Study = reproducibility.** Carries schema + policy + premise + `method`/`seed`. **No base,
  no fingerprint of the base, no name** (#125: the name belongs to the session, so it stays out
  of the serialised value). Reloading returns the declared study; the number returns when the
  user supplies the same base.

**Why no fingerprint of the base.** The guarantee comes from #116's **mandatory seed**, not from
tracking data. Hashing the frame at each bind would give the object an opinion about *which data
is the right data*, contradicting "the same policy over N bases" — the very motivation for the
decomposition.

**Finding: the deploy artifact already exists.** `DeploymentPolicy` is exactly
`policy + rating_recipe` (`deployment.py:42`) and `to_dict` is an alias of `to_production_rules`
(`deployment.py:23-25`). It is badly separated from the rest, not absent. The `metadata` it
carries today (`applicant_id_col`, `score_cols`, `time_col`, `deployment.py:45-52`) dies whole
with #118.

## Decision 4 — one builder movement, and the stage's identity is its name

```python
nova = politica.set_stage("corte_a", cutoffs={"score_a": 640})
```

Same derivation grammar as `vary` (#117); the difference is *kept* versus *disposable* — `vary`
is study scope, and editing a policy outside a study must not require assembling an experiment.
It is the movement #122 made routine: selection is advisory, the human reads the grid and
**recomposes the policy by hand**.

`drop_stage`/`reorder` stay **out** until there is a measured case: stage order is funnel
semantics, and a reorder method hides that.

**Stage identity = the name.** Today `add_stage` merely concatenates, with no check at all
(`policy.py:61-64`). A duplicate name becomes a **hard error at `add`**, mirroring the rule #125
fixed for `Study` names: an explicit duplicate is a hard error, with zero silent
disambiguation.

## Decision 5 — a default that silently switches semantics is a hard error

`AggravationStress.factor_col` (`stress.py:63`) is the same form as the
`resolve_calibration_score_col` cascade #117 killed. **A declared column name that is absent
raises at the bind**, with no fallback. This holds here for the value types; the *general* rule
of where convenience ends and silence begins stays with #132 — and is now written as the ladder
of remedies in `CONTEXT.md`.

## Consequences

- **ADR 0015 later decided *which* tree is the frozen one.** #120's list of frozen types was the
  `Stage`s, the stress classes and `GroupingRecipe` — `Expression` was **not on it**, and #135
  measured why it could not be (`Expression.__eq__` returns an `Expression`,
  `expressions.py:31`). Ticket 4 resolved it with a frozen mirror in `engine/_nodes.py`. Deep
  freeze is untouched by that; what ADR 0015 decides is *which* tree is frozen, not whether.
- **Revoked, not amended.** On 2026-09-05, via #139, this card received *"a stage that feeds the
  `contract` vector does not enter the deploy unit"*. #155 moved the contract axis into the
  premise, so **no stage feeds `contract` any more** and the exclusion has nothing to act on.
  The deploy unit is again *all* `stages`, with no written exception — simpler, because the
  exclusion stops being a rule to remember and becomes true by construction. The boundary that
  rule protected is now protected structurally: take-up lives in the **study unit**, and the
  deploy unit carries no premise, so it can never leak. Anyone reading the 2026-09-05 comment
  from here on should read the 09-06 revocation as the standing one.
- **Declared input to #126:** the rating ruler travels in the deploy artifact. *Where it lives
  as a type*, and the declared-versus-fitted protocol, remain #126's (inherited from #119).
