# ADR 0006 — Light business segmentation now; full segmentation deferred

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` (Bancada) + `studio/`. No engine change.

## Context

Policies are sometimes segmented by a **business parameter** (acquisition channel
app vs door-to-door, store, entry policy): e.g. a different cutoff for door-to-door
applicants than for app applicants, cascading through the whole decision. The owner
wants this but accepts dropping it if it is too complex right now. Making "policy" a
per-segment object (independent filters + cutoffs + rates + aggravation per segment)
is the single heaviest architectural change and a UI-complexity risk.

## Decision

Ship a **light** version now and defer the full version:

- The Bancada gains an **optional** "segment by [column]" toggle.
- When on, the user sets **cutoffs per segment value** (the cited use case), and the
  funnel/comparison **aggregate the total + break out by segment**.
- Start with **cutoffs-per-segment only**. Do **not** replicate the full
  filter/rate/aggravation structure per segment yet.

## Consequences

- Resolves critique **1.2** (segment is optional) and the segmented-policy concept,
  at low risk.
- Full per-segment policies (independent rules + per-segment comparison) are
  **deferred** and recorded as future work in the redesign spec.
- "Policy" stays a single object with per-segment cutoff overrides, not a set of
  policies — keeps the data model simple.

## Related

ADR 0001. Redesign spec §"Deferred / cut".
