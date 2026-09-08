# Quebra em tickets — implementação da v0.6

> **Insumo:** `docs/engine/spec/v06-architecture.md`.
> **Origem:** três leituras independentes da spec (uma minha, duas de agentes que não viram nenhuma proposta), mais uma rodada de refino cruzado. As quatro divergências que sobreviveram foram adjudicadas e estão registradas na §Adjudicações.
> **Escopo:** o Studio está fora, inteiro — ruling do dono, e ele pode ser descontinuado.

## A decisão estrutural: a superfície nova nasce ao lado

`src/pycreditools/engine/` cresce sem tocar em `policy.py`, `simulation.py`, `sweep.py`. É **expand–contract no nível do pacote**, e é o que torna fatia vertical possível.

**A evidência que fecha o caso:**

- `policy.py:105` é `def filter(self, name: str, condition: Any)` — `name` **posicional primeiro**. `.filter(col("age") >= 18)` sob a assinatura de hoje liga a `Expression` em `name` e morre por `condition` faltando. **Não é ampliação de assinatura, é colisão.**
- `policy.py:22-23` tem `applicant_id_col` e `score_cols` como os **dois primeiros campos obrigatórios sem default** — **todo sítio de construção de política quebra no mesmo commit**, não só os que passam `score_cols` por nome.
- Medido: `score_cols` 118 sítios em `src` do núcleo / 104 em `tests`; `current_hired_col` 31/20; `method=` 95 em `tests` do núcleo (mais 40 em `tests/studio/`).

**Não contradiz a regra do corte do #124.** Ela governa o **release publicado** — *"adiar qualquer um significa uma segunda quebra dura depois"*, e a unidade que ela protege é a versão que sai. Doze tickets dentro de uma versão não são duas versões.

**O que garante que a contração não seja adiada**, e é estrutural:

1. Nada é publicável antes dela — o único ticket que empacota e versiona é o último, bloqueado pela contração.
2. A contração está no caminho crítico único: bloqueada por todos, bloqueando o release.
3. O ticket de inventário não fecha com a suíte velha viva.
4. Tripwire: teste que falha se as duas superfícies coexistirem depois da contração.

**`_kernels/`, `expressions.py` e `sample_data.py` são compartilhados, não duplicados** — e o compartilhamento de `expressions.py` é **somente leitura**: `CalibratedExpression` é usada por `stages.py:326-341` e `tests/test_enhanced.py:283` da árvore velha, e só morre na contração.

**Três ganhos colaterais medidos:** os ~95 sítios de `method=` e os 104 de `score_cols` em `tests` **não são migrados — são deletados** com a suíte velha; o harness de paridade passa a importar as duas engines de **um checkout só** (o `validation/README.md:14-20` monta hoje dois worktrees com um venv cada, rodando em subprocesso); e o nome `engine/` executa de graça o layout `docs/engine/` que a §9.3 lista como dívida nunca executada.

---

## Os tickets

