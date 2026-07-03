"""Comparison-tier badge — reads the core `detect_tier` and renders pt-BR copy (ADR 0002)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.studio.detection import detect_tier
from pycreditools.studio.models import ColumnRoles, TierDetection

_TIER_LABELS = {
    "A": "Tier A — reprodução completa",
    "B": "Tier B — apenas flags",
    "C": "Tier C — sem base",
}


def render_tier_badge(roles: ColumnRoles, df: pd.DataFrame) -> TierDetection:
    """Render the active comparison-tier badge and return the detection (other
    pages can call `detect_tier` directly to read it without re-rendering)."""
    detection = detect_tier(roles, df)
    st.info(f"**{_TIER_LABELS[detection.tier]}**\n\n{detection.rationale}")
    return detection
