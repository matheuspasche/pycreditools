"""Canonical synthetic bases for the tutorials, the studio and the test suite.

Two generators, deliberately separate:

- :func:`generate_sample_data` — an **incumbent** book: a legacy policy is in force, so
  the outcome is masked exactly where production masks it (`actual_default` is `NaN` for
  anyone who did not contract), and the only outcome observed for everyone is
  `market_default`, a 0/1 bureau flag.
- :func:`generate_standalone_sample_data` — a **greenfield** book: nothing rejected
  anyone, so `actual_default` is observed for every row and no incumbent column exists.

They are not one function behind a `scenario=` flag: the returned shape genuinely
differs, and a return type that changes with an argument is exactly the loose contract
v0.5 is removing elsewhere.

Two columns are deliberately absent from both bases:

- **No propensity / take-up column.** `RateStage` calibrates an *observed* outcome by
  decile (`observed_col` + `calibrate_by`), so a stored propensity has no consumer.
  Take-up is a reported metric — contracted ÷ approved (ADR 0008) — never a column.
- **No modelled PD column.** A modelled PD as a policy input is circular: it validates a
  policy against your own model's opinion. `market_default` is what a lender actually
  has for a reject: observed market reality from a bureau, as a 0/1 flag.

"""

import numpy as np
import pandas as pd

#: Quantile of `legacy_score` the incumbent policy cuts at. `generate_sample_data`
#: returns the frame alone — a caller that needs the threshold recomputes it with
#: `df["legacy_score"].quantile(LEGACY_APPROVAL_QUANTILE)`, which is the very expression
#: the generator used.
LEGACY_APPROVAL_QUANTILE = 0.78

_REGIONS = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
_REGION_PROBS = [0.45, 0.20, 0.18, 0.10, 0.07]
_REGION_BIAS = {
    "Sudeste": -0.2,
    "Sul": -0.3,
    "Nordeste": 0.25,
    "Centro-Oeste": 0.05,
    "Norte": 0.3,
}

#: Take-up by `score_5` decile (worst decile first): adverse selection. The best-scoring
#: applicants shop around and contract least, so default over *approved* and default over
#: *contracted* genuinely diverge — which is why ADR 0008's denominators matter.
_TAKE_UP_AT_WORST_DECILE = 0.95
_TAKE_UP_DECILE_STEP = 0.06

#: The 18 monthly vintages both generators draw `safra` from.
_VINTAGES = pd.date_range("2024-01-01", periods=18, freq="MS").strftime("%Y-%m").tolist()


def _sigmoid(x: np.ndarray | pd.Series) -> np.ndarray | pd.Series:
    return 1.0 / (1.0 + np.exp(-x))


def _applicants(rng: np.random.Generator, n: int) -> pd.DataFrame:
    """Identity, demographics and the bureau hard-filter candidates."""
    df = pd.DataFrame(
        {
            "applicant_id": range(1, n + 1),
            "safra": rng.choice(_VINTAGES, n),
            "region": rng.choice(_REGIONS, n, p=_REGION_PROBS),
            "age": rng.normal(38, 14, n).clip(16, 90).astype(int),
            "income": rng.lognormal(7.8, 0.6, n).astype(int),
            "employment": rng.choice(
                ["Assalariado", "Autônomo", "Empresário", "Desempregado"],
                n,
                p=[0.60, 0.25, 0.10, 0.05],
            ),
        }
    )
    df["cpf_valido"] = rng.choice([True, False], n, p=[0.998, 0.002])
    df["vl_negativacao"] = rng.choice([0, 1], n, p=[0.78, 0.22]) * rng.lognormal(
        7.0, 1.5, n
    ).astype(int)
    df["vl_vencido_scr"] = rng.choice([0, 1], n, p=[0.83, 0.17]) * rng.lognormal(
        7.5, 1.8, n
    ).astype(int)
    df["vl_protestos"] = rng.choice([0, 1], n, p=[0.89, 0.11]) * rng.lognormal(6.5, 1.2, n).astype(
        int
    )
    return df


