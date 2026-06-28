"""Bridges `st.session_state` to `pycreditools.studio.models`."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools import (
    CreditPolicy,
    CreditSimResults,
    DeploymentPolicy,
    OptimizationResult,
    RiskGroupResult,
)
from pycreditools.studio import analyses
from pycreditools.studio.models import OpenMatrix, PolicyEntry, StudioState

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


@st.cache_data(show_spinner="Calculando complementaridade...")
def compute_complementarity_table(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    candidate_scores: tuple[str, ...],
    reference_score: str,
    target_col: str,
) -> pd.DataFrame:
    """Cached complementarity table (ADR 0004); `df_hash`/`population` are cache-key-only."""
    return analyses.complementarity_table(_df, list(candidate_scores), reference_score, target_col)


@st.cache_data(show_spinner="Simulando política...")
def run_policy_sim(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    _policy: CreditPolicy,
    policy_key: str,
    method: str = "analytical",
) -> CreditSimResults:
    """Cached policy simulation; `df_hash`/`population`/`policy_key` are cache-key-only."""
    return analyses.run_policy_sim(_df, _policy, method=method)


@st.cache_data(show_spinner="Calculando fronteira de trade-off...")
def run_tradeoff(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    _policy: CreditPolicy,
    policy_key: str,
    score_col: str,
    cutoff_values: tuple[float, ...],
    stress_values: tuple[float, ...] | None = None,
    rate_stage_name: str | None = None,
    rate_values: tuple[float, ...] | None = None,
    parallel: bool = False,
) -> pd.DataFrame:
    """Cached trade-off sweep; `df_hash`/`population`/`policy_key` are cache-key-only."""
    rate_stage = (rate_stage_name, list(rate_values)) if rate_stage_name and rate_values else None
    return analyses.run_tradeoff(
        _df,
        _policy,
        score_col,
        list(cutoff_values),
        stress_values=list(stress_values) if stress_values else None,
        rate_stage=rate_stage,
        parallel=parallel,
    )


@st.cache_data(show_spinner="Rodando crash test...")
def run_crash_test(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    _policy: CreditPolicy,
    policy_key: str,
    factors: tuple[float, ...],
    parallel: bool = False,
) -> pd.DataFrame:
    """Cached crash-test sweep; `df_hash`/`population`/`policy_key` are cache-key-only."""
    return analyses.run_crash_test(_df, _policy, list(factors), parallel=parallel)


@st.cache_data(show_spinner="Otimizando cortes...")
def run_optimization(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    _policy: CreditPolicy,
    policy_key: str,
    cutoff_steps: int = 10,
    target_default_rate: float = 0.05,
    min_approval_rate: float = 0.3,
    method: str = "analytical",
    parallel: bool = False,
    percentiles: tuple[float, float] | None = (0.05, 0.95),
) -> OptimizationResult:
    """Cached cutoff grid-search; `df_hash`/`population`/`policy_key` are cache-key-only."""
    return analyses.run_optimization(
        _df,
        _policy,
        cutoff_steps=cutoff_steps,
        target_default_rate=target_default_rate,
        min_approval_rate=min_approval_rate,
        method=method,
        parallel=parallel,
        percentiles=percentiles,
    )


@st.cache_data(show_spinner="Agrupando em ratings...")
def fit_risk_groups(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    score_cols: tuple[str, ...],
    default_col: str,
    bins: int = 20,
    max_groups: int | None = None,
    min_vol_ratio: float = 0.05,
    max_crossings: int = 1,
    time_col: str | None = None,
    method: str = "ward",
    oot_date: str | None = None,
) -> RiskGroupResult:
    """Cached risk grouping; `df_hash`/`population` are cache-key-only."""
    return analyses.fit_groups(
        _df,
        list(score_cols),
        default_col,
        bins=bins,
        max_groups=max_groups,
        min_vol_ratio=min_vol_ratio,
        max_crossings=max_crossings,
        time_col=time_col,
        method=method,
        oot_date=oot_date,
    )


@st.cache_data(show_spinner="Agrupando em pares (primary vs challengers)...")
def fit_pairwise_risk_groups(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    primary: str,
    challengers: tuple[str, ...],
    default_col: str,
    bins: int = 20,
    max_groups: int | None = None,
    min_vol_ratio: float = 0.05,
    max_crossings: int = 1,
    time_col: str | None = None,
    method: str = "ward",
    oot_date: str | None = None,
) -> dict[str, RiskGroupResult]:
    """Cached pairwise risk grouping; `df_hash`/`population` are cache-key-only."""
    return analyses.fit_pairwise_groups(
        _df,
        primary,
        list(challengers),
        default_col,
        bins=bins,
        max_groups=max_groups,
        min_vol_ratio=min_vol_ratio,
        max_crossings=max_crossings,
        time_col=time_col,
        method=method,
        oot_date=oot_date,
    )


@st.cache_data(show_spinner="Construindo matriz aberta...")
def build_open_matrix(
    _df: pd.DataFrame,
    df_hash: str,
    population: str,
    score1: str,
    score2: str,
    default_col: str,
    bins: int = 5,
) -> OpenMatrix:
    """Cached open score x score matrix; `df_hash`/`population` are cache-key-only."""
    return analyses.build_open_matrix(_df, score1, score2, default_col, bins=bins)


@st.cache_data(show_spinner="Escorando arquivo...")
def score_batch(
    _df: pd.DataFrame,
    file_hash: str,
    _dep: DeploymentPolicy,
    dep_key: str,
    simple: bool = True,
    method: str = "analytical",
) -> pd.DataFrame:
    """Cached batch scoring; `file_hash`/`dep_key` are cache-key-only."""
    return analyses.score_batch(_df, _dep, simple=simple, method=method)
