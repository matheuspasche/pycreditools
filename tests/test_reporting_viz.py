import pytest
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

from pycreditools.sample_data import generate_sample_data
from pycreditools.policy import CreditPolicy
from pycreditools.stages import CutoffStage, RateStage
from pycreditools.simulation import run_simulation
from pycreditools.performance import (
    print_delta_table,
    print_quadrant_summary,
    print_swap_in_by_rating,
    print_rating_quadrant_table,
)
from pycreditools.visualization import (
    plot_tradeoffs,
    plot_vintage_stability,
    plot_crash_test,
)

@pytest.fixture
def mock_sim_results():
    # Generate some realistic sample data
    df = generate_sample_data(n_applicants=500, seed=42)
    
    # Create simple policy
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=["legacy_score", "score_5"],
            current_approval_col="approved",
            actual_default_col="actual_default",
        )
        .add_stage(CutoffStage("ScoreCut", cutoffs={"score_5": 600}))
        .add_stage(RateStage("TakeUp", base_rate=0.8))
    )
    
    # Simulate
    res = run_simulation(df, policy, method="analytical")
    return res

def test_printers(mock_sim_results, capsys):
    # Test print_quadrant_summary
    print_quadrant_summary(mock_sim_results)
    captured = capsys.readouterr()
    assert "QUADRANTES" in captured.out
    
    # Test print_delta_table with None (automatic legacy extraction)
    print_delta_table(mock_sim_results)
    captured = capsys.readouterr()
    assert "P&L EXECUTIVO" in captured.out
    
    # Test print_swap_in_by_rating (with dummy Rating column if needed)
    df = mock_sim_results.data
    df["Rating"] = "A"
    print_swap_in_by_rating(mock_sim_results, rating_col="Rating")
    captured = capsys.readouterr()
    assert "SWAP INS POR RATING" in captured.out
    
    # Test print_rating_quadrant_table
    print_rating_quadrant_table(mock_sim_results, rating_col="Rating")
    captured = capsys.readouterr()
    assert "APROVADOS E CONTRATADOS POR RATING E QUADRANTE" in captured.out

def test_visualizations(mock_sim_results, tmp_path):
    # Prepare dummy tradeoff df
    tradeoff_df = pd.DataFrame({
        "approval_rate": [0.4, 0.5, 0.6],
        "default_rate": [0.05, 0.08, 0.12],
        "Score_Model": ["score_5", "score_5", "score_5"]
    })
    
    tradeoff_path = str(tmp_path / "tradeoff.png")
    fig1 = plot_tradeoffs(
        tradeoff_df,
        legacy_approval_rate=0.5,
        legacy_bad_rate=0.08,
        save_path=tradeoff_path
    )
    assert os.path.exists(tradeoff_path)
    plt.close(fig1)
    
    # Prepare dummy df for vintage stability
    df = mock_sim_results.data
    df["Rating"] = "A"
    df["safra"] = "2024-01"
    df.loc[100:200, "safra"] = "2024-02"
    df.loc[200:300, "safra"] = "2025-01"
    df.loc[300:, "safra"] = "2025-02"
    
    vintage_path = str(tmp_path / "vintage.png")
    fig2 = plot_vintage_stability(
        df,
        rating_col="Rating",
        time_col="safra",
        default_col="actual_default",
        approval_col="new_approval",
        oot_start_safra="2025-01",
        save_path=vintage_path
    )
    assert os.path.exists(vintage_path)
    plt.close(fig2)
    
    # Prepare dummy df for crash test
    crash_df = pd.DataFrame({
        "aggravation_factor": [1.0, 2.0, 3.0],
        "default_rate": [0.06, 0.08, 0.10]
    })
    crash_path = str(tmp_path / "crash.png")
    fig3 = plot_crash_test(
        crash_df,
        legacy_bad_rate=0.08,
        breakeven_factor=2.0,
        save_path=crash_path
    )
    assert os.path.exists(crash_path)
    plt.close(fig3)
