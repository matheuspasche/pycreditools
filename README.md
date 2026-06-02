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
Aplicamos os novos escudos rígidos de entrada (hard filters) de forma cumulativa sobre a base de propostas:

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
```

O funil de aprovação cumulativo resultante:

| Etapa | Volume | % Funil | Δ Etapa |
| :--- | :---: | :---: | :---: |
| **Top of Funnel** | 667,348 | 100.0% | — |
| **Após CPF Válido** | 666,017 | 99.8% | -0.2% |
| **Após Teto Negativação** | 604,823 | 90.6% | -9.2% |
| **Após Teto SCR** | 565,019 | 84.7% | -6.6% |
| **Após Teto Protestos (Pós-HF)** | **528,232** | **79.2%** | **-6.5%** |

---

### 2. Calibração e Adequação dos Cortes por Loja
Para manter a representatividade e o volume local, calibramos as notas de corte regionais para atingir cerca de **~23% de aprovação local** em cada praça (neutralizando o bias de risco geográfico):

```python
# Notas de corte regionalizadas calibradas
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

### 3. Agrupamento de Risco (Clustering) apenas nos Sobreviventes
Classificamos os clientes **aprovados sob a nova política (sobreviventes)** em DEV no modelo de agrupamento Ward, gerando Ratings contíguos:

```python
from pycreditools import find_risk_groups

# Filtramos estritamente quem sobreviveu à nova política
df_train_dev = res_final[
    (res_final["new_approval"] > 0.0) &
    (res_final["sample"] == "DEV")
].copy()

# Encontramos 5 Ratings de Risco contíguos e estáveis (max_crossings=1)
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

A estrutura final de Ratings resultante (100% contígua e monotonicamente consistente):

| Rating | Faixa de Score 5 | Inad. DEV | Inad. OOT | Vol. DEV (Aprovados) | Vol. OOT (Aprovados) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | `960` a `999` | 1.67% | 1.66% | 44,142 | 20,911 |
| **B** | `925` a `959` | 4.25% | 4.35% | 28,562 | 13,854 |
| **C** | `884` a `924` | 6.20% | 6.41% | 24,058 | 11,566 |
| **D** | `850` a `883` | 8.59% | 9.21% | 24,658 | 11,970 |
| **E** | `751` a `849` | 11.31% | 11.96% | 23,506 | 11,308 |

---

### 4. Dissecção dos Swaps e Deltas de Negócio
Aprovando a nova política, alteramos o fluxo de aprovação anterior. A carteira é segmentada em quadrantes de contratação:

- **Keep In**: Aprovados pela antiga e pela nova política.
- **Swap In**: Reprovados pela antiga, mas aprovados pela nova.
- **Swap Out**: Aprovados pela antiga, mas reprovados pela nova.

A inadimplência observada do Swap Out (histórico contratado) versus a simulada do Swap In (estressada sob agravamento angulado de até 2.1x):

| Quadrante | Vol. Contratado Esperado | Taxa de Inadimplência | Origem dos Dados |
| :--- | :---: | :---: | :--- |
| **Keep In** | 49,750 | 1.84% | Observado (`actual_default`) |
| **Swap In** | 54,427 | 4.28% | Simulado Estressado (Angulado) |
| **Swap Out** | 64,799 | 12.41% | Observado Histórico Legado |
| **Keep Out** | 0 | N/A | Sem dados (Rejeitados por ambas) |

---

### 5. Resumo do Impacto de P&L Executivo (Tabela Delta)

A comparação consolidada entre as políticas prova o sucesso do novo motor:

| Métrica | Política Legada | Nova Política (V14) | Delta Absoluto | Delta Relativo |
| :--- | :---: | :---: | :---: | :---: |
| **Aprovação Global (% ToF)** | 20.44% | **21.45%** | **+1.01%** | **+4.9%** |
| **Inadimplência Contratada (P&L)** | 7.84% | **3.12%** | **-4.72%** | **-60.2%** |
| **Volume Contratado Esperado** | 114,449 | **104,177** | **-10,272** | **-9.0%** |

*A nova política aprova **+1.01%** a mais de clientes da base geral, enquanto reduz a inadimplência do P&L contratado em **-60.2%** (de 7.84% para 3.12%), limpando a carteira através da exclusão do Swap Out (inadimplência histórica de 12.41%) e inclusão do Swap In qualificado (inadimplência estressada de 4.28%).*

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
