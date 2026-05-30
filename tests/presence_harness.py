"""Offline validation harness for presence-based detection (Phase 1).

Compares presence-detected match segments against ground-truth annotations
(OBS baselines + VTuber manual GT) and reports matched / missed / spurious
counts and boundary errors.  Pure comparison logic lives here so it can be
unit-tested without video; the slow end-to-end runs live in
``tests/test_presence_validation.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GroundTruthMatch:
    """A ground-truth FL match interval in seconds."""

    start: float
    end: float


@dataclass(frozen=True)
class GroundTruth:
    """Parsed ground-truth file."""

    source_file: str
    tolerance_sec: float
    matches: list[GroundTruthMatch]


def load_ground_truth(path: Path) -> GroundTruth:
    """Load a ground-truth JSON (OBS / VTuber shared schema)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [
        GroundTruthMatch(start=float(m["start_time"]), end=float(m["end_time"]))
        for m in data["matches"]
    ]
    return GroundTruth(
        source_file=str(data["source_file"]),
        tolerance_sec=float(data["tolerance_sec"]),
        matches=matches,
    )
