import dataclasses

import pandas as pd

from pycreditools import col, run_simulation
from pycreditools.gui import session
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    build_policy,
    make_cutoff_row,
    make_rate_row,
    make_stress_row,
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


def test_studio_built_policy_matches_hand_built_policy_on_sample_data(sample_df, roles):
    subset = population_filter(sample_df, roles, "Contratados")

    studio_rows = v14_quickfill_rows(sample_df.columns)
    studio_policy = build_policy(roles, studio_rows)
    expected_policy = _hand_built_v14_policy(roles)

    assert studio_policy.to_dict() == expected_policy.to_dict()

    studio_sim = studio_policy.simulate(subset, method="analytical")
    expected_sim = run_simulation(subset, expected_policy, method="analytical")

    pd.testing.assert_frame_equal(studio_sim.data, expected_sim.data)
    pd.testing.assert_frame_equal(
        studio_sim.to_funnel_dataframe(), expected_sim.to_funnel_dataframe()
    )


def test_cached_session_sim_matches_direct_run_simulation(sample_df, roles):
    subset = population_filter(sample_df, roles, "Contratados")
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)

    page_sim = session.run_policy_sim(
        subset, "parity-hash", "Contratados", policy, policy_cache_key(policy)
    )
    expected_sim = run_simulation(subset, policy, method="analytical")

    pd.testing.assert_frame_equal(page_sim.data, expected_sim.data)
    pd.testing.assert_frame_equal(
        page_sim.to_funnel_dataframe(), expected_sim.to_funnel_dataframe()
    )


def test_flat_stress_changes_bad_rate_but_not_funnel_volumes(sample_df, roles):
    # "Todos" (not "Contratados") keeps currently-rejected applicants in the mix,
    # so the new policy actually produces swap-ins for the stress factor to affect.
    # `estimated_default_col` is unset because a supplied PD estimate makes the
    # simulator ignore stress scenarios entirely (ground truth overrides them).
    roles = dataclasses.replace(roles, estimated_default_col=None)
    subset = population_filter(sample_df, roles, "Todos")
    base_rows = v14_quickfill_rows(sample_df.columns) + [
        make_cutoff_row(name="Corte score_5", cutoffs={"score_5": 600}),
        make_rate_row(name="Taxa base", base_rate=0.6),
    ]
    stressed_rows = base_rows + [make_stress_row(factor=1.2)]

    base_policy = build_policy(roles, base_rows)
    stressed_policy = build_policy(roles, stressed_rows)

    base_sim = base_policy.simulate(subset, method="analytical")
    stressed_sim = stressed_policy.simulate(subset, method="analytical")

    pd.testing.assert_frame_equal(
        base_sim.to_funnel_dataframe(), stressed_sim.to_funnel_dataframe()
    )

    base_bad = (base_sim.data["simulated_default"] * base_sim.data["new_approval"]).sum()
    stressed_bad = (
        stressed_sim.data["simulated_default"] * stressed_sim.data["new_approval"]
    ).sum()
    assert stressed_bad > base_bad
