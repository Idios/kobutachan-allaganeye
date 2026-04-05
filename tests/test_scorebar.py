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
) -> bytes:
    """Create a 320xH RGB24 frame with optional distinct ROI color."""
    frame = np.zeros((height, _SAMPLE_WIDTH, 3), dtype=np.uint8)
    frame[:, :, 0] = bg[0]
    frame[:, :, 1] = bg[1]
    frame[:, :, 2] = bg[2]

    if roi_color is not None:
        x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
        x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
        y2 = int(height * _SCOREBAR_ROI_Y_END)
        frame[0:y2, x1:x2, 0] = roi_color[0]
        frame[0:y2, x1:x2, 1] = roi_color[1]
        frame[0:y2, x1:x2, 2] = roi_color[2]

    return frame.tobytes()


# --- _has_scorebar tests ---


class TestHasScorebar:
    def test_fl_match_frame(self):
        """FL match frame with colored scorebar → True."""
        # ROI: R=120, G=60, B=90 → brightness ~90, std ~24.5
        raw = _make_frame(roi_color=(120, 60, 90))
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_blackout_frame(self):
        """Dark frame (brightness < 10) → False."""
        raw = _make_frame(bg=(3, 3, 3), roi_color=(5, 5, 5))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_bright_non_fl_frame(self):
        """Very bright non-FL frame (brightness > 160) → False."""
        raw = _make_frame(bg=(200, 200, 200), roi_color=(180, 190, 200))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_uniform_color_frame(self):
        """Uniform ROI color (RGB std < 5) → False."""
        raw = _make_frame(roi_color=(80, 80, 80))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_probe_failure(self):
        """None input (probe failure) → None."""
        assert _has_scorebar(None, _HEIGHT) is None

    def test_boundary_brightness_20(self):
        """ROI brightness exactly 20 → False (not strictly greater)."""
        # ROI with mean brightness ~20, but with color variation
        raw = _make_frame(roi_color=(30, 15, 15))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_boundary_brightness_just_above_20(self):
        """ROI brightness just above 20 with color variation → True."""
        raw = _make_frame(roi_color=(40, 20, 10))
        result = _has_scorebar(raw, _HEIGHT)
        # brightness ~23.3, std ~12.5 → True
        assert result is True

    def test_high_blue_non_fl(self):
        """Non-FL with high blue (Match 2 type, roi_b > 200) → False."""
        raw = _make_frame(roi_color=(170, 170, 225))
        # brightness ~188, exceeds 140 → False
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
    def test_removes_in_match(self, mock_classify):
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == []

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
        """Mix of classifications: only boundary and unknown kept."""
        mock_classify.side_effect = [
            "match_boundary",
            "in_match",
            "non_fl",
            "unknown",
            "match_boundary",
        ]
        regions = [
            (50.0, 55.0),
            (100.0, 102.0),
            (150.0, 155.0),
            (200.0, 202.0),
            (250.0, 255.0),
        ]
        result = filter_blackouts_with_scorebar(Path("v.mp4"), regions, 300.0, _HEIGHT)
        assert result == [(50.0, 55.0), (200.0, 202.0), (250.0, 255.0)]
