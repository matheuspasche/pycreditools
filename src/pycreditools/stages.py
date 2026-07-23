from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

_CALLABLE_REGISTRY: dict[str, Callable] = {}

def register_callable(name: str, func: Callable) -> None:
    """Register a custom function so it can be resolved during deserialization."""
    _CALLABLE_REGISTRY[name] = func

def _resolve_callable(name: str) -> Callable:
    # Resolve solely via explicit registry
    if name in _CALLABLE_REGISTRY:
        return _CALLABLE_REGISTRY[name]

    # If not found, raise an informative error with registration instructions
    raise ValueError(
        f"Custom function '{name}' has not been registered in the local environment.\n"
        f"Please register the function before loading or running the policy using:\n"
        f"  pycreditools.stages.register_callable('{name}', your_function)"
    )

class Stage(ABC):
    """Base class for credit policy stages."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def apply(self, df: pd.DataFrame, method: str = "analytical", policy: Any | None = None) -> pd.Series:
        """Apply the stage rule to the DataFrame.
        
        Args:
            df: The applicant data.
            method: "analytical" (returns float probabilities) or "stochastic" (returns 0/1 integers).
            policy: Optional CreditPolicy containing metadata.
            
        Returns:
            pd.Series containing the pass status for each row (0.0/1.0 or 0/1).
        """
        pass

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize the stage to a dictionary."""
        pass

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Stage:
        """Deserialize a dictionary to a Stage object."""
        if "type" not in d:
            raise ValueError("Dictionary must contain a 'type' key.")

        t = d["type"]
        if t == "cutoff":
            return CutoffStage(
                name=d["name"],
                cutoffs=d["cutoffs"],
                direction=d.get("direction", "gte")
            )
        elif t == "filter":
            cond = d["condition"]
            if isinstance(cond, dict):
                if cond.get("type") == "callable":
                    cond = _resolve_callable(cond["name"])
                else:
                    from .expressions import deserialize_expression
                    cond = deserialize_expression(cond)
            return FilterStage(name=d["name"], condition=cond)
        elif t == "rate":
            var_data = d.get("variable")
            if isinstance(var_data, dict):
                if var_data.get("type") == "callable":
                    var_data = _resolve_callable(var_data["name"])
                else:
                    from .expressions import deserialize_expression
                    var_data = deserialize_expression(var_data)
            return RateStage(
                name=d["name"],
                base_rate=d["base_rate"],
                variable=var_data,
                calibrate=d.get("calibrate", False),
                observed_col=d.get("observed_col"),
                calibrate_by=d.get("calibrate_by", "score"),
            )
        else:
            raise ValueError(f"Unknown stage type: {t}")

from ._types import StageDirection

VALID_CUTOFF_DIRECTIONS = tuple(d.value for d in StageDirection)


def validate_direction(direction: str, context: str) -> str:
    """Raise on any direction outside gte/lte; return it otherwise.

    No silent fallback: the permissive else-means-lte branch this replaces
    inverted every ">="-spelled cutoff (issue #71, Bug 1). Single source of
    the rule for stages, sweeps and analyzers.
    """
    if direction not in VALID_CUTOFF_DIRECTIONS:
        raise ValueError(
            f"Unknown direction '{direction}' for {context}: use 'gte' (>=) or 'lte' (<=)."
        )
    return direction


class CutoffStage(Stage):
    """A stage that requires specific columns to meet or exceed a cutoff value."""

    def __init__(self, name: str, cutoffs: dict[str, float], direction: str = "gte"):
        """
        Args:
            name: Stage name.
            cutoffs: Dictionary mapping column names to cutoff values.
            direction: "gte" (>=) or "lte" (<=).
        """
        super().__init__(name)
        self.cutoffs = cutoffs
        self.direction = validate_direction(direction, f"cutoff stage '{name}'")

    def apply(self, df: pd.DataFrame, method: str = "analytical", policy: Any | None = None) -> pd.Series:
        # Start with all Trues
        result = pd.Series(True, index=df.index)

        for col, val in self.cutoffs.items():
            if col not in df.columns:
                raise ValueError(f"Column '{col}' not found in data for cutoff stage '{self.name}'.")

            if self.direction == "gte":
                result &= (df[col] >= val)
            else:
                result &= (df[col] <= val)

        # Fill NAs with False
        result = result.fillna(False)

        if method == "stochastic":
            return result.astype(int)
        else:
            return result.astype(float)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "cutoff",
            "name": self.name,
            "cutoffs": self.cutoffs,
            "direction": self.direction,
        }


