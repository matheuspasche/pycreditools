"""Hard filters bind at every grid point, so approval ceilings at the survivors (#136).

The reported symptom: sweeping a score down to a near-null cutoff, the approval
rate never flattens at the hard-filter survivor share -- as if the grid approved
past what the shields would let through.

Measured on ``release/v0.6`` (2026-09-04), whose ``src/pycreditools`` tree is
byte-identical to ``release/v0.5`` (both ``2e72f16``), so the v0.5 comparison the
ticket asks for is the same engine: **no such bug**. Across twenty-two shapes --
filters as string/``Expression``/callable, shields as ``CutoffStage``, the swap
book with and without ``current_hired_col``, the masterclass funnel, one and two
swept scores, ``lte``, and the re-simulation path entered by a swept stress or
``base_rate`` -- the swept approval rate reaches the survivor share and stops
there, to the last digit, on both methods.

The sharpest statement of the contract is the owner's own: shields that cut
exactly half the base, drawn independently of the score, then a cutoff of 0 --
which gates nobody. The reported approval reads **50.0000%**, to the digit, on
both methods. The negative control gives the test teeth: the same grid point
with the shields removed reads 100%, which is what a leak would look like. The
protocol runs through the two verbs the report named as well -- the grid, the
Pareto frontier and the best pick of ``optimize_cutoffs``, and the ``tradeoff``
curve -- because a thin layer over the engine still has to carry the guarantee.

What the symptom actually is: the plateau lies outside the grid.
``optimize_cutoffs`` bounds its default grid at the 5th-95th percentiles of the
score, so its loosest point still gates 5% of the base away -- 2.33 p.p. shy of
the ceiling and still climbing (76.98% against 79.30%, n=50k, seed 42). The
curve flattens only once the cutoff falls to the score minimum, which the
percentile grid never reaches; ``percentiles=None`` reaches it exactly.

The one shape where a screen genuinely does not cap approval is a screen
declared as a ``RateStage``: ADR 0008 measures approval *pre* take-up, so rate
stages are excluded by construction. The same anti-fraud screen costs 9.70 p.p.
of reported approval as a ``.filter`` and nothing at all as a ``.rate``. That is
the metric contract, not a leak -- pinned here because it is the one way a
"filter" can read as ignored.
"""

import numpy as np
import pandas as pd
import pytest

from pycreditools import CreditPolicy, col
from pycreditools.sample_data import generate_sample_data, generate_standalone_sample_data
from pycreditools.analysis import TradeoffAnalyzer
from pycreditools.optimization import optimize_cutoffs
from pycreditools.sweep import run_sweep

N = 20_000
SEED = 42


def _hf_mask(df: pd.DataFrame) -> pd.Series:
    """The shields, evaluated in pandas -- the reference the engine is measured against."""
    return (
        (df["cpf_valido"] == True)  # noqa: E712 -- the notebook's own idiom
        & (df["vl_negativacao"] <= 1500)
        & (df["vl_vencido_scr"] <= 3000)
        & (df["vl_protestos"] <= 500)
    ).fillna(False)


def _with_shields(policy: CreditPolicy) -> CreditPolicy:
    return (
        policy.filter("Valid CPF", col("cpf_valido") == True)  # noqa: E712
        .filter("Negativation <= 1500", col("vl_negativacao") <= 1500)
        .filter("SCR arrears <= 3000", col("vl_vencido_scr") <= 3000)
        .filter("Protests <= 500", col("vl_protestos") <= 500)
    )


@pytest.fixture(scope="module")
def incumbent() -> pd.DataFrame:
    """The swap book: an incumbent decision, observed hires, masked outcome."""
    return generate_sample_data(n_applicants=N, seed=SEED)


@pytest.fixture(scope="module")
def greenfield() -> pd.DataFrame:
    """The standalone book: nobody was rejected, so every outcome is observed."""
    return generate_standalone_sample_data(n_applicants=N, seed=SEED)


def _below_minimum(df: pd.DataFrame, score: str = "score_5") -> float:
    """A cutoff no row can fail -- where the approval curve must already be flat."""
    return float(df[score].min()) - 100.0


