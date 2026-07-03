# PRD 08 — Risk Grouping & Ratings (clustering → A–E)

> Depends on PRD 02. Feeds ratings into Simulation (05), Screening (09),
> Deployment (10). Mirrors notebook v14 Cell 9 / v15 Cell 9–10 / v16 Cell 10.
> Wraps `fit_risk_groups`, `fit_pairwise_risk_groups`, `RiskGroupResult`,
> `GroupingRecipe`, `plot_vintage_stability`. See Master §8.

## Objective

Cluster a score (or scores) into stable, monotonic risk tiers (A–E), label them
by PD, validate stability across vintages (DEV vs OOT), and persist the recipe so
other pages can assign ratings.

## API (verified — `grouping.py`, `visualization.py`)
```python
fit_risk_groups(
    data, score_cols: str | list[str], default_col: str,
    bins: int = 20, max_groups: int | None = None,   # None -> 5
    min_vol_ratio: float = 0.05, max_crossings: int = 1,
    time_col: str | None = None, method: str = "ward"|"iv",
    oot_date=None,                                    # with time_col: < oot = train, >= oot = OOT
) -> RiskGroupResult

RiskGroupResult:
    data: pd.DataFrame        # input rows + 'risk_rating' (numeric cluster id)
    groups: pd.DataFrame      # per-rating: volume, pd
    recipe: GroupingRecipe
    n_groups: int
    params: dict
    report: pd.DataFrame      # DEV/OOT stability table when oot_date given
    .predict(new_data) -> df with 'risk_rating'

fit_pairwise_risk_groups(data, score_cols: list[str], default_col, **kwargs)  # primary vs challengers
GroupingRecipe.predict / to_dict / from_dict / to_json / from_json

plot_vintage_stability(df, rating_col="Rating", time_col="safra",
    default_col="actual_default", approval_col="new_approval",
    oot_start_safra="2025-01") -> plt.Figure   # reference; rebuild in Plotly
```
> `risk_rating` is a numeric cluster id. **Labeling A–E**: sort clusters by mean
> PD ascending and map to letters (A = lowest PD). This is exactly the notebook
> pattern:
> ```python
> cluster_pd = res.data.groupby("risk_rating")[default_col].mean().sort_values()
> labels = {cid: lab for cid, lab in zip(cluster_pd.index, ["A","B","C","D","E",...])}
> ```
> Store `rating_labels` in `StudioState`.

## Page: `pages/7_Risk_Grouping.py`

1. `guard_dataset()`; `guard_roles("actual_default_col")`. Recommend the **approved
   survivors** population (the notebook fits on `new_approval > 0 & DEV`); offer the
   population selector (default **Aprovados/DEV**).
2. **Mode** tabs: **Único** (one or more scores in one clustering) vs **Pairwise**
   (primary vs challengers).

### Único
- Controls: `score_cols` multiselect (default `[primary_score_col]`; allow 2 for
  the v16 multivariate case), `bins` (default 30), `max_groups` (default 5),
  `min_vol_ratio` (default 0.01), `max_crossings` (default 1), `method`
  (`ward`/`iv`), `time_col` (from roles), `oot_date` (from roles).
- Run `fit_risk_groups(...)` → store `RiskGroupResult` in `rating_result`; compute
  + store `rating_labels`.
- **Outputs**:
  - KPI: `n_groups`, total volume, PD spread (A vs E).
  - **Groups table** (`result.groups`): rating (labeled A–E via labels),
    volume, PD (%), colored by `RISK_COLORS`. Show monotonic PD.
  - **PD-by-tier bar** (`charts.bars`) using `RISK_COLORS`.
  - **Stability report** (`result.report`, when `oot_date` set): DEV vs OOT volume
    & bad rate per tier; flag tiers whose DEV↔OOT bad rate diverges.
  - **Vintage stability chart** (`charts.vintage_stability`): default rate per
    tier across `time_col`, with a vertical line at `oot_date` separating DEV/OOT.
    Build from `result.data` (apply labels) grouped by `(time_col, Rating)` mean of
    `default_col`. (Rebuild `plot_vintage_stability` in Plotly.)
  - **Score → rating map**: show the recipe intervals (`recipe.intervals` /
    `quantile_breaks`) so the user sees the cutoffs per tier.
- Button **"Usar este rating nas demais páginas"** → confirms `rating_result` +
  `rating_labels` are active (already stored), so Simulation/Deployment pick it up.

### Pairwise
- Controls: `primary` (selectbox), `challengers` (multiselect), shared params.
- Run `fit_pairwise_risk_groups(data, score_cols=[primary,*challengers], default_col, **kwargs)`.
  Render each pair's `report` (stability) so the user can judge whether a cheaper
  challenger score can replace the primary. (Use case from v15 Cell 10.)

## Charts
- `charts.bars` (PD per tier, RISK_COLORS).
- `charts.vintage_stability(df, rating_col, time_col, default_col, oot_date)` →
  one line per tier over time, colored by RISK_COLORS, dashed vline at oot.

## Edge cases
- `max_groups > bins` raises — clamp the slider so `max_groups ≤ bins`.
- Empty train set (oot_date too early) raises — translate to a friendly message.
- Target NaN for non-hired: fit on a population where `default_col` is observed;
  surface effective N.
- Multivariate (2 scores): supported; note clustering sorts by PD, not bin order.

## Acceptance criteria
- On v14 sample (approved/DEV, score_5, bins=30, max_groups=5), produces ~5
  tiers with monotonically increasing PD A→E; labels assigned by PD.
- With `oot_date="2025-01"`, the stability report and vintage chart populate and
  the DEV/OOT lines are visible around the boundary.
- After fitting, the Simulation page's swap-in-by-rating section becomes available.
- `recipe.to_dict()` round-trips via `from_dict` (used by project save & deploy).

## Validação & Gate (BLOQUEANTE)

> Não avance sem as 4 camadas verdes **E** o "aprovado" do dono. Ver `IMPLEMENTATION_GUIDE.md` §3–§4.

### Definition of Done
- [ ] `fit_risk_groups` (modo Único, 1–2 scores) e `fit_pairwise_risk_groups` (modo Pairwise).
- [ ] Labels A–E por PD ascendente; `rating_result` + `rating_labels` em estado.
- [ ] Tabela de grupos + bar de PD por tier (RISK_COLORS); stability report (com `oot_date`).
- [ ] Gráfico de vintage stability (Plotly) com vline no `oot_date`.
- [ ] `max_groups` clampado a `≤ bins`.

### Validação automática
- **L1** `ruff check ...` → 0.
- **L2** o mapeamento A–E ordena por PD asc corretamente; `recipe.to_dict`↔`from_dict` idêntico; o resumo de PD por tier == `groupby` direto em `result.data`.
- **L3** AppTest com `studio_state`: rodar grouping → tabela + bar; com `oot_date` → report presente.
- **L4** **Paridade**: `fit_risk_groups` via studio == chamada direta (mesmos `n_groups` e PDs por tier).

### Verificação visual (dono)
1. Aprovados/DEV, `score_5`, bins=30, max_groups=5 → ~5 tiers com PD monotônica A→E. 2. Vintage chart com DEV/OOT separados.

### Gate
Entregue o **Gate Report** e **pare**. Pergunte: "Aprova o PRD 08?".
