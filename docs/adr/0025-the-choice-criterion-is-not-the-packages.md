# ADR 0025 — The choice criterion is not the package's

- **Status:** Accepted
- **Date:** 2026-09-13
- **Decides:** choice-criterion
- **Scope:** the normative rule that appetite is the reader's cut over a finished grid, and the
  named knobs that die with it. The *structural* half — that no business-parameter type exists
  and selection is a table→table layer — is ADR 0024; the selection verb itself is ADR 0014.
- **Consumes:** #83, #92, #118, #122 (whose declared deliverable this ADR is), #124, #132.
- **Spec:** the living engine spec, §4.8 (grid and selection), §9.3 (which lists this ADR apart
  and measures it as *"never written, though declared as a deliverable"*).
- **Measured against:** `release/v0.6` (`24a125a`).

## Why this ADR is named, and not covered by a card number

The artifact gate enumerates **by card number**. This promise has no card of its own: it is the
declared deliverable of **#122**, whose resolution ends *"**ADR:** 'the choice criterion is not
the package's'"*. §9.3 of the spec lists it separately and measures it as **never written**, and
the reason it must be named explicitly is stated there: reading a list of card numbers, **nobody
can verify whether it is covered by #122 or by #125**. So it gets a name, and the gate checks
the name.

## Context

The package chose, in four places, and never said so.

1. **`optimization.py:194-201`** — `tradeoff_score = app - 5.0 * dr`. A **magic weight with no
   owner**, then `.iloc[0]` after sorting, then a **silent fallback** when no point satisfies the
   constraints. Three criteria stacked without a name, choosing on their own behalf.
2. **`target_default_rate=` and `min_approval_rate=`** as engine arguments — and the evidence
   that they were already noise is that cell 19 of `tutorial_masterclass` passes
   `target_default_rate=0.08, min_approval_rate=0.01` and **throws their result away**, reading
   only `o.pareto_frontier`. `best_combination`, `metrics` and `constraints_met` are consumed
   **nowhere** in the foundational notebook.
3. **#92's four proposed kwargs** (`targets=` per group, `target_metric=`, `target="incumbent"`,
   `target=lambda g: ...`) — each an attempt to let the package hold the appetite.
4. **`OptimizationResult.find_equivalent`** (`optimization.py:43-68`) — a tolerance band with a
   silent `.head(1)` fallback when the band came back empty.

#118 had already ruled, from the other end, that **optimisation is always advisory**: *"it's
there to show scenarios, and the guy picks what he wants."*

## Decision

> **Appetite is the human's, and it is a filter over the finished grid. The package produces
> the grid and names the questions; it does not hold the answer.**

Three consequences, all of them removals:

- **`target_default_rate` and `min_approval_rate` die as engine arguments.** *"8% default
  appetite, give me the cutoff per region"* stays expressible — it becomes
  `grid[grid.default_rate <= 0.08].groupby("region")` plus taking the maximum approval. That
  **is** optimising against a target.
- **The hidden best-pick dies** — the magic weight, the `.iloc[0]`, and the silent fallback.
- **Fair comparison (#83) is guaranteed by construction.** The choice criterion never travels
  inside the policy, so comparing A with B cannot mix a delta of rule with a delta of target.

## What "no business parameter" does **not** mean

Raised by the owner after the card closed — *"I may want to optimise against a pre-determined
target (what I did in section 6)"* — and it is correct. Two senses of *target* had been
collapsed:

| sense | status |
|---|---|
| **target as the user's workflow** | **alive**, and unchanged |
| **target as a concept of the package** | **dead** — no type, no engine argument, never inside the policy |

What died is `target_default_rate=` in a signature, not the workflow.

## The honest boundary: a ceiling is not an equality over an aggregate

A filter resolves a target as a **ceiling** or a **floor** — a row-by-row predicate over the
grid. It does **not** resolve a target as an **equality over an aggregate of the groups**. The
τ case of masterclass section 6 — *"hold aggregate approval identical to the simplified policy,
letting the mix move between regions"* — is a condition on the weighted sum of the groups, not
on each row.

Today the owner resolves it by manual bisection of τ over the cached grid: it works, and without
re-simulating. But it is the **one measured point** where the answer *"no type, just a filter"*
charges the user a real price — they write the search.

**Recorded rather than hidden**, because the map's rule is that a known price is written down.
It is the concrete use case justifying the adaptive-search / root-finding verb, assigned to
**#123** with section 6's τ as its named test case.

## Rejected

- **Keeping `target_default_rate=` as a convenience.** Measured as unconsumed in the only
  foundational notebook that passes it — convenience nobody used, paid for with a knob that
  makes the package look like it holds the appetite.
- **A declared tie-break rule inside the package** (`select_by_one_std_err`-style). Ties are
  several rows; choosing among them is the same act the whole ADR removes.
- **A `target=lambda g: ...` escape hatch** (#92). A callable does not serialise (the
  `CustomStress` defect, #83), and #122 Decision 4 shows the relative target does not need one.

## Consequences

- **Public-surface break**, on #124's list: `optimize_cutoffs`' target/constraint kwargs,
  `OptimizationResult.best_combination`, `.metrics`, `.constraints_met`, `.find_equivalent` and
  `tradeoff_score` all go. Pareto is the only piece that survives, and it becomes a **named
  criterion** of the selection verb (ADR 0014).
- **The empty answer is a real answer.** With the appetite cut expressed as a filter, *"no
  feasible point"* is an empty table over a grid that is still there to read — which is the
  opposite of the silent fallback it replaces, and is rung 3 of the ladder of remedies rather
  than rung zero.
- **ADR 0014 excludes the appetite cut from the selection verb on purpose** (*"the appetite cut
  — the reader's own `df[...]`, #122"*). This ADR is the decision that exclusion points at.
