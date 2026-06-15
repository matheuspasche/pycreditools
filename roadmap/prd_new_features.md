# PRD: New Credit Policy Decision Features & Visualizations in pycreditools

This document specifies the business requirements, technical design, and verification plan for adding new credit decisioning features and visualizations to the `pycreditools` library. All code elements, docstrings, error messages, and console outputs must be implemented in English.

---

## 1. Funnel Plot Visualization (`plot_funnel`)

### Context & Goal
Enable credit risk analysts to interactively visualize the applicant pass rates and drop-offs across the sequential credit policy stages (hard filters and cutoffs) without requiring individual stage columns to be kept in the final dataset.

### Technical Requirements

#### Location
* File: [visualization.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/visualization.py)
* Signature:
  ```python
  def plot_funnel(sim_results: CreditSimResults) -> go.Figure:
  ```

#### Detailed Logic
1. **Dependency Check**:
   * Dynamically import `plotly.graph_objects as go`. If not present, raise an `ImportError`:
     `"Plotly is required for plot_funnel. Please install it using 'pip install plotly' or install pycreditools with the [viz] extra."`
2. **Policy Extraction**:
   * Get the policy object `pol` from `sim_results.policy`.
   * If `pol` is `None`, attempt to deserialize it from `sim_results.metadata["policy"]` using `CreditPolicy.from_dict()`. If still `None`, raise a `ValueError`:
     `"No policy reference found in simulation results to extract hard filters."`
3. **Hard Filter Extraction**:
   * Identify hard stages (those that are not `RateStage`s):
     ```python
     from .stages import RateStage
     hard_stages = [stage for stage in pol.stages if not isinstance(stage, RateStage)]
     ```
   * Let `H` be the number of hard stages.
4. **Data Verification**:
   * Check if the `"reason"` column exists in `sim_results.data`.
   * If not present, raise a `ValueError`:
     `"The 'reason' column is missing from simulation results. Please ensure the simulation was run and calculated decision reasons."`
5. **Node Count Calculations**:
   * Let `N_total` be the total row count of the input data: `N_total = len(sim_results.data)`.
   * For each hard stage `i` (from `0` to `H-1`):
     * Let the stage fail label be: `f"{i + 1}: {hard_stages[i].name}"`.
     * Calculate the number of candidates rejected at stage `i`:
       `R[i] = (sim_results.data["reason"] == fail_label).sum()`
     * Calculate the number of candidates who passed stage `i`:
       `P[i] = (sim_results.data["reason"] == "Approved").sum() + sum(R[j] for j in range(i + 1, H))`
   * Let the total rejections be: `V_rejected = sum(R)`.
   * Let the total approvals be: `V_approved = P[H-1]` if `H > 0` else `N_total` (where `P[H-1]` is identical to `(sim_results.data["reason"] == "Approved").sum()`).
6. **Sankey Node Mapping**:
   * Set up labels and colors:
     * Node 0: `"Total"` -> Label: `f"Total<br>{N_total:,} (100.0%)"`, Color: `"#64748b"`
     * For `i` in `range(H)`:
       * Node `i + 1`: Stage Output -> Label: `f"{i + 1}: {hard_stages[i].name}<br>{P[i]:,.0f} ({P[i] / N_total:.1%})"`, Color: `"#3b82f6"`
     * Node `H + 1`: `"Approved"` -> Label: `f"Approved<br>{V_approved:,.0f} ({V_approved / N_total:.1%})"`, Color: `"#10b981"`
     * Node `H + 2`: `"Rejected"` -> Label: `f"Rejected<br>{V_rejected:,.0f} ({V_rejected / N_total:.1%})"`, Color: `"#f43f5e"`
