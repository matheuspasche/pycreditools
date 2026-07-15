"""PROTOTYPE — throwaway TUI shell over suggester.py (wayfinder ticket #60).

Run:  python prototypes/hf_suggester/tui.py

Turn the two knobs the rule is made of and watch which hard filters survive.
"""

from __future__ import annotations

import sys

import pandas as pd

from pycreditools import generate_sample_data
from suggester import Knobs, near_misses, strategy_table, suggest

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
RED = "\x1b[31m"
RESET = "\x1b[0m"

# Declared, never inferred. Cadastral / scraper variables only — the cheap ones.
DIRECTIONS = {
    "vl_negativacao": "lte",
    "vl_vencido_scr": "lte",
    "vl_protestos": "lte",
    "age": "gte",
    "income": "gte",
    "legacy_score": "gte",  # a score, on purpose: it should lose on volume, not lift
}


def load() -> tuple[pd.DataFrame, pd.DataFrame]:
    base = generate_sample_data(n_applicants=60_000, seed=42)
    contracted = base[base["hired"] == 1]
    return base, contracted


def render(base: pd.DataFrame, contracted: pd.DataFrame, table: pd.DataFrame, knobs: Knobs) -> None:
    print("\033[2J\033[H", end="")
    print(f"{BOLD}HF suggester — protótipo #60{RESET}")
    print(
        f"{DIM}base {len(base):,} | contratados {len(contracted):,} "
        f"({len(contracted) / len(base):.1%}) | inad observada "
        f"{contracted['actual_default'].mean():.2%}{RESET}"
    )
    print(
        f"{DIM}lift medido só entre contratados — actual_default é NaN para o resto (viés de seleção){RESET}\n"
    )

    print(
        f"{BOLD}regra{RESET}  lift >= {BOLD}{knobs.lift_min:.2f}x{RESET}   "
        f"corta <= {BOLD}{knobs.max_cut:.1%}{RESET}   "
        f"maus_rej >= {BOLD}{knobs.min_rejected_bads}{RESET}   "
        f"IV >= {DIM}{knobs.iv_min}{RESET}\n"
    )

    picks = suggest(table, knobs)
    header = (
        f"{'coluna':<16}{'corte':>12}{'vol_cort':>10}{'lift':>8}"
        f"{'inad_rej':>10}{'maus_rej':>10}{'inad_apr':>10}{'ganho_pp':>10}"
    )
    print(f"{BOLD}{GREEN}SUGERIDOS{RESET}")
    print(f"{DIM}{header}{RESET}")
    if picks.empty:
        print(f"{DIM}  (nenhum candidato sobrevive à regra){RESET}")
    for _, r in picks.iterrows():
        op = ">" if r["direction"] == "lte" else "<"
        print(
            f"{r['column']:<16}{op + ' ' + f'{r.threshold:,.0f}':>12}"
            f"{r['cut_volume']:>9.2%}{r['lift']:>7.2f}x"
            f"{r['default_rejected']:>10.1%}{int(r['bads_rejected']):>10}"
            f"{r['default_approved']:>10.2%}{r['default_avoided_pp']:>10.2f}"
        )

    misses = near_misses(table, knobs)
    print(f"\n{BOLD}{RED}REPROVADOS{RESET} {DIM}(melhor candidato de cada coluna, e por quê){RESET}")
    for _, r in misses.iterrows():
        op = ">" if r["direction"] == "lte" else "<"
        print(
            f"{r['column']:<16}{op + ' ' + f'{r.threshold:,.0f}':>12}"
            f"{r['cut_volume']:>9.2%}{r['lift']:>7.2f}x"
            f"{r['default_rejected']:>10.1%}{int(r['bads_rejected']):>10}"
            f"{'':>10}   {DIM}{r['reason']}{RESET}"
        )

    grids = table.groupby("column")["grid"].first()
    collapsed = [c for c, g in grids.items() if g != "quantile"]
    if collapsed:
        print(
            f"\n{DIM}grid de quantis colapsou (coluna zero-inflada), caiu p/ valores distintos: "
            f"{', '.join(collapsed)}{RESET}"
        )

    print(
        f"\n{BOLD}[l]{RESET}{DIM} lift -{RESET}  {BOLD}[L]{RESET}{DIM} lift +{RESET}  "
        f"{BOLD}[c]{RESET}{DIM} corte -{RESET}  {BOLD}[C]{RESET}{DIM} corte +{RESET}  "
        f"{BOLD}[b]{RESET}{DIM} maus -{RESET}  {BOLD}[B]{RESET}{DIM} maus +{RESET}  "
        f"{BOLD}[q]{RESET}{DIM} sair{RESET}"
    )


def main() -> None:
    base, contracted = load()
    knobs = Knobs()
    table = strategy_table(contracted, "actual_default", DIRECTIONS, knobs)

    while True:
        render(base, contracted, table, knobs)
        key = sys.stdin.readline().strip()
        if key == "q":
            break
        elif key == "l":
            knobs = Knobs(**{**knobs.__dict__, "lift_min": max(1.0, knobs.lift_min - 0.1)})
        elif key == "L":
            knobs = Knobs(**{**knobs.__dict__, "lift_min": knobs.lift_min + 0.1})
        elif key == "c":
            knobs = Knobs(**{**knobs.__dict__, "max_cut": max(0.005, knobs.max_cut - 0.01)})
        elif key == "C":
            knobs = Knobs(**{**knobs.__dict__, "max_cut": min(1.0, knobs.max_cut + 0.01)})
        elif key == "b":
            knobs = Knobs(**{**knobs.__dict__, "min_rejected_bads": max(0, knobs.min_rejected_bads - 10)})
        elif key == "B":
            knobs = Knobs(**{**knobs.__dict__, "min_rejected_bads": knobs.min_rejected_bads + 10})


if __name__ == "__main__":
    main()
