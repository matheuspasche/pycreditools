# Contrato de dados de saída — levantamento de referências

> **Insumo de decisão, não decisão.** Este documento levanta fatos, formas e preços.
> Nenhum veredito "adotar / adaptar / descartar" é tomado aqui — esses são de #131 (contrato
> de saída), #132 (silêncio) e #127 (núcleo funcional). Se você achar uma recomendação neste
> texto, é um defeito: reporte no #135.

Resolve a **fatia "contrato de saída"** da Lente B (#135), que graduou de #134, que graduou
de #113. Cobre três perguntas da §16 do `architecture-critique.md`: **9** (como declarar o
esquema de saída de um pipeline que devolve DataFrame), **20** (como impedir a terceira
grafia do mesmo vocabulário) e **10** (status ausente: valor explícito ou ausência como
código) — esta última já bastante comida por #116, então entra pelo resíduo medido.

A pergunta **6** (coerção na fronteira) foi deixada para a fatia *inferência silenciosa*:
#118, #121 e #120 já fixaram "erro duro no bind" para os casos concretos, e o que sobra é a
regra transversal, que é matéria do #132.

## Como ler

Cada célula tem **N formas**. Para cada uma: **fato**, **porta para Python/pandas?**, e
**preço**. As formas convivem porque a decisão é de outro card.

**Ressalva de método herdada de #134:** onde a medição mostra que as formas **não empatam**,
este documento diz isso e mostra o número. Apontar assimetria medida não é escolher.

**Restrição de desenho declarada pelo dono (2026-08-15), que atravessa todo o documento:**
o pacote **já tem** uma forma de declaração, e ela **perdeu** — números na §1. Toda forma
custeada aqui tem que responder *o que a impede de ter o mesmo destino do `_types.py`*. Uma
forma que não responde isso não está custeada, está descrita.

---

## 1. O estado medido, antes das formas

Medições sobre `release/v0.6`, 2026-08-15.

### 1.1 A declaração já existe e foi derrotada

`src/pycreditools/_types.py` tem 34 linhas e contém cinco declarações: `SimulationMethod`,
`ClusteringMethod`, `Quadrant`, `StageDirection` (Enums de `str`) e `PolicySummary`
(`TypedDict` com seis campos — `scenario`, `applicants`, `approved`, `hired`, `bad_rate`,
mais a docstring "Schema for simulation summary outputs").

| declaração | usos em `src/pycreditools` | literal cru equivalente |
|---|---|---|
| `SimulationMethod` | 13 | `"analytical"` / `"stochastic"` = **40** |
| `StageDirection` | 5 | `"gte"` / `"lte"` = **53** |
| `Quadrant` | 20 | — |
| `ClusteringMethod` | 3 | — |
| `PolicySummary` | 3 | — |

A §16 Q20 do levantamento formula isso como "Enum disponível trocado por string". A medida é
mais dura, e a diferença importa para o desenho: o Enum não foi *esquecido antes de existir*
— ele existe, é importável, e **perde 40:13 e 53:5** no mesmo código-base que o define.

Isso reclassifica Q9. A pergunta deixa de ser "que forma de declaração adotar" e passa a ser
composta:

1. que forma de declaração existe, e
2. **o que faz uma declaração ser obrigatória de passar em vez de opcional de usar.**

Nenhuma referência custeada abaixo é neutra quanto a (2), e é aí que elas se separam de
verdade.

### 1.2 A terceira grafia não é hipótese — as três estão vivas

Emissões (`df["x"] = …`) no pacote:

| grafia do mesmo papel | emissões |
|---|---|
| `rating` | 4 |
| `Rating` | 7 |
| `risk_rating` | 8 |

Nenhuma vence. A §13 do levantamento pergunta "quantas vezes o mesmo vocabulário pode ser
escrito antes de divergir" — a resposta medida neste pacote é **três, e já divergiu**, sem
que exista uma casca GUI envolvida nessas três (a divergência GUI×motor da §13 é adicional).

### 1.3 O guarda defende uma língua morta

`is_sim_col` (`simulation.py:192-208`) responde "esta coluna é do usuário ou minha?" por
adivinhação: lista de 18 nomes + heurística de prefixo `stage_` com checagem de dígito.

