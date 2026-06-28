import pytest

from pycreditools import GroupingRecipe, fit_pairwise_risk_groups, fit_risk_groups
from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.data import population_filter


def test_page_fit_risk_groups_matches_the_package_function_directly(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col

    page_result = session.fit_risk_groups(
        subset,
        "parity-hash",
        "Aprovados",
        ("score_5",),
        target_col,
        30,
        5,
        0.01,
        1,
        None,
        "ward",
        None,
    )
    expected_result = fit_risk_groups(
        subset, ["score_5"], target_col, bins=30, max_groups=5, min_vol_ratio=0.01
    )

    assert page_result.n_groups == expected_result.n_groups
    for cluster_id in expected_result.groups["risk_rating"]:
        expected_pd = expected_result.groups.loc[
            expected_result.groups["risk_rating"] == cluster_id, "pd"
        ].iloc[0]
        page_pd = page_result.groups.loc[
            page_result.groups["risk_rating"] == cluster_id, "pd"
        ].iloc[0]
        assert page_pd == expected_pd


def test_page_fit_pairwise_risk_groups_matches_the_package_function_directly(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col

    page_results = session.fit_pairwise_risk_groups(
        subset,
        "parity-hash",
        "Aprovados",
        "score_5",
        ("score_4",),
        target_col,
        20,
        5,
        0.01,
        1,
        None,
        "ward",
        None,
    )
    expected_results = fit_pairwise_risk_groups(
        subset, "score_5", ["score_4"], target_col, bins=20, max_groups=5, min_vol_ratio=0.01
    )

    assert page_results.keys() == expected_results.keys()
    for key in expected_results:
        assert page_results[key].n_groups == expected_results[key].n_groups


def test_build_open_matrix_covers_full_grid_with_volume_and_default_rate(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col

    matrix = analyses.build_open_matrix(subset, "score_5", "score_4", target_col, bins=5)

    assert matrix.score1 == "score_5"
    assert matrix.score2 == "score_4"
    assert len(matrix.breaks1) == 6
    assert len(matrix.breaks2) == 6
    assert matrix.cells.shape[0] == 25
    assert set(matrix.cells.columns) == {"bin1", "bin2", "volume", "pd"}
    assert matrix.cells["volume"].sum() == len(subset)
    non_empty = matrix.cells[matrix.cells["volume"] > 0]
    assert non_empty["pd"].between(0, 1).all()


def test_apply_manual_grouping_merges_selected_cells_into_one_recipe_group(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col
    matrix = analyses.build_open_matrix(subset, "score_5", "score_4", target_col, bins=5)

    cell_groups = analyses.default_cell_groups(matrix)
    cell_a, cell_b = list(cell_groups)[:2]
    merged_id = cell_groups[cell_a]
    cell_groups[cell_b] = merged_id

    result = analyses.apply_manual_grouping(matrix, subset, target_col, cell_groups)

    assert isinstance(result.recipe, GroupingRecipe)
    assert result.recipe.cluster_mapping[f"{cell_a[0]}-{cell_a[1]}"] == merged_id
    assert result.recipe.cluster_mapping[f"{cell_b[0]}-{cell_b[1]}"] == merged_id
    assert result.n_groups == len(set(cell_groups.values()))


def test_apply_manual_grouping_requires_every_grid_cell_assigned(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col
    matrix = analyses.build_open_matrix(subset, "score_5", "score_4", target_col, bins=5)

    incomplete = analyses.default_cell_groups(matrix)
    incomplete.pop(next(iter(incomplete)))

    with pytest.raises(ValueError):
        analyses.apply_manual_grouping(matrix, subset, target_col, incomplete)


def test_manual_grouping_recipe_round_trips_through_engine_predict(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col
    matrix = analyses.build_open_matrix(subset, "score_5", "score_4", target_col, bins=5)
    cell_groups = analyses.default_cell_groups(matrix)

    result = analyses.apply_manual_grouping(matrix, subset, target_col, cell_groups)

    predicted = result.recipe.predict(subset)
    assert predicted["risk_rating"].notna().all()
    assert (predicted["risk_rating"] == result.data["risk_rating"]).all()


def test_recipe_to_cell_groups_decodes_the_algorithm_output_as_a_starting_point(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col

    pairwise = fit_pairwise_risk_groups(
        subset, "score_5", ["score_4"], target_col, bins=5, max_groups=5, min_vol_ratio=0.01
    )
    algo_result = pairwise["score_5_vs_score_4"]

    cell_groups = analyses.recipe_to_cell_groups(algo_result.recipe)

    assert cell_groups
    assert all(isinstance(key, tuple) and len(key) == 2 for key in cell_groups)
    assert set(cell_groups.values()) == set(algo_result.recipe.cluster_mapping.values())


def test_cell_groups_grid_round_trips_through_data_editor_shape(sample_df, roles):
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    target_col = roles.actual_default_col
    matrix = analyses.build_open_matrix(subset, "score_5", "score_4", target_col, bins=5)
    cell_groups = analyses.default_cell_groups(matrix)

    grid = analyses.cell_groups_to_grid(cell_groups, bins1=5, bins2=5)
    round_tripped = analyses.grid_to_cell_groups(grid)

    assert grid.shape == (5, 5)
    assert round_tripped == cell_groups
