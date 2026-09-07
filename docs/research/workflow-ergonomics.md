# Ergonomia de workflow — levantamento de referências

> **Insumo de decisão, não decisão.** Este documento levanta fatos, formas e preços.
> Nenhum veredito "adotar / adaptar / descartar" é tomado aqui — esses são de #116, #117,
> #122, #123, #125 e #128. Se você achar uma recomendação neste texto, é um defeito:
> reporte no #113.

Resolve a **Lente A** do #113: a ergonomia que o dono declarou querer — *definir o setup do
estudo uma vez, portar esse objeto como premissa, e trocar barato só o que varia*. O
exemplo declarado: com base e amostragem fixas, comparar GLM contra XGB em poucas linhas, e
escalar para vários modelos, cenários e grids sem reescrever o setup.

Duas referências, lidas a fundo:

- **tidymodels** (R) — a origem do estilo que o dono nomeou. Lido pelo *passo a passo*, não
  pelo maquinário (S3, tidy-eval) que não porta.
- **scikit-learn** (Python) — o análogo Python nativo direto. Lido pelo que ele faz
  diferente e pelo preço disso.

A **Lente B** — as 20 perguntas de forma da §16 do `architecture-critique.md` contra deep
modules, functional core/imperative shell, polars/ibis e CART — está fora deste documento
por fatiamento acordado (2026-07-25); vive em ticket próprio.

## Como ler

Cada fork abaixo tem duas formas. Para cada uma: **fato** (o que a referência faz, medido),
**porta para Python?**, e **preço** (o que custa, em manutenção e em correção). As duas
colunas existem porque a decisão é de outro card; quem decidir chega com as duas na mão.

Onde este documento cruza com o `architecture-critique.md`, a seção é citada (§N).

---

## Fork 1 — o objeto-premissa carrega a base, ou só descreve como usá-la?

### Forma A — a premissa carrega a base

**Referência:** tidymodels, `rsample`.

```r
folds <- vfold_cv(train_df, v = 5)
# folds é um tibble de objetos rsplit; cada rsplit guarda o dataframe
# e os índices de linha de análise/avaliação daquele fold.
```

**Fato.** O objeto de reamostragem é inseparável da base: ele *é* uma partição de linhas
concretas. Consequências observáveis: dois modelos avaliados sobre o mesmo `folds` veem
exatamente as mesmas linhas nas mesmas dobras — a comparação é pareada por construção, sem
o chamador ter que garantir isso. E o objeto serve de identidade do estudo: "estes
resultados são sobre estas dobras".

**Porta para Python?** Sim, sem maquinário de R. É uma dataclass segurando um dataframe (ou
uma referência a ele) mais índices.

**Preço.**
- O objeto não é reutilizável com outra base. Rodar a mesma premissa sobre outro dataframe
  exige reconstruí-la, e nada no tipo obriga a reconstruir igual.
- Serialização fica cara ou impossível: gravar a premissa é gravar dados. Cruza direto com
  §3 e §10 (round-trip) — hoje o pacote já tem um não-serializável por construção
  (`CustomStress.to_dict()` devolve `str(fn)`).
- Memória: N premissas vivas = N referências à base. Em tidymodels os `rsplit` compartilham
  o dataframe original, então o custo é de índices, não de cópias — um pacote Python teria
  que ser igualmente disciplinado, e `CreditPolicy._replace` hoje faz `copy.deepcopy`
  (§3.1).

### Forma B — a premissa só descreve como usar a base

**Referência:** scikit-learn, os splitters de `model_selection`.

```python
cv = KFold(n_splits=5, shuffle=True, random_state=0)
# cv não sabe nada de X. A base entra no verbo:
cv.split(X)                       # gera pares de índices
cross_val_score(est, X, y, cv=cv) # ou aqui
```

**Fato.** O splitter é uma descrição pura: quantas dobras, embaralha ou não, semente. É
reutilizável entre bases por construção, é trivialmente serializável (`get_params()` devolve
um dicionário de escalares), e é comparável por igualdade de configuração.

**Porta para Python?** É Python.

**Preço.**
- O pareamento deixa de ser garantido pelo tipo e passa a depender da semente mais da
  ordem das linhas da base. Duas chamadas com o mesmo `cv` sobre dataframes ordenados
  diferentes produzem dobras diferentes. Ninguém avisa.
