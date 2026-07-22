"""Engine contract: keep-ins with no recorded outcome must NOT dilute the
blended ``overall_default_rate``.

Issue #97 (sibling of #95, which found the same defect in the validation
harness). A keep-in that is approved-but-never-hired carries ``actual_default``
= NaN. For keep-ins the engine sources ``simulated_default`` straight from
``actual_default`` (``_assign_simulated_defaults``), so that row's default is
NaN too, while its contracted weight ``new_approval`` is 1.0 (scalar-rate
bypass, #94).

The buggy ``_metrics`` did ``nan_to_num(pd_base, nan=0.0)``: the no-outcome row
contributes 0 to the weighted-default numerator but keeps its full weight in the
denominator, deflating the rate. Locked convention: no default parameter enters
over a keep-in without a recorded outcome, so such rows must leave BOTH sides of
the weighting.

Deterministic: analytical mode, no draws.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy
from pycreditools.sweep import _actual_defaults_array, _metrics


def _frame() -> pd.DataFrame:
    # 10 incumbent keep-ins. 5 observed (2 defaults -> true bad rate 2/5 = 0.40),
    # 5 approved-but-never-hired (actual_default NaN).
    n = 10
    outcome = np.array([1, 1, 0, 0, 0, np.nan, np.nan, np.nan, np.nan, np.nan], dtype=float)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(n),
            "score_5": np.linspace(300, 900, n),
            "approved": np.ones(n, dtype=int),
            "actual_default": outcome,
        }
    )


def _policy() -> CreditPolicy:
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        current_approval_col="approved",
        actual_default_col="actual_default",
        calibration_bins=5,
    ).cutoff("keep all", {"score_5": 300}, direction="gte")


def test_no_outcome_keepins_excluded_from_blended_default():
    frame = _frame()
    policy = _policy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sim = policy.simulate(frame, method="analytical")

    _, def_rate = _metrics(sim.data, _actual_defaults_array(frame, policy))

    # Denominator must exclude the 5 no-outcome keep-ins: 2 bads / 5 observed.
    assert def_rate == pytest.approx(0.40), f"diluted blended default: {def_rate} (expected 0.40)"
