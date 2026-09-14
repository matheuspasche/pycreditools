# ADR 0034 — The contract axis leaves the policy: it completes #117 rather than contradicting it

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** the address of the stage that feeds the `contract` vector — policy or premise — and,
  as a consequence, what remains of the `Stage` Protocol and of `stages`. Excludes the premise's
  final shape, which #152 settled into a single `Premise` type (ADR 0033).
- **Tickets:** #155 (this ADR). Consumes #114, #116, #117, #119, #120, #121, #124, #129, #139,
  #145, #146, #152.
- **Spec:** the living engine spec, §2.1 (the spine and the *changes-when* table), §4.2
  (`CreditPolicy`), §4.4 (`Premise` — `take_up`).
- **Amends:** #117 (the missing member), #119 (`stages` = one verb), #121 (§1 and §3), #129 (the
  Protocol), #145 (form B's criterion), #152 (the family loses a verb), #124 (work order).
  **#120 is revoked, not amended.**
- **Amended by:** #152 decision 3 — ruling A below falls: one `Premise` type, and the bins serve
  the contract axis in both modes.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context — and why this is not a repetition

The question was raised by the owner on 2026-09-05 inside #139, investigated, and **ruled out of
scope**. That ruling answered the question that had been asked: the diagnosis was right — *"70%
of the approved contract"* is not a rule of the policy — but what made `.rate` *look* like a
premise **had already changed address** (#117 → #129); what was left was probability + declared
vector + position in the funnel, and moving it would cost the funnel position #121 used to kill
the hardcoded `current_approval_col`.

**The new argument, brought on 2026-09-06, is a different one:**

> *"Assuming a constant probability for what happens among the observed is also a ceteris
> paribus premise."*

That is about **invariance**: the declared take-up **does not move when the cutoff moves**, and
that constancy is a ceteris paribus premise with **no name anywhere on the surface** — colliding
with #152's rule that *no modelling default hides the existence of a mechanism*.

## The reframing, which is the session's finding

The card was opened as *"move or do not move a stage"*. **It is not that.** #117's resolution had
already declared the premise's shape with **three** members:

```
Study premise = "how does someone I did not observe behave"
    ├── contract axis   (assumed take-up)
    ├── outcome axis    (assumed PD)
    └── lens
```

The outcome axis got a type; the lens was dissolved on purpose; and the contract axis got the
**knobs** — `bins`, which #117 fixed as *"valid for every axis without marking"*, and
`calibrate_on` (#139) — and **did not get a home**.

> **The contract axis is the only member of the premise that does not live in the premise.** It
> has the *how* on one side and the *that it exists* on the other. No other member is like that.

This card closes that asymmetry: **it amends #117's resolution by #117's own resolution.**

## The criterion that decided — and it was already in the repo

`docs/research/architecture-critique.md` §1, the critique that originated the map, separates the
13 fields by **reason to change**: schema changes when *the base* changes; rules when *the
policy* changes; premises when *the question* changes.

Applied to take-up: moving the cutoff from 700 to 750 **does not change** the take-up
declaration. It changes when the hypothesis about customer behaviour changes — that is, when
**the question** changes. By the document's own line, that is a **study premise**.

## The argument that reopened the card, and what is left of it

**The ceteris paribus argument decided nothing, and is recorded as non-decisive.** The research
(§I.5) measured four ways of naming ceteris paribus in primary sources — DALEX (the name is the
type), `marginaleffects::datagrid(grid_type=)` (an enumerated, keyable argument), DoWhy (a key on
the estimand), sklearn PDP (prose) — and **none of the four names it by address**. Moving the
stage to another house names no invariance at all.

## A criterion explicitly overturned, recorded so nobody revives it

The owner brought *"the policy is trending towards deterministic"* into the session. **It was
defeated and is not the basis of this decision.** The desk is `.filter(expr, draw=True)` (#145)
and feeds `decision` (#121 §8), and #121 §6 makes it draw **on the analytical path too**: after
v0.6 there is drawing on **both sides** of the vector partition. *"Deterministic × probabilistic"*
would send the desk along too, and would **re-fuse the two axes #121 §1 separated.**

## The prototype — `contract = decision × take_up`, exact

`docs/research/prototype-155-contract-axis.py` — **on an ephemeral branch** (`fe2088e`, reachable
only from `origin/claude/aoba-b0w0o3`; §9.3 lists it under *"Pesquisas em branch efêmera, fora de
`release/v0.6`"*). 60k rows, 4 configurations.

1. **Today's funnel already factorises.** The take-up implicit in the engine's output matches
   **exactly** (`|Δ| = 0`) `_observed_probs` computed outside on the swap-ins, stays in `[0,1]` on
   **every** row, and on keep-ins **is** the observed `hired` column (`|Δ| = 0`). That last one is
   an identity, not an analogy.
2. **Removing the stage and recomposing from outside reproduces everything.** `|Δ decision| = 0`,
   `|Δ contract| = 0`, and **zero rows** change `reason` or `decision` — `reason`
   (`first_failed_col`, `simulation.py:489`) being the one place in the package where funnel order
   is not inert.
3. **The funnel position is worth zero, measured.** Take-up moved to the **front** of the list:
   `|Δ| = 0` on both vectors. The price that held this subject on 09-05 is no longer *"inert by
   reading"* — it is **zero by measurement**.
4. **Negative control — the one site where the stage is load-bearing beyond `contract`.** In
   standalone with a masked outcome, the engine **re-reads the last `RateStage` as a default
   probability** (`simulation.py:551-556`): mean approved PD **33.88% with** the stage against
   **9.42% without** — **24.5 p.p.**, the probability of *contracting* read as the probability of
   *defaulting*. That path was already dead by #117; the number is new, and with the axis out of
   the policy the confusion goes from dead-by-decision to **unexpressible**.
5. With two `RateStage` (the masterclass's v0.5 idiom) it still factorises.

**Two prototype defects, found and fixed before these numbers** — recorded because citing them
would have been false evidence: the original test 1 checked an identity true by construction, and
test 3b did not exercise the path it claimed to measure (the standalone base observes an outcome
on every row, so `unknown_mask` was empty).

## Ruling A (owner) — and it was amended within the day

`ColumnPremise` carries `take_up`, scalar, with a literal `1.0` in the signature. **The parallel
with the inflation does not hold**: inflation is unexpressible there because inflating a 0/1 is
meaningless arithmetic (`1 × 1.8` clips); take-up over an external outcome is not absurd at all —
they are **two independent axes** since #116, and delivering the outcome by column says nothing
about who contracts. Omitting the field would force `1.0` **by invisible construction**, the
modelling default hiding a mechanism's *existence* that #152 decision 1 forbids.

**Amended hours later by #152 decision 3:** the two premise types collapse into one `Premise`,
so the *"only `ScorePremise` has bins to estimate with"* asymmetry — which is what justified two
types — falls. What survives from ruling A is the part that mattered: **the literal `1.0` in the
signature**, which ADR 0016 later made permanent.

## Ruling B (owner) — a one-verb `CreditPolicy` is still a type, and the Protocol drops to one member

It does not become a `list[Filter]`: it carries the **labels** (key of `ranges=` in #118, grid
coordinate in #146), **composition validation without a base** (the first of #117's two moments),
and the **deploy unit** (#120).

And the lost Protocol member is not a loss — the 5 `isinstance(stage, RateStage)` sites
(`simulation.py:79`, `:229`, `:438`, `:475`, `:552`) **vanish with no replacement**, instead of
being swapped for the *"declared vector"* #121 §1 had decided on. **Less machinery than the
previous decision asked for.**

## Rejected

- **Leaving the axis in the policy** (the 2026-09-05 ruling). Its price — the funnel position —
  measured at **zero**. What is left of it is the *reason* rule of Decision above, which points
  the other way.
- **Naming ceteris paribus by address.** Four primary-source precedents, none of which does it.
- **"Deterministic policy versus probabilistic premise" as the criterion.** It re-fuses #121 §1's
  two axes and would move the desk too.

## Consequences

- **Release blocker.** The card moves the type partition, so by the rule written in its own body
  it enters the same door as B1, alongside #152 and #139.
- **The deploy unit's exclusion rule is revoked, not amended.** #139 had added to #120 *"a stage
  that feeds the `contract` vector does not enter the deploy unit"*. With no stage feeding
  `contract`, the rule has nothing to act on: the deploy unit is again **all `stages`**, and the
  boundary it protected is now structural — take-up lives in the study unit, and the deploy unit
  carries no premise. See ADR 0022.
- **What this card did NOT decide.** **The ceteris paribus invariance still has no name on the
  surface.** It stops being *hidden in a list of rules* and becomes *declared in an object called
  a premise* — which satisfies #152 decision 1 as to the mechanism's **existence** — but no field,
  argument or output number names the **invariance under cutoff movement**. The `marginaleffects`
  precedent (an enumerated, keyable regime) is **raised and not adopted**. If it becomes a
  requirement, it is a new card.
- **Also not decided:** how `take_up` accepts an AST node (today `RateStage.variable` accepts an
  `Expression`, `stages.py:290`, evaluated at `:340-350`). Spec writing under already-fixed rules,
  not a pending decision — but recorded as written by nobody. §9.1 item 3 later wrote it.
