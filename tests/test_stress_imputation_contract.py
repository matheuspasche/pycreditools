"""Engine contract: swap-in stress is an EXACT multiply of the imputed PD.

Isolated by the ablation ladder (issue #93). In ``analytical`` mode a swap-in's
``simulated_default`` is not a drawn 0/1 outcome — it is the imputed expectation
``keep_bin_pd`` (the keep-in default rate of the score bin it lands in). Under
``AggravationStress(factor)`` that expectation is multiplied by ``factor`` and
clipped. So two properties hold to the last bit, at any n (no sampling noise):

  1. swap_in default in a bin == clip(keep_bin_pd * factor, 0, 1).
  2. the portfolio blended default == the SUMPRODUCT of the per-bin cells
     (keep-in and swap-in volume x default), i.e. the decile table reconstructs
     the headline.

Both engines pass these (only the keep-in re-gating of a scalar rate diverges —
that is issue #94, an orthogonal concern kept out of this test).
"""

import numpy as np
import pandas as pd

from pycreditools import CreditPolicy
from pycreditools.simulation import run_simulation

FACTOR = 1.5
CAL_BINS = 4


def _frame() -> pd.DataFrame:
    """Keep-ins (approved) carry observed defaults; swap-ins (not approved) share
    the same score range so the calibration bins are clean, with NO observed
    outcome. A low-score => higher-default pattern keeps every bin PD nonzero and
    well below 1.0 (so the stress multiply never clips)."""
    rng = np.arange(2000)
    # Keep-ins: scores 1..1000, approved. Deterministic default pattern whose
    # bin mean is a clean fraction (every k-th row defaults, k varying by score).
    keep_scores = np.linspace(1, 1000, 1000).astype(int)
    # default rate falls with score: ~0.30 at the bottom, ~0.03 at the top.
    p = 0.30 - 0.27 * (keep_scores - 1) / 999.0
    keep_default = (np.arange(1000) % np.maximum(2, np.round(1.0 / p).astype(int)) == 0).astype(float)
    keep = pd.DataFrame({
        "applicant_id": rng[:1000],
        "score": keep_scores,
        "approved": 1,
        "actual_default": keep_default,
    })
    # Swap-ins: scores spread across the same range, NOT approved, unobserved.
    swap = pd.DataFrame({
        "applicant_id": rng[1000:],
        "score": np.linspace(1, 1000, 1000).astype(int),
        "approved": 0,
        "actual_default": np.nan,
    })
    return pd.concat([keep, swap], ignore_index=True)


def _policy() -> CreditPolicy:
    return (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            calibration_bins=CAL_BINS,
        )
        .cutoff("Pull everyone in", {"score": 1}, direction="gte")  # swap-ins become swap_in
        .stress(FACTOR)
    )


def _calibration_bins(d: pd.DataFrame) -> pd.Series:
    """Reproduce the engine's bins: qcut of keep-in scores (calibration_base
    default = keep_in), then bin every row by those edges."""
    keep = d["scenario"] == "keep_in"
    _, edges = pd.qcut(d.loc[keep, "score"], q=CAL_BINS, retbins=True, duplicates="drop")
    edges = edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf
    return pd.cut(d["score"], bins=edges, labels=False, include_lowest=True)


def test_swap_in_stress_is_exact_multiple_of_imputed_pd():
    d = run_simulation(_frame(), _policy(), method="analytical").data
    cbin = _calibration_bins(d)
    keep = d["scenario"] == "keep_in"
    swap = d["scenario"] == "swap_in"

    saw_a_bin = False
    for b, g in d.groupby(cbin):
        gi = g.index
        ki, si = g[keep.loc[gi]], g[swap.loc[gi]]
        if ki.empty or si.empty:
            continue
        saw_a_bin = True
        keep_bin_pd = ki["actual_default"].mean()
        # Every swap-in in the bin shares one imputed baseline -> constant default.
        swap_defaults = si["simulated_default"].to_numpy()
        expected = np.clip(keep_bin_pd * FACTOR, 0.0, 1.0)
        assert np.allclose(swap_defaults, expected, rtol=0.0, atol=1e-12), (
            f"bin {b}: swap-in default {swap_defaults[:3]} != keep_bin_pd*{FACTOR} = {expected}"
        )
    assert saw_a_bin, "no bin held both keep-ins and swap-ins"


def test_blended_default_equals_sumproduct_of_cells():
    d = run_simulation(_frame(), _policy(), method="analytical").data
    cbin = _calibration_bins(d)
    keep = d["scenario"] == "keep_in"
    swap = d["scenario"] == "swap_in"

    def wmean(v, w):
        s = float(w.sum())
        return float((v * w).sum() / s) if s else float("nan")

    blended = wmean(d["simulated_default"], d["new_approval"])

    num = den = 0.0
    for _, g in d.groupby(cbin):
        gi = g.index
        for mask in (keep.loc[gi], swap.loc[gi]):
            cell = g[mask]
            vol = float(cell["new_approval"].sum())
            if vol:
                num += vol * wmean(cell["simulated_default"], cell["new_approval"])
                den += vol
    sumproduct = num / den
    assert np.isclose(sumproduct, blended, rtol=0.0, atol=1e-9)
