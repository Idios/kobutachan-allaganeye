"""Tests for scorebar detection logic."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from allaganeye.audio.matcher import BgmHit
from allaganeye.video.capture_region import CaptureRegion
from allaganeye.video.detector import (
    _SAMPLE_WIDTH,
    _SCOREBAR_CHANNEL_STD_THRESHOLD,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _has_scorebar,
    _scaled_height,
)
from allaganeye.video import scorebar as sb
from allaganeye.video.scorebar import (
    _band_mad_min,
    _is_static_from_frames,
    _majority_scorebar,
    _probe_scorebar_context,
    classify_blackout,
    filter_blackouts_with_scorebar,
)
from allaganeye.video.probe_state import PresenceState

_HEIGHT = 180  # 16:9 scaled height
_FAKE_FRAME = b"\x00" * (_SAMPLE_WIDTH * _HEIGHT * 3)  # dummy frame for mocks


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
        """FL match frame with 3GC colored scorebar sections -> True."""
        # 3 distinct section colors -> high cross-section std
        raw = _make_frame(roi_sections=((60, 75, 100), (90, 95, 80), (65, 50, 55)))
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_blackout_frame(self):
        """Dark frame (brightness < 10) -> False."""
        raw = _make_frame(bg=(3, 3, 3), roi_color=(5, 5, 5))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_bright_non_fl_frame(self):
        """Very bright non-FL frame (brightness > 160) -> False."""
        raw = _make_frame(
            bg=(200, 200, 200),
            roi_sections=((180, 190, 200), (170, 200, 220), (190, 180, 210)),
        )
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_uniform_color_frame(self):
        """Uniform ROI sections (cross-section std < 15) -> False."""
        raw = _make_frame(roi_sections=((80, 80, 80), (82, 80, 80), (80, 80, 82)))
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_probe_failure(self):
        """None input (probe failure) -> None."""
        assert _has_scorebar(None, _HEIGHT) is None

    def test_boundary_brightness_20(self):
        """ROI brightness at 20 -> False (not strictly greater)."""
        raw = _make_frame(roi_sections=((30, 10, 10), (10, 30, 10), (10, 10, 30)))
        # mean brightness ~16.7, below 20 -> False
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_boundary_brightness_just_above_20(self):
        """ROI brightness just above 20 with color variation -> True."""
        raw = _make_frame(roi_sections=((50, 15, 10), (10, 50, 15), (15, 10, 50)))
        # mean brightness ~25, cross-section R std ~18 -> True
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_high_blue_non_fl(self):
        """Non-FL with high blue (Match 2 type) -> False due to brightness."""
        raw = _make_frame(
            roi_sections=((150, 190, 230), (140, 200, 240), (110, 160, 200))
        )
        # mean brightness ~180, exceeds 140 -> False
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_lobby_like_uniform(self):
        """Lobby-like frame: brightness in range but low cross-section std."""
        raw = _make_frame(roi_sections=((55, 52, 47), (54, 53, 48), (53, 52, 46)))
        # brightness ~51, but sections are nearly identical -> std ~0.8 -> False
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_single_channel_gradient_rejected(self):
        """Loading screen gradient: 1 channel high std, others low -> False (A1).

        Simulates a loading screen where R varies across sections (std > 15)
        but G and B are nearly uniform (std < 12).
        """
        raw = _make_frame(roi_sections=((90, 60, 60), (50, 58, 62), (70, 62, 58)))
        # R std: std([90,50,70]) ~= 16.3 > 15 (passes primary)
        # G std: std([60,58,62]) ~= 1.6 < 12 (fails secondary)
        # B std: std([60,62,58]) ~= 1.6 < 12 (fails secondary)
        # secondary_std ~= 1.6 <= 12 -> False (A1)
        assert _has_scorebar(raw, _HEIGHT) is False

    def test_smooth_multi_channel_gradient_rejected(self):
        """Smooth gradient with multi-channel variation but no sharp edges -> False (A2).

        Sections have gradually changing colors (no sharp band boundaries).
        """
        raw = _make_frame(roi_sections=((60, 80, 50), (65, 55, 80), (80, 65, 55)))
        # R std: std([60,65,80]) ~= 8.5
        # G std: std([80,55,65]) ~= 10.3
        # B std: std([50,80,55]) ~= 13.3
        # max=13.3 < 15 -> actually fails primary check, not A2
        # Need values that pass primary+A1 but fail A2
        # Use per-pixel smooth gradient instead of uniform sections
        # Create a frame with smooth gradient across the ROI (no sharp edges)
        frame = np.zeros((_HEIGHT, _SAMPLE_WIDTH, 3), dtype=np.uint8)
        frame[:] = (50, 50, 50)
        x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
        x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
        y2 = int(_HEIGHT * _SCOREBAR_ROI_Y_END)
        roi_w = x2 - x1
        for x in range(roi_w):
            t = x / roi_w
            # Smooth gradient: R decreases, G stays, B increases
            r = int(100 - 60 * t)  # 100 -> 40
            g = int(50 + 30 * t)  # 50 -> 80
            b = int(40 + 70 * t)  # 40 -> 110
            frame[0:y2, x1 + x, :] = (r, g, b)
        raw = frame.tobytes()
        # Section means approximate:
        # Left: R~=90,G~=55,B~=52  Center: R~=70,G~=65,B~=75  Right: R~=50,G~=75,B~=98
        # R std ~= 16, G std ~= 8, B std ~= 19 -> max 19>15, secondary 16>12 OK
        # But max edge per pixel ~= 1-2 (smooth gradient) < 8 -> False (A2)
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
        """All probe failures -> None."""
        assert _majority_scorebar([None, None, None]) is None

    def test_partial_failure_majority_true(self):
        """2 successes, 1 failure, majority True."""
        assert _majority_scorebar([True, True, None]) is True

    def test_partial_failure_single_true(self):
        """1 success (True), 2 failures -> True (1 >= ceil(1/2))."""
        assert _majority_scorebar([True, None, None]) is True

    def test_partial_failure_single_false(self):
        """1 success (False), 2 failures -> False (0 < ceil(1/2))."""
        assert _majority_scorebar([False, None, None]) is False

    def test_tie_two_values(self):
        """1 True, 1 False, 1 None -> True (1 >= ceil(2/2) = 1)."""
        assert _majority_scorebar([True, False, None]) is True


# --- classify_blackout tests ---

SCOREBAR_MODULE = "allaganeye.video.scorebar"


class TestClassifyBlackout:
    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match(self, mock_probe, _mock_static):
        """Both sides have scorebar, not static -> in_match."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, True], [f, f, f], [None, None, None]),  # pre
            ([True, True, True], [f, f, f], [None, None, None]),  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "in_match"

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames")
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match_overridden_by_static_post(self, mock_probe, mock_static):
        """Both sides scorebar, but post is static -> match_boundary."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, True], [f, f, f], [None, None, None]),  # pre
            ([True, True, True], [f, f, f], [None, None, None]),  # post
        ]
        mock_static.return_value = True  # post side is static screen
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_static.call_count == 1

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames")
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_in_match_overridden_by_static_pre(self, mock_probe, mock_static):
        """Both sides scorebar, post not static but pre is -> match_boundary."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, True], [f, f, f], [None, None, None]),  # pre
            ([True, True, True], [f, f, f], [None, None, None]),  # post
        ]
        mock_static.side_effect = [False, True]  # post=not static, pre=static
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_static.call_count == 2

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_match_boundary_start(self, mock_probe):
        """Pre=False, Post=True -> match_boundary (match start)."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre
            ([True, True, True], [f, f, f], [None, None, None]),  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_match_boundary_end(self, mock_probe):
        """Pre=True, Post=False -> match_boundary (match end)."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, True], [f, f, f], [None, None, None]),  # pre
            ([False, False, False], [f, f, f], [None, None, None]),  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "match_boundary"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_non_fl(self, mock_probe):
        """Neither side has scorebar -> non_fl (re-probe also confirms)."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre initial
            ([False, False, False], [f, f, f], [None, None, None]),  # post initial
            ([False, False], [f, f], [None, None]),  # pre re-probe (#524)
            ([False, False], [f, f], [None, None]),  # post re-probe (#524)
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "non_fl"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_all_probes_failed(self, mock_probe):
        """All probes failed (initial+re-probe) -> unknown."""
        mock_probe.side_effect = [
            ([None, None, None], [None, None, None], [None, None, None]),  # pre initial
            (
                [None, None, None],
                [None, None, None],
                [None, None, None],
            ),  # post initial
            ([None, None], [None, None], [None, None]),  # pre re-probe (#524)
            ([None, None], [None, None], [None, None]),  # post re-probe (#524)
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "unknown"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_pre_failed_post_scorebar(self, mock_probe):
        """Pre all failed, post has scorebar -> unknown (safe side)."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([None, None, None], [None, None, None], [None, None, None]),  # pre
            ([True, True, True], [f, f, f], [None, None, None]),  # post
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 102.0), 300.0, _HEIGHT)
        assert result == "unknown"

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_partial_failure_majority(self, mock_probe):
        """Partial failures with majority vote."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, None], [f, f, None], [None, None, None]),  # pre: 2/2 True
            (
                [False, None, None],
                [f, None, None],
                [None, None, None],
            ),  # post: 1/1 False
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
        """Short in_match (< 3.5s) = character down -> removed."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]  # 2s duration
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_long_in_match(self, mock_classify):
        """Long in_match (>= 3.5s) = FL match boundary -> kept."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 108.0)]  # 8s duration
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 108.0)]
        assert cls == ["in_match"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_keeps_in_match_exactly_3_5s(self, mock_classify):
        """in_match at exactly 3.5s boundary -> kept (not strictly less than)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 103.5)]  # exactly 3.5s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == [(100.0, 103.5)]
        assert cls == ["in_match"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_removes_in_match_just_under_3_5s(self, mock_classify):
        """in_match at 3.49s -> removed (strictly less than 3.5)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 103.49)]  # 3.49s
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == []
        assert cls == []

    def test_empty_regions(self):
        """Empty blackout list -> empty result, no classify calls."""
        result, cls = filter_blackouts_with_scorebar(Path("v.mp4"), [], 300.0, _HEIGHT)
        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_stats_records_raw_counts(self, mock_classify):
        """stats dict receives raw classification counts (issue #336).

        Non-FL and short in_match regions are dropped from the return but
        must still appear in the stats counters so verbose output shows
        the full picture.
        """
        from allaganeye.video.detector import DetectionStats

        mock_classify.side_effect = ["match_boundary", "in_match", "non_fl"]
        regions = [(100.0, 105.0), (200.0, 201.0), (300.0, 302.0)]
        stats: DetectionStats = {}
        result, _ = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 400.0, _HEIGHT, stats=stats
        )
        assert stats.get("scorebar_match_boundary") == 1
        assert stats.get("scorebar_in_match") == 1
        assert stats.get("scorebar_non_fl") == 1
        assert stats.get("audio_promotions") == 0
        # Short in_match and non_fl dropped from return
        assert result == [(100.0, 105.0)]

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
        """Unknown -> safe side, keep boundary."""
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
            "in_match",  # short (2s) -> removed
            "non_fl",  # removed
            "unknown",  # kept
            "match_boundary",  # kept
            "in_match",  # long (8s) -> kept
        ]
        regions = [
            (50.0, 55.0),  # boundary -> kept
            (100.0, 102.0),  # in_match 2s -> removed
            (150.0, 155.0),  # non_fl -> removed
            (200.0, 202.0),  # unknown -> kept
            (250.0, 255.0),  # boundary -> kept
            (280.0, 288.0),  # in_match 8s -> kept
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


class TestAudioPromotion:
    """Audio-based in_match -> match_boundary promotion (#288).

    Fanfare is only searched AFTER the blackout end (post-blackout window),
    not symmetrically, to avoid promoting in-match character-down blackouts
    that happen to precede a legitimate next-match Fanfare.
    """

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_short_in_match_promoted_by_post_fanfare(self, mock_classify):
        """Short in_match with Fanfare 18s after end -> promoted."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]  # 2s, would normally be removed
        audio_hits: list[BgmHit] = [{"timestamp": 120.0, "similarity": 0.72}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == regions
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_long_in_match_promoted_by_post_fanfare(self, mock_classify):
        """Long in_match with Fanfare after end -> promoted."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 108.0)]  # 8s
        audio_hits: list[BgmHit] = [{"timestamp": 120.0, "similarity": 0.68}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == regions
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_pre_blackout_fanfare_does_not_promote(self, mock_classify):
        """Fanfare BEFORE blackout start -> not promoted (prevents in-match false positives)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        # Fanfare from a previous match, ending 50s before this blackout
        audio_hits: list[BgmHit] = [{"timestamp": 50.0, "similarity": 0.85}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_fanfare_far_past_window(self, mock_classify):
        """Fanfare > 60s past end -> not promoted."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        audio_hits: list[BgmHit] = [
            {"timestamp": 200.0, "similarity": 0.80}
        ]  # region_end + 98

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_audio_hits_does_not_change_behavior(self, mock_classify):
        """audio_hits=None -> legacy scorebar-only path (short in_match removed)."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=None
        )

        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_empty_audio_hits_treated_as_no_hits(self, mock_classify):
        """Empty audio_hits list -> no promotion."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=[]
        )

        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_non_in_match_not_affected_by_audio(self, mock_classify):
        """non_fl/match_boundary classifications unchanged by audio hits."""
        mock_classify.side_effect = ["non_fl", "match_boundary"]
        regions = [(100.0, 102.0), (200.0, 205.0)]
        audio_hits: list[BgmHit] = [
            {"timestamp": 110.0, "similarity": 0.90},
            {"timestamp": 210.0, "similarity": 0.88},
        ]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == [(200.0, 205.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_fanfare_at_window_far_edge(self, mock_classify):
        """Fanfare at region_end + 60s -> inclusive end -> promoted."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        audio_hits: list[BgmHit] = [{"timestamp": 162.0, "similarity": 0.66}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == regions
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_fanfare_just_past_window(self, mock_classify):
        """Fanfare at region_end + 60.01s -> outside window, no promotion."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        audio_hits: list[BgmHit] = [{"timestamp": 162.01, "similarity": 0.90}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == []
        assert cls == []

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_fanfare_at_region_end_promoted(self, mock_classify):
        """Fanfare exactly at region_end -> on inclusive lower bound, promoted."""
        mock_classify.return_value = "in_match"
        regions = [(100.0, 102.0)]
        audio_hits: list[BgmHit] = [{"timestamp": 102.0, "similarity": 0.70}]

        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT, audio_hits=audio_hits
        )

        assert result == regions
        assert cls == ["match_boundary"]


DETECTOR_MODULE = "allaganeye.video.detector"


class TestMergeBoundaryPairs:
    """Test match_boundary pair merging in filter_blackouts_with_scorebar."""

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_when_gap_has_no_scorebar(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Consecutive match_boundary with non-FL gap -> merged."""
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
        """Gap with scorebar detected (>=2 hits) -> no merge."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = True  # all 9 probes -> scorebar

        regions = [(100.0, 105.0), (200.0, 205.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_when_any_scorebar_hit(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Gap with any scorebar hit -> no merge (strict zero-hit policy)."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        # 1 out of 9 probes returns True
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

        regions = [(100.0, 105.0), (200.0, 205.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 300.0, _HEIGHT
        )
        # Strict: any scorebar hit blocks merge
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_no_merge_when_probe_fails(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Probe failure (None) -> no merge (safe side)."""
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
        # First pair merges -> (100, 205), third is separate
        assert result == [(100.0, 205.0), (300.0, 305.0)]
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_gap_exactly_600s(self, mock_classify, mock_probe_rgb, mock_has_sb):
        """Gap exactly 600.0s (= _MERGE_GAP_MAX) -> merge attempted."""
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
    def test_no_merge_when_scorebar_detected_in_gap(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Scorebar detected in gap -> no merge (real match content)."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        # One of the gap probes detects scorebar -> no merge
        mock_has_sb.side_effect = [
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
        ]

        regions = [(100.0, 105.0), (705.1, 710.0)]  # gap = 600.1
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 1000.0, _HEIGHT
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]

    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_single_region_no_merge(self, mock_classify):
        """Single region -> no merge processing, returned as-is."""
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
        """ROI brightness just below 140 with color variation -> True."""
        # Aim for ~135 brightness with high cross-section std
        raw = _make_frame(
            roi_sections=((180, 100, 100), (100, 180, 100), (100, 100, 180))
        )
        assert _has_scorebar(raw, _HEIGHT) is True

    def test_brightness_at_140(self):
        """ROI brightness at 140 -> False (not strictly less than)."""
        raw = _make_frame(
            roi_sections=((180, 130, 100), (130, 180, 110), (110, 100, 180))
        )
        # brightness ~140, at boundary -> False
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
        """Empty list -> None."""
        assert _majority_scorebar([]) is None


# --- classify_blackout boundary tests ---


class TestClassifyBlackoutBoundary:
    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_region_at_video_start(self, mock_probe, _mock_static):
        """Region near start (0.5s) -> pre timestamps clamp to 0.0."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True], [f], [None]),  # pre: only 1 unique timestamp after dedup
            ([True, True, True], [f, f, f], [None, None, None]),  # post: 3 timestamps
        ]
        result = classify_blackout(Path("v.mp4"), (0.5, 3.0), 300.0, _HEIGHT)
        assert result == "in_match"
        # Verify pre_timestamps were deduplicated
        pre_call_args = mock_probe.call_args_list[0]
        pre_ts = pre_call_args[0][1]  # second positional arg = timestamps
        assert len(pre_ts) < 3  # some timestamps collapsed to 0.0

    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_region_at_video_end(self, mock_probe):
        """Region near end -> post timestamps clamp to duration.

        Re-probe (#524) fires because both sides are not-True.  Pre re-probe
        runs (291.5/292.5/293.5 are well clear of duration); post re-probe
        timestamps all collapse to 300.0 which dedupes against existing
        post probe -> empty list, so post re-probe is skipped.
        """
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre initial
            ([False], [f], [None]),  # post initial: collapsed
            ([False, False, False], [f, f, f], [None, None, None]),  # pre re-probe
        ]
        result = classify_blackout(Path("v.mp4"), (297.0, 299.5), 300.0, _HEIGHT)
        assert result == "non_fl"
        # Verify post_timestamps were deduplicated
        post_call_args = mock_probe.call_args_list[1]
        post_ts = post_call_args[0][1]
        assert len(post_ts) < 3


# --- classify_blackout re-probe fallback (#524) ---


class TestClassifyBlackoutReProbe:
    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_post_recovers_match_boundary(self, mock_probe, _mock_static):
        """Both pre/post initial=False -> re-probe finds post=True -> match_boundary."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre initial
            ([False, False, False], [f, f, f], [None, None, None]),  # post initial
            ([False, False, False], [f, f, f], [None, None, None]),  # pre re-probe
            ([True, True, True], [f, f, f], [None, None, None]),  # post re-probe
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_probe.call_count == 4
        # post re-probe offsets = region_end + (region_width + 1/2/3)
        # = 108 + 9/10/11 = 117/118/119
        post_re_call = mock_probe.call_args_list[3]
        post_re_ts = post_re_call[0][1]
        assert post_re_ts == [117.0, 118.0, 119.0]

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_pre_recovers_match_boundary(self, mock_probe, _mock_static):
        """Initial both None -> re-probe pre=True, post=False -> match_boundary.

        Post must succeed (False) on re-probe; if it stays None the
        existing "either side None -> unknown" rule keeps the result
        unknown for safety.
        """
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([None, None, None], [None, None, None], [None, None, None]),  # pre initial
            (
                [None, None, None],
                [None, None, None],
                [None, None, None],
            ),  # post initial
            ([True, True, True], [f, f, f], [None, None, None]),  # pre re-probe
            (
                [False, False, False],
                [f, f, f],
                [None, None, None],
            ),  # post re-probe success False
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        # pre re-probe offsets = region_start - (region_width + 3/2/1)
        # = 100 - 11/10/9 = 89/90/91
        pre_re_call = mock_probe.call_args_list[2]
        pre_re_ts = pre_re_call[0][1]
        assert pre_re_ts == [89.0, 90.0, 91.0]

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_skipped_when_pre_true(self, mock_probe, _mock_static):
        """Initial pre=True (any-side True) -> re-probe skipped."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([True, True, True], [f, f, f], [None, None, None]),  # pre initial
            ([False, False, False], [f, f, f], [None, None, None]),  # post initial
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_probe.call_count == 2

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_skipped_when_post_true(self, mock_probe, _mock_static):
        """Initial post=True -> re-probe skipped."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre initial
            ([True, True, True], [f, f, f], [None, None, None]),  # post initial
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_probe.call_count == 2

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_no_change_keeps_non_fl(self, mock_probe, _mock_static):
        """Initial both False + re-probe both False -> non_fl preserved."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False, False, False], [f, f, f], [None, None, None]),  # pre initial
            ([False, False, False], [f, f, f], [None, None, None]),  # post initial
            ([False, False, False], [f, f, f], [None, None, None]),  # pre re-probe
            ([False, False, False], [f, f, f], [None, None, None]),  # post re-probe
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "non_fl"
        assert mock_probe.call_count == 4

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_promotes_unknown_to_non_fl(self, mock_probe, _mock_static):
        """Initial both None + re-probe both False -> non_fl (unknown -> non_fl)."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([None, None, None], [None, None, None], [None, None, None]),  # pre initial
            (
                [None, None, None],
                [None, None, None],
                [None, None, None],
            ),  # post initial
            (
                [False, False, False],
                [f, f, f],
                [None, None, None],
            ),  # pre re-probe success False
            (
                [False, False, False],
                [f, f, f],
                [None, None, None],
            ),  # post re-probe success False
        ]
        result = classify_blackout(Path("v.mp4"), (100.0, 108.0), 300.0, _HEIGHT)
        assert result == "non_fl"

    @patch(f"{SCOREBAR_MODULE}._is_static_from_frames", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_scorebar_context")
    def test_re_probe_clamps_at_video_bounds(self, mock_probe, _mock_static):
        """Pre re-probe collapses to existing 0.0 -> skipped; post re-probe runs."""
        f = _FAKE_FRAME
        mock_probe.side_effect = [
            ([False], [f], [None]),  # pre initial (all 3 collapse to 0.0)
            ([False, False, False], [f, f, f], [None, None, None]),  # post initial
            # pre re-probe: max(0, 0-(5+3/2/1)) = 0.0 -> dedupe vs {0.0} -> empty
            # post re-probe: 5+(5+1/2/3) = 11/12/13
            ([True, True, True], [f, f, f], [None, None, None]),  # post re-probe
        ]
        # region (0.0, 5.0), duration=15, region_width=5.0
        result = classify_blackout(Path("v.mp4"), (0.0, 5.0), 15.0, _HEIGHT)
        assert result == "match_boundary"
        assert mock_probe.call_count == 3
        post_re_call = mock_probe.call_args_list[2]
        post_re_ts = post_re_call[0][1]
        assert post_re_ts == [11.0, 12.0, 13.0]


# --- _scaled_height tests ---


class TestScaledHeight:
    def test_1920x1080(self):
        """Standard 16:9 -> 180 (even)."""
        assert _scaled_height(1920, 1080) == 180

    def test_1280x720(self):
        """720p 16:9 -> 180."""
        assert _scaled_height(1280, 720) == 180

    def test_2560x1440(self):
        """1440p 16:9 -> 180."""
        assert _scaled_height(2560, 1440) == 180

    def test_odd_result_rounds_to_even(self):
        """4096x2160 -> round(320*2160/4096) = 169 -> +1 = 170."""
        assert _scaled_height(4096, 2160) == 170

    def test_4_3_aspect(self):
        """1920x1200 (16:10) -> round(320*1200/1920) = 200."""
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
        """Timeout -> None."""
        from subprocess import TimeoutExpired

        from allaganeye.video.detector import _probe_frame_rgb

        mock_run.side_effect = TimeoutExpired("ffmpeg", 30)
        assert _probe_frame_rgb(Path("v.mp4"), 10.0) is None

    @patch("allaganeye.video.detector.subprocess.run")
    @patch("allaganeye.video.detector.find_ffmpeg", return_value="ffmpeg")
    def test_incomplete_frame_returns_none(self, _mock_ff, mock_run):
        """Incomplete stdout -> None."""
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
        """Complete frame -> bytes."""
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
        """ffmpeg error exit -> None (not partial data)."""
        from unittest.mock import MagicMock

        from allaganeye.video.detector import _probe_frame_rgb

        expected_size = _SAMPLE_WIDTH * _HEIGHT * 3
        result = MagicMock()
        result.returncode = 1
        result.stdout = b"\x00" * expected_size  # valid-length but from failed process
        mock_run.return_value = result
        assert _probe_frame_rgb(Path("v.mp4"), 10.0, _HEIGHT) is None

    def test_ffmpeg_not_found_raises(self):
        """ffmpeg not found -> VideoProcessingError."""
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


# --- _is_static_from_frames tests ---


class TestIsStaticFromFrames:
    """Tests for static screen detection via scorebar ROI MAD (min-based)."""

    def _make_static_frames(
        self, count: int = 3, roi_color: tuple[int, int, int] = (87, 87, 87)
    ) -> list[bytes]:
        """Create identical frames (simulating a loading screen)."""
        return [_make_frame(roi_color=roi_color) for _ in range(count)]

    def _make_varying_frames(self, count: int = 3) -> list[bytes]:
        """Create frames with different ROI content (simulating gameplay)."""
        colors = [(60, 75, 100), (90, 50, 80), (65, 95, 55)]
        return [_make_frame(roi_color=colors[i % len(colors)]) for i in range(count)]

    def test_static_screen_detected(self):
        """Identical frames -> static screen detected."""
        frames = self._make_static_frames()
        assert _is_static_from_frames(frames, _HEIGHT) is True

    def test_varying_frames_not_static(self):
        """Different frames -> not static."""
        frames = self._make_varying_frames()
        assert _is_static_from_frames(frames, _HEIGHT) is False

    def test_all_frames_none(self):
        """All frames None -> not static (safe side)."""
        assert _is_static_from_frames([None, None, None], _HEIGHT) is False

    def test_only_one_valid_frame(self):
        """Only 1 valid frame -> not static (need >=2 for comparison)."""
        frame = self._make_static_frames(1)[0]
        assert _is_static_from_frames([frame, None, None], _HEIGHT) is False

    def test_single_transition_tolerated(self):
        """Screen changes between F1-F2 but F2-F3 static -> detected (#201).

        With min(MADs), a single static pair is enough to detect loading
        screens even when a transition occurs within the probe window.
        """
        f1 = _make_frame(roi_color=(50, 100, 150))
        f2 = _make_frame(roi_color=(87, 87, 87))
        f3 = _make_frame(roi_color=(87, 87, 87))
        # F1-F2: high MAD, F2-F3: MAD=0 -> min(MADs) = 0 < 0.5 -> static
        assert _is_static_from_frames([f1, f2, f3], _HEIGHT) is True

    def test_threshold_boundary_above(self):
        """MAD just above threshold -> not static."""
        f1 = _make_frame(roi_color=(87, 87, 87))
        f2 = _make_frame(roi_color=(90, 90, 90))
        assert _is_static_from_frames([f1, f2], _HEIGHT) is False


# ---------------------------------------------------------------------------
# _probe_scorebar_context unit tests (#224)
# ---------------------------------------------------------------------------


class TestProbeScorebarContext:
    """Direct tests for _probe_scorebar_context."""

    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=_FAKE_FRAME)
    def test_duplicate_timestamps_probed_once(self, mock_probe, mock_has):
        """Duplicate timestamps should be deduplicated -- probe called once."""
        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), [1.0, 1.0, 1.0], _HEIGHT, workers=1
        )
        assert mock_probe.call_count == 1
        assert len(results) == 3
        assert len(frames) == 3
        # All three entries share the same result
        assert results == [True, True, True]
        assert all(f == _FAKE_FRAME for f in frames)

    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=_FAKE_FRAME)
    def test_results_aligned_with_input_order(self, mock_probe, mock_has):
        """Returned lists must follow the original timestamps order."""
        ts = [3.0, 1.0, 2.0]
        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), ts, _HEIGHT, workers=2
        )
        assert len(results) == len(ts)
        assert len(frames) == len(ts)
        # Each unique ts probed exactly once (3 unique -> 3 calls)
        assert mock_probe.call_count == 3

    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=None)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=None)
    def test_probe_failure_returns_none(self, mock_probe, mock_has):
        """When _probe_frame_rgb returns None, results propagate None."""
        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), [1.0, 2.0], _HEIGHT, workers=1
        )
        assert results == [None, None]
        assert frames == [None, None]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_mixed_success_and_failure(self, mock_probe, mock_has):
        """Mix of successful and failed probes -- results match per-ts."""
        mock_probe.side_effect = lambda _path, t, _h: _FAKE_FRAME if t == 1.0 else None
        mock_has.side_effect = lambda raw, _h: True if raw is not None else None

        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), [1.0, 2.0, 1.0], _HEIGHT, workers=1
        )
        # ts=1.0 succeeds (True), ts=2.0 fails (None), ts=1.0 reuses result
        assert results == [True, None, True]
        assert frames[0] == _FAKE_FRAME
        assert frames[1] is None
        assert frames[2] == _FAKE_FRAME

    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=_FAKE_FRAME)
    def test_empty_timestamps(self, mock_probe, mock_has):
        """Empty timestamps list returns empty results."""
        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), [], _HEIGHT, workers=1
        )
        assert results == []
        assert frames == []
        assert mock_probe.call_count == 0

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    def test_video_processing_error_treated_as_none(self, mock_probe, mock_has):
        """VideoProcessingError from future is caught and treated as None."""
        from allaganeye.exceptions import VideoProcessingError

        mock_probe.side_effect = VideoProcessingError("ffmpeg not found")
        mock_has.side_effect = lambda raw, _h: True if raw is not None else None

        results, frames, _loc = _probe_scorebar_context(
            Path("dummy.mp4"), [1.0, 2.0], _HEIGHT, workers=1
        )
        assert results == [None, None]
        assert frames == [None, None]


