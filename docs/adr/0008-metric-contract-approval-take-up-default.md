# ADR 0008 — Metric contract: approval rate, take-up rate, default rate

- **Status:** Accepted
- **Date:** 2026-07-14
- **Scope:** Every surface that reports approval or default — engine (`optimization.py`,
  `analysis.py`, `performance.py`) **and** `studio/`. The "MUST NOT touch the engine"
  constraint of ADR 0001 does **not** apply here (owner decision, wayfinder map #54).
- **Ticket:** #55 (wayfinder map #54).

## Context

The same policy reports different numbers depending on which function you ask, because
each surface silently picked its own denominator. A simulation produces two funnel
columns: `approved_pre_rate` (survived the filter/cutoff stages) and `new_approval`
(survived the whole funnel, RateStage included — i.e. contracted). Five surfaces mix
them five ways:

| Surface | Approval numerator | Default weight | Conforms |
|---|---|---|---|
| `studio.analyses.delta_table` | `approved_pre_rate` | `new_approval` | yes |
| `performance.summarize_results` | `approved_pre_rate` (`Approved`) + `new_approval` (`Hired`) | `new_approval` | yes |
| `analysis.TradeoffAnalyzer` (analysis.py:133) | `approved_pre_rate` | `approved_pre_rate` | no |
| `optimize_cutoffs`, analytical (optimization.py:193) | `approved_pre_rate` | `approved_pre_rate` | no |
| `optimize_cutoffs`, stochastic (optimization.py:90) | `new_approval` | `new_approval` | no |
| `studio.analyses._candidate_outcome` (analyses.py:118) | `new_approval`, **labelled `approval_rate`** | `new_approval` | no |

Two distinct defects hide in that table:

1. **`optimize_cutoffs` contradicts itself.** Its analytical and stochastic paths
   report different semantics for the same argument list — switching `method=` silently
   changes what `overall_approval_rate` means.
2. **The studio's comparison is apples-to-oranges.** `_candidate_outcome` labels the
   contracted rate as `approval_rate`, and `compare_vs_base` then deltas it against the
   base policy's `current_approval_col` — which is a *pre*-take-up approval rate. A
   candidate with 70% take-up reads ~30% worse than it is, and the penalty comes from
   the commercial funnel, not from the underwriting rule being compared.

The divergence between "default over approved" and "default over contracted" is
**zero when take-up is a flat scalar** (uniform thinning does not move a rate) and
**non-zero exactly when take-up correlates with risk** — which is what the keep-in
decile take-up rule (#56) introduces. So this is not a rounding argument; it is a
precondition for #56.

## Decision

### The contract

```python
approval_rate     = approved_pre_rate.sum() / N                    # approved ÷ total
take_up_rate      = new_approval.sum() / approved_pre_rate.sum()   # contracted ÷ approved
contracted_volume = new_approval.sum()                             # a count, not a rate
default_rate      = (simulated_default * new_approval).sum() / new_approval.sum()
```

- **Approval rate is always pre-take-up.** It measures the underwriting rule.
- **Take-up rate is a conversion**, denominated in *approved* — not in total
  (owner decision). `contracted ÷ total` is deliberately **not** a named metric: it is
  `approval_rate × take_up_rate`, derivable, and naming it invites the very confusion
  this ADR closes. The name `take_up_rate` matches `studio`'s existing
  `suggested_take_up_rate` (`hired / approved`), which already computes exactly this.
- **Default rate is always over the contracted population.** You cannot default on a
  loan you never took.
- `delta_table` and `summarize_results` are the reference implementations.
  `summarize_results` already ships `Approved` and `Hired` side by side — that is the
  precedent this vocabulary generalises.

### Per-surface obligations

- **`optimize_cutoffs`** — both paths report `overall_approval_rate` from
  `approved_pre_rate` and `overall_default_rate` weighted by `new_approval`. The
  objective and the `target_default_rate` constraint bind on the **contracted** default
  rate. The analytical path must therefore carry `new_approval` alongside `p_base`:

  ```python
  app_rate = (mask * approved_pre_rate).sum() / N
  def_rate = (mask * new_approval * pd_base).sum() / (mask * new_approval).sum()
  ```

- **`TradeoffAnalyzer` / `run_tradeoff_analysis`** — keep `approved_pre_rate` for
  `approval_rate`; switch `default_rate` to `new_approval` weighting. The deliberate
  comment at analysis.py:133 is half right (approval) and half wrong (default), and is
  replaced by a pointer to this ADR.

- **`studio.analyses.policy_kpis` / `_candidate_outcome`** — return `approval_rate`,
  `take_up_rate`, `contracted_volume`, `default_rate`. The `approval_rate` key changes
  meaning (breaking, accepted for 0.5); `pre_rate_volume` is subsumed.

- **`compare_vs_base`** — delta only what the base can honestly answer:
  `approval_rate` (now approved-vs-approved, commensurable) and `default_rate`.
  `take_up_rate` and `contracted_volume` render as candidate-only figures with no
  delta, because the comparison base is a decision column and does not know who
  contracted. **No misleading delta is ever shown**, even where a hired column happens
  to exist.

- **`delta_table`, `summarize_results`** — no change; audited as conforming.

## Consequences

- **Breaking in 0.5.** `optimize_cutoffs` results move for any policy with a
  risk-correlated RateStage, and `target_default_rate` now binds on a different (higher
  or lower) number. `policy_kpis()["approval_rate"]` changes meaning. Both are listed in
  the 0.5 changelog.
- The Bancada's KPI row gains two entries and loses a lie.
- #56 (take-up as scalar or decile rule) can land without re-opening the semantics
  question — the decile rule's whole point is risk-correlated take-up, which is only
  measurable under this contract.
- Saved projects/scenarios that persist a KPI dict need a migration pass — tracked in
  the map's "Not yet specified" (downstream consumers).

## Related

- Wayfinder map #54; tickets #56 (take-up), #57 (optimize_cutoffs vs TradeoffAnalyzer).
- ADR 0001 (Bancada), 0002 (adaptive comparison base by tier).
