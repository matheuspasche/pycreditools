"""Risk Screening page — sub-segments inside ratings ranked by IV (PRD 09)."""

from __future__ import annotations

import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles
from pycreditools.studio import charts
from pycreditools.studio.analyses import (
    attach_rating,
    existing_rating_columns,
    screening_boundaries_table,
    screening_candidate_columns,
    screening_detail_table,
    screening_heatmap_table,
    screening_iv_table,
    screening_low_coverage_variables,
)

st.title("Screening")
st.caption("Sub-segmentos dentro dos ratings, ranqueados por IV.")
guard_roles("actual_default_col")

state = get_state()
roles = state.roles
df = state.df
target_col = roles.actual_default_col
has_active_rating = state.rating_result is not None

with st.container(border=True):
    col_source, col_population = st.columns(2)
    with col_source:
        source_options = (["Rating ativo"] if has_active_rating else []) + ["Coluna existente"]
        source = st.radio("Base do rating", source_options, key="scr_source", horizontal=True)
    with col_population:
        population, subset = render_population_selector(
            df, roles, key="scr_population", default="Aprovados"
        )

if source == "Rating ativo":
    population_df = attach_rating(
        subset, state.rating_result, state.rating_labels, rating_col="Rating"
    )
    base_risk_col = "Rating"
else:
    rating_column_options = existing_rating_columns(df)
    if not rating_column_options:
        st.info(
            "Nenhum rating ativo e nenhuma coluna existente parece ser um rating. "
            "Construa um na página Risk Grouping ou escolha outra base."
        )
        st.stop()
    base_risk_col = st.selectbox(
        "Coluna de rating existente", rating_column_options, key="scr_base_col"
    )
    population_df = subset

effective_population = population_df.dropna(subset=[target_col, base_risk_col])
if effective_population.empty:
    st.warning("Nenhuma linha com o alvo observado na população selecionada.")
    st.stop()

st.caption(
    f"N efetivo (alvo observado): {tables.thousands(len(effective_population))} "
    f"de {tables.thousands(len(population_df))} na população '{population}'."
)

with st.container(border=True):
    candidate_options = [c for c in screening_candidate_columns(df, roles) if c != base_risk_col]
    candidate_cols = st.multiselect(
        "Variáveis candidatas", candidate_options, key="scr_candidates"
    )

    col_bins, col_method, col_parallel = st.columns(3)
    with col_bins:
        n_bins = st.slider("Bins", 5, 30, value=10, key="scr_bins")
    with col_method:
        method = st.radio(
            "Método",
            ["quantiles", "ward"],
            key="scr_method",
            format_func=lambda m: "Quantis" if m == "quantiles" else "Ward",
        )
    with col_parallel:
        parallel = st.toggle("Paralelo", value=False, key="scr_parallel")

if not candidate_cols:
    st.info("Selecione ao menos uma variável candidata.")
    st.stop()

try:
    result = session.screen_segments(
        effective_population,
        state.df_hash,
        population,
        base_risk_col,
        tuple(candidate_cols),
        target_col,
        n_bins,
        method,
        parallel,
    )
except ValueError as exc:
    st.error(f"Não foi possível rodar o screening: {exc}")
    st.stop()

state.screening_result = result

low_coverage = screening_low_coverage_variables(result, candidate_cols)
if low_coverage:
    st.caption(f"Cobertura reduzida (poucos valores únicos) em: {', '.join(low_coverage)}.")

iv_table = screening_iv_table(result)

kpi.kpi_row(
    [
        {"label": "Variáveis avaliadas", "value": len(candidate_cols)},
        {
            "label": "Maior IV",
            "value": f"{iv_table['iv'].iloc[0]:.3f}" if not iv_table.empty else "—",
        },
        {
            "label": "Top variável",
            "value": iv_table["variable"].iloc[0] if not iv_table.empty else "—",
        },
    ]
)

tab_charts, tab_tables = st.tabs(["Gráficos", "Tabelas"])
with tab_charts:
    st.plotly_chart(
        charts.bars(iv_table.set_index("variable")["iv"], percent=False),
        use_container_width=True,
        config={"displayModeBar": False},
    )

with tab_tables:
    st.subheader("Ranking de IV")
    tables.dataframe(iv_table, int_cols=("volume",))

st.divider()
st.subheader("Detalhe por variável")
variable = st.selectbox("Variável", candidate_cols, key="scr_detail_variable")

detail = screening_detail_table(result, population_df, variable, base_risk_col, target_col)
boundaries = screening_boundaries_table(result, variable)

if detail.empty:
    st.info("Sem dados suficientes para o detalhe desta variável.")
else:
    tab_detail_charts, tab_detail_tables = st.tabs(["Gráficos", "Tabelas"])
    with tab_detail_charts:
        heatmap_table = screening_heatmap_table(detail, base_risk_col)
        st.plotly_chart(
            charts.heatmap(heatmap_table, title=f"Bad rate por tier x sub-segmento — {variable}"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with tab_detail_tables:
        st.caption("Limites dos sub-segmentos")
        tables.dataframe(boundaries)
        st.caption("Bad rate por tier x sub-segmento")
        tables.dataframe(detail, percent_cols=("bad_rate",), int_cols=("volume",))
