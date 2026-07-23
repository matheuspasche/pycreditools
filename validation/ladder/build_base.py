"""Build the ONE canonical base for the ablation ladder (issue #93).

Principle #1 (uma base): every ladder step, on both engines, reads THIS parquet.
No ladder script ever calls ``generate_sample_data`` on its own. The SHA-256 of
the parquet goes into every result JSON so drift is impossible to hide.

What this script computes OUTSIDE the engines (so both sides share identical
bytes via ``variable=`` — never ``observed_col``):

  * ``take_up_rate``  — observed conversion ``hired / approved`` by risk band
    (decile of ``score_5`` over the APPROVED population), imputed as a column on
    every row. Shape is adverse selection: worse score -> higher conversion.
    This is the ONLY take-up source for both engines, always via
    ``rate(..., variable="take_up_rate")``.
  * ``antifraud_rate`` — the fixed observed pass rate ``mean(passed_antifraud)``
    (~0.90), stored as a scalar in the manifest. Both engines use it as
    ``rate(..., base_rate=<value>)``. No ``observed_col`` anywhere.

Run with the wt-v05 venv (the v0.5 generator is canonical, seed=7):
    python build_base.py --n 60000    --out shared_base_60k.parquet
    python build_base.py --n 1500000  --out shared_base_1p5m.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from pycreditools import generate_sample_data

SEED = 7
LEGACY_QUANTILE = 0.78
SCORE_COL = "score_5"
N_DECILES = 10
# Fixed challenger cutoff: median of score_5. Frozen in the manifest so both
# engines gate on the identical value at every ladder step (principle #3).
CUTOFF_QUANTILE = 0.50


def build(n: int, seed: int) -> tuple[pd.DataFrame, dict]:
    df = generate_sample_data(n_applicants=n, seed=seed)

    # take_up_rate imputed by risk band, OUTSIDE the engines.
    approved = df["approved"] == 1
    ap = df.loc[approved].copy()
    ap["_decile"] = pd.qcut(ap[SCORE_COL], N_DECILES, labels=False, duplicates="drop")
    conv_by_decile = ap.groupby("_decile")["hired"].mean()

    # Decile edges from the APPROVED population, applied to the whole frame so
    # swap-in rows (never approved historically) also receive a conversion rate.
    edges = np.quantile(ap[SCORE_COL], np.linspace(0, 1, N_DECILES + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    df["score_decile"] = pd.cut(df[SCORE_COL], bins=np.unique(edges), labels=False, include_lowest=True)
    df["take_up_rate"] = df["score_decile"].map(conv_by_decile.to_dict()).astype(float)
    # Rows outside any approved-decile band (extreme scores) fall back to the
    # nearest edge rate so no NaN take-up leaks into a rate stage.
    df["take_up_rate"] = df["take_up_rate"].ffill().bfill()

    antifraud_rate = float(df["passed_antifraud"].mean())
    legacy_cutoff = float(df["legacy_score"].quantile(LEGACY_QUANTILE))
    challenger_cutoff = int(round(float(df[SCORE_COL].quantile(CUTOFF_QUANTILE))))

    manifest = {
        "seed": seed,
        "n": int(len(df)),
        "score_col": SCORE_COL,
        "cutoff_quantile": CUTOFF_QUANTILE,
        "challenger_cutoff": challenger_cutoff,
        "legacy_quantile": LEGACY_QUANTILE,
        "legacy_cutoff": legacy_cutoff,
        "antifraud_rate": antifraud_rate,
        "take_up_curve_by_decile": {int(k): float(v) for k, v in conv_by_decile.items()},
        "n_deciles": N_DECILES,
    }
    return df, manifest


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=60_000)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--out", default="shared_base_60k.parquet")
    p.add_argument("--xlsx", default=None, help="also dump an Excel gabarito (skip for 1.5M)")
    args = p.parse_args()

    df, manifest = build(args.n, args.seed)
    out = Path(args.out)
    df.to_parquet(out, index=False)
    manifest["sha256"] = sha256_of(out)
    manifest["parquet"] = out.name

    manifest_path = out.with_name(out.stem + "_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    print(f"base: {len(df):,} rows x {len(df.columns)} cols -> {out}")
    print(f"  sha256           {manifest['sha256']}")
    print(f"  challenger cutoff {manifest['challenger_cutoff']} ({SCORE_COL} q{CUTOFF_QUANTILE})")
    print(f"  antifraud_rate    {manifest['antifraud_rate']:.4f}")
    print(f"  manifest         -> {manifest_path}")

    if args.xlsx:
        df.to_excel(args.xlsx, index=False)
        print(f"  xlsx gabarito    -> {args.xlsx}")
