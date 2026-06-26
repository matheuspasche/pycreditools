import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "8_Risk_Screening.py")


def test_page_without_dataset_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_without_rating_hints_to_pick_an_existing_column(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    selectboxes = [s for s in at.selectbox if s.key == "scr_base_col"]
    assert selectboxes, "expected the existing-rating-column picker when there's no active rating"


def test_page_with_rating_renders_iv_ranking_after_selecting_candidates(studio_state_with_rating):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_rating
    at.run(timeout=30)
    assert not at.exception

    radios = [r for r in at.radio if r.key == "scr_source"]
    assert radios, "expected the rating-source radio"
    assert radios[0].value == "Rating ativo"

    multiselects = [m for m in at.multiselect if m.key == "scr_candidates"]
    assert multiselects, "expected the candidate-variables multiselect"
    available = multiselects[0].options
    assert "age" in available
    assert "income" in available

    multiselects[0].set_value(["age", "income"]).run(timeout=30)
    assert not at.exception

    assert len(at.get("plotly_chart")) >= 1
    assert len(at.dataframe) >= 1

    state = at.session_state["studio"]
    assert state.screening_result is not None


def test_page_selecting_a_variable_renders_detail_table_and_heatmap(studio_state_with_rating):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_rating
    at.run(timeout=30)
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "scr_candidates"]
    multiselects[0].set_value(["age", "income"]).run(timeout=30)
    assert not at.exception

    detail_selects = [s for s in at.selectbox if s.key == "scr_detail_variable"]
    assert detail_selects, "expected the per-variable detail picker"
    detail_selects[0].set_value("income").run(timeout=30)
    assert not at.exception

    assert len(at.get("plotly_chart")) >= 2
    subheaders = [str(item.value) for item in at.subheader]
    assert any("Detalhe por variável" in s for s in subheaders)


def test_unselecting_all_candidates_shows_an_info_hint(studio_state_with_rating):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_rating
    at.run(timeout=30)
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "scr_candidates"]
    multiselects[0].set_value([]).run(timeout=30)
    assert not at.exception
    assert any("Selecione ao menos uma variável" in str(item.value) for item in at.info)
