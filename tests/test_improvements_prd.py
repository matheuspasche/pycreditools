import pytest
import pandas as pd
import numpy as np
import copy
from pycreditools import (
    CreditPolicy,
    CutoffStage,
    FilterStage,
    RateStage,
    col,
    run_simulation,
    generate_sample_data,
)
from pycreditools.stages import register_callable, _resolve_callable, Stage
from pycreditools.performance import (
    summarize_results,
    compare_policies,
    print_delta_table,
    print_quadrant_summary,
    print_swap_in_by_rating,
    print_rating_quadrant_table,
)
from pycreditools.deployment import DeploymentPolicy


@pytest.fixture
def base_df():
    return pd.DataFrame({
        "applicant_id": [1, 2, 3, 4, 5],
        "score_1": [500, 600, 700, 800, 900],
        "score_2": [650, 750, 850, 950, 1000],
        "observed_default": [0.0, 1.0, 0.0, 1.0, 0.0],
    })


# ── 1. Resolução Determinística de Funções Customizadas em Runtime ──────────

def test_resolve_callable_unregistered_raises_clear_error():
    """An unregistered callable must raise a detailed ValueError instructing the user to register it."""
    with pytest.raises(ValueError) as excinfo:
        _resolve_callable("my_completely_custom_function")
    
    assert "has not been registered in the local environment" in str(excinfo.value)
    assert "pycreditools.stages.register_callable('my_completely_custom_function', your_function)" in str(excinfo.value)


def test_resolve_callable_registered_resolves_correctly():
    """A registered callable must resolve correctly without errors."""
    def test_func(df):
        return df["score_1"] > 600

    register_callable("my_test_registered_func", test_func)
    resolved = _resolve_callable("my_test_registered_func")
    assert resolved is test_func


# ── 2. Padrão Builder Imutável (Segurança de Estado da Política) ───────────

def test_credit_policy_builder_immutability():
    """Fluid builders must return a new instance and must not mutate the original policy."""
    p1 = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
    )
    
    # 1. cutoff
    p2 = p1.cutoff("Cut 1", {"score_1": 600})
    assert p1 is not p2
    assert len(p1.stages) == 0
    assert len(p2.stages) == 1
    
    # 2. filter
    p3 = p2.filter("Filter 1", col("score_1") > 700)
    assert p2 is not p3
    assert len(p2.stages) == 1
    assert len(p3.stages) == 2
    
    # 3. rate
    p4 = p3.rate("Rate 1", base_rate=0.9)
    assert p3 is not p4
    assert len(p3.stages) == 2
    assert len(p4.stages) == 3

    # 4. with_calibration
    p5 = p4.with_calibration(score_col="score_1", bins=5, base="global")
    assert p4 is not p5
    assert p4.calibration_score_col is None
    assert p5.calibration_score_col == "score_1"

    # 5. stress (alias to stress_aggravation)
    p6 = p5.stress(1.5)
    assert p5 is not p6
    assert len(p5.stress_scenarios) == 0
    assert len(p6.stress_scenarios) == 1


# ── 3. Saídas de DataFrames Não-Mutativas e Limpas ─────────────────────────

def test_simulation_non_mutative(base_df):
    """run_simulation must not mutate the input DataFrame."""
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",  # just to satisfy normal validation
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600})

    df_copy = base_df.copy()
    run_simulation(df_copy, p, method="analytical")
    
    # Verify that no new columns were added to df_copy and its data remains unchanged
    pd.testing.assert_frame_equal(df_copy, base_df)


def test_simulation_drop_stages(base_df):
    """Setting drop_stages=True must discard intermediate stage columns but keep core output columns."""
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600}).rate("Rate 1", base_rate=0.8)

    # 1. Without drop_stages (default False)
    res_default = run_simulation(base_df, p, method="analytical", drop_stages=False)
    assert "stage_0_Cut 1" in res_default.data.columns
    assert "stage_1_Rate 1" in res_default.data.columns
    assert "new_approval" in res_default.data.columns
    assert "simulated_default" in res_default.data.columns

    # 2. With drop_stages=True
    res_clean = run_simulation(base_df, p, method="analytical", drop_stages=True)
    assert "stage_0_Cut 1" not in res_clean.data.columns
    assert "stage_1_Rate 1" not in res_clean.data.columns
    assert "new_approval" in res_clean.data.columns
    assert "simulated_default" in res_clean.data.columns


# ── 4. Fluxo de Simulação Standalone (Sem Política de Comparação) ──────────

