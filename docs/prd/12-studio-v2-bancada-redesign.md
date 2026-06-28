# PRD 12 — Studio v2: Central Bancada Redesign

> Synthesis of the `/grill-with-docs` session (2026-06-28). Load-bearing decisions
> are in `docs/adr/0001`–`0006`; the full design narrative is in
> `docs/redesign/studio-redesign.md`. **Hard rule: the package engine is not
> touched — only the `gui/` skin and the framework-agnostic `studio/` core.**

## Problem Statement

The owner has used the studio after the first build-out and finds it "good for a
mock" but conceptually wrong. Today it is a **linear pipeline of 10 independent
pages**: each page is a standalone analysis that reads shared state but never feeds
back into it. That does not match how a credit policy is actually designed:

- Designing a policy is a **coupled** activity — a weaker score means cutting more on
  hard filters; a trusted score means loosening filters and cutting more on score.
  Choosing scores and cutoffs should update the funnel and the risk-tier clustering
  (you cluster whoever survives the filters). Today nothing propagates.
- A new policy is almost always built **from a pre-existing one**, so the owner needs
  to compare **two policies across everything that matters**: approval rate, default
  rate, swap-in/swap-out/keep-in volumes and their default, the risk-tier
  distribution of those groups, their behaviour over time, and the risk exposure of
  the decision — then **worsen PD (aggravation)** and re-check "can I still approve?".
- Real engagements differ in **how much of the vigente policy the data exposes**
  (full rules, only the approval flag, or nothing at all). The studio must adapt.
- New scores usually enter **matriciated** with the vigente score (repechage) before
  any replacement, so the owner must judge **complementarity**, not isolated KS.

Concretely the owner raised ~20 specific complaints (see `studio-redesign.md`
per-critique map): pages that "say nothing" (Simulation, Trade-off), an Optimization
page that does not run, a Crash Test page that is unnecessary, an unexplained
Screening page, confusing population/score terminology, mis-labelled tables, no way
to see the distribution of a column being filtered, endless scrolling when there are
many filter rules, and more.

## Solution

Reorient the studio around a central **Bancada** (live policy-design workbench) plus
two deep-dives, collapsing the 10 pages into five:

```
Ingestion → Score Evaluation → Bancada (the heart) → Risk Grouping → Deploy
```

- The **Bancada** absorbs Policy Studio + Simulation + Trade-off + Crash Test into a
  single live loop: assemble the policy and instantly see the funnel and the
  **comparison-vs-base**; "trade-off" becomes dragging a cutoff; "crash test" becomes
  pulling the aggravation until it breaks even. It **opens with suggested scenarios**
  the owner tweaks (suggestion-first), and every knob propagates everywhere.
- The studio **auto-detects the comparison tier** from the available columns and
  adapts (full rule reconstruction / swap-only / standalone market inference).
- **Score Evaluation** ranks KS, measures **complementarity** vs the vigente/in-use
  score, and gates the 2–3 "scores em jogo" that flow downstream.
- **Risk Grouping** becomes an **open, editable matrix** (select cells, group by hand
  or via algorithm) that feeds the Bancada cutoffs — this is the matriciation surface.
- **Deploy** exports the chosen policy and batch-scores a file, reached through a
  single unified save concept.

## User Stories

1. As a policy owner, I want the studio organised as Ingestion → Score Evaluation →
   Bancada → Risk Grouping → Deploy, so that the flow matches how I actually design a
   policy instead of a grab-bag of dashboards.
2. As a policy owner, I want one Bancada screen where I assemble scores, cutoffs,
   filters and take-up rates, so that I design a whole policy in one place.
3. As a policy owner, I want the funnel and approval/default to update live as I
   change any knob, so that I can feel the impact immediately.
4. As a policy owner, I want changing a cutoff to also re-cluster the surviving
   population, so that the risk grouping reflects who actually remains after filters.
5. As a policy owner, I want to compare a candidate policy against a base across
   approval rate and default rate, so that I can judge whether the change is worth it.
6. As a policy owner, I want swap-in / swap-out / keep-in / keep-out volumes and
   their default rates, so that I understand who I gain and lose by switching.
7. As a policy owner, I want the risk-tier distribution of those swap groups, so that
   I can see whether I am swapping in higher-risk clients.
8. As a policy owner, I want to see how the candidate vs base behaves over time
   (vintages), so that I can trust the decision is stable.
9. As a policy owner, I want a measure of the risk exposure of the decision, so that
   I know how much risk I am taking on.
10. As a policy owner, I want an aggravation control that worsens PD, so that I can
    play the "even so, can I still approve?" game.
11. As a policy owner, I want the aggravation to show the break-even point vs the
    base, so that I know how much stress the candidate policy survives.
12. As a policy owner, I want the Bancada to open with 2–3 suggested scenarios
    (e.g. conservative / neutral / aggressive or by target default/approval), so that
    I start from a sensible proposal instead of a blank screen.
