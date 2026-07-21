"""Bancada — the live policy-design workbench (ADR 0001, Bancada tracer #1 / #26)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.policy_builder import render_policy_manager, render_rule_builder
from pycreditools.gui.components.population import render_population_selector_v2
from pycreditools.gui.session import get_state, guard_roles
from pycreditools.studio import charts
from pycreditools.studio.analyses import (
    aggregate_funnel,
    aggregate_segment_kpis,
    compare_vs_base,
    current_cutoff_value,
    derive_survivor_rating,
    exposure_kpis,
    get_shortlisted_scores,
    label_ratings_by_pd,
    policy_kpis,
    policy_vintage_comparison,
    risk_tier_distribution,
    run_segmented_sim,
    segment_kpi_table,
    survivor_population,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.detection import detect_tier
from pycreditools.studio.models import PolicyEntry, StudioState
from pycreditools.studio.policy_builder import (
    apply_cutoffs_to_rows,
    build_policy,
    policy_cache_key,
    roles_cache_key,
)

_AGGRAVATION_MIN, _AGGRAVATION_MAX = 1.0, 10.0

_QUADRANT_LABELS = {
    "keep_in": "Keep In",
    "swap_in": "Swap In",
    "swap_out": "Swap Out",
    "keep_out": "Keep Out",
}
_QUADRANT_ACCENTS = {"swap_in": "var(--accent)", "swap_out": "var(--danger)"}

st.title("Bancada")
st.caption(
    "Monte a política viva — scores, cortes, filtros e taxas — e veja o funil, a "
    "aprovação e a inadimplência recalcularem a cada ajuste."
)
guard_roles("applicant_id_col", "score_cols")

state = get_state()
roles = state.roles

def _render_suggested_scenarios(state: StudioState, entry: PolicyEntry) -> None:
    """Suggestion-first entry (ADR 0005, issue #30): opens with 2-3 scenarios from
    the optimization engine, run only on the scores em jogo. Picking one applies its
    cutoffs to the live policy; every knob stays freely editable afterwards."""
    shortlisted = get_shortlisted_scores(state)
    if not shortlisted:
        return

    st.subheader("Cenários sugeridos")
    st.caption(
        "Sugestões do motor de otimização sobre os scores em jogo "
        f"({', '.join(shortlisted)}) — escolha uma para começar e ajuste livremente."
    )
    subset = population_filter(state.df, state.roles, "DEV")
    if subset.empty:
        st.info("Sem dados na população DEV para sugerir cenários.")
        return
    try:
        scenarios = session.suggest_scenarios(
            subset,
            state.df_hash,
            "DEV",
            state.roles,
            roles_cache_key(state.roles),
            tuple(shortlisted),
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível sugerir cenários: {exc}")
        return

    cols = st.columns(len(scenarios))
    for col, scenario in zip(cols, scenarios, strict=False):
        with col, st.container(border=True):
            st.markdown(f"**{scenario.name.capitalize()}**")
            st.caption(f"Aprovação: {tables.pct(scenario.approval_rate)}")
            st.caption(f"Inadimplência: {tables.pct(scenario.default_rate)}")
            if st.button(
                "Usar este cenário", key=f"use_scenario_{scenario.name}", use_container_width=True
            ):
                entry.rows = apply_cutoffs_to_rows(entry.rows, scenario.cutoffs)
                st.toast(f"Cenário '{scenario.name}' aplicado à política '{entry.name}'.")
    st.divider()


builder_col, funnel_col = st.columns([1, 1], gap="large")

with builder_col:
    entry = render_policy_manager(state)
    _render_suggested_scenarios(state, entry)
    rows = render_rule_builder(state.df, roles, entry)

    rating_recipe = state.rating_result.recipe if state.rating_result is not None else None
    try:
        policy = build_policy(roles, rows, df=state.df, rating_recipe=rating_recipe)
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível montar a política: {exc}")
        st.stop()

    entry.policy = policy
    stress_rows = [row for row in rows if row["type"] == "stress"]
    entry.flat_stress_factor = stress_rows[-1]["factor"] if stress_rows else None

    try:
        policy.validate(state.df)
        st.success("✅ Política válida para esta base.")
    except ValueError as exc:
        st.warning(f"Política com colunas pendentes: {exc}")

    with st.expander("Resumo da política"):
        st.text(policy.describe())


@st.fragment
def _render_live_funnel() -> None:
    with st.container(border=True):
        periodo, quem, subset = render_population_selector_v2(
            state.df, roles, key="bancada_population", default_periodo="Dev"
        )
        population = f"{periodo}/{quem}"

    try:
        sim = session.run_policy_sim(
            subset, state.df_hash, population, entry.policy, policy_cache_key(entry.policy)
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível simular a política: {exc}")
        return

    state.last_sim = sim
    funnel_df = sim.to_funnel_dataframe()
    kpis = policy_kpis(sim)
    survivors = survivor_population(sim)

    kpi_items = [
        {"label": "Taxa de aprovação", "value": tables.pct(kpis["approval_rate"])},
    ]
    if kpis["take_up_rate"] is not None:
        kpi_items.append(
            {"label": "Taxa de contratação", "value": tables.pct(kpis["take_up_rate"])}
        )
    kpi_items.append(
        {"label": "Volume contratado", "value": tables.thousands(kpis["contracted_volume"])}
    )
    if kpis["default_rate"] is not None:
        kpi_items.append(
            {"label": "Inadimplência simulada", "value": tables.pct(kpis["default_rate"])}
        )
    kpi.kpi_row(kpi_items)
    st.caption(
        f"Sobreviventes aos filtros: {tables.thousands(len(survivors))} de "
        f"{tables.thousands(len(subset))} — é essa população, não a base bruta, "
        "que alimenta o agrupamento de risco."
    )

    tab_chart, tab_table = st.tabs(["Funil", "Tabela"])
    with tab_chart:
        st.plotly_chart(
            charts.funnel(funnel_df, stage_col="Stage", count_col="Passed"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with tab_table:
        tables.dataframe(
            funnel_df,
            percent_cols=("Stage_Pass_Rate", "Cum_Pass_Rate", "Stage_Rej_Rate"),
        )

    _render_segmentation(subset)
    _render_dragcutoff_tradeoff(subset, population)
    _render_comparison_vs_base(sim, subset, population)


def _render_segmentation(subset: pd.DataFrame) -> None:
    """Light business segmentation (ADR 0006, issue #34): an optional toggle sets
    cutoffs per segment value (e.g. channel, store), and the funnel shows the
    aggregate total + a per-segment breakout. Off by default — with the toggle off
    the Bancada behaves exactly like the non-segmented funnel above. Policy stays a
    single object: only the score-in-use's cutoff varies per segment, never a full
    per-segment filter/rate/aggravation structure (deferred)."""
    st.divider()
    st.subheader("Segmentação")
    segment_col = roles.segment_col
    if not segment_col or segment_col not in subset.columns:
        st.caption(
            "Mapeie uma coluna de segmento (ex.: canal, loja) na Ingestion para "
            "habilitar cortes por segmento."
        )
        return

    segment_on = st.toggle(f"Segmentar por '{segment_col}'", key="bancada_segment_toggle")
    if not segment_on:
        return

    score_in_use = entry.policy.calibration_score_col
    if score_in_use is None:
        st.info("Adicione um corte a um score para segmentar por ele.")
        return

    segment_values = sorted(subset[segment_col].dropna().unique().tolist())
    if not segment_values:
        st.caption(f"Sem valores observados em '{segment_col}' nesta população.")
        return

    default_value = current_cutoff_value(entry.policy, score_in_use)
    if default_value is None:
        default_value = float(subset[score_in_use].median())

    st.caption(
        f"Corte de **{score_in_use}** por valor de **{segment_col}** — o restante da "
        "política (filtros, taxas) permanece compartilhado entre os segmentos."
    )
    cutoff_cols = st.columns(len(segment_values))
    segment_cutoffs: dict[str, float] = {}
    for col, value in zip(cutoff_cols, segment_values, strict=False):
        with col:
            segment_cutoffs[value] = st.number_input(
                str(value), value=float(default_value), key=f"segment_cutoff_{value}"
            )

    try:
        sims = run_segmented_sim(subset, roles, rows, score_in_use, segment_cutoffs)
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível simular a segmentação: {exc}")
        return

    aggregate = aggregate_funnel([s.to_funnel_dataframe() for s in sims.values()])
    aggregate_kpis = aggregate_segment_kpis(sims)
    kpi_items = [
        {
            "label": "Taxa de aprovação (agregada)",
            "value": tables.pct(aggregate_kpis["approval_rate"]),
        },
    ]
    if aggregate_kpis["take_up_rate"] is not None:
        kpi_items.append(
            {
                "label": "Taxa de contratação (agregada)",
                "value": tables.pct(aggregate_kpis["take_up_rate"]),
            }
        )
    kpi_items.append(
        {
            "label": "Volume contratado (agregado)",
            "value": tables.thousands(aggregate_kpis["contracted_volume"]),
        }
    )
    if aggregate_kpis["default_rate"] is not None:
        kpi_items.append(
            {
                "label": "Inadimplência simulada (agregada)",
                "value": tables.pct(aggregate_kpis["default_rate"]),
            }
        )
    kpi.kpi_row(kpi_items)

    tab_chart, tab_table = st.tabs(["Funil agregado", "Detalhamento por segmento"])
    with tab_chart:
        st.plotly_chart(
            charts.funnel(aggregate, stage_col="Stage", count_col="Passed"),
            use_container_width=True,
            config={"displayModeBar": False},
            key="segmentation_funnel_chart",
        )
    with tab_table:
        breakout = segment_kpi_table(sims)
        tables.dataframe(
            breakout, percent_cols=("approval_rate", "take_up_rate", "default_rate")
        )


def _render_dragcutoff_tradeoff(subset: pd.DataFrame, population: str) -> None:
    """Trade-off = drag the cutoff (ADR 0001, critique 2.3): the live curve for the
    Bancada's contextual score-in-use, updating as the cutoff slider moves."""
    score_in_use = entry.policy.calibration_score_col
    st.divider()
    st.subheader("Trade-off: arraste o corte")
    if score_in_use is None:
        st.info("Adicione um corte a um score para ver a curva de trade-off.")
        return
    try:
        curve = session.bancada_tradeoff_curve(
            subset, state.df_hash, population, entry.policy, policy_cache_key(entry.policy),
            score_in_use,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível calcular o trade-off de {score_in_use}: {exc}")
        return
    st.caption(f"Score em uso: **{score_in_use}** — aprovação x inadimplência por corte.")
    st.plotly_chart(
        charts.cutoff_tradeoff(curve, score_col=score_in_use),
        use_container_width=True,
        config={"displayModeBar": False},
    )


def _delta_kpi(label: str, value: float, delta: float | None, *, fmt, higher_is_good: bool):
    item = {"label": label, "value": fmt(value)}
    if delta is not None:
        item["delta"] = f"{'+' if delta >= 0 else ''}{fmt(delta)} vs. base"
        item["delta_good"] = (delta >= 0) == higher_is_good
    return item


def _quadrant_card(container, quad_by_scenario: dict, scenario: str) -> None:
    with container, st.container(border=True):
        color = _QUADRANT_ACCENTS.get(scenario)
        label = _QUADRANT_LABELS[scenario]
        html = f"<span style='color:{color}'>{label}</span>" if color else label
        st.markdown(html, unsafe_allow_html=True)
        row = quad_by_scenario.get(scenario)
        if row is None:
            st.caption("Sem dados")
            return
        st.markdown(f"**{tables.thousands(row['Hired'])}** contratados")
        bad_rate = row["Bad_Rate"]
        st.caption(f"Inadimplência: {tables.pct(bad_rate) if pd.notna(bad_rate) else 'N/A'}")


def _render_aggravation_game(
    subset: pd.DataFrame, population: str, base_bad_rate: float | None
) -> None:
    """Aggravation game (ADR 0001, critique 2.7): pull the flat stress factor until
    the candidate breaks even vs. the base — "even so, can I still approve?". Folds
    the old Crash Test page into the Bancada."""
    st.divider()
    st.subheader("Jogo de agravamento")
    st.caption(
        "Agrave a PD por um fator de stress flat e veja a inadimplência resultante "
        "frente à base, e o fator de equilíbrio (breakeven)."
    )
    current_factor = st.slider(
        "Fator de agravamento",
        _AGGRAVATION_MIN,
        _AGGRAVATION_MAX,
        value=1.0,
        step=0.05,
        key="bancada_aggravation_factor",
    )
    try:
        result = session.aggravation_game(
            subset, state.df_hash, population, entry.policy, policy_cache_key(entry.policy),
            current_factor, base_bad_rate,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível rodar o jogo de agravamento: {exc}")
        return

    if result.get("has_estimated_pd"):
        st.info(
            "Esta base usa PD estimada como verdade. O agravamento escala essa PD pelo fator "
            "antes da simulação — a curva responde ao slider, mas o número reflete uma PD "
            "ajustada, não um stress sobre inadimplência observada."
        )
    breakeven = result["breakeven_factor"]
    kpi_items = [
        {
            "label": "Inadimplência no fator atual",
            "value": tables.pct(result["current_default_rate"]),
        },
        {
            "label": "Fator de breakeven",
            "value": (
                f"{breakeven:.2f}×"
                if breakeven is not None
                else f"Não atingido (até {_AGGRAVATION_MAX:.0f}×)"
            ),
        },
    ]
    kpi.kpi_row(kpi_items)

    if base_bad_rate is None:
        st.caption("Sem base de comparação (Tier C) — resultado standalone, sem breakeven.")
    elif breakeven is not None:
        verdict = (
            "✅ ainda aprovável"
            if current_factor < breakeven
            else "⚠️ já no ponto de equilíbrio ou além"
        )
        st.caption(f"{verdict} frente à inadimplência da base.")
    else:
        st.caption(
            f"Breakeven não atingido na faixa de 1× a {_AGGRAVATION_MAX:.0f}× — "
            "a política é robusta ao stress máximo testado."
        )

    st.plotly_chart(
        charts.crash(result["curve"], legacy_bad_rate=base_bad_rate, breakeven=breakeven),
        use_container_width=True,
        config={"displayModeBar": False},
    )


def _render_depth_section(
    sim, tier: str, comparison: dict | None = None
) -> None:
    """Risk/time/exposure depth (ADR 0001, 0004, 0007; issue #33, #39): risk-tier
    distribution of the swap groups re-fitted on current survivors, candidate-vs-base
    behaviour over vintages, and a risk-exposure KPI.

    Pass `comparison` (from `compare_vs_base`) to avoid redundant recomputation of
    `policy_kpis`/`base_outcome` inside `exposure_kpis`.
    """
    st.divider()
    st.subheader("Profundidade: risco, tempo e exposição")

    st.markdown("**Distribuição de risco dos grupos de swap**")
    survivor_rating = derive_survivor_rating(sim, roles)
    if survivor_rating is None:
        st.caption(
            "Sem dados de inadimplência observada nos sobreviventes — "
            "não é possível re-derivar o rating sobre esta população."
        )
    else:
        survivor_labels = label_ratings_by_pd(survivor_rating, roles.actual_default_col)
        n_survivors = len(survivor_population(sim))
        st.caption(
            f"Rating re-derivado sobre os {tables.thousands(n_survivors)} sobreviventes "
            "correntes — os rótulos (A, B, …) são relativos a esta população, não à base bruta."
        )
        tiers = risk_tier_distribution(sim, survivor_rating, survivor_labels)
        if tiers.empty:
            st.caption("Sem grupos de swap para detalhar por rating nesta comparação.")
        else:
            tables.dataframe(tiers, percent_cols=("Bad_Rate",))

    st.markdown("**Candidata x base por safra**")
    vintage = policy_vintage_comparison(sim, roles)
    if vintage.empty:
        st.caption("Sem coluna de safra mapeada — não é possível ver a evolução por vintage.")
    else:
        st.plotly_chart(
            charts.vintage_stability(
                vintage,
                time_col=roles.time_col,
                rating_col="series",
                rate_col="default_rate",
                oot_date=roles.oot_date,
            ),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    exposure = exposure_kpis(sim, roles, tier, comparison=comparison)
    kpi_items = []
    if exposure["candidate_bad_volume"] is not None:
        item = {
            "label": "Volume mau esperado (candidata)",
            "value": tables.thousands(exposure["candidate_bad_volume"]),
        }
        if exposure["delta"] is not None:
            delta = exposure["delta"]
            item["delta"] = f"{'+' if delta >= 0 else ''}{tables.thousands(delta)} vs. base"
            item["delta_good"] = delta <= 0
        kpi_items.append(item)
    if exposure["base_bad_volume"] is not None:
        kpi_items.append(
            {
                "label": "Volume mau esperado (base)",
                "value": tables.thousands(exposure["base_bad_volume"]),
            }
        )
    if kpi_items:
        kpi.kpi_row(kpi_items)
    else:
        st.caption("Sem inadimplência observável para estimar a exposição.")


def _render_comparison_vs_base(sim, subset: pd.DataFrame, population: str) -> None:
    """Comparison-vs-base readout (ADR 0001 bullets 5-7, ADR 0002): tier-adapted
    delta + swap quadrants, folding the old Simulation page into the Bancada."""
    st.divider()
    st.subheader("Comparação vs. base")

    tier = detect_tier(roles, sim.data).tier
    comparison = compare_vs_base(sim, roles, tier)

    if tier == "C":
        st.info(
            "Tier C — nenhuma base de comparação foi mapeada (sem aprovação vigente "
            "nesta base): os quadrantes de swap não estão disponíveis. O resultado "
            "acima é standalone, com a PD vindo da coluna de PD estimada."
        )
        _render_depth_section(sim, tier, comparison=comparison)
        _render_aggravation_game(subset, population, None)
        return

    candidate, base, delta = comparison["candidate"], comparison["base"], comparison["delta"]
    delta_items = [
        _delta_kpi(
            "Taxa de aprovação",
            candidate["approval_rate"],
            delta["approval_rate"],
            fmt=tables.pct,
            higher_is_good=True,
        )
    ]
    if candidate["default_rate"] is not None and base["default_rate"] is not None:
        delta_items.append(
            _delta_kpi(
                "Inadimplência",
                candidate["default_rate"],
                delta["default_rate"],
                fmt=tables.pct,
                higher_is_good=False,
            )
        )
    # Candidate-only figures: no delta — the base is a decision column and does not know
    # who contracted (ADR 0008).
    if candidate["take_up_rate"] is not None:
        delta_items.append(
            {"label": "Taxa de contratação", "value": tables.pct(candidate["take_up_rate"])}
        )
    delta_items.append(
        {"label": "Volume contratado", "value": tables.thousands(candidate["contracted_volume"])}
    )
    kpi.kpi_row(delta_items)

    quad = comparison["quadrants"]
    quad_by_scenario = {row["scenario"]: row for _, row in quad.iterrows()}
    row1 = st.columns(2)
    row2 = st.columns(2)
    _quadrant_card(row1[0], quad_by_scenario, "keep_in")
    _quadrant_card(row1[1], quad_by_scenario, "swap_in")
    _quadrant_card(row2[0], quad_by_scenario, "swap_out")
    _quadrant_card(row2[1], quad_by_scenario, "keep_out")
    with st.expander("Tabela de quadrantes"):
        tables.dataframe(quad, percent_cols=("Bad_Rate",))

    _render_depth_section(sim, tier, comparison=comparison)
    _render_aggravation_game(subset, population, base["default_rate"])


with funnel_col:
    _render_live_funnel()
