"""Meta-test: GPU probe must be lazy (not called at module import) in slow test
modules. A module-level `_gpu_available()` call spawns `ffmpeg -hwaccels` on every
pytest collection (even the default run that deselects slow tests).

This guard lives in its own module (no slow pytestmark) so it runs in the default
pytest lane. See tests/test_regression_330.py and tests/test_integration.py.

It catches every *import-time* form of the probe call -- a bare module-level
assignment, a decorator on a top-level function/class (`@pytest.mark.skipif(not
_gpu_available())` -- the original bug shape), a default-arg expression, and a
class-body attribute -- while allowing the lazy form (a call inside a test/function
body, which only runs when the test executes).
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_GUARDED_MODULES = ["test_regression_330.py", "test_integration.py"]


def _calls_gpu_available(node: ast.AST) -> bool:
    """True if `_gpu_available()` is called anywhere within `node`."""
    return any(
        isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Name)
        and sub.func.id == "_gpu_available"
        for sub in ast.walk(node)
    )


def _eager_calls_gpu_available(node: ast.stmt) -> bool:
    """True if `node` evaluates `_gpu_available()` at *import* time.

    Function/method *bodies* are excluded (they run lazily, on call). The eager
    surfaces are: decorators and default args of a def, the bases/decorators and
    class-level statements of a class, and any other top-level statement in full.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        eager = list(node.decorator_list)
        eager += [d for d in node.args.defaults if d is not None]
        eager += [d for d in node.args.kw_defaults if d is not None]
        return any(_calls_gpu_available(part) for part in eager)
    if isinstance(node, ast.ClassDef):
        if any(
            _calls_gpu_available(part) for part in [*node.decorator_list, *node.bases]
        ):
            return True
        # Class-body statements run at import; recurse so method bodies stay excluded.
        return any(_eager_calls_gpu_available(stmt) for stmt in node.body)
    # Any other top-level statement (Assign, Expr, If, With, ...) runs at import.
    return _calls_gpu_available(node)


@pytest.mark.parametrize("module_name", _GUARDED_MODULES)
def test_gpu_probe_is_not_called_at_import(module_name: str) -> None:
    """GPU availability probe must be lazy, not run at collection time."""
    target = pathlib.Path(__file__).parent / module_name
    tree = ast.parse(target.read_text(encoding="utf-8"))
    for node in tree.body:
        if _eager_calls_gpu_available(node):
            raise AssertionError(
                f"_gpu_available() evaluated at import in {module_name} "
                f"(line {node.lineno}); keep it lazy (call inside a test body)"
            )


def test_eager_detection_logic_fires_on_every_import_time_form() -> None:
    """Red verification: the detector FIRES on every import-time form (assign,
    decorator -- the original bug shape -- class-body attr, default arg) and does
    NOT false-positive on the lazy form (call inside a test/method body)."""
    eager_forms = [
        "g = pytest.mark.skipif(not _gpu_available())",  # module-level assign
        "@pytest.mark.skipif(not _gpu_available())\ndef test_x():\n    pass",  # decorator
        "class C:\n    skip = pytest.mark.skipif(not _gpu_available())",  # class-body attr
        "def f(x=_gpu_available()):\n    pass",  # default arg
    ]
    for src in eager_forms:
        node = ast.parse(src).body[0]
        assert _eager_calls_gpu_available(node), f"missed eager form: {src!r}"

    lazy_forms = [
        "def test_y():\n    if not _gpu_available():\n        pass",  # call in fn body
        "class C:\n    def test_z(self):\n        _gpu_available()",  # call in method body
    ]
    for src in lazy_forms:
        node = ast.parse(src).body[0]
        assert not _eager_calls_gpu_available(node), (
            f"false-positive on lazy form: {src!r}"
        )
