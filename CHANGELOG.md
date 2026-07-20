# Changelog

All notable changes to this project are documented here. The format is loosely
based on [Keep a Changelog](https://keepachangelog.com/). Pre-1.0: minor
versions may carry breaking changes.

## [Unreleased] — v0.5

### Changed — BREAKING

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
