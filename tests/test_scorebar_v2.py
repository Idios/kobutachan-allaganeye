"""Tests for V2 scorebar detection: GC-emblem 3-point AND (#307).

Covers:
- ``_has_scorebar_v2``: per-emblem AND classification (sat + edge thresholds)
- ``_probe_frame_rgb_hires``: 1080p ffmpeg probe error paths
- ``_probe_scorebar_context`` V2 integration:
  - V2 True path
  - V2 False path (no V1 fallback)
  - V2 None -> V1 fallback (opencv unavailable / probe failure)
- ``_MERGE_GAP_MAX = None``: very large gaps (e.g. >1hr) eligible for merge
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from allaganeye.video.detector import (
    _EMBLEM_EDGE_THRESHOLD,
    _EMBLEM_POSITIONS,
    _EMBLEM_SAT_THRESHOLD,
    _SCOREBAR_V2_PROBE_HEIGHT,
    _SCOREBAR_V2_PROBE_WIDTH,
    _has_scorebar_v2,
    _probe_frame_rgb_hires,
)
from allaganeye.video.scorebar import (
    _probe_scorebar_context,
    filter_blackouts_with_scorebar,
)

SCOREBAR_MODULE = "allaganeye.video.scorebar"
DETECTOR_MODULE = "allaganeye.video.detector"


def _empty_hires_frame() -> bytes:
    """Return a 1920x1080 all-zero RGB24 frame (sat=0, edge=0)."""
    return bytes(_SCOREBAR_V2_PROBE_WIDTH * _SCOREBAR_V2_PROBE_HEIGHT * 3)


def _make_hires_frame_with_emblems(
    emblem_color: tuple[int, int, int] = (200, 30, 30),
    use_emblems: tuple[bool, bool, bool] = (True, True, True),
    bg_color: tuple[int, int, int] = (40, 40, 40),
) -> bytes:
    """Build a 1920x1080 RGB frame with optional per-emblem high-feature regions.

    Each "emblem" is filled with vertical stripes alternating the chosen
    color and black.  This produces high HSV saturation (on the colored
    pixels) AND high Sobel edge density (vertical stripes give strong
    horizontal gradients without canceling out, unlike a checkerboard
    pattern which sums to zero with a 3x3 Sobel kernel).
    Bytes layout matches what ``_probe_frame_rgb_hires`` would produce:
    row-major RGB24.
    """
    width = _SCOREBAR_V2_PROBE_WIDTH
    height = _SCOREBAR_V2_PROBE_HEIGHT
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, 0] = bg_color[0]
    frame[:, :, 1] = bg_color[1]
    frame[:, :, 2] = bg_color[2]

    for (_, x1, y1, x2, y2), enable in zip(_EMBLEM_POSITIONS, use_emblems, strict=True):
        if not enable:
            continue
        region = frame[y1:y2, x1:x2, :]
        # 2-pixel-wide vertical stripes alternating bright color and black.
        # Single-pixel stripes would alias against the 3x3 Sobel kernel
        # (left/right neighbors carry the same value -> gradient cancels);
        # 2-pixel stripes guarantee strong horizontal gradients.
        for col in range(region.shape[1]):
            block = (col // 2) % 2
            if block == 0:
                region[:, col, 0] = emblem_color[0]
                region[:, col, 1] = emblem_color[1]
                region[:, col, 2] = emblem_color[2]
            else:
                region[:, col, :] = 0

    return frame.tobytes()


# ---------------------------------------------------------------------------
# _has_scorebar_v2
# ---------------------------------------------------------------------------


class TestHasScorebarV2:
    def test_none_input_returns_none(self):
        """Probe failure (None) -> None passthrough."""
        assert _has_scorebar_v2(None) is None

    def test_empty_frame_returns_false(self):
        """All-zero frame -> 0 sat, 0 edge -> False (first emblem fails)."""
        assert _has_scorebar_v2(_empty_hires_frame()) is False

    def test_all_three_emblems_present_returns_true(self):
        """All 3 emblems with high sat + high edge -> True."""
        frame = _make_hires_frame_with_emblems(use_emblems=(True, True, True))
        assert _has_scorebar_v2(frame) is True

    def test_only_left_emblem_returns_false(self):
        """Only left emblem -> AND fails on center -> False."""
        frame = _make_hires_frame_with_emblems(use_emblems=(True, False, False))
        assert _has_scorebar_v2(frame) is False

    def test_only_two_emblems_returns_false(self):
        """Two of three emblems -> AND fails -> False (3-point AND condition)."""
        frame = _make_hires_frame_with_emblems(use_emblems=(True, True, False))
        assert _has_scorebar_v2(frame) is False

    def test_missing_center_emblem_returns_false(self):
        """Center emblem missing -> False (AND requires all 3)."""
        frame = _make_hires_frame_with_emblems(use_emblems=(True, False, True))
        assert _has_scorebar_v2(frame) is False

    def test_low_saturation_returns_false(self):
        """Gray emblems (low saturation) -> False even with edges."""
        # Gray checkerboard has high edges but zero saturation.
        frame = _make_hires_frame_with_emblems(
            emblem_color=(128, 128, 128), use_emblems=(True, True, True)
        )
        assert _has_scorebar_v2(frame) is False

    def test_opencv_unavailable_returns_none(self):
        """ImportError on cv2 -> None (lets caller fall back to V1)."""
        # Force ImportError inside the function by removing cv2 from sys.modules
        # and inserting a guard that raises on import.
        import builtins
        import sys

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "cv2":
                raise ImportError("simulated missing cv2")
            return real_import(name, *args, **kwargs)

        saved = sys.modules.pop("cv2", None)
        try:
            with patch("builtins.__import__", side_effect=fake_import):
                result = _has_scorebar_v2(_empty_hires_frame())
            assert result is None
        finally:
            if saved is not None:
                sys.modules["cv2"] = saved

    def test_thresholds_are_documented_constants(self):
        """Sanity: thresholds exist and match documented validation."""
        # Saturation threshold derived from validation against lobby
        # backgrounds (median 66-79) -- should sit at 70.
        assert _EMBLEM_SAT_THRESHOLD == 70.0
        assert _EMBLEM_EDGE_THRESHOLD == 40.0


# ---------------------------------------------------------------------------
# _probe_frame_rgb_hires
# ---------------------------------------------------------------------------


class TestProbeFrameRgbHires:
    @patch(f"{DETECTOR_MODULE}.subprocess.run")
    @patch(f"{DETECTOR_MODULE}.find_ffmpeg", return_value="ffmpeg")
    def test_valid_frame_returns_bytes(self, _mock_ff, mock_run):
        """Complete 1080p frame -> bytes of expected size."""
        rgb_size = _SCOREBAR_V2_PROBE_WIDTH * _SCOREBAR_V2_PROBE_HEIGHT * 3
        result = MagicMock(returncode=0, stdout=b"\xab" * rgb_size)
        mock_run.return_value = result
        out = _probe_frame_rgb_hires(Path("v.mp4"), 10.0)
        assert out is not None
        assert len(out) == rgb_size

    @patch(f"{DETECTOR_MODULE}.subprocess.run")
    @patch(f"{DETECTOR_MODULE}.find_ffmpeg", return_value="ffmpeg")
    def test_timeout_returns_none(self, _mock_ff, mock_run):
        """TimeoutExpired -> None (graceful)."""
        from subprocess import TimeoutExpired

        mock_run.side_effect = TimeoutExpired(cmd="ffmpeg", timeout=30)
        assert _probe_frame_rgb_hires(Path("v.mp4"), 10.0) is None

    @patch(f"{DETECTOR_MODULE}.subprocess.run")
    @patch(f"{DETECTOR_MODULE}.find_ffmpeg", return_value="ffmpeg")
    def test_nonzero_returncode_returns_none(self, _mock_ff, mock_run):
        """ffmpeg error exit -> None."""
        result = MagicMock(returncode=1, stdout=b"")
        mock_run.return_value = result
        assert _probe_frame_rgb_hires(Path("v.mp4"), 10.0) is None

    @patch(f"{DETECTOR_MODULE}.subprocess.run")
    @patch(f"{DETECTOR_MODULE}.find_ffmpeg", return_value="ffmpeg")
    def test_incomplete_frame_returns_none(self, _mock_ff, mock_run):
        """stdout shorter than expected RGB size -> None."""
        result = MagicMock(returncode=0, stdout=b"\x00" * 100)
        mock_run.return_value = result
        assert _probe_frame_rgb_hires(Path("v.mp4"), 10.0) is None

    def test_ffmpeg_not_found_raises(self):
        """ffmpeg not found -> VideoProcessingError."""
        from allaganeye.exceptions import VideoProcessingError

        with patch(
            f"{DETECTOR_MODULE}.subprocess.run", side_effect=FileNotFoundError()
        ):
            with patch(f"{DETECTOR_MODULE}.find_ffmpeg", return_value="ffmpeg"):
                with pytest.raises(VideoProcessingError):
                    _probe_frame_rgb_hires(Path("v.mp4"), 10.0)


# ---------------------------------------------------------------------------
# _probe_scorebar_context V2 integration
# ---------------------------------------------------------------------------


class TestProbeScorebarContextV2:
    """V2/V1 routing in _probe_scorebar_context (#307).

    Behavioral contract from the V2 PR:
    - V2 True  -> True
    - V2 False -> False (V1 fallback intentionally disabled)
    - V2 None  -> V1 result (opencv missing or hi-res probe failed)
    """

    @patch(f"{SCOREBAR_MODULE}._SCOREBAR_METHOD", "v2")
    @patch(f"{SCOREBAR_MODULE}._has_scorebar_v2", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb_hires", return_value=b"hi")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=b"lo")
    def test_v2_true_returns_true(self, _lo, _hi, mock_v1, _mock_v2):
        """V2 True -> True; V1 not consulted."""
        results, frames = _probe_scorebar_context(Path("v.mp4"), [1.0], 180, workers=1)
        assert results == [True]
        # frames returned are LOW-RES (used for static-screen detection)
        assert frames == [b"lo"]
        mock_v1.assert_not_called()

    @patch(f"{SCOREBAR_MODULE}._SCOREBAR_METHOD", "v2")
    @patch(f"{SCOREBAR_MODULE}._has_scorebar_v2", return_value=False)
    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb_hires", return_value=b"hi")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=b"lo")
    def test_v2_false_returns_false_no_v1_fallback(self, _lo, _hi, mock_v1, _mock_v2):
        """V2 False -> False; V1 NOT consulted (intentional, prevents lobby FP).

        This is the key contract: even if V1 would return True on the same
        frame, V2 False wins, because V1 has known FP on lobby backgrounds
        that block correct merging of match_boundary pairs (PR #313 rationale).
        """
        results, _ = _probe_scorebar_context(Path("v.mp4"), [1.0], 180, workers=1)
        assert results == [False]
        mock_v1.assert_not_called()

    @patch(f"{SCOREBAR_MODULE}._SCOREBAR_METHOD", "v2")
    @patch(f"{SCOREBAR_MODULE}._has_scorebar_v2", return_value=None)
    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb_hires", return_value=None)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=b"lo")
    def test_v2_none_falls_back_to_v1(self, _lo, _hi, mock_v1, _mock_v2):
        """V2 None (e.g. opencv missing or hi-res probe failed) -> V1 result."""
        results, _ = _probe_scorebar_context(Path("v.mp4"), [1.0], 180, workers=1)
        assert results == [True]
        mock_v1.assert_called_once()

    @patch(f"{SCOREBAR_MODULE}._SCOREBAR_METHOD", "v1")
    @patch(f"{SCOREBAR_MODULE}._has_scorebar_v2")
    @patch(f"{SCOREBAR_MODULE}._has_scorebar", return_value=True)
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb_hires")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb", return_value=b"lo")
    def test_v1_method_skips_hires_probe(self, _lo, mock_hi, _mock_v1_fn, mock_v2):
        """When METHOD=v1, no high-res probe and no V2 call."""
        results, _ = _probe_scorebar_context(Path("v.mp4"), [1.0], 180, workers=1)
        assert results == [True]
        mock_hi.assert_not_called()
        mock_v2.assert_not_called()


# ---------------------------------------------------------------------------
# _MERGE_GAP_MAX = None: no upper bound
# ---------------------------------------------------------------------------


class TestMergeGapNoLimit:
    """PR #313 removed the 600s upper bound on _MERGE_GAP_MAX.

    Verify gaps far larger than the old limit are now mergeable when
    9-point probes show no scorebar.
    """

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_gap_one_hour(self, mock_classify, mock_probe_rgb, mock_has_sb):
        """1 hour gap with no scorebar -> merge succeeds."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False  # no scorebar across all 9 probes

        # 3600s (1hr) gap -- well beyond the old 600s limit
        regions = [(100.0, 105.0), (3705.0, 3710.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 7200.0, 180
        )
        assert result == [(100.0, 3710.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_merge_gap_two_hours(self, mock_classify, mock_probe_rgb, mock_has_sb):
        """2 hour gap with no scorebar -> merge still allowed (no upper bound)."""
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        mock_has_sb.return_value = False

        regions = [(100.0, 105.0), (7305.0, 7310.0)]  # 7200s gap
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 14400.0, 180
        )
        assert result == [(100.0, 7310.0)]
        assert cls == ["match_boundary"]

    @patch(f"{SCOREBAR_MODULE}._has_scorebar")
    @patch(f"{SCOREBAR_MODULE}._probe_frame_rgb")
    @patch(f"{SCOREBAR_MODULE}.classify_blackout")
    def test_huge_gap_with_scorebar_not_merged(
        self, mock_classify, mock_probe_rgb, mock_has_sb
    ):
        """Huge gap but scorebar detected mid-gap -> NOT merged.

        Guards against the regression risk of removing the upper bound:
        even at multi-hour gaps, the 9-point probe must still block merges
        when an FL match is happening between the two boundaries.
        """
        mock_classify.side_effect = ["match_boundary", "match_boundary"]
        mock_probe_rgb.return_value = b"\x00" * 100
        # One mid-gap probe sees scorebar -> merge must be blocked
        results = [False] * 9
        results[4] = True
        mock_has_sb.side_effect = results

        regions = [(100.0, 105.0), (3705.0, 3710.0)]
        result, cls = filter_blackouts_with_scorebar(
            Path("v.mp4"), regions, 7200.0, 180
        )
        assert result == regions
        assert cls == ["match_boundary", "match_boundary"]
