from decimal import Decimal

import pandas as pd

from pycreditools.studio.detection import detect_roles, detect_tier, validate_role_format
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


def test_detect_roles_pd_as_object_dtype_is_detected():
    """PD column read from CSV arrives as object dtype (strings); must still be
    detected as estimated_default_col when all values are numeric and in [0,1]. (#45)"""
    pd_values = ["0.05", "0.12", "0.33", "0.01", "0.78"]
    df = pd.DataFrame({"estimated_default": pd_values, "score_x": list(range(100, 105))})

    roles = detect_roles(df)

    assert roles.estimated_default_col == "estimated_default"


def test_detect_roles_pd_as_decimal_dtype_is_detected():
    """PD column stored as Decimal (e.g. from a database) must be detected. (#45)"""
    pd_values = [Decimal("0.05"), Decimal("0.12"), Decimal("0.33"), Decimal("0.01"), Decimal("0.78")]  # noqa: E501
    df = pd.DataFrame({"pd": pd_values, "score_x": list(range(100, 105))})

    roles = detect_roles(df)

    assert roles.estimated_default_col == "pd"


def test_detect_roles_pd_as_int_dtype_is_not_detected():
    """PD as int (all values 0 or 1) is ambiguous — same dtype as binary flag. (#45)
    We do NOT detect integer-only columns as PD to avoid false positives."""
    df = pd.DataFrame({"pd": [0, 1, 0, 1, 0], "score_x": list(range(100, 105))})

    roles = detect_roles(df)

    assert roles.estimated_default_col is None


def test_detect_roles_id_fallback_does_not_elect_score_column():
    """When no named id column exists, the fallback must not elect a score column
    (a numeric column with high cardinality). (#45)"""
    n = 200
    df = pd.DataFrame({
        "score_novo": list(range(n)),  # unique but looks like a score
        "safra": ["2024-01"] * n,
    })

    roles = detect_roles(df)

    assert roles.applicant_id_col is None


def test_detect_roles_id_fallback_accepts_explicit_id_column():
    """Named id column must still be elected even in the presence of score columns. (#45)"""
    n = 100
    df = pd.DataFrame({
        "applicant_id": list(range(n)),
        "score_novo": list(range(n)),
    })

    roles = detect_roles(df)

    assert roles.applicant_id_col == "applicant_id"


def test_tier_a_rationale_does_not_promise_rule_reconstruction():
    """Tier A has score + flag but the studio does NOT reconstruct vigente rules.
    The rationale must describe what actually happens (swap via approval flag)
    without promising reconstruction — that is future work. (#41)"""
    df = pd.DataFrame({"vigente_score": [1, 2, 3], "approved": [1, 0, 1]})
    roles = ColumnRoles(vigente_score="vigente_score", current_approval_col="approved")

    detection = detect_tier(roles, df)

    assert detection.tier == "A"
    # The old text promised "podem ser reconstruídas" (can be reconstructed) which
    # is false — nothing reconstructs the vigente rules today.
    assert "reconstruídas" not in detection.rationale
    assert "reconstruir" not in detection.rationale.lower()
    # Must still say something meaningful about what Tier A actually enables
    assert detection.rationale
