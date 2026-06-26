import dataclasses

import numpy as np
import pandas as pd
import pytest

from pycreditools import (
    GroupingRecipe,
    ModelEvaluator,
    TradeoffAnalyzer,
    compare_policies,
    fit_pairwise_risk_groups,
    fit_risk_groups,
    fit_risk_segments,
    optimize_cutoffs,
    summarize_results,
)
from pycreditools.optimization import find_pareto_frontier
from pycreditools.studio.analyses import (
    attach_rating,
    clamp_max_groups,
    compare_with_baseline,
    cutoff_range,
    decision_preview,
    delta_table,
    effective_n,
    evaluate_scores,
    existing_rating_columns,
    find_equivalent,
    fit_groups,
    fit_pairwise_groups,
    groups_table,
    ks_table,
    label_ratings_by_pd,
    optimization_grid_size,
    quadrant_table,
    recipe_breaks_table,
    run_optimization,
    run_tradeoff,
    screen_segments,
    screening_boundaries_table,
    screening_candidate_columns,
    screening_detail_table,
    screening_heatmap_table,
    screening_iv_table,
    screening_low_coverage_variables,
    stability_table,
    strip_cutoff,
    swap_in_by_rating,
    swap_in_by_segment,
    tradeoff_scenarios,
    vintage_stability_table,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    build_policy,
    legacy_cutoff_policy,
    make_cutoff_row,
    make_rate_row,
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


def test_cutoff_range_returns_increasing_ints_within_p5_p95(sample_df):
    values = cutoff_range(sample_df, "score_5", steps=10)
    assert len(values) == 10
    assert values == sorted(values)
    assert all(isinstance(v, int) for v in values)
    assert values[0] == int(sample_df["score_5"].quantile(0.05))
    assert values[-1] == int(sample_df["score_5"].quantile(0.95))


def test_cutoff_range_low_variance_falls_back_to_a_single_median_point():
    df = pd.DataFrame({"score": [500] * 100})
    assert cutoff_range(df, "score", steps=10) == [500]


def test_strip_cutoff_removes_only_the_matching_score_keeps_others(roles):
    rows = [make_cutoff_row(name="Corte", cutoffs={"score_3": 400, "score_5": 600})]
    policy = build_policy(roles, rows)
    stripped = strip_cutoff(policy, "score_5")
    assert len(stripped.stages) == 1
    assert stripped.stages[0].cutoffs == {"score_3": 400}


def test_strip_cutoff_drops_the_stage_entirely_when_no_columns_remain(roles):
    rows = [make_cutoff_row(name="Corte", cutoffs={"score_5": 600})]
    policy = build_policy(roles, rows)
    stripped = strip_cutoff(policy, "score_5")
    assert stripped.stages == ()


def test_strip_cutoff_is_a_noop_when_the_score_has_no_cutoff_stage(roles):
    rows = v14_quickfill_rows(["cpf_valido"])
    policy = build_policy(roles, rows)
    stripped = strip_cutoff(policy, "score_5")
    assert [s.name for s in stripped.stages] == [s.name for s in policy.stages]


def test_tradeoff_scenarios_matches_v14_cell12_selection_logic():
    res = pd.DataFrame(
        {
            "Cutoff": [100, 200, 300, 400, 500],
            "approval_rate": [0.9, 0.7, 0.5, 0.3, 0.1],
            "default_rate": [0.01, 0.02, 0.05, 0.08, 0.12],
        }
    )
    scenarios = tradeoff_scenarios(res, legacy_approval_rate=0.52, legacy_bad_rate=0.079)
    assert scenarios["conservador"]["Cutoff"] == 300  # closest approval_rate (0.5) to 0.52
    assert scenarios["agressivo"]["Cutoff"] == 400  # closest default_rate (0.08) to 0.079
    assert scenarios["neutro"]["Cutoff"] == 300  # closest to midpoint (300+400)/2 = 350


@pytest.fixture(scope="module")
def small_df(sample_df):
    return sample_df.head(800)


@pytest.fixture(scope="module")
def hf_policy(roles, small_df):
    return build_policy(roles, v14_quickfill_rows(small_df.columns))


def test_run_tradeoff_tags_score_model_and_a_unified_cutoff_column(hf_policy, small_df):
    values = [400, 500, 600]
    res = run_tradeoff(small_df, hf_policy, "score_5", values)
    assert (res["Score_Model"] == "score_5").all()
    assert list(res["Cutoff"]) == list(res["score_5_cutoff"])
    assert len(res) == len(values)
    assert {"approval_rate", "default_rate"}.issubset(res.columns)


def test_run_tradeoff_strips_the_swept_scores_existing_cutoff(roles, small_df):
    rows = v14_quickfill_rows(small_df.columns)
    policy_without = build_policy(roles, rows)
    policy_with = build_policy(
        roles, [*rows, make_cutoff_row(name="Corte antigo", cutoffs={"score_5": 999})]
    )

    values = [400, 500, 600]
    res_without = run_tradeoff(small_df, policy_without, "score_5", values)
    res_with = run_tradeoff(small_df, policy_with, "score_5", values)
    pd.testing.assert_frame_equal(
        res_without[["approval_rate", "default_rate"]],
        res_with[["approval_rate", "default_rate"]],
    )


def test_run_tradeoff_with_stress_values_builds_a_grid(hf_policy, small_df):
    res = run_tradeoff(small_df, hf_policy, "score_5", [400, 500], stress_values=[1.0, 1.5, 2.0])
    assert len(res) == 2 * 3
    assert set(res["aggravation_factor"]) == {1.0, 1.5, 2.0}


def test_run_tradeoff_with_rate_stage_builds_a_grid(roles, small_df):
    rows = [*v14_quickfill_rows(small_df.columns), make_rate_row(name="Taxa base", base_rate=0.5)]
    policy = build_policy(roles, rows)
    res = run_tradeoff(
        small_df, policy, "score_5", [400, 500], rate_stage=("Taxa base", [0.3, 0.7])
    )
    assert len(res) == 2 * 2


def test_run_tradeoff_matches_a_direct_tradeoffanalyzer_call_on_the_stripped_policy(
    hf_policy, small_df
):
    values = [400, 500, 600]
    res = run_tradeoff(small_df, hf_policy, "score_5", values)
    expected = (
        TradeoffAnalyzer(strip_cutoff(hf_policy, "score_5"))
        .vary_cutoff("score_5", values)
        .run(small_df, parallel=False)
    )
    pd.testing.assert_frame_equal(
        res[["score_5_cutoff", "approval_rate", "default_rate"]],
        expected[["score_5_cutoff", "approval_rate", "default_rate"]],
    )


@pytest.fixture(scope="module")
def single_score_policy(hf_policy):
    return dataclasses.replace(hf_policy, score_cols=("score_5",))


def test_optimization_grid_size_is_steps_power_n_scores():
    assert optimization_grid_size(["score_5"], 10) == 10
    assert optimization_grid_size(["score_4", "score_5"], 10) == 100
    assert optimization_grid_size([], 10) == 1


def test_run_optimization_matches_a_direct_optimize_cutoffs_call(single_score_policy, small_df):
    result = run_optimization(small_df, single_score_policy, cutoff_steps=5)
    expected = optimize_cutoffs(small_df, single_score_policy, cutoff_steps=5)
    assert result.best_combination == expected.best_combination
    assert result.metrics == expected.metrics
    pd.testing.assert_frame_equal(result.all_results, expected.all_results)


def test_run_optimization_best_combination_respects_constraints_when_feasible(
    single_score_policy, small_df
):
    result = run_optimization(
        small_df,
        single_score_policy,
        cutoff_steps=10,
        target_default_rate=0.05,
        min_approval_rate=0.1,
    )
    if result.metrics["constraints_met"]:
        assert result.metrics["overall_default_rate"] <= 0.05
        assert result.metrics["overall_approval_rate"] >= 0.1


def test_run_optimization_pareto_frontier_matches_find_pareto_frontier_on_all_results(
    single_score_policy, small_df
):
    result = run_optimization(small_df, single_score_policy, cutoff_steps=10)
    expected_pareto = find_pareto_frontier(result.all_results)
    pd.testing.assert_frame_equal(result.pareto_frontier, expected_pareto)


def test_find_equivalent_matches_the_optimizationresult_method_directly(
    single_score_policy, small_df
):
    result = run_optimization(small_df, single_score_policy, cutoff_steps=10)
    matches = find_equivalent(
        result, target_metric="approval_rate", target_value=0.3, tolerance=0.5
    )
    expected = result.find_equivalent(
        target_metric="approval_rate", target_value=0.3, tolerance=0.5
    )
    pd.testing.assert_frame_equal(matches, expected)


# --- PRD 08: Risk Grouping & Ratings ---------------------------------------


@pytest.fixture(scope="module")
def grouping_population(sample_df, roles):
    return population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )


