"""PROTOTIPO DESCARTAVEL -- card #141. Nao importar; nao e API.

Pergunta (#141): que forma tem a camada de selecao sobre a grade -- quantos
verbos, e Pareto e um deles ou um *tipo* de otimizacao?

Rodar:  python src/pycreditools/examples/prototype_141_selection_shape.py

O que este arquivo faz: escreve o caso real da secao 6 do tutorial_masterclass
(grade -> Pareto -> apetite -> corte por regiao) nas TRES formas na mesa, ponta
a ponta, contra dados reais do gerador. As tres produzem o mesmo numero; o que
muda e so a chamada da camada de selecao. Leia o codigo de cada forma, nao a
saida -- a saida so prova que as tres rodam.

Fixado pelo #122, nao reaberto aqui:
  - a selecao recebe a grade pronta (nao ve Study, nao ve base, nao roda motor)
  - nao existe alvo como tipo; apetite e filtro do humano
  - morrem target_default_rate, min_approval_rate, tradeoff_score, .iloc[0]
  - Pareto e o unico pedaco do optimize de hoje que sobrevive

Recorte do #141 (comentario de auditoria, 2026-08-17):
  - este card decide a GRAMATICA, nao o NOME. Se o verbo se chama `optimize`
    e do ponto 8 do #123. Por isso a forma 2 aqui usa um nome neutro (`choose`)
    -- leia como "um verbo com tipo declarado por argumento", name-agnostic.
  - a assinatura-uniao da forma 2 e o preco DESTA forma, nao inferencia
    silenciosa (#132).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import pandas as pd

from pycreditools import CreditPolicy, col, generate_sample_data
from pycreditools.sweep import run_sweep

warnings.filterwarnings("ignore")

APPROVAL, DEFAULT = "overall_approval_rate", "overall_default_rate"


# ----------------------------------------------------------------------------
# nucleo compartilhado: dominancia de Pareto, tabela -> tabela.
# Identico nas tres formas. So a porta de entrada muda.
# ----------------------------------------------------------------------------
def _pareto_rows(grade: pd.DataFrame, maximize: list[str], minimize: list[str]) -> pd.DataFrame:
    axes = maximize + minimize
    sign = pd.Series({**{c: -1.0 for c in maximize}, **{c: 1.0 for c in minimize}})
    pts = (grade[axes] * sign).to_numpy()  # tudo vira "menor e melhor"
    keep = []
    for i, p in enumerate(pts):
        dominated = ((pts <= p).all(axis=1) & (pts < p).any(axis=1))
        dominated[i] = False
        keep.append(not dominated.any())
    return grade.loc[keep].sort_values(maximize[0]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# FORMA 1 -- verbos pequenos irmaos.  pareto() e um verbo, como slice_max().
# ----------------------------------------------------------------------------
def pareto(grade, *, maximize, minimize):
    return _pareto_rows(grade, list(maximize), list(minimize))


# ----------------------------------------------------------------------------
# FORMA 2 -- um verbo, tipo declarado por argumento.  NOME NEUTRO de proposito.
# O preco aparece na assinatura: maximize/minimize so valem para kind="pareto".
# ----------------------------------------------------------------------------
def choose(grade, *, kind, maximize=None, minimize=None, n=None, by=None):
    if kind == "pareto":
        if maximize is None or minimize is None:
            raise TypeError("kind='pareto' exige maximize= e minimize=")
        if n is not None or by is not None:
            raise TypeError("n=/by= nao valem para kind='pareto'")
        return _pareto_rows(grade, list(maximize), list(minimize))
    if kind == "top":  # segundo tipo hipotetico, so para mostrar a uniao
        if by is None or n is None:
            raise TypeError("kind='top' exige by= e n=")
        if maximize is not None or minimize is not None:
            raise TypeError("maximize=/minimize= nao valem para kind='top'")
        return grade.nlargest(n, by).reset_index(drop=True)
    raise ValueError(f"kind desconhecido: {kind!r}")


# ----------------------------------------------------------------------------
# FORMA 3 -- estrategia como objeto.  Assinatura honesta por estrategia.
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Pareto:
    maximize: tuple[str, ...]
    minimize: tuple[str, ...]

    def apply(self, grade):
        return _pareto_rows(grade, list(self.maximize), list(self.minimize))


@dataclass(frozen=True)
class Top:
    by: str
    n: int

    def apply(self, grade):
        return grade.nlargest(self.n, self.by).reset_index(drop=True)


def select(grade, strategy):
    return strategy.apply(grade)


# ----------------------------------------------------------------------------
# o caso real: grade por regiao (motor de verdade, uma vez so)
# ----------------------------------------------------------------------------
def build_grades(n=12000, seed=42, steps=45):
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

    grades, sizes = {}, {}
    for region, sub in df.groupby("region"):
        grades[region] = run_sweep(
            sub, policy, cutoff_grid={"score_5": grid}, directions={"score_5": "gte"}
        )
        sizes[region] = len(sub)
    return df, grades, sizes


# ----------------------------------------------------------------------------
# secao 6 ponta a ponta.  `frontier_of` e A UNICA COISA que muda entre as formas.
# ----------------------------------------------------------------------------
def section_6(grades, sizes, total, frontier_of, appetite_max_default=0.12):
    pareto_only = {r: frontier_of(g) for r, g in grades.items()}

    # apetite: filtro do humano sobre a tabela (#122 -- nao e tipo, nao e alvo)
    frontiers = {r: f[f[DEFAULT] <= appetite_max_default] for r, f in pareto_only.items()}

    def agg_for_tau(tau):
        cuts, weighted = {}, 0.0
        for region, f in frontiers.items():
            row = f.iloc[(f[DEFAULT] - tau).abs().argmin()]
            cuts[region] = int(round(row["score_5"]))
            weighted += row[APPROVAL] * sizes[region]
        return cuts, weighted / total

    budget = sum(
        f.iloc[(f[DEFAULT] - 0.09).abs().argmin()][APPROVAL] * sizes[r]
        for r, f in frontiers.items()
    ) / total

    lo, hi = 0.03, 0.15
    for _ in range(40):
        mid = (lo + hi) / 2
        if agg_for_tau(mid)[1] < budget:
            lo = mid
        else:
            hi = mid
    cuts, agg = agg_for_tau((lo + hi) / 2)
    return pareto_only, frontiers, cuts, agg, (lo + hi) / 2


FORMS = {
    "FORMA 1 -- verbos irmaos pequenos": (
        'pareto(grade, maximize=["overall_approval_rate"], minimize=["overall_default_rate"])',
        lambda g: pareto(g, maximize=[APPROVAL], minimize=[DEFAULT]),
    ),
    "FORMA 2 -- um verbo, kind= (nome neutro)": (
        'choose(grade, kind="pareto", maximize=["overall_approval_rate"], minimize=["overall_default_rate"])',
        lambda g: choose(g, kind="pareto", maximize=[APPROVAL], minimize=[DEFAULT]),
    ),
    "FORMA 3 -- estrategia como objeto": (
        'select(grade, Pareto(maximize=("overall_approval_rate",), minimize=("overall_default_rate",)))',
        lambda g: select(g, Pareto(maximize=(APPROVAL,), minimize=(DEFAULT,))),
    ),
}


def main():
    print(__doc__.split("Fixado pelo")[0].strip())
    print("\ncarregando grade real (motor de verdade, uma vez so)...")
    df, grades, sizes = build_grades()
    total = len(df)
    pts = sum(len(g) for g in grades.values())
    print(f"grade: {pts} pontos em {len(grades)} regioes, {total} propostas\n")

    results = {}
    for name, (code, frontier_of) in FORMS.items():
        print("=" * 78)
        print(name)
        print("=" * 78)
        print("  a chamada da camada de selecao:\n")
        print(f"      frontier = {code}\n")
        pareto_only, frontiers, cuts, agg, tau = section_6(grades, sizes, total, frontier_of)
        npar = sum(len(f) for f in pareto_only.values())
        kept = sum(len(f) for f in frontiers.values())
        print(f"  fronteira de Pareto:      {npar} de {pts} pontos ({npar / pts:.1%} da grade)")
        print(f"  apos o filtro de apetite: {kept} de {pts} pontos ({kept / pts:.1%} da grade)")
        print(f"  tau comum = {tau:.2%}   aprovacao agregada = {agg:.2%}")
        print("  cortes por regiao: " + ", ".join(f"{r}={c}" for r, c in sorted(cuts.items())))
        print()
        results[name] = (npar, kept, tuple(sorted(cuts.items())), round(agg, 6))

    print("=" * 78)
    print("AS TRES DAO O MESMO NUMERO?", "sim" if len(set(results.values())) == 1 else "NAO")
    print("=" * 78)

    print("""
