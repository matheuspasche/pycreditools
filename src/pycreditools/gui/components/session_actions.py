"""Unified session save/load — a discreet, cross-page action (critique 1.1, #37).

Persists the whole working session (base + roles + policies + ratings + scores em
jogo) in one place. Distinct from the explicit "exportar política de produção"
action on the Deploy page (`pages/10_Deployment.py`), which is the only thing that
emits a production artifact — saving the session never deploys anything.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from pycreditools.gui import data_access
from pycreditools.gui.session import DATASET_SOURCE_KEY, get_state
from pycreditools.studio import projects as studio_projects
from pycreditools.studio.models import StudioState

ROLE_WIDGET_KEYS = (
    "role_applicant_id",
    "role_score_cols",
    "role_primary_score",
    "role_approval",
    "role_default",
    "role_hired",
    "role_time",
    "role_segment",
    "role_estimated",
    "role_oot",
    "role_vigente_score",
)


def _pick_folder_dialog(initial_dir: str | None = None) -> str | None:
    """Open a native OS folder picker (this app is single-user/local, §13)."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        st.error("Seletor de pasta não disponível neste ambiente; digite o caminho manualmente.")
        return None
    try:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        selected = filedialog.askdirectory(initialdir=initial_dir or str(Path.home()))
        root.destroy()
    except Exception:  # noqa: BLE001 - no display/Tcl available
        st.error("Seletor de pasta não disponível neste ambiente; digite o caminho manualmente.")
        return None
    return selected or None


def render_session_actions() -> None:
    """Render the discreet "Sessão" save/load popover (sidebar, every page)."""
    state = get_state()
    with st.popover("💾 Sessão", use_container_width=True):
        st.caption("Salva base + roles + políticas + ratings + scores em jogo.")

        st.subheader("Salvar sessão")
        project_name = st.text_input("Nome do projeto", key="project_save_name")

        if "project_save_dir_pending" in st.session_state:
            st.session_state["project_save_dir"] = st.session_state.pop(
                "project_save_dir_pending"
            )
        col_path, col_pick = st.columns([4, 1])
        with col_path:
            custom_dir = st.text_input(
                "Pasta (opcional, padrão ~/.pycreditools_studio/projects)",
                key="project_save_dir",
            )
        with col_pick:
            st.write("")
            if st.button("Escolher pasta...", key="pick_save_dir"):
                picked = _pick_folder_dialog(custom_dir or None)
                if picked:
                    st.session_state["project_save_dir_pending"] = picked
                    st.rerun()
        if st.button("Salvar sessão", disabled=not project_name):
            source = st.session_state.get(DATASET_SOURCE_KEY, {})
            dataset_meta = {
                "name": state.df_name,
                "path_or_source": source.get("path_or_source"),
                "hash": state.df_hash,
                "n_rows": len(state.df) if state.df is not None else None,
                "sample": source.get("sample"),
            }
            bundle = studio_projects.bundle_from_state(state, project_name, dataset=dataset_meta)
            target_dir = Path(custom_dir) if custom_dir else studio_projects.DEFAULT_PROJECTS_DIR
            dir_existed = target_dir.exists()
            path = studio_projects.save_project(bundle, custom_dir or None)
            if not dir_existed:
                st.success(f"Pasta criada e sessão salva em {path}")
            else:
                st.success(f"Sessão salva em {path}")

        st.divider()
        st.subheader("Carregar sessão")

        if "project_load_dir_pending" in st.session_state:
            st.session_state["project_load_dir"] = st.session_state.pop(
                "project_load_dir_pending"
            )
        col_load_path, col_load_pick = st.columns([4, 1])
        with col_load_path:
            load_dir = st.text_input(
                "Pasta (opcional, padrão ~/.pycreditools_studio/projects)",
                key="project_load_dir",
            )
        with col_load_pick:
            st.write("")
            if st.button("Escolher pasta...", key="pick_load_dir"):
                picked = _pick_folder_dialog(load_dir or None)
                if picked:
                    st.session_state["project_load_dir_pending"] = picked
                    st.rerun()
        available = studio_projects.list_projects(load_dir or None)
        selected = st.selectbox("Projeto", ["—", *available], key="project_load_select")
        if st.button("Carregar sessão", disabled=selected == "—"):
            bundle = studio_projects.load_project(selected, load_dir or None)
            state.roles = bundle.roles
            state.policies = studio_projects.restore_policies(bundle)
            state.active_policy = bundle.active_policy
            state.rating_labels = bundle.rating_labels
            state.scores_em_jogo = list(bundle.scores_em_jogo)
            dataset = bundle.dataset or {}
            sample = dataset.get("sample")
            if sample:
                df, df_hash = data_access.make_sample(sample["n_applicants"], sample["seed"])
                state.df = df
                state.df_name = bundle.df_name
                state.df_hash = df_hash
                st.session_state[DATASET_SOURCE_KEY] = {
                    "kind": "sample",
                    "path_or_source": "sample",
                    "sample": sample,
                }
                st.success(f"Sessão '{selected}' carregada e base regenerada.")
            else:
                st.warning(
                    "Sessão carregada, mas a base original não é regenerável automaticamente. "
                    f"Reenvie o arquivo original (hash esperado: {dataset.get('hash', '—')})."
                )
            st.rerun()

        st.divider()
        if st.button("Novo projeto", key="session_new_project"):
            for key in ROLE_WIDGET_KEYS:
                st.session_state.pop(key, None)
            st.session_state.pop(DATASET_SOURCE_KEY, None)
            st.session_state["studio"] = StudioState()
            st.rerun()
