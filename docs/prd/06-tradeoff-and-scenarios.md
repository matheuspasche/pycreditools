# PRD 06 — Trade-off & Scenarios (efficient frontier)

> Depends on PRD 04. Mirrors notebook v14 Cells 6–7. Wraps `TradeoffAnalyzer`,
> `run_tradeoff_analysis`, `plot_tradeoffs`. See Master §8, §9 (run on DEV by
> default for speed).

## Objective

Sweep a cutoff (and optionally a take-up rate or the stress factor) across a range
of values to draw the **approval-rate × default-rate efficient frontier**, compare
multiple score models on the same axes, and pick an executive scenario
(conservative / neutral / aggressive).

## API (verified — `analysis.py`)
```python
TradeoffAnalyzer(base_policy: CreditPolicy)
  .vary_cutoff(col_name: str, values: list[float], direction: str = ">=") -> self
  .vary_base_rate(stage_name: str, values: list[float]) -> self
  .vary_stress_aggravation(values: list[float]) -> self
  .run(data: pd.DataFrame, parallel: bool = False) -> pd.DataFrame
      # one row per combination; columns include approval_rate, default_rate,
      # the varied param column(s), and (when varying cutoff) the cutoff value.

run_tradeoff_analysis(data, base_policy, vary_params: dict[str, list],
                      vary_directions: dict[str,str]|None=None, parallel=False) -> pd.DataFrame
plot_tradeoffs(tradeoff_df, legacy_approval_rate=None, legacy_bad_rate=None,
               x_col="approval_rate", y_col="default_rate", hue_col="Score_Model") -> plt.Figure
```
> Build the frontier chart in Plotly (`charts.frontier`) for theme/interactivity;
> `plot_tradeoffs` (matplotlib) is reference only.

## Page: `pages/5_Tradeoff.py`

1. `require_policy()`. Use the active policy as `base_policy`. Strip its own cutoff
   on the swept score (the analyzer injects the swept cutoff) — i.e. build a base
   policy with the hard filters + stress but let `vary_cutoff` drive the score
   threshold.
2. **Controls** (bordered container):
   - **Score(s) to sweep**: multiselect over `score_cols` (default = all candidate
     scores, like the notebook loops `score_2..5`). For each, run the analyzer and
     tag rows with `Score_Model` = that score, then `pd.concat`.
   - **Cutoff range**: min/max default to the score's p5–p95 (per Master), number
     of steps (slider, default 35 as in v14). Generate
     `np.linspace(p5, p95, steps).astype(int).tolist()`.
   - Optional **also vary**: stress factor (`vary_stress_aggravation`, list) or a
     rate stage's base rate (`vary_base_rate`).
   - Population selector (default **DEV**) and `parallel` toggle.
3. **Run** each selected score: `TradeoffAnalyzer(base).vary_cutoff(score, values).run(pop_df, parallel)`,
   add `Score_Model`, concat → `res_all`. Cache by `(df_hash, population, base.to_dict(), score, values)`.
4. **Frontier chart** (`charts.frontier`): scatter+line of `approval_rate` (x) vs
   `default_rate` (y), one colored series per `Score_Model`. Overlay the legacy
   reference point (`legacy_approval_rate`, `legacy_bad_rate`) from `legacy_sim` /
   baseline if available (a distinct marker + crosshair guides). Lower-and-right is
   better; annotate.
5. **Scenario picker** (for the primary score, default `primary_score_col`), three
   executive presets computed exactly like v14 Cell 7 from that score's rows
   (`res_s = res_all[res_all.Score_Model == primary]`):
   - **Conservador** — row whose `approval_rate` is closest to the legacy approval
     rate (`(res_s.approval_rate - legacy_appr).abs().idxmin()`).
   - **Agressivo** — row whose `default_rate` is closest to the legacy bad rate.
   - **Neutro** — row whose cutoff is closest to the midpoint of the conservador &
     agressivo cutoffs.
   - Render the 3 as KPI cards (cutoff, approval rate, default rate) and highlight
     their points on the frontier.
   - Button **"Aplicar cutoff ao Policy Studio"**: writes the chosen scenario's
     cutoff into the active policy (adds/updates a `CutoffStage` on the chosen
     score) so the user can carry it forward.
6. **Results table**: `res_all` themed (percent cols), sortable.

## Charts
- `charts.frontier(df, x_col, y_col, hue_col, legacy=(appr,bad)|None)` → Plotly
  scatter + connecting line per hue, legacy reference marker, good-direction
  annotation.

## Performance
- Frontier on DEV with 35 steps × 4 scores = 140 analytical sims — fine. Warn if
  the user runs on full base × many steps; show a spinner with progress.

## Edge cases
- If `legacy_sim`/baseline missing, hide the legacy reference and the
  conservador/agressivo presets that depend on it (keep "Neutro" by cutoff
  midpoint disabled with a hint to set a baseline in PRD 05).
- Cutoff column with low variance → fall back to median single point.

## Acceptance criteria
- Frontier reproduces the v14 shape: `score_5` dominates lower-left of the others;
  legacy point sits above the frontier.
- The three scenarios match the notebook's selection logic for `score_5` on DEV.
- "Aplicar cutoff" updates the active policy and the funnel/sim pages reflect it.

## Validação & Gate (BLOQUEANTE)

> Não avance sem as 4 camadas verdes **E** o "aprovado" do dono. Ver `IMPLEMENTATION_GUIDE.md` §3–§4.

### Definition of Done
- [ ] Varrer cutoff por score(s) selecionado(s); concat com `Score_Model`.
- [ ] Fronteira eficiente (Plotly) + ponto de referência legado.
- [ ] 3 cenários (conservador/neutro/agressivo) calculados como no v14 Cell 7.
- [ ] Botão "Aplicar cutoff ao Policy Studio" altera a política ativa.
- [ ] População default = DEV; spinner em runs grandes.

### Validação automática
- **L1** `ruff check ...` → 0.
- **L2** seleção de cenário (`idxmin` de |approval-legacy| etc.) correta dado um `res` sintético; "aplicar cutoff" muda a policy em estado.
- **L3** AppTest com `studio_state_with_policy`: rodar fronteira → chart + tabela; sem exceção.
- **L4** **Paridade**: linhas da fronteira == `TradeoffAnalyzer(base).vary_cutoff(...).run(df)` direto (mesma base/steps).

### Verificação visual (dono)
1. Fronteira: `score_5` domina o canto inferior; legado acima da curva. 2. Cenários batem com o notebook para `score_5`/DEV.

### Gate
Entregue o **Gate Report** e **pare**. Pergunte: "Aprova o PRD 06?".
