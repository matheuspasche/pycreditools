import json
import pathlib

from streamlit.testing.v1 import AppTest

GUI = pathlib.Path(__file__).resolve().parents[3] / "src" / "pycreditools" / "gui"
PAGE = str(GUI / "pages" / "10_Deployment.py")


def test_page_without_policy_shows_warning_not_traceback():
    at = AppTest.from_file(PAGE)
    at.run(timeout=15)
    assert not at.exception
    assert len(at.warning) >= 1


def test_export_tab_shows_json_and_download_buttons(studio_state_with_deployment):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_deployment
    at.run(timeout=30)
    assert not at.exception

    assert any("{" in str(item.value) for item in at.get("code"))
    download_ids = {b.proto.id for b in at.get("download_button")}
    assert any(i.endswith("-dl_full_policy") for i in download_ids)
    assert any(i.endswith("-dl_production_rules") for i in download_ids)


def test_toggling_clean_export_does_not_raise(studio_state_with_deployment):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_deployment
    at.run(timeout=30)
    assert not at.exception

    toggles = [t for t in at.toggle if t.key == "dep_clean"]
    assert toggles, "expected the clean-export toggle"
    toggles[0].set_value(True).run(timeout=30)
    assert not at.exception


def test_scoring_tab_with_injected_file_produces_decisions_table(
    studio_state_with_deployment, sample_df
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_deployment
    at.run(timeout=30)
    assert not at.exception

    uploaders = [u for u in at.file_uploader if u.key == "dep_score_file"]
    assert uploaders, "expected the applicant-file uploader in the scoring tab"

    csv_bytes = sample_df.head(100).to_csv(index=False).encode("utf-8")
    uploaders[0].set_value(("applicants.csv", csv_bytes, "text/csv"))
    at.run(timeout=30)
    assert not at.exception

    assert len(at.dataframe) >= 1
    download_ids = {b.proto.id for b in at.get("download_button")}
    assert any(i.endswith("-dl_scored_csv") for i in download_ids)


def test_scoring_tab_with_uploaded_policy_json_scores_the_file(
    studio_state_with_deployment, sample_df
):
    at = AppTest.from_file(PAGE)
    at.session_state["studio"] = studio_state_with_deployment
    at.run(timeout=30)
    assert not at.exception

    sources = [r for r in at.radio if r.key == "dep_score_source"]
    assert sources, "expected the policy-source radio"
    sources[0].set_value("Carregar JSON salvo")
    at.run(timeout=30)
    assert not at.exception

    policy_uploaders = [u for u in at.file_uploader if u.key == "dep_policy_upload"]
    assert policy_uploaders, "expected the policy-json uploader"

    state = at.session_state["studio"]
    entry = state.policies[state.active_policy]
    dep = entry.policy.export(rating_recipe=state.rating_result.recipe)
    policy_bytes = json.dumps(dep.to_dict()).encode("utf-8")
    policy_uploaders[0].set_value(("policy.json", policy_bytes, "application/json"))
    at.run(timeout=30)
    assert not at.exception

    file_uploaders = [u for u in at.file_uploader if u.key == "dep_score_file"]
    assert file_uploaders, "expected the applicant-file uploader after policy upload"
    csv_bytes = sample_df.head(50).to_csv(index=False).encode("utf-8")
    file_uploaders[0].set_value(("applicants.csv", csv_bytes, "text/csv"))
    at.run(timeout=30)
    assert not at.exception
    assert len(at.dataframe) >= 1
