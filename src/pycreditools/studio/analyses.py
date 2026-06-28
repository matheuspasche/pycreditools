"""Analysis orchestration: thin wrappers over `pycreditools` returning plain data.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import dataclasses
import json
import string
from typing import Any

import numpy as np
import pandas as pd

from pycreditools import (
    CreditPolicy,
    CreditSimResults,
    CutoffStage,
    DeploymentPolicy,
    ModelEvaluator,
    OptimizationResult,
    RiskGroupResult,
    TradeoffAnalyzer,
    compare_policies,
    fit_pairwise_risk_groups,
    fit_risk_groups,
    optimize_cutoffs,
    summarize_results,
)

from .models import ColumnRoles, StudioState

# Absolute PD gap (in DEV vs OOT) above which a tier is flagged as unstable.
RATING_STABILITY_THRESHOLD = 0.02


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


# Owner rule (ADR 0005): after KS, only 2-3 of the candidate scores are worth the
# downstream compute (Bancada suggestions, complementarity); the rest stay out.
MAX_SCORES_EM_JOGO = 3


def select_scores_em_jogo(
    candidates: list[str], available: list[str], max_count: int = MAX_SCORES_EM_JOGO
) -> tuple[list[str], str | None]:
    """Apply the "scores em jogo" short-list rule (ADR 0005) to a raw selection.

    Dedupes, drops names not in `available` (e.g. stale from a previous dataset), and
    caps at `max_count`, keeping the first `max_count` valid candidates in order.
    Returns the resulting selection plus a pt-BR warning when the cap was applied.
    """
    valid = [c for c in dict.fromkeys(candidates) if c in available]
    if len(valid) > max_count:
        kept = valid[:max_count]
        warning = (
            f"Selecione no máximo {max_count} scores em jogo; mantidos os primeiros "
            f"{max_count}: {', '.join(kept)}."
        )
        return kept, warning
    return valid, None


def get_scores_em_jogo(state: StudioState) -> list[str]:
    """The persisted "scores em jogo" short-list (ADR 0005), filtered to scores still
    present in the current roles — the set downstream slices (Bancada, suggestions,
    complementarity) should read.
    """
    return [s for s in state.scores_em_jogo if s in state.roles.score_cols]


# ADR 0004: a new score usually enters matriciated with the vigente score, so the
# owner must judge complementarity, not isolated KS. Verdict thresholds:
# - a marginal lift at or above LIFT_SIGNIFICANT means the candidate adds real
#   discriminatory power on top of the reference, worth matriciating;
# - below that, a highly correlated (>= CORRELATION_HIGH) and clearly stronger
#   candidate means the reference adds nothing the candidate doesn't already
#   capture, so replacing it is simpler than keeping both;
# - otherwise the candidate is only a marginal, partially-redundant complement,
#   best used as a secondary repechage filter rather than a full swap or matrix.
COMPLEMENTARITY_CORRELATION_HIGH = 0.7
COMPLEMENTARITY_LIFT_SIGNIFICANT = 0.02


def combined_ks(
    df: pd.DataFrame, candidate_score: str, reference_score: str, target_col: str
) -> float:
    """KS of the rank-average ensemble of `candidate_score` + `reference_score`.

    A model-free combination (average percentile rank, not fit against
    `target_col`) so the result reflects genuine joint discriminatory power rather
    than a value inflated by fitting risk-grouping cells to the very labels being
    scored. The KS itself is computed by `ModelEvaluator.compute_ks()`.
    """
    ensemble = df[[candidate_score, reference_score]].rank(pct=True).sum(axis=1)
    working = df[[target_col]].copy()
    working["_ensemble"] = ensemble
    return ModelEvaluator(working, ["_ensemble"], target_col).compute_ks()["_ensemble"]


def complementarity_verdict(
    correlation: float, marginal_lift: float, ks_candidate: float, ks_reference: float
) -> str:
    """The ADR 0004 verdict hint (repechar / matriciar / substituir); see thresholds above."""
    if marginal_lift >= COMPLEMENTARITY_LIFT_SIGNIFICANT:
        return "matriciar"
    if correlation >= COMPLEMENTARITY_CORRELATION_HIGH and ks_candidate > ks_reference:
        return "substituir"
    return "repechar"


def compute_complementarity(
    df: pd.DataFrame, candidate_score: str, reference_score: str, target_col: str
) -> dict[str, float | str]:
    """Correlation, isolated vs combined KS, marginal lift, and a verdict hint (ADR 0004)
    for `candidate_score` vs `reference_score` (the vigente/in-use score)."""
    ks_values = evaluate_scores(df, [candidate_score, reference_score], target_col)
    correlation = float(df[[candidate_score, reference_score]].corr().iloc[0, 1])
    ks_pair = combined_ks(df, candidate_score, reference_score, target_col)
    marginal_lift = ks_pair - ks_values[reference_score]
    verdict = complementarity_verdict(
        correlation, marginal_lift, ks_values[candidate_score], ks_values[reference_score]
    )
    return {
        "candidate_score": candidate_score,
        "reference_score": reference_score,
        "correlation": correlation,
        "ks_candidate": ks_values[candidate_score],
        "ks_reference": ks_values[reference_score],
        "ks_combined": ks_pair,
        "marginal_lift": marginal_lift,
        "verdict": verdict,
    }


def complementarity_table(
    df: pd.DataFrame, candidate_scores: list[str], reference_score: str, target_col: str
) -> pd.DataFrame:
    """One row per `candidate_scores` (excluding `reference_score`) vs `reference_score`."""
    columns = [
        "candidate_score",
        "reference_score",
        "correlation",
        "ks_candidate",
        "ks_reference",
        "ks_combined",
        "marginal_lift",
        "verdict",
    ]
    rows = [
        compute_complementarity(df, candidate, reference_score, target_col)
        for candidate in candidate_scores
        if candidate != reference_score
    ]
    return pd.DataFrame(rows, columns=columns)


def resolve_reference_score(
    roles: ColumnRoles, ks_ranking: dict[str, float] | pd.Series
) -> str | None:
    """The complementarity reference (ADR 0004): `vigente_score` when set and still
    ranked, else the current KS champion (the contextual in-use score)."""
    ranking = ks_ranking.to_dict() if isinstance(ks_ranking, pd.Series) else dict(ks_ranking)
    if roles.vigente_score and roles.vigente_score in ranking:
        return roles.vigente_score
    if not ranking:
        return None
    return max(ranking, key=ranking.get)


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


def run_crash_test(
    df: pd.DataFrame,
    policy: CreditPolicy,
    factors: list[float],
    *,
    parallel: bool = False,
) -> pd.DataFrame:
    """Sweep the flat stress aggravation factor, via `TradeoffAnalyzer.vary_stress_aggravation()`.

    Reproduces v14 Cell 13: the result has `aggravation_factor`/`approval_rate`/`default_rate`.
    """
    return TradeoffAnalyzer(policy).vary_stress_aggravation(factors).run(df, parallel=parallel)


def breakeven_aggravation_factor(
    crash_df: pd.DataFrame, legacy_bad_rate: float
) -> float | None:
    """First `aggravation_factor` whose `default_rate` reaches `legacy_bad_rate`.

    Linearly interpolated between the bracketing rows for a smoother number; `None`
    when `default_rate` never reaches `legacy_bad_rate` within `crash_df`'s range.
    """
    ordered = crash_df.sort_values("aggravation_factor").reset_index(drop=True)
    reached = ordered.index[ordered["default_rate"] >= legacy_bad_rate]
    if len(reached) == 0:
        return None
    idx = reached[0]
    if idx == 0:
        return float(ordered.loc[0, "aggravation_factor"])
    prev, curr = ordered.loc[idx - 1], ordered.loc[idx]
    rate_gap = curr["default_rate"] - prev["default_rate"]
    if rate_gap <= 0:
        return float(curr["aggravation_factor"])
    frac = (legacy_bad_rate - prev["default_rate"]) / rate_gap
    factor_gap = curr["aggravation_factor"] - prev["aggravation_factor"]
    return float(prev["aggravation_factor"] + frac * factor_gap)


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


def optimization_grid_size(score_cols: list[str] | tuple[str, ...], cutoff_steps: int) -> int:
    """Total grid combinations `optimize_cutoffs` evaluates: `cutoff_steps ** len(score_cols)`."""
    return cutoff_steps ** len(score_cols)


def run_optimization(
    df: pd.DataFrame,
    policy: CreditPolicy,
    *,
    cutoff_steps: int = 10,
    target_default_rate: float = 0.05,
    min_approval_rate: float = 0.3,
    method: str = "analytical",
    parallel: bool = False,
    percentiles: tuple[float, float] | None = (0.05, 0.95),
    cutoff_ranges: dict[str, list[float]] | None = None,
) -> OptimizationResult:
    """Grid-search `policy.score_cols`' cutoffs, via `optimize_cutoffs()`."""
    return optimize_cutoffs(
        df,
        policy,
        cutoff_steps=cutoff_steps,
        target_default_rate=target_default_rate,
        min_approval_rate=min_approval_rate,
        method=method,
        parallel=parallel,
        percentiles=percentiles,
        cutoff_ranges=cutoff_ranges,
    )


