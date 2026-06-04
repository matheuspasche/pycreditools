import numpy as np
import pandas as pd


def generate_sample_data(
    n_applicants: int = 20_000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate a realistic synthetic credit dataset matching the Masterclass V14 structure.

    Args:
        n_applicants: Number of rows to generate.
        seed: Random seed for reproducibility.

    Returns:
        DataFrame with synthetic applicants and multiple scores/features.
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    regions = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
    r_probs = [0.45, 0.20, 0.18, 0.10, 0.07]
    r_bias = {"Sudeste": -0.2, "Sul": -0.3, "Nordeste": 0.25, "Centro-Oeste": 0.05, "Norte": 0.3}
    vintages = pd.date_range("2024-01-01", periods=18, freq="MS").strftime("%Y-%m").tolist()
    v_pen = {v: (i / 17) * 0.3 for i, v in enumerate(vintages)}

    df = pd.DataFrame(
        {
            "applicant_id": range(1, n_applicants + 1),
            "safra": rng.choice(vintages, n_applicants),
            "region": rng.choice(regions, n_applicants, p=r_probs),
            "age": rng.normal(38, 14, n_applicants).clip(16, 90).astype(int),
            "income": rng.lognormal(7.8, 0.6, n_applicants).astype(int),
            "employment": rng.choice(
                ["Assalariado", "Autônomo", "Empresário", "Desempregado"],
                n_applicants,
                p=[0.60, 0.25, 0.10, 0.05],
            ),
        }
    )
    df["cpf_valido"] = rng.choice([True, False], n_applicants, p=[0.998, 0.002])
    df["vl_negativacao"] = rng.choice([0, 1], n_applicants, p=[0.78, 0.22]) * rng.lognormal(
        7.0, 1.5, n_applicants
    ).astype(int)
    df["vl_vencido_scr"] = rng.choice([0, 1], n_applicants, p=[0.83, 0.17]) * rng.lognormal(
        7.5, 1.8, n_applicants
    ).astype(int)
    df["vl_protestos"] = rng.choice([0, 1], n_applicants, p=[0.89, 0.11]) * rng.lognormal(
        6.5, 1.2, n_applicants
    ).astype(int)

    # Latent high-variance risk factor u
    u = rng.normal(0, 3.0, n_applicants)

    y = (
        -2.5
        + df["region"].map(r_bias).astype(float)
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

    df["true_pd"] = 1.0 / (1.0 + np.exp(-y))
    df["actual_default"] = (rng.random(n_applicants) < df["true_pd"]).astype(int)

    def norm_cdf(x):
        return 1.0 / (1.0 + np.exp(-1.702 * x))

    s = -y

    # Shared noise to simulate high correlation between legacy/candidate models
    c_noise = rng.normal(0, 2.5, n_applicants)

    # Calibrated independent noise settings to hit targets: Legacy KS ~25%, Score_5 KS ~31% (Delta ~5.8%)
    legacy_noise = 1.30
    noises_candidates = {
        "score_2": 1.25,
        "score_3": 1.10,
        "score_4": 0.95,
        "score_5": 0.80,
    }

    # Legacy Score
    legacy_latent = s + c_noise + rng.normal(0, legacy_noise, n_applicants)
    z_legacy = (legacy_latent - legacy_latent.mean()) / legacy_latent.std()
    df["legacy_score"] = np.round(norm_cdf(z_legacy) * 1000).astype(int)

    # Candidate Scores
    for name, noise_std in noises_candidates.items():
        latent = s + c_noise + rng.normal(0, noise_std, n_applicants)
        z = (latent - latent.mean()) / latent.std()
        df[name] = np.round(norm_cdf(z) * 1000).astype(int)

    # Historical approval: based on age >= 18, negative list, and legacy_score >= p78 (p78 threshold ~789)
    df["approved"] = 1
    df.loc[(df["age"] < 18) | (df["vl_negativacao"] > 5000), "approved"] = 0
    legacy_cut = float(df["legacy_score"].quantile(0.78))
    df.loc[df["legacy_score"] < legacy_cut, "approved"] = 0

    # Steeper contract take-up rate (seeker behavior)
    df["score_decile"] = pd.qcut(df["score_5"], q=10, labels=False, duplicates="drop")
    df["conversion_rate"] = 0.95 - df["score_decile"] * 0.06

    # Hired status
    df["hired"] = df["approved"] * (rng.random(n_applicants) < df["conversion_rate"]).astype(int)

    # Hide actual defaults for rejected/non-hired applicants
    df.loc[df["hired"] == 0, "actual_default"] = np.nan

    return df
