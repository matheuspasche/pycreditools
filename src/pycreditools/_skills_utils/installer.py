"""Copy bundled skill packs into a Claude Code skills directory.

Never runs automatically on `pip install` — invoked explicitly via the
`pasche-utils` CLI so no code executes during package installation.

The skill files have a single home in the repo: `.claude/skills/`, the only
directory Claude Code discovers. The wheel picks them up via a
`force-include` in `pyproject.toml` that maps that directory to
`pycreditools/_skills_utils/skills/mattpocock/`, so an installed package
carries the same tree under `SKILLS_ROOT`. Running from a source checkout
there is no such tree, so `_skills_root()` falls back to the repo's
`.claude/skills/`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parent
SKILLS_ROOT = PACKAGE_ROOT / "skills"
DEV_PACK = "mattpocock"
# src/pycreditools/_skills_utils/installer.py -> repo root
DEV_SKILLS_DIR = PACKAGE_ROOT.parents[2] / ".claude" / "skills"


def _pack_dir(pack: str) -> Path:
    """Locate `pack`, falling back to the repo checkout when not installed."""
    packed = SKILLS_ROOT / pack
    if packed.is_dir():
        return packed
    if pack == DEV_PACK and DEV_SKILLS_DIR.is_dir():
        return DEV_SKILLS_DIR
    raise FileNotFoundError(f"unknown skill pack: {pack!r} (known: {list_packs()})")


def list_packs() -> list[str]:
    if SKILLS_ROOT.is_dir():
        return sorted(p.name for p in SKILLS_ROOT.iterdir() if p.is_dir())
    return [DEV_PACK] if DEV_SKILLS_DIR.is_dir() else []


def _skill_dirs(pack: str) -> list[Path]:
    return sorted(
        d for d in _pack_dir(pack).iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    )


def list_skills(pack: str) -> list[str]:
    return [d.name for d in _skill_dirs(pack)]


def install(pack: str, target: Path, overwrite: bool = False) -> list[str]:
    """Copy every SKILL.md-bearing directory in `pack` into target/<skill-name>/."""
    skill_dirs = _skill_dirs(pack)
    target = target.resolve()
    if target == _pack_dir(pack).resolve():
        raise ValueError(f"refusing to install {pack!r} over its own source: {target}")

    target.mkdir(parents=True, exist_ok=True)
    installed = []
    for skill_dir in skill_dirs:
        dest = target / skill_dir.name
        if dest.exists():
            if not overwrite:
                installed.append(f"{skill_dir.name} (skipped, exists)")
                continue
            shutil.rmtree(dest)
        shutil.copytree(skill_dir, dest)
        installed.append(skill_dir.name)

    license_file = _pack_dir(pack) / "LICENSE.mattpocock"
    if license_file.is_file():
        shutil.copy2(license_file, target / license_file.name)
    return installed
