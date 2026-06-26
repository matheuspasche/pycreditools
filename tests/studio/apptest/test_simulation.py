import dataclasses
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from pycreditools import fit_risk_groups
from pycreditools.studio.data import population_filter

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "4_Simulation.py")


@pytest.fixture
def studio_state_with_rating(studio_state_with_policy, roles):
    """`StudioState` with a fitted rating attached.

    Local to this file, not added to the shared `conftest.py`: per
    `IMPLEMENTATION_GUIDE.md` §5, `studio_state_with_rating` is PRD 08's fixture to
    add. PRD 05 only needs *some* fitted rating to exercise its rating-aware
    sections, so it fits one directly via the already-existing `fit_risk_groups`
    engine call instead of waiting on PRD 08's studio wrapper.
    """
    hired = population_filter(studio_state_with_policy.df, roles, "Contratados")
    result = fit_risk_groups(hired, ["score_5"], roles.actual_default_col, max_groups=4)
    ordered_ratings = result.groups.sort_values("pd")["risk_rating"].tolist()
    labels = dict(zip(ordered_ratings, ["A", "B", "C", "D", "E"]))
    return dataclasses.replace(
        studio_state_with_policy, rating_result=result, rating_labels=labels
    )


def test_page_without_policy_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_policy_runs_simulation_and_renders_kpis_and_quadrants(
    studio_state_with_policy,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.last_sim is not None

    assert any("Taxa de aprovação" in str(item.value) for item in at.caption)
    assert any("Quadrantes de swap" in str(item.value) for item in at.subheader)
    assert len(at.dataframe) >= 1


def test_page_without_rating_hides_swap_in_by_rating_with_a_hint(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception
    assert any("Risk Grouping" in str(item.value) for item in at.info)


def test_page_with_rating_renders_swap_in_by_rating_section(studio_state_with_rating):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_rating
    at.run(timeout=15)
    assert not at.exception
    assert any("Swap-in por rating" in str(item.value) for item in at.subheader)
    assert len(at.tabs) >= 1


def test_defining_baseline_button_stores_legacy_sim_and_renders_comparison(
    studio_state_with_policy,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    buttons = [
        b for b in at.button if b.label.startswith("📌 Definir baseline = política atual")
    ]
    assert buttons, "expected the 'set baseline = current policy' button"
    buttons[0].click().run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.legacy_sim is not None
    assert any("Comparação vs. baseline" in str(item.value) for item in at.subheader)


def test_legacy_cutoff_baseline_button_stores_legacy_sim(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    buttons = [b for b in at.button if b.label.startswith("🏛️ Baseline = cutoff legado")]
    assert buttons, "expected the 'legacy cutoff baseline' button"
    buttons[0].click().run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.legacy_sim is not None


def test_changing_population_rerenders_without_exception(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    selects = [s for s in at.selectbox if s.key == "sim_population"]
    assert selects, "expected the population selectbox"
    selects[0].set_value("Todos").run(timeout=15)
    assert not at.exception


def test_switching_to_stochastic_method_rerenders_without_exception(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    radios = [r for r in at.radio if r.key == "sim_method"]
    assert radios, "expected the method radio"
    radios[0].set_value("stochastic").run(timeout=15)
    assert not at.exception
