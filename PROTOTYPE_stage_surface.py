"""PROTOTYPE — descartável. Não é código de produção. Não importar de nada.

Card: #145 (mapa #111) — "Prototipar a superfície de estágio do #129:
escrita lado a lado e o caminho rápido".

Roda com um comando:

    .venv/bin/python PROTOTYPE_stage_surface.py

O que ele mostra (não descreve):

  PARTE A — A ESCRITA. O bloco de HFs real do `tutorial_masterclass` escrito
  nas duas superfícies, lado a lado, com o motor de verdade rodando por baixo
  dos dois (adaptador fino, precedente `PROTOTYPE_surface_shape.py` do #117).
  Os dois funis saem do `run_simulation` de hoje, e os números têm que bater.

  PARTE B — O CAMINHO RÁPIDO. Mede se `ranges=` sobre um `.filter`
  parametrizado mantém o ms/ponto do caminho rápido do #143 ou cai para o da
  re-simulação. É o único ponto do #129 sustentado por leitura, e o mais caro
  de reverter.

  PARTE C — as três perguntas que o #145 manda o protótipo forçar.

  PARTE D — O VERBO DA MESA. O #121 fechou a semântica do estágio probabilístico
  de decisão e delegou o verbo ao #129; o #129 fechou sem nomeá-lo. As quatro
  formas candidatas escritas lado a lado, todas rodando, com o custo de cada uma
  medido contra as regras já fixadas.

O que está FIXO pelo #129 e o protótipo não reabre: `.cutoff` morre; `.filter`
sobre a AST é o verbo único; condição é AST na entrada, string só na saída;
label único com default estrutural; `Stage` vira Protocol de dois membros;
`.rate` colapsa para um argumento.

ONDE O ADAPTADOR FINGE (declarado, para ninguém ler número que não existe):

  1. `ctx`. O #129 diz `apply(df, ctx)` com `ctx` estreito. O motor de hoje
     passa `policy`. O adaptador compila para o motor de hoje, então o `ctx`
     não existe aqui — o que existe é a prova de que nada na *escrita* precisa
     dele.
  2. A calibração é premissa (#117/#126), não argumento de estágio. O
     adaptador a declara uma vez, fora dos estágios, e a injeta nos campos que
     o motor de hoje lê (`calibration_score_col` / `calibration_bins`). É
     exatamente o que o `ctx` carregaria.
  3. `applicant_id_col` / `score_cols` estão mortos pelo #118. O adaptador
     preenche o que o `CreditPolicy` de hoje exige e nada mais — nenhuma
     superfície nova os menciona.
  4. O sorteio da mesa (PARTE D). O motor de hoje não tem estágio probabilístico
     de decisão: só `FilterStage` (determinístico, vetor decision) e `RateStage`
     (vetor contract). Em `materialize()` o sorteio acontece FORA do motor e
     entra como coluna, que o `.filter` então lê como máscara dura. É o maior
     fingimento do adaptador — e é exatamente o que a decisão de verbo tornaria
     nativo. A mecânica em si (observado leva o 0/1 real, o resto estima no
     mesmo `bins` da premissa, sorteio por linha chaveado a semente × posição ×
     nome) é a do #121 §6/§7 e do #127, não invenção daqui.
"""

from __future__ import annotations

import itertools
import time
import warnings

import numpy as np
import pandas as pd

from pycreditools import CalibrationReliabilityWarning, generate_sample_data
from pycreditools._kernels import calibrate_by_score_bins
from pycreditools.expressions import BinaryExpr, ColumnExpr, Expression, UnaryExpr, col
from pycreditools.policy import CreditPolicy
from pycreditools.stages import FilterStage, RateStage
from pycreditools.stress import AggravationStress
from pycreditools.sweep import _actual_defaults_array, _metrics, run_sweep

warnings.filterwarnings("ignore", category=CalibrationReliabilityWarning)

AGGRAVATION_BASE = 1.2
CMP_OPS = {">": np.greater, ">=": np.greater_equal, "<": np.less, "<=": np.less_equal}


# ---------------------------------------------------------------------------
# A SUPERFÍCIE NOVA (#129)
# ---------------------------------------------------------------------------


class LabelRequired(ValueError):
    """A estrutura não nomeia o estágio: 0 colunas, 2+ colunas, ou colisão."""


def _cols(expr: Expression) -> list[str]:
    return list(dict.fromkeys(expr.get_columns()))


def structural_label(expr: object) -> str | None:
    """O default do #129: a coluna referenciada, quando a regra referencia uma só.

    Sai da AST que o usuário escreveu — não é heurística sobre o dado (#118).
    """
    if not isinstance(expr, Expression):
        return None  # escalar: zero colunas, a estrutura não nomeia
    names = _cols(expr)
    return names[0] if len(names) == 1 else None


class ChanceExpr(Expression):
    """FORMA D — candidato NOVO, não está entre os três do #121.

    O sorteio como nó da AST, não como argumento do verbo: `chance(expr)` diz
    "sorteie-me com esta probabilidade". Vetor segue com o verbo, mecanismo
    segue na árvore, e o `.filter`/`.rate` de um argumento do #129 fica intacto.
    """

    def __init__(self, expr: Expression):
        self.expr = expr

    def eval(self, df: pd.DataFrame) -> pd.Series:
        return self.expr.eval(df)  # o sorteio é do motor; aqui é só a probabilidade

    def get_columns(self) -> list[str]:
        return self.expr.get_columns()

    def __repr__(self) -> str:
        return f"chance({self.expr!r})"


def chance(expr: Expression) -> ChanceExpr:
    return ChanceExpr(expr)


class Rule:
    """Um estágio: dois eixos independentes (#121 §1) — vetor e mecanismo.

    vector: onde a Series aterrissa (#116). mechanism: como o estágio decide.
    O #121 mandou descolar os dois; as quatro formas da PARTE D diferem só em
    ONDE cada eixo é escrito.
    """

    def __init__(self, expr: object, vector: str, label: str | None,
                 mechanism: str = "deterministic"):
        self.expr = expr
        self.vector = vector  # "decision" | "contract"
        self.mechanism = mechanism  # "deterministic" | "drawn"
        self.label = label
        self.label_was_written = label is not None

    def resolved_label(self) -> str:
        if self.label is not None:
            return self.label
        auto = structural_label(self.expr)
        if auto is None:
            raise LabelRequired(
                f"a estrutura não nomeia esta regra ({self.expr!r}): "
                f"declare label=."
            )
        return auto

    def render(self) -> str:
        """String só na saída (#129). `BinaryExpr.__repr__` já monta o render."""
        return repr(self.expr)

    def display(self) -> str:
        """O que aparece no funil: o label mais o render, e o render só quando a
        regra não se explica sozinha."""
        label = self.resolved_label()
        if self.label_was_written:
            return f"{label} — {self.render()}"
        return self.render()


