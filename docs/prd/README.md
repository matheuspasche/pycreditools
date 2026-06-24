# Pycreditools Studio — PRDs

Detailed product requirements for rebuilding the GUI as a **Streamlit** studio:
beautiful, lightweight, dark-fintech, **100% no-code**, with **full parity** to the
`pycreditools` public API. Intended to be implemented one PRD at a time (each is a
self-contained task).

**Start with [`00-overview.md`](00-overview.md)** — it defines the locked
decisions, architecture, file layout, session-state schema, design system,
API→feature map, cross-cutting conventions, build order and global acceptance
criteria. Every other PRD references it.

## Index (read in build order)

| # | PRD | Wraps / covers |
|---|---|---|
| 00 | [Overview / Master](00-overview.md) | vision, architecture, design system, state, API map, non-goals |
| 01 | [App Shell & Design System](01-app-shell-and-design-system.md) | theme, navigation, components, `state.py` |
| 02 | [Data Ingestion & Projects](02-data-ingestion-and-projects.md) | upload / `generate_sample_data`, column auto-detect, save/load projects |
| 03 | [Score Evaluation](03-score-evaluation.md) | `ModelEvaluator` (KS, decile table) |
| 04 | [Policy Studio](04-policy-studio.md) | `CreditPolicy` builder (filters/cutoff/rate/flat stress), live funnel |
| 05 | [Simulation & Impact](05-simulation-and-impact.md) | `run_simulation`, quadrants, `summarize_results`, `compare_policies` |
| 06 | [Trade-off & Scenarios](06-tradeoff-and-scenarios.md) | `TradeoffAnalyzer`, efficient frontier, scenario picker |
| 07 | [Cutoff Optimization](07-cutoff-optimization.md) | `optimize_cutoffs`, Pareto frontier |
| 08 | [Risk Grouping & Ratings](08-risk-grouping-and-ratings.md) | `fit_risk_groups`, pairwise, vintage stability |
| 09 | [Risk Screening](09-risk-screening.md) | `fit_risk_segments` (IV sub-segments) |
| 10 | [Crash Test](10-crash-test.md) | `vary_stress_aggravation`, breakeven factor |
| 11 | [Deployment & Scoring](11-deployment-and-scoring.md) | `DeploymentPolicy` export + batch `predict` |

## Locked decisions (summary)

- **Streamlit** · **Plotly** charts · **dark fintech** theme.
- **100% no-code**; custom-function notebook steps become presets.
- **Full parity** with the package in v1.
- **Single-user, local** (`streamlit run`).
- Old **Dash GUI is replaced** (deleted) — Streamlit lives in `src/pycreditools/gui/`.
- Stress = **flat aggravation factor only**; angulated/linear/monotonic stress and
  any user-typed Python are **out of v1** (see `00-overview.md` §10).
- Data: sample-data generator · column auto-detection · ~1M-row support · projects.
- Deployment page: export JSON **and** batch-score an uploaded file.

## Parity oracle

`run_v14_benchmark.py` (repo root) reproduces the v14 notebook numbers in pure
code — use it to verify the studio's funnel volumes, legacy approval/bad rate and
trade-off neutral scenario.