_W = 320


def _solid_frame(height, fill):
    return np.full((height, _W, 3), fill, dtype=np.uint8).tobytes()


def test_is_static_default_uses_absolute_roi_unchanged():
    h = 180
    # two identical frames -> static (MAD 0) under default absolute ROI
    frames = [_solid_frame(h, 50), _solid_frame(h, 50)]
    assert _is_static_from_frames(frames, h) is True


def test_is_static_band_region_argument_accepted():
    import inspect

    sig = inspect.signature(_is_static_from_frames)
    assert "region" in sig.parameters
    assert sig.parameters["region"].default is None


def test_is_static_band_region_derives_from_normalized_region():
    h = 180
    # Build frames where the absolute scorebar ROI is identical (static) but
    # a band region elsewhere differs between frames. With region given, the
    # band-derived ROI must drive the MAD -> not static.
    a = np.full((h, _W, 3), 50, dtype=np.uint8)
    b = np.full((h, _W, 3), 50, dtype=np.uint8)
    # Region = top-left quadrant (away from the bottom scorebar ROI).
    region = CaptureRegion(0.0, 0.0, 0.25, 0.25)
    bx1 = max(0, int(region.x * _W))
    bx2 = min(_W, int((region.x + region.w) * _W))
    by1 = max(0, int(region.y * h))
    by2 = min(h, int((region.y + region.h) * h))
    b[by1:by2, bx1:bx2, :] = 200  # large diff inside the band region only
    frames = [a.tobytes(), b.tobytes()]

    # Default absolute ROI sees no change -> static.
    assert _is_static_from_frames(frames, h) is True
    # Band region sees the change -> not static.
    assert _is_static_from_frames(frames, h, region=region) is False


