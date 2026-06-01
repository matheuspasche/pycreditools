import pytest
import pandas as pd
import numpy as np
from pycreditools.grouping import find_risk_groups

def test_distance_linkage_clustering():
    """Test autonomous distance-based clustering limits."""
    # Synthetic data matching our use case structure
    np.random.seed(42)
    n_rows = 5000
    df = pd.DataFrame({
        "new_score": np.random.randint(300, 900, size=n_rows),
        "temp_default": np.random.binomial(1, 0.05, size=n_rows),
        "vintage": np.random.choice(["2023-01", "2023-02", "2023-03"], size=n_rows)
    })
    
    # Run autonomous distance-linkage clustering
    res = find_risk_groups(
        df,
        score_cols="new_score",
        default_col="temp_default",
        bins=10,
        max_groups=5,
        method="distance",
        time_col="vintage",
        max_crossings=1,
        min_vol_ratio=0.05
    )
    
    # Check that it returns groups and constraints are met
    assert len(res.groups) <= 5, "Should return at most 5 groups"
    
    # Transform df
    df_pred = res.predict(df)
    assert "risk_rating" in df_pred.columns
    assert df_pred["risk_rating"].nunique() <= 5
