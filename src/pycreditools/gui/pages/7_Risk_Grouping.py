"""Risk Grouping page — A–E ratings + vintage stability (PRD 08)."""

from __future__ import annotations

import streamlit as st

from pycreditools.gui import session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.components.population import (
    render_effective_n_caption,
    render_population_selector_v2,
)
from pycreditools.gui.session import get_state, guard_roles
from pycreditools.studio import charts
from pycreditools.studio.analyses import (
    apply_manual_grouping,
    cell_groups_to_grid,
    default_cell_groups,
    grid_to_cell_groups,
    groups_table,
    label_ratings_by_pd,
    open_matrix_pivot,
    recipe_breaks_table,
    recipe_to_cell_groups,
    stability_table,
    vintage_stability_table,
)

st.title("Risk Grouping")
st.caption("Classificação em ratings A–E (clustering) e estabilidade por safra.")
guard_roles("actual_default_col")

state = get_state()
roles = state.roles
df = state.df

tab_single, tab_pairwise, tab_matrix = st.tabs(["Único", "Pairwise", "Matriz"])

with tab_single:
    with st.container(border=True):
        col_scores, col_population = st.columns(2)
        with col_scores:
            score_cols = st.multiselect(
                "Score(s)",
                roles.score_cols,
                default=roles.score_cols[-1:],
                max_selections=2,
                key="rg_score_cols",
            )
        with col_population:
            periodo_rg, quem_rg, subset = render_population_selector_v2(
                df, roles, key="rg_population", default_quem="Aprovados"
            )
            population = f"{periodo_rg}/{quem_rg}"

        col_bins, col_max, col_minvol, col_crossings, col_method = st.columns(5)
        with col_bins:
            bins = st.slider("Bins", 5, 50, value=30, key="rg_bins")
        with col_max:
            max_groups = st.slider(
                "Máx. grupos", 2, bins, value=min(5, bins), key="rg_max_groups"
            )
        with col_minvol:
            min_vol_ratio = st.slider(
                "Vol. mínimo por grupo", 0.0, 0.2, value=0.01, step=0.01, key="rg_min_vol"
            )
        with col_crossings:
            max_crossings = st.slider("Máx. cruzamentos", 0, 5, value=1, key="rg_max_crossings")
        with col_method:
            method = st.radio(
                "Método",
                ["ward", "iv"],
                key="rg_method",
                format_func=lambda m: "Ward" if m == "ward" else "IV",
            )

        use_time = st.toggle(
            "Usar safra / OOT",
            value=bool(roles.time_col and roles.oot_date),
            key="rg_use_time",
            disabled=not (roles.time_col and roles.oot_date),
        )

    if not score_cols:
        st.info("Selecione ao menos um score para agrupar.")
        st.stop()

    target_col = roles.actual_default_col
    effective_population = subset.dropna(subset=[target_col])
    if effective_population.empty:
        st.warning("Nenhuma linha com o alvo observado na população selecionada.")
        st.stop()

    render_effective_n_caption(effective_population, roles)

    time_col = roles.time_col if use_time else None
    oot_date = roles.oot_date if use_time else None

    try:
        result = session.fit_risk_groups(
            effective_population,
            state.df_hash,
            population,
            tuple(score_cols),
            target_col,
            bins,
            max_groups,
            min_vol_ratio,
            max_crossings,
            time_col,
            method,
            oot_date,
        )
    except ValueError as exc:
        st.error(f"Não foi possível agrupar: {exc}")
        st.stop()

    labels = label_ratings_by_pd(result, target_col)
    state.rating_result = result
    state.rating_labels = labels

    groups = groups_table(result, labels)

    kpi.kpi_row(
        [
            {"label": "Nº de grupos", "value": result.n_groups},
            {"label": "Volume total", "value": tables.thousands(groups["volume"].sum())},
            {
                "label": "PD spread (A→E)",
                "value": f"{(groups['pd'].max() - groups['pd'].min()) * 100:.1f} p.p.",
            },
        ]
    )

    if st.button("Usar este rating nas demais páginas", key="rg_confirm_active"):
        st.toast(f"Rating ativo: {result.n_groups} grupos prontos para Simulação/Deployment.")

    stability = stability_table(result, labels)
    breaks = recipe_breaks_table(result, labels)
    vintage_df = (
        vintage_stability_table(result, time_col, target_col, labels)
        if time_col and oot_date
        else None
    )

    tab_charts, tab_tables = st.tabs(["Gráficos", "Tabelas"])
    with tab_charts:
        st.plotly_chart(
            charts.bars(groups.set_index("Rating")["pd"], percent=True, risk_colors=True),
            use_container_width=True,
            config={"displayModeBar": False},
        )

        if vintage_df is not None:
            st.plotly_chart(
                charts.vintage_stability(
                    vintage_df,
                    time_col=time_col,
                    rating_col="Rating",
                    rate_col="bad_rate",
                    oot_date=oot_date,
                ),
                use_container_width=True,
                config={"displayModeBar": False},
            )

    with tab_tables:
        st.subheader("Grupos")
        tables.dataframe(groups, percent_cols=("pd",), int_cols=("volume",))

        if not stability.empty:
            st.subheader("Estabilidade DEV vs OOT")
            percent_stability_cols = tuple(c for c in stability.columns if c.startswith("PD_"))
            tables.dataframe(stability, percent_cols=percent_stability_cols)

        if not breaks.empty:
            st.subheader("Score → rating")
            tables.dataframe(breaks)

