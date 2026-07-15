"""PROTOTYPE — throwaway. Hard-filter suggester (wayfinder ticket #60).

The question
------------
A hard filter is a *cheap*, cadastral/scraper variable carrying a bizarre default
signal on a small slice: "1.5x a inad da base e corta pouco". Research #59 settled
the machinery (IV shortlist -> quantile grid -> declared direction -> support guard)
but assumed the credit-strategy verdict: pick the cut that hits a target approval
rate. That verdict is wrong for hard filters. The owner's rule is a **lift floor +
volume ceiling**.

This module answers: does that rule, over a quantile grid, actually surface the
hard filters planted in the data — and are `lift_min` / `max_cut` the right two
knobs for an analyst to turn?

Nothing here is production code. The pure functions below are the part worth
lifting; `tui.py` is the shell.

Two facts this prototype exists to make visible
-----------------------------------------------
1. **Selection bias.** `default_col` is only observed for contracted applicants.
   Every lift below is measured on the contracted population, not the base. A
   filter's true effect on the rejected-by-the-current-policy population is
   unobservable — same edge-extrapolation problem as #58.
2. **The 5% support floor from #59 collides head-on with `max_cut`.** A floor of
   "5% of records per side" bans every candidate a 5% volume ceiling wants. The
   floor's *intent* is "don't trust a bad rate measured on a thin bin", which is a
   statement about counts, not percentages. Here it is recast as
   `min_rejected_bads` (optbinning's `min_event_count`). Whether that recast is
   right is a question for the owner.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pycreditools._kernels import calculate_tier_metrics


@dataclass(frozen=True)
class Knobs:
    """The analyst-facing rule. Everything else is machinery."""

    lift_min: float = 1.5
    max_cut: float = 0.05
    min_rejected_bads: int = 30
    iv_min: float = 0.02  # scorecardpy var_filter convention (#59)
    n_quantiles: int = 20


def column_iv(data: pd.DataFrame, column: str, default_col: str, n_bins: int = 10) -> float:
    """IV of one column against the default flag, via the package's own kernel.

    calculate_tier_metrics is per-risk-group; a single constant group makes it
    plain IV. This is the reuse path the real suggester would take.
    """
    valid = data[[column, default_col]].dropna()
    if len(valid) < n_bins:
        return 0.0
    metrics = calculate_tier_metrics(
        values=valid[column].to_numpy(dtype=float),
        groups=np.ones(len(valid), dtype=np.int64),
        defaults=valid[default_col].to_numpy(dtype=np.int64),
        n_bins=n_bins,
    )
    return float(metrics["iv"].iloc[0]) if len(metrics) else 0.0


def candidate_thresholds(values: pd.Series, n_quantiles: int) -> tuple[np.ndarray, str]:
    """Candidate cut points, plus which grid we ended up on.

    Zero-inflated columns (78% of vl_negativacao is 0) dedup a quantile grid down
    to nothing. Falling back to distinct values is the only way such a column gets
    any candidates at all — and hard-filter columns are overwhelmingly of this shape.
    """
    quantiles = np.linspace(0, 1, n_quantiles + 1)[1:-1]
    grid = np.unique(np.quantile(values, quantiles))
    if len(grid) >= 3:
        return grid, "quantile"

    distinct = np.unique(values)
    if len(distinct) <= 50:
        return distinct, "distinct (quantile grid collapsed)"
    return np.unique(np.quantile(values, np.linspace(0, 1, 201)[1:-1])), "fine quantile"


def strategy_table(
    data: pd.DataFrame,
    default_col: str,
    directions: dict[str, str],
    knobs: Knobs,
) -> pd.DataFrame:
    """The full cutoff/strategy table — every column x every candidate threshold.

    `directions` declares, never infers: {"vl_negativacao": "lte"} means keep
    rows <= t and reject rows > t. Same spelling as CutoffStage and #57.
    """
    rows = []

    for column, direction in directions.items():
        if direction not in ("lte", "gte"):
            raise ValueError(f"direction for {column!r} must be 'lte' or 'gte', got {direction!r}")

        valid = data[[column, default_col]].dropna()
        if len(valid) < 100:
            continue

        values = valid[column]
        defaults = valid[default_col].to_numpy(dtype=float)
        base_rate = defaults.mean()
        iv = column_iv(data, column, default_col)

        grid, grid_kind = candidate_thresholds(values, knobs.n_quantiles)

        for threshold in grid:
            rejected = (values > threshold) if direction == "lte" else (values < threshold)
            rejected = rejected.to_numpy()
            n_rejected = int(rejected.sum())
            n_approved = int((~rejected).sum())
            if n_rejected == 0 or n_approved == 0:
                continue

            bads_rejected = float(defaults[rejected].sum())
            default_rejected = bads_rejected / n_rejected
            default_approved = float(defaults[~rejected].mean())

            rows.append(
                {
                    "column": column,
                    "direction": direction,
                    "threshold": float(threshold),
                    "grid": grid_kind,
                    "iv": iv,
                    "cut_volume": n_rejected / len(valid),
                    "n_rejected": n_rejected,
                    "bads_rejected": bads_rejected,
                    "default_rejected": default_rejected,
                    "lift": default_rejected / base_rate if base_rate > 0 else np.nan,
                    "default_approved": default_approved,
                    "base_default": base_rate,
                    # what the filter actually buys, in points of default rate
                    "default_avoided_pp": (base_rate - default_approved) * 100,
                }
            )

    return pd.DataFrame(rows)


def _rejection_reason(row: pd.Series, knobs: Knobs) -> str | None:
    if row["iv"] < knobs.iv_min:
        return f"IV {row['iv']:.3f} < {knobs.iv_min}"
    if row["lift"] < knobs.lift_min:
        return f"lift {row['lift']:.2f}x < {knobs.lift_min}x"
    if row["cut_volume"] > knobs.max_cut:
        return f"corta {row['cut_volume']:.1%} > {knobs.max_cut:.0%}"
    if row["bads_rejected"] < knobs.min_rejected_bads:
        return f"{int(row['bads_rejected'])} maus < {knobs.min_rejected_bads}"
    return None


def suggest(table: pd.DataFrame, knobs: Knobs) -> pd.DataFrame:
    """One suggestion per column: the most aggressive cut that still clears every knob.

    Loosening a cut (rejecting fewer) raises lift and lowers volume; tightening does
    the reverse. So `lift_min` and `max_cut` both bind from the same side, and the
    best cut under both is simply the one avoiding the most default. No trade-off to
    resolve — which is why two knobs suffice.
    """
    if table.empty:
        return table

    passing = table[table.apply(lambda r: _rejection_reason(r, knobs) is None, axis=1)]
    if passing.empty:
        return passing

    best = passing.loc[passing.groupby("column")["default_avoided_pp"].idxmax()]
    return best.sort_values("default_avoided_pp", ascending=False)


def near_misses(table: pd.DataFrame, knobs: Knobs) -> pd.DataFrame:
    """Best candidate per rejected column, with why it lost. The analyst needs the no's."""
    if table.empty:
        return table

    reasons = table.apply(lambda r: _rejection_reason(r, knobs), axis=1)
    rejected = table[reasons.notna()].assign(reason=reasons[reasons.notna()])
    suggested_cols = set(suggest(table, knobs)["column"]) if not table.empty else set()
    rejected = rejected[~rejected["column"].isin(suggested_cols)]
    if rejected.empty:
        return rejected
    return rejected.loc[rejected.groupby("column")["lift"].idxmax()].sort_values(
        "lift", ascending=False
    )
