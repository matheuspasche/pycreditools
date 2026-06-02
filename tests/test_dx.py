import pytest
import pandas as pd
from pycreditools import CreditPolicy, TradeoffAnalyzer, col

def test_dx_builder():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "score_serasa": [300, 500, 700],
        "age": [17, 25, 40],
        "approved": [1, 1, 1],
        "default": [0, 0, 0]
    })
    
    # Elegant API usage
    policy = (
        CreditPolicy(
            applicant_id_col="id",
            score_cols=["score_serasa"],
            current_approval_col="approved",
            actual_default_col="default"
        )
        .cutoff("Score Interno", {"score_serasa": 400})
        .filter("Idade", col("age") >= 18)
        .rate("Aleatorio", base_rate=1.0)
    )
    
    assert len(policy.stages) == 3
    
    # Test direct simulation
    results = policy.simulate(df, method="analytical")
    final_df = results.data
    
    # 17yo should be rejected (keep_out)
    assert final_df.loc[final_df["id"] == 1, "new_approval"].values[0] == 0.0
    # 25yo (score 500) should be approved (keep_in)
    assert final_df.loc[final_df["id"] == 2, "new_approval"].values[0] == 1.0

def test_dx_tradeoff_analyzer():
    df = pd.DataFrame({
        "id": [1, 2, 3],
        "score_serasa": [300, 500, 700],
        "age": [17, 25, 40],
        "approved": [1, 1, 1],
        "default": [0, 0, 0]
    })
    
    policy = CreditPolicy(
        applicant_id_col="id",
        score_cols=["score_serasa"],
        current_approval_col="approved",
        actual_default_col="default"
    )
    
    analyzer = (
        TradeoffAnalyzer(policy)
        .vary_cutoff("score_serasa", [400, 600])
        .vary_stress_aggravation([1.0, 1.2])
    )
    
    results = analyzer.run(df)
    
    assert len(results) == 4 # 2x2 grid
    assert "score_serasa_cutoff" in results.columns
    assert "aggravation_factor" in results.columns
    assert "approval_rate" in results.columns
