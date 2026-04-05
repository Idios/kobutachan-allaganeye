"""Tests for match boundary detection."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    _BLACKOUT_PADDING,
    _extract_segments,
    detect_match_boundaries,
)


# --- Helpers ---


def _make_frame(brightness: int) -> np.ndarray:
    """Create a 2x2 BGR frame with uniform brightness."""
    return np.full((2, 2, 3), brightness, dtype=np.uint8)


def _make_capture_mock(
    *,
    is_opened: bool = True,
    fps: float = 30.0,
    frame_count: int = 9000,
    frames: dict[int, np.ndarray] | None = None,
    default_brightness: int = 128,
) -> MagicMock:
    """Create a mock cv2.VideoCapture with sequential read behavior.

    Simulates grab()/read() sequential access pattern.
    Args:
        frames: dict mapping frame index to numpy frame.
            Missing indices use default_brightness.
    """
    cap = MagicMock()
    cap.isOpened.return_value = is_opened

    def get_prop(prop_id):
        import cv2

        if prop_id == cv2.CAP_PROP_FPS:
            return fps
        if prop_id == cv2.CAP_PROP_FRAME_COUNT:
            return frame_count
        return 0.0

    cap.get.side_effect = get_prop

    current_frame = [0]

    if frames is None:
        frames = {}

    def read():
        idx = current_frame[0]
        if idx >= frame_count:
            return False, None
        current_frame[0] += 1
        if idx in frames:
            return True, frames[idx]
        return True, _make_frame(default_brightness)

    cap.read.side_effect = read

    def grab():
        idx = current_frame[0]
        if idx >= frame_count:
            return False
        current_frame[0] += 1
        return True

    cap.grab.side_effect = grab

    return cap


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
        # seg_end padded into blackout: region (600, 603), padding clamped to 1.5
        assert result[0]["end"] == pytest.approx(601.5)
        # seg_start padded into blackout: 603 - 1.5 = 601.5
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
        # First segment: 0 to ~100.5 (too short), second: ~100.5 to 500 (long enough)
        assert len(result) == 1
        assert result[0]["start"] == pytest.approx(100.5)

    def test_multiple_blackouts_three_matches(self):
        """Multiple blackout regions create multiple match segments with padding."""
        blackout_times = [
            # First blackout at ~600s (region: 600-602, duration 2s, padding clamped to 1.0)
            600.0,
            601.0,
            602.0,
            # Second blackout at ~1800s (region: 1800-1802, duration 2s, padding clamped to 1.0)
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
        # Region: (600, 604), duration 4s, padding clamped to 2.0
        assert len(result) == 2
        assert result[0]["end"] == pytest.approx(602.0)
        assert result[1]["start"] == pytest.approx(602.0)

    def test_padding_full_when_region_long(self):
        """Full padding applied when blackout region >= 2 * padding."""
        # Region: (600, 610), duration 10s > 2*3=6s → full padding of 3.0
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
        # Region: (600, 602), duration 2s → padding = min(3.0, 1.0) = 1.0
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
        # Blackout near the very end: region (997, 1000)
        # After last blackout: seg_start = 1000 - 1.5 = 998.5
        # Only 1.5s left → too short for min_match_duration
        blackout_times = [997.0, 998.0, 999.0, 1000.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1000.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 1
        # First segment end padded into blackout
        assert result[0]["end"] == pytest.approx(998.5)

    def test_padding_constant_value(self):
        """_BLACKOUT_PADDING is 3.0 seconds."""
        assert _BLACKOUT_PADDING == 3.0


# ============================================================
# TestDetectMatchBoundaries
# ============================================================


class TestDetectMatchBoundaries:
    """Tests for detect_match_boundaries() with mocked cv2.VideoCapture."""

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_video_cannot_open(self, mock_vc_class):
        """VideoCapture open failure raises VideoProcessingError."""
        mock_vc_class.return_value = _make_capture_mock(is_opened=False)

        with pytest.raises(VideoProcessingError, match="Cannot open video"):
            detect_match_boundaries(Path("test.mp4"))

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_fps_zero(self, mock_vc_class):
        """fps=0 raises VideoProcessingError."""
        mock_vc_class.return_value = _make_capture_mock(fps=0.0, frame_count=9000)

        with pytest.raises(VideoProcessingError, match="Cannot read video properties"):
            detect_match_boundaries(Path("test.mp4"))

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_frame_count_zero(self, mock_vc_class):
        """frame_count=0 without duration_hint raises VideoProcessingError."""
        mock_vc_class.return_value = _make_capture_mock(fps=30.0, frame_count=0)

        with pytest.raises(VideoProcessingError, match="Cannot read video properties"):
            detect_match_boundaries(Path("test.mp4"))

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_frame_count_zero_with_duration_hint(self, mock_vc_class):
        """frame_count=0 with duration_hint falls back to fps * duration."""
        # frame_count=0 but we provide a 9000-frame equivalent mock
        # that returns frames when read sequentially
        cap = _make_capture_mock(fps=30.0, frame_count=9000, default_brightness=128)
        # Override get to return 0 for FRAME_COUNT but still allow reads
        original_get = cap.get.side_effect

        def get_with_zero_frames(prop_id):
            import cv2

            if prop_id == cv2.CAP_PROP_FRAME_COUNT:
                return 0
            return original_get(prop_id)

        cap.get.side_effect = get_with_zero_frames
        mock_vc_class.return_value = cap

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,  # 300s * 30fps = 9000 frames
            min_match_duration=100.0,
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == pytest.approx(300.0)

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_frame_count_negative_with_duration_hint(self, mock_vc_class):
        """frame_count=-1 (MKV) with duration_hint uses fallback."""
        cap = _make_capture_mock(fps=30.0, frame_count=9000, default_brightness=128)
        original_get = cap.get.side_effect

        def get_with_negative_frames(prop_id):
            import cv2

            if prop_id == cv2.CAP_PROP_FRAME_COUNT:
                return -1
            return original_get(prop_id)

        cap.get.side_effect = get_with_negative_frames
        mock_vc_class.return_value = cap

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_frame_count_zero_with_zero_duration_hint(self, mock_vc_class):
        """frame_count=0 with duration_hint=0 still raises."""
        mock_vc_class.return_value = _make_capture_mock(fps=30.0, frame_count=0)

        with pytest.raises(VideoProcessingError, match="Cannot read video properties"):
            detect_match_boundaries(
                Path("test.mp4"), duration_hint=0.0, min_match_duration=100.0
            )

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_negative_fps(self, mock_vc_class):
        """Negative fps raises VideoProcessingError."""
        mock_vc_class.return_value = _make_capture_mock(fps=-1.0, frame_count=9000)

        with pytest.raises(VideoProcessingError, match="Cannot read video properties"):
            detect_match_boundaries(Path("test.mp4"))

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_all_bright_frames(self, mock_vc_class):
        """All bright frames → single segment covering full duration."""
        mock_vc_class.return_value = _make_capture_mock(
            fps=30.0,
            frame_count=9000,
            default_brightness=128,
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            min_match_duration=100.0,
        )
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == pytest.approx(300.0)

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_all_black_frames(self, mock_vc_class):
        """All black frames → no segments (entire video is blackout)."""
        mock_vc_class.return_value = _make_capture_mock(
            fps=30.0,
            frame_count=9000,
            default_brightness=5,
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            min_match_duration=100.0,
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_blackout_in_middle(self, mock_vc_class):
        """Blackout in middle splits video into two segments."""
        fps = 30.0
        total_frames = 54000  # 1800s

        black_frames = {}
        for sec in range(598, 603):
            frame_idx = int(sec * fps)
            black_frames[frame_idx] = _make_frame(5)

        mock_vc_class.return_value = _make_capture_mock(
            fps=fps,
            frame_count=total_frames,
            frames=black_frames,
            default_brightness=128,
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == pytest.approx(1800.0)

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_sample_interval_respected(self, mock_vc_class):
        """frame_step = fps * sample_interval; only sampled frames are decoded."""
        fps = 30.0
        total_frames = 9000  # 300s
        cap = _make_capture_mock(
            fps=fps, frame_count=total_frames, default_brightness=128
        )
        mock_vc_class.return_value = cap

        detect_match_boundaries(
            Path("test.mp4"),
            sample_interval=2.0,
            min_match_duration=100.0,
        )

        # frame_step = 30 * 2.0 = 60
        # read() called for sampled frames, grab() for skipped frames
        # Total read calls = total_frames / frame_step = 150
        # Total grab calls = total_frames - read_calls = 8850
        read_count = cap.read.call_count
        grab_count = cap.grab.call_count
        assert read_count == 150
        assert grab_count == total_frames - read_count

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_sample_interval_very_small(self, mock_vc_class):
        """Very small sample_interval clamps frame_step to 1 (every frame sampled)."""
        fps = 30.0
        total_frames = 90  # 3s, small for speed
        cap = _make_capture_mock(
            fps=fps, frame_count=total_frames, default_brightness=128
        )
        mock_vc_class.return_value = cap

        detect_match_boundaries(
            Path("test.mp4"),
            sample_interval=0.01,
            min_match_duration=1.0,
        )

        # frame_step = int(30 * 0.01) = 0 → clamped to 1
        # Every frame is sampled via read(), no grab() calls
        assert cap.read.call_count == total_frames
        assert cap.grab.call_count == 0

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_custom_threshold(self, mock_vc_class):
        """Brightness 20 with threshold 15 → not blackout → 1 segment."""
        fps = 30.0
        total_frames = 9000  # 300s
        mock_vc_class.return_value = _make_capture_mock(
            fps=fps,
            frame_count=total_frames,
            default_brightness=20,
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_custom_threshold_blackout(self, mock_vc_class):
        """Higher threshold makes same brightness frames count as blackout."""
        fps = 30.0
        total_frames = 9000
        mock_vc_class.return_value = _make_capture_mock(
            fps=fps,
            frame_count=total_frames,
            default_brightness=20,
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            blackout_threshold=25.0,
            min_match_duration=100.0,
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_custom_min_duration(self, mock_vc_class):
        """min_match_duration filters short segments."""
        fps = 30.0
        total_frames = 54000  # 1800s

        # Blackout at 200s → segments: 0-200s (200s) and ~200-1800s (1600s)
        black_frames = {}
        for sec in range(198, 203):
            black_frames[int(sec * fps)] = _make_frame(5)

        mock_vc_class.return_value = _make_capture_mock(
            fps=fps,
            frame_count=total_frames,
            frames=black_frames,
            default_brightness=128,
        )

        # min_match_duration=300 → only the long segment
        result = detect_match_boundaries(
            Path("test.mp4"),
            min_match_duration=300.0,
        )
        assert len(result) == 1
        assert result[0]["start"] > 100.0  # the second (long) segment

    @patch("allaganeye.video.detector.cv2")
    def test_consecutive_read_failures_raises(self, mock_cv2):
        """3 consecutive read failures raise VideoProcessingError."""
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            5: 30.0,  # CAP_PROP_FPS
            7: 3600.0,  # CAP_PROP_FRAME_COUNT
        }.get(prop, 0.0)

        # Every read/grab fails
        cap.read.return_value = (False, None)
        cap.grab.return_value = False

        mock_cv2.VideoCapture.return_value = cap
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_FRAME_COUNT = 7

        with pytest.raises(VideoProcessingError, match="consecutive"):
            detect_match_boundaries(Path("test.mp4"), min_match_duration=1.0)

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_release_called_on_success(self, mock_vc_class):
        """cap.release() is called after successful processing."""
        cap = _make_capture_mock(fps=30.0, frame_count=9000, default_brightness=128)
        mock_vc_class.return_value = cap

        detect_match_boundaries(Path("test.mp4"), min_match_duration=100.0)
        cap.release.assert_called_once()

    @patch("allaganeye.video.detector.cv2.VideoCapture")
    def test_release_called_on_property_error(self, mock_vc_class):
        """cap.release() is called even when fps/frame_count error occurs."""
        cap = _make_capture_mock(fps=0.0, frame_count=9000)
        mock_vc_class.return_value = cap

        with pytest.raises(VideoProcessingError):
            detect_match_boundaries(Path("test.mp4"))

        cap.release.assert_called_once()