def test_standalone_simulation_execution(base_df):
    """A standalone simulation must run without errors, omit scenario/quadrant columns, and assign simulated defaults."""
    # policy with current_approval_col and actual_default_col set to None
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col=None,
    ).cutoff("Cut 1", {"score_1": 600}).rate("Rate 1", base_rate=0.7)

    # 1. Analytical standalone simulation
    res_analytical = run_simulation(base_df, p, method="analytical")
    df_ana = res_analytical.data
    
    assert "new_approval" in df_ana.columns
    assert "simulated_default" in df_ana.columns
    assert "scenario" not in df_ana.columns
    assert "quadrant" not in df_ana.columns
    
    # simulated_default must match the RateStage output (since actual_default_col is None)
    # approved rows: score_1 >= 600 -> applicants 2, 3, 4, 5
    # For these approved rows, the baseline_pd is the RateStage probability = 0.7
    np.testing.assert_allclose(df_ana.loc[df_ana["new_approval"] > 0, "simulated_default"], 0.7)

    # 2. Stochastic standalone simulation
    res_stochastic = run_simulation(base_df, p, method="stochastic")
    df_stoc = res_stochastic.data
    assert "new_approval" in df_stoc.columns
    assert "simulated_default" in df_stoc.columns
    # Check that simulated defaults are 0.0 or 1.0 (stochastic outcomes)
    approved_defaults = df_stoc.loc[df_stoc["new_approval"] > 0, "simulated_default"].dropna()
    assert set(approved_defaults.unique()).issubset({0.0, 1.0})


def test_standalone_simulation_with_observed_default(base_df):
    """If actual_default_col is provided in standalone mode, it must be kept as the simulated_default baseline."""
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600})

    res = run_simulation(base_df, p, method="analytical")
    df = res.data
    
    # Approved rows: score_1 >= 600 -> applicants 2, 3, 4, 5
    # observed_default values: [1.0, 0.0, 1.0, 0.0]
    expected_defaults = base_df.loc[base_df["score_1"] >= 600, "observed_default"].values
    np.testing.assert_allclose(df.loc[df["new_approval"] > 0, "simulated_default"], expected_defaults)


def test_standalone_simulation_reporting_exceptions(base_df):
    """All reporting/comparison functions must raise an informative ValueError when called on standalone simulations."""
    p_standalone = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col=None,
    ).cutoff("Cut 1", {"score_1": 600})

    p_normal = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600})

    res_standalone = run_simulation(base_df, p_standalone, method="analytical")
    res_normal = run_simulation(base_df, p_normal, method="analytical")

    # 1. summarize_results
    with pytest.raises(ValueError, match="The simulation is standalone"):
        summarize_results(res_standalone)

    # 2. compare_policies
    with pytest.raises(ValueError, match="Cannot compare policies"):
        compare_policies(res_standalone, res_normal)
    with pytest.raises(ValueError, match="Cannot compare policies"):
        compare_policies(res_normal, res_standalone)

    # 3. print_delta_table
    with pytest.raises(ValueError, match="The new policy simulation is standalone"):
        print_delta_table(res_standalone, res_normal)
    with pytest.raises(ValueError, match="The old/legacy policy simulation is standalone"):
        print_delta_table(res_normal, res_standalone)

    # 4. print_quadrant_summary
    with pytest.raises(ValueError, match="The simulation is standalone"):
        print_quadrant_summary(res_standalone)

    # 5. print_swap_in_by_rating
    with pytest.raises(ValueError, match="The simulation is standalone"):
        print_swap_in_by_rating(res_standalone)

    # 6. print_rating_quadrant_table
    with pytest.raises(ValueError, match="The simulation is standalone"):
        print_rating_quadrant_table(res_standalone)


def test_standalone_deployment_predict_works(base_df):
    """DeploymentPolicy predict must run and succeed on a standalone policy without mocking errors."""
    p_standalone = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col=None,
    ).cutoff("Cut 1", {"score_1": 600})

    dep_policy = DeploymentPolicy(policy=p_standalone)
    
    # Predict should run and complete successfully
    res_df = dep_policy.predict(base_df, simple=True, method="analytical")
    assert isinstance(res_df, pd.DataFrame)
    assert "decision" in res_df.columns
    assert "hired" in res_df.columns
    assert "defaulted" in res_df.columns
    assert "scenario" not in res_df.columns  # standalone has no scenario


