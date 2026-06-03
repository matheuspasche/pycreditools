import json

def c_md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": [l + "\n" for l in s.split("\n")]}

def c_code(s):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
            "source": [l + "\n" for l in s.split("\n")]}

cells = []

cells.append(c_md("""# Masterclass: Arquitetura de Risco de Crédito
Substituição de política legada por nova arquitetura de score.

**Terminologia dos Quadrantes:**
| Quadrante | Antes | Agora | Performance observável? |
|-----------|-------|-------|------------------------|
| Keep In   | ✅ Aprovado | ✅ Aprovado | ✅ actual_default |
| Swap In   | ❌ Reprovado | ✅ Aprovado | ❌ simulated_default |
| Swap Out  | ✅ Aprovado | ❌ Reprovado | ✅ actual_default |
| Keep Out  | ❌ Reprovado | ❌ Reprovado | ❌ sem dados |
"""))

cells.append(c_code("""import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pycreditools import (
    CreditPolicy, TradeoffAnalyzer, col,
    find_risk_groups, ModelEvaluator, CustomStress, compare_policies
)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1200)
"""))

# ─── FASE 1: GERAÇÃO ────────────────────────────────────────────────────────
cells.append(c_md("""## 1. Geração da Base e Panorama Vigente
A política legada usa `legacy_score` e aprova ~22% do Top of Funnel."""))

cells.append(c_code("""def gerar_base(n=1_000_000):
    rng = np.random.default_rng(42)
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

    # Latent high-variance risk factor u ~ N(0, 3.0)
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

    # Shared noise to simulate high correlation between legacy/candidate models
    c_noise = rng.normal(0, 2.5, n)

    # Calibrated independent noise settings to hit targets: Legacy KS ~25%, Score_5 KS ~31% (Delta ~5.8%)
    legacy_noise = 1.30
    noises_candidates = {
        "score_2": 1.25,
        "score_3": 1.10,
        "score_4": 0.95,
        "score_5": 0.80,
    }

    # Legacy Score
    legacy_latent = s + c_noise + rng.normal(0, legacy_noise, n)
    z_legacy = (legacy_latent - legacy_latent.mean()) / legacy_latent.std()
    df["legacy_score"] = np.round(norm_cdf(z_legacy) * 1000).astype(int)

    # Candidate Scores
    for name, noise_std in noises_candidates.items():
        latent = s + c_noise + rng.normal(0, noise_std, n)
        z = (latent - latent.mean()) / latent.std()
        df[name] = np.round(norm_cdf(z) * 1000).astype(int)

    # Política histórica: top 22% do legacy_score
    df["approved"] = 1
    df.loc[(df["age"] < 18) | (df["vl_negativacao"] > 5000), "approved"] = 0
    legacy_cut = float(df["legacy_score"].quantile(0.78))
    df.loc[df["legacy_score"] < legacy_cut, "approved"] = 0

    df["score_decile"] = pd.qcut(df["score_5"], q=10, labels=False, duplicates="drop")
    df["take_up_rate"] = 0.95 - df["score_decile"] * 0.06
    df["hired"]        = df["approved"] * (rng.random(n) < df["take_up_rate"]).astype(int)
    df["sample"]       = np.where(df["safra"].str.startswith("2024"), "DEV", "OOT")
    return df, legacy_cut
"""))

cells.append(c_code("""df, LEGACY_CUT = gerar_base(1_000_000)
df_hist = df[df["hired"] == 1].copy()
df_dev  = df[df["sample"] == "DEV"].copy()

N         = len(df)
n_aprov   = int(df["approved"].sum())
n_hired   = int(df["hired"].sum())
bad_aprov = df[df["approved"]==1]["actual_default"].mean()
bad_hired = df_hist["actual_default"].mean()

print("=== PANORAMA ATUAL (POLÍTICA LEGADA) ===")
print(f"Top of Funnel:                  {N:>10,}")
print(f"Aprovados (Legacy Score p78):   {n_aprov:>10,}  ({n_aprov/N:.1%} do funil)")
print(f"Contratados (após take-up):     {n_hired:>10,}  ({n_hired/n_aprov:.1%} dos aprovados)")
print(f"Bad Rate Aprovados:             {bad_aprov:>10.2%}")
print(f"Bad Rate Contratados (P&L):     {bad_hired:>10.2%}   ← ALVO")
print(f"Legacy Score Cutoff (p78):      {LEGACY_CUT:>10,.0f}")
"""))

