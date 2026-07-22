"""Ablation-ladder core for issue #93 — engine-agnostic.

Imported by ``run_ladder_main.py`` / ``run_ladder_v05.py``. Each runner supplies
the branch's ``CreditPolicy`` / ``col`` (imported from its own worktree venv) and
loops the declared steps. This module owns the DECLARATIVE ladder: what each
step adds, which invariants it compares, and the tolerance for each — all frozen
BEFORE any run (principle #5). The comparator lives here too.

Design decisions locked with the issue owner (deviating from the issue text,
recorded in README):

  * Opção B — ``current_approval_col`` is ON from L0. The swap-in population
    exists at every step; the imputed swap-in PD is a compared invariant from L0.
  * ``calibration_bins=10`` FIXED on every step, matching the 10-decile summary
    table. Same band for calibration and for the table => the swap/keep default
    ratio equals the stress factor EXACTLY, row by row (sanity check).
  * The issue's calibration-sweep rungs (L4 default-decile, L5 bins=5) collapse
    into this fixed choice, so the ladder is 6 rungs: L0 cutoff, L1 hard filters,
    L2 antifraud scalar, L3 risk-graded take-up, L4 stress x1.5, L5 regional.

Every metric comes from ``policy.simulate(...).data`` — no sweep fast-path
(principle #4).
"""

from __future__ import annotations

import hashlib
import warnings

import numpy as np
import pandas as pd

# Fixed challenger hard-filter set (the v0.5 suggester's pick — #91). Identical
# expression on both engines (principle #3).
HF_RULES = [
    ("vl_negativacao", "lte", 0),
    ("vl_vencido_scr", "lte", 0),
    ("vl_protestos", "lte", 0),
]
SCORE_COL = "score_5"
CALIBRATION_BINS = 10
STRESS_FACTOR = 1.5
# Regional cutoff search grid (L5): quantiles of score_5 within each region.
REGION_QUANTILES = np.linspace(0.30, 0.95, 27)

STEPS = ["L0", "L1", "L2", "L3", "L4", "L5"]
STEP_ADDS = {
    "L0": "cutoff only",
    "L1": "+ hard filters",
    "L2": "+ antifraud scalar rate",
    "L3": "+ risk-graded take_up_rate (variable=)",
    "L4": "+ stress x1.5",
    "L5": "+ regional segmentation",
}

# Tolerance per invariant per step, declared up front. "exact" => byte/int/hash
# equality; a float => abs-delta epsilon. Invariants not listed for a step are
# not compared at that step.
_EXACT = "exact"
TOL = {
    "L0": {"approval": _EXACT, "approved_ids_sha": _EXACT, "quadrant_counts": _EXACT,
           "keep_in_inad": 1e-4, "swap_in_pd": 1e-4, "blended_default": 1e-4},
    "L1": {"approval": _EXACT, "approved_ids_sha": _EXACT, "hf_pass_rate": _EXACT,
           "quadrant_counts": _EXACT, "keep_in_inad": 1e-4, "swap_in_pd": 1e-4,
           "blended_default": 1e-4},
    "L2": {"approval": _EXACT, "approved_ids_sha": _EXACT, "contracted": 1e-9,
           "blended_default": 1e-4, "swap_in_pd": 1e-4},
    "L3": {"approval": _EXACT, "approved_ids_sha": _EXACT, "contracted": 1e-9,
           "blended_default": 1e-9, "swap_in_pd": 1e-4, "effective_rate_by_decile": 1e-9},
    "L4": {"approval": _EXACT, "contracted": 1e-9, "blended_default": 1e-9,
           "swap_in_pd": 1e-9, "stress_ratio_ok": _EXACT},
    "L5": {"region_cutoffs": _EXACT, "segmented_approval": 1e-4, "segmented_default": 1e-4},
}


# ── policy builders ──────────────────────────────────────────────────────────
def hf_expr(col):
    e = None
    for c, direction, thr in HF_RULES:
        term = (col(c) <= thr) if direction == "lte" else (col(c) >= thr)
        e = term if e is None else (e & term)
    return e


def base_policy(CreditPolicy):
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=(SCORE_COL,),
        current_approval_col="approved",   # Opção B: swap flow ON from L0
        actual_default_col="actual_default",
        calibration_bins=CALIBRATION_BINS,  # fixed 10, matches the decile table
    )