7. **Sankey Link Calculations**:
   * Initialize link lists: `sources = []`, `targets = []`, `values = []`, `link_colors = []`.
   * If `H == 0`:
     * Add link from Total (0) to Approved (1) with value `N_total`.
   * If `H > 0`:
     * Add link from Total (0) to Stage 0 (1): value `P[0]`, color `"rgba(59, 130, 246, 0.2)"`.
     * Add link from Total (0) to Rejected (H+2): value `R[0]`, color `"rgba(244, 63, 94, 0.15)"`.
     * For `i` in `range(1, H)`:
       * Add link from Stage `i-1` (index `i`) to Stage `i` (index `i+1`): value `P[i]`, color `"rgba(59, 130, 246, 0.2)"`.
       * Add link from Stage `i-1` (index `i`) to Rejected (index `H+2`): value `R[i]`, color `"rgba(244, 63, 94, 0.15)"`.
     * Add link from last Stage `H-1` (index `H`) to Approved (index `H+1`): value `V_approved`, color `"rgba(16, 185, 129, 0.2)"`.
   * Filter links: Only append links with `value > 0`.
8. **Figure Customization**:
   * Build the Plotly figure:
     ```python
     fig = go.Figure(data=[go.Sankey(
         node=dict(
             pad=15,
             thickness=20,
             line=dict(color="black", width=0.5),
             label=labels,
             color=node_colors
         ),
         link=dict(
             source=sources,
             target=targets,
             value=values,
             color=link_colors
         )
     )])
     fig.update_layout(
         title_text="Credit Policy Decision Funnel (Sankey)",
         font_size=12,
         font_family="Inter, Roboto, sans-serif",
         plot_bgcolor="white",
         paper_bgcolor="white",
         margin=dict(l=20, r=20, t=50, b=20)
     )
     ```
   * Return `fig`.

#### Simulator Updates (to Support drop_stages=True)
* File: [simulation.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/simulation.py)
* In `run_simulation`:
  * Before applying the `if drop_stages:` check, compute the `reason` and `decision` columns using the exact logic from `to_decision_dataframe()` and append them directly to the simulation DataFrame (`df`):
    ```python
    hard_stages = [(i, stage) for i, stage in enumerate(policy.stages) if not isinstance(stage, RateStage)]
    if not hard_stages:
        df["decision"] = "Approved"
        df["reason"] = "Approved"
    else:
        stage_cols = [f"stage_{i}_{stage.name}" for i, stage in hard_stages]
        failed_df = pd.DataFrame(index=df.index)
        for col_name in stage_cols:
            if col_name in df.columns:
                failed_df[col_name] = df[col_name] < 0.5
            else:
                failed_df[col_name] = False
        has_failure = failed_df.any(axis=1)
        col_to_label = {f"stage_{i}_{stage.name}": f"{i + 1}: {stage.name}" for i, stage in hard_stages}
        first_failed_col = np.where(has_failure, failed_df.idxmax(axis=1), None)
        df["decision"] = np.where(has_failure, "Rejected", "Approved")
        df["reason"] = pd.Series(first_failed_col, index=df.index).map(col_to_label).fillna("Approved")
    ```
  * Update `to_decision_dataframe()` in `simulation.py` to simply pull these columns if they are already present, or fallback to the computation if they are not.

---

## 2. Multi-Policy Comparison (Champion vs. Challengers)

### Context & Goal
Allow side-by-side executive delta comparisons between a baseline policy (Champion) and multiple alternative policies (Challengers) in a single consolidated console layout.

### Technical Requirements

#### Location
* File: [performance.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/performance.py)

#### Function: `compare_policies`
* Signature:
  ```python
  def compare_policies(
      sim_new: CreditSimResults | list[CreditSimResults] | tuple[CreditSimResults, ...],
      sim_old: CreditSimResults,
  ) -> dict[str, Any] | list[dict[str, Any]]:
  ```
* Logic:
  * If `isinstance(sim_new, (list, tuple))`:
    * Return `[compare_policies(sim, sim_old) for sim in sim_new]`.
  * Otherwise, run the existing comparison logic.

#### Function: `print_delta_table`
* Signature:
  ```python
  def print_delta_table(
      sim_new: CreditSimResults | list[CreditSimResults] | tuple[CreditSimResults, ...],
      sim_old: CreditSimResults | pd.DataFrame | None = None,
  ) -> None:
  ```
