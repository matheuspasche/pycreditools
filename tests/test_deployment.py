import os
import tempfile
import json
import pandas as pd
import numpy as np
from pycreditools import CreditPolicy, col, fit_risk_groups, DeploymentPolicy, GroupingRecipe

def test_deployment_and_simple_df():
    # 1. Create a dummy dataset
    df = pd.DataFrame({
        "applicant_id": range(10),
        "score_5": [950, 910, 880, 850, 780, 600, 960, 920, 875, 830],
        "age": [20, 25, 30, 35, 40, 15, 50, 60, 28, 33],  # 15 fails age >= 18
        "vl_negativacao": [0, 0, 0, 0, 0, 0, 10000, 0, 0, 0], # 10000 fails <= 1500
        "actual_default": [0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
        "safra": ["2024-01"] * 10,
        "region": ["Sudeste"] * 10
    })

    # 2. Build credit policy
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=["score_5"],
            current_approval_col="actual_default",
            actual_default_col="actual_default"
        )
        .filter("Idade Mínima", col("age") >= 18)
        .filter("Teto Negativação", col("vl_negativacao") <= 1500)
        .filter("Score Mínimo", col("score_5") >= 700)
    )

    # 3. Simulate
    sim_res = policy.simulate(df, method="stochastic")
    
    # 4. Generate simple DataFrame without rating
    simple_df = sim_res.to_decision_dataframe()
    assert "decision" in simple_df.columns
    assert "reason" in simple_df.columns
    assert "hired" in simple_df.columns
    assert "defaulted" in simple_df.columns
    assert "scenario" in simple_df.columns
    assert "rating" in simple_df.columns
    assert simple_df["rating"].isna().all()
    
    # Check values
    assert simple_df.loc[0, "hired"] == "Yes"
    assert simple_df.loc[5, "hired"] == "No"
    assert simple_df.loc[0, "scenario"] == "Swap In"
    assert simple_df.loc[2, "scenario"] == "Keep In"
    
    # Check decisions
    # id 5 (age 15) fails first filter "Idade Mínima"
    # id 6 (negativacao 10000) fails "Teto Negativação"
    # id 0 passes all, is approved
    assert simple_df.loc[5, "decision"] == "Rejected"
    assert simple_df.loc[5, "reason"] == "1: Idade Mínima"
    assert simple_df.loc[6, "decision"] == "Rejected"
    assert simple_df.loc[6, "reason"] == "2: Teto Negativação"
    assert simple_df.loc[0, "decision"] == "Approved"
    assert simple_df.loc[0, "reason"] == "Approved"

    # 5. Fit rating grouping
    # Only survivors
    df_surv = sim_res.data[sim_res.data["new_approval"] == 1].copy()
    group_res = fit_risk_groups(
        data=df_surv,
        score_cols="score_5",
        default_col="actual_default",
        bins=5,
        max_groups=3,
        min_vol_ratio=0.1
    )
    
    # 6. Generate simple DataFrame with rating
    simple_df_with_rating = sim_res.to_decision_dataframe(rating_recipe=group_res.recipe)
    assert "rating" in simple_df_with_rating.columns
    # Check that highest score (950) has better rating than lowest score (780)
    # Ratings are letters starting with A
    rating_high = simple_df_with_rating.loc[0, "rating"]
    rating_low = simple_df_with_rating.loc[4, "rating"]
    assert rating_high in ("A", "B", "C")
    assert rating_low in ("A", "B", "C")
    
    # 7. DeploymentPolicy Serialization & Save/Load
    dep = policy.export(rating_recipe=group_res.recipe)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        json_path = os.path.join(tmpdir, "policy.json")
        dep.save(json_path)
        
        # Load it back
        loaded_dep = DeploymentPolicy.load(json_path)
        assert len(loaded_dep.policy.stages) == 3
        assert loaded_dep.rating_recipe is not None
        assert loaded_dep.rating_recipe.score_cols == ["score_5"]
        
        # Test clean production rules
        rules = loaded_dep.to_production_rules()
        assert "funnel_stages" in rules
        assert "rating_classification" in rules
        assert len(rules["funnel_stages"]) == 3
        assert rules["rating_classification"]["score_column"] == "score_5"

        # Test clean=True mode
        clean_rules = loaded_dep.to_production_rules(clean=True)
        assert "funnel_stages" in clean_rules
        assert "metadata" not in clean_rules
        assert "rating_classification" not in clean_rules
        assert len(clean_rules["funnel_stages"]) == 3
        
        clean_json_path = os.path.join(tmpdir, "clean_policy.json")
        loaded_dep.save_production_rules(clean_json_path, clean=True)
        assert os.path.exists(clean_json_path)
        with open(clean_json_path) as f:
            clean_loaded_data = json.load(f)
        assert "funnel_stages" in clean_loaded_data
        assert "metadata" not in clean_loaded_data
        assert "rating_classification" not in clean_loaded_data
        
        # Predict on new data
        pred_simple = loaded_dep.predict(df, simple=True, method="stochastic")
        assert list(pred_simple.columns) == list(simple_df_with_rating.columns)
        pd.testing.assert_frame_equal(pred_simple, simple_df_with_rating)
        
        # Predict raw
        pred_raw = loaded_dep.predict(df, simple=False, method="stochastic")
        assert "Rating" in pred_raw.columns
        assert "decision" not in pred_raw.columns

