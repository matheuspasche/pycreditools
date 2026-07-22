"""Ladder runner — release/v0.5 engine (feat/76 branch). Thin adapter: hands
ladder_common the branch's CreditPolicy/col and the L8 doc notes.

Run with the wt-v05 venv:
    python run_ladder_v05.py --frame shared_base_60k.parquet \
        --manifest shared_base_60k_manifest.json --tag 60k
"""

from __future__ import annotations

import pycreditools as pct
from pycreditools import CreditPolicy, col

import ladder_common

# L8 — engine-exclusive idioms on v0.5 (NOT ladder rungs; documentation only).
L8_NOTES = {
    "rate_take_up_idiom": "observed_col= + calibrate_by= available (ADR 0008); the ladder "
    "deliberately uses the common denominator variable= instead, identical to main",
    "keep_in_bypass_detection": "declarative: observed_col present -> keep-in uses observed "
    "value; absent -> 1.0. No name/position heuristic.",
    "optimize_cutoffs_directions": "directions= parameter present",
    "suggest_hard_filters": "present (PR #73); picks the fixed HF set used here",
    "calibration_reliability_warning": "CalibrationReliabilityWarning emitted on thin cells "
    "(captured in each step's warnings, never suppressed)",
}

if __name__ == "__main__":
    ladder_common.run_cli("v05", pct, CreditPolicy, col, L8_NOTES)
