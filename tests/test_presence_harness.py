"""Unit tests for the presence validation harness (no video required)."""

from __future__ import annotations

import json
from pathlib import Path

from allaganeye.video.presence import PresenceMatch
from tests.presence_harness import (
    ComparisonResult,
    GroundTruth,
    GroundTruthMatch,
    build_arg_parser,
    compare_segments,
    load_ground_truth,
)


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


def _gt(pairs: list[tuple[float, float]]) -> list[GroundTruthMatch]:
    return [GroundTruthMatch(start=a, end=b) for a, b in pairs]


def test_compare_all_matched_within_tolerance():
    detected = [PresenceMatch(50.0, 1056.0), PresenceMatch(1257.0, 2176.0)]
    gt = _gt([(49.0, 1054.0), (1256.0, 2178.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert isinstance(res, ComparisonResult)
    assert res.matched == 2
    assert res.missed == 0
    assert res.spurious == 0
    assert res.max_boundary_error <= 2.0


def test_compare_missed_match():
    detected = [PresenceMatch(50.0, 1056.0)]
    gt = _gt([(49.0, 1054.0), (1256.0, 2178.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 1
    assert res.missed == 1
    assert res.spurious == 0


def test_compare_spurious_match():
    detected = [PresenceMatch(50.0, 1056.0), PresenceMatch(4000.0, 4500.0)]
    gt = _gt([(49.0, 1054.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 1
    assert res.missed == 0
    assert res.spurious == 1


def test_compare_boundary_outside_tolerance_is_not_matched():
    # end off by 40s (> tol) -> not a match -> missed + spurious
    detected = [PresenceMatch(50.0, 1100.0)]
    gt = _gt([(49.0, 1054.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 0
    assert res.missed == 1
    assert res.spurious == 1


def test_build_arg_parser_defaults():
    parser = build_arg_parser()
    args = parser.parse_args(["--video", "v.mkv", "--ground-truth", "gt.json"])
    assert args.video == "v.mkv"
    assert args.ground_truth == "gt.json"
    assert args.stride == 4.0
    assert args.t_gap == 30.0
    assert args.t_min_match == 120.0
    assert args.tol == 1.0
    assert args.workers == 8


def test_build_arg_parser_overrides():
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--video",
            "v.mkv",
            "--ground-truth",
            "gt.json",
            "--stride",
            "3",
            "--t-gap",
            "45",
            "--t-min-match",
            "90",
            "--tol",
            "0.5",
            "--workers",
            "16",
        ]
    )
    assert args.stride == 3.0
    assert args.t_gap == 45.0
    assert args.t_min_match == 90.0
    assert args.tol == 0.5
    assert args.workers == 16
