"""Unit tests for the swap-in calibration diagnostics kernel (#72).

Two failure modes of score-bin PD imputation, each detected in isolation:
adjacent inversion (PD moves against the declared score direction) and
no-overlap (swap-ins score outside the keep-ins' observed range).
"""

import numpy as np
import pandas as pd

from pycreditools._kernels import (
    CalibrationDiagnostics,
    diagnose_score_bin_calibration,
)
from pycreditools._kernels.calibration import _count_inversions

# ── no-overlap fraction ────────────────────────────────────────────────

def test_clean_cutoff_is_full_no_overlap():
    # Every swap-in scores strictly below every keep-in: 100% extrapolation.
    cal_scores = pd.Series(np.arange(600, 700))
    cal_values = pd.Series(np.zeros(100))
    target = pd.Series(np.arange(500, 599))

    diag = diagnose_score_bin_calibration(
        cal_scores, cal_values, cal_scores, target, bins=5
    )

    assert diag.no_overlap_fraction == 1.0


def test_overrides_spanning_range_close_the_gap():
    # Swap-ins fall inside the keep-in score range: no-overlap stays quiet.
    cal_scores = pd.Series(np.arange(500, 700))
    cal_values = pd.Series(np.zeros(200))
    target = pd.Series(np.arange(550, 650))

    diag = diagnose_score_bin_calibration(
        cal_scores, cal_values, cal_scores, target, bins=5
    )

    assert diag.no_overlap_fraction == 0.0


def test_partial_overlap_reports_honest_fraction():
    cal_scores = pd.Series(np.arange(600, 700))
    cal_values = pd.Series(np.zeros(100))
    # Half below the keep-in floor, half inside.
    target = pd.Series(list(range(500, 550)) + list(range(650, 700)))

    diag = diagnose_score_bin_calibration(
        cal_scores, cal_values, cal_scores, target, bins=5
    )

    assert diag.no_overlap_fraction == 0.5


# ── adjacent inversion ─────────────────────────────────────────────────

def test_gte_monotone_decreasing_pd_no_inversion():
    # Higher score → lower PD, as gte declares. Clean.
    assert _count_inversions([0.30, 0.20, 0.10, 0.05], "gte", 0.10) == 0


def test_gte_pd_rising_beyond_tolerance_is_inversion():
    # 0.10 → 0.30 rises far past the 10% tolerance of the previous bin.
    assert _count_inversions([0.30, 0.10, 0.30], "gte", 0.10) == 1


def test_inversion_below_tolerance_is_silent():
    # 0.20 → 0.21 is a 5% rise, under the 10% relative tolerance.
    assert _count_inversions([0.20, 0.21], "gte", 0.10) == 0


def test_inversion_just_above_tolerance_fires():
    # 0.20 → 0.221 is an 10.5% rise, over the tolerance.
    assert _count_inversions([0.20, 0.221], "gte", 0.10) == 1


def test_lte_direction_mirrors():
    # Lower score is better: PD should rise with the bin index. A fall inverts.
    assert _count_inversions([0.05, 0.10, 0.30], "lte", 0.10) == 0
    assert _count_inversions([0.30, 0.10, 0.05], "lte", 0.10) == 2


def test_total_inversion_monotone_rising_gte():
    # A PD that rises monotonically against an ascending-good score is a total
    # inversion, not noise — every adjacent pair must trigger.
    assert _count_inversions([0.05, 0.15, 0.25, 0.35], "gte", 0.10) == 3


def test_nan_bins_are_skipped_not_paired():
    # Empty bins carry NaN; adjacency is over the present bins.
    assert _count_inversions([0.30, np.nan, 0.10], "gte", 0.10) == 0


# ── degenerate input never raises ──────────────────────────────────────

def test_empty_target_returns_zeroed():
    diag = diagnose_score_bin_calibration(
        pd.Series([1.0, 2.0]), pd.Series([0, 1]), pd.Series([1.0, 2.0]),
        pd.Series([], dtype=float), bins=2,
    )
    assert diag == CalibrationDiagnostics(0, 0.0)


def test_all_nan_scores_returns_zeroed():
    diag = diagnose_score_bin_calibration(
        pd.Series([np.nan, np.nan]), pd.Series([1.0, 1.0]),
        pd.Series([np.nan, np.nan]), pd.Series([1.0, 2.0]), bins=5,
    )
    assert diag == CalibrationDiagnostics(0, 0.0)


def test_diagnostics_end_to_end_clean_cutoff():
    # PD falls with score (gte-clean), but every swap-in is below the range.
    cal_scores = pd.Series(np.arange(600, 800))
    # Higher score → lower default.
    cal_values = pd.Series((np.arange(600, 800) < 700).astype(float))
    target = pd.Series(np.arange(500, 599))

    diag = diagnose_score_bin_calibration(
        cal_scores, cal_values, cal_scores, target, bins=4, direction="gte"
    )

    assert diag.no_overlap_fraction == 1.0
    assert diag.n_inversions == 0
