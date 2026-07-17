"""Unit tests for the extracted score-bin calibration kernel (#79)."""

import numpy as np
import pandas as pd

from pycreditools._kernels import calibrate_by_score_bins


def test_maps_bin_mean_onto_targets():
    # Two clean deciles: low scores default 0.0, high scores default 1.0.
    cal_scores = pd.Series([1, 2, 3, 4, 90, 91, 92, 93])
    cal_values = pd.Series([0, 0, 0, 0, 1, 1, 1, 1])
    target = pd.Series([2, 95], index=["a", "b"])

    out = calibrate_by_score_bins(
        cal_scores, cal_values, cal_scores, target, bins=2, global_fallback=0.5
    )

    assert list(out.index) == ["a", "b"]
    assert out.loc["a"] == 0.0
    assert out.loc["b"] == 1.0


def test_empty_bin_falls_back_to_global():
    # Ref spans 0..100 so both bins have edges, but calibration only fills the low bin.
    ref = pd.Series(np.arange(0, 101))
    cal_scores = pd.Series([1, 2, 3])
    cal_values = pd.Series([0, 0, 0])
    target = pd.Series([2, 99])  # second target lands in the unseen high bin

    out = calibrate_by_score_bins(
        cal_scores, cal_values, ref, target, bins=2, global_fallback=0.42
    )

    assert out.iloc[0] == 0.0
    assert out.iloc[1] == 0.42


def test_accepts_explicit_edge_sequence():
    cal_scores = pd.Series([10, 20, 80, 90])
    cal_values = pd.Series([0, 0, 1, 1])
    target = pd.Series([15, 85])

    out = calibrate_by_score_bins(
        cal_scores, cal_values, cal_scores, target, bins=[50], global_fallback=0.0
    )

    assert out.iloc[0] == 0.0
    assert out.iloc[1] == 1.0


def test_returns_global_on_degenerate_input():
    # All-NaN scores make qcut raise; the kernel swallows and returns the fallback.
    cal_scores = pd.Series([np.nan, np.nan])
    cal_values = pd.Series([1.0, 1.0])
    target = pd.Series([1.0, 2.0, 3.0], index=[7, 8, 9])

    out = calibrate_by_score_bins(
        cal_scores, cal_values, cal_scores, target, bins=5, global_fallback=0.3
    )

    assert list(out.index) == [7, 8, 9]
    assert (out == 0.3).all()


def test_kernel_reads_no_engine_module():
    # The primitive stays pure: no sibling engine import, hence no policy.
    import inspect

    from pycreditools._kernels import calibration

    src = inspect.getsource(calibration)
    assert "policy" not in src
    assert "from .." not in src and "import stages" not in src


def test_expressions_no_longer_imports_stages():
    # #79 closes the stages ↔ expressions cycle.
    import inspect

    from pycreditools import expressions

    src = inspect.getsource(expressions)
    assert "from .stages import" not in src
