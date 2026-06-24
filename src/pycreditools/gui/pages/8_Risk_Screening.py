"""Risk Screening page — sub-segments inside ratings ranked by IV (PRD 09)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Screening")
st.caption("Sub-segmentos dentro dos ratings, ranqueados por IV.")
guard_dataset()
st.info("Em construção — chega na PRD 09 (Risk Screening).")
