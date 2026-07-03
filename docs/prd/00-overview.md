# PRD 00 — Pycreditools Studio (Streamlit) — Master / Overview

> **Read this first.** Every other PRD (`01`–`11`) assumes the conventions, the
> session-state schema, the design system and the helper modules defined here.
> When a per-page PRD says "see Master", it means this file.

---

## 1. Context & problem

`pycreditools` (v0.3.1) is a complete credit-risk policy engine: build a
`CreditPolicy` (filters / cutoffs / take-up rates), simulate it on an applicant
base (`run_simulation`, analytical or stochastic, with swap-in/out quadrants),
apply stress to PD, cluster scores into risk ratings (`fit_risk_groups`),
screen sub-segments, optimize cutoffs, run trade-off / crash-test analyses,
evaluate score power (KS), visualize, and export a deployable policy JSON.

Today the only GUI is a **Dash + Mantine** app (`src/pycreditools/gui/`,
~2,000 lines, `callbacks.py` alone = 1,573 lines with duplicated callbacks —
see the root scratch scripts `find_dupes.py` / `fix_callbacks.py`). It is
verbose, hard to maintain, **dark but dated**, and covers only a fraction of the
package. The owner finds it "ugly and very limited".

**Goal:** replace it with a beautiful, lightweight **Streamlit** studio that lets
the owner do **everything they do in code** (the `tutorial_masterclass_v14/15/16`
notebooks) **with almost no code** — upload a base, point-and-click the whole
pipeline, export the result.

### Decisions already locked with the owner

