# Custo do caminho rápido correto — máscara + recalibração por ponto

> **Insumo de decisão, não decisão.** Este documento levanta preços e erros medidos.
> Nenhum veredito "consertar o caminho rápido / apagá-lo" é tomado aqui — esse é o portão
> do #146, quitado no #124. Se você achar uma recomendação neste texto, é um defeito:
> reporte no #149.

Resolve o [#149](https://github.com/matheuspasche/pycreditools/issues/149), que graduou do
[#146](https://github.com/matheuspasche/pycreditools/issues/146) (decisão 13): o portão de
release da v0.6.0 foi declarado **sem saber o preço dele**. Este documento é o preço.

Mede três coisas que o card pede:

1. **Custo por ponto** de "máscara + recalibração", nos regimes do #143 (1, 2 e 3 dimensões).
2. **O erro que sobra** depois da recalibração, contra o ruído amostral.
3. **Onde o meio-termo empata com a re-simulação.**

---

## 0. Correção de premissa: os números do #143 são a 50 mil linhas, não a 3 MM

O enunciado do #149 tabela os dois caminhos existentes como medidos "a 3 MM de linhas". Não
são. O `search-strategies.md` declara a própria base na abertura da §1: *"base sintética de
50 000 linhas (`generate_sample_data(50000, seed=7)`)"*. Os **55 ms fixos + 0,73 ms/ponto** e
os **~82 ms/ponto** são um modelo de 50 mil linhas.

Isso importa porque **nenhum dos dois números transporta para 3 MM** — o custo por ponto é
dominado por passadas O(n) sobre a base, então escala com n. Medido aqui, mesmo par de
caminhos, mesma máquina:

| caminho | 50 mil linhas | 3 MM de linhas | fator |
|---|---|---|---|
| custo fixo (a simulação-base) | 67–141 ms | 6,1–7,4 s | ~50–85× |
| rápido, por ponto | 1,0–1,4 ms | 72–82 ms | ~65× |
| re-simulação, por ponto | 62–73 ms | ~4,0–4,3 s | ~60× |

O modelo do #143 vira, a 3 MM: **≈ 6,5 s fixos + ~80 ms/ponto**. A razão rápido:re-simulação
que o #143 chamou de ~112× mede **~53×** neste levantamento — a política aqui carrega um
`.rate` (o #143 não declara ter um) e a re-simulação aqui não paga stress, então os dois
lados se aproximam. É a **razão**, não o valor absoluto, que é estável entre as duas bases.

Por isso tudo abaixo é medido **nas duas bases**.

---

## 1. Como foi medido

`release/v0.6` em `185396c`, 2026-09-03. Base sintética `generate_sample_data(n, seed=42)`.
Método **analítico** para o custo (o preço de um ponto não depende do método — o #140 mediu
+11,0% nas etapas que aceitam `method`, plano em 30 a 900 pontos) e **os dois métodos** para
o erro.

**A política.** Um `.cutoff` sobre as dimensões varridas + um `.rate("take_up",
observed_col="hired", calibrate_by="score")`, com `current_hired_col="hired"` e
`calibration_score_col="legacy_score"` declarado. Fixar o score de calibração é deliberado:
isola o mecanismo do defeito (a **população** de calibração muda com o corte) do ruído da
cascata do `resolve_calibration_score_col`, que é matéria do #137.

**As dimensões varridas são `score_2`, `score_3`, `score_5` — não `legacy_score`.** Isto é
uma condição necessária para o defeito existir, e vale registrar: o livro incumbente foi
aprovado *pelo* `legacy_score`, então **varrer `legacy_score` não produz swap-out nenhum** até
o corte passar do quantil de aprovação do incumbente. Sem swap-out, a população de keep-ins
não muda com o corte, a calibração não se move, e o caminho rápido bate **exato**. Medido:
cortes de 560 a 680 em `legacy_score` dão erro **+0,0000 pp**. O defeito do #140 só aparece
onde o eixo varrido **não** é o eixo que gerou o livro — que é o caso interessante e o caso
da masterclass.

**Os quatro caminhos custeados.** Todos produzem o mesmo par (aprovação, inadimplência) por
ponto; diferem só em como chegam lá.

| caminho | o que faz |
|---|---|
| `hoje` | máscara vetorizada sobre um baseline, **sem** recalibrar — o que ships (`sweep.py:279-309`) |
| `recal-kernel` | máscara + recalibração reusando `calibrate_by_score_bins` como está |
| `recal-numpy` | máscara + recalibração, mesma matemática em numpy puro |
| `recal-sorted` | idem, com a base **pré-ordenada uma vez** pelo score de calibração |
| `re-simulação` | `policy.simulate(data)` por ponto — o caminho caro |

O `recal-sorted` existe porque o custo dominante da recalibração é um **sort por ponto**
(o `qcut` dentro de `calibrate_by_score_bins`). Ordenar a base uma vez pelo score de
calibração torna os quantis posicionais e a atribuição de bin um `searchsorted` sobre o array
de arestas — o sort por ponto some. Custear só a forma ingênua superestimaria o portão.

**Ancoragem.** O caminho `hoje` aqui é uma reimplementação, então foi cronometrado contra o
`run_sweep` de verdade, líquido do custo fixo:

| | `run_sweep` | reimplementação | delta |
|---|---|---|---|
| 50k, 1 dim, 30 pts | 1,155 ms/pt | 1,053 ms/pt | −8,8% |
| 50k, 2 dims, 900 pts | 1,041 ms/pt | 0,999 ms/pt | −4,0% |
| 3 MM, 1 dim, 30 pts | 81,603 ms/pt | 78,355 ms/pt | −4,0% |

Dentro de 9%. As razões abaixo carregam essa margem.

---

## 2. O custo por ponto

### 2.1 A 3 MM de linhas

Custo fixo: **6,1–7,4 s** (a simulação-base). Pré-ordenação, quando usada: **4,9–7,9 s**,
paga uma vez junto com o fixo.

| dims | k | pontos | `hoje` | `recal-sorted` | `recal-numpy` | `recal-kernel` |
|---|---|---|---|---|---|---|
| 1 | 10 | 10 | 72,2 | 118,7 | 204,7 | 256,0 |
| 1 | 20 | 20 | 82,2 | 121,2 | 201,3 | 253,8 |
| 1 | 30 | 30 | 80,5 | 116,8 | 210,0 | 262,0 |
| 2 | 10 | 100 | 81,8 | 97,1 | 165,2 | 213,3 |
| 2 | 20 | 400 | 79,9 | 94,1 | 176,6 | 215,9 |
| 3 | 10 | 1 000 | 77,7 | 93,2 | 158,4 | 200,0 |

*(ms/ponto; re-simulação no mesmo regime: **~4 000–4 300 ms/ponto**.)*

**A taxa marginal é plana em 1, 2 e 3 dimensões nos quatro caminhos** — a mesma propriedade
que o #143 mediu para o caminho rápido, e ela vale igual para o corrigido.

**Ressalva de amostragem, declarada.** As grades de 1 dimensão têm 10–30 pontos, poucos demais
para amortizar custo de primeiro toque; ali o `recal-sorted` aparece **+36 a +47 ms/ponto**
acima do `hoje`. Nas grades bem amostradas (100 a 1 000 pontos, dims 2 e 3) o mesmo delta mede
**+14 a +16 ms/ponto**. O número de baixo é o confiável; os dois estão na tabela para não
esconder a dispersão.

### 2.2 A 50 mil linhas (o regime que o #143 mediu)

Custo fixo: **67–141 ms**. Pré-ordenação: **64–117 ms**.

| dims | k | pontos | `hoje` | `recal-sorted` | `recal-numpy` | `recal-kernel` |
|---|---|---|---|---|---|---|
| 1 | 10 | 10 | 1,201 | 1,777 | 3,355 | 7,263 |
| 1 | 20 | 20 | 1,168 | 1,838 | 3,444 | 7,531 |
| 1 | 30 | 30 | 1,165 | 1,766 | 3,314 | 7,443 |
| 2 | 10 | 100 | 1,212 | 1,832 | 3,072 | 7,152 |
| 2 | 20 | 400 | 1,304 | 1,794 | 3,177 | 7,356 |
| 2 | 30 | 900 | 1,355 | 1,574 | 2,909 | 6,654 |
| 3 | 10 | 1 000 | 1,067 | 1,441 | 2,630 | 6,177 |
| 3 | 20 | 8 000 | 1,098 | 1,466 | 2,623 | 6,013 |

*(ms/ponto; re-simulação no mesmo regime: **62–73 ms/ponto**.)*

### 2.3 O preço do portão, em uma linha

Quanto custa **corrigir** o caminho rápido, relativo ao caminho rápido errado de hoje, nas
grades bem amostradas:

| forma da recalibração | 50 mil linhas | 3 MM de linhas |
|---|---|---|
| pré-ordenada (`recal-sorted`) | **+16% a +35%** | **+18% a +20%** |
| numpy sem pré-ordenar | +2,1× a +2,5× | +2,0× a +2,2× |
| reuso direto do kernel do pacote | +4,9× a +5,8× | +2,6× a +2,7× |

**A forma escolhida importa mais que o fato de recalibrar.** A distância entre o teto e o piso
desta tabela (≈5,8× contra ≈1,2×) é maior que a distância entre o piso e não recalibrar.

---

## 3. O erro que sobra

### 3.1 Método analítico: sobra zero

A 3 MM, cinco cortes em `score_2` cobrindo a banda de aprovação de 24% a 76%, contra simular
aquela política à mão — o teste do #140:

| corte | aprovação | inadimplência à mão | erro de `hoje` | erro de `recal-sorted` |
|---|---|---|---|---|
| 233,8 | 0,7594 | 0,113218 | +0,0074 pp | **+0,000000 pp** |
| 366,7 | 0,6294 | 0,109845 | +0,0115 pp | **+0,000000 pp** |
| 499,5 | 0,5040 | 0,102717 | +0,2049 pp | **+0,000000 pp** |
| 632,3 | 0,3775 | 0,088279 | +0,6961 pp | **+0,000000 pp** |
| 765,2 | 0,2444 | 0,065951 | +1,0015 pp | **−0,000000 pp** |

**A recalibração não reduz o erro — ela o elimina, até a precisão de ponto flutuante.** Isso
é esperado e vale dizer por quê: uma vez recalibrada a população de keep-ins do ponto, a
máscara volta a ser o que o comentário `sweep.py:284` afirma que ela é. O comentário não
estava errado sobre a máscara; estava errado sobre o baseline ser invariante.

As três formas de recalibração (`kernel`, `numpy`, `sorted`) dão **o mesmo resultado exato** —
verificado ponto a ponto a 50 mil, com e sem `.rate`.

O perfil do erro de `hoje` reproduz o #140 qualitativamente: **sempre para cima**, crescendo
com o corte, ~zero onde o corte não move a população de keep-ins. Nesta política a magnitude
chega a **+1,00 pp** a 3 MM (e a +1,77 pp na variante sem `.rate` a 50 mil), acima dos 0,58 pp
do #140 — regime mais agressivo, não contradição: o eixo varrido aqui é ortogonal ao eixo que
gerou o livro, então há mais swap-out por passo de corte.

### 3.2 Método estocástico: dentro do ruído

O default da v0.6 é estocástico (#116), e ali não existe "exato" — existe "dentro do ruído".
Ruído amostral medido no mesmo ponto, 6 a 8 rodadas independentes: **sd 0,022 a 0,039 pp**,
da mesma ordem dos 0,018 pp do #140.

| corte | erro de `hoje` | em sd | erro de `recal-sorted` | em sd |
|---|---|---|---|---|
| 233,8 | +0,0136 pp | 0,6 | +0,0048 pp | 0,2 |
| 366,7 | +0,0132 pp | 0,5 | −0,0107 pp | 0,4 |
| 499,5 | +0,1804 pp | 6,4 | −0,0021 pp | 0,1 |
| 632,3 | +0,6811 pp | 24,3 | +0,0064 pp | 0,2 |
| 765,2 | +1,0298 pp | 41,2 | +0,1020 pp | 4,1 |

O ponto de 4,1 sd foi conferido, não explicado away: 8 rodadas pareadas do caminho rápido
contra 8 da simulação à mão, nos três cortes altos, medem o viés em **0,2 / 1,2 / 0,9 erros
padrão** — magnitude máxima **0,019 pp**, indistinguível do ruído. A leitura de 4,1 sd era
uma realização única, não viés.

| corte | à mão (média ± sd) | `recal-sorted` (média ± sd) | viés | em SE |
|---|---|---|---|---|
| 499,5 | 0,102665 ± 0,0357 pp | 0,102694 ± 0,0370 pp | +0,0029 pp | 0,2 |
| 632,3 | 0,088144 ± 0,0275 pp | 0,088331 ± 0,0349 pp | +0,0187 pp | 1,2 |
| 765,2 | 0,065789 ± 0,0389 pp | 0,065923 ± 0,0200 pp | +0,0135 pp | 0,9 |

**Resposta ao item 2 do card: sim, volta a bater dentro do ruído amostral.**

---

## 4. Onde o meio-termo empata com a re-simulação

**Não empata, e não é por dimensões.** O custo por ponto dos dois caminhos é **plano no número
de dimensões varridas**, medido em ambos:

| n | dims | `hoje` | `recal-sorted` | re-simulação |
|---|---|---|---|---|
| 50 mil | 1 | 1,17 | 1,79 | 64,8 |
| 50 mil | 2 | 1,30 | 1,79 | 61,8 |
| 50 mil | 3 | 1,08 | 1,45 | 73,3 |
| 3 MM | 1 | 80,5 | 116,8 | ~4 250 |
| 3 MM | 2 | 79,9 | 94,1 | 3 988 |
| 3 MM | 3 | 77,7 | 93,2 | 4 249 |

Adicionar dimensão multiplica o **número de pontos** (`k^N`) igualmente nos dois caminhos e
deixa a **razão** intacta. Não existe N a partir do qual manter dois caminhos deixa de valer
**por causa de N**.

O que move a razão é **n**, e move a favor do meio-termo:

| razão | 50 mil linhas | 3 MM de linhas |
|---|---|---|
| re-simulação ÷ `hoje` | ~53× | ~53× |
| re-simulação ÷ `recal-sorted` | ~44× | ~45× |
| re-simulação ÷ `recal-numpy` | ~23× | ~26× |
| re-simulação ÷ `recal-kernel` | ~10× | **~20×** |

**Mesmo a forma mais ingênua da recalibração — reusar o kernel do pacote como está — fica
10× a 20× abaixo da re-simulação.** O meio-termo não degenera para perto da re-simulação em
regime nenhum medido.

### 4.1 Orçamento de paciência de 60 segundos

Pontos que cabem, líquido do custo fixo (a 3 MM: ~6,5 s de baseline, mais ~6 s de
pré-ordenação onde ela é usada):

| caminho | 50 mil linhas | 3 MM de linhas |
|---|---|---|
| `hoje` | ~54 500 | ~670 |
| `recal-sorted` | ~41 000 | ~500 |
| `recal-numpy` | ~22 000 | ~300 |
| `recal-kernel` | ~9 800 | ~260 |
| re-simulação | ~950 | ~14 |

A 3 MM, uma grade 2-D de 30×30 (900 pontos, a grade que o #143 usou para medir a fronteira de
Pareto em 39,7%) custa **~78 s** hoje, **~97 s** recalibrada e pré-ordenada, e **~64 minutos**
re-simulando.

---

## 5. O que este documento **não** mede

- **Não implementa a correção.** O `recal-sorted` é um protótipo de medição, não um desenho
  de `Stage`/motor. Ele mostra que o preço existe nessa faixa, não que a implementação final
  cairá exatamente nela.
- **Não custeia o caminho paralelo.** Todas as medições são seriais. O #140 mediu que sob
  `parallel=True` o gargalo vira pickling da base; se isso se mantiver, o delta relativo da
  recalibração encolhe, mas não foi medido aqui.
- **Não reabre o `k^N`.** A pergunta de estratégia de busca é do
  [#147](https://github.com/matheuspasche/pycreditools/issues/147), pós-v0.6.
- **Não mexe na conta do #122 além de recustear o regime.** O #122 concluiu "grade é cache"
  com 200 simulações contra ~245 de bisecção aninhada. Como a razão rápido:re-simulação não se
  move com a correção (§4) e o custo relativo do meio-termo é +18% a +20%, a aritmética do
  #122 **sobrevive à correção** no regime em que foi feita. Se ela se transporta para o regime
  de re-simulação continua sendo o que o #143 disse que era: não medido.
- **Não escolhe a saída do portão.** Esse é o #124.
