import pandas as pd
import numpy as np
from pycreditools import CreditPolicy, run_simulation, print_delta_table, col
from pycreditools.visualization import plot_funnel

# Set random seed for reproducible results
np.random.seed(42)

# 1. Create a richer mock dataset
df = pd.DataFrame({
    "applicant_id": range(1000), # Increase volume to 1000 for nicer visualization
    "score_1": np.random.randint(500, 1000, 1000),
    "score_2": np.random.randint(400, 950, 1000),
    "age": np.random.randint(15, 75, 1000),
    "income": np.random.randint(1000, 15000, 1000),
    "has_bankruptcy": np.random.binomial(1, 0.04, 1000),
    "observed_default": np.random.binomial(1, 0.05, 1000).astype(float),
    "estimated_pd": np.random.uniform(0.01, 0.15, 1000),
    "historical_approval": np.random.binomial(1, 0.7, 1000)
})

# 2. Define Policies with Multiple Sequential Stages
# Champion policy (4 stages)
p_champion = (
    CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="historical_approval",
        actual_default_col="observed_default"
    )
    .filter("Idade Minima", col("age") >= 18)
    .filter("Sem Falencia", col("has_bankruptcy") == 0)
    .cutoff("Score Minimo", {"score_1": 600})
    .filter("Renda Minima", col("income") >= 2000)
)

# Challenger 1 (stricter stages)
p_challenger1 = (
    CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="historical_approval",
        actual_default_col="observed_default"
    )
    .filter("Idade Minima", col("age") >= 21)
    .filter("Sem Falencia", col("has_bankruptcy") == 0)
    .cutoff("Score Minimo", {"score_1": 700})
    .filter("Renda Minima", col("income") >= 3000)
)

# Challenger 2 (even stricter stages)
p_challenger2 = (
    CreditPolicy(
        applicant_id_col="applicant_id",
        score_cols=("score_1",),
        current_approval_col="historical_approval",
        actual_default_col="observed_default",
        estimated_default_col="estimated_pd"
    )
    .filter("Idade Minima", col("age") >= 25)
    .filter("Sem Falencia", col("has_bankruptcy") == 0)
    .cutoff("Score Minimo", {"score_1": 750})
    .filter("Renda Minima", col("income") >= 4000)
)

print("Running simulations...")
res_champ = run_simulation(df, p_champion, method="analytical")
res_chal1 = run_simulation(df, p_challenger1, method="analytical")
res_chal2 = run_simulation(df, p_challenger2, method="analytical")

print("\n--- 1. MULTI-POLICY COMPARISON DELTA TABLE ---")
print_delta_table([res_chal1, res_chal2], res_champ)

print("\n--- 2. FUNNEL PLOT SANKEY GENERATION ---")
fig = plot_funnel(res_champ)
print(f"Successfully generated funnel figure: {type(fig)}")
print("Node labels in Sankey:")
for i, label in enumerate(fig.data[0].node.label):
    clean_label = label.replace("<br>", " ")
    print(f"  Node {i}: {clean_label}")

# Save figure to HTML and open in browser
import os
import webbrowser

html_path = os.path.abspath("scratch/funnel_sankey.html")
fig.write_html(html_path)
print(f"\nSaved interactive multi-stage funnel plot to: {html_path}")

webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")
print("Opened interactive funnel plot in your default browser!")

print("\n--- 3. FUNNEL STAGES CONSOLE TABLE ---")
res_champ.print_funnel_table()
