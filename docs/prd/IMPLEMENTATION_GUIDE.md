# IMPLEMENTATION GUIDE — read this before writing any code

> **You (the implementing agent) have no prior context.** Everything you need is
> in this repo. This guide is the contract. Follow it exactly. If anything is
> ambiguous, **STOP and ask the owner** — never guess or invent a workaround.

You are building the **Pycreditools Studio**: a **Streamlit, 100% no-code** GUI
that wraps the `pycreditools` Python package so a user can do everything the
package does — without writing code. The full spec is in `docs/prd/`.

---

## 0. Golden rules (violating any of these fails the gate)

1. **One PRD at a time.** You don't need to be told which PRD — read
   `docs/prd/PROGRESS.md` and take the **first row that is not `DONE`** (obey its
   rules for `IN PROGRESS` / `AWAITING APPROVAL`). Implement only that one.
   **Do not start the next PRD.** Stop at its gate.
2. **Never re-implement engine logic.** The studio only *calls* `pycreditools`
   public API (see `00-overview.md` §8). If you feel tempted to compute KS, fit
   clusters, or simulate by hand — stop; call the package.
3. **No user-typed Python anywhere.** No code editor, no `eval`, no
   `CustomStress` lambdas, no string/`query` filters. Build `Expression` objects
   programmatically from widgets (`00-overview.md` §10 lists all non-goals).
4. **Stay in scope.** Only create/edit the files the PRD lists. Don't refactor
   unrelated code. Don't add dependencies beyond the `studio` extra.
5. **Small, reversible commits.** Commit logically small chunks. Each commit must
   leave the automated validation green (see §3).
6. **Blocking gate.** When the PRD is done and all 4 validation layers pass,
   **STOP and produce the Gate Report (§4)**, then wait for the owner's explicit
   "aprovado". Do not continue without it.
7. **Read before you write.** Read `IMPLEMENTATION_GUIDE.md` (this file),
   `00-overview.md`, and your assigned PRD — in that order — before any edit.
8. **Respect the core/skin boundary (`00-overview.md` §4b).** All logic goes in
   `pycreditools/studio/` (no `import streamlit` — ever). Only the thin Streamlit
   skin (`pycreditools/gui/`) may import `streamlit`. **PRD 00 §4b wins on file
   placement** even if a per-page PRD uses an older single-file name.

---

## 1. Environment setup (do once, at the start of your session)

```bash
git branch --show-current           # must be: feature/gui-streamlit-studio
# if not:
git checkout feature/gui-streamlit-studio

python -m pip install -e ".[studio,dev]"
python -c "import pycreditools, streamlit, plotly; print('ok')"
```
If the `studio` extra doesn't exist yet (you are PRD 01), add it per
`01-app-shell-and-design-system.md` first, then install.

---

## 2. The per-PRD workflow (do this for every PRD)

0. **Select your PRD from `docs/prd/PROGRESS.md`** — the first row not `DONE`
   (obey its `IN PROGRESS` / `AWAITING APPROVAL` rules). Confirm its dependencies
   are `DONE`. Set its Status → `IN PROGRESS` and commit (PROGRESS.md only).
1. **Read** this guide + `00-overview.md` + your selected PRD (in that order).
2. **Print a 5-bullet plan** of how you'll implement the PRD (files you'll
   create/edit, the API calls, the tests you'll write). Keep it short.
3. **Implement** the PRD's deliverables, in small commits.
4. **Write the tests** the PRD's "Validação automática" lists (under `tests/studio/`).
5. **Run all 4 validation layers** (§3). Make everything green. If something can't
   pass, **STOP and ask** — do not delete/skip the test.
6. Set the PRD's Status → `AWAITING APPROVAL` in PROGRESS.md, **produce the Gate
   Report** (§4) and **STOP**. Wait for the owner's "aprovado".
7. **After "aprovado":** set Status → `DONE` (+ date) in PROGRESS.md, commit, STOP.

You never advance to the next PRD yourself.

---

## 3. Automated validation — the 4 layers (all must be green)

Run these from the repo root. Paste the **full output** into the Gate Report.

```bash
# Layer 1 — Lint / style
ruff check src/pycreditools/gui tests/studio

# Layer 2 — Logic unit tests (pure functions: state, data_access, policy_builder, charts data)
pytest tests/studio -q -k "not apptest and not parity"

# Layer 3 — Streamlit AppTest (headless UI smoke + behavior)
pytest tests/studio/apptest -q

# Layer 4 — Parity (only when the PRD touches engine orchestration)
pytest tests/studio/parity -q
```

