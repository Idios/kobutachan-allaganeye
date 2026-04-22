"""Atomic metadata.json reader / writer for the CLI <-> GUI contract (#463).

Design notes: see ``docs/metadata-spec.md``.

Key guarantees:

* **Atomic write**: write to a sibling ``.tmp`` file, then ``os.replace`` onto
  the target path.  A mid-write crash never leaves a torn ``metadata.json``.
* **Encoding**: UTF-8, ``indent=2``, ``ensure_ascii=False``.  Matches the
  historical ``split`` output exactly so older cached files stay diffable.
* **``note`` field removed** (#463): messages that used to live in
  ``note`` have moved to ``docs/cli-spec.md`` section metadata.json so the
  on-disk payload stays purely structured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from allaganeye.exceptions import AllaganEyeError, InputFileError

__all__ = ["read_metadata", "write_metadata_atomic"]


def write_metadata_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Serialise ``payload`` to ``path`` atomically via a ``.tmp`` sibling.

    Raises :class:`AllaganEyeError` when the directory cannot be created or
    either write/rename fails.  Callers are responsible for shaping
    ``payload`` (this function does not validate the schema).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise AllaganEyeError(
            f"Cannot create output directory {path.parent}: {e}"
        ) from e

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp_path, path)
    except OSError as e:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise AllaganEyeError(f"Cannot write metadata to {path}: {e}") from e


def read_metadata(path: Path) -> dict[str, Any]:
    """Load ``metadata.json`` produced by ``allaganeye detect``.

    Raises :class:`InputFileError` when the file is missing or not valid
    JSON -- both are user-facing conditions that map to exit code 2.
    Unknown top-level fields (e.g. legacy ``note`` in files produced before
    #463) are preserved so GUI can round-trip without losing context.
    """
    if not path.exists():
        raise InputFileError(f"metadata file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise InputFileError(f"cannot read metadata file {path}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InputFileError(f"metadata file {path} is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise InputFileError(
            f"metadata file {path} root must be a JSON object, "
            f"got {type(data).__name__}"
        )
    return data
