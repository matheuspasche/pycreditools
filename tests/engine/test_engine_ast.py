"""The AST is pure, frozen, and its `repr` round-trips (§4.3).

The user writes with the builder in `pycreditools.expressions`; a declaration holds the frozen
tree it is converted into. `repr` is the Python render and must build the same tree back;
`pretty` is presentation and is never parsed.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from pycreditools import col
from pycreditools.engine._nodes import BinaryNode, ColumnNode, UnaryNode, from_builder
from pycreditools.engine._value import from_dict, to_dict

EXPRESSIONS = [
    col("age") >= 18,
    col("vl_negativacao") <= 1500.5,
    col("cpf_valido") == True,  # noqa: E712 — the builder's == builds a node
    col("region") != "SP",
    (col("a") >= 700) & (col("b") <= 500),
    (col("a") >= 700) | ~(col("b") == 1),
    ~col("flag"),
    col("income") / col("debt") > 0.3,
    2 * col("score") - 100 >= col("floor"),
    col("desk_outcome"),
]


@pytest.mark.parametrize("builder", EXPRESSIONS, ids=repr)
def test_repr_builds_the_same_tree_back(builder):
    node = from_builder(builder)
    again = from_builder(eval(repr(node), {"col": col}))
    assert again == node
    assert repr(again) == repr(node)


@pytest.mark.parametrize("builder", EXPRESSIONS, ids=repr)
def test_the_tree_survives_json(builder):
    node = from_builder(builder)
    assert from_dict(json.loads(json.dumps(to_dict(node)))) == node


@pytest.mark.parametrize(
    ("builder", "pretty"),
    [
        (col("age") >= 18, "age >= 18"),
        (col("cpf_valido") == True, "cpf_valido == True"),  # noqa: E712
        (col("region") != "SP", "region != 'SP'"),
        ((col("a") >= 700) & (col("b") <= 500), "(a >= 700) & (b <= 500)"),
        (~col("flag"), "~flag"),
    ],
)
def test_pretty_is_presentation(builder, pretty):
    assert from_builder(builder).pretty() == pretty


def test_calibrated_is_refused_so_the_ast_stays_pure():
    with pytest.raises(TypeError, match=r"\.calibrated\(\) dies"):
        from_builder((col("a") >= 1).calibrated())
    with pytest.raises(TypeError, match=r"\.calibrated\(\) dies"):
        from_builder((col("a") >= 1) & (col("b") >= 2).calibrated())


def test_a_rule_over_no_column_is_unexpressible():
    with pytest.raises(TypeError, match="references no column"):
        BinaryNode(1, "+", 2)


@pytest.mark.parametrize("literal", [float("nan"), float("inf"), None, [1, 2], object()])
def test_literals_are_int_finite_float_bool_str(literal):
    with pytest.raises(TypeError):
        from_builder(col("a") >= literal)


def test_numpy_scalars_become_python_literals():
    node = from_builder(col("a") >= np.int64(700))
    assert node == from_builder(col("a") >= 700)
    assert repr(node) == "col('a') >= 700"


def test_one_canonical_form_node_on_the_left():
    """A literal-left tree (only reachable from a dict) would not re-evaluate to itself."""
    assert BinaryNode(700, "<", ColumnNode("s")) == from_builder(col("s") > 700)
    assert BinaryNode(True, "&", ColumnNode("s")) == BinaryNode(ColumnNode("s"), "&", True)
    assert from_builder(700 < col("s")) == from_builder(col("s") > 700)


def test_columns_in_order_of_first_appearance():
    node = from_builder((col("b") >= 1) & (col("a") <= col("b")))
    assert node.columns() == ("b", "a")


def test_frozen_to_the_leaf():
    node = from_builder((col("a") >= 700) & ~col("b"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.left.right = 500
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.right.operand.name = "c"
    assert isinstance(node.right, UnaryNode)
    hash(node)