def test_probe_context_3tuple_localize_none_by_default(monkeypatch):
    # with_localize omitted -> 3rd element all None, scorebar/raw unchanged.
    monkeypatch.setattr(sb, "_probe_frame_rgb", lambda v, t, h: f"lo{t}".encode())
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", lambda v, t: f"hi{t}".encode())
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: True)
    # _localize_present_from_raw must NOT be called when with_localize is False.
    monkeypatch.setattr(
        sb,
        "_localize_present_from_raw",
        lambda raw: (_ for _ in ()).throw(AssertionError("must not localize")),
    )
    scorebar, raw, loc = sb._probe_scorebar_context(
        Path("x.mp4"), [1.0, 2.0], height=180, workers=1
    )
    assert scorebar == [True, True]
    assert raw == [b"lo1.0", b"lo2.0"]
    assert loc == [None, None]


def test_probe_context_with_localize_populates_3rd(monkeypatch):
    monkeypatch.setattr(sb, "_probe_frame_rgb", lambda v, t, h: b"lo")
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", lambda v, t: f"hi{t}".encode())
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: False)
    monkeypatch.setattr(
        sb,
        "_localize_present_from_raw",
        lambda raw: PresenceState.PRESENT if raw == b"hi1.0" else PresenceState.ABSENT,
    )
    _scorebar, _raw, loc = sb._probe_scorebar_context(
        Path("x.mp4"), [1.0, 2.0], height=180, workers=1, with_localize=True
    )
    assert loc == [PresenceState.PRESENT, PresenceState.ABSENT]


