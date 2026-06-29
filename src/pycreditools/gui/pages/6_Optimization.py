"""Optimization page — grid-search cutoffs + Pareto frontier (PRD 07)."""

from __future__ import annotations

import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles, require_policy
from pycreditools.studio import charts
from pycreditools.studio.analyses import find_equivalent, optimization_grid_size
from pycreditools.studio.policy_builder import apply_cutoffs_to_rows, build_policy, policy_cache_key

_GRID_WARNING_THRESHOLD = 2000

st.title("Otimização")
st.caption("Busca em grade dos melhores cortes e fronteira de Pareto.")

entry = require_policy()
guard_roles("applicant_id_col", "score_cols")

state = get_state()
roles = state.roles
policy = entry.policy
score_cols = list(policy.score_cols)

if not score_cols:
    st.warning("A política ativa não define nenhum score em `score_cols`.")
    st.stop()

st.caption(f"Scores a otimizar: {', '.join(score_cols)}")

with st.container(border=True):
    col_steps, col_target, col_min = st.columns(3)
    with col_steps:
        cutoff_steps = st.slider("Passos por score", 1, 30, value=10, key="opt_steps")
    with col_target:
        target_default_rate = st.slider(
            "Inadimplência máxima aceitável", 0.0, 1.0, value=0.05, step=0.01, key="opt_target"
        )
    with col_min:
        min_approval_rate = st.slider(
            "Aprovação mínima aceitável", 0.0, 1.0, value=0.30, step=0.01, key="opt_min_approval"
        )

    col_pct, col_method, col_population = st.columns(3)
    with col_pct:
        percentile_range = st.slider(
            "Percentis (limites da busca)", 0.0, 1.0, value=(0.05, 0.95), key="opt_percentiles"
        )
    with col_method:
        method = st.radio(
            "Método",
            ["analytical", "stochastic"],
            index=0,
            key="opt_method",
            format_func=lambda m: "Analítico" if m == "analytical" else "Estocástico",
        )
    with col_population:
        population, subset = render_population_selector(
            state.df, roles, key="opt_population", default="DEV"
        )

    parallel = st.toggle(
        "Paralelo (apenas estocástico)",
        value=False,
        disabled=method != "stochastic",
        key="opt_parallel",
    )

grid_size = optimization_grid_size(score_cols, cutoff_steps)
st.caption(
    f"Tamanho da grade: {grid_size:,} combinações "
    f"({cutoff_steps} passos ^ {len(score_cols)} score(s))."
)
if grid_size > _GRID_WARNING_THRESHOLD:
    confirmed = st.checkbox(
        f"⚠️ A grade tem {grid_size:,} combinações e pode demorar. Confirmar mesmo assim?",
        key="opt_confirm_large_grid",
    )
    if not confirmed:
        st.warning("Reduza o nº de passos ou de scores na política, ou confirme para continuar.")
        st.stop()

if subset.empty:
    st.info("Nenhum dado na população selecionada.")
    st.stop()

try:
    result = session.run_optimization(
        subset,
        state.df_hash,
        population,
        policy,
        policy_cache_key(policy),
        cutoff_steps,
        target_default_rate,
        min_approval_rate,
        method,
        parallel,
        percentile_range,
    )
except ValueError as exc:
    st.error(f"Não foi possível otimizar: {exc}")
    st.stop()

chips = " · ".join(
    f"{score} ≥ {tables.score(value)}" for score, value in result.best_combination.items()
)
kpi.kpi_row(
    [
        {"label": "Melhor combinação", "value": chips or "—"},
        {"label": "Aprovação", "value": tables.pct(result.metrics["overall_approval_rate"])},
        {"label": "Inadimplência", "value": tables.pct(result.metrics["overall_default_rate"])},
        {"label": "Score trade-off", "value": f"{result.metrics['tradeoff_score']:.3f}"},
        {
            "label": "Restrições",
            "value": "✅ Atendidas" if result.metrics["constraints_met"] else "⚠️ Não atendidas",
        },
    ]
)

st.plotly_chart(
    charts.pareto(
        result.all_results,
        result.pareto_frontier,
        (result.metrics["overall_approval_rate"], result.metrics["overall_default_rate"]),
        constraints=(target_default_rate, min_approval_rate),
    ),
    use_container_width=True,
    config={"displayModeBar": False},
)

if st.button("Aplicar melhor combinação à Bancada"):
    entry.rows = apply_cutoffs_to_rows(entry.rows, result.best_combination)
    rating_recipe = state.rating_result.recipe if state.rating_result is not None else None
    entry.policy = build_policy(roles, entry.rows, rating_recipe=rating_recipe)
    st.toast(f"Melhor combinação aplicada à política '{entry.name}'.")

st.subheader("Encontrar equivalente")
with st.container(border=True):
    col_metric, col_value, col_tol = st.columns(3)
    with col_metric:
        target_metric = st.selectbox(
            "Métrica alvo",
            ["approval_rate", "default_rate"],
            key="opt_eq_metric",
            format_func=lambda m: "Taxa de aprovação" if m == "approval_rate" else "Inadimplência",
        )
    with col_value:
        target_value = st.slider("Valor alvo", 0.0, 1.0, value=0.20, step=0.01, key="opt_eq_value")
    with col_tol:
        tolerance = st.slider(
            "Tolerância", 0.001, 0.2, value=0.01, step=0.001, key="opt_eq_tolerance"
        )
    equivalent = find_equivalent(
        result, target_metric=target_metric, target_value=target_value, tolerance=tolerance
    )
    tables.dataframe(equivalent, percent_cols=("overall_approval_rate", "overall_default_rate"))

with st.expander("Todos os resultados"):
    tables.dataframe(
        result.all_results, percent_cols=("overall_approval_rate", "overall_default_rate")
    )
