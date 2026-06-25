"""Analysis orchestration: thin wrappers over `pycreditools` returning plain data.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import pandas as pd

from pycreditools import CreditPolicy, CreditSimResults, ModelEvaluator


def effective_n(df: pd.DataFrame, target_col: str) -> int:
    """Count of rows with an observed (non-NaN) target in `df`."""
    return int(df[target_col].notna().sum())


def run_policy_sim(
    df: pd.DataFrame, policy: CreditPolicy, method: str = "analytical"
) -> CreditSimResults:
    """Run `policy` on `df`, via `CreditPolicy.simulate()`."""
    return policy.simulate(df, method=method)


def policy_kpis(sim: CreditSimResults) -> dict[str, float | None]:
    """Final approval rate, approved volume, and (if observed) the simulated bad rate."""
    data = sim.data
    approved_volume = float(data["new_approval"].sum())
    approval_rate = float(data["new_approval"].mean()) if len(data) else 0.0
    bad_rate = None
    if "simulated_default" in data.columns and data["simulated_default"].notna().any():
        weighted = (data["simulated_default"] * data["new_approval"]).sum()
        bad_rate = float(weighted / approved_volume) if approved_volume > 0 else None
    return {
        "approval_rate": approval_rate,
        "approved_volume": approved_volume,
        "bad_rate": bad_rate,
    }


def evaluate_scores(df: pd.DataFrame, score_cols: list[str], target_col: str) -> dict[str, float]:
    """KS statistic per score, via `ModelEvaluator.compute_ks()`."""
    return ModelEvaluator(df, score_cols, target_col).compute_ks()


def ks_table(df: pd.DataFrame, score_col: str, target_col: str, bins: int = 10) -> pd.DataFrame:
    """Per-bucket KS/bad-rate table for one score, via `ModelEvaluator.compute_ks_table()`."""
    return ModelEvaluator(df, [score_col], target_col).compute_ks_table(score_col, bins)
