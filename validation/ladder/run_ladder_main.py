"""Ladder runner — main-branch engine (v0.4.x). Adapter is thin: it only hands
ladder_common the branch's CreditPolicy/col and the L8 doc notes. Zero policy
logic lives here (principle: adapters carry syntax, not decisions).

Run with the wt-main venv:
    python run_ladder_main.py --frame shared_base_60k.parquet \
        --manifest shared_base_60k_manifest.json --tag 60k
"""

from __future__ import annotations

import pycreditools as pct
from pycreditools import CreditPolicy, col

import ladder_common

# L8 — engine-exclusive idioms on main (NOT ladder rungs; documentation only).
L8_NOTES = {
    "rate_take_up_idiom": "propensity column via variable=; no observed_col/calibrate_by API",
    "keep_in_bypass_detection": "RateStage bypass keyed by name/position (stages.py): "
    "stage name in {conversao, conversion, hired, take_up, take_up_rate}, calibrate=True, "
    "or last RateStage. A reorder can silently reassign the keep-in bypass.",
    "optimize_cutoffs_directions": "no directions= parameter on this branch",
    "suggest_hard_filters": "absent on main",
}

if __name__ == "__main__":
    ladder_common.run_cli("main", pct, CreditPolicy, col, L8_NOTES)
