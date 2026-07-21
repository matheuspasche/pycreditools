"""Bancada tracer #1 — política viva + funil (ADR 0001, issue #26).

Also covers the comparison-vs-base core (ADR 0001, 0002; issue #27) and the
risk/time/exposure depth readouts (ADR 0001, 0004; issue #33).
"""

import dataclasses

import pandas as pd
import pytest

from pycreditools import col, run_simulation, summarize_results
from pycreditools.gui import session
from pycreditools.studio.analyses import (
    attach_rating,
    compare_vs_base,
    exposure_kpis,
    policy_kpis,
    policy_vintage_comparison,
    risk_tier_distribution,
    survivor_population,
)
from pycreditools.studio.data import population_filter
from pycreditools.studio.detection import detect_tier
from pycreditools.studio.policy_builder import (
    build_policy,
    make_cutoff_row,
    policy_cache_key,
    v14_quickfill_rows,
)


def _hand_built_v14_policy(roles):
    from pycreditools import CreditPolicy

    policy = CreditPolicy(
        applicant_id_col=roles.applicant_id_col,
        score_cols=tuple(roles.score_cols),
        current_approval_col=roles.current_approval_col,
        actual_default_col=roles.actual_default_col,
        time_col=roles.time_col,
        current_hired_col=roles.current_hired_col,
        estimated_default_col=roles.estimated_default_col,
    )
    return (
        policy.filter("CPF válido", col("cpf_valido") == True)  # noqa: E712
        .filter("Teto de negativação", col("vl_negativacao") <= 1500)
        .filter("Teto de atraso SCR", col("vl_vencido_scr") <= 3000)
        .filter("Teto de protestos", col("vl_protestos") <= 500)
    )


def test_assembling_a_policy_and_simulating_matches_the_v14_funnel_oracle(sample_df, roles):
    """Bancada's live loop: rule rows -> CreditPolicy -> funnel/approval/default."""
    subset = population_filter(sample_df, roles, "Contratados")

    studio_rows = v14_quickfill_rows(sample_df.columns)
    studio_policy = build_policy(roles, studio_rows)
    expected_policy = _hand_built_v14_policy(roles)

    studio_sim = studio_policy.simulate(subset, method="analytical")
    expected_sim = run_simulation(subset, expected_policy, method="analytical")

    pd.testing.assert_frame_equal(
        studio_sim.to_funnel_dataframe(), expected_sim.to_funnel_dataframe()
    )

    page_sim = session.run_policy_sim(
        subset, "parity-hash", "Contratados", studio_policy, policy_cache_key(studio_policy)
    )
    pd.testing.assert_frame_equal(page_sim.data, expected_sim.data)


def test_changing_a_cutoff_changes_the_live_funnel_and_approval_rate(sample_df, roles):
    """Live propagation: any knob change recomputes the funnel (ADR 0001)."""
    subset = population_filter(sample_df, roles, "Todos")
    score_col = roles.score_cols[-1]
    loose_value = float(subset[score_col].min())
    tight_value = float(subset[score_col].quantile(0.9))
    loose_rows = [make_cutoff_row(name="Corte", cutoffs={score_col: loose_value})]
    tight_rows = [make_cutoff_row(name="Corte", cutoffs={score_col: tight_value})]

    loose_sim = build_policy(roles, loose_rows).simulate(subset, method="analytical")
    tight_sim = build_policy(roles, tight_rows).simulate(subset, method="analytical")

    assert tight_sim.data["new_approval"].mean() < loose_sim.data["new_approval"].mean()
    assert not loose_sim.to_funnel_dataframe().equals(tight_sim.to_funnel_dataframe())


def test_survivor_population_is_whoever_passed_every_hard_filter(sample_df, roles):
    """Risk clustering reads survivors, not the raw base (ADR 0001 bullet 4)."""
    subset = population_filter(sample_df, roles, "Todos")
    rows = v14_quickfill_rows(sample_df.columns)
    sim = build_policy(roles, rows).simulate(subset, method="analytical")

    survivors = survivor_population(sim)

    assert len(survivors) < len(subset)
    assert (survivors["reason"] == "Approved").all()
    pd.testing.assert_frame_equal(survivors, sim.data[sim.data["reason"] == "Approved"])


