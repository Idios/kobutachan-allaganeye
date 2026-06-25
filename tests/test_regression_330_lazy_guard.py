"""Meta-test: regression_330 GPU probe must be lazy (not called at import).

This guard lives in a separate module (no slow pytestmark) so it runs in the
default pytest lane without requiring slow test infrastructure.

See: tests/test_regression_330.py for the tested module.
"""

from __future__ import annotations


def test_gpu_probe_is_not_called_at_import() -> None:
    """Regression: GPU availability probe must be lazy, not run at collection."""
    import ast
    import pathlib

    src = pathlib.Path(__file__).parent.joinpath("test_regression_330.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        # Skip function/class bodies -- those run at call time, not import.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "_gpu_available"
            ):
                raise AssertionError(
                    "_gpu_available() called at module level; keep it lazy"
                )
