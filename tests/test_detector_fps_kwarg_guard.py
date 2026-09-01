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
_REAL_VIDEO_ENV = ("ALLAGANEYE_SAMPLE_VIDEO_DIR", "ALLAGANEYE_AUDIO_TEST_VIDEO")


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


def _module_uses_real_video(tree: ast.Module, source: str) -> bool:
    """True if the module drives the detector over a real recording.

    Two signals, either sufficient:

    1. **any slow marker** (module ``pytestmark``, or a function/class decorator)
    2. **a real-video env var** -- the module resolves its input from
       ``ALLAGANEYE_SAMPLE_VIDEO_DIR`` / ``ALLAGANEYE_AUDIO_TEST_VIDEO``

    **Module granularity, deliberately.** The obvious rule -- "the call is
    lexically inside a slow-marked function or class" -- has a hole the suite
    already contains: ``tests/test_scorebar_regression.py`` puts its
    ``detect_match_boundaries`` calls in module-level *fixtures*, outside the
    slow-marked classes that consume them. A lexical rule leaves the very files
    #864 fixed unguarded (Codex adversarial-review, 2026-09-01).

    Signal 2 exists because ``tests/generate_baselines.py`` -- also fixed by
    #864 -- is a plain helper module with no markers at all, so signal 1 alone
    would not reach it.

    Widening does not cost false-reds. Measured 2026-09-01 over every module
    that calls the detector: in scope 5 (``test_integration`` /
    ``test_l3_phase2_parity`` / ``test_regression_330`` /
    ``test_scorebar_regression`` / ``generate_baselines``), out of scope 3
    (``test_detector`` 39 calls / ``test_gpu_detector`` 1 / ``test_split_matches``
    2) -- and those three mock the decode path, so passing no fps is correct
    there.
    """
    if any(env in source for env in _REAL_VIDEO_ENV):
        return True
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            if "slow" in ast.dump(node.value):
                return True
    return any(
        any(m.startswith("slow") for m in _marker_names(node))
        for node in ast.walk(tree)
    )


def _target_bindings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Local names that reach the detector: (function aliases, module aliases).

    Resolving imports matters because the suite already uses an aliased form
    (``tests/test_l3_phase2_parity.py`` calls ``det.detect_match_boundaries``),
    so ``from ... import detect_match_boundaries as dmb`` is not an exotic style
    here -- and a name-only matcher misses it entirely (Codex adversarial-review
    round 2, 2026-09-01: measured as an empty result on an injected alias).
    """
    func_names: set[str] = set()
    module_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _TARGET:
                    func_names.add(alias.asname or alias.name)
                elif alias.name == "detector":
                    module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(".detector") or alias.name == "detector":
                    module_names.add(alias.asname or alias.name.split(".")[-1])
    return func_names, module_names


def _is_target_call(node: ast.Call, funcs: set[str], modules: set[str]) -> bool:
    """True if ``node`` calls the detector, directly or through an alias."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == _TARGET or func.id in funcs
    if isinstance(func, ast.Attribute):
        # `det.detect_match_boundaries(...)` -- accept the attribute name on any
        # receiver (a module alias we failed to resolve still reads correctly),
        # and also `<module alias>.<anything>` is not enough on its own.
        if func.attr == _TARGET:
            return True
        return func.attr in funcs and isinstance(func.value, ast.Name)
    return False


def _passes_fps(node: ast.Call) -> bool:
    """True if the call supplies a frame rate the detector can actually resolve.

    ``_resolve_fps_rational`` needs ``source_fps``, or **both** halves of the
    rational pair. Accepting any one of the three would green-light
    ``source_fps_num=`` alone, which still raises at runtime.
    """
    passed = {kw.arg for kw in node.keywords if kw.arg}
    return "source_fps" in passed or {"source_fps_num", "source_fps_den"} <= passed


def _slow_calls_without_fps(path: pathlib.Path) -> list[int]:
    """Line numbers of ``detect_match_boundaries`` calls lacking a resolvable fps.

    Only real-video modules are inspected (see ``_module_uses_real_video``).
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    if not _module_uses_real_video(tree, source):
        return []
    funcs, modules = _target_bindings(tree)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_target_call(node, funcs, modules)
        and not _passes_fps(node)
    )


def _target_call_count(path: pathlib.Path) -> int:
    """AST-recognized detector calls in ``path`` (0 if the module is out of scope).

    The anti-vacuity pin uses this rather than a substring search: an
    ``import ... as dmb`` line contains the target name while the module may
    contain no recognized call at all, which would let the pin vouch for a file
    the scanner never actually inspects.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    if not _module_uses_real_video(tree, source):
        return 0
    funcs, modules = _target_bindings(tree)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_target_call(node, funcs, modules)
    )


def _scan_all(root: pathlib.Path | None = None) -> dict[str, list[int]]:
    """Offenders under ``root`` (default: this tests directory), keyed by filename."""
    base = root if root is not None else _TESTS_DIR
    found: dict[str, list[int]] = {}
    for path in sorted(base.rglob("*.py")):
        lines = _slow_calls_without_fps(path)
        if lines:
            found[path.name] = lines
    return found


