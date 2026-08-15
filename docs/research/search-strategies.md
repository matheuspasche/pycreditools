# Estratégias de busca quando a grade não cabe — levantamento de referências

> **Insumo de decisão, não decisão.** Este documento levanta fatos, formas e preços.
> Nenhum veredito "adotar / adaptar / descartar" é tomado aqui — esses são de #123
> (política auto) e #142 (grade segmentada). Se você achar uma recomendação neste texto, é
> um defeito: reporte no #143.

Resolve a fatia **busca / CART** da Lente B (#143) — a última. Cobre uma pergunta da §16 do
`architecture-critique.md`: **19** (que estratégias de busca existem quando a grade não cabe),
levantada na §12.1.

Referência nomeada pelo ticket: **CART / árvore de decisão**, a partir do insight do dono
(2026-07-24): alvo + decisões binárias = árvore, logo talvez exista algoritmo pronto com
ordem de nós pré-determinada, em vez do exaustivo. As demais famílias entram porque a
pergunta pede o espaço, e o motivo de cada uma está registrado.

## Como ler

Cada forma tem **fato**, **porta para Python?**, **preço**.

**Ressalva de método herdada de #134:** onde a medição mostra que as formas **não empatam**,
este documento diz isso e mostra o número. Nesta fatia a medição é dura e separa as formas em
dois grupos que não competem entre si — §3.

**Restrição de desenho herdada de #135:** toda forma custeada tem que dizer o que a impede de
ter o destino do `_types.py` (declaração que existe e ninguém usa). Aqui a restrição vira
concreta: uma estratégia de busca que exija o usuário escolher parâmetros de busca é uma
declaração opcional, e §3.3 mostra o que já aconteceu com a única que o pacote tem.

---

## 1. O estado medido

Medições sobre `release/v0.6`, 2026-08-15, base sintética de 50 000 linhas
(`generate_sample_data(50000, seed=7)`), método analítico.

### 1.1 Não existe uma grade — existem duas, separadas por ~112×

`run_sweep` tem dois caminhos (`sweep.py:279`). O **caminho rápido** vale só quando a
varredura é de cutoffs e nada mais (`only_cutoffs = not base_rates and stress_factors is
None`): roda **uma** simulação base e cada ponto da grade vira máscara vetorizada. O comentário
do próprio código registra que isso é **exato**, não aproximação — "a cutoff is a pure mask
over the baseline". Qualquer `base_rate` ou `stress_factor` na varredura derruba o caminho
rápido e **cada ponto re-simula**.

Custo por ponto, medido:

| dimensões | k | pontos | tempo | ms/ponto |
|---|---|---|---|---|
| 1 | 10 | 10 | 0,061 s | 6,13 |
| 1 | 20 | 20 | 0,067 s | 3,36 |
| 1 | 30 | 30 | 0,078 s | 2,60 |
| 2 | 10 | 100 | 0,129 s | 1,29 |
| 2 | 20 | 400 | 0,359 s | 0,90 |
| 2 | 30 | 900 | 0,739 s | 0,82 |
| 3 | 10 | 1 000 | 0,824 s | 0,82 |
| 3 | 20 | 8 000 | 6,141 s | 0,77 |
| 3 | 30 | 27 000 | 19,678 s | 0,73 |

O modelo cai direto do dado: **custo ≈ 55 ms fixos + 0,73 ms por ponto**, e a taxa marginal é
plana em 1, 2 e 3 dimensões. Os 55 ms são a simulação base; tudo acima disso é máscara.

Caminho de re-simulação, mesma base, varrendo cutoff × `stress_factors=[1.0, 1.3]`:

| dimensões | pontos | tempo | ms/ponto |
|---|---|---|---|
| 1 | 4 | 0,338 s | 84,5 |
| 1 | 8 | 0,660 s | 82,5 |
| 1 | 16 | 1,305 s | 81,5 |

**~82 ms/ponto, sem amortização** — não há custo fixo a diluir, porque não há base
compartilhada.

**A razão é ~112×** (0,73 vs 82). Este é o número mais importante da fatia, e ele diz que
"a grade não cabe" não é uma condição, são duas, com limiares muito distantes. Para um
orçamento de paciência de 60 segundos:

| caminho | pontos que cabem | 3 dims | 4 dims | 5 dims |
|---|---|---|---|---|
| rápido | ~82 000 | k ≈ 43 | k ≈ 17 | k ≈ 9 |
| re-simulação | ~730 | k ≈ 9 | k ≈ 5 | k ≈ 3 |

Consequência para o desenho: **uma estratégia de busca única, aplicada aos dois caminhos, ou
é desnecessária num deles ou é insuficiente no outro.** #122 já mediu que a grade é cache e
que a bisecção aninhada não ganhava — aquela medição foi feita no regime rápido. Ela não se
transporta para o regime de re-simulação, e este documento não a estende.

### 1.2 As duas métricas são monótonas no corte

Varredura de 60 cortes em `legacy_score`, contando o sinal das 59 diferenças consecutivas:

| métrica | subidas | descidas |
|---|---|---|
| taxa de aprovação | **0** | 59 |
| taxa de inadimplência | **0** | 59 |

Monotonicidade perfeita nas duas. Isso habilita bisecção em 1 dimensão por construção — e ao
mesmo tempo tira o motivo dela, §3.2.

**Ressalva medida, com fonte:** monotonicidade **agregada** não é monotonicidade da
calibração. A mesma execução emite
`CalibrationReliabilityWarning: 2 adjacent score bin(s) invert — PD moves against the score's
declared direction` (`simulation.py:632`). O agregado é monótono; a curva de PD por faixa
inverte localmente. Uma estratégia que assuma monotonicidade **por faixa** — e várias
assumem — está assumindo mais do que o pacote garante. O aviso já existe e já é emitido; o
que não existe é alguém a jusante que o consuma.

### 1.3 A fronteira é 40% da grade

Grade 2-D de 30×30 = 900 pontos em `legacy_score` × `score_2`. Pontos não dominados
(maior aprovação e menor inadimplência):

**357 de 900 — 39,7% da grade está na fronteira de Pareto.**

Este número, cruzado com a decisão do #122 (a saída é a fronteira; a seleção é camada
tabela→tabela que recebe a grade pronta; apetite é filtro do humano), **é o fato que
reclassifica a pergunta inteira**. A §12.1 do levantamento pergunta como evitar avaliar
`k^N`. Mas o entregável não é um ponto: é ~40% dos pontos. Uma estratégia que converge para
um ótimo entrega 1 onde se pediu 357, e o trabalho economizado seria justamente o que se
queria produzir.

