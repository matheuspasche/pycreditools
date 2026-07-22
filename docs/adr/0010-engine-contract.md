# ADR 0010 — The engine contract: declared schema, column roles, bad marker, calibration

- **Status:** Accepted
- **Date:** 2026-07-15
- **Scope:** the engine's inputs and outputs — `simulation.py`, `policy.py`, `stages.py`,
  `expressions.py`, `_kernels/` — and the `studio/` types that mirror them.
- **Amends:** ADR 0008, on the simulation path only (see [The bad marker
  splits](#the-bad-marker-splits)).
- **Tickets:** #77 (the contract), #78 (the seams), #63 (this ADR).
  Plan: `docs/refactor/00-architecture-refactor.md`.

## Context

The diagnosis (#62) found the engine's real contract is an **undeclared DataFrame
schema**: `new_approval` changes dtype by simulation mode, `"hired"` is hard-coded as a
fallback, column roles are spelled once in the engine and again in `studio/models.py`, and
the policy is carried twice on `CreditSimResults` with `to_dict()` producing a third
shape. Nothing declares any of it, so every consumer re-derives it by reading the source.

## Decisions

### The DataFrame stays, and gains a declaration

pandas remains the transport. The results frame gains **one artifact** that declares it:
column-name constants, a schema type carrying each column's meaning and dtype, and
validation at `run_simulation`'s exit.

Rejected: replacing the frame with typed objects. The frame is what users want; what was
missing was the declaration, not a different container.

### `new_approval` is always a float weight in `[0, 1]`

`stochastic` emits exactly `0.0`/`1.0`; `approved_pre_rate` follows the same rule. The
`mean() if analytical else (>0).mean()` branch at four sites dies.

Note for anyone auditing the change: that branch was **already a no-op** — the mean of a
0/1 column *is* the fraction of positives. This decision mostly declares what was already
true. `== 1` continues to match `1.0`.

### Column roles are one object in the engine

Roles become a single input-schema object owned by the engine. `CreditPolicy` = that
object + composition. `studio/models.ColumnRoles` and `studio/policy_builder.build_policy`
die with it — they were the second spelling.

### The bad marker splits

This is the amendment to ADR 0008.

- **For measurement** — the suggester's `bad_col` (#73) — the marker is **any column whose
  mean is the bad rate**: an observed 0/1 flag or an estimated PD, identical mechanics, no
  mode. Both targets are biased in opposite directions (observed overstates, inferred
  understates), so the suggester **declares which one it used**. #60's note stands exactly
  where it was written.
- **For simulation** the contract narrows: `market_default_col` requires **0/1** and
  raises on a probability column. There, the dtype changes behaviour, and a modelled PD is
  circular — it validates a policy against your own model's opinion (#61).

### No input PD column exists

`estimated_default_col` dies as a **concept**, not just a name. A continuous PD survives
only as internal machinery of scenario 1 below.

Three scenarios, declared instead of inferred:

1. **Internal marking only** → swap-in PD from the score→PD calibration of the keep-ins,
   plus **stress**.
2. **External 0/1 only** → the flag; no stress.
3. **Both** → the flag for swap-ins; no stress; warn **once**.

Stress is the **declared assumption** ("whoever I rejected is X% worse") and the preferred
path. The inference is a **borrowed ruler** and an opt-in — not a degraded mode, and not
gated behind a family of warnings.

This makes declared semantics out of an undocumented quirk: today, setting the column
silently causes stress to be **ignored** (`simulation.py:547-557`).

### Calibration is one primitive, with the warning inside

`simulation.py:692-719` and `expressions.py:233-257` are the same block, and #68 was about
to write a third. It becomes one **pure** `_kernels/` function —
`(cal_scores, cal_values, ref_scores, target_scores, bins) → rate per row`, reading no
`policy` — with #58's detection **inside it**, so the warning covers
`CalibratedExpression` and #68's `calibrate_by` for free.

Shipped in two steps (decided on #63): #79 extracts the pure primitive in v0.5 and blocks
#68; #72 then puts both triggers inside it, so #68 inherits the warning without being
reopened.

> **Correction (2026-07, #72).** #79 shipped the pure primitive as planned, but #72
> deliberately did **not** move both triggers inside it. The primitive is
> **value-agnostic** — `cal_values` is an anonymous `float64` Series; a PD (0/1
> default) and a take-up/antifraud rate (0/1 outcome) are structurally identical, and
> the primitive reads no `policy`, so it cannot tell them apart. The two triggers do
> not generalise equally:
>
> - **No-overlap** is universal — extrapolating beyond the observed score range is
>   unmeasured for *any* calibrated quantity — so it *could* live inside the primitive
>   and cover the other callers "for free".
> - **Inversion** is PD-specific: it means "risk moves against the score's declared
>   direction". A rate has no canonical risk direction (approval-propensity rises with
>   risk; conversion falls, because of credit-seekers), so running it on a rate is a
>   false alarm.
>
> Decided on #72: detection stays in the **PD caller** (`_estimate_swap_in_baseline_pd`),
> which is the only site that *knows* it is calibrating risk and can declare a direction.
> Rate paths (`CalibratedExpression`, #68's `calibrate_by`) are left unwarned by choice —
> the ADR's original goal was to avoid **class proliferation** (one primitive, not three),
> which #79 already achieved; forcing the reliability warning onto every calibrated rate
> was never the goal. The warning is raised under `CalibrationReliabilityWarning` so a
> caller can mute it with one `filterwarnings`.

**The calibration population is a parameter and must stay one.** `simulation.py:598`
calibrates on `scenario == KEEP_IN`; `expressions.py:186` calibrates on
`current_approval_col == 1`, which is `KEEP_IN ∪ SWAP_OUT`. This is not a bug and cannot
be unified: the second runs *while the stages are being evaluated*, when `new_approval`
does not exist yet.

### `Stage.apply(df, ctx)` — the child stops reaching back into the parent

```python
@dataclass(frozen=True)
class ApplyContext:
    schema: InputSchema
    incumbent_approved_mask: pd.Series
    method: SimulationMethod
```

`ApplyContext` is a leaf: it imports neither `policy` nor `stages`. The
`policy ↔ stages` cycle therefore loses an edge rather than being silenced.

**The name is `incumbent_approved_mask`, not `keep_in_mask`.** In this engine `KEEP_IN` is
the quadrant `old == 1 & new == 1` (`simulation.py:429-438`); the mask a stage needs is
`old == 1`. It cannot be the quadrant — when a stage runs, `new_approval` does not exist.

Rationale, stated precisely because #78's was not:

- **Not typing.** `stages.py:1` already carries `from __future__ import annotations`, so
  `if TYPE_CHECKING: from .policy import CreditPolicy` would type `policy` today in three
  lines. `ApplyContext` is not needed for that and must not be justified by it.
- **`method` as Enum closes a class of bug that already bit.** `_types.py` defines
  `SimulationMethod(str, Enum)` and `StageDirection(str, Enum)`, and the code unwraps them
  at the boundary — `simulation.py:352` calls `stage.apply(df, method=method.value, ...)`
  so each `apply` string-compares. #57 proved the cost: the Bancada trade-off curve is
  inverted because `vary_cutoff` writes `">="` where the code tests `"gte"`.
- **A stage should not need the whole policy.** `CutoffStage.apply` and `FilterStage.apply`
  take `policy` and never read it. `RateStage` asks its parent for its siblings to learn
  whether it is itself the last one (`stages.py:262`) — #68 kills that; after it, one field
  remains, resolved twice per call.

### A scalar/anonymous RateStage does not re-gate the keep-in

This is the declarative resolution of #94, whose ablation ladder (#93) isolated the
first divergence between the engines to a single quadrant.

A `RateStage` sourced from a **pure scalar** — `base_rate` only, no `observed_col` and no
`variable` — applied to a book with `current_approval_col` active, **bypasses** the
keep-in population: every keep-in passes at `1.0`, and swap-ins pass at the scalar rate.

- **`main` re-gated the keep-in** by an implicit **name/position heuristic** of the
  `RateStage` (#91), applying a fractional (score-calibrated) rate to the incumbent book —
  the very kind of inference this ADR abolishes (see the `ApplyContext` rationale, where
  #68 kills the stage asking its parent whether it is the last one).
- **v0.5 sources the keep-in's take-up from what is *recorded* about it.** With
  `observed_col`, the keep-in takes its real `0/1` outcome (`stages.py`, `_observed_probs`
  + the caller override). Absent a recorded outcome, its membership in the incumbent book
  is the only fact; its contribution to contracted volume is **taken as given (`1.0`)**,
  never re-drawn from a swap-in-calibrated rate. This is the exact analogue of the
  `observed_col` rule: "keep-in take-up comes from what the data records about the keep-in;
  a scalar rate records nothing, so the book passes through."

Decided: **v0.5's declarative bypass is the contract.** `main`'s re-gate is the bug. The
scope is only the scalar/anonymous rate over keep-ins; the `observed_col`/`variable=`
take-up paths are unchanged. Locked by `tests/test_scalar_rate_keepin_contract.py`
(with `base_rate < 1.0`, so bypass `1.0` and re-gate `base_rate` are distinguishable —
the pre-existing `test_name_conversao_is_not_special_without_observed_col` uses
`base_rate=1.0`, where the two coincide). The v0.5 engine already honours this; no engine
change was required — the deliverable is the declared contract plus the regression lock.

### Serialized state carries a version

`ProjectBundle` gains `schema_version`; deserialization becomes strict (unknown key
raises, missing required field raises); an older file is **refused loudly**, not migrated.
Absence of `schema_version` identifies "saved by v0.5".

Rationale: `CreditPolicy.from_dict` reads every field with `d.get(...)`, so renaming or
removing a key returns `None` in silence and the policy runs without the role. The stamp
is what converts the plan's only silent failure modes into loud ones. A converter was
rejected — it makes every future slice owe a migration, permanent debt for a pre-1.0 local
tool, and it can be added later precisely because the stamp exists.

## Consequences

- `Stage` is exported in `__all__` and `apply` is its abstract method, so client
  subclasses break with a `TypeError`. Pre-1.0, and `register_callable` shows extension is
  an intended use case — the break is deliberate and loud.
- `_run_estimated_pd_stress_sweep` (`studio/analyses.py:826`, #49's workaround) dies:
  pre-scaling a 0/1 column saturates for every factor ≥ 1, so the slider it was built for
  was already flat on #61's canonical material.
- The `stages ↔ expressions` cycle is closed by #79 in v0.5, ahead of this ADR's own work.
- The `policy ↔ simulation` cycle (`policy.py:145`) is **not** addressed here and remains
  undecided.
