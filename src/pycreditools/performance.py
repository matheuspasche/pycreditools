import pandas as pd
from typing import Any

from .simulation import CreditSimResults
from ._types import Quadrant, PolicySummary

def summarize_results(results: CreditSimResults, by: str | list[str] | None = None) -> pd.DataFrame:
    """Summarize simulation results.
    
    Args:
        results: A CreditSimResults object from run_simulation.
        by: Columns to group by in addition to 'scenario'.
        
    Returns:
        DataFrame with summary statistics.
    """
    data = results.data
    policy_dict = results.metadata["policy"]
    actual_default_col = policy_dict["actual_default_col"]
    
    is_analytical = results.metadata.get("method") == "analytical"
    
    group_cols = []
    if by is not None:
        if isinstance(by, str):
            group_cols.append(by)
        else:
            group_cols.extend(by)
            
    group_cols.append("scenario")
    
    # Pre-calculate base metrics
    if not is_analytical:
        data["_bad_rate_proxy"] = data["simulated_default"]
        
        # Override swap_out / keep_out with historical default
        mask_out = data["scenario"].isin([Quadrant.SWAP_OUT.value, Quadrant.KEEP_OUT.value])
        data.loc[mask_out, "_bad_rate_proxy"] = data.loc[mask_out, actual_default_col]
        
        summary = data.groupby(group_cols, dropna=False).agg(
            Applicants=("scenario", "count"),
            Approved=("new_approval", lambda x: x.sum(skipna=True)),
            Hired=("new_approval", lambda x: x.sum(skipna=True)),
            Bad_Rate=("_bad_rate_proxy", lambda x: x.mean(skipna=True))
        ).reset_index()
        
    else:
        # Analytical
        data["_weighted_default"] = data["simulated_default"] * data["new_approval"]
        
        mask_out = data["scenario"].isin([Quadrant.SWAP_OUT.value, Quadrant.KEEP_OUT.value])
        # In analytical, swap_out and keep_out shouldn't technically have simulated defaults,
        # but to match R logic for bad_rate proxy:
        
        def calc_analytical_bad_rate(df):
            if df["scenario"].iloc[0] in [Quadrant.SWAP_OUT.value, Quadrant.KEEP_OUT.value]:
                return df[actual_default_col].mean(skipna=True)
            else:
                total_app = df["new_approval"].sum(skipna=True)
                if total_app <= 0:
                    return 0.0
                return df["_weighted_default"].sum(skipna=True) / total_app
                
        # We need a custom apply here to handle the conditional logic per group
        metrics = []
        for name, group in data.groupby(group_cols, dropna=False):
            if not isinstance(name, tuple):
                name = (name,)
                
            row = dict(zip(group_cols, name))
            row["Applicants"] = len(group)
            row["Approved"] = group["new_approval"].sum(skipna=True)
            row["Hired"] = group["new_approval"].sum(skipna=True)
            row["Bad_Rate"] = calc_analytical_bad_rate(group)
            metrics.append(row)
            
        summary = pd.DataFrame(metrics)
        
    summary["Bad_Rate"] = summary["Bad_Rate"].fillna(0.0)
    
    # Cleanup temps
    if "_bad_rate_proxy" in data.columns:
        del data["_bad_rate_proxy"]
    if "_weighted_default" in data.columns:
        del data["_weighted_default"]
        
    return summary

def compare_policies(sim_new: CreditSimResults, sim_old: CreditSimResults) -> dict[str, Any]:
    """Compare two simulated policies.
    
    Args:
        sim_new: Results of the new policy simulation.
        sim_old: Results of the old (or baseline) policy simulation.
        
    Returns:
        Dict containing global metrics, swap summaries, and the swap-in to keep-in ratio.
    """
    data_new = sim_new.data
    data_old = sim_old.data
    
    is_analytical = sim_new.metadata.get("method") == "analytical"
    
    def get_global_metrics(data):
        if not is_analytical:
            app_sum = data["new_approval"].sum(skipna=True)
            bad_rate = data.loc[data["new_approval"] == 1, "simulated_default"].mean(skipna=True)
        else:
            app_sum = data["new_approval"].sum(skipna=True)
            if app_sum > 0:
                bad_rate = (data["simulated_default"] * data["new_approval"]).sum(skipna=True) / app_sum
            else:
                bad_rate = 0.0
        return app_sum, bad_rate if pd.notna(bad_rate) else 0.0
        
    app_new, bad_new = get_global_metrics(data_new)
    app_old, bad_old = get_global_metrics(data_old)
    
    n_total = len(data_new)
    
    metrics = pd.DataFrame({
        "Metric": ["Approval Rate", "Bad Rate"],
        "Old": [app_old / n_total, bad_old],
        "New": [app_new / n_total, bad_new],
        "Delta_Abs": [(app_new - app_old) / n_total, bad_new - bad_old],
        "Delta_Rel": [(app_new / max(app_old, 1e-6)) - 1, (bad_new / max(bad_old, 1e-6)) - 1]
    })
    
    swaps = summarize_results(sim_new)
    
    # Swap-in to Keep-in ratio
    si_vol = swaps.loc[swaps["scenario"] == Quadrant.SWAP_IN.value, "Approved"].sum()
    ki_vol = swaps.loc[swaps["scenario"] == Quadrant.KEEP_IN.value, "Approved"].sum()
    
    ratio = si_vol / ki_vol if ki_vol > 0 else np.nan
    
    return {
        "metrics": metrics,
        "swaps": swaps,
        "ratio": ratio
    }
