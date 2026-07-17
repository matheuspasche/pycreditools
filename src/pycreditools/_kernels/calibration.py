from collections.abc import Sequence

import numpy as np
import pandas as pd


def calibrate_by_score_bins(
    cal_scores: pd.Series,
    cal_values: pd.Series,
    ref_scores: pd.Series,
    target_scores: pd.Series,
    bins: int | Sequence[float],
    global_fallback: float,
) -> pd.Series:
    """Map a per-row rate onto ``target_scores`` from a score-binned calibration.

    Bin edges are learned from ``ref_scores`` (``qcut`` when ``bins`` is an int,
    otherwise the given edge sequence, both pushed to ``±inf`` at the outer
    boundaries). The calibration population is dropped into those bins and its
    ``cal_values`` averaged per bin; missing bins fall back to ``global_fallback``.
    Every target row is then binned the same way and receives its bin's rate.

    The mask that selects the calibration population is **not** resolved here —
    the caller passes ``cal_scores``/``cal_values`` already sliced to it.

    Args:
        cal_scores: float64[n_cal] - scores of the calibration population.
        cal_values: float64[n_cal] - observed values of that population (a 0/1
            flag or any rate-valued column); must share ``cal_scores``' index.
        ref_scores: float64[n_ref] - scores that define the bin edges.
        target_scores: float64[n_target] - scores of the rows to receive a rate.
        bins: number of quantile bins, or an explicit sequence of bin edges.
        global_fallback: rate used for empty bins and any unresolved row.

    Returns:
        Series of rates, one per target row, indexed like ``target_scores``.
    """
    try:
        if isinstance(bins, int):
            _, bin_edges = pd.qcut(ref_scores, q=bins, retbins=True, duplicates="drop")
            # Extend edges so out-of-range values clip to the nearest bin
            bin_edges[0] = -np.inf
            bin_edges[-1] = np.inf
        else:
            edges = list(bins)
            if edges[0] > -np.inf:
                edges.insert(0, -np.inf)
            if edges[-1] < np.inf:
                edges.append(np.inf)
            bin_edges = np.array(edges)

        cal_bins = pd.cut(cal_scores, bins=bin_edges, labels=False, include_lowest=True)
        bin_rate = cal_values.groupby(cal_bins).mean()

        # Ensure every bin index maps to something (empty bins → global fallback)
        all_bin_indices = range(len(bin_edges) - 1)
        bin_rate = bin_rate.reindex(all_bin_indices).fillna(global_fallback)

        target_bins = pd.cut(
            target_scores, bins=bin_edges, labels=False, include_lowest=True
        )
        result = target_bins.map(bin_rate).fillna(global_fallback)
    except Exception:
        result = pd.Series(global_fallback, index=target_scores.index)

    return pd.Series(result.values, index=target_scores.index)
