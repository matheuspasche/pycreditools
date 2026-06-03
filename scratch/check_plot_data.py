import sys
sys.path.insert(0, "c:/Users/Matheus/Documents/GitHub/pycreditools/src")
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pycreditools import (
    CreditPolicy, col, find_risk_groups, ModelEvaluator, CustomStress
)

def main():
    rng = np.random.default_rng(42)
    n = 100000
    regions  = ["Sudeste","Sul","Nordeste","Centro-Oeste","Norte"]
    r_probs  = [0.45, 0.20, 0.18, 0.10, 0.07]
    r_bias   = {"Sudeste": -0.2, "Sul": -0.3, "Nordeste": 0.25, "Centro-Oeste": 0.05, "Norte": 0.3}
    vintages = pd.date_range("2024-01-01", periods=18, freq="MS").strftime("%Y-%m").tolist()
    v_pen   = {v: (i/17)*0.3 for i, v in enumerate(vintages)}

    df = pd.DataFrame({
        "applicant_id": range(1, n+1),
        "safra":  rng.choice(vintages, n),
        "region": rng.choice(regions, n, p=r_probs),
        "age":    rng.normal(38, 14, n).clip(16, 90).astype(int),
        "income": rng.lognormal(7.8, 0.6, n).astype(int),
        "employment": rng.choice(["Assalariado","Autônomo","Empresário","Desempregado"],
                                  n, p=[0.60,0.25,0.10,0.05]),
    })
    df["cpf_valido"]     = rng.choice([True,False], n, p=[0.998,0.002])
    df["vl_negativacao"] = rng.choice([0,1],n,p=[0.78,0.22]) * rng.lognormal(7.0,1.5,n).astype(int)
    df["vl_vencido_scr"] = rng.choice([0,1],n,p=[0.83,0.17]) * rng.lognormal(7.5,1.8,n).astype(int)
    df["vl_protestos"]   = rng.choice([0,1],n,p=[0.89,0.11]) * rng.lognormal(6.5,1.2,n).astype(int)

    u = rng.normal(0, 3.0, n)
    y = (
        -2.5
        + df["region"].map(r_bias).astype(float)
        + (df["age"] < 25).astype(float)                * 1.0
        + (~df["cpf_valido"]).astype(float)              * 4.0
        + (df["income"] < 2000).astype(float)            * 0.5
        + (df["employment"]=="Desempregado").astype(float)* 1.2
        + (df["vl_negativacao"] >    0).astype(float)   * 1.2
        + (df["vl_negativacao"] > 2000).astype(float)   * 1.5
        + (df["vl_vencido_scr"] >    0).astype(float)   * 1.0
        + (df["vl_vencido_scr"] > 3000).astype(float)   * 1.8
        + (df["vl_protestos"]   >    0).astype(float)   * 1.5
        + (df["vl_protestos"]   >  500).astype(float)   * 2.0
        + df["safra"].map(v_pen).astype(float)
        + u
    )

    df["true_pd"]        = 1.0 / (1.0 + np.exp(-y))
    df["actual_default"] = (rng.random(n) < df["true_pd"]).astype(int)

    def norm_cdf(x):
        return 1.0 / (1.0 + np.exp(-1.702 * x))

    s = -y
    noises = {
        "score_2": 6.5,
        "score_3": 5.8,
        "score_4": 5.1,
        "score_5": 4.5,
        "legacy_score": 2.8
    }

    for name, noise in noises.items():
        latent = s + rng.normal(0, noise, n)
        z = (latent - latent.mean()) / latent.std()
        df[name] = np.round(norm_cdf(z) * 1000).astype(int)

    df["approved"] = 1
    df.loc[(df["age"] < 18) | (df["vl_negativacao"] > 5000), "approved"] = 0
    legacy_cut = float(df["legacy_score"].quantile(0.78))
    df.loc[df["legacy_score"] < legacy_cut, "approved"] = 0

    df["score_decile"] = pd.qcut(df["score_5"], q=10, labels=False, duplicates="drop")
    df["take_up_rate"] = 0.90 - df["score_decile"] * 0.05
    df["hired"]        = df["approved"] * (rng.random(n) < df["take_up_rate"]).astype(int)
    df["sample"]       = np.where(df["safra"].str.startswith("2024"), "DEV", "OOT")

    score_cols = [f"score_{i}" for i in range(2,6)]
    base_policy = CreditPolicy(
        applicant_id_col="applicant_id", score_cols=score_cols,
        current_approval_col="approved",  actual_default_col="actual_default",
        time_col="safra"
    )
    policy_hf = (
        base_policy
        .filter("CPF Válido",       col("cpf_valido") == True)
        .filter("Teto Negativação",  col("vl_negativacao") <= 1500)
        .filter("Teto Atraso SCR",   col("vl_vencido_scr") <= 3000)
        .filter("Teto Protestos",    col("vl_protestos") <= 500)
    )

    cutoffs_loja = {
        "Sudeste":     781,
        "Sul":         793,
        "Centro-Oeste": 770,
        "Nordeste":    751,
        "Norte":       760,
    }

    def politica_loja(df_in):
        passa = pd.Series(False, index=df_in.index)
        for loja, cut in cutoffs_loja.items():
            passa.loc[(df_in["region"]==loja) & (df_in["score_5"]>=cut)] = True
        return passa

    policy_final = (
        policy_hf
        .filter("Score Regionalizado", politica_loja)
        .rate("Propensão de Contrato", base_rate=1.0, variable="take_up_rate")
    )

    sim_final = policy_final.simulate(df)
    res_final = sim_final.data

    df_train_dev = res_final[
        (res_final["new_approval"] > 0.0) &
        (res_final["sample"] == "DEV")
    ].copy()

    group_res = find_risk_groups(
        data=df_train_dev,
        score_cols="score_5",
        default_col="actual_default",
        bins=30, max_groups=5, min_vol_ratio=0.01,
        method="ward", time_col="safra", max_crossings=1
    )

    cluster_pd = (df_train_dev.assign(rc=group_res.data["risk_rating"])
                  .groupby("rc")["actual_default"].mean()
                  .sort_values())

    sorted_clusters = cluster_pd.index.tolist()
    LABELS = {c: l for c, l in zip(sorted_clusters, ["A","B","C","D","E"][:len(sorted_clusters)])}

    pred_res = group_res.predict(res_final)
    res_final["Rating"] = pred_res["risk_rating"].map(LABELS)

    print("Unique values of res_final['Rating'] in DEV:")
    print(res_final[res_final["sample"] == "DEV"]["Rating"].value_counts(dropna=False))
    print("Unique values of res_final['Rating'] in OOT:")
    print(res_final[res_final["sample"] == "OOT"]["Rating"].value_counts(dropna=False))

    sfp = res_final[res_final["new_approval"] > 0.0].pivot_table(
        index="safra", columns="Rating", values="actual_default", aggfunc="mean"
    )
    print("Pivot table index (safras) in sfp:")
    print(sfp.index.tolist())
    print("Pivot table values:")
    print(sfp)

if __name__ == "__main__":
    main()
