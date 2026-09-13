# ADR 0033 — The verb family, read all at once: the spine in two lines

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the shape of the public surface as a **set** — names, signatures, which verb is a
  method and which is a free function, the argument categories, and how the family announces
  itself. **Does not reopen architecture**: the type partition, the three schema fields, the
  three output vectors, the table contract, `.cutoff`'s death, one grid verb and one selection
  verb, the ladder of remedies, `Study` identity, the two serialisation units, or v0.6.0's
  content.
- **Tickets:** #152 (this ADR). Consumes #114, #116, #117, #118, #119, #120, #121, #124, #125,
  #126, #127, #129, #131, #132, #139, #141, #142, #145, #146, #155.
- **Spec:** the living engine spec, §2.1 (the spine), §2.2 (the surface end to end), §4.4
  (`Premise`), §4.9 (the suggesters), §4.11 (cross-cutting rules), §4.12 (how the family
  announces itself).
- **Amends:** #117 (the premise partition falls from two members to one), #139 (`"global"` is
  born after all), #155 (ruling A), #121 (one statement replaced).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context — the process hole this card exists to close

The v0.6 surface's names and shapes were decided **one card at a time, each against its own
problem** — #117 the partition, #118 the schema, #129/#145 the stage, #146 the grid, #141
selection, #127 the reading tables, #125 identity. The park-stroll ruler was applied **locally,
never to the set**.

**Nobody had ever read the whole surface at once.** It is the only reading that can tell whether
the family is coherent, and it is the reading no closed card had a mandate to do.

Three frictions that only appear in the set:

1. **Two idioms in one flow.** `policy.filter(...)` is a chained method; `pct.simulate/tradeoff/
   choose` are free functions. Each half is coherent with its own decision — together, the user
   switches idiom mid-line.
2. **Four constructors before the first number.** Declarative and correct; also front-loaded.
3. **`Parcelling` is jargon.** It is the PD-imputation ruler. The name does not say so.

The owner declared the subject *cosmetic* in the precise sense of **coming after the
architecture decisions** — not optional. The map's own ruler is explicit: *"an architecture
decision that produces an API that is hard to use has failed, even if the types are correct."*

## Decision 1 — the spine, in two lines (owner)

> **`CreditPolicy` declares what you DECIDE. `Premise` declares what you ASSUME.** Every output
> vector is born from one of the two, and from nowhere else.
>
> **A method declares, a free function computes.** No method touches the base; every free
> function receives first the thing it acts on, and returns a table.

**The first line is not this session's invention**: it is the *"changes when"* criterion of
`docs/research/architecture-critique.md` §1 — the critique that originated the map — and the same
one #155 used to decide take-up's address. Writing it into the family makes the criterion legible
**in the writing** instead of alive only in an ADR. After #155 it is **exact**: #116's three
vectors live in three places, and each place says whose decision it is.

| vector | where it is declared | nature |
|---|---|---|
| `decision` | `.filter(...)` on `CreditPolicy` | **rule** — changes when the policy changes |
| `contract` | `take_up=` on `Premise` | **premise** — changes when the question changes |
| `outcome` | `stress=` / `outcome_from=` on `Premise` | premise — idem |

**The second line answers friction 1, and the finding is that the rule already existed and had
never been written**: no method in the package touches the base, and no free function exists
without receiving data or a table. **These are not two idioms — it is a boundary the surface
never announced.** The research found the same cut in **polars** (context is a method, an
expression is a free function) and **sklearn** (verbs are methods, composition is a free
function); neither is accused of switching idiom, because the cut follows a real distinction.

This **replaces** the #121 statement the session had rewritten midway (*"the verb names the
stage's role in the funnel"*): with the policy down to one verb there are no roles left to
distinguish, and the line becomes redundant.

## Decision 2 — no modelling default hides the *existence* of a mechanism (owner)

The proposal to give the premise a literal default in `Study` was **rejected**. Friction 2 —
four constructors before the first number — is declared an **assumed cost**, mitigated only by
the `repr`.

> **No modelling default hides the *existence* of a mechanism — only its parameterisation.**

Verifiable, and it explains why `calibrate_on` passes and a premise default would not. #155 used
this rule as the foundation of its ruling A, on the same day it was born.

## Decision 3 — the premise is **one** type: `Premise` (owner)