with tab_pairwise:
    candidate_scores = list(roles.score_cols)
    if len(candidate_scores) < 2:
        st.info("São necessários ao menos 2 scores configurados para a comparação pairwise.")
    else:
        with st.container(border=True):
            col_primary, col_challengers = st.columns(2)
            with col_primary:
                primary = st.selectbox(
                    "Score primário (baseline)",
                    candidate_scores,
                    index=len(candidate_scores) - 1,
                    key="rg_pw_primary",
                )
            with col_challengers:
                challengers = st.multiselect(
                    "Desafiantes",
                    [s for s in candidate_scores if s != primary],
                    key="rg_pw_challengers",
                )
            periodo_pw, quem_pw, subset_pw = render_population_selector_v2(
                df, roles, key="rg_pw_population", default_quem="Aprovados"
            )
            population_pw = f"{periodo_pw}/{quem_pw}"

            col_bins_pw, col_max_pw, col_method_pw = st.columns(3)
            with col_bins_pw:
                bins_pw = st.slider("Bins", 5, 50, value=30, key="rg_pw_bins")
            with col_max_pw:
                max_groups_pw = st.slider(
                    "Máx. grupos", 2, bins_pw, value=min(5, bins_pw), key="rg_pw_max_groups"
                )
            with col_method_pw:
                method_pw = st.radio(
                    "Método",
                    ["ward", "iv"],
                    key="rg_pw_method",
                    format_func=lambda m: "Ward" if m == "ward" else "IV",
                )

            use_time_pw = st.toggle(
                "Usar safra / OOT",
                value=bool(roles.time_col and roles.oot_date),
                key="rg_pw_use_time",
                disabled=not (roles.time_col and roles.oot_date),
            )

        if not challengers:
            st.info("Selecione ao menos um score desafiante.")
        else:
            target_col_pw = roles.actual_default_col
            effective_pw = subset_pw.dropna(subset=[target_col_pw])
            if effective_pw.empty:
                st.warning("Nenhuma linha com o alvo observado na população selecionada.")
            else:
                time_col_pw = roles.time_col if use_time_pw else None
                oot_date_pw = roles.oot_date if use_time_pw else None
                try:
                    pairwise_results = session.fit_pairwise_risk_groups(
                        effective_pw,
                        state.df_hash,
                        population_pw,
                        primary,
                        tuple(challengers),
                        target_col_pw,
                        bins_pw,
                        max_groups_pw,
                        0.05,
                        1,
                        time_col_pw,
                        method_pw,
                        oot_date_pw,
                    )
                except ValueError as exc:
                    st.error(f"Não foi possível comparar: {exc}")
                    pairwise_results = {}

                for pair_name, pair_result in pairwise_results.items():
                    with st.expander(pair_name, expanded=True):
                        pair_labels = label_ratings_by_pd(pair_result, target_col_pw)
                        pair_groups = groups_table(pair_result, pair_labels)
                        tables.dataframe(pair_groups, percent_cols=("pd",), int_cols=("volume",))
                        pair_stability = stability_table(pair_result, pair_labels)
                        if not pair_stability.empty:
                            percent_cols = tuple(
                                c for c in pair_stability.columns if c.startswith("PD_")
                            )
                            tables.dataframe(pair_stability, percent_cols=percent_cols)

