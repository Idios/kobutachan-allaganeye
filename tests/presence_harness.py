"""Offline validation harness for presence-based detection (Phase 1).

Compares presence-detected match segments against ground-truth annotations
(OBS baselines + VTuber manual GT) and reports matched / missed / spurious
counts and boundary errors.  Pure comparison logic lives here so it can be
unit-tested without video; the slow end-to-end runs live in
``tests/test_presence_validation.py``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from allaganeye.video.presence import PresenceMatch


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


@dataclass(frozen=True)
class ComparisonResult:
    """Outcome of comparing detected matches against ground truth."""

    matched: int
    missed: int
    spurious: int
    boundary_errors: list[float]

    @property
    def max_boundary_error(self) -> float:
        return max(self.boundary_errors) if self.boundary_errors else 0.0


def compare_segments(
    detected: Sequence[PresenceMatch],
    gt: Sequence[GroundTruthMatch],
    *,
    tolerance: float,
) -> ComparisonResult:
    """Greedy-match detected segments to GT within ``tolerance`` seconds.

    A detected segment matches a GT match iff both its start and end are
    within ``tolerance`` of the GT start/end.  Each GT and each detected
    segment is used at most once.  Unmatched GT -> missed; unmatched
    detected -> spurious.  ``boundary_errors`` holds, for every matched
    pair, the start error and the end error (seconds).
    """
    used_detected: set[int] = set()
    matched = 0
    boundary_errors: list[float] = []

    for g in gt:
        best_idx: int | None = None
        best_err: float | None = None
        for i, d in enumerate(detected):
            if i in used_detected:
                continue
            start_err = abs(d.start - g.start)
            end_err = abs(d.end - g.end)
            if start_err <= tolerance and end_err <= tolerance:
                worst = max(start_err, end_err)
                if best_err is None or worst < best_err:
                    best_err = worst
                    best_idx = i
        if best_idx is not None:
            used_detected.add(best_idx)
            matched += 1
            boundary_errors.append(abs(detected[best_idx].start - g.start))
            boundary_errors.append(abs(detected[best_idx].end - g.end))

    missed = len(gt) - matched
    spurious = len(detected) - len(used_detected)
    return ComparisonResult(
        matched=matched,
        missed=missed,
        spurious=spurious,
        boundary_errors=boundary_errors,
    )