def resolve_calibration_score_col(policy: Any, df: pd.DataFrame) -> str | None:
    """Resolve which column drives score-bin calibration for ``policy`` over ``df``.

    Precedence: explicit ``calibration_score_col`` → the last ``CutoffStage``
    cutoff column present in ``df`` → the last ``score_cols`` entry present in
    ``df``. Returns ``None`` when nothing resolves.

    Lives here (not in the calibration primitive or in ``expressions``) because
    it is the only piece that needs ``CutoffStage``; keeping it here is what
    closes the ``stages ↔ expressions`` import cycle.
    """
    primary_score = policy.calibration_score_col
    if primary_score is None:
        cutoff_cols = []
        for stage in policy.stages:
            if isinstance(stage, CutoffStage):
                cutoff_cols.extend(stage.cutoffs.keys())
        for sc in reversed(cutoff_cols):
            if sc in df.columns:
                primary_score = sc
                break

    if primary_score is None and policy.score_cols:
        for sc in reversed(policy.score_cols):
            if sc in df.columns:
                primary_score = sc
                break

    return primary_score


def resolve_calibration_direction(policy: Any, primary_score: str | None) -> str:
    """Resolve the **declared** direction of ``primary_score`` for calibration.

    Reads it off the last ``CutoffStage`` that gates ``primary_score``. Direction
    is declared, never inferred from the data (precedent #59, #57): when no cutoff
    declares one — an explicit ``calibration_score_col`` with no matching gate —
    fall back to the package convention ``"gte"`` (higher score is better).
    """
    if primary_score is None:
        return "gte"
    for stage in reversed(policy.stages):
        if isinstance(stage, CutoffStage) and primary_score in stage.cutoffs:
            return stage.direction
    return "gte"


from .expressions import Expression


class FilterStage(Stage):
    """A stage that filters based on an expression, a callable, or a string condition."""

    def __init__(self, name: str, condition: str | callable | Expression):
        """
        Args:
            name: Stage name.
            condition: Can be:
                - A string query evaluated by pandas (e.g. 'age >= 18').
                - A pycreditools.Expression (e.g. col('age') >= 18).
                - A callable that takes a DataFrame and returns a boolean Series.
        """
        super().__init__(name)
        self.condition = condition

    def apply(self, df: pd.DataFrame, method: str = "analytical", policy: Any | None = None) -> pd.Series:
        try:
            if isinstance(self.condition, Expression):
                result = self.condition.eval(df)
            elif callable(self.condition):
                result = self.condition(df)
            else:
                # Fallback to string evaluation
                result = df.eval(self.condition)

            if not isinstance(result, pd.Series):
                result = pd.Series(result, index=df.index)
        except Exception as e:
            cond_repr = repr(self.condition)
            raise ValueError(f"Failed to evaluate filter condition {cond_repr}: {e}")

        result = result.fillna(False)

        if method == "stochastic":
            return result.astype(int)
        else:
            return result.astype(float)

    def to_dict(self) -> dict[str, Any]:
        if isinstance(self.condition, Expression):
            from .expressions import serialize_expression
            cond_data = serialize_expression(self.condition)
        elif callable(self.condition):
            cond_data = {
                "type": "callable",
                "name": getattr(self.condition, "__name__", str(self.condition))
            }
        else:
            cond_data = str(self.condition)

        return {
            "type": "filter",
            "name": self.name,
            "condition": cond_data,
        }

