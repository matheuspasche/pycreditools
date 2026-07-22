# Escada de ablação — resumo (tag `1p5m`)

Gerado por `build_summary.py` a partir de `results/*.jsonl` (gitignored). n=1,500,000 · base SHA-256 `f7283541835f52a6…`

## Matriz de paridade main × v0.5

| degrau | adiciona | veredito |
|---|---|---|
| L0 | cutoff only | 🟩 verde |
| L1 | + hard filters | 🟩 verde |
| L2 | + antifraud scalar rate | 🟥 contracted |
| L3 | + risk-graded take_up_rate (variable=) | 🟥 contracted, effective_rate_by_decile |
| L4 | + stress x1.5 | 🟥 contracted |
| L5 | + regional segmentation | 🟥 segmented_default |

**Primeiro degrau vermelho:** ('L2', 'contracted')

## Tabela por decil — v0.5, degrau L4 (+ stress x1.5)

| decil | keep_vol | keep_dec | keep_in_inad | swap_vol | swap_in_inad | conv | sw/keep |
|---|---|---|---|---|---|---|---|
| 0 | 13151 | 22898 | 0.1363 | 104467 | 0.2045 | 0.5741 | 1.500 |
| 1 | 11888 | 22594 | 0.0888 | 17956 | 0.1332 | 0.6684 | 1.500 |
| 2 | 10885 | 22700 | 0.0768 | 8447 | 0.1152 | 0.7411 | 1.500 |
| 3 | 10929 | 23457 | 0.0617 | 4713 | 0.0925 | 0.8138 | 1.500 |
| 4 | 10291 | 21983 | 0.0523 | 2706 | 0.0784 | 0.8673 | 1.500 |
| 5 | 10135 | 23653 | 0.0386 | 1671 | 0.0579 | 0.9067 | 1.500 |
| 6 | 9057 | 22030 | 0.0271 | 899 | 0.0406 | 0.9375 | 1.500 |
| 7 | 9303 | 22681 | 0.0199 | 621 | 0.0298 | 0.9565 | 1.500 |
| 8 | 9537 | 23168 | 0.0143 | 491 | 0.0214 | 0.9656 | 1.500 |
| 9 | 8938 | 21835 | 0.0062 | 401 | 0.0092 | 0.9698 | 1.500 |

blended `0.1276` · sumproduct ok `True` · stress_ratio ok `True`

## Diff mínimo — L2

- approval pré-rate: main `0.34121` · v05 `0.34121` (igual: `True`)
- quadrantes iguais: `True`
- contracted: main `360430` · v05 `483315` · delta `122885`
- keep-in contratado (decisão): main `104114` · v05 `226999`
