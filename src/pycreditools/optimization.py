"""
Cutoff optimization: the constraints + best-pick + Pareto verdict over the
single sweep engine (issue #71). All simulation and metric math lives in
:func:`pycreditools.sweep.run_sweep`; metrics follow ADR 0008
(docs/adr/0008-metric-contract-approval-take-up-default.md).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .policy import CreditPolicy
from .stages import CutoffStage
from .sweep import run_sweep


@dataclass
class OptimizationResult:
    """Result object for credit policy cutoff optimization."""
    best_combination: dict[str, float]
    metrics: dict[str, float]
    all_results: pd.DataFrame
    pareto_frontier: pd.DataFrame
    params: dict[str, Any]

    def __repr__(self) -> str:
        return (
            f"OptimizationResult(best_combination={self.best_combination}, "
            f"metrics={self.metrics}, n_combinations={len(self.all_results)})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the best result to a dictionary."""
        return {
            "best_combination": self.best_combination,
            "metrics": self.metrics,
            "params": self.params,
        }

    def find_equivalent(
        self,
        target_metric: str = "approval_rate",
        target_value: float = 0.20,
        tolerance: float = 0.01,
    ) -> pd.DataFrame:
        """Find combinations in the grid that match a target metric within tolerance."""
        col_name = "overall_approval_rate" if "approval" in target_metric else "overall_default_rate"
        if col_name not in self.all_results.columns:
            for alternate in ["approval_rate", "default_rate"]:
                if alternate in self.all_results.columns and alternate in target_metric:
                    col_name = alternate
                    break

        if col_name not in self.all_results.columns:
            raise ValueError(f"Column for target metric '{target_metric}' not found in results.")

        matches = self.all_results[np.abs(self.all_results[col_name] - target_value) <= tolerance].copy()
        matches["diff"] = np.abs(matches[col_name] - target_value)

        if matches.empty:
            closest = self.all_results.copy()
            closest["diff"] = np.abs(closest[col_name] - target_value)
            return closest.sort_values("diff").head(1)

        return matches.sort_values("diff").reset_index(drop=True)

    def plot(
        self,
        type: str = "tradeoff",
        save_path: str | None = None,
    ) -> Any:
        """Plot the tradeoff combinations space or the efficient Pareto frontier."""
        from .visualization import plot_optimization
        return plot_optimization(self, type=type, save_path=save_path)

