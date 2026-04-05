"""Tests for match boundary detection."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    _BLACKOUT_PADDING,
    _FRAME_SIZE,
    _extract_segments,
    detect_match_boundaries,
)


# --- Helpers ---


def _make_raw_frames(
    count: int,
    default_brightness: int = 128,
    overrides: dict[int, int] | None = None,
) -> bytes:
    """Build raw grayscale pipe output for *count* frames.

    Each frame is _FRAME_SIZE bytes of uniform brightness.
    *overrides* maps sample index → brightness for specific frames.
    """
    if overrides is None:
        overrides = {}
    buf = bytearray()
    for i in range(count):
        brightness = overrides.get(i, default_brightness)
        buf.extend(bytes([brightness]) * _FRAME_SIZE)
    return bytes(buf)


def _mock_popen(stdout_data: bytes, returncode: int = 0, stderr_data: bytes = b""):
    """Create a mock subprocess.Popen that yields *stdout_data*."""
    proc = MagicMock()
    proc.stdout = BytesIO(stdout_data)
    proc.stderr = BytesIO(stderr_data)
    proc.returncode = returncode
    proc.wait.return_value = returncode
    return proc


# ============================================================
# TestExtractSegments
# ============================================================


class TestExtractSegments:
    """Unit tests for segment extraction logic (no video files needed)."""

    def test_no_blackouts_long_video(self):
        """No blackouts in a long video → single segment."""
        result = _extract_segments(
            [], total_duration=1200.0, sample_interval=1.0, min_match_duration=300.0
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1200.0

    def test_no_blackouts_short_video(self):
        """No blackouts in a short video → no segments (below min duration)."""
        result = _extract_segments(
            [], total_duration=100.0, sample_interval=1.0, min_match_duration=300.0
        )
        assert len(result) == 0

    def test_single_blackout_two_matches(self):
        """Single blackout region splits video into two matches with padding."""
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
        blackout_times = [100.0, 101.0]
        result = _extract_segments(
            blackout_times,
            total_duration=500.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 1
        assert result[0]["start"] == pytest.approx(100.5)

    def test_multiple_blackouts_three_matches(self):
        """Multiple blackout regions create multiple match segments with padding."""
        blackout_times = [
            600.0,
            601.0,
            602.0,
            1800.0,
            1801.0,
            1802.0,
        ]
        result = _extract_segments(
            blackout_times,
            total_duration=3600.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 3
        assert result[0]["end"] == pytest.approx(601.0)
        assert result[1]["start"] == pytest.approx(601.0)
        assert result[1]["end"] == pytest.approx(1801.0)
        assert result[2]["start"] == pytest.approx(1801.0)

    def test_consecutive_blackouts_merged(self):
        """Consecutive blackout frames within tolerance are merged."""
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
        """Full padding applied when blackout region >= 2 * padding."""
        blackout_times = list(range(600, 611))
        result = _extract_segments(
            [float(t) for t in blackout_times],
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(603.0)
        assert result[1]["start"] == pytest.approx(607.0)

    def test_padding_clamped_for_short_region(self):
        """Padding clamped to half region duration for short blackout."""
        blackout_times = [600.0, 601.0, 602.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(601.0)
        assert result[1]["start"] == pytest.approx(601.0)

    def test_padding_does_not_exceed_total_duration(self):
        """seg_end clamped to total_duration when padding would overshoot."""
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
        """_BLACKOUT_PADDING is 3.0 seconds."""
        assert _BLACKOUT_PADDING == 3.0


# ============================================================
# TestDetectMatchBoundaries (ffmpeg pipe based)
# ============================================================


class TestDetectMatchBoundaries:
    """Tests for detect_match_boundaries() with mocked subprocess."""

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_all_bright_frames(self, mock_popen):
        """All bright frames → single segment covering full duration."""
        data = _make_raw_frames(300, default_brightness=128)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == pytest.approx(300.0)

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_all_black_frames(self, mock_popen):
        """All black frames → no segments (entire video is blackout)."""
        data = _make_raw_frames(300, default_brightness=5)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_blackout_in_middle(self, mock_popen):
        """Blackout in middle splits video into two segments."""
        # 1800 samples (1800s at 1s interval)
        overrides = {s: 5 for s in range(598, 603)}
        data = _make_raw_frames(1800, default_brightness=128, overrides=overrides)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == pytest.approx(1800.0)

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_custom_threshold(self, mock_popen):
        """Brightness 20 with threshold 15 → not blackout → 1 segment."""
        data = _make_raw_frames(300, default_brightness=20)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            blackout_threshold=15.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_custom_threshold_blackout(self, mock_popen):
        """Higher threshold makes same brightness frames count as blackout."""
        data = _make_raw_frames(300, default_brightness=20)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            blackout_threshold=25.0,
            min_match_duration=100.0,
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_custom_min_duration(self, mock_popen):
        """min_match_duration filters short segments."""
        # Blackout at 200s
        overrides = {s: 5 for s in range(198, 203)}
        data = _make_raw_frames(1800, default_brightness=128, overrides=overrides)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            min_match_duration=300.0,
        )
        assert len(result) == 1
        assert result[0]["start"] > 100.0

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_ffmpeg_failure_no_output(self, mock_popen):
        """ffmpeg failure with no output raises VideoProcessingError."""
        mock_popen.return_value = _mock_popen(
            b"", returncode=1, stderr_data=b"Error opening input"
        )

        with pytest.raises(VideoProcessingError, match="frame sampling failed"):
            detect_match_boundaries(
                Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
            )

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_ffmpeg_failure_partial_output(self, mock_popen):
        """ffmpeg failure with partial output uses available frames."""
        # 100 frames produced before failure (100s of 300s)
        data = _make_raw_frames(100, default_brightness=128)
        mock_popen.return_value = _mock_popen(data, returncode=1)

        # Should not raise — partial data is usable
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=50.0,
        )
        assert len(result) >= 1

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_ffmpeg_not_found(self, mock_popen):
        """FileNotFoundError raises VideoProcessingError."""
        mock_popen.side_effect = FileNotFoundError("ffmpeg not found")

        with pytest.raises(VideoProcessingError, match="ffmpeg not found"):
            detect_match_boundaries(
                Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
            )

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_progress_callback_called(self, mock_popen):
        """progress_callback is called for each sampled frame."""
        data = _make_raw_frames(300, default_brightness=128)
        mock_popen.return_value = _mock_popen(data)
        calls = []

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            sample_interval=1.0,
            min_match_duration=100.0,
            progress_callback=lambda si, t, bc: calls.append((si, t, bc)),
        )

        assert len(calls) == 300
        assert calls[0] == (0, 300, 0)
        # total_samples consistent
        assert all(c[1] == 300 for c in calls)
        # blackout_count non-decreasing
        counts = [c[2] for c in calls]
        assert counts == sorted(counts)

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_progress_callback_none_default(self, mock_popen):
        """No callback (default) works without error."""
        data = _make_raw_frames(300, default_brightness=128)
        mock_popen.return_value = _mock_popen(data)

        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_progress_callback_with_blackouts(self, mock_popen):
        """progress_callback reports increasing blackout count."""
        overrides = {s: 5 for s in range(598, 603)}
        data = _make_raw_frames(1800, default_brightness=128, overrides=overrides)
        mock_popen.return_value = _mock_popen(data)
        calls = []

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            progress_callback=lambda si, t, bc: calls.append((si, t, bc)),
        )

        max_blackouts = max(c[2] for c in calls)
        assert max_blackouts == 5

    @patch("allaganeye.video.detector.subprocess.Popen")
    def test_sample_interval_in_ffmpeg_command(self, mock_popen):
        """sample_interval is passed to ffmpeg select filter."""
        data = _make_raw_frames(150, default_brightness=128)
        mock_popen.return_value = _mock_popen(data)

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            sample_interval=2.0,
            min_match_duration=100.0,
        )

        cmd = mock_popen.call_args[0][0]
        # Verify select filter uses sample_interval
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert "mod(t\\,2.0)" in vf_value
