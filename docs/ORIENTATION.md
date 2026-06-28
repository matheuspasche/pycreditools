# Project orientation — what ships, what's the harness, and where we're going

> Read this to understand the **shape** of the repo and the **direction** of the
> work. It is deliberately short and durable: specifics live in ADRs and PRDs, this
> file only frames them. When the direction pivots, update the "Where we're going"
> section and record the decision as an ADR — never silently rewrite history here.

## Two layers (the separation)

This repo contains **two distinct things** that happen to live together because the
second exists only to build the first:

### 1. The package — *ships to PyPI*

`src/pycreditools/` is the product: a credit-risk policy engine
(`CreditPolicy`, `run_simulation`, `fit_risk_groups`, …) plus the Streamlit **Studio**
skin (`gui/`) over its framework-agnostic **core** (`studio/`).

This — and **only** this — is what users install. The wheel is pinned in
`pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/pycreditools"]
```

Nothing outside `src/pycreditools/` is ever in the distribution.

### 2. The development harness — *never ships*

Everything else is intrinsic to *developing* the package but is **not part of its
functionality**:

| Path | What it is |
|---|---|
| `docker/`, `docker-compose.yml` | the dockerized "ralph loop" that runs Claude Code headless to implement issues |
| `.ralph/` | ralph loop runtime logs/state (gitignored) |
| `.agents/skills/` | agent skill definitions used while developing |
| `scripts/` | board/queue tooling (`prd_board.py`, `github_board.py`) |
| `docs/prd/`, `docs/adr/`, `docs/redesign/` | the design record (PRDs, decisions, specs) |
| `tests/`, `run_v14_benchmark.py`, `dataset_v14.csv` | tests + parity oracle |
| `CLAUDE.md`, `.claude/` | Claude Code project config |

The boundary is enforced two ways: the build only packages `src/pycreditools`, and a
test asserts the studio **core** never imports Streamlit (so the engine/core stays
framework-agnostic and re-hostable). See `docs/prd/00-overview.md` §4b.

**Rule of thumb:** if it changes what a `pip install pycreditools` user can do, it
belongs in `src/pycreditools/`. Otherwise it's harness.

## Where we came from

- **v0.x engine:** the credit-risk library (policies, simulation, swap analysis,
  risk grouping, trade-off, optimization, crash test, deployment export).
- **First GUI:** a Dash + Mantine app — "ugly and very limited", since deleted.
- **Studio v1:** a Streamlit studio rebuilt as **PRDs 01–11** (one analysis page
  each: Ingestion → Score Eval → Policy Studio → Simulation → Trade-off →
  Optimization → Risk Grouping → Screening → Crash Test → Deployment), implemented
  largely by the ralph loop, PRD-by-PRD, tracked in `docs/prd/PROGRESS.md`. v1 is
  "good for a mock" but conceptually a linear pipeline of disconnected dashboards.

## Where we're going (the north star)

**Studio v2 — a central Bancada.** The owner's critique reframed the product: policy
design is *coupled* (every knob impacts every readout) and *comparative* (a candidate
policy vs a base), not a row of dashboards. The target:

```
Ingestion → Score Evaluation → Bancada (the heart) → Risk Grouping → Deploy
```

- The **Bancada** is one live workbench: assemble a policy and instantly see the
  funnel + comparison-vs-base + aggravation, opening with suggested scenarios.
- It adapts to how much of the *vigente* policy the data exposes (comparison tiers).
- Matriciation/complementarity is first-class; the engine is never touched.

The full design is **PRD 12** (`docs/prd/12-studio-v2-bancada-redesign.md`, GitHub
issue #16), broken into vertical-slice issues, with the load-bearing decisions in
`docs/adr/0001`–`0006`.

## How direction survives pivots

Decisions are recorded as **ADRs** (`docs/adr/NNNN-*.md`). A pivot does **not** edit
old ADRs — it adds a new one that supersedes them, so the trail of *why* stays
legible. PRDs describe *what* to build now; ADRs preserve *why we chose it*; this file
is the 60-second map. If you ever can't tell "where are we and why", these three, in
that order, should answer it.