# ─── FASE 2: KS ─────────────────────────────────────────────────────────────
cells.append(c_md("""## 2. Poder Preditivo: KS na Carteira Vigente
A capacidade discriminatória de cada score **dentro da carteira contratada**."""))

cells.append(c_code("""all_scores = [f"score_{i}" for i in range(2,6)] + ["legacy_score"]
ev = ModelEvaluator(df_hist, all_scores, "actual_default")
ks = ev.compute_ks()

ks_df = (pd.DataFrame(list(ks.items()), columns=["Modelo","KS"])
           .sort_values("KS", ascending=False).reset_index(drop=True))
ks_df["KS (%)"] = ks_df["KS"].apply(lambda x: f"{x*100:.1f}")
ks_df["Power"]  = ks_df["KS"].apply(
    lambda x: "🔴 Fraco" if x<0.20 else ("🟡 Razoável" if x<0.30 else
              ("🟢 Bom" if x<0.45 else "🏆 Excelente")))
print("=== PODER PREDITIVO (KS NA CARTEIRA HISTÓRICA) ===")
print(ks_df[["Modelo","KS (%)","Power"]].to_string(index=False))

print("\\n=== TABELA DECIL DO SCORE CAMPEÃO (SCORE 5) ===")
t = ev.compute_ks_table("score_5", bins=10)
print(t.map(lambda x: f"{x:.3f}" if isinstance(x,float) else x).to_string(index=False))
"""))

# ─── FASE 3: HARD FILTERS + FUNIL ───────────────────────────────────────────
cells.append(c_md("""## 3. Escudos de Bureau e o Funil de Qualidade
O custo de cada etapa de filtro de bureau, incluindo o filtro de cutoff do score legado."""))

cells.append(c_code("""score_cols = [f"score_{i}" for i in range(2,6)]
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

policy_legacy_hf = (
    policy_hf
    .filter("Ponto de Corte Vigente", col("legacy_score") >= LEGACY_CUT)
)

# Build monotonic funnel sequence including the legacy score cutoff
masks = {
    "Top of Funnel":               pd.Series(True, index=df_dev.index),
    "Após CPF Válido":             df_dev["cpf_valido"] == True,
    "Após Teto Negativação":       df_dev["vl_negativacao"] <= 1500,
    "Após Teto SCR":               df_dev["vl_vencido_scr"] <= 3000,
    "Após Teto Protestos":         df_dev["vl_protestos"] <= 500,
    "Após Ponto de Corte Vigente": df_dev["legacy_score"] >= LEGACY_CUT,
}

cumulativo = pd.Series(True, index=df_dev.index)
print("=== FUNIL DE APROVAÇÃO (BASE DEV) ===")
print(f"{'Etapa':<28} {'Volume':>10}  {'% Funil':>9}  {'Δ Etapa':>9}")
print("─" * 60)
prev_n = len(df_dev)
for nome, m in masks.items():
    cumulativo = cumulativo & m
    n = int(cumulativo.sum())
    delta = f"{(n-prev_n)/prev_n:+.1%}" if nome != "Top of Funnel" else "─"
    print(f"{nome:<28} {n:>10,}  {n/len(df_dev):>9.1%}  {delta:>9}")
    prev_n = n

# Combined funnel simulation for the legacy policy representation
sim_legacy_hf = policy_legacy_hf.simulate(df_dev)
df_clean_legacy_hf = sim_legacy_hf.data[sim_legacy_hf.data["new_approval"] == 1.0].copy()
n_leg_hf = len(df_clean_legacy_hf)
print(f"{'Pós-todos os HF (combinado)':<28} {n_leg_hf:>10,}  {n_leg_hf/len(df_dev):>9.1%}")

# For candidate model tradeoff space, we clean up using the new policy's hard filters (excluding legacy cutoff)
sim_hf = policy_hf.simulate(df_dev)
df_clean_hf = sim_hf.data[sim_hf.data["new_approval"] == 1.0].copy()
"""))

