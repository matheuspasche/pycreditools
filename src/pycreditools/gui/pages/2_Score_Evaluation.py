"""Score Evaluation page — KS ranking and decile tables (PRD 03)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles
from pycreditools.studio import charts
from pycreditools.studio.analyses import (
    MAX_SCORES_EM_JOGO,
    effective_n,
    resolve_reference_score,
    select_scores_em_jogo,
)

st.title("Avaliação de Score")
st.caption("Ranking KS dos scores candidatos e tabela de decis.")

guard_roles("score_cols", "actual_default_col")
state = get_state()
roles = state.roles
target_col = roles.actual_default_col

with st.container(border=True):
    population, subset = render_population_selector(
        state.df, roles, key="score_eval_population", default="Contratados"
    )
    n_effective = effective_n(subset, target_col)
    st.caption(f"N efetivo (com `{target_col}` observado): {tables.thousands(n_effective)}")

if n_effective == 0:
    st.warning(
        "Nenhum default observado nesta população. Escolha outra opção no seletor "
        "de população acima."
    )
    st.stop()

with st.container(border=True):
    selected_scores = st.multiselect(
        "Scores a avaliar",
        roles.score_cols,
        default=roles.score_cols,
        key="score_eval_scores",
    )
    col_bins, col_table_score = st.columns(2)
    with col_bins:
        bins = st.slider(
            "Nº de buckets (decis)", min_value=4, max_value=20, value=10, key="score_eval_bins"
        )
    with col_table_score:
        table_default = (
            roles.primary_score_col
            if roles.primary_score_col in selected_scores
            else (selected_scores[0] if selected_scores else None)
        )
        table_score = (
            st.selectbox(
                "Score para a tabela de decis",
                selected_scores,
                index=selected_scores.index(table_default),
                key="score_eval_table_score",
            )
            if selected_scores
            else None
        )

if not selected_scores or table_score is None:
    st.info("Selecione ao menos um score para avaliar.")
    st.stop()

try:
    ks_scores = session.compute_ks(
        subset, state.df_hash, population, tuple(selected_scores), target_col
    )
except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
    st.error(f"Não foi possível calcular o KS: {exc}")
    st.stop()

ks_series = pd.Series(ks_scores).sort_values(ascending=False)
top_score = ks_series.index[0]
top_ks = ks_series.iloc[0]

legacy_col = "legacy_score" if "legacy_score" in ks_series.index else None
kpi_items = [
    {"label": "Score campeão", "value": top_score},
    {"label": "KS do campeão", "value": tables.pct(top_ks)},
]
if legacy_col and legacy_col != top_score:
    legacy_ks = ks_series[legacy_col]
    delta = top_ks - legacy_ks
    kpi_items.append(
        {
            "label": "KS do legacy_score",
            "value": tables.pct(legacy_ks),
            "delta": ("+" if delta >= 0 else "") + tables.pct(delta),
            "delta_good": delta >= 0,
        }
    )
kpi.kpi_row(kpi_items)

zero_variance = [name for name, value in ks_series.items() if value == 0.0]
if zero_variance:
    st.caption(f"Sem variância suficiente para: {', '.join(zero_variance)}.")

st.plotly_chart(
    charts.bars(ks_series, percent=True, highlight=legacy_col),
    use_container_width=True,
    config={"displayModeBar": False},
)

with st.container(border=True):
    st.caption(
        f"Marque os 2-3 scores em jogo: somente eles seguem para a Bancada "
        f"(máx. {MAX_SCORES_EM_JOGO})."
    )
    em_jogo_default = [s for s in state.scores_em_jogo if s in selected_scores]
    em_jogo_input = st.multiselect(
        "Scores em jogo",
        selected_scores,
        default=em_jogo_default,
        max_selections=MAX_SCORES_EM_JOGO,
        key="score_eval_em_jogo",
    )
    scores_em_jogo, em_jogo_warning = select_scores_em_jogo(em_jogo_input, selected_scores)
    state.scores_em_jogo = scores_em_jogo
    if em_jogo_warning:
        st.warning(em_jogo_warning)
    elif scores_em_jogo:
        st.caption(f"Scores em jogo: {', '.join(scores_em_jogo)}.")
    else:
        st.caption("Nenhum score em jogo marcado ainda.")

with st.container(border=True):
    st.subheader("Complementaridade vs. score vigente/em uso")
    reference_score = resolve_reference_score(roles, ks_series)
    candidates = [s for s in scores_em_jogo if s != reference_score] if reference_score else []
    if reference_score is None:
        st.info("Calcule o KS de ao menos um score para ver a complementaridade.")
    elif not candidates:
        st.info(
            "Marque acima ao menos um score em jogo diferente da referência "
            f"({reference_score}) para ver a complementaridade."
        )
    else:
        try:
            complementarity_df = session.compute_complementarity_table(
                subset, state.df_hash, population, tuple(candidates), reference_score, target_col
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
            st.error(f"Não foi possível calcular a complementaridade: {exc}")
        else:
            ref_kind = "score vigente" if roles.vigente_score == reference_score else "score em uso"
            st.caption(f"Referência: {reference_score} ({ref_kind}).")
            tables.dataframe(
                complementarity_df,
                percent_cols=(
                    "correlation",
                    "ks_candidate",
                    "ks_reference",
                    "ks_combined",
                    "marginal_lift",
                ),
            )
            st.caption(
                "Veredito: repechar (filtro secundário) / matriciar (grade) / substituir."
            )

try:
    table_df = session.compute_ks_table(
        subset, state.df_hash, population, table_score, target_col, bins
    )
except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
    st.error(f"Não foi possível calcular a tabela de decis: {exc}")
    st.stop()

tab_chart, tab_table = st.tabs(["Curva KS", "Tabela de decis por bucket"])
with tab_chart:
    st.plotly_chart(
        charts.ks_curve(table_df), use_container_width=True, config={"displayModeBar": False}
    )
with tab_table:
    st.caption(f"Tabela de decis por bucket — {table_score}")
    tables.dataframe(table_df, percent_cols=("Bad_Rate", "Cum_Bads", "Cum_Goods", "KS"))

with st.expander("Comparação de KS entre todos os scores"):
    ks_comparison = ks_series.rename("KS").reset_index().rename(columns={"index": "Score"})
    tables.dataframe(ks_comparison, percent_cols=("KS",))
