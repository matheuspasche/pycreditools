"""Simulation page — run policy, quadrants, swap analysis (PRD 05)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import render_population_selector
from pycreditools.gui.session import get_state, guard_roles, require_policy
from pycreditools.studio import analyses, charts
from pycreditools.studio.policy_builder import legacy_cutoff_policy, policy_cache_key

st.title("Simulação")
st.caption("Rode a política, veja aprovação/inadimplência e os quadrantes de swap.")

entry = require_policy()
guard_roles("applicant_id_col", "score_cols")

state = get_state()
roles = state.roles

with st.container(border=True):
    ctrl_method, ctrl_population, ctrl_baseline, ctrl_legacy = st.columns(4)
    with ctrl_method:
        method = st.radio(
            "Método",
            ["analytical", "stochastic"],
            index=0,
            key="sim_method",
            format_func=lambda m: "Analítico" if m == "analytical" else "Estocástico",
        )
    with ctrl_population:
        population, subset = render_population_selector(
            state.df, roles, key="sim_population", default="Todos"
        )
    if method == "stochastic" and len(subset) > 200_000:
        st.caption(
            "⚠️ Estocástico tende a ser lento em bases grandes — analítico é o padrão."
        )
    with ctrl_baseline:
        st.markdown("&nbsp;")
        if st.button("📌 Definir baseline = política atual", use_container_width=True):
            try:
                state.legacy_sim = session.run_policy_sim(
                    subset,
                    state.df_hash,
                    population,
                    entry.policy,
                    policy_cache_key(entry.policy),
                    method=method,
                )
                st.toast("Baseline definido a partir da política atual.")
            except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                st.error(f"Não foi possível definir o baseline: {exc}")
    with ctrl_legacy:
        st.markdown("&nbsp;")
        if st.button("🏛️ Baseline = cutoff legado (p78)", use_container_width=True):
            legacy = legacy_cutoff_policy(roles, state.df)
            if legacy is None:
                st.warning("Coluna `legacy_score` não encontrada nesta base.")
            else:
                legacy_policy, _ = legacy
                try:
                    state.legacy_sim = session.run_policy_sim(
                        subset,
                        state.df_hash,
                        population,
                        legacy_policy,
                        policy_cache_key(legacy_policy),
                        method=method,
                    )
                    st.toast("Baseline definido com o cutoff legado (p78).")
                except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                    st.error(f"Não foi possível simular o baseline legado: {exc}")

try:
    sim = session.run_policy_sim(
        subset,
        state.df_hash,
        population,
        entry.policy,
        policy_cache_key(entry.policy),
        method=method,
    )
except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
    st.error(f"Não foi possível simular a política: {exc}")
    st.stop()

state.last_sim = sim

sim_df = analyses.attach_rating(sim.data, state.rating_result, state.rating_labels)
has_rating = "Rating" in sim_df.columns

kpis = analyses.policy_kpis(sim)
legacy_kpis = analyses.policy_kpis(state.legacy_sim) if state.legacy_sim is not None else None


def _delta_item(label: str, value: float, legacy_value: float | None, *, fmt, higher_is_good: bool):
    item = {"label": label, "value": fmt(value)}
    if legacy_value is not None:
        diff = value - legacy_value
        item["delta"] = f"{'+' if diff >= 0 else ''}{fmt(diff)} vs. baseline"
        item["delta_good"] = (diff >= 0) == higher_is_good
    return item


kpi_items = [
    _delta_item(
        "Taxa de aprovação",
        kpis["approval_rate"],
        legacy_kpis["approval_rate"] if legacy_kpis else None,
        fmt=tables.pct,
        higher_is_good=True,
    ),
    _delta_item(
        "Volume contratado",
        kpis["approved_volume"],
        legacy_kpis["approved_volume"] if legacy_kpis else None,
        fmt=tables.thousands,
        higher_is_good=True,
    ),
]
if kpis["pre_rate_volume"] is not None:
    kpi_items.append(
        {
            "label": "Volume aprovado (pré-taxa)",
            "value": tables.thousands(kpis["pre_rate_volume"]),
        }
    )
if kpis["bad_rate"] is not None:
    kpi_items.append(
        _delta_item(
            "Inadimplência simulada",
            kpis["bad_rate"],
            legacy_kpis["bad_rate"] if legacy_kpis else None,
            fmt=tables.pct,
            higher_is_good=False,
        )
    )
kpi.kpi_row(kpi_items)

is_standalone = roles.current_approval_col is None
if is_standalone:
    st.info(
        "Modo standalone (sem coluna de aprovação histórica `current_approval_col`): "
        "quadrantes de swap não estão disponíveis."
    )
else:
    st.subheader("Quadrantes de swap")
    quad = analyses.quadrant_table(sim)
    quad_by_scenario = {row["scenario"]: row for _, row in quad.iterrows()}

    _LABELS = {
        "keep_in": "Keep In",
        "swap_in": "Swap In",
        "swap_out": "Swap Out",
        "keep_out": "Keep Out",
    }
    _ACCENTS = {"swap_in": "var(--accent)", "swap_out": "var(--danger)"}

    def _quadrant_card(container, scenario: str) -> None:
        with container, st.container(border=True):
            color = _ACCENTS.get(scenario)
            label = _LABELS[scenario]
            html = f"<span style='color:{color}'>{label}</span>" if color else label
            st.markdown(html, unsafe_allow_html=True)
            row = quad_by_scenario.get(scenario)
            if row is None:
                st.caption("Sem dados")
                return
            st.markdown(f"**{tables.thousands(row['Hired'])}** contratados")
            bad_rate = row["Bad_Rate"]
            st.caption(f"Bad rate: {tables.pct(bad_rate) if pd.notna(bad_rate) else 'N/A'}")

    row1 = st.columns(2)
    row2 = st.columns(2)
    _quadrant_card(row1[0], "keep_in")
    _quadrant_card(row1[1], "swap_in")
    _quadrant_card(row2[0], "swap_out")
    _quadrant_card(row2[1], "keep_out")
    st.caption(
        "Keep In/Swap Out usam inadimplência observada; Swap In usa a PD simulada (agravada); "
        "Keep Out não tem dado observável."
    )

    with st.expander("Tabela de quadrantes"):
        tables.dataframe(quad, percent_cols=("Bad_Rate",))

    st.subheader("Swap-in por rating")
    if has_rating:
        si_rating = analyses.swap_in_by_rating(sim_df, rating_col="Rating")
        if si_rating.empty:
            st.info("Nenhum swap-in nesta simulação.")
        else:
            tab_chart, tab_table = st.tabs(["Gráfico", "Tabela"])
            with tab_chart:
                st.plotly_chart(
                    charts.rating_bars(si_rating),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            with tab_table:
                tables.dataframe(si_rating, percent_cols=("Vol_Pct", "Inad_Stressed"))

        if roles.segment_col:
            st.subheader(f"Swap-in por rating × {roles.segment_col}")
            crosstab = analyses.swap_in_by_segment(sim_df, "Rating", roles.segment_col)
            if crosstab.empty:
                st.info("Sem swap-ins para cruzar com o segmento.")
            else:
                title = f"Volume swap-in: Rating × {roles.segment_col}"
                st.plotly_chart(
                    charts.heatmap(crosstab, title=title),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
    else:
        st.info(
            "Sem rating ajustado ainda — veja a página Risk Grouping "
            "para detalhar o swap-in por rating."
        )

    if state.legacy_sim is not None:
        st.subheader("Comparação vs. baseline")
        try:
            comparison = analyses.compare_with_baseline(sim, state.legacy_sim)
            tables.dataframe(comparison["metrics"], percent_cols=("Old", "New", "Delta_Abs"))
            st.caption(
                f"Razão swap-in / keep-in: {comparison['ratio']:.2f}"
                if pd.notna(comparison["ratio"])
                else "Razão swap-in / keep-in: N/A"
            )
            st.markdown("**Delta P&L**")
            delta = analyses.delta_table(sim, state.legacy_sim)
            tables.dataframe(delta)
        except ValueError as exc:
            st.warning(str(exc))

st.subheader("Prévia de decisões")
rating_recipe = state.rating_result.recipe if state.rating_result is not None else None
preview = analyses.decision_preview(sim, rating_recipe, state.rating_labels)
tables.dataframe(preview)