- O "estudo" deixa de ter objeto: o que identifica um resultado passa a ser a tupla
  `(base, cv, scoring)` espalhada pelos argumentos do verbo. Cruza com #125 (identidade de
  experimento) e com §12.4 (alvo sem tipo).
- O chamador carrega a base em toda chamada. É o que hoje o pacote já faz —
  `policy.simulate(df)`, `optimize_cutoffs(base, config)`.

### Achado: nenhuma das duas referências é pura

**Isto foi o achado central da leitura conjunta.** O tidymodels **não** é Forma A pura — ele
tem as duas camadas ao mesmo tempo, em objetos diferentes:

| Objeto | Amarrado à base? | Como |
|---|---|---|
| `rsample::vfold_cv(df)` | **sim** | guarda linhas |
| `recipes::recipe(formula, data = df)` | **não** | usa `df` só como *template* de nomes e tipos; a documentação diz explicitamente que os dados servem para catalogar nomes e tipos |
| `recipes::prep(rec, training = df)` | **sim** | agora estima quantis, médias, níveis de fator — vira objeto ajustado |
| `parsnip` model spec | **não** | só declara motor e hiperparâmetro |

Ou seja: no tidymodels a **descrição portável** (recipe não-preparada, model spec) e o
**bind a uma base** (folds, recipe preparada) são tipos distintos, e o segundo é produzido
aplicando o primeiro sobre dados.

sklearn faz o mesmo split com **um tipo em dois estados** em vez de dois tipos: o
`Pipeline` é o mesmo objeto antes e depois do `fit()`, e o que distingue é a convenção de
atributos com sublinhado no fim (`n_features_in_`, `components_`), verificada por
`check_is_fitted()`.

**Consequência para o pycreditools, sem veredito:** a pergunta §1.1 do
`architecture-critique.md` — `rating_recipe` é dois tipos, um tipo com dois estados, ou um
tipo parametrizado? — tem **as duas respostas praticadas por referências reais**, e as duas
funcionam. tidymodels: dois tipos. sklearn: um tipo, dois estados, distinguidos por
convenção de nome. A escolha é de #117 e #126.

### Onde o pycreditools está hoje

Nem A nem B, porque não existe objeto-premissa: as premissas do estudo
(`stress_scenarios`, `calibration_score_col`, `calibration_bins`, `calibration_base`) moram
dentro de `CreditPolicy` (§2), junto com o schema da base e com as regras. A base entra no
verbo (`simulate(df)`), que é a mecânica da Forma B, mas sem o objeto descritivo que a Forma
B pressupõe — o papel dele está diluído nos 13 campos de `CreditPolicy` (§1).

---

## Fork 2 — comparar N candidatos é verbo de primeira classe ou laço de quem chama?

### Forma A — comparar é verbo

**Referência:** tidymodels, `workflowsets`.

```r
wfs <- workflow_set(
  preproc = list(base = rec),
  models  = list(glm = glm_spec, xgb = xgb_spec)
)
res <- workflow_map(wfs, "tune_grid", resamples = folds, grid = 20)
rank_results(res, rank_metric = "roc_auc")
autoplot(res)
```

**Fato.** `workflow_set` faz o produto cartesiano de pré-processadores × modelos e devolve
uma tabela onde cada linha é um candidato, com identidade derivada
(`wflow_id = "<preproc>_<model>"`). `workflow_map` aplica *o mesmo verbo* a todas as linhas
com *as mesmas premissas*, e o resultado é uma tabela empilhada, ordenável e plotável sem
trabalho adicional. As "poucas linhas" do exemplo GLM↔XGB vêm **daqui** — não do
encadeamento do workflow.

**Porta para Python?** Sim como forma de API. Nenhuma parte disso depende de tidy-eval: é um
container de candidatos nomeados mais um `map`. Mas **não existe precedente no análogo
Python direto** — ver Forma B.

