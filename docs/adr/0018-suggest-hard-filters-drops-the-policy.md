# ADR 0018 — `suggest_hard_filters` drops its `policy` parameter

- **Status:** Accepted
- **Date:** 2026-09-10
- **Scope:** the one change `suggest_hard_filters` needs to cross the contraction. What the
  function *is* — a standalone suggester of rejection thresholds, with budget and lift (#126) —
  is not in question.
- **Tickets:** #180 (this ADR). Consumes #126, #132.
- **Amends:** the living engine spec, §4.9 — *"`suggest_hard_filters(...)` # já existe,
  intacto"* — and the same line in ticket 12 (#167).
- **Measured against:** `release/v0.6` (`b884b95`).

## Context

§4.9 and ticket 12 promise to re-export the function **intact**. Measured, that is impossible:

- `screening.py:14` imports `CutoffStage`/`FilterStage` at module top, used only inside
  `_hf_policy_acts_on`; `screening.py:15-16` imports `CreditPolicy` under `TYPE_CHECKING`.
- The signature (`:388-398`, nine parameters) takes `policy: CreditPolicy | None = None`.
- `_hf_policy_acts_on` (`:375-386`), the only reading of the policy, is `isinstance` against the
  two stage classes plus a word regex over `str(stage.condition)`.

All three types die in ticket 16. And the parameter has **one consumer**: the warning at `:510`,
*"policy already acts on candidate column …"*. The only caller that passes `policy=` is one test
(`tests/test_hard_filters.py:247-252`); the README, the masterclass notebook and
`validation/measure_v05.py` do not.

## Decision

`policy` leaves the signature, and with it `_hf_policy_acts_on`, the module-top import of the
stage classes and the `TYPE_CHECKING` import of `CreditPolicy`. The function stops knowing any
type of the package.

**Why.** The warning it feeds dies with the other sixteen core warnings in ticket 16 (§4.11),
which leaves a parameter nothing consumes — the pathology §4.4 names twice, `base_rate`
*"Ignored when `observed_col` is set"* (#129) and the write-only `params` (#126). And #126 had
already set the direction: the policy's rules may filter a suggester's input, *"sem acoplar o
sugestor à política"*.

## Already decided, recorded so no one re-asks

- The warnings at `:471` (coverage) and `:527` (lift inverting against the declared direction)
  go to degree 3 — they become numbers (#132's table).
- The output's shape — the five containers of `HardFilterSuggestion` — is outside v0.6 by the
  owner's ruling of 2026-09-07 (§8): `screening.py` is touched only as a consequence of
  something else changing, never redesigned.

## Rejected

- **A list of already-used columns** (the caller passes `policy.columns()`), reported as a
  column of the output table — keeps the information without a package type, but changes the
  shape of `screening`'s output, which §8 keeps out.
- **The new `CreditPolicy`**, read through the tree instead of a regex — couples the suggester
  to the policy, which #126 refused, and the warning would still need a number somewhere.

## Consequences

- The report *"this column is already in your policy"* is gone. The user declared that policy.
- One test is removed or rewritten; the other sixteen of `tests/test_hard_filters.py` are
  untouched.
- The change lands with ticket 12's re-export, before ticket 16 deletes the stage types.