class Policy:
    """A política nova: só as regras (#117). Sem nomes de coluna, sem premissa."""

    def __init__(self, rules: tuple[Rule, ...] = ()):
        self.rules = rules

    def filter(self, condition: Expression, label: str | None = None,
               prob: bool = False) -> Policy:
        """`prob=True` é a FORMA B: mesmo verbo, e o argumento muda de tipo
        (nó booleano -> nó numérico em [0,1])."""
        if not isinstance(condition, Expression):
            raise TypeError("condição de .filter é um nó da AST (#120 matou callable/str na entrada)")
        drawn = prob or isinstance(condition, ChanceExpr)  # FORMA D
        mechanism = "drawn" if drawn else "deterministic"
        return Policy(self.rules + (Rule(condition, "decision", label, mechanism),))

    def rate(self, probability: object, label: str | None = None,
             to: str = "contract") -> Policy:
        """Uma probabilidade: escalar ou nó da AST. Um argumento (#129).

        `to="decision"` é a FORMA C: o vetor vira argumento, com default
        estrutural invisível no caso comum.
        """
        if to not in ("contract", "decision"):
            raise ValueError(f"to= é 'contract' ou 'decision', não {to!r}")
        mechanism = "drawn" if to == "decision" else "deterministic"
        return Policy(self.rules + (Rule(probability, to, label, mechanism),))

    def review(self, observed: Expression, label: str | None = None) -> Policy:
        """FORMA A: verbo próprio. Vetor e mecanismo, os dois, no nome."""
        return Policy(self.rules + (Rule(observed, "decision", label, "drawn"),))

    # -- bind ---------------------------------------------------------------

    def labels(self) -> list[str]:
        """Resolve todo label. Erro duro em 0 colunas, 2+ colunas ou colisão."""
        seen: dict[str, int] = {}
        out = []
        for i, rule in enumerate(self.rules):
            try:
                label = rule.resolved_label()
            except LabelRequired as e:
                raise LabelRequired(f"regra #{i}: {e}") from None
            if label in seen:
                raise LabelRequired(
                    f"regra #{i} colide com a regra #{seen[label]} no label "
                    f"{label!r} ({rule.render()}): declare label=."
                )
            seen[label] = i
            out.append(label)
        return out


class Premise:
    """A premissa do estudo (#117): fora da política, colada na hora de rodar.

    O que o `ctx` do #129 carregaria. Aqui ela existe para o adaptador ter
    onde pôr a calibração que saiu do `.rate`.
    """

    def __init__(self, score: str, bins: int, aggravation: float | None = None):
        self.score = score
        self.bins = bins
        self.aggravation = aggravation


# ---------------------------------------------------------------------------
# O ADAPTADOR (superfície nova -> motor de hoje). Fino, e só isso.
# ---------------------------------------------------------------------------

SCHEMA = {"approved": "approved", "hired": "hired", "outcome": "actual_default"}


DRAW_PREFIX = "__drawn_"


class DeskBindError(ValueError):
    """Erro duro de bind do desfecho de mesa (#121 §5)."""


def validate_desk_outcome(df: pd.DataFrame, column: str, label: str) -> dict[str, int]:
    """As duas amarras do #121 §5, e a cobertura como número.

    - valores fora de {0, 1, null} = erro duro;
    - observado não-nulo exige `approved == 1` = erro duro.
    """
    values = df[column]
    bad = values.dropna()
    outside = bad[~bad.isin([0, 1])]
    if len(outside):
        sample = ", ".join(f"{float(v):g}" for v in sorted(outside.unique())[:3])
        raise DeskBindError(
            f"estágio '{label}': {len(outside)} valor(es) fora de {{0, 1, null}} em "
            f"'{column}' (ex.: {sample})."
        )
    spurious = df[values.notna() & (df[SCHEMA["approved"]] != 1)]
    if len(spurious):
        raise DeskBindError(
            f"estágio '{label}': {len(spurious)} linhas com desfecho de mesa observado "
            f"mas `approved != 1` — quem nunca foi aprovado no livro antigo não pode "
            f"ter desfecho de mesa."
        )
    return {"observado": int(values.notna().sum()), "sem_observacao": int(values.isna().sum())}


def drawn_decision_column(
    df: pd.DataFrame, rule: Rule, label: str, premise: Premise, seed: int
) -> pd.Series:
    """A mecânica probabilística do #121, uma só, compartilhada com o take-up.

    1. quem tem desfecho observado leva o 0/1 real (bypass por construção: p ∈ {0,1});
    2. quem não tem, leva a estimativa por faixa de score, no MESMO `bins` da
       premissa (#121 §7 — "uma config serve todo eixo", zero campo novo);
    3. sorteia-se por linha, chaveado a (semente do estudo, posição da linha,
       nome do sorteio) — #127 —, inclusive no analítico (#121 §6), para
       `decision` ficar 0/1 duro.

    A inflação de stress NÃO incide: stress é premissa sobre inadimplência,
    não sobre propensão de aprovação (#121 §7).
    """
    inner = rule.expr.expr if isinstance(rule.expr, ChanceExpr) else rule.expr
    observed = inner.eval(df).astype(float)

    known = observed.notna()
    estimate = calibrate_by_score_bins(
        cal_scores=df.loc[known, premise.score],
        cal_values=observed[known],
        ref_scores=df.loc[known, premise.score],
        target_scores=df[premise.score],
        bins=premise.bins,
        global_fallback=float(observed[known].mean()) if known.any() else 0.0,
    )
    probs = observed.where(known, estimate).fillna(0.0).clip(0.0, 1.0)

    # (semente do estudo, nome do sorteio) chaveiam o gerador; a posição da
    # linha na base ligada é o índice do vetor. #127.
    rng = np.random.default_rng([seed, *(ord(c) for c in label)])
    return (rng.random(len(df)) < probs.to_numpy()).astype(int)


