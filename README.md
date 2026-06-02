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
| **Após Ponto de Corte Vigente** | 135,978 | 20.4% | -74.3% |
| **Pós-todos os HF (combinado)** | **135,978** | **20.4%** | **—** |

---

### 2. Curva de Otimização e Fronteira Eficiente
Avaliamos os quatro scores candidatos (`score_2` a `score_5`) confrontando sua taxa de aprovação contra a inadimplência projetada. O gráfico de Fronteira Eficiente abaixo exibe o desempenho de cada modelo, marcando com um **"X"** a performance da política histórica legada.

![Fronteira Eficiente](images/tradeoff_comparativo.png)

*O **Score 5** domina claramente a fronteira de eficiência. Ao mesmo nível de aprovação da política histórica (~20.4%), ele projeta uma inadimplência de aprovados drasticamente menor. Prosseguimos a calibração final exclusivamente com ele.*

---

### 3. Calibração e Adequação dos Cortes por Loja
Para manter a representatividade e o volume local, calibramos as notas de corte regionais do `score_5` para atingir cerca de **~23% de aprovação local** em cada praça (neutralizando o bias de risco geográfico e garantindo controle de crédito ótimo):

```python
# Notas de corte regionalizadas calibradas por loja/região
cutoffs_loja = {
    "Sudeste": 781,
    "Sul": 793,
    "Centro-Oeste": 770,
    "Nordeste": 751,
    "Norte": 760,
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
    .stress_aggravation(factor=1.2)
)
```

Estatísticas regionais resultantes da simulação da política final:

| Região / Loja | Nota de Corte | Vol. Propostas | Taxa de Aprovação Local |
| :--- | :---: | :---: | :---: |
| **Centro-Oeste** | 770 | 100,275 | 23.1% |
| **Nordeste** | 751 | 179,746 | 23.4% |
| **Norte** | 760 | 69,843 | 22.2% |
| **Sudeste** | 781 | 449,489 | 23.8% |
| **Sul** | 793 | 200,647 | 23.2% |

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
| **A** | `960` a `999` | 1.67% | 1.66% | 44,142 | 20,911 |
| **B** | `925` a `959` | 4.25% | 4.35% | 28,562 | 13,854 |
| **C** | `884` a `924` | 6.20% | 6.41% | 24,058 | 11,566 |
| **D** | `850` a `883` | 8.59% | 9.21% | 24,658 | 11,970 |
| **E** | `751` a `849` | 11.31% | 11.96% | 23,506 | 11,308 |

Abaixo, plotamos a estabilidade temporal das safras de performance observada dos aprovados sob a nova política, provando que a segregação se mantém robusta e livre de sobreposições ao longo de todo o histórico:

![Estabilidade dos Ratings por Safra](images/vintage_stability.png)

---

### 5. Dissecção dos Swaps e Quadrantes de Decisão
A transição de modelo altera a composição da carteira. Avaliamos a performance real observada para os clientes recusados na nova mas aceitos na antiga (Swap Out) vs a performance estressada para os novos aceitos (Swap In):

| Quadrante | Vol. Contratado Esperado | Taxa de Inadimplência | Origem dos Dados |
| :--- | :---: | :---: | :--- |
| **Keep In** | 49,750 | 1.84% | Observado (`actual_default`) |
| **Swap In** | 54,427 | 4.28% | Simulado Estressado (Angulado) |
| **Swap Out** | 64,799 | 12.41% | Observado Histórico Legado |
| **Keep Out** | 0 | N/A | Sem dados (Rejeitados por ambas) |

---

### 6. O Paradoxo do Volume de Contratos
Uma análise atenta da Tabela Delta revela um comportamento aparentemente paradoxal: **por que o volume contratado esperado cai (-9.0%) se a taxa de aprovação subiu levemente (+1.01%)?**

Este comportamento decorre do impacto da calibragem da **taxa de conversão (take-up rate)** na nova carteira:
1. **Adversão na Conversão**: Clientes com score de crédito alto e baixo risco (como a maioria dos aprovados no novo modelo) são muito disputados no mercado de crédito. Portanto, a taxa de fechamento de contrato (*take-up rate*) deles é menor, variando de **45% a 65%**.
2. **Seleção Inversa no Legado**: O modelo antigo (de baixo poder discriminatório) aprovava em massa clientes de score médio e baixo (Swap Out). Por possuírem poucas ofertas alternativas de financiamento, esses clientes convertem a taxas de **80% a 90%**, trazendo um grande volume de contratos, mas carregando uma inadimplência de **12.41%**.
3. **Decisão Estratégica**: Ao trocarmos o Swap Out (conversão alta, risco péssimo) pelo Swap In (conversão moderada, risco ótimo), aceitamos uma carteira contratada ligeiramente menor em volume absoluto, mas imensamente mais saudável, reduzindo a inadimplência total contratada de **7.84% para 3.12%**.

---

### 7. Resumo do Impacto de P&L Executivo (Tabela Delta)

A comparação consolidada entre as políticas prova o sucesso do novo motor de simulação:

| Métrica | Política Legada | Nova Política (V14) | Delta Absoluto | Delta Relativo |
| :--- | :---: | :---: | :---: | :---: |
| **Aprovação Global (% ToF)** | 20.44% | **21.45%** | **+1.01%** | **+4.9%** |
| **Inadimplência Contratada (P&L)** | 7.84% | **3.12%** | **-4.72%** | **-60.2%** |
| **Volume Contratado Esperado** | 114,449 | **104,177** | **-10,272** | **-9.0%** |

---

### 8. Crash Test: Resiliência dos Swap Ins (Estresse e Breakeven)
Como a performance dos Swap Ins é simulada, realizamos um teste de estresse severo aplicando multiplicadores de inadimplência sobre essa população. Variamos o fator de estresse de **1.0x** até **10.0x** no `TradeoffAnalyzer` para determinar a resiliência da carteira até o ponto de equilíbrio (*breakeven*) com a política histórica.

![Crash Test](images/crash_test.png)

*O **ponto de breakeven é atingido em 5.50x**. Isto significa que a inadimplência real do público Swap In teria de ser **5.50 vezes maior** do que a estimada pelo modelo para que a perda agregada da nova carteira subisse até os **7.84%** da política antiga. Esse amplo colchão de resiliência prova a alta segurança operacional da nova política.*
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