def test_clamp_max_groups_caps_at_bins():
    assert clamp_max_groups(10, 5) == 5
    assert clamp_max_groups(3, 5) == 3


def test_fit_groups_matches_a_direct_fit_risk_groups_call(grouping_population, roles):
    result = fit_groups(
        grouping_population,
        ["score_5"],
        roles.actual_default_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
    )
    expected = fit_risk_groups(
        grouping_population,
        ["score_5"],
        roles.actual_default_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
    )
    assert result.n_groups == expected.n_groups
    pd.testing.assert_frame_equal(result.groups, expected.groups)


def test_fit_groups_clamps_an_oversized_max_groups(grouping_population, roles):
    result = fit_groups(
        grouping_population, ["score_5"], roles.actual_default_col, bins=10, max_groups=50
    )
    assert result.n_groups <= 10


def test_fit_pairwise_groups_matches_a_direct_call(grouping_population, roles):
    result = fit_pairwise_groups(
        grouping_population,
        "score_5",
        ["score_4"],
        roles.actual_default_col,
        bins=20,
        max_groups=5,
        min_vol_ratio=0.01,
    )
    expected = fit_pairwise_risk_groups(
        grouping_population,
        "score_5",
        ["score_4"],
        roles.actual_default_col,
        bins=20,
        max_groups=5,
        min_vol_ratio=0.01,
    )
    assert result.keys() == expected.keys()
    for key in expected:
        assert result[key].n_groups == expected[key].n_groups


