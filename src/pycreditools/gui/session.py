"""Bridges `st.session_state` to `pycreditools.studio.models`."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.studio import analyses
from pycreditools.studio.models import PolicyEntry, StudioState

_KEY = "studio"


def init_state() -> None:
    """Create a `StudioState` once under `st.session_state["studio"]`."""
    if _KEY not in st.session_state:
        st.session_state[_KEY] = StudioState()


def get_state() -> StudioState:
    """Return the active `StudioState`, creating it if needed."""
    init_state()
    return st.session_state[_KEY]


def guard_dataset() -> None:
    """Stop the page with a friendly warning if no dataset is loaded."""
    state = get_state()
    if state.df is None:
        st.warning("Carregue uma base na página Ingestion.")
        st.stop()


def guard_roles(*required: str) -> None:
    """Stop the page with a friendly warning if a required column role is unset."""
    guard_dataset()
    state = get_state()
    missing = [name for name in required if not getattr(state.roles, name, None)]
    if missing:
        st.warning(f"Configure as colunas: {', '.join(missing)} na página Ingestion.")
        st.stop()


def require_policy() -> PolicyEntry:
    """Return the active `PolicyEntry` or stop with a friendly warning."""
    guard_dataset()
    state = get_state()
    if not state.active_policy or state.active_policy not in state.policies:
        st.warning("Construa uma política na página Policy Studio.")
        st.stop()
    return state.policies[state.active_policy]


@st.cache_data(show_spinner="Calculando KS...")
def compute_ks(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    score_cols: tuple[str, ...],
    target_col: str,
) -> dict[str, float]:
    """Cached KS per score; `df_hash`/`population` are cache-key-only (not used in the body)."""
    return analyses.evaluate_scores(_df, list(score_cols), target_col)


@st.cache_data(show_spinner="Calculando tabela de decis...")
def compute_ks_table(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    score_col: str,
    target_col: str,
    bins: int,
) -> pd.DataFrame:
    """Cached per-bucket KS table; `df_hash`/`population` are cache-key-only."""
    return analyses.ks_table(_df, score_col, target_col, bins)
