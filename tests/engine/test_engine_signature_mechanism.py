"""DoD 2: every rebuild is total, by construction (§6, ticket 4).

One mechanism driven by the constructor's signature, three consumers — `to_dict`, `from_dict`
and `replace` — and `set_stage` / `vary` / `.filter` are callers of `replace`, not parallel
rebuilds. The partial-rebuild family (#94/#99/#103, #133) was a caller listing the fields it
remembered; here no caller lists fields.

The totality tests are driven by `inspect.signature`, the way the five strict-xfail tests of
`tests/test_sweep_rebuild_preserves_stage_fields.py` are. Those stay red against the old tree
until ticket 14 rewrites them on this surface; they do not import this one.

The exemplars must hold a non-default value in every field that has a default — otherwise a
dropped field falls back to its default and the round-trip passes on exactly the case the bug
exploits. `test_every_defaulted_field_is_exercised` enforces that, and
`test_every_value_type_has_an_exemplar` fails the day a new value type is registered without one.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
from types import MappingProxyType

import pytest

from pycreditools import col
from pycreditools.engine import CreditPolicy, DataSchema, Premise, Study, _value
from pycreditools.engine._nodes import BinaryNode, ColumnNode, UnaryNode
from pycreditools.engine.policy import Filter

SCHEMA = DataSchema(approved="approved", hired="hired", outcome="bad")
DESK = Filter(col("desk_outcome"), draw=True, label="desk")
POLICY = CreditPolicy(
    stages=(Filter(col("score") >= 700, label="cut"), DESK, Filter(~col("fraud_flag")))
)
PARCELLING = Premise(
    lens=col("score"),
    bins=7,
    calibrate_on="keep_in",
    take_up=col("p_take_up"),
    stress=(1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8),
)
EXTERNAL = Premise(take_up=0.7, outcome_from="market_default")
STUDY = Study(SCHEMA, POLICY, PARCELLING, seed=11, name="challenger")

EXEMPLARS = [
    ColumnNode("score"),
    BinaryNode(ColumnNode("score"), ">=", 700),
    UnaryNode(ColumnNode("flag"), "~"),
    SCHEMA,
    DESK,
    POLICY,
    PARCELLING,
    EXTERNAL,
    STUDY,
]


def _id(value):
    return type(value).__name__


def test_every_value_type_has_an_exemplar():
    assert set(_value._REGISTRY) == {type(e).__name__ for e in EXEMPLARS}


def test_every_defaulted_field_is_exercised():
    for cls in {type(e) for e in EXEMPLARS}:
        for name, param in inspect.signature(cls).parameters.items():
            if param.default is inspect.Parameter.empty:
                continue
            assert any(getattr(e, name) != param.default for e in EXEMPLARS if type(e) is cls), (
                f"no exemplar of {cls.__name__} sets {name}= off its default"
            )


@pytest.mark.parametrize("value", EXEMPLARS, ids=_id)
def test_replace_with_no_change_is_the_same_value(value):
    assert _value.replace(value) == value
    assert dataclasses.replace(value) == value


@pytest.mark.parametrize("value", EXEMPLARS, ids=_id)
def test_to_dict_from_dict_round_trips(value):
    data = _value.to_dict(value)
    assert _value.from_dict(data) == value
    assert _value.from_dict(json.loads(json.dumps(data))) == value


@pytest.mark.parametrize("value", EXEMPLARS, ids=_id)
def test_to_dict_writes_exactly_the_signature(value):
    data = _value.to_dict(value)
    assert list(data) == ["type", *inspect.signature(type(value)).parameters]


def _carried(before, after, swapped):
    fields = inspect.signature(type(before)).parameters
    return [f for f in fields if f not in swapped and getattr(after, f) != getattr(before, f)]


def test_set_stage_carries_every_field_it_was_not_asked_to_swap():
    derived = POLICY.set_stage("desk", expr=col("desk_v2"))
    assert derived.stages[1].expr == ColumnNode("desk_v2")
    assert not _carried(DESK, derived.stages[1], {"expr"})


@pytest.mark.parametrize(
    ("component", "change"),
    [
        ("premise", {"bins": 9}),
        ("premise", {"calibrate_on": "global"}),
        ("schema", {"outcome": "fpd"}),
    ],
)
def test_vary_carries_every_field_it_was_not_asked_to_swap(component, change):
    varied = STUDY.vary(**{component: change})
    assert not _carried(getattr(STUDY, component), getattr(varied, component), set(change))
    assert not _carried(STUDY, varied, {component})


def test_vary_on_a_stage_carries_the_rest_of_the_stage_and_of_the_study():
    varied = STUDY.vary(policy={"desk": {"draw": False}})
    assert varied.policy.stages[1].draw is False
    assert not _carried(DESK, varied.policy.stages[1], {"draw"})
    assert not _carried(STUDY, varied, {"policy"})


def test_the_builder_moves_are_callers_of_the_one_replace(monkeypatch):
    """The acceptance criterion read literally: one mechanism, and the verbs consume it."""
    seen = []
    original = _value.replace

    def spy(value, /, **changes):
        seen.append(type(value).__name__)
        return original(value, **changes)

    monkeypatch.setattr(_value, "replace", spy)

    CreditPolicy().filter(col("a") >= 1)
    assert seen == ["CreditPolicy"]

    seen.clear()
    POLICY.set_stage("cut", expr=col("score") >= 720)
    assert seen == ["Filter", "CreditPolicy"]

    seen.clear()
    STUDY.vary(premise={"bins": 9}, policy={"cut": {"expr": col("score") >= 720}})
    assert seen == ["Premise", "Filter", "CreditPolicy", "Study"]


# --- deep freeze -------------------------------------------------------------------------


def test_the_policy_is_frozen_to_the_leaf():
    with pytest.raises(dataclasses.FrozenInstanceError):
        POLICY.stages[0].expr.right = 500
    with pytest.raises(dataclasses.FrozenInstanceError):
        POLICY.stages[0].label = "other"
    with pytest.raises(AttributeError):
        POLICY.stages.append(DESK)


def test_containers_are_normalized_on_the_way_in():
    stages = [DESK]
    policy = CreditPolicy(stages=stages)
    stages.append(Filter(col("x") >= 1))
    assert policy.stages == (DESK,)

    frozen = _value.freeze({"a": [1, {"b": 2}]})
    assert isinstance(frozen, MappingProxyType)
    assert frozen["a"] == (1, MappingProxyType({"b": 2}))
    with pytest.raises(TypeError):
        frozen["a"] = 0


def test_declarations_are_hashable_values():
    assert hash(STUDY) == hash(Study(SCHEMA, POLICY, PARCELLING, seed=11, name="challenger"))


# --- callables are refused at the constructor -------------------------------------------


def _fn(df):
    return df["a"] > 1


@pytest.mark.parametrize(
    "build",
    [
        lambda: CreditPolicy().filter(_fn),
        lambda: Filter(_fn),
        lambda: Premise(lens=_fn),
        lambda: Premise(lens=col("s"), take_up=_fn),
        lambda: Premise(lens=col("s"), stress=_fn),
        lambda: Premise(take_up=0.7, outcome_from=_fn),
        lambda: Premise(lens=col("s"), stress=[1.2, _fn]),
    ],
)
def test_a_callable_is_refused_at_the_constructor(build):
    with pytest.raises(TypeError, match="callable is not expressible"):
        build()


# --- from_dict is strict ----------------------------------------------------------------


def test_from_dict_refuses_what_to_dict_never_writes():
    data = _value.to_dict(SCHEMA)
    with pytest.raises(ValueError, match="missing"):
        _value.from_dict({k: v for k, v in data.items() if k != "hired"})
    with pytest.raises(ValueError, match="unknown"):
        _value.from_dict({**data, "applicant_id": "id"})
    with pytest.raises(ValueError, match="unknown value type"):
        _value.from_dict({**data, "type": "CutStage"})
    with pytest.raises(ValueError, match="no 'type' tag"):
        _value.from_dict({"approved": "approved"})
