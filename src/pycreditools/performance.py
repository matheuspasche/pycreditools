from typing import Any

import numpy as np
import pandas as pd

from ._types import Quadrant
from .simulation import CreditSimResults


def summarize_results(results: CreditSimResults, by: str | list[str] | None = None) -> pd.DataFrame:
    """Summarize simulation results.

    Args:
        results: A CreditSimResults object from run_simulation.
        by: Columns to group by in addition to 'scenario'.

    Returns:
        DataFrame with summary statistics.

    Notes on bad rate interpretation:
        - keep_in / swap_in: simulated_default (swap_in is score-calibrated).
        - swap_out: actual_default (client was previously approved — data is observed).
        - keep_out: NaN — this population was rejected by both policies;
                    no observed credit performance exists.
    """
    data = results.data.copy()
    policy_dict = results.metadata["policy"]
    actual_default_col = policy_dict["actual_default_col"]

    is_analytical = results.metadata.get("method") == "analytical"

    group_cols = []
    if by is not None:
        if isinstance(by, str):
            group_cols.append(by)
        else:
            group_cols.extend(by)

    group_cols.append("scenario")

    # ── Determine whether the simulation tracked pre-rate approvals ────────
    has_pre_rate = "approved_pre_rate" in data.columns

    # ── Bad rate proxy per quadrant ────────────────────────────────────
    # keep_in / swap_in  → simulated_default (swap_in is score-calibrated)
    # swap_out           → actual_default  (observed — was in old portfolio)
    # keep_out           → NaN            (rejected by both; no observed data)
    data["_bad_rate_proxy"] = data["simulated_default"]

    swap_out_mask = data["scenario"] == Quadrant.SWAP_OUT.value
    keep_out_mask = data["scenario"] == Quadrant.KEEP_OUT.value

    data.loc[swap_out_mask, "_bad_rate_proxy"] = data.loc[swap_out_mask, actual_default_col]
    data.loc[keep_out_mask, "_bad_rate_proxy"] = np.nan  # no observable data

    if not is_analytical:
        # ── Stochastic path ─────────────────────────────────────────────
        # Use applicant_id_col for counting to avoid grouping column conflicts
        summary = (
            data.groupby(group_cols, dropna=False)
            .agg(
                Applicants=(policy_dict["applicant_id_col"], "count"),
                # Approved: clients who passed all filter/cutoff stages (pre-take-up)
                Approved=("approved_pre_rate", lambda x: x.sum(skipna=True))
                if has_pre_rate
                else ("new_approval", lambda x: x.sum(skipna=True)),
                # Hired: clients who actually contracted (includes take-up probability)
                Hired=("new_approval", lambda x: x.sum(skipna=True)),
                Bad_Rate=("_bad_rate_proxy", lambda x: x.mean(skipna=True)),
            )
            .reset_index()
        )

    else:
        # ── Analytical path ────────────────────────────────────────────
        data["_weighted_default"] = data["simulated_default"] * data["new_approval"]

        def _bad_rate(grp, scen):
            if scen == Quadrant.KEEP_OUT.value:
                return np.nan
            if scen == Quadrant.SWAP_OUT.value:
                return grp[actual_default_col].mean(skipna=True)
            # keep_in / swap_in: weighted simulated default
            total_app = grp["new_approval"].sum(skipna=True)
            if total_app <= 0:
                return 0.0
            return grp["_weighted_default"].sum(skipna=True) / total_app

        metrics = []
        for name, group in data.groupby(group_cols, dropna=False):
            if not isinstance(name, tuple):
                name = (name,)

            row = dict(zip(group_cols, name))
            row["Applicants"] = len(group)
            row["Approved"] = (
                group["approved_pre_rate"].sum(skipna=True)
                if has_pre_rate
                else group["new_approval"].sum(skipna=True)
            )
            row["Hired"] = group["new_approval"].sum(skipna=True)
            row["Bad_Rate"] = _bad_rate(group, row["scenario"])
            metrics.append(row)

        summary = pd.DataFrame(metrics)

    # ── Mark keep_out as explicitly unknown ────────────────────────────
    # (do NOT fill NaN for keep_out — leave it as NaN to signal "unobservable")
    mask_not_ko = summary["scenario"] != Quadrant.KEEP_OUT.value
    summary.loc[mask_not_ko, "Bad_Rate"] = summary.loc[mask_not_ko, "Bad_Rate"].fillna(0.0)

    # Cleanup
    for tmp in ("_bad_rate_proxy", "_weighted_default"):
        if tmp in data.columns:
            del data[tmp]

    return summary


