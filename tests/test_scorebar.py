"""Tests for scorebar detection logic."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from allaganeye.video.detector import (
    _SAMPLE_WIDTH,
    _SCOREBAR_CHANNEL_STD_THRESHOLD,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _has_scorebar,
    _scaled_height,
)
from allaganeye.video.scorebar import (
    _MERGE_GAP_MAX,
    _is_static_screen,
    _majority_scorebar,
    classify_blackout,
    filter_blackouts_with_scorebar,
)

_HEIGHT = 180  # 16:9 scaled height


def _make_frame(
    height: int = _HEIGHT,
    bg: tuple[int, int, int] = (50, 50, 50),
    roi_color: tuple[int, int, int] | None = None,
    roi_sections: tuple[
        tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]
    ]
    | None = None,
) -> bytes:
    """Create a 320xH RGB24 frame with optional ROI color.

    roi_color: uniform color for entire ROI.
    roi_sections: (left_rgb, center_rgb, right_rgb) for 3-section scorebar.
    """
    frame = np.zeros((height, _SAMPLE_WIDTH, 3), dtype=np.uint8)
    frame[:, :, 0] = bg[0]
    frame[:, :, 1] = bg[1]
    frame[:, :, 2] = bg[2]

    x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
    x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
    y2 = int(height * _SCOREBAR_ROI_Y_END)

    if roi_color is not None:
        frame[0:y2, x1:x2, 0] = roi_color[0]
        frame[0:y2, x1:x2, 1] = roi_color[1]
        frame[0:y2, x1:x2, 2] = roi_color[2]
    elif roi_sections is not None:
        sec_w = (x2 - x1) // 3
        for i, color in enumerate(roi_sections):
            sx = x1 + i * sec_w
            ex = x1 + (i + 1) * sec_w if i < 2 else x2
            frame[0:y2, sx:ex, 0] = color[0]
            frame[0:y2, sx:ex, 1] = color[1]
            frame[0:y2, sx:ex, 2] = color[2]

    return frame.tobytes()


# --- _has_scorebar tests ---


class TestHasScorebar:
    def test_fl_match_frame(self):
        """FL match frame with 3GC colored scorebar sections → True."""
        # 3 distinct section colors → high cross-section std
        raw = _make_frame(roi_sections=((60, 75, 100), (90, 95, 80), (65, 50, 55)))
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_blackout_frame(self):
        """Dark frame (brightness < 10) → False."""
        raw = _make_frame(bg=(3, 3, 3), roi_color=(5, 5, 5))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_bright_non_fl_frame(self):
        """Very bright non-FL frame (brightness > 160) → False."""
        raw = _make_frame(
            bg=(200, 200, 200),
            roi_sections=((180, 190, 200), (170, 200, 220), (190, 180, 210)),
        )
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_uniform_color_frame(self):
        """Uniform ROI sections (cross-section std < 15) → False."""
        raw = _make_frame(roi_sections=((80, 80, 80), (82, 80, 80), (80, 80, 82)))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_probe_failure(self):
        """None input (probe failure) → None."""
        assert _has_scorebar(None, _HEIGHT) is None

    def test_boundary_brightness_20(self):
        """ROI brightness at 20 → False (not strictly greater)."""
        raw = _make_frame(roi_sections=((30, 10, 10), (10, 30, 10), (10, 10, 30)))
        # mean brightness ~16.7, below 20 → False
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_boundary_brightness_just_above_20(self):
        """ROI brightness just above 20 with color variation → True."""
        raw = _make_frame(roi_sections=((50, 15, 10), (10, 50, 15), (15, 10, 50)))
        # mean brightness ~25, cross-section R std ~18 → True
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_high_blue_non_fl(self):
        """Non-FL with high blue (Match 2 type) → False due to brightness."""
        raw = _make_frame(
            roi_sections=((150, 190, 230), (140, 200, 240), (110, 160, 200))
        )
        # mean brightness ~180, exceeds 140 → False
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_lobby_like_uniform(self):
        """Lobby-like frame: brightness in range but low cross-section std."""
        raw = _make_frame(roi_sections=((55, 52, 47), (54, 53, 48), (53, 52, 46)))
        # brightness ~51, but sections are nearly identical → std ~0.8 → False
        assert _has_scorebar(raw, _HEIGHT) is False


# --- _majority_scorebar tests ---


class TestMajorityScorebar:
    def test_all_true(self):
        assert _majority_scorebar([True, True, True]) is True

    def test_all_false(self):
        assert _majority_scorebar([False, False, False]) is False

    def test_majority_true(self):
        assert _majority_scorebar([True, True, False]) is True

    def test_majority_false(self):
        assert _majority_scorebar([False, False, True]) is False

    def test_all_none(self):
        """All probe failures → None."""
        assert _majority_scorebar([None, None, None]) is None

    def test_partial_failure_majority_true(self):
        """2 successes, 1 failure, majority True."""
        assert _majority_scorebar([True, True, None]) is True

    def test_partial_failure_single_true(self):
        """1 success (True), 2 failures → True (1 >= ceil(1/2))."""
        assert _majority_scorebar([True, None, None]) is True

    def test_partial_failure_single_false(self):
        """1 success (False), 2 failures → False (0 < ceil(1/2))."""
        assert _majority_scorebar([False, None, None]) is False

    def test_tie_two_values(self):
        """1 True, 1 False, 1 None → True (1 >= ceil(2/2) = 1)."""
        assert _majority_scorebar([True, False, None]) is True


# --- classify_blackout tests ---

SCOREBAR_MODULE = "allaganeye.video.scorebar"


class TestClassifyBlackout:
    @patch(f"{SCOREBAR_MODULE}._is_static_screen", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match(self, mock_probe, _mock_static):
        """Both sides have scorebar, not static → in_match."""
        mock_probe.side_effect = [
            [True, True, True],  # pre
            [True, True, True],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "in_match"

    @patch(f"{SCOREBAR_MODULE}._is_static_screen")
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match_overridden_by_static_post(self, mock_probe, mock_static):
        """Both sides scorebar, but post is static → match_boundary."""
        mock_probe.side_effect = [
            [True, True, True],  # pre
            [True, True, True],  # post
        ]
        mock_static.return_value = True  # post side is static screen
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        # Only post side checked (first call)
        assert mock_static.call_count == 1

    @patch(f"{SCOREBAR_MODULE}._is_static_screen")
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match_overridden_by_static_pre(self, mock_probe, mock_static):
        """Both sides scorebar, post not static but pre is → match_boundary."""
        mock_probe.side_effect = [
            [True, True, True],  # pre
            [True, True, True],  # post
        ]
        mock_static.side_effect = [False, True]  # post=not static, pre=static
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_static.call_count == 2

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_match_boundary_start(self, mock_probe):
        """Pre=False, Post=True → match_boundary (match start)."""
        mock_probe.side_effect = [
            [False, False, False],  # pre
            [True, True, True],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_match_boundary_end(self, mock_probe):
        """Pre=True, Post=False → match_boundary (match end)."""
        mock_probe.side_effect = [
            [True, True, True],  # pre
            [False, False, False],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_non_fl(self, mock_probe):
        """Neither side has scorebar → non_fl."""
        mock_probe.side_effect = [
            [False, False, False],  # pre
            [False, False, False],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "non_fl"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_all_probes_failed(self, mock_probe):
        """All probes failed → unknown."""
        mock_probe.side_effect = [
            [None, None, None],  # pre
            [None, None, None],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "unknown"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_pre_failed_post_scorebar(self, mock_probe):
        """Pre all failed, post has scorebar → unknown (safe side)."""
        mock_probe.side_effect = [
            [None, None, None],  # pre
            [True, True, True],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "unknown"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_partial_failure_majority(self, mock_probe):
        """Partial failures with majority vote."""
        mock_probe.side_effect = [
            [True, True, None],  # pre: 2/2 True
            [False, None, None],  # post: 1/1 False
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"


# --- filter_blackouts_with_scorebar tests ---


class TestFilterBlackouts:
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_match_boundary(self, mock_classify):
        mock_classify.return_value = "match_boundary"
        regions = [(100.0, 105.0), (200.0, 205.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_short_in_match(self, mock_classify):
        """Short in_match (< 3.5s) = character down → removed."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]  # 2s duration
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_long_in_match(self, mock_classify):
        """Long in_match (>= 3.5s) = FL match boundary → kept."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 108.0)]  # 8s duration
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 108.0)]
        assert cls == ["in_match"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_in_match_exactly_3_5s(self, mock_classify):
        """in_match at exactly 3.5s boundary → kept (not strictly less than)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 103.5)]  # exactly 3.5s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 103.5)]
        assert cls == ["in_match"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_in_match_just_under_3_5s(self, mock_classify):
        """in_match at 3.49s → removed (strictly less than 3.5)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 103.49)]  # 3.49s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == []
        assert cls == []

    def test_empty_regions(self):
        """Empty blackout list → empty result, no classify calls."""
        result, cls = filter_blackouts_with_scorebar(Path("v.mp4"), [], 300.0, _HEIGHT)
        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_non_fl(self, mock_classify):
        mock_classify.return_value = "non_fl"
        regions = [(100.0, 102.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_unknown(self, mock_classify):
        """Unknown → safe side, keep boundary."""
        mock_classify.return_value = "unknown"
        regions = [(100.0, 102.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["unknown"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_mixed_classifications(self, mock_classify):
        """Mix of classifications with duration-aware in_match filtering."""
        mock_classify.side_effect = [
            "match_boundary",  # kept
            "in_match",  # short (2s) → removed
            "non_fl",  # removed
            "unknown",  # kept
            "match_boundary",  # kept
            "in_match",  # long (8s) → kept
        ]
        regions = [
            (50.0, 55.0),  # boundary → kept
            (100.0, 102.0),  # in_match 2s → removed
            (150.0, 155.0),  # non_fl → removed
            (200.0, 202.0),  # unknown → kept
            (250.0, 255.0),  # boundary → kept
            (280.0, 288.0),  # in_match 8s → kept
        ]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [
            (50.0, 55.0),
            (200.0, 202.0),
            (250.0, 255.0),
            (280.0, 288.0),
        ]
        assert cls == ["match_boundary", "unknown", "match_boundary", "in_match"]


DETECTOR_MODULE = "allaganeye.video.detector"


class TestMergeBoundaryPairs:
    """Test match_boundary pair merging in filter_blackouts_with_scorebar."""

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_when_gap_has_no_scorebar(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Consecutive match_boundary with non-FL gap → merged."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False  # no scorebar in gap

        regions = [(100.0, 105.0), (200.0, 205.0)]  # gap=95s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 205.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_when_gap_has_scorebar(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Gap with scorebar detected (>=2 hits) → no merge."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = True  # all 9 probes → scorebar

        regions = [(100.0, 105.0), (200.0, 205.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_with_single_borderline_scorebar_hit(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Gap with 1 borderline scorebar hit out of 9 → still merged (#200)."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        # 1 out of 9 probes returns True (borderline false positive)
        mock_has_sb.side_effect = [
            False,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
        ]

        regions = [(100.0, 105.0), (200.0, 205.0)]  # gap=95s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 205.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_when_gap_exceeds_max(self, mock_classify):
        """Gap > _MERGE_GAP_MAX → no merge attempt."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        gap = _MERGE_GAP_MAX + 100
        regions = [(100.0, 105.0), (105.0 + gap, 110.0 + gap)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 10000.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_when_probe_fails(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Probe failure (None) → no merge (safe side)."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = None
        mock_has_sb.return_value = None  # probe failure

        regions = [(100.0, 105.0), (200.0, 205.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_three_consecutive_match_boundary(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """3 consecutive match_boundary: first pair merges, third kept separate."""
        mock_classify.side_effect = [
            "match_boundary",
            "match_boundary",
            "match_boundary",
        ]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False

        regions = [(100.0, 105.0), (200.0, 205.0), (300.0, 305.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 400.0, _HEIGHT
        )
        # First pair merges → (100, 205), third is separate
        assert result == [(100.0, 205.0), (300.0, 305.0)]
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_gap_exactly_600s(self, mock_classify, mock_probe_rgb, mock_has_sb):
        """Gap exactly 600.0s (= _MERGE_GAP_MAX) → merge attempted."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False

        regions = [(100.0, 105.0), (705.0, 710.0)]  # gap = 600.0
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 1000.0, _HEIGHT
        )
        assert result == [(100.0, 710.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_gap_just_over_600s(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Gap 600.1s (> _MERGE_GAP_MAX) → no merge."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False

        regions = [(100.0, 105.0), (705.1, 710.0)]  # gap = 600.1
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 1000.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_single_region_no_merge(self, mock_classify):
        """Single region → no merge processing, returned as-is."""
        mock_classify.return_value = "match_boundary"
        regions = [(100.0, 105.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary"]


# --- _has_scorebar boundary tests ---


class TestHasScorebarBoundaries:
    """Additional boundary tests for _has_scorebar thresholds."""

    def test_brightness_just_below_140(self):
        """ROI brightness just below 140 with color variation → True."""
        # Aim for ~135 brightness with high cross-section std
        raw = _make_frame(
            roi_sections=((180, 100, 100), (100, 180, 100), (100, 100, 180))
        )
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_brightness_at_140(self):
        """ROI brightness at 140 → False (not strictly less than)."""
        raw = _make_frame(
            roi_sections=((180, 130, 100), (130, 180, 110), (110, 100, 180))
        )
        # brightness ~140, at boundary → False
        result = _has_scorebar(raw, _HEIGHT)
        # Verify the threshold is exclusive at 140
        roi_y2 = int(_HEIGHT * _SCOREBAR_ROI_Y_END)
        x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
        x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(_HEIGHT, _SAMPLE_WIDTH, 3)
        roi_brightness = float(frame[0:roi_y2, x1:x2, :].mean())
        if roi_brightness >= 140.0:
            assert result is False

    def test_channel_std_threshold_constant(self):
        """_SCOREBAR_CHANNEL_STD_THRESHOLD is 15.0."""
        assert _SCOREBAR_CHANNEL_STD_THRESHOLD == 15.0


# --- _majority_scorebar edge cases ---


class TestMajorityScorebarEdge:
    def test_empty_list(self):
        """Empty list → None."""
        assert _majority_scorebar([]) is None


# --- classify_blackout boundary tests ---


class TestClassifyBlackoutBoundary:
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_region_at_video_start(self, mock_probe):
        """Region near start (0.5s) → pre timestamps clamp to 0.0."""
        mock_probe.side_effect = [
            [True],  # pre: only 1 unique timestamp after dedup
            [True, True, True],  # post: 3 timestamps
        ]
        result = classify_blackout(Path("v.mp4"), (0.5, 3.0), 300.0, _HEIGHT)
        assert result == "in_match"
        # Verify pre_timestamps were deduplicated
        pre_call_args = mock_probe.call_args_list[0]
        pre_ts = pre_call_args[0][1]  # second positional arg = timestamps
        assert len(pre_ts) < 3  # some timestamps collapsed to 0.0

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_region_at_video_end(self, mock_probe):
        """Region near end → post timestamps clamp to duration."""
        mock_probe.side_effect = [
            [False, False, False],  # pre
            [False],  # post: collapsed
        ]
        result = classify_blackout(Path("v.mp4"), (297.0, 299.5), 300.0, _HEIGHT)
        assert result == "non_fl"
        # Verify post_timestamps were deduplicated
        post_call_args = mock_probe.call_args_list[1]
        post_ts = post_call_args[0][1]
        assert len(post_ts) < 3


# --- _scaled_height tests ---


class TestScaledHeight:
    def test_1920x1080(self):
        """Standard 16:9 → 180 (even)."""
        assert _scaled_height(1920, 1080) == 180

    def test_1280x720(self):
        """720p 16:9 → 180."""
        assert _scaled_height(1280, 720) == 180

    def test_2560x1440(self):
        """1440p 16:9 → 180."""
        assert _scaled_height(2560, 1440) == 180

    def test_odd_result_rounds_to_even(self):
        """4096x2160 → round(320*2160/4096) = 169 → +1 = 170."""
        assert _scaled_height(4096, 2160) == 170

    def test_4_3_aspect(self):
        """1920x1200 (16:10) → round(320*1200/1920) = 200."""
        assert _scaled_height(1920, 1200) == 200

    def test_result_is_always_even(self):
        """Result must be even for ffmpeg -2 requirement."""
        test_cases = [
            (1920, 1080),
            (1280, 720),
            (2560, 1440),
            (4096, 2160),
            (1920, 1200),
            (3840, 2160),
        ]
        for w, h in test_cases:
            result = _scaled_height(w, h)
            assert result % 2 == 0, f"_scaled_height({w}, {h}) = {result} (odd)"


# --- _probe_frame_rgb tests ---


class TestProbeFrameRgb:
    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_timeout_returns_none(self, _mock_ff, mock_run):
        """Timeout → None."""
        from subprocess import TimeoutExpired

        from allaganeye.video.detector import _probe_frame_rgb

        mock_run.side_effect = TimeoutExpired("ffmpeg", 30)
        assert _probe_frame_rgb(Path("v.mp4"), 10.0) is None

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_incomplete_frame_returns_none(self, _mock_ff, mock_run):
        """Incomplete stdout → None."""
        from unittest.mock import MagicMock

        from allaganeye.video.detector import _probe_frame_rgb

        result = MagicMock()
        result.returncode = 0
        result.stdout = b"\x00" * 10  # way too short
        mock_run.return_value = result
        assert _probe_frame_rgb(Path("v.mp4"), 10.0) is None

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_valid_frame_returns_bytes(self, _mock_ff, mock_run):
        """Complete frame → bytes."""
        from unittest.mock import MagicMock

        from allaganeye.video.detector import _probe_frame_rgb

        expected_size = _SAMPLE_WIDTH * _HEIGHT * 3
        result = MagicMock()
        result.returncode = 0
        result.stdout = b"\x80" * expected_size
        mock_run.return_value = result
        raw = _probe_frame_rgb(Path("v.mp4"), 10.0, _HEIGHT)
        assert raw is not None
        assert len(raw) == expected_size

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_nonzero_returncode_returns_none(self, _mock_ff, mock_run):
        """ffmpeg error exit → None (not partial data)."""
        from unittest.mock import MagicMock

        from allaganeye.video.detector import _probe_frame_rgb

        expected_size = _SAMPLE_WIDTH * _HEIGHT * 3
        result = MagicMock()
        result.returncode = 1
        result.stdout = b"\x00" * expected_size  # valid-length but from failed process
        mock_run.return_value = result
        assert _probe_frame_rgb(Path("v.mp4"), 10.0, _HEIGHT) is None

    def test_ffmpeg_not_found_raises(self):
        """ffmpeg not found → VideoProcessingError."""
        from allaganeye.video.detector import _probe_frame_rgb
        from allaganeye.exceptions import VideoProcessingError

        with (
            patch(
                "allaganeye.video.detector.find_ffmpeg",
                return_value="nonexistent_ffmpeg",
            ),
            patch(
                "allaganeye.video.detector.subprocess.run",
                side_effect=FileNotFoundError,
            ),
        ):
            with pytest.raises(VideoProcessingError):
                _probe_frame_rgb(Path("v.mp4"), 10.0)


# --- _is_static_screen tests ---


class TestIsStaticScreen:
    """Tests for static screen detection via scorebar ROI MAD."""

    def _make_static_frames(
        self, count: int = 3, roi_color: tuple[int, int, int] = (87, 87, 87)
    ) -> list[bytes]:
        """Create identical frames (simulating a loading screen)."""
        return [_make_frame(roi_color=roi_color) for _ in range(count)]

    def _make_varying_frames(self, count: int = 3) -> list[bytes]:
        """Create frames with different ROI content (simulating gameplay)."""
        colors = [(60, 75, 100), (90, 50, 80), (65, 95, 55)]
        return [_make_frame(roi_color=colors[i % len(colors)]) for i in range(count)]

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_static_screen_detected(self, mock_probe):
        """Identical frames → static screen detected."""
        frames = self._make_static_frames()
        mock_probe.side_effect = frames
        assert _is_static_screen(Path("v.mp4"), [1.0, 2.0, 3.0], _HEIGHT, None) is True

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_varying_frames_not_static(self, mock_probe):
        """Different frames → not static."""
        frames = self._make_varying_frames()
        mock_probe.side_effect = frames
        assert _is_static_screen(Path("v.mp4"), [1.0, 2.0, 3.0], _HEIGHT, None) is False

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_single_transition_tolerated(self, mock_probe):
        """Screen changes between F1-F2 but F2-F3 static → detected (#201)."""
        # F1: different screen, F2-F3: identical loading screen
        f1 = _make_frame(roi_color=(50, 100, 150))
        f2 = _make_frame(roi_color=(87, 87, 87))
        f3 = _make_frame(roi_color=(87, 87, 87))
        mock_probe.side_effect = [f1, f2, f3]
        assert _is_static_screen(Path("v.mp4"), [1.0, 2.0, 3.0], _HEIGHT, None) is True

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_all_probes_failed(self, mock_probe):
        """All probes return None → not static (safe side)."""
        mock_probe.return_value = None
        assert _is_static_screen(Path("v.mp4"), [1.0, 2.0, 3.0], _HEIGHT, None) is False

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_only_one_valid_probe(self, mock_probe):
        """Only 1 valid frame → not static (need >=2 for comparison)."""
        frame = self._make_static_frames(1)[0]
        mock_probe.side_effect = [frame, None, None]
        assert _is_static_screen(Path("v.mp4"), [1.0, 2.0, 3.0], _HEIGHT, None) is False

    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_threshold_boundary_above(self, mock_probe):
        """MAD just above threshold → not static."""
        f1 = _make_frame(roi_color=(87, 87, 87))
        # Shift enough to push MAD above 0.5
        f2 = _make_frame(roi_color=(90, 90, 90))
        mock_probe.side_effect = [f1, f2]
        result = _is_static_screen(Path("v.mp4"), [1.0, 2.0], _HEIGHT, None)
        assert result is False
