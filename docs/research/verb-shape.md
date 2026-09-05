# Forma de verbo em pacotes de dados (R e Python)

Levantamento da **ergonomia da superfície pública** — como pacotes escolhem nomes de
verbos, ordenam e nomeiam argumentos, distribuem funcionalidade entre método encadeado
e função livre, anunciam a família ao usuário, imprimem seus objetos no REPL e oferecem
atalhos para construções de N passos.

**Sem veredito.** O documento registra fatos, padrões observados e trade-offs declarados
pelas próprias fontes. Onde as fontes discordam, a discordância é mostrada, não resolvida.

Data do levantamento: 2026-09-05.

---

## 0. Nota de método e limitações de rede

O ambiente desta sessão usa um proxy de egresso que **bloqueou os sites de documentação
publicada** de quase todas as referências pedidas. Domínios confirmadamente bloqueados
(erro `EGRESS_BLOCKED` do proxy):

- `design.tidyverse.org`
- `scikit-learn.org`
- `pola.rs` (e `docs.pola.rs`)
- `pandas.pydata.org`
- `arxiv.org`, `ar5iv.labs.arxiv.org`, `export.arxiv.org`
- `jmlr.org`

O que **funcionou** foi `raw.githubusercontent.com` e `git clone` sobre HTTPS. Por isso,
todas as afirmações abaixo são sustentadas pelo **código-fonte e pelas fontes dos
documentos oficiais nos repositórios canônicos dos próprios projetos** — que são a fonte
primária de onde os sites publicados são gerados. Onde existe uma URL publicada
correspondente, ela é citada em seguida, marcada como *(não alcançada nesta sessão)*.

**Fonte não consultada (declarado explicitamente, não preenchido de memória):**
o paper *"API design for machine learning software: experiences from the scikit-learn
project"*, Buitinck et al., arXiv:1309.0238 — <https://arxiv.org/abs/1309.0238>. O
domínio arXiv e todos os espelhos testados estão bloqueados pelo proxy. **Nada neste
documento é atribuído a esse paper.** O que consta sobre o protocolo Estimator/Pipeline
vem da documentação de desenvolvedor e do código do scikit-learn, citados nominalmente.

Commits lidos (HEAD no momento do levantamento):
`dplyr d5e94e7` · `tidyr 26f83e8` · `ggplot2 0ac300f` · `recipes b92024e` ·
`parsnip fb808ad` · `workflows 961443b` · `siuba 815f55b` · `plotnine 1f5ee9f` ·
`polars dd1ea07` · `tidymodels/model-implementation-principles 31e38aa`.

---

## 1. Nomeação e simetria dentro de uma família

### 1.1 Regras explícitas: o tidyverse design guide

O capítulo *Function names* declara as regras de nomeação de verbos do tidyverse
(fonte: <https://raw.githubusercontent.com/tidyverse/design/main/function-names.qmd>;
publicado em <https://design.tidyverse.org/function-names.html> — *não alcançada*):

> "In general, prefer verbs. Use imperative mood: `mutate()` not `mutated()`,
> `mutates()`, or `mutating()`; `do()` not `did()`, `does()`, `doing()`, `hide()` not
> `hid()`, `hides()`, or `hiding()`."

A exceção declarada é justamente o caso de construção incremental de objeto:

> "Exception: noun-y interfaces where you're building up a complex object like ggplot2
> or recipes (verb-y interface in ggvis was a mistake)."

Sobre agrupar funções numa família, o mesmo capítulo:

> "Use prefixes to group functions together based on common input or common purpose.
> **Prefixes are better than suffixes because of auto-complete.** Examples: ggplot2,
> purrr. Counter example: shiny."
>
> "Use suffixes for variations on a theme (e.g. `map_int()`, `map_lgl()`, `map_dbl()`;
> `str_locate()`, `str_locate_all()`.)"
>
> "Strive for thematic unity in related functions. Can you make related functions rhyme?
> Or have the same number of letters? Or similar background (i.e. all Germanic origins
> vs. French)."

E sobre comprimento:

> "Err on the side of too long rather than too short (reading is generally more important
> than writing). (…) Length of name should be inversely proportional to frequency of usage.
> Reserve very short words for functions that are likely to be used very frequently."

O guia registra também um limite auto-declarado do prefixo de pacote: *"Not sure about
common prefixes for a package. Works well for stringr (esp. with stringi), forcats, xml2,
and rvest. But there's only a limited number of short prefixes and I think it would break
down if every package did it."* (mesma fonte).

O capítulo *Unifying principles* fixa o valor que as regras servem — consistência acima
de performance — e reconhece o custo:

