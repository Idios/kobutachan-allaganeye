"""Tests for match boundary detection."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    MatchBoundary,
    _BLACKOUT_PADDING,
    _FRAME_SIZE,
    _REFINED_MIN_BLACKOUT,
    _REFINE_INTERVAL,
    _REFINE_WINDOW,
    _TRANSITION_THRESHOLD,
    _decode_chunk_cpu,
    _expand_regions_with_transitions,
    _filter_and_extract_segments,
    _generate_timestamps,
    _group_blackout_regions,
    _infer_segment_type,
    _probe_single_frame,
    _refine_blackout_regions,
    detect_match_boundaries,
)


# --- Helpers ---


def _extract_segments(
    blackout_times: list[float],
    total_duration: float,
    sample_interval: float,
    min_match_duration: float,
    min_blackout_duration: float = 3.0,
) -> list[MatchBoundary]:
    """Test helper: groups + filters + extracts (replaces old monolithic function)."""
    regions = _group_blackout_regions(blackout_times, sample_interval)
    return _filter_and_extract_segments(
        regions, total_duration, min_match_duration, min_blackout_duration
    )


def _make_run_result(brightness: int = 128, frame_size: int = _FRAME_SIZE) -> MagicMock:
    """Create a mock subprocess.run result with a single grayscale frame."""
    result = MagicMock()
    result.stdout = bytes([brightness]) * frame_size
    result.returncode = 0
    return result


# ============================================================
# TestExpandWithTransitions
# ============================================================


class TestExpandRegionsWithTransitions:
    """Tests for transition region expansion (#71)."""

    def test_no_regions_unchanged(self):
        result = _expand_regions_with_transitions([], {}, 1.0, 55.0)
        assert result == []

    def test_blackout_followed_by_lobby(self):
        """Blackout followed by low-brightness lobby screen is expanded."""
        all_results = {}
        for t in range(200):
            all_results[float(t)] = 80.0
        all_results[100.0] = 5.0
        all_results[101.0] = 5.0
        for t in range(102, 122):
            all_results[float(t)] = 51.0

        regions = [(100.0, 101.0)]
        result = _expand_regions_with_transitions(regions, all_results, 1.0, 55.0)

        assert len(result) == 1
        assert result[0][0] == 100.0  # no transition before
        assert result[0][1] == 121.0  # expanded to end of lobby

    def test_blackout_followed_by_game_not_expanded(self):
        """Blackout followed by bright game frames is NOT expanded (respawn)."""
        all_results = {}
        for t in range(200):
            all_results[float(t)] = 80.0
        all_results[100.0] = 5.0
        all_results[101.0] = 5.0

        regions = [(100.0, 101.0)]
        result = _expand_regions_with_transitions(regions, all_results, 1.0, 55.0)

        assert result == [(100.0, 101.0)]

    def test_expansion_both_directions(self):
        """Transition frames before and after blackout are included."""
        all_results = {}
        for t in range(50):
            all_results[float(t)] = 80.0
        all_results[18.0] = 50.0
        all_results[19.0] = 50.0
        all_results[20.0] = 5.0
        all_results[21.0] = 5.0
        all_results[22.0] = 50.0
        all_results[23.0] = 50.0

        regions = [(20.0, 21.0)]
        result = _expand_regions_with_transitions(regions, all_results, 1.0, 55.0)

        assert len(result) == 1
        assert result[0][0] == 18.0
        assert result[0][1] == 23.0

    def test_transition_threshold_constant(self):
        assert _TRANSITION_THRESHOLD == 55.0

    def test_expansion_enables_boundary_detection(self):
        """End-to-end: short blackout + lobby passes min_blackout_duration after expansion."""
        all_results = {}
        for t in range(200):
            all_results[float(t)] = 80.0
        all_results[100.0] = 5.0
        all_results[101.0] = 5.0
        for t in range(102, 122):
            all_results[float(t)] = 51.0

        regions = [(100.0, 101.0)]
        expanded = _expand_regions_with_transitions(regions, all_results, 1.0, 55.0)

        segments = _filter_and_extract_segments(
            expanded,
            total_duration=200.0,
            min_match_duration=10.0,
            min_blackout_duration=3.0,
        )
        assert len(segments) == 2


# ============================================================
# TestGroupBlackoutRegions
# ============================================================


class TestGroupBlackoutRegions:
    def test_empty(self):
        assert _group_blackout_regions([], 1.0) == []

    def test_single_timestamp(self):
        result = _group_blackout_regions([100.0], 1.0)
        assert result == [(100.0, 100.0)]

    def test_consecutive_merged(self):
        result = _group_blackout_regions([100.0, 101.0, 102.0], 1.0)
        assert result == [(100.0, 102.0)]

    def test_gap_splits(self):
        result = _group_blackout_regions([100.0, 101.0, 200.0, 201.0], 1.0)
        assert result == [(100.0, 101.0), (200.0, 201.0)]

    def test_tolerance_is_double_interval(self):
        """Timestamps within 2*interval are merged."""
        result = _group_blackout_regions([100.0, 102.0], 1.0)  # gap=2.0, tolerance=2.0
        assert result == [(100.0, 102.0)]

        result = _group_blackout_regions([100.0, 103.0], 1.0)  # gap=3.0 > tolerance=2.0
        assert len(result) == 2


# ============================================================
# TestRefineBlackoutRegions
# ============================================================


class TestRefineBlackoutRegions:
    """Tests for 2nd-pass precise blackout measurement (#77)."""

    def test_constants(self):
        assert _REFINE_INTERVAL == 0.25
        assert _REFINE_WINDOW == 5.0
        assert _REFINED_MIN_BLACKOUT == 1.5

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_empty_regions(self, mock_probe):
        result = _refine_blackout_regions(Path("test.mp4"), [], 15.0, 1000.0)
        assert result == []
        mock_probe.assert_not_called()

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_2s_blackout_detected(self, mock_probe):
        """A 2.0s blackout is precisely measured and retained."""

        def side_effect(path, t):
            # Blackout from 100.0 to 102.0
            return 5.0 if 100.0 <= t < 102.0 else 128.0

        mock_probe.side_effect = side_effect

        regions = [(99.0, 102.0)]  # coarse region from pass 1
        result = _refine_blackout_regions(Path("test.mp4"), regions, 15.0, 1000.0)

        # Should find a refined region ~100.0-101.75
        assert len(result) >= 1
        region = result[0]
        assert region[0] >= 99.0
        assert region[1] <= 103.0
        assert region[1] - region[0] >= _REFINED_MIN_BLACKOUT  # passes threshold

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_1s_respawn_stays_short(self, mock_probe):
        """A 1.0s respawn blackout remains short after refinement."""

        def side_effect(path, t):
            return 5.0 if 100.0 <= t < 101.0 else 128.0

        mock_probe.side_effect = side_effect

        regions = [(100.0, 101.0)]
        result = _refine_blackout_regions(Path("test.mp4"), regions, 15.0, 1000.0)

        # Refined region should be ~0.75s (< 1.8 REFINED_MIN_BLACKOUT)
        assert len(result) >= 1
        region = result[0]
        assert region[1] - region[0] < _REFINED_MIN_BLACKOUT

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_probes_limited_to_window(self, mock_probe):
        """Probes are within +-REFINE_WINDOW of each region."""
        mock_probe.return_value = 128.0

        regions = [(500.0, 502.0)]
        _refine_blackout_regions(Path("test.mp4"), regions, 15.0, 1000.0)

        probed_times = [call[0][1] for call in mock_probe.call_args_list]
        assert all(495.0 <= t <= 507.0 for t in probed_times)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_window_clamped_to_duration(self, mock_probe):
        """Window does not extend beyond 0 or total_duration."""
        mock_probe.return_value = 128.0

        regions = [(2.0, 3.0)]
        _refine_blackout_regions(Path("test.mp4"), regions, 15.0, 6.0)

        probed_times = [call[0][1] for call in mock_probe.call_args_list]
        assert all(0.0 <= t <= 8.0 for t in probed_times)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_video_processing_error_treated_as_non_blackout(self, mock_probe):
        """VideoProcessingError from a future is caught and treated as 255.0."""
        from allaganeye.exceptions import VideoProcessingError

        call_count = 0

        def side_effect(video_path, t):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise VideoProcessingError("ffmpeg not found")
            return 5.0  # dark frame

        mock_probe.side_effect = side_effect

        regions = [(100.0, 102.0)]
        result = _refine_blackout_regions(Path("test.mp4"), regions, 15.0, 1000.0)

        # Should not raise; failed probes are treated as non-blackout (255.0)
        # Some probes succeed (5.0 < 15.0 threshold), so we get a region
        assert isinstance(result, list)


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
        # Short blackout ignored -> entire video is one segment
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
        # 1s blackout kept -> two segments
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

    def test_type_unknown_without_classifications(self):
        """All segments get type=unknown when no classifications provided."""
        blackout_times = [600.0, 601.0, 602.0, 603.0, 604.0]
        result = _extract_segments(
            blackout_times,
            total_duration=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert all(s["type"] == "unknown" for s in result)

    def test_type_fl_match_with_classifications(self):
        """Segments between match_boundary blackouts get type=fl_match."""
        regions = [(100.0, 105.0), (900.0, 905.0)]
        cls = ["match_boundary", "match_boundary"]
        result = _filter_and_extract_segments(
            regions, 1800.0, 300.0, 3.0, classifications=cls
        )
        # Before first blackout: too short (102.5s < 300s) -> excluded
        # Between blackouts: fl_match (both sides match_boundary)
        # After last blackout: unknown (tail segment)
        assert len(result) == 2
        assert result[0]["type"] == "fl_match"
        assert result[1]["type"] == "unknown"

    def test_type_unknown_with_mixed_classifications(self):
        """Segments between non-boundary blackouts get type=unknown."""
        regions = [(100.0, 105.0), (900.0, 905.0)]
        cls = ["match_boundary", "unknown"]
        result = _filter_and_extract_segments(
            regions, 1800.0, 300.0, 3.0, classifications=cls
        )
        assert len(result) == 2
        assert result[0]["type"] == "unknown"

    def test_type_with_in_match_classifications(self):
        """in_match classifications produce fl_match segments."""
        regions = [(100.0, 105.0), (900.0, 905.0)]
        cls = ["in_match", "match_boundary"]
        result = _filter_and_extract_segments(
            regions, 1800.0, 300.0, 3.0, classifications=cls
        )
        assert len(result) == 2
        assert result[0]["type"] == "fl_match"

    def test_classifications_filtered_with_regions(self):
        """Short blackouts are filtered along with their classifications."""
        regions = [(100.0, 101.0), (500.0, 505.0), (1200.0, 1205.0)]
        cls = ["unknown", "match_boundary", "match_boundary"]
        result = _filter_and_extract_segments(
            regions, 1800.0, 300.0, 3.0, classifications=cls
        )
        # First region (1s) filtered out; remaining: match_boundary, match_boundary
        assert len(result) == 3
        assert result[1]["type"] == "fl_match"


# ============================================================
# TestInferSegmentType
# ============================================================


class TestInferSegmentType:
    def test_both_match_boundary(self):
        assert _infer_segment_type("match_boundary", "match_boundary") == "fl_match"

    def test_both_in_match(self):
        assert _infer_segment_type("in_match", "in_match") == "fl_match"

    def test_mixed_boundary_and_in_match(self):
        assert _infer_segment_type("match_boundary", "in_match") == "fl_match"
        assert _infer_segment_type("in_match", "match_boundary") == "fl_match"

    def test_unknown_left(self):
        assert _infer_segment_type("unknown", "match_boundary") == "unknown"

    def test_unknown_right(self):
        assert _infer_segment_type("match_boundary", "unknown") == "unknown"

    def test_both_unknown(self):
        assert _infer_segment_type("unknown", "unknown") == "unknown"

    def test_non_fl(self):
        assert _infer_segment_type("non_fl", "match_boundary") == "unknown"


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

    @patch("allaganeye.video.detector.subprocess.run")
    def test_nonzero_returncode(self, mock_run):
        result = MagicMock()
        result.returncode = 1
        result.stdout = b"\x00" * _FRAME_SIZE  # valid-length but from failed process
        mock_run.return_value = result
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
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_all_black(self, mock_chunk, mock_probe):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 5.0 for t in ts}
        mock_probe.return_value = 5.0  # Pass 2 refinement
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_blackout_in_middle(self, mock_chunk, mock_probe):
        def chunk_side_effect(vp, ts, cs, ce, si):
            return {t: 5.0 if 598.0 <= t <= 602.0 else 128.0 for t in ts}

        mock_chunk.side_effect = chunk_side_effect
        mock_probe.side_effect = lambda path, t: 5.0 if 593.0 <= t <= 607.0 else 128.0
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == pytest.approx(1800.0)

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_custom_threshold(self, mock_chunk):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 20.0 for t in ts}
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            blackout_threshold=15.0,
            min_match_duration=100.0,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_custom_threshold_blackout(self, mock_chunk, mock_probe):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 20.0 for t in ts}
        mock_probe.return_value = 20.0  # Pass 2 refinement
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

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback(self, mock_chunk):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
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

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback_none(self, mock_chunk):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_sample_count(self, mock_chunk):
        """All timestamps are processed across chunks."""
        call_timestamps = []

        def side_effect(vp, ts, cs, ce, si):
            call_timestamps.extend(ts)
            return {t: 128.0 for t in ts}

        mock_chunk.side_effect = side_effect
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            sample_interval=2.0,
            min_match_duration=100.0,
        )
        assert len(set(call_timestamps)) == 150

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_chunked_execution(self, mock_chunk):
        """Multiple chunks are created for parallel execution."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=100.0,
            sample_interval=1.0,
            min_match_duration=10.0,
        )
        assert len(result) == 1
        assert mock_chunk.call_count >= 1

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_scorebar_filtering_called_with_resolution(self, mock_chunk, mock_filter):
        """Scorebar filtering is invoked when src_resolution is provided."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        mock_filter.side_effect = lambda vp, regions, dur, h, w, **kw: (
            regions,
            ["match_boundary"] * len(regions),
        )
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
            src_resolution=(1920, 1080),
        )
        mock_filter.assert_called_once()

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_scorebar_filtering_skipped_without_resolution(
        self, mock_chunk, mock_filter
    ):
        """Scorebar filtering is NOT invoked when src_resolution is None."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
        )
        mock_filter.assert_not_called()

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_audio_hits_forwarded_to_scorebar_filter(self, mock_chunk, mock_filter):
        """audio_hits parameter is passed through to scorebar filtering (#288)."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        mock_filter.side_effect = lambda vp, regions, dur, h, w, **kw: (
            regions,
            ["match_boundary"] * len(regions),
        )
        hits: list[BgmHit] = [{"timestamp": 50.0, "similarity": 0.72}]
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
            src_resolution=(1920, 1080),
            audio_hits=hits,
        )
        mock_filter.assert_called_once()
        assert mock_filter.call_args.kwargs["audio_hits"] == hits

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_audio_hits_default_none_forwarded_as_none(self, mock_chunk, mock_filter):
        """Omitted audio_hits reaches the scorebar filter as None."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si: {t: 128.0 for t in ts}
        mock_filter.side_effect = lambda vp, regions, dur, h, w, **kw: (
            regions,
            ["match_boundary"] * len(regions),
        )
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
            src_resolution=(1920, 1080),
        )
        assert mock_filter.call_args.kwargs["audio_hits"] is None


# ============================================================
# TestDecodeChunkCpu
# ============================================================


class TestDecodeChunkCpu:
    """Tests for _decode_chunk_cpu frame fallback behavior."""

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_truncated_stdout_fills_missing_with_255(self, _mock_ff, mock_run):
        """When ffmpeg returns fewer frames than expected, missing ones get 255.0."""
        timestamps = [0.0, 1.0, 2.0, 3.0]
        # Return only 2 full frames (dark)
        dark_frame = bytes(b"\x00" * _FRAME_SIZE)
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=dark_frame * 2,
            stderr=b"",
        )

        result = _decode_chunk_cpu(Path("test.mp4"), timestamps, 0.0, 4.0, 1.0)

        assert len(result) == 4
        # First 2 timestamps have real brightness (0.0 = all black)
        assert result[0.0] == 0.0
        assert result[1.0] == 0.0
        # Last 2 timestamps filled with 255.0
        assert result[2.0] == 255.0
        assert result[3.0] == 255.0

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_zero_byte_stdout_fills_all_with_255(self, _mock_ff, mock_run):
        """When ffmpeg returns 0 bytes, all timestamps get 255.0."""
        timestamps = [0.0, 1.0, 2.0]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"",
            stderr=b"",
        )

        result = _decode_chunk_cpu(Path("test.mp4"), timestamps, 0.0, 3.0, 1.0)

        assert len(result) == 3
        assert all(v == 255.0 for v in result.values())

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_timeout_fills_all_with_255(self, _mock_ff, mock_run):
        """When ffmpeg times out, all timestamps get 255.0."""
        timestamps = [0.0, 1.0, 2.0]
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)

        result = _decode_chunk_cpu(Path("test.mp4"), timestamps, 0.0, 3.0, 1.0)

        assert len(result) == 3
        assert all(v == 255.0 for v in result.values())