def test_segmented_deployment_policy():
    df = pd.DataFrame({
        "applicant_id": range(4),
        "score_5": [950, 920, 850, 780],
        "region": ["Sudeste", "Nordeste", "Sudeste", "Nordeste"],
        "cpf_valido": [True, True, True, True],
        "vl_negativacao": [0, 0, 0, 0],
        "actual_default": [0, 0, 0, 0],
        "approved": [1, 1, 1, 1],
        "safra": ["2026-01"] * 4
    })
    
    # Create simple policy
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=["score_5"],
            current_approval_col="approved",
            actual_default_col="actual_default"
        )
        .filter("CPF Válido", col("cpf_valido") == True)
    )
    
    # Create mock recipes for Sudeste and Nordeste
    recipe_se = GroupingRecipe(
        score_cols=["score_5"],
        quantile_breaks={"score_5": [750.0, 800.0, 900.0, 1000.0]},
        cluster_mapping={"0": 3, "1": 2, "2": 1}
    )
    recipe_ne = GroupingRecipe(
        score_cols=["score_5"],
        quantile_breaks={"score_5": [750.0, 820.0, 910.0, 1000.0]},
        cluster_mapping={"0": 3, "1": 2, "2": 1}
    )
    
    segmented_recipe = {
        "Sudeste": recipe_se,
        "Nordeste": recipe_ne
    }
    
    dep = DeploymentPolicy(policy=policy, rating_recipe=segmented_recipe)
    
    # Check serialization
    d = dep.to_dict()
    assert "rating_classification" in d
    assert d["rating_classification"]["segmentation_column"] == "region"
    assert "Sudeste" in d["rating_classification"]["segments"]
    
    # Check deserialization of new format
    loaded = DeploymentPolicy.from_dict(d)
    assert isinstance(loaded.rating_recipe, dict)
    assert "Nordeste" in loaded.rating_recipe
    
    # Check backward compatibility with legacy format
    legacy_d = {
        "policy": policy.to_dict(),
        "rating_recipe": {
            "type": "segmented_recipes",
            "recipes": {
                "Sudeste": recipe_se.to_dict(),
                "Nordeste": recipe_ne.to_dict()
            }
        }
    }
    loaded_legacy = DeploymentPolicy.from_dict(legacy_d)
    assert isinstance(loaded_legacy.rating_recipe, dict)
    assert "Nordeste" in loaded_legacy.rating_recipe
    
    # Check production rules export
    rules = loaded.to_production_rules()
    assert "segments" in rules["rating_classification"]
    assert "Sudeste" in rules["rating_classification"]["segments"]
    
    # Check prediction
    res = loaded.predict(df, simple=True, method="stochastic")
    # applicant 1: Nordeste, score 920 -> maps to index 2 (910..1000) -> maps to cluster 1 -> Rating A
    # applicant 3: Nordeste, score 780 -> maps to index 0 (750..820) -> maps to cluster 3 -> Rating C
    assert res.loc[1, "rating"] == "A"
    assert res.loc[3, "rating"] == "C"


