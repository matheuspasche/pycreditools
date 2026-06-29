"""The no-code policy management + rule-row builder widgets (PRD 04)."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from pycreditools.studio.models import ColumnRoles, PolicyEntry, StudioState
from pycreditools.studio.policy_builder import (
    DIRECTIONS,
    OPERATORS,
    angled_rate_variable,
    build_policy,
    clone_rows,
    filter_pass_drop_stats,
    make_cutoff_row,
    make_filter_row,
    make_rate_row,
    make_stress_row,
    suggested_take_up_rate,
)

_TYPE_LABELS = {"filter": "Filtro", "cutoff": "Cutoff", "rate": "Taxa", "stress": "Stress"}


def _default_policy_name(state: StudioState) -> str:
    n = 1
    while f"Política {n}" in state.policies:
        n += 1
    return f"Política {n}"


def render_policy_manager(state: StudioState) -> PolicyEntry:
    """Top bar: policy selectbox + nova/duplicar/renomear/excluir. Returns the active entry."""
    if not state.policies:
        name = _default_policy_name(state)
        state.policies[name] = PolicyEntry(name=name, policy=build_policy(state.roles, []))
        state.active_policy = name

    names = list(state.policies.keys())
    if state.active_policy not in names:
        state.active_policy = names[0]
    if st.session_state.get("policy_select") != state.active_policy:
        st.session_state["policy_select"] = state.active_policy

    with st.container(border=True):
        sel_col, new_col, dup_col, del_col = st.columns([3, 1, 1, 1])
        with sel_col:
            selected = st.selectbox(
                "Política ativa",
                names,
                index=names.index(state.active_policy),
                key="policy_select",
            )
        with new_col:
            if st.button("➕ Nova", key="policy_new", use_container_width=True):
                new_name = _default_policy_name(state)
                state.policies[new_name] = PolicyEntry(
                    name=new_name, policy=build_policy(state.roles, [])
                )
                state.active_policy = new_name
                st.rerun()
        with dup_col:
            if st.button("📄 Duplicar", key="policy_duplicate", use_container_width=True):
                src = state.policies[selected]
                new_name = f"{selected} (cópia)"
                while new_name in state.policies:
                    new_name += " (cópia)"
                state.policies[new_name] = PolicyEntry(
                    name=new_name,
                    policy=src.policy,
                    flat_stress_factor=src.flat_stress_factor,
                    rows=clone_rows(src.rows),
                )
                state.active_policy = new_name
                st.rerun()
        with del_col:
            if st.button(
                "🗑️ Excluir",
                key="policy_delete",
                use_container_width=True,
                disabled=len(names) <= 1,
            ):
                del state.policies[selected]
                state.active_policy = next(iter(state.policies))
                st.rerun()

        renamed = st.text_input(
            "Nome da política", value=selected, key=f"policy_rename_{selected}"
        )
        if renamed and renamed != selected and renamed not in state.policies:
            entry = state.policies.pop(selected)
            entry.name = renamed
            state.policies[renamed] = entry
            state.active_policy = renamed
            st.rerun()

    state.active_policy = selected
    return state.policies[selected]


def _render_value_input(df: pd.DataFrame, column: str, current: Any, *, key: str) -> Any:
    series = df[column]
    if pd.api.types.is_bool_dtype(series):
        default = bool(current) if isinstance(current, bool) else True
        return st.toggle("Valor", value=default, key=key)
    if pd.api.types.is_numeric_dtype(series):
        default = (
            float(current)
            if isinstance(current, int | float) and not isinstance(current, bool)
            else float(series.median())
        )
        return st.number_input("Valor", value=default, key=key)
    options = sorted(series.dropna().unique().tolist(), key=str)
    if not options:
        return st.text_input("Valor", value=str(current or ""), key=key)
    index = options.index(current) if current in options else 0
    return st.selectbox("Valor", options, index=index, key=key)


def _render_filter_histogram(df: pd.DataFrame, clause: dict[str, Any]) -> None:
    """Show pass/drop stats for the current clause value (critique 1.9)."""
    col = clause.get("column")
    op = clause.get("operator")
    val = clause.get("value")
    if col is None or col not in df.columns or op is None or val is None:
        return
    stats = filter_pass_drop_stats(df, col, op, val)
    if stats["total"] == 0:
        return
    st.caption(
        f"**Passa:** {stats['pass_count']:,} ({stats['pass_frac']:.1%}) · "
        f"**Cai:** {stats['drop_count']:,} ({stats['drop_frac']:.1%})"
    )


def _render_filter_row(df: pd.DataFrame, row: dict[str, Any]) -> None:
    row["name"] = st.text_input("Nome do filtro", value=row["name"], key=f"filter_name_{row['id']}")
    columns = list(df.columns)
    for ci, clause in enumerate(row["clauses"]):
        col_a, col_b, col_c, col_d = st.columns([2, 1, 2, 0.6])
        with col_a:
            current_col = clause.get("column") if clause.get("column") in columns else columns[0]
            clause["column"] = st.selectbox(
                "Coluna",
                columns,
                index=columns.index(current_col),
                key=f"filter_col_{row['id']}_{ci}",
            )
        with col_b:
            current_op = clause.get("operator", ">=")
            op_index = OPERATORS.index(current_op) if current_op in OPERATORS else 0
            clause["operator"] = st.selectbox(
                "Operador", OPERATORS, index=op_index, key=f"filter_op_{row['id']}_{ci}"
            )
        with col_c:
            clause["value"] = _render_value_input(
                df, clause["column"], clause.get("value"), key=f"filter_val_{row['id']}_{ci}"
            )
        with col_d:
            st.markdown("&nbsp;")
            if st.button("✕", key=f"filter_clause_del_{row['id']}_{ci}") and len(
                row["clauses"]
            ) > 1:
                row["clauses"].pop(ci)
                st.rerun()
        _render_filter_histogram(df, clause)
    if st.button("E + condição", key=f"filter_add_clause_{row['id']}"):
        row["clauses"].append({"column": columns[0], "operator": ">=", "value": 0})
        st.rerun()


def _render_cutoff_row(df: pd.DataFrame, roles: ColumnRoles, row: dict[str, Any]) -> None:
    row["name"] = st.text_input("Nome do corte", value=row["name"], key=f"cutoff_name_{row['id']}")
    score_choices = roles.score_cols or list(df.columns)
    default_scores = [s for s in row["cutoffs"] if s in score_choices] or (
        score_choices[:1] if score_choices else []
    )
    selected_scores = st.multiselect(
        "Scores", score_choices, default=default_scores, key=f"cutoff_scores_{row['id']}"
    )
    direction_index = DIRECTIONS.index(row.get("direction", "gte"))
    direction = st.selectbox(
        "Direção",
        DIRECTIONS,
        index=direction_index,
        format_func=lambda d: "≥ (gte)" if d == "gte" else "≤ (lte)",
        key=f"cutoff_dir_{row['id']}",
    )
    new_cutoffs: dict[str, float] = {}
    for score in selected_scores:
        if score not in df.columns:
            st.warning(f"Coluna `{score}` não existe na base atual.")
            continue
        lo, hi = float(df[score].quantile(0.01)), float(df[score].quantile(0.99))
        if lo >= hi:
            lo, hi = float(df[score].min()), float(df[score].max())
        default_val = row["cutoffs"].get(score, (lo + hi) / 2)
        default_val = min(max(float(default_val), lo), hi)
        cut_val = st.slider(
            f"Corte {score}",
            min_value=lo,
            max_value=hi,
            value=default_val,
            key=f"cutoff_val_{row['id']}_{score}",
        )
        new_cutoffs[score] = cut_val
        op = ">=" if direction == "gte" else "<="
        stats = filter_pass_drop_stats(df, score, op, cut_val)
        if stats["total"] > 0:
            st.caption(
                f"**Passa:** {stats['pass_count']:,} ({stats['pass_frac']:.1%}) · "
                f"**Cai:** {stats['drop_count']:,} ({stats['drop_frac']:.1%})"
            )
    row["cutoffs"] = new_cutoffs
    row["direction"] = direction


def _render_rate_row(
    df: pd.DataFrame, roles: ColumnRoles, row: dict[str, Any]
) -> None:
    st.caption(
        "**Taxa de aceite/contratação** — dos aprovados, % que efetivamente contrata. "
        "Cada etapa encolhe o funil e evita superdimensionar o swap-in."
    )
    row["name"] = st.text_input("Nome da taxa", value=row["name"], key=f"rate_name_{row['id']}")

    # Suggestion hint (non-locking)
    suggested = suggested_take_up_rate(df, roles)
    if suggested is not None:
        hint_col, use_col = st.columns([3, 1])
        with hint_col:
            st.caption(f"Sugestão baseada nos dados: **{suggested:.1%}** (contratados / aprovados)")
        with use_col:
            if st.button("Usar", key=f"rate_suggest_use_{row['id']}", use_container_width=True):
                row["base_rate"] = round(suggested, 4)
                st.rerun()

    row["base_rate"] = st.slider(
        "Taxa base", 0.0, 1.0, value=float(row.get("base_rate", 0.5)), key=f"rate_base_{row['id']}"
    )

    current_variable = row.get("variable")
    is_angled = row.get("_angled_mode", False)
    modes = ("Nenhuma", "Coluna", "Constante", "Ângulo por score")
    if is_angled:
        mode_index = 3
    elif isinstance(current_variable, str):
        mode_index = 1
    elif isinstance(current_variable, (int, float)):
        mode_index = 2
    else:
        mode_index = 0
    mode = st.radio(
        "Variável", modes, index=mode_index, horizontal=True, key=f"rate_mode_{row['id']}"
    )

    if mode == "Coluna":
        row["_angled_mode"] = False
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        is_col = isinstance(current_variable, str) and current_variable in numeric_cols
        default_col = current_variable if is_col else (numeric_cols[0] if numeric_cols else None)
        if numeric_cols:
            row["variable"] = st.selectbox(
                "Coluna",
                numeric_cols,
                index=numeric_cols.index(default_col),
                key=f"rate_var_col_{row['id']}",
            )
        else:
            row["variable"] = None
    elif mode == "Constante":
        row["_angled_mode"] = False
        is_number = isinstance(current_variable, (int, float)) and not isinstance(
            current_variable, bool
        )
        default_const = float(current_variable) if is_number else 1.0
        row["variable"] = st.number_input(
            "Multiplicador constante", value=default_const, key=f"rate_var_const_{row['id']}"
        )
    elif mode == "Ângulo por score":
        row["_angled_mode"] = True
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        score_choices = roles.score_cols or numeric_cols
        saved = row.get("_angled_score_col")
        default_score = saved or (score_choices[-1] if score_choices else None)
        if score_choices and default_score in score_choices:
            default_idx = score_choices.index(default_score)
        elif score_choices:
            default_idx = 0
        else:
            default_idx = None
        angled_col, spread_col = st.columns([2, 1])
        with angled_col:
            if score_choices and default_idx is not None:
                chosen_score = st.selectbox(
                    "Score (pior → mais tomadores)",
                    score_choices,
                    index=default_idx,
                    key=f"rate_angled_col_{row['id']}",
                )
                row["_angled_score_col"] = chosen_score
            else:
                st.caption("Nenhuma coluna de score disponível.")
                row["variable"] = None
                row["_angled_mode"] = False
                return
        with spread_col:
            spread = st.slider(
                "Amplitude",
                0.05,
                0.6,
                value=float(row.get("_angled_spread", 0.4)),
                step=0.05,
                key=f"rate_angled_spread_{row['id']}",
            )
            row["_angled_spread"] = spread
        st.caption(
            "Piores scores recebem multiplicador maior (mais tomadores). "
            f"Faixa: [{1.0 - spread:.0%} – {1.0 + spread:.0%}] × taxa base."
        )
        row["variable"] = angled_rate_variable(df, row["_angled_score_col"], spread=spread)
    else:
        row["_angled_mode"] = False
        row["variable"] = None

    row["calibrate"] = st.toggle(
        "Calibrar (avançado)",
        value=bool(row.get("calibrate", False)),
        key=f"rate_calibrate_{row['id']}",
    )


def _render_stress_row(row: dict[str, Any]) -> None:
    st.caption("Agrava a PD dos *swap-ins* por este fator (ex.: 1.2 = +20%).")
    row["factor"] = st.slider(
        "Fator de agravamento",
        1.0,
        5.0,
        value=float(row.get("factor", 1.2)),
        step=0.05,
        key=f"stress_factor_{row['id']}",
    )


def _row_summary(row: dict[str, Any], df: pd.DataFrame) -> str:
    """One-line summary for the compact rule row header (critique 1.9.2)."""
    rtype = row["type"]
    name = row.get("name", "")
    if rtype == "filter":
        clauses = row.get("clauses", [])
        if clauses:
            c = clauses[0]
            col_name = c.get("column", "?")
            op = c.get("operator", "?")
            val = c.get("value", "?")
            stats = filter_pass_drop_stats(df, col_name, op, val) if col_name in df.columns else {}
            cut_pct = f" · corta {stats['drop_frac']:.0%}" if stats.get("total", 0) > 0 else ""
            extras = f" (e {len(clauses) - 1} mais)" if len(clauses) > 1 else ""
            return f"{name} · {col_name} {op} {val}{extras}{cut_pct}"
        return f"{name} (sem condições)"
    if rtype == "cutoff":
        cutoffs = row.get("cutoffs", {})
        direction = row.get("direction", "gte")
        dir_sym = "≥" if direction == "gte" else "≤"
        op = ">=" if direction == "gte" else "<="
        parts = []
        for score, val in cutoffs.items():
            stats = filter_pass_drop_stats(df, score, op, val) if score in df.columns else {}
            cut_pct = f" · corta {stats['drop_frac']:.0%}" if stats.get("total", 0) > 0 else ""
            parts.append(f"{score} {dir_sym} {val:.1f}{cut_pct}")
        return f"{name} · " + "; ".join(parts) if parts else name
    if rtype == "rate":
        base = row.get("base_rate", 0.0)
        return f"{name} · {base:.0%} de aceite"
    if rtype == "stress":
        factor = row.get("factor", 1.2)
        return f"Agravamento ×{factor:.2f}"
    return name


def _render_row(
    df: pd.DataFrame, roles: ColumnRoles, row: dict[str, Any], index: int, total: int, rows: list
) -> None:
    summary = _row_summary(row, df)
    with st.container(border=True):
        ctrl_col, up_col, down_col, del_col = st.columns([5, 1, 1, 1])
        with ctrl_col:
            st.caption(f"{index + 1}. {summary}")
        with up_col:
            if st.button("↑", key=f"up_{row['id']}", disabled=index == 0, use_container_width=True):
                rows[index - 1], rows[index] = rows[index], rows[index - 1]
                st.rerun()
        with down_col:
            if st.button(
                "↓", key=f"down_{row['id']}", disabled=index == total - 1, use_container_width=True
            ):
                rows[index + 1], rows[index] = rows[index], rows[index + 1]
                st.rerun()
        with del_col:
            if st.button("🗑️", key=f"del_{row['id']}", use_container_width=True):
                rows.pop(index)
                st.rerun()
                return

        with st.expander("Editar", expanded=False):
            if row["type"] == "filter":
                _render_filter_row(df, row)
            elif row["type"] == "cutoff":
                _render_cutoff_row(df, roles, row)
            elif row["type"] == "rate":
                _render_rate_row(df, roles, row)
            elif row["type"] == "stress":
                _render_stress_row(row)


def render_rule_builder(df: pd.DataFrame, roles: ColumnRoles, entry: PolicyEntry) -> list[dict]:
    """Render the add-row toolbar + the editable list of rule rows; returns the updated rows."""
    rows = entry.rows

    add_filter_col, add_cutoff_col, add_rate_col = st.columns(3)
    with add_filter_col:
        if st.button("➕ Filtro", key="add_filter", use_container_width=True):
            default_col = roles.score_cols[0] if roles.score_cols else df.columns[0]
            rows.append(
                make_filter_row(
                    name=f"Filtro {len(rows) + 1}",
                    clauses=[{"column": default_col, "operator": ">=", "value": 0}],
                )
            )
            st.rerun()
    with add_cutoff_col:
        if st.button("➕ Cutoff", key="add_cutoff", use_container_width=True):
            default_score = roles.score_cols[-1] if roles.score_cols else None
            cutoffs = (
                {default_score: float(df[default_score].quantile(0.5))} if default_score else {}
            )
            rows.append(make_cutoff_row(name=f"Cutoff {len(rows) + 1}", cutoffs=cutoffs))
            st.rerun()
    with add_rate_col:
        if st.button("➕ Taxa", key="add_rate", use_container_width=True):
            rows.append(make_rate_row(name=f"Taxa {len(rows) + 1}", base_rate=0.5))
            st.rerun()

    has_stress = any(r["type"] == "stress" for r in rows)
    if not has_stress:
        if st.button("➕ Stress (flat)", key="add_stress"):
            rows.append(make_stress_row(factor=1.2))
            st.rerun()

    if not rows:
        st.info("Adicione uma regra para começar a construir a política.")

    for index, row in enumerate(rows):
        _render_row(df, roles, row, index, len(rows), rows)

    entry.rows = rows
    return rows
