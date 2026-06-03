# 📊 PyCrediTools
*Credit Risk Simulation, Policy Optimization, and Risk Clustering for Python*

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

---

**PyCrediTools** é uma biblioteca de ponta desenvolvida especificamente para equipes de Risco de Crédito. Ela fornece motores computacionais de alta performance para **Simulação de Funis de Decisão (Trade-off de Políticas)** e **Agrupamento Autónomo de Risco (Risk Clustering)**.

Esqueça o método de tentativa e erro. Com o PyCrediTools, você pode testar filtros de bureau, simular e otimizar cortes de score por loja/região e agrupar seu portfólio aprovado em Ratings contíguos de risco de forma matematicamente ótima e temporalmente estável.

---

## 🚀 Instalação

O pacote pode ser instalado diretamente do repositório GitHub:

```bash
pip install git+https://github.com/matheuspasche/pycreditools.git
```

---

## 💡 Core Features

- **Credit Policy Simulation**: Monte esteiras de decisão compostas por múltiplos estágios (Filtros duros de bureau, Regras de Corte de Score, Propensões Variáveis de Fechamento de Contrato).
- **Automated Risk Clustering**: Agrupe faixas de score em "Ratings de Risco" (A a E) sob restrições rigorosas de negócio (Monotonicidade de risco, Volume Mínimo por grupo e Estabilidade Temporal de Safras).
- **Monotonic Sorting Kernel**: (Novo!) Garante que ratings de score único sejam estritamente contíguos e ordenados, eliminando sobreposição ou cruzamento de notas (scores mais altos sempre recebendo classificações melhores ou iguais).
- **Longitudinal Stability**: O motor Ward calcula inibições de cruzamento de risco de forma contínua ao longo de múltiplos períodos (vintages/safras).

---

## 📖 Caso de Uso: Substituição de Política Legada (Showcase V14)

Esta seção demonstra o uso real da biblioteca para simular e aprovar a substituição de uma política legada (`legacy_score` com corte único p78) por um novo modelo campeão (`score_5`) regionalizado por loja.

O fluxo de execução e validação completo está disponível em [tutorial_masterclass_v14.ipynb](tutorial_masterclass_v14.ipynb).

### 1. Modelagem do Funil de Aprovação (Bureau + Regras de Entrada)
Aplicamos os novos escudos rígidos de entrada (hard filters) e incluímos o ponto de corte do score vigente para comparação direta do funil cumulativo sobre a base de propostas:

```python
import pandas as pd
from pycreditools import CreditPolicy, col

# Criamos a política base com escudos rígidos de entrada
policy_hf = (
    CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=["score_2", "score_3", "score_4", "score_5"],
        current_approval_col="approved",
        actual_default_col="actual_default",
        time_col="safra"
    )
    .filter("CPF Válido", col("cpf_valido") == True)
    .filter("Teto Negativação", col("vl_negativacao") <= 1500)
    .filter("Teto Atraso SCR", col("vl_vencido_scr") <= 3000)
    .filter("Teto Protestos", col("vl_protestos") <= 500)
)

# Adicionamos o ponto de corte vigente na política de comparação legada
policy_legacy_hf = (
    policy_hf
    .filter("Ponto de Corte Vigente", col("legacy_score") >= LEGACY_CUT)
)
```

O funil de aprovação cumulativo resultante (incluindo o corte vigente):

| Etapa | Volume | % Funil | Δ Etapa |
| :--- | :---: | :---: | :---: |
| **Top of Funnel** | 667,348 | 100.0% | — |
| **Após CPF Válido** | 666,017 | 99.8% | -0.2% |
| **Após Teto Negativação** | 604,823 | 90.6% | -9.2% |
| **Após Teto SCR** | 565,019 | 84.7% | -6.6% |
| **Após Teto Protestos** | 528,232 | 79.2% | -6.5% |
| **Após Ponto de Corte Vigente** | 136,711 | 20.5% | -74.1% |
| **Pós-todos os HF (combinado)** | **136,711** | **20.5%** | **—** |

---

### 2. Curva de Otimização e Fronteira Eficiente
Avaliamos os quatro scores candidatos (`score_2` a `score_5`) confrontando sua taxa de aprovação contra a inadimplência projetada. O gráfico de Fronteira Eficiente abaixo exibe o desempenho de cada modelo, marcando com um **"X"** a performance da política histórica legada.