def compare_policies(sim_new: CreditSimResults, sim_old: CreditSimResults) -> dict[str, Any]:
    """Compare two simulated policies.

    Args:
        sim_new: Results of the new policy simulation.
        sim_old: Results of the old (or baseline) policy simulation.

    Returns:
        Dict containing global metrics, swap summaries, and the swap-in to keep-in ratio.
    """
    data_new = sim_new.data
    data_old = sim_old.data

    is_analytical = sim_new.metadata.get("method") == "analytical"

    def get_global_metrics(data):
        if not is_analytical:
            app_sum = data["new_approval"].sum(skipna=True)
            bad_rate = data.loc[data["new_approval"] == 1, "simulated_default"].mean(skipna=True)
        else:
            app_sum = data["new_approval"].sum(skipna=True)
            if app_sum > 0:
                bad_rate = (data["simulated_default"] * data["new_approval"]).sum(
                    skipna=True
                ) / app_sum
            else:
                bad_rate = 0.0
        return app_sum, bad_rate if pd.notna(bad_rate) else 0.0

    app_new, bad_new = get_global_metrics(data_new)
    app_old, bad_old = get_global_metrics(data_old)

    n_total = len(data_new)

    metrics = pd.DataFrame(
        {
            "Metric": ["Approval Rate", "Bad Rate"],
            "Old": [app_old / n_total, bad_old],
            "New": [app_new / n_total, bad_new],
            "Delta_Abs": [(app_new - app_old) / n_total, bad_new - bad_old],
            "Delta_Rel": [(app_new / max(app_old, 1e-6)) - 1, (bad_new / max(bad_old, 1e-6)) - 1],
        }
    )

    swaps = summarize_results(sim_new)

    # Swap-in to Keep-in ratio
    si_vol = swaps.loc[swaps["scenario"] == Quadrant.SWAP_IN.value, "Approved"].sum()
    ki_vol = swaps.loc[swaps["scenario"] == Quadrant.KEEP_IN.value, "Approved"].sum()

    ratio = si_vol / ki_vol if ki_vol > 0 else np.nan

    return {"metrics": metrics, "swaps": swaps, "ratio": ratio}


class ModelEvaluator:
    """Evaluates predictive power of credit score models."""

    def __init__(self, data: pd.DataFrame, score_cols: list[str], target_col: str):
        self.data = data
        self.score_cols = score_cols
        self.target_col = target_col

    def compute_ks(self) -> dict[str, float]:
        """Compute Kolmogorov-Smirnov (KS) statistic for each score.
        Assumes higher score = lower probability of default.
        """
        import numpy as np

        ks_dict = {}
        for col in self.score_cols:
            df = self.data[[col, self.target_col]].dropna().copy()
            # Sort by score descending
            df = df.sort_values(col, ascending=False)
            bads = df[self.target_col].values
            goods = 1 - bads

            total_bads = bads.sum()
            total_goods = goods.sum()

            if total_bads == 0 or total_goods == 0:
                ks_dict[col] = 0.0
                continue

            cum_bads = np.cumsum(bads) / total_bads
            cum_goods = np.cumsum(goods) / total_goods

            ks = np.max(np.abs(cum_bads - cum_goods))
            ks_dict[col] = float(ks)

        return ks_dict

    def compute_ks_table(self, col: str, bins: int = 10) -> pd.DataFrame:
        """Compute a quantile table with KS, Bad Rate, and volume for a specific score column."""
        import numpy as np

        df = self.data[[col, self.target_col]].dropna().copy()

        # Create quantiles (deciles by default)
        try:
            df["Decile"] = pd.qcut(df[col], q=bins, labels=False, duplicates="drop")
        except ValueError:
            # Fallback if too many identical values
            df["Decile"] = pd.cut(df[col], bins=bins, labels=False)

        # Group by Decile (we want decile 0 to be the WORST score, i.e., highest default rate)
        # So we sort descending by decile, assuming score is higher=better
        summary = (
            df.groupby("Decile")
            .agg(
                Volume=(self.target_col, "count"),
                Bads=(self.target_col, "sum"),
                Avg_Score=(col, "mean"),
            )
            .reset_index()
        )

        # Sort so that highest score (best risk) is at the top
        summary = summary.sort_values("Avg_Score", ascending=False).reset_index(drop=True)

        # Add human readable bucket numbers (1 is best, 10 is worst)
        summary["Bucket"] = range(1, len(summary) + 1)

        summary["Goods"] = summary["Volume"] - summary["Bads"]
        summary["Bad_Rate"] = summary["Bads"] / summary["Volume"]

        total_bads = summary["Bads"].sum()
        total_goods = summary["Goods"].sum()

        if total_bads > 0 and total_goods > 0:
            summary["Cum_Bads"] = summary["Bads"].cumsum() / total_bads
            summary["Cum_Goods"] = summary["Goods"].cumsum() / total_goods
            summary["KS"] = np.abs(summary["Cum_Bads"] - summary["Cum_Goods"])
        else:
            summary["Cum_Bads"] = 0.0
            summary["Cum_Goods"] = 0.0
            summary["KS"] = 0.0

        # Reorder columns
        return summary[["Bucket", "Avg_Score", "Volume", "Bad_Rate", "Cum_Bads", "Cum_Goods", "KS"]]


