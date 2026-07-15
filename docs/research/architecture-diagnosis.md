# Architecture diagnosis — pycreditools at v0.5

Findings for wayfinder ticket [#62](https://github.com/matheuspasche/pycreditools/issues/62), map [#54](https://github.com/matheuspasche/pycreditools/issues/54).
Read of `src/pycreditools` at `release/v0.5` (2026-07-15).

**This document maps the pain. It proposes nothing.** The target architecture is
[#63](https://github.com/matheuspasche/pycreditools/issues/63)'s decision, and every finding below is
raw material for it, not a recommendation in disguise.

## The pain, restated

Two experienced Python readers — the co-author and a strong pythonist friend — both bounce off the
code. The ticket's hypotheses were "too many files?" and "too many classes?". Neither survives the
count:

| | count |
|---|---|
| Python files under `src/` | 47 |
| Total lines under `src/` | 11,023 |
| Engine modules (package root) | 16 files, 4,826 lines |
| Classes in the whole package | 35, of which 9 are `Expression` AST nodes or `Enum`s |

47 files and 35 classes is a small package. A reader who cannot follow it is not being defeated by
volume. The findings below point at what they are actually being defeated by: **the same concept is
spelled three times in three layers, and the real contract between those layers is an undeclared
DataFrame schema that no type mentions.**

## Module map

Four layers, each importing only downward. That much is clean — no upward import exists
(`studio/` never imports `gui/`).

```
_kernels/          iv.py, ward.py, tier_metrics.py            440 lines  numeric primitives
   ↑
engine/            (package root, 16 modules)                 4,826     policy, stages, simulation,
                   policy · stages · expressions · stress ·             optimization, analysis,
                   simulation · optimization · analysis ·               performance, grouping,
                   performance · grouping · screening ·                 screening, deployment,
                   deployment · visualization · sample_data             visualization
   ↑
studio/            analyses · charts · policy_builder ·        2,818     orchestration returning
                   detection · models · data · projects                  plain data. No streamlit.
   ↑
gui/               session · data_access (cache shims)         2,906     streamlit skin
                   pages/ (8) · components/ (8) · theme
```

The layer rule is documented — `studio/analyses.py:1-5` and `studio/models.py:1-4` both carry *"No
`streamlit` import allowed here — see `00-overview.md` §4b"* — and it holds: 17 files import
streamlit, all under `gui/`.

### Class inventory (33)

| Module | Classes | Note |
|---|---|---|
| `policy.py` | `CreditPolicy` | frozen dataclass, **13 fields** |
| `stages.py` | `Stage`(ABC), `CutoffStage`, `FilterStage`, `RateStage` | |
| `stress.py` | `StressScenario`(ABC), `AggravationStress`, `MonotonicStress`, `CustomStress` | |
| `expressions.py` | `Expression`, `ColumnExpr`, `BinaryExpr`, `UnaryExpr`, `CalibratedExpression` | an AST |
| `simulation.py` | `CreditSimResults` | |
| `optimization.py` | `OptimizationResult` | |
| `analysis.py` | `TradeoffAnalyzer` | merged into one engine by [#71](https://github.com/matheuspasche/pycreditools/issues/71) |
| `performance.py` | `ModelEvaluator` | |
| `grouping.py` | `GroupingRecipe`, `RiskGroupResult` | |
| `screening.py` | `ScreeningRecipe`, `ScreeningResult` | |
| `deployment.py` | `DeploymentPolicy` | |
| `_types.py` | 4 `Enum` + `PolicySummary` TypedDict | |
| `studio/models.py` | `ColumnRoles`, `OpenMatrix`, `TierDetection`, `PolicyScenario`, `PolicyEntry`, `ProjectBundle`, `StudioState` | |

The class count is not the problem. `studio/` has **zero** classes beyond those seven dataclasses —
its 2,700 lines are free functions.

## Findings

### F1 — Every verb is spelled three times

`run_policy_sim`, `run_tradeoff`, `run_crash_test`, `aggravation_game`, `run_optimization`,
`suggest_scenarios`, `fit_risk_groups`, `build_open_matrix`, `score_batch`, `compute_ks`,
`compute_ks_table` each exist at three addresses with three signatures:

1. the engine function (`optimize_cutoffs`, `policy.simulate`, …);
2. a `studio/analyses.py` wrapper that adapts arguments and returns plain data;
3. a `gui/session.py` wrapper that adds `@st.cache_data` and **cache-key-only parameters**.

`gui/session.py` is 329 lines and 19 functions, essentially all of this shape
(`gui/session.py:108-118`):

```python
@st.cache_data(show_spinner="Simulando política...")
def run_policy_sim(_df, df_hash, population, _policy, policy_key, method="analytical"):
    """Cached policy simulation; `df_hash`/`population`/`policy_key` are cache-key-only."""
    return analyses.run_policy_sim(_df, _policy, method=method)
```

`analyses.run_policy_sim` is itself `return policy.simulate(df, method=method)`
(`studio/analyses.py:47-51`). Three hops, two of them pure forwarding, and the middle one is the only
place a reader can look up what the call means.

The cost lands on the reader as a search problem: grepping `run_tradeoff` returns three definitions
and none of them is obviously the one that computes anything. `gui/data_access.py` (53 lines) is the
same pattern over `studio/data.py`.

Note the caching is doing real work — Streamlit needs the `_`-prefixed unhashable args and explicit
key params — so this layer is not gratuitous. It is the *only* layer with a stated reason to exist.

### F2 — Metric math is reimplemented per output format

The engine's `performance.py` prints; the studio's `analyses.py` returns DataFrames. Neither calls
the other, so the arithmetic exists twice:

| Console (engine) | Data (studio) |
|---|---|
| `performance.print_delta_table` (`:282-440`) | `analyses.delta_table` (`:643-692`) |
| `performance.print_quadrant_summary` (`:443`) | `analyses.quadrant_table` (`:373`) |
| `performance.print_swap_in_by_rating` (`:506`) | `analyses.swap_in_by_rating` (`:397`) |
| `performance.print_rating_quadrant_table` (`:550`) | `analyses.attach_rating` + `risk_tier_distribution` |
| `performance.ModelEvaluator.compute_ks` (`:203`) | `analyses.evaluate_scores` / `ks_table` (`:231`) |

The duplication is not suspected — it is **declared in the docstring**
(`studio/analyses.py:646`):

> Reproduces `print_delta_table`'s single-comparison branch.

And the two copies of the bad-rate line are character-identical modulo whitespace
(`performance.py:356` vs `analyses.py:678-682`):

```python
bad_new = (df_new["simulated_default"] * df_new["new_approval"]).sum() / vol_new if vol_new > 0 else 0.0
```

`print_delta_table` compounds it internally: 160 lines in which the legacy-extraction block appears
**three times** (`:306-329`, `:330-343`, and the multi-sim branch re-derives the same numbers), and
the single-sim and multi-sim renderers repeat the approval/bad/volume triple line by line. The
function is metric math and console formatting fused; there is no seam at which the numbers exist
without the `print`.

ADR 0008 named `delta_table` and `summarize_results` as the reference implementations of the metric
contract, which means the *reference* currently lives in the copy, not the original.

### F3 — The real interface is an undeclared DataFrame schema

`run_simulation` returns `CreditSimResults`, whose `data` frame is the actual contract. Every
downstream module reads it by string literal. Occurrences across `src/`:

| column | hits | meaning (nowhere declared) |
|---|---|---|
| `new_approval` | 44 | final decision, int in stochastic / float probability in analytical |
| `scenario` | 34 | `keep_in` / `swap_in` / `keep_out` / `swap_out` |
| `simulated_default` | 24 | |
| `approved_pre_rate` | 19 | approval before rate stages (ADR 0008's numerator) |
| `reason` | 16 | `"Approved"` or `"<i>: <stage name>"` |
| `hired` | 16 | **a literal column name the engine falls back to** |
| `stage_*` | 7 | `f"stage_{i}_{stage.name}"` |

Two consequences a reader hits immediately:

- **The same column changes type by mode.** `new_approval` is `int` under `stochastic` and a
  probability `float` under `analytical` (`simulation.py:362-373`). Every consumer therefore
  re-derives the mode and branches on it — `df[col].mean() if is_analytical else (df[col] > 0).mean()`
  appears in `performance.py:326`, `:340`, and `analyses.py:657`, `:672`.
- **`"hired"` is hard-coded as a fallback role** in both copies of the delta math
  (`performance.py:327`, `analyses.py:655`): `legacy_hired = "hired" if "hired" in df_old.columns else old_approval_col`.
  The dataset's column naming is load-bearing.

`reason == "Approved"` is the definition of the survivor population (`analyses.py:62`) — an ADR-0001
concept whose implementation is a string comparison against a label built for display
(`simulation.py:401-404`).

### F4 — The policy is carried twice, and consumers read the dead copy

`CreditSimResults` holds **both** (`simulation.py:15-19`, `:410-415`):

```python
policy: CreditPolicy | None = None            # the object
metadata = {"policy": policy.to_dict(), ...}  # a dict of the same thing
```

29 reach-ins into `metadata["policy"][...]` exist across `performance.py` and `studio/analyses.py`,
e.g. `policy_old["actual_default_col"]`, `policy_dict.get("current_approval_col")`. The typed
`sim.policy` attribute is right there and goes unread. Every consumer thus works against a
stringly-typed dict with no autocomplete and no type checking, of a policy that *is* an object in the
same dataclass.

`CreditSimResults.to_dict()` (`simulation.py:21-25`) returns only `metadata` — dropping `data` and
`policy` — so the serialization story is a third shape again.

### F5 — Column roles are declared three times

The same semantic mapping (which column is the score, the default, the approval flag) exists as:

1. **`CreditPolicy`'s 13 fields** (`policy.py:21-33`) — `applicant_id_col`, `score_cols`,
   `current_approval_col`, `actual_default_col`, `time_col`, `current_hired_col`,
   `estimated_default_col`, plus 3 calibration fields, stages, stress, rating recipe. Config and
   composition in one frozen dataclass.
2. **`ColumnRoles`** (`studio/models.py:17-30`) — 10 fields, 7 of them the same names as (1), plus
   `segment_col`, `oot_date`, `vigente_score`.
3. **`studio/detection.py`** — name-list heuristics that guess (2) from a DataFrame.

`studio/policy_builder.build_policy` exists to map (2) → (1). A reader tracing "where does
`actual_default_col` come from" walks all three.

### F6 — Name-based heuristics decide behaviour

`stages.py:250-264` — `RateStage.apply` decides whether it is *the conversion stage* by, in order:
the `calibrate` flag; **the stage's own name** matched against
`("conversao", "conversion", "hired", "take_up", "take_up_rate")`; else *being the last `RateStage`
in the policy*. The verdict changes the arithmetic (keep-ins get their observed `hired` value instead
of `1.0`). Renaming a stage silently changes the numbers.

`studio/detection.py` runs the same style over data: `_ID_NAMES`, `_TIME_NAMES`, `_SEGMENT_NAMES`,
`_ESTIMATED_NAMES` membership tests plus `"score" not in col.lower()` (`:70`, `:80`).

Detection guessing is defensible — it is a UX affordance over an unknown CSV, and it is correctable
in the UI. The engine deciding semantics from a display name is a different thing: there is no user
to correct it. [#68](https://github.com/matheuspasche/pycreditools/issues/68) already kills this
specific heuristic; the pattern is what this diagnosis records.

### F7 — Immutability is implemented by deep-copying the whole policy

`CreditPolicy._replace` (`policy.py:90-97`) is `copy.deepcopy(self)` then `dataclasses.replace`. So
does every builder call — `.cutoff()`, `.filter()`, `.rate()`, `.stress()` — deep-copy the entire
policy including its stages, expressions and rating recipe. Building a 5-stage policy deep-copies 5
times.

Both sweeps then repeat the pattern per grid point: `optimization.py:81`, `:183` and
`analysis.py:70`, `:103`, `:111`, `:127` all do `copy.deepcopy(config)` → `dataclasses.replace(...,
stages=tuple(stages_list))`. This is the same "clone the policy, swap one stage" motion written out
four times in two modules — the duplication [#71](https://github.com/matheuspasche/pycreditools/issues/71)
merges, seen from the memory side.

### F8 — `studio/analyses.py` is the gravity well

1,367 lines, **68 top-level functions**, and at least six unrelated domains:

| lines | domain |
|---|---|
| `:42-230` | policy simulation, KPIs, segmentation, funnels |
| `:231-372` | score evaluation, KS, complementarity (ADR 0004/0005) |
| `:373-694` | swap/quadrant/rating/vintage/exposure readouts, delta table |
| `:695-1017` | trade-off, crash test, aggravation game, optimization, scenarios |
| `:1018-1320` | risk grouping, open matrix, manual grouping, ratings, stability |
| `:1322-1362` | deployment scoring |

It is the only file that imports 15 names from the engine top level, and it is where a reader
searching for *any* studio behaviour lands. Nothing in the module name tells them which of the six
they are in.

`gui/pages/3_Bancada.py` (527 lines) is the second well; `gui/components/policy_builder.py` (474)
the third.

### F9 — `Stage.apply` takes the policy back, typed `Any`

All four `apply` implementations have the signature (`stages.py:32`, `:103`, `:149`, `:220`):

```python
def apply(self, df, method="analytical", policy: Any | None = None) -> pd.Series:
```

`policy` is `Any` because `policy.py` imports `stages.py`; typing it properly would close a cycle.
`CalibratedExpression.calibrate_and_eval(df, policy: Any)` (`expressions.py:177`) does the same, and
then imports `CutoffStage` *inside the function body* (`:199`) to read the cutoff back off the
policy.

So the dependency graph reads downward — `policy → stages → expressions` — while the data flows both
ways at runtime. The evidence is the function-local import: `deployment.py` has 6,
`expressions.py` 2, `optimization.py` 4, `stages.py` 3, all deferring an import to dodge the cycle.
A child object reaching back into its parent for context is the shape; `Any` is how the type system
was made to allow it.

### F10 — Dead and pinned surface

- **Deprecated aliases still exported**: `find_risk_groups` (`grouping.py:435`), `screen_risk_segments`
  (`screening.py:228`), `visualize_tradeoffs` (`visualization.py:369`) — all three are
  `(*args, **kwargs)` passthroughs that raise `DeprecationWarning`, and all three are in `__all__`.
  Their only in-repo caller is `tutorial_masterclass_v14.ipynb`, which
  [#76](https://github.com/matheuspasche/pycreditools/issues/76) deletes.
- **Notebook-pinned code**: `examples/get_notebook_path(version=16)` and `copy_notebook(version=16)`
  default to a notebook v0.5 deletes; `studio/policy_builder.v14_quickfill_rows` (`:119`) and
  `analyses.cutoff_range`'s docstring (*"as the v14 Cell 10 uses"*, `:696`) pin studio behaviour to a
  file being removed.
- **`analyses.compare_with_baseline`** (`:638-640`) is a one-line alias of `compare_policies` with a
  different name, kept alive by two parity tests.
- **`gui/components/population.py`** carries both `render_population_selector` and
  `render_population_selector_v2` (`:15`, `:33`).

### F11 — The docs a newcomer would open do not exist or are mis-filed

- `CLAUDE.md` declares *"one `CONTEXT.md` + `docs/adr/` at the repo root"*. **`CONTEXT.md` does not
  exist.** There is `docs/ORIENTATION.md`.
- The layer rule that the code cites in its own module docstrings — *"see `00-overview.md` §4b"* —
  lives in `docs/prd/00-overview.md`, a **product requirements** doc, alongside 12 numbered feature
  PRDs. The one architectural invariant the codebase actively enforces is filed as a product
  requirement and referenced by a bare filename that resolves nowhere from the repo root.
- The 8 ADRs (`docs/adr/0001`–`0008`) are cited constantly from docstrings and are the genuinely
  useful map — `analyses.py` alone cites ADR 0001, 0002, 0004, 0005, 0006, 0007.

A reader following the code's own signposts hits a missing file, then a product doc. That is a
navigability defect independent of the code.

## Hot spots

| file | lines | note |
|---|---|---|
| `studio/analyses.py` | 1,367 | F8 — six domains, 68 functions |
| `simulation.py` | 723 | `run_simulation` is 101 lines; 4 module-level helpers do the rest |
| `performance.py` | 621 | F2 — printing fused to metric math |
| `gui/pages/3_Bancada.py` | 527 | 9 private render helpers |
| `visualization.py` | 523 | matplotlib; `studio/charts.py` (438) is the plotly twin |
| `gui/components/policy_builder.py` | 474 | `_render_rate_row` alone is 127 lines |
| `deployment.py` | 473 | `to_production_rules` is 211 lines |
| `grouping.py` | 445 | `fit_risk_groups` is 227 lines |
| `optimization.py` | 318 | `optimize_cutoffs` is 174 lines, two methods in one body |
| `stages.py` | 314 | `RateStage.apply` is 77 lines (F6) |

Two more twins worth naming: `visualization.py` (matplotlib, engine) and `studio/charts.py` (plotly,
studio) render the same five artifacts — trade-offs, crash test, funnel, vintage stability,
optimization/pareto — for two audiences, sharing nothing.

## Already ticketed — not for #63 to re-decide

Several findings above are live v0.5 work; they appear here because they are symptoms of the
architecture, not because they are open:

- F2/F7 duplication between `optimize_cutoffs` and `TradeoffAnalyzer` → [#71](https://github.com/matheuspasche/pycreditools/issues/71)
- F6's conversion-stage name heuristic → [#68](https://github.com/matheuspasche/pycreditools/issues/68)
- F2's metric semantics in studio KPIs → [#67](https://github.com/matheuspasche/pycreditools/issues/67)
- F10's v14/v15/v16 notebooks → [#76](https://github.com/matheuspasche/pycreditools/issues/76)

And one question is explicitly parked *for* [#63](https://github.com/matheuspasche/pycreditools/issues/63)
by [#61](https://github.com/matheuspasche/pycreditools/issues/61): whether `estimated_default_col`
should be renamed, narrowed to 0/1, or removed
([hint on #62](https://github.com/matheuspasche/pycreditools/issues/62#issuecomment-4982111058)). F3
and F5 are its context — the column is one more undeclared role in a frame with no schema, wired
through ~29 references across `policy.py`, `simulation.py`, `studio/analyses.py`, `studio/detection.py`,
`studio/models.py`, `studio/policy_builder.py` and `gui/components/column_roles.py`.

## What the diagnosis says about the pain

The reader is not lost because there are too many files or too many classes. They are lost because:

1. **No single artifact declares the contract.** The frame's schema (F3), the policy's roles (F5),
   and the results' shape (F4) are established by convention and string literal, so there is nothing
   to read — only code to trace.
2. **Tracing costs three hops** (F1) and lands in a 1,367-line module (F8).
3. **The same arithmetic exists in two places** (F2) and the docstring tells you it is a copy, so the
   reader must now hold both.
4. **Behaviour depends on names** (F6) and **types are `Any` at the one seam that matters** (F9), so
   neither the type checker nor the reader can rule anything out.
5. **The signposts are broken** (F11).
