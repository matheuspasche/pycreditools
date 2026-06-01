<div align="center">
  <h1>📊 PyCrediTools</h1>
  <p><i>Credit Risk Simulation and Policy Optimization for Python</i></p>
  
  [![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
  [![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
  [![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()
</div>

---

**PyCrediTools** é uma biblioteca de ponta projetada para equipes de Risco de Crédito. Traduzida e evoluída a partir do pacote fundacional em R, ela fornece motores computacionais para **Simulação de Funis de Crédito (Trade-off de Políticas)** e **Agrupamento Autónomo de Risco (Risk Clustering)**.

Esqueça as aproximações por tentativas e erros. Com o PyCrediTools, você pode testar cortes de score contra taxas de aprovação, encontrar a política que maximiza a receita mantendo a inadimplência dentro do apetite ao risco, e recriar dinamicamente as faixas de Rating de forma matematicamente ótima.

---

## 🚀 Instalação

Atualmente em fase final de testes, o pacote pode ser instalado diretamente do GitHub:

```bash
pip install git+https://github.com/matheuspasche/pycreditools.git
```

*(Em breve estará disponível no PyPI via `pip install pycreditools`)*

---

## 💡 Core Features

- **Credit Policy Simulation**: Monte estágios rigorosos (Filtros duros, Regras de Corte de Score, Probabilidades Variáveis) e estresse a carteira sob diferentes condições económicas (agravamentos macro, declínios monotónicos).
- **Automated Risk Clustering**: Agrupe milhares de combinações de scores numa arquitetura compacta de "Ratings de Risco". O algoritmo respeita limitações de negócio rigorosas (Tolerância a inversão de safra, Exigência Mínima de Volume).
- **Distance Linkage Engine**: (Novo!) Uma evolução do algoritmo Ward tradicional que prioriza a simetria orgânica e o distanciamento da probabilidade de inadimplência em vez da densidade volumétrica da carteira.

---

## 📖 Quickstart (Exemplo de Uso)

O uso típico envolve duas fases: Simular a política para gerar a "População Aprovada", e depois agrupar essa população em Ratings estruturais.

### 1. Simulação do Funil
```python
import pandas as pd
from pycreditools.policy import CreditPolicy
from pycreditools.stages import CutoffStage
from pycreditools.simulation import simulate_policy

# Carregar Dados (O seu histórico de propostas e performance real)
df = pd.read_csv("minha_base.csv") 

# Criar a Política
policy = (
    CreditPolicy(score_cols=["meu_score_novo"], actual_default_col="inadimplencia")
    .add_stage(CutoffStage("Aprovacao_Score", cutoffs={"meu_score_novo": 650}))
)

# Simular aprovação
df_simulado = simulate_policy(df, policy)
df_aprovados = df_simulado[df_simulado["_approved"]]
```

### 2. Agrupamento Ótimo de Risco (Clustering)
Vamos pedir ao motor que encontre o número **ótimo** de curvas de risco (até um máximo de 5 grupos), garantindo que **nunca se cruzam no tempo** (`max_crossings=0`).

```python
from pycreditools.grouping import find_risk_groups

clustering = find_risk_groups(
    df_aprovados,
    score_cols="meu_score_novo",
    default_col="inadimplencia",
    time_col="safra_mes",       # Para matriz de temporalidade
    bins=20,                    # Granularidade da pesquisa
    max_groups=5,               # Teto Máximo
    method="distance",          # Heurística pura de Distância
    max_crossings=0,            # Tolerância Zero a inversão de curvas
    min_vol_ratio=0.05          # Cada Rating deve ter >5% do volume
)

# Aplicar o modelo (nova coluna "risk_rating" gerada)
df_final = clustering.predict(df_aprovados)

print(f"O algoritmo agrupou os scores em {clustering.n_groups} Ratings de Risco Perfeitos.")
print(df_final.groupby("risk_rating")["inadimplencia"].mean())
```

---

## 🧠 Algoritmos de Agrupamento

Ao invocar o `find_risk_groups`, o motor aceita dois métodos principais (`method="ward"` ou `method="distance"`):

### Ward Method Tradicional (`method="ward"`)
Pesquisa aglomerativa que funde micro-faixas usando o critério de variância espacial (Ward). Este método tende a produzir faixas de risco **igualmente densas** em termos de volume (Ratings com 20% do volume cada, mesmo que o risco não esteja bem distribuído).

### Distance Linkage Autónomo (`method="distance"`)
Um critério de custo inovador que ignora o volume na hora de medir as pontes matemáticas, penalizando unicamente o `(Risco 1 - Risco 2)^2`. A consequência brilhante disto é que os Ratings finais ficam distribuídos pelas faixas de probabilidade com **distâncias perfeitamente equidistantes**, independentemente se um Rating ficar com 30% da carteira e outro com 8%. Ideal para mapas visuais limpos e estabilidade de risco orgânica.

---

## 🛠️ Contribuir e Desenvolver

Para correr a suite de testes e submeter pull requests:
```bash
git clone https://github.com/matheuspasche/pycreditools.git
cd pycreditools
pip install -e .[dev]
pytest tests/
```

## 📜 Licença
Distribuído sob licença MIT. Desenvolvido para a engenharia financeira moderna.
