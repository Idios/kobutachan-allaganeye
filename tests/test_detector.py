"""Tests for match boundary detection."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import (
    MatchBoundary,
    _BLACKOUT_PADDING,
    _BLACKOUT_THRESHOLD_UPPER_MARGIN,
    _BORDERLINE_REFINE_RADIUS,
    _ENABLE_BORDERLINE_REFINEMENT,
    _FRAME_SIZE,
    _REFINED_MIN_BLACKOUT,
    _REFINE_INTERVAL,
    _REFINE_WINDOW,
    _TRANSITION_THRESHOLD,
    _borderline_pseudo_regions,
    _decode_chunk_cpu,
    _expand_regions_with_transitions,
    _filter_and_extract_segments,
    _generate_timestamps,
    _group_blackout_regions,
    _infer_segment_type,
    _merge_regions,
    _probe_single_frame,
    _refine_blackout_regions,
    _use_legacy_fps_filter,
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
    def test_progress_callback_fires_per_probe(self, mock_probe):
        """progress_callback is called per probe completion (#366).

        Before #366 the Refining bar froze for the entire Pass 2 wait
        because progress was only reported after the function returned.
        """
        mock_probe.return_value = 128.0
        regions = [(100.0, 102.0)]
        calls: list[tuple[int, int]] = []

        _refine_blackout_regions(
            Path("test.mp4"),
            regions,
            15.0,
            1000.0,
            progress_callback=lambda c, t: calls.append((c, t)),
        )

        # Initial publish + one call per probe
        probe_count = mock_probe.call_count
        assert probe_count > 0
        assert calls[0] == (0, probe_count)
        assert len(calls) == probe_count + 1
        # Monotonically non-decreasing completed counts
        completed_seq = [c for c, _ in calls]
        assert completed_seq == sorted(completed_seq)
        # Total stays constant; final completed equals total
        assert all(t == probe_count for _, t in calls)
        assert calls[-1] == (probe_count, probe_count)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback_not_called_for_empty_regions(self, mock_probe):
        """Empty input short-circuits before any progress is published."""
        calls: list[tuple[int, int]] = []
        _refine_blackout_regions(
            Path("test.mp4"),
            [],
            15.0,
            1000.0,
            progress_callback=lambda c, t: calls.append((c, t)),
        )
        assert calls == []
        mock_probe.assert_not_called()

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback_fires_on_probe_error(self, mock_probe):
        """Progress still advances when a probe raises VideoProcessingError (#366).

        The whole point of #366 is that the Refining bar must keep moving
        during the Pass 2 wait.  If failed probes silently skipped the
        callback, a video with a corrupt region would re-freeze the bar.
        """

        call_count = 0

        def side_effect(video_path, t):
            nonlocal call_count
            call_count += 1
            # Every 3rd probe fails
            if call_count % 3 == 0:
                raise VideoProcessingError("simulated probe failure")
            return 5.0

        mock_probe.side_effect = side_effect
        calls: list[tuple[int, int]] = []
        regions = [(100.0, 102.0)]

        _refine_blackout_regions(
            Path("test.mp4"),
            regions,
            15.0,
            1000.0,
            progress_callback=lambda c, t: calls.append((c, t)),
        )

        probe_count = mock_probe.call_count
        assert probe_count > 0
        # Initial publish + one call per probe, regardless of success/failure
        assert len(calls) == probe_count + 1
        assert calls[0] == (0, probe_count)
        assert calls[-1] == (probe_count, probe_count)
        # Monotonically non-decreasing
        completed_seq = [c for c, _ in calls]
        assert completed_seq == sorted(completed_seq)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback_count_matches_deduplicated_probes(self, mock_probe):
        """Progress total equals dedup'd probe count, not len(blackout_regions).

        Guards against regressing to the old `len(blackout_regions)` semantics:
        overlapping regions share probe timestamps and must be counted once.
        """
        mock_probe.return_value = 128.0
        # Two heavily overlapping regions so probe windows overlap and dedup
        regions = [(100.0, 102.0), (101.0, 103.0)]
        calls: list[tuple[int, int]] = []

        _refine_blackout_regions(
            Path("test.mp4"),
            regions,
            15.0,
            1000.0,
            progress_callback=lambda c, t: calls.append((c, t)),
        )

        probe_count = mock_probe.call_count
        # Total reported must equal the actual (deduplicated) probe count,
        # which is strictly less than the naive sum of per-region windows.
        reported_total = calls[0][1]
        assert reported_total == probe_count
        assert len(calls) == probe_count + 1
        # And crucially: not len(regions).
        assert reported_total != len(regions)

    @patch("allaganeye.video.detector._probe_single_frame")
    def test_progress_callback_contract_holds_with_multiple_workers(self, mock_probe):
        """With workers>1 the callback contract still holds.

        as_completed runs in the main thread so the callback is never
        concurrent, but ordering is non-deterministic.  Verify counts are
        monotonic and final == total regardless.
        """
        mock_probe.return_value = 128.0
        regions = [(100.0, 110.0)]  # wider region => more probes
        calls: list[tuple[int, int]] = []

        _refine_blackout_regions(
            Path("test.mp4"),
            regions,
            15.0,
            1000.0,
            workers=4,
            progress_callback=lambda c, t: calls.append((c, t)),
        )

        probe_count = mock_probe.call_count
        assert probe_count > 1  # must actually exercise parallelism
        assert len(calls) == probe_count + 1
        completed_seq = [c for c, _ in calls]
        assert completed_seq == sorted(completed_seq)
        assert calls[-1] == (probe_count, probe_count)

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
# _filter_and_extract_segments: filter_drops stats wiring (#388)
# ============================================================


class TestFilterDropsStats:
    """Verify the stats param captures drop breakdown (#388)."""

    def test_candidates_count_matches_input(self):
        """filter_candidates == len(blackout_regions) entering the filter."""
        stats: dict = {}
        regions = [(100.0, 105.0), (500.0, 505.0), (1200.0, 1205.0)]
        _filter_and_extract_segments(
            regions,
            1800.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert stats["filter_candidates"] == 3

    def test_no_drops_when_all_segments_pass(self):
        """Every segment >= min_match_duration -> zero drops."""
        stats: dict = {}
        # Two blackouts spaced to give 3 segments each >= 300s.
        regions = [(400.0, 405.0), (800.0, 805.0)]
        _filter_and_extract_segments(
            regions,
            1500.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert stats["filter_drops"] == {
            "below_min_match_duration": 0,
            "other": 0,
        }

    def test_below_min_match_duration_increments_on_short_segment(self):
        """Segments shorter than min_match_duration bump the counter."""
        stats: dict = {}
        # First segment 0-100 (100s), second 150-400 (250s), last 450-500 (50s).
        # All three < min_match_duration=300 -> 3 drops.
        regions = [(100.0, 150.0), (400.0, 450.0)]
        result = _filter_and_extract_segments(
            regions,
            500.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert result == []
        assert stats["filter_drops"]["below_min_match_duration"] == 3
        assert stats["filter_drops"]["other"] == 0

    def test_mixed_pass_and_drop(self):
        """One segment passes, two fail -> candidates=2, drops=2, kept=1."""
        stats: dict = {}
        # seg1: 0-100 (100s, drop), seg2: 150-900 (750s, pass),
        # seg3: 950-1000 (50s, drop).
        regions = [(100.0, 150.0), (900.0, 950.0)]
        result = _filter_and_extract_segments(
            regions,
            1000.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert stats["filter_drops"]["below_min_match_duration"] == 2

    def test_empty_regions_whole_video_short_counts_as_other(self):
        """No blackouts + video shorter than min_match -> 'other' drop."""
        stats: dict = {}
        result = _filter_and_extract_segments(
            [],
            100.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert result == []
        assert stats["filter_drops"]["other"] == 1

    def test_empty_regions_whole_video_long_no_drop(self):
        """No blackouts + video >= min_match -> whole-video match, no drop."""
        stats: dict = {}
        result = _filter_and_extract_segments(
            [],
            1800.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert stats["filter_drops"] == {
            "below_min_match_duration": 0,
            "other": 0,
        }

    def test_stats_none_runs_without_raising(self):
        """When stats is None the function behaves exactly as before."""
        # Sanity: existing callers / tests that don't pass stats must
        # continue to work (backwards-compatibility with the pre-#388
        # signature).
        result = _filter_and_extract_segments([(100.0, 105.0)], 1800.0, 300.0, 3.0)
        assert len(result) >= 1

    def test_below_min_blackout_regions_rolled_into_candidate_count(self):
        """Regions below min_blackout_duration are not candidates.

        They get filtered before the segment loop and don't contribute to
        filter_drops (those live on the Scorebar / min-blackout path above
        this function). The candidate count reflects what's left after
        scorebar but before min-blackout trimming.
        """
        stats: dict = {}
        # 3 regions incoming; one is 1s (< 3s min_blackout) so it gets
        # trimmed, leaving 2 effective blackouts that make 3 segments
        # (0-100 short, 100-900 pass, 900-1000 short).
        regions = [(100.0, 101.0), (100.0, 105.0), (900.0, 905.0)]
        _filter_and_extract_segments(
            regions,
            1000.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert stats["filter_candidates"] == 3


# ============================================================
# _filter_and_extract_segments: filter_unknown stat (#433)
# ============================================================


class TestFilterUnknownStats:
    """Verify the stats param tracks unknown segment count (#433).

    Recordings starting / ending mid-match produce ``type=unknown``
    edge segments. Without a counter the verbose Filter "kept" formula
    is structurally smaller than the Detected count and users assume a
    counting bug.  ``stats["filter_unknown"]`` lets the caller emit a
    ``+ N unknown match`` reconciliation line.
    """

    def test_zero_when_all_segments_are_fl_match(self):
        """fl_match-only result -> filter_unknown == 0.

        Two blackouts framed by classifications produce one between-segment
        typed fl_match. before-first / after-last are absent because the
        outer regions hug 0s and total_duration.
        """
        stats: dict = {}
        regions = [(0.0, 5.0), (1500.0, 1505.0)]
        classifications = ["match_boundary", "match_boundary"]
        result = _filter_and_extract_segments(
            regions,
            1505.0,
            300.0,
            3.0,
            classifications=classifications,
            stats=stats,  # type: ignore[arg-type]
        )
        assert all(s["type"] == "fl_match" for s in result)
        assert stats["filter_unknown"] == 0

    def test_counts_before_first_unknown_edge(self):
        """Recording started mid-match -> 1 unknown before first blackout."""
        stats: dict = {}
        # First blackout at 1000s leaves a 0-1000 unknown edge segment.
        regions = [(1000.0, 1005.0), (1500.0, 1505.0)]
        classifications = ["match_boundary", "match_boundary"]
        result = _filter_and_extract_segments(
            regions,
            1800.0,
            300.0,
            3.0,
            classifications=classifications,
            stats=stats,  # type: ignore[arg-type]
        )
        unknowns = [s for s in result if s["type"] == "unknown"]
        assert len(unknowns) == 1
        assert stats["filter_unknown"] == 1

    def test_counts_whole_video_fallback_unknown(self):
        """No blackouts but video >= min_match -> 1 unknown whole-video segment."""
        stats: dict = {}
        result = _filter_and_extract_segments(
            [],
            1800.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert result[0]["type"] == "unknown"
        assert stats["filter_unknown"] == 1

    def test_zero_on_empty_drop_path(self):
        """No segments returned -> filter_unknown == 0 (defensive)."""
        stats: dict = {}
        # Whole-video shorter than min_match -> [] returned via 'other' drop.
        result = _filter_and_extract_segments(
            [],
            100.0,
            300.0,
            3.0,
            stats=stats,  # type: ignore[arg-type]
        )
        assert result == []
        assert stats["filter_unknown"] == 0

    def test_stats_none_runs_without_raising(self):
        """When stats is None the unknown counter is silently skipped."""
        # Backwards-compat with callers that don't pass stats.
        result = _filter_and_extract_segments([(100.0, 105.0)], 1800.0, 300.0, 3.0)
        # Result still contains unknown edges; just the stat isn't recorded.
        assert any(s["type"] == "unknown" for s in result)


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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 5.0 for t in ts
        }
        mock_probe.return_value = 5.0  # Pass 2 refinement
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 0

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_blackout_in_middle(self, mock_chunk, mock_probe):
        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 20.0 for t in ts
        }
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 20.0 for t in ts
        }
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
    def test_brightness_callback_receives_pass1_results(self, mock_chunk):
        """#569 -- brightness_callback fires once with full Pass 1 map."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 50.0 + t for t in ts
        }
        captured: list[dict[float, float]] = []
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            brightness_callback=captured.append,
        )
        # Exactly one fire (single-shot contract).
        assert len(captured) == 1
        # Captured map covers every sample timestamp.
        results = captured[0]
        assert len(results) == 10
        assert results[0.0] == pytest.approx(50.0)
        assert results[5.0] == pytest.approx(55.0)

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_brightness_callback_optional_default(self, mock_chunk):
        """Omitting the callback is a no-op (preserves pre-#569 callers)."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 100.0 for t in ts
        }
        # Should not raise even without the new kwarg.
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
        )
        assert isinstance(result, list)

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_stats_populated_cpu(self, mock_chunk):
        """Verbose callers receive pipeline statistics (issue #336 Phase 1)."""
        from allaganeye.video.detector import DetectionStats

        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
        stats: DetectionStats = {}
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            stats=stats,
        )
        assert stats.get("mode") == "CPU"
        assert stats.get("pass1_samples") == 10
        assert stats.get("pass1_blackout_frames") == 0
        assert "pass1_elapsed_s" in stats
        assert "pass2_regions" in stats
        assert "pass2_elapsed_s" in stats

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_stats_scorebar_counts(self, mock_chunk, mock_probe):
        """Scorebar classification counts flow through to stats."""
        from allaganeye.video.detector import DetectionStats

        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 5.0 if 598.0 <= t <= 602.0 else 128.0 for t in ts
        }
        mock_probe.side_effect = lambda path, t: 5.0 if 593.0 <= t <= 607.0 else 128.0
        with patch(
            "allaganeye.video.scorebar.filter_blackouts_with_scorebar"
        ) as mock_filter:

            def filter_side_effect(
                video_path,
                regions,
                duration,
                height,
                workers,
                *,
                audio_hits,
                stats,
                progress_callback=None,
            ):
                if stats is not None:
                    stats["scorebar_match_boundary"] = 1
                    stats["scorebar_in_match"] = 2
                    stats["scorebar_non_fl"] = 3
                    stats["scorebar_unknown"] = 0
                    stats["audio_promotions"] = 1
                return regions, ["match_boundary"] * len(regions)

            mock_filter.side_effect = filter_side_effect
            stats: DetectionStats = {}
            detect_match_boundaries(
                Path("test.mp4"),
                duration_hint=1800.0,
                sample_interval=1.0,
                min_match_duration=300.0,
                src_resolution=(1920, 1080),
                stats=stats,
            )
        assert stats.get("scorebar_match_boundary") == 1
        assert stats.get("scorebar_in_match") == 2
        assert stats.get("scorebar_non_fl") == 3
        assert stats.get("audio_promotions") == 1

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback(self, mock_chunk):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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
    def test_refine_progress_callback(self, mock_chunk):
        """refine_progress_callback fires during Pass 2 (#328).

        Contract: called per blackout region discovered in Pass 1, with
        (completed, total) arguments.  total matches the number of
        regions (no scorebar phase here since src_resolution=None).
        """

        # Single blackout region at t=5 (below threshold)
        def side_effect(vp, ts, cs, ce, si, **kwargs):
            return {t: 0.0 if 4.0 <= t <= 6.0 else 128.0 for t in ts}

        mock_chunk.side_effect = side_effect
        refine_calls: list[tuple[int, int]] = []
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            refine_progress_callback=lambda c, t: refine_calls.append((c, t)),
        )
        # At least one refine callback for the detected region
        assert len(refine_calls) >= 1
        # completed counts are bounded by total.  The initial probe publish
        # uses (0, total) before any probe completes (#366), so 0 is allowed.
        for completed, total in refine_calls:
            assert 0 <= completed <= total
        # final completed == total (all refine steps reported)
        assert refine_calls[-1][0] == refine_calls[-1][1]

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_refine_progress_delivered_per_probe_through_detector(
        self, mock_chunk, mock_probe
    ):
        """End-to-end #366 contract: UI receives per-probe updates, not a batch.

        Before #366, detect_match_boundaries called `_refine_step()` in a
        tight loop *after* Pass 2 returned, producing len(blackout_regions)
        batched calls.  After #366, each probe must surface as an individual
        callback invocation so the Refining bar advances during the wait.

        This test pins that contract at the detect_match_boundaries level:
        the number of refine callbacks must equal the number of actual
        probes + 1 (initial publish), which is always strictly greater than
        len(blackout_regions) for non-trivial regions.
        """

        # One blackout region around t=5.
        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
            return {t: 0.0 if 4.0 <= t <= 6.0 else 128.0 for t in ts}

        mock_chunk.side_effect = chunk_side_effect
        mock_probe.return_value = 128.0

        refine_calls: list[tuple[int, int]] = []
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            refine_progress_callback=lambda c, t: refine_calls.append((c, t)),
        )

        probe_count = mock_probe.call_count
        assert probe_count > 1, "test needs multiple probes to be meaningful"

        # The critical regression guard: we must have received at least one
        # callback per probe (plus the initial publish).  If someone reverts
        # to the pre-#366 "batch after Pass 2" shape, this count drops to
        # len(blackout_regions) == 1 and the assertion fails.
        assert len(refine_calls) >= probe_count + 1
        assert refine_calls[0] == (0, probe_count)

        # Completed count strictly increases at some point during Pass 2,
        # i.e. at least one (completed, total) pair with 0 < completed < total
        # appears before the final one -- proving delivery was not batched.
        intermediate = [(c, t) for c, t in refine_calls if 0 < c < t]
        assert intermediate, (
            "no intermediate progress was published; callbacks appear batched"
        )

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback_none(self, mock_chunk):
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_sample_count(self, mock_chunk):
        """All timestamps are processed across chunks."""
        call_timestamps = []

        def side_effect(vp, ts, cs, ce, si, **kwargs):
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
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


# ============================================================
# TestPass1HysteresisAndBorderline (#361)
# ============================================================


class TestPass1HysteresisConstants:
    """Constants for A4 hysteresis and A3 borderline refinement (#361)."""

    def test_upper_margin_default(self):
        assert _BLACKOUT_THRESHOLD_UPPER_MARGIN == 2.0

    def test_borderline_refinement_enabled_by_default(self):
        assert _ENABLE_BORDERLINE_REFINEMENT is True

    def test_borderline_refine_radius(self):
        assert _BORDERLINE_REFINE_RADIUS == 3.0


class TestBorderlinePseudoRegions:
    """Unit tests for _borderline_pseudo_regions (A3, #361)."""

    def test_empty_results(self):
        assert _borderline_pseudo_regions({}, 15.0, 1000.0) == []

    def test_no_borderline_frames(self):
        """All frames outside [threshold, threshold*2) -> no pseudo regions."""
        results = {0.0: 128.0, 10.0: 5.0, 20.0: 200.0}
        assert _borderline_pseudo_regions(results, 15.0, 1000.0) == []

    def test_borderline_frame_creates_window(self):
        """A single borderline frame at 15.13 creates a +-3s window."""
        results = {100.0: 15.13}
        regions = _borderline_pseudo_regions(results, 15.0, 1000.0)
        assert regions == [(97.0, 103.0)]

    def test_window_clamped_to_start(self):
        """Window does not go below 0.0."""
        results = {1.0: 20.0}
        regions = _borderline_pseudo_regions(results, 15.0, 1000.0)
        assert regions[0][0] == 0.0
        assert regions[0][1] == 4.0

    def test_window_clamped_to_duration(self):
        """Window does not exceed total_duration."""
        results = {999.0: 20.0}
        regions = _borderline_pseudo_regions(results, 15.0, 1000.0)
        assert regions[0][0] == 996.0
        assert regions[0][1] == 1000.0

    def test_upper_bound_exclusive(self):
        """Frames at exactly 2 * threshold are not borderline."""
        results = {100.0: 30.0}  # == threshold * 2
        assert _borderline_pseudo_regions(results, 15.0, 1000.0) == []

    def test_lower_bound_inclusive(self):
        """Frames at exactly threshold are borderline."""
        results = {100.0: 15.0}
        regions = _borderline_pseudo_regions(results, 15.0, 1000.0)
        assert len(regions) == 1


class TestMergeRegions:
    """Unit tests for _merge_regions (A3 helper, #361)."""

    def test_empty(self):
        assert _merge_regions([], 1.0) == []

    def test_single_region(self):
        assert _merge_regions([(10.0, 20.0)], 1.0) == [(10.0, 20.0)]

    def test_overlapping_merged(self):
        result = _merge_regions([(10.0, 20.0), (15.0, 25.0)], 1.0)
        assert result == [(10.0, 25.0)]

    def test_adjacent_within_tolerance_merged(self):
        """Gap <= 2*sample_interval merges."""
        result = _merge_regions([(10.0, 20.0), (21.5, 25.0)], 1.0)  # gap 1.5 < 2.0
        assert result == [(10.0, 25.0)]

    def test_far_apart_kept_separate(self):
        result = _merge_regions([(10.0, 20.0), (100.0, 110.0)], 1.0)
        assert result == [(10.0, 20.0), (100.0, 110.0)]

    def test_unsorted_input(self):
        """Regions are sorted before merging."""
        result = _merge_regions([(100.0, 110.0), (10.0, 20.0)], 1.0)
        assert result == [(10.0, 20.0), (100.0, 110.0)]


class TestPass1HysteresisIntegration:
    """Integration of A4 hysteresis and A3 refinement in detect_match_boundaries."""

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_upper_margin_catches_borderline_blackout(self, mock_chunk, mock_probe):
        """A4: Pass 1 frame at brightness 15.5 is treated as blackout with margin=2.0.

        With strict threshold 15.0 this frame would not pass Pass 1.  With
        the upper hysteresis margin, it enters the blackout set.  Pass 2
        is mocked to confirm blackout, so the boundary is retained.
        """

        # Put borderline frames in the middle, bright frames elsewhere.
        # Pass 1 runs at 3s interval (default), so frames at 600-609 become
        # a 10s borderline span.
        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
            return {t: 15.5 if 600.0 <= t <= 609.0 else 128.0 for t in ts}

        mock_chunk.side_effect = chunk_side_effect
        # Pass 2 confirms blackout (<15.0 strict) in the same span
        mock_probe.side_effect = lambda p, t: 5.0 if 599.0 <= t <= 610.0 else 128.0

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=3.0,
            min_match_duration=300.0,
        )

        # With A4, borderline Pass 1 frames trigger Pass 2, which confirms
        # the blackout and splits the video into two matches.
        assert len(result) == 2

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_borderline_triggers_refinement_around_missed_blackout(
        self, mock_chunk, mock_probe
    ):
        """A3: Pass 1 borderline frames trigger Pass 2 +-3s refinement.

        Simulates the #330 scenario: Pass 1 at 3s interval returns 20.0 at
        t=8139 (borderline, not blackout).  No frame crosses the strict
        threshold in Pass 1, so without A3 there is no blackout region.
        With A3, a pseudo-region (8136, 8142) is added and Pass 2 probes
        at 0.25s intervals -- finding the real short blackout at 8137-8140.
        """

        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
            # t=8139 is borderline; surrounding Pass 1 samples are bright
            out = {}
            for t in ts:
                if t == 8139.0:
                    out[t] = 20.0  # borderline: in [15, 30)
                else:
                    out[t] = 128.0
            return out

        mock_chunk.side_effect = chunk_side_effect
        # Pass 2 at 0.25s finds real blackout 8137.25-8139.75
        mock_probe.side_effect = lambda p, t: 2.0 if 8137.25 <= t <= 8139.75 else 128.0

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10000.0,
            sample_interval=3.0,
            min_match_duration=300.0,
        )

        # Confirm Pass 2 was asked to probe around the borderline timestamp
        probed = [c.args[1] for c in mock_probe.call_args_list]
        near_borderline = [t for t in probed if 8136.0 <= t <= 8142.0]
        assert near_borderline, (
            "Expected Pass 2 probes around borderline t=8139, "
            f"but probed: {sorted(set(probed))[:10]}..."
        )

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_borderline_refinement_disabled_skips_pseudo_regions(
        self, mock_chunk, mock_probe
    ):
        """With _ENABLE_BORDERLINE_REFINEMENT=False, no pseudo regions added."""

        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
            return {t: 20.0 if t == 8139.0 else 128.0 for t in ts}

        mock_chunk.side_effect = chunk_side_effect
        mock_probe.return_value = 128.0

        with patch("allaganeye.video.detector._ENABLE_BORDERLINE_REFINEMENT", False):
            detect_match_boundaries(
                Path("test.mp4"),
                duration_hint=10000.0,
                sample_interval=3.0,
                min_match_duration=300.0,
            )

        probed = [c.args[1] for c in mock_probe.call_args_list]
        # No Pass 2 probes around 8139 since no blackout region was created
        near_borderline = [t for t in probed if 8136.0 <= t <= 8142.0]
        assert not near_borderline

    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_upper_margin_zero_restores_strict_threshold(self, mock_chunk, mock_probe):
        """With _BLACKOUT_THRESHOLD_UPPER_MARGIN=0.0, only b<threshold is blackout."""

        def chunk_side_effect(vp, ts, cs, ce, si, **kwargs):
            # Make one frame borderline (15.5) but otherwise bright.
            # Also disable A3 so only A4 behavior is under test.
            return {t: 15.5 if 600.0 <= t <= 609.0 else 128.0 for t in ts}

        mock_chunk.side_effect = chunk_side_effect
        mock_probe.return_value = 128.0  # Pass 2 finds no blackout

        with (
            patch("allaganeye.video.detector._BLACKOUT_THRESHOLD_UPPER_MARGIN", 0.0),
            patch("allaganeye.video.detector._ENABLE_BORDERLINE_REFINEMENT", False),
        ):
            result = detect_match_boundaries(
                Path("test.mp4"),
                duration_hint=1800.0,
                sample_interval=3.0,
                min_match_duration=300.0,
            )

        # Borderline not captured -> single match spans whole video
        assert len(result) == 1


class TestUseLegacyFpsFilter:
    """env var rollback helper (#576 §6)."""

    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)
        assert _use_legacy_fps_filter() is False

    def test_explicit_1_returns_true(self, monkeypatch):
        monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")
        assert _use_legacy_fps_filter() is True

    def test_other_values_return_false(self, monkeypatch):
        for value in ("0", "true", "yes", "", "2"):
            monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", value)
            assert _use_legacy_fps_filter() is False, f"value={value!r}"


