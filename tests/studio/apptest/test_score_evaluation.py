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


def test_marking_scores_em_jogo_persists_to_state(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "score_eval_em_jogo"]
    assert multiselects, "expected the scores em jogo multiselect"
    multiselects[0].set_value(["score_5", "legacy_score"])
    at.run()
    assert not at.exception
    assert at.session_state["studio"].scores_em_jogo == ["score_5", "legacy_score"]


def test_per_bucket_ks_table_tab_names_the_selected_score(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    tabs = [t for t in at.tabs if "decis" in t.label.lower()]
    assert tabs, "expected the per-bucket KS table tab"
    assert "undefined" not in tabs[0].label.lower()


def test_complementarity_panel_shows_an_info_message_with_no_scores_em_jogo(
    studio_state_with_roles,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception
    assert any("Complementaridade" in str(item.value) for item in at.subheader)
    assert len(at.info) >= 1


def test_marking_scores_em_jogo_renders_the_complementarity_table_vs_the_champion(
    studio_state_with_roles,
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "score_eval_em_jogo"]
    multiselects[0].set_value(["score_4", "score_5"])
    at.run()
    assert not at.exception

    assert any("score em uso" in str(item.value) for item in at.caption)
    dataframes = [d for d in at.dataframe if "candidate_score" in d.value.columns]
    assert dataframes, "expected the complementarity table"
    assert list(dataframes[0].value["candidate_score"]) == ["score_4"]


def test_complementarity_uses_vigente_score_as_reference_when_set(studio_state_with_roles):
    studio_state_with_roles.roles.vigente_score = "legacy_score"
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "score_eval_em_jogo"]
    multiselects[0].set_value(["score_4", "legacy_score"])
    at.run()
    assert not at.exception

    assert any("score vigente" in str(item.value) for item in at.caption)
    dataframes = [d for d in at.dataframe if "candidate_score" in d.value.columns]
    assert dataframes, "expected the complementarity table"
    assert list(dataframes[0].value["reference_score"]) == ["legacy_score"]
