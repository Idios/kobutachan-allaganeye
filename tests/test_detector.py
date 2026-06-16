"""Tests for match boundary detection."""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from allaganeye.audio.matcher import BgmHit
from allaganeye.exceptions import VideoProcessingError
from allaganeye.video import detector as det
from allaganeye.video.capture_region import FULL_FRAME, CaptureRegion
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
    _drop_post_match_trailing,
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

        def side_effect(path, t, region=FULL_FRAME):
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

        def side_effect(path, t, region=FULL_FRAME):
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

        def side_effect(video_path, t, region=FULL_FRAME):
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

        def side_effect(video_path, t, region=FULL_FRAME):
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
    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._probe_single_frame")
    def test_all_bright(self, mock_probe, _mock_region):
        # _mock_region: zero-blackout Pass 1 now routes through the masked
        # fallback gate (#753 A5); stub the region resolver to FULL_FRAME so the
        # masked path returns None and falls through to the standard result
        # without spawning real ffmpeg probes (kept fast/deterministic).
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
        mock_probe.side_effect = lambda path, t, region=FULL_FRAME: (
            5.0 if 593.0 <= t <= 607.0 else 128.0
        )
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
        )
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == pytest.approx(1800.0)

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_custom_threshold(self, mock_chunk, _mock_region):
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub
        # falls through to standard result (no real ffmpeg probes).
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_brightness_callback_receives_pass1_results(self, mock_chunk, _mock_region):
        """#569 -- brightness_callback fires once with full Pass 1 map."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_brightness_callback_optional_default(self, mock_chunk, _mock_region):
        """Omitting the callback is a no-op (preserves pre-#569 callers)."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._detect_masked_fallback")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_masked_fallback_callback_fires_when_result_used(
        self, mock_chunk, mock_fallback
    ):
        """fallback の結果が採用されたときのみ callback が発火 (resolved provenance).

        request flag (masked) と resolved path を分離するための通知 seam。
        brightness_callback (#569/#644) と同型の配線。
        """
        # zero-blackout -> gate (not vtuber and not blackout_times) が fallback へ
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 100.0 for t in ts
        }
        fallback_result = [{"start": 0.0, "end": 9.0, "type": "fl_match"}]
        mock_fallback.return_value = fallback_result
        fired: list[bool] = []
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            masked_fallback_callback=lambda: fired.append(True),
        )
        assert result == fallback_result
        assert fired == [True]

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_masked_fallback_callback_not_fired_when_fallback_gives_up(
        self, mock_chunk, _mock_region
    ):
        """fallback が None (縮退) で標準 path に落ちた場合は callback 不発."""
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 100.0 for t in ts
        }
        fired: list[bool] = []
        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=10.0,
            sample_interval=1.0,
            min_match_duration=1.0,
            masked_fallback_callback=lambda: fired.append(True),
        )
        assert isinstance(result, list)
        assert fired == []

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_stats_populated_cpu(self, mock_chunk, _mock_region):
        """Verbose callers receive pipeline statistics (issue #336 Phase 1)."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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
        mock_probe.side_effect = lambda path, t, region=FULL_FRAME: (
            5.0 if 593.0 <= t <= 607.0 else 128.0
        )
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
                band_region=FULL_FRAME,
                localize=False,
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback(self, mock_chunk, _mock_region):
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_progress_callback_none(self, mock_chunk, _mock_region):
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
        result = detect_match_boundaries(
            Path("test.mp4"), duration_hint=300.0, min_match_duration=100.0
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_sample_count(self, mock_chunk, _mock_region):
        """All timestamps are processed across chunks."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_chunked_execution(self, mock_chunk, _mock_region):
        """Multiple chunks are created for parallel execution."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_scorebar_filtering_called_with_resolution(
        self, mock_chunk, mock_filter, _mock_region
    ):
        """Scorebar filtering is invoked when src_resolution is provided."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub
        # so the masked path returns None and the standard scorebar call still
        # fires exactly once (assertion below unchanged).
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_scorebar_filtering_skipped_without_resolution(
        self, mock_chunk, mock_filter, _mock_region
    ):
        """Scorebar filtering is NOT invoked when src_resolution is None."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub
        # -> masked path returns None before its own scorebar call, so
        # assert_not_called() still holds.
        mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kwargs: {
            t: 128.0 for t in ts
        }
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=300.0,
            min_match_duration=100.0,
        )
        mock_filter.assert_not_called()

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_audio_hits_forwarded_to_scorebar_filter(
        self, mock_chunk, mock_filter, _mock_region
    ):
        """audio_hits parameter is passed through to scorebar filtering (#288)."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_audio_hits_default_none_forwarded_as_none(
        self, mock_chunk, mock_filter, _mock_region
    ):
        """Omitted audio_hits reaches the scorebar filter as None."""
        # _mock_region: zero-blackout -> masked gate (#753 A5); FULL_FRAME stub.
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
        """All frames outside [threshold, _TRANSITION_THRESHOLD) -> no pseudo regions.

        #576 A5: upper bound extended from blackout_threshold * 2 (= 30) to
        _TRANSITION_THRESHOLD (= 55).
        """
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

    def test_upper_bound_is_transition_threshold(self):
        """#576 A5: upper bound is _TRANSITION_THRESHOLD (55), not threshold * 2.

        Sample at brightness 42.6 (case from obs-20260116 t=2178) MUST
        trigger A3 refinement so Pass 2 can find sub-sample-interval
        blackouts.  Pre-A5 fix, brightness 42.6 was outside the
        [15, 30) borderline range and Pass 2 never probed the region.
        """
        results = {100.0: 42.6}
        regions = _borderline_pseudo_regions(results, 15.0, 1000.0)
        assert len(regions) == 1, (
            "brightness 42.6 should trigger A3 with #576 A5 extension "
            "(was non-borderline pre-fix)"
        )

    def test_upper_bound_exclusive_at_transition(self):
        """Frames at exactly _TRANSITION_THRESHOLD = 55 are NOT borderline."""
        results = {100.0: 55.0}
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
        mock_probe.side_effect = lambda p, t, region=FULL_FRAME: (
            5.0 if 599.0 <= t <= 610.0 else 128.0
        )

        result = detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=3.0,
            min_match_duration=300.0,
        )

        # With A4, borderline Pass 1 frames trigger Pass 2, which confirms
        # the blackout and splits the video into two matches.
        assert len(result) == 2

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_borderline_triggers_refinement_around_missed_blackout(
        self, mock_chunk, mock_probe, _mock_region
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
        mock_probe.side_effect = lambda p, t, region=FULL_FRAME: (
            2.0 if 8137.25 <= t <= 8139.75 else 128.0
        )

        # _mock_region: borderline-only Pass 1 has 0 strict blackouts -> masked
        # gate (#753 A5); FULL_FRAME stub returns None so the standard A3
        # pseudo-region path still runs and probes around t=8139.
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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_borderline_refinement_disabled_skips_pseudo_regions(
        self, mock_chunk, mock_probe, _mock_region
    ):
        """With _ENABLE_BORDERLINE_REFINEMENT=False, no pseudo regions added."""
        # _mock_region: borderline-only Pass 1 has 0 strict blackouts -> masked
        # gate (#753 A5); FULL_FRAME stub returns None so the standard path runs
        # and (with A3 disabled) probes no region near 8139.

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

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._probe_single_frame")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_upper_margin_zero_restores_strict_threshold(
        self, mock_chunk, mock_probe, _mock_region
    ):
        """With _BLACKOUT_THRESHOLD_UPPER_MARGIN=0.0, only b<threshold is blackout."""
        # _mock_region: with margin 0, the 15.5 frame is not blackout -> 0
        # blackouts -> masked gate (#753 A5); FULL_FRAME stub falls through to
        # the standard single-match result.

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
    """env var rollback helper (#576 S6)."""

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
    """conftest.py autouse fixture clears ALLAGANEYE_DETECT_FPS_FILTER (#576 S6)."""

    def test_env_var_unset_by_default(self):
        # autouse fixture should have unset it before this test runs.
        assert "ALLAGANEYE_DETECT_FPS_FILTER" not in os.environ, (
            "conftest autouse should unset ALLAGANEYE_DETECT_FPS_FILTER. "
            "CI pollution risk (#576 R6)."
        )


