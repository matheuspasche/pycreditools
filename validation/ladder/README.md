# Escada de ablação — paridade de motor `main` × `v0.5` (issue #93)

Material de validação — **não** entra no pacote publicado. Evolução da #91: em vez
de comparar o fluxo inteiro e desmontar as diferenças por perícia, parte da política
mais simples e adiciona **um componente por degrau**. O primeiro degrau que estoura a
tolerância aponta o culpado **por construção**.

## Como rodar do zero

```bash
# Windows — as duas engines, 60k e 1,5M
powershell -ExecutionPolicy Bypass -File validation\ladder\run_all.ps1
# só um tamanho
powershell -ExecutionPolicy Bypass -File validation\ladder\run_all.ps1 -Sizes 60k
# POSIX
bash validation/ladder/run_all.sh 60k 1p5m
```

Cria/atualiza os worktrees (`../wt-main` em `main`, `../wt-v05` no HEAD desta branch),
um venv por worktree, gera a **base única** por tamanho e roda `run_ladder_main.py` /
`run_ladder_v05.py` — cada degrau, cada engine, lendo o MESMO parquet. Depois abra
`ladder_report.ipynb` (só agrega os JSONs; não importa `pycreditools`). Limpeza:
`git worktree remove ../wt-main ../wt-v05`.

Regra de ouro: **toda métrica sai de `policy.simulate(...).data`** — zero fast-path.

### Dois notebooks, escopos separados

