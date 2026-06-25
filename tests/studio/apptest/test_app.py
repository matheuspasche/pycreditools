import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"


def test_app_runs_without_exception():
    at = AppTest.from_file(str(GUI / "app.py"))
    at.run()
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
