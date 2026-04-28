"""Warning scaffold for metadata.json (#518).

This module centralises the payload shape for warnings that may accompany
a detect / split run. The initial revision writes an empty list on every
run -- no concrete warning codes are emitted yet.

Why introduce the scaffold now, before a concrete use case lands?

* Adding the `warnings: []` field to every freshly written metadata.json
  locks in the JSON schema so GUI / zod can start treating `warnings` as
  a known passthrough-safe key (consumers won't discover unknown fields
  the first time a code ships).
* Future PRs can wire emitters into detection / scorebar / audio without
  touching the payload builder or the reader surface.

See `docs/metadata-spec.md` section "warnings" for the contract.

The `MetadataWarning` TypedDict itself moved to
``allaganeye/metadata_types.py`` (auto-generated from
``schemas/metadata.schema.json``, #612). It is re-exported from here so
existing emitters keep working unchanged.
"""

from __future__ import annotations

from typing import Literal

from allaganeye.metadata_types import MetadataWarning

__all__ = [
    "WARNING_CODES",
    "MetadataWarning",
    "Severity",
    "build_warnings",
]

Severity = Literal["info", "warn", "error"]
"""Allowed severity levels for an emitted warning. Public alias for
emitters; the canonical literal lives inline in
:class:`allaganeye.metadata_types.MetadataWarning`."""


WARNING_CODES: dict[str, str] = {}
"""Registry of known warning codes mapped to their default English message.

Empty at introduction. Emitters should add entries here alongside the
code they introduce so readers can look up a human-readable default even
when the metadata payload only carries the code.
"""


def build_warnings() -> list[MetadataWarning]:
    """Build the `warnings` list for a freshly written metadata.json.

    Currently unconditional: returns an empty list. Future callers may
    pass detection / scorebar context to this helper and receive a
    populated list back.
    """
    return []
