# ADR 0035 — Repository layout: separate trees by product, and the ADR number is global

- **Status:** Accepted (decision), **not executed** (see Consequences)
- **Date:** 2026-09-13
- **Decides:** layout
- **Scope:** where agent material, documentation and product live in the repo. Explicitly
  **excludes** the internal structure of `src/pycreditools/`, which depends on the type
  decomposition (#117).
- **Consumes:** #111, #112 (the seven canonical surfaces), #114 (the source card), #115, #117,
  #124.
- **Spec:** none. This decision touches no type contract, which is why the card recorded
  *"living spec: none"*.
- **Measured against:** `release/v0.6` (`24a125a`).

## Why this ADR is named, and why it is late

The artifact gate enumerates **by card number**, and this promise has none of its own: it is
#114's declared deliverable, which named its own file — `docs/engine/adr/0012-repository-layout.md`.
**That number was taken by the output data contract**, and §9.3 of the spec measures the result:
*"the layout ADR was never written."*

So it is named, and the gate checks the name rather than a number that now points at a different
decision.

## Context, measured when the card was written

- `.agents/skills/` = **59 versioned files, against 56 in the whole package** (`src/pycreditools/`).
- `docs/` had **6 subfolders with overlapping purposes** — `adr/` (11 decisions, mixing core and
  Studio), `prd/` (16), `refactor/`, `redesign/`, `dev/`, `agents/` — plus a loose
  `docs/ORIENTATION.md`.
- The root held `prototypes/`, `scripts/`, `validation/`, `images/`, `docker/` and a loose
  `run_v14_benchmark.py`.
- **Studio ADRs (0001 Bancada, 0009 GUI test) lived alongside engine ADRs (0008, 0010, 0011) in
  one folder.**

## Decision 1 — git keeps the lock, not the skills' content

`.agents/skills/` goes into `.gitignore`; `skills-lock.json` stays versioned as a provenance
manifest.

**Measured fact:** the 59 entries are **35 skills, all vendored from `mattpocock/skills`**, with
`source` + `computedHash` in the lock. **None is original to this repo.** What is versioned today
is a copy of upstream.

**Measured caveat, and it is a condition of the decision:** `grep` for `skills-lock` in the repo
returns **zero** — no file here reads the lock. Rehydration depends on an external tool that is
not vendored. **Execution may only ignore the directory after recording, next to the lock, the
exact command that restores from it.** If that command does not exist or is not reproducible,
**the decision falls back to "version everything."**

**Rule for the future:** a skill authored by this repo is versioned, in its own directory,
separate from the vendored ones.

## Decision 2 — Studio and engine are separate trees, by product

`docs/engine/` and `docs/studio/`, each with its own `adr/` and — from v0.6 — its own `spec/`.

**Why.** It matches the map's inclination to freeze the Studio: its tree stops growing without
contaminating the engine's, and a UI decision stops sitting in the middle of a contract decision.

## Decision 3 — the ADR number is global; the folder only routes

`0001..0011` stay as they are; only the path changes. The next ADR is `0012`, in **either**
folder.

**Why, measured: 232 ADR citations across 57 files** — tests, `CONTEXT.md`, docstrings,
`validation/`, notebooks. Renumbering would break all of them and create an ambiguity
(*"ADR 0008 of which tree?"*). With a global number, only the citations of the literal path
`docs/adr/` need a `sed`; **every citation by number stays valid.**

## Decision 4 — research gets its own folder, with a written expiry

`docs/research/` stays, declared **ephemeral**: input to a wayfinder map, archived under
`docs/archive/` with a date when the map that commissioned it closes. **It does not become the
8th canonical surface** — #112's set stays closed at 7; research is an exception **with a written
death rule**.

## Decision 5 — `validation/` is a first-class test, outside `tests/`

It *is* a test (it measures a contract), but it is slow and carries a fixed versioned base
(`shared_base.parquet`/`.xlsx`), so it does not run in every commit's pytest. It stays at
`validation/` in the root, documented as the parity suite, and absorbs `run_v14_benchmark.py`.

**Not** moved into `tests/` (that would drag a binary base there and break existing citations to
`validation/...`), and **not** turned into a public `pycreditools.validation` surface — that
would be an API decision, #117's scope.

**Map consequence:** `validation/` is the instrument of the *"numerical parity with v0.5"*
acceptance criterion that #117/#124 assume. It is declared **alive, not archivable**.

## Decision 6 — the root keeps product and config; everything else goes down

**Stay:** `src/`, `tests/`, `validation/`, `docs/`, `docker/`, and the entry/config files.

**Go down:** `images/` → `docs/images/` (adjusting the 3 `README.md` links); `scripts/`
(`github_board.py`, `prd_board.py`) → next to the agent operation; `run_v14_benchmark.py` →
absorbed by `validation/` (killing a loose script's `sys.path.insert`); `prototypes/` →
**nothing to move**, measured: `prototypes/hf_suggester/` contains only `__pycache__` and nothing
versioned. **The directory disappears by vacuity.**

## Rejected

- **Renumbering ADRs per tree.** Decision 3's 232 citations; and it manufactures the ambiguity it
  was meant to remove.
- **One `adr/` folder for both products.** It is the measured starting state, and it is what put
  a GUI decision between two contract decisions.
- **`validation/` inside `tests/`** — a binary base in the test tree and broken citations.
- **`validation` as a public surface** — out of scope; an API decision belongs to #117.
- **Research as an 8th canonical surface** — #112's set is closed; an exception with an expiry
  rule costs less than opening the set.

## Consequences — and the execution gap, measured in this run

The file move itself was declared **execution** (v0.5.1), not part of the card. §9.3 records it
as **not executed**, and that is still true. Measured on `release/v0.6` (`24a125a`):

| decided | measured today |
|---|---|
| `docs/engine/` with `adr/` and `spec/` | `docs/engine/spec/` exists; `docs/engine/adr/` does not |
| `docs/studio/` with `adr/` and `prd/` | **absent** |
| ADRs routed by product | all 18 live in `docs/adr/` (37 after this ticket) |
| `docs/prd/`, `docs/refactor/`, `docs/redesign/`, `docs/dev/` collapse | all four still present |
| `docs/archive/` for dated supersessions | **absent** |
| `images/`, `scripts/`, `run_v14_benchmark.py` move down | all three still at the root |

**One tension a future session must not resolve by silently picking a side.** `CLAUDE.md` § *Domain
docs* currently declares a **single-context layout** — *"one `CONTEXT.md` + `docs/adr/` at the
repo root"* — which is the state the tree is in and is **not** Decision 2. This ADR records what
#114 decided; it does not re-decide it. Executing Decision 2, or superseding it with the
single-context layout, is a decision of its own and needs its own record — by the map's own rule
that an amendment to a decision is recorded before a line is changed.

The ADR number stayed global regardless (Decision 3), which is why this file is `0035` in the one
folder that exists, and why the promise `0012` reserved could be honoured under a different
number without breaking a single citation-by-number. **That is Decision 3 paying for itself.**