def build_policy(step: str, CreditPolicy, col, cutoff: int, antifraud_rate: float):
    """Return the policy for a ladder step. Each step = previous + ONE component."""
    p = base_policy(CreditPolicy)
    if step != "L0":  # L1+ : hard filters
        p = p.filter("Hard filters", hf_expr(col))
    p = p.cutoff("Challenger cutoff", {SCORE_COL: float(cutoff)}, direction="gte")
    if step in ("L2", "L3", "L4", "L5"):  # antifraud scalar
        p = p.rate("Anti-fraud", base_rate=float(antifraud_rate))
    if step in ("L3", "L4", "L5"):  # risk-graded take-up, SAME mechanism both sides
        p = p.rate("Take-up", base_rate=1.0, variable="take_up_rate")
    if step in ("L4", "L5"):  # stress
        p = p.stress(STRESS_FACTOR)
    return p


# ── measurement ──────────────────────────────────────────────────────────────
def _simulate(policy, base):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sim = policy.simulate(base, method="analytical")
    msgs = [f"[{w.category.__name__}] {w.message}" for w in caught]
    return sim.data, msgs


def _wmean(values: pd.Series, weights: pd.Series) -> float:
    """Weighted mean over rows with a KNOWN outcome only.

    Keep-ins are classified by the approval DECISION, so a keep-in that was
    approved-but-never-contracted (``actual_default`` is NaN) stays a keep-in —
    but it carries no default outcome. No inadimplência parameter may be computed
    over it: it must drop out of BOTH numerator and denominator, otherwise the
    unpaid book silently deflates every rate. So we mask to ``notna`` here."""
    m = values.notna()
    v, w = values[m], weights[m]
    tot = float(w.sum())
    return float((v * w).sum() / tot) if tot else float("nan")


def kpis(d: pd.DataFrame) -> dict:
    n = len(d)
    approved = float(d["approved_pre_rate"].sum())
    contracted = float(d["new_approval"].sum())
    return {
        "approval": approved / n if n else float("nan"),
        "contracted": contracted,
        "blended_default": _wmean(d["simulated_default"], d["new_approval"]),
        "take_up": contracted / approved if approved else float("nan"),
    }


def approved_ids_sha(d: pd.DataFrame) -> str:
    ids = np.sort(d.loc[d["approved_pre_rate"] > 0, "applicant_id"].to_numpy())
    return hashlib.sha256(ids.tobytes()).hexdigest()


def quadrant_counts(d: pd.DataFrame) -> dict:
    if "scenario" not in d.columns:
        return {}
    return {str(k): int(v) for k, v in d["scenario"].value_counts().items()}


def _calibration_bin(d: pd.DataFrame) -> pd.Series:
    """Reproduce the engine's swap-in calibration bins: qcut of the KEEP-IN
    score population into CALIBRATION_BINS quantile bins (calibration_base
    default = keep_in), then bin every row by those same edges. Binning the
    table exactly like the engine is what makes the swap/keep ratio land on the
    stress factor to the last digit."""
    keep = d["scenario"] == "keep_in"
    ks = d.loc[keep, SCORE_COL]
    _, edges = pd.qcut(ks, q=CALIBRATION_BINS, retbins=True, duplicates="drop")
    edges = edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf
    return pd.cut(d[SCORE_COL], bins=edges, labels=False, include_lowest=True)


def decile_table(d: pd.DataFrame) -> list[dict]:
    """The owner's summary: one row per calibration decile, keep-in vs swap-in.

    Columns per bin:
      keep_in_vol/inad   — contracted volume and new_approval-weighted default
                            (portfolio-correct: reconstructs the blend by sumproduct).
      keep_bin_pd        — UNWEIGHTED keep-in default: the exact source the engine
                            imputes each swap-in from (before stress).
      swap_in_vol/inad   — swap-in contracted volume and default.
      conversion         — effective contracted/approved rate in the bin.
      swap_over_keep     — swap_in_inad / keep_bin_pd; equals the stress factor
                            exactly (all swap-ins in a bin share keep_bin_pd*factor).
    """
    keep = d["scenario"] == "keep_in"
    swap = d["scenario"] == "swap_in"
    cbin = _calibration_bin(d)
    rows = []
    for b, g in d.groupby(cbin):
        gi = g.index
        ki = g[keep.loc[gi]]
        si = g[swap.loc[gi]]
        approved_b = float(g["approved_pre_rate"].sum())
        contracted_b = float(g["new_approval"].sum())
        # Two keep-in volumes: the DECISION book (all keep-ins) and the OBSERVED
        # book (keep-ins with a known outcome). inad is a rate over the observed
        # book only; the decision book is reported for transparency, never as an
        # inad denominator.
        ki_obs = ki[ki["simulated_default"].notna()]
        ki_vol_decision = float(ki["new_approval"].sum())
        ki_vol = float(ki_obs["new_approval"].sum())
        si_vol = float(si["new_approval"].sum())
        ki_inad = _wmean(ki["simulated_default"], ki["new_approval"])  # _wmean masks NaN
        si_inad = _wmean(si["simulated_default"], si["new_approval"])
        # Imputation source: UNWEIGHTED observed keep-in default in the bin — what
        # the engine imputes each swap-in from. Used only for the stress-ratio
        # sanity, so the check stays clean regardless of keep-in re-gating.
        keep_bin_pd = float(ki["actual_default"].mean()) if ki["actual_default"].notna().any() else float("nan")
        rows.append({
            "decile": int(b),
            "keep_in_vol": ki_vol,                     # observed (contracted) book
            "keep_in_vol_decision": ki_vol_decision,   # all keep-ins (decision)
            "keep_in_inad": ki_inad,                   # rate over observed keep-ins
            "keep_bin_pd": keep_bin_pd,                # imputation source (unweighted)
            "swap_in_vol": si_vol,
            "swap_in_inad": si_inad,
            "conversion": contracted_b / approved_b if approved_b else float("nan"),
            "swap_over_keep": (si_inad / ki_inad) if ki_inad else float("nan"),
        })
    return rows


