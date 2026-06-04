import pytest
import pandas as pd
import numpy as np
from pycreditools import (
    CreditPolicy,
    RateStage,
    FilterStage,
    col,
    generate_sample_data,
    fit_risk_groups,
    find_risk_groups,
    fit_pairwise_risk_groups,
    RiskGroupResult,
    GroupingRecipe,
)

@pytest.fixture
def sample_df():
    # Set seed for reproducible tests
    return generate_sample_data(n_applicants=200, seed=42)

@pytest.fixture
def base_policy():
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    )

def test_rate_stage_dynamic_expression(sample_df):
    # Test RateStage where variable is an Expression
    # Transition rate based on income / 10000 (scaled multiplier)
    expr = col("income") / 10000.0
    stage = RateStage(name="dyn_expression", base_rate=0.8, variable=expr)
    
    res = stage.apply(sample_df, method="analytical")
    assert isinstance(res, pd.Series)
    assert res.between(0.0, 1.0).all()
    # Check scaling effect: higher income leads to higher rate
    high_inc_idx = sample_df["income"].idxmax()
    low_inc_idx = sample_df["income"].idxmin()
    assert res.loc[high_inc_idx] >= res.loc[low_inc_idx]

def test_rate_stage_dynamic_callable(sample_df):
    # Test RateStage where variable is a Callable
    #desk approval rate: 0.95 for high income, 0.6 for low income
    fn = lambda df: np.where(df["income"] >= 5000, 1.0, 0.5)
    stage = RateStage(name="dyn_callable", base_rate=0.8, variable=fn)
    
    res = stage.apply(sample_df, method="analytical")
    assert isinstance(res, pd.Series)
    assert res.between(0.0, 1.0).all()
    # verify expected calculations
    mask_high = sample_df["income"] >= 5000
    assert (res[mask_high] == 0.8).all()
    assert (res[~mask_high] == 0.4).all()

def test_rate_stage_serialization():
    # Test round-trip serialization of a RateStage with an Expression
    expr = col("income") >= 5000.0
    stage = RateStage(name="expr_rate", base_rate=0.7, variable=expr)
    
    d = stage.to_dict()
    assert d["type"] == "rate"
    assert d["name"] == "expr_rate"
    assert d["base_rate"] == 0.7
    assert isinstance(d["variable"], dict)
    assert d["variable"]["type"] == "binary"
    
    # Reload
    from pycreditools import Stage
    loaded = Stage.from_dict(d)
    assert isinstance(loaded, RateStage)
    assert loaded.base_rate == 0.7
    assert loaded.name == "expr_rate"
    # Ensure expression evaluate compiles
    df = pd.DataFrame({"income": [6000, 4000]})
    res = loaded.apply(df, method="analytical")
    assert res.tolist() == [0.7, 0.0]

def test_credit_policy_rating_integration(sample_df, base_policy):
    # Find a risk group recipe
    rg_res = fit_risk_groups(
        data=sample_df,
        score_cols="legacy_score",
        default_col="actual_default",
        bins=5,
        max_groups=3
    )
    recipe = rg_res.recipe
    
    # Attach recipe to CreditPolicy
    policy_with_rg = base_policy.with_rating(recipe)
    assert policy_with_rg.rating_recipe == recipe
    
    # Test serialization roundtrip of policy containing recipe
    policy_dict = policy_with_rg.to_dict()
    assert "rating_recipe" in policy_dict
    assert policy_dict["rating_recipe"]["score_cols"] == ["legacy_score"]
    
    loaded_policy = CreditPolicy.from_dict(policy_dict)
    assert isinstance(loaded_policy.rating_recipe, GroupingRecipe)
    assert loaded_policy.rating_recipe.score_cols == ["legacy_score"]
    
    # Test fallback in simulation to_decision_dataframe
    sim_res = policy_with_rg.simulate(sample_df, method="analytical")
    decision_df = sim_res.to_decision_dataframe()
    # It should automatically compute and add a rating column using fallbacks
    assert "rating" in decision_df.columns
    assert decision_df["rating"].notna().any()

