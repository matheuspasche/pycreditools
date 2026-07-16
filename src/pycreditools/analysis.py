"""Trade-off analysis: the raw-curve verdict over the single sweep engine.

``TradeoffAnalyzer`` names grid dimensions; :func:`pycreditools.sweep.run_sweep`
does all simulation and metric math (issue #71). Metrics follow ADR 0008
(docs/adr/0008-metric-contract-approval-take-up-default.md): ``approval_rate``
is pre take-up over the whole base; ``default_rate`` is contracted-weighted.
"""
from typing import Any

import pandas as pd

from .policy import CreditPolicy
from .stages import VALID_CUTOFF_DIRECTIONS
from .sweep import BASE_RATE_SUFFIX, STRESS_DIM, run_sweep


class TradeoffAnalyzer:
    """A fluid builder for running trade-off analysis on a credit policy."""

    def __init__(self, base_policy: CreditPolicy):
        self.base_policy = base_policy
        self.vary_params: dict[str, list[Any]] = {}
        self.vary_directions: dict[str, str] = {}

    def vary_cutoff(
        self, col_name: str, values: list[float], direction: str | None = None
    ) -> "TradeoffAnalyzer":
        """Sweep ``col_name``'s cutoff over ``values``.

        ``direction`` is "gte"/"lte". When omitted, a column whose existing
        ``CutoffStage`` declares a direction inherits it; otherwise "gte".
        Passing it explicitly always overrides.
        """
        if direction is not None:
            if direction not in VALID_CUTOFF_DIRECTIONS:
                raise ValueError(
                    f"Unknown direction '{direction}' for cutoff sweep on '{col_name}': "
                    f"use 'gte' (>=) or 'lte' (<=)."
                )
            self.vary_directions[col_name] = direction
        self.vary_params[f"{col_name}_cutoff"] = values
        return self

    def vary_base_rate(self, stage_name: str, values: list[float]) -> "TradeoffAnalyzer":
        self.vary_params[f"{stage_name}{BASE_RATE_SUFFIX}"] = values
        return self

    def vary_stress_aggravation(self, values: list[float]) -> "TradeoffAnalyzer":
        self.vary_params[STRESS_DIM] = values
        return self

    def run(self, data: pd.DataFrame, parallel: bool = False) -> pd.DataFrame:
        # Engine warnings (e.g. calibration reliability) must reach the caller:
        # the warning suppression that used to live here hid them (issue #71).
        return run_tradeoff_analysis(
            data, self.base_policy, self.vary_params, self.vary_directions, parallel
        )


def run_tradeoff_analysis(
    data: pd.DataFrame,
    base_policy: CreditPolicy,
    vary_params: dict[str, list[Any]],
    vary_directions: dict[str, str] = None,
    parallel: bool = False,
) -> pd.DataFrame:
    """Run a trade-off analysis simulation over a grid of parameters.

    Args:
        data: Applicant data.
        base_policy: The template policy. Everything it declares binds at every
            grid point except the swept dimensions.
        vary_params: Dictionary mapping parameter names to lists of values:
            ``"{col}_cutoff"``, ``"{stage}_base_rate"`` or ``"aggravation_factor"``.
        vary_directions: Column -> "gte"/"lte" for swept cutoffs (default "gte").
        parallel: Whether to run re-simulated grids in parallel.

    Returns:
        DataFrame containing results.

    Note:
        Consider using TradeoffAnalyzer for a cleaner, object-oriented API.
    """
    cutoff_grid: dict[str, list[float]] = {}
    base_rates: dict[str, list[float]] = {}
    stress_factors: list[float] | None = None

    for key, values in vary_params.items():
        if key == STRESS_DIM:
            stress_factors = list(values)
        elif key.endswith("_cutoff"):
            cutoff_grid[key[: -len("_cutoff")]] = list(values)
        elif key.endswith(BASE_RATE_SUFFIX):
            base_rates[key[: -len(BASE_RATE_SUFFIX)]] = list(values)
        else:
            raise ValueError(
                f"Unknown sweep parameter '{key}': expected '{{col}}_cutoff', "
                f"'{{stage}}{BASE_RATE_SUFFIX}' or '{STRESS_DIM}'."
            )

    results = run_sweep(
        data,
        base_policy,
        cutoff_grid=cutoff_grid,
        directions=vary_directions,
        stress_factors=stress_factors,
        base_rates=base_rates,
        parallel=parallel,
    )

    renames = {col: f"{col}_cutoff" for col in cutoff_grid}
    renames["overall_approval_rate"] = "approval_rate"
    renames["overall_default_rate"] = "default_rate"
    return results.rename(columns=renames)
