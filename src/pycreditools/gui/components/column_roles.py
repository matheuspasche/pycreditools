"""The column-role picker widget (PRD 02)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.studio.detection import ROLE_HINTS, detect_tier, validate_role_format
from pycreditools.studio.models import ColumnRoles


def _selectbox(
    label: str, cols: list[str], current: str | None, *, key: str, help: str | None = None
) -> str | None:
    options = ["—", *cols]
    index = options.index(current) if current in cols else 0
    choice = st.selectbox(label, options, index=index, key=key, help=help)
    return None if choice == "—" else choice


def _warn_if_bad_format(role_key: str, df: pd.DataFrame, col: str | None) -> None:
    if not col:
        return
    warning = validate_role_format(role_key, df[col])
    if warning:
        st.warning(warning)


def render_column_roles(df: pd.DataFrame, roles: ColumnRoles) -> ColumnRoles:
    """Render the role picker pre-filled from `roles`; return the (possibly edited) roles.

    Most roles are optional (ADR 0002) — `estimated_default_col` ("PD estimada") is
    shown only once the picked roles resolve to comparison Tier C.
    """
    cols = list(df.columns)

    applicant_id_col = _selectbox(
        "ID do solicitante",
        cols,
        roles.applicant_id_col,
        key="role_applicant_id",
        help=ROLE_HINTS["applicant_id_col"],
    )
    score_cols = st.multiselect(
        "Colunas de score (candidatas)",
        cols,
        default=[c for c in roles.score_cols if c in cols],
        key="role_score_cols",
        help=ROLE_HINTS["score_cols"],
    )

    col_a, col_b = st.columns(2)
    with col_a:
        current_approval_col = _selectbox(
            "Aprovação atual (opcional)",
            cols,
            roles.current_approval_col,
            key="role_approval",
            help=ROLE_HINTS["current_approval_col"],
        )
        _warn_if_bad_format("current_approval_col", df, current_approval_col)

        vigente_score = _selectbox(
            "Score vigente (opcional)",
            cols,
            roles.vigente_score,
            key="role_vigente_score",
            help=ROLE_HINTS["vigente_score"],
        )
        _warn_if_bad_format("vigente_score", df, vigente_score)

        actual_default_col = _selectbox(
            "Default observado (target, opcional)",
            cols,
            roles.actual_default_col,
            key="role_default",
            help=ROLE_HINTS["actual_default_col"],
        )
        _warn_if_bad_format("actual_default_col", df, actual_default_col)

        current_hired_col = _selectbox(
            "Contratação atual (opcional)",
            cols,
            roles.current_hired_col,
            key="role_hired",
            help=ROLE_HINTS["current_hired_col"],
        )
        _warn_if_bad_format("current_hired_col", df, current_hired_col)
    with col_b:
        time_col = _selectbox(
            "Safra / vintage (opcional)",
            cols,
            roles.time_col,
            key="role_time",
            help=ROLE_HINTS["time_col"],
        )
        segment_col = _selectbox(
            "Segmento (opcional)",
            cols,
            roles.segment_col,
            key="role_segment",
            help=ROLE_HINTS["segment_col"],
        )

        tier = detect_tier(
            ColumnRoles(vigente_score=vigente_score, current_approval_col=current_approval_col),
            df,
        ).tier
        if tier == "C":
            estimated_default_col = _selectbox(
                "PD estimada (modelo)",
                cols,
                roles.estimated_default_col,
                key="role_estimated",
                help=ROLE_HINTS["estimated_default_col"],
            )
            _warn_if_bad_format("estimated_default_col", df, estimated_default_col)
        else:
            estimated_default_col = roles.estimated_default_col

    oot_date = roles.oot_date
    if time_col:
        unique_times = sorted(str(v) for v in df[time_col].dropna().unique())
        oot_options = ["—", *unique_times]
        oot_default = roles.oot_date if roles.oot_date in unique_times else "—"
        oot_choice = st.selectbox(
            "Data de corte OOT",
            oot_options,
            index=oot_options.index(oot_default),
            key="role_oot",
            help=ROLE_HINTS["oot_date"],
        )
        oot_date = None if oot_choice == "—" else oot_choice
    else:
        oot_date = None

    return ColumnRoles(
        applicant_id_col=applicant_id_col,
        score_cols=score_cols,
        current_approval_col=current_approval_col,
        actual_default_col=actual_default_col,
        current_hired_col=current_hired_col,
        time_col=time_col,
        segment_col=segment_col,
        estimated_default_col=estimated_default_col,
        oot_date=oot_date,
        vigente_score=vigente_score,
    )
