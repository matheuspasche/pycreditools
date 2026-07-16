"""Single sweep engine: grid -> simulate -> metrics (issue #71).

Every cutoff/stress/rate sweep in the package runs through :func:`run_sweep`.
The verdict layers -- ``optimize_cutoffs`` (constraints + best-pick + Pareto)
and ``TradeoffAnalyzer`` (raw curve) -- are thin wrappers; nothing outside
this module computes approval or default rates for a swept grid.

Contract:

- **The config always binds.** Every stage, stress scenario and calibration
  the policy declares holds at every grid point. The sweep overrides exactly
  the dimension being swept -- the one unavoidable exception.
- **Direction is declared, never inferred** (``directions={"col": "lte"}``,
  default ``"gte"``; a swept column that already carries a ``CutoffStage``
  inherits that stage's direction unless ``directions`` overrides it).
- **Metrics follow ADR 0008** (docs/adr/0008-metric-contract-approval-take-up-default.md):
  ``overall_approval_rate`` is the pre-take-up approval rate over the whole
  base; ``overall_default_rate`` is weighted by the *contracted* population.
- **Fast path vs re-simulation is a performance boundary, never a semantic
  one.** When only cutoffs vary, the baseline (config minus the swept cutoff
  entries) is simulated once and each grid point is a vectorised mask -- valid
  because a cutoff is a pure mask over a fixed per-row baseline. When stress
  or a rate varies, per-row ``simulated_default`` / ``approved_pre_rate``
  change, so each combination re-simulates. Whichever path runs, and whichever
  ``method=`` is chosen, the same set of stages binds.
"""
from __future__ import annotations

import dataclasses
import itertools
from typing import Any

import numpy as np
import pandas as pd

from .policy import CreditPolicy
from .stages import VALID_CUTOFF_DIRECTIONS, CutoffStage, RateStage
from .stress import AggravationStress

STRESS_DIM = "aggravation_factor"
BASE_RATE_SUFFIX = "_base_rate"


def resolve_direction(
    col: str, directions: dict[str, str] | None, policy: CreditPolicy
) -> str:
    """The declared sweep direction for ``col``: ``directions`` override, else
    the direction of the ``CutoffStage`` already covering ``col``, else ``"gte"``."""
    if directions and col in directions:
        direction = directions[col]
    else:
        direction = "gte"
        for stage in policy.stages:
            if isinstance(stage, CutoffStage) and col in stage.cutoffs:
                direction = stage.direction
                break
    if direction not in VALID_CUTOFF_DIRECTIONS:
        raise ValueError(
            f"Unknown sweep direction '{direction}' for column '{col}': "
            f"use 'gte' (>=) or 'lte' (<=)."
        )
    return direction


def _without_cutoff_entries(policy: CreditPolicy, cols: set[str]) -> CreditPolicy:
    """Drop ``cols`` from every ``CutoffStage`` (a stage left empty is dropped).

    A swept column's existing cutoff is what the sweep overrides; every other
    column in the same stage keeps binding.
    """
    kept = []
    for stage in policy.stages:
        if isinstance(stage, CutoffStage) and any(c in stage.cutoffs for c in cols):
            remaining = {c: v for c, v in stage.cutoffs.items() if c not in cols}
            if remaining:
                kept.append(
                    CutoffStage(name=stage.name, cutoffs=remaining, direction=stage.direction)
                )
            continue
        kept.append(stage)
    return dataclasses.replace(policy, stages=tuple(kept))


