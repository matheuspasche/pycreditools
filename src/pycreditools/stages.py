from __future__ import annotations
import warnings
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Any, Callable

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
        self.direction = direction
        
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
    """A generic lottery stage: a pass-rate applied to whoever reaches it.

    Take-up/contratação is the obvious example, but credit-desk approval, formalização
    and antifraude are the same shape — a pass-rate on a subpopulation that may
    correlate with the score under evaluation. Nothing here is take-up-specific.

    Three ways to express the rate, from simplest to most data-driven:

    - ``RateStage(name="Contratação", base_rate=0.7)`` — a pure scalar. No column, no
      data dependency.
    - ``RateStage(name="Contratação", base_rate=0.7, variable=...)`` — ``base_rate``
      times a multiplier (column, `Expression`, callable or constant).
    - ``RateStage(name="Contratação", base_rate=1.0, observed_col="hired")`` — the rate
      is read from real data: Keep Ins take their own outcome out of ``observed_col``
      (0/1, no draw), and Swap Ins get the rate observed in their score bin.

    Keep In bypass: a Keep In only has a real outcome in ``policy.actual_default_col``
    because they actually contracted, so their take-up is 1.0 *by construction of the
    data*. A rate stage with no ``observed_col`` therefore gives Keep Ins ``probs=1.0``
    and only thins the Swap Ins; with an ``observed_col`` their true outcome wins
    instead. Either way ``take_up_rate`` comes out as a mixture, and that mixture is
    the truth (see ADR 0008).
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
            base_rate: The base probability of passing (0.0 to 1.0).
            variable: Optional column name, expression, callable, or numeric multiplier for the base rate.
            calibrate: If True, wraps expression variable in CalibratedExpression.
            observed_col: Optional 0/1 column holding the real outcome of this stage.
                Keep Ins take their value from it verbatim; Swap Ins get an estimate of
                it (see `calibrate_by`), multiplied by `base_rate` (and by `variable`,
                when given) — so `base_rate=1.0` means "use the observed rate as is".
            calibrate_by: How the Swap In estimate is built from `observed_col`.
                `"score"` (default) bins the Keep Ins by score — using the same knobs as
                the PD imputation, `policy.calibration_score_col` and
                `policy.calibration_bins` — and gives each Swap In the observed rate of
                its bin. `None` gives every Swap In the flat observed mean over the
                approved population. When `"score"` cannot run, this falls back to the
                flat mean and warns; it never raises. Ignored without `observed_col`.
        """
        super().__init__(name)
        self.base_rate = base_rate
        self.calibrate = calibrate
        self.observed_col = observed_col
        if calibrate_by not in ("score", None):
            raise ValueError(
                f"calibrate_by must be 'score' or None, got {calibrate_by!r}."
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
            
    def apply(self, df: pd.DataFrame, method: str = "analytical", policy: Any | None = None) -> pd.Series:
        from .expressions import CalibratedExpression, Expression
        
        # 1. Compute probabilities based on self.variable
        if self.variable is not None:
            if isinstance(self.variable, Expression):
                if isinstance(self.variable, CalibratedExpression):
                    probs = (self.base_rate * self.variable.calibrate_and_eval(df, policy)).clip(0.0, 1.0)
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
            
        probs = probs.fillna(0.0)

        # 2. Fold in the observed rate, when this stage reads one from the data
        if self.observed_col is not None:
            if self.observed_col not in df.columns:
                raise ValueError(
                    f"Column '{self.observed_col}' not found in data for rate stage '{self.name}'."
                )
            probs = (probs * self._estimate_observed_rate(df, policy)).clip(0.0, 1.0)

        # 3. Apply Keep In bypass / deterministic behavior if policy is provided
        keep_ins_mask = self._keep_ins_mask(df, policy)
        if keep_ins_mask is not None and keep_ins_mask.any():
            probs = probs.copy()
            probs.loc[keep_ins_mask] = self._keep_in_probs(df, keep_ins_mask)

        if method == "stochastic":
            if keep_ins_mask is not None:
                outcomes = pd.Series(0, index=df.index, dtype=int)

                swap_ins_mask = ~keep_ins_mask
                if swap_ins_mask.any():
                    random_draws = np.random.random(swap_ins_mask.sum())
                    outcomes.loc[swap_ins_mask] = (random_draws < probs.loc[swap_ins_mask]).astype(int)

                if keep_ins_mask.any():
                    # Keep Ins are deterministic: their real outcome, or 1.0 by construction.
                    outcomes.loc[keep_ins_mask] = (
                        self._keep_in_probs(df, keep_ins_mask).round().astype(int)
                    )
                return outcomes
            else:
                random_draws = np.random.random(len(df))
                return (random_draws < probs).astype(int)
        else:
            return probs.astype(float)

    @staticmethod
    def _keep_ins_mask(df: pd.DataFrame, policy: Any | None) -> pd.Series | None:
        """The Keep In mask (approved by the current policy), or None when unknowable."""
        if policy is None or policy.current_approval_col is None:
            return None
        if policy.current_approval_col not in df.columns:
            return None
        return df[policy.current_approval_col] == 1

    def _keep_in_probs(self, df: pd.DataFrame, keep_ins_mask: pd.Series) -> pd.Series:
        """Pass probability of the Keep Ins: their real outcome, or 1.0 by construction."""
        if self.observed_col is not None:
            observed = pd.to_numeric(df.loc[keep_ins_mask, self.observed_col], errors="coerce")
            return observed.fillna(0.0).astype(float)
        return pd.Series(1.0, index=df.index[keep_ins_mask.to_numpy()])

    def _estimate_observed_rate(self, df: pd.DataFrame, policy: Any | None) -> pd.Series:
        """Per-row estimate of `observed_col`, calibrated on the approved population.

        Only the Swap Ins actually consume this — a Keep In's own outcome is known and
        overrides it in `apply`.
        """
        from .expressions import CalibratedExpression, col, resolve_calibration_score_col

        observed = pd.to_numeric(df[self.observed_col], errors="coerce")
        keep_ins_mask = self._keep_ins_mask(df, policy)
        has_keep_ins = keep_ins_mask is not None and bool(keep_ins_mask.any())

        flat_mean = observed.loc[keep_ins_mask].mean() if has_keep_ins else observed.mean()
        if pd.isna(flat_mean):
            flat_mean = 0.0
        flat = pd.Series(float(flat_mean), index=df.index)

        if self.calibrate_by is None:
            return flat

        # calibrate_by == "score": bin the Keep Ins by score, same knobs as the PD imputation.
        reason: str | None = None
        score_col = resolve_calibration_score_col(df, policy)
        if not has_keep_ins:
            reason = "the approval column is not available in the data"
        elif score_col is None:
            reason = "no usable score column was found"
        elif score_col not in df.columns:
            reason = f"the configured calibration score column '{score_col}' is not in the data"
        else:
            # Same floor as the swap-in PD imputation (simulation.py).
            min_keep_ins = 5 if policy.calibration_bins is not None else 50
            n_keep_ins = int(keep_ins_mask.sum())
            if n_keep_ins < min_keep_ins:
                reason = f"only {n_keep_ins} approved rows are available (minimum {min_keep_ins})"

        if reason is not None:
            warnings.warn(
                f"Rate stage '{self.name}': cannot calibrate '{self.observed_col}' by score "
                f"because {reason}. Falling back to the flat observed mean "
                f"({flat_mean:.4f}) over the approved population. Pass calibrate_by=None "
                f"to ask for this explicitly and silence this warning.",
                stacklevel=3,
            )
            return flat

        estimate = CalibratedExpression(col(self.observed_col)).calibrate_and_eval(df, policy)
        return pd.Series(estimate.values, index=df.index).astype(float).fillna(float(flat_mean))

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