# ─── FASE 4: TRADEOFF GLOBAL ─────────────────────────────────────────────────
cells.append(c_md("""## 4. Fronteira Eficiente: Todos os Modelos Candidatos
Relação de Aprovação × Risco para cada score com comparação da política atual."""))

cells.append(c_code("""cutoffs = np.linspace(
    df_clean_hf["score_5"].quantile(0.05),
    df_clean_hf["score_5"].quantile(0.95), 20
).astype(int).tolist()

res_list = []
for i in range(2,6):
    an = TradeoffAnalyzer(policy_hf).vary_cutoff(f"score_{i}", cutoffs)
    r  = an.run(df_dev, parallel=False)
    r["Score_Model"] = f"score_{i}"
    r["Cutoff"]      = r[f"score_{i}_cutoff"]
    res_list.append(r)
res_all = pd.concat(res_list)

import os
os.makedirs("images", exist_ok=True)

plt.figure(figsize=(10,6))
sns.lineplot(data=res_all, x="approval_rate", y="default_rate",
             hue="Score_Model", marker="o", linewidth=2)
plt.axhline(y=bad_aprov, color='r', linestyle='--', linewidth=1.5, label=f"Inad. Histórica ({bad_aprov:.1%})")
plt.axvline(x=n_aprov/N,  color='g', linestyle='--', linewidth=1.5, label=f"Aprov. Histórica ({n_aprov/N:.1%})")
plt.scatter(n_aprov/N, bad_aprov, color="black", s=180, marker="X", zorder=10, label="Política Legada (p78)")
plt.title("Fronteira Eficiente: Score 2 a 5", fontsize=14, fontweight='bold')
plt.xlabel("Taxa de Aprovação Global (% do ToF)"); plt.ylabel("Inad. Aprovados Projetada")
plt.gca().xaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f'{x:.0%}'))
plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f'{y:.0%}'))
plt.grid(True, linestyle=':', alpha=0.7); plt.legend(); plt.tight_layout()
plt.savefig("images/tradeoff_comparativo.png", dpi=150)
plt.show()
print("→ Score 5 domina claramente. Prosseguimos exclusivamente com ele.")
"""))

# ─── FASE 5: 3 PROPOSIÇÕES ───────────────────────────────────────────────────
cells.append(c_md("""## 5. As 3 Proposições Executivas (Score 5)
Três estratégias de apetite ao risco."""))