O QUE O PROTOTIPO FORCA (leia com o codigo acima na frente)

1. A fronteira e grande.  #143 mediu 39,7% da grade em 2-D; aqui Pareto
   sozinho devolve a fracao impressa acima -- e ela SOBE com a resolucao da
   grade (43% a 30 passos, 88% a 45 passos neste livro), porque mais pontos
   proximos e mais gente nao-dominada.  A saida da selecao e uma TABELA grande,
   nunca um ponto, e quanto melhor a grade pior fica.  Esse e o argumento mais
   forte contra qualquer verbo que cheire a "acha o melhor" -- e vale igual nas
   tres formas.  O que corta de verdade e o apetite, a linha seguinte.

2. Onde a forma 2 doi: rode o bloco abaixo.  A assinatura-uniao so aparece
   quando existe um segundo kind -- com um so, a forma 2 e indistinguivel da 1.
   Ou seja: a forma 2 so se paga se voce ja sabe que vem um segundo tipo.

3. O apetite nao ganhou verbo em nenhuma das tres: e `f[f[DEFAULT] <= 0.12]`,
   pandas puro (veja `section_6`).  Se ele merecesse verbo, apareceria aqui
   como atrito -- e nao aparece.  Isso e um voto do codigo, nao meu.

4. groupby: as tres rodam DENTRO de um loop por regiao, porque a grade ja vem
   por regiao.  Nenhuma das formas facilita ou atrapalha -- o encadeamento com
   groupby nao separa as tres, entao nao deveria pesar na decisao.

