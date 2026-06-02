import pandas as pd
import numpy as np

def generate_sample_data(
    n_applicants: int = 20_000,
    correlation: float = 0.7,
    base_default_rate: float = 0.10,
    base_approval_rate: float = 0.5,
    seed: int | None = None,
) -> pd.DataFrame:
    """Generate a realistic synthetic credit dataset.
    
    Args:
        n_applicants: Number of rows to generate.
        correlation: Correlation between old score and new score.
        base_default_rate: Expected default rate.
        base_approval_rate: Expected approval rate on old score.
        seed: Random seed for reproducibility.
        
    Returns:
        DataFrame with synthetic applicants.
    """
    if seed is not None:
        np.random.seed(seed)
        
    # Latent variable model
    # true risk
    z = np.random.normal(0, 1, n_applicants)
    
    # Noise for scores
    e1 = np.random.normal(0, 1, n_applicants)
    e2 = np.random.normal(0, 1, n_applicants)
    
    a = np.sqrt(correlation)
    b = np.sqrt(1 - correlation)
    
    latent_old = a * z + b * e1
    latent_new = a * z + b * e2
    
    # Map to 0-1000 using normal CDF approximation
    # 1.0 / (1.0 + exp(-1.702 * x)) is highly accurate (error < 0.01)
    def norm_cdf(x):
        return 1.0 / (1.0 + np.exp(-1.702 * x))
    
    old_score = np.round(norm_cdf(-latent_old) * 1000).astype(int)
    new_score = np.round(norm_cdf(-latent_new) * 1000).astype(int)
    
    # Default probability
    # logit(pd) = intercept + coef * z
    # we want higher z = higher risk (higher pd)
    coef = 1.5
    
    # numerical solve for intercept to hit base_default_rate approximately
    # For a standard normal z, E[1 / (1 + exp(-(int + coef*z)))] = base_pd
    # A rough approximation:
    logit_base = np.log(base_default_rate / (1 - base_default_rate))
    # the variance of coef*z increases the mean of the logistic, so we adjust
    intercept = logit_base - (coef**2) * 0.1 # rough heuristic
    
    pd_true = 1 / (1 + np.exp(-(intercept + coef * z)))
    
    # Old approval policy (cutoff to hit base_approval_rate)
    cutoff = np.quantile(old_score, 1 - base_approval_rate)
    approved = (old_score >= cutoff).astype(int)
    
    # Default flag
    defaulted = np.zeros(n_applicants)
    rand_draws = np.random.random(n_applicants)
    
    defaulted[approved == 1] = (rand_draws[approved == 1] < pd_true[approved == 1]).astype(int)
    defaulted[approved == 0] = np.nan
    
    # Demographics
    age = np.random.randint(18, 71, n_applicants)
    bureau_derogatory = np.random.poisson(0.5, n_applicants)
    
    # Vintages
    months = [f"2023-{m:02d}" for m in range(1, 13)]
    vintage = np.random.choice(months, n_applicants)
    
    # Conversion rate
    conversion_rate = np.clip(np.random.normal(0.6, 0.1, n_applicants), 0, 1)
    
    df = pd.DataFrame({
        "id": [f"APP{i:06d}" for i in range(1, n_applicants + 1)],
        "old_score": old_score,
        "new_score": new_score,
        "approved": approved,
        "defaulted": defaulted,
        "true_pd": pd_true,
        "age": age,
        "bureau_derogatory": bureau_derogatory,
        "vintage": vintage,
        "conversion_rate": conversion_rate,
        "hired": approved, # simplified
    })
    
    return df