> "Valuing consistency is a trade-off, and we explicitly value it over performance."
> (<https://raw.githubusercontent.com/tidyverse/design/main/unifying.qmd>;
> <https://design.tidyverse.org/unifying.html> — *não alcançada*)

O mesmo capítulo cita o Zen of Python (*"There should be one — and preferably only one —
obvious way to do it"*) como princípio adotado, e admite que ggplot2 (`+`) e httr (`...`)
são exceções internas ao princípio de compor com um único operador: *"These are not bad
techniques in isolation, and they are well suited to the domains in which they are used,
but the disadvantages of inconsistency outweigh any local advantages."*

### 1.2 Regras explícitas: tidymodels

O `model-implementation-principles` (livro de princípios do tidymodels;
<https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/06-arguments.Rmd>)
repete a regra de prefixo, ligada explicitamente a **tab-complete**:

> "Design similar functions using a common prefix so that users can easily tab complete
> in the IDE when searching."

E dá o exemplo de sufixo-por-contexto no capítulo de notas
(<https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/08-notes.Rmd>):

> "For example, the tune package has `control` arguments for different functions. The
> functions that generate the appropriate lists are named with suffixes that indicate
> where they are used: `control_grid()`, `control_bayes()`, `control_resamples()`, and so on."

Note a **discordância parcial** com o design guide do tidyverse, que no capítulo
*Reduce argument clutter with an options object* apresenta os pares de base R
`loess()`/`loess.control()`, `glm()`/`glm.control()` — sufixo `.control` — lado a lado
com os do tune (`control_grid()` — prefixo `control_`), sem escolher entre as duas formas
(<https://raw.githubusercontent.com/tidyverse/design/main/argument-clutter.qmd>).

### 1.3 Casos em que a simetria quebrou, com a fala dos autores

**`gather()`/`spread()` → `pivot_longer()`/`pivot_wider()` (tidyr).**
A vinheta oficial `pivot` é explícita sobre o motivo ser o *nome*:

> "For some time, it's been obvious that there is something fundamentally wrong with the
> design of `spread()` and `gather()`. **Many people don't find the names intuitive and
> find it hard to remember which direction corresponds to spreading and which to
> gathering.** It also seems surprisingly hard to remember the arguments to these
> functions, meaning that many people (including me!) have to consult the documentation
> every time."
> (<https://raw.githubusercontent.com/tidyverse/tidyr/main/vignettes/pivot.Rmd>)

O NEWS do tidyr 1.0.0 registra que a simetria era um objetivo declarado do redesenho
(*"and are symmetric (#453)"*) e lista os defeitos concretos que só puderam ser corrigidos
com nomes novos (<https://raw.githubusercontent.com/tidyverse/tidyr/main/NEWS.md>).

O design guide explica por que a troca de nome foi o único caminho:

> "Generally, it is not possible to change the order of the first few arguments because it
> will break existing code (…) This means that the only real solution is to deprecate the
> entire function and replace it with a new one. Because this is invasive to the user, it's
> best to do sparingly: if the mistake is minor, you're better off waiting until you've
> collected other problems before fixing it. For example, take `tidyr::gather()`. (…)
> Because it wasn't possible to easily fix this mistake, **we accumulated other `gather()`
> problems for several years before fixing them all at once in `pivot_longer()`**."
> (<https://raw.githubusercontent.com/tidyverse/design/main/important-args-first.qmd>)

**`top_n()`, `sample_n()`, `sample_frac()` → família `slice_*()` (dplyr 1.0.0).**
O NEWS descreve a conversão de verbos avulsos numa família com prefixo comum:

> "`slice()` gains a new set of helpers: `slice_head()` and `slice_tail()` (…);
> `slice_sample()` randomly selects rows, **taking over from `sample_frac()` and
> `sample_n()`**; `slice_min()` and `slice_max()` select the rows with the minimum or
> maximum values of a variable, **taking over from the confusing `top_n()`**."
> (<https://raw.githubusercontent.com/tidyverse/dplyr/main/NEWS.md>, seção `# dplyr 1.0.0`)

**`_if()`/`_at()`/`_all()` → `across()` (dplyr 1.0.0).** É o caso mais documentado de
sufixo abandonado. A vinheta `colwise` lista as razões, incluindo a explosão combinatória
da superfície:

> "`across()` reduces the number of functions that dplyr needs to provide. This makes dplyr
> easier for you to use (because there are fewer functions to remember) and easier for us to
> implement new verbs (**since we only need to implement one function, not four**)."
>
> "`across()` doesn't need to use `vars()`. The `_at()` functions are the only place in dplyr
> where you have to manually quote variable names, which makes them a little weird and hence
> harder to remember."
>
> "It's disappointing that we didn't discover `across()` earlier, and instead worked through
> several false starts (first not realising that it was a common problem, then with the
> `_each()` functions, and most recently with the `_if()`/`_at()`/`_all()` functions)."
> (<https://raw.githubusercontent.com/tidyverse/dplyr/main/vignettes/colwise.Rmd>)

O custo declarado do abandono: nada é removido. *"these functions (…) are now superseded.
That means that they'll stay around, but won't receive any new features and will only get
critical bug fixes."* (mesma fonte). O vocabulário formal está em
<https://raw.githubusercontent.com/r-lib/lifecycle/main/vignettes/stages.Rmd>:

> "A softer alternative to deprecation is superseded. A superseded function has a known
> better alternative, but the function itself is not going away. (…) In some ways a
> superseded function is actually safer than a stable function because **it's guaranteed
> never to change**."

**`cur_data()`/`cur_data_all()` → `pick()` (dplyr 1.1.0)**, com o motivo declarado sendo o
nome: *"We feel that `pick()` is a much more evocative name when you are just trying to
select a subset of columns from your data (#6204)."* (dplyr NEWS).

**`case_match()` → `recode_values()`/`replace_values()` (dplyr 1.2.0)** — o caso mais
recente e o mais direto sobre nomes:

> "`case_match()` is soft-deprecated, and is fully replaced by `recode_values()` and
> `replace_values()`, which are more flexible, more powerful, and **have much better names**."
> (dplyr NEWS, seção `# dplyr 1.2.0`)

Note que `recode()` havia sido *superseded em favor de `case_match()`* em dplyr 1.1.0
(*"`recode()` is superseded in favour of `case_match()` (#6433)"*, mesma fonte) — ou seja,
a mesma área da API trocou de nome duas vezes em direções opostas, e a documentação do
`recode()` superseded foi reescrita para apontar para os novos nomes (*"The superseded
`recode()` now has updated documentation showing how to migrate to `recode_values()` and
`replace_values()`"*).

**`juice()` vs `bake()` (recipes 0.1.14)** — dois verbos irmãos colapsados num só por
confusão de nome:

> "**To reduce confusion between `bake()` and `juice()`**, the latter is superseded in favor
> of using `bake(object, new_data = NULL)`. The `new_data` argument now has no default, so a
> `NULL` value must be explicitly used in order to emulate the results of `juice()`.
> `juice()` will remain in the package (and used internally) but most communication and
> training will use `bake(object, new_data = NULL)`. (#543)"
> (<https://raw.githubusercontent.com/tidymodels/recipes/main/NEWS.md>)

**Steps de imputação do recipes: sufixo → prefixo (recipes 0.1.16).**

> "Changed the names of all imputation steps, for example, from `step_knnimpute()` or
> `step_medianimpute()` (old) to `step_impute_knn()` or `step_impute_median()` (new) (#614)."
> (recipes NEWS)

Isto é a regra "prefixos agrupam, sufixos variam" aplicada retroativamente: `step_impute_*`
passa a ser um sub-prefixo, e o índice de referência do pacote passa a poder listá-lo por
`starts_with("step_impute_")` (ver §4).

**`groupby` → `group_by` e `apply` → `map_*` (polars 0.19).** O guia de upgrade oficial é
explícito sobre a regra e sobre o peso da quebra:

> "Creating a consistent and intuitive API is hard; finding the right name for each function,
> method, and parameter might be the hardest part."
>
> "**`groupby` renamed to `group_by`** — This is not a change we make lightly, as it will
> impact almost all our users. But 'group by' is really two different words, and **our naming
> strategy dictates that these should be separated by an underscore**."
>
> "**`apply` renamed to `map_*`** — `apply` is probably the most misused part of our API. Many
> Polars users come from pandas, where `apply` has a completely different meaning. We now
> consolidate all our functionality for user-defined functions under the name `map`."
> com a tabela `Expr.apply → map_elements`, `DataFrame.apply → map_rows`,
> `GroupBy.apply → map_groups`, `map → map_batches`.
> (<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/releases/upgrade/0.19.md>)

Aqui a família é construída por **prefixo comum `map_` + sufixo que diz a unidade de
aplicação** (`_elements`, `_rows`, `_groups`, `_batches`) — exatamente o padrão
"prefixo agrupa, sufixo varia" do design guide do tidyverse, chegado de forma independente.

A política de quebra do polars declara o trade-off:

> "We don't always get it right on the first try. (…) Freeing ourselves of past indiscretions
> is important to keep Polars moving forward. We know it takes time and energy for our users
> to keep up with new releases but, in the end, it benefits everyone for Polars to be the best
> product possible."
> (<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/development/versioning.md>)

**Contraste declarado com o tidyverse:** o polars remove funções depreciadas em major
releases (*"A deprecated function or method is removed"* é listado como breaking change,
mesma fonte), enquanto o tidyverse mantém funções superseded indefinidamente. As duas
fontes discordam sobre o que fazer com um nome ruim depois de substituí-lo.

### 1.4 Famílias por papel, não por prefixo léxico: scikit-learn

O scikit-learn não usa prefixo de nome; a família é definida por **quais métodos o objeto
implementa**, e os papéis têm nomes próprios na documentação de desenvolvedor
(<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/developers/develop.rst>;
publicado em <https://scikit-learn.org/stable/developers/develop.html> — *não alcançada*):

| Papel | Método que o define |
|---|---|
| Estimator | `estimator.fit(data, targets)` ou `estimator.fit(data)` |
| Predictor | `predictor.predict(data)`; opcionalmente `decision_function` / `predict_proba` |
| Transformer | `transformer.transform(data)`; `fit_transform` quando compensa |
| Model | `model.score(data)` ("higher is better") |

> "The API has one predominant object: the estimator. (…) All estimators implement the fit
> method." (mesma fonte)

Os nomes compostos são formados por **composição de verbos** (`fit_transform`,
`fit_predict`), não por prefixo/sufixo temático.

---

## 2. Ordem e nomeação de argumentos

### 2.1 Onde o "dado" vai

**Regra tidyverse** (<https://raw.githubusercontent.com/tidyverse/design/main/important-args-first.qmd>):

> "In a function call, the most important arguments should come first. (…)
> - If the output is a transformation of an input (e.g. `log()`, `stringr::str_replace()`,
>   `dplyr::left_join()`) then that argument [is] the most important.
> - Other arguments that determine the type or shape of the output are typically very important.
> - Optional arguments (i.e. arguments with a default) are the least important, and should come last."
>
> "When the output is very strongly tied to an input, putting that argument first also ensures
> that **your function works well with the pipe**, leading to code that focuses on the
> transformations rather than the object being transformed."

O mesmo capítulo lista os próprios erros do autor e os casos em que a simetria foi
deliberadamente quebrada:

- base R string functions (`grepl()`, `gsub()`) põem `pattern` antes de `x` — considerado errado;
- `lm(formula, data)` — `data` deveria vir primeiro, mas *"the designers of `lm()` wanted `data`
  to be optional (…) Because `formula` is required and `data` is not, this means that `formula`
  had to come first"*;
- `ggplot(data, mapping)` **vs** `geom_point(mapping, data)`:

> "Both data and mapping are required for every plot, so why make `data` first? I picked this
> ordering because in most plots there's one dataset shared across all layers and only the
> mapping changes. On the other hand, the layer functions, like `geom_point()`, flip the order
> of these arguments because in an individual layer you're more likely to specify `mapping`
> than `data` (…). **This makes the argument order inconsistent with `ggplot()`, but overall
> supports the most common use cases.**"

Confirmado no código: `ggplot <- function(data = NULL, mapping = aes(), ..., environment = parent.frame())`
(<https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/plot.R>) e, para as camadas, a
ordem fixa das formais é gerada mecanicamente (ver §2.3).

E o próprio ggplot2 é apresentado como caso onde o argumento mais importante *não aparece*:

> "ggplot2 functions work by creating an object that is then added on to a plot, so **the plot,
> which is really the most important argument, is not obvious at all**. ggplot2 works this way
> in part because it was written before the pipe was discovered."

**dplyr**: o dado é sempre o 1º argumento, com nome `.data`
(<https://raw.githubusercontent.com/tidyverse/dplyr/main/R/mutate.R>,
`.../R/filter.R`, `.../R/summarise.R`, `.../R/arrange.R`, `.../R/select.R`):

```r
mutate     <- function(.data, ...)
mutate.data.frame <- function(.data, ..., .by = NULL,
                              .keep = c("all","used","unused","none"),
                              .before = NULL, .after = NULL)
filter     <- function(.data, ..., .by = NULL, .preserve = FALSE)
filter_out <- function(.data, ..., .by = NULL, .preserve = FALSE)   # novo em dplyr 1.2.0
summarise  <- function(.data, ..., .by = NULL, .groups = NULL)
arrange    <- function(.data, ..., .by_group = FALSE)
select     <- function(.data, ...)
```

**siuba** (Python) reproduz a mesma escolha — dado primeiro — e resolve o problema de colisão
com `**kwargs` com um prefixo de dois underscores em vez do ponto do R:

```python
@singledispatch2((pd.DataFrame, DataFrameGroupBy))
def group_by(__data, *args, add = False, **kwargs):
```
(<https://raw.githubusercontent.com/machow/siuba/main/siuba/dply/verbs.py>)

**tidymodels inverte**: o objeto que caminha pelo pipe é a *especificação*, não o dado:

```r
fit.model_spec    <- function(object, formula, data, case_weights = NULL,
                              control = control_parsnip(), ...)
fit_xy.model_spec <- function(object, x, y, case_weights = NULL,
                              control = control_parsnip(), ...)
```
(<https://raw.githubusercontent.com/tidymodels/parsnip/main/R/fit.R>)

E no recipes, o objeto-receita é o 1º argumento de todo `step_*()`, com o dado entrando só em
`prep()`/`bake()` (ver §2.3).

**plotnine faz o oposto de fixar a ordem**: aceita `data` e `mapping` em qualquer ordem,
resolvendo por tipo em tempo de execução.

```python
def __init__(self, data: Optional[DataLike] = None, mapping: Optional[aes] = None):
    # Allow some sloppiness
    data, mapping = order_as_data_mapping(data, mapping)
```
com o helper documentado como *"Reorder args to ensure (data, mapping) order. This function allow
the user to pass mapping and data to ggplot and geom in any order."*
(<https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/ggplot.py>,
<https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/_utils/__init__.py>)

Isto neutraliza, no port Python, exatamente a inconsistência que o design guide do tidyverse
registra como custo aceito entre `ggplot()` e `geom_*()` (acima).

**scikit-learn** proíbe explicitamente o dado no construtor:

> "[The `__init__` method] should not, however, take the actual training data as an argument,
> as this is left to the `fit()` method::
> `clf3 = SGDClassifier([[1, 2], [2, 3]], [-1, 1]) # WRONG!`"
> (`doc/developers/develop.rst`)

O dado vai em `fit(X, y)`; e há uma regra de posicionamento forçada por composição:

> "even unsupervised estimators need to accept a `y=None` keyword argument **in the second
> position** that is just ignored by the estimator. For the same reason, `fit_predict`,
> `fit_transform`, `score` and `partial_fit` methods need to accept a `y` argument in the
> second place if they are implemented." (mesma fonte)

### 2.2 O que é posicional e o que é obrigatoriamente palavra-chave

**R — `...` como barreira.** O capítulo *Put `…` after required arguments*
(<https://raw.githubusercontent.com/tidyverse/design/main/dots-after-required.qmd>;
<https://design.tidyverse.org/dots-after-required.html> — *não alcançada*):

> "If you use `…` in a function, put it after the required arguments and before the optional
> arguments. This has two positive impacts:
> - It **forces the user of your function to fully name optional arguments**, because arguments
>   that come after `...` are never matched by position or by partial name. (…)
> - This in turn means that you can easily add new optional arguments or change the order of
>   existing arguments without affecting existing code."

O contra-exemplo é `mean(x, trim, na.rm, ...)`, que permite `mean(x, , TRUE)` e
`mean(x, n = TRUE, t = 0.1)`: *"Not only does this allow for confusing code, it also makes it
hard to later change the order of these arguments."* O remédio proposto é `rlang::check_dots_used()`.

Isto é o análogo funcional do `*` do Python: em R, `...` é a barreira *e* o coletor.

O tidymodels repete a regra (`06-arguments.Rmd`):

> "When defining the order of arguments in a function, try to keep the `...` as far to the left
> as possible to **coerce users to explicitly name all arguments to the right of `...`**."

**Regra complementar do lado de quem chama** — *Name all but the most important arguments*
(<https://raw.githubusercontent.com/tidyverse/design/main/call-data-details.qmd>):

> "When calling a function, you should name all but the most important arguments."
> "Never use partial matching (…) most R editing environments support autocomplete so partial
> matching only saves you a single keystroke, and it makes code substantially harder to read."
> "I don't think that most people will remember more than the one or two most important arguments,
> so you should name the rest."

Exceções declaradas: ensino (nomear tudo ao apresentar a função pela primeira vez) e o caso em
que o 1º argumento é muito longo — daí `writeLines(con = "test.txt", c(...))` e
`expect_snapshot(error = TRUE, { ... })`, em que as opções curtas vêm *antes* do argumento longo.

**Python — `*` e `*args`.** polars usa as três formas:

```python
def select(self, *exprs: IntoExpr | Iterable[IntoExpr], **named_exprs: IntoExpr) -> DataFrame
def with_columns(self, *exprs: IntoExpr | Iterable[IntoExpr], **named_exprs: IntoExpr) -> DataFrame
def filter(self, *predicates: ..., **constraints: Any) -> DataFrame
def group_by(self, *by: IntoExpr | Iterable[IntoExpr], maintain_order: bool = False,
             **named_by: IntoExpr) -> GroupBy
def sort(self, by: IntoExpr | Iterable[IntoExpr], *more_by: IntoExpr,
         descending=False, nulls_last=False, multithreaded=True, maintain_order=False)
def join(self, other: DataFrame, on=None, how: JoinStrategy = "inner", *,
         left_on=None, right_on=None, suffix: str = "_right", validate="m:m", ...)
```
(<https://raw.githubusercontent.com/pola-rs/polars/main/py-polars/src/polars/dataframe/frame.py>)

Padrões observáveis: (a) `*exprs` variádico posicional para "as colunas/expressões", com
`**named_exprs` fazendo o *aliasing* (`df.select(bmi=bmi_expr)`); (b) opções sempre
keyword-only por virem depois do variádico; (c) uma assimetria interna — `group_by(*by)` é
puramente variádico, enquanto `sort(by, *more_by)` exige o primeiro por nome/posição própria;
(d) `join()` usa o `*` nu para forçar keyword a partir de `left_on`, mas deixa `other, on, how`
posicionais.

**scikit-learn** normativiza o construtor
(`doc/developers/develop.rst`):

> "Ideally, the arguments accepted by `__init__` should all be keyword arguments with a default
> value. In other words, a user should be able to instantiate an estimator without passing any
> arguments to it."
>
> "In addition, **every keyword argument accepted by `__init__` should correspond to an
> attribute on the instance**. Scikit-learn relies on this to find the relevant attributes to
> set on an estimator when doing model selection."
>
> "There should be no logic, not even input validation, and the parameters should not be
> changed (…) The reason for postponing the validation is that if `__init__` includes input
> validation, then the same validation would have to be performed in `set_params`, which is
> used in algorithms like `GridSearchCV`."

E a divisão entre `__init__` e `fit` é declarada como regra de *onde* o argumento mora:

> "any parameter that can have a value assigned prior to having access to the data should be an
> `__init__` keyword argument. Ideally, **fit parameters should be restricted to directly data
> dependent variables**. For instance a Gram matrix or an affinity matrix (…) are data dependent.
> A tolerance stopping criterion `tol` is not directly data dependent."

Convenção de nome de atributo: `coef_` (aprendido, público), `_intermediate_coefs` (interno).
*"attributes (…) estimated or learned from the data must always have a name ending with trailing
underscore"* (mesma fonte).

### 2.3 Nomes de argumento reaproveitados entre verbos de uma família

**tidyr — prefixos `names_*` / `values_*` compartilhados pelo par pivot:**

```r
pivot_longer(data, cols, ..., cols_vary = "fastest",
             names_to = "name", names_prefix = NULL, names_sep = NULL,
             names_pattern = NULL, names_ptypes = NULL, names_transform = NULL,
             names_repair = "check_unique",
             values_to = "value", values_drop_na = FALSE,
             values_ptypes = NULL, values_transform = NULL)

pivot_wider(data, ..., id_cols = NULL, id_expand = FALSE,
            names_from = name, names_prefix = "", names_sep = "_", names_glue = NULL,
            names_sort = FALSE, names_vary = "fastest", names_expand = FALSE,
            names_repair = "check_unique",
            values_from = value, values_fill = NULL, values_fn = NULL, unused_fn = NULL)
```
(<https://raw.githubusercontent.com/tidyverse/tidyr/main/R/pivot-long.R>,
`.../R/pivot-wide.R`)

O sufixo direcional (`_to` vs `_from`) carrega o sentido da operação, e o resto do nome é
idêntico entre os dois verbos. **Assimetria observada no par declarado simétrico:**
`pivot_longer()` tem um 2º argumento posicional obrigatório (`cols`), enquanto `pivot_wider()`
não tem nenhum argumento posicional além de `data` — tudo vem depois de `...` e precisa ser
nomeado.

**recipes — toda a família `step_*()` tem a mesma forma:**

```r
step_center(recipe, ..., role = NA, trained = FALSE, means = NULL,
            na_rm = TRUE, skip = FALSE, id = rand_id("center"))
```
(<https://raw.githubusercontent.com/tidymodels/recipes/main/R/center.R>)

Isto é: `recipe` primeiro (compatível com pipe), `...` recebendo a seleção tidyselect de
colunas, e então um conjunto fixo de argumentos keyword-only comuns a todos os steps
(`role`, `trained`, `skip`, `id`), com os parâmetros específicos do step no meio.

Os verbos que consomem a receita, porém, **não compartilham o nome do 1º argumento**:
`prep.step_center(x, training, info = NULL, ...)` e
`bake.step_center(object, new_data, ...)` (mesma fonte). O recipes também renomeou
`newdata` → `new_data` em toda a superfície (*"`bake`, `juice` and other functions has
`newdata` changed to `new_data`"*, recipes NEWS), e `new_data` é um dos nomes padronizados
do tidymodels (`06-arguments.Rmd`: *"`new_data`: data to be predicted"*).

**ggplot2 — as formais das camadas são geradas mecanicamente**, o que torna a simetria
verificável por código:

```r
fixed_fmls_names <- c("mapping", "data", "stat", "position", "...",
                      "na.rm", "show.legend", "inherit.aes")
# ...
fmls <- pairlist2(
  mapping  = args$mapping,
  data     = args$data,
  stat     = args$stat %||% "identity",
  position = args$position %||% "identity",
  `...` = missing_arg(),
  !!!args[extra_args],
  na.rm    = args$na.rm %||% FALSE,
  show.legend = args$show.legend %||% NA,
  inherit.aes = args$inherit.aes %||% TRUE
)
```
(<https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/make-constructor.R>)

Ou seja: todo `geom_*()` tem exatamente `mapping, data, stat, position, ..., <específicos>,
na.rm, show.legend, inherit.aes` — com `...` no meio, exatamente como manda o capítulo
*dots after required*.

**tidymodels — vocabulário fechado de nomes de argumento.** O capítulo `06-arguments.Rmd`
publica uma lista normativa: `na_rm`, `new_data`, `weights`, `x`/`y` (métodos `.data.frame`),
`formula`/`data` (métodos `.formula`), `times`, `direction`, `level`, `link`, e um dicionário
de hiperparâmetros (`mtry`, `trees`, `min_n`, `penalty`, `mixture`, `learn_rate`,
`tree_depth`, `neighbors`, `num_comp`, `epochs`, `hidden_units`, `sample_size`, …) e
`fn`/`fns` para funções. O README do parsnip declara o objetivo:

> "Harmonize argument names (e.g. `n.trees`, `ntrees`, `trees`) so that users only need to
> remember a single name. **This will help across model types too** so that `trees` will be
> the same argument across random forest as well as boosting or bagging."
> (<https://raw.githubusercontent.com/tidymodels/parsnip/main/README.md>)

O NEWS do parsnip mostra a regra sendo aplicada retroativamente: *"`regularization` was changed
to `penalty` in a few models to be consistent with [standardized-argument-names]"*
(parsnip 0.0.0.9003).

### 2.4 Prefixo no nome do argumento como proteção contra `...`

O capítulo *Dot prefix* (<https://raw.githubusercontent.com/tidyverse/design/main/dots-prefix.qmd>):

> "When using `...` to create a data structure, or when passing `...` to a user-supplied
> function, add a `.` prefix to all named arguments. This reduces (but does not eliminate) the
> chances of matching an argument at the wrong level."

O capítulo apresenta as alternativas de base R (maiúsculas na família `apply`; nome não
sintático em `transform()`) e escolhe o ponto: *"I think a dot prefix is better because it's
easier to type"*; sobre `transform()`: *"Using a non-syntactic variable name (…) increases
friction when writing the function. In my opinion, this trade-off is not worth it."* E aponta
uma falha da própria dplyr: *"Ooops: `args(dplyr::left_join)`" —* isto é, `left_join(x, y, by, ...)`
não usa prefixo.

O tidymodels repete: *"If there is a possibility of argument name conflicts (…) it is strongly
suggested that the argument names to the main function be prefixed with a dot (e.g. `.data`,
`.x`, etc.)"* (`06-arguments.Rmd`).

**Contra-exemplo dentro da própria dplyr — `.by` vs `by`.** A documentação admite a
inconsistência sem justificá-la semanticamente:

> "Depending on the dplyr verb, the per-operation grouping argument may be named `.by` or `by`.
> (…) `mutate(.by=)`, `summarise(.by=)`, `reframe(.by=)`, `filter(.by=)`, `filter_out(.by=)`,
> `slice(.by=)`, `slice_head(by=)`, `slice_tail(by=)`, `slice_min(by=)`, `slice_max(by=)`,
> `slice_sample(by=)`. **Note that some dplyr verbs use `by` while others use `.by`. This is a
> purely technical difference.**"
> (<https://raw.githubusercontent.com/tidyverse/dplyr/main/man/rmd/by.Rmd>)

A dplyr paga o custo dessa assimetria com verificadores dedicados que produzem erro dirigido:

```r
check_by_typo     <- function(..., by = NULL, ...)  # "wrong = by, right = .by"
check_dot_by_typo <- function(..., .by = NULL, ...) # "wrong = .by, right = by"
# mensagem: "Can't specify an argument named {wrong} in this verb."
#           "Did you mean to use {right} instead?"
```
(<https://raw.githubusercontent.com/tidyverse/dplyr/main/R/by.R>)

**Python — o análogo.** siuba usa `__data` (double underscore) pelo mesmo motivo (colisão com
`**kwargs` que nomeiam colunas novas), e polars usa a separação `*exprs` / `**named_exprs`,
que elimina a colisão por construção em vez de por convenção de nome.

### 2.5 Argumentos obrigatórios e defaults

> "Required arguments shouldn't have defaults; optional arguments should have defaults. In other
> words, an argument should have a default if and only if it's optional. This simple convention
> ensures that you can tell which arguments are optional and which arguments are required **from
> a glance at the function signature**."
> (<https://raw.githubusercontent.com/tidyverse/design/main/required-no-defaults.qmd>)

O mesmo capítulo critica `predict()` da base R por aceitar ser chamado sem dados novos:
*"In my opinion, `predict()` should always require a dataset because prediction is primarily
about applying the model to new situations."* — o que é exatamente a decisão que o recipes
tomou ao remover o default de `new_data` em `bake()` (§1.3).

**Discordância direta com o scikit-learn**, que exige o oposto para o construtor: *"Ideally,
the arguments accepted by `__init__` should all be keyword arguments with a default value"*,
com a justificativa de que a introspecção de `get_params`/`set_params`/`clone` depende disso
(`develop.rst`). As duas comunidades tratam "default" como sinal semântico (tidyverse:
"opcional") e como requisito mecânico (sklearn: clonabilidade), respectivamente.

---

## 3. Método encadeado vs. função livre

### 3.1 O que cada pacote pôs em cada forma

| Pacote | Verbos | Composição | Onde o dado entra |
|---|---|---|---|
| dplyr / tidyr | funções livres | `%>%` / `\|>` | 1º argumento (`.data`, `data`) |
| ggplot2 | funções livres que devolvem objetos | `+` | `ggplot(data, mapping)`, e `data` por camada |
| recipes | funções livres (`step_*`) | `%>%` / `\|>` | `recipe` é o 1º arg; dado real só em `prep()`/`bake()` |
| parsnip | funções livres (`set_engine`, `set_mode`, `fit`) | `%>%` / `\|>` | spec é o 1º arg; dado em `fit()` |
| pandas | métodos, **e** funções livres duplicadas | encadeamento `.` + `.pipe` | `self` / 1º argumento |
| polars | métodos no frame; **expressões** são funções livres | encadeamento `.` (frame) e `.` (expressão) | `self` |
| scikit-learn | métodos no estimador; construtores de pipeline como funções livres | objetos aninhados | `fit(X, y)` |
| siuba | funções livres com dispatch | `>>` | 1º argumento (`__data`), ou parcial |

### 3.2 pandas: `.pipe` como ponte declarada

A documentação oficial afirma a preferência e o papel do `.pipe`:

> "`extract_city_name` and `add_country_name` are functions taking and returning `DataFrames`.
> Now compare the following:
> `add_country_name(extract_city_name(df_p), country_name="US")`
> Is equivalent to:
> `df_p.pipe(extract_city_name).pipe(add_country_name, country_name="US")`
> **pandas encourages the second style, which is known as method chaining.** `pipe` makes it easy
> to use your own or another library's functions in method chains, alongside pandas' methods."
> (<https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/basics.rst>;
> publicado em <https://pandas.pydata.org/docs/user_guide/basics.html> — *não alcançada*)

O mecanismo de escape para funções que **não** recebem o dado como 1º argumento é declarado:

> "What if the function you wish to apply takes its data as, say, the second argument? In this
> case, provide `pipe` with a tuple of `(callable, data_keyword)`. `.pipe` will route the
> `DataFrame` to the argument specified in the tuple."

com o exemplo `bb.query(...).assign(...).pipe((sm.ols, "data"), "hr ~ ln_h + year + g + C(lg)")`
— isto é, `.pipe` absorve bibliotecas de terceiros que **não** seguem a convenção "dado primeiro"
sem obrigar o usuário a sair do encadeamento.

Docstring do método (<https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/generic.py>):

> "Apply chainable functions that expect Series or DataFrames. Passes the object as the first
> argument to each function, so that `df.pipe(f).pipe(g)` is equivalent to `g(f(df))`. Improves
> readability when chaining several transformations."

**Duplicação verbo-livre / verbo-método no pandas.** `merge` existe nas duas formas, com listas
de parâmetros idênticas a menos do primeiro:

```python
# pandas/core/reshape/merge.py
def merge(left, right, how="inner", on=None, left_on=None, right_on=None,
          left_index=False, right_index=False, sort=False, suffixes=("_x","_y"),
          copy=..., indicator=False, validate=None) -> DataFrame

# pandas/core/frame.py
def merge(self, right, how="inner", on=None, left_on=None, right_on=None,
          left_index=False, right_index=False, sort=False, suffixes=("_x","_y"),
          copy=..., indicator=False, validate=None) -> DataFrame
```
(<https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/reshape/merge.py>,
<https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/frame.py>)

O usuário nunca precisa trocar de idioma para juntar tabelas: ambas as formas existem e
concordam nos nomes de argumento.

### 3.3 polars: expressões livres **dentro** de métodos encadeados

O polars separa dois níveis: o *contexto* é método do frame; a *expressão* é objeto livre
construído por funções de módulo (`pl.col`, `pl.when`, …).

> "In Polars, an *expression* is a lazy representation of a data transformation. Expressions are
> modular and flexible (…). Polars expressions need a *context* in which they are executed to
> produce a result. (…) the four most common contexts: `select`, `with_columns`, `filter`,
> `group_by`."
> (<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/user-guide/concepts/expressions-and-contexts.md>;
> <https://docs.pola.rs/user-guide/concepts/expressions-and-contexts/> — *não alcançada*)

O exemplo canônico mostra a expressão sendo **nomeada, guardada e reutilizada** fora de qualquer
cadeia — o que uma API só de métodos não permite:

```python
bmi_expr = pl.col("weight") / (pl.col("height") ** 2)

result = df.select(bmi=bmi_expr, avg_bmi=bmi_expr.mean(), ideal_max_bmi=25)
result = df.select(deviation=(bmi_expr - bmi_expr.mean()) / bmi_expr.std())
result = df.filter(pl.col("birthdate").is_between(date(1982,12,31), date(1996,1,1)),
                   pl.col("height") > 1.7)
```
(<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/src/python/user-guide/concepts/expressions.py>)

**A regra de "não trocar de idioma" é declarada de forma negativa**, na seção *Pipe littering*
do guia de migração do pandas:

> "A common usage in pandas is utilizing `pipe` to apply some function to a `DataFrame`.
> **Copying this coding style to Polars is unidiomatic and leads to suboptimal query plans.**"
>
> "If we do this in polars, we would create 3 `with_columns` contexts, that forces Polars to run
> the 3 pipes sequentially, utilizing zero parallelism."
>
> "**The way to get similar abstractions in polars is creating functions that create
> expressions.** (…) This single context will run all 3 expressions in parallel:
> `df.with_columns(get_ham('col_a'), get_bar('col_b'), get_foo('col_c'))`"
>
> "If you need the schema in the functions that generate the expressions, you can utilize a
> **single `pipe`**."
>
> "Another benefit of writing functions that return expressions is that these functions are
> composable, as expressions can be chained and partially applied."
> (<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/user-guide/migration/pandas.md>)

Ou seja: a unidade de extensão do usuário no polars **não** é "uma função que recebe e devolve o
frame" (como em pandas), e sim "uma função que devolve uma expressão". A troca de idioma é
evitada porque a extensão do usuário volta ao mesmo tipo (`pl.Expr`) que os verbos já consomem.

O docstring do `DataFrame.pipe` mantém a porta aberta, mas com ressalva de performance:

> "Notes — It is recommended to use LazyFrame when piping operations, in order to fully take
> advantage of query optimization and parallelization."
> (<https://raw.githubusercontent.com/pola-rs/polars/main/py-polars/src/polars/dataframe/frame.py>)

### 3.4 scikit-learn: função livre construindo objetos de método

Os verbos são métodos (`fit`/`transform`/`predict`/`score`), mas a **composição** é feita por
funções livres que montam meta-estimadores:

> "The utility function `make_pipeline` is a shorthand for constructing pipelines; it takes a
> variable number of estimators and returns a pipeline, filling in the names automatically:
> `make_pipeline(PCA(), SVC())` → `Pipeline(steps=[('pca', PCA()), ('svc', SVC())])`"
>
> "Like pipelines, feature unions have a shorthand constructor called `make_union` that does not
> require explicit naming of the components."
>
> "The `make_column_transformer` function is available to more easily create a
> `ColumnTransformer` object. Specifically, the names will be given automatically."
> (<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/compose.rst>;
> <https://scikit-learn.org/stable/modules/compose.html> — *não alcançada*)

O que evita a troca de idioma é o fato de o produto da função livre **ser ele próprio um
estimador**, com a mesma superfície de métodos:

> "The pipeline has all the methods that the last estimator in the pipeline has, i.e. if the last
> estimator is a classifier, the `Pipeline` can be used as a classifier. If the last estimator is
> a transformer, again, so is the pipeline."

E o pipeline se comporta como sequência Python (`pipe[:1]`, `pipe[-1:]`, `pipe[0]`,
`pipe.steps[0]`, `pipe.named_steps`) — a composição livre devolve um objeto indexável, não um
tipo novo (mesma fonte).

Adicionalmente, `fit` devolve `self`, o que é declarado como recurso de encadeamento:

> "The method should return the object (`self`). This pattern is useful to be able to implement
> quick one liners in an IPython session such as::
> `y_predicted = SGDClassifier(alpha=10).fit(X_train, y_train).predict(X_test)`"
> (`doc/developers/develop.rst`)

### 3.5 siuba: verbos livres com `>>`, chamáveis também na forma direta

O README apresenta os três conceitos como uma tabela explícita:

| conceito | exemplo | significado |
|---|---|---|
| verb | `group_by(...)` | "a function that operates on a table, like a DataFrame or SQL table" |
| siu expression | `_.hp.mean()` | "an expression created with `siuba._`, that represents actions you want to perform" |
| pipe | `mtcars >> group_by(...)` | "a syntax that allows you to chain verbs with the `>>` operator" |

(<https://raw.githubusercontent.com/machow/siuba/main/README.md>)

A siu expression tem a mesma função que a expressão do polars — adiar o *como* para o verbo
decidir:

> "A siu expression is a way of specifying **what** action you want to perform. This allows siuba
> verbs to decide **how** to execute the action, depending on whether your data is a local
> DataFrame or remote table."

O mecanismo que permite as **duas formas** (`filter(df, ...)` e `df >> filter(...)`) sem duplicar
código é um dispatch sobre o 1º argumento:

```python
def verb_dispatch(cls, f = None):
    """Wrap singledispatch. (…)
    This wrapper has three jobs:
        1. strip symbols off of calls
        2. pass NoArgs instance for calls like some_func(), so dispatcher can handle
        3. return a Pipeable when the first arg of a call is a symbol
    """
    dispatch_func = singledispatch(f)
    ...
    register_pipe(dispatch_func, object)   # default: devolve um pipe
```
(<https://raw.githubusercontent.com/machow/siuba/main/siuba/siu/dispatchers.py>)

Isto é: quando o 1º argumento **não** é um DataFrame, o verbo devolve um objeto `Pipeable` em vez
de um resultado — a aplicação parcial é automática. O mesmo dispatch é o que permite o mesmo verbo
rodar sobre `pandas.DataFrame`, `DataFrameGroupBy` e conexões SQL
(<https://raw.githubusercontent.com/machow/siuba/main/siuba/dply/verbs.py>).

### 3.6 dplyr / tidymodels: função livre com dado primeiro, e o pipe como único conector

O princípio de composição do tidyverse é declarado:

> "Within the tidyverse, we prefer to compose functions using a single tool: the pipe, `%>%`.
> There are two notable exceptions to this principle: **ggplot2 composes graphical elements with
> `+`**, and httr composes requests primarily through `...`. These are not bad techniques in
> isolation, and they are well suited to the domains in which they are used, but the disadvantages
> of inconsistency outweigh any local advantages."
> (<https://raw.githubusercontent.com/tidyverse/design/main/unifying.qmd>)

Ou seja: o próprio guia registra que ggplot2 **é** uma troca de idioma no meio do fluxo (`|>` para
manipular dados, `+` para montar o gráfico), e classifica isso como custo aceito, não como acerto.

No tidymodels, os três pacotes usam o mesmo conector (`|>`) mas trocam o **objeto** que caminha
pelo pipe: dados (dplyr) → receita (recipes) → especificação (parsnip) → workflow (workflows). O
`workflow()` é o objeto que reunifica os três (§6).

---

## 4. Como a família se anuncia

### 4.1 R: índice de referência gerado a partir do prefixo

O `_pkgdown.yml` do ggplot2 monta seções do índice **pelo prefixo do nome**:

```yaml
- subtitle: Geoms
  contents:
  - layer_geoms
  - starts_with("geom_")
- subtitle: Position adjustment
  contents:
  - layer_positions
  - starts_with("position_")
- title: Scales
  contents:
  - labs
  - lims
  - starts_with("scale_")
```
(<https://raw.githubusercontent.com/tidyverse/ggplot2/main/_pkgdown.yml>)

O recipes faz o mesmo, inclusive com o sub-prefixo criado no rename de 2020:

```yaml
- title: Step Functions - Imputation
  contents:
  - starts_with("step_impute_")
  - step_unknown
```
(<https://raw.githubusercontent.com/tidymodels/recipes/main/_pkgdown.yml>)

Isto fecha o ciclo com a regra "prefixos são melhores que sufixos por causa do auto-complete"
(§1.1): o mesmo prefixo serve ao autocomplete do IDE **e** à geração do índice publicado.

A dplyr organiza o índice por **objeto sobre o qual o verbo opera**, não por prefixo (a dplyr não
tem prefixo comum):

```yaml
- subtitle: Rows      # "Verbs that principally operate on rows."
  contents: [arrange, distinct, filter, slice]
- subtitle: Columns   # "Verbs that principally operate on columns."
  contents: [glimpse, mutate, pull, relocate, rename, select]
- subtitle: Groups    # "Verbs that principally operate on groups of rows."
  contents: [count, group_by, dplyr_by, rowwise, summarise, reframe, 'n']
- subtitle: Data frames  # "Verbs that principally operate on pairs of data frames."
  contents: [bind_cols, bind_rows, setops, left_join, nest_join, semi_join, cross_join, join_by, rows]
- subtitle: Multiple columns
  desc: "Pair these functions with `mutate()`, `summarise()`, `filter()`, and `group_by()`…"
  contents: [across, c_across, pick]
```
(<https://raw.githubusercontent.com/tidyverse/dplyr/main/_pkgdown.yml>)

Note a última seção: a descrição diz **com quais verbos** essas funções se combinam — a resposta a
"qual é o próximo verbo" está escrita no índice.

### 4.2 R: `@family` gera "See also" recíproco em toda a família

A dplyr marca os verbos com tags roxygen que geram automaticamente, na página de ajuda de cada
membro, a lista dos irmãos:

```
R/arrange.R:   #' @family single table verbs
R/filter.R:    #' @family single table verbs
R/mutate.R:    #' @family single table verbs
R/select.R:    #' @family single table verbs
R/slice.R:     #' @family single table verbs
R/summarise.R: #' @family single table verbs
R/rename.R:    #' @family single table verbs
R/reframe.R:   #' @family single table verbs
R/group-by.R:    #' @family grouping functions
R/group-map.R:   #' @family grouping functions
R/group-nest.R:  #' @family grouping functions
R/group-split.R: #' @family grouping functions
R/group-trim.R:  #' @family grouping functions
R/join.R:        #' @family joins
R/join-cross.R:  #' @family joins
R/rank.R:        #' @family ranking functions
```
(grep sobre <https://github.com/tidyverse/dplyr/tree/main/R>)

Cada `?mutate` termina com "Other single table verbs: `arrange()`, `filter()`, …" — o "próximo
verbo" é descoberto a partir do que se acabou de chamar, sem sair do `help()`.

### 4.3 Python: `__all__` plano e gerado

O plotnine reconstrói o `__init__.py` por script, de modo que **toda** a família aparece num
namespace único e plano:

```python
# Do not edit this file by hand.
#
# Generate it using:
#
# $ python -c 'from plotnine._utils import dev; print(dev.get_init_py())'
```
seguido de importações agrupadas por família (`from .geoms import (annotate, …, geom_abline,
geom_area, …)`, `from .coords import (coord_cartesian, …)`, `from .facets import (…)`) e de um
`__all__` explícito com todos os nomes ordenados alfabeticamente
(<https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/__init__.py>,
<https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/_utils/dev.py>).

Efeito prático: em Python, `p9.geom_<TAB>` produz o mesmo resultado que o `geom_<TAB>` do R — o
prefixo é a estrutura de descoberta, e o `__all__` é o índice.

A siuba faz o mesmo, explicitamente:

```python
from .siu import _, Fx, Lam
from .dply.across import across
from .dply.verbs import *
from .dply.verbs import __all__ as ALL_DPLY

# necessary, since _ won't be exposed in import * by default
__all__ = ['_', "Fx", "across", *ALL_DPLY]
```
(<https://raw.githubusercontent.com/machow/siuba/main/siuba/__init__.py>)

**Discordância direta com o scikit-learn**, cujas coding guidelines proíbem o mecanismo que
plotnine e siuba usam:

> "**Please don't use `import *` in any case.** It is considered harmful by the official Python
> recommendations. It makes the code harder to read as the origin of symbols is no longer
> explicitly referenced, but most important, it prevents using a static analysis tool like
> pyflakes to automatically find bugs."
> (<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/developers/develop.rst>)

O scikit-learn resolve a descoberta por **módulo temático** (`sklearn.linear_model`,
`sklearn.ensemble`, `sklearn.compose`, `sklearn.pipeline`) e por **papel** (§1.4): sabendo que o
objeto é um Transformer, você sabe que o próximo verbo é `transform`.

### 4.4 O que conta como "público"

O polars define publicidade pela documentação, não pelo `__all__`:

> "A feature is part of the public API if it is documented in the API reference."
> com a consequência declarada: *"Examples of changes that are not considered breaking: An
> undocumented function is removed. The module path of a public class is changed."*
> (<https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/development/versioning.md>)

### 4.5 Descoberta embutida no `repr`

O scikit-learn liga a representação HTML à documentação:

> "To customize the URL linking to an estimator's documentation (i.e. **when clicking on the '?'
> icon**), override the `_doc_link_module` and `_doc_link_template` attributes."
> (`doc/developers/develop.rst`, seção *Developer API for HTML representation*)

Ou seja, no notebook o próprio objeto impresso carrega o link para a sua página de referência.

---

## 5. `repr` / print no REPL

### 5.1 tibble

> "When you print a tibble, it only shows the first ten rows and all the columns that fit on one
> screen. It also prints an **abbreviated description of the column type**, and uses font styles
> and color for highlighting."
> "Numbers are displayed with three significant figures by default, and a trailing dot that
> indicates the existence of a fractional component."
> Controlado por `options(pillar.print_max = n, pillar.print_min = m)` e `options(pillar.width = n)`.
> (<https://raw.githubusercontent.com/tidyverse/tibble/main/vignettes/tibble.Rmd>)

### 5.2 recipes: o objeto imprime os passos declarados

`print.recipe()` monta um cabeçalho, a contagem de variáveis por *role*, a informação de treino
(se preparada) e a lista de operações, delegando a impressão de cada passo ao método do passo:

```r
print.recipe <- function(x, form_width = 30, ...) {
  cli::cli_h1("Recipe")
  cli::cli_h3("Inputs")
  # ... "Number of variables by role"
  if ("tr_info" %in% names(x)) cli::cli_h3("Training information")
  if (!is.null(x$steps)) cli::cli_h3("Operations")
  for (step in x$steps) print(step, form_width = form_width)
  invisible(x)
}
```
(<https://raw.githubusercontent.com/tidymodels/recipes/main/R/recipe.R>)

Saída real, capturada nos snapshots de teste do próprio pacote
(<https://github.com/tidymodels/recipes/blob/main/tests/testthat/_snaps/basics.md>):

```
-- Recipe ----------------------------------------------------------------------

-- Inputs
Number of variables by role
outcome:    1
predictor: 10

-- Training information
Training data contained 32 data points and no incomplete rows.

-- Operations
* Natural splines on: disp | Trained
```

O sufixo `| Trained` em cada passo é o estado do objeto exposto no print.

### 5.3 parsnip e workflows

O `print` de um `model_spec` mostra os argumentos declarados, separando "Main" (nomes
harmonizados) de "Engine-Specific", e o engine escolhido:

```
Random Forest Model Specification (regression)

Main Arguments:
  mtry = 10
  trees = 2000

Engine-Specific Arguments:
  importance = impurity

Computational engine: ranger
```
(<https://raw.githubusercontent.com/tidymodels/parsnip/main/README.md>)

O `print.workflow()` compõe cabeçalho + pré-processador + modelo + pós-processador
(<https://raw.githubusercontent.com/tidymodels/workflows/main/R/workflow.R>), e imprime a receita
como uma **contagem** de passos, truncando em 10:

```r
n_steps_msg <- glue::glue("{n_steps} Recipe {step}")
if (n_steps <= 10L) { cli::cat_bullet(step_names); return(invisible(x)) }
extra_steps <- n_steps - 10L
step_names <- c(step_names[1:10], "...", glue::glue("and {extra_steps} more {step}."))
```

Saída real dos snapshots
(<https://github.com/tidymodels/workflows/blob/main/tests/testthat/_snaps/printing.md>):

```
== Workflow ====================================================================
Preprocessor: None
Model: None
```
```
== Workflow ====================================================================
Preprocessor: Recipe
Model: linear_reg()

-- Preprocessor ----------------------------------------------------------------
0 Recipe Steps

-- Model -----------------------------------------------------------------------
Linear Regression Model Specification (regression)

Main Arguments:
  penalty = 0.01

Engine-Specific Arguments:
  dfmax = 5

Computational engine: glmnet
```

Um `workflow()` vazio imprime `Preprocessor: None` / `Model: None` — o print é o inventário do que
**ainda falta declarar**, o que é o mecanismo de orientação para a construção em N passos (§6).

**Regra escrita do tidymodels sobre print**
(<https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/04-print-and-summary-methods.Rmd>):

> "Every class should have a `print` method that gives a concise description of the object.
> The `print` method should invisibly return the original object.
> The number of significant digits should be an option and should use the global default.
> **Printing the call is discouraged.**
> `summary` methods are helpful but not required. These should create more verbose descriptions."

### 5.4 scikit-learn

Três mecanismos, todos configuráveis globalmente por `set_config`
(<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/_config.py>):

- `print_changed_only` — **default `True`** desde a versão 0.23:
  > "If True, only the parameters that were set to non-default values will be printed when
  > printing an estimator. For example, `print(SVC())` while True will only print 'SVC()' while
  > the default behaviour would be to print 'SVC(C=1.0, cache_size=200, ...)' with all the
  > non-changed parameters. Global default: True."
  > ".. versionchanged:: 0.23 Global default configuration changed from False to True."
- `display` — **default `'diagram'`** desde 0.23:
  > "If 'diagram', estimators will be displayed as a diagram in a Jupyter lab or notebook context.
  > If 'text', estimators will be displayed as text."
- truncamento do `__repr__` textual:
  `def __repr__(self, N_CHAR_MAX=700)` com `N_MAX_ELEMENTS_TO_SHOW = 30`, cortando pelos dois lados
  e inserindo reticências
  (<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/base.py>).

A representação HTML é declarada **experimental**:

> ".. warning:: The HTML representation API is experimental and the API is subject to change."
> "Estimators inheriting from `BaseEstimator` display a HTML representation of themselves in
> interactive programming environments such as Jupyter notebooks."
> (`doc/developers/develop.rst`)

E a saída textual do `Pipeline` mostra exatamente a estrutura declarada, incluindo os nomes que
`make_pipeline` inventou:

```
>>> pipe
Pipeline(steps=[('reduce_dim', PCA()), ('clf', SVC())])
>>> make_pipeline(PCA(), SVC())
Pipeline(steps=[('pca', PCA()), ('svc', SVC())])
>>> column_trans
ColumnTransformer(remainder=MinMaxScaler(),
                  transformers=[('onehotencoder', OneHotEncoder(), ['city']),
                                ('countvectorizer', CountVectorizer(), 'title')])
```
(`doc/modules/compose.rst`)

### 5.5 polars

`__str__` delega ao Rust e `__repr__` é idêntico a `__str__`:

```python
def __str__(self) -> str:
    return self._df.as_str()

def __repr__(self) -> str:
    return self.__str__()
```
(<https://raw.githubusercontent.com/pola-rs/polars/main/py-polars/src/polars/dataframe/frame.py>)

O formato inclui `shape` e uma **linha de dtype por coluna**, como se vê nos doctests do próprio
`pipe`:

```
shape: (4, 2)
┌─────┬─────┐
│ a   ┆ b   │
│ --- ┆ --- │
│ i64 ┆ i64 │
╞═════╪═════╡
│ 1   ┆ 10  │
└─────┴─────┘
```

Há também `_repr_html_(self, *, _from_series: bool = False)` para Jupyter, com limites ajustáveis
por variáveis de ambiente `POLARS_FMT_MAX_COLS` / `POLARS_FMT_MAX_ROWS` (mesma fonte).

### 5.6 ggplot2 e plotnine: o print é um efeito colateral

No ggplot2, `print`/`plot` desenham o gráfico:

> "Generally, you do not need to print or plot a ggplot2 plot explicitly: the default top-level
> print method will do it for you. **You will, however, need to call `print()` explicitly if you
> want to draw a plot inside a function or for loop.**"

com o exemplo do próprio arquivo de ajuda:

```r
# Doesn't seem to do anything!
for (colour in colours) {
  ggplot(mpg, aes(displ, hwy, colour = .data[[colour]])) + geom_point()
}
for (colour in colours) {
  print(ggplot(mpg, aes(displ, hwy, colour = .data[[colour]])) + geom_point())
}
```
(<https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/plot.R>)

O plotnine reproduz o comportamento com os ganchos do IPython, e mantém um `__str__` textual
distinto do render:

```python
def __str__(self) -> str:
    """Return a wrapped display size (in pixels) of the plot"""
    w, h = self.theme._figure_size_px
    return f"<ggplot: ({w} x {h})>"

def __repr__(self):
    # knitr relies on __repr__ to automatically print the last object in a cell.
    if is_knitr_engine():
        self.show()
        return ""
    return super().__repr__()

def _repr_mimebundle_(self, include=None, exclude=None) -> MimeBundle:
    """Return dynamic MIME bundle for plot display
    This method is called when a ggplot object is the last in the cell."""
```
(<https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/ggplot.py>)

Contraste com recipes/parsnip/sklearn: nesses, o print **descreve a declaração**; em
ggplot2/plotnine, o print **executa a declaração**.

### 5.7 siuba

O repr sinaliza o estado de agrupamento com um prefixo textual, visível nos doctests do pacote:

```
>>> by_cyl >> filter(_.mpg == _.mpg.max())
(grouped data frame)
    cyl   mpg   hp
3     6  21.4  110
```
(<https://raw.githubusercontent.com/machow/siuba/main/siuba/dply/verbs.py>)

---

## 6. Construção em N passos, e o atalho para o caso comum

### 6.1 scikit-learn: `Pipeline` vs `make_pipeline`

Forma longa (nomeia cada passo):

```python
estimators = [('reduce_dim', PCA()), ('clf', SVC())]
pipe = Pipeline(estimators)
```

Atalho:

```python
make_pipeline(PCA(), SVC())   # Pipeline(steps=[('pca', PCA()), ('svc', SVC())])
```

**Custo declarado, no próprio docstring:**

> "This is a shorthand for the `Pipeline` constructor; **it does not require, and does not permit,
> naming the estimators.** Instead, their names will be set to the lowercase of their types
> automatically."
> (<https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/pipeline.py>)

O nome do passo não é decorativo: é a chave usada em `pipe.named_steps` e na sintaxe
`nome__parametro` do `GridSearchCV` (`doc/modules/compose.rst` mostra
`Pipeline(steps=[("select", SelectKBest(...)), ("clf", LogisticRegression(...))])` e o acesso
`pipe[0]`, `pipe.steps[0]`). Perder o direito de nomear é perder o controle da chave.

Mesmo padrão em `make_union` (*"does not require explicit naming of the components"*) e
`make_column_transformer` (*"Specifically, the names will be given automatically"*).

**Um segundo atalho, de outra natureza**: todos os construtores têm defaults para tudo, de modo
que `SVC()` já é um objeto válido:

> "a user should be able to instantiate an estimator without passing any arguments to it. In some
> cases, where there are no sane defaults for an argument, they can be left without a default
> value. **In scikit-learn itself, we have very few places, only in some meta-estimators, where
> the sub-estimator(s) argument is a required argument.**"
> (`doc/developers/develop.rst`)

### 6.2 workflows: `workflow()` vs os `add_*()` soltos

Forma longa:

```r
workflow() |> add_recipe(recipe) |> add_model(model)
```

Atalho, com os componentes como argumentos posicionais:

```r
wf_formula  <- workflow(formula,  model)
wf_recipe   <- workflow(recipe,   model)
wf_variables<- workflow(variables, model)
```

**Custo declarado, no próprio arquivo de ajuda:**

> "The `preprocessor` and `spec` arguments allow you to add components to a workflow quickly,
> without having to go through the `add_*()` functions, such as `add_recipe()` or `add_model()`.
> **However, if you need to control any of the optional arguments to those functions, such as the
> `blueprint` or the model `formula`, then you should use the `add_*()` functions directly
> instead.**"
> (<https://raw.githubusercontent.com/tidymodels/workflows/main/R/workflow.R>)

O atalho também é *polimórfico*: um único slot `preprocessor` aceita fórmula, receita ou
`workflow_variables()`, com despacho interno e erro dirigido quando não é nenhum dos três:

```r
add_preprocessor <- function(x, preprocessor, ..., call = caller_env()) {
  if (is_formula(preprocessor)) return(add_formula(x, preprocessor))
  if (is_recipe(preprocessor))  return(add_recipe(x, preprocessor))
  if (is_workflow_variables(preprocessor)) return(add_variables(x, variables = preprocessor))
  cli_abort("{.arg preprocessor} must be a formula, recipe, or a set of workflow variables.")
}
```
(mesma fonte)

### 6.3 parsnip: default de engine como atalho

Forma longa (3 chamadas antes de qualquer resultado):

```r
rand_forest(mtry = 10, trees = 2000) |> set_engine("ranger") |> set_mode("regression")
```

Atalho introduzido em parsnip 0.1.7, com **custo declarado na mesma frase**:

> "Each model now has a default engine that is used when the model is defined. The default for
> each model is listed in the help documents. This also adds functionality to declare an engine in
> the model specification function. **`set_engine()` is still required if engine-specific
> arguments need to be added.** (#513)"
> (<https://raw.githubusercontent.com/tidymodels/parsnip/main/NEWS.md>)

O histórico registra que a direção já foi a oposta: em parsnip 0.0.0.9005, *"The engine, and any
associated arguments, are now specified using `set_engine()`. **There is no `engine` argument**"*
(mesma fonte). O argumento `engine` foi removido e depois readmitido como atalho.

Há ainda um atalho implícito no `fit()`: se o engine não foi escolhido, ele é escolhido sozinho e
o usuário é avisado — mas só se pedir verbosidade:

```r
if (is.null(object$engine)) {
  eng_vals <- possible_engines(object)
  object$engine <- eng_vals[1]
  if (control$verbosity > 0) cli::cli_warn("Engine set to {.val {object$engine}}.")
}
```
(<https://raw.githubusercontent.com/tidymodels/parsnip/main/R/fit.R>)

E o mode não escolhido produz erro em vez de default:
*"Please set the mode in the model specification."* (mesma fonte). Ou seja, dos dois eixos de
declaração (engine e mode), um tem default silencioso e o outro é obrigatório.

Nota histórica sobre o mode: em parsnip 0.0.0.9003, *"If a mode is not chosen in the model
specification, it is assigned at the time of fit"* — comportamento posteriormente endurecido.

### 6.4 recipes: separação obrigatória declaração / preparo / aplicação

O recipes exige três verbos antes de qualquer dado transformado — `recipe()` +
`step_*()`… + `prep()` + `bake()`. O atalho existente foi **removido** por conflito de nome
(§1.3): `juice()` era o atalho para "aplique aos dados de treino", e virou
`bake(object, new_data = NULL)`, com o custo declarado de que o `NULL` agora é obrigatório
(*"The `new_data` argument now has no default, so a `NULL` value must be explicitly used"*,
recipes NEWS). Trocou-se concisão por explicitude.

Um segundo atalho de escopo: a receita aceita `formula` + `data` no construtor
(`recipe(HHV ~ ., data = biomass)`), com verificação que rejeita transformações inline na fórmula
e redireciona para steps:

```
Error in `recipe()`:
x Misspelled variable name or in-line functions detected.
i The following function/misspelling was found: `log`.
i Use steps to do transformations instead.
```
(<https://github.com/tidymodels/recipes/blob/main/tests/testthat/_snaps/basics.md>)

### 6.5 ggplot2: `qplot()` e os defaults por camada

O índice de referência do ggplot2 ainda lista `qplot` na seção "Plot basics" ao lado de `ggplot`,
`aes`, `add_gg` e `ggsave` (<https://raw.githubusercontent.com/tidyverse/ggplot2/main/_pkgdown.yml>)
— um atalho de uma chamada só para o gráfico comum, mantido no índice.

O atalho estrutural, porém, são os **defaults herdados**: `make_constructor()` fixa
`inherit.aes = TRUE`, `stat = "identity"`, `position = "identity"` em todo `geom_*()`
(<https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/make-constructor.R>), de modo que
`ggplot(mpg, aes(displ, hwy)) + geom_point()` não precisa redeclarar dado nem mapeamento na camada.
O custo é o descrito em §2.1: a ordem dos dois primeiros argumentos fica invertida entre
`ggplot()` e `geom_*()`.

### 6.6 tidyverse: o atalho como argumento em vez de função nova

Dois casos em que o "caminho curto" foi implementado como **argumento de um verbo existente**, e
não como função nova:

- `transmute()` foi superseded em favor de `mutate(.keep = "none")` (dplyr 1.1.0 NEWS);
- `.by` foi introduzido como alternativa por-operação a `group_by()` + `ungroup()`:
  > "one of the goals of `.by` is to allow you to place that grouping specification alongside the
  > code that actually uses it. As an added benefit, **with `.by` you no longer need to remember
  > to `ungroup()` after `summarise()`**, and `summarise()` won't ever message you about how it's
  > handling the groups."
  > "This idea comes from data.table, which allows you to specify `by` alongside modifications in
  > `j`, like: `dt[, .(x = mean(x)), by = g]`."
  > (<https://raw.githubusercontent.com/tidyverse/dplyr/main/man/rmd/by.Rmd>)

  Custo declarado: cobertura parcial e uma restrição dura —
  *"To prevent surprising results, you can't use `.by` on an existing grouped data frame"*; e
  *"If a dplyr verb doesn't support `.by`, then that typically means that the verb isn't inherently
  affected by grouping. For example, `pull()` and `rename()` don't support `.by`."* (mesma fonte).
  Some-se a isso a assimetria `.by`/`by` documentada em §2.4.

- Simetricamente, dplyr 1.2.0 escolheu o caminho oposto para um caso vizinho, criando uma função
  nova em vez de um argumento: `filter_out()` como companheiro de `filter()`
  (*"Use `filter()` when specifying rows to keep. Use `filter_out()` when specifying rows to
  drop."* — dplyr NEWS). As duas decisões coexistem no mesmo pacote.

### 6.7 Redução de aridade por objeto de opções

O padrão declarado para conter a explosão de argumentos opcionais
(<https://raw.githubusercontent.com/tidyverse/design/main/argument-clutter.qmd>):

> "If you have a large number of optional arguments that control the fine details of the operation
> of a function, it might be worth lumping them all together into a separate 'options' object
> created by a helper function. (…) By moving rarely used and less important arguments to a
> secondary function, you can more easily draw attention to what is most important."

Vantagem declarada do helper sobre a lista nomeada: *"A helper function is more convenient than a
named list because it checks the argument names for free and gives nicer autocomplete to the
user."*

Custo declarado da migração: introduzir `opts` ao lado dos argumentos antigos cria dependência
entre argumentos (*"if you specify both `opts` and `opt1`/`opt2`, `opts` will win"*), e a
recomendação é depreciar os antigos.

Exemplos citados pela fonte: `loess()`/`loess.control()`, `glm()`/`glm.control()`,
`nls()`/`nls.control()`, `optim(control=)` sem helper, `tune::fit_resamples()` +
`tune::control_resamples()`, `caret::train()` + `caret::trainControl()`,
`readr::read_delim(locale=)` + `readr::locale()`. E funções apontadas como candidatas ainda não
migradas: `readr::read_delim()` e `ggplot2::geom_smooth()`.

O tidymodels adota a regra: *"Parameters that users will commonly modify should be main arguments
to the top-level function. Others, especially those that control computational aspects of the fit,
should be contained in a `control` object."*
(<https://raw.githubusercontent.com/tidymodels/model-implementation-principles/master/02-function-interfaces.Rmd>)
— visível em `fit.model_spec(..., control = control_parsnip())`.

---

## 7. Índice de fontes primárias

**tidyverse design guide** (lidas via fonte do repositório; site publicado inacessível nesta sessão)
- <https://raw.githubusercontent.com/tidyverse/design/main/unifying.qmd> → <https://design.tidyverse.org/unifying.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/function-names.qmd> → <https://design.tidyverse.org/function-names.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/important-args-first.qmd> → <https://design.tidyverse.org/important-args-first.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/call-data-details.qmd> → <https://design.tidyverse.org/call-data-details.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/dots-after-required.qmd> → <https://design.tidyverse.org/dots-after-required.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/dots-prefix.qmd> → <https://design.tidyverse.org/dots-prefix.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/dots-data.qmd> → <https://design.tidyverse.org/dots-data.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/required-no-defaults.qmd> → <https://design.tidyverse.org/required-no-defaults.html>
- <https://raw.githubusercontent.com/tidyverse/design/main/argument-clutter.qmd> → <https://design.tidyverse.org/argument-clutter.html>
- índice de capítulos: <https://raw.githubusercontent.com/tidyverse/design/main/_quarto.yml>

**dplyr**
- NEWS: <https://raw.githubusercontent.com/tidyverse/dplyr/main/NEWS.md>
- vinheta colwise: <https://raw.githubusercontent.com/tidyverse/dplyr/main/vignettes/colwise.Rmd>
- `.by`: <https://raw.githubusercontent.com/tidyverse/dplyr/main/man/rmd/by.Rmd> e <https://raw.githubusercontent.com/tidyverse/dplyr/main/R/by.R>
- assinaturas: `R/mutate.R`, `R/filter.R`, `R/summarise.R`, `R/arrange.R`, `R/select.R`, `R/slice.R` em <https://github.com/tidyverse/dplyr/tree/main/R>
- índice de referência: <https://raw.githubusercontent.com/tidyverse/dplyr/main/_pkgdown.yml>

**tidyr**
- NEWS: <https://raw.githubusercontent.com/tidyverse/tidyr/main/NEWS.md>
- vinheta pivot: <https://raw.githubusercontent.com/tidyverse/tidyr/main/vignettes/pivot.Rmd>
- assinaturas: <https://raw.githubusercontent.com/tidyverse/tidyr/main/R/pivot-long.R>, `.../R/pivot-wide.R`

**tidymodels**
- princípios: <https://github.com/tidymodels/model-implementation-principles> (capítulos 01, 02, 04, 06, 08)
- recipes: <https://raw.githubusercontent.com/tidymodels/recipes/main/NEWS.md>, `.../R/recipe.R`, `.../R/center.R`, `.../_pkgdown.yml`, `tests/testthat/_snaps/basics.md`
- parsnip: <https://raw.githubusercontent.com/tidymodels/parsnip/main/README.md>, `.../NEWS.md`, `.../R/fit.R`
- workflows: <https://raw.githubusercontent.com/tidymodels/workflows/main/R/workflow.R>, `tests/testthat/_snaps/printing.md`
- lifecycle: <https://raw.githubusercontent.com/r-lib/lifecycle/main/vignettes/stages.Rmd>

**ggplot2 / plotnine**
- <https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/plot.R>
- <https://raw.githubusercontent.com/tidyverse/ggplot2/main/R/make-constructor.R>
- <https://raw.githubusercontent.com/tidyverse/ggplot2/main/_pkgdown.yml>
- <https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/ggplot.py>
- <https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/__init__.py>
- <https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/_utils/dev.py>
- <https://raw.githubusercontent.com/has2k1/plotnine/main/plotnine/_utils/__init__.py> (`order_as_data_mapping`)

**scikit-learn** (site publicado inacessível nesta sessão)
- <https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/developers/develop.rst> → <https://scikit-learn.org/stable/developers/develop.html>
- <https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/doc/modules/compose.rst> → <https://scikit-learn.org/stable/modules/compose.html>
- <https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/pipeline.py>
- <https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/base.py>
- <https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/_config.py>
- **NÃO CONSULTADO:** Buitinck et al., arXiv:1309.0238 — <https://arxiv.org/abs/1309.0238> (bloqueado pelo proxy)

**polars** (site publicado inacessível nesta sessão)
- <https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/user-guide/concepts/expressions-and-contexts.md>
- <https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/src/python/user-guide/concepts/expressions.py>
- <https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/user-guide/migration/pandas.md>
- <https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/releases/upgrade/0.19.md>
- <https://raw.githubusercontent.com/pola-rs/polars/main/docs/source/development/versioning.md>
- <https://raw.githubusercontent.com/pola-rs/polars/main/py-polars/src/polars/dataframe/frame.py>

**pandas** (site publicado inacessível nesta sessão)
- <https://raw.githubusercontent.com/pandas-dev/pandas/main/doc/source/user_guide/basics.rst> → <https://pandas.pydata.org/docs/user_guide/basics.html>
- <https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/generic.py> (`pipe`)
- <https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/frame.py> (`DataFrame.merge`)
- <https://raw.githubusercontent.com/pandas-dev/pandas/main/pandas/core/reshape/merge.py> (`pd.merge`)

**siuba** (site `siuba.org` não testado/indisponível; lidos os fontes)
- <https://raw.githubusercontent.com/machow/siuba/main/README.md>
- <https://raw.githubusercontent.com/machow/siuba/main/siuba/__init__.py>
- <https://raw.githubusercontent.com/machow/siuba/main/siuba/siu/dispatchers.py>
- <https://raw.githubusercontent.com/machow/siuba/main/siuba/dply/verbs.py>

**tibble**
- <https://raw.githubusercontent.com/tidyverse/tibble/main/vignettes/tibble.Rmd>
