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
