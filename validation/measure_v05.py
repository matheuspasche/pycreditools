"""Measure the canonical flow on the release/v0.5 engine (feat/76 branch).

Run with the wt-v05 venv:
    python measure_v05.py --mode A --n 60000 --out results/v05_A_60k.json
"""

from __future__ import annotations

import inspect
import warnings

import numpy as np
import pandas as pd

import pycreditools as pct
from pycreditools import CreditPolicy, ModelEvaluator, col

import common


class V05Adapter:
    name = "v05"

    def new_policy(self, calibrated: bool = False) -> CreditPolicy:
        kwargs = {}
        if calibrated:
            # The masterclass' recommended reliability answer (PR #72): bin the
            # keep-in calibration so thin score cells don't understate swap-in PD.
            kwargs["calibration_bins"] = 5
        return CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            **kwargs,
        )

    def take_up(self, policy: CreditPolicy) -> CreditPolicy:
        # v0.5 idiom: observed outcome column, calibrated by score (ADR 0008).
        return policy.rate("Take-up", base_rate=1.0, observed_col="hired", calibrate_by="score")

    def antifraud(self, policy: CreditPolicy) -> CreditPolicy:
        # v0.5 idiom: observed 0/1 column, calibrate_by=None -> flat observed
        # rate (~0.90), risk-independent (masterclass full-funnel cell).
        return policy.rate("Anti-fraud", base_rate=1.0, observed_col="passed_antifraud", calibrate_by=None)

    def entry_filter(self):
        return (col("age") >= 18) & (col("vl_negativacao") <= 5000)

    def hf_filter(self):
        expr = None
        for c, direction, thr in common.HF_RULES:
            term = (col(c) <= thr) if direction == "lte" else (col(c) >= thr)
            expr = term if expr is None else (expr & term)
        return expr

    def compute_ks(self, df, scores, bad_col):
        return ModelEvaluator(df, scores, bad_col).compute_ks()

    def fit_risk_groups(self, *args, **kwargs):
        return pct.fit_risk_groups(*args, **kwargs)

    def suggest_hf(self, base, note):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            hf = pct.suggest_hard_filters(
                base,
                bad_col="actual_default",
                directions={
                    "vl_negativacao": "lte",
                    "vl_vencido_scr": "lte",
                    "vl_protestos": "lte",
                    "age": "gte",
                },
                hf_approval_floor=0.55,
                lift_min=1.3,
            )
        note([f"[{w.category.__name__}] {w.message}" for w in caught])
        return {
            "rules": [
                f"{r['column']} {r['direction']} {r['threshold']:g}"
                for r in hf.rule_set.to_dict("records")
            ],
            "budget": {k: float(v) for k, v in hf.budget.items()},
        }

    def extra_swap_in_facts(self, base, challenger_fn, iso_cut, note):
        """v0.5-only: swap-in PD with the naive (un-binned) calibration, to show
        how much of the gap is the PR #72 binning alone (root cause #4)."""
        naive = self.take_up(
            CreditPolicy(
                applicant_id_col="applicant_id",
                score_cols=("score_5",),
                current_approval_col="approved",
                actual_default_col="actual_default",
            )
            .filter("Hard filters", self.hf_filter())
            .cutoff("Challenger cutoff", {"score_5": float(iso_cut)}, direction="gte")
        )
        sim_data, msgs = common._simulate(naive, base)
        note(msgs)
        si = sim_data[sim_data["scenario"] == "swap_in"]
        w = si["new_approval"]
        if not float(w.sum()):
            return {"swap_in_pd_imputed_naive": float("nan")}
        return {"swap_in_pd_imputed_naive": float((si["simulated_default"] * w).sum() / w.sum())}

    def optimizer_check(self, base, target_default, note):
        """The engine's own optimize_cutoffs, called the way the masterclass
        calls it (directions=, sweep fast-path inside). Localization only —
        common.measure re-reports the metrics via .simulate()."""
        config = self.take_up(
            self.new_policy(calibrated=True).filter("Hard filters", self.hf_filter())
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            opt = pct.optimize_cutoffs(
                base,
                config,
                cutoff_steps=15,
                target_default_rate=float(target_default),
                min_approval_rate=0.15,
                directions={"score_5": "gte"},
            )
        note([f"[{w.category.__name__}] {w.message}" for w in caught])
        return {
            "cutoff": int(round(opt.best_combination["score_5"])),
            "optimizer_metrics": {
                k: float(v) for k, v in opt.metrics.items() if isinstance(v, (int, float))
            },
        }

    def engine_facts(self, base):
        rate_params = inspect.signature(CreditPolicy.rate).parameters
        opt_params = inspect.signature(pct.optimize_cutoffs).parameters
        return {
            "package_version": getattr(pct, "__version__", "n/a"),
            "rate_has_observed_col": "observed_col" in rate_params,
            "optimize_has_directions": "directions" in opt_params,
            "has_suggest_hard_filters": hasattr(pct, "suggest_hard_filters"),
            "legacy_quantile_exported": hasattr(pct, "LEGACY_APPROVAL_QUANTILE"),
            "actual_default_masked_frac": float(base["actual_default"].isna().mean()),
            "sample_data_columns": list(base.columns),
            "calibration_bins_supported": "calibration_bins"
            in inspect.signature(CreditPolicy.__init__).parameters,
        }


if __name__ == "__main__":
    common.run_cli(V05Adapter(), pct.generate_sample_data)
