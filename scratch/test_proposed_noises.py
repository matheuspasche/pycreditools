import sys
sys.path.insert(0, "c:/Users/Matheus/Documents/GitHub/pycreditools/src")
import pandas as pd
import numpy as np
from pycreditools import ModelEvaluator

def main():
    rng = np.random.default_rng(42)
    n = 1000000
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
        "employment": rng.choice(["Assalariado","Autônomo","Empresário","Desempregado"], n, p=[0.60,0.25,0.10,0.05]),
    })
    df["cpf_valido"]     = rng.choice([True,False], n, p=[0.998,0.002])
    df["vl_negativacao"] = rng.choice([0,1],n,p=[0.78,0.22]) * rng.lognormal(7.0,1.5,n).astype(int)
    df["vl_vencido_scr"] = rng.choice([0,1],n,p=[0.83,0.17]) * rng.lognormal(7.5,1.8,n).astype(int)
    df["vl_protestos"]   = rng.choice([0,1],n,p=[0.89,0.11]) * rng.lognormal(6.5,1.2,n).astype(int)

    u = rng.normal(0, 3.0, n)
    y = (-2.5 + df["region"].map(r_bias).astype(float) + (df["age"] < 25).astype(float)*1.0 + (~df["cpf_valido"]).astype(float)*4.0 + (df["income"] < 2000).astype(float)*0.5 + (df["employment"]=="Desempregado").astype(float)*1.2 + (df["vl_negativacao"] > 0).astype(float)*1.2 + (df["vl_negativacao"] > 2000).astype(float)*1.5 + (df["vl_vencido_scr"] > 0).astype(float)*1.0 + (df["vl_vencido_scr"] > 3000).astype(float)*1.8 + (df["vl_protestos"] > 0).astype(float)*1.5 + (df["vl_protestos"] > 500).astype(float)*2.0 + df["safra"].map(v_pen).astype(float) + u)
    df["true_pd"]        = 1.0 / (1.0 + np.exp(-y))
    df["actual_default"] = (rng.random(n) < df["true_pd"]).astype(int)
    def norm_cdf(x): return 1.0 / (1.0 + np.exp(-1.702 * x))
    s = -y

    noises = {
        "score_2": 6.0,
        "score_3": 5.4,
        "score_4": 4.8,
        "score_5": 4.2,
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
    df_hist = df[df["hired"] == 1].copy()

    all_scores = [f"score_{i}" for i in range(2,6)] + ["legacy_score"]
    ev = ModelEvaluator(df_hist, all_scores, "actual_default")
    ks = ev.compute_ks()
    
    print("=== NEW PROPOSED NOISES KS ===")
    for k, v in ks.items():
        print(f"{k}: {v*100:.2f}%")
        
    delta = ks["score_5"] - ks["legacy_score"]
    print(f"Delta (Score_5 - Legacy): {delta*100:.2f}%")

if __name__ == "__main__":
    main()
