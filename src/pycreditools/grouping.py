from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
import json
from typing import Any

from ._kernels import ward_cluster, iv_cluster

@dataclass
class GroupingRecipe:
    """Serializable recipe for applying grouping to new data."""
    score_cols: list[str]
    quantile_breaks: dict[str, list[float]] = None
    cluster_mapping: dict[str, int] = None
    intervals: list[dict[str, Any]] = None
    segmented_intervals: dict[str, list[dict[str, Any]]] = None
    segment_col: str = None
    
    def to_dict(self) -> dict[str, Any]:
        d = {"score_cols": self.score_cols}
        if self.quantile_breaks is not None:
            d["quantile_breaks"] = self.quantile_breaks
        if self.cluster_mapping is not None:
            d["cluster_mapping"] = self.cluster_mapping
        if self.intervals is not None:
            d["intervals"] = self.intervals
        if self.segmented_intervals is not None:
            d["segmented_intervals"] = self.segmented_intervals
        if self.segment_col is not None:
            d["segment_col"] = self.segment_col
        return d
        
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GroupingRecipe:
        mapping = None
        if "cluster_mapping" in d and d["cluster_mapping"] is not None:
            mapping = {str(k): v for k, v in d["cluster_mapping"].items()}
        return cls(
            score_cols=d["score_cols"],
            quantile_breaks=d.get("quantile_breaks"),
            cluster_mapping=mapping,
            intervals=d.get("intervals"),
            segmented_intervals=d.get("segmented_intervals"),
            segment_col=d.get("segment_col")
        )
        
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
        
    @classmethod
    def from_json(cls, s: str) -> GroupingRecipe:
        return cls.from_dict(json.loads(s))
        
    def predict(self, new_data: pd.DataFrame) -> pd.DataFrame:
        """Apply the grouping recipe to map scores to group numbers."""
        df = new_data.copy()
        df["risk_rating"] = np.nan
        
        if self.intervals is not None:
            score_col = self.score_cols[0]
            rating_to_group = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
            for f in self.intervals:
                rat = f["rating"]
                g_id = rating_to_group.get(rat, 5)
                mask = (df[score_col] >= f["nota_minima"]) & (df[score_col] <= f["nota_maxima"])
                df.loc[mask, "risk_rating"] = g_id
                
        elif self.segmented_intervals is not None:
            score_col = self.score_cols[0]
            segment_col = self.segment_col or "region"
            rating_to_group = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
            for seg, faixas in self.segmented_intervals.items():
                mask_seg = df[segment_col] == seg
                for f in faixas:
                    rat = f["rating"]
                    g_id = rating_to_group.get(rat, 5)
                    mask = mask_seg & (df[score_col] >= f["nota_minima"]) & (df[score_col] <= f["nota_maxima"])
                    df.loc[mask, "risk_rating"] = g_id
                    
        else:
            # 1. Apply quantile breaks
            bin_cols = []
            for col in self.score_cols:
                breaks = self.quantile_breaks[col]
                # Use np.digitize. np.digitize returns indices 1..len(bins)
                # We want 0-based for string mapping
                bin_idx = np.digitize(df[col], bins=breaks[1:-1])
                bin_col = f"{col}_bin"
                df[bin_col] = bin_idx
                bin_cols.append(bin_col)
                
            # 2. Combine to micro-bin keys
            if len(bin_cols) == 1:
                keys = df[bin_cols[0]].astype(str)
            else:
                keys = df[bin_cols].astype(str).agg('-'.join, axis=1)
                
            # 3. Map to groups
            df["risk_rating"] = keys.map(self.cluster_mapping)
            
            # Cleanup
            for bc in bin_cols:
                if bc in df.columns:
                    del df[bc]
                
        return df

@dataclass
class RiskGroupResult:
    data: pd.DataFrame
    groups: pd.DataFrame
    recipe: GroupingRecipe
    n_groups: int
    params: dict[str, Any]
    
    def predict(self, new_data: pd.DataFrame) -> pd.DataFrame:
        return self.recipe.predict(new_data)
        
    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe.to_dict(),
            "n_groups": self.n_groups,
            "params": self.params,
        }