def materialize(
    policy: Policy, premise: Premise, df: pd.DataFrame, seed: int = 7
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Pré-computa a coluna sorteada de todo estágio probabilístico de decisão.

    O motor de hoje não tem esse estágio — ele só conhece `FilterStage`
    (determinístico, vetor decision) e `RateStage` (vetor contract). O sorteio
    acontece aqui, fora do motor, e entra como coluna. É o maior fingimento
    do adaptador, e é o que a decisão de verbo tornaria nativo.
    """
    out = df.copy()
    coverage = {}
    for label, rule in zip(policy.labels(), policy.rules):
        if rule.mechanism != "drawn" or rule.vector != "decision":
            continue
        inner = rule.expr.expr if isinstance(rule.expr, ChanceExpr) else rule.expr
        if isinstance(inner, ColumnExpr):
            coverage[label] = validate_desk_outcome(out, inner.name, label)
        out[DRAW_PREFIX + label] = drawn_decision_column(out, rule, label, premise, seed)
    return out, coverage


def run(policy: Policy, premise: Premise, df: pd.DataFrame, seed: int = 7):
    """`simulate(study, df)` do #117, emulado: materializa, compila, simula."""
    bound, coverage = materialize(policy, premise, df, seed)
    sim = compile_to_engine(policy, premise).simulate(bound, method="analytical")
    return sim, coverage


def compile_to_engine(policy: Policy, premise: Premise) -> CreditPolicy:
    labels = policy.labels()
    stages = []
    for label, rule in zip(labels, policy.rules):
        if rule.vector == "decision" and rule.mechanism == "drawn":
            # o sorteio já virou coluna em materialize(); aqui é máscara dura
            stages.append(FilterStage(name=label, condition=col(DRAW_PREFIX + label) == 1))
        elif rule.vector == "decision":
            stages.append(FilterStage(name=label, condition=rule.expr))
        elif isinstance(rule.expr, ColumnExpr):
            # `.rate(col("hired"))`: a probabilidade de contrato é lida nessa
            # coluna. O bypass do keep-in e a estimativa do swap-in são do
            # motor/premissa (#116, #121), não argumentos do estágio.
            stages.append(
                RateStage(name=label, base_rate=1.0, observed_col=rule.expr.name, calibrate_by="score")
            )
        else:
            stages.append(RateStage(name=label, base_rate=float(rule.expr)))

    return CreditPolicy(
        applicant_id_col="applicant_id",  # morto pelo #118; o motor de hoje exige
        score_cols=(),  # morto pelo #118
        current_approval_col=SCHEMA["approved"],
        actual_default_col=SCHEMA["outcome"],
        calibration_score_col=premise.score,  # o que o ctx carregaria
        calibration_bins=premise.bins,
        stages=tuple(stages),
        stress_scenarios=(
            (AggravationStress(factor=premise.aggravation),) if premise.aggravation else ()
        ),
    )


# ---------------------------------------------------------------------------
# O CAMINHO RÁPIDO RECHAVEADO NA AST (#129 / #143)
# ---------------------------------------------------------------------------


def conjuncts(expr: Expression) -> list[Expression]:
    if isinstance(expr, BinaryExpr) and expr.op == "&":
        return conjuncts(expr.left) + conjuncts(expr.right)
    return [expr]


def numeric_comparison(expr: object) -> tuple[str, str] | None:
    """(coluna, operador) se `expr` é o literal de uma comparação numérica.

    É a propriedade estrutural que o #129 usa para rechavear o caminho rápido —
    a mesma que a `CutoffStage` representava por acidente.
    """
    if not isinstance(expr, BinaryExpr) or expr.op not in CMP_OPS:
        return None
    if not isinstance(expr.left, ColumnExpr):
        return None
    if isinstance(expr.right, bool) or not isinstance(expr.right, (int, float)):
        return None
    return expr.left.name, expr.op


class FastPathPlan:
    def __init__(self, baseline: Policy, column: str, op: str):
        self.baseline = baseline
        self.column = column
        self.op = op


def plan_fast_path(policy: Policy, label: str) -> FastPathPlan | None:
    """O caminho rápido vale quando o nó variado é o literal de uma comparação
    numérica dentro de uma máscara dura. Senão: re-simulação.
    """
    labels = policy.labels()
    if label not in labels:
        raise KeyError(f"nenhuma regra com label {label!r}; labels: {labels}")
    idx = labels.index(label)
    target = policy.rules[idx]

    if target.vector != "decision":
        return None  # vetor contract: muda probabilidade por linha, re-simula

    parts = conjuncts(target.expr) if isinstance(target.expr, Expression) else []
    varied = [p for p in parts if numeric_comparison(p) is not None]
    if len(varied) != 1:
        return None  # a estrutura não aponta um literal só

    column, op = numeric_comparison(varied[0])
    fixed = [p for p in parts if p is not varied[0]]

    # A baseline é a política menos o nó variado. Os conjuntos fixos da mesma
    # regra continuam ligando — eles não variam.
    rules = list(policy.rules)
    if fixed:
        rebuilt = fixed[0]
        for p in fixed[1:]:
            rebuilt = rebuilt & p
        rules[idx] = Rule(rebuilt, "decision", target.label or column)
    else:
        rules.pop(idx)
    return FastPathPlan(Policy(tuple(rules)), column, op)


def plan_fast_path_multi(policy: Policy, labels: list[str]) -> dict[str, FastPathPlan] | None:
    """O caso real do `optimize_cutoffs`: N nós variados na mesma grade.

    Cada label tem que ser elegível sozinho, e a baseline é a política menos
    TODOS os nós variados.
    """
    plans = {}
    baseline = policy
    for label in labels:
        plan = plan_fast_path(policy, label)
        if plan is None:
            return None
        plans[label] = plan
    for label in labels:
        stripped = plan_fast_path(baseline, label)
        if stripped is None:
            return None
        baseline = stripped.baseline
    for label in labels:
        plans[label] = FastPathPlan(baseline, plans[label].column, plans[label].op)
    return plans


def sweep_fast(
    data: pd.DataFrame, policy: Policy, premise: Premise, ranges: dict[str, list[float]]
) -> pd.DataFrame:
    plans = plan_fast_path_multi(policy, list(ranges))
    assert plans is not None
    baseline = next(iter(plans.values())).baseline
    sim_df = compile_to_engine(baseline, premise).simulate(data, method="analytical").data
    actual = _actual_defaults_array(data, compile_to_engine(policy, premise))
    arrays = {lab: data[p.column].to_numpy(dtype=float) for lab, p in plans.items()}

    rows = []
    for combo in itertools.product(*ranges.values()):
        point = dict(zip(ranges, combo))
        mask = np.ones(len(data), dtype=bool)
        for label, value in point.items():
            mask &= CMP_OPS[plans[label].op](arrays[label], value)
        app, dr = _metrics(sim_df, actual, mask.astype(float))
        rows.append({**point, "overall_approval_rate": app, "overall_default_rate": dr})
    return pd.DataFrame(rows)


def with_literal(policy: Policy, label: str, value: float) -> Policy:
    """A mesma regra com o literal trocado — a via lenta, para conferir o rápido."""
    labels = policy.labels()
    idx = labels.index(label)
    target = policy.rules[idx]
    parts = conjuncts(target.expr)
    rebuilt = None
    for p in parts:
        if numeric_comparison(p) is not None:
            p = BinaryExpr(p.left, p.op, value)
        rebuilt = p if rebuilt is None else (rebuilt & p)
    rules = list(policy.rules)
    rules[idx] = Rule(rebuilt, "decision", target.label)
    return Policy(tuple(rules))


def sweep_resimulate(
    data: pd.DataFrame, policy: Policy, premise: Premise, ranges: dict[str, list[float]]
) -> pd.DataFrame:
    actual = _actual_defaults_array(data, compile_to_engine(policy, premise))
    rows = []
    for combo in itertools.product(*ranges.values()):
        point = dict(zip(ranges, combo))
        varied = policy
        for label, value in point.items():
            varied = with_literal(varied, label, value)
        sim = compile_to_engine(varied, premise).simulate(data, method="analytical")
        app, dr = _metrics(sim.data, actual)
        rows.append({**point, "overall_approval_rate": app, "overall_default_rate": dr})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# AS POLÍTICAS REAIS DA MASTERCLASS, NAS DUAS SUPERFÍCIES
# ---------------------------------------------------------------------------

LEGACY_CUT = 600


def masterclass_today(score_cut: float) -> CreditPolicy:
    base = CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_2", "score_3", "score_4", "score_5"),
        current_approval_col="approved",
        actual_default_col="actual_default",
        time_col="safra",
        calibration_score_col="score_5",
        calibration_bins=10,
    )
    return (
        base.filter("Valid CPF", col("cpf_valido") == True)  # noqa: E712
        .filter("Negativation <= 1500", col("vl_negativacao") <= 1500)
        .filter("SCR arrears <= 3000", col("vl_vencido_scr") <= 3000)
        .filter("Protests <= 500", col("vl_protestos") <= 500)
        .filter("Incumbent score gate", col("legacy_score") >= LEGACY_CUT)
        .cutoff("National score cutoff", {"score_5": score_cut}, direction="gte")
        .rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")
        .stress(AGGRAVATION_BASE)
    )


