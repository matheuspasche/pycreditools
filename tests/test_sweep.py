"""Regression tests for the single sweep engine (issue #71).

Every assertion here is against ground truth measured on the data — never
against another implementation, which is what let Bug 1 ship.
"""
import numpy as np
import pandas as pd
import pytest

from pycreditools import (
    CreditPolicy,
    CutoffStage,
    TradeoffAnalyzer,
    optimize_cutoffs,
    run_sweep,
)


@pytest.fixture(scope="module")
def risk_df():
    """Score uniform 300-900; default probability strictly decreasing in score."""
    rng = np.random.default_rng(7)
    n = 4000
    score = rng.uniform(300, 900, n)
    pd_true = np.clip(0.45 - (score - 300) / 600 * 0.40, 0.01, 0.60)
    return pd.DataFrame(
        {
            "id": np.arange(n),
            "score_main": score,
            "score_other": rng.uniform(300, 900, n),
            "fraud_score": rng.uniform(0, 100, n),
            "approved": np.ones(n, dtype=int),
            "inad": (rng.random(n) < pd_true).astype(int),
            "pd_true": pd_true,
        }
    )


@pytest.fixture
def base_policy():
    return CreditPolicy(
        applicant_id_col="id",
        score_cols=("score_main",),
        current_approval_col="approved",
        actual_default_col="inad",
    )


# ── Bug 1: vary_cutoff inverted the cutoff direction ─────────────────────


class TestCutoffDirection:
    def test_approval_falls_as_a_gte_cutoff_rises_and_matches_ground_truth(
        self, risk_df, base_policy
    ):
        cuts = [400.0, 600.0, 800.0]
        res = TradeoffAnalyzer(base_policy).vary_cutoff("score_main", cuts).run(risk_df)
        assert res["approval_rate"].is_monotonic_decreasing
        for _, row in res.iterrows():
            truth = (risk_df["score_main"] >= row["score_main_cutoff"]).mean()
            assert abs(row["approval_rate"] - truth) < 1e-9

    def test_default_falls_as_a_gte_cutoff_rises_on_risk_decreasing_scores(
        self, risk_df, base_policy
    ):
        """Cutting deeper into a good score removes bads: no free lunch curve."""
        cuts = [400.0, 600.0, 800.0]
        res = TradeoffAnalyzer(base_policy).vary_cutoff("score_main", cuts).run(risk_df)
        assert res["default_rate"].is_monotonic_decreasing

    def test_an_lte_sweep_is_the_mirror(self, risk_df, base_policy):
        cuts = [400.0, 600.0, 800.0]
        res = (
            TradeoffAnalyzer(base_policy)
            .vary_cutoff("score_main", cuts, direction="lte")
            .run(risk_df)
        )
        assert res["approval_rate"].is_monotonic_increasing
        for _, row in res.iterrows():
            truth = (risk_df["score_main"] <= row["score_main_cutoff"]).mean()
            assert abs(row["approval_rate"] - truth) < 1e-9

    def test_legacy_comparison_operator_spellings_are_rejected(self, base_policy):
        with pytest.raises(ValueError, match="gte"):
            TradeoffAnalyzer(base_policy).vary_cutoff("score_main", [500.0], direction=">=")
        with pytest.raises(ValueError, match="lte"):
            TradeoffAnalyzer(base_policy).vary_cutoff("score_main", [500.0], direction="<=")

    def test_cutoff_stage_raises_on_an_unknown_direction(self):
        with pytest.raises(ValueError, match="gte"):
            CutoffStage(name="bad", cutoffs={"x": 1.0}, direction=">=")

    def test_optimize_cutoffs_sweeps_lte_when_declared(self, risk_df):
        """Scores where lower is better (fraud) are sweepable via directions=."""
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("fraud_score",),
            current_approval_col="approved",
            actual_default_col="inad",
        )
        result = optimize_cutoffs(
            risk_df,
            policy,
            cutoff_ranges={"fraud_score": [30.0, 60.0, 90.0]},
            directions={"fraud_score": "lte"},
        )
        for _, row in result.all_results.iterrows():
            truth = (risk_df["fraud_score"] <= row["fraud_score"]).mean()
            assert abs(row["overall_approval_rate"] - truth) < 1e-9


