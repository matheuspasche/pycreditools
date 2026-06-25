"""Analysis orchestration: thin wrappers over `pycreditools` returning plain data.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import pandas as pd

from pycreditools import ModelEvaluator


def effective_n(df: pd.DataFrame, target_col: str) -> int:
    """Count of rows with an observed (non-NaN) target in `df`."""
    return int(df[target_col].notna().sum())


def evaluate_scores(df: pd.DataFrame, score_cols: list[str], target_col: str) -> dict[str, float]:
    """KS statistic per score, via `ModelEvaluator.compute_ks()`."""
    return ModelEvaluator(df, score_cols, target_col).compute_ks()


def ks_table(df: pd.DataFrame, score_col: str, target_col: str, bins: int = 10) -> pd.DataFrame:
    """Per-bucket KS/bad-rate table for one score, via `ModelEvaluator.compute_ks_table()`."""
    return ModelEvaluator(df, [score_col], target_col).compute_ks_table(score_col, bins)
