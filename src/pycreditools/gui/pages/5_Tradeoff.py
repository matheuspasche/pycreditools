"""Trade-off page — efficient frontier + scenario picker (PRD 06)."""

import streamlit as st

from pycreditools.gui.session import guard_dataset

st.title("Trade-off")
st.caption("Fronteira eficiente e cenários conservador / neutro / agressivo.")
guard_dataset()
st.info("Em construção — chega na PRD 06 (Trade-off & Scenarios).")
