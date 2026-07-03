import streamlit as st

from pycreditools import CreditPolicy
from pycreditools.studio.models import ColumnRoles, PolicyEntry, ProjectBundle, StudioState


def test_column_roles_defaults():
    roles = ColumnRoles()
    assert roles.applicant_id_col is None
    assert roles.score_cols == []
    assert roles.oot_date is None


def test_column_roles_round_trip():
    roles = ColumnRoles(
        applicant_id_col="id",
        score_cols=["score_1", "score_2"],
        current_approval_col="approved",
        actual_default_col="bad",
        current_hired_col="hired",
        time_col="safra",
        segment_col="region",
        estimated_default_col="pd_hat",
        oot_date="2025-01",
    )
    assert roles.score_cols == ["score_1", "score_2"]
    assert roles.oot_date == "2025-01"


def test_policy_entry_holds_live_policy():
    policy = CreditPolicy(applicant_id_col="id", score_cols=("score_1",))
    entry = PolicyEntry(name="v14", policy=policy, flat_stress_factor=1.1)
    assert entry.name == "v14"
    assert entry.policy is policy
    assert entry.flat_stress_factor == 1.1


def test_project_bundle_round_trip():
    bundle = ProjectBundle(
        project_name="acme",
        df_name="sample",
        roles=ColumnRoles(score_cols=["score_1"]),
        policies={"v14": {"applicant_id_col": "id"}},
        active_policy="v14",
        rating_recipe=None,
        rating_labels={0: "A", 1: "B"},
    )
    assert bundle.project_name == "acme"
    assert bundle.policies["v14"]["applicant_id_col"] == "id"
    assert bundle.rating_labels[0] == "A"


def test_studio_state_defaults():
    state = StudioState()
    assert state.df is None
    assert state.df_name is None
    assert isinstance(state.roles, ColumnRoles)
    assert state.policies == {}
    assert state.active_policy is None
    assert state.shortlisted_scores == []


def test_studio_state_matches_fixture(studio_state, sample_df):
    assert studio_state.df_name == "sample"
    assert studio_state.df is sample_df
    assert studio_state.policies == {}
    assert studio_state.active_policy is None


def test_get_state_creates_studio_state(monkeypatch):
    from pycreditools.gui import session

    st.session_state.clear()
    state = session.get_state()
    assert isinstance(state, StudioState)
    assert state.df is None
    assert st.session_state["studio"] is state


def test_guard_dataset_warns_and_stops_without_data(monkeypatch):
    from pycreditools.gui import session

    st.session_state.clear()
    warnings = []
    stops = []
    monkeypatch.setattr(st, "warning", lambda msg: warnings.append(msg))
    monkeypatch.setattr(st, "stop", lambda: stops.append(True))

    session.guard_dataset()

    assert warnings, "guard_dataset should warn when no dataset is loaded"
    assert stops, "guard_dataset should call st.stop() when no dataset is loaded"


def test_guard_dataset_passes_with_data(monkeypatch, sample_df):
    from pycreditools.gui import session

    st.session_state.clear()
    state = session.get_state()
    state.df = sample_df
    stops = []
    monkeypatch.setattr(st, "stop", lambda: stops.append(True))

    session.guard_dataset()

    assert not stops
