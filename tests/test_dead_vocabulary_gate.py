"""The denylist is enforced by the suite, not only by an opt-in git hook.

`.pre-commit-config.yaml` runs `scripts/check_dead_vocabulary.py`, but pre-commit
only runs where a developer has installed it, and this repo has no CI that runs
either one. So the same check runs here, where it costs nothing and where anyone
running the suite sees it.

The second test is the one that matters more. pre-commit **skips a hook whose
`files:` pattern matches nothing, and reports it as Passed** — so a pattern that
drifts off the surface it guards stops guarding it, silently, with a green tick.
That is the exact shape of failure `CONTEXT.md` § *The ladder of remedies*
forbids, and prose in a config comment does not prevent it. This test does: the
scope lives in the script, and the hook's pattern has to still match it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PRE_COMMIT = REPO / ".pre-commit-config.yaml"


def _load_checker():
    path = REPO / "scripts" / "check_dead_vocabulary.py"
    spec = importlib.util.spec_from_file_location("check_dead_vocabulary", path)
    assert spec and spec.loader, f"could not load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hook_file_patterns() -> list[str]:
    """Every `files:` pattern in the pre-commit config."""
    text = PRE_COMMIT.read_text(encoding="utf-8")
    return re.findall(r"^\s*files:\s*(\S+)\s*$", text, re.MULTILINE)


def test_the_v06_surface_is_free_of_dead_vocabulary():
    checker = _load_checker()
    paths, _absent = checker.scope_files()
    findings = [f for path in paths for f in checker.check(path)]
    assert not findings, "\n".join(findings)


def test_every_file_in_the_v06_surface_is_covered_by_a_hook_pattern():
    """A file the hook's pattern misses is a file the denylist never sees."""
    checker = _load_checker()
    paths, _absent = checker.scope_files()
    if not paths:
        pytest.skip("the v0.6 surface has no files yet — nothing to cover")

    patterns = [re.compile(p) for p in _hook_file_patterns()]
    assert patterns, f"no `files:` pattern found in {PRE_COMMIT.name}"

    for path in paths:
        relative = path.relative_to(REPO).as_posix()
        assert any(p.search(relative) for p in patterns), (
            f"{relative} is inside the v0.6 surface but matches no `files:` pattern in "
            f"{PRE_COMMIT.name}. pre-commit would skip it and report a pass."
        )


def test_the_script_and_the_hook_declare_the_same_scope():
    """The scope is declared in the script; the config must still agree with it."""
    checker = _load_checker()
    joined = " ".join(_hook_file_patterns())
    for root in checker.SCOPE_ROOTS:
        # Matched with the trailing separator on purpose: a bare substring check
        # accepts `src/pycreditools/engineX/`, which points at nothing and would
        # read as agreement.
        assert f"{root}/" in joined, (
            f"{root!r} is a scope root in check_dead_vocabulary.py but appears in no "
            f"`files:` pattern in {PRE_COMMIT.name}. The two have drifted."
        )
