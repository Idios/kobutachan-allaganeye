"""metadata.json schema_version validation + forward migration hooks (#515).

Policy:

* **Current schema**: v1. Files produced by ``allaganeye detect`` and
  ``allaganeye split`` carry ``schema_version: "1"`` at the payload root.
* **Missing ``schema_version``**: treated as v1 for backward compatibility
  with files produced before #515 (pre-0.2.0 outputs). The field is added
  implicitly on read; the underlying file is not rewritten.
* **Unknown future versions**: rejected with :class:`InputFileError` so
  that an older CLI never silently mangles a newer file.

Migrations are registered as ``from_version -> callable`` pairs in
:data:`MIGRATIONS`. Adding a new schema revision should:

1. Bump :data:`CURRENT_SCHEMA_VERSION` to the new string.
2. Register a migration from the previous version to the new version,
   e.g. ``MIGRATIONS["1"] = migrate_v1_to_v2``.
3. Update ``docs/metadata-spec.md`` section "schema_version" with the diff.
4. Update ``_build_metadata_payload`` (commands/split_matches.py) so
   new writes embed the new version literal.

See ``docs/metadata-spec.md`` section "schema_version" for the full policy.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from allaganeye.exceptions import InputFileError

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "MIGRATIONS",
    "apply_migrations",
    "check_schema_version",
]

CURRENT_SCHEMA_VERSION: str = "1"
"""The schema version that :func:`_build_metadata_payload` writes today."""

MIGRATIONS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
"""Registered migration functions keyed by the *source* version they upgrade.

Populated as new schema revisions land. Currently empty since v1 is the
initial published version.
"""


def check_schema_version(payload: dict[str, Any], *, source: Path) -> None:
    """Validate the payload's ``schema_version`` against what we can read.

    * Missing field -> treat as v1 (no-op, caller keeps the payload as-is).
    * Equal to :data:`CURRENT_SCHEMA_VERSION` -> accept.
    * Known older version with a registered migration -> accept (caller may
      invoke :func:`apply_migrations` to upgrade in-memory).
    * Unknown / newer version -> :class:`InputFileError`.
    """
    version = payload.get("schema_version")
    if version is None:
        # Pre-#515 files don't have the field; assume v1.
        return
    if not isinstance(version, str):
        raise InputFileError(
            f"metadata file {source} has non-string schema_version "
            f'({type(version).__name__}); expected string like "1"'
        )
    if version == CURRENT_SCHEMA_VERSION:
        return
    if version in MIGRATIONS:
        # Caller is expected to run apply_migrations() if they want the
        # upgraded payload; check alone doesn't mutate.
        return
    raise InputFileError(
        f"metadata file {source} has unsupported schema_version "
        f'"{version}" (this build understands up to '
        f'"{CURRENT_SCHEMA_VERSION}"); update allaganeye to a newer '
        f"version or re-run detect"
    )


def apply_migrations(payload: dict[str, Any]) -> dict[str, Any]:
    """Run registered migrations until the payload reaches the current version.

    Returns a new dict (migrations should not mutate the input). Raises
    :class:`InputFileError` if the payload's version is unknown and no
    chain of migrations can bring it to :data:`CURRENT_SCHEMA_VERSION`.

    Currently a no-op for v1 payloads (and payloads missing the field,
    which are treated as v1).
    """
    version = payload.get("schema_version", CURRENT_SCHEMA_VERSION)
    if not isinstance(version, str):
        raise InputFileError(
            f"schema_version must be a string, got {type(version).__name__}"
        )
    current = dict(payload)
    current.setdefault("schema_version", CURRENT_SCHEMA_VERSION)
    while version != CURRENT_SCHEMA_VERSION:
        migrate = MIGRATIONS.get(version)
        if migrate is None:
            raise InputFileError(
                f'no migration path from schema_version "{version}" '
                f'to "{CURRENT_SCHEMA_VERSION}"'
            )
        current = migrate(current)
        new_version = current.get("schema_version")
        if not isinstance(new_version, str) or new_version == version:
            raise InputFileError(
                f'migration from "{version}" did not advance schema_version'
            )
        version = new_version
    return current
