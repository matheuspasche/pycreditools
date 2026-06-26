import numpy as np
import pandas as pd
import pytest

from pycreditools import ModelEvaluator, compare_policies, summarize_results
from pycreditools.studio.analyses import (
    attach_rating,
    compare_with_baseline,
    decision_preview,
    delta_table,
    effective_n,
    evaluate_scores,
    ks_table,
    quadrant_table,
    swap_in_by_rating,
    swap_in_by_segment,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    build_policy,
    legacy_cutoff_policy,
    v14_quickfill_rows,
)


@pytest.fixture
def hired_df(sample_df, roles):
    return population_filter(sample_df, roles, "Contratados")


@pytest.fixture(scope="module")
def v14_sim(sample_df, roles):
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)
    return policy.simulate(sample_df, method="analytical")


@pytest.fixture(scope="module")
def legacy_sim(sample_df, roles):
    legacy_policy, _ = legacy_cutoff_policy(roles, sample_df)
    return legacy_policy.simulate(sample_df, method="analytical")


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


def test_quadrant_table_matches_summarize_results_directly(v14_sim):
    pd.testing.assert_frame_equal(quadrant_table(v14_sim), summarize_results(v14_sim))


def test_quadrant_table_has_all_four_scenarios(v14_sim):
    table = quadrant_table(v14_sim)
    assert set(table["scenario"]) == {"keep_in", "swap_in", "swap_out", "keep_out"}


def test_attach_rating_is_a_noop_copy_without_a_rating_result(v14_sim):
    out = attach_rating(v14_sim.data, None, None)
    pd.testing.assert_frame_equal(out, v14_sim.data)
    assert out is not v14_sim.data


def test_swap_in_by_rating_without_rating_column_returns_empty_with_expected_columns(v14_sim):
    table = swap_in_by_rating(v14_sim.data, rating_col="Rating")
    assert table.empty
    assert list(table.columns) == ["Rating", "Vol_Esperado", "Vol_Pct", "Inad_Stressed"]


def test_swap_in_by_rating_matches_hand_aggregated_swap_ins(v14_sim):
    df = v14_sim.data.copy()
    df["Rating"] = pd.cut(df["score_5"], bins=3, labels=["C", "B", "A"])
    table = swap_in_by_rating(df, rating_col="Rating")

    swap_in = df[df["scenario"] == "swap_in"]
    for _, row in table.iterrows():
        group = swap_in[swap_in["Rating"] == row["Rating"]]
        expected_volume = group["new_approval"].sum()
        assert np.isclose(row["Vol_Esperado"], expected_volume)
        expected_bad = (group["simulated_default"] * group["new_approval"]).sum() / expected_volume
        assert np.isclose(row["Inad_Stressed"], expected_bad)
    assert np.isclose(table["Vol_Pct"].sum(), 1.0)


def test_swap_in_by_segment_crosstabs_volume_by_rating_and_segment(v14_sim, roles):
    df = v14_sim.data.copy()
    df["Rating"] = pd.cut(df["score_5"], bins=3, labels=["C", "B", "A"])
    crosstab = swap_in_by_segment(df, "Rating", roles.segment_col)

    swap_in = df[df["scenario"] == "swap_in"]
    total_expected = swap_in["new_approval"].sum()
    assert np.isclose(crosstab.to_numpy().sum(), total_expected)


def test_swap_in_by_segment_missing_columns_returns_empty(v14_sim):
    assert swap_in_by_segment(v14_sim.data, "Rating", "no_such_column").empty


def test_compare_with_baseline_matches_compare_policies_directly(v14_sim, legacy_sim):
    result = compare_with_baseline(v14_sim, legacy_sim)
    expected = compare_policies(v14_sim, legacy_sim)
    pd.testing.assert_frame_equal(result["metrics"], expected["metrics"])
    pd.testing.assert_frame_equal(result["swaps"], expected["swaps"])
    assert result["ratio"] == expected["ratio"] or (
        pd.isna(result["ratio"]) and pd.isna(expected["ratio"])
    )


def test_delta_table_matches_hand_computed_pl_delta(v14_sim, legacy_sim):
    table = delta_table(v14_sim, legacy_sim)
    assert list(table["Metric"]) == [
        "Taxa de aprovação",
        "Inadimplência esperada",
        "Volume contratado esperado",
    ]

    df_old = legacy_sim.data
    approval_old = df_old["approved"].mean()
    volume_old = df_old["hired"].sum() if "hired" in df_old.columns else df_old["approved"].sum()
    bad_old = (df_old["actual_default"] * df_old["hired"]).sum() / volume_old

    df_new = v14_sim.data
    new_col = "approved_pre_rate" if "approved_pre_rate" in df_new.columns else "new_approval"
    approval_new = df_new[new_col].mean()
    volume_new = df_new["new_approval"].sum()
    bad_new = (df_new["simulated_default"] * df_new["new_approval"]).sum() / volume_new

    row = table.set_index("Metric")
    assert np.isclose(row.loc["Taxa de aprovação", "Legacy"], approval_old)
    assert np.isclose(row.loc["Taxa de aprovação", "New"], approval_new)
    assert np.isclose(row.loc["Inadimplência esperada", "Legacy"], bad_old)
    assert np.isclose(row.loc["Inadimplência esperada", "New"], bad_new)
    assert np.isclose(row.loc["Volume contratado esperado", "Legacy"], volume_old)
    assert np.isclose(row.loc["Volume contratado esperado", "New"], volume_new)


def test_decision_preview_matches_to_decision_dataframe_head(v14_sim):
    preview = decision_preview(v14_sim, n=20)
    expected = v14_sim.to_decision_dataframe(None, None).head(20)
    pd.testing.assert_frame_equal(preview, expected)
    assert len(preview) == 20
