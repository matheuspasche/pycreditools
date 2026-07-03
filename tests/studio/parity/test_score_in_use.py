"""ADR 0003: score-in-use is contextual; cutoff axis and PD calibration are bound."""

from pycreditools.studio.policy_builder import build_policy, make_cutoff_row


def test_build_policy_binds_calibration_score_to_the_cutoff_score(roles):
    rows = [make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600})]
    policy = build_policy(roles, rows)
    assert policy.calibration_score_col == "score_5"


def test_changing_the_cutoff_score_updates_the_calibration_score(roles):
    rows_score_5 = [make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600})]
    rows_score_3 = [make_cutoff_row(name="Corte score_3", cutoffs={"score_3": 400})]
    assert build_policy(roles, rows_score_5).calibration_score_col == "score_5"
    assert build_policy(roles, rows_score_3).calibration_score_col == "score_3"


def test_calibration_score_tracks_the_most_recently_set_cutoff_score(roles):
    rows = [
        make_cutoff_row(name="Corte score_3", cutoffs={"score_3": 400}),
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
    ]
    assert build_policy(roles, rows).calibration_score_col == "score_5"


def test_no_cutoff_rows_leaves_calibration_score_unset(roles):
    assert build_policy(roles, []).calibration_score_col is None


def test_cutoff_score_and_calibration_score_can_never_diverge_through_the_builder_api(roles):
    """Regression: there is no path through the builder API that lets the cutoff
    score and the PD calibration score point at different columns (ADR 0003)."""
    rows = [
        make_cutoff_row(name="Corte score_3", cutoffs={"score_3": 400}),
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
    ]
    policy = build_policy(roles, rows)
    cutoff_scores = {score for stage in policy.stages for score in getattr(stage, "cutoffs", {})}
    assert policy.calibration_score_col in cutoff_scores
