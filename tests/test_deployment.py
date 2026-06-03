import os
import tempfile
import pandas as pd
import numpy as np
from pycreditools import CreditPolicy, col, find_risk_groups, DeploymentPolicy, GroupingRecipe

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
    assert "decisao" in simple_df.columns
    assert "motivo" in simple_df.columns
    assert "contratou" in simple_df.columns
    assert "inadimplente" in simple_df.columns
    assert "cenario" in simple_df.columns
    assert "rating" in simple_df.columns
    assert simple_df["rating"].isna().all()
    
    # Check values
    assert simple_df.loc[0, "contratou"] == "Sim"
    assert simple_df.loc[5, "contratou"] == "Não"
    assert simple_df.loc[0, "cenario"] == "Swap In"
    assert simple_df.loc[2, "cenario"] == "Keep In"
    
    # Check decisions
    # id 5 (age 15) fails first filter "Idade Mínima"
    # id 6 (negativacao 10000) fails "Teto Negativação"
    # id 0 passes all, is approved
    assert simple_df.loc[5, "decisao"] == "Reprovado"
    assert simple_df.loc[5, "motivo"] == "1: Idade Mínima"
    assert simple_df.loc[6, "decisao"] == "Reprovado"
    assert simple_df.loc[6, "motivo"] == "2: Teto Negativação"
    assert simple_df.loc[0, "decisao"] == "Aprovado"
    assert simple_df.loc[0, "motivo"] == "Aprovado"

    # 5. Fit rating grouping
    # Only survivors
    df_surv = sim_res.data[sim_res.data["new_approval"] == 1].copy()
    group_res = find_risk_groups(
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
        assert "etapas_funil" in rules
        assert "classificacao_ratings" in rules
        assert len(rules["etapas_funil"]) == 3
        assert rules["classificacao_ratings"]["score_coluna"] == "score_5"
        
        clean_json_path = os.path.join(tmpdir, "clean_policy.json")
        loaded_dep.save_production_rules(clean_json_path)
        assert os.path.exists(clean_json_path)
        
        # Predict on new data
        pred_simple = loaded_dep.predict(df, simple=True, method="stochastic")
        assert list(pred_simple.columns) == list(simple_df_with_rating.columns)
        pd.testing.assert_frame_equal(pred_simple, simple_df_with_rating)
        
        # Predict raw
        pred_raw = loaded_dep.predict(df, simple=False, method="stochastic")
        assert "Rating" in pred_raw.columns
        assert "decisao" not in pred_raw.columns

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
    assert d["rating_recipe"]["type"] == "segmented_recipes"
    assert "Sudeste" in d["rating_recipe"]["recipes"]
    
    # Check deserialization
    loaded = DeploymentPolicy.from_dict(d)
    assert isinstance(loaded.rating_recipe, dict)
    assert "Nordeste" in loaded.rating_recipe
    
    # Check production rules export
    rules = loaded.to_production_rules()
    assert "segmentos" in rules["classificacao_ratings"]
    assert "Sudeste" in rules["classificacao_ratings"]["segmentos"]
    
    # Check prediction
    res = loaded.predict(df, simple=True, method="stochastic")
    # applicant 1: Nordeste, score 920 -> maps to index 2 (910..1000) -> maps to cluster 1 -> Rating A
    # applicant 3: Nordeste, score 780 -> maps to index 0 (750..820) -> maps to cluster 3 -> Rating C
    assert res.loc[1, "rating"] == "A"
    assert res.loc[3, "rating"] == "C"

