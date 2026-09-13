# ADR 0026 — Identity belongs to the `Study`, not to the policy — and the name does not persist

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** how a policy and an experiment get a proper name, where that name lives, how it
  propagates into output, and what the comparison's baseline is. Excludes the dtype of the
  `study` column (#131, ADR 0012) and the baseline label's vocabulary (#131).
- **Tickets:** #125 (this ADR). Consumes #83, #113, #117, #118, #119, #120, #124, #131, #132,
  ADR 0004, ADR 0007.
- **Spec:** the living engine spec, §4.5 (`Study`), §4.7 (the output data contract — the `study`
  column), §4.10 (serialisation and identity).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

Direct request from the owner: be able to **name** the policies in a comparison, and have an
identifier per kind of experiment. Measured state: **there is no identity at all.**

- `compare_policies(sim_new, sim_old)` (`performance.py:127`) takes the simulations **by
  position**; the output carries the literal columns `"Old"` and `"New"` (`performance.py:183`).
  Passing a list becomes `[compare_policies(sim, sim_old) for sim in sim_new]` — with **no label
  per item** (`:142`).
- *"New 1 / New 2 / New 3"* exists only as a hand-written string in the masterclass
  (`tutorial_masterclass.ipynb:1079`), not in the code.
- `CreditPolicy` has no name field. `CreditSimResults.metadata["policy"]` carries the policy's
  dict, but nothing that names it.

It is the direct analogue of tidymodels' `workflow_set`, where each candidate has a `wflow_id` —
and #113 had predicted that *"if comparing-N becomes a verb, #125 becomes a prerequisite."*
#119 made it a verb.

## Decision 1 — the identity is the `Study`'s

The policy goes back to being **anonymous and reusable**, which is coherent with #117
(`CreditPolicy` = `stages` and nothing else) and with #119's long table (one row per study).
*"The same policy under two premises"* gets **two distinct names** — a case that is
inexpressible today.

With that, the card's own point 2 — *"policy identity versus experiment identity: are they the
same?"* — **dissolves**: only the experiment has a name.

Adjacent, from ADR 0007: *"comparing two policies by rating label is misleading."* Policy
identity and a population-relative rating label are not the same thing; #119 separated those two
objects.

## Decision 2 — the name is optional, with a positional default

`Study(name=None)` runs; at read time the anonymous ones get `study_1`, `study_2`, … in order.

**This does not reproduce today's defect**, because today there is **no** path to naming at all
— the default is a fallback, not the only way.

## Decision 3 — a duplicate is a hard error

The name is the key of the long table: two studies with `name="baseline"` is a `ValueError`. The
default fills **only the holes** and **skips a label already taken**, so a hand-written
`study_2` never collides with a generated one. **Zero silent disambiguation** — the class of
defect #132 judges, and the same rule #120 fixed for stage names.

## Decision 4 — propagation is a `study` column on every verb's table

**Measured reason.** #118 fixed that *"N curves = a `for` over N `Study`"*, i.e. the user
concatenates grids by hand — and `pd.concat` preserves neither an object attribute nor
`CreditSimResults.metadata` (`simulation.py:497`). Without a column, #118's `for` produces an
indistinguishable stack.

**Measured design constraint:** a constant column over 5M rows costs **140 MB** as `object`
against **5 MB** as `category` — **28×**. `object` is out; the final dtype is #131's matter.

## Decision 5 — the name is of the session, and does not persist

It survives neither `to_dict`/`from_dict` nor `export()`.

**Accepted consequence, declared: there is no experiment→deployment trace.** Constraint passed
to #120: if `Study` serialises, `name` stays **outside** the serialised value.

**Why.** The name is how a reader tells two rows apart in one table, not a property of the
declaration. Persisting it would make two reloads of the same declared study compare unequal,
and would put a session-scoped label inside the unit whose whole purpose is reproducing the
declaration.

## Decision 6 — the baseline is the current scenario, by default

A correction to the presumed state: the quadrants are **already** relative to the historical
column, not to `sim_old`. `simulation.py:509` does `old_app = df[policy.current_approval_col]`,
and swap-in/keep-in come from there (`simulation.py:523-525`). `sim_old` only feeds
`Delta_Abs`/`Delta_Rel` (`performance.py:183-189`). **Half of what the verb reports already had
"current" as its baseline**; the other half is what required the second simulation by position.

- **Default = the current scenario**, derived from the `DataSchema`'s `approved` column (the
  role fixed in #118). It is not a `Study` of the collection — it is what the book already did.
  So the read verb answers with no mandatory argument.
- **A named `baseline=` is an override**, pointing at a study of the collection **by name**, for
  when the reference is a candidate policy. A non-existent name is a **hard error**.

## Rejected

- **The name on the policy** (part of the value object, travelling in serialisation). It
  contradicts #117 — the policy is reusable across books and across premises — and it makes
  *"same policy, two premises"* unnameable, which is precisely the case the owner asked for.
- **A label passed at comparison time.** It puts the identity outside the thing identified, so
  a `for` over studies still produces an unlabelled stack unless every call remembers to pass it.
- **A name derived from content (a hash).** Unreadable in a table whose whole purpose is to be
  read, and it makes two deliberately identical declarations indistinguishable from one.
- **Silent disambiguation of duplicates** (`baseline`, `baseline_1`, …). Same class #132 judges:
  it changes what the user wrote without saying so.

## Consequences

- **What dies:** `compare_policies(sim_new, sim_old)` by position
  (`performance.py:127-142`), the unlabelled recursion (`:142`), and the literal `"Old"`/`"New"`
  columns (`performance.py:183`). A hard public-surface break — on #124's list.
- **§9.1 item 1 later removed the verb itself:** `simulate` accepts a collection and
  `delta_table(results, baseline=)` reads. Every decision here survives that change — the
  `study` column, the positional default, the hard error on duplicates, and `baseline=` naming a
  study — because they are properties of the **long table**, not of the verb that produces it.
  See ADR 0036.
