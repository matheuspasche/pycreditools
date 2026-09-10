"""The frozen AST. The condition is the tree, not a string (§4.3).

`pycreditools.expressions` is the builder the user writes with — `col("age") >= 18` — and it
is shared with the old surface **read-only**: nothing here writes to it. Its nodes are plain
mutable classes whose `==` builds a node instead of comparing, so they can be neither frozen
nor compared by value. A declaration therefore holds its own tree: the builder's output is
converted at the constructor, node by node, into the frozen dataclasses below.

Three node types — column, binary, unary — and nothing else. `.calibrated()` dies in v0.6 and
is refused on the way in; that is what makes the AST pure. Every node references at least one
column: a binary node with a literal on both sides is refused, so a rule that references zero
columns is unexpressible, not an error found later.

Two renders of the same node, and the rule that keeps them from diverging:

- `repr(node)` is Python and round-trips: `eval(repr(node), {"col": col})` gives back a
  builder expression that the constructor turns into an equal node.
- `node.pretty()` is presentation, for the funnel. It is never parsed back.

The string leaves at the output and never enters. `df.eval` is opaque — there is no node in it
to swap — so `ranges=` (tickets 8 and 10) finds the literal of a comparison by walking this
tree and swaps it with the same `replace` every other derivation uses.
"""

from __future__ import annotations

import math
from typing import Any

from ..expressions import BinaryExpr, CalibratedExpression, ColumnExpr, Expression, UnaryExpr
from ._value import set_field, value_type

# Comparison operator -> the one it becomes when its two sides swap.
_MIRROR = {">": "<", ">=": "<=", "<": ">", "<=": ">=", "==": "==", "!=": "!="}
_LOGICAL = frozenset({"&", "|"})
_ARITHMETIC = frozenset({"+", "-", "*", "/"})
_BINARY_OPS = frozenset(_MIRROR) | _LOGICAL | _ARITHMETIC
_UNARY_OPS = frozenset({"~"})


class Node:
    """A node of the frozen AST."""

    __slots__ = ()

    def columns(self) -> tuple[str, ...]:
        """The columns this node references, in order of first appearance."""
        raise NotImplementedError

    def pretty(self) -> str:
        """Presentation render, for the funnel. Never parsed back."""
        raise NotImplementedError


def is_literal(value: Any) -> bool:
    """The literals a node can hold: int, finite float, bool, str."""
    if type(value) is float:
        return math.isfinite(value)
    return type(value) in (bool, int, str)


def require_node(value: Any, what: str) -> Node:
    if isinstance(value, Node):
        return value
    raise TypeError(f"{what} takes an expression such as col('x'), got {value!r}")


@value_type
class ColumnNode(Node):
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise TypeError(f"a column name is a non-empty string, got {self.name!r}")

    def columns(self) -> tuple[str, ...]:
        return (self.name,)

    def pretty(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"col({self.name!r})"


@value_type
class BinaryNode(Node):
    left: Any
    op: str
    right: Any

    def __post_init__(self) -> None:
        if self.op not in _BINARY_OPS:
            raise ValueError(f"unsupported operator {self.op!r}")
        for side in (self.left, self.right):
            if not isinstance(side, Node) and not is_literal(side):
                raise TypeError(
                    f"{side!r} is not a literal the AST can hold; literals are int, "
                    "finite float, bool and str"
                )
        if isinstance(self.left, Node):
            return
        if not isinstance(self.right, Node):
            raise TypeError(
                f"{self.left!r} {self.op} {self.right!r} references no column; "
                "a rule is an expression over the data"
            )
        # One canonical form, node on the left. The builder already produces it — Python
        # reflects `700 < col("x")` into `col("x") > 700` — so this only matters for a tree
        # read back from a dict, and it keeps `repr` an exact round-trip: a literal-left
        # comparison would re-evaluate to its mirror, and `True & col("x")` not at all.
        if self.op in _MIRROR:
            left, op, right = self.right, _MIRROR[self.op], self.left
        elif self.op in _LOGICAL:
            left, op, right = self.right, self.op, self.left
        else:
            return  # reflected arithmetic (`2 * col("x")`) round-trips as written
        set_field(self, "left", left)
        set_field(self, "op", op)
        set_field(self, "right", right)

    def columns(self) -> tuple[str, ...]:
        return _unique(_columns(self.left) + _columns(self.right))

    def pretty(self) -> str:
        return f"{_pretty_operand(self.left)} {self.op} {_pretty_operand(self.right)}"

    def __repr__(self) -> str:
        return f"{_repr_operand(self.left)} {self.op} {_repr_operand(self.right)}"


@value_type
class UnaryNode(Node):
    operand: Node
    op: str

    def __post_init__(self) -> None:
        if self.op not in _UNARY_OPS:
            raise ValueError(f"unsupported unary operator {self.op!r}")
        require_node(self.operand, f"unary {self.op!r}")

    def columns(self) -> tuple[str, ...]:
        return self.operand.columns()

    def pretty(self) -> str:
        return f"{self.op}{_pretty_operand(self.operand)}"

    def __repr__(self) -> str:
        return f"{self.op}{_repr_operand(self.operand)}"


def from_builder(expr: Expression) -> Node:
    """The frozen node for a builder expression."""
    if isinstance(expr, CalibratedExpression):
        raise TypeError(
            ".calibrated() dies in v0.6: it needed the policy to evaluate, which is where "
            "`policy: Any` and the import cycle came from. The AST is pure — column, binary, "
            "unary. The population a rate is estimated on is declared on the Premise "
            "(calibrate_on=)."
        )
    if isinstance(expr, ColumnExpr):
        return ColumnNode(expr.name)
    if isinstance(expr, BinaryExpr):
        return BinaryNode(expr.left, expr.op, expr.right)
    if isinstance(expr, UnaryExpr):
        return UnaryNode(expr.expr, expr.op)
    raise TypeError(f"{type(expr).__name__} is not a node the v0.6 AST knows")


def _columns(operand: Any) -> tuple[str, ...]:
    return operand.columns() if isinstance(operand, Node) else ()


def _unique(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(names))


def _repr_operand(operand: Any) -> str:
    # Every binary child is parenthesized: `&` binds tighter than `>=` in Python, so a
    # minimal-parentheses render would re-parse into a different tree.
    return f"({operand!r})" if isinstance(operand, BinaryNode) else repr(operand)


def _pretty_operand(operand: Any) -> str:
    if isinstance(operand, BinaryNode):
        return f"({operand.pretty()})"
    if isinstance(operand, Node):
        return operand.pretty()
    return repr(operand) if isinstance(operand, str) else str(operand)
