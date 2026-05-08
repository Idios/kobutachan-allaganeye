"""Bundled binary/asset integrity check (#668).

Used by both:
- the CLI ``--version`` callback (production path) -- see ``allaganeye.cli``
- the Tauri release-build startup hook (mirror logic in Rust) -- see
  ``gui/src-tauri/src/integrity.rs``

Both paths read the same ``integrity-manifest.json`` generated at build
time by ``scripts/build-portable-zip.ps1``. Detection failures produce a
blocking error UX (CLI exit code 7 / GUI ``ErrorModal``) and append a
plain-text record to ``<install dir>/logs/error-YYYYMMDD.log``.

Skip in dev / pytest by setting ``ALLAGANEYE_INTEGRITY_SKIP=1``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from allaganeye.exceptions import IntegrityError

_MANIFEST_NAME = "integrity-manifest.json"

# Resolved at import time so monkeypatch.setattr can override for tests
# without touching the real ``__file__`` (which would also affect other
# tests). Production callers use ``_default_manifest_path()`` which reads
# this constant.
_PACKAGE_INIT: Path = Path(__file__).resolve().parent / "__init__.py"


def _resolve_install_dir(package_init: Path) -> Path:
    """Compute install dir from ``allaganeye/__init__.py`` path.

    Portable ZIP layout: ``<install dir>/lib/allaganeye/__init__.py``,
    so the install dir is 3 ancestors up from ``__init__.py``.
    """
    return package_init.resolve().parent.parent.parent


def _default_manifest_path() -> Path:
    """Return ``<install dir>/integrity-manifest.json`` for production use."""
    install_dir = _resolve_install_dir(_PACKAGE_INIT)
    return install_dir / _MANIFEST_NAME


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate the integrity manifest JSON.

    Raises :class:`IntegrityError` when the file is missing, the JSON is
    malformed, or the top-level ``files`` key is absent.
    """
    if not path.exists():
        raise IntegrityError(
            f"integrity manifest not found: {path}",
            context={"manifest_path": str(path)},
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntegrityError(
            f"integrity manifest invalid JSON: {path}",
            context={"manifest_path": str(path), "json_error": str(exc)},
        ) from exc
    if not isinstance(data, dict) or "files" not in data:
        raise IntegrityError(
            f"integrity manifest missing 'files' key: {path}",
            context={"manifest_path": str(path)},
        )
    return data


def check(
    manifest_path: Path | None = None, *, install_dir: Path | None = None
) -> None:
    """Verify all bundled files match the manifest.

    Aggregates ``missing`` paths into the IntegrityError context so the
    caller (CLI / GUI emit) can show all failures at once instead of
    one-at-a-time.
    """
    if manifest_path is None:
        manifest_path = _default_manifest_path()
    if install_dir is None:
        install_dir = manifest_path.parent

    data = load_manifest(manifest_path)
    missing: list[str] = []
    size_mismatch: list[dict[str, Any]] = []
    for entry in data.get("files", []):
        rel_path = entry["path"]
        target = install_dir / rel_path
        if not target.exists():
            missing.append(rel_path)
            continue
        # size_mismatch detection comes in Task 6
        actual = target.stat().st_size
        if actual != int(entry["size"]):
            size_mismatch.append(
                {
                    "path": rel_path,
                    "expected": int(entry["size"]),
                    "actual": actual,
                }
            )
    if missing or size_mismatch:
        raise IntegrityError(
            f"integrity check failed: {len(missing)} missing, "
            f"{len(size_mismatch)} size mismatch",
            context={"missing": missing, "size_mismatch": size_mismatch},
        )
    return None
