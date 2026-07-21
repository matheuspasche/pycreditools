"""Behaviour of :func:`suggest_hard_filters` (#73).

The suggester is consultative: the full table always returns and the greedy set is a
base to parametrize from. These tests pin the spec's guarantees — planted-signal
recovery, the set-level budget, marginal (not summed) cuts, the two-population split,
the honest-scope warnings, and the sorted+cumsum performance floor.
"""

from __future__ import annotations

import time
import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import (
    CreditPolicy,
    CutoffStage,
    generate_sample_data,
    generate_standalone_sample_data,
    suggest_hard_filters,
)
from pycreditools.screening import HardFilterSuggestion, _hf_column_table

BUREAU = {
    "vl_negativacao": "lte",
    "vl_vencido_scr": "lte",
    "vl_protestos": "lte",
    "age": "gte",
    "income": "gte",
}


@pytest.fixture(scope="module")
def incumbent() -> pd.DataFrame:
    return generate_sample_data(n_applicants=60_000, seed=42)


def _suggest(df: pd.DataFrame, **kw) -> HardFilterSuggestion:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return suggest_hard_filters(df, **kw)


def test_planted_signal_recovery(incumbent: pd.DataFrame) -> None:
    """The negativação / SCR / protestos columns are suggested; age loses on lift,
    income on IV."""
    s = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=0.40
    )
    suggested = set(s.rule_set["column"])
    assert {"vl_negativacao", "vl_vencido_scr", "vl_protestos"} <= suggested

    reasons = dict(zip(s.rejected["column"], s.rejected["reason"]))
    assert "age" in reasons and "lift" in reasons["age"]
    assert "income" in reasons and "IV" in reasons["income"]


def test_whole_table_always_returned(incumbent: pd.DataFrame) -> None:
    """Every declared column appears in the table, rejected ones included."""
    s = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=0.40
    )
    assert set(s.table["column"]) == set(BUREAU)


def test_degenerate_column_accounted_for_not_dropped(incumbent: pd.DataFrame) -> None:
    """A declared column with no usable cut (constant) must not vanish silently — it
    is accounted for in .rejected, honouring 'always return the whole table'."""
    df = incumbent.copy()
    df["const_col"] = 5  # every threshold rejects nobody or everybody
    s = _suggest(
        df,
        bad_col="actual_default",
        directions={"vl_negativacao": "lte", "const_col": "lte"},
        hf_approval_floor=0.40,
    )
    # Not in the table (no non-degenerate threshold exists)...
    assert "const_col" not in set(s.table["column"])
    # ...but every declared column is accounted for somewhere.
    accounted = set(s.rule_set["column"]) | set(s.rejected["column"])
    assert {"vl_negativacao", "const_col"} <= accounted
    reason = s.rejected.set_index("column").loc["const_col", "reason"]
    assert "degenerate" in reason


def test_budget_reports_spent_and_remaining(incumbent: pd.DataFrame) -> None:
    """.budget exposes spent (union cut) and remaining (headroom), not just the
    standing approval rate — spec: '.budget reports spent and remaining'."""
    s = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=0.40
    )
    assert set(s.budget) == {"floor", "spent", "approval_rate", "headroom"}
    assert s.budget["spent"] == pytest.approx(1.0 - s.budget["approval_rate"])
    # Spent matches the last rule's cumulative cut on the base.
    assert s.budget["spent"] == pytest.approx(s.rule_set.iloc[-1]["cumulative_cut"])