def print_delta_table(
    sim_new: CreditSimResults,
    sim_old: CreditSimResults | pd.DataFrame | None = None,
) -> None:
    """Print a beautiful executive P&L delta table comparing two simulations.

    Args:
        sim_new: Results of the new policy simulation.
        sim_old: Results of the old (or baseline) policy simulation or raw dataset.
                 If None, legacy metrics are extracted directly from sim_new.data.
    """
    df_new = sim_new.data
    policy_new_dict = sim_new.metadata["policy"]
    actual_default_col = policy_new_dict["actual_default_col"]
    current_approval_col = policy_new_dict.get("current_approval_col", "approved")

    # 1. New policy metrics
    vol_new = df_new.loc[df_new["scenario"].isin(["keep_in", "swap_in"]), "new_approval"].sum()
    if vol_new > 0:
        bad_new = (
            (
                df_new.loc[df_new["scenario"] == "keep_in", "simulated_default"]
                * df_new.loc[df_new["scenario"] == "keep_in", "new_approval"]
            ).sum()
            + (
                df_new.loc[df_new["scenario"] == "swap_in", "simulated_default"]
                * df_new.loc[df_new["scenario"] == "swap_in", "new_approval"]
            ).sum()
        ) / vol_new
    else:
        bad_new = 0.0
    if "approved_pre_rate" in df_new.columns:
        aprov_new = (df_new["approved_pre_rate"] > 0).mean()
    else:
        aprov_new = (df_new["new_approval"] > 0).mean()

    # 2. Legacy policy metrics
    if sim_old is not None:
        if isinstance(sim_old, CreditSimResults):
            df_old = sim_old.data
            policy_old_dict = sim_old.metadata["policy"]
            old_default_col = policy_old_dict["actual_default_col"]
            old_approval_col = policy_old_dict.get("current_approval_col", "approved")
        else:
            df_old = sim_old
            old_default_col = actual_default_col
            old_approval_col = current_approval_col

        aprov_old = (
            (df_old[old_approval_col] > 0).mean()
            if old_approval_col in df_old.columns
            else (df_old["new_approval"] > 0).mean()
        )
        legacy_hired_col = (
            "hired"
            if "hired" in df_old.columns
            else ("new_approval" if "new_approval" in df_old.columns else old_approval_col)
        )
        vol_old = df_old[legacy_hired_col].sum() if legacy_hired_col in df_old.columns else 0.0
        if vol_old > 0:
            bad_old = (df_old[old_default_col] * df_old[legacy_hired_col]).sum() / vol_old
        else:
            bad_old = 0.0
    else:
        # Fallback to extracting from df_new
        aprov_old = (
            (df_new[current_approval_col] > 0).mean()
            if current_approval_col in df_new.columns
            else 0.0
        )
        legacy_hired_col = "hired" if "hired" in df_new.columns else current_approval_col
        vol_old = df_new[legacy_hired_col].sum() if legacy_hired_col in df_new.columns else 0.0
        if vol_old > 0:
            bad_old = (df_new[actual_default_col] * df_new[legacy_hired_col]).sum() / vol_old
        else:
            bad_old = 0.0

    print("=== TABELA DELTA: P&L EXECUTIVO ===")
    print(f"{'Métrica':<35} {'Legacy':>10}  {'Nova':>10}  {'Δ Abs':>10}  {'Δ Rel':>10}")
    print("─" * 78)

    # Approval comparison
    aprov_diff_abs = aprov_new - aprov_old
    aprov_diff_rel = (aprov_new / aprov_old) - 1.0 if aprov_old > 0 else 0.0
    print(
        f"{'Aprovação Global (% ToF)':<35} {aprov_old:>10.2%}  {aprov_new:>10.2%}  "
        f"{aprov_diff_abs:>+10.2%}  {aprov_diff_rel:>+10.1%}"
    )

    # Bad Rate comparison
    bad_diff_abs = bad_new - bad_old
    bad_diff_rel = (bad_new / bad_old) - 1.0 if bad_old > 0 else 0.0
    print(
        f"{'Bad Rate Contratado (P&L)':<35} {bad_old:>10.2%}  {bad_new:>10.2%}  "
        f"{bad_diff_abs:>+10.2%}  {bad_diff_rel:>+10.1%}"
    )

    # Volume comparison
    vol_diff_abs = vol_new - vol_old
    vol_diff_rel = (vol_new / vol_old) - 1.0 if vol_old > 0 else 0.0
    print(
        f"{'Vol. Contratado Esperado':<35} {vol_old:>10,.0f}  {vol_new:>10,.0f}  "
        f"{vol_diff_abs:>+10,.0f}  {vol_diff_rel:>+10.1%}"
    )