@pytest.fixture(scope="module")
def fitted_result(grouping_population, roles):
    return fit_groups(
        grouping_population,
        ["score_5"],
        roles.actual_default_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
    )


@pytest.fixture(scope="module")
def fitted_result_with_oot(grouping_population, roles):
    return fit_groups(
        grouping_population,
        ["score_5"],
        roles.actual_default_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
        time_col=roles.time_col,
        oot_date=roles.oot_date,
    )


def test_label_ratings_by_pd_sorts_ascending_pd_to_a_through_e(fitted_result, roles):
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    cluster_pd = fitted_result.data.groupby("risk_rating")[roles.actual_default_col].mean()
    ordered_clusters = cluster_pd.sort_values().index.tolist()
    expected = {int(cid): letter for cid, letter in zip(ordered_clusters, "ABCDE")}
    assert labels == expected

    # PD must increase monotonically when read in label order A -> E.
    pd_by_label = {labels[int(cid)]: pd_value for cid, pd_value in cluster_pd.items()}
    ordered_pd = [pd_by_label[letter] for letter in sorted(pd_by_label)]
    assert ordered_pd == sorted(ordered_pd)


def test_groups_table_pd_matches_a_direct_groupby_on_result_data(fitted_result, roles):
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    table = groups_table(fitted_result, labels)

    direct = fitted_result.data.groupby("risk_rating")[roles.actual_default_col].mean()
    for cluster_id, label in labels.items():
        expected_pd = direct.loc[cluster_id]
        actual_pd = table.loc[table["Rating"] == label, "pd"].iloc[0]
        assert np.isclose(actual_pd, expected_pd)

    assert list(table["Rating"]) == sorted(table["Rating"])