# ---------------------------------------------------------------------------
# _sample_chunk_frames / _resolve_fps_rational (#576 S2.2 / S2.3)
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
    """ffmpeg select filter positional mapping: emitted frame K -> chunk_timestamps[K]."""

    def test_integer_60fps(self):
        # ffmpeg select filter emits 3 frames (one per chunk_timestamps entry).
        # Emitted frame 0 -> 10.0, frame 1 -> 12.0, frame 2 -> 14.0.
        # expected_frames=241 simulates VFR check with stream matching expected.
        stream = io.BytesIO(_frames_bytes([100] * 241))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=10.0,
            chunk_timestamps=[10.0, 12.0, 14.0],
            fps_num=60,
            fps_den=1,
            expected_frames=241,  # stream emits 241 total, slack covers diff
            is_tail_chunk=False,
        )
        assert result == {10.0: 100.0, 12.0: 100.0, 14.0: 100.0}

    def test_ntsc_59_94(self):
        # ffmpeg select filter emits 2 frames for 2 chunk_timestamps entries.
        # Emitted frame 0 -> 0.0, frame 1 -> 10.0 (positional mapping).
        # Stream has 600 total frames matching expected_frames (VFR check passes).
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
    """stream が chunk_timestamps より少ないフレームを emitted したとき 255.0 fallback (#576)."""

    def test_target_beyond_available_frames(self):
        # Stream emits 1 frame, but chunk_timestamps has 2 entries.
        # With positional mapping: emitted frame 0 -> chunk_timestamps[0]=0.0,
        # chunk_timestamps[1]=10.0 gets no emitted frame -> 255.0 fallback.
        stream = io.BytesIO(_frames_bytes([0] * 1))
        result = _sample_chunk_frames(
            stream=stream,
            chunk_start=0.0,
            chunk_timestamps=[0.0, 10.0],
            fps_num=60,
            fps_den=1,
            expected_frames=2,  # expected = len(chunk_timestamps) = 2
            is_tail_chunk=True,  # tail -- VFR diff=1 within slack, no raise
        )
        assert result[0.0] == 0.0
        assert result[10.0] == 255.0


