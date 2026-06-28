"""Pure dataclasses shared by the studio core and the Streamlit skin.

No `streamlit` import allowed here — see `00-overview.md` §4b.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

    from pycreditools import CreditPolicy, CreditSimResults, RiskGroupResult


@dataclass
class ColumnRoles:
    """Maps dataset columns to the semantic roles the studio needs."""

    applicant_id_col: str | None = None
    score_cols: list[str] = field(default_factory=list)
    primary_score_col: str | None = None
    current_approval_col: str | None = None
    actual_default_col: str | None = None
    current_hired_col: str | None = None
    time_col: str | None = None
    segment_col: str | None = None
    estimated_default_col: str | None = None
    oot_date: str | None = None
    vigente_score: str | None = None


@dataclass
class TierDetection:
    """The auto-detected comparison tier (ADR 0002) plus its pt-BR rationale."""

    tier: str
    rationale: str


@dataclass
class PolicyEntry:
    """A named, built `CreditPolicy` plus its mirrored flat stress factor."""

    name: str
    policy: CreditPolicy
    flat_stress_factor: float | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ProjectBundle:
    """Serializable snapshot of a studio project (no live engine objects)."""

    project_name: str
    df_name: str | None = None
    roles: ColumnRoles = field(default_factory=ColumnRoles)
    policies: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_policy: str | None = None
    rating_recipe: dict[str, Any] | None = None
    rating_labels: dict[int, str] | None = None
    created_at: str | None = None
    dataset: dict[str, Any] | None = None


@dataclass
class StudioState:
    """The single object stored under `st.session_state["studio"]`."""

    df_name: str | None = None
    df: pd.DataFrame | None = None
    df_hash: str | None = None
    roles: ColumnRoles = field(default_factory=ColumnRoles)
    policies: dict[str, PolicyEntry] = field(default_factory=dict)
    active_policy: str | None = None
    rating_result: RiskGroupResult | None = None
    rating_labels: dict[int, str] | None = None
    last_sim: CreditSimResults | None = None
    legacy_sim: CreditSimResults | None = None
    scores_em_jogo: list[str] = field(default_factory=list)
