"""Render the committed, human-readable ladder summary from the local JSONL data.

The raw per-step records live in ``results/*.jsonl`` (gitignored, regenerable).
Git tracks ONLY ``ladder_summary.md`` — the green/red matrix, the v0.5 decile
table, and the first-red minimal diff — so a reviewer sees the result without the
raw dumps and without re-running the ladder. Also emits ``results/ladder_metrics.csv``
(flat, gitignored) for quick local inspection.

    python build_summary.py --tag 1p5m
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import ladder_common as lc


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", default="1p5m")
    p.add_argument("--table-step", default="L4", help="which step's v0.5 decile table to show")
    p.add_argument("--outdir", default="results")
    args = p.parse_args()

    recs = lc.load_results(args.tag, args.outdir)
    if not recs:
        raise SystemExit(f"no results for tag {args.tag} (run run_all first)")
    n = next(iter(recs.values()))["n"]
    sha = next(iter(recs.values()))["base_sha256"]

    lines: list[str] = []
    add = lines.append
    add(f"# Escada de ablação — resumo (tag `{args.tag}`)\n")
    add(f"Gerado por `build_summary.py` a partir de `results/*.jsonl` (gitignored). "
        f"n={n:,} · base SHA-256 `{sha[:16]}…`\n")

    # ── green/red matrix ────────────────────────────────────────────────────
    add("## Matriz de paridade main × v0.5\n")
    add("| degrau | adiciona | veredito |")
    add("|---|---|---|")
    first_red = None
    csv_rows = []
    for step in lc.STEPS:
        m = recs.get((step, "main"))
        v = recs.get((step, "v05"))
        if not (m and v):
            continue
        cmp = lc.compare(m["measured"], v["measured"], step)
        reds = [r["invariant"] for r in cmp if r["verdict"] == "red"]
        if reds and first_red is None:
            first_red = (step, reds[0])
        verdict = "🟩 verde" if not reds else "🟥 " + ", ".join(reds)
        add(f"| {step} | {lc.STEP_ADDS[step]} | {verdict} |")
        for eng, rec in (("main", m), ("v05", v)):
            mm = rec["measured"]
            csv_rows.append({
                "tag": args.tag, "engine": eng, "step": step,
                "approval": mm.get("approval"), "contracted": mm.get("contracted"),
                "blended_default": mm.get("blended_default"),
                "segmented_default": mm.get("segmented_default"),
            })
    add(f"\n**Primeiro degrau vermelho:** {first_red}\n")

    # ── v0.5 decile table ───────────────────────────────────────────────────
    step = args.table_step
    v = recs.get((step, "v05"))
    if v:
        m = v["measured"]
        add(f"## Tabela por decil — v0.5, degrau {step} ({lc.STEP_ADDS[step]})\n")
        add("| decil | keep_vol | keep_dec | keep_in_inad | swap_vol | swap_in_inad | conv | sw/keep |")
        add("|---|---|---|---|---|---|---|---|")
        for r in m["decile_table"]:
            add(f"| {r['decile']} | {r['keep_in_vol']:.0f} | {r['keep_in_vol_decision']:.0f} "
                f"| {r['keep_in_inad']:.4f} | {r['swap_in_vol']:.0f} | {r['swap_in_inad']:.4f} "
                f"| {r['conversion']:.4f} | {r['swap_over_keep']:.3f} |")
        s = m["sanity"]
        add(f"\nblended `{m['blended_default']:.4f}` · sumproduct ok `{s['sumproduct_matches_blended']}` "
            f"· stress_ratio ok `{s['stress_ratio_ok']}`\n")

    # ── minimal diff of the first red step ──────────────────────────────────
    if first_red:
        step = first_red[0]
        m = recs[(step, "main")]["measured"]
        v = recs[(step, "v05")]["measured"]
        mk = sum(r["keep_in_vol_decision"] for r in m["decile_table"])
        vk = sum(r["keep_in_vol_decision"] for r in v["decile_table"])
        add(f"## Diff mínimo — {step}\n")
        add(f"- approval pré-rate: main `{m['approval']:.5f}` · v05 `{v['approval']:.5f}` "
            f"(igual: `{abs(m['approval'] - v['approval']) < 1e-9}`)")
        add(f"- quadrantes iguais: `{m['quadrant_counts'] == v['quadrant_counts']}`")
        add(f"- contracted: main `{m['contracted']:.0f}` · v05 `{v['contracted']:.0f}` "
            f"· delta `{v['contracted'] - m['contracted']:.0f}`")
        add(f"- keep-in contratado (decisão): main `{mk:.0f}` · v05 `{vk:.0f}`\n")

    Path("ladder_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote ladder_summary.md")

    csv_path = Path(args.outdir) / "ladder_metrics.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        w.writeheader()
        w.writerows(csv_rows)
    print(f"wrote {csv_path} (gitignored)")


if __name__ == "__main__":
    main()