13. As a policy owner, I want to freely adjust any suggested scenario, so that the
    studio is opinionated but never rigid.
14. As a policy owner, I want to drag a cutoff and watch the trade-off curve, so that
    I find a reasonable cutoff without a separate trade-off page.
15. As a policy owner, I want the studio to detect from my data whether I have the
    vigente score + decline reasons, only the approval flag, or no base at all, so
    that it configures itself correctly.
16. As a policy owner, I want a clear badge telling me which comparison mode I am in
    and why, so that I understand what the studio can and cannot compute.
17. As a policy owner, when I only have the approval flag, I want swap analysis to
    still work, so that I can compare even without the vigente score.
18. As a policy owner, when I have no base at all, I want to build a policy from
    scratch / market inference using an estimated PD, so that I can still design.
19. As a policy owner, I want the estimated-PD role to appear only when there is no
    comparison base, so that I am not asked for inputs I do not need.
20. As a policy owner, I want most column roles (segment, vigente score, etc.) to be
    optional, so that I am not blocked when my data lacks them.
21. As a policy owner, I want the score I am evaluating to drive both the cutoff axis
    and the PD calibration together, so that I never compute swap-in for one score
    using another score's PDs.
22. As a policy owner, I want to optionally mark the vigente score as a reference, so
    that complementarity is measured against what I run today.
23. As a policy owner, I want a KS ranking of all candidate scores, so that I can see
    which scores have power.
24. As a policy owner, I want to mark 2–3 "scores em jogo", so that heavy compute and
    suggestions only run on the scores that matter.
25. As a policy owner, I want complementarity metrics (correlation, isolated vs
    combined KS, marginal lift) between a candidate and the vigente/in-use score, so
    that I judge whether two scores add information or merely repeat each other.
26. As a policy owner, I want a verdict hint (repechage / matriciate / replace), so
    that I have a recommended next move I can override.
27. As a policy owner, I want to see the score×score grid open as quantiles (e.g.
    5×5), not only clustered, so that I can inspect the raw matrix.
28. As a policy owner, I want to select cells of that matrix and group them by hand
    (Excel-like), so that I can encode business judgement, not only the algorithm.
29. As a policy owner, I want to also run the grouping algorithm on the matrix, so
    that I can start from an automatic grouping and refine it.
30. As a policy owner, I want the resulting matrix/recipe to feed the Bancada
    cutoffs, so that my matriciated decision drives the policy.
31. As a policy owner, I want to optionally segment the policy by a business column
    (channel, store, entry policy), so that I can set different cutoffs per segment.
32. As a policy owner, I want the funnel and comparison to show the total and break
    out by segment, so that I see both the aggregate and per-segment impact.
33. As a policy owner, I want a live mini-histogram of the column I am filtering with
    the cutoff line and "% (and volume) passing / dropped", so that I know whether a
    given threshold cuts too much or too little.
34. As a policy owner, I want rules shown as compact, collapsible one-line rows, so
    that many filters do not force endless scrolling.
35. As a policy owner, I want a take-up/contracting rate stage named and explained
    clearly ("of the approved, % who actually contract"), so that I understand what
    it does.
36. As a policy owner, I want the take-up rate suggested from the approved→contracted
    columns but never locked, so that I can start from data and still adjust.
37. As a policy owner, I want take-up rates that can vary by score (angled), so that
    I can model that worse scores are more eager to take the offer.
38. As a policy owner, I want to chain multiple rate stages (e.g. effectivation then
    anti-fraud), so that I do not over-size the swap-in.
39. As a policy owner, I want the population selector split into "Período" (Todos /
    Dev / OOT) and "Quem" (Todos / Aprovados / Contratados), so that the temporal and
    funnel cuts are not mixed in one list.
40. As a policy owner, I want plain-language copy instead of "N efetivo (com
    actual_default observado)", so that the effective sample is understandable.
41. As a policy owner, I want contextual hints on each column role explaining the
    expected format and why, so that I prepare my data correctly.
42. As a policy owner, I want a friendly warning when a column looks mis-formatted
    (e.g. text where 0/1 is expected), so that I am not surprised by silent failures.
43. As a policy owner, I want a single "save" that persists my whole working session
    and a separate explicit "export production policy" action, so that I never deploy
    a draft by accident.
44. As a policy owner, I want the KS-by-bucket table correctly labelled (not
    "undefined"), so that I can read it.
45. As a policy owner, I want the dev-only "Carregar filtros do v14" shortcut
    removed, so that the UI is not cluttered with developer affordances.
46. As a policy owner, I do not want a standalone Optimization page; I want a
    "suggest cutoff/scenario" capability inside the Bancada, so that suggestions live
    where I calibrate.
47. As a policy owner, I do not want standalone Simulation, Trade-off or Crash Test
    pages, so that I am not bounced between dashboards that "say nothing".
48. As a policy owner, I do not want the Screening page for now, so that the studio is
    not cluttered with a step I do not understand.

## Implementation Decisions

