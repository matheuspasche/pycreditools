"""Build ONE canonical frame (mode B) both engines read, isolating the engine.

Generator: v0.5's ``generate_sample_data`` (seed=7 by default). The frame is
the UNION of what each engine needs:
  - v0.5 needs ``market_default`` / ``passed_antifraud`` (native to v0.5).
  - main needs ``conversion_rate`` / ``take_up_rate`` — derived from score_5
    deciles with the same formula main's own generator uses:
    ``conversion_rate = 0.95 - score_decile * 0.06``.

Run with the wt-v05 venv:
    python build_shared_frame.py --n 60000 --out shared_base.parquet [--xlsx shared_base.xlsx]
"""

from __future__ import annotations

import argparse

import pandas as pd

from pycreditools import generate_sample_data


def build(n: int, seed: int) -> pd.DataFrame:
    df = generate_sample_data(n_applicants=n, seed=seed)
    df["score_decile"] = pd.qcut(df["score_5"], q=10, labels=False, duplicates="drop")
    df["conversion_rate"] = 0.95 - df["score_decile"] * 0.06
    df["take_up_rate"] = df["conversion_rate"]
    return df


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=60_000)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default="shared_base.parquet")
    p.add_argument("--xlsx", default=None, help="also dump an Excel copy for manual checks")
    args = p.parse_args()

    df = build(args.n, args.seed)
    df.to_parquet(args.out, index=False)
    print(f"shared frame: {len(df):,} rows x {len(df.columns)} cols -> {args.out}")
    if args.xlsx:
        df.to_excel(args.xlsx, index=False)
        print(f"excel copy   -> {args.xlsx}")
