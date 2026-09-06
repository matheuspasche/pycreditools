"""PROTOTYPE — descartável. Card #155, mapa #111.

PERGUNTA
--------
O eixo de contrato pode sair da `CreditPolicy` e virar membro da premissa sem
mudar número nenhum? Isto é: o motor de HOJE já calcula

    contract = decision x take_up

com `decision` = produto só dos estágios de decisão, e `take_up` = um vetor por
linha (observado no keep-in, estimado/sorteado no swap-in)?

Se fatorar EXATO, mover o estágio é re-expressão pura: o número não muda, só o
endereço. Se não fatorar, a minha leitura da §A.3 da pesquisa está errada e o
card volta para a mesa.

NÃO É PRODUÇÃO. Sem testes, sem tratamento de erro, sem abstração.
Rodar:  python docs/research/prototype-155-contract-axis.py
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from pycreditools import CreditPolicy, col
from pycreditools.sample_data import generate_sample_data
from pycreditools.simulation import run_simulation
from pycreditools.stages import RateStage

warnings.filterwarnings("ignore")

N = 60_000
SEED = 7


# ---------------------------------------------------------------- utilidades


def base() -> pd.DataFrame:
    return generate_sample_data(n_applicants=N, seed=SEED)


def policy_com_takeup(*, hired: bool, calibrate_by: str | None) -> CreditPolicy:
    """A política de hoje: os filtros MAIS o estágio de take-up."""
    p = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        current_approval_col="approved",
        actual_default_col="actual_default",
        current_hired_col="hired" if hired else None,
        calibration_bins=5,
    )
    p = p.filter("entrada", (col("age") >= 18) & (col("vl_negativacao") <= 5000))
    p = p.cutoff("corte", {"score_5": 700})
    p = p.rate("take_up", base_rate=1.0, observed_col="hired", calibrate_by=calibrate_by)
    return p


def policy_sem_takeup(p: CreditPolicy) -> CreditPolicy:
    """A mesma política com o eixo de contrato removido da lista."""
    import dataclasses

    stages = tuple(s for s in p.stages if not isinstance(s, RateStage))
    return dataclasses.replace(p, stages=stages)


def vetor_take_up(df: pd.DataFrame, policy: CreditPolicy, method: str) -> pd.Series:
    """O vetor que a PREMISSA declararia, se o eixo de contrato morasse nela.

    Keep-in  -> a contratação observada (ADR 0011 / `calibrate_on="hired"`).
    Swap-in  -> a taxa estimada do livro (analítico) ou o sorteio (estocástico).

    A estimativa em si é reaproveitada do estágio de hoje de propósito: o que
    está sob teste é o REARRANJO, não a re-estimação.
    """
    stage = next(s for s in policy.stages if isinstance(s, RateStage))
    probs = stage._observed_probs(df, policy).fillna(0.0)

    keep_in = df[policy.current_approval_col] == 1
    swap_in = ~keep_in

    out = pd.Series(0.0, index=df.index)
    out.loc[keep_in] = df.loc[keep_in, "hired"].fillna(0.0).astype(float)

    if method == "analytical":
        out.loc[swap_in] = probs.loc[swap_in]
    else:
        draws = np.random.random(int(swap_in.sum()))
        out.loc[swap_in] = (draws < probs.loc[swap_in]).astype(float)
    return out


def delta(a: pd.Series, b: pd.Series) -> float:
    return float(np.abs(a.astype(float) - b.astype(float)).max())


# ------------------------------------------------------- teste 1: fatoração


def teste_1_fatoracao(df: pd.DataFrame) -> None:
    """O motor de hoje ja calcula contract = decision x take_up?

    NAO basta checar `decision * (contract/decision) == contract` — isso e zero
    por construcao. O teste real e comparar o take-up IMPLICITO na saida do
    motor contra o vetor que a PREMISSA declararia, calculado por fora.
    """
    print("\n" + "=" * 78)
    print("TESTE 1 — o take-up implicito no funil e o vetor da premissa?")
    print("=" * 78)
    print("  (|dif swap-in| compara o implicito contra `_observed_probs` calculado por fora)")

    for hired in (True, False):
        for calibrate_by in ("score", None):
            p = policy_com_takeup(hired=hired, calibrate_by=calibrate_by)

            np.random.seed(SEED)
            sim = run_simulation(df, p, method="analytical", drop_stages=False).data

            decision = sim["approved_pre_rate"].astype(float)
            contract = sim["new_approval"].astype(float)

            mask = decision > 0
            implicito = pd.Series(np.nan, index=sim.index)
            implicito.loc[mask] = contract.loc[mask] / decision.loc[mask]

            fora_faixa = int(((implicito < -1e-12) | (implicito > 1 + 1e-12)).sum())

            keep_in = df[p.current_approval_col] == 1
            swap_in = ~keep_in

            stage = next(s_ for s_ in p.stages if isinstance(s_, RateStage))
            esperado_swap = stage._observed_probs(df, p).fillna(0.0)

            alvo_swap = swap_in & mask
            d_swap = float(np.abs(implicito.loc[alvo_swap] - esperado_swap.loc[alvo_swap]).max())

            alvo_keep = keep_in & mask
            if hired:
                obs = df.loc[alvo_keep, "hired"].fillna(0.0).astype(float)
                d_keep = f"{float(np.abs(implicito.loc[alvo_keep] - obs).max()):.3e}"
            else:
                d_keep = "n/a"

            tag = f"hired={hired!s:<5} calibrate_by={str(calibrate_by):<5}"
            print(
                f"  {tag} fora_de_[0,1]={fora_faixa:<4} "
                f"|dif swap-in|={d_swap:.3e}  |dif keep-in vs hired|={d_keep}"
            )


# ------------------------------------- teste 2: ponta a ponta, sem o estagio


def teste_2_ponta_a_ponta(df: pd.DataFrame) -> None:
    """Tirar o estagio da lista e recompor por fora reproduz o mesmo vetor?"""
    print("\n" + "=" * 78)
    print("TESTE 2 — remover o estagio e recompor por fora (analitico, exato)")
    print("=" * 78)

    for hired in (True, False):
        for calibrate_by in ("score", None):
            p_a = policy_com_takeup(hired=hired, calibrate_by=calibrate_by)
            p_b = policy_sem_takeup(p_a)

            np.random.seed(SEED)
            a = run_simulation(df, p_a, method="analytical", drop_stages=False).data

            np.random.seed(SEED)
            b = run_simulation(df, p_b, method="analytical", drop_stages=False).data

            d_decision = delta(a["approved_pre_rate"], b["approved_pre_rate"])

            take_up = vetor_take_up(df, p_a, "analytical")
            contract_b = b["approved_pre_rate"].astype(float) * take_up
            d_contract = delta(a["new_approval"], contract_b)

            # A coluna `reason` e o UNICO lugar onde a ordem do funil nao e
            # inerte (`first_failed_col`, simulation.py:489). Se ela mudar, o
            # rearranjo nao e neutro.
            r_dif = int((a["reason"].fillna("") != b["reason"].fillna("")).sum())
            d_dif = int((a["decision"].fillna("") != b["decision"].fillna("")).sum())

            tag = f"hired={hired!s:<5} calibrate_by={str(calibrate_by):<5}"
            print(
                f"  {tag} |dif decision|={d_decision:.3e}  "
                f"|dif contract|={d_contract:.3e}  "
                f"linhas com `reason` diferente={r_dif}  `decision` diferente={d_dif}"
            )


# ------------------------------------------- teste 3: o que o rearranjo muda


def teste_3_o_que_muda(df: pd.DataFrame) -> None:
    """Onde o rearranjo NAO e neutro. Controle negativo do proprio protótipo."""
    print("\n" + "=" * 78)
    print("TESTE 3 — onde o rearranjo muda comportamento (controle negativo)")
    print("=" * 78)

    # 3a. Ordem do estagio na lista: hoje e inerte?
    p1 = policy_com_takeup(hired=True, calibrate_by="score")
    import dataclasses

    stages = list(p1.stages)
    rate = next(s for s in stages if isinstance(s, RateStage))
    stages.remove(rate)
    p2 = dataclasses.replace(p1, stages=tuple([rate] + stages))  # take-up PRIMEIRO

    np.random.seed(SEED)
    a = run_simulation(df, p1, method="analytical", drop_stages=False).data
    np.random.seed(SEED)
    b = run_simulation(df, p2, method="analytical", drop_stages=False).data

    print(
        f"  3a. take-up no fim x no inicio da lista: "
        f"|dif contract|={delta(a['new_approval'], b['new_approval']):.3e}  "
        f"|dif decision|={delta(a['approved_pre_rate'], b['approved_pre_rate']):.3e}"
    )

    # 3b. Standalone: simulation.py:551-556 reaplica o ULTIMO RateStage como PD
    #     — mas SO onde o desfecho nao e observado (`unknown_mask`,
    #     simulation.py:594). A base standalone observa tudo, entao o caminho
    #     fica morto. Aqui ele e FORCADO, mascarando 40% dos desfechos.
    from pycreditools.sample_data import generate_standalone_sample_data

    ds = generate_standalone_sample_data(n_applicants=N, seed=SEED)
    rng = np.random.default_rng(SEED)
    apagar = rng.random(len(ds)) < 0.40
    ds.loc[apagar, "actual_default"] = np.nan
    print(f"  3b. standalone com {int(apagar.sum())} desfechos mascarados de {len(ds)}")

    ps = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_5",),
        actual_default_col="actual_default",
    )
    ps = ps.cutoff("corte", {"score_5": 700})
    ps_rate = ps.rate("take_up", base_rate=0.7, variable=None, calibrate_by=None)

    np.random.seed(SEED)
    sa = run_simulation(ds, ps_rate, method="analytical", drop_stages=False).data
    np.random.seed(SEED)
    sb = run_simulation(ds, ps, method="analytical", drop_stages=False).data

    cpd = "simulated_default"
    apr_a = sa["new_approval"] > 0
    apr_b = sb["new_approval"] > 0
    print(
        f"      PD media do aprovado COM estagio: {sa.loc[apr_a, cpd].mean():.6f}  "
        f"SEM: {sb.loc[apr_b, cpd].mean():.6f}  "
        f"dif={abs(sa.loc[apr_a, cpd].mean() - sb.loc[apr_b, cpd].mean()):.6f}"
    )
    print(
        f"      linhas aprovadas sem desfecho observado: "
        f"COM={int((apr_a & sa[cpd].isna()).sum())}  SEM={int((apr_b & sb[cpd].isna()).sum())}"
    )

    # 3c. Dois RateStage na lista (o idioma v0.5 da masterclass: anti-fraude
    #     declarado como .rate). O eixo de contrato vira produto de dois.
    p3 = policy_com_takeup(hired=True, calibrate_by="score")
    p3 = p3.rate("antifraude", base_rate=1.0, observed_col="passed_antifraud", calibrate_by=None)
    np.random.seed(SEED)
    c = run_simulation(df, p3, method="analytical", drop_stages=False).data
    dec = c["approved_pre_rate"].astype(float)
    con = c["new_approval"].astype(float)
    m = dec > 0
    tu = (con[m] / dec[m])
    print(
        f"  3c. com DOIS RateStage: take_up implicito em [{tu.min():.4f}, {tu.max():.4f}], "
        f"ainda fatoriza |dif|={delta(con, dec * (con / dec.replace(0, np.nan)).fillna(0.0)):.3e}"
    )


def main() -> None:
    print(f"base sintetica: n={N}, seed={SEED}")
    df = base()
    print(f"keep-ins={int((df['approved'] == 1).sum())}  swap-ins={int((df['approved'] != 1).sum())}")
    teste_1_fatoracao(df)
    teste_2_ponta_a_ponta(df)
    teste_3_o_que_muda(df)
    print()


if __name__ == "__main__":
    main()