class TestConftestEnvVarAutouse:
    """conftest.py autouse fixture clears ALLAGANEYE_DETECT_FPS_FILTER (#576 §6)."""

    def test_env_var_unset_by_default(self):
        # autouse fixture should have unset it before this test runs.
        assert "ALLAGANEYE_DETECT_FPS_FILTER" not in os.environ, (
            "conftest autouse should unset ALLAGANEYE_DETECT_FPS_FILTER. "
            "CI pollution risk (#576 R6)."
        )


# ---------------------------------------------------------------------------
# _sample_chunk_frames / _resolve_fps_rational (#576 §2.2 / §2.3)
# ---------------------------------------------------------------------------

import io  # noqa: E402 -- placed here to keep new test section self-contained

from allaganeye.video.detector import (  # noqa: E402
    _FRAME_SIZE as _FS,
    _resolve_fps_rational,
    _sample_chunk_frames,
)


def _frames_bytes(brightnesses: list[int]) -> bytes:
    """Build a raw grayscale frame stream from per-frame mean brightness."""
    return b"".join(bytes([b]) * _FS for b in brightnesses)


class TestSampleChunkFramesRationalMapping:
    """rational fps での frame_idx mapping (#576 §2.2 / §7.1.2)."""

    def test_integer_60fps(self):
        # source_fps=60/1, chunk_start=10.0, targets {10.0, 12.0, 14.0}
        # frame_idx {0, 120, 240}
        # expected_frames=241 (> max frame_idx=240); stream has 241 frames so
        # VFR check sees diff=0 and does not fire.
        stream = io.BytesIO(_frames_bytes([100] * 241))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=10.0,
            chunk_timestamps=[10.0, 12.0, 14.0],
            fps_num=60,
            fps_den=1,
            expected_frames=241,  # > max frame_idx (240), stream matches
            is_tail_chunk=False,
        )
        assert result == {10.0: 100.0, 12.0: 100.0, 14.0: 100.0}

    def test_ntsc_59_94(self):
        # source_fps=60000/1001 (=59.94...), chunk_start=0.0, targets {0.0, 10.0}
        # frame_idx {0, round(10 * 60000 / 1001)} = {0, 599}
        # 599 + 1 = 600 frames minimum; stream has 600 frames (exact match)
        stream = io.BytesIO(_frames_bytes([50] * 600))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 10.0],
            fps_num=60000,
            fps_den=1001,
            expected_frames=600,
            is_tail_chunk=False,
        )
        assert 0.0 in result and 10.0 in result
        assert result[0.0] == 50.0
        assert result[10.0] == 50.0