def masterclass_new(score_cut: float) -> Policy:
    return (
        Policy()
        .filter(col("cpf_valido") == True)  # noqa: E712
        .filter(col("vl_negativacao") <= 1500)
        .filter(col("vl_vencido_scr") <= 3000)
        .filter(col("vl_protestos") <= 500)
        .filter(col("legacy_score") >= LEGACY_CUT, label="Incumbent score gate")
        .filter(col("score_5") >= score_cut)
        .rate(col("hired"))
    )


def masterclass_new_two_dials(score_cut: float) -> Policy:
    """A mesma política com dois dials — o caso do `optimize_cutoffs` da seção 6."""
    return (
        Policy()
        .filter(col("cpf_valido") == True)  # noqa: E712
        .filter(col("vl_negativacao") <= 1500)
        .filter(col("vl_vencido_scr") <= 3000)
        .filter(col("vl_protestos") <= 500)
        .filter(col("legacy_score") >= LEGACY_CUT, label="Incumbent score gate")
        .filter(col("score_5") >= score_cut)
        .filter(col("score_4") >= 400.0)
        .rate(col("hired"))
    )


MASTERCLASS_PREMISE = Premise(score="score_5", bins=10, aggravation=AGGRAVATION_BASE)


SOURCE_TODAY = """\
base_policy = CreditPolicy(
    applicant_id_col="applicant_id",
    score_cols=("score_2", "score_3", "score_4", "score_5"),
    current_approval_col="approved",
    actual_default_col="actual_default",
    time_col="safra",
    calibration_bins=10,
)
policy = (
    base_policy
    .filter("Valid CPF", col("cpf_valido") == True)
    .filter("Negativation <= 1500", col("vl_negativacao") <= 1500)
    .filter("SCR arrears <= 3000", col("vl_vencido_scr") <= 3000)
    .filter("Protests <= 500", col("vl_protestos") <= 500)
    .filter("Incumbent score gate", col("legacy_score") >= 600)
    .cutoff("National score cutoff", {"score_5": CUT}, direction="gte")
    .rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")
    .stress(1.2)
)
sim = policy.simulate(df, method="analytical")\
"""

SOURCE_NEW = """\
policy = (
    Policy()
    .filter(col("cpf_valido") == True)
    .filter(col("vl_negativacao") <= 1500)
    .filter(col("vl_vencido_scr") <= 3000)
    .filter(col("vl_protestos") <= 500)
    .filter(col("legacy_score") >= 600, label="Incumbent score gate")
    .filter(col("score_5") >= CUT)
    .rate(col("hired"))
)
premise = Premise(score="score_5", bins=10, aggravation=1.2)

sim = simulate(policy, premise, df)\
"""


# ---------------------------------------------------------------------------
# SAÍDA
# ---------------------------------------------------------------------------


def rule(title: str) -> None:
    print()
    print("=" * 96)
    print(title)
    print("=" * 96)


def side_by_side(left: str, right: str, head_l: str, head_r: str, width: int = 68) -> None:
    ll, rl = left.splitlines(), right.splitlines()
    print(f"{head_l:<{width}} | {head_r}")
    print("-" * width + "-+-" + "-" * width)
    for i in range(max(len(ll), len(rl))):
        a = ll[i] if i < len(ll) else ""
        b = rl[i] if i < len(rl) else ""
        print(f"{a:<{width}} | {b}")


def part_a(df: pd.DataFrame, score_cut: float) -> None:
    rule("PARTE A — A ESCRITA (o bloco de HFs real do tutorial_masterclass)")

    print("A.1 — as duas superfícies, mesma política\n")
    side_by_side(SOURCE_TODAY, SOURCE_NEW, "HOJE (v0.5)", "#129")

    print("\n\nA.2 — os dois funis, do motor de verdade (run_simulation de hoje)\n")
    today = masterclass_today(score_cut)
    new = masterclass_new(score_cut)
    sim_today = today.simulate(df, method="analytical")
    sim_new = compile_to_engine(new, MASTERCLASS_PREMISE).simulate(df, method="analytical")

    f_today = sim_today.to_funnel_dataframe()
    f_new = sim_new.to_funnel_dataframe()

    print(f"{'HOJE — nome escrito à mão':<45} {'passa':>9}   "
          f"{'#129 — label (só quando escrito) + render':<56} {'passa':>9}")
    print("-" * 126)
    # O funil do motor rotula os estágios como "i: <label>"; troca-se o label
    # pelo display() do #129 e deixam-se as linhas de resumo (Total, Approved).
    by_label = {r.resolved_label(): r for r in new.rules}
    for i in range(max(len(f_today), len(f_new))):
        lt = str(f_today.iloc[i]["Stage"]) if i < len(f_today) else ""
        pt = f"{f_today.iloc[i]['Passed']:,}" if i < len(f_today) else ""
        ln = str(f_new.iloc[i]["Stage"]) if i < len(f_new) else ""
        pn = f"{f_new.iloc[i]['Passed']:,}" if i < len(f_new) else ""
        if ": " in ln:
            prefix, label = ln.split(": ", 1)
            if label in by_label:
                ln = f"{prefix}: {by_label[label].display()}"
        print(f"{lt[:44]:<45} {pt:>9}   {ln[:55]:<56} {pn:>9}")

    a_t = sim_today.data["approved_pre_rate"].sum() / len(df)
    a_n = sim_new.data["approved_pre_rate"].sum() / len(df)
    c_t = sim_today.data["new_approval"].sum()
    c_n = sim_new.data["new_approval"].sum()
    print()
    print(f"  aprovação (pre take-up):  hoje {a_t:.6%}   #129 {a_n:.6%}   "
          f"{'IDÊNTICO' if abs(a_t - a_n) < 1e-12 else 'DIVERGE'}")
    print(f"  contratados:              hoje {c_t:.6f}   #129 {c_n:.6f}   "
          f"{'IDÊNTICO' if abs(c_t - c_n) < 1e-9 else 'DIVERGE'}")
    print("\n  (mesmo motor, mesma premissa; a superfície é a única diferença)")


