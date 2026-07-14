# Prior art: monotonic threshold suggestion for hard filters

Research for issue [#59](https://github.com/matheuspasche/pycreditools/issues/59), feeding the HF-suggester
prototype: given known approval-rate / default-rate / conversion targets, suggest columns plus
**one-directional (monotonic) threshold values** to use as hard filters (a.k.a. policy rules /
knock-out rules).

## TL;DR — what the prototype should copy

A hard filter is a *single* cut point plus a direction, which is the degenerate (2-bin) case of
optimal binning. Every serious tool in this space converges on the same three-stage pipeline, and
the prototype should copy it rather than any one library:

1. **Shortlist columns by IV** (scorecardpy's `var_filter` drops anything with IV < 0.02;
   pycreditools already has IV machinery in `src/pycreditools/_kernels/iv.py` and
   `src/pycreditools/screening.py` to reuse).
2. **Generate candidate thresholds cheaply** — quantile grid (optbinning `prebinning_method="quantile"`,
   default `max_n_prebins=20`) or class-boundary midpoints (MDLP-style), with a **minimum support
   floor of ~5% of records per side** (`min_prebin_size=0.05` in optbinning,
   `count_distr_limit=0.05` in scorecardpy — the 5% convention is universal).
3. **Sweep the grid and pick by target** — for each candidate threshold compute approval %, bad rate
   among approved, and conversion among approved; emit the full table (industry name: *cutoff /
   strategy table*) and pick the threshold that hits the target approval rate or maximum bad rate.
   This is exactly how scikit-learn's `TunedThresholdClassifierCV` works (grid over thresholds,
   maximize a metric, cross-validated) and how credit-strategy texts describe cutoff setting
   ("80% acceptance rate → cutoff 320; max default rate 6% → cutoff 360").

Direction is **asserted, not discovered**: the caller (or a config table) declares
"higher negativação ⇒ higher default" and the suggester only *validates* it (monotone bad rate
along the quantile grid; flag violations instead of silently flipping). That mirrors Siddiqi's
"logical trend" doctrine and optbinning's explicit `monotonic_trend="ascending"/"descending"`
options.

---

## 1. Optimal binning with monotonicity constraints (optbinning)

