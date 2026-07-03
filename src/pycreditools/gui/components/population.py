"""The shared population-selector widget (Master §9.4, critiques 1.7 + 2.0)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.gui import data_access
from pycreditools.studio.data import PERIODO_CHOICES, QUEM_CHOICES, population_filter_two_axes
from pycreditools.studio.models import ColumnRoles

_CHOICES = ("Todos", "Aprovados", "Contratados", "DEV", "OOT")


def render_population_selector(
    df: pd.DataFrame, roles: ColumnRoles, *, key: str, default: str = "Contratados"
) -> tuple[str, pd.DataFrame]:
    """Render the population selectbox; return `(choice, filtered_df)`.

    Falls back to an empty frame (with a warning) if the chosen population needs a
    role that isn't configured yet — never raises into the page.
    """
    index = _CHOICES.index(default) if default in _CHOICES else 0
    choice = st.selectbox("População", _CHOICES, index=index, key=key)
    try:
        subset = data_access.population_filter(df, roles, choice)
    except ValueError as exc:
        st.warning(str(exc))
        subset = df.iloc[0:0]
    return choice, subset


def render_population_selector_v2(
    df: pd.DataFrame,
    roles: ColumnRoles,
    *,
    key: str,
    default_periodo: str = "Tudo",
    default_quem: str = "Todos",
) -> tuple[str, str, pd.DataFrame]:
    """Two-axis population selector (critiques 1.7 + 2.0): Período × Quem.

    Returns `(periodo, quem, filtered_df)`.  Falls back to an empty frame with a
    warning if the required role column is not configured — never raises into the page.
    """
    periodo_idx = (
        list(PERIODO_CHOICES).index(default_periodo) if default_periodo in PERIODO_CHOICES else 0
    )
    quem_idx = list(QUEM_CHOICES).index(default_quem) if default_quem in QUEM_CHOICES else 0

    col_periodo, col_quem = st.columns(2)
    with col_periodo:
        periodo = st.selectbox(
            "Período",
            PERIODO_CHOICES,
            index=periodo_idx,
            key=f"{key}_periodo",
        )
    with col_quem:
        quem = st.selectbox(
            "Quem",
            QUEM_CHOICES,
            index=quem_idx,
            key=f"{key}_quem",
        )

    try:
        subset = population_filter_two_axes(df, roles, periodo, quem)
    except ValueError as exc:
        st.warning(str(exc))
        subset = df.iloc[0:0]

    return periodo, quem, subset


def render_effective_n_caption(
    subset: pd.DataFrame, roles: ColumnRoles, target_col: str | None = None
) -> None:
    """Render a human-readable effective-N caption (critique 1.7 / 2.0).

    Shows the count of rows that have a known default outcome, replacing the
    old "N efetivo (com actual_default observado)" copy with pt-BR.
    """
    col = target_col or roles.actual_default_col
    if col and col in subset.columns:
        n = int(subset[col].notna().sum())
        st.caption(
            f"**{n:,}** clientes com inadimplência conhecida (base do cálculo) "
            f"de {len(subset):,} na população selecionada."
        )
    else:
        st.caption(f"**{len(subset):,}** clientes na população selecionada.")
