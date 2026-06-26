import dataclasses
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "5_Tradeoff.py")


@pytest.fixture
def studio_state_with_baseline(studio_state_with_policy):
    """`StudioState` with `legacy_sim` set to the active policy's own simulation.

    Local to this file: PRD 06 just needs *some* baseline with an observed
    `simulated_default` so `policy_kpis` yields a non-None `bad_rate` and the
    executive-scenarios section renders.
    """
    entry = studio_state_with_policy.policies["v14"]
    sim = entry.policy.simulate(studio_state_with_policy.df, method="analytical")
    return dataclasses.replace(studio_state_with_policy, legacy_sim=sim)


def test_page_without_policy_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_policy_but_no_baseline_renders_frontier_and_hides_scenarios(
    studio_state_with_policy,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    assert any("Cenários executivos" in str(item.value) for item in at.subheader)
    assert any("baseline" in str(item.value) for item in at.info)
    assert len(at.get("plotly_chart")) >= 1


def test_page_with_baseline_renders_scenario_cards_and_table(studio_state_with_baseline):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_baseline
    at.run(timeout=30)
    assert not at.exception

    assert any("Conservador" in str(item.value) for item in at.caption)
    assert any("Agressivo" in str(item.value) for item in at.caption)
    assert any("Neutro" in str(item.value) for item in at.caption)
    assert len(at.dataframe) >= 1


def test_applying_a_scenario_updates_the_policy_entry_rows(studio_state_with_baseline):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_baseline
    at.run(timeout=30)
    assert not at.exception

    buttons = [b for b in at.button if b.label == "Aplicar cutoff ao Policy Studio"]
    assert buttons, "expected the apply-cutoff button"
    buttons[0].click().run(timeout=30)
    assert not at.exception

    state = at.session_state["studio"]
    entry = state.policies[state.active_policy]
    cutoff_rows = [r for r in entry.rows if r["type"] == "cutoff"]
    assert any("score_5" in row["cutoffs"] for row in cutoff_rows)


def test_changing_the_score_multiselect_rerenders_without_exception(studio_state_with_baseline):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_baseline
    at.run(timeout=30)
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "tradeoff_scores"]
    assert multiselects, "expected the scores multiselect"
    only_score_5 = ["score_5"]
    multiselects[0].set_value(only_score_5).run(timeout=30)
    assert not at.exception


def test_unselecting_all_scores_shows_an_info_hint(studio_state_with_baseline):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_baseline
    at.run(timeout=30)
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "tradeoff_scores"]
    assert multiselects, "expected the scores multiselect"
    multiselects[0].set_value([]).run(timeout=30)
    assert not at.exception
    assert any("Selecione ao menos um score" in str(item.value) for item in at.info)