class TestSampleChunkFramesDynamicVfr:
    """動的 VFR 検出: slack 超過時 raise / tail chunk は WARN のみ (#576 S2.2 / S7.1.5)."""

    def test_within_slack_no_error(self):
        # 60fps x 60s = 3600 expected, slack = max(36, 6) = 36
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
        # 60fps x 60s = 3600 expected, slack = max(36, 6) = 36
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
    変換した場合、NTSC rational と同じ frame_idx を選ぶこと (#576 S2.3 / S7.1.3)."""

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
    """フレームを逐次処理し全フレームをバッファに蓄積しないこと (spec S2.2 memory budget fix)."""

    def test_does_not_buffer_all_frames(self):
        """Only the first len(chunk_timestamps) frames are recorded; rest discarded.

        With ffmpeg select filter, the stream emits exactly one frame per
        chunk_timestamps entry in order.  Emitted frame 0 -> 0.0, frame 1 -> 1.0.
        Frames beyond len(chunk_timestamps) are consumed but not stored.
        """
        n_frames = 3600
        # frame 0 brightness=10, frame 1 brightness=200, all others=128.
        # With positional mapping: 0.0 -> frame 0 (10), 1.0 -> frame 1 (200).
        raw = (
            bytes([10]) * _FS + bytes([200]) * _FS + bytes([128]) * _FS * (n_frames - 2)
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
# _decode_chunk_cpu v2 path + env var dispatch (#576 S2.1 / S6 / S7.1.1 / S7.1.7)
# ---------------------------------------------------------------------------

import io as _io  # noqa: E402 -- placed here to keep new test section self-contained


class TestDecodeChunkCpuNewPath:
    """_decode_chunk_cpu 新 path の cmd 構築検証 (#576 S2.1 / S7.1.1)."""

    @patch("allaganeye.video.detector.subprocess.Popen")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_cmd_uses_input_seek_no_fps_passthrough(
        self, _mock_ff, mock_popen, monkeypatch
    ):
        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        mock_proc = MagicMock()
        # chunk_timestamps has 3 entries -> select filter emits exactly 3 frames.
        # expected_frames = len(chunk_timestamps) = 3; stream must match to pass
        # the VFR check.
        mock_proc.stdout = _io.BytesIO(bytes([0] * _FRAME_SIZE * 3))
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
        # dual seek: one -ss before -i (input seek), one after -i (output seek)
        ss_positions = [i for i, arg in enumerate(called_cmd) if arg == "-ss"]
        i_idx = called_cmd.index("-i")
        assert len(ss_positions) == 2, (
            f"expected 2 -ss flags for dual seek, got {ss_positions} in {called_cmd}"
        )
        assert ss_positions[0] < i_idx, "first -ss should be input seek (before -i)"
        assert ss_positions[1] > i_idx, "second -ss should be output seek (after -i)"
        # -vf must contain select filter (frame-index based, not PTS-based fps=)
        vf_idx = called_cmd.index("-vf")
        vf_value = called_cmd[vf_idx + 1]
        assert "fps=" not in vf_value, (
            f"fps filter must be removed, got -vf {vf_value!r}"
        )
        assert "select='not(mod(n\\," in vf_value, (
            f"select filter missing in -vf, got {vf_value!r}"
        )
        # -fps_mode passthrough explicit
        assert "-fps_mode" in called_cmd, "missing -fps_mode passthrough"
        fps_mode_idx = called_cmd.index("-fps_mode")
        assert called_cmd[fps_mode_idx + 1] == "passthrough"


class TestDecodeChunkCpuV2NonzeroReturncode:
    """returncode != 0 で 255.0 fallback + WARNING ログ (#576 bug fix)."""

    @patch("allaganeye.video.detector.tempfile.TemporaryFile")
    @patch("allaganeye.video.detector.subprocess.Popen")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_nonzero_returncode_returns_255_fallback(
        self, _mock_ff, mock_popen, mock_tmpfile, monkeypatch, caplog
    ):
        """proc.returncode != 0 -> 255.0 fallback, stderr read from tempfile."""
        import logging

        monkeypatch.delenv("ALLAGANEYE_DETECT_FPS_FILTER", raising=False)

        # Simulate tempfile that ffmpeg would have written to.
        # seek(0) + read() must return the error bytes.
        fake_stderr_buf = _io.BytesIO(b"error: some ffmpeg failure")
        mock_tmpfile.return_value = fake_stderr_buf

        mock_proc = MagicMock()
        # With select filter, expected_frames = len(chunk_timestamps) = 3.
        # Emit exactly 3 frames so _sample_chunk_frames VFR check passes;
        # returncode=1 then triggers the 255.0 fallback path we are testing.
        mock_proc.stdout = _io.BytesIO(bytes([128]) * _FRAME_SIZE * 3)
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
    """env var=1 で旧 fps filter cmd が生成されること (#576 S6 / S7.1.7)."""

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


class TestDetectMatchBoundariesRationalFps:
    """detect_match_boundaries が source_fps_num/den を _scan_cpu / scan_gpu
    まで伝搬すること (#576 S2.3)."""

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.detector._scan_cpu")
    def test_cpu_path_receives_rational_fps(self, mock_scan, _mock_region):
        # _mock_region: bright Pass 1 -> 0 blackouts -> masked gate (#753 A5);
        # FULL_FRAME stub returns None before the masked path can call _scan_cpu
        # again, so mock_scan.call_args remains the single standard Pass 1 call.
        mock_scan.return_value = {0.0: 100.0, 1.0: 100.0}

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1.0,
            sample_interval=1.0,
            min_match_duration=0.5,
            use_gpu=False,
            source_fps_num=60000,
            source_fps_den=1001,
        )

        kwargs = mock_scan.call_args.kwargs
        assert kwargs.get("source_fps_num") == 60000
        assert kwargs.get("source_fps_den") == 1001

    @patch("allaganeye.video.detector._resolve_masked_region", return_value=FULL_FRAME)
    @patch("allaganeye.video.gpu_detector.scan_gpu")
    @patch("allaganeye.video.detector._scan_cpu")
    def test_gpu_path_receives_rational_fps(self, _mock_cpu, mock_gpu, _mock_region):
        # _mock_region: bright Pass 1 -> 0 blackouts -> masked gate (#753 A5);
        # FULL_FRAME stub returns None before the masked path can call scan_gpu
        # again, so mock_gpu.call_args remains the single standard Pass 1 call.
        mock_gpu.return_value = {0.0: 100.0, 1.0: 100.0}

        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1.0,
            sample_interval=1.0,
            min_match_duration=0.5,
            use_gpu=True,
            source_fps_num=60,
            source_fps_den=1,
        )

        kwargs = mock_gpu.call_args.kwargs
        assert kwargs.get("source_fps_num") == 60
        assert kwargs.get("source_fps_den") == 1


# ============================================================
# _drop_post_match_trailing (#797 対策 C')
# ============================================================


