# ADR 0012 — The output data contract: declared by construction, English, domain-sovereign

- **Status:** Accepted
- **Date:** 2026-08-31
- **Scope:** everything the engine emits — `simulation.py`, `sweep.py`, `stages.py`,
  `performance.py` — plus the border surfaces that build tables from it
  (`to_decision_dataframe`, `export`).
- **Amends:** ADR 0008 (metric contract) and ADR 0010 (engine contract) on column naming and
  on what a null outcome means. Supersedes the `is_sim_col` guard entirely.
- **Tickets:** #131 (this ADR). Consumes #116, #117, #118, #119, #125, #127, #135, #140, #144.
  Feeds #132, #141, #146, and the roadmap #124.
- **Spec touched:** the living engine spec (output contract section).

## Context

The engine's output had no contract; it was guessed. `is_sim_col` (`simulation.py:192-208`)
answered "is this column mine or the user's?" from a hand-maintained list of 18 names plus a
`stage_` prefix heuristic. Measured on `release/v0.6`:

- **Seven of the 18 names are never emitted by any code path.** Five are the pt-BR vocabulary
  the `to_decision_dataframe` docstring promises and the code does not write (`decisao`,
  `motivo`, `contratou`, `inadimplente`, `cenario` — 0 emissions each, against `scenario` 18,
  `reason` 10, `hired` 5, `decision` 4, `defaulted` 3). One is `quadrant`. One is
  `risk_rating`, which the engine reads from the rating recipe but never writes.
- **The declaration already existed and lost.** `_types.py` defines the Enums and a
  `PolicySummary` TypedDict; it takes 13 uses against 40 raw `analytical`/`stochastic`
  literals, and 5 against 53 `gte`/`lte` (#135). It lost because ignoring it cost nothing.
- **Column names as string literals: 261 sites in `src` across 11 files, 222 in `tests`.**
- **The result frame has no single assembly point.** 34 column assignments in `simulation.py`
  alone; `decision`, `reason` and `scenario` are each written by two independent paths with
  the same content (`:233-234`/`:256-257` in the border against `:477-478`/`:490-491` in the
  engine); `hired` takes three dtypes in five lines (`:296-300`).

Two of the four pathologies the ticket opened with had already been dissolved by later
decisions: #140 killed the analytical method, so no column can change dtype by mode, and
#116 killed `new_approval`/`approved_pre_rate` outright.

## Decisions

### 1. The table is the interface

The §16 Q9 constraint — declare the schema *without* replacing the returned DataFrame — is
**ratified**. `CreditSimResults` survives as the carrier of the declared set, not as the
contract. Rationale: the project's UX rule (a verb takes a table and returns a table, so
nothing new must be learned to chain), and #125/#116 already legislated over the table.

### 2. One language: English, in names and values