Contando emissões de cada um dos 18 no pacote inteiro, **seis nunca são emitidos em lugar
nenhum**: `quadrant`, `decisao`, `motivo`, `contratou`, `inadimplente`, `cenario`.

Cinco desses seis são exatamente o vocabulário pt-BR que a docstring de
`to_decision_dataframe` promete (`simulation.py:169-170`) e que o código não escreve
(`:490-491` escreve `decision`/`reason`). O guarda **preserva a mentira da docstring**: gasta
seis entradas defendendo colunas que nenhum caminho de código produz.

Isso é um fato sobre o custo do não-declarado que nenhuma referência precisa provar: quando
o conjunto de saída não é declarado em lugar nenhum, a lista que o aproxima só cresce — não
há nada que force uma entrada a sair quando o nome morre.

### 1.4 Amplificação de mudança: o piso que qualquer forma tem que bater

Nome de coluna de saída como **literal de string**:

| onde | ocorrências | arquivos |
|---|---|---|
| `src/pycreditools` | **261** | 11 |
| `tests` | **222** | — |

**483 sítios.** É o preço de renomear uma coluna hoje, e é o número contra o qual se mede
qualquer forma que prometa "um lugar para o nome". Nenhuma forma abaixo reduz isso a 1 sem
custo próprio; as diferenças são de *onde* o custo cai.

### 1.5 Resíduo de Q10, já decidido mas ainda instalado

#116 matou o proxy `notna()` — "contratou?" é o vetor `contract`, "existe marcação?" é
cobertura reportada como número. O padrão `outcome_known = …notna()` continua em **9 sítios**
(`performance.py:90,165,365,485`, `sweep.py:90,118`, mais os de `simulation.py`).

E `hired` recebe as strings `"Yes"`/`"No"` em `simulation.py:298-300`, com o `:300` dando
`"No"` para coluna sem valor ausente — apresentação dentro do motor, dtype dependente do
modo (a mesma patologia da §6.1 em outra coluna).

Nenhum dos dois é pergunta aberta de arquitetura. São **insumo de execução** para o card de
roadmap (#124) e para a revisão de malha de testes: o número 9 é quantos sítios a decisão do
#116 obriga a reler.

---

## 2. Q9 — declarar o esquema de um pipeline que devolve DataFrame

Quatro formas, todas praticadas, todas portáveis para Python. O que as separa é a §1.1: a
que hora a declaração é consultada.

### Forma A — declaração passiva: `TypedDict` / dataclass de nomes

**Fato.** É o que o pacote já faz com `PolicySummary`. Um tipo lista os campos; o
type-checker vê; o runtime não.

**Porta?** Sim, é stdlib, já está em `_types.py`, e casa com a decisão de #120 (frozen
dataclass, stdlib basta, sem pydantic).

**Preço, medido, não estimado.** Esta é a forma que perdeu 3 usos contra 483 literais. O
mecanismo da derrota é preciso e vale nomear porque atinge qualquer variante desta forma:
`TypedDict` tipa um `dict`, não um `DataFrame`. `df["rating"]` não é um acesso que o
type-checker consiga ligar a um campo declarado — pandas expõe `__getitem__` genérico. Logo
a declaração e o uso **nunca se encontram**: a declaração é um comentário que o mypy
verifica contra nada.

**A resposta à restrição do dono:** esta forma **não tem** resposta. É a forma cujo destino
já foi medido neste repo.

### Forma B — declaração executável: validação de esquema (`pandera`)

**Fato.** Um esquema declara colunas, dtypes e checagens; um decorador
(`@pa.check_types` / `@pa.check_output`) valida o DataFrame **na fronteira da função**, em
runtime, e levanta erro com a lista de desvios. O esquema é um objeto: composível,
herdável, e serializável para YAML.

**Porta?** Sim — é biblioteca de pandas, feita para exatamente esta pergunta. Custo de
dependência: o repo hoje tem **zero** `pandera` e **zero** `pydantic`; seria a primeira
dependência de validação.

**Preço.** Três, e o terceiro é o que interessa:

1. Runtime, não grátis: valida percorrendo o DataFrame. Custo proporcional ao tamanho, num
   pacote cujos verbos de grade rodam a simulação centenas de vezes (#122: 200 simulações
   por grade). Validar a cada ponto da grade é o caso ruim; validar só na fronteira pública
   é o caso bom — e a diferença é decisão de onde fica a fronteira, ou seja, é #131 e #127,
   não é preço fixo da forma.