class TestSampleChunkFramesFrameMissing:
    """frame_idx >= 利用可能 frame 数 のとき 255.0 fallback (#576 §4.3 / §7.1.4)."""

    def test_target_beyond_available_frames(self):
        # 100 frames available, target wants frame_idx 200 -> fallback to 255.0
        stream = io.BytesIO(_frames_bytes([0] * 100))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 10.0],  # 10.0 * 60 = 600 > 100
            fps_num=60,
            fps_den=1,
            expected_frames=600,
            is_tail_chunk=True,  # tail なので動的 VFR check も WARN のみ
        )
        assert result[0.0] == 0.0
        assert result[10.0] == 255.0


class TestSampleChunkFramesDynamicVfr:
    """動的 VFR 検出: slack 超過時 raise / tail chunk は WARN のみ (#576 §2.2 / §7.1.5)."""

    def test_within_slack_no_error(self):
        # 60fps × 60s = 3600 expected, slack = max(36, 6) = 36
        # emit 3580 = -20 (within slack), should not raise
        stream = io.BytesIO(_frames_bytes([100] * 3580))
        _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 30.0],
            fps_num=60,
            fps_den=1,
            expected_frames=3600,
            is_tail_chunk=False,
        )
        # no raise expected

    def test_exceeds_slack_non_tail_raises(self):
        # 60fps × 60s = 3600 expected, slack = max(36, 6) = 36
        # emit 3500 = -100 (exceeds slack), non-tail chunk -> raise
        stream = io.BytesIO(_frames_bytes([100] * 3500))
        with pytest.raises(VideoProcessingError) as excinfo:
            _sample_chunk_frames(
                stream=stream,
                chunk_start=0.0,
                chunk_timestamps=[0.0, 30.0],
                fps_num=60,
                fps_den=1,
                expected_frames=3600,
                is_tail_chunk=False,
            )
        assert "Dynamic VFR" in str(excinfo.value)

    def test_exceeds_slack_tail_only_warns(self, caplog):
        # Same overshoot but tail chunk -> WARN only, no raise.
        import logging as _logging

        stream = io.BytesIO(_frames_bytes([100] * 3500))
        with caplog.at_level(_logging.WARNING):
            _sample_chunk_frames(
                stream=stream,
                chunk_start=0.0,
                chunk_timestamps=[0.0, 30.0],
                fps_num=60,
                fps_den=1,
                expected_frames=3600,
                is_tail_chunk=True,
            )
        msgs = [
            r.getMessage()
            for r in caplog.records
            if "VFR" in r.getMessage() or "tail" in r.getMessage()
        ]
        assert any("tail" in m or "VFR" in m for m in msgs), (
            f"expected WARN for tail chunk, got: {[r.getMessage() for r in caplog.records]}"
        )


