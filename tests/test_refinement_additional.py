"""Additional tester-1 tests for two-pass long-segment refinement (#317).

Complements ``tests/test_refinement.py`` (engineer-1) by covering:
- Threshold boundary conditions (exactly-at vs. just-over 28min)
- Log message content (info split / warning no-op)
- ``_refine_one_segment`` scorebar path (src_resolution != None)
- ``_refine_one_segment`` fallback when refined_regions filtered out
- ``_extract_subsegments`` with multiple blackouts / range-boundary regions
- ``_extract_subsegments`` classification propagation across multiple regions
- Integration: ``detect_match_boundaries`` invokes ``_refine_long_segments``
"""

import logging
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from allaganeye.audio.matcher import BgmHit
from allaganeye.video.detector import (
    MatchBoundary,
    _SUSPICIOUS_MATCH_MAX_DURATION,
    _extract_subsegments,
    _refine_long_segments,
    _refine_one_segment,
)

DETECTOR = "allaganeye.video.detector"


def _mb(start: float, end: float, type_: str = "fl_match") -> MatchBoundary:
    return {"start": start, "end": end, "type": type_}


# ---------------------------------------------------------------------------
# Threshold boundary conditions
# ---------------------------------------------------------------------------


class TestThresholdBoundary:
    """The threshold check is strict > (see detector.py:1072).

    Segments exactly at the threshold must NOT trigger refinement;
    segments one second over must.
    """

    @patch(f"{DETECTOR}._refine_one_segment")
    def test_exactly_at_threshold_does_not_trigger(self, mock_refine):
        """Duration == 28*60s -- strict > means not suspicious."""
        seg = _mb(0.0, float(_SUSPICIOUS_MATCH_MAX_DURATION))
        result = _refine_long_segments(
            [seg],
            Path("t.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        assert result == [seg]
        mock_refine.assert_not_called()

    @patch(f"{DETECTOR}._refine_one_segment")
    def test_one_second_over_triggers(self, mock_refine):
        """Duration == 28*60 + 1s -- triggers refinement."""
        seg = _mb(0.0, float(_SUSPICIOUS_MATCH_MAX_DURATION) + 1.0)
        mock_refine.return_value = [seg]
        _refine_long_segments(
            [seg],
            Path("t.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=None,
            workers=None,
            audio_hits=None,
        )
        mock_refine.assert_called_once()


# ---------------------------------------------------------------------------
# Log message content
# ---------------------------------------------------------------------------


class TestRefineLogging:
    @patch(f"{DETECTOR}._refine_one_segment")
    def test_info_log_on_split(self, mock_refine, caplog):
        """Split result logs INFO 'REFINE ... split into N sub-segments'."""
        seg = _mb(0.0, 30 * 60)
        mock_refine.return_value = [_mb(0.0, 1000.0), _mb(1100.0, 30 * 60)]
        with caplog.at_level(logging.INFO, logger=DETECTOR):
            _refine_long_segments(
                [seg],
                Path("t.mp4"),
                blackout_threshold=15.0,
                min_match_duration=300.0,
                min_blackout_duration=1.5,
                src_resolution=None,
                workers=None,
                audio_hits=None,
            )
        msgs = [r.getMessage() for r in caplog.records]
        assert any("split into 2 sub-segments" in m for m in msgs)

    @patch(f"{DETECTOR}._refine_one_segment")
    def test_warning_log_on_no_op(self, mock_refine, caplog):
        """When refinement returns same single segment, WARNING is logged."""
        seg = _mb(0.0, 30 * 60)
        mock_refine.return_value = [seg]
        with caplog.at_level(logging.WARNING, logger=DETECTOR):
            _refine_long_segments(
                [seg],
                Path("t.mp4"),
                blackout_threshold=15.0,
                min_match_duration=300.0,
                min_blackout_duration=1.5,
                src_resolution=None,
                workers=None,
                audio_hits=None,
            )
        msgs = [r.getMessage() for r in caplog.records]
        assert any("no additional boundaries found" in m for m in msgs)


# ---------------------------------------------------------------------------
# _refine_one_segment: scorebar path (src_resolution provided)
# ---------------------------------------------------------------------------


class TestRefineOneSegmentScorebarPath:
    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch(f"{DETECTOR}._refine_blackout_regions")
    @patch(f"{DETECTOR}._decode_chunk_cpu")
    def test_scorebar_filter_invoked_when_src_resolution_provided(
        self, mock_decode, mock_refine_regions, mock_filter
    ):
        """src_resolution != None -> filter_blackouts_with_scorebar called."""
        seg = _mb(0.0, 30 * 60)
        results = {float(t): 200.0 for t in range(0, 30 * 60)}
        for t in (900.0, 901.0, 902.0):
            results[t] = 3.0
        mock_decode.return_value = results
        mock_refine_regions.return_value = [(900.0, 902.0)]
        mock_filter.return_value = ([(900.0, 902.0)], ["match_boundary"])

        sub = _refine_one_segment(
            seg,
            Path("t.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=(1920, 1080),
            workers=None,
            audio_hits=None,
        )
        mock_filter.assert_called_once()
        # Sub-segments created
        assert len(sub) == 2

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch(f"{DETECTOR}._refine_blackout_regions")
    @patch(f"{DETECTOR}._decode_chunk_cpu")
    def test_scorebar_filters_out_all_regions_returns_original(
        self, mock_decode, mock_refine_regions, mock_filter
    ):
        """Scorebar classifier rejects all regions -> fall back to [segment]."""
        seg = _mb(0.0, 30 * 60)
        results = {float(t): 200.0 for t in range(0, 30 * 60)}
        for t in (900.0, 901.0, 902.0):
            results[t] = 3.0
        mock_decode.return_value = results
        mock_refine_regions.return_value = [(900.0, 902.0)]
        # Scorebar filter drops everything (e.g. all classified as non_fl)
        mock_filter.return_value = ([], [])

        sub = _refine_one_segment(
            seg,
            Path("t.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=(1920, 1080),
            workers=None,
            audio_hits=None,
        )
        assert sub == [seg]

    @patch("allaganeye.video.scorebar.filter_blackouts_with_scorebar")
    @patch(f"{DETECTOR}._refine_blackout_regions")
    @patch(f"{DETECTOR}._decode_chunk_cpu")
    def test_audio_hits_forwarded_to_scorebar_filter(
        self, mock_decode, mock_refine_regions, mock_filter
    ):
        """audio_hits plumbed through to filter_blackouts_with_scorebar."""
        seg = _mb(0.0, 30 * 60)
        results = {float(t): 200.0 for t in range(0, 30 * 60)}
        for t in (900.0, 901.0, 902.0):
            results[t] = 3.0
        mock_decode.return_value = results
        mock_refine_regions.return_value = [(900.0, 902.0)]
        mock_filter.return_value = ([(900.0, 902.0)], ["match_boundary"])

        hits: list[BgmHit] = [{"timestamp": 910.0, "similarity": 0.8}]
        _refine_one_segment(
            seg,
            Path("t.mp4"),
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
            src_resolution=(1920, 1080),
            workers=None,
            audio_hits=hits,
        )
        # audio_hits passed as kwarg per detector.py:1193
        _, kwargs = mock_filter.call_args
        assert kwargs.get("audio_hits") == hits


# ---------------------------------------------------------------------------
# _extract_subsegments: uncovered cases
# ---------------------------------------------------------------------------


class TestExtractSubsegmentsAdditional:
    def test_three_blackouts_yield_four_subsegments(self):
        """3 blackouts inside range -> 4 sub-segments."""
        result = _extract_subsegments(
            blackout_regions=[
                (500.0, 503.0),
                (1000.0, 1003.0),
                (1500.0, 1503.0),
            ],
            classifications=None,
            range_start=0.0,
            range_end=2000.0,
            min_match_duration=100.0,
            min_blackout_duration=1.5,
        )
        assert len(result) == 4
        assert result[0]["start"] == 0.0
        assert result[-1]["end"] == 2000.0
        # Strictly monotonic
        for prev, cur in pairwise(result):
            assert prev["end"] <= cur["start"]

    def test_blackout_straddling_range_start_included(self):
        """Region spanning [r0<range_start, r1>range_start] -> kept (r1 >= range_start)."""
        result = _extract_subsegments(
            blackout_regions=[(50.0, 105.0)],  # r0=50 < range_start=100, r1=105
            classifications=None,
            range_start=100.0,
            range_end=2000.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        # The region is kept; since r0=50 < range_start the leading sub-segment
        # collapses -- only the trailing segment survives.
        assert len(result) == 1
        assert result[0]["end"] == 2000.0

    def test_unsorted_regions_are_sorted(self):
        """Regions passed in reverse order still yield correct sub-segments."""
        result = _extract_subsegments(
            blackout_regions=[(1500.0, 1503.0), (500.0, 503.0)],  # reverse order
            classifications=None,
            range_start=0.0,
            range_end=2000.0,
            min_match_duration=100.0,
            min_blackout_duration=1.5,
        )
        assert len(result) == 3
        # Middle segment spans between the two blackouts
        assert result[0]["end"] <= result[1]["start"]
        assert result[1]["end"] <= result[2]["start"]

    def test_unsorted_regions_keep_classifications_aligned(self):
        """Sort must move classifications alongside regions."""
        result = _extract_subsegments(
            blackout_regions=[(1500.0, 1503.0), (500.0, 503.0)],
            classifications=["match_boundary", "unknown"],
            range_start=0.0,
            range_end=2000.0,
            min_match_duration=100.0,
            min_blackout_duration=1.5,
            original_type="fl_match",
        )
        # 3 sub-segments: [0..500], [500..1500], [1500..2000]
        assert len(result) == 3

    def test_multiple_classifications_infer_inner_type(self):
        """With 2 regions -> middle segment's type is inferred from both classes."""
        result = _extract_subsegments(
            blackout_regions=[(500.0, 503.0), (1500.0, 1503.0)],
            classifications=["match_boundary", "match_boundary"],
            range_start=0.0,
            range_end=2000.0,
            min_match_duration=100.0,
            min_blackout_duration=1.5,
            original_type="fl_match",
        )
        assert len(result) == 3
        # Middle segment (between two match_boundary blackouts): fl_match
        assert result[1]["type"] == "fl_match"

    def test_all_regions_filtered_by_short_duration(self):
        """All regions shorter than min_blackout -> empty result."""
        result = _extract_subsegments(
            blackout_regions=[(500.0, 500.5), (1500.0, 1500.5)],
            classifications=None,
            range_start=0.0,
            range_end=2000.0,
            min_match_duration=100.0,
            min_blackout_duration=1.5,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Integration: detect_match_boundaries wiring
# ---------------------------------------------------------------------------


class TestDetectIntegration:
    """Guard the wiring in detect_match_boundaries (#317 regression risk).

    If someone refactors detect_match_boundaries and drops the call to
    _refine_long_segments, these tests should fail immediately.
    """

    @patch(f"{DETECTOR}._refine_long_segments")
    @patch(f"{DETECTOR}._filter_and_extract_segments")
    @patch(f"{DETECTOR}._refine_blackout_regions")
    @patch(f"{DETECTOR}._scan_cpu")
    def test_refine_long_segments_called_from_detect(
        self, mock_scan, mock_refine_regions, mock_filter, mock_refine_long
    ):
        """detect_match_boundaries pipes output through _refine_long_segments."""
        from allaganeye.video.detector import detect_match_boundaries

        mock_scan.return_value = {0.0: 200.0, 10.0: 200.0, 20.0: 200.0}
        mock_refine_regions.return_value = []
        base_boundaries = [_mb(0.0, 1800.0)]
        mock_filter.return_value = base_boundaries
        # Simulate refinement pass-through (no split)
        mock_refine_long.return_value = base_boundaries

        out = detect_match_boundaries(
            Path("t.mp4"),
            duration_hint=2000.0,
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        mock_refine_long.assert_called_once()
        assert out == base_boundaries

    @patch(f"{DETECTOR}._refine_long_segments")
    @patch(f"{DETECTOR}._filter_and_extract_segments")
    @patch(f"{DETECTOR}._refine_blackout_regions")
    @patch(f"{DETECTOR}._scan_cpu")
    def test_detect_returns_refinement_output(
        self, mock_scan, mock_refine_regions, mock_filter, mock_refine_long
    ):
        """Split produced by _refine_long_segments propagates out."""
        from allaganeye.video.detector import detect_match_boundaries

        mock_scan.return_value = {0.0: 200.0}
        mock_refine_regions.return_value = []
        mock_filter.return_value = [_mb(0.0, 3000.0)]
        # Refinement splits into 2
        split = [_mb(0.0, 1400.0), _mb(1500.0, 3000.0)]
        mock_refine_long.return_value = split

        out = detect_match_boundaries(
            Path("t.mp4"),
            duration_hint=3500.0,
            sample_interval=1.0,
            blackout_threshold=15.0,
            min_match_duration=300.0,
            min_blackout_duration=1.5,
        )
        assert out == split