def find_equivalent(
    result: OptimizationResult,
    target_metric: str = "approval_rate",
    target_value: float = 0.20,
    tolerance: float = 0.01,
) -> pd.DataFrame:
    """Grid combinations matching `target_value`, via `OptimizationResult.find_equivalent()`."""
    return result.find_equivalent(
        target_metric=target_metric, target_value=target_value, tolerance=tolerance
    )


def clamp_max_groups(max_groups: int, bins: int) -> int:
    """Clamp `max_groups` so it never exceeds `bins` (`fit_risk_groups` otherwise raises)."""
    return min(max_groups, bins)


def fit_groups(
    df: pd.DataFrame,
    score_cols: list[str],
    default_col: str,
    *,
    bins: int = 20,
    max_groups: int | None = None,
    min_vol_ratio: float = 0.05,
    max_crossings: int = 1,
    time_col: str | None = None,
    method: str = "ward",
    oot_date: Any | None = None,
) -> RiskGroupResult:
    """Cluster `score_cols` into stable risk groups, via `fit_risk_groups()`."""
    if max_groups is not None:
        max_groups = clamp_max_groups(max_groups, bins)
    return fit_risk_groups(
        df,
        score_cols,
        default_col,
        bins=bins,
        max_groups=max_groups,
        min_vol_ratio=min_vol_ratio,
        max_crossings=max_crossings,
        time_col=time_col,
        method=method,
        oot_date=oot_date,
    )