def test_plot_funnel(base_df, capsys):
    """Verify plot_funnel returns a Plotly Figure and maps nodes/links correctly."""
    from pycreditools.visualization import plot_funnel

    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1", "score_2"),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600}).cutoff("Cut 2", {"score_2": 700})

    # Test with drop_stages=False
    results_no_drop = run_simulation(base_df, p, method="analytical", drop_stages=False)
    fig_no_drop = plot_funnel(results_no_drop)
    import plotly.graph_objects as go
    assert isinstance(fig_no_drop, go.Figure)

    # Test with drop_stages=True
    results_drop = run_simulation(base_df, p, method="analytical", drop_stages=True)
    fig_drop = plot_funnel(results_drop)
    assert isinstance(fig_drop, go.Figure)

    # Verify nodes (Total + 2 stages + Approved = 4 nodes)
    node_labels = fig_drop.data[0].node.label
    assert len(node_labels) == 4
    assert "Total" in node_labels[0]
    assert "1: Cut 1" in node_labels[1]
    assert "2: Cut 2" in node_labels[2]
    assert "Approved" in node_labels[3]

    # Verify link values mapping
    link_data = fig_drop.data[0].link
    assert len(link_data.value) > 0

    # Test to_funnel_dataframe
    df_funnel = results_drop.to_funnel_dataframe()
    assert isinstance(df_funnel, pd.DataFrame)
    assert len(df_funnel) == 4
    assert list(df_funnel.columns) == ["Stage", "Candidates", "Passed", "Stage_Pass_Rate", "Cum_Pass_Rate", "Rejections", "Stage_Rej_Rate"]

    # Verify Stage_Pass_Rate and Stage_Rej_Rate are NaN for Total (first row) and Approved (last row)
    assert pd.isna(df_funnel.iloc[0]["Stage_Pass_Rate"])
    assert pd.isna(df_funnel.iloc[0]["Stage_Rej_Rate"])
    assert pd.isna(df_funnel.iloc[-1]["Stage_Pass_Rate"])
    assert pd.isna(df_funnel.iloc[-1]["Stage_Rej_Rate"])

    # Verify Stage_Pass_Rate and Stage_Rej_Rate are NOT NaN for intermediate filter stages
    assert not pd.isna(df_funnel.iloc[1]["Stage_Pass_Rate"])
    assert not pd.isna(df_funnel.iloc[1]["Stage_Rej_Rate"])

    # Test print_funnel_table
    results_drop.print_funnel_table()
    captured = capsys.readouterr().out
    assert "CREDIT POLICY DECISION FUNNEL" in captured
    
    # Check that '-' is printed in the Stage Pass and Rej Rate columns for Total and Approved rows
    lines = [line.strip() for line in captured.splitlines() if line.strip()]
    
    total_line = [line for line in lines if line.startswith("Total")]
    assert len(total_line) == 1
    assert "-" in total_line[0]
    
    approved_line = [line for line in lines if line.startswith("Approved")]
    assert len(approved_line) == 1
    assert "-" in approved_line[0]


def test_multi_policy_delta_table(base_df, capsys):
    """Verify comparing multiple policies and printing delta table."""
    p_champion = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 600})

    p_challenger1 = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 700})

    p_challenger2 = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="observed_default",
        actual_default_col="observed_default",
    ).cutoff("Cut 1", {"score_1": 800})

    res_champion = run_simulation(base_df, p_champion, method="analytical")
    res_chal1 = run_simulation(base_df, p_challenger1, method="analytical")
    res_chal2 = run_simulation(base_df, p_challenger2, method="analytical")

    # Call compare_policies with list
    comparison = compare_policies([res_chal1, res_chal2], res_champion)
    assert isinstance(comparison, list)
    assert len(comparison) == 2
    assert isinstance(comparison[0], dict)
    assert isinstance(comparison[1], dict)

    # Capture stdout of print_delta_table
    print_delta_table([res_chal1, res_chal2], res_champion)
    captured = capsys.readouterr().out

    assert "=== DELTA TABLE: EXECUTIVE P&L ===" in captured
    assert "Global Approval Rate (% ToF)" in captured
    assert "Expected Bad Rate" in captured
    assert "Expected Hired Volume" not in captured


