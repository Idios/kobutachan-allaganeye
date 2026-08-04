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
    "sanitize_warnings",
]

Severity = Literal["info", "warn", "error"]
"""Allowed severity levels for an emitted warning. Public alias for
emitters; the canonical literal lives inline in
:class:`allaganeye.metadata_types.MetadataWarning`."""


WARNING_CODES: dict[str, str] = {
    # #805 段階2 (W1): DEPRECATED -- emission stopped. The non-destructive
    # ``post_match`` flag on the Match now records a post-match trailing
    # segment, so this warning is no longer emitted by ``build_warnings``. The
    # code stays registered so ``sanitize_warnings`` can still read it out of an
    # older metadata.json (backward compatibility).
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


def build_warnings() -> list[MetadataWarning]:
    """Build the `warnings` list for a freshly written metadata.json.

    Always returns an empty list (the #518 scaffold shape). The only emitter
    that ever populated it -- ``post_match_trailing_dropped`` for a dropped
    post-match trailing segment -- was unwired in #805 段階2 (W1): the
    non-destructive ``post_match`` flag on the Match now records that case, so
    no warning is emitted. The code stays registered for reading older
    metadata.json (see ``WARNING_CODES`` / ``sanitize_warnings``).
    """
    return []


def sanitize_warnings(raw: object) -> list[MetadataWarning]:
    """Coerce an arbitrary value (e.g. warnings read from an existing
    metadata.json) into a list of schema-valid MetadataWarning entries.
    Drops non-dict entries, entries without a non-empty string ``code``,
    and any optional field whose value violates the schema; unknown keys
    are dropped (schema is additionalProperties:false)."""
    if not isinstance(raw, list):
        return []
    cleaned: list[MetadataWarning] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        if not isinstance(code, str) or not code:
            continue
        warning: MetadataWarning = {"code": code}
        message_en = entry.get("message_en")
        if isinstance(message_en, str):
            warning["message_en"] = message_en
        severity = entry.get("severity")
        if severity in ("info", "warn", "error"):
            warning["severity"] = severity
        context = entry.get("context")
        if isinstance(context, dict):
            warning["context"] = context
        cleaned.append(warning)
    return cleaned
