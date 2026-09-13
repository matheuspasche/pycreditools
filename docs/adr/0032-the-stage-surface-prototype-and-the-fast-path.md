# ADR 0032 — The stage surface, prototyped: `.filter(expr, draw=True)`, and the fast path survives the re-keying

- **Status:** Accepted
- **Date:** 2026-09-13
- **Scope:** validating the surface #129 decided — the writing, the fast path's re-keying on the
  AST, the desk verb, the two classes of hard error, and the funnel's display. Excludes the
  content #129 fixed (ADR 0029) and where the `ranges=` error is raised (#146).
- **Tickets:** #145 (this ADR). Consumes #116, #118, #120, #121, #127, #129, #133, #140, #143,
  #146.
- **Spec:** the living engine spec, §4.2 (`.filter(expr, draw=True)`, the label and the
  `LabelRequired` message), §4.3 (the AST — the two renders), §4.6 (fast-path eligibility read
  on the AST).
- **Amends:** #129 — the third class of mandatory label (the band), the desk verb #121 §2 had
  delegated, and the display rule.
- **Amended by:** #155 — the **justification** of form B, not form B.
- **Measured against:** `release/v0.6` (`24a125a`).

## Context

#129 decided the **content** of the stage and left validation to a prototyping card, by the
owner's ruling: the map's notes say a large, expensive-to-reverse fork gets a `/prototype`
before an ADR is written. Two things had to be **shown, not described**:

1. **The writing.** The masterclass's real hard-filter policies, in both surfaces, side by side,
   running the real engine underneath — because the defect the owner pointed at three times in
   this decision was **of writing, not of architecture**.
2. **The fast path.** Whether `ranges=` over a parameterised `.filter` keeps #143's
   0.73 ms/point or falls to the ~82 ms/point of re-simulation. **The only point of #129
   supported by reading rather than measurement, and the most expensive to reverse.**

Prototype: `PROTOTYPE_stage_surface.py`, branch `claude/hello-0ucdo9`, commits `f24560e` →
`8044ff0` → `e8fb690` → `b967de0`. Disposable, off `main`.

## Decision 1 — the fast path survives the re-keying (the card's point 2)

Measured: re-keying on the AST matches today's fast path **bit for bit** (`|Δ| = 0.0e+00` on
approval and on default, at four proof points), at **1.48 ms/point against 1.44** for
`isinstance(CutoffStage)` — and against ~66 ms/point for re-simulation. Same on a two-dial grid
(the `optimize_cutoffs` case).

**The structural property reads in 6 lines over `BinaryExpr`; it is the same walk `get_columns()`
already does, not parsing.**

The fast path's default-rate bug (#140) reappears in the measurement and does not change the
verdict: #129 inherits the fast path **as it is**, neither fixing nor worsening it. It only ties
how the contrast is read — ~45× compares a correct path against an incorrect one.

## Decision 2 — the writing holds (the card's point 1)

Both funnels give an identical number (approval 33.370000%, contracted 3260.251684). The
hard-filter block shrinks **from 15 lines to 8**.

Census over the notebook's 9 real stages: **only 2 require a label (22%)** — the regional gate
(2 columns, once #120's callable becomes `col("score_5") >= col("region_cutoff")` through the
dplyr escape hatch) and a scalar `.rate` (0 columns, the `sweep.py:173` case). So the mandatory
label stays the exception, which was the open question.

## Decision 3 — the desk verb: `.filter(expr, draw=True)`

#121 §2 closed the semantics of the probabilistic decision stage and **delegated the verb to
#129**; #129 closed without naming it, and the formulation it left (`.filter` takes a boolean,
`.rate` takes a numeric) re-glued the two axes #121 §1 had ordered pulled apart.

**Decided: form B.** The verb names the **vector**; the argument names the **mechanism**.
`draw=` and not `prob=`: the flag says *what it does* — it draws — rather than only saying the
argument is a probability.

**Price accepted, declared:** the flag re-types the positional argument (a boolean node without
it, a numeric node in [0,1] with it). The **output** does not change type — `.filter` delivers a
hard 0/1 mask, drawn or not, guaranteed by #121 §6 — so the *"predictable output type"* ruler
stands. The owner recorded the form as *"a bit ugly, but that's the mechanics"*.

**Rejected, with reasons:**

- **`.review(...)`** — puts back the third verb #129 had just removed, against the owner's input
  in #121 §2, and the name does not generalise (desk, antifraud and formalisation are all
  probabilistic decisions).
- **`.rate(expr, to="decision")`** — reopens the `.rate` collapse to one argument, which is
  #129's headline, and **inverts the axes**: the verb would name the mechanism and the argument
  the vector.
- **`.filter(chance(expr))`** — a new candidate that arose while writing the others. It falls by
  consequence of the ruling below.

**New owner ruling, which no closed card had taken: `.calibrated()` dies in v0.6.** #129 removed
`calibrate`/`calibrate_by` from the stage but did not say whether the node survived. With it
dead, what remains is `ColumnExpr`, `BinaryExpr` and `UnaryExpr` — **an entirely pure AST** — and
`chance` would be the only instruction-node, creating in v0.6 the category v0.6 has just removed.