def test_stability_table_empty_without_an_oot_split(fitted_result, roles):
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    # fitted_result has no time_col/oot_date -> report has only the "Train" period.
    table = stability_table(fitted_result, labels)
    assert "PD_OOT" not in table.columns


def test_stability_table_has_dev_oot_columns_and_diverge_flag(fitted_result_with_oot, roles):
    labels = label_ratings_by_pd(fitted_result_with_oot, roles.actual_default_col)
    table = stability_table(fitted_result_with_oot, labels)
    assert {"PD_Train", "PD_OOT", "PD_Delta", "Diverge"}.issubset(table.columns)
    assert (table["PD_Delta"] == (table["PD_OOT"] - table["PD_Train"])).all()


def test_vintage_stability_table_matches_a_direct_groupby(fitted_result, roles):
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    table = vintage_stability_table(
        fitted_result, roles.time_col, roles.actual_default_col, labels
    )
    assert list(table.columns) == [roles.time_col, "Rating", "bad_rate"]

    work = fitted_result.data.copy()
    work["Rating"] = work["risk_rating"].map(labels)
    expected = (
        work.groupby([roles.time_col, "Rating"])[roles.actual_default_col].mean().reset_index()
    )
    assert np.isclose(table["bad_rate"].sum(), expected[roles.actual_default_col].sum())


def test_recipe_breaks_table_score_ranges_are_monotonic_with_rating(fitted_result, roles):
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    table = recipe_breaks_table(fitted_result, labels)
    assert list(table["Rating"]) == sorted(table["Rating"])
    assert {"score_5_min", "score_5_max"}.issubset(table.columns)


def test_fitted_recipe_round_trips_via_to_dict_from_dict(fitted_result):
    recipe = fitted_result.recipe
    restored = GroupingRecipe.from_dict(recipe.to_dict())
    assert restored.to_dict() == recipe.to_dict()


# --- Risk Screening (PRD 09) ---------------------------------------------------


def test_screening_candidate_columns_excludes_ids_scores_and_role_columns(sample_df, roles):
    candidates = screening_candidate_columns(sample_df, roles)
    assert roles.applicant_id_col not in candidates
    assert roles.actual_default_col not in candidates
    assert roles.current_approval_col not in candidates
    assert roles.current_hired_col not in candidates
    assert roles.time_col not in candidates
    assert roles.estimated_default_col not in candidates
    for score_col in roles.score_cols:
        assert score_col not in candidates
    assert "age" in candidates
    assert "income" in candidates


def test_existing_rating_columns_returns_low_cardinality_non_float_columns(sample_df):
    columns = existing_rating_columns(sample_df)
    assert "region" in columns
    assert "applicant_id" not in columns  # unique id, too high cardinality
    assert "income" not in columns  # high-cardinality numeric
    assert "true_pd" not in columns  # float dtype is excluded outright


@pytest.fixture(scope="module")
def screening_population(fitted_result, roles):
    """`fitted_result`'s population with A..E `Rating` attached (already has `risk_rating`)."""
    labels = label_ratings_by_pd(fitted_result, roles.actual_default_col)
    tagged = fitted_result.data.copy()
    tagged["Rating"] = tagged["risk_rating"].map(labels)
    return tagged.dropna(subset=[roles.actual_default_col, "Rating"])


def test_screen_segments_matches_a_direct_fit_risk_segments_call(screening_population, roles):
    result = screen_segments(
        screening_population, "Rating", ["age", "income"], roles.actual_default_col, n_bins=10
    )
    expected = fit_risk_segments(
        screening_population, "Rating", ["age", "income"], roles.actual_default_col, n_bins=10
    )
    pd.testing.assert_frame_equal(result.metrics, expected.metrics)
    assert result.recipes.keys() == expected.recipes.keys()


