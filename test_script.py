import sys
sys.path.insert(0, "c:/Users/Matheus/Documents/GitHub/pycreditools/src")

from pycreditools import generate_sample_data, CreditPolicy, CutoffStage, run_simulation, SimulationMethod, summarize_results

print("Generating data...")
data = generate_sample_data(n_applicants=5000, seed=42)
print("Data shape:", data.shape)

policy = CreditPolicy(
    applicant_id_col="id",
    score_cols=["old_score", "new_score"],
    current_approval_col="approved",
    actual_default_col="defaulted",
)

policy = policy.add_stage(CutoffStage(name="credit_check", cutoffs={"new_score": 600}))

print("Running simulation...")
res = run_simulation(data, policy, method=SimulationMethod.ANALYTICAL)
print("Simulation complete.")

summary = summarize_results(res)
print(summary)
