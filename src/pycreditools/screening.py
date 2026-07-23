from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from ._kernels import calculate_tier_metrics, iv_cluster, ward_cluster
from ._parallel import parallel_map
from .stages import CutoffStage, FilterStage

if TYPE_CHECKING:
    from .policy import CreditPolicy


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


#: Grid rule for :func:`suggest_hard_filters` (#73). Every distinct value is a
#: candidate threshold — hard-filter columns are zero-inflated, and the
#: sorted+cumsum path makes grid size effectively free. Beyond this many distinct
#: values fall back to a fine quantile grid so the ``argsort`` stays cheap.
_HF_MAX_DISTINCT_GRID = 10_000
_HF_FALLBACK_GRID_POINTS = 1_000


@dataclass
class HardFilterSuggestion:
    """The output of :func:`suggest_hard_filters`.

    Attributes:
        table: Every declared column × every candidate threshold, always returned
            in full. Each row is *standalone* — its ``cut_volume`` and ``lift`` are
            the rule measured alone, not net of any other rule. ``cut_volume`` is a
            **base** number (fraction of all rows), ``lift`` a **contracted** one
            (measured only where ``bad_col`` is observed); the two live on different
            populations by necessity and the column names say which is which.
        rule_set: The greedy set, in selection order. Each row carries its
            **marginal** cut (base rows this rule newly rejects, net of the rules
            already selected), the running ``cumulative_cut``, and the counts behind
            its lift so a human can audit the real impact of each rule on its own.
        rejected: Best candidate per rejected column, with the reason it lost
            (IV, lift, min-bads, or the set's budget).
        budget: ``floor`` (the input), ``spent`` (the set's union cut on the base),
            ``approval_rate`` (what the set leaves standing — same denominator as ADR
            0008's ``approval_rate``) and ``headroom`` (``approval_rate - floor``).
        params: The call's parameters plus the measured coverage fraction.
    """

    table: pd.DataFrame
    rule_set: pd.DataFrame
    rejected: pd.DataFrame
    budget: dict[str, float]
    params: dict[str, Any]


def _hf_candidate_grid(base_values: np.ndarray) -> tuple[np.ndarray, str]:
    """Candidate thresholds for one column: distinct values, or a fine quantile
    grid past :data:`_HF_MAX_DISTINCT_GRID`. Zero-inflated columns keep their
    candidates — distinct values handle the 78%-zeros shape without a special case.
    """
    finite = base_values[~np.isnan(base_values)]
    distinct = np.unique(finite)
    if len(distinct) <= _HF_MAX_DISTINCT_GRID:
        return distinct, "distinct"
    qs = np.linspace(0.0, 1.0, _HF_FALLBACK_GRID_POINTS + 1)
    return np.unique(np.quantile(finite, qs)), "quantile"


def _hf_column_iv(values: np.ndarray, defaults: np.ndarray, n_bins: int = 10) -> float:
    """IV of one column against ``bad_col`` via the package's own kernel — a single
    constant risk group turns ``calculate_tier_metrics`` into plain IV (#59 reuse).
    """
    valid = ~np.isnan(values) & ~np.isnan(defaults)
    v = values[valid]
    d = defaults[valid]
    if len(v) < n_bins:
        return 0.0
    metrics = calculate_tier_metrics(
        values=v.astype(np.float64),
        groups=np.ones(len(v), dtype=np.int64),
        defaults=d.astype(np.float64),
        n_bins=n_bins,
    )
    return float(metrics["iv"].iloc[0]) if len(metrics) else 0.0


