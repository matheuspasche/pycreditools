# ADR 0016 — Undeclared take-up is 1.0; a discrete lens with `bins` is not an error

- **Status:** Accepted
- **Date:** 2026-09-10
- **Scope:** two defaults-and-errors questions of the `Premise` (§4.4) that the spec answered
  twice, and that ticket 4 shipped by one reading.
- **Tickets:** #181 (this ADR). Consumes #139, #152, #155, and Adjudication 3 of the ticket
  breakdown (`docs/engine/spec/v06-tickets.md:202-208`).
- **Amends:** the living engine spec, §4.4 — the signature (`take_up = "binned"`), the
  `take_up` table, the lens table's *"declarar `bins` junto é erro duro"*, and the second of
  the two hard errors. **Changes code already delivered by #161.**
- **Measured against:** `release/v0.6` (`b884b95`).

## Context

**Take-up.** §4.4's signature and table give `take_up="binned"` as the default; the paragraph
under the table and US 28 say *"Take-up sem declaração é `1.0`, literal na assinatura,
permanente e documentado"*, conservative and not neutral. PR #176 followed the signature. The
two readings come from different moments of the map:

| when | card | what it says |
|---|---|---|
| 2026-09-05 | #139 §6 | *"Sem taxa de conversão declarada, todo reprovado aprovado pela política nova contrata"* — written while take-up was still a `.rate` stage in the policy |
| 2026-09-06 20:10 | #155, ruling A | `1.0` literal on `ColumnPremise`, which *"não tem baseline"*; `ScorePremise` took a scalar or `"observed"`, no default written |
| 2026-09-06 21:12 | #152, decisions 4 and 6 | one `Premise`; `take_up` is `"binned"` or a scalar; the example writes `take_up = "binned"` — the word *default* does not appear |

**Discrete lens.** §4.4 lists as its second hard error
`Premise(lens=col("rating"), bins=10, …)` → *"`lens` é discreta … remova `bins`"*. It is not
decidable without data — discreteness is a property of the bound column — and it collides with
Adjudication 3: `bins` carries the literal `5` in the signature, so it is **always** declared,
and the error read literally would refuse every premise with a discrete lens.

## Decision 1 — undeclared take-up is the scalar `1.0`

The `Premise` signature carries `take_up = 1.0`. `"binned"` and an AST node remain the two other
modes, one keyword away.

**Why.** It is US 28 and #139 §6 as written: permanent, documented, and **conservative, not
neutral** — keep-ins enter the book only if they contracted, swap-ins all enter, and since the
swap-in is the worse public the default rate is pushed up. It is the v0.5 number, so it stays
out of the parity whitelist. A book without an incumbent hire record runs without declaring
take-up. And the rule *"no modelling default hides the existence of a mechanism"* (#152) holds:
the literal is visible in `help()`, which is the reasoning #155's ruling A used for the same
`1.0`.

**Recorded against the session's recommendation**, which was `"binned"` — the latest card's
example, the spec's signature, the better-supported estimate (§4.4: take-up is observed for
every approved row, so the contract axis has no support hole), and no change to shipped code.
The owner chose `1.0`.

**Consequences.**

- `engine/premise.py:66` changes its default, with its docstring and the tests that pin the
  old one (`tests/engine/test_engine_declaration.py:178`, `:313`, and the lens-binding cases).
  This session implements nothing: the change is an item of ticket 6 (#163).
- The lens binding loosens by construction: with the default take-up, only
  `outcome_from="parcelling"` consumes `lens`, so `Premise(outcome_from="market_default")` is
  valid with no lens and no take-up declared.

## Decision 2 — the "discrete lens + `bins`" error is withdrawn

Adjudication 3 already settled the class: a `bins` nothing consumes is **reported, not
refused**, because a literal default cannot be told apart from a declaration. A discrete lens
is one more case of `bins` not consumed. The difference is only where it is known — at bind,
where the column is — so the report belongs with the premise's bind (ticket 6), not with
`Premise.__repr__`, which has no data.

Fact handed to ticket 6, not decided here: the package's own rating comes out of
`GroupingRecipe.predict` as `float64` (`grouping.py:62`, `:71`, `:108` — a `NaN` column filled
with the integers 1–5). How the bind tells a discrete lens from a continuous one is that
ticket's execution under §9.1 decision 7.