![Fronteira Eficiente](images/tradeoff_comparativo.png)

*O **Score 5** domina claramente a fronteira de eficiência. Ao mesmo nível de aprovação da política histórica (~20.4%), ele projeta uma inadimplência de aprovados drasticamente menor. Prosseguimos a calibração final exclusivamente com ele.*

---

### 3. Calibração de Inadimplência Plana (Flat Default Rate) por Loja
Para otimizar a alocação de capital e limite de crédito por região geográfica, substituímos a estratégia de aprovação plana por uma política de **Inadimplência Plana (Flat Default Rate)**. Calibramos os cortes por região para atingir um alvo estável de **5.80% de PD Estressada** localmente, permitindo que a taxa de aprovação flutue de acordo com a qualidade do público local.

```python
# Notas de corte regionalizadas para atingir alvo de 5.80% PD estressada
cutoffs_loja = {
    "Centro-Oeste": 804,
    "Nordeste": 806,
    "Norte": 794,
    "Sudeste": 778,
    "Sul": 776,
}

def politica_loja(df_in):
    passa = pd.Series(False, index=df_in.index)
    for loja, cut in cutoffs_loja.items():
        passa.loc[(df_in["region"]==loja) & (df_in["score_5"]>=cut)] = True
    return passa

policy_final = (
    policy_hf
    .filter("Score Regionalizado Flat PD", politica_loja)
    .rate("Propensão de Contrato", base_rate=1.0, variable="take_up_rate")
)
```

Estatísticas regionais resultantes da simulação da política final:

| Região / Loja | Nota de Corte | Taxa de Aprovação Local | PD Estressada |
| :--- | :---: | :---: | :---: |
| **Centro-Oeste** | 804 | 18.37% | 5.54% |
| **Nordeste** | 806 | 16.94% | 5.67% |
| **Norte** | 794 | 17.67% | 5.79% |
| **Sudeste** | 778 | 22.32% | 5.86% |
| **Sul** | 776 | 23.33% | 5.83% |

---

### 4. Agrupamento de Risco (Clustering) nos Sobreviventes
Classificamos os clientes **aprovados sob a nova política (sobreviventes)** em DEV no modelo de agrupamento Ward, gerando Ratings contíguos. O motor garante a contiguidade e a ordenação de forma 100% consistente.

```python
# Treinado na população aprovada sobrevivente
df_train_dev = res_final[
    (res_final["new_approval"] > 0.0) &
    (res_final["sample"] == "DEV")
].copy()

group_res = find_risk_groups(
    data=df_train_dev,
    score_cols="score_5",
    default_col="actual_default",
    bins=30,
    max_groups=5,
    min_vol_ratio=0.01,
    method="ward",
    time_col="safra",
    max_crossings=1
)
```

A estrutura de Ratings resultante e sua validação temporal:

| Rating | Faixa de Score 5 | Inad. DEV | Inad. OOT | Vol. DEV (Aprovados) | Vol. OOT (Aprovados) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | `941` a `1000` | 1.66% | 1.69% | 42,205 | 19,642 |
| **B** | `890` a `940` | 4.05% | 4.31% | 27,381 | 12,860 |
| **C** | `870` a `889` | 5.77% | 5.73% | 14,181 | 6,667 |
| **D** | `822` a `869` | 8.01% | 8.11% | 36,879 | 17,719 |
| **E** | `776` a `821` | 10.22% | 10.74% | 18,421 | 9,005 |

Abaixo, plotamos a estabilidade temporal das safras de performance observada dos aprovados sob a nova política, provando que a segregação se mantém robusta e livre de sobreposições ao longo de todo o histórico:

![Estabilidade dos Ratings por Safra](images/vintage_stability.png)

---

### 5. Dissecção dos Swaps e Quadrantes de Decisão
A transição de modelo altera a composição da carteira. Avaliamos a performance real observada para os clientes recusados na nova mas aceitos na antiga (Swap Out) vs a performance estressada para os novos aceitos (Swap In):

| Quadrante | Vol. Contratado Esperado | Taxa de Inadimplência | Origem dos Dados |
| :--- | :---: | :---: | :--- |
| **Keep In** | 68,912 | 4.54% | Observado (`actual_default`) |
| **Swap In** | 23,159 | 10.11% | Simulado Estressado (Angulado) |
| **Swap Out** | 25,952 | 14.33% | Observado Histórico Legado |
| **Keep Out** | 0 | N/A | Sem dados (Rejeitados por ambas) |

