"""Crash Test page — breakeven stress factor (PRD 10)."""

from __future__ import annotations

import numpy as np
import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles, require_policy
from pycreditools.studio import analyses, charts
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import policy_cache_key

st.title("Crash Test")
st.caption("Fator de estresse de equilíbrio (breakeven) frente à inadimplência legada.")

entry = require_policy()
guard_roles("applicant_id_col", "score_cols")

state = get_state()
roles = state.roles


def _auto_legacy_bad_rate() -> tuple[float | None, int | None]:
    """Legacy bad rate from `legacy_sim`, falling back to the observed hired bad rate."""
    if state.legacy_sim is not None:
        kpis = analyses.policy_kpis(state.legacy_sim)
        if kpis["bad_rate"] is not None:
            return float(kpis["bad_rate"]), None
    if roles.current_hired_col and roles.actual_default_col:
        try:
            hired = population_filter(state.df, roles, "Contratados")
        except ValueError:
            return None, None
        observed = hired[roles.actual_default_col].dropna()
        if len(observed):
            return float(observed.mean()), len(observed)
    return None, None


auto_legacy_bad_rate, observed_n = _auto_legacy_bad_rate()

with st.container(border=True):
    col_range, col_steps, col_population = st.columns([2, 1, 1])
    with col_range:
        f_min, f_max = st.slider(
            "Intervalo do fator de agravamento",
            1.0,
            10.0,
            value=(1.0, 10.0),
            step=0.1,
            key="crash_range",
        )
    with col_steps:
        steps = st.slider("Nº de passos", min_value=5, max_value=80, value=37, key="crash_steps")
    with col_population:
        population, subset = render_population_selector(
            state.df, roles, key="crash_population", default="DEV"
        )

    col_legacy, col_parallel = st.columns([2, 1])
    with col_legacy:
        legacy_bad_rate = st.number_input(
            "Inadimplência legada (override)",
            min_value=0.0,
            max_value=1.0,
            value=float(auto_legacy_bad_rate) if auto_legacy_bad_rate is not None else 0.0,
            step=0.001,
            format="%.4f",
            key="crash_legacy_bad_rate",
        )
    with col_parallel:
        st.markdown("&nbsp;")
        parallel = st.toggle("Paralelo", value=False, key="crash_parallel")

if auto_legacy_bad_rate is None:
    st.info(
        "Sem baseline definido (página Simulação) nem coluna de contratação observada — "
        "informe a inadimplência legada manualmente."
    )
elif observed_n is not None:
    st.caption(f"Inadimplência legada observada em {observed_n:,} contratos.")

if subset.empty:
    st.info("População selecionada está vazia.")
    st.stop()

factors = np.linspace(f_min, f_max, steps).tolist()
try:
    crash_df = session.run_crash_test(
        subset,
        state.df_hash,
        population,
        entry.policy,
        policy_cache_key(entry.policy),
        tuple(factors),
        parallel,
    )
except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
    st.error(f"Não foi possível rodar o crash test: {exc}")
    st.stop()

breakeven = analyses.breakeven_aggravation_factor(crash_df, legacy_bad_rate)

kpi.kpi_row(
    [
        {
            "label": "Fator de breakeven",
            "value": f"{breakeven:.2f}×" if breakeven is not None else "Não atingido",
        }
    ]
)

if breakeven is not None:
    st.markdown(
        f"A PD real dos swap-ins precisaria ser **{breakeven:.1f}×** pior que o modelo "
        "para igualar a inadimplência legada."
    )
    if breakeven >= 3.0:
        st.caption("✅ Política conservadora — boa margem de segurança frente ao agravamento.")
    else:
        st.caption("⚠️ Política sensível ao agravamento — margem de segurança estreita.")
else:
    st.warning(
        "A inadimplência não atinge o nível legado no intervalo testado — "
        "aumente o fator máximo."
    )

st.plotly_chart(
    charts.crash(crash_df, legacy_bad_rate=legacy_bad_rate, breakeven=breakeven),
    use_container_width=True,
    config={"displayModeBar": False},
)

with st.expander("Tabela de resultados"):
    tables.dataframe(crash_df, percent_cols=("default_rate", "approval_rate"))