### Layer 2 — logic tests
Test the **pure helpers** in `pycreditools/studio/`, not Streamlit. Examples:
`detect_roles(df)` returns the right roles on sample data; `population_filter`
subsets correctly; `policy_builder.build_policy(roles, rows)` produces a
`CreditPolicy` whose `to_dict()` round-trips; a chart builder returns a
`plotly.graph_objects.Figure` with the expected number of traces. Use the shared
fixtures in `tests/studio/conftest.py` (§5).

**Mandatory boundary test** (`tests/studio/test_boundary.py`): assert that **no
module under `pycreditools/studio/` imports `streamlit`** (walk the package source
and check imports, or import each module with `streamlit` removed from
`sys.modules` and a guard). This is what keeps the framework swappable
(`00-overview.md` §4b) — it must pass on every PRD.

### Layer 3 — Streamlit AppTest (headless, no browser)
Use `streamlit.testing.v1.AppTest`. Pattern:
```python
from streamlit.testing.v1 import AppTest

def test_page_runs(studio_state):                 # fixture injects a ready StudioState
    at = AppTest.from_file("src/pycreditools/gui/pages/3_Policy_Studio.py")
    at.session_state["studio"] = studio_state     # inject dataset + roles so no upload needed
    at.run()
    assert not at.exception                        # page renders with no error
    # then assert on widgets/outputs, e.g.:
    assert len(at.dataframe) >= 1
    # simulate interaction:
    at.button(key="add_rule").click(); at.run()
    assert not at.exception
```
Every page PRD must have at least: (a) "renders with an empty/guarded state with no
exception", and (b) "renders with an injected dataset and produces the page's key
output (table/chart) with no exception", plus any interaction the PRD calls out.

### Layer 4 — Parity (the anti-error invariant)
**Definition of parity:** the studio, given the same inputs, must produce the
**same numbers as calling `pycreditools` directly**. The studio is a thin wrapper;
any divergence is a bug. Write parity tests that:
- build the artifact via the studio helper (e.g. `policy_builder.build_policy`),
- compute the result via the studio path (e.g. `run_simulation`),
- compute the **same** result by calling the package directly in the test,
- assert equality (exact for counts, `pytest.approx`/`np.isclose` for rates).

Use `generate_sample_data(n_applicants=5000, seed=42)` as the fixed oracle base
(reproducible, no external file). The repo's `run_v14_benchmark.py` is a secondary
manual oracle for the v14 funnel/legacy numbers — reference it, don't depend on the
large `dataset_v14.csv` in tests.

> If a layer doesn't apply to a PRD (e.g. PRD 01 has no parity), the PRD says so.
> Otherwise all four are mandatory.

---

## 4. The Gate Report (what you hand the owner — then STOP)

When done, output **exactly** this, filled in:

```
## Gate Report — PRD <NN> <title>

### Definition of Done
<the PRD's DoD checklist, every box checked, each with a one-line note>

### Automated validation (all green)
- Layer 1 ruff:     <paste output / "0 errors">
- Layer 2 logic:    <paste pytest summary, e.g. "12 passed">
- Layer 3 AppTest:  <paste pytest summary>
- Layer 4 parity:   <paste pytest summary / "N/A for this PRD">

### Diff
<output of `git diff --stat <base>..HEAD` and the list of new files>

### Visual verification script (for you to run)
<the PRD's "Verificação visual" steps, copied, ready to follow>

### Ask
"PRD <NN> está completo e com as 4 camadas verdes. Aprova para eu seguir para o
próximo PRD?" 
```
Then **wait**. Do not implement anything else until the owner replies "aprovado"
(or gives fixes). If they request changes, apply them, re-run all 4 layers, and
re-issue the Gate Report.

---

## 5. Test scaffolding (create in PRD 01; reuse everywhere)

```
tests/studio/
├── conftest.py            # shared fixtures
├── test_boundary.py       # core has no `streamlit` import (Layer 2, mandatory)
├── test_models.py         # studio/models + session bridge (logic)
├── test_data.py           # studio/data + studio/detection (logic)
├── apptest/               # Streamlit AppTest (Layer 3)
│   └── test_<page>.py
└── parity/                # Layer 4
    └── test_<topic>.py
```

`tests/studio/conftest.py` must provide:
- `sample_df` → `generate_sample_data(5000, seed=42)`.
- `roles` → the `ColumnRoles` auto-detected from `sample_df`.
- `studio_state` → a fully-populated `StudioState` dict ready to inject into
  `at.session_state["studio"]` (dataset + roles set; no policy yet).
- `studio_state_with_policy` → same, plus one built `CreditPolicy` (v14 hard
  filters) as the active policy.
- `studio_state_with_rating` → plus a fitted `RiskGroupResult` + labels.

Keep fixtures fast: 5000 rows, `method="analytical"`.

---

