# PRD 05 — Simulation & Impact (quadrants, swap analysis, compare vs legacy)

> Depends on PRD 04 (and optionally PRD 08 ratings). Mirrors notebook v14
> Cells 8–11. Wraps `run_simulation`, `summarize_results`, `compare_policies`,
> and the `print_*` reporting functions (rebuilt as tables/charts). See Master §8.

## Objective

Run the active policy on the full base and explain its impact: approval/bad rate,
the four swap quadrants, swap-in breakdown by rating & segment, and a side-by-side
comparison against the legacy/baseline policy.

## API (verified — `simulation.py`, `performance.py`)
```python
run_simulation(data, policy, method="analytical"|"stochastic", drop_stages=False) -> CreditSimResults
# CreditSimResults.data adds columns:
#   new_approval, approved_pre_rate, scenario (keep_in/swap_in/swap_out/keep_out),
#   simulated_default, decision ("Approved"/"Rejected"), reason ("<i>: <stage>"|"Approved"),
#   stage_* (unless drop_stages)
CreditSimResults.to_funnel_dataframe()
CreditSimResults.to_decision_dataframe(rating_recipe=None, rating_labels=None)

summarize_results(results, by: str | list[str] | None = None) -> pd.DataFrame
    # rows per scenario (+ optional grouping); cols: scenario, Applicants, Approved, Hired, Bad_Rate
compare_policies(sim_new, sim_old) -> dict   # {metrics: DataFrame, swaps: ..., ratio: ...}
# Console reporters (reimplement their CONTENT as tables, do not capture stdout):
print_quadrant_summary(sim)        # volume & bad rate per quadrant
print_swap_in_by_rating(sim, rating_col="Rating")
print_rating_quadrant_table(sim, rating_col="Rating")
print_delta_table(sim_new, sim_old)
```
> The `print_*` functions write to stdout. **Do not** scrape stdout. Recreate the
> same numbers from `sim.data` / `summarize_results` and render with themed tables.
> (You may read each function's body to copy its aggregation logic.)

## Page: `pages/4_Simulation.py`

1. `require_policy()`; `guard_roles("applicant_id_col", "score_cols")`.
2. **Controls**: method toggle (`analytical` default / `stochastic`), population
   selector (default **Base completa**), and a "Definir como baseline (legacy)"
   button that stores the current sim as `legacy_sim` (for comparisons). Also a
   quick "Usar política só com cutoff legado como baseline" helper that builds a
   legacy-only policy (cutoff on `legacy_score` at its historical p78) and
   simulates it as the baseline — mirrors the notebook's legacy reference.
3. **Run**: `run_simulation(pop_df, policy, method)` (cached by
   `(df_hash, population, policy.to_dict(), method)`), store `last_sim`.
4. **KPI row**: Approval rate (`new_approval.mean()`), Approved volume, Hired
   volume (if `current_hired_col` or a rate stage), Simulated bad rate of approved,
   each with delta vs `legacy_sim` if present.
5. **Quadrants** (only if `current_approval_col` set):
   - 2×2 visual of `keep_in / swap_in / swap_out / keep_out` with volume + bad
     rate per cell (build from `summarize_results(sim)`), color-coded
     (swap_in highlight = accent, swap_out = danger).
   - Note from the engine: `keep_out` bad rate is NaN (rejected by both); `swap_out`
     uses observed `actual_default`; `keep_in/swap_in` use `simulated_default`.
6. **Swap-in by rating** (if a `Rating` column is available — see §Ratings):
   table + stacked bar of swap-in volume and bad rate per tier (A–E), using
   `RISK_COLORS`. Reproduce `print_swap_in_by_rating` logic.
7. **Swap-in by segment**: if `segment_col` set, crosstab of swap-in volume by
   `Rating × segment` (heatmap via `charts`), reproducing the notebook's
   `Rating × region` crosstab.
8. **Compare vs baseline**: if `legacy_sim` set, call
   `compare_policies(last_sim, legacy_sim)` and render the returned `metrics`
   DataFrame (Approval Rate & Bad Rate deltas) + the swap summary + swap-in/keep-in
   ratio. Also a "P&L delta" table reproducing `print_delta_table`.
9. **Decisions preview**: `to_decision_dataframe(rating_recipe, rating_labels)` head
   (themed table) so the user sees row-level decisão/motivo/rating/cenário.

### Ratings integration
- If `StudioState.rating_result` exists, apply it so a `Rating` column is present:
  predict via `rating_result.predict(sim.data)` → map cluster id → label using
  `rating_labels`, attach as `Rating`. Pass `rating_recipe`/`rating_labels` into
  `to_decision_dataframe`. If no rating yet, hide rating-based sections with a hint
  linking to the Risk Grouping page.

## Charts
- `charts.bars` (stacked) for swap-in by rating.
- A 2×2 quadrant card grid (plain `st.columns` + bordered containers + KPI style).
- Heatmap (`px.imshow` themed) for Rating × segment.

## Edge cases
- Standalone mode (`current_approval_col` is None): no quadrants; show approval/bad
  rate only and a note. (`simulated_default` then comes from
  `estimated_default_col` path.)
- `stochastic` method on ~1M rows: warn it's slower; keep analytical default.

## Acceptance criteria
- Running the v14 policy reproduces the quadrant volumes and swap-in counts from
  the notebook (`print_quadrant_summary` / `print_swap_in_by_rating`) within
  rounding.
- Setting the legacy baseline then comparing shows Approval/Bad-rate deltas
  consistent with `compare_policies`.
- With a fitted rating, swap-in-by-rating and Rating×region sections populate.
