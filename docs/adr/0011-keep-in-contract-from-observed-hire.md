# ADR 0011 — The keep-in contract weight comes from observed hire, not a silent 1.0

- **Status:** Accepted
- **Date:** 2026-07-22
- **Scope:** the engine's keep-in contract weighting — `simulation.py`, `stages.py`,
  `policy.py` — and the `studio/` types that mirror `current_hired_col`.
- **Amends:** ADR 0010, section *"A scalar/anonymous RateStage does not re-gate the
  keep-in"* (#94), and its default-rate note (`new_approval.sum()` denominator).
- **Enables:** #101 — the design refactor ADR 0010 anticipated: encode contract status in
  `new_approval` itself so the denominator carries no NaN test. This ADR lands the
  *mechanism* (no-outcome keep-in → weight 0); dropping the `notna()` proxy denominator is
  the remaining #101 step and is **not** done here.
- **Tickets:** #103 (this bug/ADR). Spins off #105 (observed-rate generalization).

## Context

ADR 0010 (#94) declared that a scalar/anonymous `RateStage` over a book with
`current_approval_col` active **bypasses** the keep-in: every keep-in passes at `1.0`. The
stated rationale was "keep-in take-up comes from what the data records about the keep-in; a
scalar rate records nothing, so the book passes through."

That contract has a hole. The core `simulate()` sources the keep-in's observed take-up
**only** through `.rate(observed_col="hired")`. Without that stage — the common path — every
approved keep-in is contracted at weight `1.0`, **including the approved-but-never-hired**
(no-outcome) rows. Those enter the default-rate denominator at weight 1.0 and **deflate the
rate silently**. `CreditPolicy` already declares `current_hired_col` (`policy.py:32`), but
the core **never consumes it** — only `studio/` and `gui/` do.

Measured on the challenger policy (HF + score_5 q0.55 cut, bins=5), 60k base, seed 7:
without `observed_col` the contracted keep-in inflates 4 168 → 9 089 (the 4 921 extra are
no-outcome), and the naive rate sinks 5.85% → 2.68%. The corrected rate (5.85%) is
invariant to the treatment — proof the data is identical; only the **weight** was wrong.

This is the **cause** of the whole #95/#97/#93 dilution family (those masked the
*consequence* in the metric). It is the concrete realization of the #101 refactor ADR 0010
flagged: "encode contract status in `new_approval` itself (approved-but-never-paid keep-in →
weight `0`)."

## Decisions

### The keep-in contract weight is observed hire, read by the core

The core `simulate()` consumes `current_hired_col` directly. For a keep-in that survives the
new policy's hard stages, its contract weight in `new_approval` is its **observed** hire
`0/1` from `current_hired_col` — not `1.0`. An approved-but-never-hired keep-in gets weight
`0`, so it contributes 0 to the numerator **and** 0 to the denominator. This makes the
denominator expressible as a plain `new_approval.sum()` with no `notna()` proxy — the #101
simplification. That denominator swap is **not** part of this change; the engine keeps its
`contracted_and_observed` proxy, which stays correct, and #101 removes it separately.

This **amends ADR 0010 #94**: the bypass principle stands (a modeled rate never re-gates the
keep-in), but "the book passes through at `1.0`" is replaced by "the book passes through at
its **observed** hire." The `1.0` was the defect. Same principle — *keep-in take-up is what
the data records* — now honored by reading the record instead of assuming it.

### Undeclared keep-in take-up is a hard error, not a silent 1.0

If the book has keep-ins (`current_approval_col == 1` present) and no declared observed
take-up (`current_hired_col` is None, and no `observed_col` rate stage), `simulate()`
**raises**. No silent 100%, no `assume_full_hire` opt-in. The silent default is the defect;
fail-fast removes it. Absent a hire record, "the data records nothing" now means **stop and
tell the caller**, not "take 1.0 as given."

> **Rollout (#103 → #106).** The raise is **staged**. #103 ships the weighting plus a
> `DeprecationWarning` on an undeclared book (legacy `1.0` retained), because ~62 call sites
> run keep-in books without `current_hired_col`. #106 migrates them and flips the warning to
> the `ValueError` this section mandates.

### Keep-in is always observed; modeled rates model swap-ins only

Firm invariant: a keep-in's approval is **historical** (`current_approval_col == 1`) and its
contract is **observed** (`current_hired_col`). A modeled `RateStage`
(`clip(base_rate * variable, 0, 1)`) never touches a keep-in — no counterfactual re-gate
mode. Hard stages (`CutoffStage`/`FilterStage`) **do** apply to keep-ins: that is the
swap-out decision. Order: a keep-in passes the new policy's hard stages (else swap-out); if
it survives, `current_hired_col` weights it.

### `current_hired_col` is the canonical source; `observed_col` is on notice

Take-up now has two spellings — the policy field `current_hired_col` (read by the core) and
the `RateStage(observed_col=...)` arg. The field is canonical: "who became a loan" is policy
input data, not a stage. `observed_col`'s keep-in role is **redundant** under this ADR and
is slated for removal, folded into the observed-rate generalization (#105). This ADR does
**not** delete `observed_col` — it stops depending on it for the keep-in contract.

## Migration (breaking change)

- **Books with keep-ins** must declare `current_hired_col` (or keep an `observed_col` rate
  stage during the deprecation window). Absent both → `ValueError`, loud.
- **Swap-in-only / no-keep-in studies** are unaffected — no `current_hired_col` required.
- **Counterfactuals** have no observed hire by definition; they were never keep-ins
  (keep-in ⇒ historically in the book). A counterfactual book is swap-in and rides the
  modeled rate — no escape hatch needed.
- **Serialized policies** already carry `current_hired_col` in `to_dict`/`from_dict`
  (`policy.py:218,249`), so no schema bump beyond ADR 0010's `schema_version` stamp. Old
  files that relied on the silent 1.0 now raise on load-then-run if they have keep-ins and
  no hire column — the intended loud failure.
- Regression lock parallel to `tests/test_scalar_rate_keepin_contract.py`: with the fix, a
  scalar rate over a book **with** `current_hired_col` weights keep-ins by the observed
  column (not 1.0), and **without** it raises.

## Consequences

- The #95/#97/#93 metric masks remain correct and complementary — they hold the number even
  if a bad row escapes; this ADR kills the bad row at the entrance. Belt and suspenders.
- ADR 0010's default-rate note (`new_approval.sum()` vs the `simulated_default.notna()`
  proxy) is now *unblocked*: contract status lives in `new_approval`, so the plain sum would
  be correct under external 0/1 marking too. #101 can drop the proxy — **not done here**;
  the engine keeps the working proxy denominator.
- CONTEXT.md's *Approval, take-up, contract* entry needs an edit: "absent a record, its
  contribution is **taken as given**" becomes "absent a record, `simulate()` **raises**."
- The observed-rate-with-eligibility-mask pattern (desk approval / "mesa", take-up) is the
  same structure and is generalized separately in #105 — this ADR keeps #103 to the bug.
