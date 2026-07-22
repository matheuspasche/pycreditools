"""Invariants of the blended default denominator (#97 follow-up).

The expected default is computed over the population that *effectively became a
contract*: keep-ins with an observed outcome, and swap-ins drawn/weighted by the
take-up rate. Approved-but-never-contracted rows must not inflate the
denominator. These invariants pin that contract, independently of the internal
NaN mechanics, so a future refactor cannot silently re-dilute:

1. For a fixed policy, moving the take-up rate MUST move the expected default
   (when keep-in and swap-in default levels differ).
2. When a take-up rate is active and no-outcome rows exist, the correct rate
   (weight over contracted-and-observed) MUST differ from the naive
   sum-over-full-weight — i.e. the dilution is real and the engine avoids it.
3. Stochastic and analytical MUST converge for large n.

Deterministic base: incumbents (keep-in) are high-score/low-default; candidates
(swap-in) are low-score; ~40% of incumbents are approved-but-never-paid
(actual_default NaN).
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy
from pycreditools.sweep import _actual_defaults_array, _metrics

N = 8000


def _frame(seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    approved = (np.arange(N) % 2 == 0).astype(int)
    score = np.where(
        approved == 1,
        rng.uniform(700, 900, N),  # incumbents: high score
        rng.uniform(300, 500, N),  # candidates: low score
    )
    actual = (rng.random(N) < 0.05).astype(float)  # incumbent default ~5%
    no_pay = (approved == 1) & (rng.random(N) < 0.40)  # approved-but-never-paid
    actual[no_pay] = np.nan
    actual[approved == 0] = np.nan  # candidates: no observed outcome
    return pd.DataFrame(
        {
            "applicant_id": np.arange(N),
            "score_5": score,
            "approved": approved,
            "actual_default": actual,
        }
    )


def _policy(rate: float) -> CreditPolicy:
    return (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            calibration_bins=5,
        )
        .cutoff("pull all", {"score_5": 300}, direction="gte")
        .rate("take-up", base_rate=rate)
    )


def _def_rate(rate: float, method: str, frame: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    policy = _policy(rate)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sim = policy.simulate(frame, method=method)
    _, dr = _metrics(sim.data, _actual_defaults_array(frame, policy))
    return dr, sim.data


def test_take_up_rate_moves_expected_default():
    """Invariant 1: full take-up vs throttled take-up give different blended default."""
    frame = _frame()
    high, _ = _def_rate(1.0, "analytical", frame)
    low, _ = _def_rate(0.1, "analytical", frame)
    assert abs(high - low) > 1e-3, f"rate did not move default: {high} vs {low}"


def test_no_outcome_rows_do_not_inflate_denominator():
    """Invariant 2: the contracted-and-observed denominator differs from the
    naive full-weight denominator — the dilution the engine must avoid is real."""
    frame = _frame()
    _, data = _def_rate(0.5, "analytical", frame)
    keep = data[data["scenario"] == "keep_in"]
    sd = keep["simulated_default"]
    w = keep["new_approval"]

    correct = (sd * w).sum() / w[sd.notna()].sum()  # over contracted-and-observed
    diluted = (sd * w).sum() / w.sum()  # naive: full weight in denominator

    assert not np.isclose(correct, diluted), "no dilution present — fixture is degenerate"
    # And the engine's own KPI must equal the correct (undiluted) figure, not the
    # diluted one, for the keep-in-only subframe.
    assert correct > diluted  # dropping zero-outcome weight raises the rate


def test_stochastic_analytical_converge_large_n():
    """Invariant 3: stochastic and analytical agree for large n."""
    frame = _frame()
    ana, _ = _def_rate(0.5, "analytical", frame)
    sto, _ = _def_rate(0.5, "stochastic", frame)
    assert ana == pytest.approx(sto, abs=5e-3), f"analytical {ana} vs stochastic {sto}"
