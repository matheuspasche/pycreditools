"""Cached `st.cache_data` bindings around `pycreditools.studio.data`."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from pycreditools.studio import data as _data
from pycreditools.studio.detection import detect_roles
from pycreditools.studio.models import ColumnRoles

POPULATION_CHOICES = _data.POPULATION_CHOICES


@st.cache_data(show_spinner="Lendo CSV...")
def load_csv(content: bytes) -> pd.DataFrame:
    """Cached CSV parse, keyed on the raw file bytes."""
    return _data.load_csv(content)


@st.cache_data(show_spinner="Lendo Parquet...")
def load_parquet(content: bytes) -> pd.DataFrame:
    """Cached Parquet parse, keyed on the raw file bytes."""
    return _data.load_parquet(content)


@st.cache_data(show_spinner="Gerando base de exemplo...")
def make_sample(n_applicants: int, seed: int) -> tuple[pd.DataFrame, str]:
    """Cached sample-data generation, keyed on `(n_applicants, seed)`."""
    return _data.make_sample(n_applicants, seed)


def hash_bytes(content: bytes) -> str:
    """Hash raw file bytes for use as `df_hash`."""
    return _data.hash_bytes(content)


def population_filter(
    df: pd.DataFrame, roles: ColumnRoles, choice: str, custom_mask: pd.Series | None = None
) -> pd.DataFrame:
    """Subset `df` per the shared population selector (delegates to the core)."""
    return _data.population_filter(df, roles, choice, custom_mask)


__all__ = [
    "POPULATION_CHOICES",
    "detect_roles",
    "hash_bytes",
    "load_csv",
    "load_parquet",
    "make_sample",
    "population_filter",
]
