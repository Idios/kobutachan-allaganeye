import numpy as np

from allaganeye.video.capture_region import (
    FULL_FRAME,
    CaptureRegion,
    RegionTimeline,
    ScorebarLocalization,
    _emblem_and_margin,
    _maybe_snap_full_frame,
    _scorebar_saturated_runs,
    detect_region_blackout_overlap,
    detect_region_variance,
    iou,
    localize_scorebar,
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
# Shared hi-res scorebar frame builder (used by P1 localize tests)
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


def test_all_grayscale_detectors_snap_full_on_obs_like_input():
    rng = np.random.default_rng(2)
    motion = [rng.integers(0, 256, (180, 320), dtype=np.uint8) for _ in range(8)]
    assert detect_region_variance(motion) == FULL_FRAME
    bright = np.full((180, 320), 120, dtype=np.uint8)
    dark = np.full((180, 320), 2, dtype=np.uint8)
    assert detect_region_blackout_overlap([bright, bright, dark]) == FULL_FRAME


# ---------------------------------------------------------------------------
# P1: localize_scorebar (re-plan #753)
# ---------------------------------------------------------------------------


def test_scorebar_localization_is_frozen_with_fields():
    loc = ScorebarLocalization(
        x_left=100, x_right=700, y_top=300, y_bottom=345, confidence=0.9
    )
    assert (loc.x_left, loc.x_right, loc.y_top, loc.y_bottom) == (100, 700, 300, 345)
    assert loc.confidence == 0.9
    import dataclasses

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        loc.x_left = 0  # type: ignore[misc]


def _sat_band(width_runs, h=45, w=1920):
    """指定 (x_left, x_right) 範囲を saturated blue で塗った band (h,w,3) を返す。"""
    band = np.full((h, w, 3), 40, dtype=np.uint8)
    for x_left, x_right in width_runs:
        band[:, x_left : x_right + 1] = (50, 50, 200)
    return band


def test_saturated_runs_finds_centered_run():
    import cv2

    band = _sat_band([(500, 1400)])
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    x_left, x_right = runs[0]
    assert abs(x_left - 500) <= 2 and abs(x_right - 1400) <= 2


def test_saturated_runs_finds_off_center_run():
    # 中心 (x=960) をまたがない左寄り帯。_find_scorebar_horizontal_range は
    # center-straddling で None を返すが、P1 はこれを拾えねばならない (#803 撤廃)。
    import cv2

    band = _sat_band([(100, 700)])
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    x_left, x_right = runs[0]
    assert abs(x_left - 100) <= 2 and abs(x_right - 700) <= 2


def test_saturated_runs_drops_narrow_and_overwide():
    import cv2

    # narrow (<500px) と overwide (>1440px) はどちらも width gate で除外。
    band = _sat_band([(0, 300), (700, 1300)])  # 301px run, 601px run
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    assert abs(runs[0][0] - 700) <= 2 and abs(runs[0][1] - 1300) <= 2

    overwide = _sat_band([(100, 1800)])  # 1701px
    assert _scorebar_saturated_runs(overwide, cv2) == []


def test_saturated_runs_blank_returns_empty():
    import cv2

    band = np.full((45, 1920, 3), 40, dtype=np.uint8)
    assert _scorebar_saturated_runs(band, cv2) == []


def _frame_with_emblem_box(fill, x1=600, y1=2, x2=665, y2=40):
    """1920x1080 frame の 1 box を指定 fill で塗る。stripe=高 sat/edge を作る用。"""
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    region = f[y1:y2, x1:x2]
    if fill == "stripe":
        for col in range(region.shape[1]):
            region[:, col] = (200, 30, 30) if (col // 2) % 2 == 0 else (0, 0, 0)
    else:
        region[:] = fill
    return f, [("e", x1, y1, x2, y2)]


def test_emblem_and_margin_strong_emblem_returns_ratio_above_one():
    import cv2

    f, positions = _frame_with_emblem_box("stripe")
    margin = _emblem_and_margin(f, positions, cv2)
    assert margin is not None and margin > 1.0


def test_emblem_and_margin_flat_region_returns_none():
    import cv2

    # 単色 (低 edge) は edge 閾値を割るので None。
    f, positions = _frame_with_emblem_box((50, 50, 200))
    assert _emblem_and_margin(f, positions, cv2) is None


def test_localize_centered_in_match_returns_localization():
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    loc = localize_scorebar(f)
    assert loc is not None
    assert abs(loc.x_left - 500) <= 4 and abs(loc.x_right - 1400) <= 4
    assert abs(loc.y_top - 120) <= 6  # stride 既定 6
    assert loc.y_bottom == loc.y_top + 45
    assert 0.0 < loc.confidence <= 1.0


def test_localize_off_center_inset_position_independent():
    # 中心 (x=960) をまたがない左寄り inset。退役した S2 (_find_scorebar_horizontal_range
    # center-straddling) では検出不能だった位置独立ケース (P1 の存在意義)。
    f = _hires_with_scorebar_at(y_top=300, x_left=100, x_right=700)
    loc = localize_scorebar(f)
    assert loc is not None
    assert abs(loc.x_left - 100) <= 4 and abs(loc.x_right - 700) <= 4
    assert abs(loc.y_top - 300) <= 6


def test_localize_blank_frame_returns_none():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    f = np.full(
        (_SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3), 40, dtype=np.uint8
    )
    assert localize_scorebar(f) is None


def test_localize_scale_variation_recovers_span():
    # HUD スケール差を span 幅で模擬。narrow と wide の両方で復元できること。
    for x_left, x_right in [(700, 1220), (300, 1620)]:
        f = _hires_with_scorebar_at(y_top=60, x_left=x_left, x_right=x_right)
        loc = localize_scorebar(f)
        assert loc is not None, (x_left, x_right)
        assert abs(loc.x_left - x_left) <= 4 and abs(loc.x_right - x_right) <= 4


def test_localize_off_center_band_without_emblems_returns_none():
    # 中心をまたがない右寄りの単色帯 (emblem なし)。all-run 化しても emblem-AND
    # が落とすので None。#803 (post-match 広帯) 防御が center 前提なしで成立する確証。
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:45, 1400:1919] = (50, 50, 200)  # 519px 右寄り帯、紋章なし
    assert localize_scorebar(f) is None


def test_localize_overwide_band_returns_none():
    f = _hires_with_scorebar_at(y_top=2, x_left=120, x_right=1810)
    assert localize_scorebar(f) is None


def test_localize_uniform_cyan_banner_returns_none():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:55, :] = (60, 200, 200)  # 全幅単色 cyan (>max width かつ紋章なし)
    assert localize_scorebar(f) is None


def test_localize_wrong_shape_returns_none():
    f = np.full((100, 100, 3), 40, dtype=np.uint8)
    assert localize_scorebar(f) is None


def test_localize_returns_none_without_cv2(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("simulated missing cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    assert localize_scorebar(f) is None
