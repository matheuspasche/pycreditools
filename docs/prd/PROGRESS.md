# PROGRESS — which PRD to implement (single source of truth)

> This file is the **work queue**. A fresh agent reads it to know which PRD to do.
> Each agent updates its row's **Status** as it goes. Do not track progress
> anywhere else.

## 👉 Which PRD do I implement now?

**Your PRD = the FIRST row in the table below whose Status is NOT `DONE`.**

Then handle its current status:
- **`TODO`** → this is your PRD. First confirm every PRD listed in its
  **Depends on** column is already `DONE` (the row order guarantees this — if a
  dependency is somehow not `DONE`, **STOP** and tell the owner). Then **mark it
  `IN PROGRESS`** (see below) and implement it.
- **`IN PROGRESS`** → a previous session already started this PRD. Read what
  exists in the repo, **continue/finish it** — do not restart from scratch unless
  it's empty or broken. Don't skip to a later PRD.
- **`AWAITING APPROVAL`** → this PRD is implemented and its 4 validation layers
  passed, but the owner hasn't approved yet. **Do NOT re-implement and do NOT start
  the next PRD.** Re-show the Gate Report and ask the owner to approve.

Never work on more than one PRD. Never start the next row until the current one is
`DONE`.

## How to update your row

1. **On start** (status was `TODO`): set Status → `IN PROGRESS`, then
   `git commit -m "chore(studio): start PRD <NN>"` (PROGRESS.md only).
2. **When all 4 validation layers are green** (guide §3): set Status →
   `AWAITING APPROVAL`, produce the **Gate Report** (guide §4), and **STOP**.
3. **After the owner replies "aprovado"**: set Status → `DONE`, fill the **Done**
   date (YYYY-MM-DD), then `git commit -m "chore(studio): PRD <NN> approved"`.
   **STOP** — do not begin the next PRD in this session.

If the owner requests changes instead of approving: keep Status `AWAITING APPROVAL`,
apply the fixes, re-run all 4 layers, re-issue the Gate Report.

## Status legend
`TODO` · `IN PROGRESS` · `AWAITING APPROVAL` · `DONE`

## Queue (top to bottom = build order; take the first non-DONE row)

| # | PRD file | Depends on | Status | Done |
|---|----------|-----------|--------|------|
| 01 | [01-app-shell-and-design-system.md](01-app-shell-and-design-system.md) | — | TODO | |
| 02 | [02-data-ingestion-and-projects.md](02-data-ingestion-and-projects.md) | 01 | TODO | |
| 03 | [03-score-evaluation.md](03-score-evaluation.md) | 02 | TODO | |
| 04 | [04-policy-studio.md](04-policy-studio.md) | 02 | TODO | |
| 05 | [05-simulation-and-impact.md](05-simulation-and-impact.md) | 04 | TODO | |
| 06 | [06-tradeoff-and-scenarios.md](06-tradeoff-and-scenarios.md) | 04 | TODO | |
| 07 | [07-cutoff-optimization.md](07-cutoff-optimization.md) | 04 | TODO | |
| 08 | [08-risk-grouping-and-ratings.md](08-risk-grouping-and-ratings.md) | 02 | TODO | |
| 09 | [09-risk-screening.md](09-risk-screening.md) | 08 | TODO | |
| 10 | [10-crash-test.md](10-crash-test.md) | 04 | TODO | |
| 11 | [11-deployment-and-scoring.md](11-deployment-and-scoring.md) | 04, 08 | TODO | |

> Note: `<NN>` in commit messages = the row number (01–11). The PRD file name also
> carries it. When all rows are `DONE`, the v1 studio is complete (00-overview §12).