cells.append(c_code("""res_s5 = res_all[res_all["Score_Model"]=="score_5"].copy()

# 1. Conservadora
pol_cons = res_s5.iloc[(res_s5["approval_rate"] - n_aprov/N).abs().argsort()[:1]]
# 2. Agressiva
pol_agr  = res_s5.iloc[(res_s5["default_rate"]  - bad_aprov).abs().argsort()[:1]]
# 3. Neutra
mid_cut  = (pol_cons["Cutoff"].iloc[0] + pol_agr["Cutoff"].iloc[0]) / 2
pol_mid  = res_s5.iloc[(res_s5["Cutoff"] - mid_cut).abs().argsort()[:1]]

CUTOFF_GLOBAL = int(pol_cons["Cutoff"].iloc[0])

header = f"{'Cenário':<18} {'Cutoff':>8} {'Aprov. Global':>15} {'Inad. Aprovados':>17}"
print("=== AS 3 PROPOSIÇÕES EXECUTIVAS ===")
print(header); print("─"*60)
for label, pol in [("1. Conservadora", pol_cons),("2. Agressiva",pol_agr),("3. Neutra",pol_mid)]:
    print(f"{label:<18} {int(pol['Cutoff'].iloc[0]):>8} "
          f"{pol['approval_rate'].iloc[0]:>15.2%} {pol['default_rate'].iloc[0]:>17.2%}")
print(f"{'─'*60}")
print(f"{'Legacy (referência)':<18} {'─':>8} {n_aprov/N:>15.2%} {bad_aprov:>17.2%}")

plt.figure(figsize=(10,6))
sns.lineplot(data=res_s5, x="approval_rate", y="default_rate",
             marker="o", linewidth=2, color="royalblue", label="Score 5")
plt.axhline(y=bad_aprov, color='r', linestyle='--', linewidth=1.5, label="Inad. Histórica")
plt.axvline(x=n_aprov/N,  color='g', linestyle='--', linewidth=1.5, label="Aprov. Histórica")
for label, pol, cor in [("Conservadora",pol_cons,"gold"),("Agressiva",pol_agr,"darkorange"),("Neutra",pol_mid,"mediumpurple")]:
    plt.scatter(pol["approval_rate"],pol["default_rate"], color=cor, s=200, zorder=6, label=label)
plt.title("Proposições Executivas (Score 5)", fontsize=14, fontweight='bold')
plt.xlabel("Taxa de Aprovação Global"); plt.ylabel("Inad. Aprovados")
plt.gca().xaxis.set_major_formatter(plt.FuncFormatter(lambda x,_: f'{x:.0%}'))
plt.gca().yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f'{y:.0%}'))
plt.grid(True, linestyle=':', alpha=0.7); plt.legend(); plt.tight_layout()
plt.savefig("images/tradeoff_individual.png", dpi=150)
plt.show()
print(f"\\n✓ Decisão do Comitê: Estratégia Conservadora → Cutoff Global = {CUTOFF_GLOBAL}")
"""))

# ─── FASE 6: CORTES POR LOJA E POLÍTICA FINAL ──────────────────────────────
cells.append(c_md("""## 6. Adequação dos Pontos de Corte por Loja e Política Final
Adequamos o ponto de corte por região geográfica a fim de permitir aprovações em todas as lojas.
Calculamos os ratings baseando-nos rigorosamente na população aprovada sob esta política."""))

cells.append(c_code("""# Ajustes regionalizados para garantir representatividade e controle de inadimplência
# Calibrado para atingir cerca de 22% de taxa de aprovação local em cada região (refletindo o nível histórico)
cutoffs_loja = {
    "Sudeste":     781,
    "Sul":         793,
    "Centro-Oeste": 770,
    "Nordeste":    751,
    "Norte":       760,
}

print("=== PONTOS DE CORTE POR LOJA ===")
print(f"{'Loja':<15} {'Cutoff':>8}  {'Vol Loja':>10}  {'Aprov Local':>13}")
print("─"*52)
for loja, cut in sorted(cutoffs_loja.items()):
    mask_loja = df["region"] == loja
    n_loja    = mask_loja.sum()
    n_pass    = ((df["region"]==loja) & (df["score_5"]>=cut)).sum()
    print(f"{loja:<15} {int(cut):>8,}  {n_loja:>10,}  {n_pass/n_loja:>13.1%}")

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

# Simulamos a política final (sem stress por enquanto) para extrair o funil de aprovados
sim_final = policy_final.simulate(df)
res_final = sim_final.data
"""))

# ─── FASE 7: RATINGS ────────────────────────────────────────────────────────
cells.append(c_md("""## 7. Segmentação de Risco (Ward Clustering com max_crossings=1)
Treinado **estritamente na população aprovada** no DEV para evitar ratings vazios."""))

