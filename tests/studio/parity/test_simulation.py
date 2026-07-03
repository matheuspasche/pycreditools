import pandas as pd

from pycreditools import CreditPolicy, compare_policies, run_simulation, summarize_results
from pycreditools.gui import session
from pycreditools.studio import analyses
from pycreditools.studio.data import population_filter
from pycreditools.studio.policy_builder import (
    build_policy,
    policy_cache_key,
    v14_quickfill_rows,
)


def _hand_built_legacy_policy(roles, df, score_col="legacy_score", quantile=0.78):
    policy = CreditPolicy(
        applicant_id_col=roles.applicant_id_col,
        score_cols=tuple(roles.score_cols),
        current_approval_col=roles.current_approval_col,
        actual_default_col=roles.actual_default_col,
        time_col=roles.time_col,
        current_hired_col=roles.current_hired_col,
        estimated_default_col=roles.estimated_default_col,
    )
    cutoff = float(df[score_col].quantile(quantile))
    return policy.cutoff("Corte legado", {score_col: cutoff})


def test_studio_quadrant_table_matches_direct_summarize_results_on_full_base(sample_df, roles):
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)

    sim = session.run_policy_sim(
        sample_df, "parity-hash", "Todos", policy, policy_cache_key(policy)
    )
    expected_sim = run_simulation(sample_df, policy, method="analytical")
    pd.testing.assert_frame_equal(sim.data, expected_sim.data)

    quad = analyses.quadrant_table(sim)
    expected_quad = summarize_results(expected_sim)
    pd.testing.assert_frame_equal(quad, expected_quad)


def test_quadrant_hired_and_bad_rate_match_a_hand_groupby_over_sim_data(sample_df, roles):
    """Reproduces `summarize_results`'s per-quadrant formulas independently from raw `sim.data`.

    keep_in/swap_in use the simulated (calibrated) default; swap_out uses the
    observed `actual_default`; keep_out has no observable target (NaN).
    """
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)
    sim = policy.simulate(sample_df, method="analytical")
    quad = analyses.quadrant_table(sim)

    data = sim.data
    for _, row in quad.iterrows():
        scenario = row["scenario"]
        group = data[data["scenario"] == scenario]
        expected_hired = group["new_approval"].sum()
        assert row["Hired"] == expected_hired

        if scenario == "keep_out":
            continue
        if scenario == "swap_out":
            expected_bad = group[roles.actual_default_col].mean()
        else:
            expected_bad = (
                group["simulated_default"] * group["new_approval"]
            ).sum() / expected_hired
        assert abs(row["Bad_Rate"] - expected_bad) < 1e-9


def test_compare_with_baseline_matches_direct_compare_policies_on_full_base(sample_df, roles):
    rows = v14_quickfill_rows(sample_df.columns)
    new_policy = build_policy(roles, rows)
    legacy_policy = _hand_built_legacy_policy(roles, sample_df)

    new_sim = session.run_policy_sim(
        sample_df, "parity-hash", "Todos", new_policy, policy_cache_key(new_policy)
    )
    legacy_sim = session.run_policy_sim(
        sample_df, "parity-hash", "Todos", legacy_policy, policy_cache_key(legacy_policy)
    )

    comparison = analyses.compare_with_baseline(new_sim, legacy_sim)
    expected = compare_policies(new_sim, legacy_sim)
    pd.testing.assert_frame_equal(comparison["metrics"], expected["metrics"])
    pd.testing.assert_frame_equal(comparison["swaps"], expected["swaps"])
    assert comparison["ratio"] == expected["ratio"]


def test_delta_table_pl_numbers_match_a_hand_rebuilt_executive_summary(sample_df, roles):
    """Independently rebuilds the P&L delta numbers `print_delta_table` would print,
    straight from each simulation's `.data` / `.metadata`, and checks `delta_table`
    against them (no stdout scraping).
    """
    rows = v14_quickfill_rows(sample_df.columns)
    new_policy = build_policy(roles, rows)
    legacy_policy = _hand_built_legacy_policy(roles, sample_df)

    new_sim = run_simulation(sample_df, new_policy, method="analytical")
    legacy_sim = run_simulation(sample_df, legacy_policy, method="analytical")

    table = analyses.delta_table(new_sim, legacy_sim).set_index("Metric")

    df_old = legacy_sim.data
    old_default_col = legacy_sim.metadata["policy"]["actual_default_col"]
    old_approval_col = legacy_sim.metadata["policy"].get("current_approval_col", "approved")
    legacy_hired_col = "hired" if "hired" in df_old.columns else old_approval_col
    approval_old = df_old[old_approval_col].mean()
    volume_old = df_old[legacy_hired_col].sum()
    bad_old = (df_old[old_default_col] * df_old[legacy_hired_col]).sum() / volume_old

    df_new = new_sim.data
    new_approval_col = (
        "approved_pre_rate" if "approved_pre_rate" in df_new.columns else "new_approval"
    )
    approval_new = df_new[new_approval_col].mean()
    volume_new = df_new["new_approval"].sum()
    bad_new = (df_new["simulated_default"] * df_new["new_approval"]).sum() / volume_new

    assert abs(table.loc["Taxa de aprovação", "Legacy"] - approval_old) < 1e-9
    assert abs(table.loc["Taxa de aprovação", "New"] - approval_new) < 1e-9
    assert abs(table.loc["Inadimplência esperada", "Legacy"] - bad_old) < 1e-9
    assert abs(table.loc["Inadimplência esperada", "New"] - bad_new) < 1e-9
    assert table.loc["Volume contratado esperado", "Legacy"] == volume_old
    assert table.loc["Volume contratado esperado", "New"] == volume_new


def test_swap_in_by_rating_volumes_match_a_hand_rebuilt_raio_x_table(sample_df, roles):
    """Independently rebuilds `print_swap_in_by_rating`'s numbers from `sim.data`."""
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)
    sim = policy.simulate(population_filter(sample_df, roles, "Todos"), method="analytical")

    df = sim.data.copy()
    df["Rating"] = pd.qcut(df["score_5"], q=3, labels=["C", "B", "A"])
    table = analyses.swap_in_by_rating(df, rating_col="Rating")

    swap_in = df[df["scenario"] == "swap_in"]
    for tier in table["Rating"]:
        group = swap_in[swap_in["Rating"] == tier]
        expected_vol = group["new_approval"].sum()
        expected_bad = (group["simulated_default"] * group["new_approval"]).sum() / expected_vol
        row = table[table["Rating"] == tier].iloc[0]
        assert abs(row["Vol_Esperado"] - expected_vol) < 1e-9
        assert abs(row["Inad_Stressed"] - expected_bad) < 1e-9