def test_slow_detector_calls_pass_fps() -> None:
    """Every real-video ``detect_match_boundaries`` call must supply the fps."""
    offenders = _scan_all()
    assert offenders == {}, (
        "real-video detect_match_boundaries call(s) do not pass source_fps / "
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


@pytest.mark.parametrize(
    ("import_line", "call"),
    [
        (
            "from allaganeye.video.detector import detect_match_boundaries as dmb",
            "dmb(video)",
        ),
        (
            "from allaganeye.video import detector as det",
            "det.detect_match_boundaries(video)",
        ),
        (
            "import allaganeye.video.detector as d",
            "d.detect_match_boundaries(video)",
        ),
    ],
)
def test_guard_follows_import_aliases(
    import_line: str, call: str, tmp_path: pathlib.Path
) -> None:
    """An alias must not be an escape hatch.

    Measured 2026-09-01 on the name-only matcher: the ``as dmb`` form returned
    an empty offender list while the module still contained an unguarded call.
    ``tests/test_l3_phase2_parity.py`` already calls through a module alias, so
    this shape is in the suite, not hypothetical.
    """
    aliased = tmp_path / "test_injected_alias.py"
    aliased.write_text(
        "import pytest\n"
        f"{import_line}\n"
        "pytestmark = pytest.mark.slow_detect\n"
        "def test_x():\n"
        f"    {call}\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(aliased) == [5]


def test_scan_discovers_files_recursively(tmp_path: pathlib.Path) -> None:
    """``_scan_all`` must actually walk the tree, not just return ``{}``.

    The per-file check above can be perfect while discovery is broken -- a bad
    glob, a wrong root, or an exception swallowed per file would leave
    `test_slow_detector_calls_pass_fps` green having read nothing.
    """
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    (nested / "test_injected_nested.py").write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.slow\n"
        "def test_x():\n"
        "    detect_match_boundaries(video)\n",
        encoding="utf-8",
    )
    assert _scan_all(tmp_path) == {"test_injected_nested.py": [4]}


def test_real_scan_actually_reads_the_known_call_sites() -> None:
    """The real tests directory must contain the call sites this guard exists for.

    Pins the scan against a silently empty corpus: if these modules were renamed
    or the detector call was refactored away, the guard would keep passing while
    covering nothing. Assert the population is non-empty and compliant, rather
    than only that the offender set is empty.

    Membership is decided by **AST-recognized call count**, not by a substring
    search for the target name. A bare ``import ... as dmb`` line contains the
    name, so a substring pin would vouch for a module in which the scanner
    recognizes nothing (Codex adversarial-review round 2).
    """
    covered = {
        path.name: _slow_calls_without_fps(path)
        for path in sorted(_TESTS_DIR.rglob("*.py"))
        if _target_call_count(path) > 0
    }
    for name in (
        "test_regression_330.py",
        "test_integration.py",
        "test_l3_phase2_parity.py",
        "test_scorebar_regression.py",
        # marker を 1 つも持たない helper。env var signal でしか届かないので、
        # signal 2 を消すと静かに射程外へ落ちる (#864 が直した 3 件の 1 つ)。
        "generate_baselines.py",
    ):
        assert name in covered, (
            f"{name} is no longer in scope of this guard "
            f"(slow marker or detector call gone?). In scope: {sorted(covered)}"
        )
        assert covered[name] == [], f"{name} has offending calls: {covered[name]}"


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


def test_guard_rejects_a_half_rational_pair(tmp_path: pathlib.Path) -> None:
    """``source_fps_num`` without ``source_fps_den`` still raises at runtime.

    ``_resolve_fps_rational`` requires both halves (or the float). A predicate
    that accepts "any one of the three" would pass this and fail on the machine.
    """
    half = tmp_path / "test_injected_half.py"
    half.write_text(
        "import pytest\n"
        "pytestmark = pytest.mark.slow_detect\n"
        "def test_x():\n"
        "    detect_match_boundaries(video, source_fps_num=60)\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(half) == [4]


def test_guard_covers_fixtures_outside_the_slow_test_bodies(
    tmp_path: pathlib.Path,
) -> None:
    """A fixture that calls the detector counts, even outside a slow-marked body.

    This is the shape ``tests/test_scorebar_regression.py`` uses: the call lives
    in a module-level fixture and only the consuming classes carry the marker.
    A lexical "inside a slow scope" rule misses it -- which is how the #864 sweep
    could have regressed unnoticed in the very files it fixed.
    """
    fixture_shaped = tmp_path / "test_injected_fixture.py"
    fixture_shaped.write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def detection(meta):\n"
        "    return detect_match_boundaries(video, duration_hint=meta['duration'])\n"
        "@pytest.mark.slow_detect\n"
        "class TestThing:\n"
        "    def test_x(self, detection):\n"
        "        assert detection\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(fixture_shaped) == [4]


def test_guard_ignores_modules_with_no_slow_marker(tmp_path: pathlib.Path) -> None:
    """Module granularity must not spill into fully-mocked unit modules.

    Measured 2026-09-01: ``test_detector.py`` / ``test_gpu_detector.py`` /
    ``test_split_matches.py`` carry zero slow markers, so widening the rule to
    the module does not make their unmocked-fps callers red.
    """
    unit_module = tmp_path / "test_injected_unit_module.py"
    unit_module.write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def detection():\n"
        "    return detect_match_boundaries(video)\n"
        "def test_x(detection):\n"
        "    assert detection\n",
        encoding="utf-8",
    )
    assert _slow_calls_without_fps(unit_module) == []


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
