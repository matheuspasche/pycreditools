"""Risk Grouping page — A–E ratings + vintage stability (PRD 08)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Risk Grouping")
st.caption("Classificação em ratings A–E e estabilidade por safra.")
guard_dataset()
st.info("Em construção — chega na PRD 08 (Risk Grouping & Ratings).")
