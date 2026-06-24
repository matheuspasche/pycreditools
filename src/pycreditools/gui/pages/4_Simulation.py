"""Simulation page — run policy, quadrants, swap analysis (PRD 05)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Simulação")
st.caption("Rode a política, veja aprovação/inadimplência e os quadrantes de swap.")
guard_dataset()
st.info("Em construção — chega na PRD 05 (Simulation & Impact).")
