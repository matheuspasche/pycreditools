# ADR 0002 — Adaptive comparison base by data-availability tier

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` (Ingestion detection + Bancada adaptation), `studio/detection.py`. No engine change.

## Context

"Base" (the comparison reference) has **two distinct senses**: (1) the **vigente
policy** = the approval decision actually taken in the portfolio (the historical
approval flag), against which swap in/out/keep is computed; and (2) a **parent
policy** that is forked to start a candidate (reuse part of a policy). Crucially,
the data available about the vigente policy **varies per engagement**:

- Sometimes we have the vigente score + decline reasons + flags → the vigente
  **rules can be reconstructed**.
- Sometimes only the approval **flag**, without even the vigente score.
- Sometimes **nothing** — the policy is built from scratch / via market inference,
  with no swap comparison at all.

The engine already supports the whole spectrum: `run_simulation` has a standalone
path when `current_approval_col is None` (market inference / from scratch), and the
swap flow only needs the **flag**, not the score. `estimated_default_col` is the PD
source in the standalone path (`simulation.py:_assign_simulated_defaults_standalone`).

## Decision

The studio recognises three **comparison tiers** and **auto-detects** them from the
configured column roles, **adapting the Bancada** accordingly:

| Tier | Available | Bancada behaviour |
|---|---|---|
| **A — Full base** | vigente score + flag | swap completo (swap-in/out/keep) via flag; score vigente disponível para análises futuras |
| **B — Flags only** | approval flag, no vigente score | swap in/out/keep works; cannot reconstruct rules |
| **C — No base** | none | standalone / market inference, **no swap**; PD comes from `estimated_default_col` |

A badge at the top of the Bancada states the active tier **and why**. Detection is
automatic; a future override may be added but is not required for v1.

## Consequences

- Resolves critique **1.3**: `estimated_default_col` (PD estimada) is **not**
  redundant — it is the PD input for **Tier C only**, and is surfaced **only** in
  that tier (it is hidden when a swap base exists).
- Resolves critique **1.2**: segment and several roles become **optional**;
  required roles depend on the detected tier.
- The Ingestion page must classify the tier and explain it in plain language.

## Implementation note (v2)

Tier A and Tier B use the **same swap mechanism** in `base_outcome` — both rely
solely on the historical approval flag. The vigente score (available in Tier A)
is not used to reconstruct the vigente policy rules in v2. **Reconstructing vigente
rules from the score is deferred to future work** (see redesign spec §Deferred).
The Tier A badge rationale reflects this: it describes the actual swap-flag behavior
without promising reconstruction. (#41)

## Related

ADR 0001, 0003. Redesign spec §"Base & tiers".