def test_budget_binds_on_the_set(incumbent: pd.DataFrame) -> None:
    """A floor that leaves room for only two rules must not select the third; the
    set stops on the budget and .budget reports the standing approval rate."""
    loose = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=0.40
    )
    assert len(loose.rule_set) >= 3  # baseline: three fit at a 40% floor

    # A floor just above what two rules leave standing bars the third.
    two_rules_leave = 1.0 - loose.rule_set.iloc[1]["cumulative_cut"]
    three_rules_leave = 1.0 - loose.rule_set.iloc[2]["cumulative_cut"]
    floor = (two_rules_leave + three_rules_leave) / 2

    s = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=floor
    )
    assert len(s.rule_set) == 2
    assert s.budget["approval_rate"] >= floor
    assert s.budget["headroom"] == pytest.approx(s.budget["approval_rate"] - floor)
    # The third column is rejected on the budget, never silently trimmed to fit.
    dropped = loose.rule_set.iloc[2]["column"]
    reason = s.rejected.set_index("column").loc[dropped, "reason"]
    assert "budget" in reason


def test_marginal_not_summed() -> None:
    """Two heavily overlapping columns must not both spend their standalone cut; the
    accumulated cut equals the union, and is strictly below the naive sum."""
    rng = np.random.default_rng(0)
    n = 40_000
    base = rng.choice([0, 1], n, p=[0.6, 0.4]) * rng.lognormal(7.0, 1.0, n)
    # near-duplicate of `base`, so the two rules reject almost the same rows
    twin = base + rng.normal(0, 1.0, n)
    y = ((base > 0).astype(float) * 0.8 + rng.random(n) * 0.4 > 0.7).astype(float)
    df = pd.DataFrame({"a": base, "b": twin, "bad": y})

    s = _suggest(
        df, bad_col="bad", directions={"a": "lte", "b": "lte"}, hf_approval_floor=0.20
    )
    assert len(s.rule_set) == 2
    accumulated = s.rule_set.iloc[-1]["cumulative_cut"]
    naive_sum = s.rule_set["cut_volume"].sum()
    assert accumulated < naive_sum  # overlap double-counts in the sum

    # The union computed independently must match the reported cumulative cut.
    masks = []
    for _, r in s.rule_set.iterrows():
        vals = df[r["column"]].to_numpy(float)
        masks.append(vals > r["threshold"])
    union = np.logical_or.reduce(masks).mean()
    assert accumulated == pytest.approx(union)


def test_floor_out_of_range_raises(incumbent: pd.DataFrame) -> None:
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="hf_approval_floor"):
            suggest_hard_filters(
                incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=bad
            )


def test_impossible_floor_returns_empty_set(incumbent: pd.DataFrame) -> None:
    """A floor so high no rule fits returns an empty rule_set — never an error — with
    every passing candidate rejected on the budget."""
    s = _suggest(
        incumbent, bad_col="actual_default", directions=BUREAU, hf_approval_floor=0.999
    )
    assert s.rule_set.empty
    # Columns that clear the floors but not the ~0.1% budget lose on budget.
    budget_rejected = s.rejected[s.rejected["reason"].str.contains("budget")]
    assert {"vl_negativacao", "vl_vencido_scr", "vl_protestos"} <= set(
        budget_rejected["column"]
    )


def test_zero_inflated_column_produces_candidates(incumbent: pd.DataFrame) -> None:
    """78% of vl_negativacao is 0; distinct values still yield candidates."""
    frac_zero = (incumbent["vl_negativacao"] == 0).mean()
    assert frac_zero > 0.5
    s = _suggest(
        incumbent,
        bad_col="actual_default",
        directions={"vl_negativacao": "lte"},
        hf_approval_floor=0.40,
    )
    assert (s.table["column"] == "vl_negativacao").sum() > 1


def test_continuous_bad_col_same_table_shape() -> None:
    """A continuous PD bad_col yields the same table shape as a 0/1 flag."""
    df = generate_standalone_sample_data(n_applicants=20_000, seed=42)
    directions = {"vl_negativacao": "lte", "vl_protestos": "lte"}

    flag = _suggest(
        df, bad_col="actual_default", directions=directions, hf_approval_floor=0.40
    )
    pd_col = _suggest(
        df, bad_col="true_pd", directions=directions, hf_approval_floor=0.40
    )
    assert list(flag.table.columns) == list(pd_col.table.columns)
    assert not pd_col.table.empty


