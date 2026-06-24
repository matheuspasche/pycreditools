import ast
import pathlib

CORE = pathlib.Path(__file__).resolve().parents[2] / "src" / "pycreditools" / "studio"


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
