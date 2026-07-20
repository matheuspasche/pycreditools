"""RateStage observed_col + calibrate_by (issue #68).

The generic lottery stage sources its rate three ways: pure scalar, a
``variable`` multiplier, or an ``observed_col`` that reads a real 0/1 outcome
from the keep-in population. These tests pin the observed-column behaviour:

  - keep-ins take their real outcome (0/1, no draw);
  - swap-ins get a score-bin-calibrated estimate (worse bins => their rate);
  - ``calibrate_by=None`` gives swap-ins the flat observed mean;
  - the no-score / too-few-keep-ins fallbacks warn and use the flat mean;
  - ``base_rate`` and ``variable`` are ignored when ``observed_col`` is set;
  - the name heuristic is gone: a stage named "Conversao" is not special.
  - new params round-trip through to_dict/from_dict.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy
from pycreditools.stages import RateStage, Stage


def _big_df(seed=0):
    """A population with a clear take-up-falls-with-worse-score signal.

    Approved (keep-in) rows only. Good scores contract at ~0.9, bad scores at
    ~0.3, so score-bin calibration must give worse-scored swap-ins a lower rate
    than the global mean.
    """
    rng = np.random.default_rng(seed)
    n = 400
    score = rng.uniform(300, 900, n)
    # take-up probability rises with score
    p = np.clip((score - 300) / 600 * 0.6 + 0.3, 0, 1)
    hired = (rng.random(n) < p).astype(int)
    approved = np.ones(n, dtype=int)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(n),
            "score": score,
            "approved": approved,
            "hired": hired,
            "actual_default": np.zeros(n, dtype=int),
        }
    )


def _policy(df, **cal):
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        current_hired_col="hired",
        actual_default_col="actual_default",
    )
    if cal:
        p = p.with_calibration(**cal)
    return p


# ---------------------------------------------------------------------------
# keep-in real outcome
# ---------------------------------------------------------------------------


def test_keep_in_takes_real_observed_outcome():
    df = pd.DataFrame(
        {
            "applicant_id": [1, 2, 3],
            "score": [800, 750, 600],
            "approved": [1, 1, 0],
            "hired": [1.0, 0.0, 0.0],
            "actual_default": [0, 0, 0],
        }
    )
    policy = _policy(df, bins=2).rate("Conversao", base_rate=1.0, observed_col="hired")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = policy.simulate(df, method="analytical").data
    # keep-ins get their real hired value, no draw
    assert res.loc[0, "stage_0_Conversao"] == 1.0
    assert res.loc[1, "stage_0_Conversao"] == 0.0


def test_stochastic_keep_in_is_deterministic_from_column():
    df = pd.DataFrame(
        {
            "applicant_id": [1, 2],
            "score": [800, 750],
            "approved": [1, 1],
            "hired": [1, 0],
            "actual_default": [0, 0],
        }
    )
    policy = _policy(df, bins=2).rate("Conversao", base_rate=1.0, observed_col="hired")
    for _ in range(5):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = policy.simulate(df, method="stochastic").data
        assert res.loc[0, "stage_0_Conversao"] == 1
        assert res.loc[1, "stage_0_Conversao"] == 0


# ---------------------------------------------------------------------------
# swap-in calibration by score bin
# ---------------------------------------------------------------------------


def test_swap_ins_calibrated_worse_bin_gets_lower_rate():
    df = _big_df()
    # Make the lowest-score decile swap-ins (approved=0), keep the rest as keep-ins.
    thresh = np.quantile(df["score"], 0.15)
    df.loc[df["score"] < thresh, "approved"] = 0
    swap_mask = df["approved"] == 0
    keep_mask = df["approved"] == 1

    policy = _policy(df, bins=5, base="global").rate(
        "Conversao", base_rate=1.0, observed_col="hired"
    )
    res = policy.simulate(df, method="analytical").data

    swap_rate = res.loc[swap_mask, "stage_0_Conversao"].mean()
    global_mean = df.loc[keep_mask, "hired"].mean()
    # worse-scored swap-ins must sit below the global keep-in mean
    assert swap_rate < global_mean


def test_base_rate_and_variable_ignored_when_observed_col_set():
    df = _big_df()
    thresh = np.quantile(df["score"], 0.15)
    df.loc[df["score"] < thresh, "approved"] = 0

    p_ref = _policy(df, bins=5).rate("Conversao", base_rate=1.0, observed_col="hired")
    # base_rate 0.5 and a bogus variable must not change the observed result
    p_alt = _policy(df, bins=5).rate(
        "Conversao", base_rate=0.5, variable=0.123, observed_col="hired"
    )
    res_ref = p_ref.simulate(df, method="analytical").data["stage_0_Conversao"]
    res_alt = p_alt.simulate(df, method="analytical").data["stage_0_Conversao"]
    pd.testing.assert_series_equal(res_ref, res_alt)


# ---------------------------------------------------------------------------
# calibrate_by=None -> flat observed mean
# ---------------------------------------------------------------------------


def test_calibrate_by_none_gives_flat_mean_to_swap_ins():
    df = _big_df()
    thresh = np.quantile(df["score"], 0.15)
    df.loc[df["score"] < thresh, "approved"] = 0
    swap_mask = df["approved"] == 0
    keep_mask = df["approved"] == 1

    policy = _policy(df, bins=5).rate(
        "Conversao", base_rate=1.0, observed_col="hired", calibrate_by=None
    )
    res = policy.simulate(df, method="analytical").data
    flat_mean = df.loc[keep_mask, "hired"].mean()
    swap_vals = res.loc[swap_mask, "stage_0_Conversao"]
    # every swap-in gets the same flat mean, not a per-bin rate
    assert swap_vals.nunique() == 1
    assert swap_vals.iloc[0] == pytest.approx(flat_mean)


# ---------------------------------------------------------------------------
# fallbacks warn
# ---------------------------------------------------------------------------


def test_too_few_keep_ins_warns_and_falls_back_to_flat_mean():
    df = pd.DataFrame(
        {
            "applicant_id": range(10),
            "score": np.linspace(300, 900, 10),
            "approved": [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],  # 2 keep-ins < floor
            "hired": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "actual_default": [0] * 10,
        }
    )
    policy = _policy(df, bins=2).rate("Conversao", base_rate=1.0, observed_col="hired")
    with pytest.warns(UserWarning, match="keep-ins"):
        res = policy.simulate(df, method="analytical").data
    swap_vals = res.loc[df["approved"] == 0, "stage_0_Conversao"]
    assert swap_vals.nunique() == 1
    assert swap_vals.iloc[0] == pytest.approx(0.5)  # mean([1, 0])


def test_no_score_column_warns_and_falls_back():
    df = _big_df()
    thresh = np.quantile(df["score"], 0.15)
    df.loc[df["score"] < thresh, "approved"] = 0
    # policy with no score column at all
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=(),
        current_approval_col="approved",
        current_hired_col="hired",
        actual_default_col="actual_default",
    ).rate("Conversao", base_rate=1.0, observed_col="hired")
    with pytest.warns(UserWarning, match="no usable score column"):
        res = policy.simulate(df, method="analytical").data
    swap_vals = res.loc[df["approved"] == 0, "stage_0_Conversao"]
    assert swap_vals.nunique() == 1


# ---------------------------------------------------------------------------
# heuristic is dead
# ---------------------------------------------------------------------------


def test_name_conversao_is_not_special_without_observed_col():
    """A stage named "Conversao" with a hired column no longer auto-elects.

    Keep-ins get the plain 1.0 bypass; the name and the presence of "hired" are
    both ignored now that the heuristic is gone.
    """
    df = pd.DataFrame(
        {
            "applicant_id": [1, 2, 3],
            "score": [800, 750, 600],
            "approved": [1, 1, 0],
            "hired": [1.0, 0.0, 0.0],
            "actual_default": [0, 0, 0],
        }
    )
    policy = _policy(df).rate("Conversao", base_rate=1.0)
    res = policy.simulate(df, method="analytical").data
    # keep-ins bypass at 1.0 regardless of their hired value
    assert res.loc[0, "stage_0_Conversao"] == 1.0
    assert res.loc[1, "stage_0_Conversao"] == 1.0  # hired=0 but still 1.0 now


# ---------------------------------------------------------------------------
# validation + serialization
# ---------------------------------------------------------------------------


def test_invalid_calibrate_by_raises():
    with pytest.raises(ValueError, match="calibrate_by"):
        RateStage("x", base_rate=1.0, observed_col="hired", calibrate_by="decile")


def test_to_dict_from_dict_round_trip():
    stage = RateStage("Conversao", base_rate=1.0, observed_col="hired", calibrate_by="score")
    d = stage.to_dict()
    assert d["observed_col"] == "hired"
    assert d["calibrate_by"] == "score"
    restored = Stage.from_dict(d)
    assert isinstance(restored, RateStage)
    assert restored.observed_col == "hired"
    assert restored.calibrate_by == "score"


def test_from_dict_legacy_without_new_keys_defaults():
    """An old serialized rate stage (no observed_col/calibrate_by) still loads."""
    d = {"type": "rate", "name": "R", "base_rate": 0.7, "variable": None, "calibrate": False}
    restored = Stage.from_dict(d)
    assert restored.observed_col is None
    assert restored.calibrate_by == "score"
