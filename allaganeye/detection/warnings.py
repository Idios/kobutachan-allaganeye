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

from collections.abc import Sequence
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


WARNING_CODES: dict[str, str] = {
    "post_match_trailing_dropped": (
        "A trailing post-match segment was dropped because no scorebar was "
        "detected in its early candidate-match window; re-run with "
        "--keep-trailing to retain it."
    ),
}
"""Registry of known warning codes mapped to their default English message.

Emitters should add entries here alongside the code they introduce so
readers can look up a human-readable default even when the metadata
payload only carries the code.
"""


def build_warnings(
    *,
    trailing_drops: Sequence[tuple[float, float]] = (),
) -> list[MetadataWarning]:
    """Build the `warnings` list for a freshly written metadata.json.

    Args:
        trailing_drops: ``(start, end)`` spans for each post-match trailing
            segment that ``_drop_post_match_trailing`` removed (#805 段階1).
            Each becomes a ``post_match_trailing_dropped`` warn entry so the
            dropped match's boundaries are recoverable from metadata.json.

    Returns an empty list when no context is supplied (backward compatible
    with the #518 scaffold).
    """
    warnings: list[MetadataWarning] = []
    for start, end in trailing_drops:
        warnings.append(
            MetadataWarning(
                code="post_match_trailing_dropped",
                message_en=WARNING_CODES["post_match_trailing_dropped"],
                severity="warn",
                context={"start": start, "end": end},
            )
        )
    return warnings
