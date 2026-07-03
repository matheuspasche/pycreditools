"""Parity tests for studio/projects.py — save/load round-trips (#40).

Focus: `restore_rating_result` correctly rehydrates `state.rating_result`
after a bundle round-trip so that the recipe (and `.predict()`) are preserved.
"""

from __future__ import annotations

import pandas as pd

from pycreditools import CreditPolicy
from pycreditools.studio import projects as studio_projects
from pycreditools.studio.models import PolicyEntry, StudioState


def _state_with_rating(sample_df, roles, rating_result, rating_labels):
    policy = CreditPolicy(
        applicant_id_col=roles.applicant_id_col,
        score_cols=tuple(roles.score_cols),
        current_approval_col=roles.current_approval_col,
        actual_default_col=roles.actual_default_col,
        time_col=roles.time_col,
    )
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={"v14": PolicyEntry(name="v14", policy=policy)},
        active_policy="v14",
        rating_result=rating_result,
        rating_labels=rating_labels,
    )


def test_restore_rating_result_returns_none_when_bundle_has_no_recipe(tmp_path, sample_df, roles):
    """Bundle with no rating_result → restore returns None (no crash)."""
    state = StudioState(df_name="sample", df=sample_df, df_hash="x", roles=roles)
    bundle = studio_projects.bundle_from_state(state, "no-rating")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("no-rating", tmp_path)

    result = studio_projects.restore_rating_result(loaded)
    assert result is None


def test_restore_rating_result_recipe_survives_round_trip(
    tmp_path, sample_df, roles, rating_result, rating_labels
):
    """Bundle that contains a rating_result → recipe dict round-trips exactly."""
    state = _state_with_rating(sample_df, roles, rating_result, rating_labels)
    bundle = studio_projects.bundle_from_state(state, "with-rating")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("with-rating", tmp_path)

    restored = studio_projects.restore_rating_result(loaded)
    assert restored is not None
    assert restored.recipe.to_dict() == rating_result.recipe.to_dict()


def test_restore_rating_result_can_predict_on_new_data(
    tmp_path, sample_df, roles, rating_result, rating_labels
):
    """Restored result's .predict() yields same risk_rating column as the original."""
    state = _state_with_rating(sample_df, roles, rating_result, rating_labels)
    bundle = studio_projects.bundle_from_state(state, "predict-parity")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("predict-parity", tmp_path)

    restored = studio_projects.restore_rating_result(loaded)
    assert restored is not None

    subset = sample_df.head(200)
    original_pred = rating_result.predict(subset)["risk_rating"]
    restored_pred = restored.predict(subset)["risk_rating"]
    pd.testing.assert_series_equal(original_pred, restored_pred, check_names=False)


def test_policy_export_preserves_rating_stage_after_load(
    tmp_path, sample_df, roles, rating_result, rating_labels
):
    """Export after load still embeds the rating recipe (AC: policy exportada mantém rating)."""
    from pycreditools.studio.policy_builder import build_policy, v14_quickfill_rows

    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows, rating_recipe=rating_result.recipe)
    entry = PolicyEntry(name="v14", policy=policy, rows=rows)
    state = StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={"v14": entry},
        active_policy="v14",
        rating_result=rating_result,
        rating_labels=rating_labels,
    )

    bundle = studio_projects.bundle_from_state(state, "export-parity")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("export-parity", tmp_path)

    restored_rating = studio_projects.restore_rating_result(loaded)
    assert restored_rating is not None

    restored_policies = studio_projects.restore_policies(loaded)
    restored_entry = restored_policies["v14"]
    dep = restored_entry.policy.export(rating_recipe=restored_rating.recipe)
    assert dep.rating_recipe is not None
    assert dep.rating_recipe.to_dict() == rating_result.recipe.to_dict()
