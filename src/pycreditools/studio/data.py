"""Data IO + the shared population filter.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import hashlib
import io

import pandas as pd

from pycreditools import generate_sample_data

from .models import ColumnRoles

POPULATION_CHOICES = ("Todos", "Aprovados", "Contratados", "DEV", "OOT", "Custom")

PERIODO_CHOICES = ("Tudo", "Dev", "OOT")
QUEM_CHOICES = ("Todos", "Aprovados", "Contratados")


def hash_bytes(content: bytes) -> str:
    """Short, stable hash of raw file bytes (used as `df_hash` for uploads)."""
    return hashlib.sha256(content).hexdigest()[:16]


def load_csv(content: bytes) -> pd.DataFrame:
    """Parse CSV bytes into a dataframe."""
    return pd.read_csv(io.BytesIO(content))


def load_parquet(content: bytes) -> pd.DataFrame:
    """Parse Parquet bytes into a dataframe."""
    return pd.read_parquet(io.BytesIO(content))


def make_sample(n_applicants: int, seed: int) -> tuple[pd.DataFrame, str]:
    """Generate sample data; the hash is deterministic from `(n_applicants, seed)`."""
    df = generate_sample_data(n_applicants, seed=seed)
    df_hash = f"sample-{n_applicants}-{seed}"
    return df, df_hash


def population_filter(
    df: pd.DataFrame,
    roles: ColumnRoles,
    choice: str,
    custom_mask: pd.Series | None = None,
) -> pd.DataFrame:
    """Subset `df` per the shared population selector.

    `choice` is one of `POPULATION_CHOICES`. `custom_mask` is a boolean `pd.Series`
    built by the caller from no-code widgets (never a user-typed expression).
    """
    if choice == "Todos":
        return df
    if choice == "Aprovados":
        if not roles.current_approval_col:
            raise ValueError("Defina a coluna de aprovação para filtrar Aprovados.")
        return df[df[roles.current_approval_col] == 1]
    if choice == "Contratados":
        if not roles.current_hired_col:
            raise ValueError("Defina a coluna de contratação para filtrar Contratados.")
        return df[df[roles.current_hired_col] == 1]
    if choice == "DEV":
        if not roles.time_col or not roles.oot_date:
            raise ValueError("Defina a safra e a data OOT para filtrar DEV.")
        return df[df[roles.time_col] < roles.oot_date]
    if choice == "OOT":
        if not roles.time_col or not roles.oot_date:
            raise ValueError("Defina a safra e a data OOT para filtrar OOT.")
        return df[df[roles.time_col] >= roles.oot_date]
    if choice == "Custom":
        if custom_mask is None:
            raise ValueError("Forneça uma máscara para o filtro customizado.")
        return df[custom_mask]
    raise ValueError(f"Opção de população desconhecida: {choice}")


def population_filter_two_axes(
    df: pd.DataFrame,
    roles: ColumnRoles,
    periodo: str,
    quem: str,
) -> pd.DataFrame:
    """Subset `df` by combining two independent axes (critiques 1.7 + 2.0).

    `periodo` is one of PERIODO_CHOICES; `quem` is one of QUEM_CHOICES.
    The two filters are AND-ed: temporal slice first, then funnel-stage slice.
    Delegates to `population_filter` so the operator logic lives in one place.
    """
    _periodo_to_choice = {"Tudo": "Todos", "Dev": "DEV", "OOT": "OOT"}
    if periodo not in _periodo_to_choice:
        raise ValueError(f"Período desconhecido: {periodo}")
    _quem_to_choice = {"Todos": "Todos", "Aprovados": "Aprovados", "Contratados": "Contratados"}
    if quem not in _quem_to_choice:
        raise ValueError(f"Quem desconhecido: {quem}")
    subset = population_filter(df, roles, _periodo_to_choice[periodo])
    return population_filter(subset, roles, _quem_to_choice[quem])
