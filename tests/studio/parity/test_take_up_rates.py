"""Taxas v2: sugerir/angular/múltiplas (issue #35, ADR 0001).

Acceptance criteria:
  (a) suggested_take_up_rate computes hired/approved from the data.
  (b) angled_rate_variable gives a higher multiplier for worse (lower) scores.
  (c) two chained rate stages compose multiplicatively on the funnel.
"""

import dataclasses

import pytest

from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    angled_rate_variable,
    build_policy,
    make_cutoff_row,
    make_rate_row,
    suggested_take_up_rate,
)

# ---------------------------------------------------------------------------
# (a) suggested rate = hired-among-approved / total-approved
# ---------------------------------------------------------------------------


def test_suggested_rate_is_hired_over_approved(sample_df, roles):
    """suggested_take_up_rate returns mean(hired | approved==1) from the raw dataset."""
    rate = suggested_take_up_rate(sample_df, roles)
    assert rate is not None
    approved_mask = sample_df[roles.current_approval_col] == 1
    expected = float(sample_df.loc[approved_mask, roles.current_hired_col].mean())
    assert rate == pytest.approx(expected)


def test_suggested_rate_is_none_without_hired_col(sample_df, roles):
    """Returns None gracefully when the hired column is not mapped."""
    no_hired = dataclasses.replace(roles, current_hired_col=None)
    assert suggested_take_up_rate(sample_df, no_hired) is None


def test_suggested_rate_is_none_without_approval_col(sample_df, roles):
    """Returns None gracefully when the approval column is not mapped (Tier C)."""
    no_approval = dataclasses.replace(roles, current_approval_col=None)
    assert suggested_take_up_rate(sample_df, no_approval) is None


# ---------------------------------------------------------------------------
# (b) angled rate variable: lower score => higher multiplier
# ---------------------------------------------------------------------------


def test_angled_variable_is_higher_for_worse_scores(sample_df, roles):
    """angled_rate_variable: eval on df gives higher multiplier for lower (worse) scores."""
    from pycreditools.expressions import Expression

    score_col = roles.score_cols[-1]  # e.g. "score_5"
    expr = angled_rate_variable(sample_df, score_col)

    assert isinstance(expr, Expression)

    multipliers = expr.eval(sample_df)
    # The median score row should sit near 1.0 (neutral multiplier)
    # Lower score rows should have multiplier above the median multiplier
    sorted_by_score = sample_df[[score_col]].assign(mult=multipliers).sort_values(score_col)
    low_mult = sorted_by_score["mult"].iloc[: len(sorted_by_score) // 4].mean()
    high_mult = sorted_by_score["mult"].iloc[3 * len(sorted_by_score) // 4 :].mean()
    assert low_mult > high_mult, (
        "Lower-score rows must get a higher angled multiplier (worse score => more seekers)"
    )


def test_angled_variable_keeps_effective_rate_in_unit_interval(sample_df, roles):
    """base_rate * angled_variable clipped stays in [0, 1] for typical base rates."""
    score_col = roles.score_cols[-1]
    expr = angled_rate_variable(sample_df, score_col)
    multipliers = expr.eval(sample_df)

    base_rate = 0.5
    effective = (base_rate * multipliers).clip(0.0, 1.0)
    assert (effective >= 0.0).all()
    assert (effective <= 1.0).all()


def test_angled_variable_respects_custom_spread(sample_df, roles):
    """Spread parameter controls the amplitude of variation around 1.0."""
    score_col = roles.score_cols[-1]
    for spread in (0.2, 0.4):
        expr = angled_rate_variable(sample_df, score_col, spread=spread)
        multipliers = expr.eval(sample_df)
        # Multipliers should fall within [1-spread, 1+spread]
        assert float(multipliers.min()) == pytest.approx(1.0 - spread, abs=1e-6)
        assert float(multipliers.max()) == pytest.approx(1.0 + spread, abs=1e-6)


# ---------------------------------------------------------------------------
# (c) two chained rate stages compose multiplicatively on the funnel
# ---------------------------------------------------------------------------


def test_two_chained_rate_stages_compose_multiplicatively(sample_df, roles):
    """Adding two RateStage rows yields funnel volume = base * r1 * r2 (analytical mode)."""
    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    r1, r2 = 0.8, 0.75

    single_row = [
        make_cutoff_row(name="Corte", cutoffs={score_col: float(subset[score_col].quantile(0.5))}),
        make_rate_row(name="Taxa aceite", base_rate=r1 * r2),
    ]
    chained_rows = [
        make_cutoff_row(name="Corte", cutoffs={score_col: float(subset[score_col].quantile(0.5))}),
        make_rate_row(name="Taxa aceite", base_rate=r1),
        make_rate_row(name="Anti-fraude", base_rate=r2),
    ]

    single_sim = build_policy(roles, single_row).simulate(subset, method="analytical")
    chained_sim = build_policy(roles, chained_rows).simulate(subset, method="analytical")

    # new_approval = cumulative pass probability; the two chains should give identical totals
    single_total = float(single_sim.data["new_approval"].sum())
    chained_total = float(chained_sim.data["new_approval"].sum())
    assert single_total == pytest.approx(chained_total, rel=1e-6)


def test_chained_rates_each_reduce_the_funnel_beyond_the_previous(sample_df, roles):
    """Each additional rate stage strictly shrinks the funnel (anti-oversizing proof)."""
    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    cutoff_val = float(subset[score_col].quantile(0.5))

    rows_no_rate = [make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val})]
    rows_one_rate = rows_no_rate + [make_rate_row(name="Taxa 1", base_rate=0.8)]
    rows_two_rates = rows_one_rate + [make_rate_row(name="Taxa 2", base_rate=0.9)]

    sim0 = build_policy(roles, rows_no_rate).simulate(subset, method="analytical")
    sim1 = build_policy(roles, rows_one_rate).simulate(subset, method="analytical")
    sim2 = build_policy(roles, rows_two_rates).simulate(subset, method="analytical")

    v0 = float(sim0.data["new_approval"].sum())
    v1 = float(sim1.data["new_approval"].sum())
    v2 = float(sim2.data["new_approval"].sum())
    assert v1 < v0, "first rate stage must shrink the funnel"
    assert v2 < v1, "second rate stage must shrink beyond the first"
