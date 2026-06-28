from pycreditools import CreditPolicy
from pycreditools.studio import projects as studio_projects
from pycreditools.studio.models import ColumnRoles, PolicyEntry, ProjectBundle, StudioState


def _state_with_policy(sample_df, roles):
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
        policies={"v14": PolicyEntry(name="v14", policy=policy, flat_stress_factor=1.2)},
        active_policy="v14",
    )


def test_save_then_load_round_trips_roles_and_policies(tmp_path, sample_df, roles):
    state = _state_with_policy(sample_df, roles)
    bundle = studio_projects.bundle_from_state(
        state,
        "acme",
        dataset={
            "name": "sample",
            "path_or_source": "sample",
            "hash": "sample-5000-42",
            "n_rows": len(sample_df),
            "sample": {"n_applicants": 5000, "seed": 42},
        },
    )

    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("acme", tmp_path)

    assert loaded.roles == bundle.roles
    assert loaded.active_policy == "v14"
    assert loaded.dataset["sample"] == {"n_applicants": 5000, "seed": 42}

    restored_policies = studio_projects.restore_policies(loaded)
    assert restored_policies["v14"].flat_stress_factor == 1.2
    assert restored_policies["v14"].policy.to_dict() == state.policies["v14"].policy.to_dict()


def test_list_projects_returns_saved_names(tmp_path, sample_df, roles):
    state = _state_with_policy(sample_df, roles)
    bundle1 = studio_projects.bundle_from_state(state, "alpha")
    bundle2 = studio_projects.bundle_from_state(state, "beta")
    studio_projects.save_project(bundle1, tmp_path)
    studio_projects.save_project(bundle2, tmp_path)

    assert studio_projects.list_projects(tmp_path) == ["alpha", "beta"]


def test_list_projects_empty_directory_returns_empty_list(tmp_path):
    assert studio_projects.list_projects(tmp_path / "missing") == []


def test_rating_labels_round_trip(tmp_path, sample_df, roles):
    state = _state_with_policy(sample_df, roles)
    state.rating_labels = {0: "A", 1: "B"}
    bundle = studio_projects.bundle_from_state(state, "gamma")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("gamma", tmp_path)
    assert loaded.rating_labels == {0: "A", 1: "B"}


def test_scores_em_jogo_round_trip(tmp_path, sample_df, roles):
    state = _state_with_policy(sample_df, roles)
    state.scores_em_jogo = ["score_2", "score_5"]
    bundle = studio_projects.bundle_from_state(state, "delta")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("delta", tmp_path)
    assert loaded.scores_em_jogo == ["score_2", "score_5"]


def test_full_session_bundle_round_trips_every_field(tmp_path, sample_df, roles):
    """Core round-trip (#37): roles, policies, ratings and scores em jogo all restore."""
    state = _state_with_policy(sample_df, roles)
    state.rating_labels = {0: "A", 1: "B"}
    state.scores_em_jogo = ["score_2", "score_5"]
    bundle = studio_projects.bundle_from_state(state, "epsilon")

    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("epsilon", tmp_path)

    assert loaded.roles == bundle.roles
    assert loaded.active_policy == "v14"
    assert loaded.rating_labels == {0: "A", 1: "B"}
    assert loaded.scores_em_jogo == ["score_2", "score_5"]

    restored_policies = studio_projects.restore_policies(loaded)
    assert restored_policies["v14"].flat_stress_factor == 1.2
    assert restored_policies["v14"].policy.to_dict() == state.policies["v14"].policy.to_dict()


def test_bundle_with_empty_roles_round_trips(tmp_path):
    bundle = ProjectBundle(project_name="empty", roles=ColumnRoles())
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("empty", tmp_path)
    assert loaded.roles == ColumnRoles()
    assert loaded.policies == {}
