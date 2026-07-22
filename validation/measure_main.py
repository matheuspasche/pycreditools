"""Measure the canonical flow on the main-branch engine (v0.4.x).

Run with the wt-main venv:
    python measure_main.py --mode A --n 60000 --out results/main_A_60k.json
"""

from __future__ import annotations

import inspect

import pycreditools as pct  # noqa: F401 (used via adapter methods)
from pycreditools import CreditPolicy, ModelEvaluator, col

import common


class MainAdapter:
    name = "main"

    def new_policy(self, calibrated: bool = False) -> CreditPolicy:
        # Equal-conditions protocol: the calibration_bins knob exists on BOTH
        # branches, so the challenger runs with bins=5 on both. The decile
        # default (the published main/README flow) is kept as a counterfactual
        # in extra_swap_in_facts.
        kwargs = {"calibration_bins": 5} if calibrated else {}
        return CreditPolicy(
            applicant_id_col="applicant_id",
            score_cols=("score_5",),
            current_approval_col="approved",
            actual_default_col="actual_default",
            **kwargs,
        )

    def take_up(self, policy: CreditPolicy) -> CreditPolicy:
        # main idiom: propensity column as a rate multiplier (README flow).
        return policy.rate("Take-up", base_rate=1.0, variable="conversion_rate")

    def antifraud(self, policy: CreditPolicy) -> CreditPolicy:
        # main idiom: flat pass rate (the generator's passed_antifraud is
        # Bernoulli(0.90), risk-independent — 0.90 is its expected rate).
        return policy.rate("Anti-fraud", base_rate=0.90)

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
        return None  # no suggester on main; fixed HF set used instead.

    def extra_swap_in_facts(self, base, challenger_fn, iso_cut, note):
        """Counterfactual: main with the DECILE default (the published
        main/README flow), since the equal-conditions run uses bins=5."""
        deciles = self.take_up(
            CreditPolicy(
                applicant_id_col="applicant_id",
                score_cols=("score_5",),
                current_approval_col="approved",
                actual_default_col="actual_default",
            )
            .filter("Hard filters", self.hf_filter())
            .cutoff("Challenger cutoff", {"score_5": float(iso_cut)}, direction="gte")
        )
        sim_data, msgs = common._simulate(deciles, base)
        note(msgs)
        si = sim_data[sim_data["scenario"] == "swap_in"]
        w = si["new_approval"]
        if not float(w.sum()):
            return {"swap_in_pd_imputed_deciles": float("nan")}
        return {"swap_in_pd_imputed_deciles": float((si["simulated_default"] * w).sum() / w.sum())}

    def optimizer_check(self, base, target_default, note):
        """main's own optimize_cutoffs (no directions= parameter on this
        branch). Localization only — metrics re-reported via .simulate()."""
        import warnings

        config = self.take_up(
            self.new_policy(calibrated=True).filter("Hard filters", self.hf_filter())
        ).stress(1.5)  # equal-conditions protocol: stress x1.5 always
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            opt = pct.optimize_cutoffs(
                base,
                config,
                cutoff_steps=15,
                target_default_rate=float(target_default),
                min_approval_rate=0.15,
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
    common.run_cli(MainAdapter(), pct.generate_sample_data)
