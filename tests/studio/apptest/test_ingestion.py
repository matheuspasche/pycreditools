import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "1_Ingestion.py")


def test_ingestion_page_shows_uploader_with_empty_state():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 2


def test_ingestion_page_with_injected_dataset_shows_kpis_and_preview(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception
    assert len(at.dataframe) >= 1


def test_generate_sample_button_populates_state():
    at = AppTest.from_file(PAGE)
    at.run()
    assert not at.exception

    buttons = [b for b in at.button if b.label == "Gerar base de exemplo"]
    assert buttons, "expected a 'Gerar base de exemplo' button"
    buttons[0].click()
    at.run()
    assert not at.exception
    state = at.session_state["studio"]
    assert state.df is not None
    assert state.roles.applicant_id_col == "applicant_id"


def test_changing_a_role_updates_session_state(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception

    tab_roles = at.tabs[1]
    selects = [s for s in tab_roles.selectbox if s.key == "role_primary_score"]
    assert selects, "expected the primary-score selectbox in the 'Mapear colunas' tab"
    selects[0].set_value("score_2")
    at.run()
    assert not at.exception
    state = at.session_state["studio"]
    assert state.roles.primary_score_col == "score_2"


def test_ingestion_page_shows_tier_badge_when_dataset_loaded(studio_state_with_roles):
    """`studio_state_with_roles` has an approval flag but no vigente score -> Tier B."""
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    assert not at.exception
    assert any("Tier B" in i.value for i in at.info)


def test_pd_estimada_role_hidden_outside_tier_c(studio_state_with_roles):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_roles
    at.run()
    tab_roles = at.tabs[1]
    selects = [s for s in tab_roles.selectbox if s.key == "role_estimated"]
    assert not selects


def test_pd_estimada_role_visible_in_tier_c(sample_df):
    from pycreditools.studio.models import ColumnRoles, StudioState

    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = StudioState(
        df_name="sample", df=sample_df, df_hash="x", roles=ColumnRoles()
    )
    at.run()
    assert not at.exception
    assert any("Tier C" in i.value for i in at.info)
    tab_roles = at.tabs[1]
    selects = [s for s in tab_roles.selectbox if s.key == "role_estimated"]
    assert selects