def _risk_logit(rng: np.random.Generator, df: pd.DataFrame) -> pd.Series:
    """Latent log-odds of default, driven by the features plus a high-variance factor."""
    v_pen = {v: (i / 17) * 0.3 for i, v in enumerate(_VINTAGES)}

    u = rng.normal(0, 3.0, len(df))
    return (
        -2.5
        + df["region"].map(_REGION_BIAS).astype(float)
        + (df["age"] < 25).astype(float) * 1.0
        + (~df["cpf_valido"]).astype(float) * 4.0
        + (df["income"] < 2000).astype(float) * 0.5
        + (df["employment"] == "Desempregado").astype(float) * 1.2
        + (df["vl_negativacao"] > 0).astype(float) * 1.2
        + (df["vl_negativacao"] > 2000).astype(float) * 1.5
        + (df["vl_vencido_scr"] > 0).astype(float) * 1.0
        + (df["vl_vencido_scr"] > 3000).astype(float) * 1.8
        + (df["vl_protestos"] > 0).astype(float) * 1.5
        + (df["vl_protestos"] > 500).astype(float) * 2.0
        + df["safra"].map(v_pen).astype(float)
        + u
    )


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    return _sigmoid(1.702 * x)


def _score_ladder(
    rng: np.random.Generator,
    df: pd.DataFrame,
    y: pd.Series,
    *,
    with_legacy: bool,
) -> None:
    """Add the monotone score ladder in place: legacy < score_2 < ... < score_5.

    `c_noise` is shared across all scores, so the models correlate with each other the
    way real challenger models correlate with the incumbent. The per-score independent
    noise is calibrated to land legacy KS ~25% and `score_5` KS ~31%.
    """
    n = len(df)
    s = -y
    c_noise = rng.normal(0, 2.5, n)

    if with_legacy:
        legacy_latent = s + c_noise + rng.normal(0, 1.30, n)
        z_legacy = (legacy_latent - legacy_latent.mean()) / legacy_latent.std()
        df["legacy_score"] = np.round(_norm_cdf(z_legacy) * 1000).astype(int)

    for name, noise_std in {
        "score_2": 1.25,
        "score_3": 1.10,
        "score_4": 0.95,
        "score_5": 0.80,
    }.items():
        latent = s + c_noise + rng.normal(0, noise_std, n)
        z = (latent - latent.mean()) / latent.std()
        df[name] = np.round(_norm_cdf(z) * 1000).astype(int)


def _market_default(rng: np.random.Generator, y: pd.Series) -> np.ndarray:
    """A 0/1 bureau flag: did this person default *anywhere in the market*.

    Observed for every row, contracted or not — that is the whole point. It correlates
    with the lender's own risk without being it: the market is wider than this lender's
    product, so the flag is both more frequent and noisier than the lender's own outcome.
    """
    market_pd = _sigmoid(y + 0.4 + rng.normal(0, 1.0, len(y)))
    return (rng.random(len(y)) < market_pd).astype(int)


def _base(rng: np.random.Generator, n: int, *, with_legacy: bool) -> tuple[pd.DataFrame, pd.Series]:
    """The shared spine of both bases: features, the risk logit, the (pre-mask)
    outcome and the score ladder. Returns the frame and the risk logit `y`,
    which the incumbent base still needs for `market_default`.

    `actual_default` is drawn as `float` so both bases share the outcome dtype even
    though only the incumbent one later writes `NaN` into it.
    """
    df = _applicants(rng, n)
    y = _risk_logit(rng, df)
    df["actual_default"] = (rng.random(n) < _sigmoid(y)).astype(float)
    _score_ladder(rng, df, y, with_legacy=with_legacy)
    return df, y