# ---------------------------------------------------------------------------
# _band_mad_min unit tests (Phase 2 B1)
# ---------------------------------------------------------------------------


def _rgb(height, fill):
    return np.full((height, _W, 3), fill, dtype=np.uint8).tobytes()


def test_band_mad_min_absolute_roi_matches_is_static():
    # region=None path must stay bit-exact: identical frames -> MAD 0 -> static.
    frames = [_rgb(180, 50), _rgb(180, 50)]
    assert _band_mad_min(frames, 180) == 0.0
    assert _is_static_from_frames(frames, 180) is True


def test_band_mad_min_returns_none_for_degenerate_band():
    # a band so thin it collapses to an empty crop -> None (not nan, not 0).
    frames = [_rgb(180, 50), _rgb(180, 90)]
    degenerate = CaptureRegion(0.5, 0.5, 0.0, 0.0)
    assert _band_mad_min(frames, 180, degenerate) is None
    # _is_static_from_frames must not raise / must be False for degenerate band.
    assert _is_static_from_frames(frames, 180, degenerate) is False


def test_band_mad_min_none_for_under_two_frames():
    assert _band_mad_min([_rgb(180, 50)], 180) is None


# ---------------------------------------------------------------------------
# _classify_blackout_localize unit tests (Phase 2 B2)
# ---------------------------------------------------------------------------


