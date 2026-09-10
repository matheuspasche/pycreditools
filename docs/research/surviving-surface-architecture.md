# A superfície que sobrevive à contração — levantamento de arquitetura

> **Insumo, sem veredito.** Este arquivo mede; quem decide são as issues de decisão listadas no fim.
> **Data:** 2026-09-10, na `release/v0.6` em `a184e7e`, com o ticket 4 (#161) aberto no PR #176.
> **Lente:** módulos profundos — *module*, *interface*, *implementation*, *depth*, *seam*, *adapter*, *leverage*, *locality*.

## Escopo, e por que ele exclui metade da árvore

O ticket 16 (#172) deleta inteiros `policy.py`, `stages.py`, `simulation.py`, `sweep.py`, `optimization.py`, `analysis.py`, `stress.py` e `performance.py`. **Aprofundar módulo que vai ser deletado é trabalho jogado fora** — é o mesmo argumento com que o #159 escopou os hooks do `pre-commit` só à superfície nova.

Então o levantamento olha só o que atravessa a contração:

| módulo | destino |
|---|---|
| `src/pycreditools/engine/` | é a superfície nova; nasce no #159 e ganha os quatro tipos no #161 |
| `src/pycreditools/expressions.py` | compartilhado, **somente leitura** — com uma ressalva medida abaixo |
| `src/pycreditools/_kernels/` | compartilhado |
| `src/pycreditools/sample_data.py` | compartilhado |
| `suggest_hard_filters` (`screening.py`) | a §4.9 promete re-exportá-lo intacto — e não dá |
| `validation/` | reescrito no ticket 15 (#171), não deletado |

---

## O que foi medido

### `expressions.py` — 282 linhas

Interface: `Expression` com **14 dunders de operador** mais `eval` e `get_columns`, três nós (`ColumnExpr:75`, `BinaryExpr:93`, `UnaryExpr:144`), `CalibratedExpression:164`, `col:230`, e o par `serialize_expression:239` / `deserialize_expression:257`. A interface é quase o arquivo inteiro.

- `BinaryExpr.eval` (`:101-130`) é um `if/elif` de **12 ramos** refazendo o que os operadores do Python já fazem.
- `__eq__` (`:31`) é sobrecarregado para **construir um nó**, não para comparar. Consequência: instâncias não são comparáveis nem hasheáveis em termos normais, e o chamador tem que saber disso. **É a razão pela qual o #161 nasceu com uma árvore congelada própria em `engine/_nodes.py`.**
- `CalibratedExpression.calibrate_and_eval` (`:179-224`) recebe `policy: Any` e lê quatro campos dele (`:183`, `:205`, `:210`) — a origem do ciclo de import.
- Os dois serializadores são uma escada de `isinstance` sobre quatro classes: nó novo significa editar três lugares.

**Censo de sobrevivência.** `CalibratedExpression` é construída em `expressions.py:72`, `stages.py:329`, `stages.py:426` e `deserialize_expression:280` — os três primeiros morrem no 16, e depois disso **nenhum código sobrevivente a constrói**: o único consumidor vivo é `engine/_nodes.py:from_builder`, que existe para **recusá-la**. `serialize_expression`/`deserialize_expression` têm como chamadores não-teste `stages.py:74, :83, :249, :478` e `deployment.py:88, :239` — todos mortos no 16. O `engine/` não usa nenhum dos dois; `engine/_value.py` tem o mecanismo próprio dirigido pela assinatura. **Ficam dois mecanismos de serialização para a mesma árvore.**

Cobertura: `tests/test_expressions.py` tem **4 funções** (uma delas testa `sample_data`, não expressão); nenhum teste faz round-trip do par serializador direto. `tests/engine/test_engine_ast.py` (#161) cobre a conversão builder → nó congelado com 10 testes.

### `_kernels/` — 621 linhas, 5 nomes públicos

| kernel | linha | forma |
|---|---|---|
| `calibrate_by_score_bins` | `calibration.py:32` | 6 params, 4 deles Series |
| `diagnose_score_bin_calibration` | `calibration.py:124` | 7 params, **os 5 primeiros idênticos aos da outra** |
| `iv_cluster` | `iv.py:6` | 8 params, numpy cru |
| `ward_cluster` | `ward.py:6` | 8 params, **6 deles iguais aos do `iv_cluster`** |
| `calculate_tier_metrics` | `tier_metrics.py:5` | numpy entra, DataFrame sai |

- **As duas funções de calibração engolem.** Cada uma embrulha o corpo inteiro num `try/except Exception` que degrada em silêncio para `global_fallback` (`:63-78`, `:153-169`). Bug lá dentro é inobservável de fora — o silêncio que a escada de remédios do `CONTEXT.md` proíbe.
- **`ward` e `iv` são o mesmo loop aglomerativo** (`ward.py:63-149` contra `iv.py:68-162`) com função de custo diferente, mas as assinaturas divergem: um leva `max_crossings` + `use_volume_weights`, o outro `lambda_cross` + `lambda_vol`. O chamador decodifica a string do método em flag de kernel: `use_volume_weights=(method == "ward")` (`grouping.py:277`).
- **Nenhum chamador tem array pronto.** Cada chamada é precedida de 15 a 30 linhas de marshalling de frame para array (`grouping.py:246-270`, `screening.py:110-185`, `:289-299`, `expressions.py:186-224`). A seam é limpa; o custo de setup mora inteiro nos chamadores.
- **Zero testes chamam `ward_cluster`, `iv_cluster` ou `calculate_tier_metrics` direto.** Os ramos de cruzamento por safra (`ward.py:104-118`, `iv.py:110-131`) são exercitados só de raspão, por um único teste de `fit_risk_groups`. A calibração, essa sim, tem 6 + 13 testes.

### `sample_data.py` — 265 linhas, 3 nomes

O módulo mais profundo dos cinco: duas funções de dois parâmetros sobre 265 linhas de implementação, e **17 testes**. Duas fricções pequenas:

- O gerador devolve só o frame e **retém deliberadamente o limiar do incumbente** (`:208-210`), então todo chamador que precisa dele re-deriva `quantile(...)`. `validation/common.py:36` e `validation/ladder/ladder_common.py` **redeclaram a constante** `0.78` em vez de importar `LEGACY_APPROVAL_QUANTILE`.
- O contrato de colunas (qual base tem `market_default`) vive só em docstring (`:185-203`, `:251-255`).

### `suggest_hard_filters` (`screening.py:388`)

Assinatura de **9 parâmetros**, corpo de ~228 linhas, saída de **cinco contêineres heterogêneos** (`HardFilterSuggestion:242-269`), dois deles `dict[str, Any]` livres. Entrelaçamento com os tipos que morrem:

- `screening.py:14` importa `CutoffStage`/`FilterStage` **no topo do módulo**, usados só dentro de `_hf_policy_acts_on`;
- `CreditPolicy` está na assinatura (`:393`);
- `_hf_policy_acts_on` (`:375-386`) é a única leitura de política, e ela é `isinstance` mais **busca de palavra por regex sobre `str(stage.condition)`** (`:379`, `:383`).

Também dentro dela: três `warnings.warn` (`:471`, `:510`, `:527`), contra a regra do #132 de que aviso sobre dado não existe; e `_hf_column_table` (`:303`) com **9 posicionais**, chamado posicionalmente em `:489`.

Cobertura: `tests/test_hard_filters.py`, 17 testes, um importando o privado `_hf_column_table` (`:25`), todos sobre um fixture de 60 mil linhas.

### `validation/` — ~1.470 linhas, fora do pacote

Dois harnesses. O de paridade (`common.py`, 525 linhas) é branch-agnóstico e recebe tudo por um adaptador; o da escada (`ladder/ladder_common.py`, 458 linhas) **recebe o próprio pacote como argumento** — `run_cli(engine_name, pct, CreditPolicy, col, l8_notes)` —, que é como um arquivo só roda contra dois checkouts.

- O protocolo do adaptador **não está declarado em lugar nenhum**: para saber os dez membros exigidos é preciso diferenciar `MainAdapter` (`measure_main.py:17-60`) de `V05Adapter` (`measure_v05.py:21+`).
- `measure()` muta `CUTOFF_QUANTILES` global (`common.py:174-177`).
- Constantes duplicadas em vez de importadas (o `0.78` em três lugares).
- Sem `__init__.py`, com imports de irmão — só roda com o diretório como cwd.
- Os dois harnesses dirigem **exclusivamente** a superfície que morre. Nada em `validation/` toca `pycreditools.engine` — o que é justamente o trabalho do ticket 15.

Cobertura: `tests/test_validation_harness_dilution.py`, 6 testes, e só sobre o guarda de invariante de `common.py`.

### `engine/` — 954 linhas de fonte, entregues no #161

`_value.py` (213) é o mecanismo dirigido pela assinatura; `_nodes.py` (189) é a árvore congelada; `schema.py` (44), `policy.py` (140), `premise.py` (180) e `study.py` (121) são os quatro tipos; `errors.py` (18). Fricções internas medidas:

- **33 sítios de erro** distribuídos pelos tipos (premise 13, nodes 8, policy 5, study 5, schema 2), todos repetindo a mesma forma: checagem de tipo, checagem de domínio, normalização.
- Quatro módulos importam `set_field` de `_value` para normalizar dentro do próprio `__post_init__` — a normalização é imperativa, e o protocolo *"você é frozen, use `set_field`"* é interface que vaza para os clientes.
- `Study.vary` (`study.py:67-81`) **despacha por nome de campo** (`if field in ("schema", "premise") / elif field == "policy" / else`). Campo novo no `Study` exige editar o despacho — a mesma forma de *"o chamador lista os campos"* que a DoD 2 mata um nível abaixo.
- `Study.__repr__` injeta a própria anotação no render da `Premise` via `render(lens_note=...)`.

---

## Os sete candidatos

| # | movimento | força | onde a decisão mora |
|---|---|---|---|
| 1 | **Uma árvore, não duas.** A árvore congelada vira *a* árvore na contração; morrem os 14 dunders duplicados, o `eval` de 12 ramos, o par serializador e `CalibratedExpression`. Trava: o `__eq__` sobrecarregado. | Strong | **#178** |
| 2 | **O kernel de calibração: uma chamada.** Série e diagnóstico do mesmo sítio, e o `except Exception` morre. | Strong | **#179** |
| 3 | **Onde mora a avaliação da árvore congelada.** Método no nó contra função livre atrás da costura 1. | Strong | **#177** |
| 4 | **Derivação genérica no `vary`.** Recursão sobre value types em vez de despacho por nome de campo; `CreditPolicy` declara que endereça por label, e o `ranges=` dos tickets 8 e 10 nasce chamador do mesmo endereçador. | Worth exploring | — |
| 5 | **Um kernel de cluster, duas funções de custo.** Dois adapters de custo tornam a seam real, não hipotética; e os dois ganham teste direto antes do ticket 12 se apoiar neles. | Worth exploring | — |
| 6 | **`suggest_hard_filters` não pode ser intacto.** A pergunta que o regex tenta responder é resposta exata de `policy.columns()`. | Strong | **#180** |
| 7 | **Vocabulário de kinds de campo** para as 33 checagens. Contra, e é forte: as mensagens deste repo são específicas de propósito, e kind genérico tende a produzir mensagem genérica sobre uma superfície de 954 linhas. | Speculative | — |

Os candidatos 4, 5 e 7 ficam aqui, sem issue: nenhum deles trava ticket, e abrir decisão para eles agora competiria por prioridade com o caminho crítico.

## O que o mapa já tinha decidido — e por que estas issues não são re-litígio

Conferido card a card depois de escrito o levantamento, porque o mapa #111 tem **~30 tickets de grilling fechados** e o risco de reabrir matéria julgada é real.

| matéria | o que o mapa decidiu | o que sobra aberto |
|---|---|---|
| congelamento fundo | **#120**, resolução §3: *"todo tipo-valor vira frozen dataclass, folhas inclusive"*. O estado medido que ele enumera são os `Stage`, as classes de stress e o `GroupingRecipe` — **`Expression` não está na lista** | **#178.** O #135 mediu o obstáculo (*"`Expression.__eq__` devolve `Expression` e quebra hasheabilidade"*) e foi declarado fora de escopo — `functional-core.md:317-318`: *"fora de escopo por ruling do dono em #135: #120 decidiu a matéria sem esperar a pesquisa"*. **O princípio e o obstáculo nunca se encontraram**, e o ticket 4 é onde colidiram |
| `except Exception` engolindo bloco | **#132**: *"substituir por captura estreita do erro esperado, deixando erro de programação subir. **Regra do pacote**"* | **Nada, quanto ao mérito.** O inventário do #132 lista sítios de `simulation.py` e **não inclui** `_kernels/calibration.py:63-78` / `:153-169`. É sítio fora do inventário, não decisão nova. O #179 fica só com a forma da interface |
| `suggest_hard_filters` | **#126**: *"fica intacto — sugere limiar de reprovação, com orçamento e lift. Produto de política, não de nota"* | **#180**, e só a palavra *"intacto"*: o que a função **é** não está em causa; o que a medição mostra é que ela não atravessa o ticket 16 sem tocar |
| onde a avaliação mora | nenhum card decide, mas a §4.6 (régua dplyr) e a §5 (o `ctx` e o `Protocol` são internos) **inclinam** | **#177** |
| população de calibração | **#139** e **#152**: a população é o livro contratado, e o nome é **`calibrate_on="hired"`**, com o registro explícito de que **`"global"` está queimado** | **#182.** A spec §4.4 shipa `"global"`, com a semântica certa e o nome que dois cards recusaram; a §9.1 enumera oito emendas declaradas e **esta não está entre elas**. O #161 já shipou o literal |

## Onde as decisões aterrissaram

- **#177** — onde mora a avaliação da árvore congelada (trava o #162).
- **#178** — uma árvore ou duas na contração (trava o #172).
- **#179** — a forma da interface do kernel de calibração, mais quando o ruling do #132 alcança o sítio dele (trava o #163).
- **#180** — `suggest_hard_filters` intacto é impossível (revisita o #126, emenda a §4.9, trava o #167).
- **#181** — as duas leituras da spec sobre a `Premise`: o default de `take_up` e o erro *"lente discreta + `bins`"*.
- **#182** — `calibrate_on`: `"hired"` dos cards contra `"global"` da spec, já shipado no ticket 4.

As duas últimas não saíram deste levantamento — vieram da implementação do ticket 4 e da conferência contra o mapa. Ficam aqui porque são do mesmo lote de decisões que estavam registradas só em prosa.
