# Orchestrates the full ablation ladder (issue #93) from a clean session.
# Usage: powershell -ExecutionPolicy Bypass -File validation\ladder\run_all.ps1 [-Sizes 60k,1p5m]
param([string[]]$Sizes = @("60k", "1p5m"))
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$ladder = $PSScriptRoot
$repo   = Split-Path -Parent (Split-Path -Parent $ladder)  # ladder/ is at validation/ladder
$wtMain = Join-Path (Split-Path -Parent $repo) "wt-main"
$wtV05  = Join-Path (Split-Path -Parent $repo) "wt-v05"

$N = @{ "60k" = 60000; "1p5m" = 1500000 }

# 1. Worktrees ---------------------------------------------------------------
git -C $repo worktree prune
if (-not (Test-Path $wtMain)) { git -C $repo worktree add $wtMain --detach main }
# v0.5 engine == this branch's HEAD. Refresh the detached worktree to it.
if (-not (Test-Path $wtV05)) { git -C $repo worktree add $wtV05 --detach feat/76-masterclass-notebook }
else {
    # git writes progress to stderr; under ErrorActionPreference=Stop that aborts
    # the script even on success. Neutralize just this call, gate on exit code.
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    git -C $wtV05 checkout --detach feat/76-masterclass-notebook 2>&1 | Out-Null
    $ErrorActionPreference = $prev
    if ($LASTEXITCODE -ne 0) { throw "wt-v05 checkout failed ($LASTEXITCODE)" }
}

# 2. Venvs + editable installs ----------------------------------------------
foreach ($wt in @($wtMain, $wtV05)) {
    $py = Join-Path $wt ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        python -m venv (Join-Path $wt ".venv")
        & $py -m pip install -q -e $wt pyarrow openpyxl nbformat
    }
}
$pyMain = Join-Path $wtMain ".venv\Scripts\python.exe"
$pyV05  = Join-Path $wtV05  ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force (Join-Path $ladder "results") | Out-Null
Set-Location $ladder

foreach ($size in $Sizes) {
    $n = $N[$size]
    $frame    = "shared_base_$size.parquet"
    $manifest = "shared_base_${size}_manifest.json"
    # 3. ONE base per size (v0.5 generator, seed=7). xlsx gabarito only for 60k.
    $xlsx = if ($size -eq "60k") { @("--xlsx", "shared_base_60k.xlsx") } else { @() }
    & $pyV05 build_base.py --n $n --out $frame @xlsx
    # 4. Both engines, every ladder step, reading the SAME parquet.
    & $pyMain run_ladder_main.py --frame $frame --manifest $manifest --tag $size
    & $pyV05  run_ladder_v05.py  --frame $frame --manifest $manifest --tag $size
    # 5. Render the committed summary (raw JSONL stays local/gitignored).
    & $pyV05  build_summary.py --tag $size
}

# 6. Regenerate the local notebooks from their committed generators (the .ipynb
#    themselves are gitignored — git carries the generator, not the JSON).
& $pyV05 _build_notebook.py
& $pyV05 _build_decomp_notebook.py

Write-Host "done. JSONs in validation/ladder/results; open ladder_report.ipynb."
# Cleanup (optional): git worktree remove wt-main wt-v05 when finished.
