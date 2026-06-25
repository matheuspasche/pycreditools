import numpy as np
import pandas as pd
import pytest

from pycreditools import ModelEvaluator
from pycreditools.studio.analyses import effective_n, evaluate_scores, ks_table
from pycreditools.studio.data import population_filter


@pytest.fixture
def hired_df(sample_df, roles):
    return population_filter(sample_df, roles, "Contratados")


def test_effective_n_counts_non_null_target(sample_df, roles):
    n = effective_n(sample_df, roles.actual_default_col)
    assert n == int(sample_df[roles.actual_default_col].notna().sum())
    assert n < len(sample_df)


def test_evaluate_scores_matches_model_evaluator_directly(hired_df, roles):
    result = evaluate_scores(hired_df, roles.score_cols, roles.actual_default_col)
    expected = ModelEvaluator(hired_df, roles.score_cols, roles.actual_default_col).compute_ks()
    assert result.keys() == expected.keys()
    for key in expected:
        assert np.isclose(result[key], expected[key])


def test_evaluate_scores_ranks_score_5_top_and_legacy_bottom(hired_df, roles):
    result = evaluate_scores(hired_df, roles.score_cols, roles.actual_default_col)
    ranked = sorted(result, key=result.get, reverse=True)
    assert ranked[0] == "score_5"
    assert ranked[-1] == "legacy_score"


def test_ks_table_has_expected_columns(hired_df, roles):
    table = ks_table(hired_df, "score_5", roles.actual_default_col, bins=10)
    assert list(table.columns) == [
        "Bucket",
        "Avg_Score",
        "Volume",
        "Bad_Rate",
        "Cum_Bads",
        "Cum_Goods",
        "KS",
    ]
    assert len(table) == 10


def test_ks_table_matches_model_evaluator_directly(hired_df, roles):
    table = ks_table(hired_df, "score_5", roles.actual_default_col, bins=10)
    expected = ModelEvaluator(hired_df, ["score_5"], roles.actual_default_col).compute_ks_table(
        "score_5", 10
    )
    pd.testing.assert_frame_equal(table, expected)


def test_ks_table_bad_rate_trends_up_with_risk(hired_df, roles):
    """Bucket 1 = best score; Bad_Rate should trend up (not strictly, due to sampling noise)."""
    table = ks_table(hired_df, "score_5", roles.actual_default_col, bins=10).sort_values("Bucket")
    assert table["Bad_Rate"].corr(table["Bucket"]) > 0.8
    assert table["Bad_Rate"].iloc[0] < table["Bad_Rate"].iloc[-1]
