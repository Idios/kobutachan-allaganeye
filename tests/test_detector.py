"""Tests for match boundary detection."""

from allaganeye.video.detector import _extract_segments


class TestExtractSegments:
    """Unit tests for segment extraction logic (no video files needed)."""

    def test_no_blackouts_long_video(self):
        """No blackouts in a long video → single segment."""
        result = _extract_segments([], total_duration=1200.0, sample_interval=1.0, min_match_duration=300.0)
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1200.0

    def test_no_blackouts_short_video(self):
        """No blackouts in a short video → no segments (below min duration)."""
        result = _extract_segments([], total_duration=100.0, sample_interval=1.0, min_match_duration=300.0)
        assert len(result) == 0

    def test_single_blackout_two_matches(self):
        """Single blackout region splits video into two matches."""
        blackout_times = [600.0, 601.0, 602.0, 603.0]
        result = _extract_segments(
            blackout_times, total_duration=1800.0, sample_interval=1.0, min_match_duration=300.0
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
            blackout_times, total_duration=500.0, sample_interval=1.0, min_match_duration=300.0
        )
        # First segment: 0-100s (too short), second: 101-500s (399s, long enough)
        assert len(result) == 1
        assert result[0]["start"] == 101.0

    def test_multiple_blackouts_three_matches(self):
        """Multiple blackout regions create multiple match segments."""
        blackout_times = [
            # First blackout at ~600s
            600.0, 601.0, 602.0,
            # Second blackout at ~1800s
            1800.0, 1801.0, 1802.0,
        ]
        result = _extract_segments(
            blackout_times, total_duration=3600.0, sample_interval=1.0, min_match_duration=300.0
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
            blackout_times, total_duration=1800.0, sample_interval=1.0, min_match_duration=300.0
        )
        assert len(result) == 2
        assert result[0]["end"] == 600.0
        assert result[1]["start"] == 604.0
