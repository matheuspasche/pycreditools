import numpy as np
import pytest

from pycreditools import ModelEvaluator
from pycreditools.studio.analyses import (
    COMPLEMENTARITY_CORRELATION_HIGH,
    COMPLEMENTARITY_LIFT_SIGNIFICANT,
    combined_ks,
    complementarity_table,
    complementarity_verdict,
    compute_complementarity,
    resolve_reference_score,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.models import ColumnRoles


@pytest.fixture(scope="module")
def complementarity_population(sample_df, roles):
    return population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )


def test_compute_complementarity_correlation_matches_pandas_directly(
    complementarity_population, roles
):
    subset = complementarity_population
    target_col = roles.actual_default_col

    result = compute_complementarity(subset, "score_4", "legacy_score", target_col)

    expected_corr = subset[["score_4", "legacy_score"]].corr().iloc[0, 1]
    assert np.isclose(result["correlation"], expected_corr)


def test_compute_complementarity_isolated_ks_matches_model_evaluator_directly(
    complementarity_population, roles
):
    subset = complementarity_population
    target_col = roles.actual_default_col

    result = compute_complementarity(subset, "score_4", "legacy_score", target_col)

    expected_ks = ModelEvaluator(subset, ["score_4", "legacy_score"], target_col).compute_ks()
    assert np.isclose(result["ks_candidate"], expected_ks["score_4"])
    assert np.isclose(result["ks_reference"], expected_ks["legacy_score"])


def test_combined_ks_matches_model_evaluator_on_the_rank_average_ensemble(
    complementarity_population, roles
):
    subset = complementarity_population
    target_col = roles.actual_default_col

    result = combined_ks(subset, "score_4", "legacy_score", target_col)

    ensemble = subset[["score_4", "legacy_score"]].rank(pct=True).sum(axis=1)
    working = subset[[target_col]].copy()
    working["_ensemble"] = ensemble
    expected = ModelEvaluator(working, ["_ensemble"], target_col).compute_ks()["_ensemble"]
    assert np.isclose(result, expected)


def test_marginal_lift_is_combined_ks_minus_reference_ks(complementarity_population, roles):
    subset = complementarity_population
    target_col = roles.actual_default_col

    result = compute_complementarity(subset, "score_4", "legacy_score", target_col)

    assert np.isclose(result["marginal_lift"], result["ks_combined"] - result["ks_reference"])


def test_complementarity_table_has_one_row_per_candidate_and_skips_the_reference(
    complementarity_population, roles
):
    subset = complementarity_population
    target_col = roles.actual_default_col

    table = complementarity_table(
        subset, ["score_4", "score_5", "legacy_score"], "legacy_score", target_col
    )

    assert list(table["candidate_score"]) == ["score_4", "score_5"]
    assert (table["reference_score"] == "legacy_score").all()


def test_complementarity_verdict_matriciar_when_lift_is_significant():
    verdict = complementarity_verdict(
        correlation=0.3,
        marginal_lift=COMPLEMENTARITY_LIFT_SIGNIFICANT + 0.01,
        ks_candidate=0.35,
        ks_reference=0.30,
    )
    assert verdict == "matriciar"


def test_complementarity_verdict_substituir_when_redundant_and_candidate_dominates():
    verdict = complementarity_verdict(
        correlation=COMPLEMENTARITY_CORRELATION_HIGH + 0.05,
        marginal_lift=0.0,
        ks_candidate=0.40,
        ks_reference=0.20,
    )
    assert verdict == "substituir"


def test_complementarity_verdict_repechar_otherwise():
    verdict = complementarity_verdict(
        correlation=0.3,
        marginal_lift=0.0,
        ks_candidate=0.30,
        ks_reference=0.30,
    )
    assert verdict == "repechar"


def test_resolve_reference_score_uses_vigente_score_when_set():
    roles = ColumnRoles(vigente_score="legacy_score")
    ks_ranking = {"legacy_score": 0.2, "score_5": 0.4}

    assert resolve_reference_score(roles, ks_ranking) == "legacy_score"


def test_resolve_reference_score_falls_back_to_the_ks_champion_when_unset():
    roles = ColumnRoles(vigente_score=None)
    ks_ranking = {"legacy_score": 0.2, "score_5": 0.4}

    assert resolve_reference_score(roles, ks_ranking) == "score_5"


def test_resolve_reference_score_ignores_a_stale_vigente_score_not_in_the_ranking():
    roles = ColumnRoles(vigente_score="removed_score")
    ks_ranking = {"legacy_score": 0.2, "score_5": 0.4}

    assert resolve_reference_score(roles, ks_ranking) == "score_5"