### 1 — Os ADRs das decisões congeladas
**Bloqueado por:** nada. **Corre em paralelo desde o dia zero.**
**Entrega:** os ADRs de #117, #118, #119, #120, #121, #122, #125, #126, #127, #129, #139, #142, #145, #152, #155, mais o **ADR de layout** — cuja numeração 0012 o #114 reservava e o contrato de saída tomou. Cada um registra o *porquê*, imutável, a partir da spec e do card de origem.
**Tamanho:** M.
**Por que ticket e não critério distribuído:** eles **não mapeiam 1:1 nos slices** (o #120 atravessa dois tickets; o #117 atravessa todos) e registram decisões **já congeladas pela spec** — não dependem de uma linha de código. Escrevê-los cedo tem valor operacional: cada sessão que pegar um slice lê o *porquê* num arquivo em vez de escavar 36 cards.

### 2 — Semente, tolerância e rodadas pareadas
**Bloqueado por:** nada.
**Entrega:** `conftest.py` (o repo não tem nenhum) com política de semente vinda do fixture e não de `np.random.seed` global, helper de asserção *"dentro de k desvios, com k e n declarados"*, e helper de rodadas pareadas. O flake de `tests/test_sweep.py:147` (analítico × estocástico, n=4000, tolerância absoluta 0,05, sem semente) fica pinado ou em quarentena declarada.
**Tamanho:** S.
**Por que cedo:** a §6 diz que higiene de semente *"virou pré-requisito, não higiene"* — o #149 gastou 16 execuções a 3 MM para descobrir que 4,1 sd não era viés. Sem isto, todo teste dos tickets 6, 8, 10 e 14 nasce flake.

### 3 — O namespace, e o portão de artefato que enumera
**Bloqueado por:** nada.
**Entrega:** `src/pycreditools/engine/` criado e **inalcançável do topo `pct.` até a contração** — `__init__.py` intocado, `engine` fora do `__all__`, com teste em `tests/test_packaging.py` que falha se vazar. As duas seções que o **portão 4** exige no `CONTEXT.md`: *Language of the code* (já presente) e a **escada de remédios** (a §9.3 mede: ausente em todas as branches, e o #132 declarou que *"só está entregue quando a seção existir no arquivo"*). Denylist do vocabulário morto, pegando carona no `pre-commit` que o repo ainda não tem.
E o portão de artefato passa a **enumerar arquivos, não confiar em citação**: as duas seções, os 16 ADRs do ticket 1, e os três arquivos de teste-evidência.
**Tamanho:** S+.
**Achado que motiva a enumeração:** `tests/test_swap_in_anchor_follows_declaration_order.py` — que a §6 cita como *"modelo executável já versionado"* e o #124 lista como teste que o portão pode consumir — **não está na `release/v0.6` nem na branch corrente**. Existe num commit só, `2725ac8`, alcançável apenas de `origin/claude/oie-5ffmh8`. É o mesmo modo de falha que criou o portão 4.

### 4 — Declarar: os quatro tipos, a AST pura e o round-trip
**Bloqueado por:** 3.
**Entrega:** o bloco de declaração da §2.2, escrito e serializável. `DataSchema` com a amarra (`approved` declarado ⇒ `hired` obrigatório); `CreditPolicy` com `.filter(expr, *, draw=, label=)`, label com default estrutural derivado da AST e erro duro nos três casos; `Premise` com os cinco campos, a amarra da `lens`, e os dois erros duros; `Study(schema, policy, premise, *, seed, name)` com o `repr` que é inventário. **Congelamento fundo** — frozen até a folha, `__post_init__` normalizando para `MappingProxyType`/`tuple` (hoje **nenhum `Stage` é dataclass**) — e o **mecanismo de `to_dict`/`from_dict` dirigido pela assinatura**, com callable recusado **no construtor**, não na serialização.
**Tamanho:** L.
**Nota:** o mecanismo de round-trip vem para cá porque é a **observação mais barata** de três coisas que este ticket tem que provar de qualquer jeito — congelamento fundo, AST pura e callable inexprimível — e porque dirigido pela assinatura significa que os campos que a `Premise` ganha no ticket 6 serializam de graça. **As duas unidades** (`export_rules`/`export_study`) **não** vêm: elas carregam a régua de rating e a premissa inteira, que só ficam de pé nos tickets 6 e 12.

### 5 — Rodar: `simulate(study, df)` standalone, e o funil sai como tabela
**Bloqueado por:** 2, 4.
**Entrega:** o tiro traçante. Base sem livro incumbente, política de N `.filter`, `Premise(take_up=0.7, outcome_from="market_default")` — o cenário A da §4.4 — atravessando: bind (presença, domínio 0/1, cadeia, zero coerção, linha malformada recusa a base); `Protocol` de **um** membro `apply(df, ctx) -> Series` com `ctx` estreito, o que mata `policy: Any` (`stages.py:36`) e o ciclo de import **por construção**; o **ponto de montagem único**, com dtype determinado e `category` nunca `object`; a cadeia de domínio com as duas asserções e nulo fora do domínio; a cobertura como número; o sorteio por linha chaveado a (semente, posição, nome do sorteio). E `funnel_table(res)` em duas colunas — Stage e Rule — que é a demo.
**Esquema do motor: SEIS colunas.** `decision`, `contract`, `outcome`, `quadrant`, `study` e **`reason`** — `category`, **nula onde `decision == 1`**, escrita só no ponto de montagem.
**Tamanho:** XL. É a espinha; nasce com quatro camadas ou não nasce.

### 6 — O livro do incumbente: lente, parcelling, stress e a população que calibra
**Bloqueado por:** 5.
**Entrega:** schema completo, quadrantes por decisão, keep-in observado, swap-in modelado, ordem causal contrato→desfecho. A `lens` declarada substitui a cascata `resolve_calibration_score_col` (`stages.py:158`) — **o kernel continua exigindo o eixo** (`_kernels/calibration.py`, `ref_scores`); o que morre é o ponteiro. `calibrate_on` governando **bordas E taxas** com a mesma população (hoje `calibration_base` governa só as bordas, `simulation.py:745-748`, e as taxas saem de `cal_scores=keep_in_scores` **cravado**, `:751`). `take_up` e `stress` nos três modos, com a escada indexando os baldes da lente. `outcome_from` no modo nó, que sorteia por ser hipótese. `n_inversions` e `no_overlap_fraction` nascem como números do portador.
**Tamanho:** L.
**Morrem aqui:** a cadeia de precedência silenciosa (`simulation.py:682` → `:691`, com `except Exception: pass`, → `:723`); o `max(axis=1)` de `:571-583` e o `UserWarning` dele; `MonotonicStress`, re-endereçado como nó de `outcome_from` porque **ignora `pd_col`** (`stress.py:96-97`) e nunca foi inflação.

### 7 — A mesa: `.filter(expr, draw=True)`
**Bloqueado por:** 5.
**Entrega:** o único item de funcionalidade nova da v0.6.0. Estágio probabilístico de decisão que sorteia também no caminho determinístico e **conta na taxa de aprovação publicada** — verificável com o número medido: 42,56% sem a mesa contra 38,52% com, reprovando 4,04% da base. `decision` continua 0/1 duro.
**Tamanho:** S — o maquinário é o sorteio chaveado, que já aterrissou no 5.
**Por que ticket próprio:** isolado, o risco do único item que não é decomposição fica visível; fundido na espinha, some dentro de um XL.

### 8 — `tradeoff`: o contrato da grade, e ele é exato
**Bloqueado por:** 6.
**Entrega:** um verbo de grade só, coordenada com **label cru**, as três métricas, as três gêmeas `baseline_*` medidas uma vez por chamada, e os dois denominadores que não são deriváveis. `by=` **já nasce como separação na hora de contar, nunca picotando a base**. Colisão label × coluna de grupo = erro duro; `ranges=` sobre estágio composto ou comparação contra coluna = erro duro, na varredura e não no bind.
**Portão 2, primeira metade:** um ponto colhido da grade bate com a política simulada à mão — declarado como **teste de equivalência costura 2 ≡ costura 1, exceção nomeada à DoD 3**.
**Tamanho:** L.

### 9 — `choose(grid, criterion=, by=)`
**Bloqueado por:** 8. **Roda em paralelo com o 10.**
**Entrega:** os três critérios — `pareto` com eixos declarados por default literal, `hold_approval`/`hold_default` devolvendo **os dois pontos que ladeiam** o vigente, sem tolerância nenhuma. `maximize=`/`minimize=` fora do Pareto = erro duro; vigente fora da faixa varrida = erro duro na língua do leitor. Mais `plot_tradeoff(grid, criterion=)`.
**Tamanho:** M — é a costura 3, *"tabela → tabela, testável sem dado"*.

### 10 — A passada única: nunca picote a base, e o caminho rápido na AST
**Bloqueado por:** 8.
**Entrega:** o mesmo contrato público do 8, com o miolo trocado — base ordenada uma vez, corte virando posição por `searchsorted`, totais corridos **nos dois sentidos, cada um na sua varrida, nunca por subtração**, e o grupo como mais um eixo do mesmo contador. Caminho rápido rechaveado na propriedade estrutural que a classe `CutoffStage` só representava por acidente (`optimization.py:144-150`).
**Portão 2, segunda metade:** **quatro** testes de exatidão, não dois — o produto cruzado dos dois knobs que movem população, `calibrate_on` × `take_up` —, e o teto de **≤1,25×** re-derivado no pior canto (`keep_in` + `"binned"`), porque o #149 o mediu **só sobre a recalibração da régua score→PD**. Se estourar, é dívida com portão no molde do #139, não licença para afrouxar. E os 13,9× com 300 lojas **deixam de existir** em vez de serem otimizados.
**Tamanho:** L.

### 11 — Ler: as quatro tabelas, a coleção de `Study` e a coluna `study`
**Bloqueado por:** 6.
**Entrega:** `simulate` aceitando coleção de `Study` — **aridade entra = aridade sai**, devolvendo sequência de portadores. A **tabela longa é produzida pelos verbos de leitura**: `delta_table(results, *, baseline=)` em formato longo `study × metric × value`, com baseline default sendo o cenário atual derivado da coluna `approved`. `quadrant_table` carrega os números do degrau 3 — cobertura, `n_inversions`, `no_overlap_fraction` —, porque as linhas dele **são** as populações. `swap_in_table(by=)`. `study` como `category` em toda tabela. `visualization.py` com import preguiçoso (medido: `import pycreditools` = 2294 ms, seaborn = 1105 ms). Escopo de `name`: numeração dentro da chamada de verbo, pulando rótulo tomado; duplicata na coleção é erro duro.
**Tamanho:** M.
**Verificável** rodando os quatro cenários da §4.5 e concatenando.

### 12 — Sugerir, aplicar, publicar: rating, deployment e as duas unidades
**Bloqueado por:** 4, 6.
**Entrega:** `suggest_rating(df, *, score, by=) -> RatingRule` (tupla cruza scores; comparar N candidatos é `for`), `apply_rating(rule, df, *, seed=)`, e **as duas unidades de serialização** — `export_rules(policy, *, rating=None)` e `export_study(study)`, com `load_*`, agora que a régua e a premissa existem. A régua exportada é **corte puro**; o esquema da borda ganha `rating` minúsculo, sob demanda. Produção pontua base nova sem premissa — roda a metade 1 e para.
**Morrem:** os quatro `predict`, `fit_risk_groups`, `fit_pairwise_risk_groups`, `ScreeningRecipe`/`ScreeningResult`, o `params: dict` write-only, a varredura `for s in range(0,1001)` que exporta regra errada em silêncio fora de 0–1000, o teto `.get(rat, 5)` que devolve 5 faixas de uma régua de 6, e os mocks de `deployment.py:419-434` — que não eram inertes: `approved = 1` **esvaziava o swap-in**.
**Tamanho:** L (`screening.py` 711 + `deployment.py` 473 + `grouping.py` 445).

### 13 — A suíte do Studio sai do portão verde
**Bloqueado por:** nada.
**Entrega:** `tests/studio/` deselecionado do `pytest` default, com a razão escrita e um item de backlog nomeado. Os arquivos **ficam em git** — são a única descrição versionada do que o Studio consumia.
**Tamanho:** S.
**Por quê:** `pyproject.toml:87-89` tem `testpaths = ["tests"]` e `tests/studio/conftest.py:1-8` importa `ColumnRoles`, `detect_roles` e `build_policy` — os três morrem. Quebram **na coleção**, não na asserção: sem isto, o vermelho deles afoga os portões da §6.

### 14 — Inventário da malha antiga: portar, não consertar
**Bloqueado por:** nada; **fecha** depois de 5, 6, 8, 10, 11, 12.
**Entrega:** o fechamento da DoD 1, reformulado para a coabitação. Um registro com uma linha por função de teste das 26 dos `tests/` do núcleo, respondendo as duas perguntas — *qual contrato eu guardo, e ele ainda existe?* / *eu ficaria vermelho se ele fosse violado?* — e classificando: **contrato portado no ticket N** / **contrato morreu com o card X** / **contrato vivo e sem guarda em lugar nenhum**. A terceira categoria vira teste novo antes da contração.
**Primeiro item, e não é limpeza de fim:** portar `test_sweep_rebuild_preserves_stage_fields.py`, `test_sweep_hard_filter_ceiling.py` e `test_swap_in_anchor_follows_declaration_order.py` para o namespace novo. Eles importam nomes da árvore velha (`CreditPolicy`, `CutoffStage`, `RateStage`, `run_sweep`, `TradeoffAnalyzer`, `optimize_cutoffs`), e **sob coabitação ficariam xfailando contra a engine velha para sempre — o sinal de portão que o #124 desenhou nunca dispararia**.
**Tamanho:** L.
**Nota:** "deletar a suíte velha" é *mais forte* que "reler", **desde que a leitura aconteça**. As 190 funções são lidas como **inventário de contratos a portar**, não como código a consertar. Sem essa reformulação escrita, deletar vira o atalho e a DoD morre calada.

### 15 — Paridade contra a v0.5 na forma (B): `validation/` reescrito
**Bloqueado por:** 10, 12.
**Entrega:** o harness parametrizado **por forma de política** — as cinco da §6, incluindo as duas que batem exato —, porque `validation/measure_main.py` roda hoje **exatamente a linha que bate exato** e atesta paridade que não existe nas outras quatro. Três camadas, nenhuma célula sem asserção. Mapa de-para explícito dos renomeios, senão viram falso positivo em massa. Roda serial.
Fecha as três dívidas *"a medir"*: a faixa da **população do baseline** (a primeira que diverge em **toda simulação**, não só na varredura), a do sorteio chaveado, e a da morte do proxy `notna()` no denominador. Herda a obrigação de trazer o `test_swap_in_anchor...` para a branch antes de consumi-lo. **Nenhuma entrada de categoria (a) sem faixa medida sai do vermelho.**
**Tamanho:** L.

### 16 — Contração: o pacote novo é o pacote
**Bloqueado por:** 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15.
**Entrega:** num commit, morrem `policy.py` (311), `stages.py` (492), `simulation.py` (820), `sweep.py` (317), `optimization.py` (261), `analysis.py` (111), `stress.py` (127), os consumidores velhos de `screening`/`grouping`/`deployment`, a suíte velha já auditada, `is_sim_col` inteiro, os 16 `warnings.warn` do núcleo com o `CalibrationReliabilityWarning` incluso, e `CalibratedExpression`/`Expression.calibrated()` (`expressions.py:70`), que só sobreviveram porque o `RateStage` os usava. O `__init__.py` passa a exportar ~20 nomes **agrupados pelos três estágios** — declarar / calcular / ler —, `help(pycreditools)` imprime as duas linhas da espinha, e todo verbo aponta o seguinte.
**Tripwire:** teste que falha se `pycreditools.CreditPolicy` e `pycreditools.engine.CreditPolicy` coexistirem depois deste ticket.
**Tamanho:** XL.

### 17 — Masterclass, CHANGELOG e os cinco portões
**Bloqueado por:** 16.
**Entrega:** a masterclass reescrita na superfície nova — que **é** o teste de ergonomia da família, e cuja §6 encolhe para uma chamada com `by="region"` mais bisseção em pandas. CHANGELOG sem lápides, com a redistribuição semântica explicada campo a campo. A nota do sorteio com os dois números — **0,018 p.p.** em rodada única, **0,41 p.p.** entre rodadas semeadas em paralelo —, corrigindo `README.md:419-423`, que hoje diz que o pacote *"prevents stochastic noise"* e aponta para o lado errado. O checklist dos cinco portões assinado, com o portão 4 estendido ao conjunto enumerado do ticket 3. **É o único ticket que empacota e versiona.**
**Tamanho:** M.

---

## Adjudicações

As quatro divergências que sobreviveram ao refino cruzado, e a razão de cada veredito.

### 1. `simulate` — **aridade entra = aridade sai**

A spec se contradizia: a §4.10 diz que `simulate([s1, s2, s3], df)` devolve a tabela longa; a §4.7 escreve o exemplo canônico como `delta_table([res_a, res_b], baseline=res_hoje)` — **uma lista de portadores**. As duas não podem estar certas.

**Vale:** `simulate` devolve portador ou sequência de portadores; coleção de um elemento devolve sequência de um, sem caso especial. **A tabela longa é produzida pelos verbos de leitura.** Isso salva a régua *"tipo de saída previsível"* e preserva inteiro o conteúdo da emenda §9.1 nº 1 — *"tabela longa, uma linha por estudo, sem tipo contêiner"* fala do **produto**, não do tipo de retorno. A alternativa é retorno polimórfico, que é exatamente o que a régua de aceite proíbe.

**Emenda à spec:** §4.10.

### 2. ADRs — **ticket próprio, sem bloqueador**

Contra: *"13 ADRs escritos por quem não tomou as decisões é prosa, e adiar para vaga sem dono é repetir a falha da §9.3"*.
A favor, e vence: eles **não mapeiam 1:1 nos slices** e registram decisões **já congeladas pela spec** — quem tem o *porquê* fresco é a spec, não o implementador. E sem bloqueador eles correm desde o dia zero, o que inverte o argumento contrário: em vez de vaga posterior sem dono, é a **primeira** coisa com dono.

O mecanismo do lado contrário **fica**: checklist enumerado por card, com cheque mecânico (ticket 3).

**Correção de fato registrada:** o **portão 4 não cobre ADR** — ele cobra as seções do `CONTEXT.md`. Quem cobra ADR é o #112 e a §9.3. O portão é **ampliado** no ticket 3, não fingido como já coberto.

### 3. `bins` inerte — **reportado no `repr`, não erro duro**

Para distinguir *"declarei 5"* de *"veio 5 por default"* é preciso sentinela (`bins: int | None = None`) — **e isso mata o `5` literal na assinatura**, que a §4.4 e a §4.11 exigem para o mecanismo ser visível no `help()`. **Não dá para ter os dois.**

**Vale:** o literal fica; `bins` declarado sem eixo que discretize é **reportado no `repr`** — *"bins=10 (não consumido)"* —, usando o precedente já escrito para a lente não referenciada pela política (§4.5). Não avisa, não recusa, nada a silenciar.

**A assimetria com `lens` fica declarada e tem causa:** `lens` não tem default, então declarar é distinguível; `bins` tem, e não é.

### 4. Unidades de serialização — **mecanismo cedo, unidades depois**

**Vale:** congelamento fundo e o mecanismo de `to_dict`/`from_dict` dirigido pela assinatura vão para o ticket 4, porque o round-trip é a observação mais barata do que aquele ticket tem que provar de qualquer jeito. **As duas unidades vão para o 12**: `export_rules` carrega a régua de rating e `export_study` carrega a premissa inteira — escrevê-las no ticket 4 é escrever contra uma `Premise` pela metade e reescrever duas vezes.

---

## Desvios da ordem do #124, e a razão

A ordem do card é **B1 → B2 → B3 → B4 → B6 → B5 → B7 → B8**. Quatro desvios, todos com causa.

- **B2 não é bloco** — está partido entre os tickets 4 e 5. A metade declarativa do estágio é inseparável do tipo que a carrega; a metade executável é inseparável do laço de funil. Um B2 autônomo seria fatia horizontal: um `Protocol` que nada implementa e um label que nada endereça. O #129 já dá o argumento — `stage.apply()` tem **dois** chamadores contra **20 `isinstance`**: *"o polimorfismo era fingido"*.
- **B4 entra na espinha.** O ponto de montagem único tem que existir **antes** de a primeira frame ser escrita; se a espinha escrever colunas espalhadas e o B4 vier depois, o B4 reescreve o que a espinha acabou de escrever.
- **O sorteio chaveado fica na espinha.** Depende de `Study.seed`, que não existe antes; e a §4.6 registra que semente obrigatória e chaveamento *"foram decididos juntos"*, porque o chaveamento é o substituto do que se perde com a morte do analítico.
- **B5 vira dois tickets** (8 e 10), porque o portão 2 tem **duas cabeças** — exatidão **e** teto de custo — e o #149 mediu que *a distância entre a melhor e a pior forma de recalibrar é maior que a distância entre a melhor forma e não recalibrar*. Sem um caminho correto dentro do pacote, o teto não tem contra o que ser medido. E o `choose` desgruda: é costura tabela→tabela, e segurá-lo atrás de otimização de performance é dependência falsa.

**Mantidos:** B6 antes de B5 (*"a exatidão da grade depende de qual população calibra"*); B8 por último entre os construtivos, como consumidor de superfície congelada; e a DoD correndo em paralelo desde o começo (tickets 1, 2, 3, 13 e 14 sem bloqueadores).

**O analítico não tem ticket.** Ele **nunca nasce** em `engine/`: os 19 ramos não são portados, são não-escritos. O caso mais claro é `simulation.py:302-307`, os dois ramos de `defaulted` em que só um mascara — a spec registra que o ramo seguro *"sobrevive por sorte, não foi desenhado — sobrou"*. Sob o ponto de montagem único não há dois ramos para escolher. O único contato com `method=` no projeto é o **adaptador v0.5 do harness de paridade** (ticket 15), que chama a API velha do lado velho.

Um `method=` aceito e inerte foi considerado e **recusado**: é argumento público que não faz nada, e a §4.4 mata `RateStage.base_rate` e o `params: dict` escrevendo a régua em voz alta — **"argumento obrigatório e inerte é a patologia, não a cerimônia"**.
