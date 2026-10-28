"""Resolution-anchor guard for scripts/capture-readme-screens.mjs (#1008).

The capture script resolves `playwright` with `createRequire` anchored at
`gui/package.json`, because a bare ESM import from `scripts/` never looks in
`gui/node_modules` (it walks `scripts/node_modules` and `<repo>/node_modules`
only) and fails with `ERR_MODULE_NOT_FOUND`.

This file is the firing point for that convention (3-point set (1)): it fails
when the anchor target disappears or stops resolving into `gui/`, which is what
happens if the script is moved without moving the anchor.

The import guard covers the forms that would actually re-introduce #1008:
static `import` / `export ... from`, and a simple dynamic `import('playwright')`.
Computed specifiers (template literal / concat) are out of scope on purpose --
a one-shot maintainer script does not need a general module-graph checker.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "capture-readme-screens.mjs"

_ANCHOR_RE = re.compile(
    r"createRequire\(\s*new URL\(\s*['\"](?P<anchor>[^'\"]+)['\"]\s*,\s*import\.meta\.url\s*\)\s*\)"
)


def test_anchor_resolves_into_gui() -> None:
    src = SCRIPT.read_text(encoding="utf-8")
    match = _ANCHOR_RE.search(src)
    assert match, "createRequire anchor not found in capture-readme-screens.mjs"
    target = (SCRIPT.parent / match.group("anchor")).resolve()
    assert target.is_file(), f"anchor target does not exist: {target}"
    assert target.parent.name == "gui", (
        f"anchor must resolve into gui/ (got parent {target.parent.name})"
    )


def test_no_bare_playwright_import() -> None:
    """A bare playwright specifier would re-introduce the #1008 failure."""
    src = SCRIPT.read_text(encoding="utf-8")
    static = re.search(r"^\s*import\s+[^;]*['\"]playwright['\"]", src, re.MULTILINE)
    reexport = re.search(
        r"^\s*export\s+[^;]*from\s+['\"]playwright['\"]", src, re.MULTILINE
    )
    dynamic = re.search(r"\bimport\s*\(\s*['\"]playwright['\"]", src)
    assert static is None, f"bare static playwright import re-introduced: {static}"
    assert reexport is None, f"playwright re-export re-introduced: {reexport}"
    assert dynamic is None, f"dynamic playwright import re-introduced: {dynamic}"
