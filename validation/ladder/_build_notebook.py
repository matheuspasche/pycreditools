"""Generate ladder_report.ipynb (issue #93). The notebook only AGGREGATES the
result JSONs — it computes no policy (principle #6). Run once to (re)emit:
    python _build_notebook.py
"""

from __future__ import annotations

import nbformat as nbf

nb = nbf.v4.new_notebook()
c = nb.cells

c.append(nbf.v4.new_markdown_cell(
    "# Escada de ablação — paridade de motor (issue #93)\n\n"
    "Um degrau, um componente. O **primeiro vermelho** aponta o culpado — nada "
    "depois dele é confiável (a divergência cascateia). Este notebook só lê os "
    "`results/L*_*.json`; toda métrica saiu de `policy.simulate().data`.\n\n"
    "**Base única** (SHA-256 no rodapé), `calibration_bins=10` fixo, "
    "`current_approval_col` ligado desde o L0 (swap-in existe em todo degrau)."
))

c.append(nbf.v4.new_code_cell(
    "import json, glob, os\n"
    "import pandas as pd\n"
    "import ladder_common as lc\n"
    "\n"
    "TAG = os.environ.get('LADDER_TAG', '1p5m')  # final report uses 1.5M\n"
    "def load(step, eng):\n"
    "    p = f'results/{step}_{eng}_{TAG}.json'\n"
    "    if not os.path.exists(p):\n"
    "        p = f'results/{step}_{eng}_60k.json'  # fallback\n"
    "    return json.load(open(p, encoding='utf-8'))\n"
    "\n"
    "recs = {(s, e): load(s, e) for s in lc.STEPS for e in ('main', 'v05')}\n"
    "shas = {r['base_sha256'] for r in recs.values()}\n"
    "print('base SHA-256 (deve ser UM):', shas)\n"
    "print('n:', {r['n'] for r in recs.values()}, ' TAG:', TAG)"
))

c.append(nbf.v4.new_markdown_cell(
    "## Matriz degrau × invariante — verde/vermelho\n"
    "Tolerância declarada por degrau **antes** de rodar (`ladder_common.TOL`)."
))

c.append(nbf.v4.new_code_cell(
    "def paint(v): return '🟩' if v == 'green' else '🟥'\n"
    "rows = []\n"
    "first_red = None\n"
    "for step in lc.STEPS:\n"
    "    m = recs[(step, 'main')]['measured']\n"
    "    v = recs[(step, 'v05')]['measured']\n"
    "    for r in lc.compare(m, v, step):\n"
    "        if r['verdict'] == 'red' and first_red is None:\n"
    "            first_red = (step, r['invariant'])\n"
    "        rows.append({'degrau': step, 'adiciona': lc.STEP_ADDS[step],\n"
    "                     'invariante': r['invariant'], 'tol': r['tolerance'],\n"
    "                     'delta': r['delta'], 'veredito': paint(r['verdict'])})\n"
    "matrix = pd.DataFrame(rows)\n"
    "print('PRIMEIRO DEGRAU VERMELHO:', first_red)\n"
    "matrix"
))

c.append(nbf.v4.new_markdown_cell(
    "## Placar por degrau (um olhar)"
))
c.append(nbf.v4.new_code_cell(
    "board = []\n"
    "for step in lc.STEPS:\n"
    "    m = recs[(step, 'main')]['measured']\n"
    "    v = recs[(step, 'v05')]['measured']\n"
    "    cmp = lc.compare(m, v, step)\n"
    "    reds = [r['invariant'] for r in cmp if r['verdict'] == 'red']\n"
    "    board.append({'degrau': step, 'adiciona': lc.STEP_ADDS[step],\n"
    "                  'veredito': '🟩 verde' if not reds else '🟥 ' + ', '.join(reds)})\n"
    "pd.DataFrame(board)"
))

