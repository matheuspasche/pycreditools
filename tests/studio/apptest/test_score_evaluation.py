import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "2_Score_Evaluation.py")


def test_page_without_roles_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_roles_renders_ranking_and_table(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception
    assert len(at.get("plotly_chart")) >= 2  # bar ranking + KS curve
    assert len(at.dataframe) >= 1
    assert any("score_5" in str(item.value) for item in at.markdown)


def test_changing_bins_rerenders_without_exception(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    sliders = [s for s in at.slider if s.key == "score_eval_bins"]
    assert sliders, "expected the buckets slider"
    sliders[0].set_value(6)
    at.run()
    assert not at.exception


def test_changing_population_rerenders_without_exception(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    selects = [s for s in at.selectbox if s.key == "score_eval_population"]
    assert selects, "expected the population selectbox"
    selects[0].set_value("Aprovados")
    at.run()
    assert not at.exception