def test_survivor_population_is_the_raw_base_when_the_policy_has_no_hard_filters(
    sample_df, roles
):
    subset = population_filter(sample_df, roles, "Todos")
    sim = build_policy(roles, []).simulate(subset, method="analytical")

    survivors = survivor_population(sim)

    assert len(survivors) == len(subset)


def test_flat_stress_changes_bad_rate_but_not_funnel_volumes(sample_df, roles):
    # "Todos" (not "Contratados") keeps currently-rejected applicants in the mix,
    # so the new policy actually produces swap-ins for the stress factor to affect.
    # `estimated_default_col` is unset because a supplied PD estimate makes the
    # simulator ignore stress scenarios entirely (ground truth overrides them).
    from pycreditools.studio.policy_builder import make_rate_row, make_stress_row

    stress_roles = dataclasses.replace(roles, estimated_default_col=None)
    subset = population_filter(sample_df, stress_roles, "Todos")
    base_rows = v14_quickfill_rows(sample_df.columns) + [
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
        make_rate_row(name="Taxa base", base_rate=0.6),
    ]
    stressed_rows = base_rows + [make_stress_row(factor=1.2)]

    base_sim = build_policy(stress_roles, base_rows).simulate(subset, method="analytical")
    stressed_sim = build_policy(stress_roles, stressed_rows).simulate(subset, method="analytical")

    pd.testing.assert_frame_equal(
        base_sim.to_funnel_dataframe(), stressed_sim.to_funnel_dataframe()
    )

    base_bad = (base_sim.data["simulated_default"] * base_sim.data["new_approval"]).sum()
    stressed_bad = (
        stressed_sim.data["simulated_default"] * stressed_sim.data["new_approval"]
    ).sum()
    assert stressed_bad > base_bad


def _build_sim(df: pd.DataFrame, roles):
    rows = v14_quickfill_rows(df.columns)
    return build_policy(roles, rows).simulate(df, method="analytical")


def test_compare_vs_base_shows_full_swap_and_deltas_in_tier_b(sample_df, roles):
    """Tier B (approval flag only, no vigente score): swap works off the flag alone."""
    tier_b_roles = dataclasses.replace(roles, vigente_score=None)
    subset = population_filter(sample_df, tier_b_roles, "Todos")
    tier = detect_tier(tier_b_roles, subset).tier
    assert tier == "B"
    sim = _build_sim(subset, tier_b_roles)

    result = compare_vs_base(sim, tier_b_roles, tier)

    expected_base_approval = float(subset[tier_b_roles.current_approval_col].mean())
    approved_mask = subset[tier_b_roles.current_approval_col] == 1
    expected_base_bad = float(
        subset.loc[approved_mask, tier_b_roles.actual_default_col].mean()
    )

    assert result["tier"] == "B"
    assert result["base"]["approval_rate"] == pytest.approx(expected_base_approval)
    assert result["base"]["default_rate"] == pytest.approx(expected_base_bad)
    assert result["delta"]["approval_rate"] == pytest.approx(
        result["candidate"]["approval_rate"] - expected_base_approval
    )
    assert result["delta"]["default_rate"] == pytest.approx(
        result["candidate"]["default_rate"] - expected_base_bad
    )
    assert result["quadrants"] is not None
    assert set(result["quadrants"]["scenario"]) == {
        "keep_in",
        "swap_in",
        "swap_out",
        "keep_out",
    }


def test_compare_vs_base_also_shows_full_swap_in_tier_a(sample_df, roles):
    """Tier A (vigente score mapped too): same comparison-vs-base contract holds."""
    tier_a_roles = dataclasses.replace(roles, vigente_score="legacy_score")
    subset = population_filter(sample_df, tier_a_roles, "Todos")
    tier = detect_tier(tier_a_roles, subset).tier
    assert tier == "A"
    sim = _build_sim(subset, tier_a_roles)

    result = compare_vs_base(sim, tier_a_roles, tier)

    assert result["tier"] == "A"
    assert result["base"] is not None
    assert result["delta"] is not None
    assert result["quadrants"] is not None


def test_compare_vs_base_is_standalone_with_no_swap_in_tier_c(sample_df, roles):
    """Tier C (no base mapped): no delta/quadrants — only the standalone candidate."""
    tier_c_roles = dataclasses.replace(roles, current_approval_col=None)
    subset = population_filter(sample_df, tier_c_roles, "Todos")
    tier = detect_tier(tier_c_roles, subset).tier
    assert tier == "C"
    sim = _build_sim(subset, tier_c_roles)

    result = compare_vs_base(sim, tier_c_roles, tier)

    assert result["tier"] == "C"
    assert result["base"] is None
    assert result["delta"] is None
    assert result["quadrants"] is None
    assert result["candidate"]["approval_rate"] == pytest.approx(
        float(sim.data["new_approval"].mean())
    )