class TestSampleChunkFramesFloatFallback:
    """float source_fps を Fraction.limit_denominator(10000) で rational に
    変換した場合、NTSC rational と同じ frame_idx を選ぶこと (#576 §2.3 / §7.1.3)."""

    def test_float_59_94_yields_ntsc_index(self):
        num, den = _resolve_fps_rational(None, None, 60000 / 1001)
        # Fraction(60000/1001).limit_denominator(10000) -> 60000/1001 exactly
        assert (num, den) == (60000, 1001)

    def test_float_60_yields_60_over_1(self):
        num, den = _resolve_fps_rational(None, None, 60.0)
        # Fraction(60.0).limit_denominator(10000) -> 60/1
        assert (num, den) == (60, 1)


class TestResolveFpsRationalPositivityCheck:
    """(0, 1) のような half-zero rational は float fallback を使うこと (#576 fix)."""

    def test_zero_num_falls_back_to_float(self):
        # fps_num=0 is invalid; must fall back to source_fps float
        num, den = _resolve_fps_rational(0, 1, 60.0)
        assert (num, den) == (60, 1)

    def test_zero_den_falls_back_to_float(self):
        # fps_den=0 would cause ZeroDivisionError if used; must fall back
        num, den = _resolve_fps_rational(60, 0, 60.0)
        assert (num, den) == (60, 1)

    def test_zero_zero_sentinel_falls_back_to_float(self):
        # probe.py parse failure sentinel (0, 0) -> fall through to float
        num, den = _resolve_fps_rational(0, 0, 60000 / 1001)
        assert (num, den) == (60000, 1001)

    def test_valid_rational_used_directly(self):
        # positive (num, den) must still be returned as-is
        num, den = _resolve_fps_rational(60, 1, 30.0)
        assert (num, den) == (60, 1)


