import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "7_Risk_Grouping.py")


def test_page_without_dataset_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_page_with_roles_renders_groups_table_and_chart(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    assert len(at.get("plotly_chart")) >= 1
    assert len(at.dataframe) >= 1

    state = at.session_state["studio"]
    assert state.rating_result is not None
    assert state.rating_labels is not None


def test_confirm_active_rating_button_shows_toast(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    buttons = [b for b in at.button if b.key == "rg_confirm_active"]
    assert buttons, "expected the 'usar este rating' confirmation button"
    buttons[0].click().run(timeout=30)
    assert not at.exception


def test_unselecting_all_scores_shows_an_info_hint(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    multiselects = [m for m in at.multiselect if m.key == "rg_score_cols"]
    assert multiselects, "expected the score multiselect"
    multiselects[0].set_value([]).run(timeout=30)
    assert not at.exception
    assert any("Selecione ao menos um score" in str(item.value) for item in at.info)


def test_enabling_oot_toggle_renders_stability_report_and_vintage_chart(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    toggles = [t for t in at.toggle if t.key == "rg_use_time"]
    assert toggles, "expected the safra/OOT toggle"
    toggles[0].set_value(True).run(timeout=30)
    assert not at.exception

    subheaders = [str(item.value) for item in at.subheader]
    assert any("Estabilidade" in s for s in subheaders)
    assert len(at.get("plotly_chart")) >= 2


def test_pairwise_tab_runs_and_renders_per_challenger_expanders(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run(timeout=30)
    assert not at.exception

    challenger_multiselects = [m for m in at.multiselect if m.key == "rg_pw_challengers"]
    assert challenger_multiselects, "expected the pairwise challengers multiselect"
    primary_value = [s for s in at.selectbox if s.key == "rg_pw_primary"][0].value
    available = [
        s for s in challenger_multiselects[0].options if s != primary_value
    ]
    challenger_multiselects[0].set_value(available[:1]).run(timeout=30)
    assert not at.exception

    expanders = [e for e in at.get("expander")]
    assert expanders, "expected at least one pairwise result expander"