def _hf_column_table(
    column: str,
    direction: str,
    base_values: np.ndarray,
    contracted_values: np.ndarray,
    contracted_bads: np.ndarray,
    base_default: float,
    iv: float,
    grid: np.ndarray,
    grid_kind: str,
) -> pd.DataFrame:
    """Standalone strategy rows for one column over the whole grid, vectorised.

    Sort once, then every threshold is a ``searchsorted`` into the sorted values and
    a slice of the ``bad_col`` cumsum — grid size costs only the sort, paid once.
    ``cut_volume`` is measured on the **base**; ``lift`` on the **contracted**.
    """
    n_base = len(base_values)
    base_sorted = np.sort(base_values[~np.isnan(base_values)])

    c_valid = ~np.isnan(contracted_values)
    cv = contracted_values[c_valid]
    cb = contracted_bads[c_valid].astype(np.float64)
    order = np.argsort(cv, kind="stable")
    cv_sorted = cv[order]
    cb_prefix = np.concatenate([[0.0], np.cumsum(cb[order])])
    n_contracted = len(cv_sorted)
    total_bads_c = cb_prefix[-1]

    if direction == "lte":  # keep <= t, reject > t
        n_rej_base = len(base_sorted) - np.searchsorted(base_sorted, grid, side="right")
        c_idx = np.searchsorted(cv_sorted, grid, side="right")
        n_rej_c = n_contracted - c_idx
        bads_rej = total_bads_c - cb_prefix[c_idx]
    else:  # gte: keep >= t, reject < t
        n_rej_base = np.searchsorted(base_sorted, grid, side="left")
        c_idx = np.searchsorted(cv_sorted, grid, side="left")
        n_rej_c = c_idx
        bads_rej = cb_prefix[c_idx]

    with np.errstate(divide="ignore", invalid="ignore"):
        default_rejected = np.where(n_rej_c > 0, bads_rej / n_rej_c, np.nan)
        lift = default_rejected / base_default if base_default > 0 else np.full(len(grid), np.nan)

    df = pd.DataFrame(
        {
            "column": column,
            "direction": direction,
            "threshold": grid.astype(float),
            "grid": grid_kind,
            "iv": iv,
            "cut_volume": n_rej_base / n_base,
            "n_rejected_base": n_rej_base,
            "n_rejected_contracted": n_rej_c,
            "bads_rejected": bads_rej,
            "default_rejected": default_rejected,
            "lift": lift,
            "base_default": base_default,
        }
    )
    # Drop degenerate cuts: rejecting nobody, or rejecting everybody on the base.
    return df[(df["n_rejected_base"] > 0) & (df["n_rejected_base"] < n_base)].reset_index(drop=True)


def _hf_rule_mask(series: pd.Series, direction: str, threshold: float) -> np.ndarray:
    """Base-level boolean: which rows this rule *rejects*. NaN never rejects
    (a NaN comparison is False), so an absent cadastral value keeps the applicant.
    """
    vals = series.to_numpy(dtype=float)
    return (vals > threshold) if direction == "lte" else (vals < threshold)


def _hf_policy_acts_on(policy: CreditPolicy, column: str) -> bool:
    """Whether any of ``policy``'s cutoff/filter stages already act on ``column`` —
    if so, the measured lift lives on a population that policy already filtered.
    """
    word = re.compile(rf"\b{re.escape(column)}\b")
    for stage in policy.stages:
        if isinstance(stage, CutoffStage) and column in stage.cutoffs:
            return True
        if isinstance(stage, FilterStage) and word.search(str(stage.condition)):
            return True
    return False