class TestSampleChunkFramesStreamingMemory:
    """フレームを逐次処理し全フレームをバッファに蓄積しないこと (spec §2.2 memory budget fix)."""

    def test_does_not_buffer_all_frames(self):
        """Only the needed frames produce brightness values; the rest are discarded."""
        # 3600 frames at 60fps (= 60s chunk), but we only ask for frame 0 and frame 60
        # (i.e. timestamps 0.0 and 1.0).  All other frames should be discarded.
        n_frames = 3600
        # frame 0 brightness=10, frame 60 brightness=200, all others=128
        raw = (
            bytes([10]) * _FS
            + bytes([128]) * _FS * 59
            + bytes([200]) * _FS
            + bytes([128]) * _FS * (n_frames - 61)
        )
        stream = io.BytesIO(raw)
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 1.0],
            fps_num=60,
            fps_den=1,
            expected_frames=n_frames,
            is_tail_chunk=False,
        )
        assert result[0.0] == pytest.approx(10.0)
        assert result[1.0] == pytest.approx(200.0)

    def test_stream_none_raises(self):
        """None stream raises VideoProcessingError immediately."""
        with pytest.raises(VideoProcessingError, match="ffmpeg stdout not available"):
            _sample_chunk_frames(
                stream=None,
                chunk_start=0.0,
                chunk_timestamps=[0.0],
                fps_num=60,
                fps_den=1,
                expected_frames=1,
                is_tail_chunk=False,
            )


