from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ._kernels import calculate_tier_metrics, iv_cluster, ward_cluster
from ._parallel import parallel_map


@dataclass
class ScreeningRecipe:
    variable: str
    boundaries: dict[int, list[float]]
    sub_mappings: dict[int, dict[int, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "boundaries": self.boundaries,
            "sub_mappings": self.sub_mappings,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScreeningRecipe:
        return cls(
            variable=d["variable"],
            boundaries={int(k): v for k, v in d["boundaries"].items()},
            sub_mappings={
                int(k): {int(sk): sv for sk, sv in v.items()} for k, v in d["sub_mappings"].items()
            },
        )


@dataclass
class ScreeningResult:
    metrics: pd.DataFrame
    recipes: dict[str, ScreeningRecipe]
    params: dict[str, Any]

    def predict(self, new_data: pd.DataFrame, variable: str, base_risk_col: str) -> pd.DataFrame:
        if variable not in self.recipes:
            raise ValueError(f"No recipe found for variable: {variable}")

        recipe = self.recipes[variable]
        df = new_data.copy()

        # We need to map each row based on its base_risk tier
        subsegments = []
        for tier in df[base_risk_col].unique():
            if pd.isna(tier):
                continue

            tier_mask = df[base_risk_col] == tier
            if tier not in recipe.boundaries:
                # Assign 1 if unknown tier
                subsegments.append(pd.Series(1, index=df[tier_mask].index))
                continue

            breaks = recipe.boundaries[tier]
            mapping = recipe.sub_mappings[tier]

            vals = df.loc[tier_mask, variable]
            # digitize
            binned = np.digitize(vals, breaks[1:-1])
            mapped = np.array([mapping.get(b, 1) for b in binned])

            subsegments.append(pd.Series(mapped, index=df[tier_mask].index))

        if subsegments:
            df[f"{variable}_sub"] = pd.concat(subsegments)
        else:
            df[f"{variable}_sub"] = np.nan

        return df

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipes": {k: v.to_dict() for k, v in self.recipes.items()},
            "params": self.params,
        }


def fit_risk_segments(
    data: pd.DataFrame,
    base_risk_col: str,
    candidate_cols: str | list[str],
    default_col: str,
    n_bins: int = 10,
    method: str = "quantiles",
    parallel: bool = False,
) -> ScreeningResult:
    """Screen candidates to find sub-segments within risk groups."""
    if isinstance(candidate_cols, str):
        candidate_cols = [candidate_cols]

    df = data.copy()
    tiers = [t for t in df[base_risk_col].unique() if not pd.isna(t)]

    recipes = {}
    all_metrics = []

    def _process_candidate(col: str) -> tuple[str, ScreeningRecipe, pd.DataFrame]:
        boundaries = {}
        sub_mappings = {}

        # Arrays for calculate_tier_metrics
        # Note: calculate_tier_metrics does the quantile binning internally
        # but we need boundaries for the recipe. So we must compute boundaries here anyway.

        tier_metrics = []

        for tier in tiers:
            tier_mask = df[base_risk_col] == tier
            tier_df = df[tier_mask].copy()

            vals = tier_df[col].values
            defaults = tier_df[default_col].values

            valid_mask = ~np.isnan(vals) & ~np.isnan(defaults)
            if not valid_mask.any():
                continue

            vals = vals[valid_mask]
            defaults = defaults[valid_mask]

            if len(vals) < n_bins:
                continue

            # Compute quantiles for boundaries
            quantiles = np.linspace(0, 1, n_bins + 1)
            q_breaks = np.unique(np.quantile(vals, quantiles))

            if len(q_breaks) < 2:
                continue

            boundaries[tier] = q_breaks.tolist()

            # Digitize to get bins
            binned = np.digitize(vals, q_breaks[1:-1])

            if method == "quantiles":
                # Just use bins as subsegments
                unique_bins = np.unique(binned)
                mapping = {int(b): int(i + 1) for i, b in enumerate(unique_bins)}
                sub_mappings[tier] = mapping

            else:
                # Need to cluster the bins
                agg_df = pd.DataFrame({"bin": binned, "default": defaults})
                agg = (
                    agg_df.groupby("bin")
                    .agg(volume=("default", "count"), bads=("default", "sum"))
                    .reset_index()
                )

                agg["pd"] = agg["bads"] / agg["volume"]

                if method == "ward":
                    clusters = ward_cluster(
                        pd_values=agg["pd"].values,
                        volumes=agg["volume"].values,
                        max_groups=3,  # typically 3 sub-segments max
                        min_vol_ratio=0.1,
                        max_crossings=1,
                    )
                else:  # iv
                    clusters = iv_cluster(
                        pd_values=agg["pd"].values,
                        volumes=agg["volume"].values,
                        max_groups=3,
                        min_vol_ratio=0.1,
                    )

                mapping = {int(b): int(c) for b, c in zip(agg["bin"], clusters)}
                sub_mappings[tier] = mapping

        # Now use the C++ equivalent kernel to get standardized metrics
        if method == "quantiles":
            metrics_df = calculate_tier_metrics(
                values=df[col].values,
                groups=df[base_risk_col].values,
                defaults=df[default_col].values,
                n_bins=n_bins,
            )
            metrics_df["variable"] = col
            tier_metrics.append(metrics_df)
        else:
            # If we clustered, the metrics should reflect the clustered subsegments?
            # For simplicity and to match C++, calculate_tier_metrics evaluates the raw quantiles
            # to measure the *potential* IV of the variable before clustering.
            metrics_df = calculate_tier_metrics(
                values=df[col].values,
                groups=df[base_risk_col].values,
                defaults=df[default_col].values,
                n_bins=n_bins,
            )
            metrics_df["variable"] = col
            tier_metrics.append(metrics_df)

        recipe = ScreeningRecipe(variable=col, boundaries=boundaries, sub_mappings=sub_mappings)

        if tier_metrics:
            combined_metrics = pd.concat(tier_metrics)
        else:
            combined_metrics = pd.DataFrame()

        return col, recipe, combined_metrics

    results = parallel_map(_process_candidate, candidate_cols, parallel=parallel)

    for col, recipe, metrics in results:
        recipes[col] = recipe
        all_metrics.append(metrics)

    if all_metrics:
        final_metrics = pd.concat(all_metrics, ignore_index=True)
    else:
        final_metrics = pd.DataFrame()

    return ScreeningResult(
        metrics=final_metrics, recipes=recipes, params={"n_bins": n_bins, "method": method}
    )


def screen_risk_segments(*args, **kwargs) -> ScreeningResult:
    """Deprecated alias for fit_risk_segments."""
    import warnings
    warnings.warn(
        "screen_risk_segments is deprecated and will be removed in a future version. "
        "Use fit_risk_segments instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return fit_risk_segments(*args, **kwargs)

