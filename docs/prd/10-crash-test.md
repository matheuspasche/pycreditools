# PRD 10 — Crash Test (breakeven stress)

> Depends on PRD 04 (and a baseline bad rate, usually from PRD 05). Page file:
> `pages/9_Crash_Test.py`. Mirrors notebook v14 Cell 13. Wraps
> `TradeoffAnalyzer.vary_stress_aggravation` + `plot_crash_test`. See Master §8.

## Objective

Answer "how much worse than our model would the swap-in PD have to be before the
new policy's bad rate hits the legacy bad rate?" — i.e. the resilience / margin of
safety of the policy, expressed as a **breakeven aggravation factor**.

## API (verified — `analysis.py`, `visualization.py`)
```python
crash_df = (TradeoffAnalyzer(policy)
            .vary_stress_aggravation(values: list[float])
            .run(data, parallel=False))
# crash_df columns include: aggravation_factor, default_rate, approval_rate

plot_crash_test(crash_df, legacy_bad_rate: float,
                breakeven_factor: float | None = None) -> plt.Figure   # reference; rebuild in Plotly
```

## Page: `pages/9_Crash_Test.py`

1. `require_policy()`. The active policy is the base (its existing flat stress, if
   any, is overridden by the swept factor).
2. **Controls**:
   - factor range slider (default 1.0 → 10.0) and steps (default 37, as in v14) →
     `np.linspace(min, max, steps).tolist()`.
   - `legacy_bad_rate`: auto-fill from `legacy_sim` (or the observed hired bad rate)
     with an override number input.
   - population selector (default **DEV**), `parallel` toggle.
3. **Run**: `TradeoffAnalyzer(policy).vary_stress_aggravation(values).run(pop_df, parallel)`
   (cached). Compute **breakeven** = the first `aggravation_factor` whose
   `default_rate >= legacy_bad_rate` (linear-interpolate between bracketing rows
   for a smoother number); `None` if never reached.
4. **Outputs**:
   - KPI: breakeven factor (big), interpretation text ("a PD real dos swap-ins
     precisaria ser **{x:.1f}×** pior que o modelo para igualar a inadimplência
     legada"), and whether the policy is conservative (high breakeven) or tight.
   - **Crash chart** (`charts.crash`): line of `default_rate` vs
     `aggravation_factor`, horizontal reference line at `legacy_bad_rate`, vertical
     marker at the breakeven factor, area below legacy shaded "safe".
   - **Results table**: `crash_df` themed (percent default_rate/approval_rate).

## Charts
- `charts.crash(crash_df, legacy_bad_rate, breakeven)` → Plotly line + legacy
  hline + breakeven vline + annotation.

## Edge cases
- `default_rate` never reaches `legacy_bad_rate` within the range → breakeven =
  None; show "não atinge no intervalo testado — aumente o fator máximo".
- No baseline available → require the user to input `legacy_bad_rate` manually.

## Acceptance criteria
- On v14 sample/DEV with factors 1→10, the curve rises monotonically and the
  breakeven matches the notebook's computed factor (first crossing of legacy bad
  rate) within interpolation tolerance.
