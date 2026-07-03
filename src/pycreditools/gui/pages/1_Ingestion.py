"""Ingestion page — upload/generate data, column roles (PRD 02).

The unified session save/load lives in the sidebar (`components/session_actions.py`,
#37) — discreet and reachable from any page, not a tab here.
"""

from __future__ import annotations

import streamlit as st

from pycreditools import CreditPolicy
from pycreditools.gui import data_access
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.column_roles import render_column_roles
from pycreditools.gui.components.tier_badge import render_tier_badge
from pycreditools.gui.session import DATASET_SOURCE_KEY, get_state
from pycreditools.studio.detection import detect_roles

st.title("Ingestão")
st.caption("Carregue uma base (CSV/Parquet) ou gere dados de amostra.")

state = get_state()

if state.df is not None:
    render_tier_badge(state.roles, state.df)


def _set_dataset(df, df_name: str, df_hash: str, *, source: dict) -> None:
    """Store a freshly loaded dataframe and reset stale downstream results."""
    if state.df_hash is not None and state.df_hash != df_hash:
        state.last_sim = None
        state.legacy_sim = None
        state.rating_result = None
    state.df = df
    state.df_name = df_name
    state.df_hash = df_hash
    state.roles = detect_roles(df)
    st.session_state[DATASET_SOURCE_KEY] = source


tab_load, tab_roles = st.tabs(["Carregar base", "Mapear colunas"])

with tab_load:
    uploaded = st.file_uploader("Arquivo (CSV ou Parquet)", type=["csv", "parquet"])
    if uploaded is not None:
        content = uploaded.getvalue()
        df_hash = data_access.hash_bytes(content)
        if state.df_hash != df_hash:
            try:
                df = (
                    data_access.load_parquet(content)
                    if uploaded.name.endswith(".parquet")
                    else data_access.load_csv(content)
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                st.error(f"Não foi possível ler o arquivo: {exc}")
                df = None
            if df is not None:
                _set_dataset(
                    df,
                    uploaded.name,
                    df_hash,
                    source={
                        "kind": "upload",
                        "path_or_source": uploaded.name,
                        "sample": None,
                    },
                )
                st.rerun()

    st.divider()
    st.subheader("Gerar base de exemplo")
    col_n, col_seed, col_btn = st.columns([2, 1, 1])
    with col_n:
        n_applicants = st.number_input(
            "Nº de solicitantes", min_value=100, max_value=1_000_000, value=50_000, step=1000
        )
    with col_seed:
        seed = st.number_input("Seed", min_value=0, value=42, step=1)
    with col_btn:
        st.write("")
        generate = st.button("Gerar base de exemplo", type="primary")
    if generate:
        df, df_hash = data_access.make_sample(int(n_applicants), int(seed))
        _set_dataset(
            df,
            f"sample_{int(n_applicants)}_{int(seed)}",
            df_hash,
            source={
                "kind": "sample",
                "path_or_source": "sample",
                "sample": {"n_applicants": int(n_applicants), "seed": int(seed)},
            },
        )
        st.rerun()

    if state.df is not None:
        df = state.df
        bad_rate = None
        if state.roles.actual_default_col and state.roles.actual_default_col in df.columns:
            target = df[state.roles.actual_default_col].dropna()
            if len(target):
                bad_rate = target.mean()
        kpi.kpi_row(
            [
                {"label": "Linhas", "value": tables.thousands(len(df))},
                {"label": "Colunas", "value": str(df.shape[1])},
                {
                    "label": "Memória (MB)",
                    "value": f"{df.memory_usage(deep=True).sum() / 1e6:.1f}",
                },
                {
                    "label": "Inadimplência observada",
                    "value": tables.pct(bad_rate) if bad_rate is not None else "—",
                    "delta_good": False,
                },
            ]
        )
        st.caption("Pré-visualização (200 primeiras linhas)")
        tables.dataframe(df.head(200))
        with st.expander("Tipos das colunas"):
            summary = df.dtypes.rename("dtype").to_frame()
            summary["% nulos"] = (df.isna().mean() * 100).round(1)
            summary["n únicos"] = df.nunique()
            tables.dataframe(summary.reset_index(names="coluna"))
    else:
        st.info("Nenhuma base carregada ainda.")

with tab_roles:
    if state.df is None:
        st.warning("Carregue uma base na aba 'Carregar base' primeiro.")
    else:
        state.roles = render_column_roles(state.df, state.roles)

        st.divider()
        st.subheader("Validação")
        roles = state.roles
        if not roles.applicant_id_col or not roles.score_cols:
            st.info("Defina ao menos o ID do solicitante e as colunas de score para validar.")
        else:
            try:
                policy = CreditPolicy(
                    applicant_id_col=roles.applicant_id_col,
                    score_cols=tuple(roles.score_cols),
                    current_approval_col=roles.current_approval_col,
                    actual_default_col=roles.actual_default_col,
                    time_col=roles.time_col,
                )
                policy.validate(state.df)
                st.success("Configuração de colunas válida.")
            except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                st.error(f"Configuração inválida: {exc}")
