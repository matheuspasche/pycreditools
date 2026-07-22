"""Validation harness must not dilute blended defaults with no-outcome keep-ins.

Issue #95 — sibling of the engine-side #97. The harness in ``validation/common.py``
weighted defaults by the FULL contracted volume, so an approved-but-never-contracted
keep-in (``simulated_default`` NaN, ``new_approval`` 1.0) dropped out of the numerator
via ``.sum()`` yet kept its weight in the denominator, deflating every rate — and the
same leak survived one level up in ``segmented_total``'s regional re-blend.

These tests pin the fix at the metric chokepoints AND prove the runtime guard
(``_assert_undiluted``) actually raises when a diluted figure is fed to it, so the
protection can't rot into a no-op. Pure DataFrame fixtures — no engine, deterministic.
"""

import numpy as np
import pandas as pd
import pytest

from validation import common


def _sim_frame() -> pd.DataFrame:
    # 3 observed keep-ins (defaults 0,0,1 -> 1/3), 1 no-outcome keep-in (NaN but
    # contracted), 1 swap-in (imputed PD 0.2). All contracted (new_approval=1).
    return pd.DataFrame(
        {
            "approved_pre_rate": [1.0, 1.0, 1.0, 1.0, 1.0],
            "new_approval": [1.0, 1.0, 1.0, 1.0, 1.0],
            "simulated_default": [0.0, 0.0, 1.0, np.nan, 0.2],
            "actual_default": [0.0, 0.0, 1.0, np.nan, np.nan],
            "scenario": ["keep_in", "keep_in", "keep_in", "keep_in", "swap_in"],
        }
    )


def test_kpis_default_excludes_no_outcome_keepin():
    k = common.kpis(_sim_frame())
    # Masked blend over the 4 outcome-known rows: (0+0+1+0.2)/4 = 0.30.
    # Diluted (full denom 5) would read 1.2/5 = 0.24.
    assert k["default"] == pytest.approx(0.30)
    assert k["contracted"] == pytest.approx(5.0)          # full volume, all approved
    assert k["contracted_observed"] == pytest.approx(4.0)  # weight matching the rate


def test_stressed_default_excludes_no_outcome_keepin():
    # Only the swap-in row is stressed: 0.2 * 1.5 = 0.3. Blend over observed book:
    # (0+0+1+0.3)/4 = 0.325.
    assert common.stressed_default(_sim_frame(), 1.5) == pytest.approx(0.325)


def test_quadrant_sim_excludes_no_outcome_keepin():
    q = common.quadrant_table(_sim_frame())
    # keep_in group: observed defaults 0,0,1 over 3 known rows -> 1/3, NOT /4.
    assert q["keep_in"]["sim"] == pytest.approx(1 / 3)
    assert q["keep_in"]["vol"] == pytest.approx(4.0)  # volume still counts all keep-ins


def test_segmented_reblend_uses_observed_weight():
    # Two "regions" with different no-outcome mixes. The aggregate blend must weight
    # each region's rate by its OBSERVED contracted volume, else the region heavy in
    # no-outcome keep-ins re-dilutes the total (#95, aggregate level).
    r1 = {"default": 0.30, "contracted": 5.0, "contracted_observed": 4.0}
    r2 = {"default": 0.10, "contracted": 3.0, "contracted_observed": 1.0}
    num = r1["default"] * r1["contracted_observed"] + r2["default"] * r2["contracted_observed"]
    den = r1["contracted_observed"] + r2["contracted_observed"]
    correct = num / den                     # 1.3 / 5 = 0.26
    diluted = (r1["default"] * r1["contracted"] + r2["default"] * r2["contracted"]) / (
        r1["contracted"] + r2["contracted"]
    )                                        # 1.8 / 8 = 0.225
    assert correct == pytest.approx(0.26)
    assert diluted != pytest.approx(correct)  # the two weightings genuinely differ


def test_guard_raises_on_diluted_default():
    d = _sim_frame()
    # 0.24 is the diluted figure (full denom); the masked oracle is 0.30 -> must raise.
    with pytest.raises(AssertionError, match="diluted blended default"):
        common._assert_undiluted(0.24, d["simulated_default"], d["new_approval"], "test")
    # The correct value passes through untouched.
    assert common._assert_undiluted(0.30, d["simulated_default"], d["new_approval"], "test") == 0.30


def test_guard_can_be_disabled(monkeypatch):
    monkeypatch.setattr(common, "VALIDATE_INVARIANTS", False)
    d = _sim_frame()
    # With the guard off, a wrong figure passes through unchecked.
    assert common._assert_undiluted(0.24, d["simulated_default"], d["new_approval"], "test") == 0.24
