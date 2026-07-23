# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/). Pre-1.0: minor
versions may carry breaking changes.

## [0.5.0] — 2026-07-23

### Changed — BREAKING

- **Two canonical sample generators; the outcome is masked, and take-up is no
  longer a column** (#74). `generate_sample_data` now returns the *incumbent*
  base: `actual_default` is `NaN` wherever `hired == 0`, exactly as production
  masks it, so nothing can be measured on a population the legacy policy had
  already rejected. New alongside it: `generate_standalone_sample_data`, the
  greenfield base with no incumbent columns and a fully observed
  `actual_default`. Two functions, not a `scenario=` flag — the returned shape
  genuinely differs.

  Removed from `generate_sample_data` with no deprecation window:
  - `conversion_rate` — #68 gave `RateStage` `observed_col` / `calibrate_by`,
    so a stored propensity has no consumer, and ADR 0008 owns `take_up_rate` as
    a metric (contracted ÷ approved), never a column;
  - `score_decile` — the caller computes it where it needs it.

  Added: `passed_antifraud` (Bernoulli(0.90), independent of risk — a rate
  stage that is *not* take-up), `market_default` (0/1 bureau flag, observed for
  every row, the only outcome available for a reject) and `sample` (DEV/OOT).
  `actual_default` is now `float64` on both bases, since the incumbent one
  holds `NaN`.

  **Impact:** code that read `conversion_rate` or `score_decile` off the sample
  base breaks; code that assumed `actual_default` was fully observed or integer
  now sees `NaN` on non-contracted rows. The legacy cut is not returned —
  recompute it with
  `df["legacy_score"].quantile(LEGACY_APPROVAL_QUANTILE)`, the same expression
  the generator uses. For a given seed the scores, `approved` and `hired` are
  unchanged from before — only the column set and `actual_default`'s masking and
  dtype move.

- **`RateStage` is now a generic lottery stage with explicit `observed_col` /
  `calibrate_by` parameters, and the conversion-stage heuristic is gone**
  (#68). A rate stage that reads a real 0/1 outcome for keep-ins and calibrates
  swap-ins must now say so: `RateStage(name, base_rate=1.0,
  observed_col="hired")`. With `observed_col` set, keep-ins take their real
  column value and swap-ins get a score-bin-calibrated estimate
  (`calibrate_by="score"`, the default) or the flat observed mean over approved
  (`calibrate_by=None`). `base_rate` and `variable` are ignored when
  `observed_col` is set — the rate comes from the data.

  Removed with no deprecation window:
  - the stage-name heuristic (`"conversao"`, `"conversion"`, `"hired"`,
    `"take_up"`, `"take_up_rate"`);
  - the "last `RateStage` is the conversion stage" fallback;
  - the `"hired"` column auto-detect;
  - `calibrate=True` implying conversion behaviour.

  **Impact:** a policy that relied on the old auto-election — e.g. a last
  `RateStage(variable="take_up_rate")`, or a `calibrate=True` stage next to a
  `hired` column — will now treat `variable` as a plain multiplier and give
  keep-ins the 1.0 bypass instead of their real outcome. Numbers change for
  anyone who leaned on the heuristic. Move to `observed_col` to restore the old
  behaviour. `policy.current_hired_col` survives as a column role only (it is
  the obvious value to hand to `observed_col`) and no longer drives any engine
  branch.

- **`true_pd` removed from the sample generators** (#76). The synthetic oracle
  column carried no client-facing meaning and had grown consumers across the
  notebooks, tests and studio detection. Both bases now expose only observable
  columns; `market_default` remains the observed outcome for rejects on the
  incumbent base.

### Added

- **Masterclass notebook rebuilt on the v14 executive arc** (#76),
  `src/pycreditools/examples/tutorial_masterclass.ipynb`. Twelve sections from the
  incumbent panorama to a deployable policy JSON — KS on the contracted book, the
  bureau funnel, the efficient frontier via `TradeoffAnalyzer`, three executive
  propositions, per-region cutoffs via the sweep engine, out-of-time rating
  validation, rating-angled swap-in stress, the swap dissection, the P&L delta and
  the crash test. Uses the package's own surfaces (`TradeoffAnalyzer`,
  `optimize_cutoffs`, `print_delta_table`, `print_quadrant_summary`,
  `fit_risk_groups`) rather than hand-rolled equivalents. The standalone quickstart
  was dropped — the masterclass is the single canonical example.
