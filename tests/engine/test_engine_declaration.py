"""The four declaration types: what each carries, and the hard errors that need no data.

Ticket 4 is the *expand* step of the package-level expand–contract, not a tracer bullet:
`simulate` lands in ticket 5, so nothing here runs a number. What is observable now is the
declaration itself — construction, the rung-1 errors, `repr`, and derivation.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from pycreditools import col
from pycreditools.engine import (
    CreditPolicy,
    DataSchema,
    LabelRequired,
    Premise,
    PremiseError,
    SchemaError,
    Study,
)

# --- DataSchema -------------------------------------------------------------------------


def test_schema_has_three_roles_and_nothing_else():
    assert list(inspect.signature(DataSchema).parameters) == ["approved", "hired", "outcome"]


def test_declaring_approved_requires_hired():
    with pytest.raises(SchemaError, match="hired= is required"):
        DataSchema(approved="approved")
    DataSchema(approved="approved", hired="hired")


def test_standalone_declares_no_role():
    assert DataSchema() == DataSchema(approved=None, hired=None, outcome=None)


def test_reuse_across_bases_is_dataclasses_replace():
    schema = DataSchema(approved="approved", hired="hired", outcome="ever60m6")
    other = dataclasses.replace(schema, outcome="fpd")
    assert other == DataSchema(approved="approved", hired="hired", outcome="fpd")
    with pytest.raises(SchemaError):
        dataclasses.replace(schema, hired=None)


@pytest.mark.parametrize("column", ["", 1, col("approved")])
def test_a_role_names_a_column(column):
    with pytest.raises(TypeError):
        DataSchema(outcome=column)


def test_schema_repr_round_trips():
    schema = DataSchema(approved="approved", hired="hired", outcome="bad")
    assert eval(repr(schema), {"DataSchema": DataSchema}) == schema


# --- CreditPolicy -----------------------------------------------------------------------


def test_policy_carries_stages_and_nothing_else():
    assert list(inspect.signature(CreditPolicy).parameters) == ["stages"]
    with pytest.raises(TypeError):
        CreditPolicy(applicant_id_col="id")  # the old kwargs break loud, not silently


def test_filter_returns_a_new_policy():
    empty = CreditPolicy()
    one = empty.filter(col("age") >= 18)
    assert empty.stages == ()
    assert len(one.stages) == 1


def test_label_defaults_to_the_one_referenced_column():
    policy = CreditPolicy().filter(col("age") >= 18).filter(col("desk_outcome"), draw=True)
    assert policy.labels == ("age", "desk_outcome")


def test_a_rule_over_two_columns_asks_for_a_label():
    with pytest.raises(LabelRequired, match="references 2 columns"):
        CreditPolicy().filter(col("score") >= col("regional_floor"))
    policy = CreditPolicy().filter(col("score") >= col("regional_floor"), label="regional_gate")
    assert policy.labels == ("regional_gate",)


def test_a_rule_over_no_column_is_unexpressible():
    """The third label case climbs to rung 1: there is no zero-column rule to label."""
    with pytest.raises(TypeError):
        CreditPolicy().filter(True)


def test_a_range_is_two_rules_and_the_collision_asks_for_names():
    with pytest.raises(LabelRequired, match="label='floor' / label='ceiling'"):
        CreditPolicy().filter(col("score_5") >= 600).filter(col("score_5") <= 900)
    policy = (
        CreditPolicy()
        .filter(col("score_5") >= 600, label="floor")
        .filter(col("score_5") <= 900, label="ceiling")
    )
    assert policy.labels == ("floor", "ceiling")


def test_a_duplicate_explicit_label_is_a_hard_error():
    with pytest.raises(LabelRequired):
        CreditPolicy().filter(col("a") >= 1, label="x").filter(col("b") >= 1, label="x")


def test_draw_is_a_bool():
    with pytest.raises(TypeError):
        CreditPolicy().filter(col("desk_outcome"), draw="yes")


def test_set_stage_swaps_one_field_and_keeps_everything_else():
    policy = (
        CreditPolicy()
        .filter(col("age") >= 18)
        .filter(col("desk_outcome"), draw=True, label="desk")
        .filter(col("score_5") >= 700, label="cut")
    )
    derived = policy.set_stage("desk", expr=col("desk_v2"))
    assert derived.stages[1].expr.columns() == ("desk_v2",)
    assert derived.stages[1].draw is True
    assert derived.stages[1].label == "desk"
    assert derived.stages[0] == policy.stages[0]
    assert derived.stages[2] == policy.stages[2]
    assert policy.stages[1].expr.columns() == ("desk_outcome",)  # the original is untouched


def test_set_stage_keeps_the_address_when_the_rule_changes_column():
    policy = CreditPolicy().filter(col("score_5") >= 700)
    derived = policy.set_stage("score_5", expr=col("score_6") >= 700)
    assert derived.labels == ("score_5",)


def test_set_stage_errors():
    policy = CreditPolicy().filter(col("a") >= 1).filter(col("b") >= 1)
    with pytest.raises(KeyError, match="no stage is labelled 'c'"):
        policy.set_stage("c", draw=True)
    with pytest.raises(TypeError, match="has no field"):
        policy.set_stage("a", cutoff=2)
    with pytest.raises(LabelRequired):
        policy.set_stage("a", label="b")


@pytest.mark.parametrize(
    "policy",
    [
        CreditPolicy(),
        CreditPolicy().filter(col("age") >= 18),
        CreditPolicy()
        .filter(col("age") >= 18)
        .filter(col("vl_negativacao") <= 0, label="antifraud")
        .filter((col("a") >= 700) & (col("b") >= 500), label="both")
        .filter(col("desk_outcome"), draw=True, label="desk"),
    ],
    ids=["empty", "one", "four"],
)
def test_policy_repr_round_trips(policy):
    assert eval(repr(policy), {"CreditPolicy": CreditPolicy, "col": col}) == policy


# --- Premise ----------------------------------------------------------------------------


def test_premise_has_six_keyword_fields_with_literal_defaults():
    params = inspect.signature(Premise).parameters
    assert list(params) == ["lens", "bins", "calibrate_on", "take_up", "stress", "outcome_from"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values())
    defaults = {name: p.default for name, p in params.items()}
    assert defaults == {
        "lens": None,
        "bins": 5,
        "calibrate_on": "global",
        "take_up": "binned",
        "stress": 1.0,
        "outcome_from": "parcelling",
    }


def test_the_three_external_outcome_scenarios_of_the_spec():
    Premise(take_up=0.7, outcome_from="market_default")  # A
    Premise(
        lens=col("score_5"),
        bins=10,
        calibrate_on="global",
        take_up="binned",
        outcome_from="market_default",
    )  # B
    Premise(take_up=0.7, outcome_from=col("pd_model"))  # C


def test_lens_is_required_when_an_axis_discretizes():
    with pytest.raises(PremiseError, match="lens= is required"):
        Premise()
    with pytest.raises(PremiseError, match="take_up='binned'"):
        Premise(outcome_from="market_default")
    with pytest.raises(PremiseError, match="outcome_from='parcelling'"):
        Premise(take_up=0.7)


def test_lens_is_refused_when_nothing_consumes_it():
    with pytest.raises(PremiseError, match="nothing consumes it"):
        Premise(lens=col("score_5"), take_up=0.7, outcome_from="market_default")


@pytest.mark.parametrize("stress", [1.8, (1.2, 1.5, 1.8), col("sector_factor")])
@pytest.mark.parametrize("outcome_from", ["market_default", col("pd_model")])
def test_stress_with_an_outcome_from_outside_is_a_hard_error(stress, outcome_from):
    with pytest.raises(PremiseError, match="nothing to inflate"):
        Premise(take_up=0.7, outcome_from=outcome_from, stress=stress)


def test_stress_one_is_no_inflation():
    Premise(take_up=0.7, outcome_from="market_default", stress=1.0)


def test_stress_takes_three_forms():
    lens = col("score_5")
    assert Premise(lens=lens, stress=1.8).stress == 1.8
    ladder = [1.2, 1.35, 1.5, 1.65, 1.8]
    premise = Premise(lens=lens, stress=ladder)
    ladder[0] = 99.0
    assert premise.stress == (1.2, 1.35, 1.5, 1.65, 1.8)
    assert Premise(lens=lens, stress=col("sector_factor")).stress.columns() == ("sector_factor",)


@pytest.mark.parametrize("stress", [0, -1.0, float("inf"), ()])
def test_stress_factors_are_finite_and_positive(stress):
    with pytest.raises(PremiseError):
        Premise(lens=col("s"), stress=stress)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("take_up", 1.5, PremiseError),
        ("take_up", "observed", PremiseError),
        ("take_up", True, TypeError),
        ("calibrate_on", "all", PremiseError),
        ("bins", 1, PremiseError),
        ("bins", 5.0, TypeError),
        ("lens", "score_5", TypeError),
        ("outcome_from", "", TypeError),
    ],
)
def test_field_domains(field, value, error):
    with pytest.raises(error):
        Premise(**{"lens": col("s"), field: value})


def test_bins_not_consumed_is_reported_in_the_premise_repr():
    assert "bins=5 (not consumed)" in repr(Premise(take_up=0.7, outcome_from="market_default"))
    assert "not consumed" not in repr(Premise(lens=col("score_5")))


# --- Study ------------------------------------------------------------------------------

SCHEMA = DataSchema(approved="approved", hired="hired", outcome="actual_default")
POLICY = (
    CreditPolicy()
    .filter(col("age") >= 18)
    .filter(col("vl_negativacao") <= 0, label="antifraud")
    .filter(col("score_5") >= 700, label="cut")
    .filter(col("desk_outcome"), draw=True, label="desk")
)
PREMISE = Premise(
    lens=col("score_5"),
    bins=5,
    calibrate_on="global",
    take_up="binned",
    stress=1.8,
    outcome_from="parcelling",
)


def test_study_signature():
    params = inspect.signature(Study).parameters
    assert list(params) == ["schema", "policy", "premise", "seed", "name"]
    kinds = [p.kind for p in params.values()]
    assert kinds[:3] == [inspect.Parameter.POSITIONAL_OR_KEYWORD] * 3
    assert kinds[3:] == [inspect.Parameter.KEYWORD_ONLY] * 2
    assert params["seed"].default is inspect.Parameter.empty
    assert params["name"].default is None


def test_the_premise_is_positional_and_required():
    with pytest.raises(TypeError):
        Study(SCHEMA, POLICY, seed=7)
    with pytest.raises(TypeError, match="a default premise would hide that imputation runs"):
        Study(SCHEMA, POLICY, None, seed=7)


def test_the_seed_is_required_and_keyword_only():
    with pytest.raises(TypeError):
        Study(SCHEMA, POLICY, PREMISE)
    with pytest.raises(TypeError):
        Study(SCHEMA, POLICY, PREMISE, 7)
    with pytest.raises(TypeError):
        Study(SCHEMA, POLICY, PREMISE, seed=True)


def test_repr_is_the_inventory():
    study = Study(SCHEMA, POLICY, PREMISE, seed=7, name="challenger")
    assert repr(study) == "\n".join(
        [
            "<Study challenger>",
            "  Schema:  approved='approved', hired='hired', outcome='actual_default'",
            "  Policy:  4 filters (1 draw)  ·  age, vl_negativacao, score_5, desk_outcome",
            "  Premise: lens=col('score_5'), bins=5, calibrate_on='global', take_up='binned', "
            "stress=1.8, outcome_from='parcelling'",
            "  Seed:    7",
        ]
    )


def test_repr_shows_what_is_not_declared():
    study = Study(DataSchema(), CreditPolicy(), Premise(lens=col("s")), seed=0)
    text = repr(study)
    assert text.startswith("<Study>\n")
    assert "Schema:  approved=None, hired=None, outcome=None" in text
    assert "Policy:  0 filters\n" in text


def test_a_lens_the_policy_does_not_reference_is_reported_by_the_study_only():
    premise = Premise(lens=col("score_c"), bins=10)
    study = Study(SCHEMA, POLICY, premise, seed=7)
    assert "lens=col('score_c') (not referenced by the policy), bins=10" in repr(study)
    assert "not referenced" not in repr(premise)
    assert "not referenced" not in repr(Study(SCHEMA, POLICY, PREMISE, seed=7))


def test_the_study_repeats_the_premise_report():
    premise = Premise(take_up=0.7, outcome_from="market_default")
    assert "bins=5 (not consumed)" in repr(Study(SCHEMA, POLICY, premise, seed=7))


def test_vary_derives_any_declared_point():
    study = Study(SCHEMA, POLICY, PREMISE, seed=7, name="challenger")
    varied = study.vary(
        schema={"outcome": "fpd"},
        premise={"stress": 2.2},
        policy={"cut": {"expr": col("score_5") >= 720}},
        seed=8,
    )
    assert varied.schema == dataclasses.replace(SCHEMA, outcome="fpd")
    assert varied.premise == dataclasses.replace(PREMISE, stress=2.2)
    assert varied.policy == POLICY.set_stage("cut", expr=col("score_5") >= 720)
    assert varied.seed == 8
    assert varied.name == "challenger"
    assert study.vary() == study


def test_rebuilding_is_not_varying():
    study = Study(SCHEMA, POLICY, PREMISE, seed=7)
    with pytest.raises(TypeError, match="derives; it does not rebuild"):
        study.vary(premise=Premise(lens=col("score_5"), stress=2.2))
    with pytest.raises(TypeError, match="derives; it does not rebuild"):
        study.vary(policy=POLICY)
    with pytest.raises(TypeError, match="has no field"):
        study.vary(method="analytical")
