"""Detection pipeline helpers shared between ``detect`` and ``split`` commands.

Extracted from ``allaganeye.commands.split_matches`` in #463 so that both
``allaganeye detect <video>`` (metadata-only) and
``allaganeye split --from-metadata <metadata.json>`` (split-only) reuse the
same detection / metadata contract.
"""

from allaganeye.detection.format import (
    format_duration,
    format_timestamp,
    iso_utc_now,
)
from allaganeye.detection.metadata_writer import (
    read_metadata,
    write_metadata_atomic,
)

__all__ = [
    "format_duration",
    "format_timestamp",
    "iso_utc_now",
    "read_metadata",
    "write_metadata_atomic",
]