def suggest_hard_filters(
    data: pd.DataFrame,
    bad_col: str,
    directions: dict[str, str],
    hf_approval_floor: float,
    policy: CreditPolicy | None = None,
    lift_min: float = 1.5,
    iv_min: float = 0.02,
    min_rejected_bads: int = 30,
    max_rules: int = 10,
) -> HardFilterSuggestion:
    """Suggest a set of hard filters that fits an approval-rate budget.

    A hard filter is a *cheap* cadastral/scraper/client-declared variable carrying a
    bizarre default signal — "1.5x the base default rate". This is a **consultative**
    tool: the full cutoff/strategy table always comes back and the suggested set is a
    greedy (not optimal) base for the client to parametrize from, not an automated
    decision.

    **Two populations, one row.** The approval-rate budget lives on the **base** — the
    whole frame — because that is where the approval rate lives. Lift can only be
    measured where ``bad_col`` is observed, the **contracted** population, because the
    incumbent policy already removed the rest. So ``cut_volume`` is a base number and
    ``lift`` a contracted one, side by side in every row, by necessity.

    **Measurement caveat.** A real hard filter has already been rejected by the
    incumbent policy, so it can have *no* observable default rate — ``cpf_valido`` in
    ``generate_sample_data`` is 1 contracted row, 0 bads, observed lift 0.00x, despite a
    2.10x true lift. Observed lift overstates (surviving a rejecting policy makes you a
    strange survivor); an inferred-PD ``bad_col`` understates (it carries only what the
    model learned). This function measures where measurement is possible and warns when
    the measurement population is compromised — it never presents an unmeasurable column
    as a weak one. See ``prototypes/hf_suggester/README.md`` on branch
    ``prototype/hf-suggester`` for the full study.

    Args:
        data: The base — one row per applicant.
        bad_col: Any column whose mean is the bad rate: an observed 0/1 flag or an
            estimated PD column. Its NaNs define the non-contracted rows.
        directions: Declares both the candidate columns and their direction —
            ``{"vl_negativacao": "lte"}`` keeps ``<= t`` and rejects ``> t``. Spelling
            is ``lte``/``gte`` (matching ``CutoffStage``); anything else raises. There
            is no auto-detection: the HF/score boundary is economic, not statistical.
        hf_approval_floor: The approval rate the set must leave standing on the base —
            the set may never approve less than this. A floor, not a target: the set
            stops wherever ``lift_min`` and ``min_rejected_bads`` stop it. Must be in
            ``(0, 1)``.
        policy: Optional. When given, a warning fires for any candidate column one of
            its cutoff/filter stages already acts on.
        lift_min: Column floor — rejects whole columns that cannot clear it at any cut.
        iv_min: IV floor (scorecardpy ``var_filter`` convention).
        min_rejected_bads: A cut must reject at least this many bads to be trusted.
        max_rules: Cap on the size of the greedy set.

    Returns:
        A :class:`HardFilterSuggestion`.

    Raises:
        ValueError: on ``hf_approval_floor`` outside ``(0, 1)``, or a direction that is
            not ``lte``/``gte``.
    """
    if not 0.0 < hf_approval_floor < 1.0:
        raise ValueError(
            f"hf_approval_floor must be in (0, 1), got {hf_approval_floor!r}."
        )
    for column, direction in directions.items():
        if direction not in ("lte", "gte"):
            raise ValueError(
                f"direction for {column!r} must be 'lte' or 'gte', got {direction!r}."
            )

    n_base = len(data)
    bad_values = data[bad_col].to_numpy(dtype=float)
    contracted_mask = ~np.isnan(bad_values)
    n_contracted = int(contracted_mask.sum())
    coverage = n_contracted / n_base if n_base else 0.0

    if contracted_mask.any():
        base_default = float(bad_values[contracted_mask].mean())
    else:
        base_default = 0.0

    if coverage < 1.0:
        warnings.warn(
            f"'{bad_col}' is observed for {coverage:.1%} of the base; every lift is "
            f"measured among the contracted, a population the incumbent policy already "
            f"selected. See the measurement caveat in suggest_hard_filters' docstring.",
            stacklevel=2,
        )

    # --- The full standalone table, one column at a time. ---
    contracted_bads = bad_values[contracted_mask]
    tables = []
    ivs: dict[str, float] = {}
    degenerate: dict[str, str] = {}  # declared columns with no usable threshold
    for column, direction in directions.items():
        base_values = data[column].to_numpy(dtype=float)
        contracted_values = base_values[contracted_mask]
        iv = _hf_column_iv(base_values, bad_values)
        ivs[column] = iv
        grid, grid_kind = _hf_candidate_grid(base_values)
        col_table = _hf_column_table(
            column,
            direction,
            base_values,
            contracted_values,
            contracted_bads,
            base_default,
            iv,
            grid,
            grid_kind,
        )
        if col_table.empty:
            # A declared candidate with no non-degenerate cut (e.g. a constant
            # column): every threshold rejects nobody or everybody. It cannot enter
            # the table, but a declared column must still be accounted for — record
            # it as rejected rather than letting it vanish (behaviour 7).
            degenerate[column] = direction
            continue
        tables.append(col_table)

        if policy is not None and _hf_policy_acts_on(policy, column):
            warnings.warn(
                f"policy already acts on candidate column '{column}'; its measured "
                f"lift is computed on a population that policy has already filtered.",
                stacklevel=2,
            )
        # Inversion: for the declared direction, tightening the cut should *raise*
        # lift (the tail is the risky side). When lift instead rises as the cut
        # widens, the rejected tail is safer than the base — the signal inverts.
        # Report, never auto-flip (owner, 2026-07-15). Judge on trustworthy cuts
        # only, so thin high-value bins do not drive the call.
        trustworthy = col_table[col_table["bads_rejected"] >= min_rejected_bads]
        if len(trustworthy) >= 3 and trustworthy["cut_volume"].nunique() > 1:
            lifts = trustworthy["lift"].to_numpy(dtype=float)
            cuts = trustworthy["cut_volume"].to_numpy(dtype=float)
            if np.isfinite(lifts).all():
                corr = float(np.corrcoef(cuts, lifts)[0, 1])
                if corr > 0.1:
                    warnings.warn(
                        f"observed lift for '{column}' inverts against the declared "
                        f"direction '{direction}': the rejected tail is safer than the "
                        f"base (lift rises as the cut widens). Reporting, not flipping.",
                        stacklevel=2,
                    )

    table = (
        pd.concat(tables, ignore_index=True)
        if tables
        else pd.DataFrame(
            columns=[
                "column", "direction", "threshold", "grid", "iv", "cut_volume",
                "n_rejected_base", "n_rejected_contracted", "bads_rejected",
                "default_rejected", "lift", "base_default",
            ]
        )
    )

    # --- One chosen cut per column: argmax(bads avoided) among cuts clearing every
    #     column-level floor. Ranking by bads avoided (not efficiency) keeps the set
    #     small and traceable (owner, 2026-07-15). ---
    params = {
        "bad_col": bad_col,
        "directions": dict(directions),
        "hf_approval_floor": hf_approval_floor,
        "lift_min": lift_min,
        "iv_min": iv_min,
        "min_rejected_bads": min_rejected_bads,
        "max_rules": max_rules,
        "coverage": coverage,
        "base_default": base_default,
    }

    rejected_rows: list[dict[str, Any]] = []

    def _reject(row: pd.Series | None, reason: str, **fields: Any) -> None:
        entry = dict(row) if row is not None else {}
        entry.update(fields)
        entry["reason"] = reason
        rejected_rows.append(entry)

    for column, direction in degenerate.items():
        _reject(
            None,
            "no non-degenerate threshold: every cut rejects nobody or everybody",
            column=column,
            direction=direction,
        )

    candidates: dict[str, pd.Series] = {}
    for column in directions:
        col_rows = table[table["column"] == column]
        if col_rows.empty:
            continue
        iv = ivs[column]
        passing = col_rows[
            (col_rows["iv"] >= iv_min)
            & (col_rows["lift"] >= lift_min)
            & (col_rows["bads_rejected"] >= min_rejected_bads)
        ]
        if not passing.empty:
            candidates[column] = passing.loc[passing["bads_rejected"].idxmax()]
            continue
        # Rejected column — the best candidate it had, and why it lost.
        best, reason = _hf_reject_reason(col_rows, iv, iv_min, lift_min, min_rejected_bads)
        _reject(best, reason)

    # --- Greedy set under the budget. The budget belongs to the *set*: its union cut
    #     may never exceed 1 - floor, and every rule spends its *marginal* cut. ---
    budget_cut_max = 1.0 - hf_approval_floor
    rejected_base = np.zeros(n_base, dtype=bool)
    selected: list[dict[str, Any]] = []
    remaining = dict(candidates)
    # Each chosen column has one fixed threshold, so its base-rejection mask is
    # computed once here — the greedy loop only recomputes marginals against the
    # growing union, it never re-masks the frame per step.
    candidate_masks = {
        column: _hf_rule_mask(data[column], row["direction"], float(row["threshold"]))
        for column, row in candidates.items()
    }

    while remaining and len(selected) < max_rules:
        scored = []
        for column, row in remaining.items():
            newly = candidate_masks[column] & ~rejected_base
            newly_c = newly & contracted_mask
            scored.append(
                (
                    float(bad_values[newly_c].sum()),  # marginal bads avoided
                    column,
                    row,
                    float(newly.mean()),  # marginal cut on the base
                )
            )
        marg_bads, column, row, marg_cut = max(scored, key=lambda s: s[0])

        if rejected_base.mean() + marg_cut > budget_cut_max + 1e-12:
            # Clears the floors but not the remaining budget: reject on budget, never
            # silently cut to fit. A smaller candidate may still fit, so keep going.
            _reject(
                row,
                f"marginal cut {marg_cut:.1%} exceeds remaining budget "
                f"{budget_cut_max - rejected_base.mean():.1%}",
            )
            del remaining[column]
            continue

        rejected_base |= candidate_masks[column] & ~rejected_base
        selected.append(
            {
                "column": column,
                "direction": row["direction"],
                "threshold": float(row["threshold"]),
                "iv": float(row["iv"]),
                "lift": float(row["lift"]),
                "bads_rejected": float(row["bads_rejected"]),
                "n_rejected_contracted": int(row["n_rejected_contracted"]),
                "cut_volume": float(row["cut_volume"]),
                "marginal_cut": marg_cut,
                "cumulative_cut": float(rejected_base.mean()),
            }
        )
        del remaining[column]

    # Any candidate still standing when max_rules is hit is rejected on the cap.
    for column, row in remaining.items():
        _reject(row, f"max_rules ({max_rules}) reached")

    rule_set = pd.DataFrame(
        selected,
        columns=[
            "column", "direction", "threshold", "iv", "lift", "bads_rejected",
            "n_rejected_contracted", "cut_volume", "marginal_cut", "cumulative_cut",
        ],
    )
    rejected = pd.DataFrame(rejected_rows)

    union_cut = float(rejected_base.mean())
    approval_rate = 1.0 - union_cut
    budget = {
        "floor": hf_approval_floor,
        "spent": union_cut,
        "approval_rate": approval_rate,
        "headroom": approval_rate - hf_approval_floor,
    }

    return HardFilterSuggestion(
        table=table, rule_set=rule_set, rejected=rejected, budget=budget, params=params
    )


def _hf_reject_reason(
    col_rows: pd.DataFrame,
    iv: float,
    iv_min: float,
    lift_min: float,
    min_rejected_bads: int,
) -> tuple[pd.Series, str]:
    """Best candidate for a rejected column and the reason it lost, in the order
    IV → min-bads → lift, so the report names the first floor the column cannot clear.
    """
    if iv < iv_min:
        best = col_rows.loc[col_rows["bads_rejected"].idxmax()]
        return best, f"IV {iv:.3f} < {iv_min}"

    solid = col_rows[col_rows["bads_rejected"] >= min_rejected_bads]
    if solid.empty:
        best = col_rows.loc[col_rows["bads_rejected"].idxmax()]
        return best, f"{int(best['bads_rejected'])} bads rejected < {min_rejected_bads}"

    best = solid.loc[solid["lift"].idxmax()]
    return best, f"lift {best['lift']:.2f}x < {lift_min}x"


def screen_risk_segments(*args, **kwargs) -> ScreeningResult:
    """Deprecated alias for fit_risk_segments."""
    warnings.warn(
        "screen_risk_segments is deprecated and will be removed in a future version. "
        "Use fit_risk_segments instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return fit_risk_segments(*args, **kwargs)