The strongest formal prior art. Navas-Palencia,
[*Optimal binning: mathematical programming formulation*](https://arxiv.org/abs/2001.08025)
(arXiv:2001.08025), implemented in the [optbinning](https://gnpalencia.org/optbinning/binning_binary.html)
library.

**Recipe** (two-stage):

1. **Prebinning**: a fast algorithm generates m split points ⇒ n = m+1 granular prebins.
   `prebinning_method` ∈ {`"cart"` (decision tree, default), `"mdlp"`, `"quantile"`, `"uniform"`};
   `max_n_prebins=20`, `min_prebin_size=0.05`.
2. **Optimal merge**: a mixed-integer / constraint program decides which contiguous prebins to merge.
   Decision variables are a binary lower-triangular matrix X where `x_ij` says prebins j..i merge into
   one bin. Objective: **maximize total IV** (Jeffreys divergence, `Σ (p_i − q_i)·log(p_i/q_i)`).
   Solvers: `"cp"` (CP-SAT), `"mip"`, `"ls"`.

**Monotonicity is a linear constraint, not a post-hoc fix.** `monotonic_trend` options:

- `"ascending"` / `"descending"` — event rate must strictly increase/decrease across bins,
  with `min_event_rate_diff` (default 0) as the minimum gap β between consecutive bins;
- `"auto"` / `"auto_heuristic"` / `"auto_asc_desc"` — pick the trend that maximizes IV
  (`auto_asc_desc` restricts the choice to ascending-or-descending, which is the hard-filter case);
- `"concave"` / `"convex"` / `"peak"` / `"valley"` — single-inflection shapes for variables that are
  legitimately non-monotone (e.g. utilization, age);
- `None` — unconstrained.

Other constraints directly relevant to a filter suggester: `min_bin_size`/`max_bin_size`,
min/max event and non-event counts per bin, and `max_pvalue` (Z-test between bins — merge bins whose
event rates are not significantly different).

**Relevance:** for a *single* cut the MIP is overkill — with 20 prebins the "optimal 2-bin merge" is
just a 19-candidate sweep. But copy: the two-stage shape (cheap candidates → constrained pick), the
5% support floor, `min_event_rate_diff` (require the cut to separate bad rates by a meaningful gap),
and the peak/valley taxonomy for flagging non-monotone variables.

Earlier same-shape prior art: Oliveira et al., *Rigorous Constrained Optimized Binning for Credit
Scoring* ([SAS Global Forum 2008, paper 153-2008](https://support.sas.com/resources/papers/proceedings/pdfs/sgf2008/153-2008.pdf))
and Mironchyk & Tchistiakov,
[*Monotone optimal binning algorithm for credit risk modeling*](https://www.researchgate.net/publication/322520135_Monotone_optimal_binning_algorithm_for_credit_risk_modeling)
(2017, the "MOB" algorithm).

## 2. Entropy and chi-square discretization (MDLP, ChiMerge)

Two classic supervised discretizers; both produce candidate cut points but **neither enforces
monotonicity** — that's why scorecard tooling wraps them.

**MDLP** — Fayyad & Irani 1993,
[*Multi-Interval Discretization of Continuous-Valued Attributes for Classification Learning*](https://www.ijcai.org/Proceedings/93-2/Papers/022.pdf)
(IJCAI-93); verified against optbinning's
[implementation](https://github.com/guillermo-navas-palencia/optbinning/blob/master/optbinning/binning/mdlp.py):

- Candidate cuts are **midpoints between consecutive sorted values where the class label changes**
  (`0.5 * (x[1:] + x[:-1])` where `y` differs) — Fayyad & Irani's boundary-point result: optimal
  entropy cuts lie on class boundaries. When too many, reduce by percentiles (`max_candidates`).
- Recursively pick the cut minimizing weighted child entropy; **stop when the information gain fails
  the MDL test** `gain > (log2(n−1) + Δ)/n` with `Δ = log2(3^k − 2) − (k·E − k1·E1 − k2·E2)`.
- The recursion depth is data-driven — no fixed bin count.

**ChiMerge** — Kerber 1992, [*ChiMerge: Discretization of Numeric Attributes*](https://cdn.aaai.org/AAAI/1992/AAAI92-019.pdf)
(AAAI-92): start with every distinct value as its own interval; repeatedly merge the **adjacent**
pair with the lowest χ² = Σ (observed − expected)²/expected on the class-count contingency table;
stop when every adjacent χ² exceeds the threshold for a chosen significance level (optionally capped
by a max-interval count). This is the ancestor of the IV-loss agglomerative merge already in
`src/pycreditools/_kernels/iv.py` (same bottom-up adjacent-merge skeleton, different merge score).

**Relevance:** the MDLP boundary-point trick is the principled alternative to a pure quantile grid
for candidate thresholds, and ChiMerge's "merge until adjacent bins differ significantly" is the
statistical version of `min_event_rate_diff`. For the prototype, quantiles are simpler and nearly as
good at n ≥ tens of thousands.

## 3. Monotonic constraints in tree learners; decision stumps

**Gradient boosting**: both major libraries accept a per-feature direction vector
(+1 increasing, −1 decreasing, 0 free) —
[XGBoost `monotone_constraints`](https://xgboost.readthedocs.io/en/stable/tutorials/monotonic.html)
and [LightGBM `monotone_constraints`](https://lightgbm.readthedocs.io/en/latest/Parameters.html)
with `monotone_constraints_method` ∈ {`basic` (reject/bound violating splits — fast but
over-constrains), `intermediate`, `advanced`} per
[Auguste, Malory & Smirnov 2020](https://hal.science/hal-02862802/document), plus `monotone_penalty`
to discourage monotone splits near the root. The key design idea to steal: **direction is a
declared input per column, not something the algorithm infers** — the model is then guaranteed
monotone even where the raw data wiggles.

**Decision stump as threshold finder**: a depth-1
[`DecisionTreeClassifier`](https://scikit-learn.org/stable/modules/tree.html) (`max_depth=1`) is the
minimal supervised cut-point picker — it scans all midpoints and picks the split minimizing
Gini/entropy. It finds the *most discriminative* cut, not the cut that hits a business target;
`min_samples_leaf` is its thin-bin guard. optbinning's default prebinning is literally a CART tree
used this way. Useful as a cross-check ("the entropy-optimal cut is at X; your target-approval cut
is at Y").

**Relevance:** GBM monotone constraints solve a different problem (monotone *score*, not a
human-readable cut) — don't build the suggester on them, but adopt the ±1 direction-vector API shape
for declaring expected directions per column.

## 4. WoE / IV-guided cuts — the classic scorecard workflow

Reference implementations: [scorecardpy](https://github.com/ShichenXie/scorecardpy) (Python) and the
R [`scorecard`](https://cran.r-project.org/web/packages/scorecard/scorecard.pdf) package; doctrine
from Siddiqi,
[*Intelligent Credit Scoring*](https://www.researchgate.net/publication/349548432_Intelligent_Credit_Scoring_Building_and_Implementing_Better_Credit_Risk_Scorecards)
(Wiley, 2017).

**The pipeline** (scorecardpy): `var_filter` (drop variables with **IV < 0.02**, high missing rate,
near-constant values) → `woebin` → `woebin_ply` (WoE transform) → logistic regression → `scorecard`
scaling → `perf_eva`/`perf_psi`. [`woebin` defaults](https://github.com/ShichenXie/scorecardpy/blob/master/scorecardpy/woebin.py):
`method="tree"`, `count_distr_limit=0.05`, `stop_limit=0.1`, `bin_num_limit=8`. The tree method
greedily adds the break that maximizes IV, subject to every bin holding ≥ 5% of records, and stops
when the relative IV gain of one more break drops below `stop_limit` — an explicit
diminishing-returns guard against over-binning. `method="chimerge"` is the Kerber alternative.

**Direction handling — "logical trend":** Siddiqi's rule is that each variable's WoE pattern must
follow a business-logical, usually monotone, trend (higher negativação ⇒ higher default ⇒
monotonically decreasing WoE). In practice the direction is **declared from domain knowledge and the
binning is adjusted (bins merged/re-cut) until the trend holds**; a variable whose WoE refuses to go
monotone is treated with suspicion (data artifact, interaction, or leakage) rather than auto-flipped.
Some jurisdictions outright require monotone predictor-risk relationships. This is the strongest
argument for the suggester taking direction as input and reporting violations.

**Relevance:** IV shortlisting (≥ 0.02 "weak", with ~0.1/0.3 as the customary medium/strong rungs)
is the standard column-ranking step, and pycreditools already computes IV — the suggester's
column-selection stage is essentially `var_filter` re-pointed at hard-filter candidates.

## 5. The simple grid — cutoff tables, threshold sweeps, swap sets

What a *simple* implementation looks like in prior art, under three names:

**(a) Cutoff / strategy table (credit-risk practice).** List candidate score cutoffs with approval
rate and bad rate at each; choose the cutoff that meets the business target. The
[RapidMiner/Altair credit-scoring series, part 8](https://blogs.sw.siemens.com/rapidminer/credit-scoring-series-part-eight-credit-risk-strategies/)
gives the canonical framing: an 80% acceptance target puts the cutoff at 320, a 6% max default rate
pushes it to 360, a profit objective to 440; a "hard cut-off" is a single fixed value versus
multi-treatment bands (accept / refer / decline), optionally segmented. Hard filters on individual
variables ride alongside as "policy and regulatory rules".

**(b) Post-hoc threshold tuning (ML practice).** scikit-learn's
[`TunedThresholdClassifierCV`](https://scikit-learn.org/stable/modules/classification_threshold.html)
formalizes the same sweep: grid over decision thresholds, evaluate a chosen metric under
cross-validation, pick the maximizer; `FixedThresholdClassifier` applies a hand-picked one. The docs
stress that the default 0.5 is arbitrary under asymmetric costs, and **warn against tuning the
threshold on the data used to fit** (overfitting). ROC-based picks (e.g. Youden's J = TPR − FPR,
Youden 1950) are the older single-number variant of the same idea.

**(c) Swap-set analysis (evaluating a cutoff change).** Comparing old vs new strategy at matched
volume: *swap-ins* (declined before, approved now), *swap-outs* (approved before, declined now), and
the unchanged core; hold approval rate constant and compare bad rates, or vice versa
([Experian](https://www.experian.com/blogs/insights/swap-set-measure-impact-model-changes/)).
This is the standard report format for "what does adding/moving this hard filter actually change".

**Concrete recipe distilled from (a)+(b):**

```
for each candidate column (IV >= iv_min, direction declared):
    grid = quantiles of column (e.g. p1..p99 step 1, dedup)
    drop candidates leaving < 5% of records on the cut side
    for t in grid:
        approved = rows passing the filter (<= t or >= t per direction)
        record (t, approval%, bad_rate(approved), conversion(approved))
    validate: bad_rate among *rejected* quantile slices is monotone in the declared
              direction (Spearman on slice bad rates, or count of inversions); flag if not
    suggest t* = the grid point hitting the target (approval% >= A, or bad_rate <= B,
              or max conversion s.t. constraints); return the whole table, not just t*
```

## Pitfalls (documented, not hypothetical)

- **Overfitting thin bins.** The universal countermeasure is a minimum-support floor: optbinning
  `min_prebin_size=0.05`, scorecardpy `count_distr_limit=0.05`, CART `min_samples_leaf`. A threshold
  whose "great bad rate" rests on 40 rejected rows is noise; also require a minimum count of *events*
  (defaults exist in optbinning for min event/non-event per bin) and a minimum bad-rate gap
  (`min_event_rate_diff` / ChiMerge significance).
- **Non-monotone raw variables.** Empirical event rates wiggle even when the true relation is
  monotone, and some variables are genuinely U-shaped (optbinning ships `peak`/`valley` shapes for
  them). A hard one-directional filter on a valley-shaped variable silently rejects the wrong tail.
  Countermeasure: validate the declared direction on the quantile grid and *refuse or flag* instead
  of auto-picking a direction — auto-flipping (`auto_asc_desc`) maximizes in-sample IV and will
  happily learn noise on weak variables.
- **Tuning and evaluating on the same data (target leakage).** scikit-learn's threshold docs warn
  explicitly: never tune the cut on the data used to fit/evaluate. Scorecard practice adds
  out-of-time validation (PSI via `perf_psi`) because credit populations drift; a threshold tuned on
  one vintage can miss the target approval rate on the next. Also classic leakage: candidate columns
  computed post-application (collections flags, post-default bureau updates) show spectacular IV and
  must be screened out before suggestion.
- **Correlated filters double-counting.** Two filters on correlated bureau variables (e.g. two
  negativação counts) each look fine alone but jointly reject nearly the same people — the second
  filter's marginal effect is far smaller than its solo grid suggests, while the *estimated* combined
  rejection (if naively multiplied) overstates reality. Countermeasure from practice: evaluate the
  filter *set* jointly (apply sequentially, report marginal approval/bad-rate impact of each — the
  swap-set discipline), and warn on high rank-correlation between suggested columns.
- **Interaction blindness.** All univariate binning/thresholding ignores interactions (a cut fine
  overall may be wrong within a segment). Scorecard practice answers with segmentation (different
  cutoffs per segment — RapidMiner part 8); pycreditools' own screening already bins *within*
  base-risk tiers (`ScreeningRecipe.boundaries` is per-tier), which is the right template: offer
  per-tier thresholds as a follow-up, not in the first prototype.
- **Reject inference / selection bias** (adjacent, worth noting): historical data only shows defaults
  for *approved* applicants, so bad rates below existing cutoffs are extrapolations. Any suggested
  filter that cuts deeper than the current policy is evaluated on a censored region.

## Recommendation — simplest credible implementation

Build the **quantile-grid cutoff table** (§5 recipe), not a MIP and not a tree wrapper:

1. Reuse existing IV machinery to shortlist columns (`iv >= 0.02`, configurable).
2. Take direction as **declared input per column** (±1 vector, LightGBM-style; a small default map
   for known bureau variables), and validate it on ~20 quantile slices; flag violations.
3. Sweep percentile candidates with a 5% support floor and a `min_event_rate_diff`-style gap check;
   compute approval%, bad rate, conversion per candidate.
4. Select by target (approval ≥ A / bad rate ≤ B / max conversion subject to both) but **return the
   whole strategy table** — the table, not the point estimate, is the deliverable practitioners trust.
5. Report suggested filters *jointly* (sequential marginal impact, swap-set style) and require a
   holdout or out-of-time slice for the reported metrics.

This matches optbinning's architecture with the optimization stage collapsed to a 1-cut argmax
(which a grid solves exactly), and matches what credit-strategy practice already calls cutoff
setting — no new vocabulary needed. Upgrade path if 2+ cuts per variable are ever needed: swap
stage 3-4 for optbinning's `OptimalBinning(monotonic_trend="ascending"|"descending")` and keep the
rest.

## Sources

- optbinning `OptimalBinning` API docs — https://gnpalencia.org/optbinning/binning_binary.html
- Navas-Palencia, *Optimal binning: mathematical programming formulation* — https://arxiv.org/abs/2001.08025
- optbinning MDLP implementation — https://github.com/guillermo-navas-palencia/optbinning/blob/master/optbinning/binning/mdlp.py
- Fayyad & Irani (1993), *Multi-Interval Discretization of Continuous-Valued Attributes* (IJCAI-93) — https://www.ijcai.org/Proceedings/93-2/Papers/022.pdf
- Kerber (1992), *ChiMerge: Discretization of Numeric Attributes* (AAAI-92) — https://cdn.aaai.org/AAAI/1992/AAAI92-019.pdf
- XGBoost monotonic constraints tutorial — https://xgboost.readthedocs.io/en/stable/tutorials/monotonic.html
- LightGBM parameters (`monotone_constraints*`) — https://lightgbm.readthedocs.io/en/latest/Parameters.html
- Auguste, Malory & Smirnov (2020), monotone-constraint methods cited by LightGBM — https://hal.science/hal-02862802/document
- scorecardpy (workflow, `var_filter` iv_limit=0.02) — https://github.com/ShichenXie/scorecardpy
- scorecardpy `woebin` defaults and tree method — https://github.com/ShichenXie/scorecardpy/blob/master/scorecardpy/woebin.py
- R `scorecard` package reference — https://cran.r-project.org/web/packages/scorecard/scorecard.pdf
- Siddiqi, *Intelligent Credit Scoring* (Wiley) — https://www.researchgate.net/publication/349548432_Intelligent_Credit_Scoring_Building_and_Implementing_Better_Credit_Risk_Scorecards
- Mironchyk & Tchistiakov (2017), *Monotone optimal binning algorithm for credit risk modeling* — https://www.researchgate.net/publication/322520135_Monotone_optimal_binning_algorithm_for_credit_risk_modeling
- Oliveira et al. (2008), *Rigorous Constrained Optimized Binning for Credit Scoring*, SAS Global Forum 153-2008 — https://support.sas.com/resources/papers/proceedings/pdfs/sgf2008/153-2008.pdf
- scikit-learn, tuning the decision threshold — https://scikit-learn.org/stable/modules/classification_threshold.html
- scikit-learn, decision trees (`max_depth`, `min_samples_leaf`) — https://scikit-learn.org/stable/modules/tree.html
- Experian, swap-set analysis — https://www.experian.com/blogs/insights/swap-set-measure-impact-model-changes/
- RapidMiner/Altair, Credit Scoring Series part 8: credit risk strategies — https://blogs.sw.siemens.com/rapidminer/credit-scoring-series-part-eight-credit-risk-strategies/