def print_quadrant_summary(sim_results: CreditSimResults) -> None:
    """Print a beautiful quadrant summary table with volumes and default rates.

    Args:
        sim_results: Results of the simulation containing 'scenario' column.
    """
    df = sim_results.data
    policy_dict = sim_results.metadata["policy"]
    actual_default_col = policy_dict["actual_default_col"]

    ki = df[df["scenario"] == "keep_in"]
    si = df[df["scenario"] == "swap_in"]
    ko = df[df["scenario"] == "keep_out"]

    # Helper to calculate bad rate safely
    def get_metric(subset, default_col, is_simulated=False):
        vol = subset["new_approval"].sum()
        if vol <= 0:
            return 0.0, 0.0
        col_to_use = "simulated_default" if is_simulated else default_col
        bad_rate = (subset[col_to_use] * subset["new_approval"]).sum() / vol
        return vol, bad_rate

    ki_vol, ki_bad = get_metric(ki, actual_default_col, is_simulated=False)
    si_vol, si_bad = get_metric(si, actual_default_col, is_simulated=True)

    # For swap out, the volume and bad rate are based on the legacy hired portfolio status
    # (stored in 'hired' column)
    legacy_hired_col = (
        "hired" if "hired" in df.columns else policy_dict.get("current_approval_col", "approved")
    )
    so_vol = (
        df.loc[df["scenario"] == "swap_out", legacy_hired_col].sum()
        if legacy_hired_col in df.columns
        else 0.0
    )
    if so_vol > 0:
        so_bad = (
            df.loc[df["scenario"] == "swap_out", actual_default_col]
            * df.loc[df["scenario"] == "swap_out", legacy_hired_col]
        ).sum() / so_vol
    else:
        so_bad = 0.0

    ko_vol = ko["new_approval"].sum()

    print("=== QUADRANTES: VOLUME ESPERADO CONTRATADO E INADIMPLÊNCIA ===")
    print(f"{'Quadrante':<12} {'Vol. Contratado':>17}  {'Bad Rate':>12}  {'Fonte'}")
    print("─" * 65)
    print(f"{'Keep In':<12} {ki_vol:>17,.0f}  {ki_bad:>12.2%}  {actual_default_col} (observado)")
    print(
        f"{'Swap In':<12} {si_vol:>17,.0f}  {si_bad:>12.2%}  simulated_default (agravado/simulado)"
    )
    print(
        f"{'Swap Out':<12} {so_vol:>17,.0f}  {so_bad:>12.2%}  {actual_default_col} (observado na carteira antiga)"
    )
    print(f"{'Keep Out':<12} {ko_vol:>17,.0f}  {'N/A':>12}  sem dados (reprovados por ambas)")


