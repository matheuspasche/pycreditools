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
    assert "col('age') >= 18" in d["condition"]