`Parcelling`/`External` and the later `ScorePremise`/`ColumnPremise` die. The ruler that decided
it: *a union signature pays off when the shared part dominates.* Count before the owner's
clarification: **1 shared × 4 exclusive**. After (*"the bins can be used there for the take-up
question"*): **3 shared** (`bins`, `calibrate_on`, `take_up`) **× 1 exclusive on each side**. The
union began to pay.

Two facts closed it:

- **The owner wants a default** (*"always our parcelling by default"*). A default lives in a
  **signature**; with two types there is no default — you are forced to name a type to start.
- **The shape is already today's.** `policy.py:33` has `estimated_default_col: str | None = None`
  and the engine branches when it is filled (`simulation.py:548`, `:682`). **Not a new pattern —
  the current pattern with a better name.**

**Declared price:** `stress` together with an external outcome becomes a **hard error** (rung 2).
With two types it was unexpressible. One error, obvious message.

**Amendments:** to **#117** (the premise partition falls from two members to one) and to **#155's
ruling A**, which had closed hours earlier saying *"`ColumnPremise` scalar only, because it has
no baseline"* — that falls, because the bins serve the contract axis in both modes, which is the
asymmetry #155 had used to justify two types.

## Decision 4 — the field names (owner)

- **`.filter` does not change.** Renaming it (`.decide`) was proposed and refused: it pays
  dplyr familiarity — the map's declared UX ruler — on the package's most used verb, to buy
  perceived regularity once.
- **`.rate` → `take_up`**, in the conversion sense (rejecting `.convert`): `take_up` appears
  **20 times** in `src/` and is a grid column by #146; `convert`/`conversion`, **zero** —
  introducing it would be the vocabulary duplicate #131 killed. Then #155 took the contract axis
  out of the policy; the name survived and changed address, becoming `Premise`'s `take_up=`.
- **`outcome_from="parcelling"` | column name.** `inferred_`/`estimated_`/`imputed_`/`assumed_
  outcome` were rejected for three reasons: the literal default **names the mechanism in the
  signature** (Decision 2 in its strongest form); **symmetry with `calibrate_on`**, since both
  answer *"where does it come from"*; and the object's internal rule — **each axis accepts either
  a sentinel naming the mechanism, or a concrete value**. `outcome=` is taken by `DataSchema` for
  the **observed** column. And *parcelling* returns as a **mechanism** name — friction 3
  complained about it as a **type** name, where it did not say what the object does.
- **`take_up`: `"binned"` or scalar.** A scalar is **flat**; there is nothing to calibrate.
  `"binned"` and not `"observed"` because `calibrate_on` already says **which population**; what
  was missing is the **granularity** — and `bins=` is in the same call, not in a footnote.
- **`calibrate_on="global"` (default) | `"keep_in"`** — **against what #139 closed** (*"`global`
  is burned"*, *"`global` is not born"*). New measured fact that weakens the alert: today
  `"global"` is not a name, it is **one of three aliases** —
  `calibration_base in ("global", "all", "dataset")`. There is no precious word being overwritten.
  Caveat kept: the **rates** coincide between the old and new reading, but the **bin edges do
  not**, and #124's parity proof matches by name — implementation debt, not this decision's.
  `"incumbent"` was considered and refused: **domain vocabulary above pairing**.
- **`stress=`, not `inflation=`.** Objection raised by the owner himself. The package already has
  the word, and #117 wrote literally *"the stress **is** the inflation"* — it was already decided
  to be **one** concept. `inflation` would be the second word for it, the duplicate #131 killed in
  `rating`/`Rating`. That the `*Stress` **types** die does not change it: **the type dies, not the
  word.**

## Decision 5 — `by=` means "one per group", and the imputation ruler is global, always

The `per=` this session had proposed for the rating suggester was **withdrawn**. #142's text is
*"it calibrates one ruler per group **without anyone asking**"* — the axis is *"without anyone
asking"*, not "reading versus modelling". In `tradeoff`, partitioning the ruler was a hidden side
effect; in the suggester, fitting one ruler per segment **is the verb's product**.

> **`by=` means "one per group"** — one grid per group (`tradeoff`), one criterion applied per
> group (`choose`), one table broken by group (`swap_in_table`), one ruler fitted per group
> (`suggest_rating`). One sense in all four.
>
> **The imputation ruler is global, always — no argument partitions it, ever.**

The second is what #142 actually measured, and stated on its own it protects the ruler
**everywhere**, not only where `by=` appears. The earlier phrasing (*"`by=` is a reading
argument"*) was weaker and badly formed.

## Decision 6 — three argument categories, not two

Applying the reading-versus-modelling test to every public argument gave **zero violations**. The
real finding is that **the test is too binary**. `label=` and `name=` are neither reading nor
modelling: they do not change a number and they do not say how to read the result — they
**address**.

| category | promise | examples |
|---|---|---|
| **modelling** | changes what the engine computes | `ranges=`, `seed=`, `bins=`, `calibrate_on=`, `take_up=`, `stress=`, `outcome_from=`, `draw=`, `score=` |
| **reading** | never changes what the engine computes | `by=`, `criterion=`, `maximize=`/`minimize=` |
| **identity** | changes neither number nor reading; addresses | `label=`, `name=` |

Without the third, `label=` would be forced into "reading" and #142's rule would go slack exactly
where it most needs to be hard.

## Decision 7 — orphan names, and the announcement

**The two rating verbs had never been named, and the route was dead.** #126 closed routing
*"verb names → #128"*; #128 was merged into #123, and #123 went out of scope. The route pointed
outside the map — and #124 put rating/deployment in **block B8 of v0.6.0**, so it was a release
hole, not debt.

```python
suggest_rating(df, *, score=, by=, ...)
suggest_hard_filters(...)
apply_rating(rule, df, *, seed=)
```

`suggest_*` becomes a real family — a prefix feeds autocomplete **and** a reference index, the
research's most direct finding (*"prefixes are better than suffixes because of auto-complete"*).

**The four reading tables were the surface's least coherent corner** — three naming schemes for
four sibling functions. They become `funnel_table`, `delta_table`, `quadrant_table` (was
`quadrant_summary`), `swap_in_table(res, *, by=)` (was `swap_in_by_rating`). Suffix and not
prefix, with the research's support: the design guide reserves a **suffix for variations on a
theme**. And `swap_in_by_rating` stops carrying the break in its name and carries it in `by=`,
which is the right category and generalises.

**The two serialisation units were invisible.** #120 fixed **two**; the surface had a single
`export`: `export_rules(policy, *, rating=None)` / `export_study(study)`, with
`load_rules`/`load_study`.

**`criterion=` in the plot too** — `plot_tradeoff(grid, *, criterion=)` instead of `highlight=`:
the same closed vocabulary of values under different names is the inverse of the tidyverse rule
that a reused name means the same thing. Declared price: `highlight` warned that the plot does
**not** discard points; that difference moves to the verb (`plot_*` draws, `choose` returns rows).

**How the family announces itself** — half of the question no closed card had touched:

- `__all__` **grouped by the three stages** (declare / compute / read), in flow order;
- `help(pycreditools)` prints **the two spine lines** and the three lists — the only place where
  *"a method declares, a free function computes"* can be read before being discovered the hard
  way;
- **reciprocal "see also" on every verb**, pointing at the next one in the flow (`simulate` →
  `funnel_table`; `tradeoff` → `choose` → `plot_tradeoff`). It is R's `@family` mechanism; in
  Python it is a hand-written docstring, and the rule is that **no verb is left without pointing
  at the next**.

## Decision 8 — the grid's two denominators: `approval_denominator` and `default_denominator`

`default_weight` — which the session had published — **fails #142's own criterion**: *"the name
has to say **this is the default rate's denominator** without requiring a footnote."*

The choice is mechanical, not aesthetic: with `<metric>_denominator`, consolidating groups
becomes **one formula, identical for both metrics** — `sum(rate × denominator) /
sum(denominator)`. The group size is not lost: it **is** `approval_denominator`.

> **Every column that is a denominator names the metric it divides.**

## An amendment this session proposed and **withdrew**

The proposal claimed the grid does not publish `take_up_rate`'s denominator, and that this was an
amendment to #146. **Wrong.** `take_up_denominator` = approved at the point =
`approval_rate × approval_denominator`, exactly derivable from two contract columns.
`default_denominator` is not derivable (contracted **and** observed, weighted). **#142 published
precisely the two that are not derivable.**

## An amendment that stands, and it is #119's

**`compare` and `delta_table` may be the same question asked twice.** #119 fixed comparing-N as a
first-class verb over a collection; #127 fixed `delta_table(sim_new: list, sim_old)`. Since #125
put the `study` column on **every** verb's table exactly so `pd.concat` works,
`simulate([s1, s2, s3], df)` would already return the long table `delta_table` reads — and
comparing-N would need no verb. That contradicts a closed decision, so **it is #119's**, not this
card's: recorded as an amendment **to decide, not decided**. (Decided later, in the ticket
breakdown — see ADR 0036.)

## Consequences

- **Release consequence.** This card was a declared blocker in #124. With it, #139 and #155
  closed, #124's work order is satisfied and B1 unblocks.
- **Fact recorded, and it fed gate 4:** `CONTEXT.md` has **zero occurrences** of *infer*,
  *imput*, *estimated*, *premise*, *assum* and *parcelling*. The premise's vocabulary had never
  been written.
- **Research:** `docs/research/verb-shape.md`, 1,530 lines, on an ephemeral branch, **with no
  verdict**. Method caveat recorded there: the proxy blocked every published site, so everything
  was read in the **canonical repositories that generate those sites**, each claim citing the raw
  URL read and the published one as unreachable. **The Buitinck et al. paper was not consulted**
  and nothing is attributed to it.
- **Nothing in the lock was touched.** Checked item by item; the ones that **are** touched are
  named as explicit amendments, never as silent changes.