@pytest.fixture(scope="module")
def screening_result(screening_population, roles):
    return screen_segments(
        screening_population, "Rating", ["age", "income"], roles.actual_default_col, n_bins=10
    )


def test_screening_iv_table_sums_iv_across_tiers_and_sorts_descending(screening_result):
    table = screening_iv_table(screening_result)
    assert list(table.columns) == ["variable", "iv", "volume"]
    assert set(table["variable"]) == {"age", "income"}
    assert (table["iv"].diff().dropna() <= 0).all()

    expected_age_iv = screening_result.metrics.loc[
        screening_result.metrics["variable"] == "age", "iv"
    ].sum()
    assert np.isclose(table.loc[table["variable"] == "age", "iv"].iloc[0], expected_age_iv)


def test_screening_iv_table_empty_metrics_returns_empty_with_expected_columns():
    empty = type(
        "EmptyResult",
        (),
        {"metrics": pd.DataFrame(columns=["variable", "iv", "tier_vol"])},
    )()
    table = screening_iv_table(empty)
    assert table.empty
    assert list(table.columns) == ["variable", "iv", "volume"]


def test_screening_low_coverage_variables_flags_a_variable_with_too_few_unique_values(
    screening_population, roles
):
    constant_population = screening_population.copy()
    constant_population["constant_col"] = 1.0
    result = screen_segments(
        constant_population,
        "Rating",
        ["age", "constant_col"],
        roles.actual_default_col,
        n_bins=10,
    )
    flagged = screening_low_coverage_variables(result, ["age", "constant_col"])
    assert flagged == ["constant_col"]


def test_screening_detail_table_matches_a_direct_predict_groupby(
    screening_result, screening_population, roles
):
    detail = screening_detail_table(
        screening_result, screening_population, "income", "Rating", roles.actual_default_col
    )
    assert list(detail.columns) == ["Rating", "Subsegmento", "bad_rate", "volume"]
    assert detail["volume"].sum() <= len(screening_population)

    predicted = screening_result.predict(screening_population, "income", "Rating")
    expected = (
        predicted.dropna(subset=[roles.actual_default_col, "income_sub"])
        .groupby(["Rating", "income_sub"])[roles.actual_default_col]
        .mean()
    )
    assert np.isclose(detail["bad_rate"].sum(), expected.sum())


def test_screening_heatmap_table_pivots_to_tier_by_subsegment_matrix(
    screening_result, screening_population, roles
):
    detail = screening_detail_table(
        screening_result, screening_population, "income", "Rating", roles.actual_default_col
    )
    pivoted = screening_heatmap_table(detail, "Rating")
    assert pivoted.index.name == "Rating"
    assert pivoted.columns.name == "Subsegmento"
    assert set(pivoted.index) == set(detail["Rating"])


def test_screening_heatmap_table_empty_detail_returns_empty_frame():
    assert screening_heatmap_table(pd.DataFrame(), "Rating").empty


def test_screening_boundaries_table_ranges_cover_the_full_variable_span(
    screening_result, screening_population
):
    boundaries = screening_boundaries_table(screening_result, "income")
    assert list(boundaries.columns) == ["Tier", "Subsegmento", "Min", "Max"]
    for tier, group in boundaries.groupby("Tier"):
        ordered = group.sort_values("Subsegmento")
        assert (ordered["Min"].values[1:] >= ordered["Min"].values[:-1]).all()
        tier_values = screening_population.loc[
            screening_population["Rating"] == tier, "income"
        ]
        assert ordered["Min"].min() <= tier_values.min()
        assert ordered["Max"].max() >= tier_values.max()


def test_screening_boundaries_table_unknown_variable_returns_empty_with_expected_columns(
    screening_result,
):
    table = screening_boundaries_table(screening_result, "not_a_real_variable")
    assert table.empty
    assert list(table.columns) == ["Tier", "Subsegmento", "Min", "Max"]
