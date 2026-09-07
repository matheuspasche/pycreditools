"""Sweeping a stage must rebuild it whole (issue #133, architecture-critique §4).

The base_rate sweep path reconstructs the ``RateStage`` field by field
(``sweep.py:169``). ``RateStage.__init__`` takes six parameters and the rebuild
passes four, so ``observed_col`` and ``calibrate_by`` silently fall to their
defaults. A policy whose take-up is read from the data then becomes, at every
grid point, a scalar-rate policy: keep-ins stop taking their observed contract
and go back to 1.0 -- the #94/#99/#103 bypass, re-entered through the sweep.

These tests pin the contract the rebuild owes: **every field the caller did not
sweep survives**. They are written against the declared meaning of the policy
(``observed_col`` wins over ``base_rate``), never against another rebuild.

Measured on ``release/v0.6`` (2026-08-31): sweeping ``base_rate`` over
[0.1, 0.5, 0.9] on a policy that declares ``base_rate`` irrelevant moves the
reported default rate by **2.27 p.p. absolute**, and one grid point misses the
same policy simulated by hand by **0.90 p.p.** (16.91% against 16.01%).
Approval rate is untouched -- it is measured pre-take-up.

They are ``strict-xfail`` by owner ruling: the fix belongs to the v0.6 spec's
definition of done (#111), not to a patch here. Passing means the fix landed and
the marker must be removed.
"""

import inspect

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy, CutoffStage
from pycreditools.stages import RateStage
from pycreditools.sweep import _policy_for_combo, _without_cutoff_entries, run_sweep


@pytest.fixture(scope="module")
def book():
    """An incumbent book with keep-ins, swap-ins and an observed take-up signal.

    Incumbent approves score >= 600. Take-up among those rises with score, so a
    score-bin calibration gives the (worse-scored) swap-ins a lower rate than
    the global mean -- and a scalar base_rate gives them something else again.
    """
    rng = np.random.default_rng(11)
    n = 3000
    score = rng.uniform(300.0, 900.0, n)
    # A noisy incumbent: keep-ins and swap-ins overlap in score, so swap-in PD
    # is interpolated from observed keep-ins rather than edge-clamped.
    approve_p = np.clip((score - 450) / 300, 0.05, 0.95)
    approved = (rng.random(n) < approve_p).astype(int)

    take_up_p = np.clip((score - 300) / 600 * 0.6 + 0.25, 0.0, 1.0)
    hired = np.where(approved == 1, (rng.random(n) < take_up_p).astype(int), 0)

    pd_true = np.clip(0.45 - (score - 300) / 600 * 0.40, 0.01, 0.60)
    default = (rng.random(n) < pd_true).astype(float)
    # No decision, no outcome: keep-outs have nothing observed (CONTEXT.md).
    default[approved == 0] = np.nan

    return pd.DataFrame(
        {
            "id": np.arange(n),
            "score": score,
            "approved": approved,
            "hired": hired,
            "inad": default,
        }
    )


