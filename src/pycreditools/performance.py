import pandas as pd
import numpy as np
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
        
    Notes on bad rate interpretation:
        - keep_in / swap_in: simulated_default (swap_in is score-calibrated).
        - swap_out: actual_default (client was previously approved — data is observed).
        - keep_out: NaN — this population was rejected by both policies;
                    no observed credit performance exists.
    """
    data = results.data.copy()
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
    
    # ── Determine whether the simulation tracked pre-rate approvals ────────
    has_pre_rate = "approved_pre_rate" in data.columns
    
    # ── Bad rate proxy per quadrant ────────────────────────────────────
    # keep_in / swap_in  → simulated_default (swap_in is score-calibrated)
    # swap_out           → actual_default  (observed — was in old portfolio)
    # keep_out           → NaN            (rejected by both; no observed data)
    data["_bad_rate_proxy"] = data["simulated_default"]
    
    swap_out_mask = data["scenario"] == Quadrant.SWAP_OUT.value
    keep_out_mask = data["scenario"] == Quadrant.KEEP_OUT.value
    
    data.loc[swap_out_mask, "_bad_rate_proxy"] = data.loc[swap_out_mask, actual_default_col]
    data.loc[keep_out_mask, "_bad_rate_proxy"] = np.nan   # no observable data
    
    if not is_analytical:
        # ── Stochastic path ─────────────────────────────────────────────
        # Use applicant_id_col for counting to avoid grouping column conflicts
        summary = data.groupby(group_cols, dropna=False).agg(
            Applicants=(policy_dict["applicant_id_col"], "count"),
            # Approved: clients who passed all filter/cutoff stages (pre-take-up)
            Approved=("approved_pre_rate",   lambda x: x.sum(skipna=True))
                      if has_pre_rate else
                      ("new_approval",       lambda x: x.sum(skipna=True)),
            # Hired: clients who actually contracted (includes take-up probability)
            Hired=("new_approval",           lambda x: x.sum(skipna=True)),
            Bad_Rate=("_bad_rate_proxy",      lambda x: x.mean(skipna=True)),
        ).reset_index()
        
    else:
        # ── Analytical path ────────────────────────────────────────────
        data["_weighted_default"] = data["simulated_default"] * data["new_approval"]
        
        def _bad_rate(grp, scen):
            if scen == Quadrant.KEEP_OUT.value:
                return np.nan
            if scen == Quadrant.SWAP_OUT.value:
                return grp[actual_default_col].mean(skipna=True)
            # keep_in / swap_in: weighted simulated default
            total_app = grp["new_approval"].sum(skipna=True)
            if total_app <= 0:
                return 0.0
            return grp["_weighted_default"].sum(skipna=True) / total_app
                
        metrics = []
        for name, group in data.groupby(group_cols, dropna=False):
            if not isinstance(name, tuple):
                name = (name,)
                
            row = dict(zip(group_cols, name))
            row["Applicants"] = len(group)
            row["Approved"]   = (group["approved_pre_rate"].sum(skipna=True)
                                  if has_pre_rate else
                                  group["new_approval"].sum(skipna=True))
            row["Hired"]      = group["new_approval"].sum(skipna=True)
            row["Bad_Rate"]   = _bad_rate(group, row["scenario"])
            metrics.append(row)
            
        summary = pd.DataFrame(metrics)
    
    # ── Mark keep_out as explicitly unknown ────────────────────────────
    # (do NOT fill NaN for keep_out — leave it as NaN to signal "unobservable")
    mask_not_ko = summary["scenario"] != Quadrant.KEEP_OUT.value
    summary.loc[mask_not_ko, "Bad_Rate"] = summary.loc[mask_not_ko, "Bad_Rate"].fillna(0.0)
    
    # Cleanup
    for tmp in ("_bad_rate_proxy", "_weighted_default"):
        if tmp in data.columns:
            del data[tmp]
        
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

class ModelEvaluator:
    """Evaluates predictive power of credit score models."""
    
    def __init__(self, data: pd.DataFrame, score_cols: list[str], target_col: str):
        self.data = data
        self.score_cols = score_cols
        self.target_col = target_col
        
    def compute_ks(self) -> dict[str, float]:
        """Compute Kolmogorov-Smirnov (KS) statistic for each score.
        Assumes higher score = lower probability of default.
        """
        import numpy as np
        ks_dict = {}
        for col in self.score_cols:
            df = self.data[[col, self.target_col]].dropna().copy()
            # Sort by score descending
            df = df.sort_values(col, ascending=False)
            bads = df[self.target_col].values
            goods = 1 - bads
            
            total_bads = bads.sum()
            total_goods = goods.sum()
            
            if total_bads == 0 or total_goods == 0:
                ks_dict[col] = 0.0
                continue
                
            cum_bads = np.cumsum(bads) / total_bads
            cum_goods = np.cumsum(goods) / total_goods
            
            ks = np.max(np.abs(cum_bads - cum_goods))
            ks_dict[col] = float(ks)
            
        return ks_dict
        
    def compute_ks_table(self, col: str, bins: int = 10) -> pd.DataFrame:
        """Compute a quantile table with KS, Bad Rate, and volume for a specific score column."""
        import numpy as np
        
        df = self.data[[col, self.target_col]].dropna().copy()
        
        # Create quantiles (deciles by default)
        try:
            df["Decile"] = pd.qcut(df[col], q=bins, labels=False, duplicates='drop')
        except ValueError:
            # Fallback if too many identical values
            df["Decile"] = pd.cut(df[col], bins=bins, labels=False)
            
        # Group by Decile (we want decile 0 to be the WORST score, i.e., highest default rate)
        # So we sort descending by decile, assuming score is higher=better
        summary = df.groupby("Decile").agg(
            Volume=(self.target_col, "count"),
            Bads=(self.target_col, "sum"),
            Avg_Score=(col, "mean")
        ).reset_index()
        
        # Sort so that highest score (best risk) is at the top
        summary = summary.sort_values("Avg_Score", ascending=False).reset_index(drop=True)
        
        # Add human readable bucket numbers (1 is best, 10 is worst)
        summary["Bucket"] = range(1, len(summary) + 1)
        
        summary["Goods"] = summary["Volume"] - summary["Bads"]
        summary["Bad_Rate"] = summary["Bads"] / summary["Volume"]
        
        total_bads = summary["Bads"].sum()
        total_goods = summary["Goods"].sum()
        
        if total_bads > 0 and total_goods > 0:
            summary["Cum_Bads"] = summary["Bads"].cumsum() / total_bads
            summary["Cum_Goods"] = summary["Goods"].cumsum() / total_goods
            summary["KS"] = np.abs(summary["Cum_Bads"] - summary["Cum_Goods"])
        else:
            summary["Cum_Bads"] = 0.0
            summary["Cum_Goods"] = 0.0
            summary["KS"] = 0.0
            
        # Reorder columns
        return summary[["Bucket", "Avg_Score", "Volume", "Bad_Rate", "Cum_Bads", "Cum_Goods", "KS"]]

