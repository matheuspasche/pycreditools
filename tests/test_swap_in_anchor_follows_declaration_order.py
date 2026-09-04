"""#137 — the swap-in PD anchor follows *position*, not the policy's decision.

``_estimate_swap_in_baseline_pd`` (``simulation.py:723``) resolves which score
calibrates the rejects through ``resolve_calibration_score_col``
(``stages.py:158``), a three-rung cascade: explicit ``calibration_score_col`` →
the **last** ``CutoffStage`` cutoff column present in the frame → the **last**
``score_cols`` entry present in the frame.

Rungs two and three are both **positional**. Nothing about tuple order, dict key
order, or stage order carries a business decision, yet each of them moves the
imputed PD of every swap-in — silently, with the funnel's decision untouched.

**Measured 2026-09-04** on the v0.6 engine (`src/pycreditools` is byte-identical
between ``release/v0.5`` and ``release/v0.6``, git tree ``2e72f16``, so this is a
bug **inherited** from v0.5, not a regression). At 3 MM rows the reversed tuple
moves the blended default rate by **−0.70 p.p.** and the swap-ins' imputed PD by
**−1.01 p.p.**, against **0.029 p.p.** of sampling noise at the same point — 24×
the noise, growing with ``n``, and always *downward*: anchoring on a weaker score
compresses the calibration and **understates** credit risk.

**These do not fix the bug.** The repair is already decided upstream — #117/#118
kill ``score_cols`` and the calibration anchor outright — so patching the cascade
on ``release/v0.6`` would be a patch on code that is scheduled to die. The three
guarantee tests are therefore ``xfail(strict=True)``: they state the contract the
v0.6 boundary must satisfy, and they will flip to green (and fail loudly if left
behind) the day the anchor stops being a position. Precedent: #133 /
``test_sweep_rebuild_preserves_stage_fields.py``.

Test form follows the map's third definition-of-done (#111, ruling 2026-09-04):

1. **Reference computed outside the engine** — ``_pandas_decile_reference``
   rebuilds the keep-in → swap-in decile calibration in plain pandas and matches
   the engine *row by row* (``atol=1e-12``). It does not merely show the number
   moved; it names which score the engine actually calibrated on.
2. **Measured at the boundary** — the swap-in PD itself, where the anchor's
   effect saturates, rather than a downstream aggregate that dilutes it.
3. **Negative control** — the same verbs with the anchor *declared*
   (``calibration_score_col``) are order-immune and green, so the xfails are the
   bug speaking and not the harness comparing unlike things.
"""

import numpy as np
import pandas as pd
import pytest

import pycreditools as pct
from pycreditools import CreditPolicy, col
from pycreditools.stages import resolve_calibration_score_col

N_ROWS = 50_000
SEED = 42
GATE = 600.0

#: The score the policy actually decides on — the business reference.
REF = "score_5"
#: A different score on the same base. Carries no decision; only tuple position.
OTHER = "score_3"


@pytest.fixture(scope="module")
def base():
    return pct.generate_sample_data(n_applicants=N_ROWS, seed=SEED)


def _policy(score_cols, **kw):
    """The same funnel every time: one gate, on ``REF``, expressed as a filter."""
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=score_cols,
        current_approval_col="approved",
        actual_default_col="actual_default",
        current_hired_col="hired",
        **kw,
    ).filter("gate", col(REF) >= GATE)


def _simulate(base, policy):
    return policy.simulate(base, method="analytical").data


def _swap_in_pd(frame):
    swap = frame["scenario"] == pct.Quadrant.SWAP_IN.value
    return frame.loc[swap, "simulated_default"]


def _default_rate(frame):
    """The load-bearing formula from ``CONTEXT.md``, in pandas."""
    numerator = (frame["simulated_default"] * frame["new_approval"]).sum()
    observed = frame["simulated_default"].notna()
    return numerator / frame.loc[observed, "new_approval"].sum()


