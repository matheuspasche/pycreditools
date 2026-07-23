"""Best-effort auto-detection of column roles from a raw dataframe.

No `streamlit` import allowed here — see `00-overview.md` §4b.
"""

from __future__ import annotations

import re

import pandas as pd

from .models import ColumnRoles, TierDetection

_ID_NAMES = {"id", "applicant_id", "cpf", "customer_id"}
_APPROVAL_NAMES = {"approved", "approval", "aprovado"}
_DEFAULT_NAMES = {"actual_default", "default", "target", "bad", "inadimplente"}
_HIRED_NAMES = {"hired", "contratou", "contracted"}
_TIME_NAMES = {"safra", "vintage", "date", "mes"}
_SEGMENT_NAMES = {"region", "loja", "segment", "uf"}
_ESTIMATED_NAMES = {"estimated_default", "pd", "est_pd"}

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
    oot_date = _pick_oot_date(df, time_col)

    return ColumnRoles(
        applicant_id_col=applicant_id_col,
        score_cols=score_cols,
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
        if _col_looks_like_score(df, c):
            continue
        if df[c].is_unique:
            return c
    return None


def _col_looks_like_score(df: pd.DataFrame, col: str) -> bool:
    """True when `col` matches the same criteria as `_find_score_cols` — used to
    avoid electing a score column as an applicant-id fallback."""
    if "score" not in col.lower():
        return False
    if not pd.api.types.is_numeric_dtype(df[col]):
        return False
    return df[col].nunique(dropna=True) > _MIN_SCORE_NUNIQUE


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
        if pd.api.types.is_integer_dtype(series):
            continue  # int-only is indistinguishable from a binary flag
        if pd.api.types.is_float_dtype(series):
            numeric = series
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.isna().sum() > series.isna().sum():
                continue  # some values could not be coerced — not a numeric PD column
        values = numeric.dropna()
        if len(values) and values.min() >= 0 and values.max() <= 1:
            return c
    return None


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


# Comparison-tier detection (ADR 0002) -----------------------------------------

ROLE_HINTS: dict[str, str] = {
    "applicant_id_col": (
        "Identificador único do solicitante; usado para juntar resultados entre simulações."
    ),
    "score_cols": (
        "Colunas numéricas com o(s) score(s) candidatos; precisam ter alta cardinalidade "
        "(não são categorias)."
    ),
    "current_approval_col": (
        "0/1: indica se o cliente foi aprovado pela política vigente; usada para o swap "
        "in/out/keep e para detectar o tier de comparação (Tier B)."
    ),
    "vigente_score": (
        "Opcional — o score em que a política vigente roda hoje; usado só como referência "
        "de comparação, não como fonte de PD do candidato. Mapeá-lo junto da aprovação "
        "atual habilita o Tier A."
    ),
    "actual_default_col": (
        "0/1: NaN para não-contratados; usada para calcular a inadimplência real."
    ),
    "current_hired_col": (
        "0/1: indica se o cliente efetivamente contratou (após aprovação)."
    ),
    "time_col": (
        "Safra/vintage (ex.: 2025-01); usada para separar populações Dev/OOT e ver "
        "comportamento no tempo."
    ),
    "segment_col": (
        "Opcional — coluna categórica de segmento (ex.: canal, loja, UF) para comparações "
        "quebradas por segmento."
    ),
    "estimated_default_col": (
        "0 a 1: PD estimada por modelo; é a fonte de PD apenas no Tier C (sem base de "
        "comparação vigente)."
    ),
    "oot_date": (
        "Valor de safra a partir do qual a população é considerada OOT (fora do período de "
        "desenvolvimento)."
    ),
}


def detect_tier(roles: ColumnRoles, df: pd.DataFrame) -> TierDetection:
    """Classify the comparison tier (A/B/C) from the roles actually present in `df`.

    Stale role mappings pointing at columns missing from `df` (e.g. a reloaded
    project applied to a different dataset) are ignored.
    """
    has_vigente_score = bool(roles.vigente_score) and roles.vigente_score in df.columns
    has_approval = bool(roles.current_approval_col) and roles.current_approval_col in df.columns

    if has_vigente_score and has_approval:
        return TierDetection(
            tier="A",
            rationale=(
                "Score vigente e aprovação atual mapeados: o swap completo "
                "(swap-in / swap-out / keep) é calculado pela flag de aprovação histórica. "
                "A reconstrução das regras vigentes a partir do score não é realizada nesta versão."
            ),
        )
    if has_approval:
        return TierDetection(
            tier="B",
            rationale=(
                "Apenas a aprovação atual está mapeada (sem score vigente): o swap "
                "in/out/keep funciona, mas as regras da política vigente não podem ser "
                "reconstruídas."
            ),
        )
    return TierDetection(
        tier="C",
        rationale=(
            "Nenhuma referência à política vigente foi mapeada: a base roda em modo "
            "autônomo / inferência de mercado, sem comparação de swap. A PD vem da "
            "coluna de PD estimada."
        ),
    )


def _looks_binary(values: pd.Series) -> bool:
    if values.empty:
        return True
    if not pd.api.types.is_numeric_dtype(values):
        return False
    return set(values.unique().tolist()).issubset({0, 1, 0.0, 1.0})


def _sample(values: pd.Series, n: int = 3) -> str:
    return ", ".join(str(v) for v in values.unique()[:n])


def validate_role_format(role_key: str, series: pd.Series) -> str | None:
    """Friendly pt-BR warning if `series` doesn't look like the format `role_key`
    expects; `None` if it looks fine. No auto-conversion, no inference."""
    values = series.dropna()
    if role_key in {"current_approval_col", "current_hired_col", "actual_default_col"}:
        if not _looks_binary(values):
            return (
                "Essa coluna deveria conter apenas 0/1; foram encontrados valores como "
                f"{_sample(values)}."
            )
    elif role_key in {"vigente_score", "estimated_default_col"}:
        if not pd.api.types.is_numeric_dtype(series):
            return "Essa coluna deveria ser numérica; foram encontrados valores não numéricos."
        if role_key == "estimated_default_col" and len(values) and (
            values.min() < 0 or values.max() > 1
        ):
            return (
                "A PD estimada deveria estar entre 0 e 1; foram encontrados valores fora "
                "desse intervalo."
            )
    return None
