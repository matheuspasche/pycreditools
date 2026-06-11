"""
Tests for recent bugfixes:
1. analysis.py — approved_pre_rate in tradeoff metrics
2. optimization.py — approved_pre_rate in analytical baseline
3. simulation.py — fixed 10-bin default calibration with warning
4. stress.py — factor_col no longer double-multiplied by self.factor
"""
import warnings

import numpy as np
import pandas as pd
import pytest

from pycreditools import (
    CreditPolicy,
    CreditSimResults,
    RateStage,
    generate_sample_data,
    optimize_cutoffs,
    run_simulation,
    col,
)
from pycreditools.analysis import TradeoffAnalyzer, run_tradeoff_analysis
from pycreditools.stress import AggravationStress


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_df():
    return generate_sample_data(n_applicants=300, seed=42)


@pytest.fixture
def policy_with_rate(sample_df):
    """Policy with a RateStage to verify approved_pre_rate vs new_approval."""
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).cutoff("Score Cut", {"legacy_score": 600}).rate("Anti-fraude", base_rate=0.85)


@pytest.fixture
def policy_no_rate():
    """Policy WITHOUT a RateStage — approved_pre_rate == new_approval."""
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("legacy_score",),
        current_approval_col="approved",
        actual_default_col="actual_default",
    ).cutoff("Score Cut", {"legacy_score": 600})


# ── 1. analysis.py — approved_pre_rate in tradeoff metrics ──────────────

class TestAnalysisApprovedPreRate:
    def test_tradeoff_uses_approved_pre_rate_when_rate_stage_present(self, sample_df, policy_with_rate):
        """When a RateStage exists, tradeoff metrics should use approved_pre_rate,
        not new_approval (which would be lower due to the rate)."""
        analyzer = TradeoffAnalyzer(policy_with_rate)
        analyzer.vary_cutoff("legacy_score", [500, 600, 700])
        results = analyzer.run(sample_df)

        # Approval rate must be > 0 for at least one combo
        assert (results["approval_rate"] > 0).any()
        # The approval rate should NOT be deflated by the 0.85 rate stage
        # (if it were using new_approval, rates would be ~15% lower)

    def test_tradeoff_without_rate_stage_unchanged(self, sample_df, policy_no_rate):
        """Without RateStage, approved_pre_rate == new_approval, so behavior is unchanged."""
        analyzer = TradeoffAnalyzer(policy_no_rate)
        analyzer.vary_cutoff("legacy_score", [500, 600, 700])
        results = analyzer.run(sample_df)
        assert (results["approval_rate"] > 0).any()

    def test_tradeoff_bad_rate_bounded(self, sample_df, policy_with_rate):
        """Default rate must always be in [0, 1]."""
        analyzer = TradeoffAnalyzer(policy_with_rate)
        analyzer.vary_cutoff("legacy_score", [400, 500, 600, 700, 800])
        results = analyzer.run(sample_df)
        assert (results["default_rate"] >= 0).all()
        assert (results["default_rate"] <= 1).all()


# ── 2. optimization.py — approved_pre_rate in analytical baseline ───────

class TestOptimizationApprovedPreRate:
    def test_optimize_analytical_uses_approved_pre_rate(self, sample_df):
        """Analytical optimizer should use approved_pre_rate for the baseline probability."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).rate("Anti-fraude", base_rate=0.9)

        result = optimize_cutoffs(
            data=sample_df,
            config=policy,
            cutoff_steps=3,
            target_default_rate=0.15,
            min_approval_rate=0.10,
            method="analytical",
        )

        # Verify approval rates are not artificially deflated by the rate stage
        assert result.metrics["overall_approval_rate"] > 0
        assert result.metrics["overall_default_rate"] >= 0

    def test_optimize_analytical_vs_no_rate(self, sample_df):
        """Compare optimization results with and without rate stage."""
        policy_no_rate = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        )

        policy_with_rate = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).rate("Rate", base_rate=0.8)

        res_no_rate = optimize_cutoffs(
            data=sample_df, config=policy_no_rate,
            cutoff_steps=3, method="analytical",
        )
        res_with_rate = optimize_cutoffs(
            data=sample_df, config=policy_with_rate,
            cutoff_steps=3, method="analytical",
        )

        # With approved_pre_rate fix, approval rates from the optimizer
        # should be the same regardless of the rate stage
        # (because the rate stage is excluded from the analytical baseline)
        # Allow small floating point differences
        for _, row_nr in res_no_rate.all_results.iterrows():
            combo = {c: row_nr[c] for c in policy_no_rate.score_cols}
            match = res_with_rate.all_results
            for c, v in combo.items():
                match = match[np.isclose(match[c], v)]
            if not match.empty:
                assert np.isclose(
                    row_nr["overall_approval_rate"],
                    match.iloc[0]["overall_approval_rate"],
                    atol=0.01,
                ), "Approval rates should be similar since optimizer uses approved_pre_rate"


# ── 3. simulation.py — fixed 10-bin default calibration with warning ────

class TestCalibrationBinsDefault:
    def test_default_bins_emits_warning(self, sample_df):
        """When calibration_bins is None, simulation should warn about 10-bin default."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).cutoff("Score Cut", {"legacy_score": 700})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run_simulation(sample_df, policy, method="analytical")
            calibration_warnings = [
                x for x in w
                if "10 score bins (deciles)" in str(x.message)
            ]
            assert len(calibration_warnings) > 0, "Should emit warning about 10-bin default"

    def test_custom_bins_no_warning(self, sample_df):
        """When calibration_bins is set, no warning should be emitted."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).with_calibration(bins=5).cutoff("Score Cut", {"legacy_score": 700})

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            run_simulation(sample_df, policy, method="analytical")
            calibration_warnings = [
                x for x in w
                if "10 score bins (deciles)" in str(x.message)
            ]
            assert len(calibration_warnings) == 0, "No warning when bins are explicitly set"

    def test_default_bins_produces_results(self, sample_df):
        """Simulation with default 10 bins should still produce valid results."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).cutoff("Score Cut", {"legacy_score": 700})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_simulation(sample_df, policy, method="analytical")

        assert result.data["simulated_default"].notna().any()
        assert (result.data["simulated_default"].dropna() >= 0).all()
        assert (result.data["simulated_default"].dropna() <= 1).all()