# ── Bancada — depth: risco/tempo/exposição (ADR 0001, 0004; issue #33) ─────────


def test_risk_tier_distribution_without_a_rating_returns_empty_with_expected_columns(
    sample_df, roles
):
    subset = population_filter(sample_df, roles, "Todos")
    sim = _build_sim(subset, roles)

    table = risk_tier_distribution(sim, None, None)

    assert table.empty
    assert list(table.columns) == [
        "Rating",
        "scenario",
        "Applicants",
        "Approved",
        "Hired",
        "Bad_Rate",
    ]


def test_risk_tier_distribution_is_empty_in_tier_c(sample_df, roles, rating_result, rating_labels):
    """No base mapped -> no swap scenarios to break down by rating (gated, not crashed)."""
    tier_c_roles = dataclasses.replace(roles, current_approval_col=None)
    subset = population_filter(sample_df, tier_c_roles, "Todos")
    sim = _build_sim(subset, tier_c_roles)

    table = risk_tier_distribution(sim, rating_result, rating_labels)

    assert table.empty


def test_risk_tier_distribution_matches_summarize_results_grouped_by_rating(
    sample_df, roles, rating_result, rating_labels
):
    """Reuses the engine's own swap classification (`summarize_results`) with an extra
    `by=Rating` groupby — no reimplemented swap/bad-rate math."""
    subset = population_filter(sample_df, roles, "Todos")
    sim = _build_sim(subset, roles)

    table = risk_tier_distribution(sim, rating_result, rating_labels)

    attached = attach_rating(sim.data, rating_result, rating_labels)
    sim_with_rating = dataclasses.replace(sim, data=attached)
    expected = summarize_results(sim_with_rating, by="Rating")
    expected = expected[expected["scenario"].isin(("swap_in", "swap_out", "keep_in"))]

    assert set(table["scenario"]) <= {"swap_in", "swap_out", "keep_in"}
    assert table["Hired"].sum() == pytest.approx(expected["Hired"].sum())
    assert len(table) == len(expected)


def test_policy_vintage_comparison_without_time_col_returns_empty(sample_df, roles):
    no_time_roles = dataclasses.replace(roles, time_col=None)
    subset = population_filter(sample_df, no_time_roles, "Todos")
    sim = _build_sim(subset, no_time_roles)

    table = policy_vintage_comparison(sim, no_time_roles)

    assert table.empty


def test_policy_vintage_comparison_tracks_candidate_and_base_per_vintage(sample_df, roles):
    subset = population_filter(sample_df, roles, "Todos")
    sim = _build_sim(subset, roles)

    table = policy_vintage_comparison(sim, roles)

    assert set(table["series"]) == {"candidate", "base"}
    assert set(table[roles.time_col]) == set(sim.data[roles.time_col].dropna().unique())

    for period, group in sim.data.groupby(roles.time_col):
        candidate_row = table[(table[roles.time_col] == period) & (table["series"] == "candidate")]
        expected_approval = float(group["new_approval"].mean())
        assert candidate_row["approval_rate"].iloc[0] == pytest.approx(expected_approval)

        base_row = table[(table[roles.time_col] == period) & (table["series"] == "base")]
        expected_base_approval = float(group[roles.current_approval_col].fillna(0).mean())
        assert base_row["approval_rate"].iloc[0] == pytest.approx(expected_base_approval)


def test_exposure_kpis_is_candidate_only_in_tier_c(sample_df, roles):
    tier_c_roles = dataclasses.replace(roles, current_approval_col=None)
    subset = population_filter(sample_df, tier_c_roles, "Todos")
    tier = detect_tier(tier_c_roles, subset).tier
    sim = _build_sim(subset, tier_c_roles)

    result = exposure_kpis(sim, tier_c_roles, tier)

    candidate = policy_kpis(sim)
    assert result["candidate_bad_volume"] == pytest.approx(
        candidate["default_rate"] * candidate["contracted_volume"]
    )
    assert result["base_bad_volume"] is None
    assert result["delta"] is None


