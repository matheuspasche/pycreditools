# ADR 0029 — Each stage redesigned: `.cutoff` dies, `.filter` over the AST is the one verb

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the internal design of a stage — the ABC, the condition's type, the stage's
  identity, the narrow context, and the collapse of `.rate`. Excludes *which* types exist
  (ADR 0019 / #117), the probabilistic semantics (ADR 0023 / #121) and the surface's validation
  (#145, ADR 0032).
- **Tickets:** #129 (this ADR). Consumes #105, #113, #116, #117, #118, #120, #121, #124, #127,
  #134, #135, #143.
- **Spec:** the living engine spec, §4.2 (`CreditPolicy` — the stage and its label), §4.3 (the
  AST), §4.6 (the engine — the funnel and the fast path).
- **Amended by:** #155 — the Protocol drops to **one** member.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

The owner asked for each main class to be re-discussed **from zero** — roles, arguments,
functions, what can be simplified — not assuming today's shape survives.

Measured state:

- **`Stage` ABC** — `apply(df, method, policy)`. The `policy: Any` parameter is threaded through
  every `apply` purely to resolve the calibration score (`resolve_calibration_score_col`); it is
  the import cycle (a policy contains stages, a stage reads the whole policy).
- **`CutoffStage(cutoffs: dict[str, float], direction: str)`** — direction as the string
  `"gte"`/`"lte"`, although an unused `StageDirection` enum exists in `_types.py`.
- **`FilterStage(condition: str | callable | Expression)`** — three condition types.
- **`RateStage(base_rate, variable, calibrate, observed_col, calibrate_by)`** — five arguments
  with overlapping roles.

Two ties arrived before the decision. **#120** made a callable unexpressible, which turns the
power of `Expression`/`df.eval` from a convenience into a **requirement** of this card; and
**#135** was added as a blocking edge, because weighing expression against string is exactly
what that research costed. (The card had been sitting on the frontier with zero blockers.)

## Decision 1 — `.cutoff` dies; `.filter` over the AST is the one verb

`CutoffStage.apply` and `FilterStage.apply` **are the same function** (boolean mask →
`fillna(False)` → cast). What distinguished the class was not the calculation — it was being the
**addressable numeric knob** that the sweep read structurally
(`optimization.py:144-150`: `isinstance(stage, CutoffStage) for col in stage.cutoffs`) — and
that is what supported #143's fast path (0.73 ms/point against ~82, **~112×**).

**The decision preserves the fast path by re-keying it on the AST**: the condition becomes *"the
varied node is the literal of a comparison inside a hard mask"* — a **structural property the
class only represented by accident**.

Dying with it: `direction="gte"/"lte"` (the operator is in the node — killing the 53 literals
measured in #135), the multi-column `cutoffs: dict[column, value]`, the never-used
`StageDirection` enum, and **11 of the 20 `isinstance`-over-Stage sites**
(`v06-architecture.md:310`, `:373`). The `CutoffStage` subset of those is **9**, and it is all of
them measured at `24a125a`: `sweep.py:56`,
`:70`, `optimization.py:149`, `policy.py:182`, `screening.py:381`, `stages.py:173`, `:200`,
`studio/analyses.py:824`, `deployment.py:224`. The spec's `11/20` is transcribed as the spec
states it and is not re-measured here.

## Decision 2 — the condition is the AST, not the string

`expressions.py` already has the tree (`BinaryExpr(left, op, right)`), already walks it
(`get_columns()`) and already round-trips it — so *"find the literal compared against
`score_a`"* is **the same walk that already exists, not parsing**.

The string leaves the **input** (`df.eval` is opaque, with no node to swap, and would be the one
real workaround) and stays in the **output**: `BinaryExpr.__repr__` already builds the render.
That closes #120's hard tie (*"expression/string has to carry the escape hatch alone"*) from the
expression side.

## Decision 3 — identity is a unique label with a structural default

The label is optional; the default is **derived from the AST** — the referenced column, when the
rule references exactly one. In the three cases where structure does not name — zero columns, two
or more, or a collision with a taken label — the label is **mandatory, a hard error at the
bind**. That label addresses `ranges=` (#118) and `set_stage` (#120).

**Display** in the funnel is the label plus the expression's render, which already travels with
it: one written name, and only when the rule does not explain itself.

Measurements that support it:

- **Addressing by column is already the real scheme**: every sweep consumer addresses by column,
  none by stage name — `optimization.py:150`, `:175`, `:177`, `analysis.py:35`
  (`vary_directions[col_name]`), `deployment.py:230`, `studio/analyses.py:825`.
- **`stage.name` today is a label, not an address, and the code admits it**: across the ~14 sites
  that read it (`simulation.py:85`, `:118`, `:236`, `:250`, `:427`, `:480`, `:488`,
  `visualization.py:429`, `:450`, `policy.py:269`) it **never appears alone** — it is always
  `f"{i+1}: {stage.name}"` or `f"stage_{i}_{stage.name}"`. **Prefixing with the position is the
  confession that the name does not anchor.** The one exception, `sweep.py:173-180`
  (`base_rate_values[stage.name]`), addresses a `RateStage`, whose knob is a scalar **with no
  column** — there is nothing structural to point at. It stops being an exception and becomes
  *"the case where structure does not name"*.
- **The double naming already exists and is already redundant in 3 of 5 cases**: in the
  masterclass, `"Negativation <= 1500"` for `col("vl_negativacao") <= 1500`, likewise SCR and
  Protests. The non-redundant ones are `"Valid CPF"` and `"Incumbent score gate"` — the
  *"rule is not intuitive"* case.

**This is not the inference #118 killed.** The default comes from the AST **the user wrote**,
not from a heuristic over the data, and it **fails hard** instead of choosing silently. And it is
**structural, not positional** — deliberately unlike #125's default, where the object has no
structure to take a name from — so inserting a stage in the middle moves no address, which fixes
the instability the 14 `i+1` sites denounce and satisfies #117's requirement of a stable address
under `vary`'s derivation.

## Decision 4 — the ABC dies; a `Protocol` replaces it, and the `ctx` is narrow

**Measured:** `stage.apply()` has **two** callers (`simulation.py:431`, the funnel loop, and
`simulation.py:555`, a direct call on a `RateStage` outside the loop) against **20 `isinstance`**
— **the polymorphism was pretended**; the code splits by type everywhere. No behaviour is
shared, only the signature, so inheritance delivers nothing, and a structural type matches
#120's deep freeze, which inherits badly.

The `ctx` is **narrow**: the study's seed and the row position (#127), plus the premise when the
stage admits it — **never the policy**. With that the `policy: Any` dies **by construction, not
by discipline**, and the import cycle with it.

## Decision 5 — `.rate` collapses from five arguments to one

**Measured:** the 4 live uses are identical — `base_rate=1.0, observed_col="hired",
calibrate_by="score"` — and the docstring itself says `base_rate` is *"Ignored when
`observed_col` is set"*: **in the only live uses, the mandatory argument is inert.** Five
arguments delivering one behaviour.

Dispatch: `observed_col` dies (#121 — take-up reads `hired`; #116 made `hired` mandatory when
`approved` is declared); `calibrate`/`calibrate_by` leave the stage (calibration is the premise,
#117, ratified in #126, and arrives via `ctx`); `variable: str | float | Expression | callable`
are one thing written four ways, with the callable already dead by #120; `base_rate` is the
scalar case of that same field.

What remains is **one probability, scalar or an AST node** — and the two stages become
symmetric: `.filter` takes a boolean node, `.rate` takes a numeric node in [0,1].

## Rejected

- **Keeping `.cutoff` for the fast path.** Decision 1 shows the property the fast path needs is
  structural, not classy — so the class was paying for something the AST already carries.
- **`df.eval` strings as stage input.** Opaque: no node to swap, so the fast path cannot be
  re-keyed and `set_stage`/`ranges=` lose their address.
- **Keeping the `Stage` ABC.** Two `apply` callers against 20 `isinstance`; nothing shared but a
  signature.
- **A positional stage identity.** It moves every address when a stage is inserted, which is the
  instability the `i+1` prefixes already document.
- **Passing the policy into `apply` (the status quo).** It *is* the import cycle.

## Consequences, and what #155 moved

- **The Protocol drops to one member.** This card decided a **two**-member Protocol —
  `apply(df, ctx) -> Series` plus the **declared vector** (`decision` | `contract`). With the
  contract axis moved into the premise, the second member has **exactly one possible
  inhabitant** — a field that distinguishes nothing — so it goes.
  > **The Protocol has one member: `apply(df, ctx) -> Series`. Every stage feeds `decision`.**
  Simplification, not loss: the narrow `ctx` still kills `policy: Any`, and the fast path's
  re-keying does not depend on the second member.
- **The `.rate` collapse survives, as a premise field.** *"One probability, scalar or an AST
  node"* describes exactly the premise's `take_up`. What changed is that it stopped being a
  builder verb.
- **The `isinstance` list shrinks and vanishes with no replacement.** This card and #121 §1 both
  planned to swap `isinstance(stage, RateStage)` for a partition by declared vector; with a
  homogeneous list the five **funnel-partition** sites in `simulation.py` (`:79`, `:229`,
  `:438`, `:475`, `:552`) simply go — and they are not the whole inventory: measured at `24a125a`,
  `isinstance`-over-`RateStage` occurs at **nine** sites, the other four being
  `simulation.py:341`, `visualization.py:413`, `sweep.py:173` and `deployment.py:235`. A session
  planning the removal should start from the nine, not the five.
  `decision` is the funnel's product, and `contract = decision × take_up` is one application by
  the engine afterwards. Measured in `docs/research/prototype-155-contract-axis.py` (**on an ephemeral
  branch** — `fe2088e`, reachable only from `origin/claude/aoba-b0w0o3`): the
  factorisation is **exact** (`|Δ| = 0`, 4 configurations), the stage's order is **inert**, and
  **zero rows** change `reason` or `decision` when the stage is removed.
- **Point 3 of the card was not this card's decision.** *"Where calibration-score resolution
  lives"* was answered upstream: #117 killed `resolve_calibration_score_col` with no
  replacement. Recorded as inherited, not as decided here.
- **The prototype was deferred, not waived.** Owner's ruling: the new surface is validated in a
  prototyping card of its own — which became #145.
- **Hard break** in the 4 masterclass uses, `studio/policy_builder.py:224`, `policy.py:120`,
  `deployment.py:90`, `sweep.py:174` — on #124's list.
