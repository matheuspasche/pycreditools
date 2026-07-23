from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


def _resolve_bin_edges(
    ref_scores: pd.Series, bins: int | Sequence[float]
) -> np.ndarray:
    """Learn bin edges from ``ref_scores``, outer boundaries pushed to ``±inf``.

    ``qcut`` when ``bins`` is an int, otherwise the given edge sequence. Shared
    by :func:`calibrate_by_score_bins` and :func:`diagnose_score_bin_calibration`
    so the two never drift on how a row is binned.
    """
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
    return bin_edges


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
        bin_edges = _resolve_bin_edges(ref_scores, bins)

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


@dataclass(frozen=True)
class CalibrationDiagnostics:
    """Two ways a swap-in score→PD calibration silently lies.

    ``n_inversions`` counts adjacent bin pairs whose PD moves against the score's
    declared direction beyond the relative tolerance. ``no_overlap_fraction`` is
    the share of target rows scoring outside the calibration population's range —
    pure edge-clamp extrapolation, not measurement.
    """

    n_inversions: int
    no_overlap_fraction: float


def _count_inversions(
    bin_pd: Sequence[float], direction: str, rel_tol: float
) -> int:
    """Count adjacent bin pairs that move against the declared direction.

    Bins arrive in ascending score-bin order. With ``direction="gte"`` (higher
    score is better) PD should fall as the bin index rises, so a pair inverts
    when the later PD exceeds the earlier by more than ``rel_tol`` of the
    earlier. ``direction="lte"`` mirrors it. Tolerance is relative to the
    previous bin's PD — an absolute pp tolerance is meaningless across a 2%-PD
    and a 30%-PD book. Every bin participates; there is no support floor.
    """
    vals = [v for v in bin_pd if not pd.isna(v)]
    inversions = 0
    for prev, nxt in zip(vals, vals[1:]):
        margin = rel_tol * prev
        if direction == "lte":
            # Lower score is better: PD should rise with the bin index.
            if nxt < prev - margin:
                inversions += 1
        else:
            # gte (default): higher score is better, PD should fall.
            if nxt > prev + margin:
                inversions += 1
    return inversions


def diagnose_score_bin_calibration(
    cal_scores: pd.Series,
    cal_values: pd.Series,
    ref_scores: pd.Series,
    target_scores: pd.Series,
    bins: int | Sequence[float],
    direction: str = "gte",
    rel_tol: float = 0.10,
) -> CalibrationDiagnostics:
    """Diagnose a swap-in score-bin calibration for the two #72 failure modes.

    Mirrors :func:`calibrate_by_score_bins`' binning exactly (shared
    ``_resolve_bin_edges``) so the diagnosed bins are the calibrated bins.

    Args:
        cal_scores: scores of the calibration (keep-in) population.
        cal_values: observed 0/1 default flags of that population.
        ref_scores: scores that define the bin edges.
        target_scores: scores of the swap-in rows receiving an imputed PD.
        bins: number of quantile bins, or an explicit sequence of edges.
        direction: the score's **declared** direction, "gte" or "lte" — never
            inferred from the data.
        rel_tol: inversion tolerance, as a fraction of the previous bin's PD.

    Returns:
        A :class:`CalibrationDiagnostics`. On degenerate input the diagnostics
        collapse to "nothing detected" (0 inversions, 0.0 outside) rather than
        raising — detection must never break a run that would otherwise succeed.
    """
    try:
        if len(target_scores) == 0 or len(cal_scores.dropna()) == 0:
            return CalibrationDiagnostics(0, 0.0)

        lo = cal_scores.min()
        hi = cal_scores.max()
        outside = (target_scores < lo) | (target_scores > hi)
        no_overlap_fraction = float(outside.mean())

        bin_edges = _resolve_bin_edges(ref_scores, bins)
        cal_bins = pd.cut(cal_scores, bins=bin_edges, labels=False, include_lowest=True)
        bin_pd = cal_values.groupby(cal_bins).mean().sort_index()
        n_inversions = _count_inversions(list(bin_pd.values), direction, rel_tol)

        return CalibrationDiagnostics(n_inversions, no_overlap_fraction)
    except Exception:
        return CalibrationDiagnostics(0, 0.0)
