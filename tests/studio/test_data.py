import pandas as pd
import pytest

from pycreditools.studio.data import make_sample, population_filter
from pycreditools.studio.detection import detect_roles


def test_detect_roles_on_sample_data(sample_df):
    roles = detect_roles(sample_df)

    assert roles.applicant_id_col == "applicant_id"
    assert set(roles.score_cols) == {
        "legacy_score",
        "score_2",
        "score_3",
        "score_4",
        "score_5",
    }
    assert roles.current_approval_col == "approved"
    assert roles.actual_default_col == "actual_default"
    assert roles.current_hired_col == "hired"
    assert roles.time_col == "safra"
    assert roles.segment_col == "region"
    assert roles.estimated_default_col == "true_pd"
    assert roles.oot_date == "2025-01"


def test_detect_roles_user_can_override(sample_df):
    roles = detect_roles(sample_df)
    roles.segment_col = "score_2"
    assert roles.segment_col == "score_2"


def test_make_sample_is_deterministic():
    df1, hash1 = make_sample(1000, 7)
    df2, hash2 = make_sample(1000, 7)
    assert hash1 == hash2
    pd.testing.assert_frame_equal(df1, df2)


def test_make_sample_hash_changes_with_params():
    _, hash1 = make_sample(1000, 7)
    _, hash2 = make_sample(1000, 8)
    assert hash1 != hash2


def test_population_filter_all_returns_same_df(sample_df, roles):
    out = population_filter(sample_df, roles, "Todos")
    assert len(out) == len(sample_df)


def test_population_filter_aprovados(sample_df, roles):
    out = population_filter(sample_df, roles, "Aprovados")
    assert (out[roles.current_approval_col] == 1).all()
    assert len(out) < len(sample_df)


def test_population_filter_contratados(sample_df, roles):
    out = population_filter(sample_df, roles, "Contratados")
    assert (out[roles.current_hired_col] == 1).all()


def test_population_filter_dev_oot_split(sample_df, roles):
    dev = population_filter(sample_df, roles, "DEV")
    oot = population_filter(sample_df, roles, "OOT")
    assert (dev[roles.time_col] < roles.oot_date).all()
    assert (oot[roles.time_col] >= roles.oot_date).all()
    assert len(dev) + len(oot) == len(sample_df)


def test_population_filter_custom_mask(sample_df, roles):
    mask = sample_df["age"] > 40
    out = population_filter(sample_df, roles, "Custom", custom_mask=mask)
    assert (out["age"] > 40).all()


def test_population_filter_custom_without_mask_raises(sample_df, roles):
    with pytest.raises(ValueError, match="máscara"):
        population_filter(sample_df, roles, "Custom")


def test_population_filter_missing_role_raises(sample_df):
    from pycreditools.studio.models import ColumnRoles

    with pytest.raises(ValueError, match="aprovação"):
        population_filter(sample_df, ColumnRoles(), "Aprovados")


def test_population_filter_unknown_choice_raises(sample_df, roles):
    with pytest.raises(ValueError, match="desconhecida"):
        population_filter(sample_df, roles, "Bogus")