## 6. Coding conventions (so cheap agents stay consistent)

- Python ≥ 3.10, type hints on public functions, docstrings one-liner.
- `ruff` config already in `pyproject.toml` (line-length 100, rules E/F/I/W/UP).
- UI copy in **pt-BR**; identifiers in English (`00-overview.md` §9.8).
- Pure logic lives in the **`pycreditools/studio/`** core (`models`, `detection`,
  `data`, `policy_builder`, `analyses`, `charts`, `projects`) — unit-testable
  **without** Streamlit and importing **no** `streamlit`. The `pycreditools/gui/`
  skin (`session.py`, `components/*`, `pages/*.py`) is thin: read session → call
  core → render. Don't bury logic in page files or in `gui/` (`00-overview.md` §4b).
- Wrap engine calls in `try/except` → `st.error(translated message)`. Never show a
  raw traceback (`00-overview.md` §9.6).
- Cache expensive calls with `@st.cache_data` keyed on `(df_hash, params)`
  (`00-overview.md` §9.2).
- Don't print to stdout for UI; recreate report numbers as tables
  (`05-simulation-and-impact.md` note on `print_*`).

---

## 7. Common failure modes (avoid these — they fail gates)

- ❌ Re-implementing KS/clustering/simulation math → call the package.
- ❌ Scraping `print_*` stdout → recompute from `sim.data` / `summarize_results`.
- ❌ Putting logic in `pages/*.py` so it can't be unit-tested → move to helpers.
- ❌ Deleting/disabling a failing test to "make it green" → STOP and ask.
- ❌ Adding angulated/linear/monotonic stress or any user Python → out of scope.
- ❌ `actual_default` is NaN for non-hired rows; KS/grouping must `dropna` on the
  target and report effective N (`00-overview.md` §9.5).
- ❌ `import streamlit` inside `pycreditools/studio/` → breaks the core/skin
  boundary and fails `test_boundary.py` (`00-overview.md` §4b).
- ❌ Touching files outside the PRD's scope.
- ❌ Continuing past the gate without an explicit "aprovado".

---

## 8. Kickoff prompt for a fresh session (the owner pastes this — UNCHANGED every time)

> Paste this **as-is** for every PRD. It does not name a PRD — the agent picks the
> next one from `PROGRESS.md`. Only thing to fill once: the repo path.

```
You are implementing the Pycreditools Studio — a Streamlit, 100% no-code GUI that
wraps the `pycreditools` package — ONE PRD at a time. You have NO prior context;
everything you need is in this repo.

Repo root: <fill path once>. First run `git branch --show-current`; it must be
`feature/gui-streamlit-studio` (if not, `git checkout feature/gui-streamlit-studio`).

MANDATORY reading, in this order, before writing any code:
1. docs/prd/IMPLEMENTATION_GUIDE.md   (rules, validation, gate — follow exactly)
2. docs/prd/PROGRESS.md               (tells you WHICH PRD to do — the first row not DONE)
3. docs/prd/00-overview.md            (architecture, file layout, state, design system, non-goals)
4. the PRD file PROGRESS.md points you to (the ONLY PRD you implement now)

Pick your PRD from PROGRESS.md: the first row whose Status is not DONE. Obey its
rules for IN PROGRESS / AWAITING APPROVAL. Confirm its dependencies are DONE, then
set its Status to IN PROGRESS and commit (PROGRESS.md only).

Hard rules (from the guide):
- Implement ONLY that one PRD. Do not start any other PRD.
- Never re-implement pycreditools logic — only call its public API.
- 100% no-code: no user-typed Python in the UI. Respect 00-overview §10 non-goals
  (e.g. only flat AggravationStress).
- Keep the core/skin split: all logic in `pycreditools/studio/` with NO
  `import streamlit`; only `pycreditools/gui/` imports streamlit (00-overview §4b).
- Work in small commits. Then run ALL 4 validation layers (ruff, pytest logic,
  Streamlit AppTest, parity-if-applicable). Everything must be green.
- BLOCKING GATE: when the PRD is done and green, set its Status to AWAITING
  APPROVAL in PROGRESS.md, output the Gate Report (filled Definition-of-Done +
  full test output + `git diff --stat` + the visual verification script), and STOP.
  Wait for my explicit "aprovado".
- After I say "aprovado": set the row to DONE (with date) in PROGRESS.md, commit,
  and STOP — do not start the next PRD.
- If anything is ambiguous or a test can't pass, STOP and ask me — do not guess.

Start by reading the 4 items, then print a 5-bullet plan for your PRD, then implement.
```

The build order lives in `PROGRESS.md` (and `00-overview.md` §11). Always take the
first non-DONE row; never start a PRD whose dependencies aren't DONE.
