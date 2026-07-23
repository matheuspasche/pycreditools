"""Taxas v2: sugerir/angular/múltiplas (issue #35, ADR 0001).

Acceptance criteria:
  (a) suggested_take_up_rate computes hired/approved from the data.
  (b) angled_rate_variable gives a higher multiplier for worse (lower) scores.
  (c) two chained rate stages compose multiplicatively on the funnel.
  (d) angled_rate_variable respects lte direction (issue #47).
  (e) angled rate row representation is clean/serializable (issue #47).
  (f) approval/take-up boundary is by stage type, not position (ADR 0008, #69).
"""

import dataclasses
import json

import pytest

from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    angled_rate_variable,
    build_policy,
    make_angled_rate_row,
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


# ---------------------------------------------------------------------------
# (d) angled rate variable: lte direction — issue #47
# ---------------------------------------------------------------------------


def test_angled_variable_lte_gives_higher_multiplier_for_worse_scores(sample_df, roles):
    """For direction='lte' (lower=better), higher scores are worse → must get higher multiplier."""
    score_col = roles.score_cols[-1]
    expr = angled_rate_variable(sample_df, score_col, direction="lte")

    multipliers = expr.eval(sample_df)
    sorted_by_score = sample_df[[score_col]].assign(mult=multipliers).sort_values(score_col)
    # High-score rows (worse for lte) are in the top quartile
    high_score_mult = sorted_by_score["mult"].iloc[3 * len(sorted_by_score) // 4 :].mean()
    low_score_mult = sorted_by_score["mult"].iloc[: len(sorted_by_score) // 4].mean()
    assert high_score_mult > low_score_mult, (
        "For lte direction, higher-score rows must get a higher multiplier"
        " (worse score => more seekers)"
    )


def test_angled_variable_lte_spread_bounds(sample_df, roles):
    """For lte direction, multipliers also fall within [1-spread, 1+spread]."""
    score_col = roles.score_cols[-1]
    for spread in (0.2, 0.4):
        expr = angled_rate_variable(sample_df, score_col, spread=spread, direction="lte")
        multipliers = expr.eval(sample_df)
        assert float(multipliers.min()) == pytest.approx(1.0 - spread, abs=1e-6)
        assert float(multipliers.max()) == pytest.approx(1.0 + spread, abs=1e-6)


def test_angled_variable_rejects_unknown_direction(sample_df, roles):
    """Unknown direction raises ValueError."""
    with pytest.raises(ValueError, match=r"(?i)dire"):
        angled_rate_variable(sample_df, roles.score_cols[-1], direction="bogus")


# ---------------------------------------------------------------------------
# (e) angled rate row representation: clean schema — issue #47
# ---------------------------------------------------------------------------


def test_make_angled_rate_row_is_json_serializable(roles):
    """make_angled_rate_row returns a plain dict with no live Expression objects."""
    row = make_angled_rate_row(
        name="Taxa angular",
        base_rate=0.6,
        score_col="score_5",
        spread=0.3,
        direction="gte",
    )
    serialized = json.dumps(row)  # must not raise
    assert isinstance(serialized, str)
    assert row["variable"] is None
    assert row["_angled_mode"] is True
    assert row["_angled_score_col"] == "score_5"
    assert row["_angled_spread"] == 0.3
    assert row["_angled_direction"] == "gte"


def test_make_angled_rate_row_lte_direction(roles):
    """make_angled_rate_row preserves the lte direction in the row schema."""
    row = make_angled_rate_row(
        name="Taxa angular lte",
        base_rate=0.5,
        score_col="score_5",
        direction="lte",
    )
    assert row["_angled_direction"] == "lte"
    assert row["type"] == "rate"


# ---------------------------------------------------------------------------
# (f) approval/take-up boundary is by stage type, not position — ADR 0008
#     amended by issue #69
# ---------------------------------------------------------------------------


def test_rate_stage_position_does_not_change_the_metrics(sample_df, roles):
    """A RateStage before vs after a cutoff yields identical approval/take-up KPIs.

    ADR 0008 (amended #69): the boundary is by stage type, not position.
    Reordering stages must not silently change what either metric means.
    """
    from pycreditools.studio.analyses import policy_kpis

    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    cutoff_val = float(subset[score_col].quantile(0.5))

    cutoff_row = make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val})
    rate_row = make_rate_row(name="Anti-fraude", base_rate=0.7)

    rate_after = build_policy(roles, [cutoff_row, rate_row]).simulate(
        subset, method="analytical"
    )
    rate_before = build_policy(roles, [rate_row, cutoff_row]).simulate(
        subset, method="analytical"
    )

    kpis_after = policy_kpis(rate_after)
    kpis_before = policy_kpis(rate_before)

    assert kpis_before["approval_rate"] == pytest.approx(kpis_after["approval_rate"])
    assert kpis_before["take_up_rate"] == pytest.approx(kpis_after["take_up_rate"])
    assert kpis_before["contracted_volume"] == pytest.approx(
        kpis_after["contracted_volume"]
    )


