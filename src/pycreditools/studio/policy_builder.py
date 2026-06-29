"""No-code policy assembly: rule rows -> `CreditPolicy` (Master §4b core).

No `streamlit` import allowed here — see `00-overview.md` §4b. Rows are plain
dicts (so they survive `st.session_state` reruns); never user-typed Python.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import uuid
from collections.abc import Iterable
from typing import Any

import pandas as pd

from pycreditools import CreditPolicy, col
from pycreditools.expressions import Expression

from .models import ColumnRoles

OPERATORS: tuple[str, ...] = (">=", ">", "<=", "<", "==", "!=")
DIRECTIONS: tuple[str, ...] = ("gte", "lte")

# The 4 v14 masterclass hard filters (Cells 3-6), injected by the quick-fill button
# when their columns exist in the loaded dataset.
V14_HARD_FILTERS: tuple[dict[str, Any], ...] = (
    {"name": "CPF válido", "column": "cpf_valido", "operator": "==", "value": True},
    {"name": "Teto de negativação", "column": "vl_negativacao", "operator": "<=", "value": 1500},
    {"name": "Teto de atraso SCR", "column": "vl_vencido_scr", "operator": "<=", "value": 3000},
    {"name": "Teto de protestos", "column": "vl_protestos", "operator": "<=", "value": 500},
)


def new_row_id() -> str:
    """A fresh unique id for a rule row (used as the widget-key namespace)."""
    return uuid.uuid4().hex


def make_filter_row(
    *, name: str, clauses: list[dict[str, Any]], row_id: str | None = None
) -> dict[str, Any]:
    """A `Filtro` row: one or more AND-ed `{column, operator, value}` clauses."""
    return {"id": row_id or new_row_id(), "type": "filter", "name": name, "clauses": clauses}


def make_cutoff_row(
    *,
    name: str,
    cutoffs: dict[str, float],
    direction: str = "gte",
    row_id: str | None = None,
) -> dict[str, Any]:
    """A `Cutoff` row: `{score_col: value, ...}` pairs plus a direction."""
    return {
        "id": row_id or new_row_id(),
        "type": "cutoff",
        "name": name,
        "cutoffs": dict(cutoffs),
        "direction": direction,
    }


def make_rate_row(
    *,
    name: str,
    base_rate: float,
    variable: str | float | None = None,
    calibrate: bool = False,
    row_id: str | None = None,
) -> dict[str, Any]:
    """A `Taxa` row: base take-up rate, optional column/constant multiplier."""
    return {
        "id": row_id or new_row_id(),
        "type": "rate",
        "name": name,
        "base_rate": base_rate,
        "variable": variable,
        "calibrate": calibrate,
    }


def make_stress_row(*, factor: float = 1.2, row_id: str | None = None) -> dict[str, Any]:
    """The (at most one) flat `AggravationStress` row."""
    return {"id": row_id or new_row_id(), "type": "stress", "factor": factor}


def v14_quickfill_rows(columns: Iterable[str]) -> list[dict[str, Any]]:
    """Rule rows for the 4 v14 hard filters, skipping any column missing from `columns`."""
    available = set(columns)
    return [
        make_filter_row(
            name=spec["name"],
            clauses=[
                {"column": spec["column"], "operator": spec["operator"], "value": spec["value"]}
            ],
        )
        for spec in V14_HARD_FILTERS
        if spec["column"] in available
    ]


def build_clause_expression(clause: dict[str, Any]) -> Expression:
    """Build a single `col(column) <op> value` `Expression` from one clause."""
    column, operator, value = clause["column"], clause["operator"], clause["value"]
    expr = col(column)
    if operator == ">=":
        return expr >= value
    if operator == ">":
        return expr > value
    if operator == "<=":
        return expr <= value
    if operator == "<":
        return expr < value
    if operator == "==":
        return expr == value
    if operator == "!=":
        return expr != value
    raise ValueError(f"Operador desconhecido: {operator}")


def build_filter_expression(clauses: list[dict[str, Any]]) -> Expression:
    """AND-combine every clause of a `Filtro` row into one `Expression`."""
    if not clauses:
        raise ValueError("Um filtro precisa de ao menos uma condição.")
    expr = build_clause_expression(clauses[0])
    for clause in clauses[1:]:
        expr = expr & build_clause_expression(clause)
    return expr


def build_policy(
    roles: ColumnRoles,
    rows: list[dict[str, Any]],
    rating_recipe: Any | None = None,
) -> CreditPolicy:
    """Assemble an immutable `CreditPolicy` by chaining builder methods in row order.

    The score-in-use is whichever score the most recent `Cutoff` row cuts on; the
    builder binds the PD calibration column to that same score so the two can never
    diverge (ADR 0003) — there is no parameter to set `calibration_score_col` on its
    own.
    """
    policy = CreditPolicy(
        applicant_id_col=roles.applicant_id_col,
        score_cols=tuple(roles.score_cols),
        current_approval_col=roles.current_approval_col,
        actual_default_col=roles.actual_default_col,
        time_col=roles.time_col,
        current_hired_col=roles.current_hired_col,
        estimated_default_col=roles.estimated_default_col,
    )
    score_in_use: str | None = None
    for row in rows:
        row_type = row["type"]
        if row_type == "filter":
            policy = policy.filter(row["name"], build_filter_expression(row["clauses"]))
        elif row_type == "cutoff":
            policy = policy.cutoff(row["name"], dict(row["cutoffs"]), row.get("direction", "gte"))
            if row["cutoffs"]:
                score_in_use = list(row["cutoffs"])[-1]
        elif row_type == "rate":
            policy = policy.rate(
                row["name"], row["base_rate"], row.get("variable"), row.get("calibrate", False)
            )
        elif row_type == "stress":
            policy = policy.stress_aggravation(row["factor"])
        else:
            raise ValueError(f"Tipo de regra desconhecido: {row_type}")
    if rating_recipe is not None:
        policy = policy.with_rating(rating_recipe)
    if score_in_use is not None:
        policy = policy.with_calibration(score_col=score_in_use)
    return policy


def legacy_cutoff_policy(
    roles: ColumnRoles,
    df: pd.DataFrame,
    score_col: str = "legacy_score",
    quantile: float = 0.78,
) -> tuple[CreditPolicy, list[dict[str, Any]]] | None:
    """A v14-style legacy-only baseline: one cutoff on `score_col` at its historical quantile.

    Returns `None` if `score_col` isn't present in `df` (mirrors `v14_quickfill_rows`).
    """
    if score_col not in df.columns:
        return None
    cutoff_value = float(df[score_col].quantile(quantile))
    rows = [make_cutoff_row(name="Corte legado", cutoffs={score_col: cutoff_value})]
    return build_policy(roles, rows), rows


def apply_cutoff_to_rows(
    rows: list[dict[str, Any]], score_col: str, value: float, direction: str = "gte"
) -> list[dict[str, Any]]:
    """Update the existing `Cutoff` row on `score_col`, or append a new one if none exists.

    Used by `apply_cutoffs_to_rows` to carry a chosen cutoff back to the Bancada.
    """
    rows = copy.deepcopy(rows)
    for row in rows:
        if row["type"] == "cutoff" and score_col in row["cutoffs"]:
            row["cutoffs"][score_col] = value
            row["direction"] = direction
            return rows
    rows.append(
        make_cutoff_row(name=f"Cutoff {score_col}", cutoffs={score_col: value}, direction=direction)
    )
    return rows


def apply_cutoffs_to_rows(
    rows: list[dict[str, Any]], cutoffs: dict[str, float], direction: str = "gte"
) -> list[dict[str, Any]]:
    """Update/append a `Cutoff` row for each `{score: value}` pair in `cutoffs`.

    Used by the Optimization page to carry a best combination back to the Bancada.
    """
    for score, value in cutoffs.items():
        rows = apply_cutoff_to_rows(rows, score, value, direction)
    return rows


def segment_cutoff_rows(
    rows: list[dict[str, Any]],
    score_col: str,
    segment_cutoffs: dict[str, float],
    direction: str = "gte",
) -> dict[str, list[dict[str, Any]]]:
    """Per-segment row variants (ADR 0006, issue #34): one `rows` copy per segment
    value, each with only `score_col`'s `Cutoff` value overridden to that segment's
    figure. Everything else (filters, rates, other cutoffs) is shared — "policy stays
    a single object with per-segment cutoff overrides, not a set of policies".
    """
    return {
        segment_value: apply_cutoff_to_rows(rows, score_col, value, direction)
        for segment_value, value in segment_cutoffs.items()
    }


def clone_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy `rows` with fresh row ids, so a duplicated policy edits independently."""
    cloned = []
    for row in rows:
        new_row = copy.deepcopy(row)
        new_row["id"] = new_row_id()
        cloned.append(new_row)
    return cloned


def policy_cache_key(policy: CreditPolicy) -> str:
    """A stable, hashable cache key for a `CreditPolicy` (its serialized `to_dict()`)."""
    return json.dumps(policy.to_dict(), sort_keys=True, default=str)


def roles_cache_key(roles: ColumnRoles) -> str:
    """A stable, hashable cache key for a `ColumnRoles` (its serialized fields)."""
    return json.dumps(dataclasses.asdict(roles), sort_keys=True, default=str)


def suggested_take_up_rate(df: pd.DataFrame, roles: ColumnRoles) -> float | None:
    """Suggested take-up rate: fraction of approved applicants who were actually hired.

    Returns ``None`` when the hired or approval column is not mapped (Tier C, etc.)
    so callers can gracefully skip the hint without crashing.
    """
    if not roles.current_approval_col or not roles.current_hired_col:
        return None
    if roles.current_approval_col not in df.columns or roles.current_hired_col not in df.columns:
        return None
    approved_mask = df[roles.current_approval_col] == 1
    if not approved_mask.any():
        return None
    return float(df.loc[approved_mask, roles.current_hired_col].mean())


def angled_rate_variable(
    df: pd.DataFrame, score_col: str, *, spread: float = 0.4
) -> Expression:
    """An Expression that gives a higher multiplier to applicants with worse (lower) scores.

    For "gte" direction policies (higher score = better), worse applicants have lower
    score values and are more likely to accept any offer ("seekers"). The multiplier
    is linearly inverse-normalized:

        multiplier = (1 + spread) - 2*spread * (score - min) / (max - min)

    So the worst-score applicant gets ``1 + spread`` and the best-score gets
    ``1 - spread``, centered at ``1.0`` at the midpoint of the observed range.
    When combined with a ``base_rate`` the engine clips the result to ``[0, 1]``.
    """
    lo = float(df[score_col].min())
    hi = float(df[score_col].max())
    span = hi - lo if hi > lo else 1.0
    # normalized ∈ [0, 1]: higher score → closer to 1
    normalized = (col(score_col) - lo) / span
    # invert: worse score (low) → higher multiplier in [1-spread, 1+spread]
    return (1.0 + spread) - (2.0 * spread) * normalized