*Caveat recorded in favour of the rejected form, for whoever reopens it:* `chance` is not impure
in the same way. `.calibrated()` needed the **policy** to evaluate — it is the origin of
`policy: Any` and the import cycle; `chance` needs only the seed and the row position, which the
`ctx` already carries (#127). It does not reintroduce the coupling, only the category.

The rest of the desk runs with nothing new, and part D of the prototype exercises it: published
approval **including** the desk (#121 §8 — 42.56% without, 38.52% with; it rejects 4.04% of the
base), coverage as a number (#121 §5 — 79.7% estimated), both hard bind errors, and estimation in
the same `bins` the take-up uses (#121 §7, zero new premise fields). The observed column's name
is the node itself, `col("desk_outcome")`, which satisfies #121 §4's role≠reference **without**
bringing a named argument back.

## Decision 4 — a band colliding on the label keeps the hard error

```python
Policy().filter(col("score_5") >= 600).filter(col("score_5") <= 900)
# LabelRequired: the band is two rules; name them (label="piso" / label="teto")
```

This had been reported as a defect of #129 — the error landing on whoever wrote the most obvious
policy. **The measurement flipped the argument:**

| how the band is written | sweep the floor | sweep the ceiling | both |
|---|---|---|---|
| two named stages | addressable | addressable | addressable |
| one stage, `>= 600 & <= 900` | — | — | **refused** |

**The natural way out for someone hitting the error is to fuse the band into one stage — and that
is precisely the writing that loses both dials.** Naming the two sides costs two words and
returns two independent levers. The hard error is not a stone in the road: **it pushes towards
the writing that is also the sweepable one.** No amendment to #129 (which already enumerated
"collision with a taken label"); only the message changes.

*Considered and rejected:* a structural default including the operator (`score_5>=`,
`score_5<=`). It dissolves the collision and respects everything #129 required of the default,
but pays an ugly label and only postpones the case.

## Decision 5 — a non-addressable stage is a hard error at `ranges=`, not at the bind

**Correction of an error in this card's earlier comments:** a `.filter` with two numeric
comparisons was reported as *"falling back to re-simulation, 45× more expensive"*. That is wrong,
and the defect was the prototype's own — `with_literal` replaced **every** literal with the same
value:

```
rule:                      (score_5 >= 700) & (score_4 >= 500)
with_literal("dois", 650):  (score_5 >= 650) & (score_4 >= 650)
```

It is not slowness, it is **ambiguity**: `ranges={"dois": [...]}` has no right answer. The number
that came out meant nothing.

**Decided: a hard error at `ranges=`.** Writing the composite stage stays **legal** — a composite
rule nobody sweeps is legitimate writing, and forbidding it at the bind would pay dearly for a
problem that exists only in the sweep. **The error is born where the ambiguity is born.**

The frontier, all of it exercised in the prototype's B.3:

- one numeric literal in a hard mask → **addressable**
- one literal plus a fixed set in the same rule → **addressable** (the fixed part stays in the
  baseline)
- a comparison against another column (the regional gate) → hard error
- two numeric comparisons in the same rule → hard error, with the message telling you to separate
  them

*Rejected:* a hard error at the bind (kills legitimate writing), and `ranges=` addressing the
node (`"dois.score_5"`) — which works, but invents a sub-address and contradicts #118's rule that
`ranges=` is keyed by label; and a sweepable composite stage appears **zero times** in the real
policies.

**Routing:** the rule is this card's; **where the error is raised is #146's.**

## Decision 6 — the funnel shows two columns, with a reading render

#129 allowed two readings of *"the label plus the render"*. **Decided: the label accompanies the
render, it does not replace it** — but in **two columns**, not concatenated, and with a
**reading render**:

```
Stage                  Rule                          Passed
-----------------------------------------------------------
                       cpf_valido == True            19,965
                       vl_negativacao <= 1500        18,097
Incumbent score gate   legacy_score >= 600            7,255
                       score_5 >= 560                 6,674
```

The ugliness was never #129's rule — it was the `—` concatenation and Python's `__repr__`.
Measured: Stage column 20, Rule column 22, against 21 for today's hand-written name. **The Stage
column is mostly blank, and the blank is the information**: #129's ruler in plain sight.

The alternative reading (label replaces the render) was rejected because it **loses the threshold
exactly on the row where the label was written *because the rule did not explain itself*** —
"Incumbent score gate" does not say 600, and today's name at least did.

**New obligation the spec carries:** there are now **two renders of the same node**. The rule that
prevents divergence — `__repr__` is Python's render, round-trippable; `pretty()` is presentation
only and **is never parsed back**.

## Consequences, and what #155 moved

- **The justification of form B changes; form B does not.** It was chosen as *"the only candidate
  that separates the two axes **while keeping two verbs**"*, and that criterion is what rejected
  `.review` and `.rate(to=…)`. With take-up out of the policy **there are no two verbs to keep**,
  so the comparison among the four forms can no longer be cited as the reason. Form B now stands
  on a simpler and stronger argument:
  > **`.filter` is the one verb of the `decision` vector; `draw=` names the mechanism.** With one
  > verb in the policy, the flag is the **only** way to express #121 §1's second axis without
  > inventing a sibling verb feeding the same vector.
- **The asymmetry #139 routed to #152** (*"`.filter` has `draw=`, `.take_up` cannot"*) stops being
  an asymmetry **between verbs** — there are no two sibling verbs left. It becomes a difference
  between the policy (which draws, with a flag) and the premise (whose take-up is always an
  estimate over the unobserved, so there is nothing to declare).
- **The scalar `.rate` case leaves the policy with the axis.** It was *"the case where structure
  does not name"*, and therefore required a mandatory label; the premise's `take_up` field needs
  no label, because it is neither a grid coordinate nor a `ranges=` key.
- **Restriction inherited from #133:** the swap-one-field move is exactly this card's point 2 —
  #133 confirmed by test that the sweep **partially rebuilds the stage and nobody notices**
  (`sweep.py:169` builds `RateStage` with 4 of its 6 constructor fields). The re-keying decided
  here is what makes the address survive derivation.
