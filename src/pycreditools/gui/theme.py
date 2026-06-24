"""Dark fintech theme: CSS injection + Plotly template activation."""

from __future__ import annotations

from pathlib import Path

import plotly.io as pio
import streamlit as st

import pycreditools.studio.charts  # noqa: F401  registers the "pct_dark" template

_ASSETS = Path(__file__).parent / "assets"


def apply_theme() -> None:
    """Inject `assets/studio.css` and make `pct_dark` the default Plotly template."""
    css_path = _ASSETS / "studio.css"
    if css_path.exists():
        css = css_path.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    pio.templates.default = "pct_dark"