def _pandas_decile_reference(frame, anchor, n_bins=10):
    """Rebuild the keep-in → swap-in decile calibration in plain pandas.

    Deliberately does not call any engine helper — not
    ``calibrate_by_score_bins``, not ``resolve_calibration_score_col``. Comparing
    the engine against another engine path pins coincidence, not contract.
    """
    keep = frame["scenario"] == pct.Quadrant.KEEP_IN.value
    swap = frame["scenario"] == pct.Quadrant.SWAP_IN.value

    cal_scores = frame.loc[keep, anchor]
    cal_values = frame.loc[keep, "actual_default"]
    fallback = cal_values.mean()

    _, edges = pd.qcut(cal_scores, q=n_bins, retbins=True, duplicates="drop")
    edges = edges.copy()
    edges[0], edges[-1] = -np.inf, np.inf

    cal_bin = pd.cut(cal_scores, bins=edges, labels=False, include_lowest=True)
    bin_pd = cal_values.groupby(cal_bin).mean()
    bin_pd = bin_pd.reindex(range(len(edges) - 1)).fillna(fallback)

    target_bin = pd.cut(frame.loc[swap, anchor], bins=edges, labels=False, include_lowest=True)
    return target_bin.map(bin_pd).fillna(fallback).clip(0.0, 1.0)


# --------------------------------------------------------------------------
# The mechanism, proven against a reference computed outside the engine.
# --------------------------------------------------------------------------


def test_engine_calibrates_on_the_last_score_cols_entry(base):
    """Name the anchor the engine used, don't just observe that a number moved.

    Reversing ``score_cols`` leaves the funnel identical, and the engine's
    per-row swap-in PD stops matching the pandas reference anchored on the score
    the policy decides on, and starts matching the one anchored on the tuple's
    last entry — exactly, to ``1e-12``.
    """
    declared_last = _simulate(base, _policy((OTHER, REF)))
    reversed_tuple = _simulate(base, _policy((REF, OTHER)))

    assert np.allclose(
        _swap_in_pd(declared_last).values,
        _pandas_decile_reference(declared_last, REF).values,
        atol=1e-12,
    ), "with REF last in the tuple the engine calibrates on REF"

    assert np.allclose(
        _swap_in_pd(reversed_tuple).values,
        _pandas_decile_reference(reversed_tuple, OTHER).values,
        atol=1e-12,
    ), "reversing the tuple re-anchors the calibration onto OTHER"

    assert not np.allclose(
        _swap_in_pd(reversed_tuple).values,
        _pandas_decile_reference(reversed_tuple, REF).values,
        atol=1e-6,
    ), "and it is no longer calibrating on the score the policy decides on"


def test_the_drift_is_material_and_understates_risk(base):
    """The anchor swap is not a rounding artefact, and it points downward.

    Anchoring on a weaker score compresses the calibration, so the imputed PD of
    the rejects — and the blended default rate built on it — come out **too low**.
    Understatement is the dangerous direction for a credit policy.
    """
    declared_last = _simulate(base, _policy((OTHER, REF)))
    reversed_tuple = _simulate(base, _policy((REF, OTHER)))

    d_pd = _swap_in_pd(reversed_tuple).mean() - _swap_in_pd(declared_last).mean()
    d_rate = _default_rate(reversed_tuple) - _default_rate(declared_last)

    assert d_pd < 0, "the re-anchored calibration understates swap-in PD"
    assert d_rate < 0, "and the blended default rate follows it down"
    assert abs(d_pd) > 1e-3, "the drift is basis points, not float noise"


def test_the_decision_never_moves(base):
    """The funnel is untouched: the whole effect lands on the imputed outcome.

    Approval is identical to the last bit across both tuple orders — which is
    what makes this silent. Nothing in the decision surface signals that the risk
    number underneath it changed.
    """
    declared_last = _simulate(base, _policy((OTHER, REF)))
    reversed_tuple = _simulate(base, _policy((REF, OTHER)))

    assert declared_last["approved_pre_rate"].sum() == reversed_tuple["approved_pre_rate"].sum()
    assert declared_last["scenario"].equals(reversed_tuple["scenario"])


# --------------------------------------------------------------------------
# Negative control: the same verbs, with the anchor declared, are order-immune.
# --------------------------------------------------------------------------


def test_declared_anchor_is_immune_to_tuple_order(base):
    """Rung one of the cascade holds — so the xfails below are the bug, not the rig.

    With ``calibration_score_col`` set, tuple order stops mattering and the two
    frames agree exactly. Without this control, "the numbers differ" would only
    show the harness comparing two unlike things.
    """
    a = _simulate(base, _policy((OTHER, REF), calibration_score_col=REF))
    b = _simulate(base, _policy((REF, OTHER), calibration_score_col=REF))

    assert np.allclose(_swap_in_pd(a).values, _swap_in_pd(b).values, atol=1e-12)
    assert _default_rate(a) == pytest.approx(_default_rate(b), abs=1e-12)