class TestDropPostMatchTrailing:
    """Tests for the scorebar-probe trailing-drop helper (#797)."""

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=False)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_trailing_no_scorebar_dropped(self, _probe, _v2):
        """Trailing unknown at EOV + scorebar absent -> segment dropped, counter incremented."""
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 1}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert result[0]["type"] == "fl_match"
        assert stats["filter_drops"]["post_match_trailing"] == 1
        # filter_unknown decremented so the verbose unknown-match count
        # stays consistent after the drop (#797).
        assert stats["filter_unknown"] == 0

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=False)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_trailing_drop_invokes_callback_once(self, _probe, _v2):
        """On a drop, trailing_drop_callback fires exactly once with (start, end).

        #805 段階1: the callback is the seam Unit 2 uses to record the dropped
        span in metadata.json so the lost match is recoverable.
        """
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        seen: list[tuple[float, float]] = []
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            {"filter_unknown": 1},  # type: ignore[arg-type]
            trailing_drop_callback=lambda start, end: seen.append((start, end)),
        )
        assert len(result) == 1
        assert seen == [(1000.0, 1800.0)]

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=False)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_trailing_drop_invokes_callback_with_stats_none(self, _probe, _v2):
        """On a drop the callback fires even when ``stats is None``.

        #805 段階1: the callback path sits intentionally outside the
        ``if stats is not None:`` block, so non-verbose runs (stats=None)
        still record the dropped span in metadata.json. Pin that the seam
        is independent of stats collection.
        """
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        seen: list[tuple[float, float]] = []
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            None,
            trailing_drop_callback=lambda start, end: seen.append((start, end)),
        )
        assert len(result) == 1
        assert seen == [(1000.0, 1800.0)]

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=True)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_trailing_keep_does_not_invoke_callback(self, _probe, _v2):
        """When the segment is kept (scorebar present), the callback never fires."""
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        seen: list[tuple[float, float]] = []
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            {},  # type: ignore[arg-type]
            trailing_drop_callback=lambda start, end: seen.append((start, end)),
        )
        assert len(result) == 2
        assert seen == []

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=True)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_trailing_scorebar_present_kept(self, _probe, _v2):
        """Trailing unknown + scorebar present -> recording cut mid-match -> kept."""
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        stats: dict = {}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 2
        assert "post_match_trailing" not in stats.get("filter_drops", {})

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=None)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=None)
    def test_trailing_probe_failure_kept(self, _probe, _v2):
        """Trailing unknown after a confirmed match + probe failure (None) -> kept.

        Preceded by an fl_match so the post-match gate passes and the probe
        path is exercised; a None probe must keep the segment (safe side).
        """
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "unknown"},
        ]
        stats: dict = {}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 2
        assert "post_match_trailing" not in stats.get("filter_drops", {})

    @patch("allaganeye.video.detector._has_scorebar_v2")
    @patch("allaganeye.video.detector._probe_frame_rgb_hires")
    def test_trailing_scorebar_early_kept(self, _probe, _v2):
        """Mixed trailing (scorebar present early, absent at midpoint) -> kept.

        A removed/missed match-end blackout (e.g. a warp misclassified as
        ``non_fl`` and dropped in scorebar.py) merges a real match and the
        post-match tail into one trailing ``unknown`` segment.  A single
        midpoint probe lands in the longer post-match portion and would
        drop the whole segment, silently losing the match.  Probing earlier
        positions and keeping on any scorebar hit prevents that
        (#797 multi-probe, Codex adversarial-review 2026-05-22).
        """

        # Trailing segment [1000, 2800]; midpoint 1900.  Scorebar present
        # only before the midpoint (the match), absent after (post-match).
        def fake_probe(_video_path, timestamp):
            return b"present" if timestamp < 1900.0 else b"absent"

        def fake_v2(raw):
            if raw is None:
                return None
            return raw == b"present"

        _probe.side_effect = fake_probe
        _v2.side_effect = fake_v2
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 2800.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 1}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            2800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 2
        assert result[-1]["type"] == "unknown"
        assert "post_match_trailing" not in stats.get("filter_drops", {})
        # No drop -> the unknown count must stay put.
        assert stats["filter_unknown"] == 1

    @patch("allaganeye.video.detector._has_scorebar_v2")
    @patch("allaganeye.video.detector._probe_frame_rgb_hires")
    def test_trailing_partial_probe_failure_kept(self, _probe, _v2):
        """A probe failure (None) anywhere in the multi-probe set -> kept.

        Without positive ``False`` proof at every probed position, keep the
        segment: the failed probe might have covered match footage.  Drop
        requires unanimous, definite scorebar absence.
        """

        # Early position fails to decode (None); later positions are absent.
        def fake_probe(_video_path, timestamp):
            return None if timestamp < 1900.0 else b"absent"

        def fake_v2(raw):
            if raw is None:
                return None
            return raw == b"present"

        _probe.side_effect = fake_probe
        _v2.side_effect = fake_v2
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 2800.0, "type": "unknown"},
        ]
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            2800.0,
            None,
        )
        assert len(result) == 2
        assert result[-1]["type"] == "unknown"

    def test_last_segment_not_unknown_kept(self):
        """Last segment with type != 'unknown' is not touched."""
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 1800.0, "type": "fl_match"},
        ]
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            None,
        )
        assert len(result) == 2

    def test_trailing_not_at_end_of_video_kept(self):
        """Last segment 'unknown' but end is far from total_duration -> kept."""
        # end = 1600.0, total_duration = 3600.0 -> abs diff = 2000 >= 1.0
        segments = [
            {"start": 100.0, "end": 1600.0, "type": "unknown"},
        ]
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            3600.0,
            None,
        )
        assert len(result) == 1

    @patch("allaganeye.video.detector._has_scorebar_v2")
    @patch("allaganeye.video.detector._probe_frame_rgb_hires")
    def test_trailing_long_loading_kept(self, _probe, _v2):
        """Mixed trailing where the HUD appears only after long loading -> kept.

        The match-end blackout was dropped, merging a real match and a longer
        post-match tail into one trailing segment.  Loading runs ~60s, so a
        single ``start + 12s`` early probe lands in the loading screen (no
        HUD), while the midpoint and late probes fall in the longer post-match
        tail.  A fixed-offset probe set would see all misses and silently drop
        the real match; an early-window scan must catch the later HUD and keep
        it (#797, Codex adversarial-review 2026-05-23).
        """

        # Trailing [1000, 3000]: loading [1000, 1060), match HUD [1060, 1600),
        # post-match [1600, 3000].  start+12 (=1012) is loading; midpoint
        # (=2000) and 85% (=2700) are post-match.
        def fake_probe(_video_path, timestamp):
            return b"M" if 1060.0 <= timestamp < 1600.0 else b"x"

        def fake_v2(raw):
            if raw is None:
                return None
            return raw == b"M"

        _probe.side_effect = fake_probe
        _v2.side_effect = fake_v2
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 3000.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 1}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            3000.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 2
        assert result[-1]["type"] == "unknown"
        assert "post_match_trailing" not in stats.get("filter_drops", {})
        assert stats["filter_unknown"] == 1

    @patch("allaganeye.video.detector._has_scorebar_v2")
    @patch("allaganeye.video.detector._probe_frame_rgb_hires")
    def test_trailing_hud_in_window_end_gap_kept(self, _probe, _v2):
        """HUD first appearing in the final stride gap of the window -> kept.

        With default min_match_duration=300 and stride=60 the strided probes
        land at start+60/120/180/240; a ``timestamp < window_end`` loop never
        probes the window end, leaving [start+240, start+300] unsampled.  A
        mixed trailing whose loading runs to start+270 (HUD only from there)
        produces misses at every strided point and would be silently dropped.
        The window-end probe must catch it (#797, Codex adversarial-review
        2026-05-24).
        """

        # Trailing [1000, 3000], window_end=1300.  Loading [1000, 1270),
        # match HUD [1270, 1800), post-match [1800, 3000].  start+60..+240 are
        # all < 1270 (loading); only a probe at/near window_end (1300) hits.
        def fake_probe(_video_path, timestamp):
            return b"M" if 1270.0 <= timestamp < 1800.0 else b"x"

        def fake_v2(raw):
            if raw is None:
                return None
            return raw == b"M"

        _probe.side_effect = fake_probe
        _v2.side_effect = fake_v2
        segments = [
            {"start": 100.0, "end": 1000.0, "type": "fl_match"},
            {"start": 1000.0, "end": 3000.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 1}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            3000.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 2
        assert result[-1]["type"] == "unknown"
        assert "post_match_trailing" not in stats.get("filter_drops", {})
        assert stats["filter_unknown"] == 1

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=False)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_whole_video_unknown_kept(self, _probe, _v2):
        """A lone whole-video unknown is never dropped (fail-open preserved).

        _filter_and_extract_segments returns a single whole-video unknown as a
        conservative fallback when no blackout survives.  With no preceding
        confirmed match there is nothing for it to be "post-match" of, so the
        trailing-drop must keep it even when the early window has no scorebar --
        otherwise "no boundaries found" silently becomes zero matches
        (#797, Codex adversarial-review 2026-05-24).
        """
        segments = [
            {"start": 0.0, "end": 1800.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 1}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert "post_match_trailing" not in stats.get("filter_drops", {})
        assert stats["filter_unknown"] == 1

    @patch("allaganeye.video.detector._has_scorebar_v2", return_value=False)
    @patch("allaganeye.video.detector._probe_frame_rgb_hires", return_value=b"x")
    def test_single_match_post_match_tail_dropped(self, _probe, _v2):
        """A single-match recording's no-scorebar post-match tail is still dropped.

        ``_filter_and_extract_segments`` hardcodes the before-first and
        after-last segments as ``unknown``, so [match -> warp -> post-match]
        is ``[unknown, unknown]``.  Only the lone whole-video fallback
        (``len(segments) < 2``) is protected; a real match followed by a
        no-scorebar post-match tail must still be dropped, else #797's FP
        returns for single-match recordings (Codex round-6 adversarial-review
        2026-05-24).
        """
        segments = [
            {"start": 0.0, "end": 900.0, "type": "unknown"},
            {"start": 900.0, "end": 1800.0, "type": "unknown"},
        ]
        stats: dict = {"filter_unknown": 2}
        result = _drop_post_match_trailing(
            segments,  # type: ignore[arg-type]
            Path("v.mp4"),
            1800.0,
            stats,  # type: ignore[arg-type]
        )
        assert len(result) == 1
        assert stats["filter_drops"]["post_match_trailing"] == 1
        assert stats["filter_unknown"] == 1

    def test_empty_segments_no_crash(self):
        """Empty input returns empty, no exception."""
        result = _drop_post_match_trailing([], Path("v.mp4"), 1800.0, None)
        assert result == []


def test_frame_brightness_full_frame_is_1d_mean_bitexact():
    # CPU scan passes a 1-D grayscale buffer (320*180,). FULL_FRAME must
    # equal float(buf.mean()) EXACTLY (no reshape) for OBS bit-exact.
    buf = np.arange(det._FRAME_SIZE, dtype=np.uint8)  # 1-D, length 320*180
    assert det._frame_brightness(buf, FULL_FRAME) == float(buf.mean())


def test_frame_brightness_band_reshapes_and_crops():
    # band branch must reshape the 1-D buffer to (180,320) then crop.
    buf = np.zeros(det._FRAME_SIZE, dtype=np.uint8)
    frame2d = buf.reshape(det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH)
    frame2d[0:9, :] = 100  # top 5% rows bright
    band = CaptureRegion(0.0, 0.0, 1.0, 0.05)
    assert det._frame_brightness(buf.reshape(-1), band) == 100.0


def test_refine_accepts_region_kwarg_default_full_frame():
    # Pass2 (_refine_blackout_regions) must accept a region kwarg defaulting to
    # FULL_FRAME so existing callers (detect_match_boundaries) stay bit-exact.
    # Signature-level pin: Pass2 needs a real video to run end-to-end (B2).
    import inspect

    sig = inspect.signature(det._refine_blackout_regions)
    assert "region" in sig.parameters
    assert sig.parameters["region"].default is FULL_FRAME


# ============================================================
# Task B4: Stage 0 band anchor resolution (_resolve_detect_region)
# ============================================================


def test_resolve_detect_region_exists():
    from allaganeye.video import detector as det

    assert hasattr(det, "_resolve_detect_region")


def test_resolve_detect_region_falls_back_full_frame_on_probe_failure(monkeypatch):
    from allaganeye.video import detector as det
    from allaganeye.video.capture_region import FULL_FRAME  # noqa: F401
    from pathlib import Path

    # all hi-res probes fail -> localize_fn always None -> band consensus FULL_FRAME
    monkeypatch.setattr(det, "_probe_frame_rgb_hires", lambda vp, t: None)
    region = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region.is_full_frame()


def test_resolve_detect_region_swallows_exceptions_to_full_frame(monkeypatch, caplog):
    # Anchor failure must NEVER break detect: any exception inside the probe
    # path is swallowed to FULL_FRAME (OBS-safe degrade, bit-exact preserved).
    # R4: 縮退は silent にせず warning を 1 行残す (診断性のみ、挙動不変)。
    import logging

    from allaganeye.video import detector as det
    from pathlib import Path

    def _boom(vp, t):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(det, "_probe_frame_rgb_hires", _boom)
    with caplog.at_level(logging.WARNING, logger="allaganeye.video.detector"):
        region = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region.is_full_frame()
    assert any("band anchor" in r.message for r in caplog.records)


def test_resolve_detect_region_warns_on_consensus_miss_full_frame(monkeypatch, caplog):
    # consensus-miss (非例外縮退) も silent にしない (R5): --vtuber 明示 run が
    # FULL_FRAME (汚染 path) で続行することを warning で痕跡に残す。
    import logging

    from pathlib import Path

    from allaganeye.video import capture_region as cr
    from allaganeye.video import detector as det

    monkeypatch.setattr(cr, "detect_scorebar_band_region", lambda **kw: cr.FULL_FRAME)
    with caplog.at_level(logging.WARNING, logger="allaganeye.video.detector"):
        region = det._resolve_detect_region(Path("dummy.mp4"), 400.0)
    assert region.is_full_frame()
    assert any("consensus" in r.message for r in caplog.records)


def test_detect_match_boundaries_passes_region_to_all_three_call_sites(monkeypatch):
    # Keystone wiring guard: the region resolved by Stage 0 must reach Pass1
    # (_scan_cpu), GPU (scan_gpu), and Pass2 (_refine_blackout_regions).  On a
    # probe failure the resolved region is FULL_FRAME, but the kwarg must still
    # be threaded through every call so VTuber band ROIs propagate.
    from allaganeye.video import detector as det
    from allaganeye.video import gpu_detector
    from allaganeye.video.capture_region import FULL_FRAME
    from pathlib import Path

    sentinel = CaptureRegion(0.0, 0.10, 1.0, 0.18, confidence=0.9, source="band")
    monkeypatch.setattr(det, "_resolve_detect_region", lambda vp, dh: sentinel)

    cpu_calls: list[CaptureRegion] = []
    gpu_calls: list[CaptureRegion] = []
    refine_calls: list[CaptureRegion] = []

    def fake_scan_cpu(*args, **kwargs):
        cpu_calls.append(kwargs.get("region", FULL_FRAME))
        return {0.0: 100.0, 1.0: 100.0}

    def fake_scan_gpu(*args, **kwargs):
        gpu_calls.append(kwargs.get("region", FULL_FRAME))
        return {0.0: 100.0, 1.0: 100.0}

    def fake_refine(*args, **kwargs):
        refine_calls.append(kwargs.get("region", FULL_FRAME))
        return []

    monkeypatch.setattr(det, "_scan_cpu", fake_scan_cpu)
    monkeypatch.setattr(gpu_detector, "scan_gpu", fake_scan_gpu)
    monkeypatch.setattr(det, "_refine_blackout_regions", fake_refine)

    # vtuber=True is required so Stage 0 resolves the band anchor; without it
    # the gate (B4-rev) keeps detect_region=FULL_FRAME and the sentinel from
    # the monkeypatched _resolve_detect_region would not reach the call sites.
    # CPU path
    det.detect_match_boundaries(
        Path("test.mp4"),
        duration_hint=2.0,
        sample_interval=1.0,
        min_match_duration=0.5,
        use_gpu=False,
        vtuber=True,
    )
    # GPU path
    det.detect_match_boundaries(
        Path("test.mp4"),
        duration_hint=2.0,
        sample_interval=1.0,
        min_match_duration=0.5,
        use_gpu=True,
        vtuber=True,
    )

    assert cpu_calls == [sentinel]
    assert gpu_calls == [sentinel]
    # Pass2 runs in both invocations.
    assert refine_calls == [sentinel, sentinel]


# ============================================================
# Task B4-rev: --vtuber gate on Stage 0 anchor (OBS bit-exact fix)
# ============================================================


def test_detect_has_vtuber_param_defaulting_false():
    from allaganeye.video import detector as det
    import inspect

    sig = inspect.signature(det.detect_match_boundaries)
    assert "vtuber" in sig.parameters
    assert sig.parameters["vtuber"].default is False


# ============================================================
# Task D1: band_region/vtuber threading + trailing-drop VTuber gate (Phase 2)
# ============================================================


def _vtuber_filter_capture(seen: dict):
    """Build a filter_blackouts_with_scorebar stand-in that records kwargs.

    Mirrors the real signature (allaganeye/video/scorebar.py) so the
    keyword-only block (band_region / localize / audio_hits / stats /
    progress_callback) binds exactly as the production call site passes it.
    Returns every region classified as ``match_boundary`` so segments survive
    into the trailing-drop stage.
    """

    def filter_side_effect(
        video_path,
        regions,
        duration,
        height,
        workers=None,
        *,
        band_region=FULL_FRAME,
        localize=False,
        audio_hits=None,
        stats=None,
        progress_callback=None,
    ):
        seen["band_region"] = band_region
        seen["localize"] = localize
        return regions, ["match_boundary"] * len(regions)

    return filter_side_effect


@patch("allaganeye.video.detector._resolve_detect_region")
@patch("allaganeye.video.detector._drop_post_match_trailing")
@patch("allaganeye.video.detector._probe_single_frame")
@patch("allaganeye.video.detector._decode_chunk_cpu")
def test_vtuber_threads_filter_kwargs_and_gates_trailing_drop(
    mock_chunk, mock_probe, mock_trailing, mock_resolve
):
    """Behavioral: vtuber=True threads band_region/vtuber into the scorebar
    filter at runtime and skips the irreversible trailing-drop (#797 gate).

    Replaces the prior inspect.getsource static checks: this exercises the
    real call path so an early return or refactor that breaks the gate fails
    here (the static substring tests would still pass).
    """
    # One blackout region around t=600 (single match boundary).
    mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kw: {
        t: 5.0 if 598.0 <= t <= 602.0 else 128.0 for t in ts
    }
    mock_probe.side_effect = lambda p, t, region=FULL_FRAME: (
        5.0 if 593.0 <= t <= 607.0 else 128.0
    )
    # Passthrough so the assertion is "was it called", independent of segments.
    mock_trailing.side_effect = lambda segs, *a, **k: segs
    # Isolate from real ffmpeg/localize I/O; return a distinct (non-FULL_FRAME)
    # region so band_region threading is observable, not a degraded default.
    band = CaptureRegion(0.1, 0.1, 0.8, 0.2, confidence=0.9, source="tierB")
    mock_resolve.return_value = band

    seen: dict = {}
    with patch(
        "allaganeye.video.scorebar.filter_blackouts_with_scorebar",
        side_effect=_vtuber_filter_capture(seen),
    ):
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            src_resolution=(1920, 1080),
            vtuber=True,
        )

    # filter received the resolved band region and the localize flag at runtime.
    assert seen["localize"] is True
    assert seen["band_region"] is not None
    assert seen["band_region"] is band
    # VTuber path must NOT run the irreversible trailing-drop (#797 / #805).
    mock_trailing.assert_not_called()


