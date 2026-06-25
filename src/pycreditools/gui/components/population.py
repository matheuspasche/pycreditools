"""The shared population-selector widget (Master §9.4)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.gui import data_access
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
