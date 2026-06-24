# PRD 09 — Risk Screening (sub-segments within tiers)

> Depends on PRD 08 (needs a base risk rating). Wraps `fit_risk_segments` /
> `ScreeningResult` / `ScreeningRecipe`. See Master §8. Niche but part of full
> parity.

## Objective

Inside an existing risk rating, screen candidate variables to find sub-segments
that further separate good/bad (e.g. does `income` split tier C into better/worse
pockets?), ranked by Information Value (IV).

## API (verified — `screening.py`)
```python
fit_risk_segments(
    data: pd.DataFrame,
    base_risk_col: str,            # column holding the base rating (numeric or A–E)
    candidate_cols: str | list[str],
    default_col: str,
    n_bins: int = 10,
    method: str = "quantiles"|"ward",
    parallel: bool = False,
) -> ScreeningResult

ScreeningResult:
    metrics: pd.DataFrame                 # IV (and other metrics) per candidate variable
    recipes: dict[str, ScreeningRecipe]   # one recipe per candidate
    params: dict
    .predict(new_data, variable: str, base_risk_col: str) -> df with sub-segment
    .to_dict()

ScreeningRecipe: variable, boundaries: dict[int,list[float]], sub_mappings: dict[int,dict[int,int]]
                 .to_dict / from_dict
```

## Page: `pages/8_Risk_Screening.py`

1. `guard_dataset()`; require a base rating: either `StudioState.rating_result`
   (apply it to get a `risk_rating`/`Rating` column on the population) or let the
   user pick an existing categorical column as `base_risk_col`. If neither, friendly
   hint linking to Risk Grouping (PRD 08).
2. **Controls**:
   - `candidate_cols` multiselect (numeric/categorical columns, excluding ids,
     scores already used, and the target).
   - `n_bins` slider (default 10), `method` toggle (`quantiles` default / `ward`),
     `parallel` toggle, population selector.
3. **Run**: `fit_risk_segments(pop_df, base_risk_col, candidate_cols, default_col,
   n_bins, method, parallel)` (cached).
4. **Outputs**:
   - **IV ranking** (`result.metrics`): table + horizontal bar of IV per candidate
     (`charts.bars`), so the strongest segmentation drivers surface first.
   - **Per-variable detail**: pick a variable → show its `ScreeningRecipe`
     boundaries and, via `result.predict(pop_df, variable, base_risk_col)`, a table
     of bad rate by `(base tier × sub-segment)` and a small heatmap.
5. Persist `ScreeningResult` into `StudioState.screening_result` (for project save).

## Charts
- `charts.bars` for IV ranking.
- Heatmap (`px.imshow` themed) of bad rate across base-tier × sub-segment.

## Edge cases
- Candidate with too few unique values for `n_bins` → engine falls back; surface a
  note.
- `base_risk_col` must exist on the population; if derived from a recipe, ensure
  the recipe was applied first.

## Acceptance criteria
- Running on v14 sample with `base_risk_col=Rating` and a couple candidates (e.g.
  `income`, `age`) yields an IV ranking and a per-variable bad-rate breakdown.
- Selecting a variable shows its boundaries and a populated sub-segment table.
