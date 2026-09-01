"""Meta-test: real-video callers of ``detect_match_boundaries`` must pass the fps.

#864 removed the pre-#576 fps-filter path. Since then, a call that supplies
neither ``source_fps`` nor ``source_fps_num``/``_den`` raises
``VideoProcessingError`` from ``_resolve_fps_rational`` instead of silently
degrading. Production always supplies one (``probe`` hard-fails on ``fps <= 0``),
so this only bites test callers -- and it bites them as a hard failure.

**Why a guard and not just the fixes.** The #864 sweep fixed three call sites
(``tests/test_scorebar_regression.py`` x2 and ``tests/generate_baselines.py``)
and missed three more, because the misses were all in tests that do not run in
the lane the sweep used:

* ``tests/test_regression_330.py`` skips unless ``ALLAGANEYE_AUDIO_TEST_VIDEO``
  is set, so it never executed (2026-09-01: setting it produced 2 hard failures)
* ``tests/test_integration.py``'s ``gpu_cpu_results`` fixture is behind
  ``slow_gpu``, which a ``-m slow_detect`` gate does not collect
* ``tests/test_l3_phase2_parity.py`` does not raise *today* only because
  ``vtuber=True`` branches into the timeline path ahead of the CPU chunk
  decode; the band-crop degrade path still reaches it

"Run the slow tests and see" cannot find these -- that is exactly the lane that
skipped them. This guard is static, so it sees call sites the runtime never
reaches, and it runs in the default (fast) pytest lane.

## What this guard does not see

* **Calls that pass the kwargs indirectly** (``**detect_kwargs``). The check is
  syntactic: a dict spread carrying the fps reads as "not passed" (false-red,
  which is the safe direction), and a spread carrying nothing reads the same.
* **Non-test callers.** Only ``tests/`` is scanned. ``allaganeye/`` production
  code threads fps through ``split_matches.py``; that contract is covered by
  the detector's own tests, not here.
* **Whether the fps value is correct.** Passing ``source_fps=0.0`` satisfies
  this guard and fails at runtime. The guard fixes the omission class only.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_TESTS_DIR = pathlib.Path(__file__).parent
_FPS_KWARGS = frozenset({"source_fps", "source_fps_num", "source_fps_den"})
_TARGET = "detect_match_boundaries"


def _marker_names(node: ast.AST) -> set[str]:
    """Decorator names on ``node``, flattened (``pytest.mark.slow_gpu`` -> parts)."""
    names: set[str] = set()
    for decorator in getattr(node, "decorator_list", []):
        current = decorator.func if isinstance(decorator, ast.Call) else decorator
        while isinstance(current, ast.Attribute):
            names.add(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            names.add(current.id)
    return names


def _module_is_slow(tree: ast.Module) -> bool:
    """True if the module sets a ``pytestmark`` mentioning a slow marker."""
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            return "slow" in ast.dump(node.value)
    return False


def _slow_calls_without_fps(path: pathlib.Path) -> list[int]:
    """Line numbers of slow-marked ``detect_match_boundaries`` calls lacking fps."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_slow = _module_is_slow(tree)
    offenders: list[int] = []
    scope: list[ast.AST] = []

    class Visitor(ast.NodeVisitor):
        def _enter(self, node: ast.AST) -> None:
            scope.append(node)
            self.generic_visit(node)
            scope.pop()

        visit_FunctionDef = _enter
        visit_AsyncFunctionDef = _enter
        visit_ClassDef = _enter

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name == _TARGET:
                in_slow_scope = module_slow or any(
                    any(m.startswith("slow") for m in _marker_names(s)) for s in scope
                )
                passed = {kw.arg for kw in node.keywords if kw.arg}
                if in_slow_scope and not (passed & _FPS_KWARGS):
                    offenders.append(node.lineno)
            self.generic_visit(node)

    Visitor().visit(tree)
    return offenders


def _scan_all() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(_TESTS_DIR.rglob("*.py")):
        lines = _slow_calls_without_fps(path)
        if lines:
            found[path.name] = lines
    return found


def test_slow_detector_calls_pass_fps() -> None:
    """Every slow-marked ``detect_match_boundaries`` call must supply the fps."""
    offenders = _scan_all()
    assert offenders == {}, (
        "slow-marked detect_match_boundaries call(s) do not pass source_fps / "
        f"source_fps_num / source_fps_den: {offenders}. Since #864 removed the "
        "fps-filter fallback these raise VideoProcessingError when executed. "
        "Mirror the production detect_kwargs (allaganeye/commands/split_matches.py)."
    )


def test_guard_finds_a_violation_when_one_is_injected(tmp_path: pathlib.Path) -> None:
    """The scan must still flag an offender (it is not vacuously empty).

    Without this, deleting the marker detection or the kwarg set would leave
    `test_slow_detector_calls_pass_fps` green while checking nothing.
    """
    offender = tmp_path / "test_injected_slow.py"
    offender.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.slow_detect\n"
        "def test_x():\n"
        "    detect_match_boundaries(video, duration_hint=1.0)\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(offender) == [4]


def test_guard_accepts_the_fixed_form(tmp_path: pathlib.Path) -> None:
    """A slow call that passes the fps must not be flagged (no false-red)."""
    compliant = tmp_path / "test_injected_ok.py"
    compliant.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.slow_detect\n"
        "def test_x():\n"
        "    detect_match_boundaries(\n"
        "        video, duration_hint=1.0, source_fps=60.0,\n"
        "        source_fps_num=60, source_fps_den=1,\n"
        "    )\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(compliant) == []


def test_guard_ignores_non_slow_callers(tmp_path: pathlib.Path) -> None:
    """Unit tests that mock the decode path are out of scope (they pass no fps).

    Scoping to slow markers is deliberate: ``tests/test_detector.py`` has many
    mocked callers without fps and they are correct as written.
    """
    unit = tmp_path / "test_injected_unit.py"
    unit.write_text(
        "def test_x():\n    detect_match_boundaries(video, duration_hint=1.0)\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(unit) == []


@pytest.mark.parametrize(
    "decorator",
    ["@pytest.mark.slow", "@pytest.mark.slow_detect", "@pytest.mark.slow_gpu"],
)
def test_guard_covers_each_slow_marker(decorator: str, tmp_path: pathlib.Path) -> None:
    """Function-level markers count, not just module ``pytestmark``.

    ``tests/test_integration.py``'s miss was behind a class-level ``slow_gpu``,
    so a guard that only read ``pytestmark`` would have missed it too.
    """
    path = tmp_path / f"test_injected_{decorator.rsplit('.', 1)[-1]}.py"
    path.write_text(
        "import pytest\n"
        f"{decorator}\n"
        "def test_x():\n"
        "    detect_match_boundaries(video, duration_hint=1.0)\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(path) == [4]
