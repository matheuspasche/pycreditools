# Architecture refactor — the plan

- **Status:** Approved
- **Date:** 2026-07-15
- **Ticket:** #63 (wayfinder map #54)
- **Decides:** the order, the gate, and the test strategy for executing the target
  architecture settled by #77 (the contract) and #78 (the seams).
- **Diagnosis:** `docs/research/architecture-diagnosis.md` (branch
  `research/architecture-diagnosis`, issue #62) — the eleven findings this plan acts on,
  cited below as F1–F11.
- **ADRs this plan earns:** 0009 (the layer rule), 0010 (the engine contract).

## What this is

The v0.5 line fixes metric semantics and ships the canonical material. This plan covers
what happens **after the v0.5 tag**: the rebuild of the engine/studio boundary. It is a
plan, not a build — executing it is a fresh effort with its own wayfinder map.

It deliberately does **not** decide the release version or the deprecation posture. See
[Open questions](#open-questions).

## The gate

Every slice declares its justification on **one** of two axes, in one line, or it is not
a slice:

1. **Architecture / design** — reduced complexity, or a named class of bug that stops
   being possible.
2. **The end client** — speed, accuracy of the numbers, or UX.

It is `or`, not `and`. But a slice that can produce neither is folded into another slice
or dropped.

This gate is not decoration. It is here because #78 approved `ApplyContext` (F9) on the
rationale *"`policy` is `Any` because typing it would close the import cycle"* — and that
rationale does not survive measurement (`stages.py:1` already carries
`from __future__ import annotations`, so `TYPE_CHECKING` types it in three lines). The
slice survives on a **different** argument. Nobody caught it because no gate asked.

Applying the gate collapsed #78's eight findings into **four slices plus an enabler**.

## Prerequisite: this starts after the v0.5 tag

S0 pins the golden master against the canonical sample base (#74), which ships in v0.5.
No slice can start before that base exists.

---

## S0 — Golden master (enabler)

**Justification:** enabler, not a slice. It buys nothing on its own; every slice below
depends on it.

**Why it is first.** The refactor's entire claim is *"the same numbers, at new
addresses"*. The net that would prove that is today nailed to the addresses being moved:
the parity suite is **2,861 lines across 21 files**, and **18 of them import
`studio.analyses`** — `tests/studio/parity/test_bancada.py` opens with
`from pycreditools.studio.analyses import attach_rating, compare_vs_base, exposure_kpis,
policy_kpis, ...`. Those tests do not fail when the functions move; they fail at
`import`, before a single assertion runs. A net that moves with the code proves nothing.

**Content.** Run the ~24 metric functions over #74's canonical base at the v0.5 tag and
freeze the outputs as fixtures, addressed through the **engine's** public API and living
outside `studio/`. The parity tests bound to `analyses` are then deleted as their
functions die — not retargeted.

**Risk.** One to two sessions producing no visible progress. Accepted: it is the only net
that does not move when the addresses move.

---

## S1 — `studio/analyses.py` dissolves; the metrics rise

**Justification:** both axes.

- *Architecture:* the bad-rate line is character-identical in `performance.py` and
  `studio/analyses.py`, and **neither file can import the other** — `performance.py`
  (engine) may not import `studio/`. Fix one, the other stays wrong, silently. ADR 0008
  had to name the copy (`delta_table`) as its reference implementation, which is the
  defect stated out loud.
- *Client:* two surfaces reporting different numbers for the same policy is exactly what
  ADR 0008 exists to stop. This removes the mechanism that keeps regenerating it.

**Content.** `studio/analyses.py` is **1,367 lines and 68 top-level functions** across six
unrelated domains. It is deleted by subtraction into three populations:

1. **~14 forwarders die** — 10 are literally `return <engine_call>(...)`. `gui/session.py`
   (33 wrappers) calls the engine directly. `gui/session.py` itself survives:
   `@st.cache_data` **is** content, so the cache hop is the one hop with a stated reason
   to exist.
2. **~24 metric functions rise to the engine, public.** Private would rebuild F2 outside
   the package (#78).
3. **~20 are genuine app residue** → `studio/presets.py`, `studio/matrix_editor.py`,
   `studio/state.py`.

The same substitution answers F8 (no split decision needed — the file dissolves) and F1
(two hops, not three).

**Internal ordering — deletions first.** The forwarder deletions and the dead/pinned
surface (below) are the **first commits of this slice**. They change no number, so the
golden master goes green for free and is exercised before anything depends on it.

**Risk.** The largest slice. `pycreditools.studio.analyses` has no underscore and imports
today; anyone who reached in breaks — loudly, at `import`.

### Folded in: F10 (dead and pinned surface)

Fails the gate on its own — it is hygiene, not architecture. It rides along because this
release publishes breaks anyway, so the aliases cost nothing extra to remove: the three
deprecated aliases still in `__all__`, `v14_quickfill_rows`, `compare_with_baseline`,
`render_population_selector_v2`.

**`examples.get_notebook_path` / `copy_notebook` are NOT part of this.** They default to
`version=16`, and #76 deletes v14/v15/v16 **in v0.5** — so `copy_notebook()` raises
`FileNotFoundError` at the v0.5 tag and `get_notebook_path()` returns a path to a file
that does not exist (it never checks). That is a v0.5 bug in #76's scope, not an F10 item.
Raised on #76.

### Folded in: F11 (broken signposts)

Fails the gate on its own — it is documentation. It rides along because #78 found that
§4b's *wording* is the documented cause of F1, so this is the slice where the cause is
removed: the layer rule becomes **ADR 0009**, and `CONTEXT.md` is created as `CLAUDE.md`
already promises. `ORIENTATION.md` is **not** renamed — its header forbids the silent
overwrite.

---

## S2 — Saved projects: version stamp and loud refusal

**Justification:** both axes.

- *Architecture:* converts the plan's only three **silent** failure modes into loud ones.
- *Client:* the client stops running a policy with a role silently missing.

**Why it precedes S3 and S4.** F4, the roles half of F3, and the rename each change a
serialized shape, and all three fail the same way for the same reason: **tolerant
deserialization**. `CreditPolicy.from_dict` reads every field with `d.get(...)`, so a
renamed or removed key does not raise — it returns `None`, and the policy runs without
that role. Those are not three risks; they are one risk, three times.

Measured: `ProjectBundle` (`studio/projects.py`) carries `created_at` and **no version
field at all**. There is today no mechanism to *detect* that a file on disk is old, let
alone migrate it.

**Content.** `schema_version` on the bundle; strict `from_dict` (unknown key raises,
missing required field raises); explicit refusal when opening a file from an earlier
version, with a message saying what to do. **Absence of `schema_version` already
identifies "saved by v0.5"** — nothing needs stamping now.

**Not a migrator.** A converter that rewrites old JSON was considered and rejected: it
makes every future slice owe a migration, which is permanent debt for a pre-1.0 local
tool. The stamp is what removes the silent failure; a migrator is optional value on top
and can be added later precisely *because* the stamp exists.

**Risk.** The client rebuilds the project by hand when upgrading. Accepted — pre-1.0,
local tool.

---

## S3 — The declared contract: schema, roles, and the policy carried once

**Justification:** both axes.

- *Architecture:* the undeclared DataFrame schema is the diagnosis's headline finding, and
  the policy is currently carried **twice** on `CreditSimResults` (typed-but-unread
  `policy`, plus `metadata["policy"]` as a dict) with `to_dict()` returning only the
  metadata — a third shape.
- *Client:* `new_approval` changing dtype by mode is the foot-gun that produced the
  four-site branch.

**Content (F3, from #77).** The results frame keeps pandas as its transport and gains a
single artifact declaring it: column-name constants, a schema type carrying each column's
meaning and dtype, validation at `run_simulation`'s exit. `new_approval` is **always a
float weight in `[0,1]`** (`stochastic` emits exactly 0.0/1.0), same for
`approved_pre_rate`. Column roles become **one input-schema object in the engine**;
`CreditPolicy` = that object + composition; `studio/models.ColumnRoles` and
`policy_builder.build_policy` die with it.

**Content (F4).** `metadata["policy"]` dies; `policy` loses its `| None`; `to_dict()`
collapses the three shapes into one.

**Note on the mode branch.** #77 found the `mean() if analytical else (>0).mean()` branch
at four sites was **already a no-op** — the mean of a 0/1 column *is* the fraction of
positives. So F3 is mostly *declaring what is already true*, and its real risk sits in the
roles object (which touches saved projects — hence S2 first), not in the dtype.

**Risk.** Public data contract. Mitigated by S0 and S2.

---

## S4 — `market_default_col`: the name stops lying, and the material follows

**Justification:** axis 2.

The studio's auto-detection **deliberately refuses** the honest input. `detection.py:134`:

```python
if pd.api.types.is_integer_dtype(series):
    continue  # int-only is indistinguishable from a binary flag
```

So a 0/1 bureau flag — which is exactly what #74's generator emits as `market_default`,
and what #77 declared the honest marker — is never detected. The client cannot do in the
GUI what the notebook teaches. The role hint says *"0 a 1: PD estimada por modelo"*
(`detection.py:196`) and `CreditPolicy.__repr__` prints `Estimated default:`
(`policy.py:252`).

**Why this lands here and not in v0.5.** Decided on #63: in the engine the rename changes
nothing — `simulation.py:596` does `astype(float)`, and the mean of a 0/1 column is a
rate, so #76 can pass `market_default` through `estimated_default_col` today without a
line of code. v0.5 therefore ships untouched, and this slice inherits the whole package.

**Content.**

- `estimated_default_col` → `market_default_col`; raise when the column is not 0/1 (this
  kills the *concept*, not just the name — a modelled PD as an input is circular, #61).
- The studio auto-detect accepts int; the role hint and `__repr__` are rewritten.
- The undocumented quirk becomes declared semantics: today, setting the column silently
  **ignores stress** (`simulation.py:547-557`). #77's three-scenario matrix replaces it —
  (1) internal marking only → swap-in PD from the score→PD calibration of the keep-ins,
  **stress**; (2) external 0/1 only → the flag, no stress; (3) both → the flag for
  swap-ins, no stress, warn **once**.
- **Rewrite what v0.5 shipped**: #76's masterclass narrative and #72's remediation text
  both name `estimated_default_col`. This slice owes that rewrite. It is the price of the
  v0.5 decision above, and it was taken with eyes open.
- `_run_estimated_pd_stress_sweep` (`studio/analyses.py:826`, #49's workaround) dies —
  pre-scaling a 0/1 column **saturates** for every factor ≥ 1, so the slider it was built
  for was already flat on #61's canonical material.

**Risk.** Public + persistence. Mitigated by S2.

---

## S5 — `ApplyContext` (F9), shrunk

**Justification:** axis 1 only. Last, and the most legitimate candidate to drop.

**What #78's rationale got wrong.** It sold `ApplyContext` as the fix for
`policy → stages → expressions`. Measured, there are **three** cycles, and F9 is not the
right tool for the one it named:

| Cycle | Dodged today by | This slice? |
|---|---|---|
| `policy ↔ stages` | `policy.py:9` imports stages at module level, so stages cannot import policy → `policy: Any` | Yes |
| `stages ↔ expressions` | `stages.py:132` imports expressions at module level; `expressions.py:199` imports `CutoffStage` back, function-locally, at runtime | **No — #79 closes it in v0.5** |
| `policy ↔ simulation` | `simulation.py:11` imports policy at module level; `policy.py:145` imports `run_simulation` locally inside `.simulate()` | **No — undecided, see Open questions** |

And the "15 function-local imports" cited as evidence is partly noise: `simulation.py:43`
and `:159` do `from .policy import CreditPolicy` inside a method while line 11 already
imports it at module level. Those dodge nothing — they are forgotten duplicates.

**What survives the gate.**

- **A named class of bug.** `_types.py` already defines `SimulationMethod(str, Enum)` and
  `StageDirection(str, Enum)`, and the code deliberately unwraps them at the boundary:
  `simulation.py:352` calls `stage.apply(df, method=method.value, policy=policy)`, so each
  `apply` string-compares `method == "stochastic"`; `CutoffStage` does the same with
  `direction == "gte"`. #57 **proved the damage**: the Bancada trade-off curve comes out
  inverted because `vary_cutoff` writes `">="` where the code tests `"gte"`. Raw strings
  across a boundary, no contract, wrong number on screen. The Enum is the vaccine, one
  field over.
- **Reduced complexity, measurable.** Writing a `Stage` today means receiving a
  `CreditPolicy` with ~15 fields and guessing which matter. Two of the three concrete
  `apply`s — `CutoffStage` and `FilterStage` — take `policy` and **never read it**.
  `RateStage` reads three fields and forwards the object; after #68 kills
  `is_conversion_stage`, **one** field is left (`current_approval_col`), and it computes
  that mask **twice in the same call**.
- **A leaf beats a parent.** `TYPE_CHECKING` would *silence* the `policy ↔ stages` cycle;
  a context object *removes the edge*. Today `RateStage` asks its parent for its siblings
  to learn whether it is itself the last one (`stages.py:262`) — that is the actual smell,
  and #68 already kills that line.

**Content.**

```python
@dataclass(frozen=True)
class ApplyContext:
    schema: InputSchema                  # the roles object from S3
    incumbent_approved_mask: pd.Series   # resolved once per run, not twice per stage
    method: SimulationMethod             # Enum, not str

def apply(self, df: pd.DataFrame, ctx: ApplyContext) -> pd.Series: ...
```

**On the field name.** #78 called it `keep_in_mask`. That name is wrong and must not enter
the ADR: in the engine `KEEP_IN` is the quadrant `old == 1 & new == 1`
(`simulation.py:429-438`), while what the context carries is `old == 1`, i.e.
`KEEP_IN ∪ SWAP_OUT`. It cannot be otherwise — when a stage runs, `new_approval` does not
exist yet. Hence `incumbent_approved_mask`.

**Risk.** `Stage` is exported in `__all__` and `apply` is its abstract method, so any
client's custom `Stage` breaks with a `TypeError` — loud. `register_callable` proves
extension is an intended use case, not an accident.

**Why last.** It changes no number, unblocks no other slice (the cycle that actually
obstructed — `stages ↔ expressions` — is gone by then, via #79), and charges a public ABC
break. It earns its place on bug-class removal alone.

---

## Test strategy

The golden master (S0) is the contract for every slice: **same numbers, new addresses**.
Slices that move a function do so as a **pure rename** — the body is identical, verified
in the `git diff` — and the fixtures prove it. Slices that change content (S3's schema,
S4's semantics) state the intended change and update the fixture in the same commit, with
the diff of the numbers in the PR body.

## Breaking changes

Six of the eight original findings change the public API, the data contract, or a file on
disk. This is a **breaking release**, not internal tidy-up:

| Change | Breaks | How it fails |
|---|---|---|
| F10 aliases removed | `import` | Loud |
| `studio.analyses` deleted | `import` (no underscore; importable today) | Loud |
| Metrics enter the engine's `__all__` | nothing (additive) | — |
| `new_approval` declared float | reads of `results.data` | Quiet but benign — `== 1` still matches `1.0` |
| `Stage.apply` signature | custom `Stage` subclasses | Loud (`TypeError`) |
| `metadata["policy"]` removed | 17 binding sites (10 in `performance.py`) | Loud |
| `to_dict()` shape | saved projects | **Loud only after S2** |
| `estimated_default_col` renamed | client code, saved projects | **Loud only after S2** |

## Open questions

Neither is decided; both are carried in map #54's fog.

1. **The release version and the deprecation posture.** Pre-1.0 clean cut (precedent: #68,
   #78) or a deprecation window? The break inventory above is the input to that decision.
2. **The `policy ↔ simulation` cycle.** `policy.py:145` imports `run_simulation` inside
   `CreditPolicy.simulate()` to dodge it. No ticket has ever decided it, and F9 does not
   touch it. It is the convenience method, a different problem from F9's.

## Corrections to the diagnosis

Carried here so they do not become folklore. Measured on `release/v0.5`:

- **`metadata["policy"]` reach-ins: 17, not 29 (#62) or 38 (#78).** 17 sites *bind* the
  dict (`metadata["policy"]` / `.get("policy")`) across `src` + `tests`, 10 of them in
  `performance.py`. The higher counts are field *reads* downstream of those bindings —
  a different measurement, worth stating as such.
- **Two of three concrete `apply`s ignore `policy`, not "three of four".** The fourth is
  the abstract method, which has no body.
- **The `Any` is not what blocks typing.** `from __future__ import annotations` is already
  on `stages.py:1`; `TYPE_CHECKING` would type `policy` today. The cycle argument for F9
  is real but is about the *edge*, not the annotation.
