# Pycreditools Studio — Redesign Spec (v2)

> Consolidated outcome of the `/grill-with-docs` session on 2026-06-28.
> The load-bearing decisions are recorded as ADRs (`docs/adr/0001`–`0006`); this
> document is the actionable synthesis and the per-critique map. **Hard rule: the
> package engine is not touched — only the `gui/` skin and `studio/` orchestration.**

## Golden rule

Everything below changes the **skin** (`pycreditools/gui/`) and at most the
framework-agnostic **core** (`pycreditools/studio/`). The risk engine
(`pycreditools/*` outside `studio/`/`gui/`) is **off-limits**. The current
architecture already makes this possible: a single live `CreditPolicy` in
`StudioState` means "every knob impacts every readout" needs no engine change.

## Concept (the why)

The studio is a workbench for **designing a policy on an uploaded base**, where
**everything impacts everything**: a weaker score → cut more on hard filters; a
trusted score → loosen filters and cut more on score. Selecting score(s) + cutoffs
must update the funnel and the clustering (you cluster whoever survives the filters).

In real life a **new policy is built from a pre-existing one**, so the user must
compare **two policies across everything that matters**: approval rate, default
rate; if switching, the volume + default of **swap-ins / swap-outs / keep-ins**;
the risk-tier distribution of those groups; their behaviour over **time**; the
**risk exposure** of the decision. Then comes the **aggravation game**: worsen PD
further and check *"even so, can I still approve this new policy?"*.

Two more real-world needs: **segmented policy** by business parameter (channel /
store / entry), and **score reuse / matriciation** — a new score usually enters
**matriciated** with the vigente one (repechage) before any replacement, for risk
and contractual reasons, so we must judge **complementarity**, not isolated KS.

Above all: **it must be extremely intuitive.** Opinionated (suggestion-first) but
never rigid.

## Target information architecture

```
Ingestion → Score Evaluation → Bancada (the heart) → Risk Grouping → Deploy
```

Hybrid (ADR 0001): a central **Bancada** plus two **deep-dives** (Score Evaluation,
Risk Grouping) that read from / write back to the live policy.

### 1. Ingestion
- Upload / generate; configure column **roles** (most are optional, see tiers).
- **Auto-detect the comparison tier** (ADR 0002) and show it with a plain-language
  badge + why.
