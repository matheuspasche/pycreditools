"""Policy Studio page — filters/cutoffs/rates + flat stress, live funnel (PRD 04)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Policy Studio")
st.caption("Construa filtros, cortes e taxas com uma prévia de funil ao vivo.")
guard_dataset()
st.info("Em construção — chega na PRD 04 (Policy Studio).")