@patch("allaganeye.video.detector._drop_post_match_trailing")
@patch("allaganeye.video.detector._probe_single_frame")
@patch("allaganeye.video.detector._decode_chunk_cpu")
def test_obs_runs_trailing_drop_and_filter_sees_vtuber_false(
    mock_chunk, mock_probe, mock_trailing
):
    """Behavioral OBS regression guard: vtuber=False (default OBS path) keeps
    running the trailing-drop and reports vtuber=False to the scorebar filter.

    Pairs with the vtuber=True test to pin the gate from both sides so a
    regression that drops the ``not vtuber`` guard is caught.
    """
    mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kw: {
        t: 5.0 if 598.0 <= t <= 602.0 else 128.0 for t in ts
    }
    mock_probe.side_effect = lambda p, t, region=FULL_FRAME: (
        5.0 if 593.0 <= t <= 607.0 else 128.0
    )
    mock_trailing.side_effect = lambda segs, *a, **k: segs

    seen: dict = {}
    with patch(
        "allaganeye.video.scorebar.filter_blackouts_with_scorebar",
        side_effect=_vtuber_filter_capture(seen),
    ):
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            src_resolution=(1920, 1080),
        )

    assert seen["localize"] is False
    # OBS path runs the trailing-drop exactly once.
    mock_trailing.assert_called_once()