class RateStage(Stage):
    """A generic lottery stage: a pass-rate on a subpopulation.

    Take-up/contratacao is the obvious example, but credit-desk approval,
    formalizacao and antifraude share the shape. Nothing here is
    take-up-specific.

    Three ways to source the rate, in increasing realism:

    - Pure scalar -- ``RateStage(name, base_rate=0.7)``. Every swap-in passes at
      0.7. No data dependency.
    - Multiplier -- ``variable`` (column/expression/callable/number) scales
      ``base_rate`` per row.
    - Observed -- ``observed_col`` reads a real 0/1 outcome (e.g. ``hired``) from
      the keep-in population. Keep-ins take their real value; swap-ins, who have
      no observed outcome, get an estimate. With ``calibrate_by="score"`` the
      estimate is the keep-in observed mean *within the swap-in's score bin*, so
      swap-ins (who live in the worse bins by construction) do not inherit the
      global mean. ``base_rate`` and ``variable`` are ignored when
      ``observed_col`` is set -- the rate comes from the data.
    """

    def __init__(
        self,
        name: str,
        base_rate: float,
        variable: str | float | Expression | callable | None = None,
        calibrate: bool = False,
        observed_col: str | None = None,
        calibrate_by: str | None = "score",
    ):
        """
        Args:
            name: Stage name.
            base_rate: The base probability of passing (0.0 to 1.0). Ignored when
                ``observed_col`` is set.
            variable: Optional column name, expression, callable, or numeric
                multiplier for the base rate. Ignored when ``observed_col`` is set.
            calibrate: If True, wraps expression ``variable`` in
                CalibratedExpression. Independent of ``observed_col``; no longer
                implies any conversion-stage behaviour.
            observed_col: Column holding the real 0/1 outcome for the keep-in
                population. When set, keep-ins take their real value and swap-ins
                get an estimated rate.
            calibrate_by: How to estimate the swap-in rate when ``observed_col``
                is set. ``"score"`` (default) bins keep-ins by score using the
                same knobs as PD imputation (``policy.calibration_score_col``,
                ``policy.calibration_bins``) and gives each swap-in its bin's
                observed mean; ``None`` gives every swap-in the flat observed mean
                over the approved population. Only ``"score"`` and ``None`` are
                valid.
        """
        super().__init__(name)
        self.base_rate = base_rate
        self.calibrate = calibrate
        self.observed_col = observed_col
        if calibrate_by not in (None, "score"):
            raise ValueError(
                f"calibrate_by must be None or 'score', got {calibrate_by!r}."
            )
        self.calibrate_by = calibrate_by

        from .expressions import CalibratedExpression, Expression
        if calibrate and variable is not None:
            if isinstance(variable, Expression) and not isinstance(variable, CalibratedExpression):
                self.variable = CalibratedExpression(variable)
            else:
                self.variable = variable
        else:
            self.variable = variable

    def _variable_probs(self, df: pd.DataFrame, policy: Any | None) -> pd.Series:
        """Swap-in probabilities from ``base_rate`` and ``variable`` (no observed_col)."""
        from .expressions import CalibratedExpression, Expression

        if self.variable is not None:
            if isinstance(self.variable, Expression):
                if isinstance(self.variable, CalibratedExpression):
                    primary_score = (
                        resolve_calibration_score_col(policy, df) if policy is not None else None
                    )
                    probs = (
                        self.base_rate
                        * self.variable.calibrate_and_eval(df, policy, primary_score)
                    ).clip(0.0, 1.0)
                else:
                    probs = (self.base_rate * self.variable.eval(df)).clip(0.0, 1.0)
            elif callable(self.variable):
                probs = (self.base_rate * self.variable(df)).clip(0.0, 1.0)
            elif isinstance(self.variable, str) and self.variable in df.columns:
                probs = (self.base_rate * df[self.variable]).clip(0.0, 1.0)
            else:
                try:
                    mult = float(self.variable)
                    probs = pd.Series(np.clip(self.base_rate * mult, 0.0, 1.0), index=df.index)
                except (ValueError, TypeError):
                    raise ValueError(
                        f"Variable '{self.variable}' must be a column name, expression, callable, or a numeric value."
                    )
        else:
            probs = pd.Series(self.base_rate, index=df.index)

        if not isinstance(probs, pd.Series):
            probs = pd.Series(probs, index=df.index)
        return probs

    def _observed_probs(self, df: pd.DataFrame, policy: Any | None) -> pd.Series:
        """Swap-in probabilities estimated from ``observed_col`` on the keep-ins.

        Keep-in rows also receive a value here (their calibrated bin rate), but
        the caller overrides them with the real observed outcome.
        """
        from .expressions import CalibratedExpression, ColumnExpr

        if self.observed_col not in df.columns:
            raise ValueError(
                f"Column '{self.observed_col}' not found in data for observed rate stage '{self.name}'."
            )

        approval_col = policy.current_approval_col if policy is not None else None
        if approval_col is None or approval_col not in df.columns:
            # No keep-in population to learn from; use the raw column as-is.
            return df[self.observed_col].astype(float)

        keep_ins_mask = df[approval_col] == 1
        if keep_ins_mask.any():
            flat_mean = df.loc[keep_ins_mask, self.observed_col].mean()
            if pd.isna(flat_mean):
                flat_mean = 0.0
        else:
            flat_mean = 0.0

        if self.calibrate_by is None:
            return pd.Series(flat_mean, index=df.index)

        # calibrate_by == "score": reuse the CalibratedExpression machinery, but
        # guard the two cases where score-bin calibration cannot run, falling
        # back to the flat observed mean over the approved population.
        # (policy is guaranteed non-None here: an absent approval col — which
        # includes policy is None — returned above.)
        primary_score = resolve_calibration_score_col(policy, df)
        # Mirrors the swap-in PD imputation floor in simulation.py; both move
        # into the calibration kernel in #72.
        min_keep_ins = 5 if policy.calibration_bins is not None else 50
        if primary_score is None or primary_score not in df.columns:
            warnings.warn(
                f"RateStage '{self.name}': no usable score column for "
                f"calibrate_by='score'; falling back to the flat observed mean of "
                f"'{self.observed_col}' over the approved population.",
                stacklevel=2,
            )
            return pd.Series(flat_mean, index=df.index)
        if keep_ins_mask.sum() < min_keep_ins:
            warnings.warn(
                f"RateStage '{self.name}': only {int(keep_ins_mask.sum())} keep-ins "
                f"(< {min_keep_ins}) for calibrate_by='score'; falling back to the "
                f"flat observed mean of '{self.observed_col}' over the approved "
                f"population.",
                stacklevel=2,
            )
            return pd.Series(flat_mean, index=df.index)

        calibrated = CalibratedExpression(ColumnExpr(self.observed_col))
        return calibrated.calibrate_and_eval(df, policy, primary_score)

    def apply(self, df: pd.DataFrame, method: str = "analytical", policy: Any | None = None) -> pd.Series:
        # 1. Swap-in probabilities: observed_col wins over base_rate/variable.
        if self.observed_col is not None:
            probs = self._observed_probs(df, policy)
        else:
            probs = self._variable_probs(df, policy)

        # Both helpers already return a Series; just normalise NaNs.
        probs = probs.fillna(0.0)

        # 2. Keep-in bypass. With observed_col, keep-ins take their real 0/1
        #    outcome (their take-up is known by construction of the data).
        #    Without it, a keep-in's take-up is 1.0 by construction: the row only
        #    exists because they actually contracted.
        keep_ins_mask = None
        if policy is not None and policy.current_approval_col in df.columns:
            keep_ins_mask = df[policy.current_approval_col] == 1
            if keep_ins_mask.any():
                probs = probs.copy()
                if self.observed_col is not None:
                    probs.loc[keep_ins_mask] = df.loc[keep_ins_mask, self.observed_col].fillna(0.0)
                else:
                    probs.loc[keep_ins_mask] = 1.0

        if method == "stochastic":
            if keep_ins_mask is not None:
                outcomes = pd.Series(0, index=df.index, dtype=int)
                swap_ins_mask = ~keep_ins_mask
                if swap_ins_mask.any():
                    random_draws = np.random.random(swap_ins_mask.sum())
                    outcomes.loc[swap_ins_mask] = (random_draws < probs.loc[swap_ins_mask]).astype(int)
                if keep_ins_mask.any():
                    if self.observed_col is not None:
                        outcomes.loc[keep_ins_mask] = (
                            df.loc[keep_ins_mask, self.observed_col].fillna(0.0).astype(int)
                        )
                    else:
                        outcomes.loc[keep_ins_mask] = 1
                return outcomes
            else:
                random_draws = np.random.random(len(df))
                return (random_draws < probs).astype(int)
        else:
            return probs.astype(float)

    def to_dict(self) -> dict[str, Any]:
        from .expressions import Expression, serialize_expression
        var_data = self.variable
        if isinstance(self.variable, Expression):
            var_data = serialize_expression(self.variable)
        elif callable(self.variable):
            var_data = {
                "type": "callable",
                "name": getattr(self.variable, "__name__", str(self.variable))
            }
        return {
            "type": "rate",
            "name": self.name,
            "base_rate": self.base_rate,
            "variable": var_data,
            "calibrate": self.calibrate,
            "observed_col": self.observed_col,
            "calibrate_by": self.calibrate_by,
        }