- **Format hints + friendly validation** (critique 1.5): a `(?)` per role explains
  the expected format and *why* (e.g. "default: 0/1; NaN for non-contracted; used to
  compute real default rate"). If a column looks wrong (text where 0/1 is expected),
  warn clearly — **no auto-conversion, no agent inference** in this round.
- Fuse **Project + Deploy** persistence (critique 1.1, ADR-note): a single "save"
  holds the whole working session (base + roles + policies + ratings), with an
  **explicit, separate "export production policy" action** so a draft is never
  deployed by accident.

### 2. Score Evaluation (deep-dive)
- KS ranking of candidates (fix critique 1.6: the "undefined" table is a label bug —
  it is the per-bucket KS table; name it; the "KS comparison across scores" table is
  the ranking and stays).
- **Complementarity mode** vs the vigente/in-use score (ADR 0004): correlation,
  isolated KS vs combined KS, marginal lift, verdict hint (repechage / matriciate /
  replace).
- **"Scores em jogo" gate** (ADR 0005): mark 2-3 scores that flow downstream; the
  rest stay out of heavy compute.

### 3. Bancada (the heart)
Absorbs Policy Studio + Simulation + Trade-off + Crash Test (ADR 0001). One live
screen:
- **Assemble** the policy: scores + cutoffs + filters + take-up rates.
- **Score-in-use is contextual** (ADR 0003): the score being cut binds the cutoff
  axis **and** `calibration_score_col` together — never diverge.
- **Live funnel + comparison-vs-base**: approval, default, swap in/out/keep
  (volume + default), risk-tier distribution, behaviour over time, risk exposure.
- **Trade-off = drag the cutoff** and watch the curve (no separate page, fixes 2.3).
- **Aggravation game = pull the stress** until the new policy breaks even vs the
  base — "can I still approve?" (absorbs Crash Test, fixes 2.7).
- **Opens with 2-3 suggested scenarios** (ADR 0005); optimization is the engine
  behind them, run only on the scores em jogo (fixes 2.4). Manual calibration free.
- **Live filter histogram** (critique 1.9): editing a filter/cutoff shows a small
  histogram of the column with the cutoff line + "% (and volume) passing / dropped",
  updating as you move it — answers "am I cutting too much or too little?".
- **Compact / collapsible rule rows** (critique 1.9.2): each rule is a one-line
  summary ("Negativação ≤ 300 · cuts 12%"), expandable to edit; dense, reorderable.
- **Take-up rates** (critique 2.1): rename to "Taxa de aceite/contratação" with
  clear copy ("of the approved, % who actually contract"); **suggest** the rate from
  the approved→contracted columns but **never lock it**; support **angled** rates
  (by score, via the existing `RateStage` `variable`); support **multiple sequential
  rate stages** (effectivation, anti-fraud 95%, …) — each shrinks the funnel and
  matters to avoid **over-sizing the swap-in**.
- **Light segmentation** (critique 1.2, ADR 0006): optional "segment by [column]"
  → cutoffs per segment; funnel/comparison aggregate total + break out by segment.

### 4. Risk Grouping (deep-dive)
- **Editable open matrix** (critique 2.5, ADR 0004): show the quantile grid (e.g.
  5×5) **open**, not only clustered; select cells and **group by hand** (Excel-like)
  or run the algorithm. Clusters whoever survives the Bancada filters.
- The resulting recipe **feeds the Bancada cutoffs**.

### 5. Deploy
- Export the chosen policy as production JSON + batch-score a new file (critique 2.8,
  unchanged), reached via the unified save concept (critique 1.1).

## Population selector (critiques 1.7 + 2.0)

Split the overloaded single list into **two axes** with human copy:
- **Período** (temporal): Tudo / Dev / OOT.
- **Quem** (funnel): Todos / Aprovados / Contratados.
Replace "N efetivo (com actual_default observado)" with e.g. "X clientes com
inadimplência conhecida (base do cálculo)".

## Comparison tiers (ADR 0002)

| Tier | Available | Behaviour |
|---|---|---|
| A | vigente score + decline reasons + flag | reconstruct vigente rules; full swap |
| B | approval flag only | swap works; no rule reconstruction |
| C | none | standalone / market inference; no swap; PD from `estimated_default_col` |

`estimated_default_col` (PD estimada) is surfaced **only in Tier C** (fixes 1.3).

## Per-critique resolution map

| # | Critique | Resolution |
|---|---|---|
| 1.1 | Save-project vs Deploy | **Fuse** into one save; explicit production-export step |
| 1.2 | Segment must be optional | Optional toggle; light per-segment cutoffs (ADR 0006) |
| 1.3 | Why PD estimada if always from model | It is the **Tier C** PD source; shown only then (ADR 0002) |
| 1.4 | "Score principal" vs vigente | Contextual score-in-use; bind cutoff+PD; optional `vigente_score` (ADR 0003) |
| 1.5 | Data not in expected format | Contextual hints + friendly validation; no auto-convert |
| 1.6 | "undefined" table / KS comparison | Label bug fix; name the per-bucket KS table |
| 1.7 | "População" + "N efetivo" copy | Two axes (Período / Quem) + human copy |
| 1.8 | "Carregar filtros do v14" | **Remove** from UI (dev shortcut) |
| 1.9 | Distribution of filter column | Live mini-histogram with cutoff line + pass/drop % |
| 1.9.2 | Too many filters → endless scroll | Compact / collapsible rule rows |
| 2.0 | Dev/OOT/Approved/Hired mixed | Two axes (temporal vs funnel) |
| 2.1 | "Taxa de bem" unexplained | Rename + suggest-not-lock + angled + multiple stages |
| 2.2 | Simulation says nothing | Folds into Bancada comparison (ADR 0001) |
| 2.3 | Trade-off says nothing | Becomes "drag the cutoff" in Bancada |
| 2.4 | Optimization doesn't run / needed? | Becomes the suggestion engine on scores em jogo (ADR 0005) |
| 2.5 | Risk grouping matrix | Open editable matrix + manual grouping (ADR 0004) |
| 2.6 | Screening not understood | **Cut**; documented as future |
| 2.7 | Crash test unnecessary | Folds into the aggravation game in Bancada |
| 2.8 | Deploy OK | Kept; reached via unified save |

## Deferred / cut

- **Cut now:** Risk Screening page (2.6); Crash Test as a page (2.7); Optimization
  as a page (2.4); the v14 quick-fill button (1.8).
- **Deferred (future work):**
  - Full per-segment policies (independent filters/rates/aggravation + per-segment
    comparison) — ADR 0006 ships cutoffs-per-segment only.
  - Re-positioned "discover a business segment that still separates risk" (a useful
    reframing of Screening) feeding the light segmentation.
  - Value mapping of mis-coded columns (e.g. "pago"/"não pago" → 0/1) — 1.5 ships
    hints + validation only.
  - Manual tier override on the auto-detected comparison base (ADR 0002).

## Glossary (terms used above)

- **Bancada** — the central live policy-design screen (the heart of the studio).
- **Vigente policy / vigente score** — the policy / score currently in production;
  the comparison benchmark.
- **Score-in-use** — the score currently being evaluated/cut; binds cutoff axis +
  PD calibration (ADR 0003).
- **Scores em jogo** — the 2-3 short-listed candidate scores that flow downstream.
- **Matriciation** — combining two scores into a decision matrix (pairwise risk
  grouping); the alternative to replacing the vigente score.
- **Swap-in / swap-out / keep-in / keep-out** — quadrants of the candidate decision
  vs the vigente decision.
- **Comparison tier (A/B/C)** — how much of the vigente policy the data lets us
  reconstruct (ADR 0002).
- **Aggravation game** — pulling the flat stress factor up to find the break-even.
