"""Parity tests for the AST-based screening-symbol scanner (issue #46).

Specifies the expected behaviour of ``_has_screening_symbol``:
  - catches real screening identifiers (class names, variable names, …)
  - ignores innocuous tokens such as "screenshot" inside string literals,
    comments, or CSS media queries embedded in strings.
"""
import ast


def _has_screening_symbol(source: str) -> bool:
    """Return True if *source* contains any Python identifier referencing screening."""
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


# --- true-positive cases: real screening identifiers ---


def test_catches_ScreeningResult_classdef():
    assert _has_screening_symbol("class ScreeningResult: pass")


def test_catches_screen_segments_variable():
    assert _has_screening_symbol("screen_segments = []")


def test_catches_screening_function_def():
    assert _has_screening_symbol("def run_screening(): pass")


def test_catches_screening_attribute_access():
    assert _has_screening_symbol("score = obj.screening_score")


def test_catches_bare_screening_import():
    assert _has_screening_symbol("import screening")


def test_catches_from_import_ScreeningResult():
    assert _has_screening_symbol("from models import ScreeningResult")


def test_catches_screening_argument():
    assert _has_screening_symbol("def f(screen_segments): pass")


def test_catches_screening_kwarg_at_call_site():
    assert _has_screening_symbol("f(screening_result=x)")


# --- false-positive cases: innocuous tokens ---


def test_ignores_screenshot_in_string_literal():
    assert not _has_screening_symbol('x = "screenshot of the app"')


def test_ignores_screen_only_in_comment():
    assert not _has_screening_symbol("# screenshot\nx = 1")


def test_ignores_css_media_screen_in_string():
    assert not _has_screening_symbol('css = "@media screen { color: red; }"')


def test_ignores_docstring_with_screenshot():
    code = '"""Take a screenshot for debugging."""\nx = 1'
    assert not _has_screening_symbol(code)


def test_ignores_clean_file():
    assert not _has_screening_symbol("x = 1\ny = x + 2\nz = x * y")
