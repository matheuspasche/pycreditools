"""Engine contract: a scalar/anonymous RateStage does NOT re-gate the keep-in.

Issue #94. A ``RateStage`` sourced from a pure scalar (``base_rate`` only, no
``observed_col`` and no ``variable``) applied to a book with
``current_approval_col`` active must **bypass** the keep-in population — every
keep-in passes at ``1.0`` — while swap-ins pass at the scalar rate.

This is the declarative rule of ADR 0010 ("declared instead of inferred", and
the death of the ``RateStage`` name/position heuristic): the keep-in's take-up
is sourced from what is *recorded* about it (``observed_col``); absent a
recorded outcome, its membership in the incumbent book is the only fact, so its
contribution to contracted volume is taken as given (``1.0``), never re-drawn
from a swap-in-calibrated rate.

The pre-existing ``test_name_conversao_is_not_special_without_observed_col``
locks the bypass with ``base_rate=1.0`` only — where bypass and re-gate are
indistinguishable (both yield ``1.0``). These tests use ``base_rate < 1.0`` so
bypass (``1.0``) and re-gate (``base_rate``) split apart, pinning the contract
that would have caught the divergent ``main`` behaviour (keep-in re-gated to a
fractional rate). Deterministic: analytical mode, no draws.
"""

import warnings

import numpy as np
import pandas as pd

from pycreditools import CreditPolicy

BASE_RATE = 0.90


def _frame() -> pd.DataFrame:
    """Half the population is the incumbent book (approved=1, the keep-ins);
    the other half is unapproved and pulled in by a permissive cutoff, so they
    become swap-ins that face the scalar rate."""
    n = 200
    score = np.linspace(300, 900, n)
    approved = (np.arange(n) % 2 == 0).astype(int)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(n),
            "score_5": score,
            "approved": approved,
            "actual_default": np.zeros(n),
        }
    )


def _policy() -> CreditPolicy:
    return (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            calibration_bins=5,
        )
        .cutoff("Pull everyone in", {"score_5": 300}, direction="gte")
        .rate("Anti-fraud", base_rate=BASE_RATE)  # scalar, no observed_col, no variable
    )


def _simulate() -> pd.DataFrame:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _policy().simulate(_frame(), method="analytical").data


def test_scalar_rate_bypasses_keep_in_and_gates_swap_in():
    """Keep-ins pass at 1.0 (bypass), swap-ins pass at the scalar base_rate."""
    d = _simulate()
    rate_col = next(c for c in d.columns if "Anti-fraud" in c)
    keep = d["scenario"] == "keep_in"
    swap = d["scenario"] == "swap_in"

    assert keep.any() and swap.any(), "fixture must hold both quadrants"

    keep_vals = d.loc[keep, rate_col].unique()
    swap_vals = d.loc[swap, rate_col].unique()

    # Bypass: keep-ins are exactly 1.0 -- NOT the scalar rate (that is the main bug).
    assert np.allclose(keep_vals, 1.0, atol=1e-12)
    assert not np.isclose(keep_vals, BASE_RATE).any()
    # Swap-ins get the scalar rate.
    assert np.allclose(swap_vals, BASE_RATE, atol=1e-12)


def test_keep_in_contracted_volume_equals_population():
    """The #94 headline: keep_in_vol == keep-in population exactly (bypass 1.0),
    read off ``new_approval`` per the ADR 0008 metric contract -- no fast-path."""
    d = _simulate()
    keep = d["scenario"] == "keep_in"

    population = int(keep.sum())
    contracted = float(d.loc[keep, "new_approval"].sum())
    assert contracted == population

    # And every keep-in row carries new_approval == 1.0 (not re-gated).
    assert np.allclose(d.loc[keep, "new_approval"].to_numpy(), 1.0, atol=1e-12)
