from __future__ import annotations
import json
import pandas as pd
from dataclasses import dataclass
from typing import Any

from .policy import CreditPolicy
from .grouping import GroupingRecipe

@dataclass
class DeploymentPolicy:
    """A unified decision policy packaged for deployment/implementation.
    
    It bundles a CreditPolicy (filters, cutoffs, rates) and an optional GroupingRecipe (clustering/ratings).
    """
    policy: CreditPolicy
    rating_recipe: GroupingRecipe | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize the deployment policy to a dictionary."""
        return {
            "policy": self.policy.to_dict(),
            "rating_recipe": self.rating_recipe.to_dict() if self.rating_recipe else None,
        }
        
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeploymentPolicy:
        """Deserialize a dictionary to a DeploymentPolicy."""
        policy = CreditPolicy.from_dict(d["policy"])
        recipe_dict = d.get("rating_recipe")
        recipe = GroupingRecipe.from_dict(recipe_dict) if recipe_dict else None
        return cls(policy=policy, rating_recipe=recipe)
        
    def save(self, path: str) -> None:
        """Save the deployment policy to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=4, ensure_ascii=False)
            
    @classmethod
    def load(cls, path: str) -> DeploymentPolicy:
        """Load a deployment policy from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)
        
    def predict(self, df: pd.DataFrame, simple: bool = True) -> pd.DataFrame:
        """Apply the complete decision flow (policy + rating) to new data."""
        sim_res = self.policy.simulate(df)
        if simple:
            return sim_res.to_decision_dataframe(rating_recipe=self.rating_recipe)
            
        res_df = sim_res.data
        if self.rating_recipe is not None:
            # Apply ratings to the full DataFrame
            pred_df = self.rating_recipe.predict(res_df)
            rating_labels = {i: chr(64 + i) for i in range(1, 27)}
            res_df["Rating"] = pred_df["risk_rating"].map(rating_labels)
        return res_df