cells.append(c_code("""df_train_dev = res_final[
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

# Aplicamos a predição de ratings na base total (df) e na base simulada final (res_final)
pred_df = group_res.predict(df)
df["risk_cluster"] = pred_df["risk_rating"]
df["Rating"] = df["risk_cluster"].map(LABELS)

pred_res = group_res.predict(res_final)
res_final["Rating"] = pred_res["risk_rating"].map(LABELS)

print(f"Mapeamento cluster→rating: {LABELS}")

# Validação DEV vs OOT (focando nos aprovados pela nova política - sobreviventes)
df_kd = res_final[(res_final["new_approval"] > 0.0) & (res_final["sample"] == "DEV")]
df_ko = res_final[(res_final["new_approval"] > 0.0) & (res_final["sample"] == "OOT")]

val = pd.concat([
    df_kd.groupby("Rating")["actual_default"].mean().rename("Bad_DEV"),
    df_ko.groupby("Rating")["actual_default"].mean().rename("Bad_OOT"),
    df_kd.groupby("Rating").size().rename("Vol_DEV"),
    df_ko.groupby("Rating").size().rename("Vol_OOT"),
], axis=1).sort_index()

print("\\n=== VALIDAÇÃO CLUSTERING (SOBREVIVENTES): DEV vs OOT ===")
print(val.map(lambda x: f"{x:.2%}" if isinstance(x,float) else f"{int(x):,}").to_string())

# Estabilidade por Safra na população aprovada pela nova política
sfp = res_final[res_final["new_approval"] > 0.0].pivot_table(
    index="safra", columns="Rating", values="actual_default", aggfunc="mean"
)
plt.figure(figsize=(12,5))
for r in sfp.columns:
    plt.plot(sfp.index, sfp[r]*100, marker='o', lw=2, label=f"Rating {r}")

# Marcar divisor entre DEV (2024) e OOT (2025)
plt.axvline(x="2025-01", color="red", linestyle="--", lw=2, label="Divisor DEV/OOT")
plt.text("2024-06", plt.gca().get_ylim()[1]*0.85, "Desenvolvimento (DEV)", color="blue", fontsize=11, fontweight="bold", ha="center")
plt.text("2025-03", plt.gca().get_ylim()[1]*0.85, "Fora do Tempo (OOT)", color="red", fontsize=11, fontweight="bold", ha="center")

plt.title("Estabilidade dos Ratings por Safra (DEV vs OOT)", fontsize=14, fontweight='bold')
plt.xlabel("Safra"); plt.ylabel("Bad Rate (%)"); plt.xticks(rotation=45)
plt.grid(True, linestyle='--', alpha=0.6); plt.legend(title="Rating", loc="upper left"); plt.tight_layout()
plt.savefig("images/vintage_stability.png", dpi=150)
plt.show()
"""))

# ─── FASE 8: POLÍTICA MAGNUM ────────────────────────────────────────────────
cells.append(c_md("""## 8. A Política Magnum: Simulação com Agravamento Swap In"""))

cells.append(c_code("""# Agravamento Angulado Swap In (A=1.2× → E=1.60×)
def angulado(df_swap, pd_col):
    mapa = {"A": 1.20, "B": 1.30, "C": 1.40, "D": 1.50, "E": 1.60}
    fator = df_swap["Rating"].map(mapa).fillna(1.4)
    return (df_swap[pd_col] * fator).clip(0,1)

policy_magnum = (
    policy_final
    .add_stress(CustomStress(angulado))
)

sim_magnum = policy_magnum.simulate(df)
res_final_mag = sim_magnum.data
res_final_mag["hired_sim"] = res_final_mag["new_approval"]

aprov_nova_pct = (res_final_mag["new_approval"] > 0).sum() / N
print(f"✓ Aprovação global nova política: {aprov_nova_pct:.1%} (alvo ~{n_aprov/N:.1%})")
"""))

# ─── FASE 9: SWAPS ──────────────────────────────────────────────────────────
cells.append(c_md("""## 9. Dissecção dos Swaps: Quem Entra, Quem Sai
Calculamos a inadimplência observada real para o Swap Out baseado na performance histórica."""))

