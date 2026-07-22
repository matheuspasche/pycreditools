"""Branch-agnostic measurement core for issue #91 (engine parity).

Imported by measure_main.py / measure_v05.py, each of which supplies an
*adapter* describing the branch-specific API surface (take-up rate stage,
engine facts, optional hard-filter suggester). Every reported metric comes
from ``policy.simulate(...).data`` — no sweep fast-path anywhere.

Metric contract used for BOTH engines (ADR 0008 raw-funnel formula):
    approval    = sum(approved_pre_rate) / n          (pre take-up)
    contracted  = sum(new_approval)
    default     = sum(simulated_default * new_approval) / contracted

A "legacy contract" variant (post-take-up approval, unweighted default) is
also emitted so the notebook can quantify how much of any gap is purely the
metric-contract change (root cause #2).
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd

SEED = 7
LEGACY_QUANTILE = 0.78
STRESS_FACTORS = [1.0, 1.3, 1.5]
# Fixed challenger hard-filter set (the one the v0.5 suggester picks), so both
# engines compare apples to apples (root cause #5 isolated by construction).
HF_RULES = [
    ("vl_negativacao", "lte", 0),
    ("vl_vencido_scr", "lte", 0),
    ("vl_protestos", "lte", 0),
]
SCORES = ["legacy_score", "score_2", "score_3", "score_4", "score_5"]
CUTOFF_QUANTILES = np.linspace(0.30, 0.95, 27)


def hf_mask(df: pd.DataFrame) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col_name, direction, thr in HF_RULES:
        m &= (df[col_name] <= thr) if direction == "lte" else (df[col_name] >= thr)
    return m


def kpis(sim_data: pd.DataFrame) -> dict:
    """ADR 0008 metric contract, read straight off the funnel columns."""
    d = sim_data
    n = len(d)
    approved = float(d["approved_pre_rate"].sum())
    contracted = float(d["new_approval"].sum())
    weighted_default = float((d["simulated_default"] * d["new_approval"]).sum())
    return {
        "approval": approved / n,
        "default": weighted_default / contracted if contracted else float("nan"),
        "contracted": contracted,
        "take_up": contracted / approved if approved else float("nan"),
    }


def kpis_legacy_contract(sim_data: pd.DataFrame) -> dict:
    """Pre-ADR-0008 denominators: post-take-up approval, unweighted default."""
    d = sim_data
    n = len(d)
    approved_mask = d["approved_pre_rate"] > 0
    return {
        "approval_post_take_up": float(d["new_approval"].sum()) / n,
        "default_unweighted": float(d.loc[approved_mask, "simulated_default"].mean()),
    }


def stressed_default(sim_data: pd.DataFrame, factor: float) -> float:
    """Blended default under AggravationStress(factor) derived analytically.

    Both engines implement AggravationStress as ``clip(baseline_pd * factor)``
    applied to swap-in rows only; keep-in rows keep the observed outcome. The
    no-stress ``simulated_default`` of a swap-in row IS its baseline PD, so the
    stressed blend follows without another simulate call.
    """
    d = sim_data
    sd = d["simulated_default"].copy()
    swap_in = d["scenario"] == "swap_in"
    sd.loc[swap_in] = (sd.loc[swap_in] * factor).clip(0.0, 1.0)
    contracted = float(d["new_approval"].sum())
    return float((sd * d["new_approval"]).sum()) / contracted if contracted else float("nan")


def true_default(sim_data: pd.DataFrame) -> float:
    """Oracle blended default: true_pd weighted by contracted volume."""
    if "true_pd" not in sim_data.columns:
        return float("nan")
    d = sim_data
    contracted = float(d["new_approval"].sum())
    if not contracted:
        return float("nan")
    return float((d["true_pd"] * d["new_approval"]).sum()) / contracted


def quadrant_table(sim_data: pd.DataFrame, actual_default_col: str = "actual_default") -> dict:
    out = {}
    for scen, grp in sim_data.groupby("scenario"):
        vol = float(grp["new_approval"].sum())
        row = {"n": int(len(grp)), "vol": vol}
        if vol:
            row["sim"] = float((grp["simulated_default"] * grp["new_approval"]).sum()) / vol
            if "true_pd" in grp.columns:
                row["true"] = float((grp["true_pd"] * grp["new_approval"]).sum()) / vol
        actual = grp[actual_default_col]
        if actual.notna().any():
            row["actual"] = float(actual.mean())
        out[scen] = row
    return out


def _simulate(policy, base):
    """simulate() capturing warnings; returns (sim_data, [warning strings])."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sim = policy.simulate(base, method="analytical")
    msgs = [f"[{w.category.__name__}] {w.message}" for w in caught]
    return sim.data, msgs


