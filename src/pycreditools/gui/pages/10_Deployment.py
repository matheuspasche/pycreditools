"""Deployment page — export policy JSON + batch-score a file (PRD 11)."""

from __future__ import annotations

import json

import streamlit as st

from pycreditools import DeploymentPolicy
from pycreditools.gui import data_access, session
from pycreditools.gui.components import kpi, tables
from pycreditools.gui.session import get_state, require_policy
from pycreditools.studio import analyses, charts

st.title("Deploy & Scoring")
st.caption("Exporte a política final e pontue uma base nova.")

entry = require_policy()
state = get_state()

tab_export, tab_score = st.tabs(["Exportar política de produção", "Escorar arquivo"])

with tab_export:
    st.subheader(f"Política ativa: `{state.active_policy}`")
    st.caption(
        "Esta é a única ação que gera o artefato de produção — salvar a sessão "
        "(barra lateral) nunca publica uma política."
    )
    st.text(entry.policy.describe())

    has_fitted_rating = state.rating_result is not None
    if has_fitted_rating:
        st.caption("Rating ajustado disponível (página Risk Grouping).")
    else:
        st.caption("Sem rating ajustado — veja a página Risk Grouping para anexar um.")

    col_clean, col_recipe = st.columns(2)
    with col_clean:
        clean = st.toggle(
            "Apenas regras duras (clean)",
            value=False,
            key="dep_clean",
            help="Omite metadados de estudo e estágios de taxa — bom artefato de produção.",
        )
    with col_recipe:
        include_recipe = st.toggle(
            "Incluir recipe de rating",
            value=has_fitted_rating,
            disabled=not has_fitted_rating,
            key="dep_include_recipe",
        )

    export_recipe = (
        state.rating_result.recipe if (include_recipe and state.rating_result is not None) else None
    )
    try:
        dep = entry.policy.export(rating_recipe=export_recipe)
    except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
        st.error(f"Não foi possível exportar a política: {exc}")
        st.stop()

    full_json = json.dumps(dep.to_dict(clean=clean), indent=2, ensure_ascii=False)
    rules_json = json.dumps(dep.to_production_rules(clean=clean), indent=2, ensure_ascii=False)

    tab_full, tab_rules = st.tabs(["JSON completo", "Regras de produção"])
    with tab_full:
        st.code(full_json, language="json")
        st.download_button(
            "⬇️ Baixar política (JSON)",
            full_json,
            file_name=f"{state.active_policy}_deployment.json",
            mime="application/json",
            key="dl_full_policy",
        )
    with tab_rules:
        st.code(rules_json, language="json")
        st.download_button(
            "⬇️ Baixar regras de produção (JSON)",
            rules_json,
            file_name=f"{state.active_policy}_production_rules.json",
            mime="application/json",
            key="dl_production_rules",
        )

with tab_score:
    st.subheader("Política de deployment")
    source = st.radio(
        "Fonte da política",
        ["Usar política atual", "Carregar JSON salvo"],
        key="dep_score_source",
    )

    dep_score: DeploymentPolicy | None = None
    if source == "Usar política atual":
        score_recipe = state.rating_result.recipe if state.rating_result is not None else None
        try:
            dep_score = entry.policy.export(rating_recipe=score_recipe)
        except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
            st.error(f"Não foi possível exportar a política atual: {exc}")
    else:
        uploaded_policy = st.file_uploader(
            "JSON da política de deployment", type=["json"], key="dep_policy_upload"
        )
        if uploaded_policy is None:
            st.info("Envie um JSON de política exportado nesta página.")
        else:
            try:
                payload = json.loads(uploaded_policy.getvalue().decode("utf-8"))
                dep_score = DeploymentPolicy.from_dict(payload)
            except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                st.error(f"JSON de política inválido: {exc}")

    if dep_score is not None:
        uploaded_file = st.file_uploader(
            "Base de aplicantes (CSV ou Parquet)", type=["csv", "parquet"], key="dep_score_file"
        )
        if uploaded_file is None:
            st.info("Envie um arquivo CSV/Parquet para escorar.")
        else:
            content = uploaded_file.getvalue()
            try:
                new_df = (
                    data_access.load_parquet(content)
                    if uploaded_file.name.endswith(".parquet")
                    else data_access.load_csv(content)
                )
            except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                st.error(f"Não foi possível ler o arquivo: {exc}")
                new_df = None

            if new_df is not None:
                st.caption(f"Pré-visualização ({len(new_df):,} linhas)")
                tables.dataframe(new_df.head(10))

                col_simple, col_method = st.columns(2)
                with col_simple:
                    simple = st.toggle(
                        "Saída simplificada (decisão/rating)", value=True, key="dep_score_simple"
                    )
                with col_method:
                    method = st.radio(
                        "Método",
                        ["analytical", "stochastic"],
                        index=0,
                        key="dep_score_method",
                        format_func=lambda m: "Analítico" if m == "analytical" else "Estocástico",
                    )

                mocked = analyses.deployment_mocked_columns(dep_score, new_df)
                if mocked:
                    st.info(
                        "Colunas ausentes no arquivo, mockadas automaticamente pelo `predict`: "
                        f"{', '.join(mocked)}."
                    )

                file_hash = data_access.hash_bytes(content)
                dep_key = analyses.deployment_cache_key(dep_score)
                try:
                    scored = session.score_batch(
                        new_df, file_hash, dep_score, dep_key, simple=simple, method=method
                    )
                except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
                    st.error(f"Não foi possível escorar o arquivo: {exc}")
                    scored = None

                if scored is not None:
                    if simple:
                        kpis = analyses.scoring_kpis(scored)
                        kpi.kpi_row(
                            [
                                {
                                    "label": "Total escorado",
                                    "value": tables.thousands(kpis["total"]),
                                },
                                {
                                    "label": "Taxa de aprovação",
                                    "value": tables.pct(kpis["approval_rate"]),
                                },
                            ]
                        )

                        dist = analyses.rating_distribution(scored)
                        if not dist.empty:
                            st.plotly_chart(
                                charts.bars(dist, percent=False, risk_colors=True),
                                use_container_width=True,
                                config={"displayModeBar": False},
                            )

                        st.subheader("Decisões")
                        tables.dataframe(scored.head(200))

                        reasons = analyses.rejection_reasons(scored)
                        if not reasons.empty:
                            st.subheader("Motivos de rejeição")
                            tables.dataframe(reasons)
                    else:
                        st.subheader("Resultado completo")
                        tables.dataframe(scored.head(200))

                    csv_bytes = scored.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇️ Baixar CSV escorado",
                        csv_bytes,
                        file_name="scored.csv",
                        mime="text/csv",
                        key="dl_scored_csv",
                    )
