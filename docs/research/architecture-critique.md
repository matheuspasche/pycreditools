# Crítica de arquitetura — levantamento medido

- **Status:** insumo, não decisão
- **Data:** 2026-07-25
- **Branch medida:** `release/v0.6` (`627b841`)
- **Propósito:** municiar a pesquisa de referências (#113) com os problemas *do código*,
  descritos sem veredito e sem proposta de solução.
- **Método:** leitura direta do núcleo (`policy`, `simulation`, `stages`, `stress`,
  `expressions`, `sweep`, `optimization`, `analysis`) + `studio/models.py`. Toda afirmação
  carrega `arquivo:linha`. Onde não medi, está escrito que não medi.

## Como este documento foi escrito, e por quê assim

Escrito **sem ler #113**, deliberadamente. Se a crítica fosse redigida a partir da pauta de
pesquisa, ela devolveria a pauta de volta em outras palavras — e a pesquisa acharia
referências para os problemas que a própria pesquisa já tinha nomeado. O valor aqui depende
de o levantamento ser independente: são os sintomas medidos, e as perguntas de forma que
eles abrem, **antes** de qualquer referência opinar.

Consequência aceita: pode haver sobreposição com o que #113 já cobre. Sobreposição é barata.
Circularidade não é.

O documento também **não propõe solução**. Onde a tentação apareceu, virou pergunta. Cada
seção termina em *"a pergunta que abre"* — é isso que a pesquisa pode responder com fatos de
outras arquiteturas, e é isso que os tickets de decisão (#116–#130) consomem.

---

## 0. Sumário

| # | Patologia | Evidência âncora | O que ela custa hoje |
|---|---|---|---|
| 1 | `CreditPolicy` é quatro objetos num só | `policy.py:21-33`, 17 métodos | Divergent change; nada tem fronteira |
| 2 | Premissas de estudo moram dentro da política | `sweep.py:164-167`, `studio/models.py:73` | O motor precisa violar o próprio contrato |
| 3 | Imutabilidade de fachada | `policy.py:90-97`, `stress.py:50` | `deepcopy` obrigatório; round-trip quebrado |
| 4 | Reconstrução manual perde campo | `sweep.py:174-179` | **Bug medido**: varrer `base_rate` apaga `observed_col` |
| 5 | Inferência silenciosa como classe | `stages.py:158`, `simulation.py:271`, `:718` | Resultado muda sem o usuário saber |
| 6 | Contrato de dados não declarado | `simulation.py:441-452`, `:192` | Saída bilíngue, dtype por modo |
| 7 | Estágio recebe a política inteira | `stages.py:36` | Ciclo de import; máscara resolvida 2× |
| 8 | Um primitivo, dois donos | `simulation.py:334`, `stages.py:319` | Motor precisa perguntar qual vale |
| 9 | Calibração em dois lugares | `expressions.py:179`, `simulation.py:682+` | População escolhida por endereço, não por parâmetro |
| 10 | Serialização à mão em 8 arquivos | 22 `to_dict`/`from_dict` | 22 lugares onde o round-trip pode quebrar |
| 11 | Núcleo imperativo | 5 `print_*`, `np.random` global | Irreprodutível; cálculo colado em IO |
| 12 | Camada de varredura | `optimization.py:194`, `sweep.py:276` | Grade exaustiva; "melhor único" com peso mágico |
| 13 | Papéis de coluna em três grafias | `studio/models.py:17-30` | Terceiro vocabulário, com campos que o motor não conhece |

---

## 1. Coesão: `CreditPolicy` é quatro objetos com um nome só

### Medida

Treze campos (`policy.py:21-33`), que se separam por **motivo de mudança**:

| Grupo | Campos | Muda quando... |
|---|---|---|
| Schema do dado | `applicant_id_col`, `score_cols`, `current_approval_col`, `actual_default_col`, `time_col`, `current_hired_col`, `estimated_default_col` | a base muda |
| As regras | `stages` | a política muda |
| Premissas do estudo | `stress_scenarios`, `calibration_score_col`, `calibration_bins`, `calibration_base` | a pergunta muda |
| Ambíguo | `rating_recipe` | (ver §1.1) |

Dezessete métodos (`grep -c "def " policy.py` = 17), cobrindo cinco responsabilidades:
construção (`add_stage:61`, `add_stress:66`, `with_rating:71`, `with_calibration:77`,
`cutoff:101`, `filter:105`, `rate:109`, `stress_aggravation:130`, `stress:134`), coerção
(`__post_init__:36`), serialização (`to_dict:196`, `from_dict:225`), validação
(`validate:161`), execução (`simulate:138`), export (`export:287`) e apresentação
(`describe:255`).

Sete de treze campos — mais da metade — descrevem *o DataFrame do usuário*, não a política.

### Por que isso é o problema-raiz, e não um sintoma

Toda outra seção deste documento é derivada desta. Quando um tipo tem quatro motivos para
mudar, cada função que o recebe recebe também os outros três; é por isso que `Stage.apply`
tem `policy: Any` (§7), que o sweep precisa fabricar políticas (§2), que a serialização é
grande e frágil (§10), e que `score_cols` acumulou três empregos (#81).

### 1.1 O caso difícil: `rating_recipe`

Não é claramente nenhum dos quatro. A régua de rating **se deploya** (`deployment.py` a
embrulha), o que a coloca do lado das regras. Mas ela carrega **estado ajustado** — é
resultado de um fit sobre uma base — o que a coloca do lado de "leitura sobre a política".
E ADR 0007 (refit sobre sobreviventes) é o caso que quebra o empate para os dois lados ao
mesmo tempo.

### A pergunta que abre

Quando um objeto de configuração acumula papéis assim, outras arquiteturas separam em
quantos tipos, e com que critério de fronteira? Existe critério publicado melhor que
"motivo de mudança"? E o caso *declarado vs ajustado* (`rating_recipe`) — outras
arquiteturas tratam como dois tipos, um tipo com dois estados, ou um tipo parametrizado?

---

## 2. Premissas de estudo dentro da política

Esta é a crítica que originou o mapa v0.6. Aqui interessa só o que é **medido**, porque as
três evidências abaixo não são opinião de design: são o código dizendo que a fronteira está
no lugar errado.

### 2.1 O motor precisa violar o próprio contrato declarado

`sweep.py:8-12` declara, em prosa, o contrato da varredura:

> **The config always binds.** Every stage, stress scenario and calibration the policy
> declares holds at every grid point.

`sweep.py:164-167`, na mesma classe de arquivo, faz o contrário:

```python
if aggravation_factor is not None:
    temp = dataclasses.replace(
        temp, stress_scenarios=(AggravationStress(factor=aggravation_factor),)
    )
```

Substitui a tupla inteira: **os cenários que a política declarou são descartados**, não
combinados. A docstring do parâmetro admite (`sweep.py:238-239`: *"replaces the policy's
stress scenarios per grid point"*).

O ponto não é a linha estar errada — ela está certa, dado o tipo. O ponto é que a *única*
exceção ao "config always binds" é justamente o campo que não deveria estar na config. O
tipo obrigou o motor a abrir exceção contra a própria regra.

### 2.2 A GUI já votou, e manteve uma cópia-sombra

`studio/models.py:67-74`:

```python
@dataclass
class PolicyEntry:
    """A named, built `CreditPolicy` plus its mirrored flat stress factor."""
    name: str
    policy: CreditPolicy
    flat_stress_factor: float | None = None
```

O Studio guarda o fator de estresse **fora** da política, ao lado dela, e a própria docstring
chama de espelho (*mirrored*). Ninguém decidiu isso por arquitetura: a interface precisou de
"a mesma política, com o estresse variando" e o tipo não oferecia. A cópia-sombra é o
sintoma de uma dimensão que existe no domínio e não existe no modelo.

### 2.3 Múltiplos cenários colapsam em `max`, com aviso

`simulation.py:583` e `:659`: `final_probs = prob_matrix.max(axis=1)`. Dois cenários
declarados não produzem duas leituras — produzem uma linha de PD pior-caso por cliente. Há
`warnings.warn` avisando (`:572-577`, `:648-653`), o que confirma que a semântica é
conhecida e indesejada, não um descuido.

Uma decisão de modelagem (agregação pior-caso) está embutida onde deveria haver uma
dimensão de resultado.

### 2.4 Colisão semântica silenciosa entre dois campos não relacionados

`simulation.py:548`, `:562`, `:637`, `:682`: quando `estimated_default_col` está presente,
o estresse é **ignorado**. Há warning nos dois caminhos (`:563-568`, `:638-643`), e ADR 0010
já legislou a semântica futura. Mas a colisão em si só existe porque um campo de *schema*
(que coluna traz a marcação) e um campo de *premissa* (quanto agravar) moram no mesmo
objeto e disputam o mesmo caminho de código.

### A pergunta que abre

Em arquiteturas que separam "especificação" de "condições de avaliação", **o que exatamente
fica de cada lado** quando a fronteira não é óbvia? Calibração é premissa (é uma hipótese de
transporte) ou é parte do schema (é uma coluna e uns bins)? E quando o mesmo estudo tem N
condições, a saída é uma linha por condição, ou existe agregação legítima — e quem declara
qual?

---

## 3. Imutabilidade de fachada

### 3.1 `frozen=True` com `deepcopy` por baixo

`policy.py:90-97`:

```python
def _replace(self, **kwargs) -> CreditPolicy:
    import copy, dataclasses
    clone = copy.deepcopy(self)          # "Deep copy the current policy to isolate state"
    return dataclasses.replace(clone, **kwargs)
```

Valor imutável de verdade nunca precisa de `deepcopy` — compartilhar é seguro por
definição. O `deepcopy` está lá porque os filhos **não** são imutáveis: as três classes de
estresse são classes comuns com atributos livres (`stress.py:50`, `:81`, `:109`) e
`GroupingRecipe` carrega estado ajustado. A casca é congelada; os órgãos não.

Custo escondido: `deepcopy` a cada movimento de builder. Numa varredura que constrói uma
política por ponto da grade (`sweep.py:142-188`), isso é uma cópia profunda por ponto — e
a `rating_recipe` ajustada vai junto.

### 3.2 O tipo declarado mente

`policy.py:36-59`, `__post_init__` usa `object.__setattr__` (a saída de emergência para
escrever em dataclass congelada) para **coagir** o que veio:

```python
if isinstance(self.score_cols, str):
    score_tuple = (self.score_cols,)
else:
    try: score_tuple = tuple(self.score_cols)
    except TypeError: score_tuple = (str(self.score_cols),)
```

A anotação diz `tuple[str, ...]`. Na prática aceita `str`, qualquer iterável, e — no
`except` — qualquer escalar, virando `("3.7",)`. O mesmo padrão em `calibration_bins:55-59`,
onde o `except TypeError: pass` deixa passar valor não coagido.

Nenhum desses caminhos avisa. Um `score_cols=3.7` por engano vira uma coluna chamada
`"3.7"`, e a falha aparece depois, em `validate()`, como "coluna ausente".

### 3.3 Round-trip quebrado por construção

`stress.py:123-127`, `CustomStress.to_dict()` devolve `{"type": "custom", "fn": str(self.fn)}`
— e `from_dict` (`stress.py:44-45`) levanta erro para `type == "custom"`, de propósito.

O objeto que a documentação chama de portável tem um membro que **não** faz round-trip, por
desenho. `FilterStage` com callable resolve o mesmo problema de outro jeito
(`stages.py:11-27`, registro global `register_callable`) — duas soluções incompatíveis para
a mesma classe de problema, dentro do mesmo pacote.

### 3.4 Rigor desigual na desserialização

`policy.py:239-253`: `applicant_id_col`, `score_cols`, `current_approval_col` e
`actual_default_col` são lidos com `d[...]` (levanta se faltar); todo o resto com `d.get(...)`
(devolve `None` em silêncio). Não há critério visível para a divisão — `current_hired_col`,
que hoje decide o peso do contrato do keep-in (ADR 0011), está do lado silencioso.

### 3.5 Default em forma de bug

`stress.py:63`: `if self.factor_col and self.factor_col in df.columns:`. Errar o nome da
coluna não levanta — cai no `else` e usa o fator escalar. Mesma chamada, semântica diferente,
sem ruído.

### A pergunta que abre

Qual é a garantia de round-trip que outras arquiteturas assumem: *todo* valor serializa, ou
existe uma classe declarada de membros não-serializáveis que **recusa alto**? Como tratam
extensão por callable sem quebrar portabilidade? E coerção de tipo na fronteira — coagir em
silêncio, recusar, ou aceitar só o tipo declarado?

---

## 4. Reconstrução manual perde campo — bug medido

`sweep.py:169-186`, caminho de varredura de `base_rate`:

```python
for i, stage in enumerate(stages_list):
    if isinstance(stage, RateStage) and stage.name in base_rate_values:
        stages_list[i] = RateStage(
            name=stage.name,
            base_rate=base_rate_values[stage.name],
            variable=stage.variable,
            calibrate=stage.calibrate,
        )
```

`RateStage.__init__` (`stages.py:286-294`) tem seis parâmetros. A reconstrução passa quatro.
`observed_col` e `calibrate_by` caem para os defaults (`None` e `"score"`).

**Consequência precisa.** Uma política cujo `RateStage` lê a contratação observada
(`observed_col`, o caminho que #68 introduziu e que `stages.py:370-427` implementa) e que
seja varrida por `base_rate` vira, em cada ponto da grade, um estágio de taxa escalar. O
keep-in deixa de receber seu valor observado (`stages.py:448-451`) e passa a receber
`1.0` — o bypass da família #94/#99/#103. A varredura devolve números de uma política que o
usuário não declarou.

Não confirmei se algum ticket cobre exatamente este caminho; #94 e #105 estão fechados e
tratam de outras faces do mesmo primitivo. Vale conferir antes de abrir.

**A causa de design, não o remendo.** Não existe movimento "trocar um campo deste estágio".
Quem precisa de uma variação reconstrói à mão, e reconstrução à mão esquece campo. O mesmo
padrão aparece em `_without_cutoff_entries` (`sweep.py:62-78`), que reconstrói `CutoffStage`
com três campos — hoje correto, porque `CutoffStage` tem exatamente três. **Cada campo novo
em qualquer `Stage` cria um lugar novo onde esquecer.** É uma classe de bug que cresce com o
tipo, não um erro pontual.

### A pergunta que abre

Como outras arquiteturas fazem derivação de um valor com um campo alterado, sem que cada
local de derivação precise conhecer todos os campos? E como se testa que uma reconstrução
é total?

---

## 5. Inferência silenciosa como classe inteira

Não são casos isolados; é um estilo recorrente. Levantei seis.

| # | Onde | O que infere | Ruído |
|---|---|---|---|
| 1 | `stages.py:158-186` | Score de calibração: explícito → **último** `CutoffStage` no df → **último** `score_cols` | nenhum |
| 2 | `stages.py:189-202` | Direção do score para calibração; sem cutoff que declare, assume `"gte"` | nenhum |
| 3 | `simulation.py:271`, `:697` | Coluna de segmento, tentando `["region", "loja", "safra"]` nesta ordem | nenhum |
| 4 | `simulation.py:713-718` | Calibração por rating; qualquer exceção cai para calibração por score | `except Exception: pass` |
| 5 | `simulation.py:63-66`, `:180-183` | Política reconstruída de `metadata`; falha vira "sem política" | `except Exception: pass` |
| 6 | `stress.py:63` | Coluna de fator ausente vira fator escalar | nenhum |

Os casos 1 e 3 mudam **o número do experimento**. O caso 1 com multi-score é o mais agudo:
trocar a ordem dos cutoffs na política muda a âncora de calibração, e portanto muda a PD
imputada dos swap-ins, sem nenhuma indicação. O caso 3 escolhe a coluna de segmentação por
um vocabulário fixo e meio pt-BR, embutido no motor.

Os casos 4 e 5 são `except Exception: pass` sobre um bloco inteiro — qualquer erro dentro do
`try` (inclusive erro de programação) vira "usa o caminho alternativo".

Contraste que mostra que o pacote *sabe* fazer diferente: `validate_direction`
(`stages.py:100-111`) recusa direção desconhecida com mensagem explícita, e a docstring diz
por quê (*"No silent fallback: the permissive else-means-lte branch this replaces inverted
every '>='-spelled cutoff"*). A lição foi aprendida em um lugar e não propagada.

### A pergunta que abre

Onde outras arquiteturas colocam a linha entre conveniência e silêncio? Existe padrão para
"default que precisa ser declarado" (o valor existe, mas usá-lo sem declarar avisa)? E
resolução em cascata — é aceitável se for *impressa* no resultado, ou é aceitável só quando
não existe?

---

## 6. Contrato de dados de saída não declarado

### 6.1 `new_approval` muda de tipo conforme o modo

`simulation.py:441-452`: `stochastic` produz `int` (0/1); `analytical` produz `float`
(probabilidade). Mesmo nome de coluna, dois tipos, decidido por um parâmetro de execução.
ADR 0010 já decidiu unificar em `float`; a medição aqui é só o estado atual.

### 6.2 A saída fala duas línguas

- `to_decision_dataframe` promete na docstring `'decisao'` e `'motivo'`
  (`simulation.py:169-170`).
- O código escreve `decision` e `reason` (`simulation.py:490-491`).
- `is_sim_col` (`simulation.py:192-208`) mantém uma lista de ~18 nomes com **os dois
  vocabulários** — `decisao`, `motivo`, `contratou`, `inadimplente`, `cenario` ao lado de
  `decision`, `reason`, `hired`, `defaulted`, `scenario` — mais `rating`, `Rating` e
  `risk_rating` (três grafias do mesmo papel), mais uma heurística por prefixo
  (`c.startswith("stage_")` com checagem de dígito).

Essa função existe para responder "esta coluna é do usuário ou minha?" — pergunta que só
precisa ser respondida por adivinhação porque nada declara o conjunto de colunas de saída.

### 6.3 Valores de apresentação dentro do motor

`simulation.py:296-300`: em modo estocástico, `hired` recebe as strings `"Yes"`/`"No"`; em
analítico, recebe número. Coluna sem valor ausente vira a string `"No"` (`:300`). Formatação
e cálculo no mesmo lugar, e o tipo da coluna depende do modo (mesma patologia do §6.1, em
outra coluna).

### 6.4 Contrato codificado como ausência

O denominador da inadimplência depende de `simulated_default` ser `NaN` ou não
(`sweep.py:118-120`: `outcome_known = ~np.isnan(pd_base)`). "Não contratado" e "contratado
sem desfecho observado" e "erro de imputação" chegam ao mesmo lugar como a mesma ausência.
O comentário do próprio arquivo (`sweep.py:113-117`) explica a distinção que o dado não
carrega.

### A pergunta que abre

Como se declara o esquema de saída de um pipeline que devolve um DataFrame, sem trocar o
DataFrame por outra coisa? Existe padrão para distinguir coluna-de-entrada de
coluna-derivada que não seja lista de nomes? E status ("não contratado" vs "sem desfecho")
— outras arquiteturas modelam como valor explícito ou aceitam a ausência como código?

---

## 7. O estágio recebe a política inteira

`stages.py:36`:

```python
def apply(self, df, method: str = "analytical", policy: Any | None = None) -> pd.Series:
```

Três observações medidas:

1. **`policy: Any`.** O tipo não é anotável sem fechar ciclo de import (`policy.py:9`
   importa `stages` no topo). O arquivo já tem `from __future__ import annotations`
   (`stages.py:1`), então `TYPE_CHECKING` resolveria a *anotação* — mas não a aresta.
2. **Dois dos três estágios concretos nunca leem `policy`.** `CutoffStage.apply`
   (`stages.py:128-147`) e `FilterStage.apply` (`:223-244`) recebem e ignoram.
3. **`method: str`, não Enum.** `_types.py` define `SimulationMethod(str, Enum)`, e
   `simulation.py:431` desembrulha na chamada (`method=method.value`), de modo que cada
   `apply` compara string. `CutoffStage` faz o mesmo com `direction == "gte"`
   (`stages.py:136`).

`RateStage` é o que de fato lê a política — e resolve a mesma máscara de keep-in **duas
vezes na mesma chamada**: em `_observed_probs` (`stages.py:388`) e de novo em `apply`
(`stages.py:445`).

Sinal correlato do ciclo: `stages.py` tem imports **no meio do arquivo** (`:95`
`from ._types import StageDirection`, `:205` `from .expressions import Expression`), além de
imports dentro de funções (`:326`, `:337`, `:376`, `:475`).

### A pergunta que abre

O que um "passo" precisa receber para executar — e como outras arquiteturas evitam que ele
receba o objeto que o contém? Quando um passo precisa de algo derivado do conjunto (uma
máscara, um bin), quem calcula e quando?

---

## 8. Um primitivo, dois donos

A pergunta "quem de fato contratou?" tem hoje duas respostas declaráveis:

- `CreditPolicy.current_hired_col` — campo de schema, lido pelo núcleo em
  `_apply_keep_in_hire_weight` (`simulation.py:346-391`).
- `RateStage.observed_col` — campo de estágio (`stages.py:319`), com sua própria calibração
  por bin (`stages.py:370-427`).

O motor precisa de uma função só para saber qual está valendo: `_has_observed_col_stage`
(`simulation.py:334-343`), cuja docstring nomeia a situação — *"the legacy take-up
declaration that predates `current_hired_col`"*. E o caminho não-declarado emite
`DeprecationWarning` mantendo o comportamento antigo (`simulation.py:382-391`), com o flip
para erro duro pendente (#106).

Não é dívida acidental: é o mesmo conceito modelado duas vezes, em camadas diferentes, com
um período de convivência declarado. O que interessa para a arquitetura é *como* dois donos
surgiram — um campo do contêiner e um campo da peça respondendo a mesma pergunta.

### A pergunta que abre

Quando um dado é simultaneamente "fato sobre a base" e "insumo de um passo", onde ele mora?
Existe critério que teria evitado a duplicação, ou o caminho é sempre convivência +
deprecação?

---

## 9. Calibração em dois endereços, com populações diferentes

`expressions.py:179-224` (`CalibratedExpression.calibrate_and_eval`) e o caminho de
imputação de PD em `simulation.py:682+` fazem a mesma mecânica: agrupar keep-ins por faixa
de score, tirar a média, mapear para os alvos. Ambos terminam no mesmo kernel puro
(`_kernels/calibrate_by_score_bins`), o que é o desenho certo.

O que sobra: as **populações** diferem, e a diferença está codificada no endereço, não no
argumento. `expressions.py:188` calibra sobre `current_approval_col == 1`;
`simulation.py` calibra sobre `scenario == KEEP_IN`. ADR 0010 documenta que a diferença é
legítima e não pode ser unificada (a expressão roda *antes* de `new_approval` existir).

Sendo legítima, ela é uma escolha de modelagem — e uma escolha de modelagem que o usuário
não vê, não escolhe e não encontra no resultado.

Some-se: `min_keep_ins = 5 if calibration_bins is not None else 50` aparece nos dois lados
(`simulation.py:728` e `stages.py:407`), com comentário admitindo o espelhamento
(*"Mirrors the swap-in PD imputation floor in simulation.py"*).

### A pergunta que abre

Quando a mesma operação roda legitimamente sobre populações diferentes em momentos
diferentes do pipeline, como se torna isso visível e escolhível sem duplicar o cálculo?

---

## 10. Serialização à mão, em toda parte

Medido no núcleo: **22** definições de `to_dict`/`from_dict` em 8 arquivos — `stages.py` (5),
`stress.py` (5), `grouping.py` (3), `screening.py` (3), `deployment.py` (2), `policy.py` (2),
`optimization.py` (1), `simulation.py` (1).

Cada uma é escrita à mão, com sua própria convenção de chave `"type"`, seu próprio rigor
(§3.4), e seu próprio tratamento de campo faltante. Cada uma é um lugar independente onde o
round-trip pode quebrar — e já quebrou em um (`CustomStress`, §3.3). `Expression` tem ainda
um par de funções livres (`serialize_expression`/`deserialize_expression`,
`expressions.py:239-282`), uma terceira convenção.

`CreditSimResults.to_dict` (`simulation.py:22-26`) devolve **só** `metadata`, descartando
`data` e `policy` — um `to_dict` que não é serialização do objeto, com o mesmo nome dos
outros 21.

### A pergunta que abre

Serialização à mão por tipo é o preço de tipos ricos, ou existe padrão (derivação, registro,
protocolo) que dá round-trip garantido sem gerar um lugar por tipo para errar?

---

## 11. Núcleo imperativo

### 11.1 Impressão dentro do núcleo

Cinco funções que calculam **e** imprimem: `performance.py:288` (`print_delta_table`),
`:458`, `:528`, `:572`, e `simulation.py:140` (`print_funnel_table`). Quatro estão
exportadas no `__all__` público. Quem quer os números sem o texto formatado precisa da
função irmã, quando existe.

### 11.2 Aleatoriedade global, sem semente — e o pacote sabe fazer diferente

`np.random.random(...)` chamado direto em quatro sítios: `simulation.py:604`, `:664`;
`stages.py:458`, `:469`. `run_simulation` (`simulation.py:394-399`) não aceita `seed` nem
`Generator`. Duas execuções idênticas em modo `stochastic` produzem números diferentes, e
nada no resultado registra qual sorteio ocorreu.

O contraste é interno e é o achado mais eloquente: `sample_data.py` faz **certo** —
`rng = np.random.default_rng(seed)` (`:212`, `:263`), `seed` como parâmetro documentado
(`:206`, `:258`), e o `Generator` passado explicitamente a cada função auxiliar (`:60`,
`:89`, `:117`, `:149`, `:160`). O pacote tem a prática correta implementada e não a aplicou
onde o número sai para o cliente.

### A pergunta que abre

Onde mora a semente quando a aleatoriedade acontece dentro de peças aninhadas (um estágio,
dentro de um ponto da grade, dentro de uma varredura)? E qual a fronteira entre calcular e
apresentar, num pacote cujo usuário principal trabalha em notebook?

---

## 12. A camada de varredura

O backend já é único (`sweep.run_sweep`), e `optimize_cutoffs`/`TradeoffAnalyzer` são
camadas finas — isso é resultado do #71 e está bem. O que resta é forma de superfície.

### 12.1 Grade exaustiva

`np.linspace` por coluna (`optimization.py:177`) × `itertools.product` de todas as dimensões
(`sweep.py:276`). Sem poda, sem busca. O caminho rápido (`sweep.py:280-309`) barateia cada
ponto — uma simulação base e máscaras vetorizadas — mas continua avaliando `k^N`.

### 12.2 "Melhor único" com peso mágico, ao lado da fronteira que ele mesmo calcula

`optimization.py:194`: `all_results["tradeoff_score"] = app - 5.0 * dr`. O `5.0` não é
parâmetro, não é documentado e não é justificado. É a taxa de câmbio implícita entre
aprovação e inadimplência — a decisão de negócio central do pacote — como constante literal.

Ele é usado quando nenhuma combinação satisfaz as restrições (`:197-201`); quando alguma
satisfaz, o critério muda para "maior aprovação" via `.iloc[0]`. Dois critérios diferentes
conforme a viabilidade, ambos devolvendo um único vencedor — enquanto a fronteira de Pareto
completa é calculada na linha seguinte (`:212`) e devolvida no mesmo objeto.

### 12.3 Despacho por substring

`OptimizationResult.find_equivalent` (`optimization.py:50-56`) escolhe a coluna assim:

```python
col_name = "overall_approval_rate" if "approval" in target_metric else "overall_default_rate"
```

Nome de métrica como string, resolvido por `in`. Um `target_metric="approval_take_up"`
resolveria para aprovação por acidente de substring.

### 12.4 Alvo sem tipo

`optimize_cutoffs` tem 10 parâmetros (`optimization.py:79-90`), dos quais quatro são o
"alvo" espalhado em kwargs: `target_default_rate`, `min_approval_rate`, `cutoff_steps`,
`percentiles`. Não há objeto que represente "o que eu quero".

### A pergunta que abre

Como outras arquiteturas representam "o alvo" de uma otimização — objeto, protocolo,
função? Devolver um vencedor único é responsabilidade da biblioteca ou de quem chama? E que
estratégias de busca essas arquiteturas oferecem quando a grade não cabe?

---

## 13. Papéis de coluna em três grafias

1. **Motor:** os sete campos de `CreditPolicy` (§1).
2. **Studio:** `ColumnRoles` (`studio/models.py:17-30`) — repete os sete e **acrescenta
   três que o motor não conhece**: `segment_col`, `oot_date`, `vigente_score`. O último
   ainda é meio pt-BR.
3. **Detecção:** as heurísticas de `studio/detection.py` (não auditei em profundidade).

`segment_col` é o caso interessante: o Studio tem o papel declarado, e o motor, que precisa
dele, adivinha por `["region", "loja", "safra"]` (§5, caso 3). O papel existe do lado errado
da fronteira.

`ProjectBundle` (`studio/models.py:77-90`) tem `created_at` e **nenhum campo de versão** —
não há como detectar que um arquivo salvo é antigo. Já coberto por S3/#77.

Escala das camadas, para dimensionar: `studio/analyses.py` tem 68 funções de topo em 1.397
linhas; `gui/session.py` tem 19; o `__all__` do pacote exporta 53 nomes.

### A pergunta que abre

Quando existe uma casca (GUI) sobre uma biblioteca, quantas vezes o mesmo vocabulário pode
ser escrito antes de divergir? Que padrões impedem a terceira grafia?

---

## 14. Sinais menores, medidos

- **`Expression.__eq__` devolve `Expression`, não `bool`** (`expressions.py:31-32`). É
  necessário para o DSL (`col("x") == 1`), mas quebra o contrato de igualdade do Python:
  definir `__eq__` sem `__hash__` torna a classe **não-hasheável**, então nenhuma
  `Expression` entra em `set` ou vira chave de `dict`, e comparação de identidade em
  coleções não funciona. Custo de DSL raramente explicitado.
- **Registro global mutável** (`stages.py:11`, `_CALLABLE_REGISTRY`). Estado de módulo,
  compartilhado por processo; interage com o caminho paralelo de `sweep`
  (`_parallel.parallel_map`), que eu não auditei quanto a herança desse registro em
  `ProcessPoolExecutor`.
- **Imports no meio do arquivo e dentro de funções** (`stages.py:95`, `:205`, `:326`,
  `:337`, `:376`, `:475`; `simulation.py:44`, `:60`, `:160`; `policy.py:92`, `:167`,
  `:294`). Sintoma dos ciclos, e ao mesmo tempo o que os mantém invisíveis.
- **`CreditSimResults.policy` é `| None`** (`simulation.py:20`), embora `run_simulation`
  sempre preencha (`:502`); os dois consumidores mantêm caminho de fallback reconstruindo a
  política de `metadata` (`:40-52`, `:175-186`). A política viaja duas vezes no mesmo objeto.
- **`describe()` imprime `Estimated default:`** (`policy.py:255+`) para um campo cujo
  conceito ADR 0010 já decidiu matar.

---

## 15. O que está bom — e por que registrar isso importa

Um levantamento só de defeitos distorce a decisão seguinte: dá a impressão de que tudo
precisa ser refeito, quando o custo real está concentrado.

- **Kernels puros** (`_kernels/`): funções sem `policy`, testáveis, com a assinatura certa.
  É o padrão que o resto do núcleo não segue.
- **`sweep` unificado** (#71): um motor, duas camadas finas. A duplicação mecânica acabou.
- **`validate_direction`** (`stages.py:100-111`): recusa alta com o motivo documentado.
- **`sample_data.py`**: `Generator` explícito, semente parametrizada, sem estado global.
- **A disciplina de ADR** (0001–0011): as decisões passadas estão escritas com medição e
  motivo, o que tornou este levantamento possível em uma sessão.

Os quatro primeiros são a evidência mais útil deste documento: **o pacote já contém a
prática correta em pelo menos um lugar para quatro das patologias listadas.** O problema não
é falta de conhecimento; é falta de fronteira que obrigue a prática a valer em todo lugar.

---

## 16. As perguntas, reunidas

Consolidadas para consumo direto pela pesquisa. Nenhuma tem resposta aqui.

1. Que critério separa tipos quando um objeto de configuração acumula papéis? (§1)
2. Declarado vs ajustado: dois tipos, um tipo com dois estados, ou tipo parametrizado? (§1.1)
3. O que é "especificação" e o que é "condição de avaliação", quando a fronteira não é
   óbvia? (§2)
4. N condições produzem N resultados, ou existe agregação legítima — e quem declara? (§2.3)
5. Qual garantia de round-trip é assumida, e como se trata extensão por callable? (§3)
6. Coerção na fronteira: coagir em silêncio, recusar, ou aceitar só o declarado? (§3.2)
7. Como derivar um valor com um campo alterado sem que cada local conheça todos os
   campos? (§4)
8. Onde fica a linha entre conveniência e silêncio; existe "default que precisa ser
   declarado"? (§5)
9. Como declarar o esquema de saída de um pipeline que devolve DataFrame? (§6)
10. Status ausente: valor explícito ou ausência como código? (§6.4)
11. O que um passo precisa receber para executar, e quem calcula o que é derivado do
    conjunto? (§7)
12. Onde mora um dado que é ao mesmo tempo fato da base e insumo de um passo? (§8)
13. Mesma operação, populações diferentes: como tornar visível e escolhível? (§9)
14. Round-trip garantido sem um lugar por tipo para errar? (§10)
15. Onde mora a semente quando a aleatoriedade é aninhada? (§11.2)
16. Fronteira entre calcular e apresentar, para um usuário de notebook? (§11.1)
17. Como se representa "o alvo" de uma otimização? (§12.4)
18. Vencedor único é responsabilidade da biblioteca ou de quem chama? (§12.2)
19. Que estratégias de busca existem quando a grade não cabe? (§12.1)
20. Como impedir a terceira grafia do mesmo vocabulário entre biblioteca e casca? (§13)

---

## 17. Limites deste levantamento

Declarados para que ninguém trate ausência como aprovação.

- **Não auditados:** `screening.py` (28 KB), `grouping.py`, `visualization.py`,
  `deployment.py`, `performance.py` (lido só para contar `print_*`), `studio/detection.py`,
  `studio/policy_builder.py`, `studio/analyses.py` (só contagem), toda a suíte de testes.
- **Não medido:** desempenho. Todas as afirmações de custo aqui são de *manutenção* e
  *correção*, não de tempo de execução. O `deepcopy` por ponto de grade (§3.1) é a única
  suspeita de custo de execução, e não a medi.
- **Não verificado contra o backlog:** este documento foi escrito a partir do código, não do
  issue tracker. Vários itens têm ticket (as referências ADR/#N que aparecem foram anotadas
  quando o próprio código as cita). O cruzamento completo com #113–#130 é trabalho de quem
  consumir, e é deliberado: cruzar antes teria enviesado o que eu fui olhar.
- **Um item pede verificação factual antes de virar ticket:** o §4 (`sweep.py:174-179`).
  Medi a assinatura e a chamada; não escrevi teste que o reproduza.
