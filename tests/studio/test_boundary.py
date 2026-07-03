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


def _has_screening_symbol(source: str) -> bool:
    """Return True if *source* contains any Python identifier referencing screening.

    Uses AST so string literals, comments, and CSS media queries embedded in
    strings cannot produce false positives (issue #46).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        names: list = []
        if isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names] + [
                a.asname for a in node.names if a.asname
            ]
        elif isinstance(node, ast.ImportFrom):
            names = (
                ([node.module] if node.module else [])
                + [a.name for a in node.names]
                + [a.asname for a in node.names if a.asname]
            )
        elif isinstance(node, ast.arg):
            names = [node.arg]
        elif isinstance(node, ast.keyword) and node.arg:
            names = [node.arg]
        if any("screen" in n.lower() for n in names):
            return True
    return False


def test_no_screening_references_remain_in_studio_or_gui():
    """Risk Screening was cut from v2 scope (owner critique 2.6) — see ADR 0001."""
    offenders = []
    for root in (CORE, GUI):
        for py in root.rglob("*.py"):
            if _has_screening_symbol(py.read_text(encoding="utf-8")):
                offenders.append(str(py.relative_to(root.parents[2])))
    assert not offenders, f"Screening references remain: {offenders}"