def find_risk_groups(
    data: pd.DataFrame,
    score_cols: str | list[str],
    default_col: str,
    bins: int = 20,
    max_groups: int | None = None,
    min_vol_ratio: float = 0.05,
    max_crossings: int = 1,
    time_col: str | None = None,
    method: str = "ward",
) -> RiskGroupResult:
    """Find optimal risk groups using clustering."""
    if isinstance(score_cols, str):
        score_cols = [score_cols]
        
    if max_groups is None:
        max_groups = 5
        
    if max_groups > bins:
        raise ValueError(f"max_groups ({max_groups}) cannot be greater than bins ({bins}).")
        
    df = data.copy()
    
    # 1. Quantile binning
    breaks_dict = {}
    bin_cols = []
    
    for col in score_cols:
        # np.quantile
        quantiles = np.linspace(0, 1, bins + 1)
        # Drop duplicate breaks (e.g. if lots of 0s)
        q_breaks = np.unique(np.quantile(df[col].dropna(), quantiles))
        
        if len(q_breaks) < 2:
            raise ValueError(f"Column {col} does not have enough variance to bin.")
            
        breaks_dict[col] = q_breaks.tolist()
        
        # Digitize
        # bin index 0 to len(q_breaks)-2
        binned = np.digitize(df[col], q_breaks[1:-1])
        bin_col = f"{col}_bin"
        df[bin_col] = binned
        bin_cols.append(bin_col)
        
    # 2. Compute PD per combo
    if len(bin_cols) == 1:
        df["_combo_key"] = df[bin_cols[0]].astype(str)
    else:
        df["_combo_key"] = df[bin_cols].astype(str).agg('-'.join, axis=1)
        
    # Aggregate
    agg = df.groupby("_combo_key").agg(
        volume=(default_col, "count"),
        bads=(default_col, "sum")
    ).reset_index()
    
    agg["pd"] = agg["bads"] / agg["volume"].replace(0, 1)
    
    # Sort from lowest risk to highest risk
    if len(score_cols) == 1:
        # Since we only have a single score, we want contiguous risk groups in terms of score.
        # We sort by the bin index in descending order (highest score/lowest risk first).
        agg["_bin_int"] = agg["_combo_key"].astype(int)
        agg = agg.sort_values("_bin_int", ascending=False).reset_index(drop=True)
        del agg["_bin_int"]
    else:
        agg = agg.sort_values("pd").reset_index(drop=True)
    
    pd_values = agg["pd"].values
    volumes = agg["volume"].values
    keys = agg["_combo_key"].values
    
    # Time matrices
    monthly_vols = None
    monthly_bads = None
    
    if time_col is not None and time_col in df.columns:
        # Pivot
        pivot_vol = df.pivot_table(index="_combo_key", columns=time_col, values=default_col, aggfunc="count", fill_value=0)
        pivot_bads = df.pivot_table(index="_combo_key", columns=time_col, values=default_col, aggfunc="sum", fill_value=0)
        
        # Reorder to match agg
        pivot_vol = pivot_vol.reindex(keys).fillna(0).values
        pivot_bads = pivot_bads.reindex(keys).fillna(0).values
        
        monthly_vols = pivot_vol.astype(np.float64)
        monthly_bads = pivot_bads.astype(np.float64)
        
    # 3. Cluster
    if method in ("ward", "distance"):
        assignments = ward_cluster(
            pd_values=pd_values,
            volumes=volumes.astype(np.float64),
            max_groups=max_groups,
            min_vol_ratio=min_vol_ratio,
            max_crossings=max_crossings,
            use_volume_weights=(method == "ward"),
            monthly_vols=monthly_vols,
            monthly_bads=monthly_bads
        )
    elif method == "iv":
        assignments = iv_cluster(
            pd_values=pd_values,
            volumes=volumes.astype(np.float64),
            max_groups=max_groups,
            min_vol_ratio=min_vol_ratio,
            monthly_vols=monthly_vols,
            monthly_bads=monthly_bads
        )
    else:
        raise ValueError(f"Unknown clustering method: {method}")
        
    # 4. Map back
    cluster_mapping = dict(zip(keys, assignments.tolist()))
    df["risk_rating"] = df["_combo_key"].map(cluster_mapping)
    
    # 5. Summary
    groups_summary = df.groupby("risk_rating").agg(
        volume=(default_col, "count"),
        pd=(default_col, "mean")
    ).reset_index()
    
    recipe = GroupingRecipe(
        score_cols=score_cols,
        quantile_breaks=breaks_dict,
        cluster_mapping=cluster_mapping
    )
    
    params = {
        "bins": bins,
        "max_groups": max_groups,
        "min_vol_ratio": min_vol_ratio,
        "method": method
    }
    
    # Cleanup
    for bc in bin_cols + ["_combo_key"]:
        if bc in df.columns:
            del df[bc]
            
    return RiskGroupResult(
        data=df,
        groups=groups_summary,
        recipe=recipe,
        n_groups=len(np.unique(assignments)),
        params=params
    )
