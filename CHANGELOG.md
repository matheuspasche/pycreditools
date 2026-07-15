# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project is pre-1.0:
breaking changes ship in minor releases and are listed under **Breaking**.

## [0.5.0] — Unreleased

### Breaking

- **`RateStage` no longer elects a "conversion stage" (#68).** A rate stage is a generic
  lottery stage — take-up/contratação is only the obvious example; credit-desk approval,
  formalização and antifraude are the same shape. The engine used to decide "am I the
  conversion stage?" by itself, and now does not. Removed outright, with no deprecation
  window:

  - the **name heuristic** — a stage called `conversao`, `conversion`, `hired`, `take_up`
    or `take_up_rate` is no longer special;
  - the **last-`RateStage` fallback** — the final rate stage of a policy is no longer
    elected by position;
  - the **`"hired"` column auto-detect** — a column literally named `hired` no longer
    means anything to the engine;
  - the rule that **`calibrate=True` implied a conversion stage**. `calibrate=True` now
    only does what it always claimed: wrap `variable` in a `CalibratedExpression`.

  **What changes in your numbers.** An old policy built as
  `RateStage(name="Conversao", variable="take_up_rate")` still runs, but as a plain
  multiplier — which is what the `variable` docstring always said it was. Where an
  auto-elected stage used to give keep-ins their historical `hired` value, they now pass
  at 1.0, so the funnel gets larger for anyone who relied on the auto-election. To get
  the old behaviour back, say it explicitly:

  ```python
  # before (implicit, by name or by position)
  policy.rate("Conversao", base_rate=1.0, variable="take_up_rate")
  # after (explicit)
  policy.rate("Contratação", base_rate=1.0, observed_col="hired")
  ```

- **`CreditPolicy.current_hired_col` drives no engine branch.** It survives as a *column
  role* only: the source of the studio's `suggested_take_up_rate`, and the obvious value
  to hand to `observed_col`. Setting it alone no longer changes a simulation.

### Added

- **`RateStage(observed_col=...)` (#68)** — the 0/1 column holding the real outcome of a
  rate stage. Keep Ins take their value from it verbatim (no draw); Swap Ins get an
  estimate of it, scaled by `base_rate`. `base_rate=1.0` means "use the observed rate as
  is".
- **`RateStage(calibrate_by=...)` (#68)** — how the Swap In estimate is built.
  `"score"` (the default when `observed_col` is given) bins the Keep Ins by score, using
  the same knobs as the swap-in PD imputation (`calibration_score_col`,
  `calibration_bins`), and gives each Swap In the observed rate of its bin — so a take-up
  that falls with worse score does not flatter the swap-ins with the global mean.
  `calibrate_by=None` gives the flat observed mean over the approved population.
  When `"score"` cannot run (no usable score column, or Keep Ins under the same floor the
  PD imputation uses), it falls back to the flat mean and `warnings.warn`s — it never
  raises, so a project with no score mapped keeps running.
- Both params are serialized by `RateStage.to_dict()`, accepted by `CreditPolicy.rate()`
  and by the studio's `make_rate_row()`, and reachable from the Bancada's Taxa row.
  Policies serialized before this release deserialize with `observed_col=None`.
- `CreditPolicy.validate()` now reports a missing `observed_col` alongside the other
  required columns.

### Unchanged, deliberately

- **The keep-in bypass stays.** A rate stage with no `observed_col` still gives Keep Ins
  `probs = 1.0`. This is not backwards compatibility: a Keep In only has a real outcome in
  `actual_default_col` because they actually contracted, so their take-up is 1.0 *by
  construction of the data*. `take_up_rate` therefore comes out as a mixture (keep-ins at
  100%, swap-ins modelled), and that mixture is the truth, not a slippery denominator.

## [0.4.1]

- Declare `matplotlib` and `seaborn` as base dependencies (#52).
- `studio.bars()` accepts a `title` param; `_apply_layout` never passes `title=None` (#50).
- The aggravation game responds to `factor` when `estimated_default_col` is set (#49).
