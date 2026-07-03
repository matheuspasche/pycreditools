import pandas as pd

from pycreditools import TradeoffAnalyzer
from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.analyses import strip_cutoff
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import build_policy, policy_cache_key, v14_quickfill_rows


def test_session_run_tradeoff_matches_a_direct_tradeoffanalyzer_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    values = (400.0, 500.0, 600.0)

    res = session.run_tradeoff(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), "score_5", values
    )
    expected = (
        TradeoffAnalyzer(strip_cutoff(policy, "score_5"))
        .vary_cutoff("score_5", list(values))
        .run(subset, parallel=False)
    )
    pd.testing.assert_frame_equal(
        res[["score_5_cutoff", "approval_rate", "default_rate"]],
        expected[["score_5_cutoff", "approval_rate", "default_rate"]],
    )


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
