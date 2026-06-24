"""Optimization page — grid-search cutoffs + Pareto frontier (PRD 07)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Otimização")
st.caption("Busca em grade dos melhores cortes e fronteira de Pareto.")
guard_dataset()
st.info("Em construção — chega na PRD 07 (Cutoff Optimization).")