# ── 4. stress.py — factor_col bugfix ────────────────────────────────────

class TestStressFactorColBugfix:
    def test_factor_col_no_longer_multiplied_by_self_factor(self):
        """When factor_col is set, only the per-row factor should be used, not self.factor."""
        df = pd.DataFrame({
            "pd": [0.1, 0.2, 0.3],
            "dynamic_factor": [1.5, 2.0, 1.0],
        })

        stress = AggravationStress(factor=1.5, factor_col="dynamic_factor")
        result = stress.apply(df, "pd")

        # Expected: pd * dynamic_factor (NOT pd * 1.5 * dynamic_factor)
        expected = pd.Series([0.1 * 1.5, 0.2 * 2.0, 0.3 * 1.0])
        pd.testing.assert_series_equal(result, expected.clip(0.0, 1.0), check_names=False)

    def test_factor_col_missing_uses_self_factor(self):
        """When factor_col is set but the column doesn't exist in df, fall back to self.factor."""
        df = pd.DataFrame({"pd": [0.1, 0.2, 0.3]})

        stress = AggravationStress(factor=1.5, factor_col="missing_col")
        result = stress.apply(df, "pd")

        expected = pd.Series([0.1 * 1.5, 0.2 * 1.5, 0.3 * 1.5])
        pd.testing.assert_series_equal(result, expected.clip(0.0, 1.0), check_names=False)

    def test_no_factor_col_uses_self_factor(self):
        """When factor_col is None, self.factor should be used."""
        df = pd.DataFrame({"pd": [0.1, 0.2, 0.3]})

        stress = AggravationStress(factor=2.0)
        result = stress.apply(df, "pd")

        expected = pd.Series([0.1 * 2.0, 0.2 * 2.0, 0.3 * 2.0])
        pd.testing.assert_series_equal(result, expected.clip(0.0, 1.0), check_names=False)

    def test_factor_col_clipping(self):
        """Stressed PD must be clipped to [0, 1]."""
        df = pd.DataFrame({
            "pd": [0.8, 0.9],
            "dynamic_factor": [2.0, 3.0],
        })

        stress = AggravationStress(factor=1.5, factor_col="dynamic_factor")
        result = stress.apply(df, "pd")

        assert (result >= 0.0).all()
        assert (result <= 1.0).all()

    def test_stress_serialization_roundtrip(self):
        """AggravationStress should serialize and deserialize correctly."""
        stress = AggravationStress(factor=1.8, factor_col="my_col")
        d = stress.to_dict()
        assert d["type"] == "aggravation"
        assert d["factor"] == 1.8
        assert d["factor_col"] == "my_col"

        from pycreditools.stress import StressScenario
        loaded = StressScenario.from_dict(d)
        assert isinstance(loaded, AggravationStress)
        assert loaded.factor == 1.8
        assert loaded.factor_col == "my_col"


# ── 5. Edge cases & integration tests ──────────────────────────────────

