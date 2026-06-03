import pytest
import pandas as pd
from pycreditools import col, FilterStage

def test_expression_evaluation():
    df = pd.DataFrame({
        "age": [17, 18, 25, 60],
        "score": [400, 500, 600, 700],
        "status": ["A", "A", "B", "C"]
    })
    
    # Test simple comparison
    expr1 = col("age") >= 18
    res1 = expr1.eval(df)
    assert res1.tolist() == [False, True, True, True]
    
    # Test multiple conditions
    expr2 = (col("age") >= 18) & (col("score") > 500)
    res2 = expr2.eval(df)
    assert res2.tolist() == [False, False, True, True]

    # Test equality
    expr3 = col("status") == "A"
    res3 = expr3.eval(df)
    assert res3.tolist() == [True, True, False, False]

    # Test bitwise OR and NOT
    expr4 = ~(col("status") == "A") | (col("score") < 500)
    res4 = expr4.eval(df)
    assert res4.tolist() == [True, False, True, True]

def test_filter_stage_with_expressions():
    df = pd.DataFrame({
        "age": [17, 18, 25],
        "score": [400, 500, 600],
    })
    
    # Test with string (old way)
    stage_str = FilterStage("StrFilter", "age >= 18")
    res_str = stage_str.apply(df)
    assert res_str.tolist() == [0.0, 1.0, 1.0]
    
    # Test with callable
    stage_call = FilterStage("CallFilter", lambda d: d["age"] >= 18)
    res_call = stage_call.apply(df)
    assert res_call.tolist() == [0.0, 1.0, 1.0]
    
    # Test with Expression
    stage_expr = FilterStage("ExprFilter", col("age") >= 18)
    res_expr = stage_expr.apply(df)
    assert res_expr.tolist() == [0.0, 1.0, 1.0]
    
    # Test representation in to_dict
    d = stage_expr.to_dict()
    assert d["name"] == "ExprFilter"
    assert d["condition"] == {
        "type": "binary",
        "left": {"type": "column", "name": "age"},
        "op": ">=",
        "right": 18
    }
    
    # Round-trip deserialization
    from pycreditools import Stage, Expression
    stage_loaded = Stage.from_dict(d)
    assert isinstance(stage_loaded.condition, Expression)
    res_loaded = stage_loaded.apply(df)
    assert res_loaded.tolist() == [0.0, 1.0, 1.0]

def test_policy_validation_and_coercion():
    from pycreditools import CreditPolicy
    
    # Test score_cols list coercion to tuple
    p = CreditPolicy(
        applicant_id_col="id",
        score_cols=["score1", "score2"],
        current_approval_col="approved",
        actual_default_col="defaulted",
    )
    assert isinstance(p.score_cols, tuple)
    assert p.score_cols == ("score1", "score2")
    
    # Test score_cols string coercion to tuple
    p2 = CreditPolicy(
        applicant_id_col="id",
        score_cols="score1",
        current_approval_col="approved",
        actual_default_col="defaulted",
    )
    assert p2.score_cols == ("score1",)

    # Test validation of missing columns in FilterStage Expression
    df = pd.DataFrame({
        "id": [1, 2],
        "score1": [500, 600],
        "approved": [1, 1],
        "defaulted": [0, 0]
    })
    
    # Validation should pass if score1 and other standard columns exist
    p2.validate(df)
    
    # Now add filter with missing column
    p3 = p2.filter("AgeFilter", col("age") >= 18)
    with pytest.raises(ValueError, match="Missing required columns in data:.*age"):
        p3.validate(df)

def test_generate_sample_data():
    from pycreditools import generate_sample_data
    df = generate_sample_data(n_applicants=100, seed=42)
    assert len(df) == 100
    expected_cols = {
        "applicant_id", "safra", "region", "age", "income", "employment",
        "cpf_valido", "vl_negativacao", "vl_vencido_scr", "vl_protestos",
        "true_pd", "actual_default", "score_2", "score_3", "score_4", "score_5",
        "legacy_score", "approved", "conversion_rate", "hired"
    }
    assert expected_cols.issubset(df.columns)
