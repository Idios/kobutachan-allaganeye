"""Tests for scorebar detection logic."""

from pathlib import Path
from unittest.mock import patch

import numpy as np

from allaganeye.video.detector import (
    _SAMPLE_WIDTH,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _has_scorebar,
)
from allaganeye.video.scorebar import (
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
        """Uniform ROI sections (cross-section std < 8) → False."""
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
        raw = _make_frame(roi_sections=((40, 15, 10), (10, 40, 15), (15, 10, 40)))
        # mean brightness ~21.7, cross-section R std ~16 → True
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
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match(self, mock_probe):
        """Both sides have scorebar → in_match."""
        mock_probe.side_effect = [
            [True, True, True],  # pre
            [True, True, True],  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "in_match"

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
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == regions

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_short_in_match(self, mock_classify):
        """Short in_match (< 5s) = character down → removed."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]  # 2s duration
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_long_in_match(self, mock_classify):
        """Long in_match (>= 5s) = FL match boundary → kept."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 108.0)]  # 8s duration
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == [(100.0, 108.0)]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_non_fl(self, mock_classify):
        mock_classify.return_value = "non_fl"
        regions = [(100.0, 102.0)]
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_unknown(self, mock_classify):
        """Unknown → safe side, keep boundary."""
        mock_classify.return_value = "unknown"
        regions = [(100.0, 102.0)]
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == regions

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
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == [
            (50.0, 55.0),
            (200.0, 202.0),
            (250.0, 255.0),
            (280.0, 288.0),
        ]
