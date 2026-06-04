import pytest
import pandas as pd
import numpy as np
from pycreditools import (
    CreditPolicy,
    optimize_cutoffs,
    OptimizationResult,
    generate_sample_data,
)

@pytest.fixture
def sample_df():
    # Set seed for reproducible tests
    return generate_sample_data(n_applicants=200, seed=42)

@pytest.fixture
def base_policy():
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score", "score_2"),
        current_approval_col="approved",
        actual_default_col="actual_default",
    )

def test_optimal_cutoffs_analytical(sample_df, base_policy):
    # Test grid search with analytical method
    opt_res = optimize_cutoffs(
        data=sample_df,
        config=base_policy,
        cutoff_steps=5,
        target_default_rate=0.10,
        min_approval_rate=0.20,
        method="analytical"
    )
    
    assert isinstance(opt_res, OptimizationResult)
    assert len(opt_res.best_combination) == 2
    assert "legacy_score" in opt_res.best_combination
    assert "score_2" in opt_res.best_combination
    
    # Assert metrics
    assert "overall_approval_rate" in opt_res.metrics
    assert "overall_default_rate" in opt_res.metrics
    assert "tradeoff_score" in opt_res.metrics
    
    # Assert DataFrames
    assert not opt_res.all_results.empty
    assert not opt_res.pareto_frontier.empty
    assert "tradeoff_score" in opt_res.all_results.columns
    assert "constraints_met" in opt_res.all_results.columns
    
    # Check that serialization roundtrips
    d = opt_res.to_dict()
    assert d["best_combination"] == opt_res.best_combination
    assert d["metrics"] == opt_res.metrics

def test_optimal_cutoffs_stochastic(sample_df, base_policy):
    # Test grid search with stochastic method
    opt_res = optimize_cutoffs(
        data=sample_df,
        config=base_policy,
        cutoff_steps=3,
        target_default_rate=0.15,
        min_approval_rate=0.10,
        method="stochastic"
    )
    assert isinstance(opt_res, OptimizationResult)
    assert not opt_res.all_results.empty

def test_analyze_tradeoffs(sample_df, base_policy):
    opt_res = optimize_cutoffs(
        data=sample_df,
        config=base_policy,
        cutoff_steps=4,
        target_default_rate=0.10,
        min_approval_rate=0.20,
        method="analytical"
    )
    
    # Test extraction of Pareto frontier from OptimizationResult property
    pareto1 = opt_res.pareto_frontier
    assert not pareto1.empty
    
    # Validate that Pareto frontier points are non-dominated
    for i, row1 in pareto1.iterrows():
        app1, def1 = row1["overall_approval_rate"], row1["overall_default_rate"]
        for j, row2 in pareto1.iterrows():
            if i == j:
                continue
            app2, def2 = row2["overall_approval_rate"], row2["overall_default_rate"]
            # Row2 cannot strictly dominate Row1
            is_row2_better = (app2 >= app1 and def2 <= def1) and (app2 > app1 or def2 < def1)
            assert not is_row2_better, f"Point {row2} dominates {row1} on the Pareto frontier."

def test_find_equivalent_policy(sample_df, base_policy):
    opt_res = optimize_cutoffs(
        data=sample_df,
        config=base_policy,
        cutoff_steps=4,
        target_default_rate=0.15,
        min_approval_rate=0.15,
        method="analytical"
    )
    
    # Find equivalent policy with ~30% approval
    eq_df = opt_res.find_equivalent(
        target_metric="approval_rate",
        target_value=0.30,
        tolerance=0.05
    )
    assert not eq_df.empty
    # Sort should return closest match first
    assert abs(eq_df.iloc[0]["overall_approval_rate"] - 0.30) <= 0.05
    
    # Test with default rate target
    eq_df2 = opt_res.find_equivalent(
        target_metric="default_rate",
        target_value=0.08,
        tolerance=0.03
    )
    assert not eq_df2.empty


def test_visualize_tradeoffs(sample_df, base_policy):
    import matplotlib.pyplot as plt
    opt_res = optimize_cutoffs(
        data=sample_df,
        config=base_policy,
        cutoff_steps=4,
        target_default_rate=0.10,
        min_approval_rate=0.20,
        method="analytical"
    )
    
    # Test tradeoff plot via result method
    fig1 = opt_res.plot(type="tradeoff")
    assert isinstance(fig1, plt.Figure)
    plt.close(fig1)
    
    # Test pareto plot via result method
    fig2 = opt_res.plot(type="pareto")
    assert isinstance(fig2, plt.Figure)
    plt.close(fig2)

def test_optimization_errors(sample_df, base_policy):
    # Empty data
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError, match="Input data DataFrame is empty"):
        optimize_cutoffs(empty_df, base_policy)
        
    # Invalid target default
    with pytest.raises(ValueError, match="target_default_rate must be between 0.0 and 1.0"):
        optimize_cutoffs(sample_df, base_policy, target_default_rate=1.5)
        
    # Invalid steps
    with pytest.raises(ValueError, match="cutoff_steps must be at least 1"):
        optimize_cutoffs(sample_df, base_policy, cutoff_steps=0)


