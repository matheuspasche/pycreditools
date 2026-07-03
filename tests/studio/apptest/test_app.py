import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"


def test_app_runs_without_exception():
    at = AppTest.from_file(str(GUI / "app.py"))
    at.run(timeout=15)
    assert not at.exception


def test_ingestion_page_runs_without_exception():
    at = AppTest.from_file(str(GUI / "pages" / "1_Ingestion.py"))
    at.run()
    assert not at.exception


def test_page_without_dataset_shows_warning_not_traceback():
    at = AppTest.from_file(str(GUI / "pages" / "2_Score_Evaluation.py"))
    at.run()
    assert not at.exception
    assert len(at.warning) >= 1
    assert "Carregue uma base" in at.warning[0].value


def test_page_with_injected_dataset_does_not_warn(studio_state_with_roles):
    at = AppTest.from_file(str(GUI / "pages" / "2_Score_Evaluation.py"))
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception
    assert len(at.warning) == 0


def test_sidebar_session_action_is_a_discreet_popover_not_a_first_screen_button(
    studio_state_with_policy,
):
    """The unified save/load (#37) is a sidebar popover, not a prominent button."""
    at = AppTest.from_file(str(GUI / "app.py"))
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    popovers = at.get("popover")
    assert len(popovers) == 1
    assert not any(b.label == "Salvar sessão" and not b.proto.disabled for b in at.button)


def test_save_then_load_session_via_sidebar_popover_restores_state(
    studio_state_with_policy, tmp_path
):
    at = AppTest.from_file(str(GUI / "app.py"))
    at.session_state["studio"] = studio_state_with_policy
    at.run(timeout=15)
    assert not at.exception

    at.text_input(key="project_save_name").set_value("acme")
    at.text_input(key="project_save_dir").set_value(str(tmp_path))
    at.run(timeout=15)
    save_button = next(b for b in at.button if b.label == "Salvar sessão")
    save_button.click().run(timeout=15)
    assert not at.exception
    assert (tmp_path / "acme.json").exists()

    at.session_state["studio"] = type(studio_state_with_policy)()
    at.run(timeout=15)
    at.text_input(key="project_load_dir").set_value(str(tmp_path))
    at.run(timeout=15)
    at.selectbox(key="project_load_select").set_value("acme")
    at.run(timeout=15)
    load_button = next(b for b in at.button if b.label == "Carregar sessão")
    load_button.click().run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.active_policy == "v14"
    assert "v14" in state.policies


def test_load_session_rehydrates_rating_result(studio_state_with_rating, tmp_path):
    """Load must restore rating_result so Bancada/Deploy don't silently lose the matrix (#40)."""
    at = AppTest.from_file(str(GUI / "app.py"))
    at.session_state["studio"] = studio_state_with_rating
    at.run(timeout=15)
    assert not at.exception

    at.text_input(key="project_save_name").set_value("with-rating")
    at.text_input(key="project_save_dir").set_value(str(tmp_path))
    at.run(timeout=15)
    save_button = next(b for b in at.button if b.label == "Salvar sessão")
    save_button.click().run(timeout=15)
    assert not at.exception
    assert (tmp_path / "with-rating.json").exists()

    at.session_state["studio"] = type(studio_state_with_rating)()
    at.run(timeout=15)
    at.text_input(key="project_load_dir").set_value(str(tmp_path))
    at.run(timeout=15)
    at.selectbox(key="project_load_select").set_value("with-rating")
    at.run(timeout=15)
    load_button = next(b for b in at.button if b.label == "Carregar sessão")
    load_button.click().run(timeout=15)
    assert not at.exception

    state = at.session_state["studio"]
    assert state.rating_result is not None, "rating_result deve ser reidratado no load"
    assert state.rating_result.recipe is not None
    original_recipe = studio_state_with_rating.rating_result.recipe.to_dict()
    assert state.rating_result.recipe.to_dict() == original_recipe
