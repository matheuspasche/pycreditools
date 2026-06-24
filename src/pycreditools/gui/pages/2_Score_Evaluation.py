"""Score Evaluation page — KS ranking and decile tables (PRD 03)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Avaliação de Score")
st.caption("Ranking KS dos scores candidatos e tabela de decis.")
guard_dataset()
st.info("Em construção — chega na PRD 03 (Score Evaluation).")
