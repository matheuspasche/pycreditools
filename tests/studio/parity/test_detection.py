import pandas as pd

from pycreditools.studio.detection import detect_tier, validate_role_format
from pycreditools.studio.models import ColumnRoles


def test_detect_tier_a_when_vigente_score_and_approval_are_mapped():
    df = pd.DataFrame({"vigente_score": [1, 2, 3], "approved": [1, 0, 1]})
    roles = ColumnRoles(vigente_score="vigente_score", current_approval_col="approved")

    detection = detect_tier(roles, df)

    assert detection.tier == "A"
    assert detection.rationale


def test_detect_tier_b_when_only_approval_flag_is_mapped():
    df = pd.DataFrame({"approved": [1, 0, 1]})
    roles = ColumnRoles(current_approval_col="approved")

    detection = detect_tier(roles, df)

    assert detection.tier == "B"
    assert detection.rationale


def test_detect_tier_c_when_no_vigente_base_is_mapped():
    df = pd.DataFrame({"score_5": [1, 2, 3]})
    roles = ColumnRoles()

    detection = detect_tier(roles, df)

    assert detection.tier == "C"
    assert detection.rationale


def test_detect_tier_ignores_roles_pointing_at_columns_missing_from_df():
    """Stale role mappings (e.g. a reloaded project applied to a different dataset)
    must not be trusted blindly — the tier reflects what's actually in `df`."""
    df = pd.DataFrame({"approved": [1, 0, 1]})
    roles = ColumnRoles(vigente_score="vigente_score_not_in_df", current_approval_col="approved")

    detection = detect_tier(roles, df)

    assert detection.tier == "B"


def test_validate_role_format_flags_non_binary_approval_column():
    series = pd.Series(["sim", "nao", "sim"])

    warning = validate_role_format("current_approval_col", series)

    assert warning is not None
    assert "0/1" in warning


def test_validate_role_format_accepts_clean_binary_column():
    series = pd.Series([0, 1, 1, 0])

    assert validate_role_format("current_approval_col", series) is None


def test_validate_role_format_accepts_default_column_with_nan_for_non_contracted():
    series = pd.Series([0, 1, None, 1])

    assert validate_role_format("actual_default_col", series) is None


def test_validate_role_format_flags_pd_estimada_out_of_range():
    series = pd.Series([0.1, 0.5, 1.4])

    warning = validate_role_format("estimated_default_col", series)

    assert warning is not None


def test_validate_role_format_accepts_clean_pd_estimada_column():
    series = pd.Series([0.1, 0.5, 0.9])

    assert validate_role_format("estimated_default_col", series) is None


def test_validate_role_format_flags_non_numeric_vigente_score():
    series = pd.Series(["alto", "baixo", "medio"])

    warning = validate_role_format("vigente_score", series)

    assert warning is not None
