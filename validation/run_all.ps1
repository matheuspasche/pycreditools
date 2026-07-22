# Orchestrates the full parity measurement (issue #91) from a clean session.
# Usage: powershell -ExecutionPolicy Bypass -File validation\run_all.ps1
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$repo = Split-Path -Parent $PSScriptRoot   # repo root (validation/ lives at root)
$val  = $PSScriptRoot
$wtMain = Join-Path (Split-Path -Parent $repo) "wt-main"
$wtV05  = Join-Path (Split-Path -Parent $repo) "wt-v05"

# 1. Worktrees ---------------------------------------------------------------
git -C $repo worktree prune
# --detach on both sides: plain `worktree add <dir> main` fails whenever main
# is already checked out somewhere (including a stale wt-main deleted by hand).
if (-not (Test-Path $wtMain)) { git -C $repo worktree add $wtMain --detach main }
if (-not (Test-Path $wtV05))  { git -C $repo worktree add $wtV05 --detach feat/76-masterclass-notebook }

# 2. Venvs + editable installs ----------------------------------------------
foreach ($wt in @($wtMain, $wtV05)) {
    $py = Join-Path $wt ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        python -m venv (Join-Path $wt ".venv")
        & $py -m pip install -q -e $wt pyarrow matplotlib seaborn openpyxl
    }
}
$pyMain = Join-Path $wtMain ".venv\Scripts\python.exe"
$pyV05  = Join-Path $wtV05  ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force (Join-Path $val "results") | Out-Null
Set-Location $val

# 3. Shared frame (mode B) + Excel copy for manual conferencia ---------------
& $pyV05 build_shared_frame.py --n 60000 --seed 7 --out shared_base.parquet --xlsx shared_base.xlsx

# 4. Measurements -------------------------------------------------------------
& $pyMain measure_main.py --mode A --n 60000 --out results/main_A_60k.json
& $pyMain measure_main.py --mode A --n 20000 --out results/main_A_20k.json
& $pyMain measure_main.py --mode B --frame shared_base.parquet --out results/main_B_60k.json
& $pyV05  measure_v05.py  --mode A --n 60000 --out results/v05_A_60k.json
& $pyV05  measure_v05.py  --mode A --n 20000 --out results/v05_A_20k.json
& $pyV05  measure_v05.py  --mode B --frame shared_base.parquet --out results/v05_B_60k.json

Write-Host "done. JSONs in validation/results; open masterclass_engine_parity.ipynb."
# Cleanup (optional): git worktree remove wt-main / wt-v05 when finished.