cells.append(c_code("""ki = res_final_mag[res_final_mag["scenario"]=="keep_in"]
si = res_final_mag[res_final_mag["scenario"]=="swap_in"]
so = res_final_mag[res_final_mag["scenario"]=="swap_out"]
ko = res_final_mag[res_final_mag["scenario"]=="keep_out"]

def bad_obs(subset, col_name="actual_default"):
    w = subset["hired_sim"]
    tot = w.sum()
    return (subset[col_name]*w).sum()/tot if tot > 0 else float("nan")

def bad_sim(subset):
    w = subset["hired_sim"]
    tot = w.sum()
    return (subset["simulated_default"]*w).sum()/tot if tot > 0 else float("nan")

print("=== QUADRANTES: VOLUME ESPERADO CONTRATADO E INADIMPLÊNCIA ===")
print(f"{'Quadrante':<12} {'Vol. Contratado':>17}  {'Bad Rate':>12}  {'Fonte'}")
print("─"*60)
print(f"{'Keep In':<12} {ki['hired_sim'].sum():>17,.0f}  {bad_obs(ki):>12.2%}  actual_default (observado)")
print(f"{'Swap In':<12} {si['hired_sim'].sum():>17,.0f}  {bad_sim(si):>12.2%}  simulated_default (agravado angulado)")

vol_so = so["hired"].sum()
bad_so = so[so["hired"]==1]["actual_default"].mean() if vol_so > 0 else float("nan")
print(f"{'Swap Out':<12} {vol_so:>17,.0f}  {bad_so:>12.2%}  actual_default (observado na carteira antiga)")
print(f"{'Keep Out':<12} {ko['hired_sim'].sum():>17,.0f}  {'N/A':>12}  sem dados (reprovados por ambas)")

# ── Raio-X Swap In por Rating ─────────────────────────────────────────────────
print("\\n=== RAIO-X DOS SWAP INS POR RATING ===")
si_r = si.groupby("Rating").apply(lambda g: pd.Series({
    "Vol_Esperado": g["hired_sim"].sum(),
    "Inad_Stressed": (g["simulated_default"]*g["hired_sim"]).sum() / g["hired_sim"].sum()
                      if g["hired_sim"].sum()>0 else float("nan")
})).reset_index()
si_r["Vol %"] = si_r["Vol_Esperado"] / si_r["Vol_Esperado"].sum()
print(f"{'Rating':>8} {'Vol. Esperado':>15} {'Vol %':>8} {'Inad Stressed':>15}")
print("─"*50)
for _, row in si_r.sort_index(ascending=False).iterrows():
    print(f"{row['Rating']:>8} {row['Vol_Esperado']:>15,.0f} {row['Vol %']:>8.1%} {row['Inad_Stressed']:>15.2%}")

# ── Swap In Rating × Loja ─────────────────────────────────────────────────────
print("\\n=== SWAP INS: RATING × LOJA (volume esperado contratado) ===")
si_lj = (si.groupby(["Rating","region"])["hired_sim"].sum()
           .unstack(fill_value=0)
           .sort_index(ascending=False))
print(si_lj.map(lambda x: f"{int(x):,}").to_string())

# ── Aprovados e Contratados por Rating × Quadrante ─────────────────────────
print("\\n=== APROVADOS E CONTRATADOS POR RATING E QUADRANTE ===")
def build_row(g):
    # Safer lookup using the groupby tuple name level 1 to prevent KeyError: 'scenario' on newer pandas versions
    scen = g.name[1]
    if scen == "swap_out":
        aprov = int((g["approved"] > 0).sum())
        hired = int(g["hired"].sum())
        bad = g.loc[g["hired"] == 1, "actual_default"].mean()
        return pd.Series({
            "Aprovados":    aprov,
            "Contratados":  hired,
            "Bad_Rate":     f"{bad:.2%}" if pd.notna(bad) else "N/A"
        })
    else:
        return pd.Series({
            "Aprovados":    int((g["new_approval"] > 0).sum()),
            "Contratados":  round(g["hired_sim"].sum(), 0),
            "Bad_Rate":     (
                f"{bad_sim(g):.2%}" if scen=="swap_in"
                else (f"{bad_obs(g):.2%}" if scen=="keep_in"
                      else "N/A")
            )
        })

rt_quad = (res_final_mag
            .groupby(["Rating","scenario"])
            .apply(build_row)
            .reset_index()
            .sort_values(["Rating","scenario"], ascending=[False,True]))
rt_quad["Contratados"] = rt_quad["Contratados"].apply(lambda x: f"{x:,.0f}" if isinstance(x,(int,float)) else x)
print(rt_quad.to_string(index=False))
"""))

