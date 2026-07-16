"""Trade-off curve tests anchored on ground truth (issue #71).

The old version of this file asserted studio output against a direct
``TradeoffAnalyzer`` call — parity against the other implementation — which is
exactly what let the inverted-curve bug ship: both sides were inverted, so
parity passed. The anchor here is measured truth on the data, not another
implementation.
"""
import pandas as pd

from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import build_policy, policy_cache_key, v14_quickfill_rows


def _hf_pass_mask(subset, policy, score_col):
    """Ground truth: rows passing every non-cutoff hard filter, computed with
    plain pandas so no engine code is on both sides of the assertion."""
    from pycreditools.expressions import Expression
    from pycreditools.stages import CutoffStage, FilterStage

    mask = pd.Series(True, index=subset.index)
    for stage in policy.stages:
        if isinstance(stage, FilterStage):
            cond = stage.condition
            if isinstance(cond, Expression):
                passed = cond.eval(subset)
            elif callable(cond):
                passed = cond(subset)
            else:
                passed = subset.eval(cond)
            mask &= pd.Series(passed, index=subset.index).fillna(False).astype(bool)
        elif isinstance(stage, CutoffStage):
            for col, val in stage.cutoffs.items():
                if col == score_col:
                    continue
                if stage.direction == "gte":
                    mask &= (subset[col] >= val).fillna(False)
                else:
                    mask &= (subset[col] <= val).fillna(False)
    return mask


def test_tradeoff_approval_matches_the_measured_pass_fraction(sample_df, roles):
    """At each gte cutoff, approval_rate == fraction of rows passing the hard
    filters AND score_5 >= cutoff, measured directly on the data."""
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = [400.0, 500.0, 600.0]

    res = analyses.run_tradeoff(subset, policy, "score_5", values)
    hf_mask = _hf_pass_mask(subset, policy, "score_5")

    for _, row in res.iterrows():
        truth = (hf_mask & (subset["score_5"] >= row["Cutoff"])).mean()
        assert abs(row["approval_rate"] - truth) < 1e-9, (
            f"cutoff {row['Cutoff']}: approval {row['approval_rate']} != measured {truth}"
        )


def test_tradeoff_approval_falls_as_a_gte_cutoff_rises(sample_df, roles):
    """Raising a gte cutoff can only reject more people. The inverted curve
    (issue #71 Bug 1) reported the exact opposite."""
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = list(analyses.cutoff_range(subset, "score_5", steps=10))

    res = analyses.run_tradeoff(subset, policy, "score_5", values)
    ordered = res.sort_values("Cutoff")["approval_rate"]
    assert ordered.is_monotonic_decreasing


def test_session_run_tradeoff_matches_the_studio_analyses_wrapper_directly(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = (400.0, 500.0, 600.0)

    res = session.run_tradeoff(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), "score_5", values
    )
    expected = analyses.run_tradeoff(subset, policy, "score_5", list(values))
    pd.testing.assert_frame_equal(res, expected)


def test_session_run_tradeoff_with_stress_values_matches_a_direct_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = (400.0, 500.0)
    stress = (1.0, 1.5, 2.0)

    res = session.run_tradeoff(
        subset,
        "parity-hash",
        "DEV",
        policy,
        policy_cache_key(policy),
        "score_5",
        values,
        stress,
    )
    expected = analyses.run_tradeoff(
        subset, policy, "score_5", list(values), stress_values=list(stress)
    )
    pd.testing.assert_frame_equal(res, expected)


def test_tradeoff_scenarios_match_a_hand_picked_selection_on_real_data(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = list(analyses.cutoff_range(subset, "score_5", steps=20))

    res = analyses.run_tradeoff(subset, policy, "score_5", values)
    legacy_sim = policy.simulate(subset, method="analytical")
    legacy_kpis = analyses.policy_kpis(legacy_sim)

    scenarios = analyses.tradeoff_scenarios(
        res, legacy_kpis["approval_rate"], legacy_kpis["bad_rate"]
    )

    expected_conservative = res.loc[
        (res["approval_rate"] - legacy_kpis["approval_rate"]).abs().idxmin()
    ]
    expected_aggressive = res.loc[(res["default_rate"] - legacy_kpis["bad_rate"]).abs().idxmin()]
    assert scenarios["conservador"]["Cutoff"] == expected_conservative["Cutoff"]
    assert scenarios["agressivo"]["Cutoff"] == expected_aggressive["Cutoff"]