def effective_rate_by_decile(d: pd.DataFrame) -> dict:
    out = {}
    for dec, g in d.groupby("score_decile"):
        appr = float(g["approved_pre_rate"].sum())
        out[int(dec)] = float(g["new_approval"].sum()) / appr if appr else float("nan")
    return out


def measure_step(step: str, sim_data: pd.DataFrame) -> dict:
    """All invariants + sanity checks for one step, straight off sim.data."""
    d = sim_data
    k = kpis(d)
    keep = d["scenario"] == "keep_in"
    swap = d["scenario"] == "swap_in"
    keep_in_inad = _wmean(d.loc[keep, "simulated_default"], d.loc[keep, "new_approval"])
    swap_in_pd = _wmean(d.loc[swap, "simulated_default"], d.loc[swap, "new_approval"])
    table = decile_table(d)

    # Sanity #1: portfolio blended default == SUMPRODUCT of the table cells.
    num = den = 0.0
    for r in table:
        for vol, inad in ((r["keep_in_vol"], r["keep_in_inad"]),
                          (r["swap_in_vol"], r["swap_in_inad"])):
            if vol and not np.isnan(inad):
                num += vol * inad
                den += vol
    sumproduct_default = num / den if den else float("nan")
    sumproduct_matches = bool(
        not np.isnan(sumproduct_default)
        and abs(sumproduct_default - k["blended_default"]) < 1e-9
    )

    # Sanity #2 (stress steps): swap-in default == imputation source * factor,
    # row by row. Compared against keep_bin_pd (the UNWEIGHTED observed keep-in
    # default the engine imputes from), so it isolates imputation x stress and is
    # immune to keep-in re-gating (which only moves the weighted keep_in_inad).
    ratios = [r["swap_in_inad"] / r["keep_bin_pd"] for r in table
              if r["swap_in_vol"] and r["keep_bin_pd"] and not np.isnan(r["keep_bin_pd"])]
    stressed = step in ("L4", "L5")
    expected_ratio = STRESS_FACTOR if stressed else 1.0
    stress_ratio_ok = bool(ratios) and all(abs(x - expected_ratio) < 1e-9 for x in ratios)

    m = {
        "step": step,
        "adds": STEP_ADDS[step],
        "approval": k["approval"],
        "contracted": k["contracted"],
        "blended_default": k["blended_default"],
        "take_up": k["take_up"],
        "approved_ids_sha": approved_ids_sha(d),
        "quadrant_counts": quadrant_counts(d),
        "keep_in_inad": keep_in_inad,
        "swap_in_pd": swap_in_pd,
        "effective_rate_by_decile": effective_rate_by_decile(d),
        "decile_table": table,
        "sanity": {
            "sumproduct_default": sumproduct_default,
            "sumproduct_matches_blended": sumproduct_matches,
            "swap_over_keep_ratios": ratios,
            "expected_ratio": expected_ratio,
            "stress_ratio_ok": stress_ratio_ok,
        },
        "stress_ratio_ok": stress_ratio_ok,
    }
    return m


