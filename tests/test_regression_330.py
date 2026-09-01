"""Regression tests for issue #330 Match 6 boundary accuracy (#361).

Verifies that detect_match_boundaries places the end of the 6th match near
2:15:37 in the 2026-04-08 21-14-05 recording, rather than the 2:16:12 value
observed before the #361 Prong A3/A4 fix.

Requires:
- ``ALLAGANEYE_AUDIO_TEST_VIDEO`` pointing to the 2026-04-08 21-14-05 primary
  recording (same env var used by ``tests/test_audio_integration.py``).
- ffmpeg/ffprobe in PATH.
- For the GPU variant, a GPU with hardware acceleration available.

Run with: ``pytest -m slow tests/test_regression_330.py``
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from allaganeye.ffmpeg_path import find_ffmpeg
from allaganeye.video.detector import (
    MatchBoundary,
    detect_match_boundaries,
)
from allaganeye.video.probe import ProbeResult, probe_video

pytestmark = pytest.mark.slow


# Match 6 actual end (ground truth, 2026-04-08 21-14-05 recording):
# 2:15:37 = 8137s, from user verification in issue #330.
_MATCH_6_ACTUAL_END_SECONDS = 8137.0
_BOUNDARY_TOLERANCE_SECONDS = 10.0


def _video_from_env() -> Path | None:
    env = os.environ.get("ALLAGANEYE_AUDIO_TEST_VIDEO")
    if not env:
        return None
    path = Path(env)
    return path if path.is_file() else None


def _gpu_available() -> bool:
    try:
        result = subprocess.run(
            [find_ffmpeg(), "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        accels = result.stdout.lower()
        return any(
            a in accels for a in ("cuda", "d3d11va", "qsv", "vulkan", "videotoolbox")
        )
    except Exception:
        return False


@pytest.fixture(scope="module")
def primary_video() -> Path:
    video = _video_from_env()
    if video is None:
        pytest.skip(
            "ALLAGANEYE_AUDIO_TEST_VIDEO not set or file missing; "
            "expected the 2026-04-08 21-14-05.mkv primary recording"
        )
    return video


@pytest.fixture(scope="module")
def primary_metadata(primary_video: Path) -> ProbeResult:
    return probe_video(primary_video)


def _run_detection(
    video: Path, metadata: ProbeResult, *, use_gpu: bool
) -> list[MatchBoundary]:
    return detect_match_boundaries(
        video,
        use_gpu=use_gpu,
        duration_hint=metadata["duration"],
        sample_interval=2.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        src_resolution=(metadata["width"], metadata["height"]),
        codec=metadata["codec"],
        # #864: mirror the production detect_kwargs (split_matches.py). Without
        # these, this helper resolved no fps at all. Before #864 that silently
        # degraded to the pre-#576 fps-filter path; after the removal it raises
        # VideoProcessingError, so the test could never have run.
        #
        # It went unnoticed because both tests here skip unless
        # ALLAGANEYE_AUDIO_TEST_VIDEO is set, so the #864 sweep that fixed the
        # sibling callers (tests/test_scorebar_regression.py, and
        # tests/generate_baselines.py) never saw this one execute.
        source_fps=metadata["fps"],
        source_fps_num=metadata["fps_num"],
        source_fps_den=metadata["fps_den"],
    )


def _assert_match_6_end_within_tolerance(boundaries: list[MatchBoundary]) -> None:
    """Assert exactly one detected match ends within tolerance of the ground truth.

    Content-based matching is robust against unrelated detector changes that
    shift the overall match count or ordering: the regression check stays
    meaningful as long as *some* match boundary lands near 2:15:37.
    """
    candidates = [
        b
        for b in boundaries
        if abs(b["end"] - _MATCH_6_ACTUAL_END_SECONDS) <= _BOUNDARY_TOLERANCE_SECONDS
    ]
    assert len(candidates) == 1, (
        f"Expected exactly one match ending within "
        f"{_BOUNDARY_TOLERANCE_SECONDS:.1f}s of "
        f"{_MATCH_6_ACTUAL_END_SECONDS:.1f}s, found {len(candidates)}. "
        f"boundaries={boundaries}"
    )


class TestMatch6BoundaryRegression:
    """Regression: #330 Match 6 end 35s shift resolved by #361 A3/A4."""

    @pytest.mark.slow_detect
    def test_match_6_boundary_2015_within_tolerance_cpu(
        self, primary_video: Path, primary_metadata: ProbeResult
    ) -> None:
        boundaries = _run_detection(primary_video, primary_metadata, use_gpu=False)
        _assert_match_6_end_within_tolerance(boundaries)

    @pytest.mark.slow_detect
    def test_match_6_boundary_2015_within_tolerance_gpu(
        self, primary_video: Path, primary_metadata: ProbeResult
    ) -> None:
        if not _gpu_available():
            pytest.skip("No GPU hardware acceleration available")
        boundaries = _run_detection(primary_video, primary_metadata, use_gpu=True)
        _assert_match_6_end_within_tolerance(boundaries)
