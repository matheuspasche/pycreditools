# Fronteira de módulo — levantamento de referências

> **Insumo de decisão, não decisão.** Este documento levanta fatos, formas e preços.
> Nenhum veredito "adotar / adaptar / descartar" é tomado aqui — esses são de #117, #118,
> #119, #120, #126, #129 e #131. Se você achar uma recomendação neste texto, é um defeito:
> reporte no #134.

Resolve a **fatia "fronteira de módulo"** da Lente B (#134), que graduou de #113. Cobre seis
das perguntas da §16 do `architecture-critique.md`: **1, 3, 7, 11, 12, 13** — as que
perguntam *com que critério se separa*, *o que fica de cada lado*, e *onde mora um dado
disputado*.

Referência principal: **deep modules** — John Ousterhout, *A Philosophy of Software Design*
(2018). Não é biblioteca nem framework; é critério publicado de fronteira e de tamanho de
interface. Entra aqui porque a §1 pergunta exatamente isso e "motivo de mudança"
(Parnas/SRP) era o único critério na mesa.

Onde uma pergunta pediu precedente praticado, as refs da Lente A (`tidymodels`,
`scikit-learn`) são citadas — com o motivo registrado.

As outras fatias da Lente B — núcleo funcional (§16 15–16), contrato de saída (6, 9, 10,
20), round-trip e o peso do `Expression` (5, 14), estratégia de busca / CART (19) — vivem em
ticket próprio.

## Como ler

Cada célula tem **N formas**. Para cada uma: **fato** (o que a referência faz, ou o que o
código mede), **porta para Python?**, e **preço**. As formas convivem porque a decisão é de
outro card.

**Uma ressalva de método, decidida com o dono (2026-07-25):** onde a medição mostra que as
formas **não empatam**, este documento diz isso e mostra o número. Simetria fabricada não é
neutralidade — é fazer o card a jusante repetir a medição. Sem veredito continua valendo:
apontar assimetria medida não é escolher.

## O que Ousterhout dá, e o que não dá

Quatro ideias usadas neste documento:

1. **Complexidade = dependências + obscuridade.** Não é tamanho. Sintomas nomeados:
   *change amplification* (uma decisão exige edição em N lugares) e *cognitive load*.
2. **Módulo profundo vs raso.** A métrica é razão: benefício da interface ÷ custo de
   aprendê-la. Profundo = interface pequena, implementação grossa.
3. **"Classitis"** — o excesso da cura. Quebrar em muitos tipos rasos não mata a
   complexidade; migra pras juntas. É um argumento **contra** decomposição, e por decisão do
   dono (2026-07-25) ele é custeado aqui como forma legítima, não descartado.
4. **Vazamento de informação** — se dois módulos precisam saber a mesma coisa, a fronteira
   está no lugar errado. É o teste mais operacional que ele dá, e o que mais rende aqui.

O que ele **não** dá: nada sobre declarado-vs-ajustado, nada sobre DataFrame, nada
específico de Python. É critério de fronteira e de largura de interface. Por isso cobre
estas seis perguntas e não as outras quatorze.

---

## §16 Q1 — que critério separa tipos quando um objeto acumula papéis

### O fato medido: a interface efetiva é o estado inteiro

Não os 13 campos declarados (`policy.py:21-33`) — os campos **lidos de fora de
`policy.py`**:

| Campo | Leituras externas | Arquivos de fora |
|---|---|---|
| `stages` | 12 | deployment, screening, simulation, stages, studio, sweep |
| `current_approval_col` | 11 | deployment, expressions, simulation, stages, studio |
| `estimated_default_col` | 11 | simulation, studio |
| `actual_default_col` | 9 | deployment, simulation, studio, sweep |
| `stress_scenarios` | 8 | simulation |
| `calibration_bins` | 5 | expressions, simulation, stages |
| `score_cols` | 4 | deployment, stages, studio |
| `current_hired_col` | 4 | simulation |
| `calibration_score_col` | 4 | gui, stages |
| `applicant_id_col` | 3 | deployment, studio |
| `rating_recipe` | 3 | simulation |
| `calibration_base` | 2 | expressions, simulation |
| `time_col` | 1 | deployment |

**Todos os 13 campos são lidos de fora.** ~77 pontos de leitura em 8 arquivos. Pela métrica
do Ousterhout (benefício ÷ custo de aprender), `CreditPolicy` não é módulo — é um registro
público com métodos ao lado. Não há nada escondido para a fronteira proteger.

### Forma A — separar por motivo de mudança (Parnas/SRP): 4 tipos

**Fato:** o critério que o mapa #111 já traz — schema / regras / premissas / motor,
agrupados pelo que os faz mudar (a base, a política, a pergunta).

**Porta para Python?** Sim, direto: quatro dataclasses.

**Preço medido:** os ~77 pontos de leitura viram ~77 pontos que precisam saber **de qual dos
4 tipos** buscar. `deployment.py` hoje lê campos de três grupos (`time_col`, `stages`,
`applicant_id_col`) e passa a depender de três tipos em vez de um. É o cenário de classitis
com número: a teia não morre, ganha endereços. A decomposição só paga se cada tipo
**esconder** — ver Q11, que mede quanto do acesso é evitável.

### Forma B — um tipo, interface estreita, schema escondido

**Fato:** a leitura ortodoxa de deep module. Os 13 campos deixam de ser públicos; quem
precisa pergunta por método.

**Porta para Python?** Sim, mas exige disciplina que a linguagem não impõe (sem `private`
real).

**Preço medido:** parte funciona — `simulation.py` não quer `estimated_default_col`, quer *a
coluna de PD estimada da base*, 11 vezes; isso é método. Duas classes de consumidor não
somem com método nenhum:

- **`deployment.py`** quer serializar campo por campo — precisa do estado, não de perguntas.
- **`sweep.py`** quer **fabricar variantes** (`sweep.py:164-167`, `:169-186`) — precisa
  reconstruir, não consultar.

Para atendê-los, a política teria que saber executar, exportar e varrer. Isso é o god object
de volta, com a interface maquiada: 5 responsabilidades continuam, só param de aparecer nos
campos. Ousterhout chamaria isso de módulo profundo pela métrica errada — interface pequena
medida em nomes, não em conceitos.

### Forma C — falta um tipo: o experimento

**Fato:** as Formas A e B falham no mesmo ponto, e o ponto não é onde os campos moram. `sweep`
e `deployment` **não são a política** e são os dois maiores consumidores do estado dela. A
medição aponta para um tipo ausente — o que representa *este estudo*: schema + regras +
premissas colados, com identidade própria.

**Precedente praticado:** `workflow` do tidymodels (spec + preprocessor colados; é o que
`tune_grid()` recebe, não a spec solta). Ausência registrada: no scikit-learn o `Pipeline`
cola preprocessor + estimador mas **não** carrega premissas de avaliação — o splitter entra
como argumento de `cross_validate`. Ou seja, das duas refs da Lente A, uma tem o tipo e a
outra resolve por argumento.

**Porta para Python?** Sim — é uma dataclass de composição.

**Preço:** um tipo novo na superfície pública, e a pergunta "o que se deploya?" muda de
endereço (hoje `DeploymentPolicy` embrulha a política inteira; sob a Forma C ele embrulharia
o quê?). Fica aberto no mapa #111 em *Not yet specified*.

**O que a célula entrega para #117:** o critério de fronteira **não decide sozinho**. As três
formas colocam a mesma pergunta — quem é o dono do experimento. Isso é sinal de que falta um
tipo, não de que os 13 campos estão no grupo errado.

---

## §16 Q3 — o que é "especificação" e o que é "condição de avaliação"

O caso difícil nomeado no §2 é **calibração**.

### O fato medido: calibração é derivada, não declarada

`resolve_calibration_score_col` (`stages.py:158`) resolve a coluna em cascata:

1. `calibration_score_col` explícito — **premissa**
2. as chaves de `CutoffStage.cutoffs` — **as regras**
3. `score_cols` — **o schema**
4. e testa presença **no DataFrame** — **o dado**

Quatro fontes, três dos quatro grupos propostos, mais a base. `calibration_direction` tem sua
própria função de resolução (`stages.py:189`). `calibration_base` é lido em dois arquivos com
a **mesma condição literal duplicada**: `in ("global", "all", "dataset")` em
`expressions.py:205` e `simulation.py:742`.

E o endereço atual foi escolhido pela topologia de import, não pelo domínio — a docstring
admite: *"Lives here (not in the calibration primitive or in `expressions`) because it is the
only piece that needs `CutoffStage`; keeping it here is what closes the `stages ↔
expressions` import cycle."*

### Forma A — calibração é premissa de estudo

**Fato:** é hipótese de transporte; muda quando a pergunta muda. É onde o mapa a coloca hoje.

**Preço:** a cascata precisa alcançar regras + schema + dado. O objeto-premissa vira leitor
dos outros três, invertendo a dependência que a decomposição queria cortar.

### Forma B — calibração é schema

**Fato:** é uma coluna e uns bins.

**Preço:** `calibration_base` (keep-in vs global) é escolha de **população** — decisão do
estudo, não do dado. E não explica por que `CutoffStage` participa da resolução.

### Forma C — calibração é artefato ajustado do bind

**Fato:** não mora em nenhum declarado; nasce quando schema + regras + base se encontram.

**Precedente praticado (medido na Lente A):** a `recipe` não-preparada do tidymodels usa o
dataframe só como template de nomes e tipos, e é o `prep()` que ajusta — dois estados em
tipos distintos. O scikit-learn resolve o mesmo com **um tipo em dois estados**, distinguidos
pela convenção de atributo com sublinhado no fim (`check_is_fitted`).

**Preço:** exige que "preparado" seja um estado observável e serializável, o que puxa Q14
(round-trip de estado ajustado, outra fatia).

### §2.3 — N condições produzem quantas saídas

Custeado num lado só, por decisão do dono (2026-07-25).

**Fato medido:** `simulation.py:583` e `:659` fazem `final_probs = prob_matrix.max(axis=1)`.
Dois cenários declarados produzem **uma** linha de PD pior-caso por cliente. Há
`warnings.warn` nos dois caminhos (`:572-577`, `:648-653`) — a semântica é conhecida e
indesejada, não descuido.

**Forma custeada: a condição é dimensão do resultado, nunca agregada pelo motor.** N
condições → N resultados; quem quer pior-caso agrega depois, explicitamente.

**Precedente:** `rsample` produz N splits e `fit_resamples` devolve N linhas; nenhuma
referência colapsa por dentro.

**Preço medido:** toda saída ganha uma coluna de cenário, e todo consumidor que hoje espera
uma linha por cliente quebra — inclusive a GUI e a masterclass. É quebra dura, logo é insumo
de #124 (roadmap).

**A forma não custeada, registrada:** agregação declarada (o agregador — max / média /
percentil — como campo do objeto-premissa) mantém o caso pior-caso que o domínio de crédito
usa, e é mais barata de migrar. Não foi custeada nesta sessão; se #119 ou #124 precisar do
preço, é uma célula a abrir.

---

## §16 Q7 — derivar com um campo alterado, sem conhecer todos os campos

**Esta célula não tem formas empatadas, e a assimetria é medida.** Registrado como fato, na
mesma disciplina do §15 do levantamento (a prática correta já existe em outro lugar do
pacote).

### O fato: o bug é um tipo fora do padrão que o próprio pacote adotou

`sweep.py:169-186` reconstrói à mão:

```python
stages_list[i] = RateStage(
    name=stage.name,
    base_rate=base_rate_values[stage.name],
    variable=stage.variable,
    calibrate=stage.calibrate,
)
```

Quatro argumentos; `RateStage.__init__` (`stages.py:286-294`) tem **seis**. Faltam
`observed_col` e `calibrate_by`.

Por que é classe de bug e não deslize: o autor dessa linha precisou **saber a lista completa
de campos de um tipo que mora em outro arquivo**. Ele acertou no dia. Quando #68 acrescentou
`observed_col`, a linha ficou errada sem ninguém tocá-la — e **em silêncio**, porque o
parâmetro que falta tem default. Change amplification com número: cada campo novo em
qualquer `Stage` × cada ponto de reconstrução = um lugar novo pra esquecer. O mesmo padrão
está em `_without_cutoff_entries` (`sweep.py:62-78`), hoje correto por coincidência de
contagem.

**Nenhum `Stage` é dataclass.** `Stage` (`stages.py:29`), `CutoffStage:117`,
`FilterStage:211`, `RateStage:286` — todos com `__init__` à mão. O pacote usa `@dataclass` em
**17** lugares, incluindo `@dataclass(frozen=True)` em `policy.py:13` e
`_kernels/calibration.py:83`. Os estágios são a exceção, e são os que sangram.

### Forma A — `Stage` vira dataclass frozen; derivação é `dataclasses.replace`

**Fato:** `replace` reconstrói a partir de `fields(obj)`, gerado pelo decorador. Quem chama
**não conhece campo nenhum**; campo novo entra na lista sozinho. O ponto de esquecimento
deixa de ser policiado e passa a ser inalcançável — é o *"define errors out of existence"* do
Ousterhout.

**Porta para Python?** É nativo (`dataclasses`, stdlib).

**Preço:** `RateStage.__init__` faz validação e coerção; migra para `__post_init__` (frozen
exige `object.__setattr__` para coagir — o pacote já paga isso em `policy.py:36`).

**Ganho medido além do §4:** `CreditPolicy` é `frozen=True`, mas frozen em Python é **raso**
— proíbe `policy.stages = ...` e não proíbe `policy.stages[0].base_rate = 0.9`. Por isso
`policy._replace` (`policy.py:90-96`) faz `copy.deepcopy` a cada movimento de builder,
inclusive de `rating_recipe`, que carrega estado ajustado. Com filhos frozen o
compartilhamento deixa de ser perigoso e o `deepcopy` sai. **Um movimento, §4 e §3.1 juntos.**

### Forma B — método `.with_(...)` por tipo

**Fato:** cada tipo expõe seu próprio movimento de derivação.

**Preço:** um lugar por tipo pra errar — literalmente o §10 (22 definições de
`to_dict`/`from_dict` em 8 arquivos) replicado numa segunda dimensão.

### Forma C — teste de totalidade (ortogonal, não substitui)

**Fato:** responde a segunda metade da pergunta ("como se testa que uma reconstrução é
total"), e é o único jeito de pegar a Forma B quebrando.

```python
@pytest.mark.parametrize("obj", [...um exemplar de cada tipo, todos os campos não-default...])
def test_derivacao_total(obj):
    assert dataclasses.replace(obj) == obj
    assert type(obj).from_dict(obj.to_dict()) == obj
```

**Duas exigências escondidas, ambas decisões a jusante:** os tipos precisam de **igualdade
por valor** (`eq=True`, que dataclass dá de graça e `__init__` à mão não dá), e o exemplar
precisa ter **todos os campos não-default** — senão o teste passa justamente no caso que o
bug do §4 explora.

É o mesmo teste que fecha §16 Q14, o que confirma que Q7 e Q14 são a mesma mecânica vista de
dois lados.

---

## §16 Q11 — o que um passo precisa receber, e quem calcula o derivado

### O fato medido: o estágio não quer campos, quer dois derivados

`stages.py` toca `policy.` em 10 lugares; fora de docstring são **7 leituras de 4 campos**:

| Campo lido | Linhas | Para quê |
|---|---|---|
| `current_approval_col` | `:383`, `:444`, `:445` | montar a máscara de keep-in |
| `calibration_score_col` | `:169` | resolver a coluna de bin |
| `score_cols` | `:180`, `:181` | fallback da mesma resolução |
| `stages` | `:172`, `:199` | fallback da mesma resolução |
| `calibration_bins` | `:407` | escolher `min_keep_ins` (5 ou 50) |

Três leituras que a tabela produz:

1. **`RateStage` não precisa de nenhum dos 4 campos.** Precisa de duas coisas derivadas: **a
   máscara de keep-in** e **a atribuição de bin por linha**. Os campos são só o caminho.
   O estágio está fazendo trabalho do executor.
2. **`CutoffStage` e `FilterStage` recebem `policy` e ignoram** (`:128-147`, `:223-244`). A
   assinatura carrega a dependência para 3 tipos por causa de 1.
3. **A circularidade é de dado, não só de import.** `resolve_calibration_score_col` lê
   `policy.stages` para achar os `CutoffStage` — um passo consultando a lista de passos
   irmãos. É o vazamento de informação na forma mais nítida do pacote.

E `RateStage` resolve a **mesma** máscara de keep-in duas vezes na mesma chamada:
`_observed_probs` (`:388`) e `apply` (`:445`).

**Premissa de custeio, decidida com o dono (2026-07-25):** máscara de keep-in e bin de score
são **derivados nomeados, calculados uma vez no bind**. Sustentação: a duplicação `:388`/`:445`
e o fato de a resolução de bin obrigar um passo a ler os irmãos. Casa com o achado do #113 —
a `recipe` preparada é exatamente "derivado calculado uma vez no encontro com a base".

### Forma A — argumentos explícitos

`apply(df, keep_in_mask=..., score_bins=...)`. O executor calcula uma vez e passa.

**Preço:** a assinatura cresce a cada estágio que precise de outro derivado, e o executor
passa a conhecer a necessidade de cada tipo. Acoplamento invertido, não removido — e a
extensão por estágio de terceiro fica impossível sem mexer no executor.

### Forma B — objeto de contexto estreito

Um tipo só-leitura (`bind` / `ExecutionContext`) que carrega os derivados e nada mais.

**Preço:** entra na superfície pública se estágio for extensível pelo usuário. E o risco está
medido: ele engorda até virar `policy` com outro nome — foi assim que `policy: Any` nasceu. A
mitigação é o próprio critério do Ousterhout aplicado a esse tipo (interface estreita, e o
que ele esconde é o cálculo do derivado).

### Forma C — protocolo declarado

O estágio declara o que precisa (`requires = ("keep_in_mask",)`) e o executor supre.

**Preço:** indireção stringly-typed, mesma classe de §5 e §13. Ganho: o executor não conhece
tipos, só nomes de derivado, e estágio de terceiro funciona.

**Nota transversal:** `method: str` em vez de `SimulationMethod` (`stages.py:36`, com
`simulation.py:431` desembrulhando via `.value`) e `direction == "gte"` (`:136`) são a mesma
patologia da Forma C já instalada — nome em string onde havia Enum disponível. Se a Forma C
for adotada, ela precisa de vocabulário fechado, o que é §16 Q20 (outra fatia).

---

## §16 Q12 — onde mora um dado que é fato da base *e* insumo de um passo

### O fato medido: os dois donos surgiram da falta de referência por papel

`CreditPolicy.current_hired_col` (contêiner) e `RateStage.observed_col` (peça,
`stages.py:319`) respondem à mesma pergunta — qual coluna registra a contratação real. O
motor precisa de `_has_observed_col_stage` (`simulation.py:334-343`) só para saber qual está
valendo, e a docstring nomeia: *"the legacy take-up declaration that predates
`current_hired_col`"*. O caminho não-declarado emite `DeprecationWarning` (`:382-391`), com o
flip para erro duro pendente (#106).

**Como os dois donos surgiram** — que é o que a pergunta pede: o `RateStage` precisava dizer
*"eu leio o desfecho observado"*, e não existia nenhum jeito de um estágio **referenciar um
papel do schema** sem repetir o nome da coluna. Sem mecanismo de referência, a única saída é
copiar o nome — e um nome copiado em dois tipos é dois donos. `current_hired_col` veio depois,
pelo outro lado, resolvendo a mesma falta.

Isso reenquadra a célula: a pergunta não é "schema ou estágio?" — é **"existe um jeito de o
estágio nomear um papel sem possuir a coluna?"**. As duas formas óbvias são as duas que o
pacote já tentou, e o resultado das duas juntas está medido.

### Forma A — mora no schema; o passo referencia por papel

O passo declara `observed=role("hired_outcome")`; o schema amarra papel→coluna no bind.

**Precedente praticado:** `has_role()` do `hardhat`/`recipes`, e os seletores de coluna do
scikit-learn (`make_column_selector`, `ColumnTransformer`). **As duas refs da Lente A
resolvem por seleção declarada, não por nome copiado** — é o raro caso em que elas concordam.

**Preço:** exige o vocabulário de papéis existir e ser fechado (§16 Q20, outra fatia), e um
papel não-amarrado tem que falhar **no bind**, não em runtime. É a única das três em que só
um lado sabe o nome da coluna — logo a única que passa o teste de vazamento do Ousterhout.

### Forma B — mora no passo; o schema não conhece

**Preço medido:** o motor perde a visão global e precisa varrer os estágios para descobrir o
que a base tem. `_has_observed_col_stage` (`simulation.py:334-343`) **é** esse custo, já pago.

### Forma C — mora no schema; o passo não declara nada

O passo lê "o desfecho observado" sem nomear qual.

**Preço:** só funciona com **um** desfecho observado por estudo. Morre no dia em que houver
dois estágios de rate com desfechos diferentes — e a docstring do `RateStage` (`:264-283`)
cita exatamente esses casos como alvo: mesa de crédito, formalização, antifraude.

---

## §16 Q13 — mesma operação, populações diferentes

### O fato medido: o kernel está certo; a duplicação é do adaptador

Os dois caminhos terminam na mesma chamada, com os seis argumentos idênticos em nome e
posição:

```python
# expressions.py:216-223              # simulation.py:750-757
calibrate_by_score_bins(              calibrate_by_score_bins(
  cal_scores=keep_in_scores,            cal_scores=keep_in_scores,
  cal_values=keep_in_vals,              cal_values=keep_in_defaults,
  ref_scores=reference_scores,          ref_scores=reference_scores,
  target_scores=df[primary_score],      target_scores=swap_ins[primary_score],
  bins=n_bins,                          bins=n_bins,
  global_fallback=global_mean,          global_fallback=global_pd,
)                                     )
```

O kernel **já é parametrizado na população** — `cal_scores`/`cal_values` são o subconjunto que
o chamador escolheu. ADR 0010 está certo ao dizer que os dois momentos não unificam (a
expressão roda antes de `new_approval` existir).

O que duplica é o **adaptador entre `CreditPolicy` e o kernel**:

| Passo | `expressions.py` | `simulation.py` | Igual? |
|---|---|---|---|
| Define população | `df[current_approval_col] == 1` (`:188`) | `keep_ins_mask` (`scenario == KEEP_IN`) | não — é a diferença legítima |
| O que calibra | valores da expressão | `actual_default_col` | não |
| Alvo | `df` inteiro | só `swap_ins` | não |
| Ramo `calibration_base` | `in ("global","all","dataset")` (`:205`) | idem (`:742`) | **sim, literal** |
| Default de bins | `10 if None` (`:212-215`) | `10 if None` (`:747`) | **sim** (comentário admite: *"consistent with simulation.py"*) |
| Piso de amostra | **ausente** | `5 if calibration_bins else 50` (`:728`) | **não** |
| `global_fallback` NaN→0.0 | `:196`, `:214` | `:730-732`, `:737-739` | **sim** |
| Diagnóstico | **ausente** | `diagnose_score_bin_calibration` (`:759`) | **não** |

Três decisões de modelagem — o ramo `calibration_base`, o default de 10 bins, o tratamento de
NaN — escritas duas vezes com literais iguais. Nada garante que continuem concordando. Isso
não é consequência do ADR 0010; é a falta de uma camada entre a política e o kernel puro.

### ⚠️ Divergência já instalada — não é insumo de decisão

Registrado à parte porque não é forma a custear: é comportamento diferente em produção sem
ADR que o autorize.

1. **Piso de amostra existe num caminho e não no outro.** `simulation.py:728` recusa calibrar
   com menos de 50 keep-ins (ou 5, com bins custom) e cai para o global. `expressions.py`
   **não tem piso** — calibra com quantos houver. Duas respostas para a mesma pergunta de
   robustez estatística. O mesmo piso aparece uma **terceira** vez em `stages.py:407`: três
   endereços para um número.
2. **O diagnóstico roda num lado só.** Se calibração é hipótese de transporte, ela precisa de
   diagnóstico nos dois lados — ou o usuário só sabe quando confiar em metade delas.

### Forma A — população como argumento nomeado do adaptador

Uma função/tipo de calibração recebe `population=` (com nome de domínio: "aprovados atuais"
vs "keep-ins") + os valores, e resolve `calibration_base`, bins, piso e NaN **uma vez**.

**Porta para Python?** Sim — função pura sobre `(df, população, knobs)`.

**Preço:** o momento do pipeline continua implícito. Quem chama ainda precisa saber que só uma
população existe antes de `new_approval`; chamar com a errada dá resultado silenciosamente
diferente. ADR 0010 passa a ser cumprido por convenção, não por tipo.

### Forma B — dois tipos, um por momento

`PreSimCalibration` / `PostSimCalibration`, cada um com a população fixada pelo tipo.

**Preço:** o usuário aprende dois nomes; e as três decisões duplicadas precisam morar numa
base comum, senão B **nomeia** a duplicação sem resolvê-la. Ganho: chamar com a população
indisponível deixa de ser possível — erro fora do espaço de estados.

### Forma C — um tipo, dois estados

Declarada uma vez, *preparada* contra a população disponível no momento; o estado ajustado
registra qual população foi usada, e isso viaja para o resultado.

É **a mesma Forma C da Q3** e o tipo-em-dois-estados do scikit-learn. Q3 e Q13 podem ser uma
decisão só.

**Nas três formas**, a parte "visível e escolhível" da pergunta exige a mesma coisa, e nenhuma
dá de graça: **a população usada tem que aparecer no resultado**. Hoje não aparece em nenhum
dos dois caminhos, e isso é decisão do contrato de saída (§16 Q9, outra fatia).

---

## O achado transversal desta fatia

Quatro das seis células — **Q1, Q3, Q12 e Q13** — desembocam no mesmo lugar por caminhos
independentes:

- **Q1:** `sweep` e `deployment` são os maiores consumidores do estado da política e não são a
  política.
- **Q3:** calibração é derivada de premissa + regras + schema + base, e não é declarável em
  nenhuma das quatro gavetas.
- **Q11:** o estágio quer derivados do conjunto (máscara, bin), não campos.
- **Q12/Q13:** o papel precisa ser amarrado a uma coluna, e a população precisa ser
  escolhida — as duas coisas só existem quando as regras encontram a base.

O padrão: **o objeto que representa o encontro de schema + regras + premissas + base não
existe**. O diagnóstico "os 13 campos estão no grupo errado" é verdadeiro e insuficiente —
separar os campos sem criar esse objeto redistribui a teia (Forma A da Q1) ou reconstrói o god
object (Forma B).

Isso é insumo direto de #117 e é o que esta fatia entrega de mais forte. **Não é veredito:**
o mapa pode decidir que o encontro é um argumento de função e não um tipo — foi o caminho do
scikit-learn, medido na Lente A. Mas ele precisa decidir isso explicitamente, porque hoje o
encontro acontece espalhado em `simulation.py`, `stages.py`, `expressions.py` e `sweep.py`,
cada um resolvendo sua parte por conta.

## Assimetrias registradas

Onde a medição não mostrou empate, por decisão de método:

- **Q7:** `dataclasses.replace` é nativo e já praticado em 17 tipos do pacote; mata §4 e §3.1
  juntos. `.with_()` por tipo reproduz §10. As formas não empatam.
- **Q12:** só a Forma A (referência por papel) passa o teste de vazamento; B e C são as duas
  que o pacote já tentou, e o custo das duas está medido no código de hoje.

## Cruzamento com o levantamento

| §16 | § do `architecture-critique.md` | Card a jusante |
|---|---|---|
| 1 | §1 | #117 |
| 3 | §2 | #116, #119 |
| 4 | §2.3 | #119, #124 |
| 7 | §4 | #120, #129, #133 |
| 11 | §7 | #117, #118, #129 |
| 12 | §8 | #118 |
| 13 | §9 | #119, #131 |

## O que esta fatia não cobriu

- **§16 15, 16** — núcleo funcional / casca imperativa (`print_*` no core, `np.random` global).
- **§16 6, 9, 10, 20** — contrato de saída, coerção na fronteira, ausência como código,
  vocabulário único.
- **§16 8** — a linha entre conveniência e silêncio (§5, inferência silenciosa como classe).
- **§16 5, 14** — round-trip e o peso do `Expression` DSL contra polars/ibis.
- **§16 19** — estratégias de busca quando a grade não cabe (CART), com a ressalva do alvo
  móvel.

Vivem em ticket próprio, graduado de #134.
