"""#658 -- forward-looking AST guard: ``subprocess.run(text=True)`` must set encoding.

``tests/test_subprocess_encoding.py`` (#656 / PR #657) pins the **four call sites that
existed at the time** by asserting their kwargs through mocks. That form cannot catch a
*new* call site added later without ``encoding=``, which is exactly the regression #656
was about: on Windows the OS default encoding (cp932) cannot decode ffmpeg's UTF-8
stderr, so a Japanese path raises ``UnicodeDecodeError``.

This module takes the ``tests/test_ascii_guard.py`` approach instead: walk the AST of
every production module and fail on any ``subprocess.run`` / ``subprocess.Popen`` that
decodes to ``str`` without saying which codec to use.

Scope note: only text-mode calls are checked. Binary calls (no ``text``/``universal_
newlines``, or an explicit ``text=False``) hand back ``bytes`` and decode explicitly at
the use site, so they are not affected by the OS default encoding.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "allaganeye"

# Calls that hand back ``str`` rather than ``bytes``.
_TEXT_KWARGS = ("text", "universal_newlines", "encoding")

# The subprocess entry points that spawn a process and can decode its streams.
_SPAWN_NAMES = frozenset({"run", "Popen", "check_output", "call", "check_call"})


def _subprocess_bindings(tree: ast.AST) -> tuple[set[str], dict[str, str]]:
    """Resolve which names in this module actually refer to ``subprocess``.

    Returns ``(module_aliases, direct_names)``:

    * ``module_aliases`` -- names bound to the module itself
      (``import subprocess`` / ``import subprocess as sp``)
    * ``direct_names`` -- local name -> spawn name
      (``from subprocess import run`` / ``... import run as r``)

    Resolving the binding rather than matching any ``X.run(text=True)`` keeps the
    guard from flagging unrelated libraries, while still following aliases -- an
    alias is precisely how a future call site would slip past a scan that only
    looked for the literal ``subprocess.run``. ``ast.walk`` is used so lazily
    imported bindings inside function bodies (common in this codebase) count too.
    """
    module_aliases: set[str] = set()
    direct_names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module != "subprocess":
                continue
            for alias in node.names:
                if alias.name in _SPAWN_NAMES:
                    direct_names[alias.asname or alias.name] = alias.name

    # Assignment aliases: ``run = subprocess.run`` / ``_spawn = sp.Popen``.
    # Without this, rebinding the callable is a one-line way to walk past the
    # scan (Codex adversarial-review). Two passes so an alias assigned before
    # its import statement (module-level order is irrelevant to ast.walk) is
    # still resolved.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        spawn: str | None = None
        if (
            isinstance(value, ast.Attribute)
            and value.attr in _SPAWN_NAMES
            and isinstance(value.value, ast.Name)
            and value.value.id in module_aliases
        ):
            spawn = value.attr
        elif isinstance(value, ast.Name) and value.id in direct_names:
            spawn = direct_names[value.id]
        if spawn is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                direct_names[target.id] = spawn
    return module_aliases, direct_names


def _spawn_callee(
    node: ast.Call, module_aliases: set[str], direct_names: dict[str, str]
) -> str | None:
    """Return the subprocess entry-point name for *node*, else ``None``."""
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr not in _SPAWN_NAMES:
            return None
        if isinstance(func.value, ast.Name) and func.value.id in module_aliases:
            return func.attr
        return None
    if isinstance(func, ast.Name):
        return direct_names.get(func.id)
    return None


def _partial_spawn_callee(
    node: ast.Call, module_aliases: set[str], direct_names: dict[str, str]
) -> str | None:
    """Return the spawn name when *node* is ``functools.partial(<spawn>, ...)``.

    A partial detaches the kwargs from the eventual call, so an
    attribute/name-only scan of call sites would never see it.
    """
    func = node.func
    is_partial = (isinstance(func, ast.Attribute) and func.attr == "partial") or (
        isinstance(func, ast.Name) and func.id == "partial"
    )
    if not is_partial or not node.args:
        return None
    first = node.args[0]
    if (
        isinstance(first, ast.Attribute)
        and first.attr in _SPAWN_NAMES
        and isinstance(first.value, ast.Name)
        and first.value.id in module_aliases
    ):
        return first.attr
    if isinstance(first, ast.Name):
        return direct_names.get(first.id)
    return None


def _keyword(node: ast.Call, name: str) -> ast.keyword | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw
    return None


def _is_literal_true(kw: ast.keyword | None) -> bool:
    return (
        kw is not None and isinstance(kw.value, ast.Constant) and kw.value.value is True
    )


def _is_literal_false(kw: ast.keyword | None) -> bool:
    return (
        kw is not None
        and isinstance(kw.value, ast.Constant)
        and kw.value.value is False
    )


def _has_kwargs_splat(node: ast.Call) -> bool:
    """True when the call forwards ``**kwargs`` (text mode becomes unprovable)."""
    return any(kw.arg is None for kw in node.keywords)


def _is_nonliteral(kw: ast.keyword | None) -> bool:
    """True when *kw* is present but its value is not a literal ``True``/``False``."""
    return kw is not None and not isinstance(kw.value, ast.Constant)


def _decodes_to_str(node: ast.Call) -> bool:
    """True when the call may return ``str`` (so an implicit codec could be used).

    **Fails closed.** Codex adversarial-review flagged that only accepting a literal
    ``text=True`` lets a spawn slip through when text mode is switched on by a
    variable or a forwarded ``**kwargs``. Since the guard cannot evaluate those
    statically, it treats "cannot prove this is binary" as "must prove it declares a
    codec" -- noisier, but a guard that only catches the literal form is the shape
    that lets #656 come back.
    """
    if _is_literal_true(_keyword(node, "text")):
        return True
    if _is_literal_true(_keyword(node, "universal_newlines")):
        return True
    if _is_nonliteral(_keyword(node, "text")):
        return True
    if _is_nonliteral(_keyword(node, "universal_newlines")):
        return True
    if _has_kwargs_splat(node):
        return True
    # ``encoding=`` alone also switches the streams to text mode -- but that is
    # the compliant form, so it is handled by the encoding check below.
    return False


def _violations_in_file(path: pathlib.Path) -> list[str]:
    """Return human-readable violations for one production module."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = path.relative_to(_PROJECT_ROOT)
    module_aliases, direct_names = _subprocess_bindings(tree)

    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = _partial_spawn_callee(node, module_aliases, direct_names)
        if callee is not None:
            # functools.partial(subprocess.run, ...) -- the kwargs are frozen
            # here, so require the codec here too rather than chasing the
            # call site (Codex adversarial-review).
            if _keyword(node, "encoding") is None or _keyword(node, "errors") is None:
                out.append(
                    f"{rel}:{node.lineno}: functools.partial over subprocess.{callee} "
                    f"must pin encoding='utf-8', errors='replace' -- the guard cannot "
                    f"follow the resulting callable to its call sites (#658)."
                )
            continue

        callee = _spawn_callee(node, module_aliases, direct_names)
        if callee is None:
            continue
        if _is_literal_false(_keyword(node, "text")) and not _has_kwargs_splat(node):
            continue  # explicit binary mode
        if not _decodes_to_str(node):
            continue  # binary mode -- caller decodes explicitly

        encoding_kw = _keyword(node, "encoding")
        errors_kw = _keyword(node, "errors")
        missing = []
        if encoding_kw is None:
            missing.append("encoding=")
        if errors_kw is None:
            missing.append("errors=")
        if missing:
            out.append(
                f"{rel}:{node.lineno}: subprocess.{callee}(...) decodes to str but is "
                f"missing {' and '.join(missing)}. On Windows the stream is then decoded "
                f"with the OS default (cp932) and a UTF-8 byte raises "
                f"UnicodeDecodeError (#656). Add encoding='utf-8', errors='replace'."
            )
    return out


