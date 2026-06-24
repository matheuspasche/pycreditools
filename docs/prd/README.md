# Pycreditools Studio — PRDs

Detailed product requirements for rebuilding the GUI as a **Streamlit** studio:
beautiful, lightweight, dark-fintech, **100% no-code**, with **full parity** to the
`pycreditools` public API. Intended to be implemented one PRD at a time (each is a
self-contained task).

**Implementing agents start with [`IMPLEMENTATION_GUIDE.md`](IMPLEMENTATION_GUIDE.md)** —
rules of engagement, the per-PRD workflow, the **4-layer automated validation**
(ruff · pytest logic · Streamlit AppTest · parity), the **blocking human gate**,
commit discipline, the test scaffold, and a ready-to-paste **kickoff prompt** for a
fresh session.

Then **[`00-overview.md`](00-overview.md)** — locked decisions, architecture, file
layout, session-state schema, design system, API→feature map, cross-cutting
conventions, build order and global acceptance criteria. Every other PRD references it.

Each per-page PRD ends with a **"Validação & Gate (BLOQUEANTE)"** section:
Definition-of-Done checklist, the specific automated tests, the visual-verification
script, and the gate question. **An agent never advances past a PRD without all 4
test layers green AND the owner's explicit "aprovado".**

## Index (read in build order)

| # | PRD | Wraps / covers |
|---|---|---|
| — | [Implementation Guide](IMPLEMENTATION_GUIDE.md) | **read first** — rules, 4-layer validation, blocking gate, kickoff prompt |
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
- **Single-user, local** (`streamlit run`) — but built to be server-publishable
  without rework (see `00-overview.md` §13).
- **Two-layer architecture** (no-rework insurance, `00-overview.md` §4b): a
  framework-agnostic **core** `pycreditools/studio/` (no streamlit) + a thin
  Streamlit **skin** `pycreditools/gui/`. If Streamlit is ever outgrown, the core is
  reused behind FastAPI; only the skin is rewritten.
- Old **Dash GUI is replaced** (deleted) — Streamlit skin lives in `src/pycreditools/gui/`.
- Stress = **flat aggravation factor only**; angulated/linear/monotonic stress and
  any user-typed Python are **out of v1** (see `00-overview.md` §10).
- Data: sample-data generator · column auto-detection · ~1M-row support · projects.
- Deployment page: export JSON **and** batch-score an uploaded file.

## Parity oracle

`run_v14_benchmark.py` (repo root) reproduces the v14 notebook numbers in pure
code — use it to verify the studio's funnel volumes, legacy approval/bad rate and
trade-off neutral scenario.