# ---------------------------------------------------------------------------
# _decode_chunk_cpu v2 path + env var dispatch (#576 §2.1 / §6 / §7.1.1 / §7.1.7)
# ---------------------------------------------------------------------------

import io as _io  # noqa: E402 -- placed here to keep new test section self-contained


class TestDecodeChunkCpuNewPath:
    """_decode_chunk_cpu 新 path の cmd 構築検証 (#576 §2.1 / §7.1.1)."""

    @patch("allaganeye.video.detector.subprocess.Popen")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_cmd_uses_output_seek_no_fps_passthrough(
        self, _mock_ff, mock_popen, monkeypatch
    ):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        # 60s @ 60fps = 3600 frames; emit exactly that
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FRAME_SIZE * 3600))
        mock_proc.stderr = _io.BytesIO(b"")
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value.__enter__.return_value = mock_proc

        _decode_chunk_cpu(
            Path("test.mp4"),
            chunk_timestamps=[0.0, 1.0, 2.0],
            chunk_start=0.0,
            chunk_end=60.0,
            sample_interval=1.0,
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        called_cmd = mock_popen.call_args[0][0]
        # output seek: -ss must come AFTER -i, not before
        i_idx = called_cmd.index("-i")
        ss_idx = called_cmd.index("-ss")
        assert ss_idx > i_idx, f"-ss must follow -i (output seek), got {called_cmd}"
        # no fps= in -vf
        vf_idx = called_cmd.index("-vf")
        vf_value = called_cmd[vf_idx + 1]
        assert "fps=" not in vf_value, (
            f"fps filter must be removed, got -vf {vf_value!r}"
        )
        # -fps_mode passthrough explicit
        assert "-fps_mode" in called_cmd, "missing -fps_mode passthrough"
        fps_mode_idx = called_cmd.index("-fps_mode")
        assert called_cmd[fps_mode_idx + 1] == "passthrough"


class TestDecodeChunkCpuV2NonzeroReturncode:
    """returncode != 0 で 255.0 fallback + WARNING ログ (#576 bug fix)."""

    @patch("allaganeye.video.detector.subprocess.Popen")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_nonzero_returncode_returns_255_fallback(
        self, _mock_ff, mock_popen, monkeypatch, caplog
    ):
        """proc.returncode != 0 → 255.0 fallback, no ValueError from closed pipe."""
        import logging

        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        # 3s @ 60fps = 180 frames; emit exactly that so _sample_chunk_frames succeeds,
        # then returncode=1 triggers the 255.0 fallback path we are testing.
        mock_proc.stdout = _io.BytesIO(bytes([128]) * _FRAME_SIZE * 180)
        mock_proc.stderr = _io.BytesIO(b"error: some ffmpeg failure")
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_popen.return_value.__enter__.return_value = mock_proc

        timestamps = [0.0, 1.0, 2.0]
        with caplog.at_level(logging.WARNING, logger="allaganeye.video.detector"):
            result = _decode_chunk_cpu(
                Path("test.mp4"),
                chunk_timestamps=timestamps,
                chunk_start=0.0,
                chunk_end=3.0,
                sample_interval=1.0,
                source_fps_num=60,
                source_fps_den=1,
                is_tail_chunk=False,
            )

        # All timestamps must map to 255.0 (safe non-blackout fallback)
        assert result == {0.0: 255.0, 1.0: 255.0, 2.0: 255.0}, (
            f"Expected all 255.0 fallback, got {result}"
        )
        # A WARNING must be logged containing the stderr snippet
        warning_messages = [
            r.message for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert any("error: some ffmpeg failure" in m for m in warning_messages), (
            f"Expected stderr snippet in WARNING log, got: {warning_messages}"
        )


class TestDecodeChunkCpuLegacyRollback:
    """env var=1 で旧 fps filter cmd が生成されること (#576 §6 / §7.1.7)."""

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_legacy_cmd_used_when_env_set(self, _mock_ff, mock_run, monkeypatch):
        monkeypatch.setenv("ALLAGANEYE_DETECT_FPS_FILTER", "1")
        mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")

        _decode_chunk_cpu(
            Path("test.mp4"),
            chunk_timestamps=[0.0, 1.0, 2.0],
            chunk_start=0.0,
            chunk_end=3.0,
            sample_interval=1.0,
            source_fps_num=60,
            source_fps_den=1,
            is_tail_chunk=False,
        )

        called_cmd = mock_run.call_args[0][0]
        # legacy: -ss before -i
        i_idx = called_cmd.index("-i")
        ss_idx = called_cmd.index("-ss")
        assert ss_idx < i_idx, f"legacy -ss must precede -i, got {called_cmd}"
        # legacy: fps= present in -vf
        vf_idx = called_cmd.index("-vf")
        vf_value = called_cmd[vf_idx + 1]
        assert "fps=" in vf_value, f"legacy must keep fps filter, got -vf {vf_value!r}"
