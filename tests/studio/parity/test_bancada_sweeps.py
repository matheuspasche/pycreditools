"""Bancada live sweeps — drag-the-cutoff trade-off + aggravation game (ADR 0001,
critiques 2.3/2.7; issue #28). Folds Trade-off + Crash Test into the Bancada.
"""

import dataclasses

import pandas as pd
import pytest

from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    build_policy,
    make_cutoff_row,
    policy_cache_key,
    v14_quickfill_rows,
)


def test_tradeoff_curve_for_score_in_use_matches_run_tradeoff_oracle(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    score_col = "score_5"
    cutoff_value = float(subset[score_col].quantile(0.6))
    rows = [make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_value})]
    policy = build_policy(roles, rows)

    curve = analyses.tradeoff_curve_for_score_in_use(subset, policy, score_col, steps=15)

    expected_values = analyses.cutoff_range(subset, score_col, steps=15)
    expected = analyses.run_tradeoff(subset, policy, score_col, expected_values)
    pd.testing.assert_frame_equal(curve.drop(columns="is_current"), expected)


def test_tradeoff_curve_flags_exactly_the_row_nearest_the_policys_active_cutoff(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    score_col = "score_5"
    cutoff_value = float(subset[score_col].quantile(0.6))
    rows = [make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_value})]
    policy = build_policy(roles, rows)

    curve = analyses.tradeoff_curve_for_score_in_use(subset, policy, score_col, steps=15)

    expected_values = analyses.cutoff_range(subset, score_col, steps=15)
    nearest_expected = min(expected_values, key=lambda v: abs(v - cutoff_value))
    assert curve["is_current"].sum() == 1
    assert curve.loc[curve["is_current"], "Cutoff"].iloc[0] == pytest.approx(nearest_expected)


def test_tradeoff_curve_flags_nothing_without_an_active_cutoff_on_that_score(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    policy = build_policy(roles, [])

    curve = analyses.tradeoff_curve_for_score_in_use(subset, policy, "score_5", steps=10)

    assert not curve["is_current"].any()


def test_aggravation_game_matches_run_crash_test_and_breakeven_oracle(sample_df, roles):
    stress_roles = dataclasses.replace(roles, estimated_default_col=None)
    subset = population_filter(sample_df, stress_roles, "Todos").head(1000)
    rows = v14_quickfill_rows(subset.columns) + [
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
    ]
    policy = build_policy(stress_roles, rows)
    base_bad_rate = 0.05
    factors = [1.0, 1.5, 2.0, 3.0]

    result = analyses.aggravation_game(
        subset, policy, current_factor=1.5, base_bad_rate=base_bad_rate, factors=factors
    )

    expected_curve = analyses.run_crash_test(subset, policy, sorted(set(factors) | {1.5}))
    pd.testing.assert_frame_equal(result["curve"], expected_curve)

    expected_breakeven = analyses.breakeven_aggravation_factor(expected_curve, base_bad_rate)
    assert result["breakeven_factor"] == pytest.approx(expected_breakeven)

    idx = (expected_curve["aggravation_factor"] - 1.5).abs().idxmin()
    assert result["current_default_rate"] == pytest.approx(expected_curve.loc[idx, "default_rate"])


def test_aggravation_game_skips_breakeven_when_no_base_bad_rate_is_available(sample_df, roles):
    subset = population_filter(sample_df, roles, "Todos").head(500)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(subset, policy, current_factor=1.0, base_bad_rate=None)

    assert result["breakeven_factor"] is None
    assert result["base_bad_rate"] is None


def test_aggravation_game_default_sweep_reaches_10x(sample_df, roles):
    """Default sweep must cover up to 10× — previously capped at 5× (issue #43)."""
    subset = population_filter(sample_df, roles, "Todos").head(800)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(subset, policy, current_factor=1.0, base_bad_rate=None)

    assert result["curve"]["aggravation_factor"].max() >= 10.0


def test_aggravation_game_max_factor_configurable(sample_df, roles):
    """max_factor param sets the sweep ceiling (issue #43)."""
    subset = population_filter(sample_df, roles, "Todos").head(800)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(
        subset, policy, current_factor=1.0, base_bad_rate=None, max_factor=7.0
    )

    curve_max = result["curve"]["aggravation_factor"].max()
    assert curve_max >= 7.0
    assert curve_max < 10.0


def test_session_bancada_tradeoff_curve_matches_the_studio_analyses_wrapper_directly(
    sample_df, roles
):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = [make_cutoff_row(name="Corte", cutoffs={"score_5": 600})]
    policy = build_policy(roles, rows)

    cached = session.bancada_tradeoff_curve(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), "score_5", steps=15
    )
    expected = analyses.tradeoff_curve_for_score_in_use(subset, policy, "score_5", steps=15)
    pd.testing.assert_frame_equal(cached, expected)


def test_session_aggravation_game_matches_the_studio_analyses_wrapper_directly(sample_df, roles):
    subset = population_filter(sample_df, roles, "Todos").head(800)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    cached = session.aggravation_game(
        subset, "parity-hash", "Todos", policy, policy_cache_key(policy), 1.5, 0.05
    )
    expected = analyses.aggravation_game(subset, policy, 1.5, 0.05)
    pd.testing.assert_frame_equal(cached["curve"], expected["curve"])
    assert cached["breakeven_factor"] == pytest.approx(expected["breakeven_factor"])
    assert cached["current_default_rate"] == pytest.approx(expected["current_default_rate"])


# ── Aggravation game: estimated_default_col path (issue #49) ────────────────


def test_aggravation_game_with_estimated_pd_produces_non_flat_curve(sample_df, roles):
    """When estimated_default_col is set the curve must respond to the factor (#49)."""
    assert roles.estimated_default_col is not None, "fixture must have estimated_default_col set"
    subset = population_filter(sample_df, roles, "Todos").head(1000)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(subset, policy, current_factor=1.0, base_bad_rate=None)

    curve = result["curve"]
    assert curve["default_rate"].max() > curve["default_rate"].min(), (
        "aggravation game with estimated PD produced a flat curve — factor must scale the PD"
    )


def test_aggravation_game_with_estimated_pd_sets_flag(sample_df, roles):
    """Result must have has_estimated_pd=True when policy uses estimated_default_col (#49)."""
    assert roles.estimated_default_col is not None
    subset = population_filter(sample_df, roles, "Todos").head(500)
    policy = build_policy(roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(subset, policy, current_factor=1.0, base_bad_rate=None)

    assert result["has_estimated_pd"] is True


def test_aggravation_game_without_estimated_pd_has_flag_false(sample_df, roles):
    """Result must have has_estimated_pd=False when estimated_default_col is cleared (#49)."""
    stress_roles = dataclasses.replace(roles, estimated_default_col=None)
    subset = population_filter(sample_df, stress_roles, "Todos").head(500)
    policy = build_policy(stress_roles, v14_quickfill_rows(subset.columns))

    result = analyses.aggravation_game(subset, policy, current_factor=1.0, base_bad_rate=None)

    assert result["has_estimated_pd"] is False
