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

**Protocolo de condições iguais**: `calibration_bins=5` nas DUAS engines (o knob existe nas
duas) e **stress ×1,5 sempre** — toda inad manchete de challenger é a estressada ×1,5, com
as variantes sem stress / ×1,3 / oráculo mantidas como diagnóstico.

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
| PD imputado do swap-in | **Fechada sob condições iguais** | Mesmo knob → mesma resposta: bins=5 dá 7,60% (main) vs 7,62% (v0.5); decis default dá 8,16% vs 8,13%. Resíduo de ~0,03 p.p. = pesos de take-up. A divergência original era *escolha de fluxo* (masterclass seta bins=5, resposta ao warning do PR #72; README ficava nos decis), não capacidade de engine. |
| “Modelo melhor sem ganho” | **Artefato do stress ×1,5 — confirmado, e quantificado sob o protocolo** | PD real do swap-in (oráculo): 10,1%. Imputado cru (bins=5) 7,6% subestima ~25%; **markup honesto ≈ ×1,3** (9,9% ≈ real); **×1,5 superestima** (11,4%). Sob o protocolo ×1,5 fixado nos dois lados: manchete 6,90% (main) vs 6,95% (v0.5) contra 7,54% do incumbente — **ainda sobra −0,6 p.p. de ganho**, idêntico nas duas engines; contra o oráculo o ganho é −1,1 p.p. (o ×1,5 come metade). Stress também **medido** via `policy.stress(1.5)` real — coincide com a derivação (`clip(pd × fator)` nos dois lados). |
| Funil completo (antifraude taxa fixa + conversão por score): contratado da main cai menos que ×0,90 | **Esperada, mas semântica frágil na main** | Nos keep-ins, a main dá bypass (probs=1,0) a qualquer rate stage “não-conversão”, com detecção por **nome/posição** do estágio (`stages.py`: nome em `{conversao, conversion, hired, take_up, take_up_rate}`, `calibrate=True`, ou último RateStage); antifraude fixo nunca toca o livro histórico. A v0.5 é declarativa: `observed_col` presente → keep-in usa o valor observado (~0,90); ausente → 1,0. Aprovação pré-rate intacta e gradiente de conversão decrescente no score nas **duas** engines; probe de ordem invertida deu invariante nos dois lados (na main por coincidência aritmética: `hired` é 0/1). |
| `optimize_cutoffs` alega ≠ `.simulate()` entrega | **Achado operacional — a ÚNICA etapa que condições iguais não fecham** | Mesma config (bins=5 + stress ×1,5) nos dois otimizadores, mesmo alvo 7,54%: a **main** alega 7,2% no corte 688, re-simulado estressado dá **8,5%** — fura o alvo em ~1 p.p. (otimista/inseguro). A **v0.5** alega 7,2% no corte 751, re-simulado dá **6,3%** — conservadora (inflação de swap-in do sweep, já flagrada na issue). Diferença de código do fast-path, não de configuração. Regra de ouro: fast-path localiza, `.simulate()` reporta. |
| Cutoffs (iso-inad, regionais) | **Fecharam sob condições iguais** | Com bins=5 + ×1,5 nos dois lados: as três políticas colapsam pro mesmo corte 736 nas duas engines, e os cortes regionais saem **idênticos** nas 5 regiões (752/785/732/694/680). A divergência das rodadas anteriores era 100% premissa de calibração/stress. Sob ×1,5, o challenger compra redução de risco na mesma aprovação, não expansão. |
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

Lição operacional que vale para as duas engines: **em condições iguais, tudo que é política
cola** (cortes, aprovação, inad manchete) — o que sobra é o idioma de take-up (~0,05 p.p.)
e o fast-path do otimizador. Localize cortes com `.simulate()` + markup (×1,3 honesto contra
o oráculo; ×1,5 é o conservadorismo declarado do protocolo), nunca pelo otimizador cru.

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
