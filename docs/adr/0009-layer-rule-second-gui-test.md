# ADR 0009 — The layer rule is the second-GUI test

- **Status:** Accepted
- **Date:** 2026-07-15
- **Scope:** every placement decision between `pycreditools/` (engine), `studio/`
  (framework-agnostic core) and `gui/` (Streamlit skin).
- **Supersedes:** `docs/prd/00-overview.md` §4b — the "no-rework" rule. §4b's *intent* is
  retained in full; its *test* is replaced.
- **Ticket:** #78 (wayfinder map #54). Plan: `docs/refactor/00-architecture-refactor.md`.

## Context

§4b exists to keep the framework choice reversible: the owner wants the option of moving
to a server or another UI later without rewriting everything. That intent is correct and
still held. It is not what this ADR changes.

The defect is the **wording of the test**. §4b says the core:

> Holds ALL studio logic: dataclasses […], column detection […], data IO + population
> filter […], policy assembly […], analysis orchestration (`analyses.py` — thin wrappers
> over `pycreditools` returning plain DataFrames/dicts) […]

Read literally, and it was: **a forwarder is studio logic**. So the rule asked for an
address in `studio/` for every verb the studio can perform, and it got one — 68 of them.
`studio/analyses.py` is 1,367 lines across six unrelated domains, and roughly 14 of its
functions are literally `return <engine_call>(...)`. §4b did not merely permit that file;
the parenthetical **prescribed** it.

The second-order damage is worse than the file. `performance.py` (engine) cannot import
`studio/`. So while `delta_table` lives in `studio/analyses.py`, `print_delta_table` in
`performance.py` **must** be a copy of the same arithmetic — and ADR 0008 was then forced
to name the copy as its reference implementation. One sentence of placement guidance
produced a duplicated metric the package cannot deduplicate without moving the metric.

## Decision

The placement test is: **"would a second GUI have to rewrite this?"**

- **Yes** → it belongs in `studio/`.
- **No — it is a call into the engine** → call the engine. There is no middle address.

The corollary, which is the part §4b got backwards: **decoupling comes from the engine not
knowing a dashboard exists — never from the middle hop.** A forwarder has no content, so
it protects nothing. It is a name, and names are not seams.

`@st.cache_data` wrappers in `gui/session.py` are **not** forwarders and survive: caching
is content, and it is the one hop with a stated reason to exist (Streamlit needs the
`_`-prefixed unhashable args).

## Consequences

- `studio/analyses.py` is deleted by subtraction, not split: ~14 forwarders die, ~24
  metric functions rise to the engine (public — private would rebuild the duplication
  outside the package), ~20 land in `studio/presets.py`, `studio/matrix_editor.py`,
  `studio/state.py` as genuine app residue. F8 therefore needs no split decision and F1
  goes to two hops.
- Metric arithmetic lives in the engine, once. `performance.py`'s printers become
  formatting over that arithmetic instead of a second copy of it.
- ADR 0008's reference implementations move with the metrics; the ADR's *contract* is
  unchanged.
- The rule leaves `docs/prd/` — a product-requirements directory, where the code was
  citing it from its own docstrings by a bare filename that resolves nowhere from the repo
  root — and lives here, where a decision belongs.

## Alternatives rejected

- **Keep §4b and split `analyses.py` by domain.** Rejected: it addresses the file's size
  and leaves the cause intact. The forwarders would be redistributed, not removed, and the
  metric duplication would survive untouched.
- **Sharpen §4b in place.** Rejected: the rule is a load-bearing decision the code cites,
  and it was unfindable in a PRD directory. That is F11, and moving it is the fix.