c.append(nbf.v4.new_markdown_cell(
    "## Tabela-resumo por decil (v0.5, degrau selecionado)\n"
    "Decis da calibração nas linhas; keep-in vs swap-in em volume e inad, taxa de "
    "conversão efetiva, e a razão `swap_in_inad / keep_bin_pd`.\n\n"
    "**Sanity #1** — carteira = SOMARPRODUTO das células ≡ `blended_default`.\n"
    "**Sanity #2** — sob stress, a razão swap/keep = fator, decil a decil."
))
c.append(nbf.v4.new_code_cell(
    "STEP = os.environ.get('LADDER_STEP', 'L4')  # L4 = primeiro degrau com stress\n"
    "m = recs[(STEP, 'v05')]['measured']\n"
    "tbl = pd.DataFrame(m['decile_table'])\n"
    "print(f'degrau {STEP} — {lc.STEP_ADDS[STEP]}')\n"
    "s = m['sanity']\n"
    "print('sumproduct == blended :', s['sumproduct_matches_blended'],\n"
    "      f\"({s['sumproduct_default']:.6f} vs {m['blended_default']:.6f})\")\n"
    "print('razão swap/keep == fator', s['expected_ratio'], ':', s['stress_ratio_ok'])\n"
    "tbl.round(4)"
))

c.append(nbf.v4.new_markdown_cell(
    "## Diff mínimo do primeiro degrau vermelho\n"
    "Config + contadores divergentes + delta — suficiente pra abrir bug sem re-rodar."
))
c.append(nbf.v4.new_code_cell(
    "if first_red:\n"
    "    step = first_red[0]\n"
    "    m = recs[(step, 'main')]['measured']; v = recs[(step, 'v05')]['measured']\n"
    "    print('degrau', step, '—', lc.STEP_ADDS[step])\n"
    "    print('approval (pre-rate)  main', m['approval'], 'v05', v['approval'], '(deve bater)')\n"
    "    print('quadrantes iguais    :', m['quadrant_counts'] == v['quadrant_counts'])\n"
    "    print('contracted           main', round(m['contracted']), 'v05', round(v['contracted']),\n"
    "          'delta', round(m['contracted'] - v['contracted']))\n"
    "    print('blended_default      main', round(m['blended_default'], 5), 'v05', round(v['blended_default'], 5))\n"
    "    mk = sum(r['keep_in_vol_decision'] for r in m['decile_table']); vk = sum(r['keep_in_vol_decision'] for r in v['decile_table'])\n"
    "    ms = sum(r['swap_in_vol'] for r in m['decile_table']); vs = sum(r['swap_in_vol'] for r in v['decile_table'])\n"
    "    print('keep_in_vol (decisão) main', round(mk), 'v05', round(vk), '<-- fonte da divergência' if abs(mk-vk)>1 else '')\n"
    "    print('swap_in_vol          main', round(ms), 'v05', round(vs))\n"
    "else:\n"
    "    print('paridade total — nenhum degrau vermelho.')"
))

c.append(nbf.v4.new_markdown_cell(
    "## L8 — idiomas exclusivos de cada engine (documentação, NÃO degraus)"
))
c.append(nbf.v4.new_code_cell(
    "for eng in ('main', 'v05'):\n"
    "    notes = recs[('L5', eng)].get('l8_engine_exclusive_notes', {})\n"
    "    print('===', eng, '===')\n"
    "    for k, val in notes.items():\n"
    "        print(f'  {k}: {val}')\n"
    "\n"
    "print('\\n--- warnings capturados (nunca suprimidos) ---')\n"
    "for step in lc.STEPS:\n"
    "    for eng in ('main', 'v05'):\n"
    "        w = recs[(step, eng)]['warnings']\n"
    "        if w:\n"
    "            print(step, eng, w)"
))

with open("ladder_report.ipynb", "w", encoding="utf-8") as fh:
    nbf.write(nb, fh)
print("wrote ladder_report.ipynb")
