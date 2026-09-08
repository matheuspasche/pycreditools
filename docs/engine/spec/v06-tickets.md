# Quebra em tickets — implementação da v0.6

> **Insumo:** `docs/engine/spec/v06-architecture.md`.
> **Origem:** três leituras independentes da spec (uma minha, duas de agentes que não viram nenhuma proposta), mais uma rodada de refino cruzado e **uma revisão a frio da lista pronta**, feita por um quarto agente que abriu a árvore e conferiu ~50 afirmações factuais. As divergências adjudicadas estão na §Adjudicações; o que a revisão derrubou está corrigido em linha.
> **Números medidos nesta árvore, não citados de memória.** A revisão encontrou **nove** afirmações falsas, das quais três eram contagens de sítios reescritas com rótulo trocado e quatro eram citações `arquivo:linha` deslocadas por poucas linhas. Todas corrigidas. É o mesmo modo de falha que criou o portão 4, e a lição é a dele: **citação não é evidência.**
> **Escopo:** o Studio está fora, inteiro — ruling do dono, e ele pode ser descontinuado.

## A decisão estrutural: a superfície nova nasce ao lado

`src/pycreditools/engine/` cresce sem tocar em `policy.py`, `simulation.py`, `sweep.py`. É **expand–contract no nível do pacote**, e é o que torna fatia vertical possível.

**A evidência que fecha o caso:**

- `policy.py:105` é `def filter(self, name: str, condition: Any)` — `name` **posicional primeiro**. `.filter(col("age") >= 18)` sob a assinatura de hoje liga a `Expression` em `name` e morre por `condition` faltando. **Não é ampliação de assinatura, é colisão.**
- `policy.py:21-22` tem `applicant_id_col` e `score_cols` como os **dois primeiros campos obrigatórios sem default** — **todo sítio de construção de política quebra no mesmo commit**, não só os que passam `score_cols` por nome.
- Medido nesta árvore, **núcleo = `src/` sem `gui/` e sem `studio/`**: `score_cols` **77** sítios em `src` do núcleo / **104** em `tests`; `current_hired_col` **17/20**; `method=` **95** em `tests` do núcleo (mais 40 em `tests/studio/`). Para referência, `score_cols` em `src` **inteiro** é 137 — que é o número que a §7 da spec cita, e não o do núcleo.

**Não contradiz a regra do corte do #124.** Ela governa o **release publicado** — *"adiar qualquer um significa uma segunda quebra dura depois"*, e a unidade que ela protege é a versão que sai. Doze tickets dentro de uma versão não são duas versões.

**O que garante que a contração não seja adiada**, e é estrutural:

1. Nada é publicável antes dela — o único ticket que empacota e versiona é o último, bloqueado pela contração.
2. A contração está no caminho crítico único: bloqueada por todos, bloqueando o release.
3. O ticket de inventário não fecha com a suíte velha viva.
4. Tripwire: teste que falha se as duas superfícies coexistirem depois da contração.

**`_kernels/`, `expressions.py` e `sample_data.py` são compartilhados, não duplicados** — e o compartilhamento de `expressions.py` é **somente leitura**. Censo de `CalibratedExpression` na árvore velha: construída em `stages.py:329` e `stages.py:426` (o caminho `observed_col` do `RateStage`), referenciada em `:328`, `:341`, `:376`, `:399`; nos testes, `tests/test_enhanced.py:283` e a classe `TestCalibratedExpressionFallback` inteira (`tests/test_bugfixes.py:390`), mais `:365`. Nenhum sítio escreve nela; **só morre na contração**.

**Três ganhos colaterais medidos:** os ~95 sítios de `method=` e os 104 de `score_cols` em `tests` **não são migrados — são deletados** com a suíte velha; o harness de paridade passa a importar as duas engines de **um checkout só** (o `validation/README.md:14-20` monta hoje dois worktrees com um venv cada, rodando em subprocesso); e o nome `engine/` executa de graça o layout `docs/engine/` que a §9.3 lista como dívida nunca executada.

---

## Publicado no tracker