def test_classify_localize_truth_table(monkeypatch):
    # Inject localize-present per probe set; assert the present-only labels.
    from allaganeye.video import scorebar as sb

    calls = {"n": 0}

    def fake_probe(
        video, ts, height, workers, *, with_localize=False, with_lowres=True
    ):
        # pre call first, post call second (region_width re-probe not triggered
        # unless both not-True).
        calls["n"] += 1
        # pre present, post absent -> match_boundary
        state = PresenceState.PRESENT if calls["n"] == 1 else PresenceState.ABSENT
        return ([None] * len(ts), [b"f"] * len(ts), [state] * len(ts))

    monkeypatch.setattr(sb, "_probe_scorebar_context", fake_probe)
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 1.23)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 103.0), duration=400.0, height=180, workers=1
    )
    assert cls == "match_boundary"


def test_classify_localize_both_present_is_in_match(monkeypatch):
    from allaganeye.video import scorebar as sb

    monkeypatch.setattr(
        sb,
        "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False, with_lowres=True: (
            [None] * len(ts),
            [b"f"] * len(ts),
            [PresenceState.PRESENT] * len(ts),
        ),
    )
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 5.0)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 101.0), duration=400.0, height=180, workers=1
    )
    assert cls == "in_match"


def test_classify_localize_both_absent_is_non_fl(monkeypatch):
    from allaganeye.video import scorebar as sb

    monkeypatch.setattr(
        sb,
        "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False, with_lowres=True: (
            [None] * len(ts),
            [b"f"] * len(ts),
            [PresenceState.ABSENT] * len(ts),
        ),
    )
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 0.1)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 102.0), duration=400.0, height=180, workers=1
    )
    assert cls == "non_fl"


