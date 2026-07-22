#!/usr/bin/env bash
# Orchestrates the full ablation ladder (issue #93) from a clean session.
# Usage: bash validation/ladder/run_all.sh [60k 1p5m]
set -euo pipefail
export PYTHONIOENCODING=utf-8

ladder="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$ladder/../.." && pwd)"
parent="$(dirname "$repo")"
wtMain="$parent/wt-main"
wtV05="$parent/wt-v05"
sizes=("${@:-60k 1p5m}")
declare -A N=( [60k]=60000 [1p5m]=1500000 )

git -C "$repo" worktree prune
[ -d "$wtMain" ] || git -C "$repo" worktree add "$wtMain" --detach main
if [ -d "$wtV05" ]; then git -C "$wtV05" checkout --detach feat/76-masterclass-notebook || true
else git -C "$repo" worktree add "$wtV05" --detach feat/76-masterclass-notebook; fi

for wt in "$wtMain" "$wtV05"; do
  py="$wt/.venv/bin/python"
  if [ ! -x "$py" ]; then
    python -m venv "$wt/.venv"
    "$py" -m pip install -q -e "$wt" pyarrow openpyxl
  fi
done
pyMain="$wtMain/.venv/bin/python"
pyV05="$wtV05/.venv/bin/python"

mkdir -p "$ladder/results"
cd "$ladder"

for size in ${sizes[@]}; do
  n="${N[$size]}"
  frame="shared_base_$size.parquet"
  manifest="shared_base_${size}_manifest.json"
  xlsx=(); [ "$size" = "60k" ] && xlsx=(--xlsx shared_base_60k.xlsx)
  "$pyV05" build_base.py --n "$n" --out "$frame" "${xlsx[@]}"
  "$pyMain" run_ladder_main.py --frame "$frame" --manifest "$manifest" --tag "$size"
  "$pyV05"  run_ladder_v05.py  --frame "$frame" --manifest "$manifest" --tag "$size"
  "$pyV05"  build_summary.py --tag "$size"
done

echo "done. JSONs in validation/ladder/results; open ladder_report.ipynb."
