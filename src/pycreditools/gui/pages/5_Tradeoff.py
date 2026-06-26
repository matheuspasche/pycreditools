"""Trade-off page — efficient frontier + scenario picker (PRD 06)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles, require_policy
from pycreditools.studio import charts
from pycreditools.studio.analyses import cutoff_range, policy_kpis, tradeoff_scenarios
from pycreditools.studio.policy_builder import apply_cutoff_to_rows, build_policy, policy_cache_key

_SCENARIO_LABELS = {"conservador": "Conservador", "agressivo": "Agressivo", "neutro": "Neutro"}

st.title("Trade-off")
st.caption("Fronteira eficiente e cenários conservador / neutro / agressivo.")

entry = require_policy()
guard_roles("applicant_id_col", "score_cols")

state = get_state()
roles = state.roles

with st.container(border=True):
    col_scores, col_steps, col_population = st.columns([2, 1, 1])
    with col_scores:
        selected_scores = st.multiselect(
            "Scores a varrer", roles.score_cols, default=roles.score_cols, key="tradeoff_scores"
        )
    with col_steps:
        steps = st.slider("Nº de passos", min_value=5, max_value=60, value=35, key="tradeoff_steps")
    with col_population:
        population, subset = render_population_selector(
            state.df, roles, key="tradeoff_population", default="DEV"
        )

    with st.expander("Também variar (opcional)"):
        stress_values = None
        if st.toggle("Fator de stress", key="tradeoff_vary_stress"):
            s_min, s_max = st.slider(
                "Intervalo do fator",
                1.0,
                5.0,
                value=(1.0, 1.5),
                step=0.05,
                key="tradeoff_stress_range",
            )
            s_steps = st.slider("Passos do fator", 2, 10, value=3, key="tradeoff_stress_steps")
            stress_values = np.linspace(s_min, s_max, s_steps).tolist()

        rate_rows = [r for r in entry.rows if r["type"] == "rate"]
        rate_stage_name, rate_values = None, None
        if rate_rows and st.toggle("Taxa base de um estágio", key="tradeoff_vary_rate"):
            rate_names = [r["name"] for r in rate_rows]
            rate_stage_name = st.selectbox("Estágio", rate_names, key="tradeoff_rate_stage")
            r_min, r_max = st.slider(
                "Intervalo da taxa", 0.0, 1.0, value=(0.3, 0.7), key="tradeoff_rate_range"
            )
            r_steps = st.slider("Passos da taxa", 2, 10, value=3, key="tradeoff_rate_steps")
            rate_values = np.linspace(r_min, r_max, r_steps).tolist()

    parallel = st.toggle("Paralelo", value=False, key="tradeoff_parallel")

if not selected_scores:
    st.info("Selecione ao menos um score para varrer.")
    st.stop()

if population == "Todos" and steps * len(selected_scores) > 80:
    st.caption("⚠️ Rodando na base completa com muitos passos — pode demorar.")

res_list = []
for score in selected_scores:
    values = cutoff_range(subset, score, steps)
    try:
        res = session.run_tradeoff(
            subset,
            state.df_hash,
            population,
            entry.policy,
            policy_cache_key(entry.policy),
            score,
            tuple(values),
            tuple(stress_values) if stress_values else None,
            rate_stage_name,
            tuple(rate_values) if rate_values else None,
            parallel,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível rodar o trade-off para {score}: {exc}")
        st.stop()
    res_list.append(res)
res_all = pd.concat(res_list, ignore_index=True)

legacy_kpis = policy_kpis(state.legacy_sim) if state.legacy_sim is not None else None
has_legacy = legacy_kpis is not None and legacy_kpis["bad_rate"] is not None
legacy_point = (legacy_kpis["approval_rate"], legacy_kpis["bad_rate"]) if has_legacy else None

primary_score = (
    roles.primary_score_col if roles.primary_score_col in selected_scores else selected_scores[0]
)
res_primary = res_all[res_all["Score_Model"] == primary_score]

scenarios = (
    tradeoff_scenarios(res_primary, legacy_point[0], legacy_point[1]) if has_legacy else None
)
scenario_points = (
    {
        _SCENARIO_LABELS[k]: (row["approval_rate"], row["default_rate"])
        for k, row in scenarios.items()
    }
    if scenarios
    else None
)

st.plotly_chart(
    charts.frontier(res_all, hue_col="Score_Model", legacy=legacy_point, scenarios=scenario_points),
    use_container_width=True,
    config={"displayModeBar": False},
)

st.subheader("Cenários executivos")
if not has_legacy:
    st.info(
        "Defina um baseline na página Simulação para calcular os cenários executivos "
        "(conservador / agressivo / neutro)."
    )
else:
    cols = st.columns(3)
    for col, key in zip(cols, ["conservador", "agressivo", "neutro"]):
        row = scenarios[key]
        with col, st.container(border=True):
            st.caption(_SCENARIO_LABELS[key])
            st.markdown(f"**Cutoff ({primary_score}):** {tables.score(row['Cutoff'])}")
            st.markdown(f"Aprovação: {tables.pct(row['approval_rate'])}")
            st.markdown(f"Inadimplência: {tables.pct(row['default_rate'])}")

    apply_col, button_col = st.columns([2, 1])
    with apply_col:
        chosen = st.radio(
            "Cenário a aplicar",
            ["conservador", "neutro", "agressivo"],
            format_func=lambda k: _SCENARIO_LABELS[k],
            horizontal=True,
            key="tradeoff_chosen_scenario",
        )
    with button_col:
        st.markdown("&nbsp;")
        if st.button("Aplicar cutoff ao Policy Studio", use_container_width=True):
            cutoff_value = float(scenarios[chosen]["Cutoff"])
            entry.rows = apply_cutoff_to_rows(entry.rows, primary_score, cutoff_value)
            rating_recipe = state.rating_result.recipe if state.rating_result is not None else None
            entry.policy = build_policy(roles, entry.rows, rating_recipe=rating_recipe)
            st.toast(
                f"Cutoff de {primary_score} aplicado à política "
                f"'{entry.name}': {tables.score(cutoff_value)}"
            )

with st.expander("Tabela de resultados"):
    tables.dataframe(res_all, percent_cols=("approval_rate", "default_rate"))
