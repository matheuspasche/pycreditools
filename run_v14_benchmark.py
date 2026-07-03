"""
Ground truth benchmark usando a API exata do tutorial_masterclass_v14.
Reproduz os numeros do Jupyter para comparar com o Dashboard.
"""
import sys, os, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import pandas as pd
import numpy as np
from pycreditools import CreditPolicy, TradeoffAnalyzer, col, find_risk_groups, CustomStress

# ============================================================
# 1. DADOS
# ============================================================
df = pd.read_csv('dataset_v14.csv')
df_dev = df[df['sample'] == 'DEV'].copy()
df_oot = df[df['sample'] == 'OOT'].copy()
N = len(df_dev)

# Legacy cutoff (assume mediana como "corte vigente" para referencia)
LEGACY_CUT = int(df_dev['legacy_score'].quantile(0.5))
AGRAVAMENTO_BASE = 1.2
SCORE_COLS = [f"score_{i}" for i in range(2, 6)]

print(f"=== DATASET ===")
print(f"Total: {len(df):,}  |  DEV: {len(df_dev):,}  |  OOT: {len(df_oot):,}")
print(f"Colunas: {list(df.columns)}")
print()

# ============================================================
# 2. POLITICA (igual ao V14)
# ============================================================
base_policy = CreditPolicy(
    applicant_id_col="applicant_id",
    score_cols=tuple(SCORE_COLS),
    current_approval_col="approved",
    actual_default_col="actual_default",
    time_col="safra"
)
policy_hf = (
    base_policy
    .filter("CPF Valido",       col("cpf_valido") == True)
    .filter("Teto Negativacao", col("vl_negativacao") <= 1500)
    .filter("Teto Atraso SCR",  col("vl_vencido_scr") <= 3000)
    .filter("Teto Protestos",   col("vl_protestos") <= 500)
)
policy_legacy_hf = policy_hf.filter("Corte Legado", col("legacy_score") >= LEGACY_CUT)

# ============================================================
# 3. FUNIL (igual ao V14)
# ============================================================
masks = {
    "Top of Funnel":          pd.Series(True, index=df_dev.index),
    "Apos CPF Valido":        df_dev["cpf_valido"] == True,
    "Apos Teto Negativacao":  df_dev["vl_negativacao"] <= 1500,
    "Apos Teto SCR":          df_dev["vl_vencido_scr"] <= 3000,
    "Apos Teto Protestos":    df_dev["vl_protestos"] <= 500,
    "Apos Corte Legado":      df_dev["legacy_score"] >= LEGACY_CUT,
}

cumulativo = pd.Series(True, index=df_dev.index)
print("=== FUNIL DE APROVACAO (BASE DEV) ===")
print(f"{'Etapa':<30} {'Volume':>10}  {'% Funil':>9}  {'D Etapa':>9}")
print("-" * 62)
prev_n = N
for nome, m in masks.items():
    cumulativo = cumulativo & m
    n = int(cumulativo.sum())
    delta = f"{(n-prev_n)/prev_n:+.1%}" if nome != "Top of Funnel" else "—"
    print(f"{nome:<30} {n:>10,}  {n/N:>9.1%}  {delta:>9}")
    prev_n = n
print()

# ============================================================
# 4. SIMULA POLITICA COM HF (sem legado)
# ============================================================
sim_hf = policy_hf.simulate(df_dev)
df_clean_hf = sim_hf.data[sim_hf.data["new_approval"] == 1.0].copy()
n_hf = len(df_clean_hf)

# Legacy reference
sim_leg = policy_legacy_hf.simulate(df_dev)
df_leg = sim_leg.data[sim_leg.data["new_approval"] == 1.0].copy()
n_aprov = len(df_leg)
bad_hired = df_leg["actual_default"].mean()

print(f"=== REFERENCIAS LEGADO ===")
print(f"Aprovados apos HF (sem score cutoff): {n_hf:,}  ({n_hf/N:.1%})")
print(f"Aprovados com corte legado:           {n_aprov:,}  ({n_aprov/N:.1%})")
print(f"Bad rate legado (aprovados):          {bad_hired:.4%}")
print(f"Legacy cutoff usado:                  {LEGACY_CUT}")
print()

# ============================================================
# 5. TRADEOFF (igual ao V14 - score_5)
# ============================================================
def angulado_tradeoff(df_swap, pd_col):
    return (df_swap[pd_col] * AGRAVAMENTO_BASE).clip(0, 1)

policy_tradeoff = policy_hf.add_stress(CustomStress(angulado_tradeoff))

cutoffs_s5 = np.linspace(
    df_clean_hf["score_5"].quantile(0.05),
    df_clean_hf["score_5"].quantile(0.95), 35
).astype(int).tolist()

print(f"=== TRADEOFF: score_5 (stress x{AGRAVAMENTO_BASE}) ===")
print(f"Cutoff range: {min(cutoffs_s5)} to {max(cutoffs_s5)}")

an = TradeoffAnalyzer(policy_tradeoff).vary_cutoff("score_5", cutoffs_s5)
res = an.run(df_dev, parallel=False)

print(f"Cenarios gerados: {len(res)}")
print()
print(f"{'Cutoff':>8} {'Approval%':>10} {'DefaultRate%':>13} {'Volume':>8}")
print("-" * 45)
for _, row in res.iterrows():
    cutoff_val = row.get("score_5_cutoff", row.get("cutoff", "?"))
    appr = row.get("approval_rate", 0) * 100
    dr = row.get("default_rate", 0) * 100
    vol = row.get("volume", 0)
    print(f"{cutoff_val:>8}  {appr:>9.2f}%  {dr:>12.2f}%  {vol:>8,.0f}")

print()

# Find neutral scenario (closest approval_rate to legacy)
legacy_appr = n_aprov / N
diffs = (res["approval_rate"] - legacy_appr).abs()
neutral_idx = diffs.idxmin()
neutral = res.loc[neutral_idx]
print(f"=== CENARIO NEUTRO (mais proximo do legado: {legacy_appr:.1%}) ===")
print(f"  Cutoff score_5:  {neutral.get('score_5_cutoff', '?')}")
print(f"  Approval Rate:   {neutral.get('approval_rate', 0):.4%}")
print(f"  Default Rate:    {neutral.get('default_rate', 0):.4%}")
print(f"  Volume:          {neutral.get('volume', 0):,.0f}")
print()
print("=== BENCHMARK COMPLETO ===")
