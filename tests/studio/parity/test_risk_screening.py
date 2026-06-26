import numpy as np

from pycreditools import fit_risk_segments
from pycreditools.gui import session
from pycreditools.studio.analyses import fit_groups, label_ratings_by_pd


def test_page_screen_segments_matches_the_package_function_directly(sample_df, roles):
    target_col = roles.actual_default_col
    grouping_population = sample_df.dropna(subset=[target_col])
    fitted = fit_groups(
        grouping_population,
        ["score_5"],
        target_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
    )
    labels = label_ratings_by_pd(fitted, target_col)
    population = fitted.data.copy()
    population["Rating"] = population["risk_rating"].map(labels)
    population = population.dropna(subset=[target_col, "Rating"])

    page_result = session.screen_segments(
        population,
        "parity-hash",
        "Aprovados",
        "Rating",
        ("age", "income"),
        target_col,
        10,
        "quantiles",
        False,
    )
    expected_result = fit_risk_segments(
        population, "Rating", ["age", "income"], target_col, n_bins=10, method="quantiles"
    )

    assert page_result.metrics.shape == expected_result.metrics.shape
    page_iv = page_result.metrics.groupby("variable")["iv"].sum()
    expected_iv = expected_result.metrics.groupby("variable")["iv"].sum()
    for variable in expected_iv.index:
        assert np.isclose(page_iv[variable], expected_iv[variable])