@pytest.fixture
def observed_policy(book):
    """Take-up read from the data, not declared as a scalar."""
    return (
        CreditPolicy(
            applicant_id_col="id",
            score_cols=("score",),
            current_approval_col="approved",
            current_hired_col="hired",
            actual_default_col="inad",
        )
        .with_calibration(score_col="score", bins=5)
        .add_stage(CutoffStage(name="cut", cutoffs={"score": 500.0}))
        .add_stage(RateStage(name="takeup", base_rate=0.5, observed_col="hired"))
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Confirmed live bug (#133). Owner ruling 2026-08-31: the fix is not a patch "
        "on release/v0.6 -- it is a definition of done the v0.6 architecture spec "
        "(#111) carries, discharged by the implementation map. These stay strict-xfail "
        "so the day the swap-one-field mechanism lands they turn green and this marker "
        "must come off."
    ),
)
class TestBaseRateSweepKeepsTheDeclaredTakeUp:
    def test_rebuilt_stage_keeps_observed_col_and_calibrate_by(self, observed_policy):
        """Only base_rate is swept; the other five fields are not the sweep's to touch."""
        rebuilt = _policy_for_combo(
            observed_policy,
            cutoff_values={},
            resolved_directions={},
            aggravation_factor=None,
            base_rate_values={"takeup": 0.9},
        )
        stage = next(s for s in rebuilt.stages if isinstance(s, RateStage))

        assert stage.base_rate == 0.9, "the swept field must take the grid value"
        assert stage.observed_col == "hired", (
            "the sweep dropped observed_col: the policy's take-up source is gone"
        )
        assert stage.calibrate_by == "score"

    def test_every_ratestage_field_is_carried_through(self, observed_policy):
        """Signature-driven: a field added to RateStage cannot silently fall out."""
        original = next(s for s in observed_policy.stages if isinstance(s, RateStage))
        rebuilt = _policy_for_combo(
            observed_policy,
            cutoff_values={},
            resolved_directions={},
            aggravation_factor=None,
            base_rate_values={"takeup": 0.9},
        )
        stage = next(s for s in rebuilt.stages if isinstance(s, RateStage))

        fields = [p for p in inspect.signature(RateStage.__init__).parameters if p != "self"]
        dropped = [
            f
            for f in fields
            if f != "base_rate" and getattr(stage, f, None) != getattr(original, f, None)
        ]
        assert not dropped, f"base_rate sweep dropped RateStage field(s): {dropped}"

    def test_calibrate_by_is_dropped_too(self, book):
        """Not just observed_col: the estimator for swap-ins falls to its default."""
        policy = (
            CreditPolicy(
                applicant_id_col="id",
                score_cols=("score",),
                current_approval_col="approved",
                current_hired_col="hired",
                actual_default_col="inad",
            )
            .add_stage(CutoffStage(name="cut", cutoffs={"score": 500.0}))
            .add_stage(
                RateStage(
                    name="takeup", base_rate=0.5, observed_col="hired", calibrate_by=None
                )
            )
        )
        rebuilt = _policy_for_combo(
            policy,
            cutoff_values={},
            resolved_directions={},
            aggravation_factor=None,
            base_rate_values={"takeup": 0.9},
        )
        stage = next(s for s in rebuilt.stages if isinstance(s, RateStage))
        assert stage.calibrate_by is None, (
            "the sweep re-declared calibrate_by='score': the flat-mean estimator "
            "the user asked for was swapped for score binning"
        )

    def test_sweeping_base_rate_cannot_move_a_policy_that_ignores_base_rate(
        self, book, observed_policy
    ):
        """``observed_col`` wins over ``base_rate`` (stages.py docstring).

        So every point of a base_rate grid is the same policy, and must report
        the same numbers. If they move, the sweep is running a policy the user
        never declared.
        """
        res = run_sweep(book, observed_policy, base_rates={"takeup": [0.1, 0.5, 0.9]})

        assert res["overall_approval_rate"].nunique() == 1
        spread = res["overall_default_rate"].max() - res["overall_default_rate"].min()
        assert spread < 1e-9, (
            "sweeping an ignored base_rate moved the default rate by "
            f"{spread:.4%} -- observed_col was dropped at the grid points"
        )

    def test_the_grid_point_matches_simulating_that_policy_by_hand(
        self, book, observed_policy
    ):
        """Ground truth, not a second implementation: the declared policy itself."""
        sim = observed_policy.simulate(book).data
        keep_ins = book["approved"] == 1
        contracted = sim.loc[keep_ins, "new_approval"]

        # Direct evidence of the bypass: with observed_col alive, keep-in
        # contract weight is the observed 0/1, so it is not all-ones.
        assert contracted.max() <= 1.0
        assert not np.allclose(contracted.to_numpy(), 1.0), (
            "fixture no longer exercises observed keep-in take-up"
        )

        res = run_sweep(book, observed_policy, base_rates={"takeup": [0.9]})
        truth_app = sim["approved_pre_rate"].sum() / len(book)
        assert res["overall_approval_rate"].iloc[0] == pytest.approx(truth_app, abs=1e-9)

        weight = sim["new_approval"]
        observedness = sim["simulated_default"].notna()
        truth_def = (
            (sim["simulated_default"].fillna(0.0) * weight).sum()
            / weight[observedness].sum()
        )
        assert res["overall_default_rate"].iloc[0] == pytest.approx(truth_def, abs=1e-9)


class TestTheSiblingRebuild:
    """``_without_cutoff_entries`` has the same shape and is correct by accident."""

    def test_every_cutoffstage_field_is_carried_through(self, book):
        policy = CreditPolicy(
            applicant_id_col="id",
            score_cols=("score",),
            current_approval_col="approved",
            actual_default_col="inad",
        ).add_stage(
            CutoffStage(name="cut", cutoffs={"score": 500.0, "other": 1.0}, direction="gte")
        )
        original = policy.stages[0]
        kept = _without_cutoff_entries(policy, {"other"}).stages[0]

        fields = [p for p in inspect.signature(CutoffStage.__init__).parameters if p != "self"]
        dropped = [
            f
            for f in fields
            if f != "cutoffs" and getattr(kept, f, None) != getattr(original, f, None)
        ]
        assert not dropped, f"cutoff sweep dropped CutoffStage field(s): {dropped}"
        assert kept.cutoffs == {"score": 500.0}
