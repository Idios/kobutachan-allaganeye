import numpy as np

from allaganeye.video.capture_region import (
    FULL_FRAME,
    CaptureRegion,
    RegionTimeline,
    _maybe_snap_full_frame,
    detect_region_blackout_overlap,
    detect_region_scorebar_band,
    detect_region_variance,
    iou,
    top_edge_error_px,
)


def test_full_frame_is_unit_square():
    assert (FULL_FRAME.x, FULL_FRAME.y, FULL_FRAME.w, FULL_FRAME.h) == (
        0.0,
        0.0,
        1.0,
        1.0,
    )


def test_clamp_bounds_region_into_unit_square():
    r = CaptureRegion(-0.1, 0.2, 1.5, 0.5).clamp()
    assert r.x == 0.0 and r.y == 0.2
    assert r.x + r.w <= 1.0 + 1e-9 and r.y + r.h <= 1.0 + 1e-9


def test_round_trip_dict():
    r = CaptureRegion(0.1, 0.2, 0.3, 0.4, confidence=0.8, source="tierB")
    assert CaptureRegion.from_dict(r.to_dict()) == r


def test_region_timeline_to_dict_shape():
    tl = RegionTimeline(coarse=FULL_FRAME, segments=[((10.0, 20.0), FULL_FRAME)])
    d = tl.to_dict()
    assert d["coarse"]["w"] == 1.0
    assert d["segments"][0]["time_range"] == [10.0, 20.0]


def test_iou_identical_is_one():
    r = CaptureRegion(0.1, 0.1, 0.5, 0.5)
    assert iou(r, r) == 1.0


def test_iou_disjoint_is_zero():
    a = CaptureRegion(0.0, 0.0, 0.2, 0.2)
    b = CaptureRegion(0.5, 0.5, 0.2, 0.2)
    assert iou(a, b) == 0.0


def test_top_edge_error_px_scales_by_height():
    a = CaptureRegion(0.0, 0.10, 1.0, 0.5)
    b = CaptureRegion(0.0, 0.12, 1.0, 0.5)
    assert round(top_edge_error_px(a, b, 1080)) == round(0.02 * 1080)


def test_snap_full_frame_when_region_covers_most_of_frame():
    near_full = CaptureRegion(0.01, 0.01, 0.97, 0.97, source="tierA")
    assert _maybe_snap_full_frame(near_full) == FULL_FRAME


def test_snap_keeps_small_inset_unchanged():
    inset = CaptureRegion(0.2, 0.1, 0.5, 0.5, source="tierA")
    assert _maybe_snap_full_frame(inset) is inset


# ---------------------------------------------------------------------------
# Task B.1: S1 detect_region_variance
# ---------------------------------------------------------------------------


def _stack_static_bg_with_moving_inset(
    n=12, h=180, w=320, inset=(0.30, 0.20, 0.40, 0.50)
):
    """静止 bg (一定値) + inset 内だけフレームごとに乱数 = 高分散."""
    rng = np.random.default_rng(0)
    x0, y0, ww, hh = (
        int(inset[0] * w),
        int(inset[1] * h),
        int(inset[2] * w),
        int(inset[3] * h),
    )
    frames = []
    for _ in range(n):
        f = np.full((h, w), 50, dtype=np.uint8)
        f[y0 : y0 + hh, x0 : x0 + ww] = rng.integers(0, 256, (hh, ww), dtype=np.uint8)
        frames.append(f)
    return frames, inset


def test_variance_finds_moving_inset():
    frames, inset = _stack_static_bg_with_moving_inset()
    r = detect_region_variance(frames)
    assert r.source == "tierA"
    assert inset[0] <= r.x + r.w / 2 <= inset[0] + inset[2]
    assert inset[1] <= r.y + r.h / 2 <= inset[1] + inset[3]
    expected = CaptureRegion(inset[0], inset[1], inset[2], inset[3])
    assert iou(r, expected) >= 0.8


def test_variance_full_frame_motion_snaps_full():
    rng = np.random.default_rng(1)
    frames = [rng.integers(0, 256, (180, 320), dtype=np.uint8) for _ in range(12)]
    assert detect_region_variance(frames) == FULL_FRAME


def test_variance_static_frames_fall_back_full():
    frames = [np.full((180, 320), 50, dtype=np.uint8) for _ in range(12)]
    assert detect_region_variance(frames) == FULL_FRAME


