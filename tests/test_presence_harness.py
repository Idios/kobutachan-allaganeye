"""Unit tests for the presence validation harness (no video required)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.presence_harness import GroundTruth, GroundTruthMatch, load_ground_truth


def test_load_ground_truth(tmp_path: Path):
    gt_file = tmp_path / "gt.json"
    gt_file.write_text(
        json.dumps(
            {
                "source_file": "20260116/rec.mkv",
                "tolerance_sec": 5,
                "matches": [
                    {"index": 1, "start_time": 49, "end_time": 1054},
                    {"index": 2, "start_time": 1256, "end_time": 2178},
                ],
            }
        ),
        encoding="utf-8",
    )
    gt = load_ground_truth(gt_file)
    assert isinstance(gt, GroundTruth)
    assert gt.source_file == "20260116/rec.mkv"
    assert gt.tolerance_sec == 5.0
    assert gt.matches == [
        GroundTruthMatch(start=49.0, end=1054.0),
        GroundTruthMatch(start=1256.0, end=2178.0),
    ]