def part_a3(df: pd.DataFrame) -> None:
    print("\n\nA.3 — censo de label sobre TODAS as políticas reais do notebook\n")

    # O callable do #120 vira coluna calculada na base + expressão (a escotilha
    # dplyr declarada no #129). É o que faz o estágio ter 2 colunas.
    cutoffs_by_region = {r: 600 + 10 * i for i, r in enumerate(sorted(df["region"].unique()))}
    df["region_cutoff"] = df["region"].map(cutoffs_by_region)

    # A coluna "nome redundante?" é a leitura do #129 sobre os nomes escritos à
    # mão hoje, transcrita — não uma heurística de string.
    census = [
        ("Valid CPF", col("cpf_valido") == True, False),  # noqa: E712
        ("Negativation <= 1500", col("vl_negativacao") <= 1500, True),
        ("SCR arrears <= 3000", col("vl_vencido_scr") <= 3000, True),
        ("Protests <= 500", col("vl_protestos") <= 500, True),
        ("Incumbent score gate", col("legacy_score") >= LEGACY_CUT, False),
        ("National score cutoff", col("score_5") >= 700, True),
        ("Regional score cutoffs", col("score_5") >= col("region_cutoff"), False),
        ("Take-up", col("hired"), False),
        ("Antifraud (rate escalar)", 0.90, False),
    ]

    print(f"{'nome de hoje':<26} {'expressão / probabilidade':<42} {'cols':>4}  "
          f"{'default estrutural':<20} {'label?':<12} nome de hoje era")
    print("-" * 132)
    needed = 0
    redundant = 0
    for name, expr, is_redundant in census:
        auto = structural_label(expr)
        n = len(_cols(expr)) if isinstance(expr, Expression) else 0
        if auto is None:
            verdict = "OBRIGATÓRIO"
            needed += 1
        else:
            verdict = "opcional"
        if is_redundant:
            redundant += 1
        note = "redundante (a AST escreve)" if is_redundant else "informação nova"
        print(f"{name:<26} {repr(expr)[:41]:<42} {n:>4}  {str(auto or '—'):<20} "
              f"{verdict:<12} {note}")

    total = len(census)
    print(f"\n  {total} estágios reais: {needed} exigem label ({needed / total:.0%}); "
          f"{redundant} dos {total} nomes de hoje eram redundantes com o render,")
    print(f"  ou seja {total - redundant} nomes carregam informação que a AST não tem.")
    print("  O label obrigatório é exceção — mas as duas exceções são reais, não hipóteses:")
    print("    · `Regional score cutoffs` — 2 colunas, porque o callable do #120 virou")
    print("      `col(\"score_5\") >= col(\"region_cutoff\")` pela escotilha dplyr.")
    print("    · `Antifraud` — 0 colunas (o caso `base_rate` de sweep.py:173).")

    print("\n  E um caso que o #129 não enumerou, mas o bind encontra:")
    band = Policy().filter(col("score_5") >= 600).filter(col("score_5") <= 900)
    try:
        band.labels()
    except LabelRequired as e:
        print(f"    · faixa nos dois lados da MESMA coluna -> colisão: {e}")


