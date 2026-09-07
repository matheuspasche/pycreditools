# CONTEXT

Domain glossary and ubiquitous language for `pycreditools`. Read this before working in
the engine; then read the ADRs that touch your area (`docs/adr/`). This file grows lazily —
terms land here when a decision actually resolves them, not upfront.

## Ubiquitous language

Use these exact terms in issues, tests, and proposals. Don't drift to synonyms.

### Language of the code — English, names and values

The engine speaks **one language: English**, in every emitted column name and every value
that isn't presentation. pt-BR is a presentation concern and lives outside the core, on the
far side of the calculate/present boundary (**#127**).

If the engine emits the name, it's English. That's the whole rule — there's no list to keep.

**Dead vocabulary, measured, never to be reintroduced.** These pt-BR column names are
promised by `to_decision_dataframe`'s docstring (`simulation.py:169-171`) and written by
**no code path** — 0 emissions each, measured on `release/v0.6`:

| dead | use |
|---|---|
| `decisao` | `decision` |
| `motivo` | `reason` |
| `contratou` | `hired` |
| `inadimplente` | `defaulted` |
| `cenario` | `scenario` |

Values follow the same rule: `'Aprovado'` / `'Reprovado'` are presentation, not engine
values.

**One more duplicate, not pt-BR.** `Rating` (capitalized, `deployment.py`) and `rating`
(`simulation.py`) are the same column written by two modules — the letter label,
`risk_rating.map({i: chr(64 + i)})`. The name is **`rating`**, lowercase, like every other
output column. `risk_rating` is *not* a third spelling of it: that's the numeric group id
emitted by `GroupingRecipe`, a different column with a different meaning.

Decided in **#131**, ratifying the naming **#116** already used. The v0.6 renames themselves
ship with v0.6; the rule governs new code from now on.

### Quadrants (membership is by **decision**, never by contract)

An applicant is classified by comparing the incumbent decision (`current_approval_col`)
against the new policy's decision:

- **keep_in** — approved by both (stays in the book).
- **swap_in** — rejected before, approved now (new business the policy pulls in).
- **swap_out** — approved before, rejected now (dropped from the book).
- **keep_out** — rejected by both. No observable credit performance — default is `NaN`,
  never filled.

Quadrant is the **decision**, not the contract. A keep-in that was approved but never
became a paying contract is *still a keep-in*. See ADR 0010 (`KEEP_IN` is the decision, not
a mask).

### Approval, take-up, contract

- **`approved_pre_rate`** — passed all filter/cutoff stages, **before** any take-up/rate
  stage. The underwriting decision. Drives the **approval rate**.
- **take-up rate** — conversion from approved to contracted. Applies to swap-ins (drawn /
  weighted by the rate). Keep-in take-up is **observed, not drawn** — sourced from
  `current_hired_col`, read by the core (ADR 0011). An approved-but-never-hired keep-in gets
  contract weight `0`. Absent a declared take-up the engine still warns and falls back to the
  legacy `1.0` (a `DeprecationWarning`); it becomes a hard error in a follow-up (#106).
- **`new_approval`** — the **contract weight**, a float in `[0, 1]` (stochastic emits
  exactly `0.0`/`1.0`). This is *contracted*, not *approved*. Drives **contracted volume**
  (`Hired`) and the **default-rate denominator**.

### Default marking

- **`simulated_default`** — the per-row default used by the engine. keep_in copies
  `actual_default`; swap_in gets a score-calibrated (or externally marked) PD/outcome.
- **`actual_default`** — observed 0/1 outcome on the incumbent book. **`NaN` when a keep-in
  was approved but never contracted** (no outcome to observe).
- **market marking** — external 0/1 default (`market_default_col`, backtest-derived).
  Present for every row; requires 0/1, not a probability (ADR 0010).

### Blended / expected default rate — **the load-bearing formula**

The expected default over a policy's book, weighted by the contracted population:

```
default_rate = (simulated_default × new_approval).sum()
             / new_approval[contracted_and_observed].sum()
```

**The denominator is contracted-AND-observed, not the full `new_approval.sum()`.** A row
with no recorded outcome (approved-but-never-paid keep-in, `actual_default` NaN) contributes
`0` to the numerator and **must leave the denominator too**. Counting it deflates the rate —
this is the recurring calculation bug in this repo (**#95** in validation, **#97** shipped in
the engine). Numerator drops `NaN` via multiplication; the denominator must drop the same
rows.

Guardrails this must satisfy (`tests/test_default_denominator_invariants.py`):

1. Changing the take-up rate **moves** the expected default (when keep-in and swap-in
   default levels differ).
2. With a rate active, `mean(contracted)` ≠ `sum / n_rows`.
3. Stochastic and analytical **converge** for large `n`.

⚠️ **The `notna()` check in the engine is a proxy, not the definition of "contract".** It
breaks under external marking (all rows non-null). The robust form encodes contract status
in `new_approval` itself. See ADR 0010's default-rate note and design issue **#101**.

## Authoritative sources

- **ADR 0008** — metric contract (approval / take-up / default), with the #97 amendment.
- **ADR 0010** — engine contract: `new_approval` as float weight, marking scenarios,
  keep-in take-up, the default-denominator note.
- **#97 / #99** — the shipped dilution fix. **#101** — the robust rate-driven refactor.
