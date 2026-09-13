# ADR 0036 — `simulate` has output arity equal to input arity; the long table is the reading verbs'

- **Status:** Accepted
- **Date:** 2026-09-13
- **Decides:** adjudication-1
- **Scope:** what `simulate` returns when given a collection, and where the long table is
  produced. Excludes the long table's own contract (ADR 0012 / #131) and the `study` column
  (ADR 0026 / #125).
- **Consumes:** #113, #119, #125, #127, #146, #152, and the ticket breakdown
  `docs/engine/spec/v06-tickets.md` § *Adjudicações*.
- **Spec:** the living engine spec, §4.10 (serialisation and identity — the arity paragraph),
  §4.7 (the four reading tables).
- **Amends:** ADR 0021 / #119 — *"comparing N is a first-class verb"*. The content of that
  decision survives whole; what changes is **which verb produces it**.
- **Measured against:** `release/v0.6` (`24a125a`).

## Why this ADR is named, and not covered by a card number

This is one of **two amendments the ticket breakdown made to the spec**, in a document whose last
line reads *"an amendment to it is an amendment to a decision — record the why in an ADR before
changing a line here."* This one — the arity of `simulate` — was **declared** as an amendment when
it was made; the other (`reason`, ADR 0037) was not. Both are enumerated by the artifact gate
under a name, because neither has a card of its own.

## Context — the spec contradicted itself

- **§4.10** said `simulate([s1, s2, s3], df)` returns the long table.
- **§4.7** wrote the canonical example as `delta_table([res_a, res_b], baseline=res_hoje)` — **a
  list of carriers**.

**The two cannot both be right.** One of them has `simulate` producing a flattened table; the
other has a reading verb consuming unflattened carriers.

The contradiction is inherited, not invented: §9.1 item 1 had already removed the `compare` verb
(*"`simulate` accepts a collection; `delta_table(results, baseline=)` reads; `compare` is never
born"*), and in doing so it left the question of what `simulate` itself hands back.

## Decision

> **`simulate` has output arity equal to its input arity.** One `Study` in, one
> `CreditSimResults` out. A collection of `Study` in, **a collection of `CreditSimResults` out,
> in the same order**. `simulate` does **not** flatten to the long table.
>
> **The long table is produced by the reading verbs.**

A collection of one returns a sequence of one, **with no special case**.

## Why this and not the collection becoming a table

**Flattening is reading, and reading belongs to the `_table` verbs.** §4.7's canonical call is
`delta_table([res_a, res_b], baseline=res_hoje)`, a list of carriers. If `simulate` already
returned the long table, that call could not exist — and the **four** reading tables would have
no input in the N case: `funnel_table`, `quadrant_table` and `swap_in_table` need the **carrier**,
not an already-reduced delta.

Flattening early would force each of them either to **undo** the flattening, or to exist in two
versions — one for the 1 case and one for the N case. **Uniform arity gives all four readings for
free in both cases.**

It also saves the acceptance ruler *"predictable output type"*, and it preserves §9.1 item 1's
content whole: *"long table, one row per study, no container type"* speaks of the **product**, not
of the return type.

## Rejected

- **Polymorphic return** — a carrier for one study, a long table for a collection. That is
  **exactly** what the acceptance ruler forbids: the user cannot tell the output's type from the
  call without counting the input.
- **A special case for a collection of one.** It reintroduces the same unpredictability at a
  smaller scale, and it makes a loop over a variable-length list of studies branch on its own
  length.
- **A `compare` verb producing the table.** Already removed by §9.1 item 1: since the `study`
  column exists **precisely so that `pd.concat` works**, a `compare` would be the same question
  asked twice. #152 raised this as an amendment **to decide**, explicitly not decided there
  because it contradicted a closed decision (#119). This ADR decides it.

## Consequences

- **Cost accepted and declared:** `simulate(studies)` is not the one line that prints the
  comparison — it needs the reading verb after it. **It is the same cost dplyr pays**, and for the
  same reason: the object in circulation is **homogeneous**, and whoever reduces is whoever reads.
- **`compare_policies` dies** — by position, with unlabelled recursion per item and the literal
  `"Old"`/`"New"` columns.
- **Amendment to §4.10 of the spec**, applied.
- **ADR 0021's Decision 3 survives in content**: one policy per `Study`, a long table with one row
  per study, no container type, and #125 (identity) as its prerequisite. Only the producer moved.
