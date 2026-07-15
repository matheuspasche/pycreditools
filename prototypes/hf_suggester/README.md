# PROTOTYPE — hard-filter suggester (wayfinder ticket #60)

Throwaway. Lives on branch `prototype/hf-suggester`, off `release/v0.5`. Nothing here ships.

```
python prototypes/hf_suggester/tui.py
```

`l`/`L` lift floor, `c`/`C` volume ceiling, `b`/`B` minimum bads, `q` quit.

## The question

Research [#59](https://github.com/matheuspasche/pycreditools/issues/59) settled the machinery — IV
shortlist, quantile grid, declared direction, support guard — but assumed the credit-strategy
verdict: pick the cut that hits a target approval rate. Wrong verdict for hard filters. A hard filter
is a *cheap* cadastral/scraper variable carrying a bizarre default signal on a small slice: "1.5x a
inad da base e corta pouco". So the rule under test is a **lift floor + volume ceiling**.

Does that rule surface the hard filters planted in `generate_sample_data`, and are `lift_min` /
`max_cut` the right two knobs?

## What it answered

**1. The lift floor never picks the cut — it picks the column.** On any monotone risk variable lift
rises continuously as you cut less (`vl_negativacao`: 1.53x at 12.3%, 1.96x at 2.5%), with no knee
at the threshold the generator literally planted. So every column's suggestion lands exactly on
`max_cut`. The floor still earns its place: it rejects columns that can't clear it at all (`age`
1.34x, `income` 1.02x). Two knobs, two different jobs — `max_cut` picks the threshold, `lift_min`
picks the column.

**2. No statistical property separates a hard filter from a score cutoff.** Tail concentration
(lift@2.5% ÷ lift@10%) was the candidate discriminator; `score_5` scores *highest* on it (1.60) —
a good score is precisely concentrated risk. The HF/score boundary is economic, not statistical:
HF variables are client-declared, cadastral, scraped, cheap. So it is **declared by the caller**,
same precedent as direction (#59) and the sweep contract (#57). Not the suggester's job.

**3. The bad marker is just a column whose mean is the bad rate** — observed flag or estimated PD,
no special case, no mode. But both lie, in opposite directions:

| | true lift | observed (contracted) | inferred (whole base) |
|---|---|---|---|
| cpf inválido | 2.10x | n=1, unmeasurable | 1.41x |
| negativação > 2000 | 1.64x | 2.23x | 1.41x |
| protestos > 500 | 1.85x | 2.21x | 1.37x |

Observed **overstates** — surviving a policy that rejects your kind makes you a strange survivor.
Inferred **understates** — it carries only what the model learned. `cpf_valido` is the textbook hard
filter (2.10x true lift, 0.20% of base) and among contracted it is **1 row, 0 bads, 0.00x**: the
incumbent policy already rejected it, so it has no observable default rate by construction. This is
[#58](https://github.com/matheuspasche/pycreditools/issues/58)'s no-overlap problem in a harsher
form — not edge extrapolation, total absence.

Owner's verdict: measure where measurement is possible, declare which target was used, warn on
columns the incumbent policy already acts on. The estimated column is the caller's escape, not a
mode.

**4. #59's 5% support floor collides head-on with `max_cut`.** "Each side needs ≥5% of records" bans
every candidate a ≤5% volume ceiling wants. The floor's intent is about counts, not percentages —
recast as `min_rejected_bads` (optbinning's `min_event_count`), held loose because the package
assumes volume.

**5. Hard-filter columns are zero-inflated and the quantile grid collapses on them.** 78% of
`vl_negativacao` is 0; dedup leaves almost no candidates. Distinct values are the only fallback that
gives such a column any candidates at all — and this is the *normal* shape for HF variables, not an
edge case.

## Amendment — findings 1 and the `max_cut` parameter are superseded

`max_cut` (~5% per column) was invented by the agent, not grounded in #59, and the owner corrected it
in the same session. **The budget belongs to the HF set and is relative to the target approval rate**:
`budget = 1 - target_approval_rate - score_room`. A 20%-approval product spends ~60pp on all hard
filters together, leaving the score the remaining ~20pp — the score must stay the dominant lever on
the approval rate. So finding 1 above ("every column lands exactly on `max_cut`") is an artifact of an
invented ceiling set far too tight, `target_approval_rate` comes back as the budget's source, and
overlap becomes first-class: five sample rules cutting 67.2% by naive sum cut **51.6%** in union.

The code in `suggester.py` therefore has the wrong parameter *and* the wrong algorithm — it re-masks
the frame per threshold, which makes grid size a cost knob (6.5s at 380 candidates, 22.8s at 1,980,
1M × 20). Sorting each column once and binary-searching a cumsum of the bad column makes the grid
free: **3.16s at 380 candidates, 3.96s at 199,980**. Findings 2, 3, 4 and 5 stand unchanged.

Full correction in [#60's amendment](https://github.com/matheuspasche/pycreditools/issues/60#issuecomment-4981301908);
the spec is [#73](https://github.com/matheuspasche/pycreditools/issues/73).

## Files

- `suggester.py` — the pure part, worth lifting: `strategy_table`, `suggest`, `near_misses`,
  `column_iv` (reuses `_kernels.calculate_tier_metrics` with a single constant group).
- `tui.py` — throwaway shell.