def test_estimated_default_col():
    """Verify estimated_default_col behaves correctly in Swap and Standalone modes."""
    # Create sample dataframe
    df = pd.DataFrame({
        "applicant_id": [1, 2, 3, 4, 5],
        "score_1": [500, 600, 700, 800, 900],
        "observed_default": [0.0, 1.0, 0.0, 1.0, 0.0],
        "estimated_pd": [0.1, 0.2, 0.3, 0.4, 0.5],
        "historical_approval": [1, 1, 0, 0, 1]  # Keep-ins: 1, 2, 5. Swap-ins: 3, 4.
    })

    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="historical_approval",
        actual_default_col="observed_default",
        estimated_default_col="estimated_pd"
    ).cutoff("Cut 1", {"score_1": 600})  # Approved: 2, 3, 4, 5.

    # 1. Swap Mode: run_simulation
    res_swap = run_simulation(df, p, method="analytical")
    df_swap = res_swap.data

    # keep_in: applicant 2, 5 (historical_approval == 1, score_1 >= 600)
    # swap_in: applicant 3, 4 (historical_approval == 0, score_1 >= 600)
    # Check keep_ins have actual default from observed_default
    np.testing.assert_allclose(df_swap.loc[df_swap["scenario"] == "keep_in", "simulated_default"], [1.0, 0.0])
    # Check swap_ins have estimated_pd values
    np.testing.assert_allclose(df_swap.loc[df_swap["scenario"] == "swap_in", "simulated_default"], [0.3, 0.4])

    # 2. Standalone Mode: run standalone simulation (current_approval_col is None)
    p_standalone = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col="observed_default",
        estimated_default_col="estimated_pd"
    ).cutoff("Cut 1", {"score_1": 600})

    # Add observed_default with NaN to test fallback/observed split
    df_standalone = df.copy()
    df_standalone.loc[df_standalone["applicant_id"] == 5, "observed_default"] = np.nan # Approved without observed default

    res_std = run_simulation(df_standalone, p_standalone, method="analytical")
    df_std = res_std.data

    # Approved: 2, 3, 4, 5
    # Applicant 2: observed_default is 1.0 (should copy observed)
    # Applicant 3: observed_default is 0.0 (should copy observed)
    # Applicant 4: observed_default is 1.0 (should copy observed)
    # Applicant 5: observed_default is NaN (should use estimated_pd = 0.5)
    np.testing.assert_allclose(df_std.loc[df_std["new_approval"] > 0, "simulated_default"], [1.0, 0.0, 1.0, 0.5])


def test_estimated_default_col_ignores_stress(base_df):
    """Verify that when both estimated_default_col and stress_scenarios are provided,
    a UserWarning is raised, the stress scenarios are ignored, and simulated_default
    is assigned directly from estimated_default_col."""
    import pytest
    from pycreditools.stress import AggravationStress

    df = pd.DataFrame({
        "applicant_id": [1, 2, 3, 4, 5],
        "score_1": [500, 600, 700, 800, 900],
        "observed_default": [0.0, 1.0, 0.0, 1.0, 0.0],
        "estimated_pd": [0.1, 0.2, 0.3, 0.4, 0.5],
        "historical_approval": [1, 1, 0, 0, 1]
    })

    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="historical_approval",
        actual_default_col="observed_default",
        estimated_default_col="estimated_pd"
    ).cutoff("Cut 1", {"score_1": 600}).stress(2.0)

    # 1. Swap Mode: run_simulation with stress and estimated_default_col
    with pytest.warns(UserWarning, match="Stress scenarios will be ignored"):
        res_swap = run_simulation(df, p, method="analytical")
    df_swap = res_swap.data
    # Swap-ins (applicants 3, 4) should have simulated_default = estimated_pd, NOT stressed (estimated_pd * 2)
    np.testing.assert_allclose(df_swap.loc[df_swap["scenario"] == "swap_in", "simulated_default"], [0.3, 0.4])

    # 2. Standalone Mode: run_simulation with stress and estimated_default_col
    p_standalone = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col=None,
        actual_default_col="observed_default",
        estimated_default_col="estimated_pd"
    ).cutoff("Cut 1", {"score_1": 600}).stress(2.0)

    df_standalone = df.copy()
    df_standalone.loc[df_standalone["applicant_id"] == 5, "observed_default"] = np.nan # Approved without observed default

    with pytest.warns(UserWarning, match="Stress scenarios will be ignored"):
        res_std = run_simulation(df_standalone, p_standalone, method="analytical")
    df_std = res_std.data
    # Applicant 5: observed_default is NaN (uses estimated_pd = 0.5, NOT stressed 1.0)
    np.testing.assert_allclose(df_std.loc[df_std["new_approval"] > 0, "simulated_default"], [1.0, 0.0, 1.0, 0.5])