- `ladder_report.ipynb` — **paridade v0.5 × main** (matriz verde/vermelho, diff mínimo).
  É o debug de motor; a paridade está pacificada aqui (primeiro vermelho = L2, #94).
- `swap_in_conversion_decomp.ipynb` — **análise de modelagem, uma engine só (v0.5)**,
  só observáveis (sem oráculo). Decompõe o que o stage de conversão faz com o peso do
  swap-in na carteira nova (Efeito A = mix × Efeito B = nível). **Não** é paridade —
  não misturar com o de cima.

## Decisões travadas com o dono (desvios do texto do issue)

1. **Opção B — `current_approval_col` ligado desde o L0.** A população swap-in existe
   em todo degrau; o PD imputado do swap-in é invariante comparado desde o L0. (O issue
   sugeria ligar a coluna só no L4; o dono optou por B.)
2. **`calibration_bins=10` fixo em toda a escada**, casando com os 10 decis da tabela-
   resumo. Mesma banda pra calibração e pra tabela → a razão `swap_in_inad / keep_bin_pd`
   dá **exatamente** o fator de stress, decil a decil. Com isso os degraus de varredura de
   calibração do issue (L4 default-decis, L5 bins=5) colapsam num só ajuste fixo.
3. **Mesmo mecanismo nos dois lados.** Take-up e antifraude usam o **denominador comum**
   (`rate(base_rate=, variable=)`), idêntico byte a byte. `observed_col`/`calibrate_by`
   (v0.5) e a heurística de nome/posição (main) viram nota L8, nunca degrau.

### Mapa dos degraus (issue L0–L8 → esta escada)

| esta escada | + componente | issue |
|---|---|---|
| **L0** | corte `score_5 >= c` | L0 |
| **L1** | + hard filters | L1 |
| **L2** | + antifraude escalar (`base_rate=0.90`) | L2 |
| **L3** | + take_up por risco (`variable="take_up_rate"`) | L3 |
| **L4** | + stress ×1,5 | L6 |
| **L5** | + segmentação regional | L7 |
| — | swap-in / calibração: intrínsecos desde L0 (Opção B + bins=10) | L4–L5 (colapsados) |
| L8 | idiomas exclusivos — só documentação | L8 |

## A base (`build_base.py`, uma vez por tamanho)

- Gerador v0.5, `seed=7`. Tamanhos: `n=60_000` (iteração) e `n=1_500_000` (número final).
- **`take_up_rate` imputada por risco, FORA das engines:** conversão observada
  `hired/approved` por decil de `score_5` na população aprovada, gravada como coluna.
  Forma: pior score → maior conversão (adverse selection). Única fonte de take-up dos dois
  lados, sempre via `variable="take_up_rate"`.
- **`antifraud_rate`:** média de `passed_antifraud` (~0,90), constante escalar no manifesto.
- Manifesto (`*_manifest.json`): seed, n, **SHA-256** do parquet, curva take-up por decil,
  taxa de antifraude, corte legacy e o corte challenger (mediana de `score_5`).
- Cópia `.xlsx` (gabarito) só no 60k. `true_pd` viaja como curiosidade — nunca invariante.

## Invariantes e tolerâncias (declarados em `ladder_common.TOL`, antes de rodar)

Booleanos/ids/contadores: **exato**. Floats: `1e-9` (aritmética direta) ou `1e-4`
(imputação com calibração). Cada JSON de degrau serializa a config completa, os
invariantes medidos, o SHA da base e os **warnings capturados** (nunca suprimidos).

### Dois sanity checks embutidos (pedido do dono)

- **Carteira = SOMARPRODUTO.** `Σ(inad_célula × volume_célula) / Σvolume` sobre keep-in +
  swap-in de todos os decis ≡ `blended_default` do `kpis`. Bate a `1e-9` em todo degrau.
- **Razão = stress.** `swap_in_inad / keep_bin_pd` = fator aplicado, decil a decil
  (`keep_bin_pd` é a fonte não-ponderada que o motor imputa; o swap-in do bin é esse PD ×
  fator). Sem stress = 1,0; no L4/L5 = 1,5, cravado.

> **Exato, não amostral.** No modo `analytical` o `simulated_default` do swap-in **é** o PD
> imputado (`keep_bin_pd × fator`), valor esperado determinístico — não um desfecho sorteado.
> Logo a razão dá o fator **exato** em qualquer `n`, sem ruído amostral. As duas engines
> passam os dois checks (60k e 1,5M); o divergente é só o re-gate do keep-in (#94), ortogonal.
> Esse contrato virou teste de pacote: `tests/test_stress_imputation_contract.py`.

## Resultado (60k; o relatório final usa 1,5M)

| degrau | + componente | veredito main × v0.5 |
|---|---|---|
| L0 | corte | 🟩 verde (funil booleano idêntico) |
| L1 | + hard filters | 🟩 verde |
| **L2** | **+ antifraude escalar** | 🟥 **primeiro vermelho** — `contracted`, `blended_default` |
| L3 | + take_up por risco | 🟥 (cascata do L2) |
| L4 | + stress ×1,5 | 🟥 (cascata) |
| L5 | + regional | 🟥 (cascata) |

### Diff mínimo do L2 (culpado isolado)

`approval` pré-rate **idêntica** (0,34175) e **quadrantes idênticos** — o funil não mexeu.
`swap_in_vol` idêntico (antifraude 0,90 aplicado ao swap-in nos dois). Só `keep_in_vol`
diverge:

- **v0.5**: `keep_in_vol` = população keep-in inteira (9.137) → **bypass declarativo**:
  rate escalar sem `observed_col` ⇒ keep-in recebe 1,0.
- **main**: `keep_in_vol` = 4.196 → **aplica a taxa** ao keep-in (heurística de nome/posição
  do RateStage não reconhece "Anti-fraud" como estágio-conversão de bypass).

Componente culpado: o rate escalar no keep-in. Semântica divergente por **código**, não por
configuração — vira issue própria (fora de escopo, abaixo). Tudo após o L2 fica vermelho
porque `contracted` já diverge; a escada não "descobre" nada novo depois — só confirma a
cascata.

## Critérios de aceite (issue #93)

- [x] UMA base: só `build_base.py` gera dados; todos os JSONs registram o mesmo SHA-256.
- [x] `take_up_rate` por risco FORA das engines, via `variable=` idêntico; nenhum degrau usa
      `observed_col`.
- [x] Cada degrau adiciona exatamente um componente; config serializada no JSON.
- [x] Tolerâncias declaradas no código antes da comparação.
- [x] L0–L5 rodam nas duas engines com um comando (`run_all`); matriz verde/vermelho no
      notebook.
- [x] Degrau vermelho com diff mínimo reproduzível (config + contadores divergentes + delta).
- [x] L8 documenta idiomas exclusivos sem misturar na escada.
- [x] Nenhuma métrica de fast-path; tudo `simulate()`.
- [x] Rodado em 60k e 1,5M; relatório final usa 1,5M.

## Fora de escopo

- **Corrigir** o bypass divergente do L2 — vira issue própria, com o diff mínimo como corpo.
- `optimize_cutoffs` segmentado — é a #92.
- Números históricos do README da main — abandonados (#91).
- Oráculo `true_pd` — fora do protocolo (não portável); no máximo curiosidade no xlsx.

## Referências

- #91 — estudo de paridade original (a perícia que motivou este protocolo).
- #92 — `optimize_cutoffs(by=)` com re-reporte via simulate.
- ADR 0008 (contrato de métrica), ADR 0010 (contrato de engine).