# ── L5: regional segmentation ────────────────────────────────────────────────
def measure_regional(CreditPolicy, col, base: pd.DataFrame, antifraud_rate: float,
                     target_default: float, note) -> dict:
    """Per-region cutoff chosen from a quantile grid to meet a common target
    default (= L4 global blended default), maximizing approval. Compared:
    chosen cutoffs (exact) and the segmented aggregate (1e-4)."""
    regions = []
    seg_appr = seg_contr = seg_wdef = 0.0
    n = len(base)
    for region, sub in base.groupby("region"):
        sub = sub.reset_index(drop=True)
        grid = sorted({int(round(q)) for q in sub[SCORE_COL].quantile(REGION_QUANTILES)})
        best = None
        for cut in grid:
            pol = build_policy("L5", CreditPolicy, col, cut, antifraud_rate)
            sim_data, msgs = _simulate(pol, sub)
            note(msgs)
            k = kpis(sim_data)
            if k["blended_default"] <= target_default and (best is None or k["approval"] > best[1]["approval"]):
                best = (cut, k)
            if best is None:
                best = (cut, k)  # fallback: keep last if none meets target yet
        cut, k = best
        regions.append({
            "region": str(region), "applicants": int(len(sub)), "cutoff": int(cut),
            "approval": k["approval"], "default": k["blended_default"],
            "contracted": k["contracted"],
        })
        seg_appr += k["approval"] * len(sub)
        seg_contr += k["contracted"]
        seg_wdef += k["blended_default"] * k["contracted"]
    return {
        "step": "L5",
        "adds": STEP_ADDS["L5"],
        "target_default": target_default,
        "region_cutoffs": {r["region"]: r["cutoff"] for r in regions},
        "regions": regions,
        "segmented_approval": seg_appr / n if n else float("nan"),
        "segmented_default": seg_wdef / seg_contr if seg_contr else float("nan"),
        "segmented_contracted": seg_contr,
    }


# ── comparator ───────────────────────────────────────────────────────────────
def _delta(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        keys = set(a) | set(b)
        return max((abs(float(a.get(k, np.nan)) - float(b.get(k, np.nan))) for k in keys),
                   default=0.0)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b))
    return 0.0 if a == b else float("inf")


def run_cli(engine_name: str, pct, CreditPolicy, col, l8_notes: dict) -> None:
    """Shared entry point for both runners. Reads the frozen base, runs every
    ladder step, dumps one JSON per step (schema-identical across engines)."""
    import argparse
    import json
    from pathlib import Path

    p = argparse.ArgumentParser()
    p.add_argument("--frame", required=True, help="shared base parquet (built by build_base.py)")
    p.add_argument("--manifest", required=True)
    p.add_argument("--outdir", default="results")
    p.add_argument("--tag", default="", help="filename suffix, e.g. 60k / 1p5m")
    args = p.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)
    base = pd.read_parquet(args.frame)
    base_sha = manifest["sha256"]
    cutoff = int(manifest["challenger_cutoff"])
    antifraud_rate = float(manifest["antifraud_rate"])

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.tag}" if args.tag else ""

    global_default = None  # L4 blended default feeds L5's target
    for step in STEPS:
        notes: list[str] = []

        def note(msgs):
            for msg in msgs:
                if msg not in notes:
                    notes.append(msg)

        if step == "L5":
            m = measure_regional(CreditPolicy, col, base, antifraud_rate, global_default, note)
        else:
            pol = build_policy(step, CreditPolicy, col, cutoff, antifraud_rate)
            sim_data, msgs = _simulate(pol, base)
            note(msgs)
            m = measure_step(step, sim_data)
            if step == "L4":
                global_default = m["blended_default"]

        record = {
            "engine": engine_name,
            "step": step,
            "base_sha256": base_sha,
            "n": int(len(base)),
            "cutoff": cutoff,
            "antifraud_rate": antifraud_rate,
            "calibration_bins": CALIBRATION_BINS,
            "package_version": getattr(pct, "__version__", "n/a"),
            "measured": m,
            "warnings": notes,  # never suppressed (principle: warnings -> report)
        }
        if step == "L5" and l8_notes:
            record["l8_engine_exclusive_notes"] = l8_notes

        out = outdir / f"{step}_{engine_name}{suffix}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False, default=float)
        blended = m.get("blended_default", m.get("segmented_default"))
        print(f"{engine_name} {step}: blended_default={blended} -> {out}")


def compare(main_m: dict, v05_m: dict, step: str) -> list[dict]:
    """One row per invariant: value_main, value_v05, delta, verdict green/red."""
    out = []
    for inv, tol in TOL[step].items():
        a, b = main_m.get(inv), v05_m.get(inv)
        if tol == _EXACT:
            green = (a == b)
            delta = 0.0 if green else float("inf")
        else:
            delta = _delta(a, b)
            green = delta <= float(tol)
        out.append({
            "invariant": inv,
            "tolerance": tol,
            "delta": delta,
            "verdict": "green" if green else "red",
            "main": a if not isinstance(a, dict) else "<dict>",
            "v05": b if not isinstance(b, dict) else "<dict>",
        })
    return out
