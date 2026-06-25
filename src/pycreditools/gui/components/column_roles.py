"""The column-role picker widget (PRD 02)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.studio.models import ColumnRoles


def _selectbox(label: str, cols: list[str], current: str | None, *, key: str) -> str | None:
    options = ["—", *cols]
    index = options.index(current) if current in cols else 0
    choice = st.selectbox(label, options, index=index, key=key)
    return None if choice == "—" else choice


def render_column_roles(df: pd.DataFrame, roles: ColumnRoles) -> ColumnRoles:
    """Render the role picker pre-filled from `roles`; return the (possibly edited) roles."""
    cols = list(df.columns)

    applicant_id_col = _selectbox(
        "ID do solicitante", cols, roles.applicant_id_col, key="role_applicant_id"
    )
    score_cols = st.multiselect(
        "Colunas de score (candidatas)",
        cols,
        default=[c for c in roles.score_cols if c in cols],
        key="role_score_cols",
    )
    primary_options = ["—", *score_cols]
    primary_default = roles.primary_score_col if roles.primary_score_col in score_cols else "—"
    primary_score_col = st.selectbox(
        "Score principal",
        primary_options,
        index=primary_options.index(primary_default),
        key="role_primary_score",
    )
    primary_score_col = None if primary_score_col == "—" else primary_score_col

    col_a, col_b = st.columns(2)
    with col_a:
        current_approval_col = _selectbox(
            "Aprovação atual", cols, roles.current_approval_col, key="role_approval"
        )
        actual_default_col = _selectbox(
            "Default observado (target)", cols, roles.actual_default_col, key="role_default"
        )
        current_hired_col = _selectbox(
            "Contratação atual", cols, roles.current_hired_col, key="role_hired"
        )
    with col_b:
        time_col = _selectbox("Safra / vintage", cols, roles.time_col, key="role_time")
        segment_col = _selectbox("Segmento", cols, roles.segment_col, key="role_segment")
        estimated_default_col = _selectbox(
            "PD estimada (modelo)", cols, roles.estimated_default_col, key="role_estimated"
        )

    oot_date = roles.oot_date
    if time_col:
        unique_times = sorted(str(v) for v in df[time_col].dropna().unique())
        oot_options = ["—", *unique_times]
        oot_default = roles.oot_date if roles.oot_date in unique_times else "—"
        oot_choice = st.selectbox(
            "Data de corte OOT", oot_options, index=oot_options.index(oot_default), key="role_oot"
        )
        oot_date = None if oot_choice == "—" else oot_choice
    else:
        oot_date = None

    return ColumnRoles(
        applicant_id_col=applicant_id_col,
        score_cols=score_cols,
        primary_score_col=primary_score_col,
        current_approval_col=current_approval_col,
        actual_default_col=actual_default_col,
        current_hired_col=current_hired_col,
        time_col=time_col,
        segment_col=segment_col,
        estimated_default_col=estimated_default_col,
        oot_date=oot_date,
    )
