# ADR 0037 — `reason` is the sixth column of the engine schema

- **Status:** Accepted
- **Date:** 2026-09-13
- **Decides:** adjudication-5
- **Scope:** whether *which stage blocked* belongs to the engine's output schema, and the three
  consequences that come with it. Excludes the schema's other five columns (ADR 0012 / #131) and
  the stage label's rules (ADR 0029 / #129, ADR 0032 / #145).
- **Consumes:** #116, #129, #131, #145, ADR 0012, and the ticket breakdown
  `docs/engine/spec/v06-tickets.md` § *Adjudicações*.
- **Spec:** the living engine spec, §4.7 (the output data contract — the engine's schema), §4.2
  (the stage label), §4.6 (the funnel is short-circuit).
- **Amends:** the living engine spec, §4.7 — applied.
- **Measured against:** `release/v0.6` (`24a125a`).

## Why this ADR is named, and not covered by a card number

Raised in the cold review of the ticket breakdown: **ticket 5 declared six columns and §4.7
declared five**, and that was an **undeclared amendment** to a document whose last line reads
*"an amendment to it is an amendment to a decision — record the why in an ADR before changing a
line here."* The other amendment (arity, ADR 0036) was declared; **this one was not.** It is
declared now, and the artifact gate enumerates it by name because it has no card.

## Context

The measured state that §4.7 itself reports:

> `decision`/`reason` are **written by two independent paths with the same content**, the border
> **recomputing** what the engine already calculated.

And §4.7's own remedy is *"the result table has exactly ONE assembly point, and the declared
schema is its input; nothing else writes to the frame."* Leaving `reason` **out** of the engine
schema keeps the border recomputing — **keeping alive exactly the bug the section exists to
kill.**

## Decision

`reason` enters the engine's schema as its sixth column: **`category`, null where
`decision == 1`, written only at the assembly point.**

**Who knows which stage blocked is the engine, at the instant it blocks.** There is no second
place that may write the column, so the duplicate path is not forbidden — it is
**unexpressible**, which is rung 1 of the ladder of remedies rather than a convention to
maintain.

## Three consequences the implementation must hold

**1. The value is the stage's label, not a sentence.** The same unique label of §4.2, with its
structural default. A sentence is presentation, and presentation lives outside the core (§ *one
language*): whoever wants readable text resolves the label at the border.

**2. The first stage that blocks, and only it.** The chain is short-circuit by construction
(§4.6): a blocked row is not evaluated by the following stages, so there is no *"blocked in two"*
to represent.

Consequence the test must pin: **`reason` depends on the stages' declaration order**, and
changing the order changes `reason`'s distribution **without changing `decision`**. That is a
**reading**, not a decision — and it is why
`tests/test_swap_in_anchor_follows_declaration_order.py` is the executable model of the third
DoD.

**3. Null where `decision == 1` is contract, not convenience.** An approved applicant has no
reason for refusal. Filling it with `""`, `"approved"` or any sentinel would **invent a category
that is not a stage** and would make `value_counts()` lie about the distribution of barriers.

The reading rule follows directly: **`reason` is only read under `decision == 0`**, and the count
of non-null `reason` closes with the count of rejections.

## Rejected

- **Leaving `reason` out of the engine schema** (what §4.7 wrote). It is the status quo that
  keeps two writers for one column — the defect the section was written to remove.
- **A human-readable sentence as the value.** Presentation inside the core, against the
  single-language rule; and it makes the column's cardinality a function of the message text
  rather than of the stages.
- **`""` or `"approved"` for approved rows.** It manufactures a category that corresponds to no
  stage, and silently corrupts the one aggregation anybody runs on this column.
- **Recording every stage that would have blocked.** The funnel is short-circuit, so the extra
  values would have to be computed for rows the engine deliberately stops evaluating — paying for
  a fact nobody asked for, and contradicting §4.6.

## Consequences

- **Ticket 5 holds the three consequences above**, and `reason` is the sixth column its schema
  declares.
- **`dtype` is `category`, never `object`**, by ADR 0012's measurement: **140 MB against 5 MB at
  5M rows (28×)**.
- **The border schema is unaffected.** It adds `rating` — the letter label, produced on demand —
  which does **not** enter the engine schema, because the rating ruler does not touch the funnel.
- **Amendment to §4.7, applied**, and recorded here rather than left as a silent divergence
  between ticket and spec.