5. #140: o caminho rapido erra a inadimplencia em ate 0,58 p.p., com o maior
   erro na banda de decisao.  Nenhuma das tres formas deve apresentar um ponto
   como "o otimo" -- a precisao nao existe.  A forma que mais convida a isso e
   a que tiver um verbo no singular com cara de resposta unica.
""")

    print("-" * 78)
    print("O PRECO DA FORMA 2, ao vivo (um segundo kind entra em cena):")
    print("-" * 78)
    g = next(iter(grades.values()))
    for call, fn in [
        ('choose(grade, kind="top", by=APPROVAL, n=3)', lambda: choose(g, kind="top", by=APPROVAL, n=3)),
        ('choose(grade, kind="top", maximize=[APPROVAL], minimize=[DEFAULT])',
         lambda: choose(g, kind="top", maximize=[APPROVAL], minimize=[DEFAULT])),
        ('choose(grade, kind="pareto", by=APPROVAL, n=3)',
         lambda: choose(g, kind="pareto", by=APPROVAL, n=3)),
    ]:
        try:
            fn()
            print(f"  ok    {call}")
        except TypeError as e:
            print(f"  ERRO  {call}\n          -> {e}")
    print("""
  Tres chamadas, mesma funcao, e so uma combinacao de argumentos vale por kind.
  Na forma 1 e na 3 esses erros sao impossiveis de escrever: cada verbo/objeto
  so aceita o que usa.  Esse e o custo exato que a forma 2 pede que voce aceite
  em troca de um nome so no pacote.
""")


if __name__ == "__main__":
    main()