def test_classify_localize_reprobe_rescues_to_boundary(monkeypatch):
    # Pins the #524 re-probe rescue: the initial +1/2/3s probes both land
    # absent (e.g. inside a fade), but the region_width-offset re-probe finds
    # the scorebar on the pre side -> rescued from non_fl to match_boundary.
    # Call ordering inside _classify_blackout_localize: pre (1), post (2),
    # then pre_re (3), post_re (4) since both initial sides are not-True.
    from allaganeye.video import scorebar as sb

    calls = {"n": 0}
    # call 1 pre absent, call 2 post absent, call 3 pre_re present, call 4 post_re absent
    per_call_state = {
        1: PresenceState.ABSENT,
        2: PresenceState.ABSENT,
        3: PresenceState.PRESENT,
        4: PresenceState.ABSENT,
    }

    def fake_probe(
        video, ts, height, workers, *, with_localize=False, with_lowres=True
    ):
        calls["n"] += 1
        state = per_call_state[calls["n"]]
        return ([None] * len(ts), [b"f"] * len(ts), [state] * len(ts))

    monkeypatch.setattr(sb, "_probe_scorebar_context", fake_probe)
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 1.23)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 103.0), duration=400.0, height=180, workers=1
    )
    # Without the re-probe block this region would be non_fl (both initial
    # sides absent); the pre-side re-probe rescues it to match_boundary.
    assert calls["n"] == 4  # all four probe sets were consulted
    assert cls == "match_boundary"