The engine speaks English in every emitted name and every value that is not presentation.
pt-BR is presentation and lives outside the core, past the calculate/present boundary (#127).
Recorded in `CONTEXT.md` § *Language of the code* and pointed to from `CLAUDE.md`, which is
the file every session loads.

Consequences: the `to_decision_dataframe` docstring dies whole — it promises pt-BR names *and*
pt-BR values (`Aprovado`/`Reprovado`), and the values are presentation. A mixed-language name
list inside the engine is a rule violation, not a case-by-case judgement (#132, case 3).

### 3. One name per role

Two duplicates die, both being one column written under two spellings:

- `Rating` (`deployment.py:462,466`) and `rating` (`simulation.py:282,287`) are the same
  expression — `risk_rating.map({i: chr(64 + i)})`. The name is **`rating`**, lowercase, like
  every other output column. `risk_rating` is *not* a third spelling: it is the numeric group
  id emitted by `GroupingRecipe`, a different column, and its contract belongs to #126.
- The column filled with `Quadrant.*` values is emitted as `scenario` (`simulation.py:531`)
  while the ubiquitous language calls the concept **Quadrant** and `stress_scenarios` is an
  unrelated concept with 20 references. The name is **`quadrant`**.

### 4. The rating label is a border column

It is not part of the engine's declared schema. #119 already decided the label is derived from
the bind and never enters the engine, and measured that the rating recipe does not touch the
funnel — only `to_decision_dataframe` and `export`. So this ADR declares **two** schemas, the
engine's and the border's. The two `df["rating"] = None` plantings (`simulation.py:275,289`)
die: absent a declared rating recipe there is no column, rather than a column full of nulls.

### 5. The declaration is mandatory **by construction**

> The result table has exactly one assembly point, and the declared schema is its input.
> Nothing else writes into the frame.

A column that is not declared cannot appear, because nothing else can write it. Inside the
assembler, names are symbols, not literals.

Schema validation (`pandera`) is **rejected** — not deferred. Its whole value is runtime
obligatoriness, and that is free once there is a single exit: comparing *declared* against
*what I actually created* is a few lines of stdlib. Its costs are not free — a first
validation dependency against the stdlib inclination of #120, runtime cost in the
200-simulations-per-grid regime of #122, and a second vocabulary for dtypes. On complexity,
construction is a move of **deletion** (`is_sim_col` and the duplicate paths go) while
validation is a move of **addition** that removes nothing. On elasticity, the assembler
**determines** the dtype where validation only **checks** it.

`is_sim_col` dies: the assembler knows what it created, so "mine or the user's" is answered by
the carrier, not guessed from a list.

**Two declared limits.** This binds the write side, not the read side — a wrong literal in a
read position raises `KeyError`, which is ergonomics, not correctness. And the guarantee is
structural: it holds **while the frame does not circulate mutably inside the core**. That
constraint is part of the contract, not an implicit assumption.

### 6. Domain sovereignty, and the naive mean is correct by construction

The vectors form a chain of nested domains: `decision` → `contract` (domain: the approved) →
`outcome` (domain: the contracted).

> The engine derives the vectors from the chain and **discards** any supplied marking outside
> its domain — 0, 1, or anything else. A rejected applicant has no contract marking; an
> uncontracted one has no outcome marking.

Therefore **null is not a status**: it is *outside the domain of this calculation*, and it is
derivable. No status value is needed for "not contracted" or "no observed outcome" — the chain
yields both. Inside the domain, absence is an **invariant violation**, not a state: a
contracted row with a null outcome is a defect, and today it passes silently
(`simulation.py:602`, where a swap-in whose calibration returned no PD leaves the denominator
unnoticed — the #95/#97 family).

The acceptance criterion, stated as a testable property:

> The emitted column is null outside its domain, so that the naive mean is correct by
> construction.

`Series.mean()` skips nulls, so a reader who takes a plain mean of the outcome column gets the
right answer — not by having read the documentation, but by there being no way to get it
wrong. The protection does not depend on the client marking correctly; it depends on the
engine discarding their marking. This is the answer to the 0-filled-outcome practice, where a
base never contains nulls and ineligible rows enter the denominator as observed non-defaults.

The chain becomes two assertions at the assembler's single exit: `contract > 0` implies
approved; `outcome` present if and only if `contract > 0`. Obligatoriness by construction thus
covers the **relation between columns**, not only their names.

**Where the guarantee stops, and the spec must say so:** it covers the columns the *engine*
emits. A mean over the user's own raw column stays wrong and cannot be protected.

The state measured: `defaulted` has two branches and only one masks —
`simulation.py:304` copies `simulated_default` raw while `:307` masks by contract. The safe
branch survives only by luck, since #140 killed the analytical path. Three sites must be
re-read against this decision: `simulation.py:302-307`, `sweep.py:107-110` (which puts the
user's raw marking back over rows the engine deliberately nulled), and `stages.py:444-448`
(which masks by the *incumbent* decision and turns nulls into 0 silently).

### 7. No dispersion column on the grid table

The analytic standard error measures sampling noise (0.018 p.p.) while the dominant
uncertainty is that of the declared premise (#140's threshold ruling). Publishing it would
report the smallest source of error and stay silent about the largest, and would be read as
"this is my uncertainty". Zero cost to compute is not zero cost to own.

The obligation moves to documentation: the package must state that **every number comes from a
draw**, hence carries margin — which after #140 is a property of the whole package, there
being one calculation path. Two measured numbers belong in that note: 0.018 p.p. of sampling
noise in a single run, and **0.41 p.p. between seeded runs** under `parallel=True` (ruled a
characteristic, not a bug, on 2026-08-16). Today `README.md:419-423` points the other way,
describing stochastic noise as something the package *prevents*.

### 8. No rule against a shell redeclaring the vocabulary

There is no live case — #118 killed `ColumnRoles`. And the cause is removed rather than
policed: redeclaration was possible because the core had no usable declaration, and decision 5
creates one. The spec carries one line — the declared set is the single source, shells consume
and do not redeclare — with no enforcement mechanism. If a second shell redeclares anyway,
there is a live case and the question returns with evidence.

## Migration (breaking change)

Renaming output columns and changing dtypes breaks the public contract. Candidate for
**v0.6.0**, to be confirmed in #124, consistent with the single, minimal hard break the map
declares.

Dying: `new_approval`, `approved_pre_rate` (#116); `Rating`, `scenario` as a column name,
`decisao`, `motivo`, `contratou`, `inadimplente`, `cenario`; `is_sim_col` entire.

## Consequences

- The declared engine set, derived from closed decisions: `decision` (0/1 always, #116),
  `contract` (take-up weight, #116), `outcome` (null outside the domain, #116 + decision 6),
  `quadrant` (membership by decision, `category`), `study` (#125). Column-by-column
  enumeration with dtypes is spec writing that follows mechanically from these rules.
- **Pareto axis candidates** are the grid table's *metric* columns, not the swept
  coordinates, which are decision variables rather than objectives. With decision 7, no
  dispersion column enters, so the pair (approval, default) stays the obvious one — the
  collision the 2026-08-17 audit anticipated does not occur. This is what #141 was waiting for.
- Any surviving status column is `category`, never `object` — 140 MB against 5 MB at 5M rows
  (#125).
- Execution residues for #124: a mechanical denylist for the dead vocabulary, riding the
  `pre-commit` #115 already decided to install; the documentation note above; the nine
  `notna()` sites #116 obliges a re-read of; and the three masking sites named in decision 6.
