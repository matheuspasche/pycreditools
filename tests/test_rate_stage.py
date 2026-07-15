"""RateStage as a generic lottery stage (issue #68).

A rate stage is a pass-rate on whoever reaches it -- take-up/contratação is only the
obvious example. Nothing elects a "conversion stage" any more: a stage reads the real
outcome if and only if it declares `observed_col`.

Covers:
  (a) the scalar-only stage -- no column, no data dependency;
  (b) `observed_col` + `calibrate_by="score"` -- swap-ins get their score bin's rate;
  (c) the fallback path -- warns and uses the flat observed mean, never raises;
  (d) several rate stages in one policy -- none of them is special;
  (e) the hard cut -- name heuristic, last-stage fallback, "hired" auto-detect gone;
  (f) serialization round-trip of the new params.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy, col
from pycreditools.stages import RateStage, Stage


def _df(n: int = 400, *, seed: int = 7) -> pd.DataFrame:
    """Keep-ins are the top half by score, and their take-up rises with the score."""
    rng = np.random.default_rng(seed)
    score = np.linspace(0, 1000, n)
    approved = (score >= 500).astype(int)
    # Take-up climbs from ~0.2 at the cutoff to ~0.9 at the top; 0 where not approved.
    p_hire = np.clip((score - 500) / 500 * 0.7 + 0.2, 0, 1)
    hired = np.where(approved == 1, (rng.random(n) < p_hire).astype(int), 0)
    return pd.DataFrame(
        {
            "applicant_id": np.arange(n),
            "score": score,
            "approved": approved,
            "hired": hired.astype(float),
            "actual_default": (rng.random(n) < 0.1).astype(int),
        }
    )


def _policy(df: pd.DataFrame, **kwargs) -> CreditPolicy:
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        current_hired_col="hired",
        actual_default_col="actual_default",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# (a) scalar-only stage
# ---------------------------------------------------------------------------


def test_scalar_stage_needs_no_column_at_all():
    """RateStage(base_rate=0.7) is a pure scalar: no column, no data dependency."""
    df = pd.DataFrame({"applicant_id": [1, 2, 3], "score": [10, 20, 30]})
    probs = RateStage(name="Contratação", base_rate=0.7).apply(df)
    assert probs.tolist() == [0.7, 0.7, 0.7]


def test_scalar_stage_gives_keep_ins_the_bypass():
    """No observed_col => keep-ins pass at 1.0 (take-up of a keep-in is 1.0 by
    construction of the data); only swap-ins are thinned."""
    df = _df()
    policy = _policy(df)
    probs = RateStage(name="Contratação", base_rate=0.7).apply(df, policy=policy)

    keep_ins = df["approved"] == 1
    assert (probs[keep_ins] == 1.0).all()
    assert (probs[~keep_ins] == 0.7).all()


def test_scalar_stage_stochastic_keep_ins_always_pass():
    df = _df()
    policy = _policy(df)
    outcomes = RateStage(name="Contratação", base_rate=0.5).apply(
        df, method="stochastic", policy=policy
    )
    keep_ins = df["approved"] == 1
    assert (outcomes[keep_ins] == 1).all()
    assert set(outcomes[~keep_ins].unique()) <= {0, 1}


# ---------------------------------------------------------------------------
# (b) observed_col + calibrate_by="score"
# ---------------------------------------------------------------------------


def test_observed_col_keep_ins_take_their_real_outcome():
    """Keep-ins read 0/1 straight out of observed_col -- no draw, no estimate."""
    df = _df()
    policy = _policy(df, calibration_bins=4)
    probs = RateStage(name="Contratação", base_rate=1.0, observed_col="hired").apply(
        df, policy=policy
    )
    keep_ins = df["approved"] == 1
    pd.testing.assert_series_equal(
        probs[keep_ins], df.loc[keep_ins, "hired"], check_names=False
    )


def test_observed_col_score_calibration_gives_swap_ins_their_bin_rate():
    """Swap-ins live in the worse score bins by construction, so score calibration must
    give them a lower rate than the global mean over the approved population."""
    df = _df()
    policy = _policy(df, calibration_bins=4)
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the calibration must actually run
        probs = stage.apply(df, policy=policy)

    keep_ins = df["approved"] == 1
    swap_ins = ~keep_ins
    global_mean = float(df.loc[keep_ins, "hired"].mean())

    swap_in_rate = float(probs[swap_ins].mean())
    assert swap_in_rate < global_mean, (
        "swap-ins sit in the worst score bin; the global mean would flatter them"
    )
    assert 0.0 <= swap_in_rate <= 1.0


def test_observed_col_score_calibration_is_monotone_in_the_score():
    """A take-up that rises with the score must come back out of the calibration."""
    df = _df()
    policy = _policy(df, calibration_bins=4)
    probs = RateStage(name="Contratação", base_rate=1.0, observed_col="hired").apply(
        df, policy=policy
    )
    keep_ins = df["approved"] == 1
    # Estimates are per score bin; compare the worst against the best approved bin.
    approved = df[keep_ins].assign(est=probs[keep_ins])
    worst = approved.nsmallest(40, "score")["est"].mean()
    best = approved.nlargest(40, "score")["est"].mean()
    assert best > worst


def test_observed_col_reuses_calibrated_expression():
    """observed_col + calibrate_by="score" is a named case of CalibratedExpression, not
    a second engine: the two must agree row for row on the swap-ins."""
    from pycreditools.expressions import CalibratedExpression

    df = _df()
    policy = _policy(df, calibration_bins=4)
    stage_probs = RateStage(name="Contratação", base_rate=1.0, observed_col="hired").apply(
        df, policy=policy
    )
    expected = CalibratedExpression(col("hired")).calibrate_and_eval(df, policy)

    swap_ins = df["approved"] == 0
    np.testing.assert_allclose(stage_probs[swap_ins], expected[swap_ins])


def test_base_rate_scales_the_observed_rate():
    """base_rate multiplies the estimate, so base_rate=1.0 means "as observed"."""
    df = _df()
    policy = _policy(df, calibration_bins=4)
    full = RateStage(name="C", base_rate=1.0, observed_col="hired").apply(df, policy=policy)
    half = RateStage(name="C", base_rate=0.5, observed_col="hired").apply(df, policy=policy)

    swap_ins = df["approved"] == 0
    np.testing.assert_allclose(half[swap_ins], full[swap_ins] * 0.5)
    # Keep-ins keep their real outcome regardless of base_rate.
    keep_ins = ~swap_ins
    np.testing.assert_allclose(half[keep_ins], df.loc[keep_ins, "hired"])


def test_observed_col_stochastic_keep_ins_are_deterministic():
    df = _df()
    policy = _policy(df, calibration_bins=4)
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")
    outcomes = stage.apply(df, method="stochastic", policy=policy)
    keep_ins = df["approved"] == 1
    np.testing.assert_array_equal(
        outcomes[keep_ins].to_numpy(), df.loc[keep_ins, "hired"].astype(int).to_numpy()
    )


def test_observed_col_missing_from_data_raises():
    df = _df()
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="nao_existe")
    with pytest.raises(ValueError, match="nao_existe"):
        stage.apply(df, policy=_policy(df))


def test_unknown_calibrate_by_is_rejected():
    with pytest.raises(ValueError, match="calibrate_by"):
        RateStage(name="C", base_rate=1.0, observed_col="hired", calibrate_by="rating")


# ---------------------------------------------------------------------------
# (c) the fallback path: warn, never raise
# ---------------------------------------------------------------------------


def test_calibrate_by_none_uses_the_flat_mean_without_warning():
    """calibrate_by=None is an explicit choice: flat observed mean, no warning."""
    df = _df()
    policy = _policy(df)
    stage = RateStage(name="C", base_rate=1.0, observed_col="hired", calibrate_by=None)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        probs = stage.apply(df, policy=policy)

    keep_ins = df["approved"] == 1
    expected = float(df.loc[keep_ins, "hired"].mean())
    assert probs[~keep_ins].unique().tolist() == pytest.approx([expected])


def test_fallback_warns_when_no_score_column_is_usable():
    """Tier C has no score mapped: fall back to the flat mean and warn -- never raise."""
    df = _df().drop(columns=["score"])
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),  # not present in df
        current_approval_col="approved",
        current_hired_col="hired",
        actual_default_col="actual_default",
    )
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")

    with pytest.warns(UserWarning, match="no usable score column"):
        probs = stage.apply(df, policy=policy)

    keep_ins = df["approved"] == 1
    expected = float(df.loc[keep_ins, "hired"].mean())
    assert probs[~keep_ins].unique().tolist() == pytest.approx([expected])


def test_fallback_warns_when_keep_ins_are_below_the_floor():
    """Below the min_keep_ins floor the score bins are noise: flat mean and warn."""
    df = _df(n=12)  # 6 keep-ins, under the default floor of 50
    policy = _policy(df)
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")

    with pytest.warns(UserWarning, match="minimum 50"):
        probs = stage.apply(df, policy=policy)

    assert (probs >= 0.0).all() and (probs <= 1.0).all()


def test_explicit_bins_lower_the_floor_to_five():
    """calibration_bins is an explicit choice about granularity, so the floor drops to
    5 -- same rule as the swap-in PD imputation."""
    df = _df(n=12)  # 6 keep-ins: over the floor of 5, under the default of 50
    policy = _policy(df, calibration_bins=2)
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        stage.apply(df, policy=policy)  # must not warn


def test_fallback_warns_without_an_approval_column():
    """Standalone data with no approval column: still runs, on the whole-df mean."""
    df = _df().drop(columns=["approved"])
    policy = CreditPolicy(applicant_id_col="applicant_id", score_cols=("score",))
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")

    with pytest.warns(UserWarning, match="approval column"):
        probs = stage.apply(df, policy=policy)

    assert probs.unique().tolist() == pytest.approx([float(df["hired"].mean())])


# ---------------------------------------------------------------------------
# (d) several rate stages in one policy
# ---------------------------------------------------------------------------


def test_several_rate_stages_compose_and_none_is_special():
    """Two plain rate stages: both bypass the keep-ins, both thin the swap-ins."""
    df = _df()
    policy = _policy(df, calibration_bins=4).rate("Antifraude", 0.9).rate("Contratação", 0.8)
    data = policy.simulate(df, method="analytical").data

    keep_ins = df["approved"] == 1
    assert (data.loc[keep_ins, "stage_0_Antifraude"] == 1.0).all()
    assert (data.loc[keep_ins, "stage_1_Contratação"] == 1.0).all()
    swap_probs = data.loc[~keep_ins, "new_approval"]
    np.testing.assert_allclose(swap_probs, 0.9 * 0.8)


def test_only_the_stage_with_observed_col_reads_the_outcome():
    df = _df()
    policy = (
        _policy(df, calibration_bins=4)
        .rate("Antifraude", 0.9)
        .rate("Contratação", 1.0, observed_col="hired")
    )
    data = policy.simulate(df, method="analytical").data

    keep_ins = df["approved"] == 1
    assert (data.loc[keep_ins, "stage_0_Antifraude"] == 1.0).all()
    np.testing.assert_allclose(
        data.loc[keep_ins, "stage_1_Contratação"], df.loc[keep_ins, "hired"]
    )
    # A keep-in who never contracted is out of the funnel entirely.
    np.testing.assert_allclose(data.loc[keep_ins, "new_approval"], df.loc[keep_ins, "hired"])


def test_two_observed_stages_are_independent():
    """Nothing is elected: two stages may both read a real outcome."""
    df = _df()
    df["passed_desk"] = (df["hired"] + (df["score"] > 700).astype(float)).clip(0, 1)
    policy = (
        _policy(df, calibration_bins=4)
        .rate("Mesa", 1.0, observed_col="passed_desk")
        .rate("Contratação", 1.0, observed_col="hired")
    )
    data = policy.simulate(df, method="analytical").data

    keep_ins = df["approved"] == 1
    expected = df.loc[keep_ins, "passed_desk"] * df.loc[keep_ins, "hired"]
    np.testing.assert_allclose(data.loc[keep_ins, "new_approval"], expected)


# ---------------------------------------------------------------------------
# (e) the hard cut -- issue #68
# ---------------------------------------------------------------------------


def test_a_stage_named_conversao_is_not_elected():
    """The name heuristic is gone: only observed_col makes a stage read the outcome."""
    df = _df()
    policy = _policy(df).rate("Conversao", base_rate=0.7)
    probs = policy.stages[0].apply(df, policy=policy)
    keep_ins = df["approved"] == 1
    assert (probs[keep_ins] == 1.0).all(), "name must not elect a conversion stage"


@pytest.mark.parametrize("name", ["conversao", "conversion", "hired", "take_up", "take_up_rate"])
def test_no_name_elects_a_conversion_stage(name):
    df = _df()
    policy = _policy(df).rate(name, base_rate=0.7)
    probs = policy.stages[0].apply(df, policy=policy)
    assert (probs[df["approved"] == 1] == 1.0).all()


def test_the_last_rate_stage_is_not_elected():
    """The last-RateStage fallback is gone."""
    df = _df()
    policy = _policy(df).rate("Antifraude", 0.9).rate("Formalização", 0.8)
    data = policy.simulate(df, method="analytical").data
    keep_ins = df["approved"] == 1
    assert (data.loc[keep_ins, "stage_1_Formalização"] == 1.0).all()


def test_a_hired_column_is_not_auto_detected():
    """A column literally called "hired" no longer means anything to the engine."""
    df = _df()
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).rate("Contratação", 0.7)
    probs = policy.stages[0].apply(df, policy=policy)
    assert (probs[df["approved"] == 1] == 1.0).all()


def test_calibrate_true_no_longer_implies_a_conversion_stage():
    """calibrate=True calibrates the *variable*; it does not read the outcome."""
    df = _df()
    policy = _policy(df, calibration_bins=4).rate(
        "Contratação", base_rate=1.0, variable=col("hired"), calibrate=True
    )
    probs = policy.stages[0].apply(df, policy=policy)
    keep_ins = df["approved"] == 1
    assert (probs[keep_ins] == 1.0).all(), "calibrate=True must not elect a conversion stage"


def test_legacy_take_up_rate_variable_still_runs_as_a_plain_multiplier():
    """An old policy keeps running -- variable is a multiplier, as the docstring said."""
    df = _df()
    df["take_up_rate"] = 0.6
    policy = _policy(df).rate("take_up_rate", base_rate=1.0, variable="take_up_rate")
    probs = policy.stages[0].apply(df, policy=policy)
    keep_ins = df["approved"] == 1
    assert (probs[~keep_ins] == 0.6).all()
    assert (probs[keep_ins] == 1.0).all()


def test_current_hired_col_drives_no_engine_branch():
    """Setting the column role alone changes nothing in the funnel."""
    df = _df()
    with_role = _policy(df).rate("Contratação", 0.7)
    without_role = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).rate("Contratação", 0.7)

    a = with_role.simulate(df, method="analytical").data["new_approval"]
    b = without_role.simulate(df, method="analytical").data["new_approval"]
    pd.testing.assert_series_equal(a, b)


# ---------------------------------------------------------------------------
# (f) serialization
# ---------------------------------------------------------------------------


def test_to_dict_carries_the_new_params():
    stage = RateStage(name="Contratação", base_rate=1.0, observed_col="hired")
    d = stage.to_dict()
    assert d["observed_col"] == "hired"
    assert d["calibrate_by"] == "score"


def test_round_trip_preserves_observed_col_and_calibrate_by():
    for calibrate_by in ("score", None):
        stage = RateStage(
            name="Contratação", base_rate=0.9, observed_col="hired", calibrate_by=calibrate_by
        )
        restored = Stage.from_dict(stage.to_dict())
        assert isinstance(restored, RateStage)
        assert restored.observed_col == "hired"
        assert restored.calibrate_by == calibrate_by
        assert restored.base_rate == 0.9


def test_from_dict_of_a_pre_068_payload_defaults_to_a_plain_multiplier():
    """An old serialized policy has neither key: no observed_col, so no outcome read."""
    restored = Stage.from_dict(
        {"type": "rate", "name": "Conversao", "base_rate": 0.7, "variable": None}
    )
    assert restored.observed_col is None
    assert restored.calibrate_by == "score"  # inert without observed_col


def test_policy_round_trip_keeps_the_observed_col():
    df = _df()
    policy = _policy(df).rate("Contratação", 1.0, observed_col="hired", calibrate_by=None)
    restored = CreditPolicy.from_dict(policy.to_dict())
    assert restored.stages[0].observed_col == "hired"
    assert restored.stages[0].calibrate_by is None


def test_validate_requires_the_observed_col():
    df = _df()
    policy = _policy(df).rate("Contratação", 1.0, observed_col="nao_existe")
    with pytest.raises(ValueError, match="nao_existe"):
        policy.validate(df)
