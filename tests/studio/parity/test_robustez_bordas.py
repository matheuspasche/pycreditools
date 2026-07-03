"""Robustez de bordas — funil agregado com segmento vazio + encoding de aprovação (#42).

TDD: escreva aqui primeiro; deixe vermelhos; depois implemente em studio/analyses.py.
"""

import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools.studio.analyses import _base_outcome, aggregate_funnel
from pycreditools.studio.models import ColumnRoles

_FUNNEL_COLS = [
    "Stage",
    "Candidates",
    "Passed",
    "Stage_Pass_Rate",
    "Cum_Pass_Rate",
    "Rejections",
    "Stage_Rej_Rate",
]


def _make_funnel_without_total(filter_stages=("Filtro CPF",), n=100, passed=70, approved=40):
    """Minimal funnel WITHOUT the 'Total' row — simulates an empty-segment funnel."""
    rows = []
    for stage in filter_stages:
        rows.append(
            {
                "Stage": stage,
                "Candidates": n,
                "Passed": passed,
                "Stage_Pass_Rate": passed / n,
                "Cum_Pass_Rate": passed / n,
                "Rejections": n - passed,
                "Stage_Rej_Rate": (n - passed) / n,
            }
        )
    rows.append(
        {
            "Stage": "Approved",
            "Candidates": approved,
            "Passed": approved,
            "Stage_Pass_Rate": np.nan,
            "Cum_Pass_Rate": approved / n,
            "Rejections": 0,
            "Stage_Rej_Rate": np.nan,
        }
    )
    return pd.DataFrame(rows, columns=_FUNNEL_COLS)


def _make_full_funnel(filter_stages=("Filtro CPF",), n=100, passed=70, approved=40):
    """Minimal funnel WITH the 'Total' row at the top."""
    rows = [
        {
            "Stage": "Total",
            "Candidates": n,
            "Passed": n,
            "Stage_Pass_Rate": np.nan,
            "Cum_Pass_Rate": 1.0,
            "Rejections": 0,
            "Stage_Rej_Rate": np.nan,
        }
    ]
    for stage in filter_stages:
        rows.append(
            {
                "Stage": stage,
                "Candidates": n,
                "Passed": passed,
                "Stage_Pass_Rate": passed / n,
                "Cum_Pass_Rate": passed / n,
                "Rejections": n - passed,
                "Stage_Rej_Rate": (n - passed) / n,
            }
        )
    rows.append(
        {
            "Stage": "Approved",
            "Candidates": approved,
            "Passed": approved,
            "Stage_Pass_Rate": np.nan,
            "Cum_Pass_Rate": approved / n,
            "Rejections": 0,
            "Stage_Rej_Rate": np.nan,
        }
    )
    return pd.DataFrame(rows, columns=_FUNNEL_COLS)


# ── Bug 1: aggregate_funnel com segmento vazio ────────────────────────────────


def test_aggregate_funnel_sem_total_nao_estoura_emite_aviso_e_retorna_vazio():
    """Funil sem etapa 'Total' não estoura com IndexError; emite aviso pt-BR e retorna vazio."""
    funnel = _make_funnel_without_total()
    with pytest.warns(UserWarning, match="Total"):
        result = aggregate_funnel([funnel])
    assert list(result.columns) == _FUNNEL_COLS
    assert len(result) == 0


def test_aggregate_funnel_segmento_vazio_junto_com_valido_nao_estoura():
    """Segmento sem 'Total' + segmento válido: não estoura; avisa e retorna vazio."""
    bad_funnel = _make_funnel_without_total()
    good_funnel = _make_full_funnel()
    with pytest.warns(UserWarning, match="Total"):
        result = aggregate_funnel([bad_funnel, good_funnel])
    assert list(result.columns) == _FUNNEL_COLS


def test_aggregate_funnel_lista_vazia_retorna_df_vazio_sem_aviso():
    """Lista vazia retorna DataFrame com colunas certas — comportamento já existente."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = aggregate_funnel([])
    assert list(result.columns) == _FUNNEL_COLS
    assert len(result) == 0


def test_aggregate_funnel_todos_validos_continua_funcionando():
    """Funnels normais (com 'Total') não emitem aviso e agregam corretamente."""
    f1 = _make_full_funnel(n=100, passed=70, approved=40)
    f2 = _make_full_funnel(n=200, passed=150, approved=90)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = aggregate_funnel([f1, f2])
    total_row = result.loc[result["Stage"] == "Total"]
    assert not total_row.empty
    assert int(total_row["Candidates"].iloc[0]) == 300  # 100 + 200


# ── Bug 2: _base_outcome com encoding não-{0,1} ───────────────────────────────


def _roles(approval_col="aprovado", default_col=None):
    return ColumnRoles(current_approval_col=approval_col, actual_default_col=default_col)


def test_base_outcome_encoding_sim_nao_emite_aviso_e_retorna_none():
    """Coluna de aprovação 'Sim'/'Não' emite UserWarning; não retorna taxa errada."""
    df = pd.DataFrame(
        {
            "aprovado": ["Sim", "Não", "Sim", "Sim", "Não"],
            "default": [0, 0, 1, 0, 0],
        }
    )
    with pytest.warns(UserWarning, match="aprovação|encoding|0.*1|\\{0.*1\\}"):
        result = _base_outcome(df, _roles("aprovado", "default"))
    assert result is None


def test_base_outcome_encoding_numerico_nao_binario_emite_aviso_e_retorna_none():
    """Coluna de aprovação com código numérico ≠ {0,1} emite UserWarning e retorna None."""
    df = pd.DataFrame(
        {
            "aprovado": [2, 0, 2, 2, 0],
            "default": [0, 0, 1, 0, 0],
        }
    )
    with pytest.warns(UserWarning, match="aprovação|encoding|0.*1|\\{0.*1\\}"):
        result = _base_outcome(df, _roles("aprovado", "default"))
    assert result is None


def test_base_outcome_encoding_correto_nao_emite_aviso_e_calcula_taxa():
    """Coluna de aprovação {0,1} não emite aviso e calcula taxa corretamente."""
    df = pd.DataFrame(
        {
            "aprovado": [1, 0, 1, 1, 0],
            "default": [0, 0, 1, 0, 0],
        }
    )
    roles = ColumnRoles(current_approval_col="aprovado", actual_default_col="default")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = _base_outcome(df, roles)
    assert result is not None
    assert result["approval_rate"] == pytest.approx(0.6)  # 3/5 aprovados


def test_base_outcome_coluna_ausente_retorna_none_sem_aviso():
    """Coluna mapeada mas ausente do DataFrame retorna None (comportamento existente)."""
    df = pd.DataFrame({"outra": [1, 0, 1]})
    roles = ColumnRoles(current_approval_col="aprovado")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = _base_outcome(df, roles)
    assert result is None


def test_base_outcome_encoding_apenas_zeros_aceito_sem_aviso():
    """Coluna 0/0 (ninguém aprovado) é encoding {0,1} válido — não deve avisar."""
    df = pd.DataFrame({"aprovado": [0, 0, 0, 0]})
    roles = ColumnRoles(current_approval_col="aprovado")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = _base_outcome(df, roles)
    assert result is not None
    assert result["approval_rate"] == pytest.approx(0.0)
