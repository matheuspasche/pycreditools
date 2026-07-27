"""Copy bundled skill packs into a Claude Code skills directory.

Never runs automatically on `pip install` — invoked explicitly via the
`matt-utils` CLI so no code executes during package installation.
"""

from __future__ import annotations

import shutil
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent
SKILLS_ROOT = PACKAGE_ROOT / "skills"


def list_packs() -> list[str]:
    return sorted(p.name for p in SKILLS_ROOT.iterdir() if p.is_dir())


def list_skills(pack: str) -> list[str]:
    pack_dir = SKILLS_ROOT / pack
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"unknown skill pack: {pack!r} (known: {list_packs()})")
    skills = []
    for category_dir in pack_dir.iterdir():
        if not category_dir.is_dir():
            continue
        for skill_dir in category_dir.iterdir():
            if (skill_dir / "SKILL.md").exists():
                skills.append(f"{category_dir.name}/{skill_dir.name}")
    return sorted(skills)


def install(pack: str, target: Path, overwrite: bool = False) -> list[str]:
    """Copy every SKILL.md-bearing directory in `pack` into target/<skill-name>/."""
    pack_dir = SKILLS_ROOT / pack
    if not pack_dir.is_dir():
        raise FileNotFoundError(f"unknown skill pack: {pack!r} (known: {list_packs()})")

    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for category_dir in pack_dir.iterdir():
        if not category_dir.is_dir():
            continue
        for skill_dir in category_dir.iterdir():
            if not (skill_dir / "SKILL.md").exists():
                continue
            dest = target / skill_dir.name
            if dest.exists():
                if not overwrite:
                    installed.append(f"{skill_dir.name} (skipped, exists)")
                    continue
                shutil.rmtree(dest)
            shutil.copytree(skill_dir, dest)
            installed.append(skill_dir.name)
    return installed