**Preço.**
- Identidade deixa de ser opcional. Um container de N candidatos precisa de chave estável
  para cada um, e ela tem que sobreviver à tabela de resultados. Hoje `compare_policies`
  recebe por posição e escreve colunas literais `"Old"`/`"New"`, e a masterclass usa
  `"New 1"/"New 2"/"New 3"` como string solta (§13, #125). **Se o verbo entrar, #125 vira
  pré-requisito, não item paralelo.**
- Um tipo a mais na superfície pública, com seus próprios `to_dict`/`from_dict` — a §10 já
  conta ~11 tipos com serialização à mão.
- O produto cartesiano automático repete a armadilha da §12.1: `workflow_set` cruza tudo
  com tudo por padrão, e a grade do pacote já é exaustiva (`itertools.product` em
  `sweep.py:276`).

### Forma B — comparar é laço barato

**Referência:** scikit-learn.

```python
candidates = {"glm": LogisticRegression(), "xgb": XGBClassifier()}
results = {
    name: cross_validate(Pipeline([("prep", prep), ("est", est)]), X, y, cv=cv)
    for name, est in candidates.items()
}
pd.DataFrame({k: v["test_score"].mean() for k, v in results.items()}, index=["score"]).T
```

**Fato medido.** scikit-learn **não tem** análogo de `workflow_set`. Não existe
`estimator_set`, não existe `compare_estimators`. O laço explícito é o idioma da biblioteca,
e a documentação oficial de comparação de modelos escreve laço. `GridSearchCV` compara
*hiperparâmetros de um estimador*, não estimadores entre si — comparar estimadores por
`GridSearchCV` exige o truque de um `Pipeline` com passo trocável e um `param_grid` de lista
de objetos, que é reconhecidamente contorcido.

**Isto é a única célula da Lente A onde a forma que o dono descreveu não tem precedente no
análogo Python.**

**Porta para Python?** É Python, por definição.

**Preço.**
- Identidade, ordenação e empilhamento do resultado são responsabilidade de quem chama, toda
  vez. É exatamente onde nascem as strings `"New 1"` soltas.
- Nada garante que os N candidatos correram sob as mesmas premissas: é convenção do laço,
  não do tipo. Um `cv=` esquecido em uma iteração passa silencioso.
- Em troca: zero tipo novo, zero serialização nova, e o usuário compõe o que quiser
  (filtrar candidatos, rodar em paralelo do jeito dele, interromper no meio).

### Nota de fronteira

Este fork decide a forma da camada `sweep` / `tradeoff` / `optimize` (#128) e depende de
como a identidade fechar (#125). O backend já foi unificado em v0.5 — ambos chamam
`run_sweep` — então o que está em jogo é vocabulário e superfície, não mecânica duplicada.

---

## Fork 3 — como se marca "isto é o que varia"?

### Forma A — marcador dentro da spec

**Referência:** tidymodels, `tune()` + `finalize_workflow()`.

```r
spec  <- boost_tree(trees = tune(), tree_depth = tune()) |> set_engine("xgboost")
wf    <- workflow() |> add_recipe(rec) |> add_model(spec)

extract_parameter_set_dials(wf)   # a spec DIZ quais são seus buracos
res   <- tune_grid(wf, resamples = folds, grid = 20)
best  <- select_best(res, metric = "roc_auc")
final <- finalize_workflow(wf, best)   # preenche os buracos, devolve spec completa
```

**Fato.** `tune()` é um objeto sentinela que ocupa o campo. Efeitos observáveis:

- A spec é **auto-descritiva**: existe função que a inspeciona e devolve o conjunto de
  parâmetros a variar, com tipo e faixa. Ninguém precisa repetir a lista de buracos.
- O buraco tem **lugar tipado**. Renomear o campo move o buraco junto; não há string a
  atualizar.
- Existe um verbo explícito de fechamento (`finalize_workflow`) que transforma spec
  incompleta + resultado de seleção em spec completa. O "adotar a sugestão" é uma operação
  nomeada, não um `dict` montado à mão.

**Porta para Python?** Sim, sem tidy-eval. Um sentinela (`TUNE = object()` ou uma dataclass
`Tune(range=...)`) num campo de dataclass. A inspeção é `dataclasses.fields()` mais um
teste de tipo.

**Preço.**
- Cria um estado **válido mas não executável**. Todo consumidor precisa decidir o que faz ao
  encontrar um buraco: `validate()`, `to_dict()`, `simulate()`, `export()`, e o Studio. São
  cinco lugares hoje em `CreditPolicy` (§1: 17 métodos, cinco responsabilidades), e é
  precisamente a classe de bug da §5 se algum deles resolver "ah, se for `tune()` eu uso o
  default" em silêncio.
- O tipo do campo passa a ser `float | Tune`, e todo leitor a jusante herda a união. tidymodels
  paga isso com R dinâmico; um pacote com type hints paga em anotação e em `isinstance`.
- Round-trip: o sentinela precisa serializar e desserializar como sentinela, não como
  valor. Mais um caso na §10.

### Forma B — o que varia mora fora, endereçado por caminho

**Referência:** scikit-learn, `GridSearchCV` + a convenção `__`.

```python
pipe = Pipeline([("prep", PCA()), ("est", LogisticRegression())])
grid = {"est__C": [0.1, 1, 10], "prep__n_components": [5, 10]}

gs = GridSearchCV(pipe, grid, cv=cv, refit=True).fit(X, y)
gs.best_params_      # {"est__C": 1, "prep__n_components": 10}
gs.best_estimator_   # refit automático sobre a base inteira
gs.cv_results_       # tabela de todos os pontos, não só o vencedor
```

**Fato.** A spec (`pipe`) está **sempre completa e executável**; o que varia é um dicionário
separado, e o endereçamento é uma string com caminho hierárquico (`passo__parametro`,
recursivo: `passo__subpasso__parametro`). `refit=True` faz o `finalize` automático e devolve
o objeto pronto. `cv_results_` expõe a grade inteira ao lado do vencedor.

**Porta para Python?** É Python.

**Preço.**
- Endereçamento *stringly-typed*. Renomear um passo do pipeline quebra o grid, e o erro só
  aparece na chamada. É a mesma classe das §5 (silêncio) e §13 (a mesma coisa escrita de
  três jeitos) — e o pacote já tem despacho por substring (§12.3).
- Nada liga o grid à spec: são dois objetos que precisam concordar por convenção. Serializar
  "o experimento" é serializar os dois juntos, e nada impede que se separem.
- O `refit=True` esconde uma decisão de modelagem (refit sobre a base inteira, não sobre a
  dobra) atrás de um booleano — parente da §2.3, onde N cenários de stress colapsam num
  `max` por linha com um aviso.
- Em troca: **nunca existe objeto meio-válido**. Toda spec que existe pode rodar. É a
  propriedade que a Forma A abre mão.

### Onde o pycreditools está hoje

Nem A nem B: o que varia entra como kwargs soltos do verbo (`optimize_cutoffs(base, config)`
com `target_default_rate=`), e a #92 propõe acrescentar mais (`targets=`, `target_metric=`,
`target="incumbent"`, `target=lambda g: ...`). §12.4 registra isso como "alvo sem tipo". A
faixa de variação de cada dimensão é gerada por `np.linspace` por coluna
(`optimization.py:177`) — a faixa é implícita no verbo, não declarada em lugar nenhum.

**Nota de fronteira:** a forma do *alvo* (o que se otimiza) é #122; a forma do *fechamento*
(como uma sugestão vira política aceita) é #123; a forma do *passo* que carrega o buraco é
#129.

---

## O que este documento deliberadamente não responde

- Qualquer veredito adotar/adaptar/descartar sobre os três forks. São de #116, #117, #122,
  #123, #125, #128.
- As 20 perguntas da §16 do `architecture-critique.md` que não são de ergonomia — Lente B,
  ticket próprio.
- Fatos sobre deep modules, functional core/imperative shell, polars/ibis e CART. Lente B.
- Nomes. Nenhum nome de tipo, método ou argumento é proposto aqui.

## Limites deste levantamento

- **Lido, não executado.** As afirmações sobre tidymodels e scikit-learn vêm da API pública
  e do comportamento documentado. Nenhum benchmark, nenhuma medição de tempo ou memória.
- **Duas referências apenas.** A ausência de uma forma nestas duas não é prova de que ela
  não existe — a Forma A do Fork 2 não ter precedente em scikit-learn é afirmação sobre
  scikit-learn, não sobre Python.
- **Sem contagem de linhas.** "Poucas linhas" foi tratado qualitativamente; ninguém contou
  linhas de um caso equivalente nas duas formas.