def _greenfield_policy() -> CreditPolicy:
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        actual_default_col="actual_default",
    )


def _halve(df: pd.DataFrame) -> pd.DataFrame:
    """Two shields keeping exactly half the base, drawn independently of the score.

    The first keeps 75%, the second two thirds of those. Nothing about the draw
    knows the score, so the plateau it imposes is purely the shields'.
    """
    df = df.copy()
    n = len(df)
    assert n % 4 == 0
    u = np.random.default_rng(7).permutation(n)
    df["hf_a"] = (u >= n // 4).astype(int)
    df["hf_b"] = np.where(u >= n // 4, (u - n // 4) >= (3 * n // 4) / 3, 0).astype(int)
    assert float(((df["hf_a"] == 1) & (df["hf_b"] == 1)).mean()) == 0.5
    assert float(df["score_5"].min()) >= 0.0, "a cutoff of 0 must gate nobody"
    return df


def _shielded(policy: CreditPolicy) -> CreditPolicy:
    return policy.filter("HF A", col("hf_a") == 1).filter("HF B", col("hf_b") == 1)


def _incumbent_policy(**kwargs) -> CreditPolicy:
    return CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        current_approval_col="approved",
        actual_default_col="actual_default",
        calibration_bins=10,
        **kwargs,
    )


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("method", ["analytical", "stochastic"])
def test_shields_cutting_half_the_base_plateau_at_half(greenfield, method):
    """The owner's protocol: shields that cut exactly half, then a null cutoff.

    Two shields drawn from a permutation independent of the score keep exactly
    50% of the base. ``score_5`` has a minimum of 0, so a cutoff of 0 gates
    nobody -- the reported approval must be 50%, to the digit. Above it means
    the grid approved past the shields; below it means the grid cut something
    the policy never declared. The negative control pins what a leak would look
    like: the same grid point without the shields reads 100%.
    """
    df = _halve(greenfield)
    policy = _shielded(_greenfield_policy())

    out = run_sweep(df, policy, cutoff_grid={"score_5": [0.0, 50.0, 300.0]}, method=method)
    at_null = float(out.loc[out["score_5"] == 0.0, "overall_approval_rate"].iat[0])

    assert at_null == 0.5
    assert (out["overall_approval_rate"] <= 0.5 + 1e-12).all()

    unshielded = run_sweep(
        df, _greenfield_policy(), cutoff_grid={"score_5": [0.0]}, method=method
    )
    assert float(unshielded["overall_approval_rate"].iat[0]) == 1.0


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("method", ["analytical", "stochastic"])
def test_greenfield_approval_ceilings_at_the_survivors(greenfield, method):
    """A cutoff below the score minimum approves the shields' survivors, and no more."""
    ceiling = float(_hf_mask(greenfield).mean())
    policy = _with_shields(
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            actual_default_col="actual_default",
        )
    )
    grid = [_below_minimum(greenfield), 200.0, 500.0]
    out = run_sweep(greenfield, policy, cutoff_grid={"score_5": grid}, method=method)

    assert out["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12)
    assert (out["overall_approval_rate"] <= ceiling + 1e-12).all()


@pytest.mark.filterwarnings("ignore")
@pytest.mark.parametrize("method", ["analytical", "stochastic"])
def test_swap_book_approval_ceilings_at_the_survivors(incumbent, method):
    """Keep-ins do not lift approval past the shields: the funnel gates them too."""
    ceiling = float(_hf_mask(incumbent).mean())
    policy = _with_shields(_incumbent_policy(current_hired_col="hired"))
    grid = [_below_minimum(incumbent), 200.0, 500.0]
    out = run_sweep(incumbent, policy, cutoff_grid={"score_5": grid}, method=method)

    assert out["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12)


@pytest.mark.filterwarnings("ignore")
def test_masterclass_funnel_ceilings_at_the_survivors(incumbent):
    """The shape that raised the report: four shields, an observed take-up, a stress."""
    ceiling = float(_hf_mask(incumbent).mean())
    policy = (
        _with_shields(_incumbent_policy())
        .rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")
        .stress(1.2)
    )
    grid = [_below_minimum(incumbent), 200.0, 500.0]
    out = run_sweep(
        incumbent,
        policy,
        cutoff_grid={"score_5": grid},
        method="analytical",
        directions={"score_5": "gte"},
    )

    assert out["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12)


@pytest.mark.filterwarnings("ignore")
def test_shields_bind_however_they_are_written(greenfield):
    """A shield is a shield: string query, ``Expression``, callable or ``CutoffStage``."""
    ceiling = float(_hf_mask(greenfield).mean())
    base = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        actual_default_col="actual_default",
    )
    shapes = {
        "expression": _with_shields(base),
        "callable": base.filter("shields", lambda d: _hf_mask(d)),
        "cutoff_stages": (
            base.cutoff("Negativation", {"vl_negativacao": 1500}, direction="lte")
            .cutoff("SCR arrears", {"vl_vencido_scr": 3000}, direction="lte")
            .cutoff("Protests", {"vl_protestos": 500}, direction="lte")
            .filter("Valid CPF", col("cpf_valido") == True)  # noqa: E712
        ),
    }
    grid = [_below_minimum(greenfield), 400.0]

    for name, policy in shapes.items():
        out = run_sweep(greenfield, policy, cutoff_grid={"score_5": grid})
        assert out["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12), name


@pytest.mark.filterwarnings("ignore")
def test_shields_bind_on_the_re_simulation_path(incumbent):
    """A swept stress or ``base_rate`` leaves the fast path; the shields still bind."""
    ceiling = float(_hf_mask(incumbent).mean())
    policy = _with_shields(_incumbent_policy(current_hired_col="hired")).rate(
        "Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score"
    )
    grid = [_below_minimum(incumbent), 400.0]

    stressed = run_sweep(
        incumbent, policy, cutoff_grid={"score_5": grid}, stress_factors=[1.0, 1.5]
    )
    rated = run_sweep(
        incumbent, policy, cutoff_grid={"score_5": grid}, base_rates={"Take-up": [0.5, 1.0]}
    )

    assert stressed["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12)
    assert rated["overall_approval_rate"].max() == pytest.approx(ceiling, abs=1e-12)


@pytest.mark.filterwarnings("ignore")
def test_percentile_grid_stops_short_of_the_plateau(incumbent):
    """The symptom, reproduced: the default grid never reaches the flat region.

    ``optimize_cutoffs`` bounds the grid at the 5th-95th percentiles, so its
    loosest cutoff still gates part of the base away and the curve is still
    climbing at the edge of the grid. ``percentiles=None`` reaches the ceiling.
    """
    ceiling = float(_hf_mask(incumbent).mean())
    policy = _with_shields(_incumbent_policy(current_hired_col="hired"))

    bounded = optimize_cutoffs(
        incumbent, policy, cutoff_steps=40, target_default_rate=0.08, min_approval_rate=0.01
    )
    full = optimize_cutoffs(
        incumbent,
        policy,
        cutoff_steps=40,
        target_default_rate=0.08,
        min_approval_rate=0.01,
        percentiles=None,
    )

    loosest = float(bounded.all_results["overall_approval_rate"].max())
    assert loosest < ceiling - 0.01, "the default grid is expected to stop short"
    assert float(full.all_results["overall_approval_rate"].max()) == pytest.approx(
        ceiling, abs=1e-12
    )


@pytest.mark.filterwarnings("ignore")
def test_a_screen_declared_as_a_rate_stage_does_not_cap_approval(incumbent):
    """ADR 0008: approval is measured pre take-up, so a rate stage is excluded.

    The same anti-fraud screen caps approval as a ``.filter`` and is invisible to
    the reported approval as a ``.rate``. This is the metric contract, and it is
    the one way a declared screen can read as ignored by the grid.
    """
    screen_share = float((incumbent["passed_antifraud"] == 1).mean())
    base = _incumbent_policy(current_hired_col="hired")
    grid = [_below_minimum(incumbent), 300.0]

    as_filter = run_sweep(
        incumbent,
        base.filter("Anti-fraud", col("passed_antifraud") == 1),
        cutoff_grid={"score_5": grid},
    )
    as_rate = run_sweep(
        incumbent,
        base.rate("Anti-fraud", base_rate=1.0, observed_col="passed_antifraud", calibrate_by=None),
        cutoff_grid={"score_5": grid},
    )

    assert as_filter["overall_approval_rate"].max() == pytest.approx(screen_share, abs=1e-12)
    assert as_rate["overall_approval_rate"].max() == pytest.approx(1.0, abs=1e-12)


@pytest.mark.filterwarnings("ignore")
def test_the_public_verbs_hold_the_ceiling(greenfield):
    """The same 50% protocol through the two verbs the report actually named.

    ``optimize_cutoffs`` and ``tradeoff`` are thin layers over ``run_sweep``, so
    the guarantee has to survive the layer: the grid, the Pareto frontier and
    the best pick all sit at or below the shields' survivors, and a null cutoff
    reads exactly half. Stripped of the shields, both verbs read 100% at the
    same grid point -- the leak they are accused of.
    """
    df = _halve(greenfield)
    grid = [0.0, 50.0, 300.0, 600.0]

    opt = optimize_cutoffs(
        df,
        _shielded(_greenfield_policy()),
        cutoff_ranges={"score_5": grid},
        target_default_rate=0.5,
        min_approval_rate=0.01,
    )
    results = opt.all_results
    assert float(results.loc[results["score_5"] == 0.0, "overall_approval_rate"].iat[0]) == 0.5
    assert (results["overall_approval_rate"] <= 0.5 + 1e-12).all()
    assert (opt.pareto_frontier["overall_approval_rate"] <= 0.5 + 1e-12).all()
    assert opt.metrics["overall_approval_rate"] <= 0.5 + 1e-12

    curve = (
        TradeoffAnalyzer(_shielded(_greenfield_policy()))
        .vary_cutoff("score_5", grid, direction="gte")
        .run(df)
    )
    assert float(curve.loc[curve["score_5_cutoff"] == 0.0, "approval_rate"].iat[0]) == 0.5
    assert (curve["approval_rate"] <= 0.5 + 1e-12).all()

    bare_opt = optimize_cutoffs(
        df,
        _greenfield_policy(),
        cutoff_ranges={"score_5": [0.0]},
        target_default_rate=0.5,
        min_approval_rate=0.01,
    )
    bare_curve = (
        TradeoffAnalyzer(_greenfield_policy())
        .vary_cutoff("score_5", [0.0], direction="gte")
        .run(df)
    )
    assert float(bare_opt.all_results["overall_approval_rate"].iat[0]) == 1.0
    assert float(bare_curve["approval_rate"].iat[0]) == 1.0


@pytest.mark.filterwarnings("ignore")
def test_the_public_verbs_hold_the_ceiling_on_the_swap_book(incumbent):
    """And on the shape the report came from: keep-ins, observed take-up, stress."""
    df = _halve(incumbent)
    policy = (
        _shielded(_incumbent_policy(current_hired_col="hired"))
        .rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")
        .stress(1.2)
    )
    grid = [0.0, 50.0, 300.0]

    opt = optimize_cutoffs(
        df,
        policy,
        cutoff_ranges={"score_5": grid},
        target_default_rate=0.5,
        min_approval_rate=0.01,
    )
    curve = TradeoffAnalyzer(policy).vary_cutoff("score_5", grid, direction="gte").run(df)
    results = opt.all_results

    assert float(results.loc[results["score_5"] == 0.0, "overall_approval_rate"].iat[0]) == 0.5
    assert float(curve.loc[curve["score_5_cutoff"] == 0.0, "approval_rate"].iat[0]) == 0.5
    assert (results["overall_approval_rate"] <= 0.5 + 1e-12).all()
    assert (curve["approval_rate"] <= 0.5 + 1e-12).all()
