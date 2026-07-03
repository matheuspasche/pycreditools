"""Themed `st.dataframe` wrappers + number formatters."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def pct(x: float) -> str:
    """Format a 0-1 rate as a percentage with one decimal."""
    return f"{x * 100:.1f}%"


def thousands(x: float) -> str:
    """Format a count with a thousands separator."""
    return f"{x:,.0f}"


def score(x: float) -> str:
    """Format a score as an integer."""
    return f"{round(x):d}"


def dataframe(
    df: pd.DataFrame,
    *,
    percent_cols: tuple[str, ...] = (),
    int_cols: tuple[str, ...] = (),
    money_cols: tuple[str, ...] = (),
    **kwargs: Any,
) -> Any:
    """Render a themed `st.dataframe` with right-aligned, formatted numeric columns.

    `percent_cols` hold 0-1 rates; they are scaled to 0-100 for display since the
    printf-style `NumberColumn` format does not multiply by 100 on its own.
    """
    column_config: dict[str, Any] = {}
    display_df = df
    if percent_cols:
        display_df = df.copy()
        for col in percent_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col] * 100
    for col in percent_cols:
        column_config[col] = st.column_config.NumberColumn(col, format="%.1f%%")
    for col in int_cols:
        column_config[col] = st.column_config.NumberColumn(col, format="%d")
    for col in money_cols:
        column_config[col] = st.column_config.NumberColumn(col, format="R$ %.2f")
    return st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
        **kwargs,
    )
