"""Tests for match boundary detection."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    _BLACKOUT_PADDING,
    _FRAME_SIZE,
    _extract_segments,
    _generate_timestamps,
    _probe_single_frame,
    detect_match_boundaries,
)


# --- Helpers ---


def _make_run_result(brightness: int = 128, frame_size: int = _FRAME_SIZE) -> MagicMock:
    """Create a mock subprocess.run result with a single grayscale frame."""
    result = MagicMock()
    result.stdout = bytes([brightness]) * frame_size
    result.returncode = 0
    return result


# ============================================================
# TestExtractSegments
# ============================================================


class TestExtractSegments:
    """Unit tests for segment extraction logic (no video files needed)."""

    def test_no_blackouts_long_video(self):
        result = _extract_segments(
            [], total_duration=1200.0, sample_interval=1.0, min_match_duration=300.0
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1200.0

    def test_no_blackouts_short_video(self):
        result = _extract_segments(
            [], total_duration=100.0, sample_interval=1.0, min_match_duration=300.0
        )
        assert len(result) == 0

    def test_single_blackout_two_matches(self):
        blackout_times = [600.0, 601.0, 602.0, 603.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == pytest.approx(601.5)
        assert result[1]["start"] == pytest.approx(601.5)
        assert result[1]["end"] == 1800.0

    def test_short_segment_filtered(self):
        """Segments shorter than min_match_duration are excluded."""
        # Blackout at 100-104s (4s, passes min_blackout_duration=3)
        blackout_times = [100.0, 101.0, 102.0, 103.0, 104.0]
        result = _extract_segments(
            blackout_times,
            total_duration=500.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        # First segment: 0 to ~102 (too short), second: ~102 to 500 (long enough)
        assert len(result) == 1
        assert result[0]["start"] == pytest.approx(102.0)

    def test_multiple_blackouts_three_matches(self):
        """Multiple blackout regions create multiple match segments with padding."""
        blackout_times = [
            # First blackout (600-604, 4s > 3s min_blackout)
            600.0,
            601.0,
            602.0,
            603.0,
            604.0,
            # Second blackout (1800-1804, 4s > 3s min_blackout)
            1800.0,
            1801.0,
            1802.0,
            1803.0,
            1804.0,
        ]
        result = _extract_segments(
            blackout_times,
            total_duration=3600.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 3
        # padding clamped to 2.0 (region duration 4s / 2)
        assert result[0]["end"] == pytest.approx(602.0)
        assert result[1]["start"] == pytest.approx(602.0)
        assert result[1]["end"] == pytest.approx(1802.0)
        assert result[2]["start"] == pytest.approx(1802.0)

    def test_consecutive_blackouts_merged(self):
        blackout_times = [600.0, 601.0, 602.0, 603.0, 604.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(602.0)
        assert result[1]["start"] == pytest.approx(602.0)

    def test_padding_full_when_region_long(self):
        blackout_times = [float(t) for t in range(600, 611)]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(603.0)
        assert result[1]["start"] == pytest.approx(607.0)

    def test_padding_clamped_for_short_region(self):
        """Padding clamped for region shorter than 2*padding but >= min_blackout."""
        # Region 600-604 (4s): padding = min(3.0, 2.0) = 2.0
        blackout_times = [600.0, 601.0, 602.0, 603.0, 604.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(602.0)
        assert result[1]["start"] == pytest.approx(602.0)

    def test_padding_does_not_exceed_total_duration(self):
        blackout_times = [997.0, 998.0, 999.0, 1000.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1000.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 1
        assert result[0]["end"] == pytest.approx(998.5)

    def test_padding_constant_value(self):
        assert _BLACKOUT_PADDING == 3.0

    def test_short_blackout_ignored(self):
        """Blackout regions shorter than min_blackout_duration are ignored."""
        # 1-2s respawn blackout should NOT split the video
        blackout_times = [600.0, 601.0]  # 1s region
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
        )
        # Short blackout ignored → entire video is one segment
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1800.0

    def test_long_blackout_kept(self):
        """Blackout regions >= min_blackout_duration are kept as boundaries."""
        # 5s blackout should split the video
        blackout_times = [600.0, 601.0, 602.0, 603.0, 604.0, 605.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
        )
        assert len(result) == 2

    def test_min_blackout_duration_zero(self):
        """min_blackout_duration=0 keeps all blackout regions."""
        blackout_times = [600.0, 601.0]  # 1s region
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            min_blackout_duration=0.0,
        )
        # 1s blackout kept → two segments
        assert len(result) == 2

    def test_mixed_short_and_long_blackouts(self):
        """Only long blackouts are used as boundaries, short ones ignored."""
        blackout_times = [
            # Short respawn blackout (1s, ignored)
            600.0,
            601.0,
            # Long match boundary (5s, kept)
            900.0,
            901.0,
            902.0,
            903.0,
            904.0,
            905.0,
        ]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            min_blackout_duration=3.0,
        )
        # Only the 5s blackout at 900s splits the video
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == 1800.0


# ============================================================
# TestGenerateTimestamps
# ============================================================


class TestGenerateTimestamps:
    def test_basic(self):
        assert _generate_timestamps(10.0, 2.0) == [0.0, 2.0, 4.0, 6.0, 8.0]

    def test_single(self):
        assert _generate_timestamps(0.5, 1.0) == [0.0]

    def test_empty(self):
        assert _generate_timestamps(0.0, 1.0) == []


# ============================================================
# TestProbeSingleFrame
# ============================================================


class TestProbeSingleFrame:
    @patch("allaganeye.video.detector.subprocess.run")
    def test_bright_frame(self, mock_run):
        mock_run.return_value = _make_run_result(brightness=128)
        assert _probe_single_frame(Path("test.mp4"), 10.0) == pytest.approx(128.0)

    @patch("allaganeye.video.detector.subprocess.run")
    def test_dark_frame(self, mock_run):
        mock_run.return_value = _make_run_result(brightness=5)
        assert _probe_single_frame(Path("test.mp4"), 10.0) == pytest.approx(5.0)

    @patch("allaganeye.video.detector.subprocess.run")
    def test_ss_before_i(self, mock_run):
        mock_run.return_value = _make_run_result()
        _probe_single_frame(Path("test.mp4"), 42.0)
        cmd = mock_run.call_args[0][0]
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx

    @patch("allaganeye.video.detector.subprocess.run")
    def test_incomplete_output(self, mock_run):
        result = MagicMock()
        result.stdout = b"\x00" * 10
        result.returncode = 0
        mock_run.return_value = result
        assert _probe_single_frame(Path("test.mp4"), 10.0) == 255.0

    @patch("allaganeye.video.detector.subprocess.run")
    def test_ffmpeg_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ffmpeg")
        with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
            _probe_single_frame(Path("test.mp4"), 10.0)

    @patch("allaganeye.video.detector.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)
        assert _probe_single_frame(Path("test.mp4"), 10.0) == 255.0


# ============================================================
# TestDetectMatchBoundaries
# ============================================================


class TestDetectMatchBoundaries:
    @patch("allaganeye.video.detector._probe_single_frame")
    def test_all_bright(self, mock_probe):
        mock_probe.return_value = 128.0
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == pytest.approx(300.0)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_all_black(self, mock_probe):
        mock_probe.return_value = 5.0
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_blackout_in_middle(self, mock_probe):
        def side_effect(path, t):
            return 5.0 if 598.0 <= t <= 602.0 else 128.0

        mock_probe.side_effect = side_effect
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == pytest.approx(1800.0)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_custom_threshold(self, mock_probe):
        mock_probe.return_value = 20.0
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            blackout_threshold=15.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_custom_threshold_blackout(self, mock_probe):
        mock_probe.return_value = 20.0
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            blackout_threshold=25.0,
            min_match_duration=100.0,
        )
        assert len(result) == 0

    def test_no_duration_hint_raises(self):
        with pytest.raises(
            VideoProcessingError, match="Cannot determine video duration"
        ):
            detect_match_boundaries(Path("test.mp4"), min_match_duration=100.0)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback(self, mock_probe):
        mock_probe.return_value = 128.0
        calls = []
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            progress_callback=lambda c, t, bc: calls.append((c, t, bc)),
        )
        assert len(calls) == 10
        assert all(c[1] == 10 for c in calls)
        completed = sorted(c[0] for c in calls)
        assert completed == list(range(1, 11))

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback_none(self, mock_probe):
        mock_probe.return_value = 128.0
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_sample_count(self, mock_probe):
        mock_probe.return_value = 128.0
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            sample_interval=2.0,
            min_match_duration=100.0,
        )
        assert mock_probe.call_count == 150

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_parallel_execution(self, mock_probe):
        mock_probe.return_value = 128.0
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=100.0,
            sample_interval=1.0,
            min_match_duration=10.0,
        )
        assert len(result) == 1
        assert mock_probe.call_count == 100
