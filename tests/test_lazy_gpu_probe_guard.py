"""Meta-test: GPU probe must be lazy (not called at module import) in slow test
modules. A module-level `_gpu_available()` call spawns `ffmpeg -hwaccels` on every
pytest collection (even the default run that deselects slow tests).

This guard lives in its own module (no slow pytestmark) so it runs in the default
pytest lane. See tests/test_regression_330.py and tests/test_integration.py.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_GUARDED_MODULES = ["test_regression_330.py", "test_integration.py"]


@pytest.mark.parametrize("module_name", _GUARDED_MODULES)
def test_gpu_probe_is_not_called_at_import(module_name: str) -> None:
    """GPU availability probe must be lazy, not run at collection time."""
    target = pathlib.Path(__file__).parent / module_name
    tree = ast.parse(target.read_text(encoding="utf-8"))
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
                    f"_gpu_available() called at module level in {module_name}; "
                    "keep it lazy"
                )