def test_a_single_cutoff_gate_masks_the_tuple_order(base):
    """Why the bug was reported as a suspicion and not a measurement.

    Rung two — the last ``CutoffStage`` column — fires before the tuple is ever
    consulted, so a ``.cutoff``-gated policy is order-immune *by accident*. The
    originally proposed reproduction gated on ``.cutoff`` and therefore could not
    show the drift. It is ``.filter``-gated policies that fall through to the
    tuple — and #129 retires ``.cutoff`` in favour of ``.filter`` as the single
    verb, which would make that fall-through the only path left.
    """

    def cutoff_policy(score_cols):
        return CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=score_cols,
            current_approval_col="approved",
            actual_default_col="actual_default",
            current_hired_col="hired",
        ).cutoff("gate", {REF: GATE}, direction="gte")

    a = _simulate(base, cutoff_policy((OTHER, REF)))
    b = _simulate(base, cutoff_policy((REF, OTHER)))

    assert resolve_calibration_score_col(cutoff_policy((REF, OTHER)), base) == REF
    assert np.allclose(_swap_in_pd(a).values, _swap_in_pd(b).values, atol=1e-12)


# --------------------------------------------------------------------------
# The contract the v0.6 boundary owes. Red today, by construction.
# --------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="#137: rung 3 of the cascade — the last score_cols entry — anchors "
    "the swap-in calibration. Fixed upstream by #117/#118 killing the anchor.",
)
def test_tuple_order_does_not_move_the_imputed_pd(base):
    """``score_cols`` declares which columns *are* scores, not which one decides."""
    a = _simulate(base, _policy((OTHER, REF)))
    b = _simulate(base, _policy((REF, OTHER)))

    assert np.allclose(_swap_in_pd(a).values, _swap_in_pd(b).values, atol=1e-12)


@pytest.mark.xfail(
    strict=True,
    reason="#137: rung 2 of the cascade is positional too — the last key of the "
    "cutoffs dict wins. Fixed upstream by #117/#118 killing the anchor.",
)
def test_cutoff_dict_key_order_does_not_move_the_imputed_pd(base):
    """One stage, two gated scores: dict insertion order must not pick the anchor.

    Wider than the card's title, which named only the tuple. A ``dict`` literal's
    key order is a keystroke, and it re-anchors the whole reject calibration.
    """

    def two_cutoffs(order):
        return CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=(OTHER, REF),
            current_approval_col="approved",
            actual_default_col="actual_default",
            current_hired_col="hired",
        ).cutoff("gate", {k: v for k, v in order}, direction="gte")

    a = _simulate(base, two_cutoffs([(OTHER, 550.0), (REF, GATE)]))
    b = _simulate(base, two_cutoffs([(REF, GATE), (OTHER, 550.0)]))

    assert np.allclose(_swap_in_pd(a).values, _swap_in_pd(b).values, atol=1e-12)


@pytest.mark.xfail(
    strict=True,
    reason="#137: rung 2 also reads stage order — the later CutoffStage wins. "
    "Fixed upstream by #117/#118 killing the anchor.",
)
def test_stage_order_does_not_move_the_imputed_pd(base):
    """Two gates that commute in the funnel must commute in the calibration too.

    Both orders approve exactly the same applicants — an ``and`` of two
    thresholds — so any difference in the imputed PD comes from the ordering
    alone.
    """

    def two_stages(first, second):
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=(OTHER, REF),
            current_approval_col="approved",
            actual_default_col="actual_default",
            current_hired_col="hired",
        )
        for name, score, gate in (first, second):
            policy = policy.cutoff(name, {score: gate}, direction="gte")
        return policy

    weak = ("weak", OTHER, 550.0)
    strong = ("strong", REF, GATE)

    a = _simulate(base, two_stages(weak, strong))
    b = _simulate(base, two_stages(strong, weak))

    assert a["approved_pre_rate"].sum() == b["approved_pre_rate"].sum()
    assert np.allclose(_swap_in_pd(a).values, _swap_in_pd(b).values, atol=1e-12)
