from __future__ import annotations
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Any

class Stage(ABC):
    """Base class for credit policy stages."""
    
    def __init__(self, name: str):
        self.name = name
        
    @abstractmethod
    def apply(self, df: pd.DataFrame, method: str = "analytical") -> pd.Series:
        """Apply the stage rule to the DataFrame.
        
        Args:
            df: The applicant data.
            method: "analytical" (returns float probabilities) or "stochastic" (returns 0/1 integers).
            
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
            return FilterStage(name=d["name"], condition=d["condition"])
        elif t == "rate":
            return RateStage(
                name=d["name"], 
                base_rate=d["base_rate"], 
                variable=d.get("variable")
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
        
    def apply(self, df: pd.DataFrame, method: str = "analytical") -> pd.Series:
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

class FilterStage(Stage):
    """A stage that filters based on a string condition evaluated by pandas."""
    
    def __init__(self, name: str, condition: str):
        """
        Args:
            name: Stage name.
            condition: Pandas query string (e.g. 'age >= 18 and status == "A"').
        """
        super().__init__(name)
        self.condition = condition
        
    def apply(self, df: pd.DataFrame, method: str = "analytical") -> pd.Series:
        try:
            # We want to return a boolean series of the same length as df.
            # df.eval returns a Series of booleans if the expression is a boolean condition.
            result = df.eval(self.condition)
            if not isinstance(result, pd.Series):
                result = pd.Series(result, index=df.index)
        except Exception as e:
            raise ValueError(f"Failed to evaluate filter condition '{self.condition}': {e}")
            
        result = result.fillna(False)
        
        if method == "stochastic":
            return result.astype(int)
        else:
            return result.astype(float)
            
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "filter",
            "name": self.name,
            "condition": self.condition,
        }

class RateStage(Stage):
    """A stage that applies a probability of passing."""
    
    def __init__(self, name: str, base_rate: float, variable: str | float | None = None):
        """
        Args:
            name: Stage name.
            base_rate: The base probability of passing (0.0 to 1.0).
            variable: Optional column name or numeric multiplier for the base rate.
        """
        super().__init__(name)
        self.base_rate = base_rate
        self.variable = variable
        
    def apply(self, df: pd.DataFrame, method: str = "analytical") -> pd.Series:
        if self.variable is not None:
            if isinstance(self.variable, str) and self.variable in df.columns:
                probs = (self.base_rate * df[self.variable]).clip(0.0, 1.0)
            else:
                try:
                    mult = float(self.variable)
                    probs = pd.Series(np.clip(self.base_rate * mult, 0.0, 1.0), index=df.index)
                except (ValueError, TypeError):
                    raise ValueError(f"Variable '{self.variable}' must be a column name or a numeric value.")
        else:
            probs = pd.Series(self.base_rate, index=df.index)
            
        probs = probs.fillna(0.0)
            
        if method == "stochastic":
            random_draws = np.random.random(len(df))
            return (random_draws < probs).astype(int)
        else:
            return probs.astype(float)
            
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "rate",
            "name": self.name,
            "base_rate": self.base_rate,
            "variable": self.variable,
        }
