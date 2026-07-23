"""Integration tests: the #72 swap-in calibration warning through run_simulation.

The engine ``warnings.warn`` in ``_estimate_swap_in_baseline_pd`` is the single
source of truth for "this calibration is not measuring what it claims". These
tests drive it end to end and confirm it survives the sweep engine (#71).
"""

import warnings

import numpy as np
import pandas as pd

from pycreditools import CalibrationReliabilityWarning, CreditPolicy
from pycreditools.analysis import TradeoffAnalyzer
from pycreditools.simulation import run_simulation


def _catch(df, policy):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        run_simulation(df, policy, method="analytical")
    return [str(x.message) for x in w]


def _catch_records(df, policy):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        run_simulation(df, policy, method="analytical")
    return list(w)


def _policy(**kw):
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
        **kw,
    )


def _clean_cutoff_frame():
    """Keep-ins score high, swap-ins score strictly below them all.

    Old policy approved score >= 750; the new cutoff at 600 pulls in everyone
    above it. Every swap-in (old-rejected, new-approved) therefore scores below
    every keep-in — 100% no-overlap by construction. Keep-in default falls with
    score, so the calibration is monotone (no inversion) — only no-overlap fires.
    """
    keep = np.arange(750, 950)  # 200 keep-ins
    swap = np.arange(600, 700)  # 100 swap-ins, all below keep floor
    score = np.concatenate([keep, swap])
    approved = np.concatenate([np.ones(len(keep)), np.zeros(len(swap))])
    # Monotone-decreasing PD in score: high scores rarely default.
    default = (score < 800).astype(float) * (np.arange(len(score)) % 3 == 0)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(len(score)),
            "score": score,
            "approved": approved,
            "actual_default": default.astype(float),
        }
    )


def _overlapping_frame(default_pattern):
    """Keep-ins and swap-ins span the same score range (overlap ~100%).

    Old approval alternates independently of score, so both populations cover
    the full 600–899 range. ``default_pattern`` maps a keep-in score to its 0/1
    outcome, letting a test dial in a monotone or an inverted calibration.
    """
    score = np.tile(np.arange(600, 900), 2)  # each score appears twice
    approved = np.tile([1, 0], len(score) // 2)  # independent of score
    default = np.array([default_pattern(s) for s in score], dtype=float)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(len(score)),
            "score": score,
            "approved": approved,
            "actual_default": default,
        }
    )


# ── no-overlap trigger ─────────────────────────────────────────────────

def test_clean_cutoff_fires_no_overlap_warning():
    df = _clean_cutoff_frame()
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 600})

    msgs = _catch(df, policy)
    hits = [m for m in msgs if "outside the keep-ins' observed range" in m]

    assert len(hits) == 1
    assert "100% of swap-ins" in hits[0]
    assert "estimated_default_col" in hits[0]


def test_overrides_spanning_range_stay_quiet():
    # Monotone-decreasing PD, full overlap: neither trigger should fire.
    df = _overlapping_frame(lambda s: 1.0 if s < 700 else 0.0)
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 500})

    msgs = _catch(df, policy)

    assert not [m for m in msgs if "outside the keep-ins' observed range" in m]
    assert not [m for m in msgs if "invert" in m]


def test_no_overlap_silent_when_supplying_inference_column():
    # The escape hatch: estimated_default_col short-circuits before any warning.
    df = _clean_cutoff_frame()
    df["market_pd"] = 0.2
    policy = _policy(
        calibration_bins=4, estimated_default_col="market_pd"
    ).cutoff("Cut", {"score": 600})

    msgs = _catch(df, policy)

    assert not [m for m in msgs if "unreliable" in m]


# ── inversion trigger ──────────────────────────────────────────────────

def test_inverted_calibration_fires_inversion_warning():
    # PD rises with score (a total inversion against gte) but full overlap keeps
    # no-overlap quiet — so only the inversion warning fires.
    df = _overlapping_frame(lambda s: float((s - 600) / 300.0))
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 500})

    msgs = _catch(df, policy)
    hits = [m for m in msgs if "invert" in m]

    assert len(hits) == 1
    assert "calibration_bins" in hits[0]
    assert not [m for m in msgs if "outside the keep-ins' observed range" in m]


def test_monotone_calibration_no_inversion_warning():
    df = _overlapping_frame(lambda s: 1.0 if s < 700 else 0.0)
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 500})

    msgs = _catch(df, policy)

    assert not [m for m in msgs if "invert" in m]


# ── survives the sweep engine (#71) ────────────────────────────────────

def test_warning_survives_tradeoff_analyzer():
    df = _clean_cutoff_frame()
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 600})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        (
            TradeoffAnalyzer(policy)
            .vary_cutoff("score", [580, 600, 620], direction="gte")
            .run(df)
        )

    assert [
        str(x.message)
        for x in w
        if "outside the keep-ins' observed range" in str(x.message)
    ], "The #72 warning must reach the trade-off curve, not be suppressed by #71"


# ── category: dedicated, suppressible, decoupled from wording ───────────

def test_reliability_warning_uses_dedicated_category():
    df = _clean_cutoff_frame()
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 600})

    records = _catch_records(df, policy)
    reliability = [r for r in records if "unreliable" in str(r.message)]

    assert reliability
    assert all(
        issubclass(r.category, CalibrationReliabilityWarning) for r in reliability
    )


def test_reliability_warning_is_suppressible_by_category():
    df = _clean_cutoff_frame()
    policy = _policy(calibration_bins=4).cutoff("Cut", {"score": 600})

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        warnings.filterwarnings("ignore", category=CalibrationReliabilityWarning)
        run_simulation(df, policy, method="analytical")

    assert not [x for x in w if "unreliable" in str(x.message)]


def test_no_overlap_suppresses_the_default_bins_nudge():
    # Default bins (calibration_bins=None) + 100% no-overlap: the granularity
    # nudge is moot ("no bin count fixes this") and must not stack alongside it.
    df = _clean_cutoff_frame()
    policy = _policy().cutoff("Cut", {"score": 600})

    msgs = _catch(df, policy)

    assert [m for m in msgs if "outside the keep-ins' observed range" in m]
    assert not [m for m in msgs if "10 score bins (deciles)" in m]
