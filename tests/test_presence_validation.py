"""Slow, sample-gated OBS validation for presence detection (Phase 1 gate).

Runs the presence detector on each OBS source that has a manual ground-truth
file and asserts the GT-accuracy gate: zero missed, zero spurious, and all
boundary errors within the GT tolerance.  Requires ALLAGANEYE_SAMPLE_VIDEO_DIR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from allaganeye.video.presence import detect_matches_by_presence
from allaganeye.video.probe import probe_video
from tests.presence_harness import compare_segments, load_ground_truth

_GT_DIR = Path(__file__).parent / "baselines" / "v0.3.0" / "ground-truth"

# Provisional thresholds (spec section 4.6). Calibrate with Idios if a gate
# fails on real footage during Phase 1 sign-off.
_STRIDE = 4.0
_T_GAP = 30.0
_T_MIN_MATCH = 120.0
_TOL = 1.0
_WORKERS = 8


def _obs_gt_files() -> list[Path]:
    return sorted(_GT_DIR.glob("obs-*.json"))


@pytest.mark.slow
@pytest.mark.parametrize("gt_file", _obs_gt_files(), ids=lambda p: p.stem)
def test_obs_presence_gt_accuracy(gt_file: Path, sample_video_dir: Path) -> None:
    gt = load_ground_truth(gt_file)
    video = sample_video_dir / gt.source_file
    if not video.exists():
        pytest.skip(f"sample video not found: {video}")

    duration = float(probe_video(video)["duration"])
    detected = detect_matches_by_presence(
        video,
        duration,
        stride=_STRIDE,
        t_gap=_T_GAP,
        t_min_match=_T_MIN_MATCH,
        tol=_TOL,
        workers=_WORKERS,
    )
    res = compare_segments(detected, gt.matches, tolerance=gt.tolerance_sec)

    assert res.missed == 0, f"{gt_file.stem}: missed {res.missed} matches"
    assert res.spurious == 0, f"{gt_file.stem}: {res.spurious} spurious matches"
    assert res.max_boundary_error <= gt.tolerance_sec, (
        f"{gt_file.stem}: boundary error {res.max_boundary_error:.1f}s "
        f"> tol {gt.tolerance_sec}s"
    )