# ─── FASE 10: DELTA RESUMO ──────────────────────────────────────────────────
cells.append(c_md("""## 10. Tabela Delta: Impacto P&L Executivo"""))

cells.append(c_code("""vol_novo  = ki["hired_sim"].sum() + si["hired_sim"].sum()
bad_novo  = (
    (ki["simulated_default"] * ki["hired_sim"]).sum() +
    (si["simulated_default"] * si["hired_sim"]).sum()
) / vol_novo if vol_novo > 0 else float("nan")

aprov_nova  = (res_final_mag["new_approval"] > 0).sum() / N
aprov_velha = n_aprov / N

print("=== TABELA DELTA: P&L EXECUTIVO ===")
print(f"{'Métrica':<35} {'Legacy':>10}  {'Nova':>10}  {'Δ Abs':>10}  {'Δ Rel':>10}")
print("─"*78)
print(f"{'Aprovação Global (% ToF)':<35} {aprov_velha:>10.2%}  {aprov_nova:>10.2%}  "
      f"{aprov_nova-aprov_velha:>+10.2%}  {(aprov_nova/aprov_velha)-1:>+10.1%}")
print(f"{'Bad Rate Contratado (P&L)':<35} {bad_hired:>10.2%}  {bad_novo:>10.2%}  "
      f"{bad_novo-bad_hired:>+10.2%}  {(bad_novo/bad_hired)-1:>+10.1%}")
print(f"{'Vol. Contratado Esperado':<35} {n_hired:>10,}  {vol_novo:>10,.0f}  "
      f"{vol_novo-n_hired:>+10,.0f}  {(vol_novo/n_hired)-1:>+10.1%}")
"""))

# ─── FASE 11: CRASH TEST ─────────────────────────────────────────────────────
cells.append(c_md("""## 11. Crash Test: O Airbag do Swap In
Até que ponto a política é resiliente e qual o breakeven de estresse dos Swap Ins."""))

cells.append(c_code("""an_st = TradeoffAnalyzer(policy_final)
# Stress Swap In up to 10x to find the exact breakeven factor
an_st.vary_stress_aggravation(np.linspace(1.0, 10.0, 37).tolist())
res_st = an_st.run(df_dev, parallel=False)

breakeven = None
for _, row in res_st.iterrows():
    if row["default_rate"] >= bad_hired:
        breakeven = row["aggravation_factor"]
        print(f"🔥 BREAKEVEN ENCONTRADO: Fator = {breakeven:.2f}×")
        print(f"   Bad Rate projetada: {row['default_rate']:.2%} (teto: {bad_hired:.2%})")
        print(f"   → A PD real dos Swap Ins teria que ser {breakeven:.2f}× pior do que")
        print(f"     o nosso modelo estima para o P&L novo empatar com o legado.")
        break
if not breakeven:
    print("A nova política não regride mesmo com fator 10.0× no Swap In.")

plt.figure(figsize=(10,5))
plt.plot(res_st["aggravation_factor"], res_st["default_rate"]*100,
         color="royalblue", lw=2, label="Bad Rate Nova Política")
plt.axhline(y=bad_hired*100, color='r', linestyle='--', lw=1.5,
            label=f"Bad Rate Legada ({bad_hired:.2%})")
if breakeven:
    plt.axvline(x=breakeven, color='orange', linestyle=':', lw=2,
                label=f"Breakeven ({breakeven:.2f}×)")
plt.xlabel("Fator de Agravamento Swap In (×)"); plt.ylabel("Bad Rate Contratado (%)")
plt.title("Crash Test: Resiliência da Nova Política", fontsize=14, fontweight='bold')
plt.grid(True, linestyle=':', alpha=0.7); plt.legend(); plt.tight_layout()
plt.savefig("images/crash_test.png", dpi=150)
plt.show()
"""))

notebook = {
    "cells": cells,
    "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
    "nbformat": 4, "nbformat_minor": 4
}

with open("tutorial_masterclass_v14.ipynb", "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)
print("tutorial_masterclass_v14.ipynb gerado!")
