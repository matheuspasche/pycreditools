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
        return self.to_production_rules()
        
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeploymentPolicy:
        """Deserialize a dictionary to a DeploymentPolicy."""
        # Check if loading old representation for backward compatibility
        if "policy" in d:
            policy = CreditPolicy.from_dict(d["policy"])
            recipe_dict = d.get("rating_recipe")
            recipe = None
            if recipe_dict:
                if isinstance(recipe_dict, dict) and recipe_dict.get("type") == "segmented_recipes":
                    recipe = {k: GroupingRecipe.from_dict(v) for k, v in recipe_dict["recipes"].items()}
                else:
                    recipe = GroupingRecipe.from_dict(recipe_dict)
            return cls(policy=policy, rating_recipe=recipe)

        # Parse new representation
        metadata = d.get("metadata", {})
        applicant_id_col = metadata.get("applicant_id_col", "applicant_id")
        score_cols = metadata.get("score_cols", [])
        if isinstance(score_cols, list):
            score_cols = tuple(score_cols)
        current_approval_col = metadata.get("current_approval_col", "approved")
        actual_default_col = metadata.get("actual_default_col", "defaulted")
        conversion_rate_col = metadata.get("conversion_rate_col")
        pd_col = metadata.get("pd_col")
        time_col = metadata.get("time_col")
        
        from .stages import FilterStage, CutoffStage, RateStage
        stages = []
        for s in d.get("etapas_funil", []):
            t = s.get("tipo")
            if t == "filtro":
                expr = s["expressao"]
                if isinstance(expr, str) and expr.startswith("callable:"):
                    from .stages import _resolve_callable
                    func_name = expr.split("callable:", 1)[1]
                    stages.append(FilterStage(name=s["nome"], condition=_resolve_callable(func_name)))
                else:
                    stages.append(FilterStage(name=s["nome"], condition=expr))
            elif t == "corte_score":
                stages.append(
                    CutoffStage(
                        name=s["nome"],
                        cutoffs=s["valores"],
                        direction="gte" if s.get("operador") == ">=" else "lte"
                    )
                )
            elif t == "conversao_taxa":
                stages.append(
                    RateStage(
                        name=s["nome"],
                        base_rate=s["taxa_base"],
                        variable=s.get("coluna_propensao")
                    )
                )
                
        policy = CreditPolicy(
            applicant_id_col=applicant_id_col,
            score_cols=score_cols,
            current_approval_col=current_approval_col,
            actual_default_col=actual_default_col,
            conversion_rate_col=conversion_rate_col,
            pd_col=pd_col,
            time_col=time_col,
            stages=tuple(stages)
        )
        
        ratings_dict = d.get("classificacao_ratings")
        recipe = None
        if ratings_dict:
            score_coluna = ratings_dict.get("score_coluna")
            if "segmentos" in ratings_dict:
                recipe = {}
                coluna_segmentacao = ratings_dict.get("coluna_segmentacao", "region")
                for seg, faixas in ratings_dict["segmentos"].items():
                    recipe[seg] = GroupingRecipe(
                        score_cols=[score_coluna],
                        intervals=faixas,
                        segment_col=coluna_segmentacao
                    )
            elif "faixas" in ratings_dict:
                recipe = GroupingRecipe(
                    score_cols=[score_coluna],
                    intervals=ratings_dict["faixas"]
                )
                
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
        
        # 1. Metadata
        metadata = {
            "applicant_id_col": self.policy.applicant_id_col,
            "score_cols": list(self.policy.score_cols),
            "current_approval_col": self.policy.current_approval_col,
            "actual_default_col": self.policy.actual_default_col,
            "conversion_rate_col": self.policy.conversion_rate_col,
            "pd_col": self.policy.pd_col,
            "time_col": self.policy.time_col,
        }
        
        # 2. Clean stages/filters
        etapas = []
        for i, stage in enumerate(self.policy.stages):
            from .stages import FilterStage, CutoffStage, RateStage
            if isinstance(stage, FilterStage):
                if callable(stage.condition):
                    cond_repr = f"callable:{getattr(stage.condition, '__name__', str(stage.condition))}"
                elif isinstance(stage.condition, str):
                    cond_repr = stage.condition
                else:
                    cond_repr = repr(stage.condition)
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
                
        # 3. Clean rating ranges from recipe
        ratings = None
        if self.rating_recipe is not None:
            if isinstance(self.rating_recipe, dict):
                segmentos_dict = {}
                score_col = None
                segment_col = "region"
                for r in self.rating_recipe.values():
                    if r.segment_col:
                        segment_col = r.segment_col
                        break
                        
                for seg, recipe in self.rating_recipe.items():
                    if not score_col and recipe.score_cols:
                        score_col = recipe.score_cols[0]
                    
                    if recipe.intervals is not None:
                        segmentos_dict[seg] = recipe.intervals
                    else:
                        breaks = np.array(recipe.quantile_breaks[score_col])
                        mapping = recipe.cluster_mapping
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
                        segmentos_dict[seg] = faixas_list
                    
                ratings = {
                    "score_coluna": score_col,
                    "coluna_segmentacao": segment_col,
                    "segmentos": segmentos_dict
                }
            else:
                score_col = self.rating_recipe.score_cols[0] if self.rating_recipe.score_cols else None
                if score_col:
                    if self.rating_recipe.intervals is not None:
                        faixas_list = self.rating_recipe.intervals
                    else:
                        breaks = np.array(self.rating_recipe.quantile_breaks[score_col])
                        mapping = self.rating_recipe.cluster_mapping
                        
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
            "metadata": metadata,
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
            if isinstance(self.rating_recipe, dict):
                segment_col = "region"
                for c in ["region", "loja", "safra"]:
                    if c in res_df.columns:
                        segment_col = c
                        break
                res_df["Rating"] = None
                for seg, recipe in self.rating_recipe.items():
                    mask = res_df[segment_col] == seg
                    if mask.any():
                        pred_seg = recipe.predict(res_df[mask])
                        rating_labels = {i: chr(64 + i) for i in range(1, 27)}
                        res_df.loc[mask, "Rating"] = pred_seg["risk_rating"].map(rating_labels)
            else:
                pred_df = self.rating_recipe.predict(res_df)
                rating_labels = {i: chr(64 + i) for i in range(1, 27)}
                res_df["Rating"] = pred_df["risk_rating"].map(rating_labels)
        return res_df
