# Núcleo funcional vs casca imperativa — levantamento de referências

> **Insumo de decisão, não decisão.** Este documento levanta fatos, formas e preços.
> Nenhum veredito "adotar / adaptar / descartar" é tomado aqui — esses são de #127
> (núcleo funcional) e, no que toca ao método, de #140. Se você achar uma recomendação
> neste texto, é um defeito: reporte no #143.

Resolve a fatia **núcleo funcional** da Lente B (#143), que graduou de #135, que graduou de
#134, que graduou de #113. Cobre duas perguntas da §16 do `architecture-critique.md`:
**15** (onde mora a semente quando a aleatoriedade é aninhada) e **16** (fronteira entre
calcular e apresentar, para usuário de notebook).

Referência: **functional core / imperative shell** (Gary Bernhardt, 2012) — não é biblioteca,
é critério de fronteira: o núcleo é função pura de valores para valores, e todo efeito (IO,
relógio, aleatoriedade, processo) mora numa casca fina em volta. Entra aqui porque a §11 do
levantamento tem exatamente os dois efeitos que o critério nomeia — `print` e aleatoriedade —
dentro do núcleo.

## Como ler

Cada célula tem **N formas**: **fato**, **porta para Python/pandas?**, **preço**.

**Ressalva de método herdada de #134:** onde a medição mostra que as formas **não empatam**,
este documento diz isso e mostra o número.

**Restrição de desenho herdada de #135:** o pacote já teve uma forma declarada que perdeu
(`_types.py`, 13 usos contra 40 literais). Toda forma custeada tem que dizer o que a impede
de ter o mesmo destino. Nesta fatia a restrição morde de um jeito específico e favorável,
registrado na §1.3.

---

## 1. O estado medido

Medições sobre `release/v0.6`, 2026-08-15, em máquina Windows (relevante para a §2.3).

### 1.1 A semente não existe — não é que esteja no lugar errado

Ocorrências da palavra `seed` nos seis módulos do núcleo:

| módulo | ocorrências de `seed` |
|---|---|
| `simulation.py` | **0** |
| `sweep.py` | **0** |
| `stages.py` | **0** |
| `optimization.py` | **0** |
| `policy.py` | **0** |
| `performance.py` | **0** |

`np.random.default_rng` aparece só em `sample_data.py` (`:212`, `:263`), que não é caminho de
simulação. Os três sorteios do núcleo usam `np.random.random` — estado global de módulo,
sem semente: `simulation.py:604` (desfecho de quem tem marcação desconhecida),
`simulation.py:664` (desfecho de swap-in sob stress), `stages.py:458` (contratação do
`RateStage`).

Isso reformula Q15. A pergunta do levantamento é "onde mora a semente quando a aleatoriedade
é aninhada", pressupondo uma semente mal colocada. **Não há semente em lugar nenhum.** A
decisão do #116 (`method`+`seed` = premissa do estudo, semente obrigatória) não tem nada a
migrar: é terreno vazio. O card #127 desenha do zero, e o custo de reescrita medido na §2.4
é o único preço real.

Consequência para o método deste documento: as formas abaixo não competem por "qual é menos
custosa de migrar" — competem só pelo que garantem depois de instaladas.

### 1.2 O aninhamento, medido

Três chamadas idênticas de `simulate(method="stochastic")` sobre a mesma base
(`generate_sample_data(20000, seed=7)`, um `.cutoff` e um `.rate(0.55, observed_col="hired")`):

| execução | soma de `simulated_default` | soma de `new_approval` |
|---|---|---|
| 0 | 816,0 | 3940,0 |
| 1 | 847,0 | 3968,0 |
| 2 | 800,0 | 4019,0 |

Contra o analítico, estável por construção: 812,651 e 3966,953.

**As duas colunas variam, e é isso que dá o aninhamento seu nome.** São dois sorteios
distintos por execução — contratação (`stages.py:458`) e desfecho (`simulation.py:604`/`:664`)
— e o segundo é **condicionado ao primeiro**: só quem contratou recebe desfecho. Trocar o
número de contratados muda o tamanho do vetor sorteado a jusante.

Isso é o fato que define o custo de todas as formas da §2: um único fluxo de números
aleatórios consumido em ordem faz o segundo sorteio depender de quantos números o primeiro
puxou. Não é preferência de estilo; é o que decide se dois estudos que diferem numa dimensão
continuam comparáveis.

### 1.3 A grade não reproduz, e o paralelo é uma segunda fonte

Mesma política, grade de 4 cortes em `legacy_score`, duas execuções de `run_sweep` por modo:

| modo | duas execuções idênticas? | delta máximo na taxa de inadimplência |
|---|---|---|
| serial | **não** | 0,00640 |
| paralelo | **não** | 0,00794 |
| analítico | sim, por construção | — |

O caminho paralelo passa por `ProcessPoolExecutor` (`_parallel.py:18`), e `method` chega até
lá (`sweep.py:196`, `:207`, `:315`) — logo os sorteios acontecem **dentro dos workers**, sobre
o estado global de `np.random` de cada processo.

**Fato de plataforma, medido de um lado só e declarado como tal:** esta medição é Windows,
onde o start method é *spawn* e cada worker inicializa estado próprio a partir de entropia do
SO. Em POSIX com *fork*, o filho herda o estado do pai — o mecanismo é diferente, e a
literatura de numpy trata "fork + estado global de RNG" como caso clássico de fluxos
correlacionados entre workers. **Não medi isso**, e o card não deve tratar a hipótese como
confirmada; o que está medido é que o resultado paralelo depende do start method, ou seja,
**do sistema operacional**, e nada no pacote o declara.

Aqui a restrição de desenho do #135 morde ao contrário do usual e vale registrar: uma
semente não corre o risco do `_types.py` — ela não é "opcional de usar", porque a
reprodutibilidade ou existe ou não existe, e a ausência é observável em um diff de duas
execuções. O que o `_types.py` não tinha (um jeito de a violação doer) a semente tem de
graça, desde que exista **um** caminho de aleatoriedade. A forma que fracassa nessa
restrição é justamente a que deixa dois caminhos coexistirem — §2.1.

### 1.4 `print_*`: os quatro calculam, e nenhum devolve

| função | linhas | `print(` | operações de cálculo | anotação de retorno |
|---|---|---|---|---|
| `print_delta_table` (`:288`) | 170 | 15 | 14 | `-> None` |
| `print_quadrant_summary` (`:458`) | 70 | 7 | 7 | `-> None` |
| `print_swap_in_by_rating` (`:528`) | 44 | 6 | 5 | `-> None` |
| `print_rating_quadrant_table` (`:572`) | 79 | 3 | 15 | `-> None` |

"Operações de cálculo" = ocorrências de `.sum(`, `.mean(`, `.groupby(`, `.notna(`, `.agg(`,
`.div(`, `.count(`, `.value_counts(`.

**363 linhas, 41 operações de cálculo, zero valores devolvidos.** Os três `return` que existem
são saída antecipada, não retorno de valor — todos os quatro são anotados `-> None`.

E são superfície pública, não interno: 8 menções no `__init__.py` do pacote e **42 usos fora
do `performance.py`** (notebooks e testes).

Este é o fato central de Q16, e ele é mais forte do que "formatação misturada com cálculo".
Cálculo misturado com formatação ainda deixa o número acessível se a função devolver algo.
Aqui **o número não existe fora do stdout**: para usar em outra célula do notebook, o
usuário refaz a conta. Uma tabela de deltas de 170 linhas é reimplementada pelo consumidor
ou não é usada.

---

## 2. Q15 — onde mora a semente com aleatoriedade aninhada

Quatro formas. Todas portam para Python; o que as separa é o que garantem quando o estudo
varia numa dimensão — que é o caso de uso do pacote inteiro (#118 fixou varredura como
`ranges=` no verbo; #122 fixou grade como cache de ~200 simulações).

### Forma A — semente global no início

**Fato.** `np.random.seed(s)` (ou um `default_rng` de módulo) uma vez, e todo sorteio puxa do
mesmo fluxo em ordem.

**Porta?** Sim, é a mudança de uma linha sobre o código atual.

**Preço.** É a forma que a §1.2 mata com número. Com um fluxo em ordem, o sorteio de desfecho
consome uma quantidade de números que depende de **quantos contrataram**. Dois pontos de
grade que diferem no corte mudam o número de contratados, logo desalinham todo o fluxo a
jusante — e a diferença entre eles passa a conter ruído de realinhamento, não só o efeito do
corte. Reprodutível de ponta a ponta, sim; **comparável entre pontos, não**.

Preço adicional: não sobrevive ao `ProcessPoolExecutor` da §1.3 sem um mecanismo de
propagação, porque estado global não atravessa processo por si.

**Resposta à restrição do #135:** existe um caminho e a violação dói. Falha por outro motivo.

### Forma B — um `Generator` explícito, passado como argumento

**Fato.** `np.random.Generator` criado na fronteira e passado adiante; nenhum sorteio lê
estado global. É o que `sample_data.py` já faz (`:212`, `:263`) e o que a §15 do levantamento
registra como a prática correta que já existe num lugar do pacote.

**Porta?** Sim, sem dependência nova, e com precedente interno.

**Preço.** Toca a assinatura de todo caminho que sorteia: os três sítios de sorteio, mais
`simulate`, `run_sweep`, `_evaluate_combo` e o que estiver entre eles. Mantém o problema de
alinhamento da Forma A — um `Generator` consumido em ordem tem exatamente a mesma dependência
de quantos números foram puxados antes. Resolve *de onde vem*, não *como se mantém alinhado*.

Sobre o paralelo: um `Generator` é picklável, então atravessa o `ProcessPoolExecutor` — mas
mandar o **mesmo** `Generator` para N workers dá a todos o mesmo fluxo, o que é a versão
determinística do problema de fork. Precisa da Forma C ou D para o paralelo.

### Forma C — derivação hierárquica de sementes (`SeedSequence.spawn`)

**Fato.** `np.random.SeedSequence` permite derivar filhas de uma semente-raiz
(`.spawn(n)`), com garantia de independência estatística entre os fluxos filhos. É o
mecanismo que numpy publica exatamente para o caso "muitos workers, uma semente".

**Porta?** Sim, stdlib do numpy, sem dependência nova. Casa com a decisão do #116 (uma
semente é premissa do estudo): a semente do estudo é a raiz, e cada ponto de grade / cada
worker recebe uma filha determinística da posição dele.

**Preço.** Duas coisas, e a segunda é o ponto de decisão real:

1. Custo de desenho: alguém precisa nomear o eixo de derivação — filha por ponto de grade,
   por estágio, por ambos. Errar o eixo reintroduz o desalinhamento da Forma A num lugar mais
   difícil de ver.
2. **Custo semântico, que o card tem que julgar:** com filha por ponto de grade, dois pontos
   da grade deixam de compartilhar o ruído. Isso torna cada ponto reprodutível e independente
   — mas **remove** a técnica de variáveis aleatórias comuns, em que dois cenários usam o
   mesmo ruído justamente para que a diferença entre eles tenha variância menor. É um trade
   real e ele não é resolvido por medição: depende de a grade ser lida como "N estudos
   independentes" ou "um estudo com N variações". #122 decidiu que a grade é cache de uma
   fronteira, o que empurra para a segunda leitura, mas não a declara.

### Forma D — sorteio por linha, derivado da identidade da linha

**Fato.** Cada linha recebe seu número aleatório de uma função determinística de
(semente do estudo, identidade da linha, nome do sorteio) — em vez de puxar de um fluxo
sequencial. O sorteio da linha *i* não depende de quantas linhas vieram antes.

**Porta?** Sim, mas exige uma identidade estável por linha — e o #118 **matou
`applicant_id`** do schema, medindo que o pacote o fabrica com `range(len(df))`
(`deployment.py:422`). Uma identidade fabricada por posição reintroduz a dependência de
ordenação que a forma existe para eliminar.

**Preço.** É a única forma que resolve o problema de alinhamento da §1.2 por construção:
mudar o corte muda quem contrata, mas não muda o número sorteado para quem continua
contratando. Preço: custa mais por sorteio que um fluxo vetorizado, e o custo por chamada é
uma restrição já medida neste pacote (#122: 13,9× com 300 grupos), então a diferença precisa
ser medida antes de ser assumida pequena. E cria uma dependência dura de identidade de linha
que o #118 acabou de remover — reabrir isso é decisão de schema, não de aleatoriedade.

### Onde as formas não empatam

| forma | reprodutível? | pontos de grade comparáveis? | atravessa `ProcessPoolExecutor`? |
|---|---|---|---|
| A — semente global | sim | **não** (§1.2) | não sem mecanismo extra |
| B — `Generator` passado | sim | **não** (mesmo motivo) | só com C ou D |
| C — `SeedSequence.spawn` | sim | por construção **independentes**, não pareados | sim, é o caso de uso publicado |
| D — por linha | sim | **sim, pareados** | sim, por construção |

As colunas 2 e 3 não são preferências: são a pergunta que Q15 de fato faz, uma vez que a
§1.1 mostrou que não há semente a mudar de lugar.

---

## 3. Q16 — a fronteira entre calcular e apresentar

Três formas. O fato da §1.4 (zero retorno em 41 operações de cálculo) inclina a pergunta,
mas o que se faz com os 42 usos existentes é decisão do #127 e do roadmap (#124).

### Forma A — devolver e imprimir na mesma função

**Fato.** A função calcula, devolve o objeto, e imprime como efeito colateral opcional
(`verbose=`).

**Porta?** Sim, mudança mínima sobre o estado atual: acrescentar `return` aos quatro.

**Preço.** Barato e compatível — nenhum dos 42 usos quebra. Mas não move a fronteira: o
cálculo continua dentro da função que imprime, então continua sem teste que o alcance sem
capturar stdout, e a formatação continua acoplada ao cálculo (é a patologia da §6.3 do
levantamento, `"Yes"`/`"No"` dentro do motor, na sua versão de relatório). Resolve o sintoma
medido (número inacessível), não a fronteira que a pergunta nomeia.

### Forma B — dois verbos: um calcula, outro apresenta

**Fato.** `delta_table(sim) -> DataFrame` e uma apresentação separada que recebe o DataFrame.
É a forma que a régua dplyr do mapa descreve — verbos pequenos e componíveis com tipo de
saída previsível — e é a que o próprio pacote já pratica em `to_decision_dataframe`.

**Porta?** Sim, sem dependência.

**Preço.** Quebra dura nos 42 usos, logo entra na lista do #124. E força uma decisão que hoje
está escondida: **qual é o tipo de saída de cada um dos quatro**. Três deles produzem tabela;
`print_delta_table` produz uma comparação de dois cenários com 15 `print`, e não é óbvio que
caiba numa tabela só — o card tem que olhar. Amarra ao #131: se essas tabelas passam a ser
valor devolvido, elas caem sob o contrato de saída, com nome de coluna e dtype declarados.

### Forma C — o núcleo devolve, e a apresentação vira responsabilidade de fora

**Fato.** O pacote não apresenta: devolve tabelas, e formatação é do consumidor (pandas
Styler, o notebook, o Studio). É o formato estrito do critério functional core / imperative
shell — e, na prática, o que a maior parte das bibliotecas de dados em Python faz.

**Porta?** Sim.

**Preço.** É o mais caro para o usuário de notebook, que é exatamente o usuário que a §16 Q16
nomeia. Os quatro `print_*` existem porque alguém queria uma linha só numa célula, e as 42
chamadas medem que essa vontade é real. Empurrar a formatação para fora troca 1 linha por N
no notebook, ou obriga a masterclass a carregar helpers próprios — o que recria o problema
fora do pacote, sem controle de versão sobre ele.

**Fato que separa esta forma da B, e que o card deve pesar:** a Forma C não é a Forma B levada
ao limite. Na B a apresentação continua no pacote, versionada e testável; na C ela sai. A
diferença é onde mora o código de formatação, não se ele existe.

### Assimetria medida

Nenhuma das três é grátis, mas os custos caem em pessoas diferentes: a Forma A não custa nada
a ninguém e não resolve a fronteira; a Forma B custa 42 chamadas ao roadmap; a Forma C custa
ao usuário de notebook, em toda célula, para sempre.

---

## 4. O que este documento deixa aberto para o #127

1. **Se a grade é N estudos independentes ou um estudo com N variações** — é o que decide
   entre a Forma C e a Forma D de Q15, e nenhuma medição resolve. #122 inclina, não declara.
2. **Se a identidade de linha volta** — a Forma D de Q15 depende dela, e o #118 acabou de
   matar `applicant_id`. Reabrir é decisão de schema.
3. **O eixo de derivação da semente** (por ponto de grade, por estágio, por ambos), se a
   Forma C for escolhida.
4. **O tipo de saída de cada um dos quatro `print_*`**, se a Forma B de Q16 for escolhida —
   e com isso a amarra ao contrato de saída do #131.
5. **O comportamento em POSIX/fork do caminho paralelo** — a §1.3 mediu só Windows/spawn.
   Se o #127 precisar do fato, é medição, não pesquisa.

## 5. O que sobra da Lente B

- **Busca / CART** (§16 19 → #123, #142) — última fatia, segue no #143.
- **Contrato de saída** (§16 9, 20, 10) — fechado em #135, `docs/research/output-contract.md`.
- **Fronteira de módulo** (§16 1, 3, 4, 7, 11, 12, 13) — fechado em #134,
  `docs/research/module-boundaries.md`.
- **Ergonomia de workflow** — fechado em #113, `docs/research/workflow-ergonomics.md`.
- **Round-trip e `Expression`** (§16 5, 14) — fora de escopo por ruling do dono em #135:
  #120 decidiu a matéria sem esperar a pesquisa.