def fit_pairwise_groups(
    df: pd.DataFrame,
    primary_score: str,
    challenger_scores: list[str],
    default_col: str,
    *,
    bins: int = 20,
    max_groups: int | None = None,
    min_vol_ratio: float = 0.05,
    max_crossings: int = 1,
    time_col: str | None = None,
    method: str = "ward",
    oot_date: Any | None = None,
) -> dict[str, RiskGroupResult]:
    """Primary vs each challenger score, via `fit_pairwise_risk_groups()`."""
    if max_groups is not None:
        max_groups = clamp_max_groups(max_groups, bins)
    return fit_pairwise_risk_groups(
        df,
        primary_score,
        challenger_scores,
        default_col,
        time_col=time_col,
        bins=bins,
        max_groups=max_groups,
        min_vol_ratio=min_vol_ratio,
        max_crossings=max_crossings,
        method=method,
        oot_date=oot_date,
    )


def label_ratings_by_pd(result: RiskGroupResult, default_col: str) -> dict[int, str]:
    """Map each numeric `risk_rating` cluster id to a letter (A = lowest mean PD)."""
    cluster_pd = result.data.groupby("risk_rating")[default_col].mean().sort_values()
    letters = string.ascii_uppercase
    return {
        int(cluster_id): letters[i] if i < len(letters) else str(i)
        for i, cluster_id in enumerate(cluster_pd.index)
    }


def groups_table(result: RiskGroupResult, labels: dict[int, str] | None) -> pd.DataFrame:
    """`result.groups` with `risk_rating` relabeled to `Rating` (A..E), sorted ascending."""
    table = result.groups.copy()
    table["Rating"] = (
        table["risk_rating"].map(labels) if labels else table["risk_rating"].astype(str)
    )
    return table.drop(columns="risk_rating").sort_values("Rating").reset_index(drop=True)[
        ["Rating", "volume", "pd"]
    ]


def stability_table(result: RiskGroupResult, labels: dict[int, str] | None) -> pd.DataFrame:
    """DEV vs OOT volume/PD per tier (from `result.report`), flagging tiers that diverge.

    Empty when `result.report` has no OOT split (no `time_col`/`oot_date` was given).
    """
    report = result.report
    if report is None or report.empty:
        return pd.DataFrame()
    df = report.copy()
    df["Rating"] = df["risk_rating"].map(labels) if labels else df["risk_rating"].astype(str)

    volume = df.pivot_table(index="Rating", columns="period", values="volume", aggfunc="sum")
    volume.columns = [f"Volume_{c}" for c in volume.columns]
    pd_rate = df.pivot_table(index="Rating", columns="period", values="pd", aggfunc="mean")
    pd_rate.columns = [f"PD_{c}" for c in pd_rate.columns]
    out = volume.join(pd_rate).reset_index()

    if "PD_Train" in out.columns and "PD_OOT" in out.columns:
        out["PD_Delta"] = out["PD_OOT"] - out["PD_Train"]
        out["Diverge"] = out["PD_Delta"].abs() > RATING_STABILITY_THRESHOLD
    return out.sort_values("Rating").reset_index(drop=True)