def test_classify_localize_all_none_is_unknown(monkeypatch):
    # All probes (including the re-probe) return localize None -> the re-probe
    # majority is None and must NOT override, leaving the side None -> unknown.
    from allaganeye.video import scorebar as sb

    monkeypatch.setattr(
        sb,
        "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False, with_lowres=True: (
            [None] * len(ts),
            [b"f"] * len(ts),
            [None] * len(ts),
        ),
    )
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 1.23)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 103.0), duration=400.0, height=180, workers=1
    )
    assert cls == "unknown"


# ---------------------------------------------------------------------------
# classify_blackout localize selector unit tests (Phase 2 B3)
# ---------------------------------------------------------------------------


def test_classify_blackout_vtuber_delegates_to_localize(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion

    seen = {}

    def fake_localize(video, region, duration, height, workers=None, *, band_region):
        seen["band"] = band_region
        return "in_match"

    monkeypatch.setattr(sb, "_classify_blackout_localize", fake_localize)
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    out = sb.classify_blackout(
        Path("x.mp4"), (10.0, 11.0), 400.0, 180, localize=True, band_region=band
    )
    assert out == "in_match"
    assert seen["band"] is band


def test_classify_blackout_obs_does_not_call_localize(monkeypatch):
    from allaganeye.video import scorebar as sb

    monkeypatch.setattr(
        sb,
        "_classify_blackout_localize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("OBS must not localize")),
    )
    # vtuber defaults False -> must take the v2 path (probe returns absent here).
    monkeypatch.setattr(
        sb,
        "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False, with_lowres=True: (
            [False] * len(ts),
            [b"f"] * len(ts),
            [None] * len(ts),
        ),
    )
    out = sb.classify_blackout(Path("x.mp4"), (10.0, 12.0), 400.0, 180)
    assert out == "non_fl"


