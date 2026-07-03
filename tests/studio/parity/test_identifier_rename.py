"""TDD: rename scores_em_jogo → shortlisted_scores (#44).

Tests the core seam (data → data) for the identifier migration:
- dataclasses expose `shortlisted_scores`, not `scores_em_jogo`
- analyses module exports the English names
- projects.from_json_dict migrates a bundle saved with the old key
"""

from __future__ import annotations

import json

import pytest

from pycreditools.studio import projects as studio_projects
from pycreditools.studio.analyses import (
    MAX_SHORTLISTED_SCORES,
    get_shortlisted_scores,
    select_shortlisted_scores,
)
from pycreditools.studio.models import ProjectBundle, StudioState

# ---------------------------------------------------------------------------
# dataclass fields
# ---------------------------------------------------------------------------


def test_project_bundle_has_shortlisted_scores_field():
    bundle = ProjectBundle(project_name="x", shortlisted_scores=["score_1"])
    assert bundle.shortlisted_scores == ["score_1"]


def test_project_bundle_has_no_scores_em_jogo_field():
    with pytest.raises(TypeError):
        ProjectBundle(project_name="x", scores_em_jogo=["score_1"])  # type: ignore[call-arg]


def test_studio_state_has_shortlisted_scores_field():
    state = StudioState(shortlisted_scores=["score_2"])
    assert state.shortlisted_scores == ["score_2"]


def test_studio_state_has_no_scores_em_jogo_field():
    with pytest.raises(TypeError):
        StudioState(scores_em_jogo=["score_2"])  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# analyses API names
# ---------------------------------------------------------------------------


def test_max_shortlisted_scores_constant_exists():
    assert MAX_SHORTLISTED_SCORES == 3


def test_select_shortlisted_scores_basic():
    selected, warning = select_shortlisted_scores(["a", "b"], ["a", "b", "c"])
    assert selected == ["a", "b"]
    assert warning is None


def test_select_shortlisted_scores_caps_at_max():
    selected, warning = select_shortlisted_scores(
        ["a", "b", "c", "d"], ["a", "b", "c", "d"], max_count=3
    )
    assert selected == ["a", "b", "c"]
    assert warning is not None


def test_get_shortlisted_scores_filters_stale(roles):
    state = StudioState(roles=roles, shortlisted_scores=["score_4", "nonexistent"])
    result = get_shortlisted_scores(state)
    assert "score_4" in result
    assert "nonexistent" not in result


# ---------------------------------------------------------------------------
# migration: old key → new key
# ---------------------------------------------------------------------------


def test_from_json_dict_reads_old_scores_em_jogo_key():
    """Bundle saved under the old 'scores_em_jogo' key is transparently migrated."""
    data = {
        "name": "legacy-project",
        "scores_em_jogo": ["score_1", "score_2"],
    }
    bundle = studio_projects.from_json_dict(data)
    assert bundle.shortlisted_scores == ["score_1", "score_2"]


def test_from_json_dict_reads_new_shortlisted_scores_key():
    data = {
        "name": "new-project",
        "shortlisted_scores": ["score_3"],
    }
    bundle = studio_projects.from_json_dict(data)
    assert bundle.shortlisted_scores == ["score_3"]


def test_to_json_dict_writes_new_key(sample_df, roles):
    state = StudioState(
        df_name="sample", df=sample_df, df_hash="h", roles=roles,
        shortlisted_scores=["score_4"],
    )
    bundle = studio_projects.bundle_from_state(state, "project-x")
    d = studio_projects.to_json_dict(bundle)
    assert "shortlisted_scores" in d
    assert d["shortlisted_scores"] == ["score_4"]
    assert "scores_em_jogo" not in d


def test_round_trip_preserves_shortlisted_scores(tmp_path, sample_df, roles):
    """Save with new key, load back — value survives the round-trip."""
    state = StudioState(
        df_name="sample", df=sample_df, df_hash="h", roles=roles,
        shortlisted_scores=["score_4", "score_5"],
    )
    bundle = studio_projects.bundle_from_state(state, "rt-project")
    studio_projects.save_project(bundle, tmp_path)
    loaded = studio_projects.load_project("rt-project", tmp_path)
    assert loaded.shortlisted_scores == ["score_4", "score_5"]


def test_legacy_json_file_round_trip(tmp_path):
    """A JSON file with the old 'scores_em_jogo' key loads without error."""
    legacy = {
        "name": "legacy",
        "scores_em_jogo": ["score_1"],
        "roles": {},
        "policies": {},
    }
    (tmp_path / "legacy.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = studio_projects.load_project("legacy", tmp_path)
    assert loaded.shortlisted_scores == ["score_1"]
