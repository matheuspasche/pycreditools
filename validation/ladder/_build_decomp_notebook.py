"""Generate swap_in_conversion_decomp.ipynb — a SINGLE-ENGINE (v0.5) modeling
analysis, separate from the parity study.

Scope boundary (deliberate): `ladder_report.ipynb` debugs v0.5 vs main and the
parity there is settled. THIS notebook does not compare engines — it decomposes
what the take-up/conversion stage does to the swap-in's weight in the new book,
using only observables (no oracle / true_pd). Run once to (re)emit:
    python _build_decomp_notebook.py
"""

from __future__ import annotations

import nbformat as nbf

nb = nbf.v4.new_notebook()
c = nb.cells

c.append(nbf.v4.new_markdown_cell(
    "# Decomposição A vs B — o stage de conversão sobre o swap-in\n\n"
    "**Escopo:** análise de modelagem, **uma engine só (v0.5)**, só observáveis "
    "(sem oráculo/`true_pd`). **NÃO** é estudo de paridade — a paridade v0.5 × main "
    "está pacificada no `ladder_report.ipynb`. Aqui a pergunta é outra: o que um "
    "`RateStage` de conversão (`take_up_rate`, com taxa < 1) faz com o **peso do "
    "swap-in** na carteira nova.\n\n"
    "Isolado pela escada #93: L2 (sem conversão) → L3 (+conversão) muda **exatamente "
    "um** componente. Comparamos os dois degraus da MESMA engine.\n\n"
    "## Dois efeitos opostos\n"
    "- **Efeito A (mix):** seleção adversa — pior score converte mais → o swap-in que "
    "sobra é mais arriscado. Empurra o PD do swap-in **pra cima**.\n"
    "- **Efeito B (nível):** conversão < 1 → menos swap-ins fecham contrato. Como o "
    "keep-in tem bypass (=1.0, contrato #94), o swap-in **encolhe como fração da "
    "carteira nova**. Puxa o blended **pra baixo**.\n\n"
    "O blended é `wk·pk + ws·ps` (pesos de keep-in/swap-in, PDs de cada). B mexe em "
    "`ws`; A mexe em `ps`; `pk` fica (são os mesmos keep-ins)."
))

c.append(nbf.v4.new_code_cell(
    "import os\n"
    "import pandas as pd\n"
    "import ladder_common as lc\n"
    "\n"
    "TAG = os.environ.get('LADDER_TAG', '1p5m')\n"
    "recs = lc.load_results(TAG)  # results/*.jsonl (gitignored, regenerable)\n"
    "def facts(step):\n"
    "    m = recs[(step, 'v05')]['measured']\n"
    "    kv = sum(r['keep_in_vol'] for r in m['decile_table'])\n"
    "    sv = sum(r['swap_in_vol'] for r in m['decile_table'])\n"
    "    ps = sum(r['swap_in_inad'] * r['swap_in_vol'] for r in m['decile_table'] if r['swap_in_vol']) / sv\n"
    "    pk = sum(r['keep_in_inad'] * r['keep_in_vol'] for r in m['decile_table'] if r['keep_in_vol']) / kv\n"
    "    tot = kv + sv\n"
    "    return {'keep_in_vol': kv, 'swap_in_vol': sv, 'ws': sv / tot, 'wk': kv / tot,\n"
    "            'ps': ps, 'pk': pk, 'blended': m['blended_default']}\n"
    "\n"
    "a, b = facts('L2'), facts('L3')\n"
    "tbl = pd.DataFrame({'L2 (sem conversão)': a, 'L3 (+conversão)': b}).T\n"
    "tbl[['keep_in_vol', 'swap_in_vol', 'ws', 'ps', 'pk', 'blended']].round(4)"
))

c.append(nbf.v4.new_markdown_cell(
    "## Decomposição sequencial (B primeiro, depois A)\n"
    "`pk` é mantido (mesmos keep-ins; bypass não deixa a conversão tocá-los). "
    "B move só a fração `ws`; A move só o PD `ps`."
))

c.append(nbf.v4.new_code_cell(
    "pk = a['pk']  # keep-in PD, constante entre os degraus\n"
    "blend = lambda ws, ps: (1 - ws) * pk + ws * ps\n"
    "base   = blend(a['ws'], a['ps'])   # L2\n"
    "afterB = blend(b['ws'], a['ps'])   # aplica só a mudança de fração (Efeito B)\n"
    "afterA = blend(b['ws'], b['ps'])   # aplica também a mudança de mix (Efeito A)\n"
    "eff_B = afterB - base\n"
    "eff_A = afterA - afterB\n"
    "print(f'swap-in / carteira nova:  {a[\"ws\"]:.3f} -> {b[\"ws\"]:.3f}')\n"
    "print(f'PD do swap-in (mix):      {a[\"ps\"]:.4f} -> {b[\"ps\"]:.4f}')\n"
    "print(f'blended:                  {a[\"blended\"]:.4f} -> {b[\"blended\"]:.4f}')\n"
    "print()\n"
    "print(f'Efeito B (nível/share):   {eff_B:+.4f}')\n"
    "print(f'Efeito A (mix):           {eff_A:+.4f}')\n"
    "print(f'total:                    {eff_A + eff_B:+.4f}  (delta blended {b[\"blended\"] - a[\"blended\"]:+.4f})')"
))

c.append(nbf.v4.new_markdown_cell(
    "## Leitura\n\n"
    "O **Efeito B domina o A** (várias vezes maior). Modelar a conversão **reduz** a "
    "participação do swap-in de alto risco na carteira nova — o keep-in (com bypass) "
    "dilui, e o blended cai, **antes de qualquer stress**. O efeito-mix (A, seleção "
    "adversa) existe mas é pequeno perto disso.\n\n"
    "> **Base observada, não decisão.** `keep_in_vol` aqui é o keep-in **contratado** "
    "(com desfecho) — os aprovados-não-pagos ficam de fora de toda conta de inad "
    "(seguem keep-in por decisão, mas sem `actual_default` não entram em denominador). "
    "Por isso o swap-in pesa mais na carteira observada do que a intuição sugere.\n\n"
    "**Consequência pro estudo de 'modelo melhor sem ganho':** sem o stage de "
    "conversão a carteira nova fica ~metade swap-in de alto risco e o ganho some; com "
    "ele, o swap-in dilui e o ganho aparece — sem invocar oráculo. A alavanca do "
    "'ganho' são **duas premissas de modelagem** (conversão presente + fator de "
    "stress escolhido), não a engine."
))

with open("swap_in_conversion_decomp.ipynb", "w", encoding="utf-8") as fh:
    nbf.write(nb, fh)
print("wrote swap_in_conversion_decomp.ipynb")
