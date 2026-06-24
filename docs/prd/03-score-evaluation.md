# PRD 03 — Score Evaluation (KS / power)

> Depends on PRD 02. Wraps `ModelEvaluator`. Mirrors notebook v14 Cell 4.
> See Master §8, §9 (population selector, NaN target).

## Objective

Rank the candidate scores by predictive power (KS) and inspect per-decile
performance — the "which score is the champion?" step.

## API (verified)
```python
ev = ModelEvaluator(data: pd.DataFrame, score_cols: list[str], target_col: str)
ev.compute_ks() -> dict[str, float]                 # {score_name: ks}; higher score assumed = lower PD
ev.compute_ks_table(col: str, bins: int = 10) -> pd.DataFrame
    # columns: Bucket(1=best..N=worst), Avg_Score, Volume, Bad_Rate, Cum_Bads, Cum_Goods, KS
```
`ModelEvaluator` internally `dropna()`s on `[score, target]`.

## Page: `pages/2_Score_Evaluation.py`

1. `guard_dataset()`; `guard_roles("score_cols", "actual_default_col")`.
2. **Population selector** (shared `data_access.population_filter`) — default
   **"Contratados"** (hired), matching the notebook's `df_hist` (only the hired
   population has observed `actual_default`). Show effective N after dropna.
3. **Controls** (bordered container): multiselect of scores to evaluate (default =
   all `score_cols` incl. legacy), `bins` slider (default 10), and a selectbox to
   choose which score drives the decile table.
4. **KS ranking**:
   - call `compute_ks()` (cached by `(df_hash, population, score_cols)`),
   - KPI row with the top score + its KS, and the delta vs `legacy_score`,
   - a horizontal bar chart (`charts.bars`) sorted desc, accent color, value
     labels as `%`. Highlight legacy in a muted color.
5. **KS curve** (`charts.ks_curve`): for the selected score, build cumulative
   good/bad curves from `compute_ks_table` (`Cum_Goods` vs `Cum_Bads` across
   buckets) and mark the max-gap (KS point). Two lines + filled gap.
6. **Decile table**: `compute_ks_table(selected, bins)` rendered via
   `components/tables.dataframe` with `Bad_Rate` as percent, `Volume` thousands,
   `KS`/`Cum_*` as percent, and a `Bad_Rate` bar (`st.column_config.ProgressColumn`
   or a small inline bar). Monotonic bad rate across buckets is the visual story.
7. Optional **comparison table**: KS of every score side by side (one row per
   score) — just `pd.Series(compute_ks()).sort_values(ascending=False)`.

## Charts
- `charts.bars(series, *, percent=True, highlight=None)` → horizontal bars.
- `charts.ks_curve(table_df)` → 2 line traces (`Cum_Goods`, `Cum_Bads`) over
  `Bucket`, plus a vertical line / annotation at the KS-maximizing bucket.

## Edge cases
- Score where `total_bads==0 or total_goods==0` → `compute_ks` returns 0.0; show
  "sem variância suficiente" hint.
- If population has no observed defaults (all NaN), block with a friendly message
  pointing to the population selector.

## Acceptance criteria
- On v14 sample (hired population), `score_5` ranks highest and `legacy_score`
  lowest, KS values plausible (~0.30 vs ~0.25). Numbers match
  `ModelEvaluator(df_hist, scores, "actual_default").compute_ks()` from a notebook.
- Decile table shows monotonically decreasing `Bad_Rate` from Bucket 1→N.
