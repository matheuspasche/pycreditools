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