def measure(adapter, base: pd.DataFrame, mode: str, seed: int, out_path: str) -> dict:
    notes: list[str] = []

    def note(msgs):
        for m in msgs:
            if m not in notes:
                notes.append(m)

    n = len(base)
    legacy_cut = float(base["legacy_score"].quantile(LEGACY_QUANTILE))

    result = {
        "branch": adapter.name,
        "mode": mode,
        "seed": seed,
        "n": n,
        "legacy_cutoff": legacy_cut,
        "engine_facts": adapter.engine_facts(base),
    }

    # ── Step 1: incumbent ────────────────────────────────────────────────
    incumbent = adapter.take_up(
        adapter.new_policy()
        .filter("Bureau knock-outs", adapter.entry_filter())
        .cutoff("Legacy cutoff", {"legacy_score": legacy_cut}, direction="gte")
    )
    inc_data, msgs = _simulate(incumbent, base)
    note(msgs)
    inc = kpis(inc_data)
    inc["legacy_contract"] = kpis_legacy_contract(inc_data)
    inc["default_true"] = true_default(inc_data)
    inc["quadrants"] = quadrant_table(inc_data)
    result["incumbent"] = inc

    # ── Step 2: challenger hard filters ──────────────────────────────────
    result["hard_filters"] = {
        "used_rules": [f"{c} {d} {t}" for c, d, t in HF_RULES],
        "bad_col": "actual_default",  # marker the suggester screens against (ADR 0010)
        "suggested": adapter.suggest_hf(base, note),
        "hf_pass_rate": float(hf_mask(base).mean()),
    }

    # ── Step 3: KS on HF-approved only ───────────────────────────────────
    hf_approved = base[hf_mask(base)]
    result["ks_on_hf_approved"] = {
        k: round(float(v), 4)
        for k, v in adapter.compute_ks(hf_approved, SCORES, "actual_default").items()
    }

    # ── Steps 4-5: challenger frontier over score_5 cutoffs ─────────────
    def challenger(cutoff: float):
        return adapter.take_up(
            adapter.new_policy(calibrated=True)
            .filter("Hard filters", adapter.hf_filter())
            .cutoff("Challenger cutoff", {"score_5": float(cutoff)}, direction="gte")
        )

    cutoffs = sorted({int(round(q)) for q in base["score_5"].quantile(CUTOFF_QUANTILES)})
    frontier = []
    sims_by_cutoff = {}
    for cut in cutoffs:
        sim_data, msgs = _simulate(challenger(cut), base)
        note(msgs)
        row = kpis(sim_data)
        row["cutoff"] = cut
        row["default_true"] = true_default(sim_data)
        for f in STRESS_FACTORS[1:]:
            row[f"default_stress_{f}"] = stressed_default(sim_data, f)
        frontier.append(row)
        sims_by_cutoff[cut] = sim_data
    result["frontier"] = frontier

    fr = pd.DataFrame(frontier)

    # Three policies, localized on the frontier (no-stress simulated default).
    iso_appr_cut = int(fr.loc[(fr["approval"] - inc["approval"]).abs().idxmin(), "cutoff"])
    ok = fr[fr["default"] <= inc["default"]]
    iso_inad_cut = (
        int(ok.loc[ok["approval"].idxmax(), "cutoff"])
        if len(ok)
        else int(fr.loc[(fr["default"] - inc["default"]).abs().idxmin(), "cutoff"])
    )
    balanced_cut = int(
        fr.loc[(fr["cutoff"] - (iso_appr_cut + iso_inad_cut) / 2).abs().idxmin(), "cutoff"]
    )

    def policy_row(name, cut):
        row = dict(fr[fr["cutoff"] == cut].iloc[0])
        row = {k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in row.items()}
        row["name"] = name
        row["cutoff"] = int(cut)
        row["default_sim"] = row["default"]  # issue-schema alias
        return row

    result["three_policies"] = [
        policy_row("iso_approval", iso_appr_cut),
        policy_row("iso_default", iso_inad_cut),
        policy_row("balanced", balanced_cut),
    ]

    # Champion detail at iso-approval cutoff.
    champ_data = sims_by_cutoff[iso_appr_cut]
    champ = kpis(champ_data)
    champ["cutoff"] = iso_appr_cut
    champ["default_sim"] = champ["default"]  # issue-schema alias
    champ["default_true"] = true_default(champ_data)
    for f in STRESS_FACTORS[1:]:
        champ[f"default_stress_{f}"] = stressed_default(champ_data, f)
    champ["legacy_contract"] = kpis_legacy_contract(champ_data)
    champ["quadrants"] = quadrant_table(champ_data)

    # Stress measured through the engine's own code path (policy.stress(1.5)),
    # not just derived analytically — verifies the clip(pd*factor) assumption.
    stressed_data, msgs = _simulate(challenger(iso_appr_cut).stress(1.5), base)
    note(msgs)
    champ["default_stress_1.5_measured"] = kpis(stressed_data)["default"]
    si_st = stressed_data[stressed_data["scenario"] == "swap_in"]
    w_st = si_st["new_approval"]
    champ["swap_in_pd_stress_1.5_measured"] = (
        float((si_st["simulated_default"] * w_st).sum() / w_st.sum())
        if float(w_st.sum())
        else float("nan")
    )
    result["champion_iso_approval"] = champ

    # Swap-in PD calibration dial (root cause #4).
    si = champ_data[champ_data["scenario"] == "swap_in"]
    w = si["new_approval"]
    baseline = float((si["simulated_default"] * w).sum() / w.sum()) if float(w.sum()) else float("nan")
    dial = {
        "swap_in_pd_true": (
            float((si["true_pd"] * w).sum() / w.sum())
            if "true_pd" in si.columns and float(w.sum())
            else float("nan")
        )
    }
    for f in STRESS_FACTORS:
        dial[f"swap_in_pd_stress_{f}"] = float(np.clip(si["simulated_default"] * f, 0, 1).mul(w).sum() / w.sum()) if float(w.sum()) else float("nan")
    dial["swap_in_pd_imputed"] = baseline
    dial.update(adapter.extra_swap_in_facts(base, challenger, iso_appr_cut, note))
    result["swap_in_calibration"] = dial

    # ── Step 6: regional cutoffs vs one general cutoff, common target ────
    target = inc["default"]
    general = fr[fr["default"] <= target]
    general_row = (
        policy_row("general", int(general.loc[general["approval"].idxmax(), "cutoff"]))
        if len(general)
        else policy_row("general", int(fr.loc[(fr["default"] - target).abs().idxmin(), "cutoff"]))
    )
    regions = []
    seg_approved = seg_contracted = seg_weighted_def = 0.0
    for region, sub in base.groupby("region"):
        sub = sub.reset_index(drop=True)
        reg_cutoffs = sorted({int(round(q)) for q in sub["score_5"].quantile(CUTOFF_QUANTILES)})
        best = None
        for cut in reg_cutoffs:
            sim_data, msgs = _simulate(challenger(cut), sub)
            note(msgs)
            k = kpis(sim_data)
            if k["default"] <= target and (best is None or k["approval"] > best[1]["approval"]):
                best = (cut, k)
        if best is None:  # no cutoff meets target: take lowest default
            rows = []
            for cut in reg_cutoffs:
                sim_data, _ = _simulate(challenger(cut), sub)
                rows.append((cut, kpis(sim_data)))
            best = min(rows, key=lambda r: r[1]["default"])
        cut, k = best
        regions.append(
            {
                "region": region,
                "applicants": int(len(sub)),
                "cutoff": cut,
                "approval": k["approval"],
                "default": k["default"],
                "contracted": k["contracted"],
            }
        )
        seg_approved += k["approval"] * len(sub)
        seg_contracted += k["contracted"]
        seg_weighted_def += k["default"] * k["contracted"]
    result["regional_cutoffs"] = {
        "target_default": target,
        "general": general_row,
        "regions": regions,
        "segmented_total": {
            "approval": seg_approved / n,
            "default": seg_weighted_def / seg_contracted if seg_contracted else float("nan"),
            "contracted": seg_contracted,
        },
    }

    # Engine's own optimize_cutoffs, as the masterclass would call it (root
    # cause #6). Cutoff LOCALIZED by the optimizer, metrics RE-REPORTED via
    # .simulate() at that cutoff, honouring the golden rule (the v0.5
    # optimizer rides the sweep fast-path internally).
    try:
        opt = adapter.optimizer_check(base, target, note)
        if opt is not None and "cutoff" in opt:
            sim_data, msgs = _simulate(challenger(opt["cutoff"]), base)
            note(msgs)
            opt["resimulated"] = kpis(sim_data)
            opt["resimulated"]["default_true"] = true_default(sim_data)
        result["optimizer_check"] = opt
    except Exception as exc:
        result["optimizer_check"] = {"error": f"{type(exc).__name__}: {exc}"}
        note([f"[optimizer_check] {type(exc).__name__}: {exc}"])

    # ── Step 7: rating A-E with DEV/OOT validation ───────────────────────
    contracted_df = base[base["hired"] == 1].copy()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rating = adapter.fit_risk_groups(
                contracted_df,
                "score_5",
                "actual_default",
                bins=20,
                max_groups=5,
                min_vol_ratio=0.05,
                max_crossings=3,
                time_col="safra",
                oot_date="2025-01",
            )
        note([f"[{w.category.__name__}] {w.message}" for w in caught])
        letters = {i: chr(64 + i) for i in range(1, 27)}
        report = rating.report.copy()
        report["grade"] = report["risk_rating"].map(letters)
        result["rating"] = {
            "n_groups": int(rating.n_groups),
            "rows": [
                {
                    "grade": r["grade"],
                    "period": r["period"],
                    "pd": float(r["pd"]),
                    "volume": float(r.get("volume", r.get("count", float("nan")))),
                }
                for r in report.to_dict("records")
            ],
        }
    except Exception as exc:  # keep the JSON usable even if rating fails on one side
        result["rating"] = {"error": f"{type(exc).__name__}: {exc}"}
        note([f"[rating] {type(exc).__name__}: {exc}"])

    result["notes"] = notes

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, ensure_ascii=False, default=float)
    return result


def run_cli(adapter, generate_fn):
    """Shared argparse entry point for both measure scripts."""
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["A", "B"], required=True)
    p.add_argument("--n", type=int, default=60_000)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--frame", default=None, help="parquet path (mode B)")
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if args.mode == "A":
        base = generate_fn(n_applicants=args.n, seed=args.seed)
    else:
        if not args.frame:
            p.error("--frame is required in mode B")
        base = pd.read_parquet(args.frame)

    res = measure(adapter, base, args.mode, args.seed, args.out)
    print(
        f"{adapter.name} mode {args.mode} n={len(base)}: "
        f"incumbent approval {res['incumbent']['approval']:.3f} "
        f"default {res['incumbent']['default']:.3f} -> {args.out}"
    )