def test_unknown_direction_raises(incumbent: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="lte' or 'gte'"):
        suggest_hard_filters(
            incumbent,
            bad_col="actual_default",
            directions={"vl_negativacao": "down"},
            hf_approval_floor=0.40,
        )


def test_ge_spelling_rejected(incumbent: pd.DataFrame) -> None:
    """'>=' is not a valid spelling — gte is (#71's precedent)."""
    with pytest.raises(ValueError, match="lte' or 'gte'"):
        suggest_hard_filters(
            incumbent,
            bad_col="actual_default",
            directions={"vl_negativacao": ">="},
            hf_approval_floor=0.40,
        )


def test_coverage_warning_fires(incumbent: pd.DataFrame) -> None:
    """actual_default is NaN off the contracted population; the warning reports it."""
    assert incumbent["actual_default"].isna().any()
    with pytest.warns(UserWarning, match="of the base"):
        suggest_hard_filters(
            incumbent,
            bad_col="actual_default",
            directions={"vl_negativacao": "lte"},
            hf_approval_floor=0.40,
        )


def test_incumbent_column_warning_fires(incumbent: pd.DataFrame) -> None:
    """A policy stage already acting on a candidate column warns."""
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        stages=(CutoffStage("neg", {"vl_negativacao": 5000}, "lte"),),
    )
    with pytest.warns(UserWarning, match="policy already acts on"):
        suggest_hard_filters(
            incumbent,
            bad_col="actual_default",
            directions={"vl_negativacao": "lte"},
            hf_approval_floor=0.40,
            policy=policy,
        )


def test_inversion_warns_without_flipping() -> None:
    """When the rejected side is safer than the base, warn — never auto-flip."""
    rng = np.random.default_rng(1)
    n = 20_000
    val = rng.uniform(0, 100, n)
    # High values are SAFER: bad concentrates at low val. Declared lte rejects high,
    # so the rejected side is the safe side — an inversion.
    bad = (rng.random(n) < (1.0 - val / 100.0) * 0.4).astype(float)
    df = pd.DataFrame({"x": val, "bad": bad})

    with pytest.warns(UserWarning, match="inverts against the declared"):
        s = suggest_hard_filters(
            df, bad_col="bad", directions={"x": "lte"}, hf_approval_floor=0.40
        )
    # Direction is reported as declared, not flipped.
    assert set(s.table["direction"]) == {"lte"}


def test_column_clearing_lift_only_outside_budget_rejected_on_budget(
    incumbent: pd.DataFrame,
) -> None:
    """A candidate that clears every floor but not the remaining budget is rejected on
    budget, not trimmed to a smaller cut that would fit."""
    s = _suggest(
        incumbent,
        bad_col="actual_default",
        directions={"vl_negativacao": "lte"},
        hf_approval_floor=0.95,  # ~5% budget; vl_negativacao's cut is larger
    )
    assert s.rule_set.empty
    reason = s.rejected.set_index("column").loc["vl_negativacao", "reason"]
    assert "budget" in reason


def test_performance_does_not_scale_with_grid_size() -> None:
    """The sorted+cumsum path must not scale with grid size: a 1000-point grid on the
    same data costs about the same as a 20-point grid, not 50x more."""
    rng = np.random.default_rng(2)
    n = 300_000
    base_values = rng.lognormal(7.0, 1.5, n)
    contracted = base_values.copy()
    bads = (rng.random(n) < 0.1).astype(float)
    base_default = float(bads.mean())

    def build(points: int) -> float:
        grid = np.unique(np.quantile(base_values, np.linspace(0, 1, points + 1)))
        best = np.inf
        for _ in range(3):
            t0 = time.perf_counter()
            _hf_column_table(
                "x", "lte", base_values, contracted, bads, base_default, 0.1, grid, "q"
            )
            best = min(best, time.perf_counter() - t0)
        return best

    t20 = build(20)
    t1000 = build(1000)
    # Naive per-threshold masking would be ~50x here; the cumsum path stays flat.
    assert t1000 <= 4.0 * t20 + 0.05
