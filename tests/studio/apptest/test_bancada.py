import dataclasses
import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from pycreditools.studio.models import PolicyEntry
from pycreditools.studio.policy_builder import build_policy, make_cutoff_row

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "3_Bancada.py")


@pytest.fixture
def studio_state_with_cutoff(studio_state_with_policy):
    """`StudioState` whose active policy also cuts `score_5` — gives it a score-in-use
    (ADR 0003) so the drag-the-cutoff trade-off section (#28) has something to sweep."""
    state = studio_state_with_policy
    rows = state.policies["v14"].rows + [
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600})
    ]
    policy = build_policy(state.roles, rows)
    entry = PolicyEntry(name="v14", policy=policy, rows=rows)
    return dataclasses.replace(state, policies={"v14": entry})


def test_page_without_roles_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_roles_creates_default_policy_and_renders_funnel(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=15)
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1
    assert len(at.dataframe) >= 1


def test_page_with_existing_policy_renders_its_rule_rows(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception
    name_inputs = [t for t in at.text_input if t.key and t.key.startswith("filter_name_")]
    assert len(name_inputs) == 4


def test_quickfill_v14_button_adds_four_filter_rows(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=15)
    assert not at.exception

    buttons = [b for b in at.button if b.key == "quickfill_v14"]
    assert buttons, "expected the v14 quick-fill button"
    buttons[0].click().run(timeout=15)
    assert not at.exception

    name_inputs = [t for t in at.text_input if t.key and t.key.startswith("filter_name_")]
    assert len(name_inputs) == 4


def test_adding_a_cutoff_row_does_not_raise(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=15)
    assert not at.exception

    buttons = [b for b in at.button if b.key == "add_cutoff"]
    assert buttons, "expected the add-cutoff button"
    buttons[0].click().run(timeout=15)
    assert not at.exception

    sliders = [s for s in at.slider if s.key and s.key.startswith("cutoff_val_")]
    assert sliders, "expected a cutoff slider after adding a cutoff row"


def test_duplicating_a_policy_edits_independently_from_the_original(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    buttons = [b for b in at.button if b.key == "policy_duplicate"]
    assert buttons, "expected the duplicate-policy button"
    buttons[0].click().run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert set(state.policies) == {"v14", "v14 (cópia)"}
    assert state.active_policy == "v14 (cópia)"
    original_value = state.policies["v14"].rows[0]["clauses"][0]["value"]

    toggles = [t for t in at.toggle if t.key and t.key.startswith("filter_val_")]
    assert toggles, "expected the boolean clause-value toggle on the duplicated policy"
    toggles[0].set_value(not toggles[0].value).run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.policies["v14"].rows[0]["clauses"][0]["value"] == original_value
    assert state.policies["v14 (cópia)"].rows[0]["clauses"][0]["value"] != original_value


def test_changing_population_rerenders_without_exception(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    selects = [s for s in at.selectbox if s.key == "bancada_population"]
    assert selects, "expected the population selectbox"
    selects[0].set_value("Todos").run(timeout=15)
    assert not at.exception


def test_survivor_caption_reflects_simulated_approved_population(studio_state_with_policy):
    """Survivor-based readouts use the live policy's simulated population (ADR 0001)."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception
    assert any("Sobreviventes aos filtros" in str(c.value) for c in at.caption)


def test_changing_a_cutoff_slider_recomputes_the_live_funnel(studio_state_with_policy):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    add_cutoff = [b for b in at.button if b.key == "add_cutoff"]
    assert add_cutoff, "expected the add-cutoff button"
    add_cutoff[0].click().run(timeout=15)
    assert not at.exception

    before = at.session_state["studio"].last_sim.to_funnel_dataframe()

    sliders = [s for s in at.slider if s.key and s.key.startswith("cutoff_val_")]
    assert sliders, "expected a cutoff slider after adding a cutoff row"
    new_value = sliders[0].min + (sliders[0].max - sliders[0].min) * 0.9
    sliders[0].set_value(new_value).run(timeout=15)
    assert not at.exception

    after = at.session_state["studio"].last_sim.to_funnel_dataframe()
    assert not before.equals(after)


def test_comparison_vs_base_renders_delta_and_quadrants_in_tier_b(studio_state_with_policy):
    """Tier B (the fixture's default roles: flag only, no vigente score) — full swap."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    assert any("Comparação vs. base" in str(item.value) for item in at.subheader)
    assert any("Taxa de aprovação" in str(item.value) for item in at.caption)
    assert any("Keep In" in str(item.value) for item in at.markdown)
    assert any("Swap In" in str(item.value) for item in at.markdown)


def test_comparison_vs_base_hides_swap_with_a_note_in_tier_c(studio_state_with_policy):
    """Tier C (no `current_approval_col` mapped) hides the swap UI with a pt-BR note."""
    state = studio_state_with_policy
    tier_c_roles = dataclasses.replace(state.roles, current_approval_col=None)
    tier_c_state = dataclasses.replace(state, roles=tier_c_roles)

    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = tier_c_state
    at.run(timeout=15)
    assert not at.exception

    assert any("Comparação vs. base" in str(item.value) for item in at.subheader)
    assert any("Tier C" in str(item.value) for item in at.info)
    assert not any("Keep In" in str(item.value) for item in at.markdown)
    assert not any("Swap In" in str(item.value) for item in at.markdown)


def test_without_a_cutoff_the_tradeoff_section_shows_an_info_hint(studio_state_with_policy):
    """No cutoff row -> no score-in-use (ADR 0003) -> nothing to sweep yet (#28)."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    assert any("Trade-off: arraste o corte" in str(item.value) for item in at.subheader)
    assert any("Adicione um corte" in str(item.value) for item in at.info)


def test_with_a_cutoff_the_tradeoff_curve_renders_for_the_score_in_use(studio_state_with_cutoff):
    """Drag-the-cutoff trade-off (ADR 0001, critique 2.3): renders a live curve for
    the contextual score-in-use, no separate Trade-off page (#28)."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_cutoff
    at.run(timeout=30)
    assert not at.exception

    assert any("Score em uso: **score_5**" in str(item.value) for item in at.caption)
    assert len(at.get("plotly_chart")) >= 2  # funnel + trade-off curve


def test_changing_the_cutoff_slider_updates_the_live_tradeoff_curve(studio_state_with_cutoff):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_cutoff
    at.run(timeout=30)
    assert not at.exception

    sliders = [s for s in at.slider if s.key and s.key.startswith("cutoff_val_")]
    assert sliders, "expected a cutoff slider for the existing score_5 cutoff row"
    new_value = sliders[0].min + (sliders[0].max - sliders[0].min) * 0.9
    sliders[0].set_value(new_value).run(timeout=30)
    assert not at.exception
    assert any("Score em uso: **score_5**" in str(item.value) for item in at.caption)


def test_aggravation_game_renders_slider_and_breakeven_kpi_in_tier_b(studio_state_with_policy):
    """Aggravation game (ADR 0001, critique 2.7): folds Crash Test into the Bancada (#28)."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    assert any("Jogo de agravamento" in str(item.value) for item in at.subheader)
    sliders = [s for s in at.slider if s.key == "bancada_aggravation_factor"]
    assert sliders, "expected the aggravation-factor slider"
    assert any("Fator de breakeven" in str(item.value) for item in at.caption)


def test_dragging_the_aggravation_slider_recomputes_the_curve_without_exception(
    studio_state_with_policy,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=30)
    assert not at.exception

    sliders = [s for s in at.slider if s.key == "bancada_aggravation_factor"]
    assert sliders, "expected the aggravation-factor slider"
    sliders[0].set_value(3.0).run(timeout=30)
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 1


def test_aggravation_game_skips_breakeven_with_a_note_in_tier_c(studio_state_with_policy):
    """Tier C (no base) — standalone curve, no breakeven (#28)."""
    tier_c_roles = dataclasses.replace(studio_state_with_policy.roles, current_approval_col=None)
    tier_c_state = dataclasses.replace(studio_state_with_policy, roles=tier_c_roles)

    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = tier_c_state
    at.run(timeout=30)
    assert not at.exception

    assert any("Jogo de agravamento" in str(item.value) for item in at.subheader)
    assert any("sem breakeven" in str(item.value) for item in at.caption)
