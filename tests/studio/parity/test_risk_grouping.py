from pycreditools import fit_pairwise_risk_groups, fit_risk_groups
from pycreditools.gui import session
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
