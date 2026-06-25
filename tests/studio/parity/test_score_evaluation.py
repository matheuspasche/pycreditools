import numpy as np
import pandas as pd

from pycreditools import ModelEvaluator
from pycreditools.gui import session
from pycreditools.studio.data import population_filter


def test_page_ks_matches_model_evaluator_directly_on_same_subset(sample_df, roles):
    subset = population_filter(sample_df, roles, "Contratados")
    target_col = roles.actual_default_col

    page_ks = session.compute_ks(
        subset, "parity-hash", "Contratados", tuple(roles.score_cols), target_col
    )
    expected_ks = ModelEvaluator(subset, roles.score_cols, target_col).compute_ks()

    assert page_ks.keys() == expected_ks.keys()
    for key in expected_ks:
        assert np.isclose(page_ks[key], expected_ks[key])


def test_page_ks_table_matches_model_evaluator_directly_on_same_subset(sample_df, roles):
    subset = population_filter(sample_df, roles, "Contratados")
    target_col = roles.actual_default_col

    page_table = session.compute_ks_table(
        subset, "parity-hash", "Contratados", "score_5", target_col, 10
    )
    expected_table = ModelEvaluator(subset, ["score_5"], target_col).compute_ks_table(
        "score_5", 10
    )

    pd.testing.assert_frame_equal(page_table, expected_table)