Os 17 são **sub-issues de #156** (a spec), criados em ordem de dependência para que cada aresta aponte um identificador real. Label `ready-for-agent` em todos — eles são agarráveis por construção.

| ticket | issue | ticket | issue |
|---|---|---|---|
| 1 — ADRs | #157 | 10 — passada única | #169 |
| 2 — semente | #158 | 11 — ler | #166 |
| 3 — namespace | #159 | 12 — sugerir/publicar | #167 |
| 4 — declarar | #161 | 13 — Studio fora do portão | #160 |
| 5 — rodar | #162 | 14 — inventário | #170 |
| 6 — livro do incumbente | #163 | 15 — paridade | #171 |
| 7 — a mesa | #164 | 16 — contração | #172 |
| 8 — `tradeoff` | #165 | 17 — release | #173 |
| 9 — `choose` | #168 | | |

**A frente do dia zero são quatro:** #157, #158, #159 e #160 — nenhum tem bloqueador.

---

## Os tickets

### 1 — Os ADRs das decisões congeladas
**Bloqueado por:** nada. **Corre em paralelo desde o dia zero.**
**Entrega:** os ADRs de #117, #118, #119, #120, #121, #122, #125, #126, #127, #129, #139, #142, #145, #152, #155, mais o **ADR de layout** — cuja numeração 0012 o #114 reservava e o contrato de saída tomou — e o **ADR do "critério de escolha não é do pacote"**, que a §9.3 lista à parte e mede como *"nunca escrito, embora declarado como entregável"*. Nomeá-lo explicitamente é obrigatório porque a enumeração é por número de card e ninguém consegue verificar, lendo a lista, se ele está coberto por #122 ou #125. Cada um registra o *porquê*, imutável, a partir da spec e do card de origem.
**Tamanho:** M.
**Por que ticket e não critério distribuído:** eles **não mapeiam 1:1 nos slices** (o #120 atravessa dois tickets; o #117 atravessa todos) e registram decisões **já congeladas pela spec** — não dependem de uma linha de código. Escrevê-los cedo tem valor operacional: cada sessão que pegar um slice lê o *porquê* num arquivo em vez de escavar 36 cards.

### 2 — Semente, tolerância e rodadas pareadas
**Bloqueado por:** nada.
**Entrega:** `tests/conftest.py` (**a suíte do núcleo não tem nenhum** — o único `conftest.py` da árvore é `tests/studio/conftest.py`, que o ticket 13 trata) com política de semente vinda do fixture e não de `np.random.seed` global, helper de asserção *"dentro de k desvios, com k e n declarados"*, e helper de rodadas pareadas. O flake de `tests/test_sweep.py:147` (analítico × estocástico, n=4000, tolerância absoluta 0,05, sem semente) fica pinado ou em quarentena declarada.
**Tamanho:** S.
**Por que cedo:** a §6 diz que higiene de semente *"virou pré-requisito, não higiene"* — o #149 gastou 16 execuções a 3 MM para descobrir que 4,1 sd não era viés. Sem isto, todo teste dos tickets 6, 8, 10 e 14 nasce flake.

### 3 — O namespace, e o portão de artefato que enumera
**Bloqueado por:** nada.
**Entrega:** `src/pycreditools/engine/` criado e **inalcançável do topo `pct.` até a contração** — `__init__.py` intocado, `engine` fora do `__all__`, com teste em `tests/test_packaging.py` que falha se vazar. As duas seções que o **portão 4** exige no `CONTEXT.md`: *Language of the code* (já presente) e a **escada de remédios** (a §9.3 mede: ausente em todas as branches, e o #132 declarou que *"só está entregue quando a seção existir no arquivo"*). Denylist do vocabulário morto, pegando carona no `pre-commit` que o repo ainda não tem.
E **traz `2725ac8` para a branch** — cherry-pick de `origin/claude/oie-5ffmh8`, sem dependência nenhuma, deixando `tests/test_swap_in_anchor_follows_declaration_order.py` presente no `HEAD`. Ele entra **xfailando contra a árvore velha**, o que é aceito: quem o reescreve contra a superfície nova é o ticket 14.
**Tamanho:** S+ — e o `pre-commit` **é parte da entrega**, não carona: o repo não tem `.pre-commit-config.yaml`, então este ticket o introduz.
**O que este ticket NÃO entrega:** o portão enumerador em si. Ele **especifica** a lista fechada; quem a executa como cheque de release é o **ticket 17**, onde o checklist dos cinco portões é assinado. A razão é aresta: a lista inclui os 16 ADRs do ticket 1, e ligar o portão aqui deixaria o ticket 3 vermelho até o 1 fechar — um ticket sem bloqueador que não aterrissa verde.
**Achado que motiva a enumeração:** `tests/test_swap_in_anchor_follows_declaration_order.py` — que a §6 cita como *"modelo executável já versionado"* e o #124 lista como teste que o portão pode consumir — **não está na `release/v0.6` nem na branch corrente**. Existe num commit só, `2725ac8`, alcançável apenas de `origin/claude/oie-5ffmh8`. É o mesmo modo de falha que criou o portão 4.

### 4 — Declarar: os quatro tipos, a AST pura e o round-trip
**Bloqueado por:** 3.
**Entrega:** o bloco de declaração da §2.2, escrito e serializável. `DataSchema` com a amarra (`approved` declarado ⇒ `hired` obrigatório); `CreditPolicy` com `.filter(expr, *, draw=, label=)`, label com default estrutural derivado da AST e erro duro nos três casos; `Premise` com os **seis** campos — `lens`, `bins`, `calibrate_on`, `take_up`, `stress`, `outcome_from` —, a amarra da `lens`, e os dois erros duros; `Study(schema, policy, premise, *, seed, name)` com o `repr` que é inventário. **Congelamento fundo** — frozen até a folha, `__post_init__` normalizando para `MappingProxyType`/`tuple` (hoje **nenhum `Stage` é dataclass**) — e o **mecanismo de `to_dict`/`from_dict` dirigido pela assinatura**, com callable recusado **no construtor**, não na serialização.
**Mais dois verbos que a spec contrata e que são método de `CreditPolicy`/`Study`:** `set_stage(label, ...)` — o **único** movimento de builder que a §4.2 preserva, e é ele que endereça o label junto com `ranges=` —, e `vary` (§4.5), que *"recebe o encontro inteiro e pode sobrescrever qualquer ponto declarado — regra, schema ou premissa — desde que por derivação"*, com o ruling **"reconstruir não é variar"**.
**Os dois renders da §4.3, e a regra existe para impedir que divirjam:** `__repr__` faz round-trip; `pretty()` é apresentação e **nunca é parseado de volta**.
**O `repr` reconcilia os três espécimes parciais** espalhados pela spec, e os dois relatos do degrau 3 têm loci distintos: `bins` não consumido mora em `Premise.__repr__` (é intra-premissa); `lens` não referenciada pela política mora em `Study.__repr__` (só lá dá para saber).
**Tamanho:** L.
**O mecanismo da DoD 2 é deste ticket, e isto precisava estar escrito.** A §6 exige *"um mecanismo genérico de troca-um-campo dirigido pela assinatura do construtor"* e diz em voz alta que *"se a resposta for 'o chamador passa todos', o buraco continua aberto"*. **É a mesma maquinaria dirigida pela assinatura que dá o `to_dict`/`from_dict` — um mecanismo, três consumidores:** `to_dict`, `from_dict` e **`replace`**, o troca-um-campo. `set_stage` (acima) e o `ranges=` da varredura (tickets 8 e 10) são **chamadores** dele, não implementações paralelas — e é exatamente por serem chamadores que a família de bugs de reconstrução parcial fica **impossível por construção**, em vez de depender de cada sítio lembrar de passar todos os campos.
O teste que guarda isso é `test_sweep_rebuild_preserves_stage_fields.py`, reescrito no ticket 14; ele **passa sozinho quando o mecanismo aterrissa**, que é como os 5 `xfail(strict=True)` foram desenhados.

**Natureza deste ticket, dita pelo nome:** ele **é o passo de *expand*** do expand–contract de pacote — não um tracer bullet, e não tem como ser: `simulate` só chega no 5. O teste de horizontalidade que reprovou o B2 não se aplica aqui pela mesma razão que o skill isenta o *expand* e o prefactoring. Escrito assim, quem revisar o ticket 4 para de exigir uma demo que não pode existir.
**Nota:** o mecanismo de round-trip vem para cá porque é a **observação mais barata** de três coisas que este ticket tem que provar de qualquer jeito — congelamento fundo, AST pura e callable inexprimível — e porque dirigido pela assinatura significa que os campos que a `Premise` ganha no ticket 6 serializam de graça. **As duas unidades** (`export_rules`/`export_study`) **não** vêm: elas carregam a régua de rating e a premissa inteira, que só ficam de pé nos tickets 6 e 12.

### 5 — Rodar: `simulate(study, df)` standalone, e o funil sai como tabela
**Bloqueado por:** 2, 4.
**Entrega:** o tiro traçante. Base sem livro incumbente, política de N `.filter`, `Premise(take_up=0.7, outcome_from="market_default")` — o cenário A da §4.4 — atravessando: bind (presença, domínio 0/1, cadeia, zero coerção, linha malformada recusa a base); `Protocol` de **um** membro `apply(df, ctx) -> Series` com `ctx` estreito, o que mata `policy: Any` (`stages.py:36`) e o ciclo de import **por construção**; o **ponto de montagem único**, com dtype determinado e `category` nunca `object`; a cadeia de domínio com as duas asserções e nulo fora do domínio; a cobertura como número; o sorteio por linha chaveado a (semente, posição, nome do sorteio). E `funnel_table(res)` **em três colunas — `Stage | Rule | Passed`** — que é a demo. (O *"duas colunas"* da §4.3 diz que **label e render são duas colunas em vez de uma string concatenada**; a contagem sai da tabela renderizada logo abaixo. Funil sem contagem não é funil.)
**Esquema do motor: SEIS colunas.** `decision`, `contract`, `outcome`, `quadrant`, `study` e **`reason`** — `category`, **nula onde `decision == 1`**, escrita só no ponto de montagem.
**As seis colunas EXISTEM aqui e passam a VALER no 6.** O cenário A é standalone, sem livro incumbente: `quadrant` fica degenerado e `contract` é `decision × 0.7` chapado. Isso é comportamento legítimo de tiro traçante, e tem que estar escrito — senão as seis colunas são lidas como seis contratos funcionando.
**Tamanho:** XL. É a espinha; nasce com quatro camadas ou não nasce.

### 6 — O livro do incumbente: lente, parcelling, stress e a população que calibra
**Bloqueado por:** 5.
**Entrega:** schema completo, quadrantes por decisão, keep-in observado, swap-in modelado, ordem causal contrato→desfecho. A `lens` declarada substitui a cascata `resolve_calibration_score_col` (`stages.py:158`) — **o kernel continua exigindo o eixo** (`_kernels/calibration.py`, `ref_scores`); o que morre é o ponteiro. `calibrate_on` governando **bordas E taxas** com a mesma população (hoje `calibration_base` governa só as bordas, `simulation.py:742-745`, e as taxas saem de `cal_scores=keep_in_scores` **cravado**, `:752`). `take_up` e `stress` nos três modos, com a escada indexando os baldes da lente. `outcome_from` no modo nó, que sorteia por ser hipótese. `n_inversions` e `no_overlap_fraction` nascem como números do portador.
**Bind das colunas da premissa, generalizado da §4.10:** `lens`, o nó de `take_up`, o nó de `stress` e a string-ou-nó de `outcome_from` **levantam duro no bind quando a coluna não existe, sem fallback**. É a regra que o `AggravationStress.factor_col` motivou — `if self.factor_col and self.factor_col in df.columns`, que troca a semântica para o fator escalar em silêncio quando o nome está errado. O ticket 5 é dono do bind dos papéis do schema; este é dono do bind da premissa.
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
**Grupo pequeno, contratado pela §4.8 e fácil de resolver errado:** *"roda todos; onde a premissa não engata, o número sai nulo, com a cobertura ao lado. Nem piso que levanta, nem exclusão calada, nem queda para o PD global — essa não é ausência de resposta, é resposta errada com cara de certa."* **Nulo com cobertura, e nada de piso.**
**Portão 2, primeira metade:** um ponto colhido da grade bate com a política simulada à mão — declarado como **teste de equivalência costura 2 ≡ costura 1, exceção nomeada à DoD 3**.
**Tamanho:** L.

### 9 — `choose(grid, criterion=, by=)`
**Bloqueado por:** 8. **Roda em paralelo com o 10.**
**Entrega:** os três critérios — `pareto` com eixos declarados por default literal, `hold_approval`/`hold_default` devolvendo **os dois pontos que ladeiam** o vigente, sem tolerância nenhuma. `maximize=`/`minimize=` fora do Pareto = erro duro; vigente fora da faixa varrida = erro duro na língua do leitor. Mais `plot_tradeoff(grid, criterion=)`.
**Tamanho:** M — é a costura 3, *"tabela → tabela, testável sem dado"*.

### 10 — A passada única: nunca picote a base, e o caminho rápido na AST
**Bloqueado por:** 8.
**Entrega:** o mesmo contrato público do 8, com o miolo trocado — base ordenada uma vez, corte virando posição por `searchsorted`, totais corridos **nos dois sentidos, cada um na sua varrida, nunca por subtração**, e o grupo como mais um eixo do mesmo contador. Caminho rápido rechaveado na propriedade estrutural que a classe `CutoffStage` só representava por acidente (`optimization.py:144-151`).
**Portão 2, segunda metade:** **quatro** testes de exatidão, não dois — o produto cruzado dos dois knobs que movem população, `calibrate_on` × `take_up` —, e o teto de **≤1,25×** re-derivado no pior canto (`keep_in` + `"binned"`), porque o #149 o mediu **só sobre a recalibração da régua score→PD**. Se estourar, é dívida com portão no molde do #139, não licença para afrouxar. E os 13,9× com 300 lojas **deixam de existir** em vez de serem otimizados.
**Tamanho:** L.

### 11 — Ler: as quatro tabelas, a coleção de `Study` e a coluna `study`
**Bloqueado por:** 6.
**Entrega:** `simulate` aceitando coleção de `Study` — **aridade entra = aridade sai**, devolvendo sequência de portadores. A **tabela longa é produzida pelos verbos de leitura**: `delta_table(results, *, baseline=)` em formato longo `study × metric × value`, com baseline default sendo o cenário atual derivado da coluna `approved`. `quadrant_table` carrega os números do degrau 3 — cobertura, `n_inversions`, `no_overlap_fraction` —, porque as linhas dele **são** as populações. `swap_in_table(by=)`. `study` como `category` em toda tabela. `visualization.py` com import preguiçoso (medido: `import pycreditools` = 2294 ms, seaborn = 1105 ms) — **o único pedaço não-vertical desta fatia**, puramente aditivo pela §7 ("custo zero", cauda aditiva), e por isso **o primeiro a sair se o 11 apertar**. Escopo de `name`: numeração dentro da chamada de verbo, pulando rótulo tomado; duplicata na coleção é erro duro.
**Tamanho:** M.
**Verificável** rodando os quatro cenários da §4.5 e concatenando.

### 12 — Sugerir, aplicar, publicar: rating, deployment e as duas unidades
**Bloqueado por:** 4, 6.
**Entrega:** `suggest_rating(df, *, score, by=) -> RatingRule` (tupla cruza scores; comparar N candidatos é `for`), `apply_rating(rule, df, *, seed=)`, e **as duas unidades de serialização** — `export_rules(policy, *, rating=None)` e `export_study(study)`, com `load_*`, agora que a régua e a premissa existem. A régua exportada é **corte puro**; o esquema da borda ganha `rating` minúsculo, sob demanda. Produção pontua base nova sem premissa — roda a metade 1 e para. **`suggest_hard_filters` é re-exportado de `engine/` intacto** (§4.9: *"já existe, intacto"*) — ele mora em `screening.py`, cujo `ScreeningRecipe`/`ScreeningResult` morrem aqui e cujos consumidores velhos morrem no 16; sem esta linha, a §4.9 fica com um verbo prometido e sem endereço no pacote novo.
**Morrem:** os quatro `predict`, `fit_risk_groups`, `fit_pairwise_risk_groups`, `ScreeningRecipe`/`ScreeningResult`, o `params: dict` write-only, as **duas** varreduras `for s in range(0, 1001)` — `deployment.py:319` e `deployment.py:380`, não em `grouping.py`/`screening.py` —, que exportam regra errada em silêncio fora de 0–1000, o teto `.get(rat, 5)` que devolve 5 faixas de uma régua de 6, e os mocks de `deployment.py:419-434` — que não eram inertes: `approved = 1` **esvaziava o swap-in**.
**Tamanho:** L (`screening.py` 711 + `deployment.py` 473 + `grouping.py` 445).

### 13 — A suíte do Studio sai do portão verde
**Bloqueado por:** nada.
**Entrega:** `tests/studio/` deselecionado do `pytest` default, com a razão escrita e um item de backlog nomeado. Os arquivos **ficam em git** — são a única descrição versionada do que o Studio consumia.
**Tamanho:** S.
**Por quê:** `pyproject.toml:87-89` tem `testpaths = ["tests"]` e `tests/studio/conftest.py:1-8` importa `ColumnRoles`, `detect_roles` e `build_policy` — os três morrem. Quebram **na coleção**, não na asserção.
**Correção de razão:** sob a coabitação que este documento decide, `tests/studio/` fica **verde durante os tickets 1 a 15** e só quebra na contração — a árvore velha está intocada até lá. Logo a razão **não** é *"o vermelho deles afoga os portões da §6"*; é **"bloqueia o 16"**. O efeito prático: ele é barato, fica onde está, e **não compete por prioridade no dia zero**.

### 14 — Inventário da malha antiga: portar, não consertar
**Bloqueado por:** nada; **fecha** depois de 5, 6, 8, 10, 11, 12.
**Entrega:** o fechamento da DoD 1, reformulado para a coabitação. Um registro com uma linha por função de teste dos 26 arquivos dos `tests/` do núcleo — **206 funções** (158 no nível do módulo + 48 métodos), 5.012 linhas, recontadas nesta árvore, respondendo as duas perguntas — *qual contrato eu guardo, e ele ainda existe?* / *eu ficaria vermelho se ele fosse violado?* — e classificando: **contrato portado no ticket N** / **contrato morreu com o card X** / **contrato vivo e sem guarda em lugar nenhum**. A terceira categoria vira teste novo antes da contração.
**Os três testes-evidência, e o item está partido em dois por uma razão de timing:**
- *Trazer o arquivo para a branch* — sem bloqueador, e mora no **ticket 3** (é cherry-pick de `2725ac8`).
- *Reescrever os três contra a superfície nova* — **aqui, e bloqueado por 5, 8 e 10.** Não é porte: `test_sweep_rebuild_preserves_stage_fields.py`, `test_sweep_hard_filter_ceiling.py` e `test_swap_in_anchor_follows_declaration_order.py` importam `CreditPolicy(applicant_id_col=…, score_cols=…)`, `CutoffStage`, `RateStage`, `run_sweep`, `TradeoffAnalyzer` e `optimize_cutoffs` — **nenhum dos seis existe na v0.6** —, e 3 dos 10 testes do teto parametrizam sobre `method=`, que a spec mata. É **reescrita contra `simulate`/`tradeoff`/`choose`**.

O diagnóstico continua valendo e é o que torna isto obrigatório antes da contração: **sob coabitação eles ficariam xfailando contra a engine velha para sempre, e o sinal de portão que o #124 desenhou nunca dispararia.**
**Tamanho:** L.
**Nota:** "deletar a suíte velha" é *mais forte* que "reler", **desde que a leitura aconteça**. As 206 funções são lidas como **inventário de contratos a portar**, não como código a consertar. (O 190/4.392/24 que circulava é o levantamento de 2026-08-14 citado pela spec; a árvore cresceu desde então, e a contagem errada é estimativa de tamanho errada.) Sem essa reformulação escrita, deletar vira o atalho e a DoD morre calada.

### 15 — Paridade contra a v0.5 na forma (B): `validation/` reescrito
**Bloqueado por:** 10, **11**.
**Correção de aresta:** a dependência do 12 é **falsa**. As cinco formas de política da §6 — `um .cutoff só`, `.filter`, `2+ scores cortados`, tupla de 4 scores, `calibration_score_col` declarado — **não tocam rating, `apply_rating`, `export_*` nem deployment**, que é tudo o que o 12 entrega. O que o harness precisa é da superfície por onde ele compara: `delta_table` / `quadrant_table` / `swap_in_table` e a coluna `study`, que aterrissam no **11**.
**Entrega:** o harness parametrizado **por forma de política** — as cinco da §6, incluindo as duas que batem exato —, porque `validation/measure_main.py` roda hoje **exatamente a linha que bate exato** e atesta paridade que não existe nas outras quatro. Três camadas, nenhuma célula sem asserção. Mapa de-para explícito dos renomeios, senão viram falso positivo em massa. Roda serial.
Fecha as três dívidas *"a medir"*: a faixa da **população do baseline** (a primeira que diverge em **toda simulação**, não só na varredura), a do sorteio chaveado, e a da morte do proxy `notna()` no denominador. O arquivo `test_swap_in_anchor...` já está na branch desde o ticket 3 e reescrito desde o 14; este ticket apenas o consome.
**Entrada de whitelist que estava faltando, e sem ela este ticket não fecha:** o adaptador v0.5 roda `method=` do lado velho contra o caminho único da v0.6, e a §9.4 registra que método e caminho de grade são **ortogonais**, com desacordo entre métodos de **0,019 p.p.** Isso é divergência intencional de **categoria (a)** e precisa de **linha própria na whitelist da §6, com faixa medida e qual método roda para cada uma das cinco formas** — hoje a whitelist não tem essa linha. **Nenhuma entrada de categoria (a) sem faixa medida sai do vermelho**, e essa regra se aplica a ela também.
**Tamanho:** L.

### 16 — Contração: o pacote novo é o pacote
**Bloqueado por:** 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15.
**Entrega:** num commit, morrem `policy.py` (311), `stages.py` (492), `simulation.py` (820), `sweep.py` (317), `optimization.py` (261), `analysis.py` (111), `stress.py` (127), **`performance.py` (650)**, os consumidores velhos de `screening`/`grouping`/`deployment`, a suíte velha já auditada, `is_sim_col` inteiro, os 16 `warnings.warn` do núcleo com o `CalibrationReliabilityWarning` incluso, e `CalibratedExpression`/`Expression.calibrated()` (`expressions.py:70`), que só sobreviveram porque o `RateStage` os usava.

**`performance.py` estava faltando nesta lista, e é o buraco maior dela.** Ele é importado por `__init__.py:21` e carrega nominalmente tudo o que o ticket 11 reconstrói em `engine/` sem aposentar o original: os quatro `print_*` que a §4.6 manda virar função livre que devolve tabela — `print_delta_table:288`, `print_quadrant_summary:458`, `print_swap_in_by_rating:528`, `print_rating_quadrant_table:572`, que **são** as *"363 linhas, 41 operações de cálculo, zero valores devolvidos"* da spec —, o **`compare_policies` (`:127`)** que a §4.10 mata com todas as letras, `summarize_results`, `ModelEvaluator`, e os cinco sítios de recomputação à mão do vigente que a coluna `baseline_*` da §4.8 torna desnecessários. Ele lê `metadata["policy"]`, `metadata["method"]`, `simulated_default`, `new_approval` e `scenario` — **todos mortos**.

**Mesma forma, escala menor:** `_types.py` morre com `StageDirection` (§4.2) e `SimulationMethod` (morre com o `method`); e `tests/test_packaging.py:26-31` **assere `plot_tradeoffs`/`plot_funnel`/`plot_crash_test`/`plot_vintage_stability` como exports de topo** — a redução do `__all__` quebra essa asserção, então **este ticket edita `test_packaging.py`**, o mesmo arquivo que o ticket 3 tocou. O `__init__.py` passa a exportar ~20 nomes **agrupados pelos três estágios** — declarar / calcular / ler —, `help(pycreditools)` imprime as duas linhas da espinha, e todo verbo aponta o seguinte.
**Tripwire:** teste que falha se `pycreditools.CreditPolicy` e `pycreditools.engine.CreditPolicy` coexistirem depois deste ticket.
**Tamanho:** XL.

### 17 — Masterclass, CHANGELOG e os cinco portões
**Bloqueado por:** 16.
**Entrega:** a masterclass reescrita na superfície nova — que **é** o teste de ergonomia da família, e cuja §6 encolhe para uma chamada com `by="region"` mais bisseção em pandas. CHANGELOG sem lápides, com a redistribuição semântica explicada campo a campo. A nota do sorteio com os dois números — **0,018 p.p.** em rodada única, **0,41 p.p.** entre rodadas semeadas em paralelo —, corrigindo **`README.md:439`**, que hoje diz que o pacote *"prevents stochastic noise"* e aponta para o lado errado. O checklist dos cinco portões assinado — e **é aqui que o portão 4 enumerador roda**, sobre a lista fechada que o ticket 3 especificou: as duas seções do `CONTEXT.md`, os ADRs do ticket 1, e os três arquivos de teste-evidência, **verificados por existência no `HEAD` e não por menção em prosa**. Ligá-lo aqui e não no 3 é o que impede um ticket sem bloqueador de nascer vermelho esperando o 1. **É o único ticket que empacota e versiona.**
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

### 5. `reason` é a sexta coluna do esquema do motor

Levantado na revisão a frio: o ticket 5 declarava **seis** colunas e a §4.7 declarava **cinco**, e essa era uma emenda **não declarada** num documento cuja última linha é *"emenda a ele é emenda a decisão — registre o porquê num ADR antes de mudar uma linha aqui"*. A outra emenda (aridade) estava declarada; esta não. Fica declarada agora.

**Vale:** `reason` entra no esquema do motor — `category`, **nula onde `decision == 1`**, escrita **só** no ponto de montagem. O argumento é da própria §4.7, que mede que `decision`/`reason` são hoje *"escritos por dois caminhos independentes com o mesmo conteúdo, a borda recomputando o que o motor já calculou"* — e então deixava `reason` de fora do esquema, **mantendo vivo exatamente o bug que a seção existe para matar**. Quem sabe qual estágio barrou é o motor, no instante em que barra.

**Três consequências que o ticket 5 tem que prender:** o valor é o **label do estágio** (frase é apresentação, e apresentação vive fora do núcleo); **primeiro estágio que barra e só ele**, porque a cadeia é curto-circuito e não existe "barrou em dois" a representar; e **`reason` depende da ordem de declaração dos estágios** — mudar a ordem muda a distribuição de `reason` **sem mudar `decision`**. Nulo em aprovado é contrato e não conveniência: `""` ou `"approved"` inventaria uma categoria que não é estágio e faria `value_counts()` mentir.

**Emenda à spec:** §4.7, aplicada. **ADR:** entra na lista do ticket 1.

---

## Uma supressão declarada, para não ser lida como buraco

A §7 e a US 65 contratam *"o `__init__` do Studio falhar limpo, dizendo 'não migrado para a API v0.6'"* — o **único** trabalho de Studio previsto na v0.6.0. Esta lista **não o entrega**, por ruling do dono (*"deixe o Studio de fora; talvez eu acabe com ele"*).

Isso é **supressão declarada de um contrato da spec**, não esquecimento. Se o Studio sobreviver, o item volta como ticket próprio; se morrer, o contrato morre com ele. O ticket 13 (deselecionar `tests/studio/` do `pytest` default) fica de pé nos dois mundos, porque ele existe para não bloquear a contração, não para manter o Studio vivo.

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
