# PRD 07 — Cutoff Optimization (grid search + Pareto)

> Depends on PRD 04. Wraps `optimize_cutoffs` / `OptimizationResult` /
> `find_pareto_frontier` / `plot_optimization`. See Master §8, §9.

## Objective

Automatically search a grid of cutoff combinations across the policy's score
column(s) to find the best set under business constraints (max default rate, min
approval rate), and visualize the Pareto frontier.

## API (verified — `optimization.py`)
```python
optimize_cutoffs(
    data: pd.DataFrame,
    config: CreditPolicy,                 # base policy; its score_cols define what is optimized
    cutoff_steps: int = 10,
    target_default_rate: float = 0.05,    # max acceptable overall default rate
    min_approval_rate: float = 0.3,       # min acceptable overall approval rate
    method: str = "analytical",           # or "stochastic"
    parallel: bool = False,
    percentiles: tuple[float, float] | None = (0.05, 0.95),
    cutoff_ranges: dict[str, list[float]] | None = None,   # override the grid per score
) -> OptimizationResult

OptimizationResult:
    best_combination: dict[str, float]
    metrics: dict[str, float]             # overall_approval_rate, overall_default_rate,
                                          # tradeoff_score, constraints_met
    all_results: pd.DataFrame
    pareto_frontier: pd.DataFrame
    params: dict
    .find_equivalent(target_metric="approval_rate", target_value=0.20, tolerance=0.01) -> pd.DataFrame
    .plot(type="tradeoff"|"pareto", save_path=None) -> plt.Figure
    .to_dict()

find_pareto_frontier(df) -> pd.DataFrame
plot_optimization(opt_results, type="tradeoff"|"pareto") -> plt.Figure
```
> Build charts in Plotly from `all_results` / `pareto_frontier`; matplotlib funcs
> are reference only.

## Page: `pages/6_Optimization.py`

1. `require_policy()`. The active policy is `config`; the scores optimized are
   `config.score_cols`. Show which scores will be gridded (warn if many — grid is
   the product across scores: `cutoff_steps ** n_scores`).
2. **Controls**:
   - `cutoff_steps` slider (default 10).
   - `target_default_rate` slider (default 0.05) and `min_approval_rate` slider
     (default 0.30).
   - `percentiles` range slider (default 0.05–0.95) bounding the search.
   - method toggle (`analytical` default), `parallel` toggle (stochastic only).
   - population selector (default **DEV**).
   - Advanced: per-score explicit `cutoff_ranges` override (number inputs / a small
     editor) — optional.
3. **Run**: `optimize_cutoffs(pop_df, config, **params)` (cached by
   `(df_hash, population, config.to_dict(), params)`). Wrap in spinner; show grid
   size up front.
4. **Best result**: KPI cards — `best_combination` (one chip per score: "score_5 ≥
   742"), `overall_approval_rate`, `overall_default_rate`, `tradeoff_score`, and a
   ✅/⚠️ for `constraints_met`.
5. **Pareto frontier chart** (`charts.pareto`): scatter of `all_results`
   (approval_rate x, default_rate y) in muted color, the `pareto_frontier` points
   highlighted and connected, the `best_combination` starred, and the constraint
   lines (`target_default_rate` horizontal, `min_approval_rate` vertical) drawn as
   dashed guides. Feasible region shaded subtly.
6. **Find equivalent**: a small panel — pick `target_metric` (approval_rate /
   default_rate) + `target_value` + `tolerance`, call `.find_equivalent(...)`,
   render the matching combinations table (useful to "match legacy approval rate").
7. **All results table**: `all_results` themed, sortable, with the chosen point
   highlighted.
8. Button **"Aplicar melhor combinação ao Policy Studio"** → write
   `best_combination` cutoffs into the active policy (CutoffStage per score) and
   set it active.

## Charts
- `charts.pareto(all_df, pareto_df, best, constraints=(target_def, min_appr))`.

## Performance / edge cases
- Guard against explosive grids: if `cutoff_steps ** n_scores > ~2000`, warn and
  suggest fewer steps or fewer scores; still allow with confirmation.
- `analytical` is the fast path; `parallel` only matters for `stochastic`.
- Validate `0 ≤ target_default_rate ≤ 1`, `0 ≤ min_approval_rate ≤ 1`,
  `cutoff_steps ≥ 1` (the function raises otherwise — translate the error).

## Acceptance criteria
- On v14 sample with a single score (`score_5`), the best combination's approval
  and default rates respect the constraints when feasible, and `constraints_met`
  reflects feasibility.
- Pareto points are non-dominated (match `find_pareto_frontier(all_results)`).
- "Aplicar melhor combinação" updates the active policy's cutoff.
