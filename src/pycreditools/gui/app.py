"""Streamlit entrypoint: page config, theme, navigation, sidebar context."""

import streamlit as st

from pycreditools.gui.session import get_state, init_state
from pycreditools.gui.theme import apply_theme

st.set_page_config(page_title="Pycreditools Studio", page_icon="📊", layout="wide")
apply_theme()
init_state()

pages = [
    st.Page("pages/1_Ingestion.py", title="Ingestão", icon="📥"),
    st.Page("pages/2_Score_Evaluation.py", title="Avaliação de Score", icon="📈"),
    st.Page("pages/3_Policy_Studio.py", title="Policy Studio", icon="🧱"),
    st.Page("pages/4_Simulation.py", title="Simulação", icon="🧪"),
    st.Page("pages/5_Tradeoff.py", title="Trade-off", icon="⚖️"),
    st.Page("pages/6_Optimization.py", title="Otimização", icon="🎯"),
    st.Page("pages/7_Risk_Grouping.py", title="Risk Grouping", icon="🗂️"),
    st.Page("pages/8_Risk_Screening.py", title="Screening", icon="🔬"),
    st.Page("pages/9_Crash_Test.py", title="Crash Test", icon="💥"),
    st.Page("pages/10_Deployment.py", title="Deploy & Scoring", icon="🚀"),
]
nav = st.navigation(pages, position="sidebar")


def render_sidebar_context() -> None:
    """Show the active dataset name/row count and active policy in the sidebar."""
    state = get_state()
    with st.sidebar:
        st.markdown("## 📊 Pycreditools Studio")
        st.divider()
        n_rows = f"{len(state.df):,}" if state.df is not None else "0"
        st.caption(f"Base: `{state.df_name or '—'}` · {n_rows} linhas")
        st.caption(f"Política ativa: `{state.active_policy or '—'}`")


render_sidebar_context()
nav.run()