# ---------------------------------------------------------------------------
# Task B.3: S3 detect_region_blackout_overlap
# ---------------------------------------------------------------------------


def test_blackout_overlap_finds_region_that_goes_dark():
    h, w = 180, 320
    inset = (0.30, 0.20, 0.40, 0.50)
    x0, y0 = int(inset[0] * w), int(inset[1] * h)
    ww, hh = int(inset[2] * w), int(inset[3] * h)
    bright = np.full((h, w), 120, dtype=np.uint8)
    dark_inset = bright.copy()
    dark_inset[y0 : y0 + hh, x0 : x0 + ww] = 2
    frames = [bright, bright, dark_inset, dark_inset]
    r = detect_region_blackout_overlap(frames)
    assert r.source == "tierA"
    assert inset[0] <= r.x + r.w / 2 <= inset[0] + inset[2]
    assert inset[1] <= r.y + r.h / 2 <= inset[1] + inset[3]
    expected = CaptureRegion(inset[0], inset[1], inset[2], inset[3])
    assert iou(r, expected) >= 0.8


def test_blackout_overlap_obs_full_frame_blackout_snaps_full():
    h, w = 180, 320
    bright = np.full((h, w), 120, dtype=np.uint8)
    dark = np.full((h, w), 2, dtype=np.uint8)
    assert detect_region_blackout_overlap([bright, bright, dark]) == FULL_FRAME


def test_variance_tiny_speck_below_min_area_falls_back_full():
    rng = np.random.default_rng(7)
    frames = []
    for _ in range(8):
        f = np.full((180, 320), 50, dtype=np.uint8)
        f[0:8, 0:8] = rng.integers(0, 256, (8, 8), dtype=np.uint8)  # ~0.1% area
        frames.append(f)
    assert detect_region_variance(frames) == FULL_FRAME


# ---------------------------------------------------------------------------
# Task B.2: S2 detect_region_scorebar_band
# ---------------------------------------------------------------------------


def _hires_with_scorebar_at(y_top: int, x_left: int, x_right: int):
    """1920x1080 RGB: y_top 行に saturated 帯 + 3 紋章 (striped) を描く。

    紋章位置は detector._EMBLEM_RELATIVE_POSITIONS を帯 span に投影。
    """
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_WIDTH,
        _SCOREBAR_V2_PROBE_HEIGHT,
        _EMBLEM_RELATIVE_POSITIONS,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    bar_w = x_right - x_left
    f[y_top : y_top + 45, x_left : x_right + 1] = (50, 50, 200)
    for _name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS:
        cx = int(x_left + cx_rel * bar_w)
        hw = max(2, int(hw_rel * bar_w))
        region = f[y_top + ey1 : y_top + ey2, cx - hw : cx + hw]
        for col in range(region.shape[1]):
            region[:, col] = (200, 30, 30) if (col // 2) % 2 == 0 else (0, 0, 0)
    return f


def test_scorebar_band_at_offset_y_returns_inset_top():
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    r = detect_region_scorebar_band(f)
    assert r is not None and r.source == "tierB"
    assert abs(r.y - 120 / 1080) < 0.012


def test_scorebar_band_overwide_returns_none():
    # scorebar 幅 1690px > detector._SCOREBAR_SCAN_MAX_WIDTH_PX (1440, #806) のため
    # _find_scorebar_horizontal_range が None を返し S2 も None。OBS の全体縮退は
    # coarse 検出器 (S1/S3) の責務であり S2 (Tier-B precise) は OBS を snap しない。
    f = _hires_with_scorebar_at(y_top=2, x_left=120, x_right=1810)
    assert detect_region_scorebar_band(f) is None


def test_scorebar_band_uniform_cyan_banner_rejected():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_WIDTH,
        _SCOREBAR_V2_PROBE_HEIGHT,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:55, :] = (60, 200, 200)  # 単色 cyan 帯 (紋章なし)
    assert detect_region_scorebar_band(f) is None


def test_all_grayscale_detectors_snap_full_on_obs_like_input():
    rng = np.random.default_rng(2)
    motion = [rng.integers(0, 256, (180, 320), dtype=np.uint8) for _ in range(8)]
    assert detect_region_variance(motion) == FULL_FRAME
    bright = np.full((180, 320), 120, dtype=np.uint8)
    dark = np.full((180, 320), 2, dtype=np.uint8)
    assert detect_region_blackout_overlap([bright, bright, dark]) == FULL_FRAME
