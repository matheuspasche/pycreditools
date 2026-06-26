"""Analysis orchestration: thin wrappers over `pycreditools` returning plain data.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pandas as pd

from pycreditools import (
    CreditPolicy,
    CreditSimResults,
    CutoffStage,
    ModelEvaluator,
    TradeoffAnalyzer,
    compare_policies,
    summarize_results,
)


def effective_n(df: pd.DataFrame, target_col: str) -> int:
    """Count of rows with an observed (non-NaN) target in `df`."""
    return int(df[target_col].notna().sum())


def run_policy_sim(
    df: pd.DataFrame, policy: CreditPolicy, method: str = "analytical"
) -> CreditSimResults:
    """Run `policy` on `df`, via `CreditPolicy.simulate()`."""
    return policy.simulate(df, method=method)


def policy_kpis(sim: CreditSimResults) -> dict[str, float | None]:
    """Final approval rate, approved/hired volume, and (if observed) the simulated bad rate."""
    data = sim.data
    approved_volume = float(data["new_approval"].sum())
    approval_rate = float(data["new_approval"].mean()) if len(data) else 0.0
    bad_rate = None
    if "simulated_default" in data.columns and data["simulated_default"].notna().any():
        weighted = (data["simulated_default"] * data["new_approval"]).sum()
        bad_rate = float(weighted / approved_volume) if approved_volume > 0 else None
    pre_rate_volume = (
        float(data["approved_pre_rate"].sum()) if "approved_pre_rate" in data.columns else None
    )
    return {
        "approval_rate": approval_rate,
        "approved_volume": approved_volume,
        "bad_rate": bad_rate,
        "pre_rate_volume": pre_rate_volume,
    }


def evaluate_scores(df: pd.DataFrame, score_cols: list[str], target_col: str) -> dict[str, float]:
    """KS statistic per score, via `ModelEvaluator.compute_ks()`."""
    return ModelEvaluator(df, score_cols, target_col).compute_ks()


def ks_table(df: pd.DataFrame, score_col: str, target_col: str, bins: int = 10) -> pd.DataFrame:
    """Per-bucket KS/bad-rate table for one score, via `ModelEvaluator.compute_ks_table()`."""
    return ModelEvaluator(df, [score_col], target_col).compute_ks_table(score_col, bins)


def quadrant_table(sim: CreditSimResults) -> pd.DataFrame:
    """One row per swap quadrant (volume, bad rate), via `summarize_results()`."""
    return summarize_results(sim)


def attach_rating(
    df: pd.DataFrame,
    rating_result: Any | None,
    rating_labels: dict[int, str] | None,
    *,
    rating_col: str = "Rating",
) -> pd.DataFrame:
    """Predict the fitted rating onto `df` and map cluster ids to labels (A..E).

    A no-op copy of `df` when `rating_result` is unset.
    """
    out = df.copy()
    if rating_result is None:
        return out
    predicted = rating_result.predict(df)["risk_rating"]
    out[rating_col] = predicted.map(rating_labels) if rating_labels else predicted
    return out


def swap_in_by_rating(df: pd.DataFrame, rating_col: str = "Rating") -> pd.DataFrame:
    """Swap-in volume/bad-rate per rating tier — reproduces `print_swap_in_by_rating`'s table."""
    columns = [rating_col, "Vol_Esperado", "Vol_Pct", "Inad_Stressed"]
    if rating_col not in df.columns or "scenario" not in df.columns:
        return pd.DataFrame(columns=columns)
    swap_in = df[df["scenario"] == "swap_in"]
    if swap_in.empty:
        return pd.DataFrame(columns=columns)

    def _aggregate(group: pd.DataFrame) -> pd.Series:
        volume = group["new_approval"].sum()
        bad_rate = (
            (group["simulated_default"] * group["new_approval"]).sum() / volume
            if volume > 0
            else np.nan
        )
        return pd.Series({"Vol_Esperado": volume, "Inad_Stressed": bad_rate})

    grouped = swap_in.groupby(rating_col).apply(_aggregate, include_groups=False).reset_index()
    total = grouped["Vol_Esperado"].sum()
    grouped["Vol_Pct"] = grouped["Vol_Esperado"] / total if total > 0 else 0.0
    return grouped.sort_values(rating_col, ascending=False).reset_index(drop=True)[columns]


def swap_in_by_segment(
    df: pd.DataFrame, rating_col: str = "Rating", segment_col: str = "region"
) -> pd.DataFrame:
    """Crosstab of swap-in volume by `rating_col` x `segment_col`."""
    required = (rating_col, segment_col, "scenario")
    if any(col not in df.columns for col in required):
        return pd.DataFrame()
    swap_in = df[df["scenario"] == "swap_in"]
    if swap_in.empty:
        return pd.DataFrame()
    return pd.pivot_table(
        swap_in,
        index=rating_col,
        columns=segment_col,
        values="new_approval",
        aggfunc="sum",
        fill_value=0.0,
    )


def compare_with_baseline(sim_new: CreditSimResults, sim_old: CreditSimResults) -> dict[str, Any]:
    """Approval/bad-rate deltas + swap summary vs `sim_old`, via `compare_policies()`."""
    return compare_policies(sim_new, sim_old)


