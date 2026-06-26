import numpy as np
import pandas as pd

from pycreditools import TradeoffAnalyzer
from pycreditools.gui import session
from pycreditools.studio.analyses import run_crash_test
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import build_policy, policy_cache_key, v14_quickfill_rows


def test_run_crash_test_matches_a_direct_tradeoffanalyzer_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    factors = np.linspace(1.0, 10.0, 10).tolist()

    result = run_crash_test(subset, policy, factors)
    expected = TradeoffAnalyzer(policy).vary_stress_aggravation(factors).run(subset, parallel=False)
    pd.testing.assert_frame_equal(result, expected)


def test_session_run_crash_test_matches_the_studio_analyses_wrapper_directly(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    rows = v14_quickfill_rows(subset.columns)
    policy = build_policy(roles, rows)
    factors = (1.0, 2.0, 3.0, 5.0)

    cached = session.run_crash_test(
        subset, "parity-hash", "DEV", policy, policy_cache_key(policy), factors
    )
    expected = run_crash_test(subset, policy, list(factors))
    pd.testing.assert_frame_equal(cached, expected)
