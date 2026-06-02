from __future__ import annotations
from typing import Any
import pandas as pd

class Expression:
    """Base class for building logical column expressions."""
    
    def eval(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError("Subclasses must implement eval()")

    def get_columns(self) -> list[str]:
        raise NotImplementedError("Subclasses must implement get_columns()")

    def __gt__(self, other: Any) -> Expression:
        return BinaryExpr(self, ">", other)

    def __ge__(self, other: Any) -> Expression:
        return BinaryExpr(self, ">=", other)

    def __lt__(self, other: Any) -> Expression:
        return BinaryExpr(self, "<", other)

    def __le__(self, other: Any) -> Expression:
        return BinaryExpr(self, "<=", other)

    def __eq__(self, other: Any) -> Expression: # type: ignore
        return BinaryExpr(self, "==", other)

    def __ne__(self, other: Any) -> Expression: # type: ignore
        return BinaryExpr(self, "!=", other)

    def __and__(self, other: Expression) -> Expression:
        return BinaryExpr(self, "&", other)

    def __or__(self, other: Expression) -> Expression:
        return BinaryExpr(self, "|", other)

    def __invert__(self) -> Expression:
        return UnaryExpr(self, "~")


class ColumnExpr(Expression):
    """An expression representing a DataFrame column."""
    
    def __init__(self, name: str):
        self.name = name

    def eval(self, df: pd.DataFrame) -> pd.Series:
        if self.name not in df.columns:
            raise KeyError(f"Column '{self.name}' not found in DataFrame.")
        return df[self.name]

    def get_columns(self) -> list[str]:
        return [self.name]

    def __repr__(self) -> str:
        return f"col('{self.name}')"


class BinaryExpr(Expression):
    """An expression comparing two values (at least one being an Expression)."""
    
    def __init__(self, left: Any, op: str, right: Any):
        self.left = left
        self.op = op
        self.right = right

    def eval(self, df: pd.DataFrame) -> pd.Series:
        left_val = self.left.eval(df) if isinstance(self.left, Expression) else self.left
        right_val = self.right.eval(df) if isinstance(self.right, Expression) else self.right

        if self.op == ">":
            return left_val > right_val
        elif self.op == ">=":
            return left_val >= right_val
        elif self.op == "<":
            return left_val < right_val
        elif self.op == "<=":
            return left_val <= right_val
        elif self.op == "==":
            return left_val == right_val
        elif self.op == "!=":
            return left_val != right_val
        elif self.op == "&":
            return left_val & right_val
        elif self.op == "|":
            return left_val | right_val
        else:
            raise ValueError(f"Unsupported operator: {self.op}")

    def get_columns(self) -> list[str]:
        cols = []
        if isinstance(self.left, Expression):
            cols.extend(self.left.get_columns())
        if isinstance(self.right, Expression):
            cols.extend(self.right.get_columns())
        return cols

    def __repr__(self) -> str:
        return f"({self.left} {self.op} {self.right})"


class UnaryExpr(Expression):
    """An expression with a unary operator (like NOT)."""
    
    def __init__(self, expr: Expression, op: str):
        self.expr = expr
        self.op = op

    def eval(self, df: pd.DataFrame) -> pd.Series:
        val = self.expr.eval(df)
        if self.op == "~":
            return ~val
        raise ValueError(f"Unsupported unary operator: {self.op}")

    def get_columns(self) -> list[str]:
        return self.expr.get_columns()

    def __repr__(self) -> str:
        return f"{self.op}({self.expr})"


def col(name: str) -> ColumnExpr:
    """Create a Column Expression builder.
    
    Example:
        `col("age") >= 18`
    """
    return ColumnExpr(name)


def serialize_expression(expr: Expression) -> dict[str, Any]:
    """Serialize an Expression object to a dict."""
    if isinstance(expr, ColumnExpr):
        return {"type": "column", "name": expr.name}
    elif isinstance(expr, BinaryExpr):
        left = serialize_expression(expr.left) if isinstance(expr.left, Expression) else expr.left
        right = serialize_expression(expr.right) if isinstance(expr.right, Expression) else expr.right
        return {"type": "binary", "left": left, "op": expr.op, "right": right}
    elif isinstance(expr, UnaryExpr):
        return {"type": "unary", "op": expr.op, "expr": serialize_expression(expr.expr)}
    else:
        raise ValueError(f"Unknown expression type: {type(expr)}")


def deserialize_expression(d: dict[str, Any]) -> Expression:
    """Deserialize a dict to an Expression object."""
    if not isinstance(d, dict) or "type" not in d:
        raise ValueError("Invalid serialized expression representation.")
        
    t = d["type"]
    if t == "column":
        return ColumnExpr(d["name"])
    elif t == "binary":
        left = deserialize_expression(d["left"]) if (isinstance(d["left"], dict) and "type" in d["left"]) else d["left"]
        right = deserialize_expression(d["right"]) if (isinstance(d["right"], dict) and "type" in d["right"]) else d["right"]
        return BinaryExpr(left, d["op"], right)
    elif t == "unary":
        return UnaryExpr(deserialize_expression(d["expr"]), d["op"])
    else:
        raise ValueError(f"Unknown serialized expression type: {t}")