> [!NOTE]
> Para a simulação dos **Swap Ins** (Magnum), utilizamos uma estratégia de **Agravamento Angulado** de risco para precificar de forma conservadora a seleção adversa. O estresse é aplicado de forma incremental por Rating de risco (do melhor para o pior), penalizando mais os ratings mais arriscados:
> - **Rating A**: 1.20x (+20% de estresse)
> - **Rating B**: 1.30x (+30% de estresse)
> - **Rating C**: 1.40x (+40% de estresse)
> - **Rating D**: 1.40x (+40% de estresse)
> - **Rating E**: 1.50x (+50% de estresse)

Aqui está um trecho do código onde definimos e adicionamos esse agravamento angulado por Rating de risco através da classe `CustomStress`:

```python
from pycreditools import CustomStress

# Agravamento Angulado Swap In (A=1.2× a E=1.50×)
def angulado(df_swap, pd_col):
    mapa = {"A": 1.20, "B": 1.30, "C": 1.40, "D": 1.40, "E": 1.50}
    fator = df_swap["Rating"].map(mapa).fillna(1.4)
    return (df_swap[pd_col] * fator).clip(0, 1)

policy_magnum = (
    policy_final
    .add_stress(CustomStress(angulado))
)
```

---

### 6. Equilíbrio de Volume e Risco no P&L
A nova política estruturada alcança um resultado extremamente equilibrado no P&L contratado esperado:
1. **Atração Saudável**: Com um motor discriminatório muito superior (Score 5), aprovamos clientes de menor risco. Ao calibrar a taxa de conversão (*take-up rate*) refletindo o apetite real dos clientes (de **41%** nos melhores scores até **95%** nos scores mais baixos), mitigamos a seleção adversa.
2. **Substituição Eficiente (Swaps)**: Trocamos com sucesso o público de alto risco do legado (**Swap Out** com inadimplência de **14.33%**) por um público qualificado (**Swap In** com inadimplência esperada mesmo com estresse angulado de **10.11%**).
3. **Efeito Win-Win**: O resultado final demonstra que conseguimos reduzir a inadimplência contratada global do portfólio de **7.18% para 5.94%** (uma redução de **-17.3%** no risco total contratado sob estresse angulado rigoroso) enquanto o volume de contratos esperado ficou em **92,071** (contra 94,675 legados, uma pequena redução planejada de **-2.8%** para maior segurança operacional e controle de risco).

---

### 7. Resumo do Impacto de P&L Executivo (Tabela Delta)

A comparação consolidada entre as políticas prova o sucesso do novo motor de simulação:

| Métrica | Política Legada | Nova Política (Flat PD) | Delta Absoluto | Delta Relativo |
| :--- | :---: | :---: | :---: | :---: |
| **Aprovação Global (% ToF)** | 20.47% | **20.50%** | **+0.02%** | **+0.1%** |
| **Inadimplência Contratada (P&L)** | 7.18% | **5.94%** | **-1.24%** | **-17.3%** |
| **Volume Contratado Esperado** | 94,675 | **92,071** | **-2,604** | **-2.8%** |

---

### 8. Crash Test: Resiliência dos Swap Ins (Estresse e Breakeven)
Como a performance dos Swap Ins é simulada, realizamos um teste de estresse severo aplicando multiplicadores de inadimplência sobre essa população. Variamos o fator de estresse de **1.0x** até **10.0x** no `TradeoffAnalyzer` para determinar a resiliência da carteira até o ponto de equilíbrio (*breakeven*) com a política histórica.

![Crash Test](images/crash_test.png)

*O **ponto de breakeven é atingido em 2.25x**. Isto significa que a inadimplência real do público Swap In teria de ser **2.25 vezes maior** do que a estimada pelo modelo (e já estressada angularmente) para que a perda agregada da nova carteira subisse até os **7.18%** da política antiga. Esse colchão de resiliência de 125% de sobrecarga prova a segurança operacional e resiliência extrema da nova política de Inadimplência Plana.*

---

## 🛠️ Contribuir e Desenvolver

Para executar a suíte de testes unitários e verificar o comportamento do motor:
```bash
git clone https://github.com/matheuspasche/pycreditools.git
cd pycreditools
pip install -e .
pytest tests/
```

## 📜 Licença
Distribuído sob a licença MIT. Desenvolvido para modelagem e engenharia de risco financeiro moderno.
