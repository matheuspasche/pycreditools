import dataclasses
import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "3_Bancada.py")


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