def print_swap_in_by_rating(sim_results: CreditSimResults, rating_col: str = "Rating") -> None:
    """Print detailed Swap In metrics grouped by credit rating.

    Args:
        sim_results: Results of the simulation containing 'scenario' column.
        rating_col: Name of the rating column in the data.
    """
    df = sim_results.data.copy()
    if rating_col not in df.columns:
        print(f"Coluna de Rating '{rating_col}' não encontrada nos dados.")
        return

    si = df[df["scenario"] == "swap_in"]
    print("\n=== RAIO-X DOS SWAP INS POR RATING ===")
    if si.empty:
        print("Nenhum swap in na simulação.")
        return

    def _si_agg(g):
        vol = g["new_approval"].sum()
        bad = (g["simulated_default"] * g["new_approval"]).sum() / vol if vol > 0 else np.nan
        return pd.Series({"Vol_Esperado": vol, "Inad_Stressed": bad})

    si_r = si.groupby(rating_col).apply(_si_agg, include_groups=False).reset_index()
    si_r["Vol %"] = (
        si_r["Vol_Esperado"] / si_r["Vol_Esperado"].sum() if si_r["Vol_Esperado"].sum() > 0 else 0.0
    )

    # Sort descending by rating
    si_r = si_r.sort_values(rating_col, ascending=False)

    print(f"{rating_col:>8} {'Vol. Esperado':>15} {'Vol %':>8} {'Inad Stressed':>15}")
    print("─" * 50)
    for _, row in si_r.iterrows():
        print(
            f"{row[rating_col]:>8} {row['Vol_Esperado']:>15,.0f} {row['Vol %']:>8.1%} {row['Inad_Stressed']:>15.2%}"
        )


def print_rating_quadrant_table(sim_results: CreditSimResults, rating_col: str = "Rating") -> None:
    """Print approval, volume, and bad rates by rating and quadrant.

    Args:
        sim_results: Results of the simulation containing 'scenario' column.
        rating_col: Name of the rating column in the data.
    """
    df = sim_results.data.copy()
    policy_dict = sim_results.metadata["policy"]
    actual_default_col = policy_dict["actual_default_col"]
    current_approval_col = policy_dict.get("current_approval_col", "approved")
    legacy_hired_col = "hired" if "hired" in df.columns else current_approval_col

    print("\n=== APROVADOS E CONTRATADOS POR RATING E QUADRANTE ===")

    def build_row(g):
        scen = g.name[1]
        if scen == "swap_out":
            aprov = (
                int((g[current_approval_col] > 0).sum()) if current_approval_col in g.columns else 0
            )
            hired = int(g[legacy_hired_col].sum()) if legacy_hired_col in g.columns else 0
            if legacy_hired_col in g.columns and g[legacy_hired_col].sum() > 0:
                bad = (g[actual_default_col] * g[legacy_hired_col]).sum() / g[
                    legacy_hired_col
                ].sum()
            else:
                bad = np.nan
            return pd.Series(
                {
                    "Aprovados": aprov,
                    "Contratados": hired,
                    "Bad_Rate": f"{bad:.2%}" if pd.notna(bad) else "N/A",
                }
            )
        else:
            vol = g["new_approval"].sum()
            if scen == "swap_in":
                bad = (
                    (g["simulated_default"] * g["new_approval"]).sum() / vol if vol > 0 else np.nan
                )
            elif scen == "keep_in":
                bad = (g[actual_default_col] * g["new_approval"]).sum() / vol if vol > 0 else np.nan
            else:
                bad = np.nan

            aprov_count = int((g["approved_pre_rate"] > 0).sum()) if "approved_pre_rate" in g.columns else int((g["new_approval"] > 0).sum())
            return pd.Series(
                {
                    "Aprovados": aprov_count,
                    "Contratados": round(vol, 0),
                    "Bad_Rate": f"{bad:.2%}" if pd.notna(bad) else "N/A",
                }
            )

    if rating_col in df.columns and "scenario" in df.columns:
        rt_quad = (
            df.groupby([rating_col, "scenario"])
            .apply(build_row, include_groups=False)
            .reset_index()
        )
        rt_quad = rt_quad.sort_values([rating_col, "scenario"], ascending=[False, True])
        rt_quad["Contratados"] = rt_quad["Contratados"].apply(
            lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else x
        )
        print(rt_quad.to_string(index=False))
    else:
        print(f"Colunas '{rating_col}' ou 'scenario' não encontradas nos dados.")
