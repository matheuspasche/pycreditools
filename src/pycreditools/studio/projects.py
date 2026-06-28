"""Project (de)serialization: `ProjectBundle` <-> local JSON file.

No `streamlit` import allowed here — see `00-overview.md` §4b.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pycreditools import CreditPolicy

from .models import ColumnRoles, PolicyEntry, ProjectBundle, StudioState

DEFAULT_PROJECTS_DIR = Path.home() / ".pycreditools_studio" / "projects"


def bundle_from_state(
    state: StudioState, project_name: str, *, dataset: dict[str, Any] | None = None
) -> ProjectBundle:
    """Build a serializable `ProjectBundle` snapshot from the live `StudioState`."""
    policies = {
        name: {"policy": entry.policy.to_dict(), "flat_stress_factor": entry.flat_stress_factor}
        for name, entry in state.policies.items()
    }
    rating_recipe = (
        state.rating_result.recipe.to_dict() if state.rating_result is not None else None
    )
    return ProjectBundle(
        project_name=project_name,
        df_name=state.df_name,
        roles=state.roles,
        policies=policies,
        active_policy=state.active_policy,
        rating_recipe=rating_recipe,
        rating_labels=state.rating_labels,
        scores_em_jogo=list(state.scores_em_jogo),
        created_at=datetime.now(timezone.utc).isoformat(),
        dataset=dataset,
    )


def restore_policies(bundle: ProjectBundle) -> dict[str, PolicyEntry]:
    """Reconstruct live `PolicyEntry` objects (with real `CreditPolicy`s) from a bundle."""
    restored: dict[str, PolicyEntry] = {}
    for name, payload in bundle.policies.items():
        policy = CreditPolicy.from_dict(payload["policy"])
        restored[name] = PolicyEntry(
            name=name, policy=policy, flat_stress_factor=payload.get("flat_stress_factor")
        )
    return restored


def to_json_dict(bundle: ProjectBundle) -> dict[str, Any]:
    """Serialize a `ProjectBundle` to the on-disk JSON shape (PRD 02)."""
    return {
        "name": bundle.project_name,
        "created_at": bundle.created_at,
        "dataset": bundle.dataset,
        "roles": asdict(bundle.roles),
        "policies": bundle.policies,
        "active_policy": bundle.active_policy,
        "rating_recipe": bundle.rating_recipe,
        "rating_labels": ({str(k): v for k, v in bundle.rating_labels.items()} or None)
        if bundle.rating_labels
        else None,
        "scores_em_jogo": bundle.scores_em_jogo,
    }


def from_json_dict(data: dict[str, Any]) -> ProjectBundle:
    """Deserialize the on-disk JSON shape back into a `ProjectBundle`."""
    rating_labels = data.get("rating_labels")
    if rating_labels:
        rating_labels = {int(k): v for k, v in rating_labels.items()}
    return ProjectBundle(
        project_name=data["name"],
        df_name=(data.get("dataset") or {}).get("name"),
        roles=ColumnRoles(**data.get("roles", {})),
        policies=data.get("policies", {}),
        active_policy=data.get("active_policy"),
        rating_recipe=data.get("rating_recipe"),
        rating_labels=rating_labels,
        scores_em_jogo=data.get("scores_em_jogo") or [],
        created_at=data.get("created_at"),
        dataset=data.get("dataset"),
    )


def save_project(bundle: ProjectBundle, directory: Path | str | None = None) -> Path:
    """Write `bundle` as `<directory>/<project_name>.json`; returns the written path."""
    target_dir = Path(directory) if directory else DEFAULT_PROJECTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{bundle.project_name}.json"
    payload = json.dumps(to_json_dict(bundle), indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    return path


def list_projects(directory: Path | str | None = None) -> list[str]:
    """List saved project names (without `.json`) in `directory`."""
    target_dir = Path(directory) if directory else DEFAULT_PROJECTS_DIR
    if not target_dir.exists():
        return []
    return sorted(p.stem for p in target_dir.glob("*.json"))


def load_project(name: str, directory: Path | str | None = None) -> ProjectBundle:
    """Load a project by name from `directory`."""
    target_dir = Path(directory) if directory else DEFAULT_PROJECTS_DIR
    path = target_dir / f"{name}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return from_json_dict(data)
