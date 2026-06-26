import dataclasses
import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "9_Crash_Test.py")


def test_page_without_policy_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_policy_runs_crash_test_and_shows_chart_table_and_kpi(
    studio_state_with_policy,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    assert len(at.get("plotly_chart")) >= 1
    assert len(at.dataframe) >= 1
    assert any("Fator de breakeven" in str(item.value) for item in at.caption)


def test_changing_the_population_selector_rerenders_without_exception(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    selects = [s for s in at.selectbox if s.key == "crash_population"]
    assert selects, "expected the population selectbox"
    selects[0].set_value("Todos").run(timeout=30)
    assert not at.exception


def test_no_baseline_and_no_hired_column_shows_a_manual_entry_hint(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    no_hired_roles = dataclasses.replace(studio_state_with_policy.roles, current_hired_col=None)
    state = dataclasses.replace(studio_state_with_policy, roles=no_hired_roles)
    at.session_state["studio"] = state
    at.run(timeout=30)
    assert not at.exception
    assert any("informe a inadimplência legada manualmente" in str(item.value) for item in at.info)


def test_breakeven_not_reached_shows_a_warning(studio_state_with_policy):
    """A near-zero factor range + a legacy bad rate of 100% can never be crossed."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    sliders = [s for s in at.slider if s.key == "crash_range"]
    assert sliders
    sliders[0].set_value((1.0, 1.01)).run(timeout=30)
    number_inputs = [n for n in at.number_input if n.key == "crash_legacy_bad_rate"]
    assert number_inputs
    number_inputs[0].set_value(1.0).run(timeout=30)
    assert not at.exception
    assert any("não atinge" in str(item.value).lower() for item in at.warning)