def test_exposure_kpis_computes_delta_vs_base_in_tier_b(sample_df, roles):
    tier_b_roles = dataclasses.replace(roles, vigente_score=None)
    subset = population_filter(sample_df, tier_b_roles, "Todos")
    tier = detect_tier(tier_b_roles, subset).tier
    assert tier == "B"
    sim = _build_sim(subset, tier_b_roles)

    result = exposure_kpis(sim, tier_b_roles, tier)

    candidate = policy_kpis(sim)
    expected_candidate_volume = candidate["default_rate"] * candidate["contracted_volume"]
    approval_col = sim.data[tier_b_roles.current_approval_col].fillna(0)
    expected_base_bad_rate = float(
        sim.data.loc[approval_col == 1, tier_b_roles.actual_default_col].mean()
    )
    expected_base_volume = expected_base_bad_rate * float(approval_col.sum())

    assert result["candidate_bad_volume"] == pytest.approx(expected_candidate_volume)
    assert result["base_bad_volume"] == pytest.approx(expected_base_volume)
    assert result["delta"] == pytest.approx(expected_candidate_volume - expected_base_volume)


# ── Bancada — re-fit automático do rating sobre os sobreviventes (ADR 0007; issue #39) ──


from pycreditools.studio.analyses import derive_survivor_rating  # noqa: E402


def test_derive_survivor_rating_recomputes_thresholds_when_cutoff_moves(sample_df, roles):
    """Moving a cutoff re-derives rating thresholds on the new survivor set (ADR 0007)."""
    score_col = roles.score_cols[0]
    subset = population_filter(sample_df, roles, "Todos")

    loose_value = float(subset[score_col].quantile(0.2))
    tight_value = float(subset[score_col].quantile(0.8))

    loose_sim = build_policy(
        roles, [make_cutoff_row(name="Corte", cutoffs={score_col: loose_value})]
    ).simulate(subset, method="analytical")
    tight_sim = build_policy(
        roles, [make_cutoff_row(name="Corte", cutoffs={score_col: tight_value})]
    ).simulate(subset, method="analytical")

    loose_rating = derive_survivor_rating(loose_sim, roles)
    tight_rating = derive_survivor_rating(tight_sim, roles)

    assert loose_rating is not None
    assert tight_rating is not None

    # Tight survivors are fewer and have higher scores than loose survivors.
    assert len(survivor_population(tight_sim)) < len(survivor_population(loose_sim))

    # Re-fitted breaks differ because the survivor populations differ.
    loose_breaks = loose_rating.recipe.quantile_breaks[score_col]
    tight_breaks = tight_rating.recipe.quantile_breaks[score_col]
    assert loose_breaks != tight_breaks


def test_derive_survivor_rating_is_fitted_only_on_survivors(sample_df, roles):
    """The re-fitted rating uses survivors with observed defaults, not the full population."""
    score_col = roles.score_cols[0]
    subset = population_filter(sample_df, roles, "Todos")

    tight_value = float(subset[score_col].quantile(0.75))
    sim = build_policy(
        roles, [make_cutoff_row(name="Corte", cutoffs={score_col: tight_value})]
    ).simulate(subset, method="analytical")

    survivor_rating = derive_survivor_rating(sim, roles)

    assert survivor_rating is not None
    # Fitted volume must be ≤ the number of survivors (some may lack observed defaults).
    assert len(survivor_rating.data) <= len(survivor_population(sim))
    # And strictly less than the full population (the cutoff removed some rows).
    assert len(survivor_rating.data) < len(subset)


def test_derive_survivor_rating_returns_none_without_default_col(sample_df, roles):
    """No actual_default_col → cannot fit a risk grouping → returns None."""
    subset = population_filter(sample_df, roles, "Todos")
    sim = build_policy(roles, []).simulate(subset, method="analytical")

    no_default_roles = dataclasses.replace(roles, actual_default_col=None)
    assert derive_survivor_rating(sim, no_default_roles) is None


def test_derive_survivor_rating_returns_none_without_score_cols(sample_df, roles):
    """No score cols mapped → cannot fit a risk grouping → returns None."""
    subset = population_filter(sample_df, roles, "Todos")
    sim = build_policy(roles, []).simulate(subset, method="analytical")

    no_scores_roles = dataclasses.replace(roles, score_cols=[])
    assert derive_survivor_rating(sim, no_scores_roles) is None
