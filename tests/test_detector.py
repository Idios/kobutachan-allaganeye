"""Tests for match boundary detection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    BrightnessStats,
    _extract_segments,
    detect_match_boundaries,
)


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
        """Single blackout region splits video into two matches."""
        blackout_times = [600.0, 601.0, 602.0, 603.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 600.0
        assert result[1]["start"] == 603.0
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
        # First segment: 0-100s (too short), second: 101-500s (399s, long enough)
        assert len(result) == 1
        assert result[0]["start"] == 101.0

    def test_multiple_blackouts_three_matches(self):
        """Multiple blackout regions create multiple match segments."""
        blackout_times = [
            # First blackout at ~600s
            600.0,
            601.0,
            602.0,
            # Second blackout at ~1800s
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
        assert result[0]["end"] == 600.0
        assert result[1]["start"] == 602.0
        assert result[1]["end"] == 1800.0
        assert result[2]["start"] == 1802.0

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
        assert result[0]["end"] == 600.0
        assert result[1]["start"] == 604.0


class TestDetectMatchBoundaries:
    """Tests for detect_match_boundaries with mocked OpenCV."""

    def _make_mock_cap(self, fps=30.0, total_frames=3600, read_failures=None):
        """Create a mock VideoCapture that returns bright frames."""
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            5: fps,  # CAP_PROP_FPS
            7: float(total_frames),  # CAP_PROP_FRAME_COUNT
        }.get(prop, 0.0)

        bright_frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        failure_positions = set(read_failures or [])
        call_count = {"n": 0}

        def mock_read():
            pos = call_count["n"]
            call_count["n"] += 1
            if pos in failure_positions:
                return False, None
            return True, bright_frame.copy()

        cap.read.side_effect = mock_read
        return cap

    @patch("allaganeye.video.detector.cv2")
    def test_consecutive_read_failures_raises(self, mock_cv2):
        cap = self._make_mock_cap(read_failures={0, 1, 2})
        mock_cv2.VideoCapture.return_value = cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_POS_FRAMES = 1

        with pytest.raises(VideoProcessingError, match="consecutive"):
            detect_match_boundaries(Path("test.mp4"), min_match_duration=1.0)

    @patch("allaganeye.video.detector.cv2")
    def test_open_failure_raises(self, mock_cv2):
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = cap

        with pytest.raises(VideoProcessingError, match="Cannot open"):
            detect_match_boundaries(Path("test.mp4"))

    @patch("allaganeye.video.detector.cv2")
    def test_collect_brightness_returns_stats(self, mock_cv2):
        cap = self._make_mock_cap(fps=30.0, total_frames=90)
        mock_cv2.VideoCapture.return_value = cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7
        mock_cv2.CAP_PROP_POS_FRAMES = 1
        mock_cv2.COLOR_BGR2GRAY = 6

        result = detect_match_boundaries(
            Path("test.mp4"),
            min_match_duration=1.0,
            collect_brightness=True,
        )
        assert isinstance(result, tuple)
        _segments, stats = result
        assert isinstance(stats, BrightnessStats)
        assert len(stats.samples) > 0
        assert stats.min_brightness > 0
        assert stats.max_brightness > 0


class TestBrightnessStats:
    def test_empty_stats(self):
        stats = BrightnessStats()
        assert stats.min_brightness == 0.0
        assert stats.max_brightness == 0.0
        assert stats.mean_brightness == 0.0
        assert stats.near_threshold(15.0) == []

    def test_stats_properties(self):
        stats = BrightnessStats(
            samples=[
                (0.0, 5.0),
                (1.0, 10.0),
                (2.0, 100.0),
                (3.0, 200.0),
            ]
        )
        assert stats.min_brightness == 5.0
        assert stats.max_brightness == 200.0
        assert stats.mean_brightness == pytest.approx(78.75)

    def test_near_threshold(self):
        stats = BrightnessStats(
            samples=[
                (0.0, 5.0),
                (1.0, 14.0),
                (2.0, 16.0),
                (3.0, 100.0),
            ]
        )
        near = stats.near_threshold(15.0, margin=10.0)
        assert len(near) == 3  # 5.0, 14.0, 16.0 are within 15 +/- 10
        timestamps = [t for t, _ in near]
        assert 0.0 in timestamps
        assert 1.0 in timestamps
        assert 2.0 in timestamps