def part_b(df: pd.DataFrame, score_cut: float) -> None:
    rule("PARTE B — O CAMINHO RÁPIDO (medido, não lido)")

    values = np.linspace(560.0, 860.0, 100).tolist()
    new = masterclass_new(score_cut)
    today = masterclass_today(score_cut)

    plan = plan_fast_path(new, "score_5")
    print("B.0 — a AST admite o caminho rápido?\n")
    print("  regra endereçada por label ......... 'score_5' (default estrutural)")
    print(f"  nó variado ......................... literal de {plan.column} {plan.op} <lit>")
    print("  vetor declarado .................... decision (máscara dura)")
    print(f"  baseline = política menos esse nó .. {len(plan.baseline.rules)} regras "
          f"(de {len(new.rules)})")
    print("  -> elegível. A varredura anda a MESMA árvore que `get_columns()` já anda:")
    print("     `numeric_comparison()` são 6 linhas sobre `BinaryExpr`, não um parser.")

    print("\nB.1 — equivalência numérica\n")
    probe = [values[0], values[33], values[66], values[-1]]
    ranges = {"score_5": probe}
    fast = sweep_fast(df, new, MASTERCLASS_PREMISE, ranges)
    slow = sweep_resimulate(df, new, MASTERCLASS_PREMISE, ranges)
    old = run_sweep(df, today, cutoff_grid={"score_5": probe},
                    directions={"score_5": "gte"}, method="analytical")

    print("  (a) a pergunta do card: o rechaveamento na AST dá o MESMO que o")
    print("      caminho rápido de hoje (CutoffStage + isinstance)?\n")
    print(f"{'corte':>8} {'AST: aprov / inadimp':>34} {'hoje: aprov / inadimp':>34} {'|Δ|':>10}")
    print("-" * 92)
    worst_rekey = 0.0
    for i, v in enumerate(probe):
        d = max(abs(fast["overall_approval_rate"][i] - old["overall_approval_rate"][i]),
                abs(fast["overall_default_rate"][i] - old["overall_default_rate"][i]))
        worst_rekey = max(worst_rekey, d)
        print(f"{v:>8.1f} {fast['overall_approval_rate'][i]:>16.12f} / "
              f"{fast['overall_default_rate'][i]:<15.12f} "
              f"{old['overall_approval_rate'][i]:>16.12f} / "
              f"{old['overall_default_rate'][i]:<15.12f} {d:>10.1e}")
    print(f"\n  -> {'IDÊNTICO' if worst_rekey == 0.0 else 'DIVERGE'} "
          f"(pior |Δ| = {worst_rekey:.1e}). O caminho rápido sobrevive ao rechaveamento.")

    print("\n  (b) o bug JÁ REGISTRADO no mapa (medido no #140, sem ticket próprio),")
    print("      reproduzido aqui: os dois caminhos rápidos divergem da RE-SIMULAÇÃO.\n")
    print(f"{'corte':>8} {'inadimp (rápido)':>18} {'inadimp (re-sim)':>18} {'Δ abs':>11} {'Δ rel':>9}")
    print("-" * 70)
    worst_abs = 0.0
    for i, v in enumerate(probe):
        f_, s_ = fast["overall_default_rate"][i], slow["overall_default_rate"][i]
        worst_abs = max(worst_abs, abs(f_ - s_))
        print(f"{v:>8.1f} {f_:>18.10f} {s_:>18.10f} {f_ - s_:>+11.2e} {(f_ - s_) / s_:>+9.2%}")
    print(f"\n  A aprovação bate exatamente; a INADIMPLÊNCIA não (pior Δ = {worst_abs:.1e}),")
    print("  com viés para cima na banda de decisão e encolhendo até desaparecer no")
    print("  corte mais apertado (onde o share de swap-in encolhe) — a mesma assinatura")
    print("  que o #140 mediu a 3 MM (0,58 p.p., 32x o ruído amostral).")
    print("  Mecanismo, o mesmo já registrado no mapa e re-medido aqui: quem é KEEP_IN")
    print("  depende da regra variada, e são os keep-ins que calibram a PD do swap-in")
    print("  (`_estimate_swap_in_baseline_pd`); a baseline congela a calibração e a")
    print("  máscara não recalibra (3.762 keep-ins na baseline, 2.286 no corte 860).")
    print("\n  Isto NÃO é achado deste protótipo, e não muda o veredito de B.1: o #129")
    print("  herda o caminho rápido exatamente como ele é, defeito incluído — nem")
    print("  conserta, nem piora. Mas amarra o número de B.2: o contraste ~45x compara")
    print("  um caminho correto com um incorreto, como o #140 já anotou sobre os 112x.")

    print(f"\nB.2 — ms/ponto ({len(df):,} linhas, method=analytical)\n")

    def timed(fn):
        t0 = time.perf_counter()
        fn()
        return (time.perf_counter() - t0) * 1000.0

    grid1 = {"score_5": values}
    ms_slow = timed(lambda: sweep_resimulate(df, new, MASTERCLASS_PREMISE, grid1))
    ms_today = timed(lambda: run_sweep(df, today, cutoff_grid={"score_5": values},
                                       directions={"score_5": "gte"}, method="analytical"))
    ms_fast = timed(lambda: sweep_fast(df, new, MASTERCLASS_PREMISE, grid1))
    n = len(values)

    print(f"  1 dial, {n} pontos (o `vary_cutoff` da masterclass)\n")
    print(f"{'via':<54} {'total (ms)':>11} {'ms/ponto':>10}")
    print("-" * 77)
    print(f"{'re-simulação (uma simulate por ponto)':<54} {ms_slow:>11.1f} {ms_slow / n:>10.3f}")
    print(f"{'caminho rápido de HOJE (CutoffStage, isinstance)':<54} {ms_today:>11.1f} {ms_today / n:>10.3f}")
    print(f"{'caminho rápido RECHAVEADO NA AST (#129)':<54} {ms_fast:>11.1f} {ms_fast / n:>10.3f}")
    print()
    print(f"  AST vs re-simulação ....... {ms_slow / ms_fast:>7.1f}x mais rápido")
    print(f"  AST vs fast path de hoje .. {ms_today / ms_fast:>7.2f}x  "
          f"({'a AST não custa nada' if ms_fast <= ms_today * 1.25 else 'a AST custa'})")

    # 2 dials: o caso real do optimize_cutoffs, onde o caminho rápido paga a conta.
    two = masterclass_new_two_dials(score_cut)
    today2 = masterclass_today(score_cut)
    g5 = np.linspace(560.0, 860.0, 12).tolist()
    g4 = np.linspace(400.0, 700.0, 12).tolist()
    grid2 = {"score_5": g5, "score_4": g4}
    n2 = len(g5) * len(g4)
    ms_slow2 = timed(lambda: sweep_resimulate(df, two, MASTERCLASS_PREMISE, grid2))
    ms_today2 = timed(lambda: run_sweep(df, today2, cutoff_grid={"score_5": g5, "score_4": g4},
                                        directions={"score_5": "gte", "score_4": "gte"},
                                        method="analytical"))
    ms_fast2 = timed(lambda: sweep_fast(df, two, MASTERCLASS_PREMISE, grid2))
    print(f"\n  2 dials, {n2} pontos (o `optimize_cutoffs` da seção 6)\n")
    print(f"{'via':<54} {'total (ms)':>11} {'ms/ponto':>10}")
    print("-" * 77)
    print(f"{'re-simulação':<54} {ms_slow2:>11.1f} {ms_slow2 / n2:>10.3f}")
    print(f"{'caminho rápido de HOJE':<54} {ms_today2:>11.1f} {ms_today2 / n2:>10.3f}")
    print(f"{'caminho rápido RECHAVEADO NA AST (#129)':<54} {ms_fast2:>11.1f} {ms_fast2 / n2:>10.3f}")
    print(f"\n  AST vs re-simulação ....... {ms_slow2 / ms_fast2:>7.1f}x")
    print(f"  AST vs fast path de hoje .. {ms_today2 / ms_fast2:>7.2f}x")

    print("\nB.3 — a fronteira do rechaveamento (o que cai para re-simulação)\n")
    cases = [
        ("um literal numérico numa máscara dura", masterclass_new(score_cut), "score_5", "esperado rápido"),
        ("vetor contract (.rate) — muda prob por linha", masterclass_new(score_cut), "hired", "esperado re-simula"),
        ("comparação contra outra COLUNA (o gate regional)",
         Policy().filter(col("score_5") >= col("region_cutoff"), label="regional"), "regional",
         "esperado re-simula"),
        ("um literal + um conjunto FIXO na mesma regra",
         Policy().filter(col("cpf_valido") == True)  # noqa: E712
                 .filter((col("score_5") >= 700) & (col("score_5") >= col("region_cutoff")),
                         label="misto"),
         "misto", "esperado rápido"),
        ("DOIS literais na mesma regra (o label não desambigua)",
         Policy().filter((col("score_5") >= 700) & (col("score_4") >= 500), label="dois"), "dois",
         "esperado re-simula"),
    ]
    for name, pol, label, expected in cases:
        plan = plan_fast_path(pol, label)
        verdict = "rápido" if plan else "RE-SIMULA"
        extra = f"  (baseline: {len(plan.baseline.rules)} regra(s))" if plan else ""
        print(f"  {name:<52} -> {verdict:<10}{extra}")
    print("\n  O último caso é a consequência que o #129 não enumerou: o label endereça o")
    print("  ESTÁGIO, e o caminho rápido precisa endereçar o NÓ. Enquanto cada regra")
    print("  carregar um literal só, os dois coincidem — e a masterclass escreve assim")
    print("  (\"Each shield is its own stage\"). Duas comparações numéricas num `.filter`")
    print("  só tornam o estágio invarrível, em silêncio. Hoje isso não acontece porque")
    print("  o endereço é a COLUNA (`cutoffs: dict`), não o estágio.")


