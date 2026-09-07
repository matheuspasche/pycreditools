# Spec de arquitetura — pycreditools v0.6

> **Status:** viva. Este é o *contrato corrente*, não o histórico do porquê.
> **Origem:** colapso do [wayfinder map #111](https://github.com/matheuspasche/pycreditools/issues/111), 36/36 cards fechados entre 2026-07-24 e 2026-09-06.
> **Entregável irmão:** um ADR por decisão (`docs/adr/`), imutável, com o *porquê*. Regra do [#112](https://github.com/matheuspasche/pycreditools/issues/112).
> **Sucessor:** o mapa de implementação. Este documento é o insumo dele, e os portões da §6 são as condições de fechamento dele.

## Como ler este documento

**Precedência.** Onde este documento e um card divergirem, **vale este documento**; onde dois cards divergirem, **vale o mais recente** — regra declarada nas *Notes* do mapa, e ela morde de verdade: o #152 (2026-09-06 21:12) reverteu decisões que o #155 tinha tomado às 20:10 do mesmo dia, e o #155 revogou uma emenda que o #139 tinha feito no dia anterior. Cada ponto abaixo cita o card vigente.

**O que é decisão e o que é escrita.** Tudo aqui é decisão fechada, salvo o que estiver marcado **[aberto]**. Enumeração de coluna, ordem de campo, texto de mensagem de erro e largura de tabela são *escrita de spec* — mecânicos a partir das regras fixadas, e resolvidos aqui sem virar pergunta.

**Régua de aceite de toda superfície pública**, declarada pelo dono em 2026-07-24 e nunca revogada:

> Tem que ser um **passeio no parque**, tão lógico e intuitivo quanto brincar com dados no dplyr. Verbos pequenos e componíveis, cada um fazendo uma coisa óbvia, com tipo de saída previsível, encadeáveis.
> **Uma decisão de arquitetura que produz uma API difícil de usar falhou, mesmo que os tipos estejam corretos.**

---

## 1. Problem Statement

O `CreditPolicy` de hoje tem 13 campos e finge ser um tipo só. Ele é, ao mesmo tempo:

- **schema de dados** — `applicant_id_col`, `score_cols`, `current_approval_col`, `current_hired_col`, `actual_default_col`, `time_col`, `estimated_default_col`;
- **regras de política** — `stages`;
- **premissas de estudo** — `stress_scenarios`, `calibration_score_col`, `calibration_bins`, `calibration_base`;
- **pós-processamento** — `rating_recipe`;

e responde a 23 métodos que cobrem construção, serialização, validação, execução e export. O usuário que quer rodar a mesma série de regras sobre duas bases, ou a mesma política sob duas hipóteses de calote, não tem como dizer isso — ele reconstrói o objeto inteiro e reza para não esquecer um campo.

**Isso não é feiura de nome. Produz números errados, medidos:**

| sintoma | onde | magnitude |
|---|---|---|
| A âncora da calibração é **posição**, não decisão — a ordem da tupla de scores, a ordem das chaves do `dict` e a ordem dos estágios reancoram a régua score→PD | `stages.py:158` (`resolve_calibration_score_col`) | **−0,70 p.p.** na inadimplência a 3 MM, **24× o ruído**, sempre subestimando risco ([#137](https://github.com/matheuspasche/pycreditools/issues/137)) |
| Varrer um campo **reconstrói o estágio pela metade** — 4 de 6 campos — e o resto cai para os defaults, sem aviso | `sweep.py:169` | **2,27 p.p.** de deriva no eixo varrido, **0,90 p.p.** num ponto ([#133](https://github.com/matheuspasche/pycreditools/issues/133)) |
| O caminho rápido da grade **não recalibra** quando o corte muda quem é keep-in — e são os keep-ins que calibram o PD dos swap-ins | `sweep.py:284-305` (comentário `this is exact` é falso) | até **+1,00 p.p.**, **32× o ruído**, sem encolher com *n*, **máximo no meio da banda de decisão de 15–45%** ([#140](https://github.com/matheuspasche/pycreditools/issues/140), [#149](https://github.com/matheuspasche/pycreditools/issues/149)) |
| A régua de imputação é aprendida **dentro** da simulação, então varrer sobre uma fatia calibra uma régua por fatia — **sem ninguém ter pedido** | `simulation.py:685` + `_kernels/calibration.py:18` | os **cinco cortes regionais** da §6 da masterclass (752/785/732/694/680) são produto disso ([#142](https://github.com/matheuspasche/pycreditools/issues/142)) |
| Em standalone com desfecho mascarado, o motor **relê o último `RateStage` como probabilidade de calote** | `simulation.py:551-556` | PD média do aprovado **33,88% com** o estágio contra **9,42% sem** — **24,5 p.p.** ([#155](https://github.com/matheuspasche/pycreditools/issues/155)) |

Os cinco são a **mesma classe**: o motor resolve alguma coisa sozinho, em silêncio, a partir de uma estrutura que não foi desenhada para carregar aquela decisão. Nenhum é um bug isolado a consertar; todos são consequência da fronteira ausente.

**E a suíte não guardava nenhum deles.** Levantamento de 2026-08-14: 24 arquivos, 4.392 linhas, 190 funções de teste, **zero parametrizadas por método**, cobertura **~7:1** a favor do analítico — e toda a família de bugs de contrato keep-in (#97, #99, #103, #105, #106) testada **só** no analítico. Não existe `conftest.py` nem política de semente; `test_sweep.py:147` compara analítico com estocástico **sem semente**, n=4000, tolerância 0,05. Quando o #136 foi verificar se "todo estágio declarado liga em todo ponto da grade", descobriu que a garantia era **folclore**: nenhum teste a guardava, e o sintoma só pôde ser resolvido remedindo do zero.

## 2. Solution

### 2.1 A espinha, em duas linhas

Fechadas pelo dono no [#152](https://github.com/matheuspasche/pycreditools/issues/152), o card mais recente do mapa:

> **A `CreditPolicy` declara o que você DECIDE. A `Premise` declara o que você ASSUME.**
> Todo vetor de saída nasce de um dos dois, e de nenhum outro lugar.
>
> **Método declara, função livre calcula.**
> Nenhum método toca a base; toda função livre recebe primeiro aquilo sobre o que age, e devolve tabela.

A primeira é o critério **"muda quando"** de `docs/research/architecture-critique.md` §1 — a crítica que originou o mapa —, e depois do #155 ela é **exata**: os três vetores de saída do #116 moram em três lugares, e cada lugar diz de quem é a decisão.

| vetor | onde se declara | natureza |
|---|---|---|
| `decision` | `.filter(...)` na `CreditPolicy` | **regra** — muda quando a política muda |
| `contract` | `take_up=` na `Premise` | **premissa** — muda quando a pergunta muda |
| `outcome` | `stress=` / `outcome_from=` na `Premise` | **premissa** — idem |

A segunda **já era verdade e nunca tinha sido escrita**: nenhum método do pacote toca a base, e nenhuma função livre existe sem receber dado ou tabela. Não são dois idiomas — é uma fronteira que a superfície nunca anunciou. Precedentes lidos em fonte primária: **polars** (contexto é método, expressão é função livre) e **sklearn** (verbos são métodos, composição é função livre); nenhum dos dois é acusado de trocar de idioma, porque o corte acompanha uma distinção real.

### 2.2 A superfície, ponta a ponta

```python
import pycreditools as pct
from pycreditools import col

schema = pct.DataSchema(approved="approved", hired="hired", outcome="actual_default")

policy = (
    pct.CreditPolicy()
      .filter(col("age") >= 18,               label="idade")
      .filter(col("vl_negativacao") <= 0,     label="antifraude")
      .filter(col("score_5") >= 700,          label="corte")
      .filter(col("desk_outcome"), draw=True, label="mesa")
)

premise = pct.Premise(
    bins         = 5,
    calibrate_on = "global",      # "global" (default) | "keep_in"
    take_up      = "binned",      # "binned" | escalar | nó da AST
    stress       = 1.8,           # escalar | escada por bin | nó da AST
    outcome_from = "parcelling",  # "parcelling" | nome de coluna 0/1 | nó da AST
)

study = pct.Study(schema, policy, premise, seed=7, name="challenger")

res  = pct.simulate(study, df)
grid = pct.tradeoff(study, df, ranges={"corte": range(600, 800, 10)}, by="loja")
best = pct.choose(grid, criterion="pareto", by="loja")
pct.plot_tradeoff(grid, criterion="pareto")

pct.funnel_table(res)
pct.delta_table([res_a, res_b], baseline=res_hoje)
pct.swap_in_table(res, by="rating")
```

Quatro declarações, quatro verbos de cálculo, quatro verbos de leitura. **Nenhum objeto executa; nenhuma função livre declara.**

### 2.3 O tamanho da quebra

`__all__` exporta **53 nomes**. Entre **35 e 40 morrem ou mudam de forma** — **~70%**. A quebra é **única e grande**: "mínima" caiu por medição, não por ampliação de escopo, porque as decisões estão entrelaçadas (`ranges=` só existe porque o schema saiu da política; `choose()` só existe porque o best único morreu; a mesa só é exprimível porque o `.filter` foi reescrito).

> **Regra do corte ([#124](https://github.com/matheuspasche/pycreditools/issues/124)):** toda remoção ou renomeio de superfície pública entra na quebra única — adiar qualquer um significa uma segunda quebra dura depois. E **todo substituto viaja junto com a remoção**: remover sem substituto deixa o usuário sem caminho.

**A migração é guia simples, sem lápides** — sem stubs, sem janela de depreciação, sem codemod. Ruling do dono: *"projeto pessoal, não tem realmente usuários utilizando e pipelines que vão quebrar"*. O codemod foi recusado **com argumento**: a migração não é renomeio, é **redistribuição semântica** — onde havia um `CreditPolicy` de 13 campos passam a existir quatro objetos, e nenhum script infere quais campos eram schema, quais eram regra e quais eram premissa. Um codemod acertaria os renomeios triviais e falharia **calado** onde mais importa.

Duas consequências disso, e a segunda é a que carrega peso:

1. A quebra única deixa de se justificar por custo de migração do usuário e passa a se justificar por **não fazer duas reescritas do mesmo código**. A decisão sobrevive; a razão troca.
2. **A prova de paridade ganha peso.** Sem usuário para reportar regressão, ela é a única coisa que garante que a reescrita não mudou o que a ferramenta diz.

---

## 3. User Stories

### Declarar o dado

1. Como analista de crédito, quero declarar **três** papéis de coluna — aprovado, contratou, desfecho — para que o motor saiba ler meu livro sem adivinhar nada.
2. Como analista, quero que declarar aprovação **obrigue** declarar contratação, para que o pacote nunca infira take-up de um livro que não me disse quem contratou.
3. Como analista, quero rodar **standalone** (sem livro incumbente) sem declarar papel nenhum, para avaliar uma política sobre uma base de propostas cruas.
4. Como analista, quero que uma coluna declarada e ausente **levante no bind**, nomeando o papel e a coluna, para descobrir o erro antes de olhar um número.
5. Como analista, quero que um valor fora de `{0, 1}` em `approved` ou `hired` **levante no bind**, para que o pacote nunca leia um `0.07` como se fosse um fato.
6. Como analista, quero que `"S"/"N"`, `"sim"/"não"` e `bool` **não** sejam convertidos em silêncio, porque converter reintroduziria a inferência que estou pagando para matar.
7. Como analista, quero que uma linha com desfecho marcado em quem não contratou, ou contratação marcada em quem não foi aprovado, **recuse a base inteira**, para que meu erro de extração exploda onde nasceu e não vire uma média deflacionada.
8. Como analista, quero que **maturação parcial** — aprovado, contratou, desfecho ainda nulo — **não** seja erro, porque é o caso normal de um livro vivo; quero a cobertura reportada como número.
9. Como analista, quero reusar o mesmo schema em outra base com nomes diferentes trocando um campo, sem mecanismo novo.
10. Como analista, quero **não** ser obrigado a declarar `applicant_id`, `time_col` ou lista de scores, porque o motor não usa nenhum dos três para decidir.

### Declarar a política

11. Como analista, quero declarar minhas regras com **um verbo só**, `.filter`, para não ter que lembrar qual verbo serve para corte e qual serve para filtro.
12. Como analista, quero escrever a regra como **expressão** (`col("score_5") >= 700`), para que ela seja legível, componível e serializável.
13. Como analista, quero que a política seja **anônima e reusável**, para rodar a mesma série de regras sobre N bases e sob N premissas sem copiar objeto.
14. Como analista, quero que cada regra ganhe um **label automático** quando ela referencia uma coluna só, para não nomear cinco filtros óbvios à mão.
15. Como analista, quero que o pacote **exija** label quando a estrutura não nomeia — zero colunas, duas ou mais, ou colisão —, e que a mensagem me diga o que fazer.
16. Como analista de fraude, quero declarar um estágio **probabilístico de decisão** (a mesa, a formalização) com `draw=True`, e que ele **conte na taxa de aprovação publicada**, porque reprovado na mesa é reprovado.
17. Como analista, quero que `decision` seja **0/1 duro** sempre, inclusive quando a mesa sorteia, porque ele é a máscara que decide quem entra em toda conta a jusante.
18. Como analista, quero trocar o corte de um estágio nomeado e receber uma política nova, sem reconstruir os outros estágios e sem perder um campo que eu não lembrei de copiar.
19. Como analista, quero que **nome de estágio duplicado** seja erro duro, porque o nome é o endereço de `ranges=` e da coordenada da grade.
20. Como analista, quero que a política **não aceite função Python opaca**, para que o que eu simulo seja exatamente o que eu consigo exportar.
21. Como analista, quero que a escotilha para regra complexa seja **calcular a coluna na base e filtrar por expressão** — o movimento `mutate` → `filter` do dplyr —, porque coluna é dado e dado serializa.
22. Como analista, quero ver o funil com **duas colunas** — o nome que eu escrevi e a regra renderizada —, para que a coluna de nomes fique quase vazia e o branco me diga que a regra se explica sozinha.

### Declarar a premissa

23. Como analista, quero **um** objeto que diga tudo que estou assumindo sobre quem eu não observei, para que "premissa" seja uma palavra com endereço.
24. Como analista, quero ser **obrigado** a construir esse objeto, sem default escondido, porque um default de premissa esconderia que existe imputação rodando.
25. Como analista, quero declarar de que **população** sai a régua score→PD, e que esse valor seja o mesmo para bordas e para taxas, porque hoje o `calibration_base` governa só metade e a outra metade é cravada.
26. Como analista, quero que o default seja a população **invariante ao meu challenger**, para que a mesma pessoa com o mesmo score não receba PD diferente conforme onde eu corto.
27. Como analista, quero declarar o take-up como **escalar** quando eu tenho um número, como `"binned"` quando quero que ele siga a faixa de score, ou como **nó da AST** quando eu tenho a probabilidade por linha.
28. Como analista, quero que take-up **não declarado** seja `1.0` **literal na assinatura**, visível no `help()`, e quero saber que isso é **conservador, não neutro**.
29. Como analista, quero estressar a PD dos negados com um **escalar**, porque a premissa "o negado é 1,8× pior que o aprovado comparável" é o que eu de fato assumo.
30. Como analista, quero estressar em **escada por faixa** — 20% no melhor decil, 80% no pior — porque a inadimplência dos negados não é uniforme e a angulação é o que eu faço na masterclass hoje.
31. Como analista, quero que **uma** hipótese de inflação exista por estudo, sem agregador, porque `max(pd×1.3, pd×1.8)` é cerimônia com resposta predeterminada e o `max` por linha monta uma curva que não corresponde a hipótese nenhuma.
32. Como analista, quero declarar que o desfecho vem de uma **coluna minha 0/1** (bureau, modelo materializado), e que nesse caso inflar seja **erro duro**, porque não há o que inflar.
33. Como analista, quero que **variar premissa seja outro estudo**, nunca outra dimensão da grade, para que dois pontos da mesma grade sejam sempre comparáveis.

### Rodar

34. Como analista, quero um verbo `simulate(study, df)` que devolve resultado, sem método no objeto e sem base guardada dentro dele.
35. Como analista, quero declarar a **semente** e que ela seja obrigatória, para que a diferença entre duas políticas seja regra e nunca ruído.
36. Como analista, quero que dois pontos de grade sejam **comparáveis por construção**, para que a diferença entre eles não dependa de quantos números o ponto anterior consumiu.
37. Como analista, quero que rodar em paralelo **reproduza** sob semente, porque hoje não reproduz e a diferença é 0,41 p.p.
38. Como analista, quero **um** caminho de cálculo, para não ter que escolher entre dois modos cuja paridade nunca foi testada.
39. Como analista, quero que a inadimplência seja calculada **somente** sobre quem completa a cadeia aprovado → contratou → desfecho, e que isso seja contrato documentado, não configuração.
40. Como analista, quero que a coluna emitida seja **nula fora do domínio**, para que `df["outcome"].mean()` esteja certa por construção, mesmo que eu não leia a documentação.
41. Como analista, quero a **cobertura da marcação como número** no resultado, porque "quantas linhas têm desfecho" é grau, não erro.
42. Como analista, quero que o motor **nunca me avise sobre o meu dado**, porque aviso silenciável é, para o desatento, aviso silencioso.
43. Como analista, quero que os números de inversão e de fora-de-suporte apareçam no **resumo de leitura** que eu já leio, para comparar 6, 7 e 10 faixas numa tabela em vez de em três mensagens no terminal.

### Varrer, escolher, ler

44. Como analista, quero **um** verbo de grade, `tradeoff`, e declarar o que varrer com `ranges=` chaveado pelo label do estágio.
45. Como analista, quero que a coordenada saia da tabela com o **label cru**, sem sufixo, porque a chave que entra tem que ser a chave que sai.
46. Como analista, quero que a grade traga o **cenário vigente medido** ao lado de cada ponto, para que "segurar a aprovação de hoje" não me obrigue a passar um número que eu teria que medir por fora.
47. Como analista, quero que a grade traga os **denominadores**, porque percentual não soma e sem eles consolidar grupos é impossível — nem à mão.
48. Como analista, quero varrer **por grupo** com `by=`, e que o custo não exploda com o número de grupos.
49. Como analista, quero que `by=` **nunca** mude o que o motor calcula, para que o número consolidado e a soma dos números por grupo contem a mesma história.
50. Como analista, quero que a régua de imputação seja **global sempre**, para que a curva da loja pequena não seja desenhada pelo azar de 30 pessoas.
51. Como analista, quero **um** verbo de seleção, `choose`, com o cardápio inteiro de critérios no `help()`, porque o meu problema é não saber que a pergunta existe.
52. Como analista, quero que o pacote **nunca** escolha um ponto por mim, porque o peso mágico `aprovação − 5×inadimplência` responde a uma pergunta que ninguém faz.
53. Como analista, quero que o apetite continue sendo `df[...]` meu, uma regra só para estreitar.
54. Como analista, quero que "segurar a aprovação de hoje" me devolva os **dois pontos que ladeiam** o vigente, e não uma banda cujo tamanho é a resolução da minha grade disfarçada de resposta.
55. Como analista, quero que **vigente fora da faixa varrida** seja erro duro que me diga a faixa e o meu número, porque aí a varredura é que está errada.
56. Como analista, quero as quatro tabelas de leitura como **funções livres que devolvem tabela**, para usar o número na célula seguinte em vez de refazer a conta.
57. Como analista, quero comparar N estudos passando uma **coleção** ao `simulate`, recebendo tabela longa com a coluna `study`, para concatenar sem perder quem produziu o quê.

### Sugerir, aplicar, publicar

58. Como analista, quero um verbo que **sugere** uma régua de rating a partir da base, e outro que a **aplica**, sem objeto que aplique a si mesmo.
59. Como analista, quero que a régua sugerida saia como **corte puro** — legível, exportável, independente da política.
60. Como analista, quero cruzar dois scores numa grade passando uma tupla, e comparar N candidatos com um `for`, porque as duas coisas são diferentes e um argumento só não pode significar as duas.
61. Como analista, quero ajustar uma régua **por segmento** com `by=`, porque é isso que eu peço explicitamente.
62. Como analista, quero exportar **duas** unidades distintas — as regras que vão para produção e o estudo que reproduz o experimento —, com nomes que digam qual é qual.
63. Como engenheiro de produção, quero pontuar uma base nova sem declarar premissa nenhuma, porque decidir aprovar não usa premissa.
64. Como engenheiro de produção, quero que o pacote **nunca fabrique** colunas para mim, porque hoje ele mocka `approved = 1` e isso escolhe um caminho de código.
65. Como usuário do Studio, quero um erro claro dizendo "não migrado para a API v0.6" em vez de um traceback no meio de uma página.

### Confiar no número

66. Como analista, quero que toda garantia que a arquitetura afirma "por construção" tenha um teste com **referência calculada fora do motor**, porque comparar motor com motor pina coincidência.
67. Como analista, quero que esse teste seja medido **na fronteira**, onde a garantia satura, e que tenha **controle negativo**, para saber que o teste tem dente.
68. Como analista, quero que a grade seja **exata**: um ponto colhido dela tem que bater com a mesma política simulada à mão.
69. Como analista, quero saber que **todo número sai de um sorteio** e carrega margem, e quero os dois números que importam — 0,018 p.p. em rodada única e 0,41 p.p. entre rodadas semeadas em paralelo.
70. Como analista, quero que a prova de paridade contra a v0.5 seja parametrizada **por forma de política**, porque a divergência não é uniforme e o harness de hoje roda a única forma que bate exato.

---

## 4. Implementation Decisions

### 4.0 Os quatro tipos, e o que cada um carrega

| tipo | carrega | muda quando | fonte |
|---|---|---|---|
| **`DataSchema`** | que coluna faz que papel | **a base** muda | [#117](https://github.com/matheuspasche/pycreditools/issues/117), [#118](https://github.com/matheuspasche/pycreditools/issues/118) |
| **`CreditPolicy`** | as regras, e só elas | **a política** muda | #117, [#119](https://github.com/matheuspasche/pycreditools/issues/119), [#155](https://github.com/matheuspasche/pycreditools/issues/155) |
| **`Premise`** | o que se assume sobre quem não foi observado | **a pergunta** muda | #117, [#139](https://github.com/matheuspasche/pycreditools/issues/139), [#152](https://github.com/matheuspasche/pycreditools/issues/152) |
| **`Study`** | o encontro dos três + `method`/`seed` + identidade | — | #117, [#116](https://github.com/matheuspasche/pycreditools/issues/116), [#125](https://github.com/matheuspasche/pycreditools/issues/125) |

Mais **a regra de rating como tipo próprio**, produzida pelo sugestor ([#126](https://github.com/matheuspasche/pycreditools/issues/126)) — não é peça da decomposição, é produto de um verbo.

**A base entra no verbo, nunca no tipo.** É o que torna a política portável entre bases, e o que dispensa cachear qualquer coisa derivada do bind.

**Quem executa: funções livres.** `simulate`, `tradeoff`, `choose`, `export_*`, as quatro tabelas, os dois sugestores. **Nenhum método no encontro que leia só uma parte.** Derivação é `dataclasses.replace`.

**Premissa nunca é `None`.** Omitir não constrói silêncio — o `Study` **exige** a premissa (§4.4). O que pode ser omitido é um campo dela, e aí o default é **literal na assinatura**.

### 4.1 `DataSchema` — três campos, nada mais

```python
DataSchema(approved: str | None = None, hired: str | None = None, outcome: str | None = None)
```

| campo | obrigatório | nota |
|---|---|---|
| `approved` | — | se declarado, `hired` passa a ser obrigatório |
| `hired` | **condicional** | a amarra de entrada do #116 |
| `outcome` | — | aceita nulo: **nulo é o não-observado** |

**Morrem do schema:** `score_cols`, `applicant_id`, `time_col`, `estimated_default_col`, `segment_col` (que nunca chegou a entrar e era **adivinhado** por `["region","loja","safra"]` em `simulation.py:271`), e todos os `calibration_*`.

**A linha que separa schema de política — e ela não é literal:**

> **O schema é dono dos nomes que o motor lê POR PAPEL** (aprovado, contratou, desfecho).
> **A política nomeia as colunas que suas regras REFERENCIAM** (score, renda, PD).

Papel ≠ referência. `.filter(col("score_5") >= 700)` continua nomeando `score_5`, e isso não é violação.

**O princípio que decidiu três campos, e que caiu três vezes seguidas na mesma sessão** (vocabulário de varredura, `segment_col`, OOT/safra):

> **Eixo de experimento ou de análise é argumento do verbo. Papel do funil é schema.**
> Papel do funil é finito e o motor lê sempre; eixo de análise é aberto e por chamada.

**Bind — presença, domínio, cadeia; zero coerção:**

1. Coluna declarada e ausente → **erro duro**, nomeando papel e coluna.
2. Valor fora de `{0, 1}` em `approved`/`hired` → **erro duro**.
3. `outcome` aceita nulo; a **cobertura vira número** no resultado.
4. **Nenhuma coerção silenciosa** — `bool`, `"S"/"N"`, `"sim"/"não"` não são convertidos.
5. **Linha malformada → erro duro, recusa a base**: desfecho marcado em quem não contratou, ou contratação marcada em quem não foi aprovado. Quebra a monotonicidade da cadeia; é dado inválido, não estado a descartar.
6. **Maturação parcial não é erro** — aprovado + contratou + desfecho nulo é livro vivo.

O item 5 é a versão vigente (#132, 2026-09-02), e **substitui** o descarte silencioso que o #131 tinha decidido em 31/08. O motivo da mudança: o 0-preenchedor típico preenche a base inteira, inclusive fora do domínio; sob descarte, esses zeros eram **jogados fora sem ninguém saber** — a média emitida ficava certa e quem entregou a base errada nunca descobria.

**Reuso entre bases** é `dataclasses.replace`, sem mecanismo.

**No Studio:** `ColumnRoles` (`studio/models.py:17`) morre — era a terceira grafia do mesmo papel. `studio/detection.py` vira **sugestão de formulário**, para o humano confirmar; nunca inferência que chega ao motor.

### 4.2 `CreditPolicy` — `stages`, e nada mais

Depois da decomposição, `CreditPolicy` carrega **uma lista de estágios**. O nome fica: ele recebe hoje exatamente os kwargs que migram (`applicant_id_col`, `score_cols`, `current_*_col`), então código antigo levanta `TypeError` de kwarg inesperado — **quebra alta e imediata**, não mudança silenciosa.

**Uma lista de um verbo só ainda é um tipo?** Sim, e por três coisas que uma `list[Filter]` não carrega:

1. os **labels** — chave de `ranges=` e coordenada da grade;
2. a **validação de composição**, sem base (o primeiro dos dois momentos de validação);
3. a **unidade de deploy**.

#### O verbo único: `.filter`

```python
.filter(expr, *, draw: bool = False, label: str | None = None) -> CreditPolicy
```

**`.cutoff` morre.** `CutoffStage.apply` e `FilterStage.apply` são a mesma função (máscara booleana → `fillna(False)` → cast). O que distinguia a classe **não era o cálculo** — era ser o **botão numérico endereçável** que a varredura lia por estrutura (`optimization.py:144-150`). A decisão preserva o caminho rápido **rechaveando-o na AST**: a condição é *"o nó variado é o literal de uma comparação numa máscara dura"* — propriedade estrutural que a classe só representava por acidente.

Morrem junto: `direction="gte"/"lte"` (o operador está no nó — mata os 53 literais medidos), `cutoffs: dict[coluna, valor]` multi-coluna, o enum `StageDirection` nunca usado, e **11 dos 20 `isinstance` sobre `Stage`**.

**`draw=True` é a mesa.** O verbo nomeia o **vetor** (`.filter` → `decision`); o argumento nomeia o **mecanismo** (sorteia ou não). Com um verbo só na política, a flag é a **única** maneira de exprimir o segundo eixo sem inventar um verbo irmão que alimente o mesmo vetor.

- `draw=` e não `prob=`: a flag diz **o que faz** — sorteia —, não que o argumento é uma probabilidade.
- **Preço declarado e aceito:** a flag re-tipa o argumento posicional (nó booleano sem ela, nó numérico em `[0,1]` com ela). **A saída não muda de tipo** — `.filter` entrega máscara 0/1 dura, sorteada ou não —, então "tipo de saída previsível" fica de pé. O dono registrou a forma como *"meio feio, mas a mecânica é essa"*.
- **A mesa sorteia também no caminho determinístico** e **entra na taxa de aprovação publicada** (medido: 42,56% sem a mesa contra 38,52% com — ela reprova 4,04% da base).
- A coluna observada da mesa é **o próprio nó** (`col("desk_outcome")`), o que satisfaz papel≠referência sem trazer argumento nomeado de volta.

Descartadas, com o porquê registrado: `.review(...)` (repõe um terceiro verbo e o nome não generaliza — mesa, antifraude e formalização são todas decisão probabilística); `.rate(expr, to="decision")` (inverte os eixos: o verbo passaria a nomear o mecanismo e o argumento o vetor); `.filter(chance(expr))` (cai com o ruling de que `.calibrated()` morre — sem ele a AST fica **pura**, e `chance` seria a única instrução-nó, criando a categoria que a v0.6 acabou de remover).

#### Identidade do estágio: label único, com default **estrutural**

- O label é **opcional**; o default é **derivado da AST** — a coluna referenciada, quando a regra referencia exatamente uma.
- **Erro duro no bind** em três casos: zero colunas, duas ou mais, ou **colisão** com label já tomado.
- O label endereça `ranges=` e `set_stage`.

**Não é a inferência que o #118 matou:** o default sai da AST que o usuário escreveu, não de heurística sobre o dado, e **falha duro em vez de escolher em silêncio**. E é **estrutural, não posicional** — inserir estágio no meio não move endereço nenhum, o que corrige a instabilidade que os ~14 sítios com `f"{i+1}: {stage.name}"` denunciam.

**Censo sobre os 9 estágios reais do notebook: só 2 exigem label (22%)** — o gate regional (duas colunas) e um `.rate` escalar (zero colunas, que sai da política com o eixo de contrato).

**A colisão de faixa é caso comum, e o erro duro fica:**

```python
CreditPolicy().filter(col("score_5") >= 600).filter(col("score_5") <= 900)
# LabelRequired: a faixa são duas regras; nomeie-as (label="piso" / label="teto")
```

A medição virou o argumento: a saída natural de quem topa com o erro é fundir a faixa num estágio só, e **é justamente a escrita que perde os dois dials**.

| escrita da faixa | varrer o piso | varrer o teto | os dois |
|---|---|---|---|
| dois estágios nomeados | endereçável | endereçável | endereçável |
| um estágio, `>= 600 & <= 900` | — | — | **recusado** |

**O erro duro não é pedra no caminho — é o que empurra para a escrita que também é a varrível.**

#### Estágio composto: escrita legal, `ranges=` sobre ele é erro duro

Escrever `.filter((col("a") >= 700) & (col("b") >= 500))` é **legítimo**. O erro nasce **onde a ambiguidade nasce** — na varredura, não no bind:

| forma | endereçável por `ranges=`? |
|---|---|
| um literal numérico numa máscara dura | **sim** |
| um literal + um conjunto fixo na mesma regra | **sim** (o fixo fica na baseline) |
| comparação contra outra coluna (gate regional) | **não** — erro duro |
| duas comparações numéricas na mesma regra | **não** — erro duro, mensagem manda separar |
| nó que alimenta `contract` | **não** — uma probabilidade não tem corte |

Descartados: erro duro no bind (mata escrita legítima) e `ranges=` endereçando o nó (`"dois.score_5"` — inventa sub-endereço e contraria `ranges=` chaveado por label). **Estágio composto varrível não aparece nenhuma vez nas políticas reais.**

#### Movimento de builder: um só

```python
nova = policy.set_stage("corte", ...)   # devolve política nova com aquele estágio trocado
```

Mesma gramática de derivação do `vary`; a diferença é guardada × descartável. **`drop_stage`/`reorder` ficam de fora até caso medido** — ordem de estágios é semântica de funil, e método de reordenar esconde isso. **Nome duplicado no `add` é erro duro.**

#### O que um estágio é, por dentro

**O `Stage` ABC morre; fica um `Protocol` de UM membro:** `apply(df, ctx) -> Series`. **Todo estágio alimenta `decision`.**

- Medido: `stage.apply()` tem **dois** chamadores contra **20 `isinstance`** — o polimorfismo era fingido, o código repartia por tipo em toda parte.
- Dos 20: 11 morrem com o `.cutoff`; **5 são a partição `RateStage`-vs-resto e somem SEM SUBSTITUTO** (`simulation.py:79, 229, 438, 475, 552`), porque com o eixo de contrato fora da lista ela fica homogênea e não há o que particionar. **É menos mecanismo do que a decisão anterior previa.**
- Nenhum comportamento é compartilhado — só a assinatura —, então herança não entrega nada, e estrutural casa com o congelamento fundo, que herda mal.
- **O `ctx` é estreito:** semente do estudo, posição de linha, e a premissa quando o estágio a admite. **Nunca a política.** Com isso o `policy: Any | None` costurado em todo `Stage.apply` morre **por construção**, e o ciclo de import junto.

### 4.3 A AST — pura, e é a condição

**A condição é a AST, não a string.** `expressions.py` já tem a árvore (`BinaryExpr(left, op, right)`), já anda nela (`get_columns()`) e já faz round-trip (`serialize_expression`/`deserialize_expression`) — então "achar o literal comparado a `score_a`" é **a mesma caminhada que já existe**, lida em ~6 linhas, não parsing.

- **A string sai da entrada e fica na saída.** `df.eval` é opaco, sem nó para trocar — seria a única gambiarra real. `__repr__` monta o render.
- **`.calibrated()` morre na v0.6.** Sobram `ColumnExpr`, `BinaryExpr` e `UnaryExpr` — **AST inteiramente pura**. (Ressalva registrada a favor de quem reabrir: `.calibrated()` precisava da **política** para avaliar — é a origem do `policy: Any` e do ciclo de import; um nó que precisasse só de semente e posição não reintroduziria o acoplamento, só a categoria.)
- **Callable é inexprimível.** Não é "recusa alta no `to_dict`": deploy é parametrização de motor, e regra que não vira dado não é regra, é código de notebook. Recusar só na serialização cria a política que simula lindo e falha no export — descobrindo o defeito **depois** de a decisão de negócio já ter sido tomada em cima dela. **Falha no construtor é falha cedo.**
- **Custo medido de matar o callable: zero.** Varredura de `src`, `tests`, `validation`, `docs`: **nenhum** `.filter` com callable. O único callable vivo é a angulação da masterclass, que vira coluna.
- **A escotilha não some, muda de lugar** — e o lugar novo é **dado, que serializa**: calcula a coluna na base, filtra pela expressão. É o `mutate` → `filter` do dplyr.

**Dois renders do mesmo nó, e a regra que impede divergência:**

| render | papel | round-trip |
|---|---|---|
| `__repr__` | render de Python, companheiro do `serialize_expression` | **sim** |
| `pretty()` | apresentação, para o funil | **nunca é parseado de volta** |

**Exibição do funil — duas colunas, não concatenação:**

```
Stage                  Rule                          Passed
-----------------------------------------------------------
                       cpf_valido == True            19,965
                       vl_negativacao <= 1500        18,097
Incumbent score gate   legacy_score >= 600            7,255
                       score_5 >= 560                 6,674
```

O label **acompanha** o render, não o substitui — a leitura alternativa perde o limiar exatamente na linha em que o label foi escrito *porque a regra não se explicava sozinha*. Medido: coluna Stage 20 caracteres, coluna Rule 22, contra 21 do nome à mão de hoje. **A coluna Stage fica quase toda em branco, e o branco é a informação.**

### 4.4 `Premise` — um tipo, cinco campos

```python
Premise(
    *,
    bins: int = 5,
    calibrate_on: Literal["global", "keep_in"] = "global",
    take_up: Literal["binned"] | float | Expression = "binned",
    stress: float | Sequence[float] | Expression = 1.0,
    outcome_from: Literal["parcelling"] | str | Expression = "parcelling",
)
```

**Um tipo, não dois.** `Parcelling`/`External` e a variante posterior `ScorePremise`/`ColumnPremise` morrem. A régua que decidiu: *assinatura-união se paga quando a parte compartilhada domina*. Contagem antes do esclarecimento do dono: 1 campo compartilhado × 4 exclusivos. Depois (*"os bins podem ser utilizados ali na questão do take up"*): **3 compartilhados** (`bins`, `calibrate_on`, `take_up`) **× 1 exclusivo de cada lado** (`stress` de um, a coluna do outro). **A união passou a se pagar.**

Dois fatos que fecharam:

- **O dono quer default** (*"padrão sempre nosso parcelling"*). Default mora em **assinatura**; com dois tipos não existe default — você é obrigado a nomear um tipo para começar.
- **A forma já é a de hoje.** `policy.py:33` tem `estimated_default_col: str | None = None` e o motor desvia quando vem preenchido (`simulation.py:548`, `:682`). **Não é padrão novo — é o padrão atual com nome melhor.**

**Regra interna do objeto**, e ela vale para os dois eixos:

> Cada eixo aceita **ou** um sentinela que **nomeia o mecanismo**, **ou** um valor concreto.
> `take_up="binned"` ou `0.7`. `outcome_from="parcelling"` ou o nome da sua coluna.

**A premissa é declarativa e inerte.** Quem executa é o motor — exatamente como já acontece com a inflação hoje (`simulation.py:657`). **Nenhum membro de premissa ganha método.**

#### `bins`

Discretização. **Uma config serve todo eixo sem marcação** — não há `bins` de take-up e `bins` de PD.

#### `calibrate_on` — de que população sai a régua

| valor | população, para **bordas E taxas** |
|---|---|
| `"global"` (default) | todo o livro observado — os contratados do incumbente, independente de onde caem na decisão nova. **Invariante ao challenger.** |
| `"keep_in"` | os que a política nova **também** aprova |

**Um eixo só governa bordas e taxas.** Morre o `calibration_base`, que governava **apenas as bordas** (`simulation.py:745-748`, via `ref_scores`) enquanto as taxas saíam de `cal_scores=keep_in_scores` (`:751`), **cravado, sem parâmetro**. Nome que promete a calibração e entrega metade dela é a classe que o resto do mapa matou.

**Consequências que valem escrever:**

- **Não existe configuração da v0.5 que produza o comportamento da v0.6.** `calibration_base="global"` de hoje não é o default novo — é outra coisa.
- Sob o **default**, a população é invariante ao challenger, então **a exatidão da grade sai de graça**. Sob `keep_in`, o caminho rápido só é exato **recalibrando por ponto** (+18% a +20%). ⇒ **a exatidão é provada por valor do knob: dois testes no portão, não um.**
- **Por que não existe uma terceira população "todo mundo, incluindo não observado":** a taxa por bin é `cal_values.groupby(cal_bins).mean()` (`_kernels/calibration.py:67`), e **`mean()` pula `NaN`**; `actual_default` é `NaN` onde `hired == 0`. Logo **toda** população candidata ensina, de fato, *ela ∩ quem tem desfecho* — e "global ∩ observado" **é** o livro contratado. O único mundo em que seria distinto é aquele em que o desfecho é observado **fora** do livro, e esse mundo já tem porta própria: `outcome_from=<coluna>`. Detectar em qual mundo se está exigiria **detecção**, proibida pela §4.11.
- **Terceira variante rejeitada** — "sobreviventes dos hard filters da política proposta": em v0.6 "HF" deixa de ser tipo, sobra *"filtro que este grid não varre"*, então a população passaria a depender do `ranges=` — **o mesmo `Study` com grades diferentes daria PD diferente para a mesma pessoa**. É a doença do `keep_in` uma camada acima, contra o eixo de comparabilidade.
- **Ressalva de nome, que é dívida de implementação:** as **taxas** coincidem entre a leitura velha e a nova, mas as **bordas não** — a mesma palavra `"global"` produz cortes diferentes entre v0.5 e v0.6, e a prova de paridade casa por nome. (O que enfraqueceu o alerta original: hoje `"global"` não é um nome, é **um de três apelidos** — `calibration_base in ("global","all","dataset")`.)
- **Quadrante é sobre decisão, não sobre desfecho.** "Ter desfecho" **não** entra na definição da população — é **pré-condição para ensinar**, idêntica nos dois valores, aplicada a bordas e taxas. O que muda em relação a hoje não é o conjunto: é que ele passa a ser **escrito**, em vez de emergir do `groupby.mean()` pulando `NaN`.

#### `take_up` — o eixo de contrato

| valor | significado |
|---|---|
| `"binned"` (default) | estimado por faixa, usando os mesmos `bins` e a população de `calibrate_on` |
| escalar (`0.7`) | **flat** — não há o que calibrar |
| nó da AST (`col("p_contrata")`) | probabilidade por linha, vinda de coluna |

`"binned"` e não `"observed"`: **`calibrate_on` já diz qual população; o que faltava anunciar é a granularidade** — e `bins=` está na mesma chamada, não numa nota de rodapé.

O terceiro modo preserva a capacidade que o `RateStage.variable` tem hoje (`stages.py:290`, avaliado em `:340-350`) e mantém a fatoração `contract = decision × take_up` — **o nó descreve a probabilidade, e o motor multiplica.**

**Take-up sem declaração é `1.0`, literal na assinatura, permanente e documentado.** Morre o `DeprecationWarning` de hoje. **Número idêntico ao de hoje — não entra na whitelist.**

> **A spec diz em voz alta: o `1.0` é CONSERVADOR, não neutro.** Keep-ins entram na carteira só se contrataram; swap-ins entram todos. Como o swap-in é o público pior, o peso dele infla e **a inadimplência é empurrada para cima**.

**Não existe agravar conversão.** A aprovação é medida pré-take-up (ADR 0008), então conversão não a move; qualquer inadimplência alvo é alcançável mexendo só na inflação do desfecho. O que ficaria diferente é o volume contratado, que não é métrica publicada.

**Assimetria registrada, que não muda a decisão:** a pré-condição de observabilidade difere por eixo. No desfecho é `outcome` presente — daí o buraco de suporte. **No contrato, take-up é observado para todo aprovado**, então ali não há buraco.

#### `stress` — a inflação do desfecho

| valor | significado |
|---|---|
| escalar (`1.8`) | *"o negado é 1,8× pior que o aprovado comparável"* |
| escada (`[1.2, 1.35, 1.5, 1.65, 1.8]`) | um fator **por bin**, na ordem dos `bins`; comprimento tem que bater com `bins`, senão erro duro |
| nó da AST (`col("fator_setorial")`) | um fator **por linha**, vindo de coluna |

**A escada é o caso da masterclass**, escrito como valor: *"para o melhor decil estresso 20%, para o pior 80%"*.

**O terceiro modo existe porque a escada não cobria tudo.** Inventário do que existe hoje, medido:

| forma de hoje | o que faz | coberto por |
|---|---|---|
| `AggravationStress(factor=1.5)` | `pd × 1.5` | **escalar** |
| `AggravationStress(factor_col="f")` | `pd × df["f"]` — fator **por linha**, coluna arbitrária | **nó da AST** |
| `CustomStress(angled_by_rating)` | callable; é o que a masterclass usa | **escada** (angula por rating, que é faixa de score) |
| `MonotonicStress(score_col, baseline, factor)` | `baseline − (score/1000) × factor` | **nenhum, e de propósito** — ver abaixo |

**`MonotonicStress` não é stress.** Ele **ignora `pd_col` inteiro** (`stress.py:96-97`): não multiplica nada, **substitui** a PD por uma reta sobre o score. É um **modelo de PD vestido de stress**, e o endereço dele na v0.6 é `outcome_from` com um nó — quem quer aquela reta calcula a coluna e a entrega. É o `mutate` antes do `filter`.

Com os três modos, a família `AggravationStress`/`MonotonicStress`/`CustomStress` — **três tipos e um callable** — vira **um campo com três modos, e nenhuma capacidade se perde**.

**Por que essa forma e não os tipos:**

- **É valor.** Frozen, comparável por igualdade, round-trippável — as três coisas que `CustomStress` quebrava por construção (`to_dict` devolvia `str(fn)`, `from_dict` levantava de propósito).
- **É a mesma grade que o resto da premissa usa.** A escada não inventa faixa própria; ela indexa os `bins` que `calibrate_on` já particiona. Zero mecanismo novo.
- **O nó não reintroduz o callable.** `col("f")` é AST — serializa, compara por igualdade, faz round-trip. O que morre é a **função opaca**, não o fator por linha.
- **Continua sendo UMA inflação, sem agregador.** `WorstCase(1.3, 1.8)` morre: sobre escalares o agregador é cerimônia com resposta predeterminada (`max(pd×1.3, pd×1.8) = pd×1.8` sempre); quando as hipóteses se cruzam é pior — o `max` por linha monta uma curva que **não corresponde a hipótese nenhuma**, medido custando **+70%** (0,0963 → 0,1643).
- **N hipóteses são N `Study`s**, comparados pelo verbo de leitura. Isso dissolve o `max(axis=1)` de `simulation.py:571-583` **por construção**, e o `UserWarning` dele morre junto com o caso que o gerava.

**`stress` e não `inflation`:** o pacote já tem a palavra (`stress.py`, `StressScenario`, `AggravationStress`), e já ficou decidido que **o stress *é* a inflação** — verificado: ele incide **só** em `swap_ins.index` (`simulation.py:657`); keep-in recebe `actual_default` intocado (`:625`). **Nunca foi cenário macro de livro.** `inflation` seria a segunda palavra para o mesmo conceito. **Morre o tipo, não a palavra.**

**Decidido nesta sessão, registrado como emenda (§9.1):** os três modos saem do ruling do dono de 2026-09-07 (*"escalar ou a família \*stress… uma escadinha"*) mais a constatação, ao inventariar o código, de que a escada sozinha **perdia o `factor_col`**. Isso **emenda** a decisão 8 do #152, que dizia apenas *"morre o tipo, não a palavra"* sem dizer que forma o valor toma.

#### `outcome_from` — de onde vem o desfecho

| valor | tipo | significado | sorteia? |
|---|---|---|---|
| `"parcelling"` (default) | sentinela | discretiza em `bins`, transfere a taxa do aprovado no balde, aplica `stress` | **sim** |
| `"flag_bureau"` | **string** | o desfecho **realizado** vem de fora — coluna 0/1 | **não** |
| `col("pd_modelo")` | **nó da AST** | **probabilidade por linha**, vinda de um modelo | **sim** |

**O tipo distingue as duas colunas, e a distinção é semântica, não estética.** Pela regra *"sorteia-se sempre o que não foi observado"*: a flag de bureau é **fato** — não há o que sortear; a PD de modelo é **hipótese** — é uma probabilidade, e probabilidade se sorteia. **String é nome de coluna observada; nó é expressão que produz probabilidade.** Nenhuma flag é necessária para separá-las.

Cada uma com seu erro duro: **string cuja coluna não é 0/1 levanta no bind**; **nó cujo valor sai de `[0,1]` levanta**.

> **Por que os dois caminhos existem, e a temporalidade que decide.** O #117 matou a coluna de PD por linha (*"quem tem PD de modelo materializa em 0/1 antes de entregar"*). O **#118, no mesmo dia e depois**, reinstalou: `estimated_default_col` viraria o eixo de desfecho recebendo **probabilidade por linha**, e o card diz textualmente que **não colide** com o caminho 0/1 — *"aquele é desfecho realizado dos negados, coluna 0/1; **este é probabilidade por linha**"*. **Pela regra de precedência deste documento, o #118 vence.**
>
> A casa que o #118 deu a esse caminho era o verbo `.rate` no eixo de desfecho. Esse verbo colapsou no #129, saiu da política no #155 e virou `take_up` no #152 — e **ninguém re-alojou o eixo de desfecho**. O terceiro modo acima é essa re-alojagem, e sem ele a v0.6 perderia um caminho que **nenhum card decidiu matar**.

- **O default literal nomeia o mecanismo na assinatura.** `outcome_from="parcelling"` aparece no `help()` dizendo que há parcelling rodando — a regra "nenhum default esconde a existência de um mecanismo" na forma mais forte, sem depender de o leitor inferir o mecanismo de `bins` e `stress` estarem por perto.
- **O modo string exige 0/1, com erro duro no bind, e é o que o #117 decidiu.** Hoje a coluna é tratada como **probabilidade** sem distinção (`simulation.py:548-550`, ligando `use_stochastic_draw` de lado). Separar os dois modos derruba a ambiguidade: **quem entrega fato entrega 0/1 e não sorteia; quem entrega hipótese entrega nó e sorteia.** Sem o erro duro no modo string, quem hoje passa `0.07` recebe o float lido como **desfecho realizado** e a inadimplência despenca — **mudança silenciosa de semântica**.
  **O que sobrevive do argumento do #117 e o que cai:** sobrevive que *"não infla"* vira **aritmética** sobre 0/1 (`1 × 1.8` clipa em 1, `0 × 1.8` = 0) e que a coluna 0/1 dispensa sorteio. **Cai** *"bureau e modelo colapsam num caminho só"* — o #118 mediu que **não colapsam**, e é a leitura mais recente.
- **`stress` junto com desfecho vindo de fora é ERRO DURO**, com mensagem óbvia (*"o desfecho veio de coluna; não há o que inflar"*), nos dois modos externos. Com dois tipos isso era inexprimível; com o tipo único é degrau 2. **Preço declarado da união.**
  Sobre o modo 0/1 a regra é aritmética antes de ser política: `1 × 1.8` clipa em 1 e `0 × 1.8` = 0. Sobre o modo probabilidade ela é modelagem: inflar a PD de um modelo é sobrescrever a hipótese de quem entregou o modelo.
- `outcome=` está tomado: o `DataSchema` usa `outcome` para a coluna **observada**.

#### O que a premissa faz morrer

A **cadeia de precedência silenciosa dos três caminhos de inferência** — `simulation.py:682` (coluna declarada) → `:691` (`rating_recipe`, com **`except Exception: pass`**) → `:723` (a cascata de score). Não era só o *score* que era inferido em silêncio: **o método também**.

E a **cascata `resolve_calibration_score_col`** morre **sem substituto único**. Ninguém procura score; ninguém aponta score. Medido no protótipo: **92,4% dos swap-ins caem fora do suporte dos keep-ins** no score em que a política antiga selecionou, e o motivo é **estrutural** — o incumbente **selecionou** naquele eixo. A cascata não era só arbitrária: **o primeiro fallback dela é a última coluna de `CutoffStage`, o score em que a política corta — a escolha com maior probabilidade de ter o suporte destruído por seleção. Ela tendia ao pior caso.**

**Correção de fato que a spec carrega, contra o texto que circulou por semanas:** quem cai fora do suporte **não recebe o PD global** — as bordas são empurradas para ±∞ (`_kernels/calibration.py:20-21`), então ele **grampeia no bin mais baixo** e recebe **a taxa do pior decil observado**. A direção do achado sobrevive (é **extrapolação, não medição**, e a inflação faz quase todo o trabalho sobre uma constante); **cai a magnitude implícita** — a imputação de hoje é **menos otimista** do que o texto sugeria. Segunda imprecisão: o piso de 50 keep-ins é sobre o **total**, não por célula.

### 4.5 `Study` — o encontro

```python
Study(schema, policy, premise, *, seed: int, name: str | None = None)
```

- **A premissa é posicional e obrigatória.** A fricção *"quatro construtores antes do primeiro número"* fica declarada como **custo assumido**, mitigada só pelo `repr`. Um default de premissa esconderia que existe imputação rodando.
- **`method` não existe.** Há **um** caminho de cálculo.
- **`seed` é obrigatório.** Duas políticas comparadas no mesmo estudo enfrentam o **mesmo sorteio**: a diferença entre elas é regra, nunca ruído.
- **`name` é opcional, com default posicional** (`study_1`, `study_2`…) preenchido na hora da leitura, **pulando rótulo já tomado**. **Duplicata é erro duro.** O nome **não persiste** — não sobrevive à serialização. Consequência aceita: **não há rastro experimento → deployment**.

**`vary` recebe o encontro inteiro** e pode sobrescrever **qualquer ponto declarado** — regra, schema ou premissa — desde que **por derivação**, e o resultado é descartável: dá dimensão de impacto, não vira config.

> **Reconstruir não é variar.** Reconstruir preserva só o que o autor lembrou de copiar; derivar preserva tudo que não foi pedido.

**O `repr` é o inventário do que falta declarar** — o achado mais transferível da pesquisa sobre `repr` (um `workflow()` vazio do tidymodels imprime `Preprocessor: None / Model: None`, e o print **é** a lista do que falta):

```
<Study challenger>
  Schema:  approved / hired / actual_default
  Policy:  4 filter (1 draw)
  Premise: bins=5, calibrate_on="global", take_up="binned", stress=1.8
  Seed:    7
```

Front-loading dói porque nada diz onde você está. O `repr` responde isso **sem tirar nenhuma declaração do caminho**.

**Recusa honesta, registrada:** não existe API fluente que crie o `Study` do nada. `DataSchema` e `CreditPolicy` são **irredutíveis** — são o que a ferramenta existe para tornar explícito. O "uau" do dplyr é começar no dado porque **no dplyr o dado é a única coisa declarada**; aqui há três papéis e um funil, e fingir o contrário compraria fluência com inferência silenciosa.

**Variação de premissa é outro estudo, não outra dimensão.** Esta regra fechou quatro forks: a lente, o stress no `vary`, o agregador de inflação e o take-up.

### 4.6 O motor

#### Três vetores, um dono cada

| vetor | o que é | moeda |
|---|---|---|
| `decision` | passou nos estágios da política — gera quadrante e taxa de aprovação | **0/1 sempre** |
| `contract` | contratou — gera volume e denominador | 0/1 sorteado |
| `outcome` | desfecho | 0/1 sorteado; **nulo fora do domínio** |

`new_approval` e `approved_pre_rate` morrem. Somem as temporárias `pass_prob_funnel` e `pass_prob_pre_rate` (`simulation.py:420-426`, deletadas em `:455-457`) — cada acumulador vira um vetor de saída com nome próprio.

**Ordem causal: contrato primeiro, desfecho depois.** Sorteia-se quem vira contrato; a marcação trazida é lida **só** de quem foi sorteado, o resto é descartado. Isso substitui a ponderação por esperança **como definição**.

**Origem do `contract` por quadrante:** keep-in = **observado** (`hired`); swap-in = **modelado**; swap-out/keep-out = 0.

**`decision` é 0/1 duro mesmo quando a mesa sorteia.** Ele é usado como **máscara** a jusante — decisão fracionária multiplicando em `contract` e `outcome` é literalmente a mecânica de peso que produziu a família de bugs #95/#97/#93. Preço declarado: *"determinístico"* passa a significar **determinístico dada a semente**, não livre de semente.

**`contract = decision × take_up`, aplicado uma vez pelo motor.** Medido: **o funil de hoje já fatoriza assim** — `|Δ| = 0` em 4 configurações, e nos keep-ins o take-up implícito **é** a coluna `hired` observada. Isso é **identidade, não analogia**.

#### A cadeia de domínio, e a soberania

```
decision  →  contract (domínio: aprovados)  →  outcome (domínio: contratados)
```

> **Domínio soberano.** O motor deriva os vetores pela cadeia. Marcação fornecida fora do domínio **recusa a base** (§4.1, item 5).
> **Critério de aceite:** a coluna emitida é **nula fora do domínio**, de modo que **a média ingênua esteja certa por construção**.

`Series.mean()` ignora nulo — então quem faz a média burra acerta, **não por ter lido a documentação, mas por não haver como errar**.

**Nulo não é status**, é *"fora do domínio deste cálculo"*, e é derivável. Sob a cadeia, "não contratado" e "sem desfecho observado" nem existem como casos a distinguir ⇒ **nenhuma coluna de status entra no contrato de saída por causa deles**. Dentro do domínio, ausência é **violação de invariante**.

**Duas asserções no ponto de montagem:** `contract > 0 ⟹ aprovado`; `outcome presente ⟺ contract > 0`. **Obrigatoriedade por construção passa a valer para a relação entre colunas, não só para nomes.**

**Limite declarado:** isso protege as colunas que o **motor emite**. `df["coluna_crua_do_usuario"].mean()` continua errada e **não há como proteger** — o contrato promete sobre o que o motor escreve.

**A garantia já existe hoje pela metade, por sorte:** `simulation.py:302-307` tem dois ramos e **só um mascara**. O ramo seguro sobrevive porque o outro morre com o analítico. **Não foi desenhado — sobrou.** Três sítios que a regra obriga a reler: `simulation.py:302-307`, `sweep.py:107-110` (repõe a marcação crua **exatamente nas linhas que o motor anulou de propósito**), `stages.py:444-448` (máscara pela decisão do **incumbente**, não pela nova, e `.fillna(0.0)` silencioso).

#### Sorteio: por linha, chaveado

> **Nenhum `np.random` global sobra no núcleo.** Cada sorteio vem de uma função determinística de **(semente do estudo, posição da linha na base ligada, nome do sorteio)**.

- **Sorteia-se sempre o que não foi observado. O que foi observado fica como está.**

| quem | motor faz |
|---|---|
| aprovado pelo incumbente **e** contratou | nada — fica o observado |
| aprovado pelo incumbente **e não** contratou | nada — *"não contratou" é observação, não buraco* |
| reprovado pelo incumbente | **sorteia a contratação**; se contratou, **sorteia o desfecho** |

- **Dois sorteios = dois nomes.** Hoje o motor **combina** taxa de contratação com probabilidade de calote; passa a **sortear em sequência**. Preço aceito: mais variância, administrável porque semente e sorteio nomeado são obrigatórios.
- **Por que chavear resolve comparabilidade:** hoje o sorteio é **posicional dentro da máscara**, e a máscara **muda com o corte**. Medido: o mesmo ponto de stress dá `0,51068308` dentro de uma grade de 6 pontos e `0,50880279` varrido sozinho, **mesma semente** — 0,19 p.p. **Semear fixa a grade inteira, nunca o ponto.**
- **A chave não é coluna, não é schema e não viaja** — é interna ao motor. Medido: **o motor nunca reordena** (zero `sort_values`/`sort_index`/`reset_index` em `simulation.py`, `stages.py`, `sweep.py`), então a estabilidade da posição é **por construção, não por confiança**.
- **Drop-in nos 4 sítios** (`simulation.py:604`, `:664`, `stages.py:458`, `:469`): sortear o vetor do tamanho da base e selecionar pela máscara. **Nenhuma máscara muda, nenhum cálculo muda** — só o número.
- **Custo medido (3 MM):** 39,3 ms/ponto hoje → 45,4 ms sem cache (**+7,4%**) → **0 ms com cache por estudo** (a chave é invariante em toda a grade). Cache: 4 × 3 MM × float64 = **96 MB**, escolha de implementação.
- **O paralelo fecha junto.** Os 0,41 p.p. sob `parallel=True` existem porque cada worker spawnado inicializa estado global próprio. Com o número derivado da chave, **worker nenhum precisa de estado compartilhado** — e a dependência de start method deixa de existir como pergunta. **Um mecanismo fecha os dois buracos.**
- `SeedSequence` fica no desenho como derivação **por nome de sorteio**, nunca por ponto de grade. Um fluxo consumido em ordem faria o segundo sorteio depender de quantos números o primeiro puxou (medido: 3 execuções idênticas dão 816/847/800 defaults) — **reprodutível, não comparável**. Um `spawn` por ponto daria **independência**, que é o oposto do que a grade precisa: a grade é **um estudo com N variações**, não N estudos independentes.
- **Não há migração:** `seed` tem **zero ocorrências** nos seis módulos do núcleo. Desenho em terreno vazio. (A prática correta já existe em `sample_data.py`, com `Generator` explícito — **falta a fronteira que a obrigue**.)

#### Um caminho de cálculo

**O método analítico morre.** `method` sai de **39 assinaturas** e **19 ramos** que bifurcam por método em `src/`.

O argumento não é performance — sortear custa **+7,9% serial / +5,5% paralelo** no notebook inteiro a 3 MM, e o multiplicador `k^N` que se temia **não existe** (no caminho rápido o método é pago uma vez sobre um baseline; delta plano em ~13% de 30 a 900 pontos). O argumento é o **ruling de patamar**:

> O pacote é um guia sobre premissas declaradas, e **a precisão do resultado está teto-limitada pela precisão da premissa** — que é escolha do usuário, não medição. Onde os dois caminhos discordam, **a discordância é menor que a arbitrariedade da premissa que os alimenta**.

Medido em política fixa a 3 MM, 6 rodadas: **aprovação e volume de keep-in com desvio exatamente zero** (não sorteiam); contratados −0,022%; inadimplência **0,019 p.p.**, viés a 1,6 erros-padrão de zero. **Escala de referência: o bug do caminho rápido erra 26× mais que o desacordo entre métodos.**

E, decisivo: **118 literais `"analytical"` contra 16 `"stochastic"` em `tests/`, com zero testes parametrizados por método.** Manter os dois caminhos significaria **escrever** a paridade que nunca existiu, não preservá-la.

Sai junto: o **tipo divergente da coluna `hired`** (`simulation.py:295` — numérico num ramo, `"Yes"/"No"` no outro) e a penalidade do ramo analítico em `summarize_results` (**2× mais lento**, num verbo que nem aceita `method`).

**O que se perde, declarado:** o analítico era **comparável por construção**. O substituto é o sorteio chaveado acima — e é por isso que os dois foram decididos juntos.

#### Núcleo funcional

**Os quatro `print_*` viram funções livres que devolvem tabela.** Fato que decide: **363 linhas, 41 operações de cálculo, zero valores devolvidos, todos `-> None`** — o número não existe fora do stdout, e quem quer usá-lo refaz a conta.

**Função livre, não método**, por duas razões:

1. **`delta_table` não tem receptor** — é N estudos contra um baseline; método só funciona se um dos N virar dono arbitrário da tabela.
2. **A regra ficaria partida** — *"cálculo sobre entrada = função livre, cálculo sobre resultado = método"* é regra por aridade, que o usuário tem que saber de cabeça. **Régua dplyr: verbo que recebe e devolve, uma regra só.**

**A apresentação continua no pacote**, como camada de borda que recebe a tabela pronta — versionada e testável. A alternativa (formatação sai) cobra recriar os helpers fora do pacote, sem controle de versão, em toda célula, para sempre.

**`visualization.py` fica, com import preguiçoso.** Medido: `import pycreditools` = **2294 ms**, dos quais **seaborn = 1105 ms (48%)**. Metade do tempo de import é a pilha de plot, paga hoje por todo consumidor que só quer os números. **Nenhuma API muda** — é aditivo.

#### A fronteira de produção

**Produção roda a metade 1 e para.**

| metade | o que faz | o que lê |
|---|---|---|
| **1** — funil (`simulation.py:414-457`, `:474-491`) | laço de estágios, decisão, motivo | **só as colunas que os estágios referenciam** |
| **2** — estudo (`:465-472`, `_classify_scenarios`, `_assign_simulated_defaults`, `_estimate_swap_in_baseline_pd`) | quadrantes, desfecho simulado, PD de baseline | os três papéis **mais a premissa** |

Não é motor separado nem duplicação: **é a mesma metade 1 que o estudo roda antes de continuar.**

**Os mocks morrem por construção.** Hoje `DeploymentPolicy.predict` fabrica `applicant_id`, `approved` e `default` (`deployment.py:419-434`) — e **eles não são inertes**: `approved = 1` **escolhe o caminho de código** e declara "todo mundo era aprovado antes" (**todo reprovado vira swap-out, swap-in fica vazio**); `default = 0` **zera a PD base do keep-in**; e as colunas só são removidas da saída, em silêncio. Os dois motivos do mock somem sozinhos: o schema **não está no artefato de deploy** (não há nome a cobrar) e o ramo `current_approval_col is None` morre com os três campos obrigatórios. **O mock fica inexprimível, não evitado.**

### 4.7 O contrato de dados de saída

> **A tabela é a interface.** O `CreditSimResults` sobrevive como **portador** do conjunto declarado, não como contrato. Tipo de resultado com acessores saiu da mesa: no dplyr o tibble *é* a interface, e objeto com acessores é **mais verbo, não menos**.

#### Declaração obrigatória **por construção**

> **A tabela de resultado tem exatamente UM ponto de montagem, e o esquema declarado é a entrada dele. Nada mais escreve na frame.**
> Dentro do montador, **nome é símbolo, não literal**.

Uma coluna não declarada não aparece porque **não existe outro lugar que a escreva**. Esta é a resposta à única pergunta em que as formas não empatavam: *o que faz uma declaração ser obrigatória de passar em vez de opcional de usar*. O `_types.py` perdeu porque **ignorá-lo não custava nada** — **13 usos contra 40 literais**. Aqui desviar não é caro: é **inexprimível**.

**`pandera` foi recusado, e não é "não agora":**

| eixo | por construção | `pandera` |
|---|---|---|
| complexidade | **deleção** — some o `is_sim_col` inteiro, somem os caminhos duplicados, somem as decisões de dtype espalhadas | **adição** — dependência, objeto de esquema, decoradores, **segundo vocabulário** — e nada sai |
| profundidade | módulo fundo: esquema entra, frame sai | módulo raso: interface adicionada |
| dtype | o montador **determina** | a validação **confere** |

**Determinar é mais forte que conferir.** E o valor inteiro do `pandera` — obrigatoriedade em runtime — **sai de graça** quando há saída única: comparar *declarado* × *o que de fato criei* são meia dúzia de linhas de stdlib. **O problema que ela resolve deixa de existir.**

**O estado que motivou a decisão**, medido: **34 atribuições de coluna** em `simulation.py`; `decision`/`reason` escritos por **dois caminhos independentes com o mesmo conteúdo** (a borda **recomputa** o que o motor já calculou); `hired` com **três dtypes em cinco linhas**; **483 sítios** de literal de nome de coluna (261 em `src`, 222 em `tests`).

**Dois limites declarados:**

1. **Colapsa o lado de escrita, não o de leitura.** Literal em posição de leitura não é forçado sem lint. Mas leitura errada dá `KeyError` — o contrato já pune. É **ergonomia, não correção**.
2. **A garantia é estrutural: vale enquanto a frame não circular mutável dentro do núcleo.** Isto é restrição que **a spec declara**, não suposição implícita.

#### Língua única

> **O motor fala uma língua só, inglês, em todo nome emitido e em todo valor que não seja apresentação.** pt-BR é apresentação e vive fora do núcleo.

Medido: as seis entradas pt-BR do `is_sim_col` têm **0 emissões** cada; as inglesas estão todas vivas. **Não há lista a manter — se é nome emitido pelo motor, é inglês.** A regra está gravada em `CONTEXT.md` § *Language of the code* e apontada do `CLAUDE.md`.

Isso mata de graça a docstring mentirosa de `to_decision_dataframe` (`simulation.py:169-171`), que promete nome pt-BR **e** valor pt-BR.

#### Dois esquemas: motor e borda

**O do motor:**

| coluna | papel | dtype |
|---|---|---|
| `decision` | passou nos estágios — **0/1 sempre** | inteiro |
| `contract` | contratou | inteiro |
| `outcome` | desfecho; **nulo fora do domínio** | nullable |
| `quadrant` | pertencimento **por decisão** | `category` |
| `study` | identidade do estudo | `category` |

`category` e nunca `object`: medido, **140 MB contra 5 MB em 5 MM de linhas (28×)**.

**O da borda** acrescenta `rating` — o rótulo de letra, produzido **sob demanda** por `to_decision_dataframe` e `export_*`. Ele **não entra no esquema do motor**: a régua de rating **não toca o funil**, e pôr o rótulo lá plantaria coluna cheia de nulo para quem não declarou régua (hoje: `df["rating"] = None` em `simulation.py:275` e `:289`).

**Nomes mortos:** `new_approval`, `approved_pre_rate`, `Rating` (capitalizado — capitalização é apresentação vazando para dentro de um nome), `decisao`, `motivo`, `contratou`, `inadimplente`, `cenario`. **`scenario` → `quadrant`**, porque `scenario` carregava dois conceitos (`Quadrant.*` e `stress_scenarios`) e o `CONTEXT.md` chama o conceito de *Quadrants*.

**`risk_rating` não é deste esquema** — é o **id numérico do grupo**, emitido pela régua de rating; `simulation.py` apenas **lê**, nunca escreve. A entrada dele no `is_sim_col` é morta, como as seis pt-BR. **`is_sim_col` morre inteiro**, com heurística de prefixo e tudo.

#### As quatro tabelas de leitura

```python
funnel_table(res)
delta_table(results, *, baseline=)     # formato longo: study × metric × value
quadrant_table(res)                    # era quadrant_summary
swap_in_table(res, *, by=)             # era swap_in_by_rating
```

Sufixo `_table` e não prefixo, por regra declarada: **sufixo é para variações de um mesmo tema**. `swap_in_by_rating` deixa de ter a quebra no nome e passa a tê-la em `by=`, que **generaliza**.

#### Sem coluna de dispersão

Nenhuma coluna de erro-padrão entra no contrato da grade. **O erro-padrão perde não por custo — perde por honestidade do número.** Ele mede ruído amostral (**0,018 p.p.**) enquanto a incerteza dominante é a da premissa declarada, ordens de grandeza maior. Uma coluna `std_error` ao lado de `default_rate` é lida como *"±isto é a minha incerteza"*, **e isso é falso**. **Custo zero de computar não é custo zero de ter.**

A obrigação muda de lugar e vira **critério de aceite de documentação**:

> A documentação diz que **todo número sai de um sorteio**, logo carrega margem — com os dois números medidos: **0,018 p.p.** em rodada única, e **0,41 p.p.** entre rodadas **semeadas** com `parallel=True`.

O segundo é **23× o primeiro** e é o que efetivamente surpreende (*"pus semente e deu outro número"*). E o estado de hoje é **pior que omissão**: `README.md:419-423` diz que o pacote *"prevents stochastic noise"* — o leitor sai achando que ruído é coisa que o pacote **evita**.

### 4.8 Grade e seleção

#### `tradeoff` — um verbo

```python
tradeoff(study, df, *, ranges: dict[str, Sequence], by: str | None = None) -> DataFrame
```

`sweep` e `tradeoff` colapsam. O backend já era unificado desde a v0.5; dos dois conteúdos reais do `tradeoff`, o renomeio de métrica **evaporou** com o ponto de montagem único, e a desambiguação da coordenada vira responsabilidade do verbo único.

**O custo de manter os dois já estava materializado:** o `TradeoffAnalyzer` **não repassava `method`** (`analysis.py:97`), então o estocástico era **inalcançável por cima**. Duas superfícies para o mesmo ato **divergiram sozinhas**.

O nome é `tradeoff` — a palavra do domínio — **contra a recomendação de quem grilou**, que propunha `sweep`. **Preço declarado e aceito:** é substantivo em posição de verbo, e o pacote assume esse desvio da gramática dplyr em troca de falar a língua do usuário. **`sweep` sobrevive como nome interno.**

**`TradeoffAnalyzer` morre:** não é tipo, é **construtor de dicionário com nome de tipo** — os três `vary_*` preenchem entradas que `ranges=` recebe direto. Sem estado, sem invariante, nada escondido: **interface adicionada sem nada por baixo**. Quebra em 22 sítios.

**`OptimizationResult` morre inteiro.** Nenhum dos cinco campos sobrevive: `best_combination` e `metrics` mortos pelo fim do best-pick; `all_results` **é** a tabela; `pareto_frontier` vira saída de seletor; `params` carrega dois argumentos mortos, `method` morto e `cutoff_steps` substituído por `ranges=`.

#### O contrato da tabela de grade

Uma linha por **(grupo, ponto)**:

| coluna | papel |
|---|---|
| `study` | identidade do estudo |
| `{label}` (uma por dimensão varrida) | a coordenada — **label cru, sem sufixo** |
| coluna de grupo (com `by=`) | chave do grupo |
| `approval_rate` | aprovação **pré-take-up** sobre a base |
| `take_up_rate` | conversão de aprovado a contratado |
| `default_rate` | inadimplência **ponderada por contratado** |
| `baseline_approval_rate` · `baseline_take_up_rate` · `baseline_default_rate` | as mesmas três, **medidas** no cenário vigente |
| `approval_denominator` | denominador da aprovação — **é o tamanho do grupo** |
| `default_denominator` | denominador da inadimplência — contratado **e** observado, ponderado |

**Mortas:** `overall_approval_rate`, `overall_default_rate`, `{col}_cutoff`, `combination_id`, `constraints_met`, `tradeoff_score`.

**O label cru, sem `_cutoff`:** o sufixo seria **vocabulário morto** — nomearia um estágio que não existe mais — e quebraria a simetria chave-entra/chave-sai. **Colisão entre label varrido e coluna de grupo é erro duro.**

**Três métricas, não duas** (ruling do dono contra a recomendação): hoje a grade publica aprovação **pré-take-up** e inadimplência **entre contratados** — populações diferentes —, e **sem o take-up o volume contratado não é derivável da tabela**. Preço transferido: as candidatas a eixo de Pareto passam de duas para três, e o par *(aprovação, take-up)* é possível e **não tem sentido de negócio** ⇒ **declarar os eixos deixa de ser conveniência e vira necessidade**.

**O vigente viaja como coluna, e é derivação interna sem tipo próprio:**

- **Ele é medido, não simulado.** Fora do dado sintético **não existe score que reconstrua a decisão tomada** — há drift de score e regra no tempo, e há overrides. **Só pode ser observado.** Derivá-lo rodando o motor seria inferência silenciosa da pior espécie: **um número de referência fabricado, apresentado como o que a casa faz hoje.**
- **Não tem nada a declarar** — os outros quatro tipos existem porque o usuário declara algo neles.
- **Argumento de correção, não de elegância:** as métricas do vigente têm que usar **a mesma definição** das colunas da grade, ou "iso-aprovação" compara coisas diferentes. Computar no mesmo lugar torna a coerência **estrutural em vez de documentada**. Mata duplicação viva: `performance.py` recalcula isso à mão em **cinco sítios**.
- **Passar a referência é a porta pela qual o alvo volta:** `reference=0.302` é, na assinatura, indistinguível de `target_default_rate=0.08`. Como coluna, a confusão é inexprimível.
- **Custo medido (3 MM):** 45 ms na base inteira, 158 ms em 5 regiões, 230 ms em 300 lojas — contra ~712 ms de uma grade de 900 pontos. **Uma vez por chamada = 6% do caminho rápido**; por ponto seriam 40 s, **57× a grade inteira**.
- **Preço declarado:** a tabela passa a **misturar duas proveniências** — colunas simuladas ao lado de colunas medidas. **A spec declara isso explicitamente.**

**Os denominadores existem porque percentual não soma.** Uma loja de 40k propostas aprovando 71% e outra de 900 aprovando 64% não têm média igual à aprovação da empresa. **Custo: zero** — o contador já os calcula para dividir; hoje ele os **joga fora depois de dividir**.

> **Regra: toda coluna que é denominador nomeia a métrica que ela divide.**
> Com `<métrica>_denominator`, consolidar grupos vira **uma fórmula só**: `soma(taxa × denominador) / soma(denominador)`.

`take_up_denominator` **não** viaja: é derivável (`approval_rate × approval_denominator`). **A grade publica precisamente os dois que não são deriváveis.**

#### `by=` — um por grupo, e nunca modelagem

> **`by=` significa "um por grupo"** — uma grade por grupo (`tradeoff`), um critério por grupo (`choose`), uma tabela quebrada por grupo (`swap_in_table`), uma régua ajustada por grupo (`suggest_rating`). **Um sentido nos quatro.**
> **A régua de imputação é global, SEMPRE — nenhum argumento a particiona, nunca.**

O segundo enunciado é o que de fato se mediu, e **solto ele protege a régua em todo lugar**, não só onde `by=` aparece. O eixo real não é "leitura × modelagem" — é **"sem ninguém ter pedido"**: no `tradeoff`, particionar a régua era efeito colateral escondido; no sugestor, ajustar uma régua por segmento **é o produto do verbo**.

**O que isso corrigiu:** o laço ingênuo chama a varredura sobre `data[data.region == r]`, e como a régua é aprendida **dentro** da simulação, **hoje o notebook calibra uma régua por região**. Sob régua global, **os cinco cortes regionais mudam** — e não são número solto: o `validation/README.md` os reporta nominalmente (**752 / 785 / 732 / 694 / 680**) como *"idênticos nas 5 regiões"*.

**Por que régua global e não uma por grupo:** na cauda longa (300 lojas de ~1k linhas), cada decil de cada loja tem ~100 linhas, das quais só as contratadas-e-observadas contam. Um PD sobre algumas dezenas de linhas **balança vários p.p. por amostra, e esse ruído vira a régua daquele grupo** — contaminando todos os pontos de grade dele. **A curva da loja pequena seria desenhada pelo azar de 30 pessoas.**

**Consequência de leitura:** o número consolidado e a soma dos números por grupo contam **a mesma história**. Com régua por grupo eles não bateriam, e **a diferença não seria da realidade — seria da régua ter mudado no meio**.

**Se a heterogeneidade entre grupos for real e importar, a forma honesta é declarar** — outro `Study`, outra premissa, um estágio que endereça o segmento —, nunca como efeito colateral de um argumento de agregação.

**Grupo pequeno:** roda todos; onde a premissa não engata, **o número sai nulo, com a cobertura ao lado**. Nem piso que levanta (mataria o `by=` no caso de 300 lojas — abortar por uma loja de 40 propostas é o oposto do passeio no parque), nem exclusão calada, nem queda para o PD global — **essa não é ausência de resposta, é resposta errada com cara de certa**.

#### O mecanismo: nunca picote a base

> **Nunca picote a base. Varra sempre a população inteira, e separe por grupo só na hora de contar.**

- Base **ordenada uma vez**; um corte deixa de ser uma varrida e vira **uma posição** (`searchsorted`).
- As somas de `_metrics` viram **totais corridos**, lidos por posição — **uma passada responde a grade inteira**.
- **O grupo é mais um eixo do mesmo contador.** Cada linha é visitada uma vez. **300 grupos custam a mesma passada que um.**
- **Os totais corridos são nos dois sentidos** (`gte`/`lte`), e **cada sentido é calculado na sua própria varrida — nunca derivado por subtração**. `sufixo = total − prefixo` **come casas decimais onde a fatia é pequena**, e a DoD de exatidão exige referência de fora batendo **na fronteira**. Duas varridas continuam sendo **uma** passada.
- **É a mesma máquina do caminho rápido.** Um usa "posição no score" como eixo, o outro "grupo". Decididos como **um** mecanismo — em releases diferentes seriam o mesmo trabalho duas vezes, a segunda por cima de código assentado.

**Diagnóstico que fundamenta:** o número de grupos **não custa** — G grades sobre N/G linhas é uma grade sobre N linhas. O que custa é o **custo fixo por chamada de sweep, pago G vezes**. Os **13,9× medidos com 300 lojas** não são problema de otimização: são consequência de ter picotado a base. **Não se conserta — deixa de existir.**

**No caminho que re-simula, `by=` também é quase de graça**, por outro motivo: a simulação já roda sobre a base inteira, então o grupo é só a separação da soma final. **Uma regra, duas implementações.**

#### `choose` — um verbo, critério nomeado

```python
choose(grid, *, criterion, maximize="approval_rate", minimize="default_rate", by=None) -> DataFrame
# criterion ∈ {"pareto", "hold_approval", "hold_default"}
```

**Filtra e devolve as linhas que passaram.** O apetite segue sendo `df[...]` do leitor — **uma regra só para estreitar**.

**Um verbo e não três irmãos** (decisão do dono contra a delegação da sessão): **um verbo põe o cardápio inteiro no `help()`, que é a resposta ao problema real — o leitor não saber que a pergunta existe** — e atende literalmente o critério declarado *menos verbos*.

**Preços declarados:**

- **Assinatura-união:** `maximize=`/`minimize=` valem só para `"pareto"`, **erro duro** nos outros. É explícito e apenas irregular — **não é inferência silenciosa**.
- **`choose` lê como "escolher um"**, e o verbo devolve **199 de 225 pontos** no livro medido. O que limita o dano é **estrutural, não editorial**: **nada nesta camada consegue devolver uma linha por juízo próprio**. **A spec diz que o retorno é conjunto.**

**Nomes recusados, por colisão medida:** `select` (em dplyr/polars escolhe **colunas** — mesmo nome, **eixo invertido**), `candidates`, `screen`, `optimize` (lê como *"achei o melhor"*), `filter` (já ocupado na política).

**`criterion=` e não `method=`:** `method` está sendo morto de 39 assinaturas nesta mesma versão; reusar a palavra com sentido novo seria a duplicata que a língua única mata.

**Os critérios:**

- **`"pareto"`** — fronteira de dominância. **Eixos declarados com default literal na assinatura.** Default na assinatura **≠ inferência**: é visível no `help()`, **estável quando a grade cresce**, e sobrescrevível; varredura de colunas mudaria de resposta conforme o dado. **Métrica nomeada inexistente = erro duro na chamada.**
- **`"hold_approval"` / `"hold_default"`** — devolvem **os dois pontos que ladeiam** o vigente no eixo. **Não fazem banda por tolerância**, e a banda **morreu medida**:

| tolerância | regiões que devolvem nada |
|---|---|
| 0,10% | **5 de 5** |
| 0,25% | 3 de 5 |
| 0,50% | 2 de 5 |
| 1,00% | 0 de 5 — mas **exatamente 1 linha** em cada |

Passo mediano da grade no eixo de aprovação: **1,53%–1,71%**. **A tolerância disputa espaço com o passo**: abaixo dele a banda é vazia, e o primeiro valor que devolve algo devolve **um** ponto. **O tamanho do resultado é governado pela resolução da varredura, não pela pergunta** — e a correção natural do leitor é alargar a tolerância até aparecer alguma coisa, **calibrando-a contra o sweep em vez de contra o negócio**. É o mecanismo que pôs o `.head(1)` dentro do `find_equivalent`: **vazio era o caso comum.** Um default de tolerância derivado do passo consertaria, e é exatamente a inferência que a §4.11 proíbe. **Bracketing não tem parâmetro nenhum — é regra, não valor calibrado.**

**O bracket expõe a resolução da grade em vez de escondê-la** (largura medida no eixo de inadimplência: de 0,0 a 3,3 p.p. entre regiões). Quem quer resposta mais fina **aumenta os passos** — decisão que uma tolerância no chute encobre.

**Regra de família, deliberadamente irregular:** seletor **ancorado no vigente** é `hold_<métrica>`; seletor **não ancorado** leva o nome do próprio algoritmo. O Pareto genuinamente não é irmão — **ele ignora as colunas `baseline_` que definem os outros dois**.

**Limite declarado do nome:** `hold_approval` diz que a aprovação foi mantida; a decisão devolve dois pontos que a **ladeiam**, nenhum a mantendo exatamente. **A spec diz que a resposta é um bracket, não uma igualdade.**

**Caso vazio: um só modo de falha, e é erro duro** — **o vigente está fora da faixa varrida**, explicado na língua do leitor (*"você varreu 3,6%–76,7% de aprovação e seu livro está em 17,7%"*). **É a varredura errada, não artefato de tolerância.** Pareto nunca é vazio.

**Limite declarado do apetite:** como ele não ganha verbo, **o pacote não tem de onde levantar erro** quando o corte não devolve nada — é o `df[...]` do usuário. *"Nenhuma solução aceitável"* fica **protegido onde há verbo e desprotegido onde não há**. **É limite, não garantia.**

**Fatos de escala que sustentam a postura consultiva:** a fronteira de Pareto é **39,7% da grade a 30 passos** e **88,4% a 45 passos** no mesmo livro. **Quem corta de verdade é o apetite (88,4% → 46,7%), não o Pareto.**

> **A fronteira tende à grade inteira conforme a grade melhora. Qualquer verbo com cara de "acha o melhor" mente mais quanto melhor for a simulação.**

#### Não existe parâmetro de negócio

**`target_default_rate`, `min_approval_rate` e o best-pick oculto morrem.** O best-pick eram **três critérios empilhados sem nome**: o peso mágico `aprovação − 5 × inadimplência`, o `.iloc[0]` após ordenar, e o **fallback silencioso** quando nenhum ponto satisfaz.

Evidência de que já eram ruído: **a célula 19 da masterclass passa `target_default_rate=0.08, min_approval_rate=0.01` e descarta o resultado deles** — lê só `pareto_frontier`. `best_combination`, `metrics` e `constraints_met` **não são consumidos em lugar nenhum do notebook fundacional**.

**A distinção que precisa ficar escrita:**

- **Alvo como fluxo do usuário: vivo.** *"Apetite de 8%, me dá o corte por região"* é `grid[grid.default_rate <= 0.08].groupby("region")` + o máximo de aprovação. **Isso é otimizar contra alvo.**
- **Alvo como conceito do pacote: morto.** Não vira tipo, não vira argumento do motor, não viaja dentro da política.

**A fronteira honesta:** filtro resolve alvo como **teto** ou **piso** — predicado linha a linha. **Não** resolve alvo como **igualdade sobre um agregado dos grupos**. Esse é o **único ponto medido** em que a resposta "sem tipo, só filtro" cobra preço real do usuário: ele escreve a bisseção. Fica no backlog, nomeado.

#### O fluxo de dois estágios é padrão de uso, não recurso de motor

Rodar global, chegar num cenário conhecido, usar a inadimplência pós-política como novo alvo, e reotimizar por região com faixa estreita — **já roda hoje**, e o próprio notebook declara o mecanismo: *"Cache each region's cutoff → frontier with ONE fine sweep, then the reallocation search reads off the cache — no re-simulation inside the loop."* É **"a grade é cache"** funcionando na prática.

**Mas o motivo de estreitar muda.** Estreitava-se por **custo**; com o eixo de grupo saindo de graça, esse motivo evapora. Sobra outro, melhor e permanente: **resolução** — 30 pontos espalhados na faixa inteira dão 30 pontos quase todos inúteis; 30 pontos na faixa que decide dão 30 úteis.

**A faixa é sempre declarada.** Se o motor derivasse a faixa do segundo estágio por grupo, **herdaria G vezes** o problema de faixa medido: a grade parando antes do platô, cada grupo numa faixa diferente.

### 4.9 Sugestores, rating e deployment

#### Não existe protocolo fit/predict

**Rating é um sugestor standalone**, na mesma postura consultiva do otimizador: **entra base, sai sugestão, o humano usa ou não.** `suggest_hard_filters` já tinha essa forma; `fit_risk_groups` era **o mesmo ato vestido de fit/predict** — devolvendo um objeto que aplica a si mesmo.

```python
suggest_rating(df, *, score, by=None, ...) -> RatingRule
suggest_hard_filters(...)                          # já existe, intacto
apply_rating(rule, df, *, seed=None) -> DataFrame
```

`suggest_*` vira **família de verdade** — prefixo alimenta autocomplete **e** índice de referência.

- **`score=` escalar ou tupla = cruzar os scores numa grade.** **Comparar N candidatos é `for`, não argumento** — dar à tupla o segundo sentido tornaria *"cruze principal × challenger, para cada um de 3 challengers"* **inexprimível**.
- **`by=` cobre segmento e tier, e com isso `screening` colapsa aqui dentro**: `ScreeningRecipe` guarda `boundaries: dict[tier, cortes]` e `sub_mappings`, que **é** a forma `segmented_intervals` do rating com a partição vindo do tier.
- **`seed` é argumento de `apply_rating`, ignorado por quem é determinístico.** Sortear **não separa os verbos**: a régua da UX vale mais que marcar estado aleatório no nome.
- **O sugestor não exige schema** — medido, ele lê da base exatamente **duas** colunas de papel e **não toca `approved` nem `hired`**. `DataSchema` fica intacto.
- **As regras da política entram como filtro opcional** (clusteriza só quem sobrevive), sem acoplar o sugestor à política.

#### A saída é a regra, como tipo próprio

Duas formas: **corte** (1 score) e **grade** (2+ scores: célula → rating). `quantile_breaks` e `cluster_mapping` viram **interno do algoritmo e nunca escapam**.

**A regra exportada é corte puro.** Empurrar reprovado para um rating reservado é **composição do humano**, não conteúdo da regra — senão a regra passa a referenciar a política e **deixa de ser independente**.

**O que isso conserta, medido:** hoje `GroupingRecipe` tem **três formas mutuamente exclusivas** e `predict` é um if/elif/else sobre qual está preenchida. **Só a terceira sai do fit** — a primeira, que é a regra legível, **só entra por JSON importado**. Para exportar a regra a partir do fit, o código faz **`for s in range(0, 1001)`**: varredura de inteiro por força bruta que **assume domínio de score 0–1000 e exporta regra errada, em silêncio, para qualquer outra faixa.**

**Declarado-vs-ajustado não vira regra do pacote.** Não há spec declarada a tipar: **o sugestor é o verbo, a regra é o produto**. O `params: dict` morre — medido **write-only** e **incompleto**. E `fit` é função livre, não método.

**Sintoma que isso apaga:** a spec declarada já estava **duplicada e divergente** — `derive_survivor_rating` redigita `bins=10, max_groups=5, min_vol_ratio=0.02` contra os defaults do próprio fit (`bins=20`, `min_vol_ratio=0.05`).

#### Rating são dois objetos

| | **régua declarada** | **rótulo relativo à população** |
|---|---|---|
| onde vive | motor / artefato de deploy | **Studio** |
| quando ajusta | uma vez, declarada, serializada | re-ajusta **a cada rodada**, sobre os sobreviventes |
| toca o funil | **não** | **não** |

**Regra é o que muda quem passa; a régua não muda.** Medido: `rating_recipe` não filtra, não corta, não taxa. **O rótulo relativo é derivado do bind e nunca entra no motor.**

#### Morrem

Os **quatro `predict`** (o do `GroupingRecipe` com três formas em if/elif/else; `RiskGroupResult.predict`, **delegação de uma linha**; `ScreeningResult.predict`, que **pede um argumento que o próprio recipe já carrega**; `DeploymentPolicy.predict`, que **roda o motor**). `fit_risk_groups`, `fit_pairwise_risk_groups` (**é um `for` sobre challengers**), `fit_risk_segments`, `ScreeningRecipe`, `ScreeningResult`, os shims `find_risk_groups`/`screen_risk_segments`. A varredura `for s in range(0,1001)`. Os mocks de `deployment.py:419-434`. O `params: dict`.

**E o teto `.get(rat, 5)`**, que **colapsa qualquer rótulo além de "E" em 5** enquanto a saída remapeia 1..26 → A..Z — **uma régua de 6 faixas volta com 5**.

### 4.10 Serialização e identidade

**Duas unidades, com propósitos diferentes — não uma com modos.**

| unidade | carrega | não carrega |
|---|---|---|
| **deploy** = parametrização de motor | **todos os `stages`** + a régua de rating (opcional) | schema, premissa, seed, nome |
| **estudo** = reprodutibilidade | schema + política + premissa + `seed` | **base, impressão digital da base, nome** |

```python
export_rules(policy, *, rating=None)    # unidade de deploy
export_study(study)                     # unidade de estudo
load_rules(...) / load_study(...)
```

O prefixo põe as duas no autocomplete, **que é onde a decisão deveria estar visível e não estava** — a superfície tinha um `export` só.

**Por que o deploy não leva o schema:** os três papéis são vocabulário de estudo **retrospectivo** — em produção não existe desfecho nem histórico de aprovação. As colunas que as regras de fato leem **já viajam dentro do próprio estágio**, pela linha papel≠referência.

**Por que o deploy não leva a premissa:** decidir aprovar **não usa premissa**. Se o artefato de deploy fosse o `Study`, ele **obrigaria declarar premissa para fazer decisão que não usa premissa nenhuma**.

**A unidade de deploy é "todos os `stages`", sem exceção escrita.** A regra intermediária *"estágio que alimenta `contract` não entra no deploy"* foi **revogada**: não existe mais estágio que alimente `contract`. **A exclusão deixa de ser regra a lembrar e passa a ser verdade por construção** — o take-up mora na unidade de estudo porque é campo da premissa, e a unidade de deploy não carrega premissa.

**Por que o estudo não carrega a base nem hash dela:** hashear o df a cada bind daria ao objeto **opinião sobre qual dado é o certo**, contrariando *"mesma política sobre N bases"*, que é a motivação da decomposição. **A garantia de reprodutibilidade vem do seed obrigatório, não de rastrear dado.**

**Achado que vale registrar:** o artefato de deploy **já existe** — `DeploymentPolicy` é exatamente `policy + rating_recipe`, e `to_dict` é alias de `to_production_rules`. **Está mal separado, não ausente.** O `metadata` que ele carrega hoje morre inteiro.

**Round-trip total por construção, não por disciplina.** Com callable inexprimível, **nenhum ramo de `to_dict` pode degradar**. Morrem o `CustomStress` e seu `to_dict`/`from_dict`, e o **degradê gêmeo não catalogado**: `FilterStage.to_dict` troca callable por `{"name": fn.__name__}` e `from_dict` reconstrói string/`Expression`, **nunca a função**. Mesma patologia, dois lugares.

**Congelamento fundo.** Todo tipo-valor é **frozen dataclass, folhas inclusive**; `__post_init__` normaliza `dict`/`list` para `MappingProxyType`/`tuple`. O usuário segue passando `dict` normal.

É o **único** caminho em que o `copy.deepcopy` do `_replace` morre de verdade: frozen raso deixa `p.stages[0].cutoffs["score_a"] = 500` passar — exatamente a **imutabilidade de fachada** que a v0.6 mata. Cópia defensiva na leitura foi descartada por alocar no **caminho quente do sweep**; `MappingProxyType` não aloca na leitura.

Estado medido: **nenhum `Stage` é dataclass**; as classes de stress são classes comuns com atributos livres; `GroupingRecipe` é `@dataclass` **não**-frozen com `list`/`dict` mutáveis. **Sem `pydantic`** — stdlib basta.

**Default que troca semântica em silêncio é erro duro.** `AggravationStress.factor_col`: `if self.factor_col and self.factor_col in df.columns` — **errar o nome troca a semântica para o fator escalar, sem aviso**. **Nome de coluna declarado e ausente levanta no bind, sem fallback.**

**Identidade é do `Study`** (§4.5). **Coluna `study` em toda tabela de verbo**, porque **`pd.concat` não preserva atributo de objeto nem `metadata`** — sem a coluna, o `for` sobre N estudos produz **pilha indistinguível**.

**Comparar-N não precisa de verbo.** `simulate` aceita uma **coleção** de `Study` e devolve a tabela longa (uma linha por estudo); `delta_table(results, *, baseline=)` faz a leitura. Como a coluna `study` já existe **precisamente para o `pd.concat` funcionar**, um verbo `compare` seria a mesma pergunta feita duas vezes. **Morre `compare_policies`** — por posição, com recursão sem rótulo por item e colunas literais `"Old"`/`"New"`.

> **Emenda declarada:** isto **substitui** a decisão de que comparar-N é verbo de primeira classe. O conteúdo daquela decisão sobrevive inteiro (**tabela longa, uma linha por estudo, sem tipo contêiner**); o que muda é que o verbo que a produz é o `simulate`, não um `compare` irmão.

**O baseline default é o cenário atual**, derivado da coluna `approved` — **não é um `Study` da coleção, é o que o livro já fez**. `baseline=` nomeado é override apontando um estudo **pelo nome**; nome inexistente = erro duro.

Correção que sustenta isso: os quadrantes **já** são relativos à coluna histórica, não a uma segunda simulação — **metade do que o verbo reporta já tinha o "atual" como baseline**; a outra metade é que exigia a segunda simulação por posição.

### 4.11 Regras transversais

#### A escada de remédios contra o silêncio

> **Nenhuma inferência silenciosa. Todo caso em que o motor resolveria algo sozinho sobe ao degrau mais alto que couber:**
> 1. **inexprimível por construção**
> 2. **erro duro no bind**
> 3. **número reportado no resultado**
>
> **Não há quarto degrau. Silêncio é proibido.**

**O critério do degrau é pelo que o REMÉDIO precisa saber** — três perguntas em ordem, a primeira que der "sim" fixa o degrau:

1. Dá para checar **sem a base**? (combinação inválida de tipos ou campos) → **1**
2. Precisa da base, e existe **certo/errado objetivo**? (nome que não existe; valor fora do domínio) → **2**
3. Precisa da base, mas é **grau e não erro**? (cobertura, suporte, tamanho de grupo) → **3**

O critério foi escolhido **por reproduzir seis rulings já tomados, sem exceção** — não é regra nova imposta sobre decisões velhas, é a regra que já estava sendo aplicada sem nome.

**O degrau "aviso" não existe.** Dos 16 `warnings.warn` do núcleo, **13 são sobre dado e nenhum sobrevive**. Morre inclusive o `CalibrationReliabilityWarning`, **o mecanismo mais bem construído do pacote e ainda assim o errado**: a docstring dele entrega o desenho — a categoria própria existe *"so a user can mute them with a single `filterwarnings`"*. **Foi desenhado para ser silenciável, e remédio silenciável é, para o desatento, remédio silencioso.**

> **A régua: o critério não é avisar o usuário atento; é o desatento não conseguir errar.**

**O degrau 3 é passivo de propósito.** A resposta a isso **não é pendurar um aviso nele** — é **subir de degrau**. **Caso que não tolera passividade não pertence ao degrau 3.**

`DeprecationWarning` sobre API fica **fora** desta regra — é ferramenta de migração, não inferência.

**Nenhuma detecção, em forma nenhuma.** O caso do 0-preenchido dentro do domínio **não é detectado e o pacote não promete detectar**. A razão é fronteira de produto, não cautela estatística:

> **Nem a definição de "mau" é uma só.** FPD, SPD, ever60m6 são desfechos diferentes, e a escolha é do usuário. **Não há padrão a criar — logo não há do que inferir.**

Detecção por *"proporção de zeros implausível"* seria **inferir, a partir do dado, um julgamento sobre o dado** — o caso 1 outra vez. **A regra deste documento proíbe a detecção que ele mesmo poderia ter proposto.**

**Suporte de calibração: mede e reporta como número; não avisa e não recusa.** Suporte é grau, não erro.

**Casos residuais fechados pela regra:**

- **`except Exception: pass` na reconstrução de política morre.** Assimetria medida: 12 sítios leem `metadata["policy"]` **direto, sem `try`**; só dois embrulham e engolem. Falha de desserialização é objetiva ⇒ **erro duro**. E com round-trip total por construção, `from_dict` falhando **deixa de ser caminho esperado e passa a ser bug de verdade.**
- Heurística de coluna de segmento: **violação de regra de língua**, não julgamento caso a caso.

#### As três categorias de argumento

| categoria | promessa | exemplos |
|---|---|---|
| **modelagem** | **muda** o que o motor calcula | `ranges=`, `seed=`, `bins=`, `calibrate_on=`, `take_up=`, `stress=`, `outcome_from=`, `draw=`, `score=` |
| **leitura** | **nunca** muda o que o motor calcula | `by=`, `criterion=`, `maximize=`/`minimize=` |
| **identidade** | não muda número nem leitura; **endereça** | `label=`, `name=` |

A terceira existe porque o teste binário é **binário demais**: `label=` e `name=` não mudam número e não dizem como ler — **eles endereçam**. Sem a terceira categoria, `label=` seria forçado a "leitura" e a regra ficaria frouxa **no ponto em que ela mais precisa ser dura**.

**Auditoria sobre toda a superfície pública: zero violações.**

#### Regras de nome

- **Prefixo para família** (`suggest_*`, `export_*`, `load_*`) — alimenta autocomplete **e** índice de referência.
- **Sufixo para variações de um mesmo tema** (`*_table`).
- **Toda coluna que é denominador nomeia a métrica que ela divide.**
- **Um nome por papel.** Nome reaproveitado numa família significa a mesma coisa nos dois lugares — e a mesma coisa leva o mesmo nome (por isso `plot_tradeoff` recebe `criterion=`, não `highlight=`; preço declarado: `highlight` avisava que o gráfico **não descarta** pontos, e essa diferença passa a ser do verbo, não do argumento).
- **Nenhum default de modelagem esconde a *existência* de um mecanismo — só a sua parametrização.**

### 4.12 Como a família se anuncia

Sem isto, o resto é decoração — e é a metade da pergunta que nenhum card fechado tinha tocado.

- **`__all__` agrupado pelos três estágios** — declarar / calcular / ler — **na ordem do fluxo**. São ~20 nomes; cabe à mão.
- **`help(pycreditools)` imprime as duas linhas da espinha** e as três listas. **É o único lugar em que *"método declara, função livre calcula"* pode ser lido antes de ser descoberto na marra.**
- **"Veja também" recíproco em todo verbo**, apontando o próximo do fluxo (`simulate` → `funnel_table`; `tradeoff` → `choose` → `plot_tradeoff`). **Regra: nenhum verbo fica sem apontar o seguinte.**

---

## 5. As costuras (seams)

**A regra:** preferir costura existente a costura nova, e usar sempre a **mais alta** possível. Quanto menos costuras, melhor — **o ideal é uma**.

Aqui são **quatro**, e as quatro **já existem** (são os verbos públicos). Nenhuma costura nova é aberta abaixo delas.

| # | costura | o que se observa por ela | por que ela e não uma mais baixa |
|---|---|---|---|
| **1** | `simulate(study, df) -> res` | schema e bind, política e funil, premissa, os três vetores, a cadeia de domínio, o sorteio chaveado, a cobertura, o esquema do motor | **É a costura mais alta que existe.** Tudo que a §4.1–§4.7 decide é observável aqui, na tabela. Testar `Stage.apply` ou o kernel de calibração diretamente pinaria implementação, não contrato |
| **2** | `tradeoff(study, df, ranges=, by=) -> grid` | contrato da tabela de grade, coordenada por label, as gêmeas `baseline_`, os denominadores, `by=`, e **a exatidão do caminho rápido** | O caminho rápido é um **mecanismo próprio** com portão próprio (§6). A exatidão dele só é afirmável comparando esta costura com a costura 1 — **é a única costura em que a garantia satura** |
| **3** | `choose(grid, criterion=, by=) -> grid` | os três critérios, o bracket, o caso vazio, a assinatura-união, `by=` dentro do grupo | Camada **tabela → tabela**: não vê `Study`, não vê base, não roda motor. **Testável sem dado** — a costura mais barata do pacote, e por isso a que deve carregar todo teste de seleção |
| **4** | as quatro `*_table`, `export_rules`/`export_study`, `suggest_*`/`apply_rating` | leitura, serialização e sugestão | Todas **função livre, tabela ou valor entra, tabela ou valor sai**. Round-trip se testa aqui; nenhum acessor de objeto precisa ser exercitado |

**A referência fica FORA de todas elas.** O valor esperado sai de **pandas ou da conta à mão**, nunca de outro caminho do próprio motor — **comparar motor com motor pina coincidência, não contrato** (§6, DoD 3).

**Consequências para o que NÃO é costura:**

- **O `ctx`, o Protocol de um membro, o rechaveamento na AST, o contador de totais corridos e o cache de sorteio são internos.** Nenhum deles ganha teste próprio; todos são exercitados pelas costuras 1 e 2. Se um deles precisar de teste direto, isso é sinal de que a costura acima dele não observa o que deveria.
- **`validation/` é a quinta superfície de teste, e não é costura nova** — é a costura 1 e 2 rodadas com base fixa versionada, fora do pytest de todo commit, para a prova de paridade.

---

## 6. Testing Decisions

### O que faz um bom teste aqui

**Teste comportamento externo, na costura mais alta.** A pergunta por teste é dupla:

> **Qual contrato desta spec eu guardo, e ele ainda existe?**
> **Eu ficaria vermelho se ele fosse violado?**

A segunda pergunta é a que a suíte de hoje reprova. Quando se foi verificar se *"todo estágio declarado liga em todo ponto da grade"*, descobriu-se que a garantia era **folclore**: **nenhum teste da suíte a guardava**, e por isso um sintoma de campo **não pôde ser resolvido lendo a suíte, só remedindo do zero**.

### As três definitions of done

Nenhuma delas é ticket — as três são **critério de aceite que esta spec carrega** e que o mapa de implementação transforma em portão.

#### DoD 1 — a malha inteira é relida, item a item

A v0.6 mexe em muita coisa ao mesmo tempo, então **nenhuma parte da suíte pode ser presumida ainda válida**. Um teste que continua verde depois da decomposição **pode estar verde por acidente**: pinando um nome que morreu, um caminho que virou default, ou um invariante que a nova fronteira já garante por construção.

**Toda a malha é relida de ponta a ponta — não corrigida onde quebrar.** 190 funções, 4.392 linhas, 24 arquivos.

Insumo já levantado, com números: cobertura assimétrica **~7:1** a favor do analítico, **zero** testes parametrizados por método, **toda a família de bugs de contrato keep-in testada só no analítico**, ausência de `conftest.py` e de política de semente, e um flake latente em `test_sweep.py:147`.

Três das quatro lacunas de 2026-08-14 **morreram** com o analítico (não há segundo caminho a parametrizar; o caminho quase não testado passa a ser o único; a razão entre métodos deixa de existir). **Sobra a terceira — higiene de semente — e ela virou pré-requisito**, não higiene.

**Ganho colateral:** os quatro `print_*` só são testáveis hoje **capturando stdout**. Depois da mudança, **41 operações de cálculo passam a ter valor alcançável por teste** — a revisão tem que cobrir **tabela por tabela**, não só o que quebrou.

#### DoD 2 — toda reconstrução de estágio é total

O contrato de `Stage` tem que tornar a reconstrução parcial **impossível por construção**, via um **mecanismo genérico de troca-um-campo dirigido pela assinatura do construtor** — e **não** confiar em quem chama passar todos os campos. **Foi exatamente isso que falhou, três vezes, na mesma família de bugs.**

Se a resposta for *"o chamador passa todos"*, o buraco continua aberto.

**Evidência já versionada:** `tests/test_sweep_rebuild_preserves_stage_fields.py` — 5 testes `xfail(strict=True)` dirigidos por `inspect.signature`, que **passam sozinhos quando o mecanismo aterrissar**.

Nota de leitura registrada: o rebuild irmão `_without_cutoff_entries` (`sweep.py:62`) vai **sem marcador** — ele está correto **por acaso**, porque `CutoffStage` tem exatamente 3 campos hoje.

#### DoD 3 — invariante estrutural com referência externa e controle negativo

> **Toda garantia que a arquitetura afirmar "por construção" carrega um teste com três propriedades:**
>
> 1. **Referência calculada fora do motor** — pandas ou a conta à mão, **nunca outro caminho do próprio motor**. Comparar motor com motor **pina coincidência, não contrato**.
> 2. **Medido na fronteira, onde a garantia satura** — o ponto em que o invariante fica plano, **não o meio da curva**, onde qualquer número parece plausível.
> 3. **Controle negativo** — a mesma medição **com a garantia removida**, mostrando o teste ficar vermelho. Sem ele, "50%" é só um número que o motor produziu; com ele, os 100% da política sem escudos **provam que o teste tem dente**.

**Dois modelos executáveis já versionados:**

- `tests/test_sweep_hard_filter_ceiling.py` — 13 testes; teto medido em pandas, cutoff nulo na fronteira, controle negativo pelas duas superfícies públicas.
- `tests/test_swap_in_anchor_follows_declaration_order.py` — 5 verdes + 3 `xfail(strict=True)`; a referência em pandas bate com o motor **linha a linha** (`atol=1e-12`) e por isso **nomeia em qual score ele ancorou**, em vez de só mostrar que o número mexeu.

Esta DoD **emenda a primeira**: reler cada teste contra os contratos novos **e** exigir as três propriedades de todo teste que guarde garantia estrutural.

### Higiene de semente — pré-requisito, não higiene

Todo teste que compare o verbo de grade com simulação à mão declara **três** coisas, senão vira flake:

1. **Política de semente.** Sem semente fixa o teste não é reproduzível; **com semente fixa mas sem pareamento, ele testa uma realização, não o caminho**.
2. **Tolerância em unidade de ruído, nunca em p.p. absoluto.** O sd medido a 3 MM é **0,022–0,039 p.p.** e escala com `1/√n` — uma tolerância absoluta escolhida a 3 MM **reprova sozinha a 200k**. O critério é *"dentro de k desvios"*, com **k e n declarados**.
3. **Rodadas pareadas onde o critério for viés.** Comparar uma rodada contra uma rodada **não separa viés de ruído**.

**Por que isso é obrigatório e não conselho:** ao medir o caminho rápido corrigido, um dos cinco pontos leu **4,1 sd** — e **não era viés**: 8 rodadas pareadas contra 8 simulações à mão mediram 0,2 / 1,2 / 0,9 erros padrão. **Descobrir isso exigiu 16 execuções a 3 MM. Uma única rodada teria reprovado um caminho correto.**

E isso amarra com o sorteio chaveado: **é justamente ele que torna o pareamento barato**, porque dois pontos de grade voltam a ser comparáveis por construção. Sem ele, **cada teste de paridade paga N execuções para estimar a própria banda**.

### A prova de paridade contra a v0.5 — forma (B)

A forma ingênua ("bate ponto a ponto, com whitelist do que não bate") **não sobrevive**: **oito frentes movem número de propósito** na v0.6.0. Com isso, "bate ponto a ponto" tem resposta *"não, e de propósito, em quase todo lugar"*, e a whitelist cresceria até cobrir quase toda célula — **momento em que "esperado divergir" vira, na prática, "não comparado", e uma regressão real se esconde dentro de uma célula whitelistada.**

**Três camadas, nenhuma célula sem asserção:**

1. **Invariantes duros — igualdade exata.** Em política **fixa**, sem varredura: **aprovação pré-take-up** e **volume de keep-in**. Medido: desvio **exatamente zero** nos dois a 3 MM; não dependem de sorteio nem de calibração. **Divergência aqui é regressão, ponto.**
2. **Convergentes — tolerância em unidade de ruído.** Contratados e inadimplência, sob as três regras de higiene acima. **Tolerância absoluta é proibida.**
3. **Deltas intencionais com magnitude asserida.** Cada entrada de whitelist **deixa de ser "não comparar"** e vira teste que exige **direção e faixa**. Os `xfail(strict=True)` já versionados **são esse mecanismo pronto** — viram verdes quando a correção entra e **falham se ficarem para trás**.

> **Regra que impede (B) de degenerar em (A): uma entrada de categoria (a) SEM FAIXA MEDIDA não é entrada de whitelist — é DÍVIDA.** Enquanto a faixa não existir, a célula **não pode** ser marcada "esperado divergir" e sair do teste: ela fica **vermelha e visível**.

#### Parametrização obrigatória por forma de política

| forma | v0.5 × v0.6 |
|---|---|
| um `.cutoff` só | **bate exato** |
| `.filter` (`Expression`, string ou callable) | diverge, até **0,70 p.p.** |
| 2+ scores cortados | diverge, até **0,73 p.p.** |
| tupla de 4 scores | diverge, até **0,93 p.p.** |
| `calibration_score_col` declarado | **bate exato** |

> **Isto condena o harness de hoje.** `validation/measure_main.py` roda **uma** forma — um score só, cortes localizados pela grade — e é **precisamente a linha que bate exato**. Rodado como está, ele **atesta paridade que não existe** nas outras quatro formas. **O `validation/` é reescrito.**

#### A whitelist, entrada por entrada

| frente | categoria | faixa |
|---|---|---|
| reconstrução parcial do estágio ao varrer | (a) intencional | **medida**: 2,27 p.p. no eixo varrido, 0,90 p.p. num ponto; aprovação exata |
| âncora posicional da calibração | (a) | **medida, e NÃO uniforme por forma** (tabela acima) |
| caminho rápido recalibrado | (a) | **medida**: sai de +0,58/+1,00 p.p. para **dentro do ruído** |
| população do baseline (`calibrate_on`) | (a) — **a primeira de MODELAGEM** | **a medir — dívida com portão** |
| cortes regionais do notebook (régua global) | (a) — modelagem | os cinco cortes **752/785/732/694/680** mudam |
| sorteio por linha chaveado | (a) — exceção nomeada | **a medir**: nenhum cálculo e nenhuma máscara mudam; o que muda é o valor de um ponto **deixar de depender da grade em que foi rodado** |
| morte do proxy `notna()` no denominador | (a) | **a medir**: move o **denominador**, não o numerador |
| eixo de contrato saindo da política | — | **NADA entra**: re-expressão **exata**, `|Δ| = 0`, zero linhas mudando `reason` |
| renomeios de coluna | **(b) deve bater** | não move número — move o **casamento de colunas**. **Precisa de mapa de-para explícito**, senão vira **falso positivo em massa** |
| HFs no verbo de grade | **(b) deve bater** | nada a whitelistar — bug não confirmado |

**Escopo da divergência da população do baseline**, para o harness não classificar errado: **inadimplência diverge**; **aprovação bate exato** (pré-take-up, a calibração não a toca); **take-up bate exato** enquanto a conversão não for declarada. **E ela é a primeira entrada que diverge em toda simulação, não só na varredura** — um teste de paridade que só varra grade **não a vê**.

**Por que a faixa dela é dívida e não card:** as outras entradas mediram **bugs que existem no código de hoje**; esta mede uma mudança que **ainda não existe**, e produzir o número exige **construir o caminho novo**. Fazê-lo em protótipo agora seria construir duas vezes.

**A prova roda serial.** Sob `parallel=True` o resultado não reproduz sob semente (**0,41 p.p.**) — registrado como **característica**, não bug, porque cada processo amostra independente.

### Os portões de release

A v0.6.0 **não sai** enquanto qualquer um destes estiver aberto:

1. **As três DoDs**, aplicadas.
2. **Exatidão da grade** — *um ponto colhido da otimização bate com a mesma simulação feita à mão, montando as regras* — **e o teto de custo ≤ 1,25×** por ponto a 3 MM em grades ≥ 100 pontos. **Dois testes, não um:** sob `calibrate_on="global"` a exatidão sai de graça; sob `"keep_in"` ela exige recalibração por ponto.
3. **Paridade na forma (B)**, parametrizada por forma de política, com o `validation/` reescrito, **e nenhuma entrada de categoria (a) sem faixa medida**.
4. **Checagem de artefato** — o portão verifica que as seções de **língua única** e da **escada de remédios** **existem no `CONTEXT.md`**. Isto não é zelo: uma decisão foi dada como gravada citando um commit que **não existe em ref nenhuma**, e as seções tinham **0 ocorrências em todas as branches**. **Sem essa checagem, a v0.6 fecha com regras que nenhuma sessão futura consegue ler fora do histórico de issues.**
5. **A nota de documentação sobre o sorteio**, com os dois números (0,018 p.p. e 0,41 p.p.) — hoje o `README` aponta para o lado errado.

**Por que o teto de custo existe:** sem ele a implementação pode aterrissar a forma ingênua. Medido, **a distância entre a melhor e a pior forma de recalibrar (≈1,2× contra ≈5,8×) é MAIOR que a distância entre a melhor forma e não recalibrar**. O custo dominante da forma ingênua é um **sort por ponto**; ordenar a base uma vez torna os quantis posicionais e o sort some.

---

## 7. Roadmap — o conteúdo da v0.6.0

### Os oito blocos, mais a mesa

| bloco | conteúdo | tamanho | natureza |
|---|---|---|---|
| **B1** Tipos e fronteira | `DataSchema` / `CreditPolicy` = só `stages` / `Premise` / `Study`; bind com erro duro | **XL** | espinha: cria 4 tipos, todo o resto pendura nela |
| **B2** Estágios | `.cutoff` morre, `.filter` único sobre a AST, Protocol de um membro, label, `ctx` estreito, **troca-um-campo dirigida pela assinatura** | **M** | + a mesa |
| **B3** Motor | analítico morre, sorteio por linha chaveado, semente do estudo, `print_*` → funções livres que devolvem tabela | **L** | **remoção mecânica**, não reescrita |
| **B4** Contrato de saída | três vetores, `notna()` morre, ponto de montagem único, língua única, dtype determinado | **M** | toca toda tabela, regra única |
| **B5** Grade e seleção | `tradeoff` único, `ranges=`, `choose()`, `OptimizationResult`/`TradeoffAnalyzer` morrem, renomeios, **caminho rápido exato**, **passada única do `by=`** | **M** | |
| **B6** Calibração | a âncora posicional morre; **população do baseline** | **S–M** | |
| **B7** Identidade e serialização | identidade do `Study`, coluna `study`, duas unidades, `set_stage` | **M** | mecânico depois dos tipos |
| **B8** Rating e deployment | régua declarada × rótulo relativo, sugerir · aplicar, `export_*` | **L** | consumidor; só com a superfície congelada |
| **+ mesa** | `.filter(expr, draw=True)` | — | **o único item que é funcionalidade nova, não decomposição** |
| **DoD** | releitura da malha | **L** | corre em paralelo desde B1 |

**A mesa entra na v0.6.0**, contra a classificação inicial como aditiva, por três razões: a superfície é a mesma e está sendo reescrita em B2, então adiar **reabre `.filter` na 0.6.1**; o maquinário (sorteio chaveado) já está em B3; e sem ela a spec **declararia semântica de aprovação para algo inexprimível** — contrato sem verbo.

### A ordem, por dependência

> **B1 → B2 → B3 → B4 → B6 → B5 → B7 → B8**, com a releitura da malha correndo em paralelo desde B1.

- **B5 depois de B6** porque a exatidão da grade **depende de qual população calibra**.
- **B7 e B8 por último** porque são **consumidores** de tipos que precisam estar congelados.

### O corpo, medido

**12.516 linhas de Python — núcleo 6.699 (53%), Studio+GUI 5.787 (47%).** Testes: 24 arquivos, 4.392 linhas, 190 funções.

Sítios que morrem ou mudam, por bloco: `score_cols` **137 src / 147 testes**; `current_hired_col` 39/24; `method=` 20 src / **130 testes** e 19 ramos; `print_` 15/31; **40 literais de coluna contra 13 usos** do módulo de tipos; `CutoffStage` 38; `optimize_cutoffs` 9/33; `TradeoffAnalyzer` 14/27; `OptimizationResult` 14/4; `calibration_` 54/64; **11 tipos com `to_dict`/`from_dict` à mão → 1 mecanismo**.

**O dimensionamento é relativo por escolha, não por omissão.** Não há conversão para horas ou dias, e não houve tentativa: **qualquer número absoluto aqui seria chute apresentado como medição** — exatamente o modo de falha que este mapa passou oito cards combatendo. Se um número absoluto for necessário, ele vem de calibração contra blocos já executados, não de julgamento.

### O Studio sai quebrado

*"Congelar — vira consumidor da nova API"* **não sobrevive à medição**: o Studio é **47% do pacote** e consome exatamente o que morre (`score_cols` 60 sítios, `current_hired_col` 22, `method=` 11, `OptimizationResult` 6, `optimize_cutoffs` e `TradeoffAnalyzer` 5 cada). **Congelado, ele não roda.**

**Ruling: sai quebrado na v0.6.0, migração no backlog.** Único trabalho de Studio dentro da v0.6.0: **o `__init__` falhar limpo**, com erro que diz *"não migrado para a API v0.6"*.

**Aceitável apenas porque é projeto pessoal, sem usuários nem pipelines a quebrar.** Com usuários, a saída teria sido outra — e isso fica escrito.

**O Studio migrado será o teste de ergonomia mais honesto que esta superfície vai ter**, porque ele é um consumidor externo de verdade.

### A cauda aditiva — dois itens

| item | por quê é aditivo |
|---|---|
| tradutor sugestão → política (HF aceito vira `.filter`) | funcionalidade nova sobre superfície congelada |
| `visualization.py` com import preguiçoso | nenhuma API muda; pode ir junto da 0.6.0, custo zero |

### A migração

**CHANGELOG + a masterclass reescrita na superfície nova**, servindo de exemplo canônico ponta a ponta. Ela precisa ser reescrita de qualquer forma — **e reescrevê-la é o teste de ergonomia da família nova**.

Nota de execução: a §6 do notebook usa `target_default_rate=` e `min_approval_rate=`, ambos mortos. A seção será reescrita e **encolhe**: uma chamada de grade com `by="region"` mais o laço de bisseção em pandas, no lugar do laço que varre região por região.

---

## 8. Out of Scope

**Fora da v0.6, com ruling registrado:**

| assunto | ruling |
|---|---|
| **A política auto** — plugar a sugestão como aceita, varrer HFs/scores para achar a melhor política | É **feature apoiada na arquitetura**, não peça dela. Migrou íntegra para o backlog, com os 8 pontos, a busca de estrutura/CART e a estratégia de busca |
| **Busca de estrutura ("a árvore por trás")** | Sai junto com a política auto. Os fatos levantados sobre CART ficam; o veredito é pós-v0.6 |
| **Alvo consolidado de carteira com rebalanceamento do mix** | A v0.6.0 entrega o critério **dentro de cada grupo**. Adiar é seguro porque **não é otimizador**: é o caso por-grupo mais um escalar girando por fora — casca fina sobre a grade, escrevível em pandas assim que os denominadores viajam nela. **Dois motivos para não entrar agora:** existem **dois critérios** (alvo comum τ, que iguala o *nível* de risco e serve auditoria; preço comum λ, que iguala o risco *na margem* e minimiza calote total) e **escolher entre eles é pergunta de negócio**; e há uma **pergunta de produto sem resposta — existe limite de quanto um grupo pode se mover?** Na conta pura um grupo pode despencar de 64% para 30% de aprovação porque a matemática mandou. **Não é coisa para descobrir no meio da maior quebra do pacote** |
| **A migração do Studio para a API v0.6** | Backlog. A v0.6.0 sai com o Studio quebrado |
| **Reweight e inferência de negados modelada** | Nasce num **futuro pacote de modelagem**; aqui o pycreditools é **cliente** e a recebe pronta, por `outcome_from=<coluna>`. **Não é ruling de mérito — é fronteira de produto** |
| **Medir a magnitude do suporte comum num livro real** | Com a decisão de população tomada, é **validação de execução, não decisão de arquitetura** |
| **`screening.py`, `performance.py`, `visualization.py`, `deployment.py`, `analysis.py`, `grouping.py` como superfícies a redesenhar** | **Ruling do dono, 2026-09-07: fora.** A v0.6 é sobre o **core da arquitetura**. Isso **não significa que não serão mexidos** — serão, e bastante (B3, B8 e o contrato de saída atravessam os seis) —, mas **por consequência de algo que mudou e os afeta**, nunca como redesenho próprio. Nenhuma pergunta de forma sobre eles entra nesta spec |
| **A invariância de coeteris paribus, nomeada na superfície** | Levantada e **não adotada**. Mover o take-up para a premissa declara que o mecanismo **existe**, mas **nenhum campo, argumento ou número nomeia a invariância sob movimento do corte** — o take-up declarado não se mexe quando o corte anda, e isso é coeteris paribus **sem palavra**. A pesquisa achou o precedente completo (`marginaleffects::datagrid(grid_type=)`: regime enumerado, chaveável, viajando pelo verbo que constrói a grade) e o registrou **sem veredito**; das quatro formas medidas, **nenhuma nomeia por endereço**. **Se virar exigência, é card novo** |
| **A implementação e a migração do código** | Esta spec produz o contrato. **A execução é um mapa novo, com seu próprio portão** |

---

## 9. Further Notes

### 9.1 Decisões que este documento toma, e que não estavam em card fechado

Quatro. As três primeiras são rulings do dono de 2026-09-07; a quarta é escrita de spec sob regras já fixadas. **Cada uma vira emenda explícita ao card de origem.**

| # | decisão | emenda a |
|---|---|---|
| 1 | **Comparar-N não precisa de verbo.** `simulate` aceita coleção; `delta_table(results, baseline=)` lê. **`compare` não nasce** | a decisão de que comparar-N é verbo de primeira classe — **o conteúdo dela sobrevive inteiro** (tabela longa, uma linha por estudo, sem tipo contêiner); muda **qual verbo a produz** |
| 2 | **`stress` aceita escalar, escada por bin OU nó da AST** | a decisão *"morre o tipo, não a palavra"*, que **não dizia que forma o valor toma**. A família `*Stress` inteira — três tipos e um callable — vira **um campo com três modos, sem perda de capacidade** |
| 3 | **`take_up` aceita `"binned"`, escalar OU nó da AST** | o registro explícito de que *"ninguém escreveu como o campo aceita nó da AST"*. Preserva a capacidade que `RateStage.variable` tem hoje |
| 4 | **A escada de `stress` indexa os mesmos `bins`**, e comprimento diferente de `bins` é erro duro | escrita de spec — decorre de *"uma config serve todo eixo"* e da escada não poder inventar faixa própria |
| 5 | **`outcome_from` aceita nó da AST — probabilidade por linha** —, distinguido da coluna 0/1 **pelo tipo**: string é observado e não sorteia, nó é hipótese e sorteia | **re-aloja o eixo de desfecho do #118**, que o card deu ao verbo `.rate` e que evaporou quando o `.rate` colapsou (#129), saiu da política (#155) e virou `take_up` (#152). **Nenhum card decidiu matar esse caminho** — ele foi perdido por atrito entre três decisões corretas. Pela regra de precedência, o #118 vence o #117 nesse ponto |
| 6 | **`MonotonicStress` não é stress e não ganha modo próprio** | ele **ignora `pd_col`** (`stress.py:96-97`) e **substitui** a PD por uma reta sobre o score. É modelo de PD, não inflação; o endereço dele é `outcome_from` com um nó |

**Consequência da 1 para a lista de nomes públicos:** `compare_policies` já estava na lista de mortos; o que muda é que **nada nasce no lugar** — `simulate` ganha um overload, não um irmão.

**Consequência da 2, 3, 5 e 6 para a whitelist:** nenhuma. Os três modos novos **reproduzem caminho que já existe** — a escada reproduz a angulação por faixa, o nó de `stress` reproduz `AggravationStress(factor_col=)`, o nó de `take_up` reproduz `RateStage.variable`, e o nó de `outcome_from` reproduz o `estimated_default_col` lido como probabilidade (`simulation.py:548-550`). Onde o usuário usava **callable**, o número muda de propósito e **já estava contabilizado** na morte do callable.

**Regularidade que as decisões 2, 3 e 5 compram junto:** os três campos que respondem *"de onde vem o número"* — `take_up`, `stress`, `outcome_from` — passam a aceitar **a mesma coisa**: um sentinela que nomeia o mecanismo, um valor concreto, ou um nó da AST. Isso não era desenho intencional; caiu quando o inventário do código forçou o terceiro modo em dois deles.

### 9.2 O que continua **[aberto]**

| # | item | por quê está aberto, e não escondido |
|---|---|---|
| 1 | **Se a distinção string × nó no `outcome_from` é legível o bastante** | Ela é **semântica e correta** — observado não sorteia, hipótese sorteia — mas é distinção **por tipo**, não por palavra. Nenhum card a validou porque nenhum card sabia que os dois modos coexistiriam. Se ela se mostrar sutil demais na masterclass reescrita, a alternativa é nomear o mecanismo (`outcome_from=("model_pd", col(...))`), ao custo de perder a simetria com `take_up`. **Não bloqueia a v0.6.0** |

**A dúvida do dono sobre *"quantos verbos o stress precisa"* está respondida: zero tipos, um campo com três modos.**

**Nada mais está aberto.** As duas entradas de névoa que o mapa carregava foram fechadas: as seis superfícies não olhadas saíram por ruling (§8), e a invariância de coeteris paribus está registrada como **levantada e não adotada** (§8), não como pendência.

### 9.3 Dívida de artefato — o que o mapa decidiu e o repositório não tem

Levantado ao escrever esta spec. **Não é decisão pendente; é execução que ficou para trás**, e o portão 4 (§6) existe por causa dela.

| item | estado |
|---|---|
| ADRs 0012 (contrato de saída), 0013 (verbo de grade), 0014 (camada de seleção) | ✅ escritos e mergeados |
| `CONTEXT.md` § *Language of the code* | ✅ presente |
| `CONTEXT.md` § **escada de remédios** | ❌ **ausente** — e a decisão declarou explicitamente que *"só está entregue quando a seção existir no arquivo"* |
| **ADR do "critério de escolha não é do pacote"** | ❌ **nunca escrito**, embora declarado como entregável |
| ADRs das demais decisões (tipos, schema, premissas, valores de verdade, mesa, rating, núcleo funcional, identidade, superfície de estágio, população do baseline, `by=`, eixo de contrato, família de verbos) | ❌ **nenhum escrito** |
| **spec viva por tipo** | ❌ **este documento é a primeira** |
| Layout `docs/engine/` + `docs/studio/` | ❌ **não executado** — e o número **0012**, que a decisão de layout reservava para si, foi tomado pelo contrato de saída. **O ADR de layout nunca foi escrito** |
| Denylist mecânica do vocabulário morto, no `pre-commit` | ❌ o repo **não tem `pre-commit`** |
| `docs/wayfinder/map-111-body.md` | ⚠️ **desatualizado** — 38 KB contra 57,7 KB do corpo real |
| Pesquisas em branch efêmera, fora de `release/v0.6` | ⚠️ `verb-shape.md`, `contract-vector-address.md`, `fastpath-recalibration-cost.md`, `prototype-155-contract-axis.py` |

### 9.4 Fatos que uma sessão futura não deve reapurar

- **`src/pycreditools` é byte-idêntico entre `release/v0.5` e `release/v0.6`** — mesma árvore git. A v0.6 até aqui carrega **só ADR, pesquisa e testes**. Então *"comparar com a v0.5"* é **comparar a mesma engine**: nenhum dos bugs verificados é regressão; **todos são herdados**.
- **Método (analítico × estocástico) e caminho da grade (rápido × re-simulação) são ORTOGONAIS.** Matar o analítico custou +7,9% serial e **não criou nem mudou** o defeito do caminho rápido, que é anterior e independente.
- **O caminho rápido é exato quando o eixo varrido é o eixo que gerou o livro** — varrer o score pelo qual o incumbente aprovou não produz swap-out até o corte passar do quantil de aprovação dele, a população de keep-ins não muda, e o erro mede **+0,0000 p.p.** O defeito exige que o eixo varrido seja **ortogonal** ao que gerou o livro — **que é o caso interessante e o caso da masterclass**.
- **Os números de custo de grade de 50 mil linhas não transportam para 3 MM em valor absoluto; só a razão (~53×) transporta.** O modelo a 3 MM é **≈ 6,5 s fixos + ~80 ms/ponto**.
- **Recalibrar por ponto não reduz o erro — elimina**, até a precisão de ponto flutuante (`+0,000000 p.p.` em cinco cortes cobrindo 24% a 76% de aprovação).
- **`MonotonicStress` nunca foi um stress.** `stress.py:96-97` computa `baseline − (score/1000) × factor` **sem tocar `pd_col`** — ele **substitui** a PD, não a multiplica. Quem o classificar como inflação ao ler o nome vai errar a migração dele.
- **A curva de ρ do protótipo de lente é inválida** e não deve ser citada: o eixo "correlação entre scores" ficou confundido com "quanto sinal o segundo score carrega".
- **`parallel=True` não reproduz sob semente** (0,41 p.p.) — **característica, não bug**. E **quebra com filtro callable** (`PicklingError`, porque o pickle vem **antes** da resolução) — o que **morre junto com a classe de casos**, quando callable virar inexprimível. **O repasse é verificação, não conserto:** confirmar que a inexprimibilidade fecha o caso, em vez de deixar um caminho lateral que ainda aceite callable e ainda quebre em paralelo.

### 9.5 Duas decisões tomadas **contra** a recomendação de quem grilou

Registradas porque a distinção entre escolha do dono e delegação já custou uma reversão de meio dia, e porque **o erro é insumo**:

1. **O verbo de grade chama-se `tradeoff`, não `sweep`.** Recomendação: `sweep`, que é verbo de verdade e não cria vocabulário. **Preço aceito:** substantivo em posição de verbo.
2. **A grade publica três métricas, não duas.** Recomendação: duas, para manter curta a lista de eixos. **O ganho é real** e a recomendação estava errada: sem o take-up o volume contratado **não é derivável da tabela**.

E **uma recomendação que a medição matou**: propôs-se colapsar a camada de seleção num verbo só (o Pareto), porque com o vigente como coluna os dois `hold_*` **pareciam** exprimíveis em pandas puro, por analogia com o apetite.

> **O erro foi de geometria.** O apetite é um **semiplano**, monótono, cujo resultado escala com a pergunta; a banda iso é um **intervalo em torno de um ponto**, disputando espaço com o passo da grade. **Formas diferentes, respostas diferentes** — e a segunda devolve vazio em 5 de 5 regiões.

---

*Este documento é vivo. Emenda a ele é emenda a decisão — registre o porquê num ADR antes de mudar uma linha aqui.*
