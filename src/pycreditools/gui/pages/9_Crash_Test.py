"""Crash Test page — breakeven stress factor (PRD 10)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Crash Test")
st.caption("Fator de estresse de equilíbrio (breakeven).")
guard_dataset()
st.info("Em construção — chega na PRD 10 (Crash Test).")