- **Information architecture.** Five entries: Ingestion, Score Evaluation, Bancada,
  Risk Grouping, Deploy (ADR 0001). Simulation, Trade-off, Crash Test fold into the
  Bancada; Optimization becomes its suggestion engine; Screening is cut.
- **Layer discipline (unchanged).** All new logic lands in the framework-agnostic
  `studio/` core (detection, analyses, policy assembly, charts, projects). The
  `gui/` skin stays the only place `streamlit` is imported. No change to the package
  engine. The existing core/skin boundary test stays green.
- **Live propagation.** The Bancada drives a single live `CreditPolicy` held in
  session state; the funnel, comparison, and survivor clustering all derive from it,
  so "every knob impacts every readout" needs no engine change.
- **Comparison tiers (ADR 0002).** Detection classifies the base into Tier A (full
  rule reconstruction), Tier B (flag-only swap), or Tier C (standalone / market
  inference). The Bancada lights up panels accordingly and shows a mode badge. The
  estimated-PD role is surfaced only in Tier C.
- **Contextual score-in-use (ADR 0003).** Remove the fixed "primary score" role. The
  score under evaluation binds the cutoff axis and the PD calibration column together
  so they cannot diverge. Add an optional "vigente score" reference role.
- **Matriciation as first-class (ADR 0004).** Score Evaluation gains a
  complementarity mode (correlation, combined KS, marginal lift, verdict hint). Risk
  Grouping becomes an open editable matrix with manual cell grouping plus the
  algorithm; the resulting recipe feeds the Bancada cutoffs. Built on the existing
  pairwise-grouping orchestration.
- **Suggestion-first + short-list (ADR 0005).** Score Evaluation gates 2–3 "scores
  em jogo"; the Bancada opens with suggested scenarios produced by the (now embedded)
  optimization engine, run only on the short-list to bound compute.
- **Light segmentation (ADR 0006).** Optional "segment by column" → cutoffs per
  segment, with aggregate + per-segment funnel/comparison. Policy stays a single
  object with per-segment cutoff overrides (not a set of policies). Full per-segment
  policies are deferred.
- **Take-up rates.** Rename/clarify; suggest from approved→contracted but keep
  editable; support angled (by-score) multipliers via the existing rate-stage
  variable; support multiple chained rate stages.
- **Pointwise UI.** Live filter histogram with pass/drop readout; compact/collapsible
  rule rows; two-axis population selector with human copy; per-role format hints +
  friendly validation; unified save with explicit production export; fix the
  KS-by-bucket table label; remove the v14 quick-fill button.

## Testing Decisions

- **What makes a good test:** assert external behaviour (numbers in → numbers out),
  not implementation details. A test should survive a UI refactor.
- **Primary seam (one, highest, existing):** the `studio/` core. New logic — tier
  detection, complementarity metrics, the suggestion engine, per-segment cutoffs,
  matrix grouping orchestration, and the cutoff+PD binding — is implemented as pure
  functions/dataclasses and tested under `tests/studio/parity/`, mirroring the
  existing parity tests (data in → plain DataFrame/dict out, validated against the
  engine and against `run_v14_benchmark.py` where applicable).
- **Secondary seam (thin):** Streamlit `AppTest` under `tests/studio/apptest/`, used
  only to verify Bancada wiring (a knob change propagates to the funnel/comparison;
  the mode badge reflects the detected tier; "scores em jogo" gates downstream). Keep
  these minimal — they are slower and UI-coupled.
- **Prior art:** the current `tests/studio/parity/*` and `tests/studio/apptest/*`
  already establish both seams; new tests follow their shape. The core-has-no-
  streamlit-import boundary test must stay green.
- **Parity oracle:** `run_v14_benchmark.py` remains the regression check for funnel
  volumes, legacy approval/bad rate, and the neutral scenario.

## Out of Scope

- Any change to the package engine (`pycreditools/*` outside `studio/`/`gui/`).
- Full per-segment policies (independent filters/rates/aggravation and per-segment
  comparison) — only cutoffs-per-segment ship now.
- Value mapping of mis-coded columns (e.g. "pago"/"não pago" → 0/1) — only hints +
  validation now; no auto-conversion, no agent inference.
- A re-positioned Screening ("discover a business segment that still separates
  risk") — recorded as future work.
- Manual override of the auto-detected comparison tier.
- Multi-user / auth / cloud-scale concerns (still single-user, local).

## Further Notes

- **Delivery model:** this PRD's work items are to be **dockerized as issues and run
  with the ralph loop** (existing `docker/` + `.ralph/` infrastructure). Keep the
  docker setup intact; do not delete it.
- **Traceability:** every owner critique (1.1–2.8) maps to a resolution in
  `docs/redesign/studio-redesign.md` (§"Per-critique resolution map").
- **Sequencing suggestion (not binding):** Ingestion tier detection + roles →
  Bancada core loop (funnel + comparison + aggravation) → suggestion engine + scores
  em jogo → complementarity + editable matrix → light segmentation → pointwise UI
  polish → page removals.
