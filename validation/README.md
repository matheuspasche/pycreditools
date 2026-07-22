# Validação de paridade: masterclass `main` × `release/v0.5` (issue #91)

Material de validação — **não** entra no pacote publicado.

## Como rodar do zero

```bash
# Windows
powershell -ExecutionPolicy Bypass -File validation\run_all.ps1
# POSIX
bash validation/run_all.sh
```

O orquestrador cria os worktrees (`../wt-main` em `main`, `../wt-v05` em
`feat/76-masterclass-notebook`), um venv por worktree, gera o frame canônico
(`shared_base.parquet` + cópia `shared_base.xlsx` para conferência manual) e roda
`measure_main.py` / `measure_v05.py` em subprocesso (modos A e B, n=60k e 20k),
emitindo os JSONs em `results/`. Depois abra `masterclass_engine_parity.ipynb`
(ele só lê os JSONs; não importa `pycreditools`). Limpeza:
`git worktree remove ../wt-main ../wt-v05`.

Regra de ouro respeitada: **toda métrica reportada sai de `policy.simulate(...).data`**;
nenhum número vem do fast-path de sweep (a `optimize_cutoffs` da v0.5 usa `run_sweep`
internamente, por isso os scripts localizam cortes com a própria grade de `.simulate()`).

## Veredito, por diferença

Números a seed=7, n=60.000, modo A (≡ modo B). Nenhum diff ficou “inexplicado”.

