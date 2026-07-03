"""Analysis orchestration: thin wrappers over `pycreditools` returning plain data.

No `streamlit` import allowed here — see `00-overview.md` §4b. Caching (`@st.cache_data`)
wraps these functions in the `gui/` skin, not here.
"""

from __future__ import annotations

import dataclasses
import json
import string
import warnings
from typing import Any

import numpy as np
import pandas as pd

from pycreditools import (
    CreditPolicy,
    CreditSimResults,
    CutoffStage,
    DeploymentPolicy,
    GroupingRecipe,
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

from .models import ColumnRoles, OpenMatrix, PolicyScenario, StudioState
from .policy_builder import build_policy, segment_cutoff_rows

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


def survivor_population(sim: CreditSimResults) -> pd.DataFrame:
    """Rows that passed every hard filter/cutoff of the live policy (ADR 0001).

    This is "whoever survives the filters" — the population risk clustering and
    other downstream readouts must use, instead of the raw base. Independent of
    any rate stage (take-up): a row counts as a survivor once it clears the last
    filter/cutoff, even before the take-up draw decides if it is hired.
    """
    return sim.data[sim.data["reason"] == "Approved"]


# Minimum number of survivors with an observed default required before we attempt
# a fresh risk-group fit (too few rows → unstable clusters).
_SURVIVOR_REFIT_MIN_VOLUME = 30


def derive_survivor_rating(
    sim: CreditSimResults,
    roles: ColumnRoles,
    *,
    bins: int = 10,
    max_groups: int = 5,
    min_vol_ratio: float = 0.02,
) -> RiskGroupResult | None:
    """Re-derive the risk grouping over the survivors of `sim` (ADR 0007, issue #39).

    Called after every Bancada simulation so the risk readouts always reflect the
    population that actually survived the current filters — never the static recipe
    from the Risk Grouping page. Returns None when preconditions are unmet (no
    default col, no score cols, too few survivors with observed defaults, or if
    the clustering engine raises).
    """
    default_col = roles.actual_default_col
    score_cols = [c for c in (roles.score_cols or []) if c]
    if not default_col or not score_cols:
        return None

    survivors = survivor_population(sim)
    if survivors.empty:
        return None

    with_defaults = survivors.dropna(subset=[default_col])
    if len(with_defaults) < _SURVIVOR_REFIT_MIN_VOLUME:
        return None

    present_scores = [c for c in score_cols if c in with_defaults.columns]
    if not present_scores:
        return None

    try:
        return fit_groups(
            with_defaults,
            present_scores,
            default_col,
            bins=bins,
            max_groups=max_groups,
            min_vol_ratio=min_vol_ratio,
        )
    except Exception:  # noqa: BLE001
        return None


def _candidate_outcome(data: pd.DataFrame) -> dict[str, float | None]:
    """Candidate approval rate + (if observed) simulated bad rate over `data`'s rows."""
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


def policy_kpis(sim: CreditSimResults) -> dict[str, float | None]:
    """Final approval rate, approved/hired volume, and (if observed) the simulated bad rate."""
    data = sim.data
    outcome = _candidate_outcome(data)
    pre_rate_volume = (
        float(data["approved_pre_rate"].sum()) if "approved_pre_rate" in data.columns else None
    )
    return {**outcome, "pre_rate_volume": pre_rate_volume}


# ── Light business segmentation — cutoffs per segment (ADR 0006, issue #34) ────


def run_segmented_sim(
    df: pd.DataFrame,
    roles: ColumnRoles,
    rows: list[dict[str, Any]],
    score_col: str,
    segment_cutoffs: dict[str, float],
    *,
    direction: str = "gte",
    method: str = "analytical",
) -> dict[str, CreditSimResults]:
    """Simulate each segment value's own cutoff variant on its own slice of `df`
    (ADR 0006). `roles.segment_col` selects the slice; `segment_cutoff_rows` swaps in
    each segment's `score_col` cutoff value while every other rule row stays shared.
    """
    if not roles.segment_col:
        raise ValueError("roles.segment_col não está mapeado.")
    variants = segment_cutoff_rows(rows, score_col, segment_cutoffs, direction)
    return {
        segment_value: build_policy(roles, segment_rows).simulate(
            df[df[roles.segment_col] == segment_value], method=method
        )
        for segment_value, segment_rows in variants.items()
    }


def aggregate_funnel(funnels: list[pd.DataFrame]) -> pd.DataFrame:
    """Sum per-stage `Candidates`/`Passed`/`Rejections` across segment funnels and
    recompute the rate columns from those sums (ADR 0006) — the Bancada's "aggregate
    total" alongside the per-segment breakout. Stage order/names follow the first
    funnel (every segment shares the same rule rows, so stages line up 1:1).
    """
    columns = [
        "Stage", "Candidates", "Passed", "Stage_Pass_Rate", "Cum_Pass_Rate",
        "Rejections", "Stage_Rej_Rate",
    ]
    if not funnels:
        return pd.DataFrame(columns=columns)

    stage_order = funnels[0]["Stage"].tolist()
    combined = pd.concat(funnels, ignore_index=True)
    summed = (
        combined.groupby("Stage", sort=False)[["Candidates", "Passed", "Rejections"]]
        .sum()
        .reindex(stage_order)
        .reset_index()
    )
    total_candidates = summed.loc[summed["Stage"] == "Total", "Candidates"]
    if total_candidates.empty:
        warnings.warn(
            "Etapa 'Total' ausente do funil agregado — provavelmente um segmento sem dados. "
            "Funil agregado não disponível.",
            UserWarning,
            stacklevel=2,
        )
        return pd.DataFrame(columns=columns)
    n_total = float(total_candidates.iloc[0])
    summed["Stage_Pass_Rate"] = summed["Passed"] / summed["Candidates"]
    summed["Stage_Rej_Rate"] = summed["Rejections"] / summed["Candidates"]
    no_stage_rate = summed["Stage"].isin(["Total", "Approved"])
    summed.loc[no_stage_rate, ["Stage_Pass_Rate", "Stage_Rej_Rate"]] = np.nan
    summed["Cum_Pass_Rate"] = summed["Passed"] / n_total if n_total > 0 else 0.0
    return summed[columns]


def segment_kpi_table(sims: dict[str, CreditSimResults]) -> pd.DataFrame:
    """Per-segment approval/bad-rate breakout (ADR 0006): one row per segment value,
    each segment's own `policy_kpis` over its own cutoff variant and data slice.
    """
    rows = [{"segment": segment, **policy_kpis(sim)} for segment, sim in sims.items()]
    columns = ["segment", "approval_rate", "approved_volume", "bad_rate", "pre_rate_volume"]
    return pd.DataFrame(rows, columns=columns)


def aggregate_segment_kpis(sims: dict[str, CreditSimResults]) -> dict[str, float | None]:
    """Approval/bad-rate KPIs over every segment's combined data (ADR 0006) — the
    Bancada's "aggregate total" companion to `segment_kpi_table`'s breakout.
    """
    combined = pd.concat([sim.data for sim in sims.values()], ignore_index=True)
    outcome = _candidate_outcome(combined)
    pre_rate_volume = (
        float(combined["approved_pre_rate"].sum())
        if "approved_pre_rate" in combined.columns
        else None
    )
    return {**outcome, "pre_rate_volume": pre_rate_volume}


def evaluate_scores(df: pd.DataFrame, score_cols: list[str], target_col: str) -> dict[str, float]:
    """KS statistic per score, via `ModelEvaluator.compute_ks()`."""
    return ModelEvaluator(df, score_cols, target_col).compute_ks()


def ks_table(df: pd.DataFrame, score_col: str, target_col: str, bins: int = 10) -> pd.DataFrame:
    """Per-bucket KS/bad-rate table for one score, via `ModelEvaluator.compute_ks_table()`."""
    return ModelEvaluator(df, [score_col], target_col).compute_ks_table(score_col, bins)


# Owner rule (ADR 0005): after KS, only 2-3 of the candidate scores are worth the
# downstream compute (Bancada suggestions, complementarity); the rest stay out.
MAX_SHORTLISTED_SCORES = 3


def select_shortlisted_scores(
    candidates: list[str], available: list[str], max_count: int = MAX_SHORTLISTED_SCORES
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


def get_shortlisted_scores(state: StudioState) -> list[str]:
    """The persisted shortlisted scores (ADR 0005), filtered to scores still
    present in the current roles — the set downstream slices (Bancada, suggestions,
    complementarity) should read.
    """
    return [s for s in state.shortlisted_scores if s in state.roles.score_cols]


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


def _base_outcome(data: pd.DataFrame, roles: ColumnRoles) -> dict[str, float | None] | None:
    """Vigente (historical) approval rate + observed bad rate over `data`'s rows.
    `None` when no base is mapped (Tier C) or the mapped column is absent from `data`.
    """
    if not roles.current_approval_col or roles.current_approval_col not in data.columns:
        return None
    raw = data[roles.current_approval_col]
    if raw.dtype == object or not raw.dropna().isin([0, 1]).all():
        warnings.warn(
            f"Coluna de aprovação '{roles.current_approval_col}' contém valores fora de {{0, 1}}. "
            "Taxa da base não calculada — revise o encoding da coluna de aprovação.",
            UserWarning,
            stacklevel=2,
        )
        return None
    approval_col = raw.fillna(0)
    approval_rate = float(approval_col.mean())
    bad_rate = None
    if roles.actual_default_col and roles.actual_default_col in data.columns:
        observed = data.loc[approval_col == 1, roles.actual_default_col]
        if observed.notna().any():
            bad_rate = float(observed.mean())
    return {"approval_rate": approval_rate, "bad_rate": bad_rate}


def base_outcome(sim: CreditSimResults, roles: ColumnRoles) -> dict[str, float | None] | None:
    """Vigente (historical) approval rate + observed bad rate, read straight off
    `sim.data`'s approval flag and actual default (ADR 0002 Tier A/B) — no rule
    reconstruction, no second simulation. `None` when no base is mapped (Tier C),
    signalling the caller to hide the comparison-vs-base readout entirely.
    """
    return _base_outcome(sim.data, roles)


def compare_vs_base(
    sim: CreditSimResults, roles: ColumnRoles, tier: str
) -> dict[str, Any]:
    """The Bancada's comparison-vs-base readout (ADR 0001 bullets 5-7, ADR 0002),
    tier-adapted.

    Tier A/B (`current_approval_col` mapped): the candidate's approval/default
    rate delta vs the vigente decision (`base_outcome`), plus the
    swap-in/out/keep-in/keep-out breakdown via the engine's existing swap
    classification (`quadrant_table`) — neither is reimplemented here.
    Tier C (no base): no delta, no quadrants — only the candidate's standalone
    result, whose PD comes from `estimated_default_col`.
    """
    candidate = policy_kpis(sim)
    if tier == "C":
        return {
            "tier": tier,
            "candidate": candidate,
            "base": None,
            "delta": None,
            "quadrants": None,
        }

    base = base_outcome(sim, roles)
    if base is None:
        return {
            "tier": tier,
            "candidate": candidate,
            "base": None,
            "delta": None,
            "quadrants": quadrant_table(sim),
        }
    bad_delta = (
        candidate["bad_rate"] - base["bad_rate"]
        if candidate["bad_rate"] is not None and base["bad_rate"] is not None
        else None
    )
    delta = {
        "approval_rate": candidate["approval_rate"] - base["approval_rate"],
        "bad_rate": bad_delta,
    }
    return {
        "tier": tier,
        "candidate": candidate,
        "base": base,
        "delta": delta,
        "quadrants": quadrant_table(sim),
    }


def risk_tier_distribution(
    sim: CreditSimResults,
    rating_result: RiskGroupResult | None,
    rating_labels: dict[int, str] | None,
    rating_col: str = "Rating",
) -> pd.DataFrame:
    """Volume + bad-rate per rating tier x swap group (issue #33 depth): swap-in/out
    and keep-in, using the rating recipe from Risk Grouping (ADR 0004) over the
    engine's own swap classification (`summarize_results`, grouped by `rating_col`)
    — no swap/bad-rate math is reimplemented here.

    Empty (with the expected columns) when no rating result is fitted yet, or the
    simulation has no base mapped (Tier C, no swap scenarios to break down) — the
    caller shows a friendly pt-BR note in either case instead of crashing.
    """
    columns = [rating_col, "scenario", "Applicants", "Approved", "Hired", "Bad_Rate"]
    if rating_result is None or sim.metadata["policy"].get("current_approval_col") is None:
        return pd.DataFrame(columns=columns)

    attached = attach_rating(sim.data, rating_result, rating_labels, rating_col=rating_col)
    sim_with_rating = dataclasses.replace(sim, data=attached)
    table = summarize_results(sim_with_rating, by=rating_col)
    relevant = table[table["scenario"].isin(("swap_in", "swap_out", "keep_in"))]
    return relevant.sort_values([rating_col, "scenario"]).reset_index(drop=True)


def policy_vintage_comparison(sim: CreditSimResults, roles: ColumnRoles) -> pd.DataFrame:
    """Candidate vs. base approval/default evolution by vintage (issue #33 depth):
    the same `(time_col, mean)` grouping the engine's vintage-stability primitive
    (`plot_vintage_stability`) uses for ratings, applied instead to the candidate's
    outcome and, when a base is mapped (Tier A/B), the vigente outcome — so the
    Bancada can chart how the two decisions diverge over time.

    Empty when `roles.time_col` is unset or absent from `sim.data`.
    """
    time_col = roles.time_col
    data = sim.data
    columns = [time_col or "period", "series", "approval_rate", "bad_rate"]
    if not time_col or time_col not in data.columns:
        return pd.DataFrame(columns=columns)

    rows = []
    for period, group in data.groupby(time_col):
        candidate = _candidate_outcome(group)
        rows.append(
            {
                time_col: period,
                "series": "candidate",
                "approval_rate": candidate["approval_rate"],
                "bad_rate": candidate["bad_rate"],
            }
        )
        base = _base_outcome(group, roles)
        if base is not None:
            rows.append(
                {
                    time_col: period,
                    "series": "base",
                    "approval_rate": base["approval_rate"],
                    "bad_rate": base["bad_rate"],
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values([time_col, "series"]).reset_index(
        drop=True
    )


def exposure_kpis(
    sim: CreditSimResults,
    roles: ColumnRoles,
    tier: str,
    *,
    comparison: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    """Risk-exposure KPI (issue #33 depth): the candidate's expected bad volume
    (`bad_rate x approved_volume`, already computed by `policy_kpis` — no new math),
    plus the base's for Tier A/B so the delta reads as one clear exposure number
    instead of two separate rates. `base_bad_volume`/`delta` stay `None` in Tier C.

    Pass `comparison` (the result of `compare_vs_base`) to reuse already-computed
    candidate/base KPIs and avoid a redundant `policy_kpis`/`base_outcome` call.
    """
    if comparison is not None:
        candidate = comparison["candidate"]
        precomputed_base = comparison.get("base")
    else:
        candidate = policy_kpis(sim)
        precomputed_base = None

    candidate_bad_volume = (
        candidate["bad_rate"] * candidate["approved_volume"]
        if candidate["bad_rate"] is not None
        else None
    )
    result: dict[str, float | None] = {
        "candidate_bad_volume": candidate_bad_volume,
        "base_bad_volume": None,
        "delta": None,
    }
    if tier == "C":
        return result

    base = precomputed_base if comparison is not None else base_outcome(sim, roles)
    if base is None or base["bad_rate"] is None or not roles.current_approval_col:
        return result
    base_volume = float(sim.data[roles.current_approval_col].fillna(0).sum())
    base_bad_volume = base["bad_rate"] * base_volume
    result["base_bad_volume"] = base_bad_volume
    if candidate_bad_volume is not None:
        result["delta"] = candidate_bad_volume - base_bad_volume
    return result


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


def current_cutoff_value(policy: CreditPolicy, score_col: str) -> float | None:
    """The cutoff `policy` currently applies to `score_col`, or `None` if unset."""
    for stage in policy.stages:
        if isinstance(stage, CutoffStage) and score_col in stage.cutoffs:
            return float(stage.cutoffs[score_col])
    return None


def tradeoff_curve_for_score_in_use(
    df: pd.DataFrame, policy: CreditPolicy, score_col: str, steps: int = 25
) -> pd.DataFrame:
    """The Bancada's live "drag the cutoff" trade-off curve (ADR 0001, critique 2.3).

    Sweeps `score_col`'s cutoff via `cutoff_range` + `run_tradeoff` (no separate page,
    no reimplemented sweep) and flags the row closest to `policy`'s currently applied
    cutoff for `score_col` as `is_current` — the point the chart highlights as the
    user drags the slider. No row is flagged when `score_col` has no active cutoff.
    """
    values = cutoff_range(df, score_col, steps)
    result = run_tradeoff(df, policy, score_col, values)
    result["is_current"] = False
    current = current_cutoff_value(policy, score_col)
    if current is not None and not result.empty:
        idx = (result["Cutoff"] - current).abs().idxmin()
        result.loc[idx, "is_current"] = True
    return result


def _run_estimated_pd_stress_sweep(
    df: pd.DataFrame,
    policy: CreditPolicy,
    sweep: list[float],
) -> pd.DataFrame:
    """Custom aggravation sweep for when estimated_default_col is set.

    The engine ignores stress scenarios when estimated_default_col is present
    (treats it as ground truth). Instead we pre-scale the column by each factor
    so the curve responds to the slider (issue #49).
    """
    estimated_col = policy.estimated_default_col
    rows = []
    for factor in sweep:
        df_stressed = df.copy()
        df_stressed[estimated_col] = (df_stressed[estimated_col] * factor).clip(0.0, 1.0)
        sim = run_policy_sim(df_stressed, policy)
        kpis = policy_kpis(sim)
        rows.append({
            "aggravation_factor": factor,
            "approval_rate": kpis["approval_rate"],
            "default_rate": kpis["bad_rate"] if kpis["bad_rate"] is not None else float("nan"),
        })
    return pd.DataFrame(rows, columns=["aggravation_factor", "approval_rate", "default_rate"])


def aggravation_game(
    df: pd.DataFrame,
    policy: CreditPolicy,
    current_factor: float,
    base_bad_rate: float | None,
    *,
    factors: list[float] | None = None,
    max_factor: float = 10.0,
) -> dict[str, Any]:
    """The Bancada's aggravation game (ADR 0001, critique 2.7): "even so, can I still
    approve?". Sweeps the flat stress factor, reads off the candidate's default rate at
    `current_factor`, and finds the break-even factor (`breakeven_aggravation_factor`)
    at which it reaches `base_bad_rate` — absorbing the Crash Test page rather than
    reimplementing its sweep.

    When `policy.estimated_default_col` is set the engine ignores stress scenarios, so
    the sweep pre-scales that column by each factor instead (issue #49). The result
    carries `has_estimated_pd=True` in that case so the UI can surface a note.

    `base_bad_rate=None` (Tier C, no comparison base) yields no breakeven factor;
    the standalone curve + current default rate are still returned.

    `max_factor` sets the sweep ceiling (default 10×, raised from the old 5× cap).
    Ignored when `factors` is supplied explicitly.
    """
    sweep = sorted({*(factors or np.linspace(1.0, max_factor, 25).tolist()), current_factor})
    has_estimated_pd = bool(
        policy.estimated_default_col and policy.estimated_default_col in df.columns
    )
    if has_estimated_pd:
        curve = _run_estimated_pd_stress_sweep(df, policy, sweep)
    else:
        curve = run_crash_test(df, policy, sweep)
    idx = (curve["aggravation_factor"] - current_factor).abs().idxmin()
    breakeven = (
        breakeven_aggravation_factor(curve, base_bad_rate) if base_bad_rate is not None else None
    )
    return {
        "curve": curve,
        "current_factor": current_factor,
        "current_default_rate": float(curve.loc[idx, "default_rate"]),
        "base_bad_rate": base_bad_rate,
        "breakeven_factor": breakeven,
        "has_estimated_pd": has_estimated_pd,
    }


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


def suggest_scenarios(
    df: pd.DataFrame,
    roles: ColumnRoles,
    shortlisted_scores: list[str],
    *,
    cutoff_steps: int = 8,
    target_default_rate: float = 0.05,
    min_approval_rate: float = 0.3,
    percentiles: tuple[float, float] | None = (0.05, 0.95),
) -> list[PolicyScenario]:
    """Suggest-first Bancada entry point (ADR 0005): 3 scenarios — conservador /
    neutro / agressivo — picked off an `optimize_cutoffs` grid run **only** on
    `shortlisted_scores`, so heavy compute never touches the other candidate scores.
    """
    if not shortlisted_scores:
        raise ValueError("shortlisted_scores não pode ser vazio.")
    base_policy = CreditPolicy(
        applicant_id_col=roles.applicant_id_col,
        score_cols=tuple(shortlisted_scores),
        current_approval_col=roles.current_approval_col,
        actual_default_col=roles.actual_default_col,
        time_col=roles.time_col,
        current_hired_col=roles.current_hired_col,
        estimated_default_col=roles.estimated_default_col,
    )
    result = run_optimization(
        df,
        base_policy,
        cutoff_steps=cutoff_steps,
        target_default_rate=target_default_rate,
        min_approval_rate=min_approval_rate,
        percentiles=percentiles,
    )
    grid = result.all_results
    conservative_row = grid.loc[grid["overall_default_rate"].idxmin()]
    aggressive_row = grid.loc[grid["overall_approval_rate"].idxmax()]
    mid_approval = (
        conservative_row["overall_approval_rate"] + aggressive_row["overall_approval_rate"]
    ) / 2
    neutral_row = grid.loc[(grid["overall_approval_rate"] - mid_approval).abs().idxmin()]

    picks = {
        "conservador": conservative_row,
        "neutro": neutral_row,
        "agressivo": aggressive_row,
    }
    return [
        PolicyScenario(
            name=name,
            cutoffs={score: float(row[score]) for score in shortlisted_scores},
            approval_rate=float(row["overall_approval_rate"]),
            default_rate=float(row["overall_default_rate"]),
        )
        for name, row in picks.items()
    ]


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


def _quantile_breaks(series: pd.Series, bins: int) -> list[float]:
    quantiles = np.linspace(0, 1, bins + 1)
    breaks = np.unique(np.quantile(series.dropna(), quantiles))
    if len(breaks) < 2:
        raise ValueError("Not enough variance to bin this score into quantiles.")
    return breaks.tolist()


def build_open_matrix(
    data: pd.DataFrame,
    score1: str,
    score2: str,
    default_col: str,
    bins: int = 5,
) -> OpenMatrix:
    """The open score x score quantile grid (critique 2.5 / ADR 0004).

    Every `bins x bins` cell is present, even ones with zero volume, each carrying
    its volume and default rate — the matriciation construction surface, shown
    open rather than only clustered.
    """
    breaks1 = _quantile_breaks(data[score1], bins)
    breaks2 = _quantile_breaks(data[score2], bins)
    bin1 = np.digitize(data[score1], breaks1[1:-1])
    bin2 = np.digitize(data[score2], breaks2[1:-1])

    work = pd.DataFrame({"bin1": bin1, "bin2": bin2, "_target": data[default_col].to_numpy()})
    observed = (
        work.groupby(["bin1", "bin2"])
        .agg(volume=("_target", "count"), pd=("_target", "mean"))
        .reset_index()
    )

    full_grid = pd.MultiIndex.from_product(
        [range(len(breaks1) - 1), range(len(breaks2) - 1)], names=["bin1", "bin2"]
    ).to_frame(index=False)
    cells = full_grid.merge(observed, on=["bin1", "bin2"], how="left")
    cells["volume"] = cells["volume"].fillna(0).astype(int)

    return OpenMatrix(score1=score1, score2=score2, breaks1=breaks1, breaks2=breaks2, cells=cells)


def default_cell_groups(matrix: OpenMatrix) -> dict[tuple[int, int], int]:
    """Starting-point grouping before any manual edit: each cell is its own group."""
    return {
        (int(row.bin1), int(row.bin2)): i + 1
        for i, row in enumerate(matrix.cells.itertuples())
    }


def recipe_to_cell_groups(recipe: GroupingRecipe) -> dict[tuple[int, int], int]:
    """Decode a 2-score recipe's `cluster_mapping` into the matrix's cell-group grid.

    The "run the algorithm as a starting point to refine" path (ADR 0004): seeds the
    editable grid with `fit_pairwise_risk_groups`'s clustering before manual edits.
    """
    cell_groups: dict[tuple[int, int], int] = {}
    for combo_key, group_id in (recipe.cluster_mapping or {}).items():
        bin1_str, bin2_str = combo_key.split("-")
        cell_groups[(int(bin1_str), int(bin2_str))] = int(group_id)
    return cell_groups


def cell_groups_to_grid(
    cell_groups: dict[tuple[int, int], int], bins1: int, bins2: int
) -> pd.DataFrame:
    """`cell_groups` as a `bins1 x bins2` grid, for an Excel-like editable table."""
    grid = pd.DataFrame(index=range(bins1), columns=range(bins2), dtype="Int64")
    for (bin1, bin2), group_id in cell_groups.items():
        grid.loc[bin1, bin2] = group_id
    return grid


def grid_to_cell_groups(grid: pd.DataFrame) -> dict[tuple[int, int], int]:
    """Inverse of `cell_groups_to_grid`: reads the hand-edited grid back into a mapping."""
    cell_groups: dict[tuple[int, int], int] = {}
    for bin1 in grid.index:
        for bin2 in grid.columns:
            value = grid.loc[bin1, bin2]
            if pd.notna(value):
                cell_groups[(int(bin1), int(bin2))] = int(value)
    return cell_groups


def open_matrix_pivot(matrix: OpenMatrix, value: str = "pd") -> pd.DataFrame:
    """`matrix.cells[value]` pivoted to `bin1 x bin2`, for a heatmap of volume or PD."""
    return matrix.cells.pivot_table(index="bin1", columns="bin2", values=value)


def apply_manual_grouping(
    matrix: OpenMatrix,
    data: pd.DataFrame,
    default_col: str,
    cell_groups: dict[tuple[int, int], int],
) -> RiskGroupResult:
    """Turn a hand-edited `cell_groups` mapping over `matrix` into a `RiskGroupResult`.

    The studio-side counterpart to the engine's algorithmic clustering (ADR 0004 /
    critique 2.5): every cell of `matrix`'s grid must be assigned a group for the
    resulting recipe to be valid (`GroupingRecipe.predict()` would otherwise leave
    unmapped cells as NaN). The result drops into `StudioState.rating_result` like
    any `fit_risk_groups()` output, feeding the Bancada cutoffs the same way.
    """
    grid_cells = {(int(row.bin1), int(row.bin2)) for row in matrix.cells.itertuples()}
    missing = grid_cells - cell_groups.keys()
    if missing:
        raise ValueError(f"Faltam grupos para as células: {sorted(missing)}")

    cluster_mapping = {
        f"{bin1}-{bin2}": int(group_id) for (bin1, bin2), group_id in cell_groups.items()
    }

    full_df = data.copy()
    bin1 = np.digitize(full_df[matrix.score1], matrix.breaks1[1:-1])
    bin2 = np.digitize(full_df[matrix.score2], matrix.breaks2[1:-1])
    combo_key = pd.Series(bin1, index=full_df.index).astype(str) + "-" + pd.Series(
        bin2, index=full_df.index
    ).astype(str)
    full_df["risk_rating"] = combo_key.map(cluster_mapping)

    groups_summary = (
        full_df.groupby("risk_rating")
        .agg(volume=(default_col, "count"), pd=(default_col, "mean"))
        .reset_index()
    )

    recipe = GroupingRecipe(
        score_cols=[matrix.score1, matrix.score2],
        quantile_breaks={matrix.score1: matrix.breaks1, matrix.score2: matrix.breaks2},
        cluster_mapping=cluster_mapping,
    )

    return RiskGroupResult(
        data=full_df,
        groups=groups_summary,
        recipe=recipe,
        n_groups=len(set(cell_groups.values())),
        params={"bins1": len(matrix.breaks1) - 1, "bins2": len(matrix.breaks2) - 1, "manual": True},
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


