import pytest

from pycreditools import generate_sample_data
from pycreditools.studio.analyses import fit_groups, label_ratings_by_pd
from pycreditools.studio.data import population_filter
from pycreditools.studio.detection import detect_roles
from pycreditools.studio.models import ColumnRoles, PolicyEntry, StudioState
from pycreditools.studio.policy_builder import build_policy, v14_quickfill_rows


@pytest.fixture(scope="session")
def sample_df():
    return generate_sample_data(5000, seed=42)


@pytest.fixture(scope="session")
def roles(sample_df):
    """Auto-detected `ColumnRoles` on the sample base (PRD 02)."""
    return detect_roles(sample_df)


@pytest.fixture
def studio_state(sample_df):
    """Basic state: dataset loaded, roles empty. PRD 02 fills roles; PRD 04/08 extend."""
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=ColumnRoles(),
        policies={},
        active_policy=None,
        rating_result=None,
        rating_labels=None,
        screening_result=None,
        last_sim=None,
        legacy_sim=None,
    )


@pytest.fixture
def studio_state_with_roles(sample_df, roles):
    """`StudioState` with auto-detected roles filled in (PRD 02)."""
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={},
        active_policy=None,
        rating_result=None,
        rating_labels=None,
        screening_result=None,
        last_sim=None,
        legacy_sim=None,
    )


@pytest.fixture
def studio_state_with_policy(sample_df, roles):
    """`StudioState` with a v14 hard-filters `CreditPolicy` as the active policy (PRD 04)."""
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows)
    entry = PolicyEntry(name="v14", policy=policy, rows=rows)
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={"v14": entry},
        active_policy="v14",
        rating_result=None,
        rating_labels=None,
        screening_result=None,
        last_sim=None,
        legacy_sim=None,
    )


@pytest.fixture(scope="session")
def rating_result(sample_df, roles):
    """A fitted `RiskGroupResult` on `score_5` over the approved/observed-target population."""
    subset = population_filter(sample_df, roles, "Aprovados").dropna(
        subset=[roles.actual_default_col]
    )
    return fit_groups(
        subset,
        [roles.primary_score_col],
        roles.actual_default_col,
        bins=30,
        max_groups=5,
        min_vol_ratio=0.01,
    )


@pytest.fixture(scope="session")
def rating_labels(rating_result, roles):
    return label_ratings_by_pd(rating_result, roles.actual_default_col)


@pytest.fixture
def studio_state_with_rating(sample_df, roles, rating_result, rating_labels):
    """`StudioState` with a fitted `RiskGroupResult` + A..E labels active (PRD 08)."""
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={},
        active_policy=None,
        rating_result=rating_result,
        rating_labels=rating_labels,
        screening_result=None,
        last_sim=None,
        legacy_sim=None,
    )


@pytest.fixture
def studio_state_with_deployment(sample_df, roles, rating_result, rating_labels):
    """`StudioState` with an active policy AND a fitted rating attached (PRD 11)."""
    rows = v14_quickfill_rows(sample_df.columns)
    policy = build_policy(roles, rows, rating_recipe=rating_result.recipe)
    entry = PolicyEntry(name="v14", policy=policy, rows=rows)
    return StudioState(
        df_name="sample",
        df=sample_df,
        df_hash="sample-5000-42",
        roles=roles,
        policies={"v14": entry},
        active_policy="v14",
        rating_result=rating_result,
        rating_labels=rating_labels,
        screening_result=None,
        last_sim=None,
        legacy_sim=None,
    )
