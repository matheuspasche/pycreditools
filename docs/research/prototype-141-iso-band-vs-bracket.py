"""Medicao para o #141, pergunta 2: a banda iso-* e uma BANDA ou um PONTO?

Se um `.abs() <= tol` tipico devolve 0 ou 1 linha, entao "iso-aprovacao" nao e
predicado, e busca do vizinho mais proximo -- e o pandas puro vira armadilha
(exatamente o pecado do find_equivalent, que caia em .head(1) quando vazio).
Se devolve uma banda saudavel, o pandas puro e honesto e o verbo e dispensavel.

Roda contra release/v0.6 (185396c), mesmo caso da secao 6 do tutorial_masterclass
que o prototipo/141 ja usava.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from pycreditools import CreditPolicy, col, generate_sample_data
from pycreditools.sweep import run_sweep

warnings.filterwarnings("ignore")

APPROVAL, DEFAULT = "overall_approval_rate", "overall_default_rate"


def build(n=12000, seed=42, steps=45):
    df = generate_sample_data(n, seed=seed)
    policy = (
        CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            time_col="safra",
            calibration_bins=10,
        )
        .filter("Valid CPF", col("cpf_valido") == True)  # noqa: E712
        .filter("Negativation <= 1500", col("vl_negativacao") <= 1500)
        .filter("SCR arrears <= 3000", col("vl_vencido_scr") <= 3000)
        .filter("Protests <= 500", col("vl_protestos") <= 500)
        .rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")
        .stress(1.2)
    )
    lo, hi = df["score_5"].quantile([0.05, 0.95])
    step = (hi - lo) / (steps - 1)
    grid = [round(lo + i * step) for i in range(steps)]

    grades = {}
    for region, sub in df.groupby("region"):
        g = run_sweep(sub, policy, cutoff_grid={"score_5": grid}, directions={"score_5": "gte"})
        # as tres gemeas do #146, decisao 1+2: MEDIDAS do dado, uma por grupo.
        appr = sub["approved"].astype(float)
        hired = sub["hired"].astype(float)
        g["baseline_approval_rate"] = appr.mean()
        g["baseline_take_up_rate"] = hired.sum() / appr.sum()
        g["baseline_default_rate"] = sub.loc[hired > 0.5, "actual_default"].mean()
        grades[region] = g
    return df, grades


def pareto_rows(g, maximize, minimize):
    axes = maximize + minimize
    sign = pd.Series({**{c: -1.0 for c in maximize}, **{c: 1.0 for c in minimize}})
    pts = (g[axes] * sign).to_numpy()
    keep = []
    for i, p in enumerate(pts):
        dom = (pts <= p).all(axis=1) & (pts < p).any(axis=1)
        dom[i] = False
        keep.append(not dom.any())
    return g.loc[keep]


def main():
    df, grades = build()
    pts = sum(len(g) for g in grades.values())
    print(f"grade: {pts} pontos em {len(grades)} regioes, {len(df)} propostas\n")

    print("=" * 78)
    print("1. O VIGENTE CAI DENTRO DA FAIXA QUE A GRADE VARRE?")
    print("=" * 78)
    for r, g in sorted(grades.items()):
        b = g["baseline_approval_rate"].iloc[0]
        lo, hi = g[APPROVAL].min(), g[APPROVAL].max()
        inside = lo <= b <= hi
        print(
            f"  {r:<12} vigente={b:6.2%}   grade varre [{lo:6.2%}, {hi:6.2%}]"
            f"   {'DENTRO' if inside else '>>> FORA <<<'}"
        )

    print()
    print("=" * 78)
    print("2. QUANTAS LINHAS CAEM NA BANDA ISO-APROVACAO, POR TOLERANCIA")
    print("=" * 78)
    print(f"  (grade de {len(next(iter(grades.values())))} pontos por regiao)\n")
    header = "  tol      " + "".join(f"{r[:10]:>12}" for r in sorted(grades)) + "   vazias"
    print(header)
    for tol in (0.001, 0.0025, 0.005, 0.01, 0.02):
        counts, empties = [], 0
        for r, g in sorted(grades.items()):
            d = (g[APPROVAL] - g["baseline_approval_rate"]).abs()
            n = int((d <= tol).sum())
            counts.append(n)
            empties += n == 0
        print(f"  {tol:>6.2%}   " + "".join(f"{c:>12}" for c in counts) + f"   {empties}/{len(grades)}")

    print()
    print("=" * 78)
    print("3. IDEM, ISO-INADIMPLENCIA")
    print("=" * 78)
    print(header)
    for tol in (0.001, 0.0025, 0.005, 0.01, 0.02):
        counts, empties = [], 0
        for r, g in sorted(grades.items()):
            d = (g[DEFAULT] - g["baseline_default_rate"]).abs()
            n = int((d <= tol).sum())
            counts.append(n)
            empties += n == 0
        print(f"  {tol:>6.2%}   " + "".join(f"{c:>12}" for c in counts) + f"   {empties}/{len(grades)}")

    print()
    print("=" * 78)
    print("4. PASSO DA GRADE NO EIXO DE APROVACAO (o que 'tolerancia' compete)")
    print("=" * 78)
    for r, g in sorted(grades.items()):
        step = g[APPROVAL].sort_values().diff().dropna()
        print(
            f"  {r:<12} passo mediano={step.median():.3%}  min={step.min():.3%}  max={step.max():.3%}"
        )

    print()

    print("=" * 78)
    print("6. BRACKETING NO EIXO DE APROVACAO: os 2 pontos que ladeiam o vigente")
    print("=" * 78)
    print(f"{'regiao':<13}{'vigente':>9}{'linhas':>8}{'aprov. abaixo':>15}{'aprov. acima':>14}"
          f"{'inadimp. no par':>18}{'vs vigente':>12}")
    for r, g in sorted(grades.items()):
        b = g["baseline_approval_rate"].iloc[0]
        bd = g["baseline_default_rate"].iloc[0]
        below = g[g[APPROVAL] <= b]
        above = g[g[APPROVAL] >= b]
        if below.empty or above.empty:
            print(f"  {r:<11} vigente FORA da faixa varrida -> erro duro")
            continue
        lo = below.loc[below[APPROVAL].idxmax()]
        hi = above.loc[above[APPROVAL].idxmin()]
        n = 1 if lo.equals(hi) else 2
        print(f"{r:<13}{b:>9.2%}{n:>8}{lo[APPROVAL]:>15.2%}{hi[APPROVAL]:>14.2%}"
              f"{f'{lo[DEFAULT]:.2%} a {hi[DEFAULT]:.2%}':>18}{f'{bd:.2%}':>12}")

    print()
    print("=" * 78)
    print("6b. O PAR E UTIL?  largura do bracket nos dois eixos")
    print("=" * 78)
    for r, g in sorted(grades.items()):
        b = g["baseline_approval_rate"].iloc[0]
        lo = g[g[APPROVAL] <= b].pipe(lambda d: d.loc[d[APPROVAL].idxmax()])
        hi = g[g[APPROVAL] >= b].pipe(lambda d: d.loc[d[APPROVAL].idxmin()])
        print(f"  {r:<13} aprovacao: {hi[APPROVAL]-lo[APPROVAL]:.3%} de largura   "
              f"inadimplencia: {abs(hi[DEFAULT]-lo[DEFAULT]):.3%}   "
              f"corte score: {lo['score_5']:.0f} a {hi['score_5']:.0f}")

    print()
    print("=" * 78)
    print("7. CONTEXTO: TAMANHO DA FRONTEIRA DE PARETO")
    print("=" * 78)
    npar = sum(len(pareto_rows(g, [APPROVAL], [DEFAULT])) for g in grades.values())
    print(f"  fronteira = {npar} de {pts} pontos ({npar / pts:.1%} da grade)")


if __name__ == "__main__":
    main()
