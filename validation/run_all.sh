#!/usr/bin/env bash
# Orchestrates the full parity measurement (issue #91) from a clean session.
set -euo pipefail
export PYTHONIOENCODING=utf-8

VAL="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$VAL")"
WT_MAIN="$(dirname "$REPO")/wt-main"
WT_V05="$(dirname "$REPO")/wt-v05"

git -C "$REPO" worktree prune
# --detach on both sides: plain `worktree add <dir> main` fails whenever main
# is already checked out somewhere (including a stale wt-main deleted by hand).
[ -d "$WT_MAIN" ] || git -C "$REPO" worktree add "$WT_MAIN" --detach main
[ -d "$WT_V05" ]  || git -C "$REPO" worktree add "$WT_V05" --detach feat/76-masterclass-notebook

for WT in "$WT_MAIN" "$WT_V05"; do
    if [ ! -x "$WT/.venv/bin/python" ] && [ ! -x "$WT/.venv/Scripts/python.exe" ]; then
        python -m venv "$WT/.venv"
        PY="$WT/.venv/bin/python"; [ -x "$PY" ] || PY="$WT/.venv/Scripts/python.exe"
        "$PY" -m pip install -q -e "$WT" pyarrow matplotlib seaborn openpyxl
    fi
done
PY_MAIN="$WT_MAIN/.venv/bin/python"; [ -x "$PY_MAIN" ] || PY_MAIN="$WT_MAIN/.venv/Scripts/python.exe"
PY_V05="$WT_V05/.venv/bin/python";   [ -x "$PY_V05" ]  || PY_V05="$WT_V05/.venv/Scripts/python.exe"

cd "$VAL"
mkdir -p results

"$PY_V05" build_shared_frame.py --n 60000 --seed 7 --out shared_base.parquet --xlsx shared_base.xlsx

"$PY_MAIN" measure_main.py --mode A --n 60000 --out results/main_A_60k.json
"$PY_MAIN" measure_main.py --mode A --n 20000 --out results/main_A_20k.json
"$PY_MAIN" measure_main.py --mode B --frame shared_base.parquet --out results/main_B_60k.json
"$PY_V05"  measure_v05.py  --mode A --n 60000 --out results/v05_A_60k.json
"$PY_V05"  measure_v05.py  --mode A --n 20000 --out results/v05_A_20k.json
"$PY_V05"  measure_v05.py  --mode B --frame shared_base.parquet --out results/v05_B_60k.json

echo "done. JSONs in validation/results; open masterclass_engine_parity.ipynb."