def delta_table(sim_new: CreditSimResults, sim_old: CreditSimResults) -> pd.DataFrame:
    """Executive P&L delta (approval rate, bad rate, hired volume).

    Reproduces `print_delta_table`'s single-comparison branch.
    """
    df_new, df_old = sim_new.data, sim_old.data
    policy_old = sim_old.metadata["policy"]
    is_analytical_new = sim_new.metadata.get("method") == "analytical"
    is_analytical_old = sim_old.metadata.get("method") == "analytical"

    old_default_col = policy_old["actual_default_col"]
    old_approval_col = policy_old.get("current_approval_col", "approved")
    legacy_hired_col = "hired" if "hired" in df_old.columns else old_approval_col

    approval_old = (
        df_old[old_approval_col].mean()
        if is_analytical_old
        else (df_old[old_approval_col] > 0).mean()
    )
    volume_old = df_old[legacy_hired_col].sum()
    bad_old = (
        (df_old[old_default_col] * df_old[legacy_hired_col]).sum() / volume_old
        if volume_old > 0
        else 0.0
    )

    new_approval_col = (
        "approved_pre_rate" if "approved_pre_rate" in df_new.columns else "new_approval"
    )
    approval_new = (
        df_new[new_approval_col].mean()
        if is_analytical_new
        else (df_new[new_approval_col] > 0).mean()
    )
    volume_new = df_new["new_approval"].sum()
    bad_new = (
        (df_new["simulated_default"] * df_new["new_approval"]).sum() / volume_new
        if volume_new > 0
        else 0.0
    )

    rows = [
        {"Metric": "Taxa de aprovação", "Legacy": approval_old, "New": approval_new},
        {"Metric": "Inadimplência esperada", "Legacy": bad_old, "New": bad_new},
        {"Metric": "Volume contratado esperado", "Legacy": volume_old, "New": volume_new},
    ]
    table = pd.DataFrame(rows)
    table["Delta_Abs"] = table["New"] - table["Legacy"]
    table["Delta_Rel"] = (table["New"] / table["Legacy"].replace(0, np.nan)) - 1.0
    return table


def cutoff_range(df: pd.DataFrame, score_col: str, steps: int = 35) -> list[int]:
    """p5..p95 sweep of `score_col`, as the int cutoffs v14 Cell 10 uses.

    Falls back to a single median point when the score has too little spread
    for `steps` distinct integer cutoffs (the PRD's low-variance edge case).
    """
    p5 = float(df[score_col].quantile(0.05))
    p95 = float(df[score_col].quantile(0.95))
    if p95 <= p5:
        return [int(df[score_col].median())]
    return np.linspace(p5, p95, steps).astype(int).tolist()


def strip_cutoff(policy: CreditPolicy, score_col: str) -> CreditPolicy:
    """Drop `score_col` from any `CutoffStage`, so a swept trade-off cutoff isn't double-applied.

    A stage cutting on multiple columns keeps its other columns; a stage left
    with none is dropped entirely.
    """
    kept = []
    for stage in policy.stages:
        if isinstance(stage, CutoffStage) and score_col in stage.cutoffs:
            remaining = {col: val for col, val in stage.cutoffs.items() if col != score_col}
            if remaining:
                kept.append(
                    CutoffStage(name=stage.name, cutoffs=remaining, direction=stage.direction)
                )
            continue
        kept.append(stage)
    return dataclasses.replace(policy, stages=tuple(kept))


def run_tradeoff(
    df: pd.DataFrame,
    base_policy: CreditPolicy,
    score_col: str,
    cutoff_values: list[float],
    *,
    stress_values: list[float] | None = None,
    rate_stage: tuple[str, list[float]] | None = None,
    parallel: bool = False,
) -> pd.DataFrame:
    """Sweep `score_col`'s cutoff (optionally x stress factor / a rate stage's base rate).

    Reproduces v14 Cell 10: tags `Score_Model` and a unified `Cutoff` column from
    the analyzer's `{score_col}_cutoff` output, via `TradeoffAnalyzer`.
    """
    stripped = strip_cutoff(base_policy, score_col)
    analyzer = TradeoffAnalyzer(stripped).vary_cutoff(score_col, cutoff_values)
    if stress_values:
        analyzer = analyzer.vary_stress_aggravation(stress_values)
    if rate_stage:
        stage_name, rate_values = rate_stage
        analyzer = analyzer.vary_base_rate(stage_name, rate_values)
    result = analyzer.run(df, parallel=parallel).copy()
    result["Score_Model"] = score_col
    result["Cutoff"] = result[f"{score_col}_cutoff"]
    return result


def tradeoff_scenarios(
    res_s: pd.DataFrame, legacy_approval_rate: float, legacy_bad_rate: float
) -> dict[str, pd.Series]:
    """The 3 executive scenarios from v14 Cell 12: conservador / agressivo / neutro.

    `res_s` is one score model's trade-off rows (has `Cutoff`/`approval_rate`/`default_rate`).
    """
    conservative = res_s.loc[(res_s["approval_rate"] - legacy_approval_rate).abs().idxmin()]
    aggressive = res_s.loc[(res_s["default_rate"] - legacy_bad_rate).abs().idxmin()]
    mid_cutoff = (conservative["Cutoff"] + aggressive["Cutoff"]) / 2
    neutral = res_s.loc[(res_s["Cutoff"] - mid_cutoff).abs().idxmin()]
    return {"conservador": conservative, "agressivo": aggressive, "neutro": neutral}


def decision_preview(
    sim: CreditSimResults,
    rating_recipe: Any | None = None,
    rating_labels: dict[int, str] | None = None,
    n: int = 50,
) -> pd.DataFrame:
    """Head of the row-level decision table, via `CreditSimResults.to_decision_dataframe()`."""
    return sim.to_decision_dataframe(rating_recipe, rating_labels).head(n)
