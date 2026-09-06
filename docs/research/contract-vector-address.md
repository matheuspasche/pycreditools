# Endereço do vetor `contract` — pesquisa de fronteira de módulo (insumo do #155)

> **Insumo de decisão, não decisão.** Este documento resolve o **passo 1** do
> [#155](https://github.com/matheuspasche/pycreditools/issues/155): a pesquisa de fronteira de
> módulo que o card manda pôr *na frente* da decisão, *"e não pelo ruling de conveniência que o
> fechou da primeira vez"*. **Nenhum veredito.** A pergunta — o estágio que produz o vetor
> `contract` (hoje `RateStage`, renomeado `.take_up` no #152) mora na `CreditPolicy` ou na
> premissa? — fica deliberadamente sem resposta aqui. Se você achar neste texto algo que se leia
> como recomendação, é **defeito do documento**: reporte no #155.
>
> **Método herdado do #134 e do #143:** onde a evidência **não se equilibra**, este documento
> diz isso e mostra o número. Simetria fabricada não é neutralidade — é fazer o card a jusante
> repetir a medição. Onde não foi possível medir ou verificar, está escrito que não foi.
>
> Documento **efêmero**, pelo #114. Duas partes, produzidas em paralelo:
>
> | parte | assunto | fonte |
> |---|---|---|
> | **I** | prior art de fronteira — como outros pacotes separam *regra declarada* de *premissa sobre o não observado*, e onde (se em algum lugar) uma invariância ganha nome | fontes primárias, 41 numeradas |
> | **II** | medição no código de hoje — acoplamento nos dois sentidos, o eixo do sorteio, a invariância localizada, e o raio de explosão contado | `arquivo:linha` sobre `src/pycreditools` |
>
> **Estado do código:** `src/pycreditools` é v0.5 e é byte-idêntico em `main`, `release/v0.5` e
> `release/v0.6`. Toda arquitetura v0.6 citada está **decidida e não implementada** — onde o
> texto diz "hoje", é o código; onde diz "decidido", é o issue.

---

# Parte I — Prior art de fronteira

## Endereço do vetor `contract` — prior art de fronteira (insumo do #155)

> **Insumo de decisão, não decisão.** Este documento registra *fatos, formas e preços*
> colhidos em fontes primárias. Ele não contém — e não deve conter — veredito,
> recomendação, ou chamada de "adotar/adaptar/descartar". Se você encontrar neste texto
> algo que se leia como recomendação, isso é um **defeito do documento**: reporte em #155
> em vez de agir sobre ele. A pergunta que este material alimenta (o estágio que produz o
> vetor `contract` pertence a `CreditPolicy` ou à premissa `Parcelling`/`External`?) fica
> deliberadamente sem resposta aqui.

### Como ler

Cada célula abaixo contém **N formas** distintas que a fronteira "regra × premissa" assume
em bibliotecas reais. Para cada forma registro três coisas: **fato** — o que a referência
concretamente faz, com nome de função, nome de argumento e citação verbatim; **porta para
Python?** — se a forma é transportável para o desenho de `pycreditools` v0.6 (tipos,
funções livres, `DataSchema`), e sob que restrição; e **preço** — o que aquela forma custa
em ergonomia, verificabilidade ou superfície de API, medido pelo que a própria fonte diz ou
pelo que a forma mecanicamente implica. Onde a evidência não se equilibra entre as opções,
digo isso e mostro o desequilíbrio: apontar assimetria medida não é escolher lado.

**Nota de acesso.** O proxy de egresso desta sessão bloqueia `scikit-learn.org`,
`parsnip.tidymodels.org`, `tmwr.org`, `lifelines.readthedocs.io`, `cran.r-project.org`,
`arxiv.org`, `tidymodels.github.io` e `marginaleffects.com`. Todo o material abaixo foi
lido do **fonte que gera esses sites** (`raw.githubusercontent.com`: `.rst`, `.Rmd`, `.Rd`,
`.py`, `.R`, `NAMESPACE`), que é a fonte primária de fato. Onde não consegui alcançar nada,
digo explicitamente "não verificado" em vez de preencher de memória.

---

### 1. tidymodels — onde moram as premissas vs. onde moram as regras

#### Forma 1.1 — A especificação é "o quê", nunca "o fazer"

**Fato.** O vignette do `parsnip` afirma o critério de separação em uma frase:

> "The parsnip package, similar to ggplot2, dplyr and recipes, **separates the
> specification of what you want to do from the actual doing**."
> — `vignettes/parsnip.Rmd`, linha 57 [1]

A especificação carrega exatamente três coisas nomeadas — *type*, *mode*, *engine* — mais
os argumentos do modelo:

> "The **mode** of the model denotes how it will be used. Two common modes are
> _classification_ and _regression_. Others would include "censored regression" and "risk
> regression" […]"
> "The **computational engine** indicates how the actual model might be fit." [1]

E o adiamento é literal, não retórico: os argumentos da spec **não são avaliados** na
construção.

> "Normally, when a function is executed, the function's arguments are immediately
> evaluated. In the case of parsnip, the model specification's arguments are _not_; the
> expression is captured along with the environment where it should be evaluated. That is
> what a quosure does."
> — `vignettes/parsnip.Rmd`, linha 162 [1]

Isso é o que permite `mtry = tune()`: um buraco declarado na spec, resolvido depois, fora
dela.

**Porta para Python?** Sim, e é essencialmente o desenho já decidido do v0.6: `CreditPolicy`
como spec inerte, execução como funções livres. O que não porta é o mecanismo de quosure
(avaliação preguiçosa de argumentos); o análogo Python é um sentinela de tipo (`Tune`,
`Unset`) ou um campo `Optional[...]` explícito.

**Preço.** Uma spec que não avalia nada não pode validar nada na construção. Erros de
coerência (por ex. um cutoff que referencia uma coluna inexistente) só aparecem no momento
do encontro com os dados. `parsnip` paga isso conscientemente — é o mesmo trade-off que o
`scikit-learn` codifica na regra §2.1 abaixo.

#### Forma 1.2 — Recusa de escopo declarada no README do pacote

**Fato.** `rsample` (reamostragem — a premissa de estudo mais óbvia do ecossistema)
declara sua fronteira negativamente, por escrito:

> "The scope of rsample is to provide the basic building blocks for creating and analyzing
> resamples of a data set, but **this package does not include code for modeling or
> calculating statistics**."
> — `rsample/README.md`, seção Overview [2]

`workflows`, por sua vez, é o único objeto autorizado a *juntar*:

> "A workflow is an object that can bundle together your pre-processing, modeling, and
> post-processing requests."
> — `workflows/README.md` [3]

Ou seja: no tidymodels a premissa (reamostragem) e a regra (spec) são pacotes **diferentes**,
e existe um terceiro tipo cuja única razão de ser é o encontro. O `Study` do v0.6 ocupa
exatamente a posição de `workflow`.

**Porta para Python?** Sim, e a tradução é direta: `CreditPolicy` ↔ spec, `Parcelling`/
`External` ↔ premissa, `Study` ↔ workflow. O que não porta é a fronteira ser *de pacote*;
em `pycreditools` ela é de módulo/tipo, o que é uma fronteira mais fraca — nada impede um
import cruzado.

**Preço.** Três tipos onde poderia haver um. O `workflows/README.md` lista o custo que a
junção resolve — "You don't have to keep track of separate objects in your workspace" [3] —
o que é a admissão de que a separação *cria* trabalho de rastreamento para o usuário, e
que o tipo-junção existe para pagá-lo de volta.

#### Forma 1.3 — `hardhat`: o blueprint é o lado do esquema, e viaja com o modelo

**Fato.** `hardhat` existe para padronizar o *pré-processamento*, e o blueprint é descrito
como o objeto que sabe reproduzi-lo:

> "This is responsible for knowing how to preprocess both the training data, and any new
> data at prediction time."
> "attach the `blueprint` to your model object before returning it to the user."
> — `hardhat/vignettes/mold.Rmd` [4]

E as metas do pacote são explícitas quanto ao que ele *não* é:

> "hardhat is a *developer focused* package designed to ease the creation of new modeling
> packages, while simultaneously promoting good R modeling package standards as laid out by
> the set of opinionated Conventions for R Modeling Packages."
> — `hardhat/README.md` [5]

**Porta para Python?** O papel de `mold()`/`forge()` (uma função que produz o par
esquema-aplicado + a receita para reaplicá-lo a dados novos) mapeia para `DataSchema` +
uma função livre de aplicação. Porta.

**Preço.** O blueprint gruda no objeto-modelo (`attach the blueprint to your model object`),
isto é: o tidymodels aceita que *um pedaço da premissa de dados viaje dentro do artefato da
regra*, porque sem isso `predict()` em dados novos não é reprodutível. É um contraexemplo
interno à própria separação — a fronteira é vazada de propósito, e a razão declarada é
reprodutibilidade em tempo de predição.

#### Forma 1.4 — O documento de critério de primeira mão (parcialmente inacessível)

**Fato.** Existe um documento de desenho de primeira mão: *Guiding Principles for tidymodels
Packages* (`tidymodels/model-implementation-principles`). Ele declara seu propósito:

> "The goal of this document is to define a specification for creating functions and
> packages for _new modeling packages_. These are opinionated specifications but are meant
> to reflect reasonable positions for standards based on prior experience."
> — `index.Rmd` [6]

Do capítulo "The Model Object" duas regras são diretamente relevantes:

> "Unless explicitly required by the model, **the training set should not be embedded in
> the model object** (exceptions being models such as _k_-nearest neighbors)."
> "Retain the _minimally sufficient_ objects in the model object."
> "When providing a convenience interface that allows fitting more than one type of model,
> **the resulting model objects should have different classes for each type of model**."
> — `03-model-object.Rmd` [7]

**Não verificado.** Só consegui recuperar `index.Rmd`, `01-general-conventions.Rmd` e
`03-model-object.Rmd` do branch `master`; os capítulos intermediários (a função de ajuste) e
o capítulo de Notas retornaram 404 sob os nomes que tentei. Não posso afirmar que o documento
enuncie em outro capítulo um critério explícito de "de que lado uma coisa cai". **Procurei e
não achei um enunciado desse critério em forma direta em nenhuma das quatro fontes tidymodels
que li** — o critério aparece só na forma performativa ("separates the specification from the
doing") e nas recusas de escopo.

**Porta para Python?** "different classes for each type of model" é a única das três regras
que fala diretamente da pergunta do #155: ela diz que uma interface de conveniência que cobre
N variantes deve produzir N classes, não uma classe com um campo discriminador.

**Preço.** N classes é N pontos de manutenção e N lugares para a documentação divergir.

---

### 2. scikit-learn — `__init__` vs `fit`, e a terceira categoria

#### Forma 2.1 — A regra dura: `__init__` guarda, `fit` faz

**Fato.** Texto verbatim de `doc/developers/develop.rst` [8]:

> "This concerns the creation of an object. The object's ``__init__`` method might accept
> constants as arguments that determine the estimator's behavior (like the ``alpha``
> constant in SGDClassifier). **It should not, however, take the actual training data as an
> argument, as this is left to the ``fit()`` method**"

> "In addition, **every keyword argument accepted by** ``__init__`` **should correspond to
> an attribute on the instance**. Scikit-learn relies on this to find the relevant
> attributes to set on an estimator when doing model selection."

> "**There should be no logic, not even input validation**, and the parameters should not be
> changed; which also means ideally they should not be mutable objects such as lists or
> dictionaries."

> "The reason for postponing the validation is that if ``__init__`` includes input
> validation, then the same validation would have to be performed in ``set_params``, which
> is used in algorithms like GridSearchCV."

**O teste mecânico** — e aqui está o critério explícito que a pergunta procura:

> "Depending on the nature of the algorithm, ``fit`` can sometimes also accept additional
> keywords arguments. However, **any parameter that can have a value assigned prior to
> having access to the data should be an ``__init__`` keyword argument**. Ideally, **fit
> parameters should be restricted to directly data dependent variables**. For instance a
> Gram matrix or an affinity matrix which are precomputed from the data matrix ``X`` are
> data dependent. A tolerance stopping criterion ``tol`` is not directly data dependent
> (although the optimal value according to some scoring function probably is)."
> — `develop.rst`, seção *Fitting* [8]

E a contrapartida no lado do estado ajustado:

> "attributes which you'd want to expose to your users as public attributes and have been
> estimated or learned from the data must always have a name ending with trailing
> underscore" [8]

**Porta para Python?** Literalmente — é Python. O teste "pode receber valor antes de ver os
dados?" é aplicável palavra por palavra a um `take_up` escalar: `0.70` pode ser escrito antes
de ver os dados, logo, por este critério, é parâmetro de construção. O mesmo teste aplicado a
uma taxa de take-up *estimada por decil observado* dá a resposta oposta. **O critério do
sklearn separa por dependência-de-dados, não por natureza (regra vs. premissa)** — e isso é
uma assimetria relevante: é um critério que classifica corretamente um take-up empírico e
classifica um take-up assumido junto com os hiperparâmetros da regra.

**Preço.** O contrato `get_params`/`set_params`/`clone` é o que cobra:

> "However, in scikit-learn, when we copy an estimator, we get an unfitted estimator where
> only the constructor arguments are copied (with some exceptions, e.g. attributes related
> to certain internal machinery such as metadata routing). The function responsible for this
> behavior is `base.clone`."
> — `develop.rst`, seção *Cloning* [8]

Consequência mecânica: **tudo que estiver em `__init__` deve ser suficiente para reconstruir
o objeto e nada além disso pode sobreviver ao clone.** Um tipo que carrega regra *e* premissa
em `__init__` continua clonável — mas todo `GridSearchCV` sobre esse tipo passa a varrer o
espaço de premissas junto com o espaço de regras, sem que nada na API marque a diferença. O
sklearn tem um teste executável para conformidade (`check_estimator`,
`parametrize_with_checks`, `develop.rst` §"Rolling your own estimator" [8]), mas ele verifica
a *forma* do contrato, não a *natureza* do que foi posto em `__init__`.

#### Forma 2.2 — Metadata routing: a terceira categoria, que não é nem hiperparâmetro nem coluna

**Fato.** Esta é a resposta explícita do sklearn para "isto não é hiperparâmetro e não é
`X`/`y`". Definição verbatim:

> "**Metadata is data that an estimator, scorer, or CV splitter takes into account if the
> user explicitly passes it as a parameter.** For instance, KMeans accepts `sample_weight`
> in its `fit()` method and considers it to calculate its centroids. `classes` are consumed
> by some classifiers and `groups` are used in some splitters, but **any data that is passed
> into an object's methods apart from X and y can be considered as metadata**."
> — `doc/metadata_routing.rst` [9]

O mecanismo de declaração é `set_{method}_request()`, e tem **quatro estados**, não dois:

> "- ``True``: method requests a ``sample_weight``. This means if the metadata is provided,
> it will be used, otherwise no error is raised.
> - ``False``: method does not request a ``sample_weight``.
> - ``None``: **router will raise an error if ``sample_weight`` is passed. This is in almost
> all cases the default value when an object is instantiated and ensures the user sets the
> metadata requests explicitly when a metadata is passed.** The only exception are
> ``Group*Fold`` splitters.
> - ``"param_name"``: alias for ``sample_weight`` […]"
> — `metadata_routing.rst`, seção *API Interface* [9]

O erro que o `None` produz é literal e nomeia o remédio:

> `[sample_weight] are passed but are not explicitly set as requested or not requested for
> LogisticRegression.score, which is used within GridSearchCV.fit. Call
> LogisticRegression.set_score_request({metadata}=True/False) for each metadata you want to
> request/ignore.` [9]

O SLEP006 (Accepted, Standards Track) dá o enquadramento do problema e a propriedade que
justifica o roteamento:

> "Scikit-learn has limited support for passing around information that is not `(X, y)`."
> "Note that in the core library nothing is requested by default, except ``groups`` in
> ``Group*CV`` objects […] **At the time of writing this proposal, all metadata requested in
> the core library are sample aligned.**"
> "Also note that ``X``, ``y``, and ``Y`` input arguments are never automatically added to
> the routing mechanism and are always passed into their respective methods."
> — `slep006/proposal.rst` [10]

**Porta para Python?** Sim, e é a forma mais próxima do que o #155 descreve como "premissa
que viaja com os dados". Duas propriedades são transportáveis independentemente do mecanismo
de roteamento: (a) o dado é **sample-aligned** — um valor por linha, não um escalar de
configuração; (b) o **default é o erro**, não o silêncio: o estado `None` existe
precisamente para impedir que a existência do mecanismo passe despercebida. Esta segunda
propriedade é o análogo mecânico exato da regra do repositório *"nenhum default de modelagem
pode esconder a EXISTÊNCIA de um mecanismo, apenas sua parametrização"*, implementado por um
projeto grande, com SLEP aceito.

**Preço.** O SLEP006 e a documentação são explícitos sobre o custo: a API é **experimental**,
está atrás de uma flag global (`sklearn.set_config(enable_metadata_routing=True)`), "is not
yet implemented for all estimators" e "may change without the usual deprecation cycle" [9].
E o custo ergonômico está no próprio exemplo canônico: para passar `sample_weight` por um
`GridSearchCV`, o usuário precisa fazer **duas** chamadas de declaração
(`.set_fit_request(sample_weight=True).set_score_request(sample_weight=False)`) antes de
poder passar o vetor. O preço de tornar a existência não-default é uma declaração obrigatória
por método consumidor.

#### Forma 2.3 — Papéis de dados nomeados no `fit`, sem objeto de premissa (EconML)

**Fato.** `EconML` (py-why) expressa a premissa de não-confundimento **apenas pela escolha de
qual matriz vai em qual slot nomeado**:

> `est.fit(Y, T, X=X, W=W) # W -> high-dimensional confounders, X -> features`
> — `EconML/README.md`, linha 153 [11]

Não há, no README, nenhuma menção às palavras *assumption*, *unconfoundedness*, *ignorability*
ou *exogeneity* (grep sobre o arquivo: zero ocorrências). O mesmo padrão em `linearmodels`:

> "dependent : array_like / **Endogenous variables** (nobs by 1)
>  exog : array_like / **Exogenous regressors** (nobs by nexog)
>  endog : array_like / **Endogenous regressors** (nobs by nendog)
>  instruments : array_like / **Instrumental variables** (nobs by ninstr)"
> — `linearmodels/iv/model.py`, docstring de `class IV2SLS` [12]

E na interface de fórmula a declaração vira **sintaxe**:

> `mod = IV2SLS.from_formula('np.log(wage) ~ 1 + exper + exper ** 2 + [educ ~ motheduc + fatheduc]', data)`
> "The expressions in the `[ ]` indicate endogenous regressors (before `~`) and the
> instruments."
> — `linearmodels/README.md`, linhas 86–90 [12]

**Porta para Python?** Sim, e é exatamente a forma que `DataSchema` já tem: a premissa é
codificada no *nome do papel* que uma coluna ocupa (`approved` / `hired` / `outcome`), não em
um objeto separado. É a forma mais barata de todas as levantadas aqui.

**Preço.** A premissa fica **inominada**. Ninguém escreve "exogeneidade"; escreve-se
`instruments=`. O nome do slot carrega a premissa por convenção compartilhada com a
literatura — o que funciona quando existe um termo canônico (instrumento, confundidor) e
falha quando não existe. `CausalML` explicita o limite dessa forma: "without strong
assumptions on the model form" [13] é a única frase sobre premissas em todo o README, e não
há tipo algum que as carregue.

---

### 3. Reject inference e take-up em pacotes de risco

Esta é a célula onde a evidência **não se equilibra**, e o desequilíbrio é grande o
suficiente para ser o achado principal da célula.

#### Forma 3.1 — A maioria dos pacotes de scorecard não representa take-up de forma alguma

**Fato.** Levantamento por `NAMESPACE`/`__init__.py`/assinatura de classe:

| Pacote | Fonte lida | Função/atributo de acceptance, take-up ou reject inference |
|---|---|---|
| `scorecardpy` (Python) | `scorecardpy/__init__.py` [14] | **nenhum** — exporta `woebin`, `scorecard`, `scorecard_ply`, `perf_eva`, `perf_psi`, `var_filter`, `iv`, `vif`, `split_df`, `one_hot` |
| `scorecard` (R) | `NAMESPACE` [15] | **nenhum** — 21 exports, todos de binning/scaling/performance |
| `toad` (Python) | `toad/__init__.py` [16] | **nenhum** — `merge`, `detect`, `KS`, `IV`, `Combiner`, `WOETransformer`, `select`, `ScoreCard` |
| `creditmodel` (R) | `NAMESPACE` [17] | **nenhum** — 181 exports; grep por `reject\|accept\|take.?up` retorna zero |
| `Rprofet` (R) | `NAMESPACE` [18] | não determinável — usa `exportPattern("^[[:alpha:]]+")`, sem lista explícita |
| `optbinning` (Python) | `optbinning/scorecard/scorecard.py` [19] | **nenhum** — `Scorecard(binning_process, estimator, scaling_method, scaling_method_params, intercept_based, …)`; métodos `fit(X, y, sample_weight=…)`, `predict`, `predict_proba`, `score` |

O `Scorecard` do `optbinning` é o caso mais nítido de "o tipo é só a regra":

> "binning_process : object / A ``BinningProcess`` instance.
>  estimator : object / A supervised learning estimator with a ``fit`` and ``predict``
>  method […]
>  scaling_method : str or None (default=None) / The scaling method to control the range of
>  the scores."
> — docstring de `class Scorecard` [19]

Nada de aceitação, nada de take-up, nada de contrato. O funil é uma coisa; o scorecard é
outra, e a outra não é modelada.

**Preço da ausência.** Nenhum desses pacotes produz um vetor equivalente a `contract`.
A pergunta do #155 **não tem prior art nesse conjunto** — a assimetria não é entre "põem na
regra" e "põem na premissa"; é entre "não modelam" (6 pacotes) e "modelam na premissa"
(1 pacote, abaixo).

#### Forma 3.2 — `scoringTools`: `acceptance_model` é um *slot nomeado do resultado da premissa*

**Fato.** O pacote R `scoringTools` (Adrien Ehrhardt) é o único do levantamento que implementa
reject inference como API de primeira classe. Exports [20]:

```
export(augmentation)   export(fuzzy_augmentation)   export(parcelling)
export(reclassification)   export(twins)   export(generate_data)
```

Todos os cinco métodos retornam **o mesmo tipo S4**, `reject_infered`, cuja documentação
lista quatro slots [21]:

> "An S4 class to represent a reject inference technique.
>  \item{\code{method_name}}{The name of the used reject inference method.}
>  \item{\code{financed_model}}{The logistic regression model on financed clients.}
>  \item{\code{acceptance_model}}{**The acceptance model (if estimated by the given
>  method).**}
>  \item{\code{infered_model}}{The logistic regression model resulting from the reject
>  inference method.}"

E o preenchimento desse slot varia por método, verbatim do código:

```r
# R/twins.R:54
methods::new(Class = "reject_infered", method_name = "twins",
             financed_model = model_f, acceptance_model = model_acc,
             infered_model = model_twins)

# R/parcelling.R (última linha)
methods::new(Class = "reject_infered", method_name = "parceling",
             financed_model = model_f, acceptance_model = as.logical(NA),
             infered_model = model_parcelling)

# R/augmentation.R:70 e R/reclassification.R:49 — idem, acceptance_model = as.logical(NA)
```

Três fatos que decorrem disso, e que respondem literalmente à sub-pergunta "onde o pacote
põe, e diz por quê":

1. **O modelo de aceitação é um slot do resultado da inferência de rejeitados — isto é, da
   premissa — e não do scorecard.** O `financed_model` (a regra ajustada nos financiados) é
   um slot *irmão*, separado.
2. **O slot existe mesmo quando o método não o parametriza.** `parcelling`, `augmentation` e
   `reclassification` escrevem `as.logical(NA)`: a ausência é *expressa dentro do nome*, não
   pela inexistência do nome. O tipo declara que existe um mecanismo de aceitação em todo
   estudo de reject inference; cada método declara se o estimou. É um caso concreto e
   publicado do padrão "nomeie o mecanismo, mesmo quando o valor for 'não modelado'".
3. **A premissa de missingness é nomeada por método, em prosa de roxygen, na primeira linha
   da doc de cada função:**
   - `parcelling`: "Note that this technique is theoretically good in the **MNAR** framework
     although **coefficients must be chosen a priori**." [22]
   - `augmentation`: "Note that this technique is theoretically better than using the
     financed clients scorecard in the **MAR** and misspecified model case." [23]
   - `twins`: "Note that this technique has **no theoretical foundation**." [24]
   - `reclassification`: "Note that this technique has **no theoretical foundation** as it
     performs a one-step CEM algorithm." [25]

A assinatura de `parcelling` mostra como a premissa vira argumento:

```r
parcelling <- function(xf, xnf, yf, probs = seq(0, 1, 0.25),
                       alpha = rep(1, length(probs) - 1))
```
> "@param probs The sequence of quantiles to use to make scorebands"
> "@param alpha **The user-defined coefficients** to use with Parcelling" [22]

`alpha = rep(1, ...)` é um default que **parametriza** o mecanismo (coeficiente 1 = sem
inflação da taxa de mau nas faixas) sem esconder que ele existe: o argumento está na
assinatura e a doc diz que os coeficientes são escolhidos *a priori* pelo usuário.

**Porta para Python?** Sim, em duas formas separáveis:
- o **slot nomeado com ausência explícita** (`acceptance_model: AcceptanceModel | None`, com
  `None` significando "esta premissa não estima aceitação" e não "não pensei nisso");
- o **par premissa-nomeada / parâmetro-a-priori** (`Parcelling(probs=..., alpha=...)`),
  onde a docstring nomeia o regime (MNAR) e a assinatura carrega os coeficientes.

**Preço.** Três custos mensuráveis no próprio código:
1. O slot é do **resultado**, não da **entrada**. O usuário não declara nada sobre aceitação;
   o método decide se estima. Isso significa que a existência do mecanismo é comunicada
   *depois* da execução, ao inspecionar o objeto — não *antes*, ao escrever o estudo.
2. Para o slot aceitar dois tipos (`glm` ou `NA`), o pacote define uma classe-união
   `glmORlogicalORspeedglm` e faz `class(model_acc) <- c("glmORlogicalORspeedglm",
   class(model_acc))`. O preço de nomear a ausência dentro de um slot tipado é um tipo-união
   artificial atravessando o pacote.
3. O `method_name` é uma **string**, não um tipo. Discriminar métodos por string é o oposto
   da regra tidymodels §1.4 ("different classes for each type of model"). Os dois desenhos
   de primeira mão discordam neste ponto — registro a discordância, não a arbitro.

#### Forma 3.3 — Heckman: duas equações, dois argumentos

**Fato.** Em `sampleSelection` (R), a separação entre equação de seleção e equação de
resultado é a assinatura da função:

```r
selection(selection, outcome, data = sys.frame(sys.parent()),
   weights = NULL, subset, method = "ml", type = NULL, start = NULL,
   boundaries = NULL, ys = FALSE, xs = FALSE, yo = FALSE, xo = FALSE,
   mfs = FALSE, mfo = FALSE, printLevel = print.level, print.level = 0, ...)
```
> "**selection**: formula, **the selection equation**."
> "**outcome**: **the outcome equation(s).** Either a single equation (for tobit 2 models),
> or a list of two equations (tobit 5 models)."
> — `man/selection.Rd` [26]

Os dois primeiros argumentos posicionais são duas fórmulas independentes. A seleção não é um
argumento *da* equação de resultado: é um par. Note também que o `type` (tobit 2 vs. tobit 5)
é inferido da *forma* do argumento `outcome`, e que o sufixo `s`/`o` percorre toda a lista de
argumentos (`ys`/`yo`, `xs`/`xo`, `mfs`/`mfo`) marcando de qual das duas equações cada
artefato retornado vem.

**Ausência em Python — verificada.** `statsmodels/api.py` (o namespace público, 148 linhas)
não contém nenhuma ocorrência de `heckman` ou `selection`; `docs/source/regression.rst`
também não [27]. `linearmodels` cobre IV, painel e sistemas, e não lista modelos de seleção
entre as capacidades do README [12]. **Não encontrei implementação de Heckman em nenhuma das
duas bibliotecas Python de econometria que consultei diretamente.** Não fiz uma varredura
exaustiva do ecossistema Python.

**Porta para Python?** A forma — *duas declarações irmãs, simétricas, na mesma assinatura* —
porta trivialmente e é o desenho mais explícito levantado neste documento sobre a relação
entre "quem entra na amostra" e "o que acontece com quem entrou". Note que ela **não** decide
a pergunta do #155 por si: `selection()` é uma função de estimação, não um par de tipos
regra/premissa; as duas equações são igualmente "premissa" ali.

**Preço.** Simetria de argumentos exige simetria de conteúdo: as duas fórmulas do
`sampleSelection` operam sobre a mesma tabela e o mesmo vocabulário de colunas. E o pacote
paga isso na superfície: seis argumentos de retorno duplicados (`ys`/`yo`, `xs`/`xo`,
`mfs`/`mfo`) existem só para desambiguar de qual equação vem cada peça.

---

### 4. Censura em análise de sobrevivência — a premissa que tem nome

Esta célula tem uma estrutura interna nítida e repetida em três pacotes independentes: **o
indicador viaja com os dados; a FORMA do mecanismo é nomeada na API; a INDEPENDÊNCIA do
mecanismo não é nomeada em lugar nenhum da API.**

#### Forma 4.1 — O indicador é parte do tipo de resposta

**Fato — R `survival`:**
```r
Surv(time, time2, event, type = c('right','left','interval','counting','interval2'), origin = 0)
```
> "Create a survival object, usually used as **a response variable in a model formula**."
> "**event**: The status indicator, normally 0=alive, 1=dead. […]"
> "**type**: character string specifying the type of censoring. Possible values are
> "right", "left", "counting", "interval", "interval2". **The default is multi-state if
> `event` is a factor, counting process if `time2` is present, or right censored, in that
> order.**"
> — `man/Surv.Rd` [28]

**Fato — `scikit-survival`:** o análogo é uma classe-helper cuja única função é construir o
array estruturado que é o `y`:

> "A helper class to create a structured array for survival analysis. This class provides
> helper functions to create a structured array that encapsulates the event indicator and
> the observed time. **The resulting structured array is the recommended format for the
> ``y`` argument in scikit-survival's estimators.**"
> ```python
> Surv.from_arrays(event, time, name_event=None, name_time=None)
> # event : "Event indicator. A boolean array or array with values 0/1, where True or 1
> #          indicates an event and False or 0 indicates right-censoring."
> # time  : "Observed time. Time to event or time of censoring."
> ```
> — `sksurv/util.py`, `class Surv` [29]

**Fato — `lifelines`:** viaja como argumento de `fit`, não como tipo:
```python
KaplanMeierFitter.fit(durations, event_observed=None, timeline=None, entry=None,
                      label=None, alpha=None, ci_labels=None, weights=None,
                      fit_options=None)
```
> "**event_observed**: […] True if the death was observed, False if the event was lost
> (right-censored). **Defaults all True if event_observed==None**"
> — `lifelines/fitters/kaplan_meier_fitter.py`, docstring de `fit` [30]

**Porta para Python?** As duas formas Python já existem e diferem: `scikit-survival` faz do
par (indicador, tempo) **um tipo** (`y` estruturado, construído por `Surv.from_arrays`);
`lifelines` faz dele **dois argumentos de método**. A primeira é o análogo de um `DataSchema`
que declara papéis; a segunda é o análogo de passar vetores soltos.

**Preço — e aqui há um achado direto sobre a regra "nenhum default esconde a EXISTÊNCIA de um
mecanismo".** Duas das três bibliotecas embutem um default que **assume ausência total de
censura**, e ambas documentam isso em prosa de docstring:

- R `survival`: "**Although unusual, the event indicator can be omitted, in which case all
  subjects are assumed to have an event.**" [28]
- `lifelines`: "**Defaults all True if event_observed==None**" [30]

Ou seja: nos dois casos, omitir o argumento faz o mecanismo de censura desaparecer
silenciosamente, e a única barreira é a linha de docstring. `scikit-survival` não oferece esse
default — `Surv.from_arrays(event, time)` exige ambos, posicionalmente — e ainda expõe um
parâmetro de checagem, `check_y_survival(..., allow_all_censored=False, ...)`:
> "**allow_all_censored** : bool, optional, default: False — Whether to allow all events to
> be censored." [29]
Este é o único ponto em toda a célula 4 onde um *aspecto* do mecanismo de censura vira
argumento verificável em vez de prosa — e ele checa o caso degenerado (tudo censurado), não a
independência.

#### Forma 4.2 — A forma da censura é nomeada; em `Surv()` como enum, em `lifelines` como método

**Fato.** R `survival` nomeia a forma no argumento `type=` com cinco valores literais
(`"right"`, `"left"`, `"counting"`, `"interval"`, `"interval2"`) e documenta a ordem de
resolução do default [28]. `lifelines` nomeia a mesma coisa no **nome do método**:
`fit()` ("Fit the model to a right-censored dataset"), `fit_interval_censoring()` ("Fit the
model to a interval-censored dataset using non-parametric MLE. This estimator is also called
the Turnbull Estimator.") [30].

**Porta para Python?** Ambas. Um `Literal["right","left","interval"]` num campo, ou N funções
livres nomeadas. É a mesma escolha de forma que aparece em §5.2 (`grid_type=`) e §3.2
(`method_name` string vs. classes distintas).

**Preço.** O enum concentra a documentação num lugar e faz o default ser uma regra de
resolução com três cláusulas ("multi-state if event is a factor, counting process if time2 is
present, or right censored, in that order" [28]) — regra que é ela própria um default
implícito sobre qual mecanismo está em jogo. Os métodos separados eliminam a regra de
resolução mas multiplicam docstrings e assinaturas.

#### Forma 4.3 — A premissa de censura não-informativa: prosa forte, zero API

**Fato.** Fiz grep por `independent censoring`, `non-informative`, `noninformative`,
`uninformative`, `informative censor` em: `man/Surv.Rd`, `man/coxph.Rd`, `sksurv/util.py`,
`lifelines/fitters/kaplan_meier_fitter.py`, `docs/Survival Analysis intro.rst` (lifelines) e
`doc/user_guide/00-introduction.ipynb` (scikit-survival). **Zero ocorrências em todos os
seis.** A palavra aparece exatamente **quatro vezes** em ~3.800 linhas do vignette principal
do `survival` [31], e sempre em prosa argumentativa:

> "In order to estimate this fictional quantity one needs to assume that death is
> uninformative with respect to future disease progression. The early deaths in months 0–2,
> before transplant begins, are however a very different class of patient. **Non-informative
> censoring is untenable.** […] We are left with an unreliable estimate of an uninteresting
> quantity. **Mislabeling any true state as censoring is always a mistake**, one that will
> not be repeated here."
> — `vignettes/survival.Rnw`, linhas 1144–1150 [31]

> "(**If there is informative censoring** the overall and individual estimates still agree,
> but **they will both be wrong**. An example of informative censoring would be subjects who
> are removed from the data because of an impending event, e.g., censoring subjects who
> enter hospice care would underestimate death rates.)"
> — `vignettes/survival.Rnw`, linhas 3635–3639 [31]

**Não encontrei**, em nenhum dos três pacotes, um objeto, um argumento, um atributo ou uma
função de checagem que nomeie ou torne verificável a premissa de censura independente. A
premissa mais central da análise de sobrevivência é, nos três, **exclusivamente prosa** — e
prosa que o próprio autor do pacote considera importante o bastante para escrever "sempre um
erro" em um vignette de referência.

**Assimetria registrada.** Esta é uma evidência forte de **um lado só**: o precedente
dominante em sobrevivência é *não nomear a invariância na API*. Não encontrei o
contra-exemplo pedido pelo briefing ("algum pacote que torne a premissa de censura
verificável ou nomeável"); o mais próximo é o `allow_all_censored` do `scikit-survival`, que
checa um caso degenerado e não a premissa. Registro isso como lacuna de busca, não como
inexistência provada.

---

### 5. Coeteris paribus nomeável — precedentes

#### Forma 5.1 — O nome da premissa *é* o nome do tipo (DALEX / ingredients)

**Fato.** Em R, `ingredients::ceteris_paribus()`:
> "**Ceteris Paribus Profiles aka Individual Variable Profiles**
>  This explainer works for individual observations. For each observation it calculates
>  Ceteris Paribus Profiles for selected variables. Such profiles can be used to hypothesize
>  about model results **if selected variable is changed**. For this reason it is also called
>  '**What-If Profiles**'."
> "@return an object of the class `ceteris_paribus_explainer`."
> — `ingredients/R/ceteris_paribus.R` [32]

Em Python, o mesmo conceito aparece em **três níveis simultâneos**:
1. como **classe**: `class CeterisParibus(Explanation)` — "Calculate predict-level variable
   profiles as Ceteris Paribus" [33];
2. como **valor de argumento enumerado**:
   `Explainer.predict_profile(new_observation, type=('ceteris_paribus',), …)`, com
   `type : {'ceteris_paribus', TODO: 'oscilations'}` [34];
3. como **nome do método**: `predict_profile`.

Os parâmetros do tipo são todos sobre *como* variar, não sobre *o que fica constante*:
`variables`, `grid_points=101`, `variable_splits`, `variable_splits_type={'uniform',
'quantiles'}`, `variable_splits_with_obs=True` [33].

**Porta para Python?** Sim — é literalmente Python, e é o precedente mais direto de "dar nome
próprio a uma invariância". O nome latino carrega a premissa inteira: *tudo o mais constante*.
Note a assimetria interna dessa forma: **o nome nomeia a invariância, mas nenhum campo do tipo
enumera o que está sendo mantido constante.** O conjunto invariante é o complemento implícito
de `variables`.

**Preço.** O nome é o único portador. Não há campo, não há validação, não há relatório de "o
que ficou fixo". Quem lê `CeterisParibus(variables=['age'])` sabe, pelo nome do tipo, que tudo
menos `age` está congelado — mas o objeto não diz *em que valores*, e a doc do próprio pacote
delega o significado a um capítulo de livro externo (`Notes: https://pbiecek.github.io/ema/
ceterisParibus.html` [33]). **Não verificado:** não consegui recuperar o capítulo do livro
*Explanatory Model Analysis* no repositório `pbiecek/ema` (404 nos nomes de arquivo que
tentei); cito o URL apenas como referência que os próprios pacotes fazem.

#### Forma 5.2 — O regime de "mantido constante" como argumento enumerado (`marginaleffects`)

**Fato.** `marginaleffects::datagrid()` faz do "held constant" um **parâmetro nomeado com
enumeração documentada**, e não uma propriedade implícita:

> "@return A `data.frame` in which each row corresponds to one combination of the named
> predictors supplied by the user via the `...` dots. **Variables which are not explicitly
> defined are held at their mean or mode.**"

> "@param **grid_type** character. Determines the functions to apply to each variable. The
> defaults can be overridden by defining individual variables explicitly in `...`, or by
> supplying a function to one of the `FUN_*` arguments.
>   * "**mean_or_mode**": Character, factor, logical, and binary variables are set to their
>     modes. Numeric, integer, and other variables are set to their means.
>   * "**balanced**": Each unique level of character, factor, logical, and binary variables
>     are preserved. Numeric, integer, and other variables are set to their means. […]
>   * "**dataframe**": Similar to "mean_or_mode" but creates a data frame by binding columns
>     element-wise rather than taking the cross-product. […]
>   * "**counterfactual**": the entire dataset is duplicated for each combination of the
>     variable values specified in `...`. **Variables not explicitly supplied to
>     `datagrid()` are set to their observed values in the original dataset.**"
> — `r/R/datagrid.R`, roxygen de `datagrid()` [35]

E há um segundo nível de controle, por *tipo de coluna*: `FUN`, `FUN_character`, `FUN_factor`,
`FUN_logical`, `FUN_integer`, `FUN_binary`, `FUN_numeric`, `FUN_other` [35].

Crucialmente, a costura: `datagrid()` **não é argumento do modelo**. Ela é passada no
argumento `newdata=` de `predictions()`, `comparisons()` e `slopes()`:
> "Generate a data grid of user-specified values **for use in the `newdata` argument** of the
> `predictions()`, `comparisons()`, and `slopes()` functions. This is useful to define **where
> in the predictor space we want to evaluate the quantities of interest**." [35]

**Porta para Python?** Sim, e é a forma mais estruturalmente próxima da pergunta do #155
entre todas as levantadas: um **regime de invariância nomeado, enumerado e default-explícito**,
que viaja pelo **canal dos dados** (`newdata=`) e não pelo canal do modelo, para uma **função
livre** que faz o encontro. O pacote também é R+Python (mesmo desenho nas duas linguagens,
por afirmação do README [36]).

**Preço.** Três custos visíveis no próprio roxygen:
1. O regime default (`"mean_or_mode"`) é **um default que decide a invariância** — exatamente
   a categoria de default que o repositório restringe. O pacote o mitiga documentando-o na
   seção `@return` e no primeiro exemplo ("The output only has 2 rows, and all the variables
   except `hp` are at their mean or mode." [35]), não impedindo-o.
2. O default é **conhecidamente capaz de produzir estados impossíveis**, e a doc admite isso
   com um aviso dedicado: "**Warning about hierarchical grouping variables:** When using the
   default `grid_type = "mean_or_mode"` […] `datagrid()` may create invalid combinations of
   grouping variables. […] This can cause prediction errors." [35] O preço de nomear o regime
   sem verificá-lo é que o usuário recebe um aviso em prosa, não um erro.
3. Quatro regimes × oito `FUN_*` = uma superfície de argumentos larga para uma única ideia.

#### Forma 5.3 — A premissa como *dado nomeado anexado ao estimando* (DoWhy)

**Fato.** DoWhy carrega as premissas como **strings nomeadas dentro do objeto `estimand`**,
uma entrada de dicionário por premissa, construídas no passo de identificação:

```python
# dowhy/causal_identifier/auto_identifier.py
sym_assumptions = {
    "Unconfoundedness": ("If U→{0} and U→{1} then P({1}|{0},{2},U) = P({1}|{0},{2})")…
}
estimand = {"estimand": sym_effect, "assumptions": sym_assumptions}
```
Os nomes literais usados são: `"Unconfoundedness"` (backdoor), `"As-if-random"` e
`"Exclusion"` (IV), `"Full-mediation"`, `"First-stage-unconfoundedness"` e
`"Second-stage-unconfoundedness"` (frontdoor) [37]. Eles são impressos no `__str__` do
estimando:
```python
s += "Estimand assumption {0}, {1}: {2}\n".format(j, ass_name, ass_str)
```
— `dowhy/causal_identifier/identified_estimand.py`, linha 158 [38]

A classe `IdentifiedEstimand` — "Class for storing a causal estimand, typically as a result of
the identification step" — tem campos nomeados para cada papel estrutural:
`treatment_variable`, `outcome_variable`, `backdoor_variables`, `general_adjustment_variables`,
`instrumental_variables`, `frontdoor_variables`, `mediator_variables`,
`mediation_first_stage_confounders`, `mediation_second_stage_confounders`, `identifier_method`
[38].

O benefício declarado pela documentação de primeira mão:

> "DoWhy stresses on the interpretability of its output. **At any point in the analysis, you
> can inspect the untested assumptions, identified estimands (if any), and the estimate (if
> any).**"
> — `README.rst`, linhas 183–185 [39]

> "A key feature of DoWhy is its **refutation and falsification API that can test causal
> assumptions for any estimation method**, thus making inference more robust and accessible
> to non-experts."
> — `README.rst`, linha 45 [39]

> "Since causal tasks concern an interventional data distribution that is often not observed,
> we need special ways to evaluate the validity of a causal estimate. **Methods like
> cross-validation from predictive machine learning do not work**, unless we have access to
> samples from the interventional distribution. Therefore, for each causal task, an important
> part of the analysis is to test whether the obtained answer is valid. In DoWhy, we call this
> process *refutation*, **which involves refuting or challenging the assumptions made by a
> causal analysis**."
> — `docs/source/user_guide/intro.rst`, linha 29 [40]

E a arquitetura de quatro passos separa fisicamente premissa de estimação:
```python
model = CausalModel(data=…, treatment=…, outcome=…, graph=…)   # I. modelar (premissa)
identified_estimand = model.identify_effect()                   # II. identificar
estimate = model.estimate_effect(identified_estimand, method_name=…)  # III. estimar
refute_results = model.refute_estimate(identified_estimand, estimate, method_name=…)  # IV. refutar
```
— `README.rst`, linhas 165–182 [39]

**Porta para Python?** Sim, integralmente — é Python. A forma tem três peças separáveis:
(a) premissas como **dados nomeados** (`dict[str, str]`), não como tipos; (b) anexadas ao
**resultado da identificação**, que é um objeto intermediário distinto tanto do modelo quanto
da estimativa; (c) um passo de **refutação** como API separada, cujo texto do README chama as
premissas de "**untested**" enquanto não passam por ele.

**Preço.** O próprio vocabulário do pacote nomeia o preço: as premissas são "untested" por
construção — nomear não é verificar, e o DoWhy precisa de uma quarta API inteira (`refute_*`)
para fazer alguma coisa com os nomes. Além disso, premissas como strings formatadas não são
comparáveis, indexáveis ou tipadas: dois estimandos com a mesma premissa produzem duas strings
que só coincidem se as variáveis tiverem o mesmo nome. É a mesma escolha string-vs-tipo da
§3.2 (`method_name`) e o oposto da regra tidymodels da §1.4.

#### Forma 5.4 — A invariância mencionada só na prosa, sem nome na API (sklearn PDP/ICE)

**Fato.** `sklearn.inspection.partial_dependence` é o caso de referência de "held constant"
implícito. A documentação enuncia a premissa duas vezes, ambas em prosa, e nunca a expõe como
argumento:

> "Both PDPs and ICEs **assume that the input features of interest are independent from the
> complement features**, and this assumption is **often violated in practice**. Thus, in the
> case of correlated features, **we will create absurd data points** to compute the PDP/ICE."
> — `doc/modules/partial_dependence.rst`, linhas 14–17 [41]

> "Remember, however, that **the primary assumption for interpreting PDPs is that the
> features should be independent**."
> — idem, nota da seção de métodos de cálculo, linhas 261–263 [41]

O vocabulário do "o que fica constante" é *marginalização*, não *invariância*:
> "Partial dependence plots (PDP) show the dependence between the target response and a set
> of input features of interest, **marginalizing over the values of all other input features
> (the 'complement' features)**." [41]

O único lugar onde a premissa toca a API é indiretamente, via `method={'brute','recursion'}`:
> "The `'brute'` method **assumes the existence of the data points** $(x_S, x_C^{(i)})$. When
> the features are correlated, such artificial samples may have a very low probability mass."
> [41]

**Porta para Python?** É Python. Registro-a aqui como o **polo oposto** da §5.1/§5.2 na mesma
linguagem e para o mesmo tipo de objeto (perfil de variação com o resto congelado): mesma
operação, zero nomes.

**Preço.** O preço é nomeado pela própria doc: "we will create absurd data points". A ausência
de nome não gera erro nem aviso em tempo de execução — a única mitigação é a linha de
documentação e a distinção `brute`/`recursion`, que o texto adverte que "will likely disagree"
exatamente no caso em que a premissa falha [41].

#### Síntese da célula 5 (fatos, não juízo)

Quatro formas, ordenadas por quanto do "coeteris paribus" está codificado na API:

| Forma | O nome da invariância está em… | O conjunto invariante está enumerado? | O regime é escolhível? |
|---|---|---|---|
| sklearn PDP/ICE [41] | prosa da doc, apenas | não (complemento implícito de `features`) | não |
| DALEX / ingredients [32][33][34] | nome do tipo, do método e valor de `type=` | não (complemento implícito de `variables`) | não |
| DoWhy [37][38][39] | chave de dicionário no estimando (`"Unconfoundedness"`) | os *papéis* sim (`backdoor_variables` etc.); a invariância não | não (decorre do grafo + identificação) |
| marginaleffects `datagrid()` [35] | valor do argumento `grid_type=` | sim, por tipo de coluna (`FUN_*`) e por variável (`...`) | **sim**, quatro regimes nomeados |

Nenhuma das quatro põe a invariância dentro do **modelo**. Duas põem no **objeto de
explicação/premissa** (DALEX, DoWhy); uma põe na **construção da grade de dados** que viaja
por `newdata=` (marginaleffects); uma não põe em lugar nenhum (sklearn). Esta é uma assimetria
medida: **não encontrei nenhum precedente, nas fontes que li, em que uma premissa de
invariância seja um campo do objeto que representa a regra.**

---

### 6. O preço de um tipo que carrega regra e premissa juntas

Não encontrei um documento de desenho de primeira mão cujo assunto declarado seja "o modo de
falha de um tipo que mistura configuração e premissa". O que existe, em fontes primárias, são
**critérios publicados com teste enunciado** que incidem sobre a mistura como efeito colateral.
Registro os quatro que consegui ler, com o teste de cada um.

#### Critério 6.1 — Reconstrutibilidade por `get_params` (scikit-learn) — teste executável

**Fato.** O contrato: `get_params()` "returns a dict of the ``__init__`` parameters of the
estimator, together with their values"; `clone` produz "an unfitted estimator where only the
constructor arguments are copied" [8]. O teste é executável e distribuído com a biblioteca:

> "Rolling your own estimator […] check_estimator on an instance. The
> `parametrize_with_checks` pytest decorator […]"
> ```python
> >>> from sklearn.utils.estimator_checks import check_estimator
> >>> check_estimator(DecisionTreeClassifier())  # passes
> ```
> — `develop.rst`, seção *Rolling your own estimator*, linhas 256–269 [8]

**O que o teste pega e o que não pega.** `check_estimator` verifica a *forma* (init sem lógica,
params ↔ atributos, clonabilidade, sufixo `_` para estado aprendido). Ele **não** verifica a
*natureza* do que foi posto em `__init__`. Um tipo que carregasse regra e premissa passaria em
`check_estimator` sem reclamação. O custo mecânico, porém, é determinado: como
`GridSearchCV`/`set_params` operam sobre *todo* o dicionário de `get_params`, uma premissa
posta em `__init__` torna-se automaticamente varrível como se fosse hiperparâmetro, sem nada
na API que a distinga.

**Preço da alternativa.** O sklearn construiu uma segunda categoria inteira (metadata routing,
§2.2) precisamente para o que não cabe nem em `__init__` nem em `X`/`y`, e pagou por ela com:
flag global, status experimental, isenção do ciclo normal de depreciação, e uma declaração
obrigatória por método consumidor [9][10].

#### Critério 6.2 — "Minimamente suficiente" e "uma classe por tipo" (tidymodels)

**Fato.** Do capítulo *The Model Object* [7]:
> "Retain the _minimally sufficient_ objects in the model object."
> "Unless explicitly required by the model, the training set should not be embedded in the
> model object […]"
> "When providing a convenience interface that allows fitting more than one type of model,
> the resulting model objects should have different classes for each type of model."

**O teste.** "Minimamente suficiente" é um teste de necessidade: um campo só permanece se
alguma operação declarada do objeto o exigir. Aplicado a um tipo que carrega premissa, o teste
pergunta se as operações da *regra* precisam do campo da *premissa*.

**Preço do critério.** É um teste de julgamento, não executável — ao contrário do 6.1, não vem
com `check_*`. O documento é explícito quanto ao seu próprio estatuto: "These are **opinionated
specifications** but are meant to reflect reasonable positions for standards based on prior
experience." [6]

#### Critério 6.3 — Recusa de escopo por escrito (rsample)

**Fato.** "The scope of rsample is […] but this package **does not include** code for modeling
or calculating statistics." [2] O teste implícito é de admissibilidade: se a mudança proposta
exige escrever código de modelagem dentro do pacote de reamostragem, ela está do lado errado da
fronteira.

**Preço.** Recusas de escopo empurram o custo para o usuário, que passa a manter objetos
separados — custo que `workflows` existe para pagar de volta, por admissão do próprio README
[3].

#### Critério 6.4 — O custo observável de um slot que aceita "modelo ou nada" (scoringTools)

**Fato.** Não é um critério declarado; é um custo **observado** no código, e o registro aqui é
descritivo. Para que `acceptance_model` aceitasse tanto um `glm` ajustado quanto
`as.logical(NA)`, o pacote precisou de uma classe-união `glmORlogicalORspeedglm`, aplicada por
atribuição manual de classe (`class(model_acc) <- c("glmORlogicalORspeedglm", class(model_acc))`
em `R/twins.R`; o mesmo padrão em `R/parcelling.R` e `R/reclassification.R`) [20][22][24][25].
E o discriminador de método é uma string livre (`method_name = "parceling"`, note inclusive a
grafia divergente do nome exportado `parcelling`) em vez de um tipo.

**Preço registrado.** (a) um tipo-união artificial atravessando o pacote; (b) um discriminador
não-tipado, sujeito a erro de grafia, que o critério 6.2 explicitamente desaconselha; (c) a
existência do mecanismo é legível apenas *pós-execução*, ao inspecionar o slot do resultado.

#### O que não consegui verificar nesta célula

- O artigo de desenho de API do scikit-learn (Buitinck et al., 2013, *API design for machine
  learning software*) está no arXiv, **bloqueado** pelo proxy desta sessão. Não o cito.
- Os capítulos intermediários de *Guiding Principles for tidymodels Packages* (a função de
  ajuste; o capítulo de Notas referenciado por `[{note}](#minimal)`) retornaram 404 nos nomes
  que tentei. É possível que contenham um enunciado mais direto do critério de fronteira.
- **Não encontrei nenhum documento de primeira mão** — em nenhum dos ecossistemas consultados —
  que enuncie um teste nomeado para "este campo é regra ou é premissa?". Os quatro critérios
  acima incidem sobre a questão de viés, por dependência-de-dados (6.1), por necessidade (6.2),
  por escopo de pacote (6.3), ou por custo observado (6.4). Registro isso como ausência
  procurada, não como inexistência provada.

---

### Fontes

Todas lidas em `raw.githubusercontent.com` (fonte que gera a documentação publicada), via
`curl`, nesta sessão. Domínios bloqueados pelo proxy de egresso e portanto **não** consultados
diretamente: `scikit-learn.org`, `parsnip.tidymodels.org`, `tmwr.org`,
`lifelines.readthedocs.io`, `cran.r-project.org`, `arxiv.org`, `tidymodels.github.io`,
`marginaleffects.com`.

1. `https://raw.githubusercontent.com/tidymodels/parsnip/main/vignettes/parsnip.Rmd` — definição de type/mode/engine; a frase "separates the specification of what you want to do from the actual doing"; a explicação de quosures e da não-avaliação dos argumentos.
2. `https://raw.githubusercontent.com/tidymodels/rsample/main/README.md` — recusa de escopo ("does not include code for modeling or calculating statistics").
3. `https://raw.githubusercontent.com/tidymodels/workflows/main/README.md` — definição de workflow como objeto de junção; vantagens declaradas.
4. `https://raw.githubusercontent.com/tidymodels/hardhat/main/vignettes/mold.Rmd` — papel do blueprint; instrução de anexá-lo ao objeto-modelo.
5. `https://raw.githubusercontent.com/tidymodels/hardhat/main/README.md` — as quatro metas do hardhat; ponteiro para as *Conventions for R Modeling Packages*.
6. `https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/index.Rmd` — propósito e estatuto do documento de princípios.
7. `https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/03-model-object.Rmd` — "minimally sufficient"; não embutir o treino; uma classe por tipo de modelo.
8. `https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/developers/develop.rst` — seções *Instantiation*, *Fitting*, *Estimated Attributes*, *get_params and set_params*, *Cloning*, *Rolling your own estimator*. Todas as citações verbatim da §2.1 e do critério 6.1.
9. `https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/metadata_routing.rst` — definição de metadata; `set_{method}_request`; os quatro estados `True`/`False`/`None`/alias; a mensagem de erro; o estatuto experimental e a flag `enable_metadata_routing`.
10. `https://raw.githubusercontent.com/scikit-learn/enhancement_proposals/main/slep006/proposal.rst` — SLEP006 (Accepted): motivação, vocabulário consumer/router, "nothing is requested by default", "all metadata requested in the core library are sample aligned", `X`/`y` nunca roteados.
11. `https://raw.githubusercontent.com/py-why/EconML/main/README.md` — `est.fit(Y, T, X=X, W=W)` e o comentário que nomeia os papéis; ausência de qualquer menção a "assumption"/"unconfoundedness" no README.
12. `https://raw.githubusercontent.com/bashtage/linearmodels/main/linearmodels/iv/model.py` (docstring de `IV2SLS`) e `.../main/README.md` — os quatro papéis nomeados; a sintaxe `[endog ~ instruments]`; ausência de modelos de seleção na lista de capacidades.
13. `https://raw.githubusercontent.com/uber/causalml/master/README.md` — "without strong assumptions on the model form" (única menção a premissas).
14. `https://raw.githubusercontent.com/ShichenXie/scorecardpy/master/scorecardpy/__init__.py` — lista de exports; ausência de reject inference/take-up.
15. `https://raw.githubusercontent.com/ShichenXie/scorecard/master/NAMESPACE` — 21 exports; ausência de reject inference/take-up.
16. `https://raw.githubusercontent.com/amphibian-dev/toad/master/toad/__init__.py` — exports; ausência de reject inference/take-up.
17. `https://raw.githubusercontent.com/cran/creditmodel/master/NAMESPACE` — 181 exports; grep por `reject|accept|take.?up` = zero.
18. `https://raw.githubusercontent.com/cran/Rprofet/master/NAMESPACE` — `exportPattern("^[[:alpha:]]+")`; não determinável por NAMESPACE.
19. `https://raw.githubusercontent.com/guillermo-navas-palencia/optbinning/master/optbinning/scorecard/scorecard.py` — docstring e assinatura de `class Scorecard`; métodos `fit`/`predict`/`predict_proba`/`score`. Também `.../master/README.rst` (grep: apenas `Counterfactual`, nada de acceptance).
20. `https://raw.githubusercontent.com/adimajo/scoringTools/master/NAMESPACE` — exports: `augmentation`, `fuzzy_augmentation`, `parcelling`, `reclassification`, `twins`, `generate_data`.
21. `https://raw.githubusercontent.com/adimajo/scoringTools/master/man/reject_infered-class.Rd` — os quatro slots da classe S4, incluindo `acceptance_model` "The acceptance model (if estimated by the given method)".
22. `https://raw.githubusercontent.com/adimajo/scoringTools/master/R/parcelling.R` — assinatura com `probs`/`alpha`; a nota MNAR e "coefficients must be chosen a priori"; `acceptance_model = as.logical(NA)`.
23. `https://raw.githubusercontent.com/adimajo/scoringTools/master/R/augmentation.R` — nota MAR; `acceptance_model = as.logical(NA)` (linha 70).
24. `https://raw.githubusercontent.com/adimajo/scoringTools/master/R/twins.R` — "no theoretical foundation"; `model_acc` ajustado sobre o indicador `acc`; `acceptance_model = model_acc` (linha 54); a união `glmORlogicalORspeedglm`.
25. `https://raw.githubusercontent.com/adimajo/scoringTools/master/R/reclassification.R` — "no theoretical foundation […] one-step CEM"; argumento `thresh`; `acceptance_model = as.logical(NA)` (linha 49).
26. `https://raw.githubusercontent.com/cran/sampleSelection/master/man/selection.Rd` — assinatura completa de `selection()`; "formula, the selection equation" / "the outcome equation(s)"; sufixos `s`/`o`.
27. `https://raw.githubusercontent.com/statsmodels/statsmodels/main/statsmodels/api.py` e `.../main/docs/source/regression.rst` — grep por `heckman|selection` = zero em ambos.
28. `https://raw.githubusercontent.com/cran/survival/master/man/Surv.Rd` — assinatura de `Surv()`; documentação de `event` e `type`; a regra de resolução do default; "the event indicator can be omitted, in which case all subjects are assumed to have an event".
29. `https://raw.githubusercontent.com/sebp/scikit-survival/master/sksurv/util.py` — `class Surv`, `Surv.from_arrays(event, time, …)` e sua docstring; `check_y_survival(..., allow_all_censored=False, allow_time_zero=True, competing_risks=False)`.
30. `https://raw.githubusercontent.com/CamDavidsonPilon/lifelines/master/lifelines/fitters/kaplan_meier_fitter.py` — assinatura e docstring de `fit()` ("Defaults all True if event_observed==None") e de `fit_interval_censoring()`.
31. `https://raw.githubusercontent.com/cran/survival/master/vignettes/survival.Rnw` — as quatro ocorrências de censura informativa/não-informativa em ~3.800 linhas; passagens das linhas 1144–1150 e 3635–3639.
32. `https://raw.githubusercontent.com/ModelOriented/ingredients/master/R/ceteris_paribus.R` — roxygen de `ceteris_paribus()`; "What-If Profiles"; classe de retorno `ceteris_paribus_explainer`.
33. `https://raw.githubusercontent.com/ModelOriented/DALEX/master/python/dalex/dalex/predict_explanations/_ceteris_paribus/object.py` — `class CeterisParibus(Explanation)`, parâmetros e atributos; nota apontando para o capítulo EMA.
34. `https://raw.githubusercontent.com/ModelOriented/DALEX/master/python/dalex/dalex/_explainer/object.py` — assinatura de `Explainer.predict_profile(..., type=('ceteris_paribus',), ...)` e `type : {'ceteris_paribus', TODO: 'oscilations'}`.
35. `https://raw.githubusercontent.com/vincentarelbundock/marginaleffects/main/r/R/datagrid.R` — roxygen de `datagrid()`: `grid_type` e seus quatro valores; os oito `FUN_*`; "held at their mean or mode"; o aviso sobre variáveis de agrupamento hierárquico; a costura por `newdata=`.
36. `https://raw.githubusercontent.com/vincentarelbundock/marginaleffects/main/README.md` — o pacote é R e Python; referência ao livro *Model to Meaning* (2026).
37. `https://raw.githubusercontent.com/py-why/dowhy/main/dowhy/causal_identifier/auto_identifier.py` — dicionários `sym_assumptions` e as chaves literais `"Unconfoundedness"`, `"As-if-random"`, `"Exclusion"`, `"Full-mediation"`, `"First-stage-unconfoundedness"`, `"Second-stage-unconfoundedness"`.
38. `https://raw.githubusercontent.com/py-why/dowhy/main/dowhy/causal_identifier/identified_estimand.py` — `class IdentifiedEstimand` e seus campos; a linha de formatação "Estimand assumption {0}, {1}: {2}".
39. `https://raw.githubusercontent.com/py-why/dowhy/main/README.rst` — os quatro passos model/identify/estimate/refute; "you can inspect the untested assumptions"; "refutation and falsification API that can test causal assumptions".
40. `https://raw.githubusercontent.com/py-why/dowhy/main/docs/source/user_guide/intro.rst` — por que validação preditiva não serve; definição de *refutation*; refutações em dois estágios.
41. `https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/partial_dependence.rst` — a premissa de independência enunciada duas vezes; "we will create absurd data points"; vocabulário de marginalização; a nota sobre `brute` vs `recursion`.

#### Fontes buscadas e não obtidas

- Capítulo *Ceteris-paribus Profiles* de *Explanatory Model Analysis* (`pbiecek/ema`): 404 nos
  nomes de arquivo tentados. Citado apenas como referência que `ingredients` e `dalex` fazem.
- Capítulos intermediários de `tidymodels/model-implementation-principles`: 404 nos nomes
  tentados (só `index`, `01-general-conventions` e `03-model-object` recuperados).
- Buitinck et al., *API design for machine learning software* (arXiv): domínio bloqueado.
- `scikit-survival` `doc/user_guide/understanding_predictions.ipynb`: 404 no caminho tentado;
  usei `doc/user_guide/00-introduction.ipynb`, que discute censura mas não a premissa de
  independência (grep = zero).
- Não fiz varredura exaustiva do PyPI atrás de implementações Python de reject inference além
  de `scorecardpy`, `optbinning` e `toad`; a ausência registrada na §3.1 vale para esses três.


---

# Parte II — Medição no código

## Endereço do vetor `contract` — medição no código (insumo do #155)

> **Insumo de decisão, não decisão.** Este documento mede o código de hoje e localiza, com
> `arquivo:linha`, o que cada lado do fork custa. **Nenhum veredito** — o endereço do estágio
> de vetor `contract` é decisão do #155. Se você achar uma recomendação neste texto, é um
> defeito: reporte no #155.
>
> **Método herdado do #134 e do #143:** onde a medição mostra que os dois lados **não
> empatam**, este documento diz isso e mostra o número. Simetria fabricada não é neutralidade.
> Onde não foi possível medir, está escrito que não foi medido.

**Critérios já estabelecidos, citados e não re-derivados:**

- `docs/research/module-boundaries.md` (`origin/release/v0.6`) — deep modules do Ousterhout,
  vazamento de informação, classitis, e a medição *"a interface efetiva é o estado inteiro"*
  (os 13 campos de `policy.py:21-33`, todos lidos de fora, ~77 pontos em 8 arquivos).
- `docs/research/functional-core.md` (`origin/release/v0.6`) — núcleo funcional / casca
  imperativa; §1.1 mede **zero** ocorrências de `seed` nos seis módulos do núcleo.
- `docs/research/architecture-critique.md` (`origin/release/v0.6`) — as 13 patologias.

**Estado do código medido:** `src/pycreditools` é v0.5 e é byte-idêntico em `main`,
`release/v0.5` e `release/v0.6`. Toda arquitetura v0.6 citada aqui está **decidida e não
implementada**; onde este documento diz "hoje", é o código; onde diz "decidido", é o issue.

---

### A. O que o estágio de take-up é hoje

#### A.1 Anatomia completa do `RateStage`

Classe em `stages.py:264`; construtor em `stages.py:286-294`. **Seis** parâmetros:

| campo | linha da atribuição | o que faz | despacho decidido |
|---|---|---|---|
| `name` | `stages.py:316` (via `Stage.__init__`, `:32`) | rótulo do estágio | vira **label**, opcional com default estrutural — mas **obrigatório** para `.rate` escalar, "o caso em que a estrutura não nomeia" (#129, ratificado no #145 §2) |
| `base_rate` | `stages.py:317` | probabilidade escalar de passar | **sobrevive**, é a única coisa que sobra: *"Resta uma probabilidade, escalar ou nó da AST"* (#129) |
| `variable` | `stages.py:329`/`:331`/`:333` | multiplicador por linha (coluna, `Expression`, callable ou número) | **colapsa** em `base_rate`: *"`variable: str \| float \| Expression \| callable` são a mesma coisa escrita de quatro jeitos"* (#129); o callable já morreu no #120 |
| `calibrate` | `stages.py:318` | embrulha `variable` em `CalibratedExpression` (`stages.py:327-329`) | **morre** — calibração é a `Parcelling`, chega pelo `ctx` (#129); e `.calibrated()` morre na v0.6 (#145 §3, ruling do dono) |
| `observed_col` | `stages.py:319` | coluna 0/1 do desfecho observado | **morre** — *"take-up lê `hired` do schema, não nomeia coluna nenhuma"* (#121 §4; #129) |
| `calibrate_by` | `stages.py:324`, validado em `:320-323` (só `None` ou `"score"`) | como estimar a taxa do swap-in | **morre** — sai do estágio para a `Parcelling` (#117 → #129) |

**Verificação pedida pelo card:** `observed_col`, `calibrate` e `calibrate_by` **ainda estão
no código de hoje** — `stages.py:292`, `:291`, `:293` no construtor; `stages.py:318-324` nas
atribuições; `stages.py:489-491` no `to_dict`; `stages.py:84-90` no `from_dict`;
`policy.py:115-116` e `:124-126` no builder `.rate`. A saída deles é **decisão registrada
(#117 → #129), não código**. Contagem de usos vivos que passam esses argumentos: **4** na
masterclass (`examples/tutorial_masterclass.ipynb:406`, `:594`, `:794`, `:863`), todos
idênticos (`base_rate=1.0, observed_col="hired", calibrate_by="score"`), mais
`validation/measure_v05.py:40` e `:45`.

**Dois métodos privados** repartem o cálculo:

- `_variable_probs` (`stages.py:335-368`) — caminho `base_rate × variable`.
- `_observed_probs` (`stages.py:370-427`) — caminho `observed_col`, que é onde mora o
  acoplamento medido na §B.

`apply` (`stages.py:429-472`) faz três coisas: escolhe o caminho (`:431-434`), aplica o
**bypass de keep-in** (`:443-451`) e sorteia no modo estocástico (`:453-470`).

#### A.2 Onde o vetor `contract` é produzido e consumido

**Produzido** em um lugar só: `simulation.py:446` (estocástico) e `:450` (analítico),
`df["new_approval"]`, a partir do produto acumulado `pass_prob_funnel`
(`simulation.py:419`, `:434`). A `CONTEXT.md:39-41` chama `new_approval` de *"the **contract
weight**, a float in `[0, 1]`"* — o vetor `contract` do #116 é este.

Depois de produzido, é **reescrito** para os keep-ins em `simulation.py:378-381`
(`_apply_keep_in_hire_weight`, ADR 0011): keep-in `new_approval := approved_pre_rate ×
current_hired_col`. Ou seja, para o keep-in o take-up **não vem do estágio** — vem da coluna
observada, lida pelo motor (`simulation.py:366-381`).

**Consumido** (contagem sobre `src/pycreditools`, 106 ocorrências de
`new_approval`/`approved_pre_rate` em 7 arquivos):

| arquivo | linhas | papel |
|---|---|---|
| `simulation.py` | `:446`, `:450` (produção); `:378` (reescrita keep-in); `:589` (máscara de desfecho no modo standalone); `:296`, `:306-307` (coluna `hired`/`defaulted` da tabela de decisão) | motor |
| `sweep.py` | `:106` (peso contratado), `:120` (zera quem não tem desfecho), `:124` (máscara do ponto de grade), `:129` (denominador), `:103` (fallback quando não há `RateStage`) | métrica ADR 0008 |
| `performance.py` | `:70`, `:72`, `:80`, `:91`, `:104-108`, `:157-170`, `:359-368`, `:478-489`, `:513`, `:552-553`, `:612-629` | tabelas de leitura |
| `visualization.py` | `:103` (`approval_col: str = "new_approval"` como default de argumento) | gráfico |
| `analysis.py` | nenhuma leitura direta — delega a `sweep.run_sweep` (`analysis.py:98-106`) | — |
| `deployment.py` | **nenhuma** ocorrência de `new_approval` | — |
| `stages.py` | **nenhuma** ocorrência de `new_approval`, `approved_pre_rate`, `pass_prob_*` ou `stage_*` | — |

O zero em `deployment.py` é o fato que a emenda do #120 (via #139 §10) já transformou em
regra escrita: *"Um estágio que alimenta o vetor `contract` não entra na unidade de deploy."*
O que existe hoje em `deployment.py` é o oposto parcial: `to_production_rules` **inclui** o
`RateStage` a menos que `clean=True` (`deployment.py:235-252`), e o `from_dict` o reconstrói
como `type == "rate_conversion"` (`deployment.py:80-95`) — com **3 dos 6 campos**
(`name`, `base_rate`, `variable`), perdendo `calibrate`, `observed_col` e `calibrate_by`.

#### A.3 Posição no funil — o mecanismo, medido

**O que um estágio vê do que veio antes dele.** O laço é `simulation.py:425-439`:

```
:427   stage_output_col = f"stage_{i}_{stage.name}"
:431   stage_res = stage.apply(df, method=method.value, policy=policy)
:434   df["pass_prob_funnel"] = df["pass_prob_funnel"] * stage_res
:435   df[stage_output_col] = df["pass_prob_funnel"]
:438   if not isinstance(stage, RateStage):
:439       df["pass_prob_pre_rate"] = df["pass_prob_pre_rate"] * stage_res
```

O `df` passado a `apply` (`:431`) é o **mesmo objeto mutado a cada volta**, então um estágio
na posição *i* **pode** ler `pass_prob_funnel` e as colunas `stage_0_…` até `stage_{i-1}_…`.

**Nenhum estágio lê.** Medido: `grep` por `pass_prob`, `stage_`, `new_approval`,
`approved_pre_rate` e `scenario` em `stages.py` devolve **zero** ocorrências. Os três tipos de
estágio leem só colunas da base e, no caso do `RateStage`, campos de `policy`.

**Consequência medida — hoje a posição não muda o que o estágio calcula:**

1. `pass_prob_funnel` é **produto** (`:434`). Produto é comutativo: mover o `RateStage` na
   lista não altera `new_approval`.
2. `approved_pre_rate` é acumulado por **teste de tipo**, não por posição — `if not
   isinstance(stage, RateStage)` (`:438`). Um `RateStage` na primeira posição e outro na
   última produzem o mesmo `approved_pre_rate`.
3. `new_approval` estocástico é `df[stage_approval_cols].fillna(0).min(axis=1)` (`:446`) —
   mínimo sobre colunas cumulativas monotônicas, logo o valor é o da última, também
   invariante à ordem.
4. A **única** coisa que a posição muda é a atribuição de motivo: `first_failed_col`
   (`simulation.py:489`) usa `failed_df.idxmax(axis=1)`, que devolve a **primeira** coluna
   verdadeira na ordem de `stage_cols` (`:480`) — e essa lista já exclui os `RateStage`
   (`:475`). Ou seja: a posição do estágio de take-up não muda nem o motivo.

**O mecanismo de partição é o `isinstance`, e ele está em 9 lugares:**
`simulation.py:79`, `:229`, `:341`, `:438`, `:475`, `:552`; `visualization.py:413`;
`deployment.py:235`; `sweep.py:173`. O #129 conta **5** deles como "a partição `RateStage`
vs resto" (`simulation.py:79,229,438,475,552`); os outros 4 são despacho de serialização,
render e varredura.

**O preço nomeado de mover — o que é decisão, não código.** O #121 §3 decidiu que *"elegibilidade
é posição no funil, não máscara declarada"*, matando `policy.current_approval_col` de
`stages.py:388`; e o #121 §1 decidiu que *"morre `isinstance(stage, RateStage)` em
`simulation.py:438` como mecanismo de partição"* — o funil passa a se partir por **vetor
declarado**. O #139 §10 nomeia o custo de mover: *"o #121 fixou que elegibilidade é posição
no funil, e o objeto de premissa não tem posição."*

**Medição honesta do preço:** a posição no funil que o #121 tornou semântica **não existe no
código de hoje** — hoje ela é inerte (itens 1–4 acima). O custo de mover o take-up é o custo
de **uma capacidade decidida e ainda não escrita**, não o de um comportamento existente. Este
documento não julga se isso torna o preço maior ou menor; registra que ele não é medível no
código de hoje, só no texto do #121.

#### A.4 O `contract` é terminal, ou é insumo de regra a jusante?

**As duas respostas existem, em caminhos diferentes do mesmo motor.**

**No fluxo de swap (`current_approval_col` declarado) — o `contract` NÃO alimenta regra
nenhuma:**

- `_classify_scenarios` é chamado com `"approved_pre_rate"`, não com `new_approval`
  (`simulation.py:471`), e classifica em `simulation.py:509-531`.
- Logo a população swap-in que recebe imputação de PD (`simulation.py:619`,
  `_estimate_swap_in_baseline_pd` em `:674`) é definida **antes** do take-up.
- O keep-in recebe `actual_default` intocado (`simulation.py:626-628`).
- Depois disso, `new_approval` só aparece como **peso** em métricas (`sweep.py:106`,
  `:120`, `:129`; `performance.py:80`, `:168`, `:489`).

**No fluxo standalone (`current_approval_col is None`, `simulation.py:466-468`) — o
`contract` alimenta DUAS regras:**

1. `approved_mask = df["new_approval"] > 0` (`simulation.py:589`) gateia quem recebe
   desfecho.
2. **A saída do estágio de take-up vira a PD.** `simulation.py:552-556`:

```python
rate_stages = [s for s in policy.stages if isinstance(s, RateStage)]
if rate_stages:
    last_rate_stage = rate_stages[-1]
    sim_pd = last_rate_stage.apply(df, method="analytical", policy=policy).astype(float)
    use_stochastic_draw = True
```

O **último** `RateStage` da lista é aplicado uma segunda vez, fora do laço do funil, e seu
resultado é lido como probabilidade de **calote**. Aqui a posição na lista importa
(`rate_stages[-1]`), e o vetor `contract` é insumo direto do vetor `outcome`.

Este é também o **segundo dos dois únicos chamadores** de `stage.apply()` no pacote — o outro
é o laço do funil (`simulation.py:431`). O #129 mediu exatamente isso: *"`stage.apply()` tem
dois chamadores… contra 20 `isinstance`."*

---

### B. Acoplamento, contado nos dois sentidos

Método do `module-boundaries.md`: **interface efetiva = o que é lido de fora do módulo dono.**

#### B.1 Se `.take_up` FICA na `CreditPolicy` — o que a política tem que saber que não é regra

Leituras de `policy.` dentro de `stages.py`, fora de docstring: **10** (as de `:310` e `:311`
são docstring). Repartidas por dono:

| campo lido | linhas | quem lê | é regra? | despacho decidido |
|---|---|---|---|---|
| `current_approval_col` | `stages.py:383`, `:444`, `:445` | `RateStage` | **não** — papel de schema | `DataSchema.approved` (#119) |
| `calibration_bins` | `stages.py:407` | `RateStage` | **não** — config de premissa | `Parcelling.bins` (#117) |
| `calibration_score_col` | `stages.py:169` | resolver, chamado de `:343` e `:404` | **não** | morre sem substituto (#117) |
| `score_cols` | `stages.py:180`, `:181` | resolver | **não** | morre inteiro (#118) |
| `stages` | `stages.py:172`, `:199` | resolver | **é a regra, lida por um irmão** | um passo consultando a lista de passos irmãos — o vazamento nomeado no `module-boundaries.md` §Q11 |

**Contagem:** 7 leituras não-docstring de 5 campos. **Zero delas são regra** no sentido do
#119 (`stages` é regra, mas está sendo lido *por* um estágio, o que é o vazamento, não o uso).

**Contra-medição obrigatória, no mesmo sentido:** `CutoffStage.apply` (`stages.py:128-147`) e
`FilterStage.apply` (`stages.py:223-244`) recebem `policy` e **não o leem nenhuma vez**. A
assinatura `apply(df, method, policy)` (`stages.py:33`) carrega a dependência para **3 tipos
por causa de 1**.

**E a contra-medição que muda o número:** todas as 7 leituras acima estão **decididas para
sair do estágio** (#117 → #129). Depois delas, o que resta no `.take_up` é, por #139 §10:
*"uma probabilidade, um vetor declarado e uma posição no funil"* — e a probabilidade é regra
tanto quanto o limiar de um `.filter`. **Sob a v0.6 decidida, a contagem de "coisa que não é
regra dentro do `CreditPolicy` por causa do take-up" cai de 5 campos para 1 item: o próprio
vetor declarado `contract`.**

#### B.2 Se `.take_up` SAI para a premissa — o que a premissa passa a ter que saber

Cada item mede uma coisa que hoje o `RateStage` tem **porque é `Stage`**, e que o
`Parcelling`/`External` não tem:

| o que a premissa passa a precisar | onde isso vive hoje | medição |
|---|---|---|
| **Posição no funil** | `simulation.py:425-439` (o laço) | o objeto de premissa não tem posição (#139 §10). Hoje a posição é inerte (§A.3), mas o #121 §3 já a tornou o mecanismo de elegibilidade. Nenhuma linha de código a implementa ainda. |
| **A AST** | `expressions.py` (`Expression`, `BinaryExpr`, `ColumnExpr`) | `.rate` passa a receber *"uma probabilidade, escalar ou nó da AST"* (#129). Hoje `RateStage.variable` já aceita `Expression` (`stages.py:290`, avaliada em `:340-350`); `Parcelling` não tem campo de expressão em decisão nenhuma. |
| **O protocolo de `Stage`** | `stages.py:29-52` (ABC hoje); Protocol de 2 membros na v0.6 (#129) | a premissa teria que expor `apply(df, ctx) -> Series` **e** o vetor declarado — ou o motor teria que ganhar um segundo mecanismo de execução para o take-up. Não há decisão fechada sobre qual. |
| **O mecanismo de sorteio** | `stages.py:458`, `:469` (hoje); `ctx` na v0.6 (#129: *"o `ctx` é estreito: semente do estudo e posição de linha (#127)"*) | ver §C — o sorteio **não** precisa mudar de casa, mas o `ctx` só é entregue no laço do funil (`simulation.py:431`). |

**O que a `CreditPolicy` deixa de precisar saber:** medido em campos de `policy.py:21-33`,
**zero** — os 5 campos que o take-up lê já foram despachados para fora da política pelo #117 e
#119, independentemente deste card. O que a política deixa de carregar é **um verbo e um valor
de vetor**, não um campo.

**Os dois lados não empatam, e o número é este:** de um lado, 1 item (o vetor `contract`
dentro de um tipo que o #119 declarou ser *"`stages` e nada mais"*); do outro, 3 itens
estruturais que a premissa passa a precisar (posição, AST, protocolo) mais uma pergunta em
aberto sobre o `ctx`.

#### B.3 `CreditPolicy` = `stages` e nada mais (#119) — o que sobra em `stages`

**Tipos de estágio hoje:** 3 classes — `CutoffStage` (`stages.py:117`), `FilterStage`
(`stages.py:208`), `RateStage` (`stages.py:264`).

**Mapeados pelos renames decididos:**

| hoje | v0.6 decidida | fonte | vetor declarado |
|---|---|---|---|
| `CutoffStage` | **morre** — vira `.filter` sobre a AST | #129 (*"`.cutoff` morre; `.filter` sobre a AST é o verbo único"*) | `decision` |
| `FilterStage` | `.filter(expr)` | #129 | `decision` |
| — (não existe hoje) | `.filter(expr, draw=True)` — a mesa | #145 §3 (forma B decidida) | `decision` |
| `RateStage` | `.take_up` | #152 (nome), #155 (endereço em aberto) | `contract` |

**A mesa não é um tipo novo:** é o mesmo verbo `.filter` com uma flag (#145 §3). Logo a
contagem correta é por **verbo** e por **vetor declarado**, não por classe.

| cenário | verbos em `stages` | vetores declarados em `stages` |
|---|---|---|
| `.take_up` FICA | **2** (`.filter`, `.take_up`) | **2** (`decision`, `contract`) |
| `.take_up` SAI | **1** (`.filter`) | **1** (`decision`) |

**Consequência contada, e ela é assimétrica:** o #129 decidiu que *"o `Stage` ABC morre; fica
um Protocol de **dois** membros — `apply(df, ctx) -> Series` e o vetor declarado (`decision` |
`contract`)"*. Se o take-up sai, o segundo membro passa a ter **um único habitante possível**
— um membro de protocolo que não distingue nada. O Protocol de dois membros vira, na prática,
de um.

E o mecanismo que o #121 §1 instalou no lugar do `isinstance` — *"o funil se parte por vetor
declarado"* — passa a não ter o que partir **dentro** da política: a partição migra para a
fronteira entre `CreditPolicy` e a premissa. Os 5 sítios de `isinstance(stage, RateStage)`
que o #121 mata (`simulation.py:79`, `:229`, `:438`, `:475`, `:552`) precisariam de um
mecanismo novo, não do mecanismo já decidido.

**Uma lista `stages` de um verbo só ainda é um tipo?** Isto é a pergunta do card e não é
respondida aqui. O que está medido é: 1 verbo, 1 vetor, e um membro de Protocol sem
informação.

#### B.4 Tamanho de interface e a razão do Ousterhout

Contagem de **conceitos que o usuário aprende** em cada lado, sobre as decisões fechadas. A
razão do Ousterhout é benefício ÷ custo de aprender; aqui está só o denominador, contado.

**Lado "fica" (arquitetura decidida hoje):**

- `CreditPolicy`: 2 verbos (`.filter`, `.take_up`), 1 flag (`draw=`), 1 argumento de
  identidade (`label=`). Protocol de 2 membros.
- `Parcelling`: 3 campos — `bins` (#117), `inflation` (#117), população do baseline
  (#139 §2). `External`: 1 campo (a coluna 0/1, #117).
- Total de conceitos de superfície: **2 verbos + 4 campos de premissa**.

**Lado "sai":**

- `CreditPolicy`: 1 verbo (`.filter`), 1 flag, 1 `label=`. Protocol degenerado (§B.3).
- Premissa: os 4 campos acima **mais** o que a §B.2 enumera — uma probabilidade (escalar ou
  nó da AST), um lugar de funil, e a mecânica de aterrissar no vetor `contract`.
- Total: **1 verbo + 4 campos + ≥3 conceitos novos na premissa**.

**Onde os dois lados não se equilibram, e o número:** o lado "sai" tira **1** conceito da
política e põe **≥3** na premissa. O lado "fica" mantém 1 conceito (o vetor `contract`)
dentro de um tipo cuja definição fechada (#119) é *"as regras, e só elas"*.

**O que NÃO foi possível medir:** a razão do Ousterhout precisa do **numerador** (benefício da
interface), e nenhum dos dois lados tem benefício medido — não há usuário observado escrevendo
a superfície v0.6, porque ela não existe em código. Os únicos números de superfície do mapa
são de protótipo (#117: S0 16 linhas/1 conceito, S1 15/2, S2 18/7, S3 17/5) e o próprio #120
declarou que *"a medição antiga não vale mais"*. **Não meça a razão a partir deste documento.**

---

### C. O eixo do sorteio

#### C.1 Onde o sorteio mora hoje — contado e localizado

`np.random` em `src/pycreditools`, **11 ocorrências, 3 arquivos**:

| arquivo:linha | forma | o que sorteia | lado |
|---|---|---|---|
| `stages.py:458` | `np.random.random(swap_ins_mask.sum())` | contratação do swap-in, com máscara de keep-in ativa | **estágio** |
| `stages.py:469` | `np.random.random(len(df))` | contratação, sem política / sem coluna de aprovação | **estágio** |
| `simulation.py:604` | `np.random.random(not_na_mask.sum())` | desfecho no modo standalone | **motor** |
| `simulation.py:664` | `np.random.random(len(swap_ins))` | desfecho do swap-in no fluxo de swap | **motor** |
| `sample_data.py:60`, `:89`, `:117`, `:149`, `:160`, `:212`, `:263` | `np.random.Generator` / `default_rng(seed)` | geração de base sintética | **fora do caminho de simulação** |

**Contagem do que importa:** 4 sorteios no caminho de simulação — **2 no lado do estágio, 2 no
lado do motor**. Os quatro usam `np.random.random`, estado global de módulo, **sem semente** —
confirma `docs/research/functional-core.md` §1.1 (zero ocorrências de `seed` em
`simulation.py`, `sweep.py`, `stages.py`, `optimization.py`, `policy.py`, `performance.py`).

O aninhamento medido no `functional-core.md` §1.2 é exatamente entre estes dois lados: o
sorteio de desfecho (`simulation.py:604`/`:664`) consome uma quantidade de números que depende
de quantos o sorteio de contratação (`stages.py:458`) puxou.

#### C.2 Se o take-up sai, o sorteio tem que ir junto?

**Medido, e a resposta é: não — porque o mecanismo decidido já não mora no estágio.**

- O #144 decidiu **sorteio por linha chaveado a (semente do estudo, posição da linha na base
  ligada, nome do sorteio)**, resolvido junto com o #127.
- O #129 decidiu onde ele chega: *"O `ctx` é **estreito**: semente do estudo e posição de
  linha (#127), e a `Parcelling` quando o estágio a admite — nunca a política."*
- Logo, sob a v0.6, o estágio **recebe** o mecanismo; não o possui. Hoje ele o possui, e é
  isso que as linhas `stages.py:458` e `:469` medem.

**O que muda de fato se o take-up sair:** o portador do `ctx` hoje é o laço do funil —
`stage.apply(df, method=method.value, policy=policy)` (`simulation.py:431`), o único ponto
onde o motor entrega contexto a um estágio dentro da sequência. Um objeto de premissa não
está nesse laço. Não há decisão fechada sobre como um `Parcelling` receberia semente e
posição de linha; o #129 só define o `ctx` para estágios.

**Fato que o card precisa e que a medição isola:** *probabilístico* deixou de ser sinônimo de
*take-up* na v0.6. A mesa é `.filter(expr, draw=True)` (#145 §3) e alimenta `decision`
(#121 §8); o #121 §6 decidiu ainda que **o estágio de decisão probabilístico sorteia também
no caminho analítico**, para manter `decision` 0/1 duro. Ou seja: depois da v0.6 existe
sorteio dos **dois** lados da partição de vetor, e *"o take-up é o estágio que sorteia"*
deixa de ser uma diferença entre ele e os demais. Hoje é: `stages.py:458`/`:469` são o único
sorteio de estágio no pacote.

---

### D. A invariância, localizada no código

#### D.1 Onde a probabilidade de take-up é mantida constante enquanto o corte se move

**Caminho rápido (`sweep.py:280-309`) — a constância é literal, é um vetor congelado.**

```
sweep.py:285   baseline = _without_cutoff_entries(policy, set(cutoff_grid))
sweep.py:286   sim = baseline.simulate(data, method=method)     # UMA simulação
sweep.py:296   for combo in grid:                                # cada ponto = uma máscara
sweep.py:304       app_rate, def_rate = _metrics(sim_df, actual_defaults, mask.astype(float))
```

Dentro de `_metrics`, o vetor de take-up entra como `contracted_w = ... sim_df["new_approval"]`
(`sweep.py:106`) e a máscara do ponto só multiplica esse peso (`sweep.py:124`). **O valor por
linha de `new_approval` é calculado uma vez e não é recalculado em ponto nenhum da grade.**

A justificativa está escrita no contrato do módulo, `sweep.py:20-26`: *"Fast path vs
re-simulation is a performance boundary, never a semantic one… valid because a cutoff is a
pure mask over a fixed per-row baseline."*

**Caminho de re-simulação (`sweep.py:311-317`) — a constância é estrutural, e é mais forte do
que a do caminho rápido.**

Cada ponto reconstrói a política (`_policy_for_combo`, `sweep.py:142-188`) e re-simula
(`sweep.py:207`). Mesmo assim, a população que ensina a taxa de take-up **não se move**:

```
stages.py:383   approval_col = policy.current_approval_col
stages.py:388   keep_ins_mask = df[approval_col] == 1        # coluna OBSERVADA
stages.py:445   keep_ins_mask = df[policy.current_approval_col] == 1
```

`_policy_for_combo` só mexe em `CutoffStage` (`sweep.py:152-162`), em `stress_scenarios`
(`:164-167`) e em `RateStage.base_rate` (`:169-186`). Nenhum deles toca
`current_approval_col`. **Logo o corte pode andar por toda a grade e a máscara de keep-in que
alimenta o take-up é a mesma em todos os pontos.**

#### D.2 Existe caminho onde o take-up varia com a fronteira de decisão?

**Pelo valor do corte: não.** Nenhuma das 4 leituras do take-up (`stages.py:383`, `:388`,
`:444`, `:445`) depende de `new_approval`, de `approved_pre_rate` ou de `scenario` — e
`stages.py` não menciona nenhuma dessas colunas (§A.3).

**Por qual coluna é varrida: sim, e é sutil.** `resolve_calibration_score_col`
(`stages.py:158-186`), chamada pelo take-up em `stages.py:404`, resolve a lente pegando *a
última coluna de `CutoffStage` presente no df* (`stages.py:171-178`, com
`for sc in reversed(cutoff_cols)`). E `_policy_for_combo` **acrescenta ao fim da lista** o
estágio de corte do ponto de grade (`sweep.py:153-162`, `stages_list.append(...)`). Portanto,
no caminho de re-simulação a lente de bins do take-up passa a ser **a coluna varrida**. No
caminho rápido acontece o inverso: `_without_cutoff_entries` (`sweep.py:62-78`) **remove** as
entradas varridas antes de simular (`sweep.py:285`), então a lente cai para outra coluna de
corte, ou para `score_cols` (`stages.py:180-184`).

Consequência medida: **os dois caminhos do mesmo `run_sweep` podem resolver lentes diferentes
para o take-up.** Isto não é variação com o *valor* do corte — é variação com *qual dimensão a
grade varre*. É a mesma "confusão de eixo por desenho" que o #117 registrou em 2026-08-14
(*"o primeiro fallback da cascata assume que a coluna de corte é a lente"*), aqui na sua
manifestação de varredura. A cascata inteira está decidida para morrer sem substituto (#117).

**Pela dimensão `base_rates`: sim, mas é outro eixo.** `run_sweep(base_rates=...)`
(`sweep.py:222`, `:263`) e `TradeoffAnalyzer.vary_base_rate` (`analysis.py:41-43`) varrem a
taxa declarada. Não é o corte se movendo. E aqui existe um defeito medido: a reconstrução em
`sweep.py:174-179` passa **4 dos 6 campos** do `RateStage`, derrubando `observed_col` e
`calibrate_by` para os defaults — o #133 mediu **2,27 p.p. absolutos** de deriva na
inadimplência ao varrer um `base_rate` que a política declara irrelevante.

#### D.3 O contraste com a regra de imputação de PD — a assimetria, medida

**Duas máscaras de "keep-in", em dois arquivos, com duas definições diferentes:**

| eixo | máscara | linha | move com o corte? |
|---|---|---|---|
| **contrato** (take-up) | `df[policy.current_approval_col] == 1` | `stages.py:388`, `:445` | **não** — coluna observada, fixa |
| **desfecho** (PD imputada) | `df["scenario"] == Quadrant.KEEP_IN.value` | `simulation.py:685` (e `:625`) | **sim** |

A cadeia que faz a segunda se mover é curta e inteira mensurável:

```
simulation.py:438-439   approved_pre_rate = produto dos estágios NÃO-RateStage
simulation.py:448/:452  approved_pre_rate materializado
simulation.py:471       _classify_scenarios(df, policy, "approved_pre_rate")
simulation.py:512-519   new_flag = (approved_pre_rate > 0)  → KEEP_IN = old & new
simulation.py:685       keep_ins_mask = scenario == KEEP_IN
simulation.py:735-737   keep_in_scores / keep_in_defaults / global_pd saem dessa máscara
simulation.py:751-758   calibrate_by_score_bins(cal_scores=..., cal_values=...)
```

O corte varrido entra em `approved_pre_rate` porque `_policy_for_combo` o acrescenta como
`CutoffStage` (`sweep.py:155-161`) e todo `CutoffStage` é não-`RateStage` (`simulation.py:438`).
**A régua de PD recalibra a cada ponto de grade no caminho de re-simulação; a de take-up
não.**

No **caminho rápido**, as duas ficam congeladas juntas — a única simulação (`sweep.py:286`)
fixa `simulated_default` e `new_approval` por linha, e o ponto de grade só mascara. É este
congelamento que o #140 registrou como defeito de exatidão da inadimplência, e que o #124
decidiu **consertar recalibrando por ponto**, com teto de custo ≤1,25×; o #149 mediu o
conserto em **+18 a +20%**.

**As duas decisões que dão o outro lado da assimetria:**

- **#139 §2** — duas populações possíveis para o baseline, e o knob mora **dentro do
  `Parcelling`**: o *default* é o livro contratado do incumbente, **invariante ao challenger**
  (a exatidão da grade sai de graça); o valor `keep_in` **recalibra por ponto**, e *"os +18 a
  +20% do #149 são o preço de quem escolhe"*.
- **#139 §4** — a escolha de população vale para **os dois chutes** (contrato e desfecho), uma
  escolha só. E a assimetria que este documento acaba de medir no código está lá registrada em
  palavras: *"a **pré-condição de observabilidade difere por eixo**. No desfecho é `outcome`
  presente — daí o buraco de suporte. No contrato, take-up é observado para **todo aprovado**,
  então ali não há buraco."*
- **#142** — a régua de imputação é **global**: bordas *e* taxas medidas uma vez sobre a base
  inteira; daí a regra *"`by=` é argumento de leitura, não de modelagem"* e *"nunca picote a
  base"*. Hoje o código faz o contrário quando o usuário fatia: a §6 da masterclass chama a
  varredura sobre a fatia de cada região e portanto **calibra uma régua por região** (o #142
  registra os cinco cortes nominais 752/785/732/694/680 do `validation/README.md` como o
  número que muda).

**A assimetria, dita como medição:** hoje, no código, a régua do eixo **desfecho** é função da
fronteira de decisão em um dos dois caminhos de varredura (`simulation.py:685` ← `:471` ←
`:438`), e a do eixo **contrato** não é em nenhum (`stages.py:388` lê coluna fixa). As
decisões de v0.6 (#139 §2 e §4) fundem os dois eixos sob **uma** escolha de população
declarada no `Parcelling` — ou seja, **a premissa já é dona da população que estima o
take-up**, mesmo com o estágio ficando onde está. O que continua sem nome em lugar nenhum é a
**invariância declarada da probabilidade de take-up sob movimento do corte** — nenhum campo,
nenhum argumento e nenhum número de saída a nomeia; a medição acima é toda ela sobre
mecanismo, não sobre declaração.

**Não foi medido:** o efeito numérico de recalibrar o take-up por ponto de grade. Ele exigiria
construir o caminho, que não existe — mesma situação que o #139 §8 classificou como *"mede uma
mudança que ainda não existe"*.

---

### E. Raio de explosão, contado

Uma linha por decisão: **o que exatamente a mudança de endereço emendaria.** Sem juízo sobre
se a emenda é aceitável.

| # | o que a decisão fixou | o que a mudança de endereço emenda |
|---|---|---|
| **#117** | A partição em 4 tipos e as amarras legadas ao #129: *"o estágio declara **qual eixo** estima; **como** estimar é do `Parcelling`, nunca do estágio"* | emenda a frase-amarra: o eixo de contrato deixaria de ser **declarado por um estágio** e passaria a ser declarado pelo próprio membro de premissa — a linha "estágio declara o quê / premissa declara o como" perde um dos seus dois lados. |
| **#119** | `CreditPolicy` = `stages` e nada mais; a tabela de despacho dos 13 campos, com `stages` marcado *"fica — é a política"* | emenda a extensão de `stages`: de 2 verbos / 2 vetores para 1 verbo / 1 vetor (§B.3), e obriga uma linha nova dizendo que a premissa carrega um passo executável — hoje nenhum membro de premissa executa. |
| **#120** | Duas unidades de serialização (deploy = `stages` + régua de rating; estudo = schema + política + premissa + `method`/`seed`), **já emendado em 2026-09-05** com *"um estágio que alimenta o vetor `contract` não entra na unidade de deploy"* | a emenda de 05/09 vira **desnecessária e teria que ser revogada**: se o take-up não é `stage`, a regra de exclusão não tem sobre o que incidir; a unidade de deploy volta a ser "todos os `stages`" sem exceção escrita. |
| **#121** | *"Elegibilidade é posição no funil, não máscara declarada"* (§3), matando `policy.current_approval_col` de `stages.py:388`; e *"determinismo e vetor são dois eixos"* (§1), matando `isinstance(stage, RateStage)` como partição | emenda o §3: o take-up sai do funil, logo sua elegibilidade volta a precisar de máscara declarada — exatamente o `current_approval_col` que o §3 matou; e emenda o §1, porque o vetor `contract` deixa de ser um valor possível do "vetor declarado" de um estágio. |
| **#129** | `.cutoff` morre; `.filter` sobre a AST é o verbo único; `.rate` colapsa de 5 argumentos para 1; `Stage` ABC → **Protocol de dois membros** (`apply(df, ctx)` + vetor declarado) | emenda o Protocol: o segundo membro fica com um único habitante (§B.3); emenda o colapso do `.rate`, que deixa de ser um verbo de política; e emenda a lista de `isinstance` a matar — os 5 sítios de partição `RateStage` (`simulation.py:79,229,438,475,552`) precisariam de outro mecanismo, não do "vetor declarado". |
| **#145** | Verbo da mesa = `.filter(expr, draw=True)` (forma B), escolhida por ser *"a única candidata que separa os dois eixos **mantendo dois verbos**"*; `.calibrated()` morre; `ranges=` chaveado por label com erro duro sobre estágio composto | emenda a justificativa da forma B: com o take-up fora, sobra **um** verbo, e o critério "mantendo dois verbos" que descartou `.review` e `.rate(to=…)` perde a premissa — a comparação entre as quatro formas teria que ser refeita. |
| **#152** | A família de verbos, com trava explícita de não reabrir *"a partição de tipos (#117), … a premissa fora da política (#119)"*; o fluxo renderizado inclui `.rate("take_up", …)` na cadeia de `CreditPolicy` | o ADR da família nasceria com emenda pendente: a cadeia de `CreditPolicy` perde um verbo e o `Parcelling` ganha um argumento — e o card, cujo escopo declarado é *"não mexeremos em arquitetura"*, passa a depender de uma decisão de arquitetura tomada depois dele. |

**Sétima entrada, não pedida pelo card mas medida:** o #139 §10 é o texto que *"não mexer na
estrutura; escrever a regra que falta"* produziu, e ele é o registro do ruling de 2026-09-05
que a reabertura contradiz. Ele não precisa de emenda técnica — precisa de ser marcado como
superado, ou o repositório passa a ter duas resoluções em conflito para a mesma pergunta.

---

### Método e limites

**O que foi medido, e como.**

- Anatomia e leituras: leitura direta de `src/pycreditools/stages.py` (492 linhas),
  `simulation.py` (820), `sweep.py` (317), `policy.py` (311), `deployment.py` (473),
  `analysis.py` (111), `expressions.py` (282). Todas as linhas citadas são do
  *working tree* em `/home/user/pycreditools`, idêntico a `main` e a `origin/release/v0.6` em
  `src/`.
- Contagens de leitura de campo: `grep -rn "\.<campo>\b"` sobre `src/pycreditools`, excluindo
  `policy.py` (o módulo dono). Os números de módulo do núcleo estão na §B.1; a contagem
  incluindo `gui/` e `studio/` é maior (ex.: `current_approval_col` 26, `score_cols` 36,
  `stages` 32, `current_hired_col` 12) e **não** é a mesma base de contagem da tabela do
  `module-boundaries.md` §Q1 — não compare os dois números diretamente.
- Sorteios: `grep -rn "np\.random" src/pycreditools` — 11 ocorrências, 3 arquivos, tabuladas
  na §C.1.
- `isinstance` sobre `RateStage`: `grep -rn "isinstance(.*RateStage"` — 9 sítios, listados na
  §A.3.
- Issues lidos por `mcp__github__issue_read` (`get` + `get_comments`) em
  `matheuspasche/pycreditools`: #155, #117, #119, #120, #121, #129, #139, #142, #144, #145,
  #152.

**O que NÃO foi possível medir, e está declarado como tal.**

1. **O preço da posição no funil.** A semântica que o #121 §3 dá à posição (*elegibilidade*)
   **não existe em código**. No código de hoje a posição do estágio de take-up é inerte
   (§A.3, itens 1–4). O custo de mover só é legível no texto do #121, não em um comportamento
   que se possa executar.
2. **A razão do Ousterhout.** Contei o denominador (conceitos a aprender, §B.4); o numerador
   (benefício) não é medível sem superfície escrita, e a medição antiga de superfície foi
   invalidada pelo próprio #120.
3. **O número da recalibração do take-up por ponto.** Exigiria construir um caminho que não
   existe. Mesma classe da entrada de dívida do #139 §8.
4. **Como um `Parcelling`/`External` receberia semente e posição de linha.** O #129 define o
   `ctx` só para estágios; nenhum card fechado diz o que acontece se um membro de premissa
   precisar dele. Registrado como buraco, não como custo.
5. **Take-up sob `External`.** O #139 §2 diz que *"`External` não tem baseline"* e que por
   isso a população é inexprimível ali. Se o take-up virasse premissa, o que `External`
   declararia sobre contratação não está decidido em card nenhum e não foi possível deduzir do
   código.

**Onde os dois lados não empatam, repetido para não se perder:**

- §B.2/§B.4 — o lado "sai" tira **1** conceito da política e põe **≥3** na premissa.
- §B.3 — o Protocol de dois membros do #129 fica com um membro de habitante único.
- §D.3 — a régua do eixo **desfecho** é função da fronteira de decisão (`simulation.py:685` ←
  `:471` ← `:438`); a do eixo **contrato** não é em caminho nenhum (`stages.py:388`). As
  decisões #139 §2/§4 já fundem os dois sob uma escolha declarada no `Parcelling`.
- §E — das 7 decisões, **#120 é a única que a mudança de endereço não emenda e sim revoga**
  (a emenda de 05/09 perderia objeto).