def generate_sample_data(
    n_applicants: int = 20_000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate the incumbent base: a book with a legacy policy already in force.

    The outcome is masked the way production masks it — `actual_default` is `NaN` for
    every row that did not contract — so anything measured on rejects has to come from
    `market_default`, the 0/1 bureau flag observed for all rows.

    Columns:

    - identity / features: `applicant_id`, `safra`, `region`, `age`, `income`,
      `employment`
    - bureau (hard-filter candidates): `cpf_valido`, `vl_negativacao`, `vl_vencido_scr`,
      `vl_protestos`
    - scores: `legacy_score`, `score_2` ... `score_5` (monotone quality ladder)
    - `approved`: the incumbent's decision (~22% approval)
    - `passed_antifraud`: Bernoulli(0.90), independent of risk — a rate stage that is
      *not* take-up
    - `hired`: 0/1 observed contract outcome, with take-up falling as `score_5` rises
    - `actual_default`: 0/1 where `hired == 1`, `NaN` everywhere else
    - `market_default`: 0/1 for every row
    - `sample`: `DEV` for 2024 vintages, `OOT` after

    `passed_antifraud` is *not* folded into `approved` or `hired`: it is the incumbent's
    fraud screen expressed as data, so a simulated funnel can apply it as a `RateStage`
    and the take-up read (contracted ÷ approved) stays the take-up read.

    Args:
        n_applicants: Number of rows to generate.
        seed: Random seed for reproducibility; `None` draws fresh entropy.

    Returns:
        The frame alone. The legacy threshold is not returned — recompute it with
        `df["legacy_score"].quantile(LEGACY_APPROVAL_QUANTILE)`.
    """
    rng = np.random.default_rng(seed)
    n = n_applicants

    df, y = _base(rng, n, with_legacy=True)

    df["approved"] = 1
    df.loc[(df["age"] < 18) | (df["vl_negativacao"] > 5000), "approved"] = 0
    legacy_cut = float(df["legacy_score"].quantile(LEGACY_APPROVAL_QUANTILE))
    df.loc[df["legacy_score"] < legacy_cut, "approved"] = 0

    # Adverse selection: take-up falls as score rises. The decile is local to this
    # generator — no propensity column survives it (ADR 0008).
    decile = pd.qcut(df["score_5"], q=10, labels=False, duplicates="drop")
    take_up = _TAKE_UP_AT_WORST_DECILE - decile * _TAKE_UP_DECILE_STEP
    df["hired"] = df["approved"] * (rng.random(n) < take_up).astype(int)

    # The mask *is* the contract: no contract, no outcome.
    df.loc[df["hired"] == 0, "actual_default"] = np.nan

    # Drawn after the funnel so that adding these columns did not perturb the
    # approved/hired stream a given seed used to produce.
    df["passed_antifraud"] = (rng.random(n) < 0.90).astype(int)
    df["market_default"] = _market_default(rng, y)
    df["sample"] = np.where(df["safra"].str.startswith("2024"), "DEV", "OOT")

    return df


def generate_standalone_sample_data(
    n_applicants: int = 20_000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate the greenfield base: no incumbent policy, therefore no masking.

    Nothing rejected anyone, so `actual_default` is observed for every row and there is
    no `approved`, `legacy_score`, `hired`, `passed_antifraud` or `sample` column. No
    swap analysis or P&L delta is expressible on this base — that is the point of it
    being a separate function rather than a flag.

    Columns: the same features, the same bureau columns, the same `score_2` ... `score_5`
    ladder, and a fully observed `actual_default`. There is no
    `market_default`: the bureau flag exists so a lender can see the outcome of the
    applicants it *rejected*, and this base rejected nobody.

    Args:
        n_applicants: Number of rows to generate.
        seed: Random seed for reproducibility; `None` draws fresh entropy.

    Returns:
        DataFrame with one row per applicant.
    """
    rng = np.random.default_rng(seed)
    df, _ = _base(rng, n_applicants, with_legacy=False)
    return df
