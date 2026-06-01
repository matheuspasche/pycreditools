from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Any
import warnings

from .policy import CreditPolicy
from ._types import SimulationMethod, Quadrant

@dataclass
class CreditSimResults:
    data: pd.DataFrame
    metadata: dict[str, Any]
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize the results to a dictionary.
        Note that this does not serialize the entire DataFrame (as it can be huge).
        Instead, it returns just a summary or we can require users to save the df separately.
        For agents, we provide metadata and a summary.
        """
        return {
            "metadata": self.metadata,
        }

def run_simulation(
    data: pd.DataFrame,
    policy: CreditPolicy,
    method: SimulationMethod | str = SimulationMethod.STOCHASTIC,
) -> CreditSimResults:
    """Run a multi-stage credit policy simulation.
    
    Args:
        data: Applicant data.
        policy: The credit policy to simulate.
        method: "stochastic" (default) or "analytical".
        
    Returns:
        CreditSimResults containing the simulation data and metadata.
    """
    if isinstance(method, str):
        method = SimulationMethod(method)
        
    df = data.copy()
    
    policy.validate(df)
    
    stage_approval_cols = []
    df["pass_prob_funnel"] = 1.0
    
    if policy.stages:
        for i, stage in enumerate(policy.stages):
            stage_output_col = f"stage_{i}_{stage.name}"
            stage_approval_cols.append(stage_output_col)
            
            # Run the stage
            stage_res = stage.apply(df, method=method.value)
            
            # Cumulative pass probability
            df["pass_prob_funnel"] = df["pass_prob_funnel"] * stage_res
            df[stage_output_col] = df["pass_prob_funnel"]
            
    if method == SimulationMethod.STOCHASTIC:
        if not stage_approval_cols:
            df["new_approval"] = 1
        else:
            # Must have passed all stages
            df["new_approval"] = df[stage_approval_cols].fillna(0).min(axis=1).astype(int)
    else:
        df["new_approval"] = df["pass_prob_funnel"]
        
    del df["pass_prob_funnel"]
    
    df = _classify_scenarios(df, policy, "new_approval")
    df = _assign_simulated_defaults(df, policy, method)
    
    metadata = {
        "policy": policy.to_dict(),
        "method": method.value,
    }
    
    return CreditSimResults(data=df, metadata=metadata)

def _classify_scenarios(df: pd.DataFrame, policy: CreditPolicy, new_approval_col: str) -> pd.DataFrame:
    """Classify applicants into swap_in, swap_out, keep_in, keep_out."""
    old_app = df[policy.current_approval_col].fillna(0).astype(float)
    new_app = df[new_approval_col].fillna(0).astype(float)
    
    old_flag = (old_app > 0).astype(int)
    new_flag = (new_app > 0).astype(int)
    
    conditions = [
        (old_flag == 0) & (new_flag == 1),
        (old_flag == 1) & (new_flag == 0),
        (old_flag == 1) & (new_flag == 1),
        (old_flag == 0) & (new_flag == 0),
    ]
    
    choices = [
        Quadrant.SWAP_IN.value,
        Quadrant.SWAP_OUT.value,
        Quadrant.KEEP_IN.value,
        Quadrant.KEEP_OUT.value,
    ]
    
    # We use numpy where/select or simply map via a Series mapping to avoid dtype promotion issues.
    # Alternatively, ensure the default is a string (e.g. 'unknown').
    df["scenario"] = np.select(conditions, choices, default="unknown")
    return df

def _assign_simulated_defaults(
    df: pd.DataFrame, 
    policy: CreditPolicy, 
    method: SimulationMethod
) -> pd.DataFrame:
    """Assign default outcomes for the final approved population."""
    swap_in_defaults = _simulate_swap_in_defaults(df, policy, method)
    
    if not swap_in_defaults.empty:
        df = df.merge(swap_in_defaults, on=policy.applicant_id_col, how="left")
    else:
        df["swap_in_default"] = np.nan
        
    conditions = [
        df["scenario"] == Quadrant.KEEP_IN.value,
        df["scenario"] == Quadrant.SWAP_IN.value,
    ]
    
    choices = [
        df[policy.actual_default_col],
        df["swap_in_default"],
    ]
    
    df["simulated_default"] = np.select(conditions, choices, default=np.nan)
    del df["swap_in_default"]
    
    return df

def _simulate_swap_in_defaults(
    df: pd.DataFrame, 
    policy: CreditPolicy, 
    method: SimulationMethod
) -> pd.DataFrame:
    """Simulate default outcomes for swap-in applicants."""
    swap_ins = df[df["scenario"] == Quadrant.SWAP_IN.value].copy()
    
    if swap_ins.empty:
        return pd.DataFrame(columns=[policy.applicant_id_col, "swap_in_default"])
        
    if not policy.stress_scenarios:
        # Neutral scenario (1.0x) using historical average
        global_mask = df[policy.current_approval_col] == 1
        global_pd = df.loc[global_mask, policy.actual_default_col].mean()
        if pd.isna(global_pd):
            global_pd = 0.0
            
        final_probs = pd.Series(global_pd, index=swap_ins.index)
    else:
        prob_matrix = pd.DataFrame(index=swap_ins.index)
        
        # Get baseline historical PD for the aggravating stresses
        global_mask = df[policy.current_approval_col] == 1
        global_pd = df.loc[global_mask, policy.actual_default_col].mean()
        if pd.isna(global_pd):
            global_pd = 0.0
            
        # Add a baseline PD column temporarily
        swap_ins["__baseline_pd"] = global_pd
        
        for i, scenario in enumerate(policy.stress_scenarios):
            res = scenario.apply(swap_ins, "__baseline_pd")
            prob_matrix[f"prob_{i}"] = res
            
        final_probs = prob_matrix.max(axis=1)
        
    if method == SimulationMethod.STOCHASTIC:
        random_draws = np.random.random(len(swap_ins))
        outcomes = (random_draws < final_probs).astype(int)
    else:
        outcomes = final_probs
        
    return pd.DataFrame({
        policy.applicant_id_col: swap_ins[policy.applicant_id_col],
        "swap_in_default": outcomes
    })