def test_longitudinal_risk_groups_with_oot(sample_df):
    # Prepare oot_date split
    # Split safra
    safra_list = sorted(sample_df["safra"].unique())
    split_date = safra_list[len(safra_list) // 2]
    
    rg_res = fit_risk_groups(
        data=sample_df,
        score_cols="legacy_score",
        default_col="actual_default",
        time_col="safra",
        bins=5,
        max_groups=3,
        oot_date=split_date
    )
    
    assert isinstance(rg_res, RiskGroupResult)
    assert rg_res.report is not None
    # Report should have period columns representing train and OOT
    assert "period" in rg_res.report.columns
    assert set(rg_res.report["period"].unique()).issubset({"Train", "OOT"})
    assert not rg_res.report[rg_res.report["period"] == "Train"].empty
    assert not rg_res.report[rg_res.report["period"] == "OOT"].empty

def test_find_pairwise_risk_groups(sample_df):
    results = fit_pairwise_risk_groups(
        data=sample_df,
        primary_score="legacy_score",
        challenger_scores=["score_2", "score_3"],
        default_col="actual_default",
        bins=5,
        max_groups=3
    )
    
    assert isinstance(results, dict)
    assert "legacy_score_vs_score_2" in results
    assert "legacy_score_vs_score_3" in results
    assert isinstance(results["legacy_score_vs_score_2"], RiskGroupResult)
    assert isinstance(results["legacy_score_vs_score_3"], RiskGroupResult)


def test_deprecated_grouping_warnings(sample_df):
    import warnings
    with pytest.warns(DeprecationWarning, match="find_risk_groups is deprecated"):
        rg_res = find_risk_groups(
            data=sample_df,
            score_cols="legacy_score",
            default_col="actual_default",
            bins=5,
            max_groups=3
        )
    assert rg_res is not None




def test_reference_score_col_dynamic_cutoff_detection(sample_df):
    # If reference_score_col is not set but score_2 is cut off, it should calibrate with score_2
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_2", "score_5"),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).cutoff("Score Cutoff Stage", {"score_2": 700})
    
    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None


def test_rating_based_swap_in_calibration(sample_df):
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    )
    rg_res = fit_risk_groups(
        data=sample_df,
        score_cols="legacy_score",
        default_col="actual_default",
        bins=5,
        max_groups=3
    )
    policy_rating = policy.with_rating(rg_res.recipe).cutoff("test_cut", {"legacy_score": 750})
    sim_res = policy_rating.simulate(sample_df, method="analytical")
    assert sim_res is not None
    assert sim_res.data["simulated_default"].notna().any()


def test_custom_calibration_bins_count(sample_df):
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(bins=7).cutoff("test_cut", {"legacy_score": 750})

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    assert sim_res.data["simulated_default"].notna().any()


def test_custom_calibration_bins_list(sample_df):
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(bins=[0, 500, 750, 850, 1000]).cutoff("test_cut", {"legacy_score": 750})

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    assert sim_res.data["simulated_default"].notna().any()


def test_custom_calibration_base_global(sample_df):
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(base="global").cutoff("test_cut", {"legacy_score": 750})

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    assert sim_res.data["simulated_default"].notna().any()


def test_custom_calibration_score_col(sample_df):
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score", "score_2"),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(score_col="score_2").cutoff("test_cut", {"legacy_score": 750})

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    assert sim_res.data["simulated_default"].notna().any()


def test_policy_calibration_serialization():
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(score_col="score_2", bins=(500, 750, 850), base="global")

    assert policy.calibration_score_col == "score_2"
    assert policy.calibration_bins == (500, 750, 850)
    assert policy.calibration_base == "global"

    d = policy.to_dict()
    assert d["calibration_score_col"] == "score_2"
    assert d["calibration_bins"] == (500, 750, 850)
    assert d["calibration_base"] == "global"

    loaded = CreditPolicy.from_dict(d)
    assert loaded.calibration_score_col == "score_2"
    assert loaded.calibration_bins == (500, 750, 850)
    assert loaded.calibration_base == "global"