# ── Bug 2: the config always binds, on every method ──────────────────────


class TestConfigAlwaysBinds:
    def test_a_cutoff_outside_the_grid_caps_every_grid_point(self, risk_df):
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main",),
            current_approval_col="approved",
            actual_default_col="inad",
        ).cutoff("corte_other", {"score_other": 800})
        cap = (risk_df["score_other"] >= 800).mean()

        for method in ("analytical", "stochastic"):
            result = optimize_cutoffs(risk_df, policy, cutoff_steps=4, method=method)
            assert (
                result.all_results["overall_approval_rate"] <= cap + 1e-9
            ).all(), f"method={method} ignored the off-grid cutoff"

    def test_analytical_and_stochastic_agree(self, risk_df):
        """method= is a simulation choice: the same set of stages binds."""
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main",),
            current_approval_col="approved",
            actual_default_col="inad",
        ).cutoff("corte_other", {"score_other": 600})

        res_a = optimize_cutoffs(risk_df, policy, cutoff_steps=4, method="analytical")
        res_s = optimize_cutoffs(risk_df, policy, cutoff_steps=4, method="stochastic")
        diff = (
            res_a.all_results["overall_approval_rate"]
            - res_s.all_results["overall_approval_rate"]
        ).abs()
        assert (diff < 0.05).all()

    def test_a_fully_parameterised_policy_raises_and_names_the_escape(self, risk_df):
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main",),
            current_approval_col="approved",
            actual_default_col="inad",
        ).cutoff("corte", {"score_main": 600})
        with pytest.raises(ValueError, match="cutoff_ranges"):
            optimize_cutoffs(risk_df, policy, cutoff_steps=3)

    def test_cutoff_ranges_sweeps_an_already_parameterised_score(self, risk_df):
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main",),
            current_approval_col="approved",
            actual_default_col="inad",
        ).cutoff("corte", {"score_main": 600})
        result = optimize_cutoffs(risk_df, policy, cutoff_ranges={"score_main": [500.0, 700.0]})
        for _, row in result.all_results.iterrows():
            truth = (risk_df["score_main"] >= row["score_main"]).mean()
            assert abs(row["overall_approval_rate"] - truth) < 1e-9

    def test_cutoff_ranges_keys_must_be_score_cols(self, risk_df, base_policy):
        with pytest.raises(ValueError, match="score_cols"):
            optimize_cutoffs(risk_df, base_policy, cutoff_ranges={"score_other": [500.0]})

    def test_the_default_grid_is_the_score_cols_without_a_cutoff(self, risk_df):
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main", "score_other"),
            current_approval_col="approved",
            actual_default_col="inad",
        ).cutoff("corte", {"score_main": 600})
        result = optimize_cutoffs(risk_df, policy, cutoff_steps=3)
        # Only the un-parameterised score is gridded; the decided one is frozen.
        assert "score_other" in result.all_results.columns
        assert "score_main" not in result.best_combination
        assert list(result.best_combination) == ["score_other"]
        # And the frozen cutoff binds at every grid point.
        cap = (risk_df["score_main"] >= 600).mean()
        assert (result.all_results["overall_approval_rate"] <= cap + 1e-9).all()


# ── ADR 0008: contracted-weighted default rate ───────────────────────────


