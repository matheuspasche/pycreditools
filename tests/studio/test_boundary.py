import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parents[2] / "src" / "pycreditools" / "studio"
GUI = pathlib.Path(__file__).resolve().parents[2] / "src" / "pycreditools" / "gui"


def test_core_has_no_streamlit_import():
    offenders = []
    for py in CORE.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                a.name.split(".")[0] == "streamlit" for a in node.names
            ):
                offenders.append(py.name)
            if isinstance(node, ast.ImportFrom) and (
                (node.module or "").split(".")[0] == "streamlit"
            ):
                offenders.append(py.name)
    assert not offenders, f"streamlit imported in studio/ core: {offenders}"


def test_no_screening_references_remain_in_studio_or_gui():
    """Risk Screening was cut from v2 scope (owner critique 2.6) — see ADR 0001."""
    offenders = []
    for root in (CORE, GUI):
        for py in root.rglob("*.py"):
            if "screen" in py.read_text(encoding="utf-8").lower():
                offenders.append(str(py.relative_to(root.parents[2])))
    assert not offenders, f"Screening references remain: {offenders}"
