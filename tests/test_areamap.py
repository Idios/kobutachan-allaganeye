"""Tests for allaganeye/video/areamap.py (Task D1, Refs #481)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _det_seq(results):
    """Return a DetectFn that yields from *results* one call at a time."""
    it = iter(results)
    return lambda frames: next(it)


# ---------------------------------------------------------------------------
# Step 1 (TDD): consensus unit tests -- cv2 NOT needed (DI probe/detect)
# ---------------------------------------------------------------------------


def test_consensus_majority_and_confidence():
    from allaganeye.video.areamap import resolve_match_regions

    fake_probe = lambda v, t: b"\x00" * (1920 * 1080 * 3)  # noqa: E731
    box = (0.01, 0.02, 0.28, 0.35, 0.9)
    off = (0.50, 0.50, 0.20, 0.20, 0.5)  # IoU=0 の外れ window
    results, warns = resolve_match_regions(
        Path("v.mkv"),
        [(1, 100.0, 1100.0)],
        probe=fake_probe,
        detect=_det_seq([box, box, off]),
    )
    assert len(results) == 1
    r = results[0]
    assert r.match_index == 1 and r.region.source == "auto"
    assert r.scattered is True and abs(r.region.confidence - 2 / 3) < 1e-6
    assert warns  # 移動疑い warning


def test_all_windows_miss_drops_match():
    from allaganeye.video.areamap import resolve_match_regions

    results, warns = resolve_match_regions(
        Path("v.mkv"),
        [(1, 100.0, 1100.0)],
        probe=lambda v, t: b"\x00" * (1920 * 1080 * 3),
        detect=lambda frames: None,
    )
    assert results == [] and any("1" in w for w in warns)


def test_short_match_uses_midpoint_samples():
    from allaganeye.video.areamap import resolve_match_regions

    # end-start < 2*edge_margin でも sample が生成される (中央寄せ)
    seen: list[float] = []

    def probe(v, t):
        seen.append(t)
        return b"\x00" * (1920 * 1080 * 3)

    resolve_match_regions(
        Path("v.mkv"),
        [(1, 0.0, 90.0)],
        probe=probe,
        detect=lambda f: (0.0, 0.0, 0.3, 0.3, 0.9),
    )
    assert all(0.0 <= t <= 90.0 for t in seen) and seen


def test_consensus_no_majority_cluster():
    """windows=3 で valid=2（1 window は None）、残り 2 window が IoU<0.8 の 1-1 split。

    多数派閾値 ceil(3/2)=2 に届かず、その match は results に含まれず warning が出る。
    """
    from allaganeye.video.areamap import resolve_match_regions

    fake_probe = lambda v, t: b"\x00" * (1920 * 1080 * 3)  # noqa: E731
    box1 = (0.01, 0.02, 0.28, 0.35, 0.9)
    box2 = (0.50, 0.50, 0.20, 0.20, 0.5)  # IoU(box1, box2) = 0 (非重複)
    results, warns = resolve_match_regions(
        Path("v.mkv"),
        [(1, 100.0, 1100.0)],
        windows=3,
        probe=fake_probe,
        detect=_det_seq([box1, None, box2]),  # [valid, invalid, valid]
    )
    # valid_count = 2, best_cluster の max は 1 (box1 単独 or box2 単独)
    # majority_thresh = ceil(3/2) = 2 > 1 -> no majority -> match は skip
    assert len(results) == 0
    assert any("no majority cluster" in w for w in warns)


# ---------------------------------------------------------------------------
# Step 5: detect_areamap_seed unit tests (cv2 required)
# ---------------------------------------------------------------------------


cv2 = pytest.importorskip(
    "cv2", reason="cv2 not installed -- skipping detect_areamap_seed unit tests"
)


def _make_frames_with_overlay(
    n: int = 5,
    box_xywh: tuple[float, float, float, float] = (0.05, 0.06, 0.25, 0.25),
    seed: int = 42,
) -> list[np.ndarray]:
    """Synthesize *n* 1920x1080 RGB frames: dynamic background + static bright rect.

    Background uses alternating dark/bright stripes per-frame to guarantee
    temporal std >> A_STD_THRESH (12.0) so the static mask captures only the
    overlay region.  The overlay itself has a checkerboard for edge density.
    """
    frames = []
    bx, by, bw, bh = box_xywh
    px = int(bx * 1920)
    py = int(by * 1080)
    pw = int(bw * 1920)
    ph = int(bh * 1080)
    # Background colors that alternate strongly across frames to ensure high temporal std
    bg_colors = [
        (20, 30, 40),
        (200, 190, 180),
        (25, 35, 45),
        (195, 185, 175),
        (15, 25, 35),
    ]
    for fi in range(n):
        r, g, b = bg_colors[fi % len(bg_colors)]
        bg = np.empty((1080, 1920, 3), dtype=np.uint8)
        bg[:, :, 0] = r
        bg[:, :, 1] = g
        bg[:, :, 2] = b
        # static bright structured overlay (simulate minimap window with texture)
        overlay = np.full((ph, pw, 3), 200, dtype=np.uint8)
        # add internal texture (checkerboard) for edge density
        for iy in range(0, ph, 8):
            for ix in range(0, pw, 8):
                if (iy // 8 + ix // 8) % 2 == 0:
                    overlay[iy : iy + 8, ix : ix + 8] = 240
                else:
                    overlay[iy : iy + 8, ix : ix + 8] = 160
        bg[py : py + ph, px : px + pw] = overlay
        frames.append(bg)
    return frames


from allaganeye.video.areamap import _iou_xywh  # noqa: E402


def test_detect_areamap_seed_synthetic_iou():
    """Static bright rect overlay on random bg: detected bbox should have IoU >= 0.8."""
    from allaganeye.video.areamap import detect_areamap_seed

    box_xywh = (0.05, 0.06, 0.25, 0.25)
    frames = _make_frames_with_overlay(n=5, box_xywh=box_xywh)
    result = detect_areamap_seed(frames)
    assert result is not None, "detect_areamap_seed returned None on synthetic frames"
    rx, ry, rw, rh, score = result
    iou = _iou_xywh((rx, ry, rw, rh), box_xywh)
    assert iou >= 0.8, f"IoU={iou:.3f} < 0.8"
    assert score > 0.0


def test_detect_areamap_seed_whole_frame_guard():
    """When the static region covers the whole frame, detect_areamap_seed returns None."""
    from allaganeye.video.areamap import detect_areamap_seed

    # All frames identical (fully static) -> static mask = whole frame blob -> guard fires
    frame = np.full((1080, 1920, 3), 128, dtype=np.uint8)
    # add edge texture to satisfy edge density check (but whole-frame guard fires first)
    for i in range(0, 1920, 8):
        frame[:, i] = 200
    frames = [frame.copy() for _ in range(5)]
    result = detect_areamap_seed(frames)
    # whole-frame blob: the guard A_MAX_DIM_FRAC=0.95 should cause None
    assert result is None, f"whole-frame guard failed: got {result}"


def test_detect_areamap_seed_too_few_frames():
    """Fewer than 3 frames -> None."""
    from allaganeye.video.areamap import detect_areamap_seed

    frames = _make_frames_with_overlay(n=2)
    result = detect_areamap_seed(frames)
    assert result is None
