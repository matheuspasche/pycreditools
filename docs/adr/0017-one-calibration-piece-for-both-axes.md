# ADR 0017 — One calibration piece computes both axes of the premise

- **Status:** Accepted
- **Date:** 2026-09-10
- **Scope:** the calibration entry in `_kernels/` that the v0.6 engine calls from ticket 6 —
  the per-band estimate of take-up and PD for the rows the premise models, and its degree-3
  numbers.
- **Tickets:** #179 (this ADR). Consumes #72, #132, #139, #155, and ADR 0016.
- **Amends:** the living engine spec, §4.11 (the calibration-support note gains the inversion
  count's definition).
- **Measured against:** `release/v0.6` (`b884b95`).

## Context

`_kernels/calibration.py` has two entry points over one computation:
`calibrate_by_score_bins` (`:32`, six parameters) and `diagnose_score_bin_calibration` (`:124`,
seven — the first five identical). The caller passes the same five arguments twice and must
keep them in agreement; the diagnosis learns the edges and cuts the population again. Both
wrap their whole body in `try/except Exception` and degrade to `global_fallback` (`:63-78`,
`:153-169`) — a site outside the inventory of #132's package rule.

The v0.5 engine calls the rate function twice per study — take-up through
`CalibratedExpression` (`expressions.py:217`), PD at `simulation.py:751` — and diagnoses PD
once more (`:760`), with a direction read off the last cutoff that gates the score and a silent
`"gte"` when none does (`stages.py:189-202`). That direction source died with the cascade
(#132, case 2), while `n_inversions` stayed contracted (US 43, tickets 6 and 11). The premise
has no direction field.

## Decision

**One piece, one call per study** — per grid point under `calibrate_on="keep_in"`, which
recalibrates by construction. It computes every axis of the premise that buckets on the lens:
the contract rate when `take_up="binned"`, the PD when `outcome_from="parcelling"`; an axis not
asked for is not computed.

- **Takes:** the lens for the base (a score, or a rating already built upstream), the incumbent's
  approval, hire and outcome, the `calibrate_on` population, and `bins` — or the lens's
  categories, in declared order, when it is discrete.
- **Each axis has its own bands, learned on its own teaching set.** One population choice
  governs both guesses (#139 §4), but the observability precondition differs per axis and
  applies to edges and rates alike (#139): take-up is taught on *population ∩ approved*, PD on
  *population ∩ outcome present*. The `bins` setting is shared; the edges are not. The stress
  ladder indexes the PD bands.
- **No fallback, no swallowing.** An empty band or an unbanded row gets a null, with coverage
  beside it — never the global rate (#132 §4.3; ticket 6's contract,
  `v06-tickets.md:111`). Errors are caught narrowly; a programming error propagates (#132).
- **Diagnostics are PD-only.** `n_inversions` counts how many times the per-band PD curve
  changes direction, beyond the same relative tolerance used today (0.10 of the previous band's
  PD). A curve monotone in either direction scores 0; no direction is declared or inferred.
  `no_overlap_fraction` is unchanged in meaning. **The contract axis has no direction
  diagnostic**: flat by risk level, or sloped — worse score, more credit-seeking, converts more,
  which is how `sample_data.py:222-226` generates it (*"Adverse selection"*) — are both
  legitimate behaviours of the client.
- **Returns one frozen result:** per-row take-up, per-row PD, `n_inversions`,
  `no_overlap_fraction`, coverage.

**Coexistence.** The piece lands beside the old pair. `calibrate_by_score_bins`,
`diagnose_score_bin_calibration` and `CalibrationDiagnostics` stay untouched for the old tree
(`v06-tickets.md:143`) and die in ticket 16. The question of *when* #132's rule reaches this
site dissolves: the swallow never enters the engine.

## Rejected

- **Two functions, prefix repeated** — today's shape minus the fallback: five arguments passed
  twice and kept equal by hand, and the diagnosis re-derives the bands.
- **One generic "rate per band over this population" function, called once per axis**, with
  the diagnosis apart — more general, but *"one population for both guesses"* then lives in the
  caller, which can pass two different ones.
- **A direction field on the premise** — a seventh field consumed only by a diagnostic number,
  amending *"um tipo, seis campos"*.
- **Reading the direction off the policy's filter on the lens** — inference (§4.11), and it
  breaks in the mixed configuration (cut on one score, lens on another), where it would need a
  silent default: today's defect.

## Consequences

- `n_inversions` **changes meaning** against v0.5. A PD-like score (higher is riskier) no longer
  reads as fully inverted under the old `"gte"` convention; a monotone curve in the wrong
  direction is no longer flagged, because "wrong" has no declared referent. The parity harness
  (ticket 15) must not compare the two numbers as if they were one.
- The six plus thirteen direct tests (`test_calibration_kernel.py`,
  `test_calibration_diagnostics.py`) keep covering the old pair until 16. The new piece is
  internal and tested through seam 1 (§5).
- A correction recorded for the next reader: during the grilling session the bands of the two
  axes were first described as identical because *"uma config serve todo eixo"*. They are not —
  the config (`bins`) is shared, the teaching sets are not.
