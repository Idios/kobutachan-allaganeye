"""Presence-based match detection (scorebar present/absent as the signal).

Phase 1 of the presence-detection engine (spec
docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md).
This module is ADDITIVE and NOT wired into the production detection path;
it exists for the offline validation harness only.  The brightness-based
``detector.detect_match_boundaries`` remains the production detector until
the Phase 3 cutover.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceSample:
    """One time-grid sample: whether the scorebar is present at ``time``."""

    time: float
    present: bool
    confidence: float


@dataclass(frozen=True)
class PresenceMatch:
    """A detected FL match segment in seconds (presence-based)."""

    start: float
    end: float
