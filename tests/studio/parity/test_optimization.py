import dataclasses

import pandas as pd

from pycreditools import optimize_cutoffs
from pycreditools.gui import session
from pycreditools.optimization import find_pareto_frontier
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import build_policy, policy_cache_key, v14_quickfill_rows


def test_session_run_optimization_matches_a_direct_optimize_cutoffs_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = dataclasses.replace(build_policy(roles, rows), score_cols=("score_5",))

    res = session.run_optimization(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), 5
    )
    expected = optimize_cutoffs(subset, policy, cutoff_steps=5)

    assert res.best_combination == expected.best_combination
    assert res.metrics == expected.metrics
    pd.testing.assert_frame_equal(res.all_results, expected.all_results)


def test_session_run_optimization_pareto_frontier_matches_find_pareto_frontier(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = dataclasses.replace(build_policy(roles, rows), score_cols=("score_5",))

    res = session.run_optimization(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), 10
    )
    expected_pareto = find_pareto_frontier(res.all_results)
    pd.testing.assert_frame_equal(res.pareto_frontier, expected_pareto)


def test_session_run_optimization_with_constraints_matches_direct_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = dataclasses.replace(build_policy(roles, rows), score_cols=("score_5",))

    res = session.run_optimization(
        subset,
        "parity-hash",
        "DEV",
        policy,
        policy_cache_key(policy),
        8,
        0.10,
        0.20,
    )
    expected = optimize_cutoffs(
        subset, policy, cutoff_steps=8, target_default_rate=0.10, min_approval_rate=0.20
    )
    assert res.best_combination == expected.best_combination
    assert res.metrics == expected.metrics
