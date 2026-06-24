# PRD 04 — Policy Studio (no-code policy builder)

> Depends on PRD 02. The core page; unblocks Simulation (05), Trade-off (06),
> Optimization (07), Crash Test (09-crash), Deployment (10). Mirrors notebook v14
> Cells 3–6. See Master §6, §8, §9, §10.

## Objective

Build one or more `CreditPolicy` objects entirely by clicking: hard filters,
score cutoffs, take-up rate, and a single flat stress factor — with a **live
funnel preview** that updates as rules change. No Python typed by the user.

## API (verified — `policy.py`, `stages.py`, `stress.py`, `expressions.py`)
```python
CreditPolicy(
    applicant_id_col: str,
    score_cols: tuple[str, ...],          # accepts str or list, coerced to tuple
    current_approval_col: str | None = None,
    actual_default_col: str | None = None,
    time_col: str | None = None,
    # ...stages, stress_scenarios, rating_recipe, calibration_*, current_hired_col,
    #    estimated_default_col
)
# Immutable; builder methods return a NEW policy:
.filter(name: str, condition)            # condition = Expression (we always pass an Expression)
.cutoff(name: str, cutoffs: dict[str, float], direction: str = "gte")  # "gte"|"lte"
.rate(name: str, base_rate: float, variable: str | float | None = None, calibrate: bool = False)
.stress_aggravation(factor: float)       # adds AggravationStress(factor)
.with_rating(rating_recipe)              # set from Risk Grouping page later
.with_calibration(score_col=None, bins=None, base="keep_in")
.validate(df) -> None                    # raises ValueError(missing cols)
.describe() -> str
.to_dict() / CreditPolicy.from_dict(d)
.simulate(df, method="analytical", drop_stages=False) -> CreditSimResults

col(name) >= value     # ColumnExpr; operators: > >= < <= == != & | ~
```
**Expression builder note:** `col("x") == True` works (binary `==`). Combine
clauses with `&`. The studio builds `Expression` objects programmatically from the
no-code rows — never from user strings.

## Page: `pages/3_Policy_Studio.py`

Layout (wide): **left column = builder**, **right column = live funnel**.
`guard_dataset()`; `guard_roles("applicant_id_col", "score_cols")`.

### Policy management (top bar)
- Selectbox of existing policies (`StudioState.policies`) + "Nova política" +
  "Duplicar" + "Renomear" + "Excluir". `st.text_input` for the active policy name.
- The active policy is rebuilt from its rule rows on every change and stored back
  into `StudioState.policies[name].policy` and set as `active_policy`.

### Builder (left) — a list of **rule rows**, each added via "Adicionar regra"
Each rule row is a `dict` in `session_state` (so it survives reruns). A row has a
**type** selectbox and type-specific inputs:

1. **Filtro (FilterStage via `col` expression)**
   - `name` (text), `column` (selectbox), `operator` (selectbox:
     `>= , > , <= , < , == , !=`), `value` (typed input matching the column dtype:
     number / boolean toggle / category select).
   - Builds `col(column) <op> value`. For booleans use `== True/False`.
   - Multiple conditions in one filter: allow "E" (AND) sub-rows that combine via
     `&` into one `FilterStage` (keeps the funnel stage named once). OR is **out**
     of v1 scope (note for clarity); use separate filters if needed.
2. **Cutoff (CutoffStage)**
   - `name`, one or more `{score_col: value}` pairs (multiselect of score_cols +
     a number input per selected score), `direction` (`gte`/`lte`, default `gte`).
   - Builds `.cutoff(name, {score: val,...}, direction)`.
   - Provide a slider per score bounded by the column's p1–p99 for ergonomics.
3. **Taxa / Take-up (RateStage)**
   - `name`, `base_rate` (slider 0–1), optional `variable` = a column name
     (selectbox, e.g. `conversion_rate`/`take_up_rate`) or a constant, and an
     advanced `calibrate` toggle (maps to `with_calibration` + `calibrate=True`).
   - Builds `.rate(name, base_rate, variable, calibrate)`.
4. **Stress (flat aggravation)** — single, optional, at most one per policy.
   - `factor` slider (1.0–5.0, step 0.05, default 1.2). Builds
     `.stress_aggravation(factor)`. Store mirror in `PolicyEntry.flat_stress_factor`.
   - Copy: "Agrava a PD dos *swap-ins* por este fator (ex.: 1.2 = +20%)."

Each row has up/down reorder + delete. Rule order = funnel order (filters/cutoffs
first; rate stages applied after; stress is separate). Provide a "carregar
filtros do v14" quick-fill button that injects the 4 masterclass hard filters
(`cpf_valido == True`, `vl_negativacao <= 1500`, `vl_vencido_scr <= 3000`,
`vl_protestos <= 500`) when those columns exist.

### Build + validate
- A `policy_builder.build_policy(roles, rows) -> CreditPolicy` helper assembles the
  immutable policy by chaining the builder methods in row order, then
  `with_rating(rating_result.recipe)` if a rating exists in state and
  `actual_default_col`/`current_approval_col` from roles.
- Call `.validate(df)`; show inline green check or translated error.
- Show `policy.describe()` in a collapsed "Resumo da política" expander.

### Live funnel preview (right) — `@st.fragment` so it updates fast
- On any change, run `policy.simulate(population_df, method="analytical")` where
  `population_df` = the **DEV** population by default (selector reused from PRD 02;
  ~1M rows analytical is fine but DEV keeps it snappy).
- Render `sim.to_funnel_dataframe()` two ways:
  - **Funnel chart** (`charts.funnel`): a Plotly funnel of `Stage` → `Passed`
    (use `go.Funnel`), themed; tooltips show `Stage_Pass_Rate` and `Cum_Pass_Rate`.
  - **Funnel table** (`components/tables`): Stage, Candidates, Passed,
    Stage_Pass_Rate %, Cum_Pass_Rate %, Rejections.
- KPI row above the funnel: final approval rate (`new_approval` mean), approved
  volume, and (if `actual_default_col` set) the simulated bad rate of approved.

> Reuse `plot_funnel(sim)` only if it already returns a themeable Plotly figure;
> otherwise build the funnel in `charts.funnel` from `to_funnel_dataframe()` for
> full theme control (preferred per Master §7).

## Edge cases
- No stress configured → simulation runs without stress (fine).
- Cutoff on a score not in `score_cols` → still valid if the column exists; warn if
  the column is missing.
- `current_approval_col` unset → no swap quadrants; funnel still works; downstream
  pages that need quadrants will warn.
- Boolean columns: `==` with a `True/False` toggle (not text).

## Acceptance criteria
- User can recreate the v14 `policy_hf` (4 hard filters) + a legacy cutoff
  (`legacy_score >= p78`) by clicking, and the live funnel volumes match
  `run_v14_benchmark.py`'s funnel for the same population.
- Adding a flat stress factor changes the simulated bad rate KPI but not the
  funnel volumes.
- Switching/duplicating policies preserves each policy's rules independently.
- The built `CreditPolicy.to_dict()` round-trips through `from_dict` unchanged.
