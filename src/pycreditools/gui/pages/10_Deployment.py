"""Deployment page — export policy JSON + batch-score a file (PRD 11)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Deploy & Scoring")
st.caption("Exporte a política final e pontue uma base nova.")
guard_dataset()
st.info("Em construção — chega na PRD 11 (Deployment & Batch Scoring).")