| Decision | Value |
|---|---|
| Framework | **Streamlit** (chosen for speed-to-beautiful + minimal boilerplate) |
| Philosophy | **100% no-code** — no Python typed by the user anywhere |
| Scope of v1 | **Full parity** with the package's public API |
| Audience / runtime | **Single user, local** (`streamlit run` on the owner's machine) |
| Old Dash GUI | **Replaced** — delete `src/pycreditools/gui/` Dash code, Streamlit takes its place |
| Theme | **Dark, modern, fintech** |
| Data features | Generate-sample-data button · automatic column detection · large bases (~1M rows) · save/load projects |
| Stress modes | **Flat aggravation factor only** (`AggravationStress`). Angulated-by-rating, linear-by-decile and `MonotonicStress` are **explicitly out of v1** (see §10 Non-goals) |
| Charts | **Plotly native** (interactive, themed) — do **not** embed the package's matplotlib figures |
| Deployment page | Export policy JSON **and** batch-score an uploaded file |

---

## 2. Goals / Non-goals

### Goals
- One Streamlit app that exposes the full public API of `pycreditools` (see §8 map).
- Upload a CSV (or generate sample data) → configure column roles → run the
  entire masterclass workflow visually → export a deployment JSON and/or score a
  new file.
- Beautiful dark fintech look, fast on ~1M-row bases.
- No code typed by the user. Custom-function steps from the notebooks become
  configurable presets.
- Save/restore a "project" (column config + policies + ratings) locally.

### Non-goals (v1) — see §10 for the full list
- No multi-user / auth / server deployment.
- No arbitrary user Python (no `CustomStress` lambdas, no callable filters).
- Only `AggravationStress` (flat factor). No angulated/linear/monotonic stress.
- No real-time DB connectors (CSV/Parquet upload only).

---

## 3. Tech stack

- **Python ≥ 3.10**, **Streamlit ≥ 1.36** (uses `st.dialog`, `st.fragment`,
  `st.column_config`, `st.cache_data`).
- **Plotly ≥ 5** for all charts.
- **pandas ≥ 2 / numpy** (already core deps).
- The studio imports `pycreditools` as a normal library — **it never
  re-implements engine logic**, it only orchestrates calls and renders results.
- New optional extra in `pyproject.toml`:
  ```toml
  studio = [
      "streamlit>=1.36",
      "plotly>=5.0",
      "pandas>=2.0",
      "pyarrow>=14.0",   # fast CSV/Parquet + caching
  ]
  ```
  Remove the old `gui = [...]` Dash extra (dash, dash-mantine-components,
  dash-iconify, dash-ag-grid).

---

## 4. Architecture & file layout

Delete the Dash app and create the Streamlit app under the **same** package path
so it ships with `pip install pycreditools[studio]`.

> **Two layers (read §4b first).** The studio is split into a framework-agnostic
> **core** (`pycreditools/studio/`, no Streamlit) and a thin Streamlit **skin**
> (`pycreditools/gui/`). The tree below is the *skin*; every logic module it
> references (`data_access`, `policy_builder`, `charts`, `projects`, the pure parts
> of `state.py`) actually lives in the **core** per §4b. `gui/` holds only `st.*` code.

```
src/pycreditools/gui/
├── __init__.py                 # exposes run_studio()
├── app.py                      # Streamlit entrypoint (st.navigation / pages)
├── theme.py                    # dark fintech theme: CSS injection + Plotly template
├── state.py                    # SessionState dataclass + accessors (see §6)
├── data_access.py              # cached loaders, column auto-detection (PRD 02)
├── components/                 # small reusable render helpers (no engine logic)
│   ├── __init__.py
│   ├── kpi.py                  # KPI "stat cards"
│   ├── tables.py               # styled st.dataframe wrappers + column_config
│   ├── charts.py               # Plotly chart builders (themed)
│   ├── column_roles.py         # the column-role picker widget (PRD 02)
│   └── policy_builder.py       # the no-code stage/filter builder widget (PRD 04)
├── pages/                      # one module per PRD page
│   ├── 1_Ingestion.py
│   ├── 2_Score_Evaluation.py
│   ├── 3_Policy_Studio.py
│   ├── 4_Simulation.py
│   ├── 5_Tradeoff.py
│   ├── 6_Optimization.py
│   ├── 7_Risk_Grouping.py
│   ├── 8_Risk_Screening.py
│   ├── 9_Crash_Test.py
│   └── 10_Deployment.py
├── projects.py                 # save/load project JSON (PRD 02 §Projects)
└── assets/
    └── studio.css              # extra CSS loaded by theme.py
```

Delete: `src/pycreditools/gui/app.py` (Dash), `callbacks.py`, `callbacks_fixed.py`,
`components/{ingestion,studio,simulation,evaluation,risk}.py`, `assets/style.css`,
and the root scratch scripts that only existed to patch Dash callbacks
(`find_dupes.py`, `fix_callbacks.py`). Keep `parse_nb.py` / `read_v14_notebook.py`
/ `run_v14_benchmark.py` only if useful as a parity oracle (see §9).

### 4b. Two-layer architecture — the "no-rework" rule (IMPORTANT)

The owner wants to keep the option of moving to a server / scaling later **without
rewriting everything**. The framework choice is made reversible by a hard split:

- **Core — `src/pycreditools/studio/` — framework-agnostic. MUST NOT import
  `streamlit`.** Holds ALL studio logic: dataclasses (`models.py`: `ColumnRoles`,
  `PolicyEntry`, `ProjectBundle`), column detection (`detection.py`), data IO +
  population filter (`data.py`), policy assembly (`policy_builder.py`), analysis
  orchestration (`analyses.py` — thin wrappers over `pycreditools` returning plain
  DataFrames/dicts), Plotly figure builders (`charts.py` → `go.Figure`, which is
  framework-agnostic; also registers the `pct_dark` template), and project
  (de)serialization (`projects.py`). Pure functions, unit-testable with zero Streamlit.
- **Skin — `src/pycreditools/gui/` — the ONLY place `import streamlit` appears.**
  `app.py`, `theme.py` (CSS injection), `session.py` (bridges `st.session_state` ↔
  `studio.models` + `@st.cache_data` wrappers around `studio.analyses`),
  `components/` (st widgets that call core), `pages/` (thin: read session → call
  core → render).

```
src/pycreditools/studio/            # CORE — no streamlit anywhere
├── __init__.py
├── models.py        # ColumnRoles, PolicyEntry, ProjectBundle (pure dataclasses)
├── detection.py     # detect_roles(df) -> ColumnRoles
├── data.py          # load_csv/parquet, df hashing, population_filter(...)
├── policy_builder.py# build_policy(roles, rule_rows) -> CreditPolicy
├── analyses.py      # evaluate_scores/run_policy_sim/tradeoff/optimize/
│                    #   fit_groups/screen/crash_test/score_batch -> plain data
├── charts.py        # frontier/funnel/ks_curve/bars/vintage_stability/crash/pareto
│                    #   -> go.Figure (+ pct_dark template registration)
└── projects.py      # ProjectBundle <-> JSON
```

**Placement rule (authoritative — overrides per-page PRDs):** wherever a per-page
PRD (01–11) names a *logic* module (`data_access.py`, `policy_builder.py`,
`charts.py`, `projects.py`, `detect_roles`, `population_filter`, or the pure parts
of `state.py`), that code goes in **`pycreditools/studio/`**. Only the `st.*`
binding goes in `pycreditools/gui/`. Function names stay identical; import from the
core (e.g. `from pycreditools.studio import charts`). The boundary is enforced by a
test — see `IMPLEMENTATION_GUIDE.md` §3 Layer 2 (`test_core_has_no_streamlit_import`).

### Entrypoint

`src/pycreditools/gui/__init__.py`:
```python
def run_studio(port: int = 8501) -> None:
    """Launch the Streamlit studio (`streamlit run app.py`)."""
```
Add a console script in `pyproject.toml`:
```toml
[project.scripts]
pycreditools-studio = "pycreditools.gui:run_studio"
```
`run_studio` should shell out to `streamlit run <path to app.py>` via
`streamlit.web.bootstrap` or `subprocess`. The user starts it with
`pycreditools-studio` **or** `streamlit run src/pycreditools/gui/app.py`.

### Navigation

Use `st.navigation` + `st.Page` (Streamlit ≥ 1.36) in `app.py` to define the
sidebar. Order = build order. Pages that need a dataset must call
`guard_dataset()` (see §6) and show a friendly "load a base first" state instead
of erroring.

---

## 5. UX / Information architecture

Sidebar (top → bottom), each item is one page:

1. **Ingestion** — upload / generate data, configure column roles, projects.
2. **Score Evaluation** — KS ranking & decile tables (`ModelEvaluator`).
3. **Policy Studio** — build filters / cutoffs / rates / flat stress; live funnel.
4. **Simulation** — run policy, quadrants, swap analysis, compare vs legacy.
5. **Trade-off** — efficient frontier, scenario picker (conservative/neutral/aggressive).
6. **Optimization** — grid search for best cutoffs, Pareto frontier.
7. **Risk Grouping** — cluster scores into A–E ratings, vintage stability, pairwise.
8. **Risk Screening** — sub-segments inside ratings (`fit_risk_segments`).
9. **Crash Test** — breakeven stress factor.
10. **Deployment** — export JSON, batch-score a new file.

The sidebar header shows the active **dataset name + row count** and the active
**policy name** so the user always knows the context.

---

## 6. Shared state model (`studio/models.py` dataclasses + `gui/session.py` bridge)

The dataclasses below are **pure** and live in `studio/models.py` (no Streamlit).
The bridge that stores them in `st.session_state` and provides the guards lives in
`gui/session.py` (skin). Streamlit reruns top-to-bottom on every interaction;
persist everything in `st.session_state` behind a small typed accessor. Engine objects
(`CreditPolicy`, `RiskGroupResult`) are **not** JSON-serializable widget values —
keep the live objects in session state and serialize only when saving a project.

```python
# state.py — schema (use a dataclass or TypedDict; store under st.session_state["studio"])
ColumnRoles:
    applicant_id_col: str | None
    score_cols: list[str]                 # candidate scores
    primary_score_col: str | None         # default score for cutoffs/grouping
    current_approval_col: str | None      # historical approval (enables swap quadrants)
    actual_default_col: str | None        # observed default 0/1 (NaN allowed for non-hired)
    current_hired_col: str | None         # take-up outcome
    time_col: str | None                  # safra / vintage
    segment_col: str | None               # e.g. region (for segmented grouping)
    estimated_default_col: str | None     # modeled PD for standalone sims
    oot_date: str | None                  # e.g. "2025-01" for DEV/OOT split

PolicyEntry:
    name: str
    policy: CreditPolicy                  # live object
    flat_stress_factor: float | None      # mirrored into policy via .stress_aggravation()

StudioState:
    df_name: str | None
    df: pd.DataFrame | None               # the loaded base (cached separately by hash)
    df_hash: str | None
    roles: ColumnRoles
    policies: dict[str, PolicyEntry]      # keyed by name
    active_policy: str | None
    rating_result: RiskGroupResult | None # last fitted grouping
    rating_labels: dict[int, str] | None  # {cluster_id -> "A".."E"} sorted by PD
    screening_result: ScreeningResult | None
    last_sim: CreditSimResults | None     # cache of the most recent simulation
    legacy_sim: CreditSimResults | None   # baseline simulation for comparisons
```

Helpers in `gui/session.py`:
- `get_state() -> StudioState`
- `guard_dataset()` — if `df is None`, `st.warning("Carregue uma base na página Ingestion.")` + `st.stop()`.
- `guard_roles(*required)` — ensure required roles are set, else friendly stop.
- `require_policy()` — returns the active `PolicyEntry` or stops.

---

## 7. Design system (`theme.py` + `assets/studio.css`)

**Mood:** dark, modern, fintech — think Linear / Vercel dark, applied to a risk
dashboard. Generous spacing, restrained color, one accent.

### Tokens
```
--bg:        #0B0E14   (app background)
--surface:   #141925   (cards / panels)
--surface-2: #1C2233   (hover / elevated)
--border:    #232A3B
--text:      #E6EAF2
--text-dim:  #94A0B8
--accent:    #4F8CFF   (primary / interactive)
--success:   #3DD68C   (good / approve / lower risk)
--warning:   #F5A623
--danger:    #FF5C5C   (bad rate / default / higher risk)
font: "Inter", system-ui, sans-serif;  mono: "JetBrains Mono", monospace
radius: 12px;  card padding: 20px;  shadow: 0 1px 2px rgba(0,0,0,.4)
```
Risk-tier palette (A→E): green→amber→red ramp, reused everywhere ratings appear:
`A #3DD68C · B #9BD460 · C #F5C84B · D #F5853F · E #FF5C5C`.

### Implementation
- `theme.py` exposes `apply_theme()` called once at top of `app.py`:
  - inject `assets/studio.css` via `st.markdown(<style>, unsafe_allow_html=True)`,
  - register a **Plotly dark template** `pct_dark` (`plotly.io.templates`) with the
    tokens above (paper/plot bg transparent, font Inter, gridcolor `--border`,
    colorway starting with `--accent`), and set it as default.
- All Plotly figures use `template="pct_dark"`, `height` set explicitly,
  `margin=dict(l,r,t,b)` tight, `config={"displayModeBar": False}` unless a chart
  benefits from zoom.
- Set `[theme]` in `.streamlit/config.toml` (base dark, primaryColor `--accent`,
  backgroundColor `--bg`, secondaryBackgroundColor `--surface`, textColor `--text`,
  font Inter). `app.py` also sets `st.set_page_config(layout="wide", page_title="Pycreditools Studio", page_icon="📊")`.

### Reusable components (`components/`)
- `kpi.kpi_row(items)` — renders a row of stat cards: label, big value, optional
  delta with up/down color. Use `st.columns` + styled `st.container(border=True)`.
- `tables.dataframe(df, **column_config)` — themed `st.dataframe`, right-aligned
  numerics, percent/format via `st.column_config`, `use_container_width=True`.
- `charts.*` — themed Plotly builders (frontier, funnel, KS curve, stability,
  crash, pareto, distribution). Each returns a `go.Figure`.

Every page follows the same skeleton: **title + one-line subtitle → KPI row →
controls (in a bordered container or `st.popover`) → results (tabs: Charts /
Tables)**. Keep it airy.

---

## 8. Package API → Studio feature map

The public API is exported from `pycreditools/__init__.py`. The studio must cover
all of it. Verified signatures live in each per-page PRD; this is the index.

| Capability | Public API | Page (PRD) |
|---|---|---|
| Load / generate data | `generate_sample_data(n_applicants, seed)` | 02 |
| Column validation | `CreditPolicy.validate(df)` | 02/04 |
| Score power (KS) | `ModelEvaluator(data, score_cols, target_col).compute_ks()` / `.compute_ks_table(col, bins)` | 03 |
| Build policy | `CreditPolicy(...)`, `.filter`, `.cutoff`, `.rate`, `.stress_aggravation`, `.with_rating`, `.with_calibration`, `.describe`, `.to_dict`/`.from_dict` | 04 |
| Filter expressions | `col(name)` + operators (`>=,>,<=,<,==,!=,&,|,~`) | 04 |
| Stages | `FilterStage`, `CutoffStage`, `RateStage`, `register_callable` | 04 |
| Stress (flat) | `AggravationStress(factor)` via `policy.stress_aggravation(factor)` | 04 |
| Simulate | `run_simulation(data, policy, method, drop_stages)` → `CreditSimResults` | 04/05 |
| Funnel | `CreditSimResults.to_funnel_dataframe()`, `plot_funnel(sim)` | 04/05 |
| Decisions | `CreditSimResults.to_decision_dataframe(rating_recipe, rating_labels)` | 05/10 |
| Summaries | `summarize_results(results, by)` | 05 |
| Compare vs legacy | `compare_policies(sim_new, sim_old)`, `print_delta_table` | 05 |
| Quadrant reports | `print_quadrant_summary`, `print_swap_in_by_rating`, `print_rating_quadrant_table` | 05 |
| Trade-off | `TradeoffAnalyzer(policy).vary_cutoff/.vary_base_rate/.vary_stress_aggravation.run(data, parallel)`; `run_tradeoff_analysis`; `plot_tradeoffs` | 06/05 |
| Optimize cutoffs | `optimize_cutoffs(data, config, ...)` → `OptimizationResult` (`.find_equivalent`, `.plot`); `find_pareto_frontier`; `plot_optimization` | 07 |
| Risk grouping | `fit_risk_groups(...)` → `RiskGroupResult` (`.data,.groups,.recipe,.n_groups,.report,.predict`); `fit_pairwise_risk_groups`; `find_risk_groups` | 08 |
| Grouping recipe | `GroupingRecipe.to_dict/from_dict/to_json/from_json/predict` | 08/10 |
| Vintage stability | `plot_vintage_stability(df, rating_col, time_col, default_col, approval_col, oot_start_safra)` | 08 |
| Risk screening | `fit_risk_segments(data, base_risk_col, candidate_cols, default_col, n_bins, method)` → `ScreeningResult` | 09 |
| Crash test | `TradeoffAnalyzer(policy).vary_stress_aggravation(values).run(data)`; `plot_crash_test(crash_df, legacy_bad_rate, breakeven_factor)` | 10 (Crash) |
| Deployment | `CreditPolicy.export(rating_recipe, path, clean)` → `DeploymentPolicy`; `DeploymentPolicy.save/load/predict/to_production_rules` | 10 (Deploy) |

> **Note on `_types`:** `SimulationMethod` (`"analytical"`/`"stochastic"`),
> `Quadrant` (`keep_in/swap_in/swap_out/keep_out`), `ClusteringMethod`
> (`ward`/`iv`), `StageDirection` (`gte`/`lte`). Use the string values directly
> in widgets.

---

## 9. Cross-cutting conventions (apply in every page)

1. **Never re-implement engine math.** Always call `pycreditools`. The studio is a
   thin, pretty orchestration layer.
2. **Caching.** Wrap pure, expensive calls in `@st.cache_data` keyed on
   `(df_hash, serialized params)`. Helpers:
   - data loading → cache by file bytes hash;
   - `compute_ks`, `fit_risk_groups`, `optimize_cutoffs`, tradeoff `.run` →
     cache by `(df_hash, policy.to_dict(), params)`. Engine results that contain a
     DataFrame are cacheable; objects like `RiskGroupResult` should be cached via a
     wrapper returning `(recipe.to_dict(), data, groups, report)` then rebuilt, OR
     stored directly in `session_state` (preferred for the "active" result).
3. **Performance on ~1M rows.** Default heavy analyses (trade-off grid,
   optimization, grouping) to run on the **DEV** subset (`time_col < oot_date`, or
   a `sample`/`approved`/`hired` filter the user picks) and offer an explicit
   "run on full base" toggle. Use `method="analytical"` as the default everywhere
   (fast expected-value path); expose a "stochastic" switch where the package
   supports it. Show `st.progress`/`st.spinner` for anything > ~1s.
4. **Population selector.** Several steps operate on a sub-population (e.g. KS on
   *hired*, grouping on *approved survivors*). Provide a shared, reusable
   "population filter" control (All / Approved / Hired / DEV / OOT / custom
   expression) defined once in `components/` and reused.
5. **`actual_default` is NaN for non-hired** (see `sample_data.py`). KS/grouping
   must run on a population where the target is observed; always `dropna` on the
   target for those steps and surface the effective N to the user.
6. **Errors are friendly.** Wrap engine calls in `try/except` → `st.error` with the
   message; never show a raw traceback. Validate columns with
   `CreditPolicy.validate` before simulating and translate the `ValueError`.
7. **Numbers formatting.** Rates as `%` (1 decimal), volumes with thousands
   separators, scores as integers. Centralize in `components/tables.py`.
8. **Language.** UI copy in **Portuguese (pt-BR)** to match the notebooks
   (e.g. "Taxa de aprovação", "Inadimplência", "Cenário"), code/identifiers in
   English.

---

## 10. Non-goals (explicit — do NOT build in v1)

These exist in the package but are intentionally excluded so implementers don't
spend effort on them:

- **Stress beyond flat:** no UI for `MonotonicStress`, no angulated-by-rating, no
  linear-by-decile stress. Only `AggravationStress(factor)` (one slider). The
  per-applicant `factor_col` path of `AggravationStress` is also out.
- **Custom Python:** no `CustomStress` lambdas, no callable/`str`-query filters
  typed by the user, no `register_callable` UI. Filters are built only via the
  no-code expression builder (`col` + operator + value, combined with AND).
- **Calibration deep-dive:** `with_calibration` is supported as an advanced toggle
  on rate stages only (PRD 04), not a dedicated page.
- **Multi-user / auth / cloud deploy / scheduling.**
- **DB / warehouse connectors:** input is CSV/Parquet upload or sample data.
- **Segmented (per-region) rating recipes** in grouping are **optional / phase-2**
  (PRD 08 marks them clearly); single-recipe grouping is the v1 requirement.

---

## 11. Build order & dependencies

Implement in this order; each PRD is a self-contained task for a cheaper model.

```
01 App Shell & Design System   (no deps)        ← foundation
02 Data Ingestion & Projects   (needs 01)       ← unblocks everything
03 Score Evaluation            (needs 02)
04 Policy Studio               (needs 02)        ← core; unblocks 05/06/07/10
05 Simulation & Impact         (needs 04)
06 Trade-off & Scenarios       (needs 04)
07 Cutoff Optimization         (needs 04)
08 Risk Grouping & Ratings     (needs 02; feeds 05/10 ratings)
09 Risk Screening              (needs 08)
10 Crash Test                  (needs 04)
11 Deployment & Batch Scoring  (needs 04 + 08)
```

A page may ship as a "needs X first" stub before its dependency exists.

---

## 12. Global acceptance criteria

The studio is "done" for v1 when, starting from a fresh `streamlit run`, a user
can **reproduce the entire `tutorial_masterclass_v14` notebook without writing a
line of code**:

1. Generate sample data (or upload `dataset_v14.csv`); column roles auto-detected.
2. See the KS ranking of `score_2..5` + `legacy_score` (score_5 should rank top).
3. Build a policy with the 4 hard filters + a legacy cutoff; see the live funnel.
4. Run a simulation with a flat stress factor; see quadrant summary & swap-in-by-rating.
5. Vary the cutoff → see the efficient frontier; pick a conservative scenario.
6. Optimize cutoffs → get a best combination + Pareto frontier.
7. Fit risk groups → A–E ratings + vintage-stability chart.
8. Run a crash test → see the breakeven aggravation factor.
9. Export the final policy JSON and batch-score an uploaded sample.
10. Save the project and reopen it with all of the above restored.

Each numbered item maps to a page acceptance section in PRDs 02–11. Visual: dark
fintech theme applied consistently; no raw tracebacks; responsive on a laptop.

### Parity oracle
`run_v14_benchmark.py` (repo root) reproduces the v14 numbers in pure code. Use it
as a regression check: the studio's funnel volumes, legacy approval/bad rate, and
trade-off neutral scenario must match the script's output for the same inputs.

---

## 13. Deployment & evolution path (decided: stay Streamlit, keep the door open)

The owner's eventual scale is **undecided** — the directive is "avoid rework".
Therefore: **build on Streamlit now, enforce the §4b core/skin split, and do not
pre-build for scale.** This keeps the framework a reversible decision.

- **Run locally:** `pycreditools-studio` or `streamlit run`.
- **Publish on a server (no framework change needed):** containerize
  (`streamlit run app.py --server.port 8501 --server.address 0.0.0.0` in a
  Dockerfile), put behind nginx/traefik; add auth via Streamlit's native OIDC
  (`st.login` / `st.user`, Streamlit ≥ 1.42) or the reverse proxy. Streamlit
  Community Cloud / Snowflake are also options. **Deployment ≠ scale.**
- **Streamlit's real ceiling is concurrency:** full-script rerun per interaction +
  one in-memory DataFrame per session → RAM/CPU grow with concurrent users, and
  heavy compute blocks the session. Mitigate with `@st.cache_data`, running heavy
  analyses on the DEV/sample subset (§9.3), container resource limits, and multiple
  replicas with sticky sessions. Comfortable for an internal tool / small team.
- **If you ever outgrow it (only then):** reuse `pycreditools` + the
  `pycreditools/studio/` core **unchanged** behind a **FastAPI** service
  (`analyses.py` functions → endpoints; `charts.py` figures → `fig.to_json()` for a
  JS frontend), and build a JS UI or a heavier Python UI (Reflex / NiceGUI). You
  rewrite the **skin**, not the risk logic or the studio core. That is the entire
  purpose of §4b — a bounded migration, not a rewrite.
