import pandas as pd
import pytest

from pycreditools import CreditPolicy, col
from pycreditools.studio.policy_builder import (
    V14_HARD_FILTERS,
    build_filter_expression,
    build_policy,
    clone_rows,
    make_cutoff_row,
    make_filter_row,
    make_rate_row,
    make_stress_row,
    policy_cache_key,
    v14_quickfill_rows,
)


def test_v14_quickfill_rows_returns_one_row_per_available_column(sample_df):
    rows = v14_quickfill_rows(sample_df.columns)
    assert len(rows) == len(V14_HARD_FILTERS)
    assert all(row["type"] == "filter" for row in rows)


def test_v14_quickfill_rows_skips_missing_columns():
    rows = v14_quickfill_rows(["cpf_valido", "vl_negativacao"])
    assert len(rows) == 2
    assert {row["clauses"][0]["column"] for row in rows} == {"cpf_valido", "vl_negativacao"}


def test_build_filter_expression_matches_hand_built_mask(sample_df):
    clauses = [{"column": "vl_negativacao", "operator": "<=", "value": 1500}]
    expr = build_filter_expression(clauses)
    expected = col("vl_negativacao") <= 1500
    pd.testing.assert_series_equal(
        expr.eval(sample_df), expected.eval(sample_df), check_names=False
    )


def test_build_filter_expression_ands_multiple_clauses(sample_df):
    clauses = [
        {"column": "vl_negativacao", "operator": "<=", "value": 1500},
        {"column": "cpf_valido", "operator": "==", "value": True},
    ]
    expr = build_filter_expression(clauses)
    expected = (col("vl_negativacao") <= 1500) & (col("cpf_valido") == True)  # noqa: E712
    pd.testing.assert_series_equal(
        expr.eval(sample_df), expected.eval(sample_df), check_names=False
    )


def test_build_filter_expression_rejects_empty_clauses():
    with pytest.raises(ValueError, match="ao menos uma condição"):
        build_filter_expression([])


def test_build_filter_expression_rejects_unknown_operator():
    with pytest.raises(ValueError, match="Operador desconhecido"):
        build_filter_expression([{"column": "x", "operator": "~=", "value": 1}])


def test_build_policy_chains_filter_cutoff_rate_stress_in_row_order(roles):
    rows = [
        make_filter_row(
            name="CPF válido",
            clauses=[{"column": "cpf_valido", "operator": "==", "value": True}],
        ),
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
        make_rate_row(name="Taxa base", base_rate=0.6),
        make_stress_row(factor=1.2),
    ]
    policy = build_policy(roles, rows)
    assert isinstance(policy, CreditPolicy)
    assert [type(s).__name__ for s in policy.stages] == [
        "FilterStage",
        "CutoffStage",
        "RateStage",
    ]
    assert len(policy.stress_scenarios) == 1
    assert [s.name for s in policy.stages] == ["CPF válido", "Corte score_5", "Taxa base"]


def test_build_policy_with_no_rows_has_no_stages(roles):
    policy = build_policy(roles, [])
    assert policy.stages == ()
    assert policy.stress_scenarios == ()
    assert policy.applicant_id_col == roles.applicant_id_col
    assert tuple(policy.score_cols) == tuple(roles.score_cols)


def test_build_policy_rejects_unknown_row_type(roles):
    with pytest.raises(ValueError, match="desconhecido"):
        build_policy(roles, [{"type": "bogus"}])


def test_build_policy_to_dict_from_dict_round_trip(roles):
    rows = v14_quickfill_rows(["cpf_valido", "vl_negativacao", "vl_vencido_scr", "vl_protestos"])
    rows.append(make_stress_row(factor=1.3))
    policy = build_policy(roles, rows)
    restored = CreditPolicy.from_dict(policy.to_dict())
    assert restored.to_dict() == policy.to_dict()


def test_clone_rows_gives_fresh_ids_and_independent_nested_state():
    original = [
        make_filter_row(
            name="CPF válido",
            clauses=[{"column": "cpf_valido", "operator": "==", "value": True}],
        ),
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
    ]
    cloned = clone_rows(original)

    assert [row["id"] for row in cloned] != [row["id"] for row in original]

    cloned[0]["clauses"][0]["value"] = False
    cloned[1]["cutoffs"]["score_5"] = 999
    assert original[0]["clauses"][0]["value"] is True
    assert original[1]["cutoffs"]["score_5"] == 600


def test_policy_cache_key_is_stable_and_distinguishes_policies(roles):
    rows_a = v14_quickfill_rows(["cpf_valido"])
    rows_b = v14_quickfill_rows(["cpf_valido", "vl_negativacao"])
    policy_a = build_policy(roles, rows_a)
    policy_b = build_policy(roles, rows_b)
    assert policy_cache_key(policy_a) == policy_cache_key(build_policy(roles, rows_a))
    assert policy_cache_key(policy_a) != policy_cache_key(policy_b)