def _production_modules() -> list[pathlib.Path]:
    return sorted(_SRC_DIR.rglob("*.py"))


def test_scan_covers_the_production_package():
    """The scan must actually see files -- an empty sweep would be a false green.

    A rename of the package directory or a glob typo would otherwise turn this
    module into a test that asserts nothing while still reporting green.
    """
    modules = _production_modules()
    assert len(modules) > 20, (
        f"expected the production package to have many modules, found {len(modules)} "
        f"under {_SRC_DIR} -- the scan root is probably wrong"
    )


def test_no_text_mode_subprocess_without_explicit_encoding():
    """Every text-mode subprocess spawn in ``allaganeye/**`` names its codec (#658)."""
    violations: list[str] = []
    for path in _production_modules():
        violations.extend(_violations_in_file(path))

    assert not violations, "subprocess text-mode encoding violations:\n" + "\n".join(
        violations
    )


# --- the guard's own red proof (self-test) -------------------------------------
#
# A guard that never fires is indistinguishable from a guard that cannot fire.
# These feed adversarial-but-valid sources through the same scanner used above and
# assert it still finds the violation, so the detector cannot silently rot into a
# no-op (e.g. if `_spawn_callee` stopped matching, every test above would still be
# green while catching nothing).


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=True)\n", id="attribute-text"
        ),
        pytest.param(
            "import subprocess as sp\nsp.run(cmd, capture_output=True, text=True)\n",
            id="aliased-module",
        ),
        pytest.param(
            "from subprocess import run\nrun(cmd, text=True)\n", id="bare-from-import"
        ),
        pytest.param(
            "from subprocess import run as r\nr(cmd, text=True)\n",
            id="aliased-from-import",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, universal_newlines=True)\n",
            id="universal-newlines",
        ),
        pytest.param(
            "import subprocess\nsubprocess.Popen(cmd, text=True)\n", id="popen"
        ),
        pytest.param(
            "import subprocess\nsubprocess.check_output(cmd, text=True)\n",
            id="check-output",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=True, encoding='utf-8')\n",
            id="errors-missing",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=True, errors='replace')\n",
            id="encoding-missing",
        ),
        pytest.param(
            "def f():\n    import subprocess\n    subprocess.run(cmd, text=True)\n",
            id="lazy-import-inside-function",
        ),
        # --- indirections Codex adversarial-review called out (#658) ---
        pytest.param(
            "import subprocess\nrun = subprocess.run\nrun(cmd, text=True)\n",
            id="assignment-alias",
        ),
        pytest.param(
            "import subprocess as sp\n_spawn = sp.Popen\n_spawn(cmd, text=True)\n",
            id="assignment-alias-of-alias",
        ),
        pytest.param(
            "import functools, subprocess\n"
            "runner = functools.partial(subprocess.run, text=True)\n",
            id="functools-partial",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, **kwargs)\n",
            id="kwargs-splat-hides-text-mode",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=want_text)\n",
            id="variable-text-mode",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=False, **kwargs)\n",
            id="kwargs-splat-can-override-text-false",
        ),
    ],
)
def test_guard_flags_violating_source(source: str, tmp_path: pathlib.Path):
    """Each violating form is detected by the same scanner the real test uses."""
    mod = tmp_path / "offender.py"
    mod.write_text(source, encoding="utf-8")

    # _violations_in_file reports paths relative to the repo root; point it at a
    # file inside a temp tree by faking that root for the duration of the call.
    found = _violations_in_file_at(mod, tmp_path)
    assert found, f"guard failed to flag a violating call:\n{source}"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(
            "import subprocess\n"
            "subprocess.run(cmd, text=True, encoding='utf-8', errors='replace')\n",
            id="compliant-text",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, capture_output=True)\n",
            id="binary-default",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(cmd, text=False)\n", id="explicit-binary"
        ),
        pytest.param(
            "import shutil\nshutil.run(cmd, text=True)\n", id="other-module-same-attr"
        ),
        pytest.param(
            "class Runner:\n    def run(self, cmd, text=True): ...\n"
            "Runner().run(cmd, text=True)\n",
            id="unrelated-method-named-run",
        ),
    ],
)
def test_guard_accepts_compliant_source(source: str, tmp_path: pathlib.Path):
    """Compliant / irrelevant forms must not be flagged (no false reds).

    The two ``other-module`` cases matter: an attribute-only scan that matched any
    ``X.run(text=True)`` would fail closed but flood unrelated libraries, and the
    noise is what gets a guard disabled.
    """
    mod = tmp_path / "ok.py"
    mod.write_text(source, encoding="utf-8")

    found = _violations_in_file_at(mod, tmp_path)
    assert not found, f"guard produced a false positive for:\n{source}\n-> {found}"


def _violations_in_file_at(path: pathlib.Path, root: pathlib.Path) -> list[str]:
    """``_violations_in_file`` with a caller-supplied root (for the self-tests)."""
    global _PROJECT_ROOT
    original = _PROJECT_ROOT
    _PROJECT_ROOT = root
    try:
        return _violations_in_file(path)
    finally:
        _PROJECT_ROOT = original