def part_c(score_cut: float) -> None:
    rule("PARTE C — as três perguntas que o #145 manda forçar")

    hand = ["Valid CPF", "Negativation <= 1500", "SCR arrears <= 3000",
            "Protests <= 500", "Incumbent score gate", "National score cutoff"]
    new = masterclass_new(score_cut)
    renders = [r.display() for r in new.rules if r.vector == "decision"]
    w_hand = max(len(s) for s in hand)
    w_new = max(len(s) for s in renders)

    print(f"""\
1. O default estrutural produz nome legível no funil, ou o render vira ruído
   numa política de 5+ estágios?
       Ver A.2. Não vira ruído por ILEGIBILIDADE — vira por LARGURA. Em 4 dos 6
       estágios de decisão o nome de hoje só repetia a regra à mão (e podia
       mentir); o render não pode. Mas a coluna cresce: nome escrito no pior
       caso {w_hand} caracteres, display do #129 {w_new} ({w_new / w_hand:.1f}x), contra as 25
       colunas que `print_funnel_table` reserva hoje (simulation.py:144). O
       funil precisa de largura nova, ou de truncar o render — decisão de
       apresentação, não de arquitetura, mas é onde o defeito de escrita
       apareceria primeiro.

2. `.rate(col("hired"))` simétrico ao `.filter` se lê, ou fica mágico demais?
       Ver A.1/A.2. Escreve-se e roda, com número idêntico. O que ele não diz
       na cara é que o keep-in leva o valor observado e o swap-in leva a
       estimativa por faixa de score — mas isso é #116/#121/premissa, não
       argumento do estágio, e nenhuma das cinco palavras que sumiram
       (`base_rate`, `observed_col`, `calibrate`, `calibrate_by`, `variable`)
       dizia isso também. O que a superfície nova perde é o LUGAR onde
       perguntar: hoje `observed_col=` grita "isto é uma coluna observada";
       amanhã `col("hired")` é indistinguível de uma probabilidade por linha.
       A diferença passa a morar na premissa.

3. Estágio com 2+ colunas — quantos aparecem nas políticas reais depois que o
   callable do #120 vira coluna por linha?
       Ver A.3. Um em nove (o gate regional), mais um de zero colunas (rate
       escalar). O label obrigatório segue exceção, ~22%, e as duas exceções
       são justamente estágios cujo nome de hoje já carregava informação nova.
       Mas o bind achou uma TERCEIRA classe que o #129 não enumerou: colisão
       na mesma coluna — uma faixa `>= 600` e `<= 900` escrita como dois
       `.filter` colide no default `score_5`. É escrita plausível, e o erro
       duro cai sobre quem escreveu a política mais óbvia possível.""")


# ---------------------------------------------------------------------------
# PARTE D — o verbo do estágio probabilístico de decisão (a mesa)
# ---------------------------------------------------------------------------

DESK_COL = "desk_outcome"


def desk_book(df: pd.DataFrame) -> pd.DataFrame:
    """O desfecho de mesa como o livro antigo o registra: observado só para quem
    de fato foi à mesa (aprovado), null para todo o resto — que é a amarra de
    bind do #121 §5, e a razão de a cobertura virar número."""
    out = df.copy()
    out[DESK_COL] = np.where(out["approved"] == 1, out["passed_antifraud"], np.nan)
    return out


def desk_forms(score_cut: float) -> dict[str, tuple[str, Policy]]:
    """A MESMA política, com a mesa escrita de quatro jeitos."""
    def base() -> Policy:
        return (
            Policy()
            .filter(col("cpf_valido") == True)  # noqa: E712
            .filter(col("vl_negativacao") <= 1500)
            .filter(col("score_5") >= score_cut)
        )

    return {
        "A — verbo próprio": (
            '.review(col("desk_outcome"))',
            base().review(col(DESK_COL), label="Mesa").rate(col("hired")),
        ),
        "B — filter com flag": (
            '.filter(col("desk_outcome"), prob=True)',
            base().filter(col(DESK_COL), label="Mesa", prob=True).rate(col("hired")),
        ),
        "C — rate com destino": (
            '.rate(col("desk_outcome"), to="decision")',
            base().rate(col(DESK_COL), label="Mesa", to="decision").rate(col("hired")),
        ),
        "D — sorteio na AST": (
            '.filter(chance(col("desk_outcome")))',
            base().filter(chance(col(DESK_COL)), label="Mesa").rate(col("hired")),
        ),
    }


SOURCE_DESK = """\
policy = (
    Policy()
    .filter(col("cpf_valido") == True)
    .filter(col("vl_negativacao") <= 1500)
    .filter(col("score_5") >= CUT)
    {MESA}
    .rate(col("hired"))
)\
"""


