"""Shared format helpers for the detection pipeline (#463).

These were previously private to ``commands.split_matches``; extraction lets
the new ``detect`` command and ``split --from-metadata`` use the same
timestamp / duration / ISO formatting.
"""

from datetime import UTC, datetime


def format_timestamp(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    """Format duration as e.g. '14m02s' or '1h05m'."""
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def iso_utc_now() -> str:
    """UTC timestamp in ISO 8601 with 'Z' suffix, e.g. '2026-04-19T12:34:56Z'.

    Used for metadata.json ``detected_at`` / ``detection_started_at`` /
    ``detection_completed_at`` (#370 / #586). Second precision keeps the
    string human-readable without losing practical reproducibility.
    """
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