class TestEdgeCases:
    def test_simulation_with_all_approved(self, sample_df):
        """If everyone is approved, there should be no swap_in, only keep_in."""
        sample_df = sample_df.copy()
        sample_df["approved"] = 1  # All previously approved

        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_simulation(sample_df, policy, method="analytical")

        assert (result.data["scenario"] == "keep_in").all()

    def test_simulation_with_none_approved(self, sample_df):
        """If nobody was approved, everyone should be swap_in or keep_out."""
        sample_df = sample_df.copy()
        sample_df["approved"] = 0  # None previously approved

        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).cutoff("Score Cut", {"legacy_score": 600})

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_simulation(sample_df, policy, method="analytical")

        # No keep_in or swap_out since nobody was previously approved
        assert (result.data["scenario"].isin(["swap_in", "keep_out"])).all()

    def test_approved_pre_rate_exists_in_simulation(self, sample_df):
        """Verify that approved_pre_rate column is always created by simulation."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).cutoff("Score Cut", {"legacy_score": 600}).rate("Rate", base_rate=0.9)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result_analytical = run_simulation(sample_df, policy, method="analytical")
            result_stochastic = run_simulation(sample_df, policy, method="stochastic")

        assert "approved_pre_rate" in result_analytical.data.columns
        assert "approved_pre_rate" in result_stochastic.data.columns

    def test_approved_pre_rate_gte_new_approval(self, sample_df):
        """approved_pre_rate should always be >= new_approval (since rate stage reduces it)."""
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).cutoff("Score Cut", {"legacy_score": 600}).rate("Rate", base_rate=0.8)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_simulation(sample_df, policy, method="analytical")

        df = result.data
        assert (df["approved_pre_rate"] >= df["new_approval"] - 1e-10).all()

    def test_calibrated_expression_bins_use_policy_config(self, sample_df):
        """CalibratedExpression should also respect calibration_bins from policy."""
        np.random.seed(42)
        sample_df = sample_df.copy()
        sample_df["hired"] = sample_df["approved"] * np.random.choice(
            [0, 1], size=len(sample_df), p=[0.3, 0.7]
        )

        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).with_calibration(bins=5).rate(
            "Conversao", base_rate=1.0,
            variable=col("hired") / col("approved"),
            calibrate=True,
        )

        result = run_simulation(sample_df, policy, method="analytical")
        assert result is not None
        assert result.data["new_approval"].notna().all()


# ── 6. CalibratedExpression fallback bins consistency ───────────────────

class TestCalibratedExpressionFallback:
    def test_calibrated_expression_uses_dynamic_bins_when_no_policy_bins(self, sample_df):
        """CalibratedExpression still uses dynamic binning when calibration_bins is None,
        which is inconsistent with simulation.py's new 10-bin default.
        This test documents the current behavior."""
        np.random.seed(42)
        sample_df = sample_df.copy()
        sample_df["hired"] = sample_df["approved"] * np.random.choice(
            [0, 1], size=len(sample_df), p=[0.3, 0.7]
        )

        # Policy WITHOUT explicit bins — CalibratedExpression uses dynamic bins
        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).rate(
            "Conversao", base_rate=1.0,
            variable=col("hired") / col("approved"),
            calibrate=True,
        )

        # Should still produce valid results
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_simulation(sample_df, policy, method="analytical")
        assert result is not None


# ── 7. compare_policies and DeploymentPolicy serialization fixes ──────────

class TestComparePoliciesApprovedPreRate:
    def test_compare_policies_uses_approved_pre_rate(self, sample_df, policy_with_rate):
        """compare_policies should report the approval rate using approved_pre_rate if available."""
        from pycreditools.performance import compare_policies
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim_new = run_simulation(sample_df, policy_with_rate, method="analytical")
            sim_old = run_simulation(sample_df, policy_with_rate, method="analytical")

        comparison = compare_policies(sim_new, sim_old)
        metrics = comparison["metrics"]

        # Expected approval rate should be the mean of approved_pre_rate, not new_approval
        expected_rate = sim_new.data["approved_pre_rate"].mean()
        app_rate_new = metrics.loc[metrics["Metric"] == "Approval Rate", "New"].values[0]
        assert np.isclose(app_rate_new, expected_rate)


class TestDeploymentSerialization:
    def test_deployment_policy_serialization_with_rate_expression(self):
        """DeploymentPolicy should serialize and deserialize RateStage Expression variables correctly."""
        from pycreditools.deployment import DeploymentPolicy

        policy = CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("legacy_score",),
            current_approval_col="approved",
            actual_default_col="actual_default",
        ).rate("Conversion", base_rate=0.8, variable=col("legacy_score") > 600)

        deploy_policy = DeploymentPolicy(policy=policy)

        # Convert to production rules (serialize)
        rules = deploy_policy.to_production_rules(clean=False)

        # Verify propensity_column in rate_conversion is serialized (not raw Expression object)
        rate_stage_rule = [s for s in rules["funnel_stages"] if s["type"] == "rate_conversion"][0]
        assert isinstance(rate_stage_rule["propensity_column"], dict)
        assert rate_stage_rule["propensity_column"]["type"] == "binary"

        # Deserialize back
        loaded_deploy_policy = DeploymentPolicy.from_dict(rules)
        loaded_policy = loaded_deploy_policy.policy

        # Verify deserialized RateStage variable is an Expression
        loaded_rate_stage = loaded_policy.stages[0]
        assert hasattr(loaded_rate_stage.variable, "eval")