Isso separa as formas da §2 em dois grupos que não competem — §3.1.

### 1.4 O que existe hoje de "busca"

`np.linspace` por coluna (`optimization.py:177`) × `itertools.product` de todas as dimensões
(`sweep.py:276`). Sem poda, sem adaptação, sem critério de parada. Os parâmetros de resolução
são `cutoff_steps` e `percentiles`, dois dos dez de `optimize_cutoffs` — e ambos morrem junto
com o alvo pelo #122, que matou `target_default_rate`/`min_approval_rate` como argumentos de
motor.

---

## 2. As formas

Sete famílias. As três primeiras acham ponto; as quatro últimas, ou produzem conjunto, ou
mudam a resolução em vez do critério.

### Forma A — grade exaustiva (o estado atual)

**Fato.** Produto cartesiano, avaliação de todos os pontos.

**Porta?** Já está.

**Preço.** `k^N`, com os dois limiares da §1.1. Vantagens que nenhuma outra forma tem e que
precisam ser ditas porque são fáceis de esquecer: é **exata** no caminho rápido (§1.1),
produz a fronteira inteira de graça (§1.3), é trivialmente paralelizável (já é,
`_parallel.py:18`), e não tem parâmetro de busca a ajustar — só resolução.

### Forma B — bisecção / busca binária por dimensão

**Fato.** Explora a monotonicidade (§1.2) para achar, em `log k` avaliações, o corte que
atinge um alvo numa métrica.

**Porta?** Sim, trivial, sem dependência.