* Logic:
  1. **Normalize Input**:
     * `sims_new = list(sim_new) if isinstance(sim_new, (list, tuple)) else [sim_new]`
  2. **Extract Legacy Baseline**:
     * Compute `aprov_old` and `bad_old` from `sim_old`.
     * If `sim_old` is a `CreditSimResults`:
       * `df_old = sim_old.data`
       * `policy_old_dict = sim_old.metadata["policy"]`
       * `old_default_col = policy_old_dict["actual_default_col"]`
       * `old_approval_col = policy_old_dict.get("current_approval_col", "approved")`
       * `method = sim_old.metadata.get("method", "stochastic")`
     * If `sim_old` is a `pd.DataFrame`:
       * `df_old = sim_old`
       * `policy_ref = sims_new[0].metadata["policy"]`
       * `old_default_col = policy_ref["actual_default_col"]`
       * `old_approval_col = policy_ref.get("current_approval_col", "approved")`
       * `method = sims_new[0].metadata.get("method", "stochastic")`
     * If `sim_old` is `None`:
       * Extract baseline stats from `sims_new[0].data` using its configured `current_approval_col` and `actual_default_col`.
     * Calculations:
       * `is_analytical = method == "analytical"`
       * `aprov_old = df_old[old_approval_col].mean() if is_analytical else (df_old[old_approval_col] > 0).mean()`
       * `legacy_hired = "hired" if "hired" in df_old.columns else old_approval_col`
       * `vol_old = df_old[legacy_hired].sum()`
       * `bad_old = (df_old[old_default_col] * df_old[legacy_hired]).sum() / vol_old if vol_old > 0 else 0.0`
  3. **Extract Challenger Metrics**:
     * For each `sim` in `sims_new`:
       * `df_new = sim.data`
       * `is_analytical = sim.metadata.get("method") == "analytical"`
       * `aprov_col = "approved_pre_rate" if "approved_pre_rate" in df_new.columns else "new_approval"`
       * `aprov_new = df_new[aprov_col].mean() if is_analytical else (df_new[aprov_col] > 0).mean()`
       * `vol_new = df_new["new_approval"].sum()`
       * `bad_new = (df_new["simulated_default"] * df_new["new_approval"]).sum() / vol_new if vol_new > 0 else 0.0`
       * Store in lists: `aprov_news.append(aprov_new)`, `bad_news.append(bad_new)`.
  4. **Render Console Output**:
     * If `sims_new` has length 1:
       * Print the standard single-comparison table.
     * If `sims_new` has length > 1:
       * Print the consolidated multi-column delta table:
         ```text
         === DELTA TABLE: EXECUTIVE P&L ===
         Metric                               Legacy         New 1         New 2
         ──────────────────────────────────────────────────────────────────────────────
         Global Approval Rate (% ToF)         35.00%        40.00%        42.50%
           Delta Abs (vs Legacy)                            +5.00%        +7.50%
           Delta Rel (vs Legacy)                            +14.3%        +21.4%
         Expected Bad Rate                     2.50%         2.20%         2.45%
           Delta Abs (vs Legacy)                                -0.30%        -0.05%
           Delta Rel (vs Legacy)                                -12.0%         -2.0%
         ```
       * Width formatting: Column 1 (`Metric`) is left-aligned with width 36. Column 2 (`Legacy`) is right-aligned with width 14. Columns 3+ (`New X`) are right-aligned with width 14.
       * Separator line spans the entire table width: `36 + 14 + 14 * len(sims_new)`.
       * Absolute differences are calculated as: `val_new - val_old`.
       * Relative differences are calculated as: `(val_new / val_old) - 1.0` (handle division by zero by returning `0.0` if `val_old == 0.0`).

---

## 3. Direct Inferred Default Column (`estimated_default_col`)

### Context & Goal
Provide a direct path for the simulator to inherit pre-calculated probability of default (PD) estimates from Reject Inference models, bypassing the decile calibration logic while keeping quadrant scenarios and observed outcomes intact.

### Technical Requirements

