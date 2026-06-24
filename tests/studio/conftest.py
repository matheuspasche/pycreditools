import pytest

from pycreditools import generate_sample_data
from pycreditools.studio.models import ColumnRoles, StudioState


@pytest.fixture(scope="session")
def sample_df():
    return generate_sample_data(5000, seed=42)


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