def vintage_stability_table(
    result: RiskGroupResult,
    time_col: str,
    default_col: str,
    labels: dict[int, str] | None,
) -> pd.DataFrame:
    """Mean `default_col` per `(time_col, Rating)` from `result.data` — the vintage chart's data."""
    df = result.data
    if time_col not in df.columns:
        return pd.DataFrame()
    work = df.copy()
    work["Rating"] = work["risk_rating"].map(labels) if labels else work["risk_rating"].astype(str)
    grouped = (
        work.groupby([time_col, "Rating"])[default_col]
        .mean()
        .reset_index()
        .rename(columns={default_col: "bad_rate"})
    )
    return grouped.sort_values([time_col, "Rating"]).reset_index(drop=True)


def recipe_breaks_table(result: RiskGroupResult, labels: dict[int, str] | None) -> pd.DataFrame:
    """Score range(s) mapped to each tier, decoded from `result.recipe`'s quantile breaks.

    One row per tier with `{score}_min`/`{score}_max` columns (one pair per score in
    `recipe.score_cols`; multivariate grouping combines bins from every score).
    """
    recipe = result.recipe
    if not recipe.quantile_breaks or not recipe.cluster_mapping:
        return pd.DataFrame()

    rows = []
    for combo_key, cluster_id in recipe.cluster_mapping.items():
        row: dict[str, Any] = {"risk_rating": cluster_id}
        for score_col, bin_idx in zip(recipe.score_cols, combo_key.split("-")):
            breaks = recipe.quantile_breaks[score_col]
            bin_idx = int(bin_idx)
            row[f"{score_col}_min"] = breaks[bin_idx]
            row[f"{score_col}_max"] = breaks[bin_idx + 1]
        rows.append(row)

    df = pd.DataFrame(rows)
    agg = {
        col: (col, "min" if col.endswith("_min") else "max")
        for col in df.columns
        if col != "risk_rating"
    }
    out = df.groupby("risk_rating").agg(**agg).reset_index()
    out["Rating"] = out["risk_rating"].map(labels) if labels else out["risk_rating"].astype(str)
    return out.drop(columns="risk_rating").sort_values("Rating").reset_index(drop=True)


def deployment_cache_key(dep: DeploymentPolicy) -> str:
    """A stable, hashable cache key for a `DeploymentPolicy` (its serialized `to_dict()`)."""
    return json.dumps(dep.to_dict(), sort_keys=True, default=str)


def deployment_mocked_columns(dep: DeploymentPolicy, df: pd.DataFrame) -> list[str]:
    """Columns `DeploymentPolicy.predict()` will auto-mock because `df` lacks them."""
    policy = dep.policy
    candidates = [policy.applicant_id_col, policy.current_approval_col, policy.actual_default_col]
    return [c for c in candidates if c and c not in df.columns]


def score_batch(
    df: pd.DataFrame, dep: DeploymentPolicy, *, simple: bool = True, method: str = "analytical"
) -> pd.DataFrame:
    """Batch-score `df` through a deployment policy, via `DeploymentPolicy.predict()`."""
    return dep.predict(df, simple=simple, method=method)


def scoring_kpis(scored: pd.DataFrame, decision_col: str = "decision") -> dict[str, float]:
    """Total scored rows and approval rate, from a `simple=True` scored frame."""
    total = len(scored)
    approval_rate = (
        float((scored[decision_col] == "Approved").mean())
        if total and decision_col in scored.columns
        else 0.0
    )
    return {"total": total, "approval_rate": approval_rate}


def rating_distribution(scored: pd.DataFrame, rating_col: str = "rating") -> pd.Series:
    """Volume per rating tier from a scored frame, for `charts.bars(risk_colors=True)`."""
    if rating_col not in scored.columns:
        return pd.Series(dtype=float)
    return scored[rating_col].value_counts(dropna=True)


def rejection_reasons(scored: pd.DataFrame, reason_col: str = "reason") -> pd.DataFrame:
    """`reason` value counts (rejection breakdown), sorted by volume descending."""
    if reason_col not in scored.columns:
        return pd.DataFrame(columns=[reason_col, "volume"])
    counts = scored[reason_col].value_counts(dropna=False).reset_index()
    counts.columns = [reason_col, "volume"]
    return counts.sort_values("volume", ascending=False).reset_index(drop=True)


