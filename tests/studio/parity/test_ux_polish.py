"""UX polish parity tests — issue #36.

Core seam tests for:
- filter_pass_drop_stats: single-clause pass/drop stats for the live histogram
- population_filter_two_axes: two-axis (Período × Quem) population selector
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from pycreditools.studio.data import population_filter_two_axes
from pycreditools.studio.policy_builder import filter_pass_drop_stats  # noqa: E402

# ── filter_pass_drop_stats ─────────────────────────────────────────────────────


def test_filter_pass_drop_stats_lte_returns_correct_counts(sample_df):
    col = "vl_negativacao"
    val = 1500.0
    result = filter_pass_drop_stats(sample_df, col, "<=", val)
    mask = sample_df[col] <= val
    total = len(sample_df)
    assert result["total"] == total
    assert result["pass_count"] == int(mask.sum())
    assert result["drop_count"] == total - int(mask.sum())
    assert result["pass_frac"] == pytest.approx(float(mask.mean()))
    assert result["drop_frac"] == pytest.approx(1.0 - float(mask.mean()))


def test_filter_pass_drop_stats_gte_fractions_sum_to_one(sample_df):
    result = filter_pass_drop_stats(sample_df, "score_5", ">=", 600.0)
    assert result["pass_frac"] + result["drop_frac"] == pytest.approx(1.0)
    mask = sample_df["score_5"] >= 600.0
    assert result["pass_count"] == int(mask.sum())


def test_filter_pass_drop_stats_gt(sample_df):
    result = filter_pass_drop_stats(sample_df, "vl_vencido_scr", ">", 1000.0)
    mask = sample_df["vl_vencido_scr"] > 1000.0
    assert result["pass_count"] == int(mask.sum())


def test_filter_pass_drop_stats_lt(sample_df):
    result = filter_pass_drop_stats(sample_df, "vl_protestos", "<", 500.0)
    mask = sample_df["vl_protestos"] < 500.0
    assert result["pass_count"] == int(mask.sum())


def test_filter_pass_drop_stats_eq_bool(sample_df):
    result = filter_pass_drop_stats(sample_df, "cpf_valido", "==", True)
    mask = sample_df["cpf_valido"] == True  # noqa: E712
    assert result["pass_count"] == int(mask.sum())


def test_filter_pass_drop_stats_neq(sample_df):
    result = filter_pass_drop_stats(sample_df, "cpf_valido", "!=", True)
    mask = sample_df["cpf_valido"] != True  # noqa: E712
    assert result["pass_count"] == int(mask.sum())


def test_filter_pass_drop_stats_unknown_operator_raises(sample_df):
    with pytest.raises(ValueError, match="Operador"):
        filter_pass_drop_stats(sample_df, "score_5", "~=", 500.0)


def test_filter_pass_drop_stats_empty_df():
    df = pd.DataFrame({"x": []})
    result = filter_pass_drop_stats(df, "x", ">=", 0.0)
    assert result["total"] == 0
    assert result["pass_count"] == 0
    assert result["drop_count"] == 0
    assert result["pass_frac"] == 0.0
    assert result["drop_frac"] == 0.0


# ── population_filter_two_axes ─────────────────────────────────────────────────


def test_population_filter_two_axes_tudo_todos_returns_full_df(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "Tudo", "Todos")
    assert len(result) == len(sample_df)


def test_population_filter_two_axes_tudo_aprovados(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "Tudo", "Aprovados")
    expected = sample_df[sample_df[roles.current_approval_col] == 1]
    assert len(result) == len(expected)
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


def test_population_filter_two_axes_tudo_contratados(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "Tudo", "Contratados")
    expected = sample_df[sample_df[roles.current_hired_col] == 1]
    assert len(result) == len(expected)


def test_population_filter_two_axes_dev_todos(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "Dev", "Todos")
    expected = sample_df[sample_df[roles.time_col] < roles.oot_date]
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


def test_population_filter_two_axes_oot_todos(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "OOT", "Todos")
    expected = sample_df[sample_df[roles.time_col] >= roles.oot_date]
    pd.testing.assert_frame_equal(result.reset_index(drop=True), expected.reset_index(drop=True))


def test_population_filter_two_axes_oot_contratados(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "OOT", "Contratados")
    oot_mask = sample_df[roles.time_col] >= roles.oot_date
    hired_mask = sample_df[roles.current_hired_col] == 1
    expected = sample_df[oot_mask & hired_mask]
    assert len(result) == len(expected)


def test_population_filter_two_axes_dev_aprovados(sample_df, roles):
    result = population_filter_two_axes(sample_df, roles, "Dev", "Aprovados")
    dev_mask = sample_df[roles.time_col] < roles.oot_date
    aprov_mask = sample_df[roles.current_approval_col] == 1
    expected = sample_df[dev_mask & aprov_mask]
    assert len(result) == len(expected)


def test_population_filter_two_axes_dev_requires_time_col(sample_df, roles):
    no_time = dataclasses.replace(roles, time_col=None)
    with pytest.raises(ValueError, match="safra"):
        population_filter_two_axes(sample_df, no_time, "Dev", "Todos")


def test_population_filter_two_axes_aprovados_requires_approval_col(sample_df, roles):
    no_aprov = dataclasses.replace(roles, current_approval_col=None)
    with pytest.raises(ValueError, match="aprovação"):
        population_filter_two_axes(sample_df, no_aprov, "Tudo", "Aprovados")


def test_population_filter_two_axes_unknown_periodo_raises(sample_df, roles):
    with pytest.raises(ValueError, match="Período"):
        population_filter_two_axes(sample_df, roles, "Semana", "Todos")


def test_population_filter_two_axes_unknown_quem_raises(sample_df, roles):
    with pytest.raises(ValueError, match="Quem"):
        population_filter_two_axes(sample_df, roles, "Tudo", "Gestores")