class TestAdr0008Metrics:
    @pytest.fixture
    def rate_policy(self, risk_df):
        """Risk-correlated take-up: risky applicants contract more. The
        approved-vs-contracted divergence is zero for a flat RateStage, so a
        correlated one is required for these tests to bite."""
        risk_df["propensity"] = np.clip(0.2 + risk_df["pd_true"] * 1.5, 0, 1)
        return CreditPolicy(
            applicant_id_col="id",
            score_cols=("score_main",),
            actual_default_col="inad",
        ).rate("take-up", base_rate=1.0, variable="propensity")

    def test_default_rate_is_contracted_weighted(self, risk_df, rate_policy):
        cut = 400.0
        res = TradeoffAnalyzer(rate_policy).vary_cutoff("score_main", [cut]).run(risk_df)

        mask = risk_df["score_main"] >= cut
        w = risk_df["propensity"] * mask
        contracted_weighted = (w * risk_df["inad"]).sum() / w.sum()
        approved_weighted = (mask * risk_df["inad"]).sum() / mask.sum()

        got = res["default_rate"].iloc[0]
        assert abs(got - contracted_weighted) < 1e-9
        # Sanity: the two weightings genuinely diverge on this data.
        assert abs(contracted_weighted - approved_weighted) > 0.005
        assert abs(got - approved_weighted) > 0.005

    def test_approval_rate_is_pre_take_up(self, risk_df, rate_policy):
        cut = 400.0
        res = TradeoffAnalyzer(rate_policy).vary_cutoff("score_main", [cut]).run(risk_df)
        assert abs(res["approval_rate"].iloc[0] - (risk_df["score_main"] >= cut).mean()) < 1e-9

    def test_method_does_not_move_the_default_rate(self, risk_df, rate_policy):
        res_a = run_sweep(
            risk_df, rate_policy, cutoff_grid={"score_main": [400.0]}, method="analytical"
        )
        res_s = run_sweep(
            risk_df, rate_policy, cutoff_grid={"score_main": [400.0]}, method="stochastic"
        )
        assert (
            abs(
                res_a["overall_default_rate"].iloc[0]
                - res_s["overall_default_rate"].iloc[0]
            )
            < 0.03
        )

    def test_constraints_bind_on_the_contracted_default_rate(self, risk_df, rate_policy):
        cut = 400.0
        res = TradeoffAnalyzer(rate_policy).vary_cutoff("score_main", [cut]).run(risk_df)
        contracted = res["default_rate"].iloc[0]

        result = optimize_cutoffs(
            risk_df,
            rate_policy,
            cutoff_ranges={"score_main": [cut]},
            target_default_rate=float(contracted) - 0.001,
        )
        assert not result.all_results["constraints_met"].iloc[0]

        result = optimize_cutoffs(
            risk_df,
            rate_policy,
            cutoff_ranges={"score_main": [cut]},
            target_default_rate=float(contracted) + 0.001,
        )
        assert result.all_results["constraints_met"].iloc[0]


# ── Both verdicts are the same engine ────────────────────────────────────


class TestOneEngine:
    def test_optimize_and_tradeoff_report_identical_metrics_on_the_same_grid(
        self, risk_df, base_policy
    ):
        cuts = [400.0, 600.0, 800.0]
        opt = optimize_cutoffs(risk_df, base_policy, cutoff_ranges={"score_main": cuts})
        curve = TradeoffAnalyzer(base_policy).vary_cutoff("score_main", cuts).run(risk_df)

        pd.testing.assert_series_equal(
            opt.all_results["overall_approval_rate"],
            curve["approval_rate"],
            check_names=False,
        )
        pd.testing.assert_series_equal(
            opt.all_results["overall_default_rate"],
            curve["default_rate"],
            check_names=False,
        )

    def test_tradeoff_run_does_not_swallow_engine_warnings(self, risk_df, base_policy):
        """analysis.py used to wrap the run in simplefilter('ignore'), which
        would have hidden the calibration warnings #72 adds."""
        import warnings

        policy = base_policy  # keep-in flow triggers the default-bins warning
        risk_df2 = risk_df.copy()
        risk_df2.loc[risk_df2["score_main"] < 500, "approved"] = 0
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            TradeoffAnalyzer(policy).vary_cutoff("score_main", [400.0]).run(risk_df2)
        assert any("bins" in str(w.message) for w in caught), (
            "engine warnings must reach the TradeoffAnalyzer caller"
        )