def test_filter_threads_vtuber_to_classify(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion

    seen = []

    def fake_classify(
        video, region, duration, height, workers=None, *, band_region, localize
    ):
        seen.append((localize, band_region.source))
        return "match_boundary"

    monkeypatch.setattr(sb, "classify_blackout", fake_classify)
    monkeypatch.setattr(sb, "_merge_boundary_pairs", lambda *a, **k: (a[1], a[2]))
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    sb.filter_blackouts_with_scorebar(
        Path("x.mp4"), [(10.0, 12.0)], 400.0, 180, band_region=band, localize=True
    )
    assert seen == [(True, "band")]


def test_merge_gap_probe_uses_localize_path(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion

    captured = {}

    def fake_probe(
        video, points, height, workers, *, with_localize=False, with_lowres=True
    ):
        captured["with_localize"] = with_localize
        # gap shows no scorebar by either signal -> eligible to merge.
        return (
            [None] * len(points),
            [b"f"] * len(points),
            [PresenceState.ABSENT] * len(points),
        )

    monkeypatch.setattr(sb, "_probe_scorebar_context", fake_probe)
    regions = [(10.0, 12.0), (30.0, 32.0)]
    cls = ["match_boundary", "match_boundary"]
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    merged, _merged_cls = sb._merge_boundary_pairs(
        Path("x.mp4"), regions, cls, 400.0, 180, None, band_region=band, localize=True
    )
    assert captured["with_localize"] is True
    assert merged == [(10.0, 32.0)]  # localize-absent gap -> merged


def test_classify_blackout_localize_selector_routes(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(sb, "_classify_blackout_localize", lambda *a, **k: "LOCALIZED")
    # localize=True routes to the position-independent classifier
    assert (
        sb.classify_blackout(Path("x.mp4"), (10.0, 12.0), 100.0, 180, localize=True)
        == "LOCALIZED"
    )
    # localize=False takes the v2 path (must NOT be the localize sentinel).
    monkeypatch.setattr(
        sb,
        "_probe_scorebar_context",
        lambda *a, **k: ([False, False, False], [None, None, None], [None, None, None]),
    )
    assert (
        sb.classify_blackout(Path("x.mp4"), (10.0, 12.0), 100.0, 180, localize=False)
        != "LOCALIZED"
    )


# --- T5/T6: _probe_scorebar_context with_lowres + logger ---


def test_probe_scorebar_context_with_lowres_false_skips_lowres(monkeypatch):
    """with_lowres=False in v2 mode: low-res probe not called, result from hi-res."""
    from unittest.mock import MagicMock
    from pathlib import Path
    from allaganeye.video import scorebar as sb

    lo = MagicMock(return_value=b"\x00" * 10)
    hi = MagicMock(return_value=b"\x00" * 10)
    monkeypatch.setattr(sb, "_probe_frame_rgb", lo)
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", hi)
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: True)  # opencv present
    monkeypatch.setattr(sb, "_SCOREBAR_METHOD", "v2")
    res, _frames, _ = sb._probe_scorebar_context(
        Path("x.mkv"), [1.0, 2.0], 180, 2, with_lowres=False
    )
    lo.assert_not_called()  # low-res skipped (normal path, opencv present)
    assert res == [True, True]  # decided by hi-res (bit-exact)


def test_probe_scorebar_context_lazy_lowres_when_v2_none(monkeypatch):
    """with_lowres=False + V2 returns None (no opencv): lazy low-res probe fires."""
    from unittest.mock import MagicMock
    from pathlib import Path
    from allaganeye.video import scorebar as sb

    lo = MagicMock(return_value=b"\x00" * 10)
    monkeypatch.setattr(sb, "_probe_frame_rgb", lo)
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", MagicMock(return_value=b""))
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: None)  # opencv absent
    monkeypatch.setattr(sb, "_has_scorebar", lambda raw, h: False)  # V1 fallback
    monkeypatch.setattr(sb, "_SCOREBAR_METHOD", "v2")
    res, _, _ = sb._probe_scorebar_context(
        Path("x.mkv"), [1.0], 180, 1, with_lowres=False
    )
    lo.assert_called()  # lazily probed for V1 fallback (no-opencv preserved)
    assert res == [False]


def test_probe_scorebar_context_logs_probe_failure(monkeypatch, caplog):
    """VideoProcessingError in probe -> debug-logged (not silently swallowed)."""
    import logging
    from pathlib import Path
    from allaganeye.exceptions import VideoProcessingError
    from allaganeye.video import scorebar as sb

    def boom(*a, **k):
        raise VideoProcessingError("ffmpeg not found")

    monkeypatch.setattr(sb, "_probe_frame_rgb", boom)
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", boom)
    with caplog.at_level(logging.DEBUG, logger="allaganeye.video.scorebar"):
        sb._probe_scorebar_context(Path("x.mkv"), [1.0], 180, 1)
    assert any("probe" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# #824 site 4/5: tri-state migration tests
# ---------------------------------------------------------------------------


def test_localize_present_from_raw_tristate():
    # #824 site 4: 表現形式のみ変更 (semantics は docstring 分離済みのまま)。
    assert sb._localize_present_from_raw(None) is PresenceState.UNKNOWN
    blank = np.full((1080, 1920, 3), 40, dtype=np.uint8).tobytes()
    assert sb._localize_present_from_raw(blank) is PresenceState.ABSENT


def test_majority_presence_excludes_unknown_from_denominator():
    P, A, U = PresenceState.PRESENT, PresenceState.ABSENT, PresenceState.UNKNOWN
    assert sb._majority_presence([P, U, U]) is True  # 有効票 1, present 1
    assert sb._majority_presence([P, A, U]) is True  # 有効票 2, present 1 >= ceil(2/2)
    assert sb._majority_presence([A, A, P]) is False
    assert sb._majority_presence([U, U, None]) is None  # 有効票ゼロ
    assert sb._majority_presence([]) is None  # 有効票ゼロ (空入力) も None


def test_probe_scorebar_context_localize_results_are_tristate(monkeypatch):
    # with_localize=True で probe 失敗 frame は UNKNOWN、成功 miss は ABSENT。
    # scorebar_results (bool|None) は従来のまま (OBS 不変 pin)。
    from pathlib import Path

    def fake_probe_rgb(v, t, h):
        return b"lo"

    def fake_probe_hires(v, t):
        # t=1.0 -> None (probe failure) -> UNKNOWN; t=2.0 -> blank frame -> ABSENT
        if t == 1.0:
            return None
        return np.full((1080, 1920, 3), 40, dtype=np.uint8).tobytes()

    monkeypatch.setattr(sb, "_probe_frame_rgb", fake_probe_rgb)
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", fake_probe_hires)
    # has_scorebar_v2 returns False for both so scorebar_results are unchanged
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: False)

    _scorebar, _raw, loc = sb._probe_scorebar_context(
        Path("x.mp4"), [1.0, 2.0], height=180, workers=1, with_localize=True
    )
    # scorebar_results must remain bool (OBS path unaffected)
    assert _scorebar == [False, False]
    # localize results: probe failure -> UNKNOWN, blank frame -> ABSENT
    assert loc[0] is PresenceState.UNKNOWN
    assert loc[1] is PresenceState.ABSENT
