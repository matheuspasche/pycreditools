import dataclasses
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "6_Optimization.py")


@pytest.fixture
def studio_state_single_score(studio_state_with_policy):
    """`StudioState` whose active policy only optimizes `score_5` (a small grid)."""
    entry = studio_state_with_policy.policies["v14"]
    single_score_policy = dataclasses.replace(entry.policy, score_cols=("score_5",))
    single_score_entry = dataclasses.replace(entry, policy=single_score_policy)
    return dataclasses.replace(
        studio_state_with_policy, policies={"v14": single_score_entry}
    )


def test_page_without_policy_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_multi_score_policy_shows_grid_size_warning(studio_state_with_policy):
    """The v14-quickfill fixture's policy has several score_cols -> an explosive grid by default."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception
    checkboxes = [c for c in at.checkbox if c.key == "opt_confirm_large_grid"]
    assert checkboxes, "expected the large-grid confirmation checkbox"
    assert "combinações" in checkboxes[0].label
    assert any("Reduza o nº de passos" in str(item.value) for item in at.warning)


def test_page_with_single_score_renders_kpis_and_pareto_chart(studio_state_single_score):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_single_score
    at.run(timeout=30)
    assert not at.exception

    assert len(at.get("plotly_chart")) >= 1
    markdowns = [str(item.value) for item in at.markdown]
    assert any("###" in md for md in markdowns)  # KPI cards render a big value


def test_page_confirming_a_large_grid_runs_the_optimization(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    # Lower the steps so the (still > threshold) grid stays fast to actually compute.
    sliders = [s for s in at.slider if s.key == "opt_steps"]
    assert sliders, "expected the cutoff-steps slider"
    sliders[0].set_value(5).run(timeout=30)

    checkboxes = [c for c in at.checkbox if c.key == "opt_confirm_large_grid"]
    assert checkboxes, "expected the large-grid confirmation checkbox"
    checkboxes[0].set_value(True).run(timeout=60)
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1


def test_applying_best_combination_updates_the_policy_entry_rows(studio_state_single_score):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_single_score
    at.run(timeout=30)
    assert not at.exception

    buttons = [b for b in at.button if b.label == "Aplicar melhor combinação à Bancada"]
    assert buttons, "expected the apply-best-combination button"
    buttons[0].click().run(timeout=30)
    assert not at.exception

    state = at.session_state["studio"]
    entry = state.policies[state.active_policy]
    cutoff_rows = [r for r in entry.rows if r["type"] == "cutoff"]
    assert any("score_5" in row["cutoffs"] for row in cutoff_rows)


def test_find_equivalent_panel_renders_a_table(studio_state_single_score):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_single_score
    at.run(timeout=30)
    assert not at.exception
    assert any("Encontrar equivalente" in str(item.value) for item in at.subheader)
    assert len(at.dataframe) >= 1
