"""Engine contract: the keep-in contract weight is its OBSERVED hire (ADR 0011).

Issue #103. The core ``simulate()`` consumes ``current_hired_col``: a keep-in
that survives the new policy's hard stages is weighted by its real hire (0/1),
NOT a silent 1.0. An approved-but-never-hired keep-in gets contract weight 0, so
it leaves BOTH sides of the default-rate ratio (realizes #101; amends ADR 0010
#94's "passes at 1.0"). A modeled rate stage still never re-gates a keep-in.

Rollout (#103): an *undeclared* take-up (keep-ins, no ``current_hired_col``, no
``observed_col`` stage) currently emits a ``DeprecationWarning`` and keeps the
legacy 1.0 pass-through. That warning becomes a hard error in a follow-up.

Deterministic: analytical mode, no draws.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy


def _frame() -> pd.DataFrame:
    # 10 incumbent keep-ins. 5 hired (2 defaults), 5 approved-but-never-hired
    # (hired=0, actual_default NaN — no outcome to observe).
    n = 10
    hired = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype=float)
    outcome = np.array([1, 1, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, np.nan], dtype=float)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(n),
            "score_5": np.linspace(300, 900, n),
            "approved": np.ones(n, dtype=int),
            "hired": hired,
            "actual_default": outcome,
        }
    )


def _policy(with_hire: bool) -> CreditPolicy:
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        current_approval_col="approved",
        actual_default_col="actual_default",
        current_hired_col="hired" if with_hire else None,
        calibration_bins=5,
    ).cutoff("keep all", {"score_5": 300}, direction="gte")


def test_keep_in_weighted_by_observed_hire():
    """new_approval mirrors current_hired_col: hired keep-ins weight 1, the
    approved-but-never-hired weight 0 — not a blanket 1.0."""
    frame = _frame()
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no DeprecationWarning when hire is declared
        d = _policy(with_hire=True).simulate(frame, method="analytical").data

    keep = d["scenario"] == "keep_in"
    assert keep.all(), "fixture is a pure incumbent book"

    np.testing.assert_allclose(
        d["new_approval"].to_numpy(), frame["hired"].to_numpy(), atol=1e-12
    )
    # Contracted volume is the hired count (5), not the population (10).
    assert float(d["new_approval"].sum()) == pytest.approx(5.0)


def test_no_outcome_keep_in_excluded_via_hire_weight():
    """The #103 headline: the 5 never-hired keep-ins carry weight 0, so they do
    not sit in the default-rate denominator (the cause fix, not the metric mask)."""
    frame = _frame()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = _policy(with_hire=True).simulate(frame, method="analytical").data

    contracted = d["new_approval"] > 0
    # Only the 5 hired rows are contracted; all 5 no-outcome rows dropped out.
    assert int(contracted.sum()) == 5
    assert d.loc[frame["hired"] == 0, "new_approval"].sum() == pytest.approx(0.0)


def test_undeclared_take_up_warns():
    """No current_hired_col and no observed_col stage over a keep-in book emits a
    DeprecationWarning (staged toward a hard error)."""
    frame = _frame()
    with pytest.warns(DeprecationWarning, match="current_hired_col"):
        _policy(with_hire=False).simulate(frame, method="analytical")


def test_non_binary_hired_raises():
    """current_hired_col is an observed 0/1 flag; a fractional/other value over a
    keep-in would silently mis-weight the default, so it raises (ADR 0011)."""
    frame = _frame()
    frame.loc[0, "hired"] = 0.5  # a rate-looking value where a 0/1 flag is required
    with pytest.raises(ValueError, match="must be 0/1"):
        _policy(with_hire=True).simulate(frame, method="analytical")


def test_scalar_rate_over_keep_in_uses_observed_hire_not_bypass():
    """ADR 0011 Migration lock: a scalar RateStage (the #103 root-cause path,
    `stages.py` `probs.loc[keep_ins_mask] = 1.0`) over a book WITH current_hired_col
    weights keep-ins by their observed hire, NOT the silent 1.0 bypass. The scalar
    still governs swap-ins; only the keep-in's take-up is sourced from the record."""
    frame = _frame()
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            current_hired_col="hired",
            calibration_bins=5,
        )
        .cutoff("keep all", {"score_5": 300}, direction="gte")
        .rate("Anti-fraud", base_rate=0.9)  # scalar: the silent-1.0 bypass path
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = policy.simulate(frame, method="analytical").data

    keep = d["scenario"] == "keep_in"
    # Keep-in contract follows observed hire, not the 1.0 bypass and not the 0.9 scalar.
    np.testing.assert_allclose(
        d.loc[keep, "new_approval"].to_numpy(),
        frame.loc[keep.to_numpy(), "hired"].to_numpy(),
        atol=1e-12,
    )
    assert float(d.loc[keep, "new_approval"].sum()) == pytest.approx(5.0)