**Preço.** #122 já mediu no regime rápido: ~245 avaliações de bisecção aninhada contra 200 da
grade, **e ainda perderia a curva**. Este documento acrescenta o motivo estrutural: bisecção
resolve "que corte dá inadimplência de 8%", e o #122 decidiu que **essa pergunta não é do
motor** — alvo é filtro do humano sobre a grade pronta. A forma resolve uma pergunta que
deixou de existir.

Onde ela volta a ter sentido: no regime de re-simulação (82 ms/ponto), onde `log k` contra
`k` é a diferença entre 1 s e 20 s. Mas aí ela precisa de um alvo, e o alvo foi removido do
motor — logo a forma exige reabrir o #122, não se compõe com ele.

### Forma C — surrogate / otimização bayesiana (`optuna`, `scikit-optimize`)

**Fato.** Modela a superfície objetivo com um modelo probabilístico e escolhe o próximo ponto
a avaliar por ganho esperado. Feita para o caso "cada avaliação é cara".

**Porta?** Sim, bibliotecas maduras. Dependência nova — e o repo hoje não tem nenhuma
dependência de otimização.

**Preço.** Três, e o terceiro é decisivo:

1. Cada avaliação precisa ser cara para o overhead do modelo compensar. A 0,73 ms/ponto do
   caminho rápido, o modelo custa mais que a avaliação que ele evita. A 82 ms/ponto pode
   compensar — mas isso é uma medição a fazer, não um fato deste documento.