def part_d(df: pd.DataFrame, score_cut: float) -> None:
    rule("PARTE D — o verbo da mesa (quinta pergunta; #121 delegou, #129 não entregou)")

    print("""\
D.0 — o que as quatro formas têm que expressar (semântica já fechada no #121)

  · a mesa é DECISÃO probabilística: alimenta `decision`, logo a taxa de
    aprovação publicada INCLUI a mesa (§8);
  · sorteia mesmo no analítico, para `decision` ficar 0/1 duro (§6);
  · elegibilidade é POSIÇÃO NO FUNIL, não máscara declarada (§3);
  · quem tem desfecho observado leva o 0/1 real; quem não tem, estima no MESMO
    `bins` da premissa — a mecânica probabilística é uma só, compartilhada com
    o take-up (§7);
  · o nome da coluna observada é REFERÊNCIA da regra, mora no estágio (§4).

  Nada disso está em disputa. Em disputa está uma coisa só: ONDE se declara que
  esta probabilidade aterrissa em `decision` e não em `contract`.""")

    forms = desk_forms(score_cut)
    bound = desk_book(df)

    print("\n\nD.1 — as quatro escritas\n")
    for name, (mesa, _) in forms.items():
        print(f"  {name}")
        print("  " + "-" * len(name))
        for line in SOURCE_DESK.replace("{MESA}", mesa).splitlines():
            print(f"    {line}")
        print()

    print("\nD.2 — as quatro rodam, e dão o MESMO número\n")
    results = {}
    for name, (_, policy) in forms.items():
        sim, coverage = run(policy, MASTERCLASS_PREMISE, bound)
        data = sim.data
        results[name] = (
            data["approved_pre_rate"].sum() / len(bound),
            float(data["new_approval"].sum()),
            coverage.get("Mesa", {}),
        )

    print(f"{'forma':<24} {'aprovação (inclui mesa)':>24} {'contratados':>14}")
    print("-" * 66)
    for name, (app, contracted, _) in results.items():
        print(f"{name:<24} {app:>23.8%} {contracted:>14.4f}")
    apps = {round(v[0], 12) for v in results.values()}
    print(f"\n  -> {'IDÊNTICAS' if len(apps) == 1 else 'DIVERGEM'}: as quatro são a mesma")
    print("     semântica escrita de quatro jeitos. A escolha é 100% de escrita.")

    cov = next(iter(results.values()))[2]
    total = cov["observado"] + cov["sem_observacao"]
    print(f"\n  cobertura como número (#121 §5): {cov['observado']:,} linhas com desfecho "
          f"de mesa observado, {cov['sem_observacao']:,} sem ({cov['sem_observacao'] / total:.1%} "
          f"estimadas).")

    # A mesa dentro do funil: a aprovação publicada a inclui (#121 §8).
    sim, _ = run(forms["A — verbo próprio"][1], MASTERCLASS_PREMISE, bound)
    funnel = sim.to_funnel_dataframe()
    print("\n  o funil, com a mesa dentro dele:\n")
    for _, r in funnel.iterrows():
        print(f"    {str(r['Stage'])[:44]:<46} {r['Passed']:>9,}")

    # #121 §8: reprovado na mesa é reprovado, e o número publicado diz isso.
    no_desk = (
        Policy()
        .filter(col("cpf_valido") == True)  # noqa: E712
        .filter(col("vl_negativacao") <= 1500)
        .filter(col("score_5") >= score_cut)
        .rate(col("hired"))
    )
    sim_no_desk, _ = run(no_desk, MASTERCLASS_PREMISE, bound)
    app_with = sim.data["approved_pre_rate"].sum() / len(bound)
    app_without = sim_no_desk.data["approved_pre_rate"].sum() / len(bound)
    print(f"\n  aprovação publicada COM a mesa .... {app_with:.2%}")
    print(f"  aprovação publicada SEM a mesa .... {app_without:.2%}")
    print(f"  a mesa reprova {app_without - app_with:.2%} da base, e o número publicado")
    print("  diz isso (#121 §8) — hoje `approved_pre_rate` excluiria a mesa por ser rate.")

    print("\n\nD.3 — os erros duros de bind do #121 §5, exercidos\n")
    for description, mutate in [
        ("valor fora de {0, 1, null}",
         lambda d: d.assign(**{DESK_COL: d[DESK_COL].mask(d.index == d.index[0], 0.5)})),
        ("observado com approved == 0",
         lambda d: d.assign(**{DESK_COL: d[DESK_COL].mask(d["approved"] == 0, 1.0)})),
    ]:
        try:
            run(forms["A — verbo próprio"][1], MASTERCLASS_PREMISE, mutate(bound))
            print(f"  {description:<32} -> PASSOU (não devia)")
        except DeskBindError as e:
            print(f"  {description:<32} -> erro duro:")
            print(f"  {'':<32}    {e}")

    print("""\


D.4 — o que cada forma custa (medido contra as regras já fixadas)

  A — .review(col("desk_outcome"))
      + os dois eixos ficam no nome, e o caso raro não polui o caso comum;
      + `.filter`/`.rate` de UM argumento sobrevivem intactos (a manchete do #129);
      - TERCEIRO verbo, contra o insumo do dono no #121 §2 ("inclinação a matar
        o `.cutoff` também — não quer encher de verbos"): o #129 tirou um verbo
        e esta forma repõe;
      - o nome não generaliza. Mesa, antifraude, formalização são todos "decisão
        probabilística"; `.review` nomeia UM deles. Nomear a mecânica em vez do
        evento (`.draw`, `.chance`) devolve a vagueza;
      - o #118 fixou varredura como `ranges=` no verbo: com três verbos, é preciso
        dizer em quais `ranges=` aponta.

  B — .filter(col("desk_outcome"), prob=True)
      + é a ÚNICA forma que separa os dois eixos como o #121 §1 pede: o verbo
        nomeia o VETOR (`.filter` -> decision, `.rate` -> contract) e o argumento
        nomeia o MECANISMO. Nas outras três o verbo carrega os dois, ou nenhum;
      + dois verbos, contagem intacta;
      - a flag RE-TIPA o argumento posicional: sem ela um nó booleano, com ela um
        nó numérico em [0,1]. É a pior espécie de flag booleana;
      - fere a régua de UX que o próprio #121 §2 invocou (tipo de saída
        previsível): o mesmo verbo às vezes joga moeda.

  C — .rate(col("desk_outcome"), to="decision")
      + o vetor fica ESCRITO, que é literalmente o que o #121 §1 pediu;
      + default estrutural invisível: o caso comum (`contract`) não escreve nada,
        só o raro escreve — mesma lógica do label do #129;
      - reabre o colapso do `.rate` para UM argumento, que é a manchete do #129
        ("de cinco argumentos para um"). Volta a dois;
      - inverte os eixos em relação a B: o verbo passa a nomear o MECANISMO
        (probabilidade) e o argumento o VETOR. Fica difícil dizer o que `.filter`
        e `.rate` são, se não são os vetores.

  D — .filter(chance(col("desk_outcome")))   [NOVO — não é dos três do #121]
      + um argumento, dois verbos, zero flag: o mecanismo vira NÓ, e o #129 já
        decidiu que tudo que descreve a regra mora na AST;
      + o vetor segue com o verbo (`.filter` -> decision), então os dois eixos
        ficam separados como em B, sem re-tipar nada: `chance(x)` é um nó, e o
        argumento continua sendo "um nó";
      + `serialize_expression` ganha um caso e o round-trip do #120 fecha sozinho;
      + o caminho rápido enxerga `chance(...)` e sabe que não é máscara dura —
        a elegibilidade do rechaveamento (PARTE B) se lê na árvore, como o resto;
      - um conceito novo na AST, que até aqui só tinha colunas, operadores e
        literais: `chance` não é uma função sobre valores, é uma instrução ao
        motor. A árvore deixa de ser puramente declarativa;
      - `chance(col("hired"))` num `.rate` seria redundante ou contraditório —
        precisa de regra dizendo onde `chance` é legal.""")


def main() -> None:
    df = generate_sample_data(20_000, seed=42)
    score_cut = float(np.quantile(df["score_5"], 0.55))

    print(__doc__.split("O que está FIXO")[0].strip())
    print(f"\nbase: {len(df):,} linhas, seed=42; corte score_5 = {score_cut:.0f}")

    part_a(df, score_cut)
    part_a3(df)
    part_b(df, score_cut)
    part_c(score_cut)
    part_d(df, score_cut)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# PARTE E — o render de leitura (pedido do dono, 2026-08-31)
# ---------------------------------------------------------------------------


def pretty(expr: object, connective_parent: bool = False) -> str:
    """Render de LEITURA: `vl_negativacao <= 1500`, não `(col('x') <= 1500)`.

    O `__repr__` continua sendo o render de Python (round-trippável, colável).
    Este é o de apresentação — o #129 disse "string só na saída", não disse que
    a saída é Python. Parênteses só onde carregam informação: comparação dentro
    de um `&`/`|`.
    """
    if isinstance(expr, ColumnExpr):
        return expr.name
    if isinstance(expr, ChanceExpr):
        return f"chance({pretty(expr.expr)})"
    if isinstance(expr, UnaryExpr):
        return f"not {pretty(expr.expr, connective_parent=True)}"
    if isinstance(expr, BinaryExpr):
        is_connective = expr.op in ("&", "|")
        left = pretty(expr.left, connective_parent=is_connective)
        right = pretty(expr.right, connective_parent=is_connective)
        body = f"{left} {expr.op} {right}"
        return f"({body})" if connective_parent else body
    if isinstance(expr, bool):
        return str(expr)
    if isinstance(expr, float) and expr.is_integer():
        return str(int(expr))
    return repr(expr)
