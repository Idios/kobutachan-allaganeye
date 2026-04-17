"""Tests for two-pass long-segment refinement (#317)."""

import logging
from pathlib import Path
from unittest.mock import patch

from allaganeye.video.detector import (
    MatchBoundary,
    _REFINEMENT_SAMPLE_INTERVAL,
    _SUSPICIOUS_MATCH_MAX_DURATION,
    _extract_subsegments,
    _refine_long_segments,
    _refine_one_segment,
)


def _mb(start: float, end: float, type_: str = "fl_match") -> MatchBoundary:
    """Build a MatchBoundary TypedDict for tests."""
    return {"start": start, "end": end, "type": type_}


# --- Constants sanity ---


class TestConstants:
    def test_threshold_is_28_min(self):
        assert _SUSPICIOUS_MATCH_MAX_DURATION == 28 * 60

    def test_refinement_interval_is_one_second(self):
        assert _REFINEMENT_SAMPLE_INTERVAL == 1.0


# --- _refine_long_segments ---


class TestRefineLongSegments:
    def test_no_suspicious_segments_returns_unchanged(self):
        """All segments below threshold -> no refinement, return as-is."""
        boundaries: list[MatchBoundary] = [
            _mb(0.0, 1000.0),
            _mb(1100.0, 2000.0),
        ]
        result = _refine_long_segments(
            boundaries,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert result == boundaries

    def test_empty_boundaries_returns_empty(self):
        result = _refine_long_segments(
            [],
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert result == []

    @patch("allaganeye.video.detector._refine_one_segment")
    def test_long_segment_triggers_refine(self, mock_refine):
        """Segment > 28min triggers refinement; result replaces it."""
        original = _mb(100.0, 100.0 + 30 * 60)
        boundaries: list[MatchBoundary] = [original]
        mock_refine.return_value = [
            _mb(100.0, 1100.0),
            _mb(1300.0, 100.0 + 30 * 60),
        ]
        result = _refine_long_segments(
            boundaries,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert len(result) == 2
        mock_refine.assert_called_once()

    @patch("allaganeye.video.detector._refine_one_segment")
    def test_refine_returning_single_segment_keeps_original(self, mock_refine):
        """If refinement finds no new structure, original segment is kept."""
        original = _mb(100.0, 100.0 + 30 * 60)
        boundaries: list[MatchBoundary] = [original]
        mock_refine.return_value = [original]  # same single segment
        result = _refine_long_segments(
            boundaries,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert result == boundaries

    @patch("allaganeye.video.detector._refine_one_segment")
    def test_multiple_long_segments_each_refined_independently(self, mock_refine):
        """Multiple segments above threshold are each processed once."""
        long1 = _mb(0.0, 30 * 60)
        short = _mb(35 * 60, 50 * 60)
        long2 = _mb(60 * 60, 95 * 60)
        boundaries: list[MatchBoundary] = [long1, short, long2]

        def fake_refine(seg, *args, **kwargs):
            mid = (seg["start"] + seg["end"]) / 2
            return [
                _mb(seg["start"], mid - 10),
                _mb(mid + 10, seg["end"]),
            ]

        mock_refine.side_effect = fake_refine
        result = _refine_long_segments(
            boundaries,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        # 1 short + 2 sub-segments + 2 sub-segments = 5
        assert len(result) == 5
        assert result[2] == short  # untouched short segment in middle
        assert mock_refine.call_count == 2

    @patch("allaganeye.video.detector._refine_one_segment")
    def test_no_recursion_when_refined_still_long(self, mock_refine, caplog):
        """One-level guard: refined sub-segments still >threshold log warning,
        no further refinement."""
        original = _mb(0.0, 60 * 60)
        # Refinement returns one still-long sub-segment + a normal one
        mock_refine.return_value = [
            _mb(0.0, 35 * 60),  # still > 28min
            _mb(35 * 60 + 100, 60 * 60),
        ]
        with caplog.at_level(logging.WARNING, logger="allaganeye.video.detector"):
            result = _refine_long_segments(
                [original],
                Path("test.mp4"),
                blackout_threshold=15.0,
                min_match_duration=300.0,
                min_blackout_duration=1.5,
                src_resolution=None,
                workers=None,
                audio_hits=None,
            )
        # _refine_one_segment called only once (no recursion)
        assert mock_refine.call_count == 1
        assert len(result) == 2
        # Warning logged about residual long segment
        assert any("still > " in r.message for r in caplog.records)


# --- _refine_one_segment ---


class TestRefineOneSegment:
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_no_blackouts_returns_original(self, mock_decode):
        """No blackouts found in fine scan -> keep original segment."""
        seg = _mb(100.0, 100.0 + 30 * 60)
        mock_decode.return_value = {float(t): 200.0 for t in range(100, 100 + 30 * 60)}
        result = _refine_one_segment(
            seg,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert result == [seg]

    @patch("allaganeye.video.detector._refine_blackout_regions")
    @patch("allaganeye.video.detector._decode_chunk_cpu")
    def test_blackouts_found_split_into_subsegments(
        self, mock_decode, mock_refine_regions
    ):
        """Fine scan finds blackouts -> sub-segments returned."""
        seg = _mb(0.0, 30 * 60)
        results = {float(t): 200.0 for t in range(0, 30 * 60)}
        for t in (900.0, 901.0, 902.0):
            results[t] = 3.0
        mock_decode.return_value = results
        mock_refine_regions.return_value = [(900.0, 902.0)]

        result = _refine_one_segment(
            seg,
            Path("test.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        # Split into 2 sub-segments around the blackout
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["end"] == 30 * 60


# --- _extract_subsegments ---


class TestExtractSubsegments:
    def test_no_regions_returns_empty(self):
        result = _extract_subsegments(
            blackout_regions=[],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        assert result == []

    def test_one_blackout_splits_range_in_two(self):
        result = _extract_subsegments(
            blackout_regions=[(1000.0, 1003.0)],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        assert len(result) == 2
        assert result[0]["start"] == 100.0
        assert result[-1]["end"] == 2000.0

    def test_short_blackouts_filtered(self):
        """Blackouts shorter than min_blackout_duration are ignored."""
        result = _extract_subsegments(
            blackout_regions=[(1000.0, 1000.5)],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        assert result == []

    def test_blackouts_outside_range_ignored(self):
        result = _extract_subsegments(
            blackout_regions=[(50.0, 55.0), (1000.0, 1003.0), (3000.0, 3003.0)],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        assert len(result) == 2

    def test_subsegments_below_min_duration_filtered(self):
        """Sub-segments shorter than min_match_duration are dropped."""
        result = _extract_subsegments(
            blackout_regions=[(150.0, 153.0)],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        # Leading sub-segment [100, ~150] < 300s -> filtered
        assert len(result) == 1
        assert result[0]["end"] == 2000.0

    def test_classifications_inferred_for_inner_segments(self):
        result = _extract_subsegments(
            blackout_regions=[(1000.0, 1003.0)],
            classifications=["match_boundary"],
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            original_type="fl_match",
        )
        assert result[0]["type"] == "fl_match"

    def test_preserves_original_type_when_no_split(self):
        """When no boundary present, segment type preserved via original_type."""
        result = _extract_subsegments(
            blackout_regions=[(1000.0, 1003.0)],
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            original_type="fl_match",
        )
        assert result[0]["type"] == "fl_match"
        assert result[-1]["type"] == "fl_match"
