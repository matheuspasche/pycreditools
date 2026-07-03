import pandas as pd

from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.policy_builder import build_policy, v14_quickfill_rows


def test_session_score_batch_matches_the_studio_analyses_wrapper_directly(
    sample_df, roles, rating_result
):
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows, rating_recipe=rating_result.recipe)
    dep = policy.export(rating_recipe=rating_result.recipe)
    subset = sample_df.head(100)

    cached = session.score_batch(
        subset, "parity-file-hash", dep, analyses.deployment_cache_key(dep)
    )
    expected = analyses.score_batch(subset, dep)
    pd.testing.assert_frame_equal(cached, expected)
