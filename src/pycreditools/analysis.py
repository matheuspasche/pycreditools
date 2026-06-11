import copy
import itertools
from typing import Any

import pandas as pd

from .policy import CreditPolicy
from .simulation import SimulationMethod, run_simulation
from .stages import CutoffStage, RateStage
from .stress import AggravationStress


class TradeoffAnalyzer:
    """A fluid builder for running trade-off analysis on a credit policy."""

    def __init__(self, base_policy: CreditPolicy):
        self.base_policy = base_policy
        self.vary_params: dict[str, list[Any]] = {}

    def vary_cutoff(self, col_name: str, values: list[float]) -> "TradeoffAnalyzer":
        self.vary_params[f"{col_name}_cutoff"] = values
        return self

    def vary_base_rate(self, stage_name: str, values: list[float]) -> "TradeoffAnalyzer":
        self.vary_params[f"{stage_name}_base_rate"] = values
        return self

    def vary_stress_aggravation(self, values: list[float]) -> "TradeoffAnalyzer":
        self.vary_params["aggravation_factor"] = values
        return self

    def run(self, data: pd.DataFrame, parallel: bool = False) -> pd.DataFrame:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return run_tradeoff_analysis(data, self.base_policy, self.vary_params, parallel)


def run_tradeoff_analysis(
    data: pd.DataFrame,
    base_policy: CreditPolicy,
    vary_params: dict[str, list[Any]],
    parallel: bool = False,
) -> pd.DataFrame:
    """Run a trade-off analysis simulation over a grid of parameters.

    Args:
        data: Applicant data.
        base_policy: The template policy.
        vary_params: Dictionary mapping parameter names to lists of values.
        parallel: Whether to run in parallel using concurrent.futures.

    Returns:
        DataFrame containing results.

    Note:
        Consider using TradeoffAnalyzer for a cleaner, object-oriented API.
    """
    keys = list(vary_params.keys())
    values = list(vary_params.values())

    # Create parameter grid
    grid = [dict(zip(keys, v)) for v in itertools.product(*values)]

    def _run_single(params: dict[str, Any]) -> dict[str, Any]:
        temp_policy = copy.deepcopy(base_policy)

        # 1. Handle Cutoffs
        cutoff_params = {k: v for k, v in params.items() if k.endswith("_cutoff")}
        if cutoff_params:
            actual_cutoffs = {}
            for k, v in cutoff_params.items():
                col_name = k.replace("_cutoff", "")
                if col_name in data.columns:
                    actual_cutoffs[col_name] = v

            if actual_cutoffs:
                stages_list = list(temp_policy.stages)
                unmatched_cutoffs = {}
                for col_name, val in actual_cutoffs.items():
                    matched = False
                    for i, stage in enumerate(stages_list):
                        if isinstance(stage, CutoffStage) and col_name in stage.cutoffs:
                            new_cutoffs = dict(stage.cutoffs)
                            new_cutoffs[col_name] = val
                            stages_list[i] = CutoffStage(
                                name=stage.name, cutoffs=new_cutoffs, direction=stage.direction
                            )
                            matched = True
                            break
                    if not matched:
                        unmatched_cutoffs[col_name] = val

                if unmatched_cutoffs:
                    stages_list.append(
                        CutoffStage(name="dynamic_cutoffs", cutoffs=unmatched_cutoffs)
                    )

                import dataclasses

                temp_policy = dataclasses.replace(temp_policy, stages=tuple(stages_list))

        # 2. Handle Aggravation Factor
        if "aggravation_factor" in params:
            agg_stress = AggravationStress(factor=params["aggravation_factor"])
            # Replace stress scenarios
            import dataclasses

            temp_policy = dataclasses.replace(temp_policy, stress_scenarios=(agg_stress,))

        # 3. Handle Dynamic Base Rates
        base_rate_params = {k: v for k, v in params.items() if k.endswith("_base_rate")}
        if base_rate_params:
            stages_list = list(temp_policy.stages)
            for k, v in base_rate_params.items():
                stage_name = k.replace("_base_rate", "")
                for i, stage in enumerate(stages_list):
                    if stage.name == stage_name and isinstance(stage, RateStage):
                        stages_list[i] = RateStage(
                            name=stage.name, base_rate=v, variable=stage.variable
                        )

            import dataclasses

            temp_policy = dataclasses.replace(temp_policy, stages=tuple(stages_list))

        # Run simulation
        sim_results = run_simulation(data, temp_policy, method=SimulationMethod.ANALYTICAL)
        final_data = sim_results.data

        # Use approved_pre_rate when available so metrics reflect the *approved* population,
        # not the contracted one — avoids RateStage (take-up) distorting the tradeoff curve.
        _aprov_col = (
            "approved_pre_rate"
            if "approved_pre_rate" in final_data.columns
            else "new_approval"
        )

        app_sum = final_data[_aprov_col].sum()
        total = len(final_data)
        approval_rate = app_sum / total if total > 0 else 0.0

        if app_sum > 0:
            bad_rate = (
                final_data["simulated_default"] * final_data[_aprov_col]
            ).sum() / app_sum
        else:
            bad_rate = 0.0

        result = dict(params)
        result["approval_rate"] = approval_rate
        result["default_rate"] = bad_rate
        return result

    if parallel:
        import concurrent.futures

        with concurrent.futures.ProcessPoolExecutor() as executor:
            results = list(executor.map(_run_single, grid))
    else:
        results = [_run_single(p) for p in grid]

    return pd.DataFrame(results)