with tab_matrix:
    st.caption(
        "Matriz aberta score x score (matriciação): selecione células e agrupe-as à "
        "mão, ou rode o algoritmo como ponto de partida. O recipe resultante "
        "alimenta os cortes da Bancada."
    )
    candidate_scores_matrix = list(roles.score_cols)
    if len(candidate_scores_matrix) < 2:
        st.info("São necessários ao menos 2 scores configurados para a matriz.")
    else:
        with st.container(border=True):
            col_score1, col_score2 = st.columns(2)
            with col_score1:
                score1 = st.selectbox(
                    "Score 1 (linhas)",
                    candidate_scores_matrix,
                    index=len(candidate_scores_matrix) - 1,
                    key="rg_matrix_score1",
                )
            with col_score2:
                score2_options = [s for s in candidate_scores_matrix if s != score1]
                score2 = st.selectbox("Score 2 (colunas)", score2_options, key="rg_matrix_score2")
            periodo_mat, quem_mat, subset_matrix = render_population_selector_v2(
                df, roles, key="rg_matrix_population", default_quem="Aprovados"
            )
            population_matrix = f"{periodo_mat}/{quem_mat}"
            bins_matrix = st.slider(
                "Bins por score (grade quadrada)", 3, 10, value=5, key="rg_matrix_bins"
            )

        target_col_matrix = roles.actual_default_col
        effective_matrix = subset_matrix.dropna(subset=[target_col_matrix])
        if effective_matrix.empty:
            st.warning("Nenhuma linha com o alvo observado na população selecionada.")
        else:
            try:
                matrix = session.build_open_matrix(
                    effective_matrix,
                    state.df_hash,
                    population_matrix,
                    score1,
                    score2,
                    target_col_matrix,
                    bins_matrix,
                )
            except ValueError as exc:
                st.error(f"Não foi possível construir a matriz: {exc}")
                st.stop()

            matrix_tag = (score1, score2, bins_matrix, population_matrix)
            if st.session_state.get("rg_matrix_tag") != matrix_tag:
                st.session_state["rg_matrix_tag"] = matrix_tag
                st.session_state["rg_matrix_seed"] = default_cell_groups(matrix)
                st.session_state["rg_matrix_version"] = (
                    st.session_state.get("rg_matrix_version", 0) + 1
                )

            col_vol, col_pd = st.columns(2)
            with col_vol:
                st.plotly_chart(
                    charts.heatmap(open_matrix_pivot(matrix, "volume"), title="Volume"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            with col_pd:
                st.plotly_chart(
                    charts.heatmap(open_matrix_pivot(matrix, "pd"), title="Inadimplência"),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )

            if st.button("Rodar algoritmo (ponto de partida)", key="rg_matrix_algo"):
                try:
                    pairwise_seed = session.fit_pairwise_risk_groups(
                        effective_matrix,
                        state.df_hash,
                        population_matrix,
                        score1,
                        (score2,),
                        target_col_matrix,
                        bins_matrix,
                        bins_matrix,
                        0.01,
                        1,
                        None,
                        "ward",
                        None,
                    )
                    algo_result = pairwise_seed[f"{score1}_vs_{score2}"]
                except ValueError as exc:
                    st.error(f"Não foi possível rodar o algoritmo: {exc}")
                else:
                    st.session_state["rg_matrix_seed"] = recipe_to_cell_groups(algo_result.recipe)
                    st.session_state["rg_matrix_version"] += 1

            bins1 = len(matrix.breaks1) - 1
            bins2 = len(matrix.breaks2) - 1
            seed_grid = cell_groups_to_grid(st.session_state["rg_matrix_seed"], bins1, bins2)

            st.caption("Edite os grupos célula a célula (estilo Excel): mesmo número agrupa.")
            edited_grid = st.data_editor(
                seed_grid, key=f"rg_matrix_editor_{st.session_state['rg_matrix_version']}"
            )

            if st.button("Aplicar agrupamento manual", key="rg_matrix_apply"):
                cell_groups = grid_to_cell_groups(edited_grid)
                try:
                    manual_result = apply_manual_grouping(
                        matrix, effective_matrix, target_col_matrix, cell_groups
                    )
                except ValueError as exc:
                    st.error(f"Não foi possível aplicar o agrupamento manual: {exc}")
                else:
                    manual_labels = label_ratings_by_pd(manual_result, target_col_matrix)
                    state.rating_result = manual_result
                    state.rating_labels = manual_labels
                    st.toast(
                        f"Matriz manual aplicada: {manual_result.n_groups} grupos "
                        "prontos para a Bancada."
                    )
                    tables.dataframe(
                        groups_table(manual_result, manual_labels),
                        percent_cols=("pd",),
                        int_cols=("volume",),
                    )