@patch("allaganeye.video.detector._drop_post_match_trailing")
@patch("allaganeye.video.detector._probe_single_frame")
@patch("allaganeye.video.detector._decode_chunk_cpu")
def test_keep_trailing_gates_trailing_drop(mock_chunk, mock_probe, mock_trailing):
    """keep_trailing=True opts out of the irreversible trailing-drop (#805 段階1).

    Pairs with test_obs_runs_trailing_drop_* (which proves the default
    keep_trailing=False path DOES drop) to pin the new gate from both sides:
    flipping --keep-trailing must be the only thing that suppresses the call.
    """
    mock_chunk.side_effect = lambda vp, ts, cs, ce, si, **kw: {
        t: 5.0 if 598.0 <= t <= 602.0 else 128.0 for t in ts
    }
    mock_probe.side_effect = lambda p, t, region=FULL_FRAME: (
        5.0 if 593.0 <= t <= 607.0 else 128.0
    )
    mock_trailing.side_effect = lambda segs, *a, **k: segs

    with patch(
        "allaganeye.video.scorebar.filter_blackouts_with_scorebar",
        side_effect=_vtuber_filter_capture({}),
    ):
        detect_match_boundaries(
            Path("test.mp4"),
            duration_hint=1800.0,
            sample_interval=1.0,
            min_match_duration=300.0,
            src_resolution=(1920, 1080),
            keep_trailing=True,
        )

    # --keep-trailing -> the drop helper is never invoked, so the final
    # segment survives untouched.
    mock_trailing.assert_not_called()


