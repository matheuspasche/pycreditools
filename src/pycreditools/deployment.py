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
        
    def to_production_rules(self) -> dict[str, Any]:
        """Convert the policy to a simplified, production-friendly rules dictionary."""
        import numpy as np
        
        # 1. Clean stages/filters
        etapas = []
        for i, stage in enumerate(self.policy.stages):
            from .stages import FilterStage, CutoffStage, RateStage
            if isinstance(stage, FilterStage):
                # Format Expression conditions nicely
                cond_repr = repr(stage.condition)
                if cond_repr.startswith("col('"):
                    cond_repr = cond_repr.replace("col('", "").replace("')", "")
                etapas.append({
                    "posicao": i + 1,
                    "nome": stage.name,
                    "tipo": "filtro",
                    "expressao": cond_repr
                })
            elif isinstance(stage, CutoffStage):
                etapas.append({
                    "posicao": i + 1,
                    "nome": stage.name,
                    "tipo": "corte_score",
                    "colunas": list(stage.cutoffs.keys()),
                    "operador": ">=" if stage.direction == "gte" else "<=",
                    "valores": stage.cutoffs
                })
            elif isinstance(stage, RateStage):
                etapas.append({
                    "posicao": i + 1,
                    "nome": stage.name,
                    "tipo": "conversao_taxa",
                    "taxa_base": stage.base_rate,
                    "coluna_propensao": stage.variable
                })
                
        # 2. Clean rating ranges from recipe
        ratings = None
        if self.rating_recipe is not None:
            score_col = self.rating_recipe.score_cols[0] if self.rating_recipe.score_cols else None
            if score_col:
                breaks = np.array(self.rating_recipe.quantile_breaks[score_col])
                mapping = self.rating_recipe.cluster_mapping
                
                # Check actual risk mapping sorted default order
                # Default mapping of cluster labels in find_risk_groups assigns 1..K.
                # A to E map (1 -> A, 2 -> B, etc.)
                cluster_to_rating = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}
                score_to_rating = {}
                for s in range(0, 1001):
                    bin_idx = np.digitize([s], bins=breaks[1:-1])[0]
                    cid = mapping.get(str(bin_idx))
                    score_to_rating[s] = cluster_to_rating.get(cid, "E")
                    
                faixas = {}
                for s, r in score_to_rating.items():
                    if r not in faixas:
                        faixas[r] = []
                    faixas[r].append(s)
                
                faixas_list = []
                for r in sorted(faixas.keys()):
                    faixas_list.append({
                        "rating": r,
                        "nota_minima": min(faixas[r]),
                        "nota_maxima": max(faixas[r])
                    })
                ratings = {
                    "score_coluna": score_col,
                    "faixas": faixas_list
                }
                
        return {
            "etapas_funil": etapas,
            "classificacao_ratings": ratings
        }
        
    def save_production_rules(self, path: str) -> None:
        """Save the production-friendly rules to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_production_rules(), f, indent=4, ensure_ascii=False)
        
    def predict(self, df: pd.DataFrame, simple: bool = True, method: str = "analytical") -> pd.DataFrame:
        """Apply the complete decision flow (policy + rating) to new data."""
        sim_res = self.policy.simulate(df, method=method)
        if simple:
            return sim_res.to_decision_dataframe(rating_recipe=self.rating_recipe)
            
        res_df = sim_res.data.copy()
        if self.rating_recipe is not None:
            # Apply ratings to the full DataFrame
            pred_df = self.rating_recipe.predict(res_df)
            rating_labels = {i: chr(64 + i) for i in range(1, 27)}
            res_df["Rating"] = pred_df["risk_rating"].map(rating_labels)
        return res_df
