# ADR 0030 — The PD-imputation baseline comes from the observed book, not from the policy under test

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** which population produces the swap-in's imputed PD — bin edges *and* rates — whether
  that is a premise knob or fixed, and what number reports the support hole. Excludes which
  *axis* calibrates (#137; the lens, §9.1 item 7) and measuring the support magnitude on a real
  book (execution validation).
- **Tickets:** #139 (this ADR). Consumes #106, #116, #117, #118, #121, #124, #132, #137, #140,
  #144, #146, #149, ADR 0008.
- **Spec:** the living engine spec, §4.4 (`calibrate_on`), §4.6 (the engine), §6 (the release
  gates — exactness proved per knob value).
- **Amended by:** #152 decision 7 (the knob is named `calibrate_on`, and its default value is
  spelled `"global"`), ADR 0016 (undeclared take-up is `1.0`, permanently).
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

#117 decided that reject inference is `baseline × inflation`, and that the stress **is** the
inflation — but it **never pinned down whose baseline**. That was never decided; it is a tacit
inheritance from the code.

Code facts:

- `calibration_base` (`policy.py:31`, default `"keep_in"`) chooses **only the bin edges**
  (`simulation.py:742-746`, via `ref_scores`).
- The population that **produces the rates** is always the same, with no knob:
  `cal_scores=keep_in_scores`, `cal_values=keep_in_defaults` (`simulation.py:751`).

