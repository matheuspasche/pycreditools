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