def _metrics(
    sim_df: pd.DataFrame,
    actual_defaults: np.ndarray | None,
    mask: np.ndarray | None = None,
) -> tuple[float, float]:
    """ADR 0008 metrics over a simulated frame, optionally under a cutoff mask.

    overall_approval_rate = approved_pre_rate.sum() / N        (pre take-up)
    overall_default_rate  = weighted by the contracted population (new_approval)
    """
    n = len(sim_df)
    if n == 0:
        return 0.0, 0.0

    # Pre-take-up approval; falls back to new_approval when the policy has no
    # RateStage (the columns coincide there).
    if "approved_pre_rate" in sim_df.columns:
        p_pre = sim_df["approved_pre_rate"].to_numpy(dtype=float)
    else:
        p_pre = sim_df["new_approval"].to_numpy(dtype=float)
    p_pre = np.nan_to_num(p_pre, nan=0.0)

    contracted_w = np.nan_to_num(sim_df["new_approval"].to_numpy(dtype=float), nan=0.0)

    pd_base = sim_df["simulated_default"].to_numpy(dtype=float)
    if actual_defaults is not None:
        nas = np.isnan(pd_base)
        if nas.any():
            pd_base = np.where(nas, actual_defaults, pd_base)
    pd_base = np.nan_to_num(pd_base, nan=0.0)

    if mask is not None:
        p_pre = p_pre * mask
        contracted_w = contracted_w * mask

    app_rate = float(p_pre.sum() / n)
    contracted_sum = float(contracted_w.sum())
    if contracted_sum > 0:
        def_rate = float((contracted_w * pd_base).sum() / contracted_sum)
    else:
        def_rate = 0.0
    return app_rate, def_rate


def _actual_defaults_array(data: pd.DataFrame, policy: CreditPolicy) -> np.ndarray | None:
    col = policy.actual_default_col
    if col is not None and col in data.columns:
        return data[col].to_numpy(dtype=float)
    return None


def _policy_for_combo(
    policy: CreditPolicy,
    cutoff_values: dict[str, float],
    resolved_directions: dict[str, str],
    aggravation_factor: float | None,
    base_rate_values: dict[str, float],
) -> CreditPolicy:
    """The per-combination policy: the config, with exactly the swept dimensions overridden."""
    temp = policy
    if cutoff_values:
        temp = _without_cutoff_entries(temp, set(cutoff_values))
        stages_list = list(temp.stages)
        for col, val in cutoff_values.items():
            stages_list.append(
                CutoffStage(
                    name=f"sweep_cutoff_{col}",
                    cutoffs={col: val},
                    direction=resolved_directions[col],
                )
            )
        temp = dataclasses.replace(temp, stages=tuple(stages_list))

    if aggravation_factor is not None:
        temp = dataclasses.replace(
            temp, stress_scenarios=(AggravationStress(factor=aggravation_factor),)
        )

    if base_rate_values:
        stages_list = list(temp.stages)
        matched = set()
        for i, stage in enumerate(stages_list):
            if isinstance(stage, RateStage) and stage.name in base_rate_values:
                stages_list[i] = RateStage(
                    name=stage.name,
                    base_rate=base_rate_values[stage.name],
                    variable=stage.variable,
                    calibrate=stage.calibrate,
                )
                matched.add(stage.name)
        missing = set(base_rate_values) - matched
        if missing:
            raise ValueError(
                f"No RateStage named {sorted(missing)} in the policy to sweep base_rate on."
            )
        temp = dataclasses.replace(temp, stages=tuple(stages_list))

    return temp


def _evaluate_combo(args: tuple) -> dict[str, Any]:
    """Slow-path worker: rebuild the policy for one combination and re-simulate.

    Module-level so ProcessPoolExecutor can pickle it.
    """
    (combo, data, policy, resolved_directions, method) = args
    cutoff_values = {k: v for k, v in combo.items() if k in resolved_directions}
    aggravation = combo.get(STRESS_DIM)
    base_rate_values = {
        k[: -len(BASE_RATE_SUFFIX)]: v
        for k, v in combo.items()
        if k.endswith(BASE_RATE_SUFFIX) and k not in resolved_directions and k != STRESS_DIM
    }
    temp_policy = _policy_for_combo(
        policy, cutoff_values, resolved_directions, aggravation, base_rate_values
    )
    sim = temp_policy.simulate(data, method=method)
    app_rate, def_rate = _metrics(sim.data, _actual_defaults_array(data, policy))
    row = dict(combo)
    row["overall_approval_rate"] = app_rate
    row["overall_default_rate"] = def_rate
    return row


