"""Bancada tracer #1 — política viva + funil (ADR 0001, issue #26)."""

import dataclasses

import pandas as pd

from pycreditools import col, run_simulation
from pycreditools.gui import session
from pycreditools.studio.analyses import survivor_population
from pycreditools.studio.data import population_filter
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
