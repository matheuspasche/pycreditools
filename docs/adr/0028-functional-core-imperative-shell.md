# ADR 0028 — Functional core: a per-row draw keyed to position, and the calculate/present border

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** randomness in the core, the five `print_*` functions, and the plot stack's import
  weight. Excludes the comparability decision the seed enabled (#144) and the output contract of
  the four tables (#131, ADR 0012).
- **Tickets:** #127 (this ADR). Consumes #113, #116, #117, #118, #119, #122, #124, #125, #131,
  #135, #140, #143, #144, and `docs/research/functional-core.md`.
- **Spec:** the living engine spec, §4.6 (the engine — the randomness mechanism, the purity
  contract of the verbs), §4.7 (the output contract of the four tables), §4.11.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

IO and presentation are cooked into the core.

- **Five `print_*` functions with a stdout side effect**: `print_delta_table`,
  `print_quadrant_summary`, `print_swap_in_by_rating`, `print_rating_quadrant_table`
  (`performance.py`) and `CreditSimResults.print_funnel_table` (`simulation.py`). Calculation,
  formatting and terminal writing in the same place. **A library that `print()`s does not
  compose** — an MCP client, the Studio or an agent get no return value, only the side effect.
- **`np.random.random` called straight off global state** (`simulation.py:518`, `:578`);
  `run_simulation` accepts neither a seed nor a `Generator`. A stochastic run is
  irreproducible.
- **`matplotlib`/`seaborn` imported in the core** (`visualization.py`).

The seed was being asked in three places — here, in #119 (as a study premise) and in #135 (the
research on nested randomness). **This card became its sole owner**, because *"where does the
seed enter"* and *"who still draws from global state"* are one investigation.

By the owner's ruling this card was **merged with #144** (comparability between grid points):
the research (`docs/research/functional-core.md` §2) showed that Q15's forms C/D *are* the
comparability decision, so deciding the seed without deciding comparability was deciding half.

## Decision 1 — a per-row draw, keyed to position

**No global `np.random` remains in the core.** Every draw comes from a deterministic function of
**(the study's seed, the row's position in the bound base, the name of the draw)** — form D of
the research.

**The `applicant_id` objection does not bite.** #118 killed `applicant_id` because it was
*fabricated* (`range(len(df))`, `deployment.py:422`) and travelled in the schema all the way to
deployment. The key here **is not a column, is not schema, and does not travel**: it is internal
to the engine. #117 fixed that the base enters the verb, so every point of a grid shares **one
bind**, and position is already stable within the study.

**Measured in the deciding session** — the engine never reorders: zero `sort_values` /
`sort_index` / `reset_index` in `simulation.py`, `stages.py`, `sweep.py`. Position stability is
by construction, not by trust. The exposure that remains is only *between* studies over the same
data in a different order — which #125 already does not treat as comparable.

**Drop-in at the 4 sites.** All have the same shape: `np.random.random(<size of a subset>)`
assigned into `df.loc[mask]` — `simulation.py:604` (unknown outcome), `:664` (`len(swap_ins)`),
`stages.py:458` (`swap_ins_mask.sum()`), `:469` (`len(df)`). The draw is **positional within the
mask**, and the mask changes with the cutoff — **that is exactly where comparability dies.** The
swap is to draw a base-length vector and select by the mask. No mask changes; no calculation
changes.

**Price measured (3M rows):**

| form | cost per point |
|---|---|
| today, 4 masked draws | 39.3 ms |
| form D, 4 full-length vectors | 45.4 ms (**+6.1 ms = +7.4%** over #143's ~82 ms/point) |
| form D with a per-study cache | **0 ms** |

With the cache it is **cheaper than today**: the key is invariant across the whole grid, so the
4 vectors are generated once per study and reused at every point. Cache cost: 4 × 3M × float64 =
96 MB — an implementation choice, not an architectural one.

**The parallel bug closes with it.** The 0.41 p.p. under `parallel=True` (#140) exist because
each spawned worker initialises its own global state. With the number derived from (seed,
position, name), no worker needs shared state — and the start-method dependency (spawn vs fork)
stops being a question at all. **One mechanism closes both holes**, and the research's open item
to measure POSIX/fork dies without the measurement.

## Rejected (and why each one fails a different requirement)

- **Forms A and B — a consumed stream.** A stream consumed in order makes the second draw depend
  on how many numbers the first pulled: §1.2 of the research measured 3 identical runs giving
  **816 / 847 / 800** defaults. **Reproducible, not comparable.**
- **Form C — `SeedSequence.spawn` per grid point.** It gives independence, which is the opposite
  of what a grid needs: #122 fixed the grid as a cache of a frontier read row against row, i.e.
  **one study with N variations**, not N independent studies. `SeedSequence` stays in the design,
  but as derivation **by draw name**, never by grid position.
- **Methods on the result for the four tables** — see Decision 2.
- **An optional `[viz]` extra, or removing plotting** — see Decision 3.

## Decision 2 — the `print_*` return a table, as free functions

**The fact that decides it:** 363 lines, 41 calculation operations, **zero returned values**,
all `-> None`. The number does not exist outside stdout, and whoever wants it in another cell
redoes the arithmetic.

**The research's caveat about `print_delta_table` resolves: it fits in one table.** Despite its
15 `print`s and 170 lines, it is metrics on the rows × (Legacy, New_i) on the columns with
abs/rel deltas — in **long format** (`study` × `metric` × `value`) that is one table, and #125
already put a `study` column on every verb's table.

**As free functions, not methods.** The owner first leaned towards a method on the result; the
decision fell to free functions after two objections:

- **`delta_table` has no receiver.** Its signature is `(sim_new: list[CreditSimResults],
  sim_old)` — N studies against a baseline. A method only works if one of the N becomes the
  arbitrary owner of the table, and #119 already decided comparing-N as a first-class verb over
  a collection, with no container type.
- **The rule would be split.** #117 took execution out of the objects. A method on the result
  would create *"calculation over input = free function, calculation over result = method"* — a
  rule by arity, which the user has to memorise. The dplyr ruler is one rule: a verb that takes
  and returns.

Notebook convenience survives: `delta_table(sims)` is still one line. What is lost is
`sim.<tab>`.

**Presentation stays in the package**, as a separate border layer receiving the finished table —
versioned and testable. Against the research's form C (formatting leaves the package), whose
price is recreating the helpers outside, without version control, in every cell, forever.

**Hard break**: 8 mentions in `__init__.py` and 42 external uses (notebooks and tests). On
#124's list.

## Decision 3 — plotting stays in the core, with a lazy import

`visualization.py` (matplotlib + seaborn) **stays in the package and stays a hard dependency**,
but leaves the eager `__init__.py` (`:51`).

**Measured** (`python -X importtime`, warm cache): `import pycreditools` = **2294 ms**
cumulative, of which **seaborn = 1105 ms (48%)**, matplotlib = 198 ms inside it, pandas =
699 ms. **Half the package's import time is the plotting stack**, paid today by every consumer
who only wants the numbers — MCP, Studio, agent, test suite.

An optional extra (`pycreditools[viz]`) and outright removal were refused: the lazy import
captures the whole measured gain without breaking anyone and without pushing plotting out.
**Not a boundary decision** — it is execution, and enters #124 as an additive item, not a break.

## Consequences

- **Tie to #131:** the four tables become returned values, so they fall under the output
  contract — declared column names and dtypes. The pt-BR presentation literals in the core
  (`performance.py:515-519`) die with the separation.
- **Mandatory seed** already comes from #116. §1.1 of the research measured that there is **no
  seed anywhere** (`seed` = 0 occurrences across the six core modules), so there is no migration:
  this is design on empty ground.
- **One ADR covers two cards.** The comparability half (#144) is the same decision seen from the
  grid's side, and is recorded with it.
- **Input inherited from #117:** with an externally observed outcome being a 0/1 column rather
  than a probability, **the draw disappears from that path** — analytical and stochastic agree
  by construction on that population. One fewer source of randomness to re-anchor. (#121 later
  added one back, deliberately: the desk draws even on the analytical path, so *analytical* now
  means *deterministic given the seed*.)
