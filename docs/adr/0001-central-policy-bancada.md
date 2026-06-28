# ADR 0001 — Reorient the studio around a central Policy Bancada

- **Status:** Accepted
- **Date:** 2026-06-28
- **Scope:** `gui/` skin + `studio/` orchestration only. **MUST NOT touch the package engine.**
- **Supersedes (partially):** PRD 04 (Policy Studio), 05 (Simulation), 06 (Trade-off), 10 (Crash Test) — these stop being standalone pages.

## Context

The shipped studio is a **linear pipeline of 10 independent pages**. Each page reads
shared session state but does not feed back into it, so the unit of work is "an
analysis", not "a policy". The owner's actual workflow (see redesign spec §Concept)
is the opposite: the unit of work is **a candidate policy compared against a base
policy**, where every knob (scores, cutoffs, filters, take-up, aggravation) impacts
every readout (funnel, swap, risk-tier mix, behaviour over time, exposure) and the
risk-tier clustering is computed on whoever survives the filters. The owner
explicitly pushed back on "many dashes, many simulations" and on three pages that
"say nothing" (Simulation, Trade-off) or are "unnecessary" (Crash Test).

## Decision

Adopt a **hybrid** information architecture:

```
Ingestion → Score Evaluation → Bancada (the heart) → Risk Grouping → Deploy
```

- The **Bancada** is one live screen that **absorbs Policy Studio + Simulation +
  Trade-off + Crash Test**. The user assembles the policy and sees, live:
  funnel/approval, default rate, and the **comparison-vs-base** (swap in/out/keep
  with volume + default, risk-tier distribution, behaviour over time, risk
  exposure). "Trade-off" becomes *drag the cutoff and watch the curve*; "Crash
  test" becomes *pull the aggravation until it breaks → can I still approve?*.
- **Score Evaluation** and **Risk Grouping** survive as **deep-dives**, but they
  read from / write back to the live policy (e.g. Risk Grouping clusters the
  surviving population; its matrix feeds the Bancada cutoffs).
- Everything propagates through the single live `CreditPolicy` already held in
  `StudioState` — no engine change is required to make knobs impact readouts.

## Consequences

- Four pages collapse into one; the sidebar shrinks to five entries.
- Removes critiques 2.2 (Simulation says nothing) and 2.3 (Trade-off axes unclear)
  by construction — the comparison is the page, not a separate dashboard.
- The Bancada becomes the most complex component; it must stay airy and
  suggestion-first (see ADR 0005) to remain intuitive.
- Deep-dive pages must be wired bidirectionally, not read-only.

## Related

- ADR 0002 (adaptive base), 0003 (contextual score), 0004 (matriciation),
  0005 (suggestion-first), 0006 (segmentation). Redesign spec: `docs/redesign/studio-redesign.md`.