def test_rate_stage_before_cutoff_is_take_up_not_approval(sample_df, roles):
    """A RateStage declared before a cutoff counts as take-up, never as approval.

    ADR 0008 amended by #69: `approval_rate` = deterministic-rule survivors only.
    The rate stage must NOT inflate/deflate approval just because it sits first;
    it must show up in `take_up_rate` instead.
    """
    from pycreditools.studio.analyses import policy_kpis

    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    cutoff_val = float(subset[score_col].quantile(0.5))

    cutoff_row = make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val})
    rate_row = make_rate_row(name="Anti-fraude", base_rate=0.7)

    cutoff_only = build_policy(roles, [cutoff_row]).simulate(subset, method="analytical")
    rate_before_cutoff = build_policy(roles, [rate_row, cutoff_row]).simulate(
        subset, method="analytical"
    )

    kpis_cutoff = policy_kpis(cutoff_only)
    kpis_rate_first = policy_kpis(rate_before_cutoff)

    # approval_rate is unchanged by the leading rate stage: it measures the rule.
    assert kpis_rate_first["approval_rate"] == pytest.approx(
        kpis_cutoff["approval_rate"]
    )
    # ...and the rate stage lands in take-up, shrinking contracted below approved.
    assert kpis_rate_first["take_up_rate"] < 1.0
    assert kpis_rate_first["contracted_volume"] < kpis_cutoff["contracted_volume"]


def test_take_up_rate_is_product_of_all_rate_stages_regardless_of_order(
    sample_df, roles
):
    """`take_up_rate` = product of EVERY RateStage, wherever each sits in the list.

    Guards against a future "the last rate stage" shortcut: two rate stages
    interleaved around a cutoff must give the same take-up as both stacked after it.
    """
    from pycreditools.studio.analyses import policy_kpis

    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    cutoff_val = float(subset[score_col].quantile(0.5))

    cutoff_row = make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val})
    r1 = make_rate_row(name="Anti-fraude", base_rate=0.8)
    r2 = make_rate_row(name="Aceite", base_rate=0.75)

    interleaved = build_policy(roles, [r1, cutoff_row, r2]).simulate(
        subset, method="analytical"
    )
    both_after = build_policy(roles, [cutoff_row, r1, r2]).simulate(
        subset, method="analytical"
    )

    tu_interleaved = policy_kpis(interleaved)["take_up_rate"]
    tu_after = policy_kpis(both_after)["take_up_rate"]
    assert tu_interleaved == pytest.approx(tu_after)


def test_build_policy_angled_row_with_df_reconstructs_expression(sample_df, roles):
    """build_policy with an angled rate row and df reconstructs the Expression without crashing."""
    score_col = roles.score_cols[-1]
    cutoff_val = float(sample_df[score_col].quantile(0.5))
    rows = [
        make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val}),
        make_angled_rate_row(name="Taxa angular", base_rate=0.6, score_col=score_col),
    ]
    from pycreditools import CreditPolicy

    policy = build_policy(roles, rows, df=sample_df)
    assert isinstance(policy, CreditPolicy)
    sim = policy.simulate(sample_df, method="analytical")
    assert "new_approval" in sim.data.columns


def test_build_policy_angled_row_lte_gives_more_approvals_to_high_score(sample_df, roles):
    """Angled lte policy: high-score (worse-for-lte) applicants get higher rate."""
    score_col = roles.score_cols[-1]
    cutoff_val = float(sample_df[score_col].quantile(0.5))

    rows_gte = [
        make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val}),
        make_angled_rate_row(name="Angular gte", base_rate=0.5, score_col=score_col),
    ]
    rows_lte = [
        make_cutoff_row(name="Corte", cutoffs={score_col: cutoff_val}),
        make_angled_rate_row(
            name="Angular lte", base_rate=0.5, score_col=score_col, direction="lte"
        ),
    ]

    sim_gte = build_policy(roles, rows_gte, df=sample_df).simulate(sample_df, method="analytical")
    sim_lte = build_policy(roles, rows_lte, df=sample_df).simulate(sample_df, method="analytical")

    # Among the approved-by-cutoff population, join the two simulations and compare
    # by score band: top half score (gte: better; lte: worse) should have
    # higher new_approval in lte mode than gte mode
    merged = sim_gte.data[["new_approval"]].rename(columns={"new_approval": "gte_approval"}).join(
        sim_lte.data[["new_approval"]].rename(columns={"new_approval": "lte_approval"})
    )
    merged[score_col] = sample_df[score_col]
    high_score = merged[merged[score_col] >= merged[score_col].median()]
    assert high_score["lte_approval"].mean() > high_score["gte_approval"].mean(), (
        "lte angled: high-score rows (worse for lte) must get higher approval rate than gte"
    )