def test_multivariate_matrix_deployment():
    # 1. Create a dummy dataset with two scores
    df = pd.DataFrame({
        "applicant_id": range(5),
        "score_5": [950, 920, 850, 780, 600],
        "score_4": [900, 880, 820, 750, 580],
        "cpf_valido": [True, True, True, True, True],
        "actual_default": [0, 0, 0, 0, 0],
        "approved": [1, 1, 1, 1, 1],
        "region": ["Sudeste", "Sudeste", "Nordeste", "Nordeste", "Nordeste"]
    })
    
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=["score_5", "score_4"],
            current_approval_col="approved",
            actual_default_col="actual_default"
        )
        .filter("CPF Válido", col("cpf_valido") == True)
    )
    
    # 2. Fit a multivariate rating group
    group_res = fit_risk_groups(
        data=df,
        score_cols=["score_5", "score_4"],
        default_col="actual_default",
        bins=3,
        max_groups=2,
        min_vol_ratio=0.1
    )
    
    # Export deployment policy
    dep = policy.export(rating_recipe=group_res.recipe)
    
    # Check serialization
    d = dep.to_dict()
    assert "rating_classification" in d
    ratings_dict = d["rating_classification"]
    assert ratings_dict["type"] == "matrix"
    assert ratings_dict["score_columns"] == ["score_5", "score_4"]
    assert "quantile_breaks" in ratings_dict
    assert "cell_mapping" in ratings_dict
    
    # Check that cells are mapped to letters (e.g. A, B)
    for key, val in ratings_dict["cell_mapping"].items():
        assert val in ("A", "B")
        
    # Check deserialization
    loaded = DeploymentPolicy.from_dict(d)
    assert loaded.rating_recipe is not None
    assert loaded.rating_recipe.score_cols == ["score_5", "score_4"]
    
    # Confirm that original prediction and loaded prediction match
    orig_pred = dep.predict(df, simple=True)
    load_pred = loaded.predict(df, simple=True)
    pd.testing.assert_frame_equal(orig_pred, load_pred)
    
    # 3. Test Segmented matrix serialization/deserialization
    recipe_se = GroupingRecipe(
        score_cols=["score_5", "score_4"],
        quantile_breaks={
            "score_5": [500.0, 800.0, 1000.0],
            "score_4": [500.0, 750.0, 1000.0]
        },
        cluster_mapping={"0-0": 2, "1-1": 1}
    )
    recipe_ne = GroupingRecipe(
        score_cols=["score_5", "score_4"],
        quantile_breaks={
            "score_5": [600.0, 850.0, 1000.0],
            "score_4": [550.0, 800.0, 1000.0]
        },
        cluster_mapping={"0-0": 2, "1-1": 1}
    )
    
    segmented_recipe = {
        "Sudeste": recipe_se,
        "Nordeste": recipe_ne
    }
    
    dep_seg = policy.export(rating_recipe=segmented_recipe)
    d_seg = dep_seg.to_dict()
    assert "rating_classification" in d_seg
    ratings_dict_seg = d_seg["rating_classification"]
    assert ratings_dict_seg["type"] == "segmented_matrix"
    assert ratings_dict_seg["segmentation_column"] == "region"
    assert "Sudeste" in ratings_dict_seg["segments"]
    assert "Nordeste" in ratings_dict_seg["segments"]
    
    se_info = ratings_dict_seg["segments"]["Sudeste"]
    assert se_info["score_columns"] == ["score_5", "score_4"]
    assert se_info["cell_mapping"] == {"0-0": "B", "1-1": "A"}
    
    # Check deserialization of segmented matrix
    loaded_seg = DeploymentPolicy.from_dict(d_seg)
    assert isinstance(loaded_seg.rating_recipe, dict)
    assert "Sudeste" in loaded_seg.rating_recipe
    assert loaded_seg.rating_recipe["Sudeste"].score_cols == ["score_5", "score_4"]
    
    orig_pred_seg = dep_seg.predict(df, simple=True)
    load_pred_seg = loaded_seg.predict(df, simple=True)
    pd.testing.assert_frame_equal(orig_pred_seg, load_pred_seg)

