"""Best-effort auto-detection of column roles from a raw dataframe.

No `streamlit` import allowed here — see `00-overview.md` §4b.
"""

from __future__ import annotations

import re

import pandas as pd

from .models import ColumnRoles

_ID_NAMES = {"id", "applicant_id", "cpf", "customer_id"}
_APPROVAL_NAMES = {"approved", "approval", "aprovado"}
_DEFAULT_NAMES = {"actual_default", "default", "target", "bad", "inadimplente"}
_HIRED_NAMES = {"hired", "contratou", "contracted"}
_TIME_NAMES = {"safra", "vintage", "date", "mes"}
_SEGMENT_NAMES = {"region", "loja", "segment", "uf"}
_ESTIMATED_NAMES = {"estimated_default", "pd", "true_pd", "est_pd"}

_SAFRA_PATTERN = re.compile(r"^\d{4}-\d{2}$")

_MIN_SCORE_NUNIQUE = 20
_MAX_SEGMENT_NUNIQUE = 20


def detect_roles(df: pd.DataFrame) -> ColumnRoles:
    """Auto-detect `ColumnRoles` from `df`'s column names/dtypes (user may override)."""
    cols = list(df.columns)

    applicant_id_col = _find_id_col(df, cols)
    score_cols = _find_score_cols(df, cols)
    current_approval_col = _find_named_binary(df, cols, _APPROVAL_NAMES)
    actual_default_col = _find_named_binary(df, cols, _DEFAULT_NAMES, allow_na=True)
    current_hired_col = _find_named_binary(df, cols, _HIRED_NAMES)
    time_col = _find_time_col(df, cols)
    segment_col = _find_segment_col(df, cols)
    estimated_default_col = _find_estimated_default_col(df, cols)
    primary_score_col = _pick_primary_score(df, score_cols, actual_default_col)
    oot_date = _pick_oot_date(df, time_col)

    return ColumnRoles(
        applicant_id_col=applicant_id_col,
        score_cols=score_cols,
        primary_score_col=primary_score_col,
        current_approval_col=current_approval_col,
        actual_default_col=actual_default_col,
        current_hired_col=current_hired_col,
        time_col=time_col,
        segment_col=segment_col,
        estimated_default_col=estimated_default_col,
        oot_date=oot_date,
    )


def _find_id_col(df: pd.DataFrame, cols: list[str]) -> str | None:
    for c in cols:
        if c.lower() in _ID_NAMES:
            return c
    for c in cols:
        if df[c].is_unique:
            return c
    return None


def _find_score_cols(df: pd.DataFrame, cols: list[str]) -> list[str]:
    result = []
    for c in cols:
        if "score" not in c.lower():
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            continue
        if df[c].nunique(dropna=True) <= _MIN_SCORE_NUNIQUE:
            continue
        result.append(c)
    return result


def _find_named_binary(
    df: pd.DataFrame, cols: list[str], names: set[str], *, allow_na: bool = False
) -> str | None:
    for c in cols:
        if c.lower() not in names:
            continue
        series = df[c].dropna() if allow_na else df[c]
        values = set(series.unique().tolist())
        if values and values.issubset({0, 1, 0.0, 1.0}):
            return c
    return None


def _find_time_col(df: pd.DataFrame, cols: list[str]) -> str | None:
    for c in cols:
        if c.lower() in _TIME_NAMES:
            return c
    for c in cols:
        series = df[c]
        if pd.api.types.is_datetime64_any_dtype(series):
            return c
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            sample_vals = series.dropna().astype(str).head(20)
            if len(sample_vals) and sample_vals.str.match(_SAFRA_PATTERN).all():
                return c
    return None


def _find_segment_col(df: pd.DataFrame, cols: list[str]) -> str | None:
    for c in cols:
        if c.lower() in _SEGMENT_NAMES:
            return c
    for c in cols:
        series = df[c]
        is_categorical = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(
            series
        )
        if is_categorical and series.nunique() <= _MAX_SEGMENT_NUNIQUE:
            return c
    return None


def _find_estimated_default_col(df: pd.DataFrame, cols: list[str]) -> str | None:
    for c in cols:
        if c.lower() not in _ESTIMATED_NAMES:
            continue
        series = df[c]
        if pd.api.types.is_float_dtype(series) and series.min() >= 0 and series.max() <= 1:
            return c
    return None


def _pick_primary_score(
    df: pd.DataFrame, score_cols: list[str], actual_default_col: str | None
) -> str | None:
    if not score_cols:
        return None
    if not actual_default_col:
        return score_cols[-1]
    mask = df[actual_default_col].notna()
    if mask.sum() < 10:
        return score_cols[-1]
    try:
        from pycreditools import ModelEvaluator

        evaluator = ModelEvaluator(df.loc[mask], score_cols, actual_default_col)
        ks = evaluator.compute_ks()
        return max(ks, key=ks.get)
    except Exception:
        return score_cols[-1]


def _pick_oot_date(df: pd.DataFrame, time_col: str | None) -> str | None:
    if not time_col:
        return None
    values = sorted(df[time_col].dropna().unique().tolist())
    if not values:
        return None
    if "2025-01" in values:
        return "2025-01"
    idx = max(0, int(len(values) * 0.8))
    return str(values[min(idx, len(values) - 1)])