2. É **aproximada** por definição, num pacote cujo caminho rápido é exato (§1.1) e cujo
   critério de aceite da v0.6 é paridade numérica contra a v0.5 (nota do mapa #111). Trocar
   exatidão por velocidade num release cujo portão é bater número é uma tensão que o #124
   teria que resolver.
3. **Otimiza para um escalar.** Existe variante multiobjetivo (`optuna` implementa NSGA-II e
   MOTPE), mas a família nasce apontando um ponto — e §1.3 diz que o entregável são 357.

### Forma D — árvore de decisão / CART

**Fato.** Particiona o espaço recursivamente, escolhendo em cada nó a variável e o corte que
mais separam o alvo. É a forma que o insight do dono nomeia: alvo + decisões binárias =
árvore, com ordem de nós determinada pelo algoritmo em vez do produto cartesiano.

**Porta?** Sim, `sklearn.tree` é maduro e já é vocabulário conhecido do domínio.

**Preço.** Duas objeções estruturais, e a segunda é a que o próprio ticket já levantava:

1. **A árvore escolhe cortes para separar o alvo, não para varrer a superfície.** Ela devolve
   *um* conjunto de regras — que é uma política, não uma fronteira. Está no grupo dos
   ponto-únicos da §3.1.
2. **O alvo se move com os swap-ins**, e isto agora tem mecanismo nomeado pelas decisões do
   mapa: o desfecho de swap-in é *inferido* (baseline × inflação, #117), não observado. CART
   clássica assume rótulo fixo e dado; aqui o rótulo de metade da população é produto da
   própria simulação, e muda quando o corte muda. A árvore treinada sobre o rótulo inferido
   está aprendendo a função de inferência tanto quanto o risco.

**Onde a família ainda serve, e o levantamento não tinha notado:** o `suggest_hard_filters` e
o `fit_risk_groups` do pacote já fazem exatamente esse trabalho — achar cortes que separam
desfecho — e o #126 já decidiu que rating é **sugestor standalone** na postura consultiva.
Ou seja, CART já tem casa no pacote, e não é a camada de varredura; é a camada de sugestão a
montante dela. Registrar isso não é escolher: é apontar que a pergunta §16 19 e o insight do
dono podem estar mirando camadas diferentes, e o #123 tem que dizer qual.

### Forma E — evolutivo multiobjetivo (NSGA-II)

**Fato.** Família que produz uma **aproximação da fronteira de Pareto** diretamente, mantendo
uma população de soluções não dominadas em vez de convergir para um ponto.

**Porta?** Sim (`pymoo`, `optuna`). Dependência nova.

**Preço.** É a única forma da lista que produz o mesmo tipo de saída que o #122 decidiu, o que
a torna a comparação honesta contra a Forma A — e é aí que ela perde no regime rápido: entrega
uma fronteira **aproximada e amostrada** onde a grade exaustiva entrega a fronteira **exata e
completa** por 19,7 s em 27 000 pontos. Ganha só quando `k^N` estoura o orçamento, isto é, a
partir de 4–5 dimensões no caminho rápido e 3 no de re-simulação (§1.1).

Preço adicional: introduz parâmetros de busca (tamanho de população, gerações, operadores)
que o usuário teria que entender — e isso colide com a régua dplyr do mapa e com a restrição
do #135, §3.3.

### Forma F — amostragem em vez de enumeração (aleatória, LHS, Sobol)

**Fato.** Avalia N pontos escolhidos para cobrir o espaço, em vez de todos. Custo desacoplado
de `k^N`: escolhe-se N.

**Porta?** Sim, `scipy.stats.qmc` é stdlib científica, sem dependência nova de fato.

**Preço.** Preserva o que a Forma A tem de bom — nenhuma suposição sobre a superfície, produz
conjunto e não ponto, paraleliza igual — e troca completude por orçamento fixo. A fronteira
sai amostrada: com 40% dos pontos na fronteira (§1.3), uma amostra de N pontos rende ~0,4·N
pontos de fronteira, o que é uma relação favorável e **medida**, não suposta.

Perde a estrutura de grade: hoje a saída é uma tabela onde as colunas de dimensão têm valores
repetidos e regulares, e a leitura de "varri este eixo" é imediata. Com amostragem, cada linha
é um ponto solto — o que interage com o contrato de saída do #131 e com o `by=` do #142.

### Forma G — refinamento em duas passadas (grade grossa, depois fina na região de interesse)

**Fato.** Uma grade barata sobre todo o espaço, e uma segunda, fina, só onde a primeira
mostrou que a fronteira passa.

**Porta?** Sim, é composição de duas chamadas do que já existe — zero mecanismo novo, zero
dependência.

**Preço.** É a única forma que **não** exige decidir nada do que o #122 removeu: não precisa
de alvo, não precisa de critério de parada, e a segunda passada é escolha do humano sobre a
tabela da primeira — exatamente a postura consultiva já decidida. E o custo fixo de 55 ms
(§1.1) é pago duas vezes, o que é irrelevante contra os ganhos de `k^N`.

Preço real: **não é uma estratégia de busca, é uma composição de verbos** — o que só tem
preço se a superfície não permitir chamar `run_sweep` duas vezes com grades diferentes. Hoje
permite. Logo esta forma é menos uma opção de algoritmo e mais uma constatação de que a
pergunta §16 19 pode ter resposta na superfície, não no motor. O #123 tem que decidir se isso
é resposta ou fuga da pergunta.

---

## 3. Onde as formas não empatam

### 3.1 Ponto único × conjunto: não são alternativas, são propósitos

| forma | o que devolve | compatível com o entregável do #122 (a fronteira)? |
|---|---|---|
| B — bisecção | 1 ponto, dado um alvo | **não** — e o alvo foi removido do motor |
| C — surrogate | 1 ponto (ou fronteira aproximada, na variante MO) | parcial |
| D — CART | 1 conjunto de regras | **não** — e ver §2.D sobre a camada |
| A — grade | fronteira exata e completa | sim, é o estado atual |
| E — NSGA-II | fronteira aproximada | sim |
| F — amostragem | fronteira amostrada (~0,4·N) | sim |
| G — duas passadas | fronteira, em duas resoluções | sim |

As três primeiras só voltam à mesa se o #123 reabrir a decisão do #122 — o que é decisão
dele, não defeito deste documento.

### 3.2 A monotonicidade habilita a forma que ela mesma torna inútil

§1.2 mede monotonicidade perfeita, o que é a precondição da bisecção. Mas monotonicidade
perfeita em 1 dimensão significa que **todo ponto da curva está na fronteira** — não há
ótimo interno a encontrar, a curva inteira é o trade-off. A bisecção acha rápido um ponto
que não é especial. O valor da monotonicidade aqui não é habilitar busca: é permitir **poda**
em N dimensões (se um corte já viola um teto, cortes mais frouxos também violam), o que é a
Forma G com um critério, e não uma família à parte.

### 3.3 A restrição do #135, aplicada: parâmetro de busca é declaração opcional

O pacote já tem uma constante de busca que ninguém escolheu e que decide o resultado: o
`5.0` de `tradeoff_score = app - 5.0 * dr` (`optimization.py:194`) — a taxa de câmbio entre
aprovação e inadimplência como literal, sem parâmetro e sem documentação, e o #122 já a matou.

Toda forma que traga parâmetros de busca (C, E) traz o mesmo tipo de objeto: um número que
decide o resultado e que o usuário não tem como calibrar. A diferença é que o `5.0` era um só
e escondido; população e gerações de NSGA-II são vários e expostos — o que pela régua dplyr
do mapa (verbos pequenos, cada um fazendo uma coisa óbvia) é pior, não melhor. As formas A, F
e G não têm parâmetro de busca: têm resolução ou orçamento, que são grandezas que o usuário
entende sem teoria.

Isto é assimetria medida no próprio repo, não preferência.

---

## 4. O que este documento deixa aberto para o #123 e o #142

1. **O regime que importa é o rápido ou o de re-simulação?** As duas medições estão 112×
   apart e nenhuma estratégia serve bem aos dois. O caso auto do #123 (varrer HFs + scores) é
   só cutoffs — logo rápido — **a menos que** varra base rates, e isso ainda não está dito.
2. **A medição do #122 (grade é cache, bisecção não ganha) foi feita no regime rápido.** Não
   se transporta. Se o caso auto entrar no regime de re-simulação, o custeio precisa ser
   refeito.
3. **CART é camada de varredura ou de sugestão?** O pacote já a tem na segunda
   (`suggest_hard_filters`, `fit_risk_groups`, e o #126 decidiu a postura consultiva). O
   insight do dono e a §16 19 podem estar mirando camadas diferentes.
4. **A poda por monotonicidade** (§3.2) é a única exploração da estrutura que não exige alvo
   nem parâmetro. Não foi custeada com número aqui — é medição, não pesquisa.
5. **Se a saída pode deixar de ser grade regular** (Forma F), com consequência no contrato de
   saída do #131 e no `by=` do #142.
6. **Quem consome o `CalibrationReliabilityWarning`** (§1.2): o agregado é monótono, a
   calibração por faixa inverte, e hoje ninguém a jusante lê o aviso.

## 5. Lente B, completa

| fatia | §16 | artefato | ticket |
|---|---|---|---|
| Ergonomia de workflow | — | `docs/research/workflow-ergonomics.md` | #113 |
| Fronteira de módulo | 1, 3, 4, 7, 11, 12, 13 | `docs/research/module-boundaries.md` | #134 |
| Contrato de saída | 9, 20, 10 | `docs/research/output-contract.md` | #135 |
| Núcleo funcional | 15, 16 | `docs/research/functional-core.md` | #143 |
| Busca / CART | 19 | este documento | #143 |
| Round-trip / `Expression` | 5, 14 | **fora de escopo** — #120 decidiu sem esperar | #135 |

As quatro perguntas de §16 que nenhuma fatia de pesquisa cobriu — **2** (declarado vs
ajustado), **8** (a linha entre conveniência e silêncio), **17** (como se representa o alvo)
e **18** (vencedor único é da biblioteca ou de quem chama) — não ficaram sem resposta: três
foram **decididas sem pesquisa**, e uma segue em card aberto.

| §16 | onde caiu |
|---|---|
| 2 | decidida em #126 — declarado-vs-ajustado não vira regra do pacote |
| 8 | **aberta**, em #132 |
| 17 | decidida em #122 — o alvo não vira tipo, é filtro do humano |
| 18 | decidida em #122 — de quem chama; a seleção é camada tabela→tabela |

Padrão que vale registrar para o mapa, porque se repetiu quatro vezes nesta trilha (5, 14,
17, 18): **o card de decisão alcançou a pergunta antes da fatia de pesquisa**, e a pesquisa
teria custeado forma já escolhida. Não é defeito do fatiamento — é o que acontece quando a
frente de decisão anda mais rápido que a de levantamento. O que custa é só descobrir tarde.