# ============================================================
# TestDecodeGrayRaw / TestProbeFrameGray2d (masked-OBS A2)
# ============================================================


def test_probe_frame_gray2d_returns_2d(monkeypatch):
    buf = bytes(range(256)) * (det._FRAME_SIZE // 256 + 1)
    monkeypatch.setattr(det, "_decode_gray_raw", lambda v, t: buf[: det._FRAME_SIZE])
    frame = det._probe_frame_gray2d(det.Path("x.mp4"), 1.0)
    assert frame is not None
    assert frame.shape == (det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH)
    assert frame.dtype == np.uint8


def test_probe_frame_gray2d_none_on_decode_failure(monkeypatch):
    monkeypatch.setattr(det, "_decode_gray_raw", lambda v, t: None)
    assert det._probe_frame_gray2d(det.Path("x.mp4"), 1.0) is None


def test_probe_single_frame_regression_via_shared_decoder(monkeypatch):
    # Extraction must preserve _probe_single_frame brightness exactly.
    buf = bytes([10]) * det._FRAME_SIZE
    monkeypatch.setattr(det, "_decode_gray_raw", lambda v, t: buf)
    assert det._probe_single_frame(det.Path("x.mp4"), 1.0) == 10.0
    monkeypatch.setattr(det, "_decode_gray_raw", lambda v, t: None)
    assert det._probe_single_frame(det.Path("x.mp4"), 1.0) == 255.0


# ============================================================
# TestResolveMaskedRegion (masked-OBS A3)
# ============================================================


def _masked_frames():
    out = []
    for v in (5, 200, 5, 200):
        f = np.full((det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH), v, dtype=np.uint8)
        f[120:180, 0:120] = 200  # static bright mask, bottom-left
        out.append(f)
    return out


def test_resolve_masked_region_finds_mask_free_rect(monkeypatch):
    seq = iter(_masked_frames() * 20)
    monkeypatch.setattr(
        det, "_probe_frame_gray2d", lambda v, t: next(seq, _masked_frames()[0])
    )
    region = det._resolve_masked_region(det.Path("x.mp4"), 600.0, None)
    assert not region.is_full_frame()


def test_resolve_masked_region_full_frame_when_no_frames(monkeypatch):
    monkeypatch.setattr(det, "_probe_frame_gray2d", lambda v, t: None)
    assert det._resolve_masked_region(det.Path("x.mp4"), 600.0, None).is_full_frame()


def test_resolve_masked_region_swallows_exceptions(monkeypatch):
    def boom(v, t):
        raise RuntimeError("decode blew up")

    monkeypatch.setattr(det, "_probe_frame_gray2d", boom)
    assert det._resolve_masked_region(det.Path("x.mp4"), 600.0, None).is_full_frame()


# ============================================================
# Masked fallback (#753 masked-OBS, A-Task 5)
# ============================================================


def _zero_blackout_results():
    return {float(t): 200.0 for t in range(0, 600, 3)}


def test_masked_fallback_triggers_on_zero_blackout(monkeypatch):
    monkeypatch.setattr(det, "_scan_cpu", lambda *a, **k: _zero_blackout_results())
    called = {}

    def fake_masked(video_path, **kw):
        called["hit"] = True
        return [{"start": 0.0, "end": 300.0}]

    monkeypatch.setattr(det, "_detect_masked_fallback", fake_masked)
    out = det.detect_match_boundaries(
        det.Path("x.mp4"),
        duration_hint=600.0,
        use_gpu=False,
        src_resolution=(1920, 1080),
    )
    assert called.get("hit") is True
    assert out == [{"start": 0.0, "end": 300.0}]


def test_masked_fallback_not_triggered_when_blackouts_present(monkeypatch):
    # OBS bit-exact gate: blackouts present + masked=False -> fallback NOT called.
    results = _zero_blackout_results()
    results[300.0] = 2.0  # one blackout frame
    monkeypatch.setattr(det, "_scan_cpu", lambda *a, **k: results)
    monkeypatch.setattr(det, "_refine_blackout_regions", lambda *a, **k: [])
    called = {}
    monkeypatch.setattr(
        det, "_detect_masked_fallback", lambda *a, **k: called.setdefault("hit", True)
    )
    det.detect_match_boundaries(
        det.Path("x.mp4"), duration_hint=600.0, use_gpu=False, src_resolution=None
    )
    assert "hit" not in called


def test_masked_fallback_forced_even_with_blackouts(monkeypatch):
    results = _zero_blackout_results()
    results[300.0] = 2.0
    monkeypatch.setattr(det, "_scan_cpu", lambda *a, **k: results)
    monkeypatch.setattr(
        det, "_detect_masked_fallback", lambda *a, **k: [{"start": 1.0, "end": 2.0}]
    )
    out = det.detect_match_boundaries(
        det.Path("x.mp4"),
        duration_hint=600.0,
        use_gpu=False,
        masked=True,
        src_resolution=(1920, 1080),
    )
    assert out == [{"start": 1.0, "end": 2.0}]


def test_detect_masked_fallback_returns_none_when_no_region(monkeypatch):
    monkeypatch.setattr(det, "_resolve_masked_region", lambda *a, **k: det.FULL_FRAME)
    scan_called = {}
    monkeypatch.setattr(
        det, "_scan_cpu", lambda *a, **k: scan_called.setdefault("hit", True) or {}
    )
    out = det._detect_masked_fallback(
        det.Path("x.mp4"),
        duration_hint=600.0,
        sample_interval=3.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        use_gpu=False,
        workers=None,
        src_resolution=(1920, 1080),
        codec="h264",
        gpu_vendor=None,
        source_fps_num=60,
        source_fps_den=1,
        source_fps=None,
        audio_hits=None,
        stats=None,
    )
    assert out is None
    assert "hit" not in scan_called  # short-circuits before scanning


def test_detect_masked_fallback_wires_region_band_localize(monkeypatch):
    from allaganeye.video.capture_region import CaptureRegion

    fake_region = CaptureRegion(0.0, 0.0, 1.0, 0.3, source="tierA")
    monkeypatch.setattr(det, "_resolve_masked_region", lambda *a, **k: fake_region)
    seen = {}

    def fake_scan(video_path, dur, si, thr, workers, cb, **kw):
        seen["scan_region"] = kw.get("region")
        return {0.0: 2.0, 3.0: 2.0, 100.0: 200.0}

    monkeypatch.setattr(det, "_scan_cpu", fake_scan)

    def fake_refine(video_path, regions, thr, dur, workers, **kw):
        seen["refine_region"] = kw.get("region")
        return [(0.0, 3.0)]

    monkeypatch.setattr(det, "_refine_blackout_regions", fake_refine)

    def fake_filter(video_path, regions, dur, height, workers, **kw):
        seen["band_region"] = kw.get("band_region")
        seen["localize"] = kw.get("localize")
        return regions, ["match_boundary"]

    monkeypatch.setattr(
        "allaganeye.video.scorebar.filter_blackouts_with_scorebar", fake_filter
    )
    monkeypatch.setattr(
        det,
        "_filter_and_extract_segments",
        lambda *a, **k: [{"start": 0.0, "end": 9.0}],
    )

    out = det._detect_masked_fallback(
        det.Path("x.mp4"),
        duration_hint=600.0,
        sample_interval=3.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        use_gpu=False,
        workers=None,
        src_resolution=(1920, 1080),
        codec="h264",
        gpu_vendor=None,
        source_fps_num=60,
        source_fps_den=1,
        source_fps=None,
        audio_hits=None,
        stats=None,
    )
    assert out == [{"start": 0.0, "end": 9.0}]
    assert seen["scan_region"] is fake_region
    assert seen["refine_region"] is fake_region
    assert seen["band_region"] is det.FULL_FRAME
    assert seen["localize"] is True


# ============================================================
# A-Task 8: brightness-hint dark+even sampling
# ============================================================


def test_resolve_masked_region_hint_samples_darkest(monkeypatch):
    # brightness_hint marks 3 very-dark timestamps (the masked blackouts).
    DUR = 1000.0
    hint = {
        float(t): (5.0 if t in (100, 300, 700) else 200.0) for t in range(0, 1000, 10)
    }
    sampled = []

    def fake(v, t):
        sampled.append(round(t, 3))
        return np.zeros((det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH), dtype=np.uint8)

    monkeypatch.setattr(det, "_probe_frame_gray2d", fake)
    det._resolve_masked_region(det.Path("x.mp4"), DUR, None, brightness_hint=hint)
    # The 3 darkest timestamps must be among those decoded (dark-moment sampling).
    assert {100.0, 300.0, 700.0}.issubset(set(sampled))


def test_resolve_masked_region_hint_finds_region(monkeypatch):
    DUR = 1000.0
    dark = {100.0, 300.0, 700.0}
    hint = {float(t): (5.0 if t in dark else 200.0) for t in range(0, 1000, 10)}

    def fake(v, t):
        # dark timestamps -> game region dark (5); others -> game bright (200).
        base = 5 if t in dark else 200
        f = np.full((det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH), base, dtype=np.uint8)
        f[120:180, 0:120] = 200  # static bright mask, bottom-left
        return f

    monkeypatch.setattr(det, "_probe_frame_gray2d", fake)
    r = det._resolve_masked_region(det.Path("x.mp4"), DUR, None, brightness_hint=hint)
    assert not r.is_full_frame()  # dark+even sampling recovers the region


def test_resolve_masked_region_no_hint_unchanged(monkeypatch):
    # Without a hint, behavior is the prior even-only sampling (backward compat).
    seq = iter(_masked_frames() * 40)
    monkeypatch.setattr(
        det, "_probe_frame_gray2d", lambda v, t: next(seq, _masked_frames()[0])
    )
    r = det._resolve_masked_region(det.Path("x.mp4"), 600.0, None)
    assert not r.is_full_frame()


def test_detect_masked_fallback_threads_brightness_hint(monkeypatch):
    seen = {}

    def fake_resolve(video_path, duration_hint, workers, *, brightness_hint=None):
        seen["hint"] = brightness_hint
        return det.FULL_FRAME  # short-circuit (returns None) -- we only check wiring

    monkeypatch.setattr(det, "_resolve_masked_region", fake_resolve)
    out = det._detect_masked_fallback(
        det.Path("x.mp4"),
        duration_hint=600.0,
        sample_interval=3.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        use_gpu=False,
        workers=None,
        src_resolution=(1920, 1080),
        codec="h264",
        gpu_vendor=None,
        source_fps_num=60,
        source_fps_den=1,
        source_fps=None,
        audio_hits=None,
        stats=None,
        brightness_results={1.0: 5.0, 2.0: 200.0},
    )
    assert out is None
    assert seen["hint"] == {1.0: 5.0, 2.0: 200.0}