def test_calibrated_expression(sample_df):
    from pycreditools import col
    # Seed numpy for reproducible test
    np.random.seed(42)
    sample_df["hired"] = sample_df["approved"] * np.random.choice([0, 1], size=len(sample_df), p=[0.3, 0.7])

    expr = (col("hired") / col("approved")).calibrated()
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(base="global", bins=5).rate("Contract Rate", base_rate=1.0, variable=expr)

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    stage_col = "stage_0_Contract Rate"
    assert stage_col in sim_res.data.columns
    assert sim_res.data[stage_col].between(0.0, 1.0).all()
    assert len(sim_res.data[stage_col].unique()) > 2


def test_rate_calibrate_syntax(sample_df):
    from pycreditools import col
    # Seed numpy for reproducible test
    np.random.seed(42)
    sample_df["hired"] = sample_df["approved"] * np.random.choice([0, 1], size=len(sample_df), p=[0.3, 0.7])

    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).with_calibration(base="global", bins=5).rate(
        "Contract Rate", base_rate=1.0, variable=col("hired") / col("approved"), calibrate=True
    )

    sim_res = policy.simulate(sample_df, method="analytical")
    assert sim_res is not None
    stage_col = "stage_0_Contract Rate"
    assert stage_col in sim_res.data.columns
    assert sim_res.data[stage_col].between(0.0, 1.0).all()
    assert len(sim_res.data[stage_col].unique()) > 2


def test_keep_in_rate_bypass():
    # Keep-in applicants must bypass rate stages (have 1.0 in pre-approval rate stages
    # and their actual hired value in conversion rate stages).
    df = pd.DataFrame({
        "applicant_id": [1, 2, 3],
        "score": [800, 750, 600],
        "approved": [1, 1, 0], # 1 and 2 are keep-ins
        "hired": [1.0, 0.0, 0.0],    # applicant 1 converted, applicant 2 did not, 3 is rejected
        "actual_default": [0, 0, 0]
    })
    
    # We define a policy with two rate stages: a pre-approval (Anti-fraude) and conversion (Conversao)
    policy = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score",),
        current_approval_col="approved",
        current_hired_col="hired",
        actual_default_col="actual_default"
    ).rate(
        "Anti-fraude", base_rate=0.85
    ).rate(
        "Conversao", base_rate=1.0, variable=col("hired") / col("approved"), calibrate=True
    ).with_calibration(bins=2, base="keep_in")
    
    # 1. Analytical simulation
    res_analytical = policy.simulate(df, method="analytical").data
    # For applicant 1 (keep-in, hired=1):
    # stage_0_Anti-fraude should be 1.0 (pre-approval bypass)
    # stage_1_Conversao should be 1.0 (historic hired value)
    # new_approval should be 1.0
    assert res_analytical.loc[0, "stage_0_Anti-fraude"] == 1.0
    assert res_analytical.loc[0, "stage_1_Conversao"] == 1.0
    assert res_analytical.loc[0, "new_approval"] == 1.0

    # For applicant 2 (keep-in, hired=0):
    # stage_0_Anti-fraude should be 1.0
    # stage_1_Conversao should be 0.0 (historic hired value)
    # new_approval should be 0.0
    assert res_analytical.loc[1, "stage_0_Anti-fraude"] == 1.0
    assert res_analytical.loc[1, "stage_1_Conversao"] == 0.0
    assert res_analytical.loc[1, "new_approval"] == 0.0

    # 2. Stochastic simulation
    res_stochastic = policy.simulate(df, method="stochastic").data
    assert res_stochastic.loc[0, "stage_0_Anti-fraude"] == 1
    assert res_stochastic.loc[0, "stage_1_Conversao"] == 1
    assert res_stochastic.loc[0, "new_approval"] == 1

    assert res_stochastic.loc[1, "stage_0_Anti-fraude"] == 1
    assert res_stochastic.loc[1, "stage_1_Conversao"] == 0
    assert res_stochastic.loc[1, "new_approval"] == 0









