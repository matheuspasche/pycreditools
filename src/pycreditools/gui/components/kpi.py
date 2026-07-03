"""KPI "stat card" row."""

from __future__ import annotations

from typing import Any

import streamlit as st


def kpi_row(items: list[dict[str, Any]]) -> None:
    """Render a row of stat cards: label, big value, optional colored delta."""
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col, st.container(border=True):
            st.caption(item["label"])
            st.markdown(f"### {item['value']}")
            delta = item.get("delta")
            if delta is not None:
                color = "var(--success)" if item.get("delta_good", True) else "var(--danger)"
                st.markdown(f"<span style='color:{color}'>{delta}</span>", unsafe_allow_html=True)
            help_text = item.get("help")
            if help_text:
                st.caption(help_text)
