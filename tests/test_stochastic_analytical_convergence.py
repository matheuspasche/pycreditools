"""For n large enough, the STOCHASTIC simulation converges to the ANALYTICAL one.

Analytical mode computes expectations (fractional ``new_approval``, expected PD);
stochastic mode draws one realization per applicant. By the law of large numbers
the stochastic aggregates must approach the analytical ones as n grows — that is
the whole justification for reporting analytical numbers as the headline.

These tests pin that convergence at a large n across several RNG seeds (so it is
not seed-luck), with tolerances ~5x the empirically observed deltas at this n —
tight enough to catch a regression, loose enough to never flake. The pre-rate
approval funnel is deterministic, so it must match the two methods EXACTLY.
"""

import warnings

import numpy as np
import pytest

from pycreditools import CreditPolicy, generate_sample_data
from pycreditools.simulation import run_simulation

N = 60_000
DATA_SEED = 7
STOCHASTIC_SEEDS = [0, 1, 2]
# Observed at n=60k: contracted rel-delta ~6e-4, blended-default abs-delta ~1.3e-3.
CONTRACTED_REL_TOL = 0.01
DEFAULT_ABS_TOL = 0.006


def _policy() -> CreditPolicy:
    return (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            calibration_bins=10,
        )
        .cutoff("Challenger cutoff", {"score_5": 500}, direction="gte")
        .rate("Take-up", base_rate=0.9)
    )


def _aggregates(df, method, seed=None):
    if seed is not None:
        np.random.seed(seed)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        d = run_simulation(df, _policy(), method=method).data
    contracted = float(d["new_approval"].sum())
    approved_pre_rate = float((d["approved_pre_rate"] > 0).sum())
    m = d["new_approval"] > 0
    w = d.loc[m, "new_approval"]
    blended = float((d.loc[m, "simulated_default"] * w).sum() / w.sum()) if float(w.sum()) else float("nan")
    return {"contracted": contracted, "approved_pre_rate": approved_pre_rate, "blended": blended}


@pytest.fixture(scope="module")
def frame():
    return generate_sample_data(n_applicants=N, seed=DATA_SEED)


@pytest.fixture(scope="module")
def analytical(frame):
    return _aggregates(frame, "analytical")


@pytest.mark.parametrize("seed", STOCHASTIC_SEEDS)
def test_stochastic_contracted_converges(frame, analytical, seed):
    st = _aggregates(frame, "stochastic", seed=seed)
    rel = abs(st["contracted"] - analytical["contracted"]) / analytical["contracted"]
    assert rel < CONTRACTED_REL_TOL, f"seed {seed}: contracted rel-delta {rel:.4f}"


@pytest.mark.parametrize("seed", STOCHASTIC_SEEDS)
def test_stochastic_default_converges(frame, analytical, seed):
    st = _aggregates(frame, "stochastic", seed=seed)
    delta = abs(st["blended"] - analytical["blended"])
    assert delta < DEFAULT_ABS_TOL, f"seed {seed}: blended-default abs-delta {delta:.5f}"


@pytest.mark.parametrize("seed", STOCHASTIC_SEEDS)
def test_pre_rate_funnel_is_deterministic(frame, analytical, seed):
    """The funnel up to the rate stages is a boolean mask — identical in both
    methods regardless of the draw."""
    st = _aggregates(frame, "stochastic", seed=seed)
    assert st["approved_pre_rate"] == analytical["approved_pre_rate"]