2. Dependência nova, contra a inclinação stdlib do #120.
3. **Ela responde a restrição do dono, e é a única forma passiva-para-ativa da lista.** A
   declaração para de ser opcional porque o código **quebra** quando o DataFrame diverge
   dela. O `_types.py` perdeu porque ignorá-lo não custava nada; um esquema validado custa
   um erro. O preço dessa resposta é simétrico e deve ser dito: torna-se possível quebrar em
   produção por uma divergência que antes passava — o que é o ponto, e também o risco.

### Forma C — o nome não é string em lugar nenhum: constante / Enum de coluna

**Fato.** Cada nome de coluna vira um símbolo (`Col.RATING`), e `df[Col.RATING]` funciona
porque `str`-Enum é `str`. É o mesmo mecanismo dos Enums que o `_types.py` já tem.

**Porta?** Sim, trivialmente, e sem dependência.

**Preço.** É o caso do `_types.py` **de novo**, com o mesmo mecanismo de derrota já medido
(40:13, 53:5): nada impede `df["rating"]`, então a forma depende inteiramente de disciplina
ou de lint. A diferença — e é uma diferença real, não simetria fabricada — é que aqui existe
um mecanismo de obrigatoriedade disponível que não existe na Forma A: **uma regra de lint
que proíbe literal de string em posição de índice de DataFrame** transforma disciplina em
erro de CI. Isso é o que faltou ao `_types.py`, e é barato de custear no card. Sem essa
regra, esta forma e a Forma A têm o mesmo destino medido.

**Fato colateral que a §1.2 dá de graça:** com três grafias vivas, a Forma C obriga a
escolher uma na hora de definir o símbolo. A unificação de vocabulário deixa de ser um card
separado e vira efeito colateral da declaração — o que aproxima Q9 e Q20 de serem a mesma
pergunta.

### Forma D — a saída não é DataFrame: tipo de resultado com acessores

**Fato.** O pipeline devolve um objeto (o pacote já tem `CreditSimResults`), e o DataFrame
sai por um método que constrói a tabela sob demanda — `to_decision_dataframe` é exatamente
isso. O esquema fica declarado como a assinatura dos métodos, não como uma lista de nomes.

**Porta?** Já está portado, parcialmente: o tipo existe e é o que os verbos devolvem.

**Preço.** Este é o único ponto onde o levantamento e a decisão já gravada se contradizem, e
vale registrar sem resolver: a §16 Q9 formula a pergunta como *"sem trocar o DataFrame por
outra coisa"* — isto é, exclui a Forma D por enunciado. Mas #125 decidiu **coluna `study` em
toda tabela de verbo**, e #116 decidiu **três vetores de saída nomeados**, ambas decisões que
tratam a tabela como a interface. A restrição do enunciado da §16 nunca foi ratificada por
um card. **Se ela cai, esta forma volta à mesa; se vale, a Forma D está fora antes de ser
pesada.** Isso é uma pergunta para o #131, não para este documento.

Preço próprio, independente disso: o acessor não impede que o DataFrame que ele devolve
tenha colunas não declaradas — ele muda *quem* declara, não *se* alguém declara. As Formas
B e C compõem com a D; não são alternativas a ela.

### Onde as formas não empatam

A tabela abaixo é a assimetria medida, não um ranking.

| forma | tem resposta à derrota do `_types.py`? | mecanismo |
|---|---|---|
| A — `TypedDict` | **não** | destino já medido: 3 usos |
| B — esquema validado | **sim** | divergir levanta erro |
| C — Enum de coluna | **só com lint** | literal em índice vira erro de CI |
| D — tipo de resultado | **ortogonal** | move o declarante, não a obrigatoriedade |

---

## 3. Q20 — impedir a terceira grafia

A §13 pergunta com a casca GUI em mente. A §1.2 mostra que a divergência já acontece **sem**
a GUI, o que separa a pergunta em duas que têm respostas diferentes.

### 3.1 Divergência dentro do mesmo módulo — três grafias de `rating`

