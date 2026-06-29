import pytest

from pycreditools.gui import session
from pycreditools.studio.analyses import suggest_scenarios
from pycreditools.studio.data import population_filter
from pycreditools.studio.models import PolicyScenario
from pycreditools.studio.policy_builder import roles_cache_key


def test_suggest_scenarios_returns_sensible_scenarios_for_a_short_list(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    scores_em_jogo = ["score_4", "score_5"]

    scenarios = suggest_scenarios(subset, roles, scores_em_jogo, cutoff_steps=5)

    assert 2 <= len(scenarios) <= 3
    for scenario in scenarios:
        assert isinstance(scenario, PolicyScenario)
        assert set(scenario.cutoffs) == set(scores_em_jogo)
        assert 0.0 <= scenario.approval_rate <= 1.0
        assert 0.0 <= scenario.default_rate <= 1.0

    by_name = {s.name: s for s in scenarios}
    conservative, aggressive = by_name["conservador"], by_name["agressivo"]
    assert conservative.default_rate <= aggressive.default_rate
    assert conservative.approval_rate <= aggressive.approval_rate


def test_suggest_scenarios_only_consumes_the_short_listed_scores(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800).copy()
    scores_em_jogo = ["score_5"]
    # Corrupt every other candidate score; the suggestion engine must not touch them.
    for other in roles.score_cols:
        if other not in scores_em_jogo:
            subset[other] = None

    scenarios = suggest_scenarios(subset, roles, scores_em_jogo, cutoff_steps=5)

    assert scenarios
    for scenario in scenarios:
        assert list(scenario.cutoffs) == scores_em_jogo


def test_suggest_scenarios_rejects_an_empty_short_list(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    with pytest.raises(ValueError):
        suggest_scenarios(subset, roles, [], cutoff_steps=5)


def test_session_suggest_scenarios_matches_a_direct_call(sample_df, roles):
    subset = population_filter(sample_df, roles, "DEV").head(800)
    scores_em_jogo = ("score_4", "score_5")

    page_scenarios = session.suggest_scenarios(
        subset, "parity-hash", "DEV", roles, roles_cache_key(roles), scores_em_jogo, 5
    )
    expected = suggest_scenarios(subset, roles, list(scores_em_jogo), cutoff_steps=5)

    assert page_scenarios == expected