def run_sweep(
    data: pd.DataFrame,
    policy: CreditPolicy,
    *,
    cutoff_grid: dict[str, list[float]] | None = None,
    directions: dict[str, str] | None = None,
    stress_factors: list[float] | None = None,
    base_rates: dict[str, list[float]] | None = None,
    method: str = "analytical",
    parallel: bool = False,
) -> pd.DataFrame:
    """Evaluate a grid of policy variations and report ADR 0008 metrics per point.

    Args:
        data: Applicant data.
        policy: The base policy. Everything it declares binds at every grid
            point except the dimensions named below.
        cutoff_grid: Column -> list of cutoff values to sweep. A column that
            already carries a ``CutoffStage`` has that entry replaced per grid
            point; otherwise a cutoff is appended.
        directions: Column -> ``"gte"``/``"lte"`` for swept columns. Defaults
            to the existing stage's direction, else ``"gte"``. Never inferred
            from the data.
        stress_factors: Values for a swept flat ``AggravationStress`` factor
            (replaces the policy's stress scenarios per grid point).
        base_rates: RateStage name -> list of ``base_rate`` values to sweep.
        method: "analytical" or "stochastic" -- the *simulation* choice,
            orthogonal to whether the sweep re-simulates per point.
        parallel: Parallelise the re-simulation path.

    Returns:
        DataFrame with one row per grid combination: the swept dimensions
        (cutoff columns by name, ``aggravation_factor``, ``{stage}_base_rate``)
        plus ``overall_approval_rate`` and ``overall_default_rate``.
    """
    cutoff_grid = cutoff_grid or {}
    base_rates = base_rates or {}

    resolved_directions = {
        col: resolve_direction(col, directions, policy) for col in cutoff_grid
    }

    dims: list[tuple[str, list[Any]]] = [(col, list(vals)) for col, vals in cutoff_grid.items()]
    dims += [(f"{name}{BASE_RATE_SUFFIX}", list(vals)) for name, vals in base_rates.items()]
    if stress_factors is not None:
        dims.append((STRESS_DIM, list(stress_factors)))

    if not dims:
        raise ValueError(
            "Nothing to sweep: pass cutoff_grid, base_rates and/or stress_factors."
        )
    for name, vals in dims:
        if not vals:
            raise ValueError(f"Sweep dimension '{name}' has no values.")

    keys = [name for name, _ in dims]
    grid = [dict(zip(keys, combo)) for combo in itertools.product(*(vals for _, vals in dims))]

    only_cutoffs = not base_rates and stress_factors is None

    if only_cutoffs:
        # Fast path: one baseline simulation (config minus the swept cutoff
        # entries), then each grid point is a vectorised mask. Per-row
        # simulated_default / approved_pre_rate are fixed, so this is exact --
        # a cutoff is a pure mask over the baseline.
        baseline = _without_cutoff_entries(policy, set(cutoff_grid))
        sim = baseline.simulate(data, method=method)
        sim_df = sim.data
        actual_defaults = _actual_defaults_array(data, policy)

        missing = [c for c in cutoff_grid if c not in data.columns]
        if missing:
            raise ValueError(f"Swept column(s) not found in data: {missing}")
        score_arrays = {col: data[col].to_numpy(dtype=float) for col in cutoff_grid}

        rows = []
        for combo in grid:
            mask = np.ones(len(data), dtype=bool)
            for col, val in combo.items():
                arr = score_arrays[col]
                if resolved_directions[col] == "gte":
                    mask &= arr >= val
                else:
                    mask &= arr <= val
            app_rate, def_rate = _metrics(sim_df, actual_defaults, mask.astype(float))
            row = dict(combo)
            row["overall_approval_rate"] = app_rate
            row["overall_default_rate"] = def_rate
            rows.append(row)
        return pd.DataFrame(rows)

    # Re-simulation path: stress / base-rate changes move per-row
    # simulated_default and approved_pre_rate, so every combination re-simulates.
    from ._parallel import parallel_map

    tasks = [(combo, data, policy, resolved_directions, method) for combo in grid]
    rows = parallel_map(_evaluate_combo, tasks, parallel=parallel)
    return pd.DataFrame(rows)