#### A. Policy Configuration Updates
* File: [policy.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/policy.py)
* Add `estimated_default_col: str | None = None` to `CreditPolicy`'s initialization parameters.
* Update `to_dict` to serialize the key `"estimated_default_col"`.
* Update `from_dict` to deserialize the key `"estimated_default_col"` (defaulting to `None`).
* Update `describe` to append the line `f"  Estimated default: {self.estimated_default_col}"`.
* Update `validate(self, df)` to ensure that if `self.estimated_default_col` is not `None`, it is appended to the required columns list and verified to be present in `df.columns`.

#### B. Swap Simulator Path
* File: [simulation.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/simulation.py)
* In `_estimate_swap_in_baseline_pd`, check if `policy.estimated_default_col` is configured:
  ```python
  if policy.estimated_default_col is not None and policy.estimated_default_col in df.columns:
      return swap_ins[policy.estimated_default_col].astype(float)
  ```
* This bypasses the decile binning calculations and uses the column values directly for all `swap_in` candidates.

#### C. Standalone Simulator Path
* File: [simulation.py](file:///c:/Users/Matheus/Documents/GitHub/pycreditools/src/pycreditools/simulation.py)
* Replace the baseline extraction logic in `_assign_simulated_defaults_standalone(df, policy, method)`:
  1. Identify observed defaults:
     * `known_outcome` is initialized as a NaN series. If `policy.actual_default_col` is set and in `df.columns`, populate `known_outcome = df[policy.actual_default_col].astype(float)`.
  2. Identify simulated defaults baseline:
     * If `policy.estimated_default_col` is set and in `df.columns`, set `sim_pd = df[policy.estimated_default_col].astype(float)`.
     * Otherwise, fallback to rate stages: if `RateStage`s are present, evaluate the last one analytically to set `sim_pd`. Else, set `sim_pd` as a NaN series.
  3. Apply stress scenarios:
     * If `policy.stress_scenarios` are defined, apply them to `sim_pd` to compute `final_probs`. Else, `final_probs = sim_pd.clip(0.0, 1.0)`.
  4. Assign outcomes to the approved population (`new_approval > 0`):
     * For candidates where `known_outcome` is not NaN, copy the outcome directly to `simulated_default`.
     * For candidates where `known_outcome` is NaN, draw default status stochastically (if method is `SimulationMethod.STOCHASTIC`) using `final_probs`, or copy `final_probs` directly (if analytical).

---

## Verification & Testing Plan

All test functions must be written in English and located inside the existing testing structure.

### 1. test_plot_funnel (`tests/test_improvements_prd.py`)
* Create a dummy dataset and configure a CreditPolicy with two CutoffStages.
* Run the simulation with `drop_stages=True` and `drop_stages=False`.
* Call `plot_funnel(results)` on both simulation results:
  * Verify it returns a Plotly `Figure` in both cases.
  * Verify the number of nodes in the figure is equal to `len(hard_stages) + 3`.
  * Verify the link values perfectly match the cumulative pass counts and rejections.

### 2. test_multi_policy_delta_table (`tests/test_improvements_prd.py`)
* Configure a base policy and simulate it (Champion).
* Configure two challenger policies (e.g., varying a scorecard cutoff stage) and simulate them (Challengers).
* Call `compare_policies(challengers, champion)` and verify it returns a list of two dicts.
* Call `print_delta_table(challengers, champion)`:
  * Capture stdout using pytest's `capsys` fixture.
  * Verify the printed string contains the headers `=== DELTA TABLE: EXECUTIVE P&L ===`, `Global Approval Rate (% ToF)`, and `Expected Bad Rate`.
  * Verify the printed string does *not* contain `Expected Hired Volume`.

### 3. test_estimated_default_col (`tests/test_improvements_prd.py`)
* Create a dataset containing `actual_default` and `estimated_pd` columns.
* Configure a policy with `estimated_default_col="estimated_pd"`.
* **Swap Mode**: Run simulation. Verify:
  * `keep_in` applicants' `simulated_default` values match their `actual_default` values.
  * `swap_in` applicants' `simulated_default` values match their `estimated_pd` values (or stressed variations if stress is active).
* **Standalone Mode**: Run standalone simulation. Verify:
  * Approved applicants with observed defaults retain their observed values.
  * Approved applicants without observed defaults (NaN) get simulated using `estimated_pd`.
