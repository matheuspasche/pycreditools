"""
Smoke tests that guard against missing declared dependencies.
These would fail in a clean install if a package is imported by __init__.py
but not declared in [project].dependencies.
"""

import importlib


def test_matplotlib_importable():
    """matplotlib must be importable — it is used unconditionally by visualization.py."""
    importlib.import_module("matplotlib")


def test_seaborn_importable():
    """seaborn must be importable — it is used unconditionally by visualization.py."""
    importlib.import_module("seaborn")


def test_top_level_import_does_not_raise():
    """Importing pycreditools must not raise ModuleNotFoundError (regression for #52)."""
    import pycreditools  # noqa: F401


def test_visualization_symbols_exported():
    """visualization symbols must be accessible from the top-level package."""
    import pycreditools

    for name in ("plot_tradeoffs", "plot_vintage_stability", "plot_crash_test", "plot_funnel"):
        assert hasattr(pycreditools, name), f"pycreditools.{name} missing"


# --- The v0.6 engine namespace stays off the top level until the contraction ---
#
# `src/pycreditools/engine/` is the expand half of a package-level
# expand-contract: the new surface grows beside the old one instead of
# replacing it in place. The separation is load-bearing, not cosmetic.
# `CreditPolicy.filter(self, name, condition)` takes `name` positionally first
# (policy.py:105), so the v0.6 `.filter(col("age") >= 18)` binds its Expression
# to `name` and dies on the missing `condition`. The two spellings collide, and
# only one of them can be reachable as `pct.` while both are alive.
#
# These three tests are the gate. They fail the moment the namespace leaks, so
# a ticket cannot wire it to the top level early by accident.


def test_engine_namespace_exists():
    """The namespace must exist — the leak tests below are vacuous without it."""
    importlib.import_module("pycreditools.engine")


def test_engine_is_not_bound_by_a_plain_top_level_import():
    """`import pycreditools` must not bind `pycreditools.engine`.

    Checked in a clean interpreter on purpose: importing a subpackage anywhere
    sets it as an attribute on its parent, so any other test in this session
    that touches `pycreditools.engine` would make an in-process `hasattr` pass
    for the wrong reason. A subprocess is the only honest reading.
    """
    import subprocess
    import sys

    probe = (
        "import pycreditools, sys; "
        "sys.exit(1 if hasattr(pycreditools, 'engine') else 0)"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert result.returncode == 0, (
        "pycreditools.engine is reachable from the top level. The v0.6 surface must "
        "stay off `pct.` until the contraction — see src/pycreditools/engine/__init__.py."
    )


def test_engine_is_absent_from_dunder_all():
    """`engine` must not be exported, so `from pycreditools import *` cannot reach it."""
    import pycreditools

    assert "engine" not in pycreditools.__all__, (
        "engine leaked into pycreditools.__all__; the v0.6 surface is not public yet."
    )