| Diferença observada | Classificação | Causa / referência |
|---|---|---|
| Dados gerados pro mesmo seed | **Inexistente** | Colunas compartilhadas dos dois geradores são byte a byte idênticas (v0.5 sorteia as colunas novas *depois* do stream comum). Modo A ≡ modo B nas duas engines. A premissa da issue de que os geradores divergem não se confirmou. |
| Incumbente (20,55% / 7,54% / 5.719 contratados) | **Idêntico** | Nenhuma divergência; bate com a referência de sessão da issue. |
| Contrato de métrica (ADR 0008) | **Esperada, sem gap numérico** | Aplicando a mesma fórmula aos mesmos dados, os números coincidem — inclusive recomputando o contrato antigo nos dois lados. O ADR 0008 muda o que se *reporta*, não o funil. Manchetes diferentes entre README e masterclass vêm da fórmula exibida, não da engine. |
| KS nos aprovados-HF (score_5 = 0,3333) | **Idêntico** | `ModelEvaluator.compute_ks` igual nas duas branches. |
| Seleção de hard filters | **Esperada, neutralizada** | O sugestor da v0.5 (PR #73), deixado livre, escolhe exatamente `vl_negativacao<=0 & vl_vencido_scr<=0 & vl_protestos<=0` — o mesmo conjunto do README. Fixado nos dois lados. |
| Volume contratado do challenger (5.526 vs 5.574; swap-in 1.811 vs 1.859) | **Esperada, documentada** | Idioma de take-up: coluna de propensão (`main`) × `observed_col="hired"` + `calibrate_by="score"` (v0.5, RateStage genérico #68 / ADR 0008). Efeito ~+2,6% no volume de swap-in. |
| PD imputado do swap-in (8,16% main vs 7,62% v0.5) | **Esperada, documentada — é O driver** | Com a mesma calibração (decis default), as engines quase coincidem (8,16% vs 8,13%; resíduo = pesos de take-up); e setando `calibration_bins=5` na main também (o parâmetro **existe nas duas engines**), os imputados voltam a colar (7,60% vs 7,62%). O deslocamento é *escolha de fluxo*: a masterclass seta bins=5 (resposta ao warning do PR #72); o README/main fica nos decis default. |
| “Modelo melhor sem ganho” | **Artefato do stress ×1,5 — confirmado** | PD real do swap-in (oráculo): 10,1%. Imputado cru subestima (~×0,78); **markup honesto ≈ ×1,3** (9,9–10,6% cerca o real); **×1,5 superestima** (11,4–12,2%). Na mesma aprovação, o challenger entrega inad real 6,4% vs 7,5% do incumbente (−1,1 p.p., nas duas engines); com ×1,5 o ganho quase desaparece (6,95–7,18%). O stress ×1,5 também foi **medido** via `policy.stress(1.5)` real em cada engine — coincide com a derivação analítica (`clip(pd × fator)` nos dois lados). |
| `optimize_cutoffs` alega ≠ `.simulate()` entrega | **Achado operacional — fast-path das duas erra, em direções opostas** | Deixando cada engine usar seu próprio otimizador (mesmo alvo 7,54%): a **main** alega inad 6,8% no corte 625, mas re-simulado dá **8,5%** — fura o alvo em ~1 p.p. (otimista/inseguro). A **v0.5** alega 7,4% no corte 688 e re-simulado dá **6,7%** — conservadora (a inflação de swap-in do sweep já flagrada na issue). Confirma a regra de ouro: fast-path localiza, `.simulate()` reporta. |
| Cutoff iso-inad (686 main vs 661 v0.5) e cutoffs regionais (ex.: Sul 680 vs 575) | **Downstream do driver, não é bug** | A v0.5 imputa PD menor no swap-in → “acha” que cabe descer mais o corte pro mesmo orçamento de risco. Critério e grade idênticos nos dois lados. |
| Rating A–E (Train 1,4%→17,6%; OOT estável) | **Idêntico** | `fit_risk_groups` igual nas duas branches. |
| “5,80% de PD estressado” regional do README | **Não reproduzível — diferença de setup** | Alvo escolhido à mão com outra premissa de stress; nenhum fluxo canônico chega nele. Não é evidência contra nenhuma engine. |
| Sensibilidade a n=20.000 | **Veredito estável** | Ganho real do challenger persiste (6,9% vs 7,1% do incumbente), margem menor. Nenhuma conclusão muda com o tamanho. |

## Em qual confiar?

**Nas duas para a mecânica** (dados, funil, KS, quadrantes, rating — tudo idêntico). O que
muda entre README/`main` e masterclass/v0.5 são **premissas declaradas**: `calibration_bins=5`
e o markup de stress. Onde as engines de fato se separam é no **fast-path do otimizador**:
o da main erra pro lado inseguro (fura alvo de risco), o da v0.5 pro lado conservador — e a
v0.5 ainda te avisa quando a calibração é extrapolação (`CalibrationReliabilityWarning`,
capturado nos `notes` dos JSONs), o que a `main` não faz. Para decisão de corte, os números
do README calibrados pelo otimizador da main devem ser tratados como otimistas.

Uma lição operacional que vale para as duas engines: **localizar cortes pela inad simulada
crua é otimista** — a política “iso-inad” escolhida assim entrega inad real acima do alvo
(main 7,9%, v0.5 8,6%, alvo 7,54%). Localize cortes com markup ~×1,3 sobre o imputado.

**Conclusão para o merge:** nenhum bug encontrado; todas as divergências são esperadas e
documentadas (ADR 0008, PR #68, PR #72, PR #73). O desencontro que motivou a issue era
(a) manchete do README calculada com premissas hand-picked não reproduzíveis e
(b) stress ×1,5 mascarando o ganho real do `score_5`. Sem bloqueio de paridade para o merge.

## Arquivos

```
validation/
  run_all.ps1 / run_all.sh       # orquestração completa (worktrees + venvs + medições)
  build_shared_frame.py          # frame canônico modo B (+ shared_base.xlsx pra conferência)
  common.py                      # núcleo de medição compartilhado (só .simulate())
  measure_main.py                # adaptador pra API da main
  measure_v05.py                 # adaptador pra API da v0.5
  masterclass_engine_parity.ipynb# tabelas lado a lado, passos 1–7 + veredito
  results/*.json                 # main|v05 × A|B × 60k|20k
```
