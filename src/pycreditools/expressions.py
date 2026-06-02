from __future__ import annotations
from typing import Any
import pandas as pd

class Expression:
    """Base class for building logical column expressions."""
    
    def eval(self, df: pd.DataFrame) -> pd.Series:
        raise NotImplementedError("Subclasses must implement eval()")

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

    def __repr__(self) -> str:
        return f"col('{self.name}')"


class BinaryExpr(Expression):
    """An expression comparing two values (at least one being an Expression)."""
    
    def __init__(self, left: Any, op: str, right: Any):
        self.left = left
        self.op = op
        self.right = right

    def eval(self, df: pd.DataFrame) -> pd.Series:
        # Evaluate left and right sides
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

    def __repr__(self) -> str:
        return f"{self.op}({self.expr})"


def col(name: str) -> ColumnExpr:
    """Create a Column Expression builder.
    
    Example:
        `col("age") >= 18`
    """
    return ColumnExpr(name)