**The keep-in population depends on the cutoff being swept** — a keep-in is whoever *both* the
incumbent and the challenger approve. That dependency is what produces the defect measured in
#140: the fast path calibrates once over a baseline without the swept cutoffs and then masks, so
every grid point receives PDs learned on another point's population — **0.58 p.p. (#140) to
1.00 p.p. (#149), always upward, maximal in the middle of the decision band.**

And the support hole, measured on `validation/shared_base.parquet` (n=60,000, seed=7):

```
support of legacy_score   keep-in: [790, 998]   swap-in: [609, 996]
swap-ins below the keep-in minimum: 92.4%
```

Refining the N-score matrix does not rescue it — cell hit stays at 6–8% from 3×3 to 10×10. The
limit is not cell size, it is the support hole, and its cause is **structural**: the incumbent
**selected** on that score.

**Declared limit of those measurements:** the canonical base is synthetic and its scores
correlate 0.90–0.95 by construction. **The direction of the finding is robust; the magnitude is
not** — which is why magnitude stopped being this card's question when the owner rewrote it on
2026-09-05.

**The posture the owner declared for deciding it.** Swapping the population was born as a
**performance escape hatch**. That is explicitly *not* how this card was to be decided: #124 had
already accepted paying the +18–20%, and the untested monotone/prefix mechanism could make that
cost nearly vanish — *"a card decided on it would have decided on sand"*. **Decide on merit, use
cost as a tie-break.**

## Decision 1 — rates and edges are one axis

One population, declared once, serves **both roles**.

`calibration_base` dies as it exists: it governs only the edges while the rates come from
`keep_in_scores`/`keep_in_defaults`, **hardcoded, with no parameter**. **A name that promises
calibration and delivers half of it** is the class #118 and #132 killed.

Recorded for the roadmap: **no v0.5 configuration produces the v0.6 behaviour.** Today's
`calibration_base="global"` is not the new default — it is a different thing.

## Decision 2 — two populations, not three, and the knob is the premise's

| value | population, for edges **and** rates |
|---|---|
| **default** | the incumbent's contracted book — everyone the incumbent approved, regardless of where they land in the new decision. **Invariant to the challenger.** |
| `keep_in` | those the new policy **also** approves |

**Why merit, not cost.** Today **the same person, with the same score, gets a different imputed
PD depending on where the challenger cuts**, because the ruler that measures them is made of the
population the challenger approved. **The ruler should be a property of the observed book, not
of the policy under test.** And keep-in throws away the swap-outs — contracted, observed rows at
the low end of the challenger's axis, which is exactly where the swap-ins live.

`keep_in` **survives as a possible value**, so the per-point recalibration machinery is
**mandatory either way**: under that value the fast path is only exact by recalibrating, and
#149's +18–20% is the price paid by whoever chooses it. Under the default, exactness is free.

**Where the knob lives:** a sibling field of `bins` **inside the premise**, by the same argument
with which #117 put the inflation there — when the outcome comes from outside there is no
baseline, so *"which population does the baseline come from"* is **unexpressible** rather than
writable-and-policed. Rung 1 of the ladder.

## Rejected

- **A third `"global"` population.** The reason is mechanical, not taste. The per-bin rate is
  `cal_values.groupby(cal_bins).mean()` (`_kernels/calibration.py:67`), and `mean()` **skips
  `NaN`**; `actual_default` is `NaN` where `hired == 0`. So *every* candidate population
  actually teaches **itself ∩ whoever has an outcome** — and "global ∩ observed" **is** the
  contracted book. `"global"` would produce the same rates as the default, differing only in the
  edges, which Decision 1 just fused, at the value the owner had already rejected on merit. The
  only world where it would differ is one where the outcome is observed **outside** the book —
  and that world has its own door (`outcome_from=<column>`). Detecting which world one is in
  would require **detection**, forbidden by #132.
- **"Survivors of the proposed policy's hard filters."** Raised by the owner, noting it would be
  invariant *within* a grid. Rejected for three reasons: (i) in v0.6 `.cutoff` died and "HF"
  stops being a type — what is left is *"a filter this grid does not sweep"*, so the population
  would depend on `ranges=`, and **the same `Study` with different grids would give the same
  person a different PD** — keep-in's disease one layer up, against #144's comparability axis;
  (ii) on merit it is **conditioning**, and modelled reject inference went out of scope in #117 —
  whoever wants to condition supplies the column; (iii) each value costs a proof of exactness at
  the release gate.
- **Making the population a sweep dimension.** By the lens precedent (#117 — *N lenses = N
  premises = N studies*) and by mechanics: two points with different calibration populations are
  **not comparable**, and comparability between points is #144's axis.
- **A warning instead of a number** for inversions and out-of-support — see Decision 5.

## Decision 3 — the grid honours the knob, and exactness is proved per value

The knob lives on the premise, which is a field of the `Study`, and `tradeoff` operates on a
`Study` — so **it arrives by construction, with no new argument on the verb.** The owner's
requirement (*"the grid has to receive this parameter"*) holds as **the grid has to honour it**;
a second place to set the same thing is what #146 kept out of the signature.

**Written obligation:** the grid's exactness is proved **per knob value** — **two tests at the
gate, not one.** At the default, exact without recalibrating; at `keep_in`, exact by
recalibrating, within #124's ≤1.25× ceiling.

## Decision 4 — one population governs both guesses, and the general rule is *draw the unobserved*

The engine guesses **two** things about a rejected applicant: whether they would default, and
whether they would have accepted the offer. The population choice governs **both** — one choice
for everything the premise estimates, by the precedent that `bins` is already shared by every
axis with no marking. What does **not** transport is the inflation, which stays exclusive to the
outcome for a semantic reason: aggravating conversion means nothing.

The owner's ruling, declared in this session and larger than the card:

> **You always draw what was not observed. What was observed stays as it is.**

| who | the engine does |
|---|---|
| approved by the incumbent **and** contracted | nothing — the observation stands |
| approved by the incumbent **and did not** contract | nothing — *"did not contract"* is an observation, not a hole |
| rejected by the incumbent | **draws the contract**; if contracted in the draw, **draws the outcome** |

**What actually changes:** today the engine combines a conversion rate with a default
probability; it moves to **drawing in sequence**. Price accepted: more variance, manageable
because the seed and named draws are already mandatory.

**Modelling correction, recorded:** *a quadrant is about decision, not about outcome.* The
keep-in/swap-out/swap-in/keep-out partition is decision × decision
(`simulation.py:509-511`). *"Having an outcome"* does **not** enter the population's definition
— it is a **precondition for teaching**, identical under both knob values. What changes versus
today's code is not the set: it is that the set becomes **written**, instead of emerging from
`groupby.mean()` skipping `NaN`.

**Asymmetry recorded, which does not change the decision:** the observability precondition
differs by axis. On the outcome it is `outcome` present — hence the support hole. On the
contract, take-up is observed for **every approved applicant**, so there is no hole there.

## Decision 5 — the support hole is two numbers, in the reading summary

**Inversions and the out-of-support fraction**, measured against the chosen population and moving
with it. Both already exist (`CalibrationDiagnostics`) and both were already routed by #132 to
**rung 3 — become a number**.

**Where:** in the **reading summary the user already reads after running** — the funnel render,
as the free function returning a table (#127) — not only as a field of the result object.

**Why not the warning the owner wanted to keep.** The use case was real (*"10 bands may be too
many; I test 6 and 7 until monotonicity holds"*), and the number serves it **better**: three runs
become one comparable table instead of three terminal messages. And the warning would lose
precisely the deliberate case — an intentional inversion fires on every run, the way out is
`filterwarnings`, and muted it disappears **also** when it mattered. That is exactly why #132
killed `CalibrationReliabilityWarning`, designed with its own category *"so a user can mute them
with a single filterwarnings"*.

Rung 3 is passive by nature, and #132 admits it. **Putting the numbers in the summary removes the
passivity without creating a warning and with nothing to silence.**

## Decision 6 — undeclared take-up is 1.0, and now on purpose

Without a declared conversion rate, every rejected applicant approved by the new policy
contracts. **This is not the silence #132 forbids** — it is the case #132 itself opened: *"a
literal default in the signature, which is not inference"*. Visible in `help()`, not discovered
in the data. Today's `DeprecationWarning` (#106) dies; the `1.0` becomes permanent and
documented. **Number identical to today's — it does not enter the whitelist.**

> **The spec must say out loud that the `1.0` is CONSERVATIVE, not neutral.** Keep-ins enter the
> book only if they contracted; swap-ins all enter. Since swap-ins are the worse population,
> their weight inflates and the default rate is pushed **upward**.

**Owner's ruling on aggravating conversion: it does not exist, and is not missed.** Approval is
measured pre-take-up (ADR 0008), so conversion does not move it; any target default rate is
reachable by moving the outcome's inflation alone. What would differ is contracted volume, which
is not a published metric.

## Consequences

- **Release blocker.** Swapping the population changes the number in **every simulation**, not
  only in the sweep — in a v0.6.1 it would be a **second hard break inside a patch**. So this
  card closes before v0.6.0 ships.
- **Parity whitelist (#124):** one **category (a)** entry, and the map's first that is a
  **modelling change**. Default rate **diverges**; approval **matches exactly** (pre-take-up, the
  calibration does not touch it); take-up **matches exactly** while conversion is undeclared. The
  range **must be measured, not estimated** — entered in the spec as **declared debt** and turned
  into a **gate**: v0.6.0 does not ship without the measured range, and the test that produces it
  carries the third DoD (reference outside the engine, measured at the border, negative
  control).
- **Fact correction, recorded.** The body of this card claimed the out-of-support swap-ins
  *"are not discretised into any bucket: they get the global PD."* **They do not.** The edges are
  pushed to ±infinity (`_kernels/calibration.py:20-21`), so whoever falls below the lowest
  keep-in **clips into the lowest bin** and gets its rate — the worst observed decile — not the
  global mean. The direction survives (they get **extrapolation, not measurement**, and the
  inflation does almost all the work over a constant); what falls is the implied magnitude —
  today's imputation is **less optimistic** than the text suggested. Second, smaller imprecision:
  the 50-keep-in floor is over the **total** (`simulation.py:731`), not per cell.
- **Naming, settled later.** #152 decision 7 named the knob `calibrate_on` and spelled its
  default value `"global"` — meaning *the whole observed book*, which is this ADR's default
  population, not the `"global"` this ADR refused. §9.6 records that as **not an amendment**:
  the word changed, the population did not. A name caveat that is implementation debt: the
  **rates** coincide between the old and new reading, but the **edges do not**, and the parity
  proof matches by name.
- **Collateral, and its later revocation.** This card's §10 added to #120 the rule *"a stage that
  feeds the `contract` vector does not enter the deploy unit"*. #155 moved the contract axis into
  the premise, so that rule lost its object and was **revoked** — see ADR 0022.