Aqui não existe fronteira a atravessar: é o mesmo pacote escrevendo o mesmo papel de três
jeitos. Nenhuma referência de arquitetura é necessária para diagnosticar, e a Forma C da §2 é
uma resposta direta e completa: com um símbolo, a terceira grafia é inexprimível.

O preço é o da §1.4: a unificação toca 483 sítios contando testes, e a decisão de qual das
três grafias sobrevive é do #131.

### 3.2 Divergência através de uma fronteira — motor × Studio

`ColumnRoles` (`studio/models.py:17-30`) repete os sete campos do motor e acrescenta três que
o motor não conhece (`segment_col`, `oot_date`, `vigente_score`). Duas formas praticadas:

**Forma A — uma fonte, a casca importa.** A casca não redeclara: importa o tipo do núcleo e o
estende por composição. Impede a segunda grafia por construção.
*Preço:* acopla a casca à versão do núcleo, e obriga o núcleo a hospedar campos que só a
casca usa — ou a casca a carregar os seus **fora** do tipo importado, o que reintroduz duas
listas, só que agora com fronteira declarada em vez de acidental.

**Forma B — geração.** A casca deriva sua declaração do núcleo por código, em build. Uma
fonte, duas materializações, divergência detectável por diff.
*Preço:* passo de build num pacote que hoje não tem nenhum; e o repo já rejeitou CI para o
hook de nbstripout (#115, risco aceito, só hook local) — precedente que sugere que este
preço é caro aqui, embora #115 não seja ruling sobre build em geral.

**Fato que muda a pergunta:** #118 decidiu que `segment_col` fica **fora** do schema e que
`ColumnRoles` **morre**, com `studio/detection.py` virando sugestão de formulário. O caso
concreto da §13 já foi dissolvido por decisão. O que sobra para o #131 é se existe **regra**
que impeça a próxima casca de refazer o mesmo — e essa pergunta não tem caso vivo para
medir. Registrada como tal.

---

## 4. Q10 — status ausente

Duas formas, e a decisão já tomada escolheu uma sem citar a pergunta.

**Forma A — ausência como código.** `NaN` carrega "não contratado", "contratado sem desfecho"
e "erro de imputação" no mesmo valor. É o estado atual (`sweep.py:113-120`, onde o próprio
comentário explica a distinção que o dado não carrega).

**Forma B — valor explícito.** Cada status é um valor nomeado; a ausência deixa de ser
polissêmica.

**Preço em pandas, que é onde a pergunta é específica e não genérica:** a Forma B custa dtype.
Uma coluna de status com valores nomeados é `object` a menos que seja `category` — e #125 já
mediu esse eixo neste pacote: **140 MB `object` contra 5 MB `category`** em 5 MM de linhas.
Logo a Forma B é viável ao preço de `category` obrigatória, e ruinosa sem ela. O número já
existe; o card não precisa remedi-lo.

#116 escolheu a Forma B em substância — `contract` é vetor próprio, cobertura é número — sem
que a forma tivesse sido custeada. O resíduo medido (§1.5: 9 sítios de `notna()`) é o
tamanho da dívida que essa escolha abriu, e é execução, não decisão.

---

## 5. O que este documento deixa aberto para o #131

1. **A restrição do enunciado da §16 Q9** ("sem trocar o DataFrame por outra coisa") nunca
   foi ratificada por card, e #125/#116 legislaram sobre a tabela como interface. Se a
   restrição cai, a Forma D da §2 volta à mesa.
2. **Qual das três grafias de `rating` sobrevive**, e se a unificação é feita com símbolo
   (Forma C) ou só por convenção.
3. **Se a declaração é obrigatória de passar ou opcional de usar** — a pergunta que a §1.1
   levantou, e a única em que as formas não empatam.
4. **Se existe regra contra a próxima casca redeclarar vocabulário**, agora que o caso
   concreto (`ColumnRoles`) morreu por decisão do #118 e não sobrou caso vivo para medir.

## 6. O que sobra da Lente B depois desta fatia

- **Núcleo funcional** (§16 15, 16) — #127.
- **Busca / CART** (§16 19) — #123, #142.
- **Round-trip e `Expression`** (§16 5, 14) — **fora de escopo**: resolvidos por decisão em
  #120 (callable inexprimível, congelamento fundo, stdlib basta) sem esperar a pesquisa.
  Registrado no #135 em 2026-08-15.
