"""Parity tests for the issue #48 cleanup — dedup, recompute, legacy_score.

All tests are pure data-in / data-out with no Streamlit dependency.
"""

from __future__ import annotations

import ast
import pathlib

import pandas as pd
import pytest

from pycreditools.studio.analyses import compare_vs_base, exposure_kpis
from pycreditools.studio.data import population_filter, population_filter_two_axes
from pycreditools.studio.detection import detect_tier
from pycreditools.studio.policy_builder import (
    build_policy,
    filter_pass_drop_stats,
    v14_quickfill_rows,
)

# ---------------------------------------------------------------------------
# 1. population_filter_two_axes reuses population_filter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "periodo_choice, pop_choice",
    [
        ("Tudo", "Todos"),
        ("Dev", "DEV"),
        ("OOT", "OOT"),
    ],
)
def test_population_filter_two_axes_periodo_matches_population_filter(
    sample_df, roles, periodo_choice, pop_choice
):
    """periodo axis must delegate to population_filter — same rows, same order."""
    result = population_filter_two_axes(sample_df, roles, periodo_choice, "Todos")
    expected = population_filter(sample_df, roles, pop_choice)
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


@pytest.mark.parametrize(
    "quem_choice, pop_choice",
    [
        ("Todos", "Todos"),
        ("Aprovados", "Aprovados"),
        ("Contratados", "Contratados"),
    ],
)
def test_population_filter_two_axes_quem_matches_population_filter(
    sample_df, roles, quem_choice, pop_choice
):
    """quem axis must delegate to population_filter — same rows, same order."""
    result = population_filter_two_axes(sample_df, roles, "Tudo", quem_choice)
    expected = population_filter(sample_df, roles, pop_choice)
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


def test_population_filter_two_axes_combined_equals_two_sequential_filters(sample_df, roles):
    """Dev + Aprovados must equal population_filter(population_filter(df, DEV), Aprovados)."""
    result = population_filter_two_axes(sample_df, roles, "Dev", "Aprovados")
    expected = population_filter(population_filter(sample_df, roles, "DEV"), roles, "Aprovados")
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


# ---------------------------------------------------------------------------
# 2. exposure_kpis accepts precomputed comparison (no redundant recompute)
# ---------------------------------------------------------------------------


def test_exposure_kpis_with_precomputed_comparison_matches_standalone(sample_df, roles):
    """exposure_kpis(comparison=...) must return identical result to the standalone call."""
    from pycreditools.gui import session

    subset = population_filter(sample_df, roles, "Contratados")
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)
    sim = session.run_policy_sim(subset, "hash-faxina", "Contratados", policy, "key")
    tier = detect_tier(roles, sim.data).tier

    standalone = exposure_kpis(sim, roles, tier)
    comparison = compare_vs_base(sim, roles, tier)
    with_precomputed = exposure_kpis(sim, roles, tier, comparison=comparison)

    assert standalone == with_precomputed


def test_exposure_kpis_with_comparison_does_not_deviate_on_tier_c(sample_df):
    """Tier-C path: exposure_kpis must return None base/delta regardless of comparison kwarg."""
    from pycreditools import generate_sample_data
    from pycreditools.gui import session
    from pycreditools.studio.detection import detect_roles
    from pycreditools.studio.models import ColumnRoles

    # Build a minimal roles with no approval col → Tier C
    df = generate_sample_data(500, seed=7)
    roles_c = detect_roles(df)
    roles_c = ColumnRoles(
        applicant_id_col=roles_c.applicant_id_col,
        score_cols=roles_c.score_cols,
        actual_default_col=roles_c.actual_default_col,
        estimated_default_col=roles_c.estimated_default_col,
        current_approval_col=None,
        current_hired_col=None,
        time_col=roles_c.time_col,
        oot_date=roles_c.oot_date,
        vigente_score=None,
    )
    rows = v14_quickfill_rows(df.columns)
    policy = build_policy(roles_c, rows)
    sim = session.run_policy_sim(df, "hash-tierc", "Todos", policy, "key-c")

    result = exposure_kpis(sim, roles_c, "C", comparison=None)
    assert result["base_bad_volume"] is None
    assert result["delta"] is None


# ---------------------------------------------------------------------------
# 3. legacy_score is not hardcoded in Score Evaluation (boundary-style)
# ---------------------------------------------------------------------------


def test_score_evaluation_page_has_no_hardcoded_legacy_score_literal():
    """'legacy_score' must not appear as a hardcoded string literal in Score Evaluation."""
    page = (
        pathlib.Path(__file__).resolve().parents[3]
        / "src"
        / "pycreditools"
        / "gui"
        / "pages"
        / "2_Score_Evaluation.py"
    )
    source = page.read_text(encoding="utf-8")
    tree = ast.parse(source)
    hardcoded = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value == "legacy_score"
    ]
    assert not hardcoded, (
        "2_Score_Evaluation.py has a hardcoded 'legacy_score' string; "
        "use resolve_reference_score(roles, ks_series) instead (ADR 0003)."
    )


# ---------------------------------------------------------------------------
# 4. filter_pass_drop_stats uses a shared operator helper (structural check)
# ---------------------------------------------------------------------------


def test_filter_pass_drop_stats_all_operators_agree_with_pandas_masks(sample_df):
    """filter_pass_drop_stats must give the same count as a direct pandas mask."""
    col = "vl_negativacao"
    threshold = 1000.0
    series = sample_df[col]

    cases = [
        (">=", series >= threshold),
        (">", series > threshold),
        ("<=", series <= threshold),
        ("<", series < threshold),
        ("==", series == threshold),
        ("!=", series != threshold),
    ]
    for op, expected_mask in cases:
        stats = filter_pass_drop_stats(sample_df, col, op, threshold)
        assert stats["pass_count"] == int(expected_mask.sum()), f"operator {op!r} mismatch"
        assert stats["drop_count"] == len(sample_df) - int(expected_mask.sum()), (
            f"operator {op!r} drop mismatch"
        )