def optimize_cutoffs(
    data: pd.DataFrame,
    config: CreditPolicy,
    cutoff_steps: int = 10,
    target_default_rate: float = 0.05,
    min_approval_rate: float = 0.3,
    method: str = "analytical",
    parallel: bool = False,
    percentiles: tuple[float, float] | None = (0.05, 0.95),
    cutoff_ranges: dict[str, list[float]] | None = None,
    directions: dict[str, str] | None = None,
) -> OptimizationResult:
    """Systematically evaluates a grid of cutoff combinations for a set of scores to find the optimal set of cutoffs.

    The config always binds: hard filters, stress, rate stages, calibration and
    cutoffs on non-swept scores hold at every grid point. The default grid is
    the ``score_cols`` **without** a ``CutoffStage`` in the config — a score
    carrying a cutoff is a decided parameter (frozen, not gridded). Pass
    ``cutoff_ranges`` to sweep an already-parameterised score explicitly.

    Args:
        data: Applicant data.
        config: Base CreditPolicy.
        cutoff_steps: Number of steps to generate for each score cutoff.
        target_default_rate: Maximum acceptable overall default rate
            (contracted-weighted, per ADR 0008).
        min_approval_rate: Minimum acceptable overall approval rate
            (pre take-up, per ADR 0008).
        method: "analytical" (expected values) or "stochastic" (row sampling).
            A simulation choice only — the same set of stages binds either way.
        parallel: Whether to evaluate combinations in parallel (re-simulation path only).
        percentiles: Optional tuple specifying lower/upper quantiles to bound score ranges (default 5% to 95%).
        cutoff_ranges: Optional dictionary of pre-defined list of cutoffs per score
            column. The explicit escape from the frozen-cutoff convention: it *is*
            the grid, exactly those columns. Keys must be in ``score_cols``.
        directions: Optional per-column sweep direction ("gte"/"lte", default
            "gte"; a swept score with an existing cutoff inherits its stage's
            direction unless overridden here). Declared, never inferred.

    Returns:
        OptimizationResult object.
    """
    if not (0.0 <= target_default_rate <= 1.0):
        raise ValueError("target_default_rate must be between 0.0 and 1.0.")
    if not (0.0 <= min_approval_rate <= 1.0):
        raise ValueError("min_approval_rate must be between 0.0 and 1.0.")
    if cutoff_steps < 1:
        raise ValueError("cutoff_steps must be at least 1.")
    if data.empty:
        raise ValueError("Input data DataFrame is empty.")

    # 1. Decide the grid columns
    score_cols = list(config.score_cols)
    if not score_cols:
        raise ValueError("The policy must define at least one score column in score_cols to optimize cutoffs.")

    if cutoff_ranges is not None:
        unknown = sorted(set(cutoff_ranges) - set(score_cols))
        if unknown:
            raise ValueError(
                f"cutoff_ranges keys must be in score_cols; unknown: {unknown}. "
                f"score_cols is the vocabulary for what counts as a score."
            )
        cutoff_ranges_dict = {col: list(vals) for col, vals in cutoff_ranges.items()}
    else:
        # A score already carrying a CutoffStage is a decided parameter: it
        # binds in the baseline and is not gridded. Sweep the rest.
        frozen = {
            col
            for stage in config.stages
            if isinstance(stage, CutoffStage)
            for col in stage.cutoffs
        }
        swept_cols = [col for col in score_cols if col not in frozen]
        if not swept_cols:
            raise ValueError(
                "Every score_col already has a cutoff in the policy; nothing to sweep. "
                "Pass cutoff_ranges= to sweep an already-parameterised score."
            )

        cutoff_ranges_dict = {}
        for col in swept_cols:
            if col not in data.columns:
                raise ValueError(f"Score column '{col}' not found in data.")
            vals = data[col].dropna()
            if vals.empty:
                raise ValueError(f"Score column '{col}' has only NaNs or is empty.")

            if percentiles is not None:
                min_val = float(np.floor(vals.quantile(percentiles[0])))
                max_val = float(np.ceil(vals.quantile(percentiles[1])))
            else:
                min_val = float(np.floor(vals.min()))
                max_val = float(np.ceil(vals.max()))

            if cutoff_steps == 1:
                cutoff_ranges_dict[col] = [float(vals.median())]
            else:
                cutoff_ranges_dict[col] = np.linspace(min_val, max_val, cutoff_steps).tolist()

    keys = list(cutoff_ranges_dict.keys())

    # 2. Run the sweep (single engine — the config binds, ADR 0008 metrics)
    all_results = run_sweep(
        data,
        config,
        cutoff_grid=cutoff_ranges_dict,
        directions=directions,
        method=method,
        parallel=parallel,
    )
    all_results.insert(0, "combination_id", range(1, len(all_results) + 1))
    app = all_results["overall_approval_rate"]
    dr = all_results["overall_default_rate"]
    all_results["constraints_met"] = (dr <= target_default_rate) & (app >= min_approval_rate)
    all_results["tradeoff_score"] = app - 5.0 * dr

    # 3. Find optimal result
    valid = all_results[all_results["constraints_met"]]
    if valid.empty:
        best_row = all_results.sort_values("tradeoff_score", ascending=False).iloc[0]
    else:
        best_row = valid.sort_values("overall_approval_rate", ascending=False).iloc[0]

    best_combo = {col: float(best_row[col]) for col in keys}
    best_metrics = {
        "overall_approval_rate": float(best_row["overall_approval_rate"]),
        "overall_default_rate": float(best_row["overall_default_rate"]),
        "tradeoff_score": float(best_row["tradeoff_score"]),
        "constraints_met": bool(best_row["constraints_met"])
    }

    # 4. Find Pareto frontier
    pareto_frontier = find_pareto_frontier(all_results)

    params = {
        "target_default_rate": target_default_rate,
        "min_approval_rate": min_approval_rate,
        "cutoff_steps": cutoff_steps,
        "method": method
    }

    return OptimizationResult(
        best_combination=best_combo,
        metrics=best_metrics,
        all_results=all_results,
        pareto_frontier=pareto_frontier,
        params=params
    )

def find_pareto_frontier(df: pd.DataFrame) -> pd.DataFrame:
    """Extract Pareto efficient combinations from the results.
    
    We want to maximize approval rate and minimize default rate.
    """
    clean_df = df.dropna(subset=["overall_approval_rate", "overall_default_rate"])
    if clean_df.empty:
        return pd.DataFrame(columns=df.columns)

    points = clean_df[["overall_approval_rate", "overall_default_rate"]].drop_duplicates().values
    pareto_points = []

    for i, p1 in enumerate(points):
        dominated = False
        for j, p2 in enumerate(points):
            if i == j:
                continue
            # p2 dominates p1 if approval(p2) >= approval(p1) and default(p2) <= default(p1)
            # with at least one strict inequality.
            if (p2[0] >= p1[0] and p2[1] <= p1[1]) and (p2[0] > p1[0] or p2[1] < p1[1]):
                dominated = True
                break
        if not dominated:
            pareto_points.append(p1)

    if not pareto_points:
        return pd.DataFrame(columns=df.columns)

    pareto_df = pd.DataFrame(pareto_points, columns=["overall_approval_rate", "overall_default_rate"])
    res = pd.merge(df, pareto_df, on=["overall_approval_rate", "overall_default_rate"], how="inner")
    return res.sort_values("overall_approval_rate").reset_index(drop=True)


