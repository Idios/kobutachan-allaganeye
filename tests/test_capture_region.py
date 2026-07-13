import numpy as np

from allaganeye.video.capture_region import (
    FULL_FRAME,
    CaptureRegion,
    RegionTimeline,
    ScorebarLocalization,
    _emblem_and_margin,
    _maximal_ones_rectangle,
    _maybe_snap_full_frame,
    _scorebar_saturated_runs,
    band_region_from_localization,
    consensus_scorebar_localization,
    detect_mask_free_region,
    detect_region_blackout_overlap,
    detect_region_variance,
    detect_scorebar_band_region,
    iou,
    localize_scorebar,
    region_mean,
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


def test_localize_invalid_target_ratio_raises():
    # target_ratio<=1.0 は confidence 分母が 0/負 になるため ValueError (public kwarg 前提条件)。
    import pytest

    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    with pytest.raises(ValueError):
        localize_scorebar(f, target_ratio=1.0)


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


def test_localize_agrees_with_has_scorebar_v2_in_match():
    # 絶対 emblem 位置に重なる span を描くと _has_scorebar_v2 Primary が True。
    # localize_scorebar も relative 位置で検出 -> 両者が in-match で合致 (OBS parity)。
    from allaganeye.video.detector import _has_scorebar_v2

    f = _hires_with_scorebar_at(y_top=0, x_left=600, x_right=1318)
    assert localize_scorebar(f) is not None
    assert _has_scorebar_v2(f.tobytes()) is True


def test_localize_agrees_with_has_scorebar_v2_non_match():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
        _has_scorebar_v2,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    assert localize_scorebar(f) is None
    assert _has_scorebar_v2(f.tobytes()) is False


# ---------------------------------------------------------------------------
# Task A1: is_full_frame + region_mean
# ---------------------------------------------------------------------------


def test_is_full_frame_true_only_for_unit_rect():
    assert FULL_FRAME.is_full_frame() is True
    assert CaptureRegion(0.0, 0.0, 1.0, 1.0).is_full_frame() is True
    assert CaptureRegion(0.1, 0.0, 0.9, 1.0).is_full_frame() is False
    assert CaptureRegion(0.0, 0.0, 1.0, 0.5).is_full_frame() is False


def test_region_mean_full_frame_equals_frame_mean():
    frame = np.arange(12, dtype=np.uint8).reshape(3, 4)
    assert region_mean(frame, FULL_FRAME) == float(frame.mean())


def test_region_mean_crops_to_band():
    frame = np.zeros((10, 10), dtype=np.uint8)
    frame[0:2, :] = 200  # bright top band
    band = CaptureRegion(0.0, 0.0, 1.0, 0.2)
    assert region_mean(frame, band) == 200.0


def test_region_mean_empty_crop_clamps_to_1px():
    frame = np.full((10, 10), 50, dtype=np.uint8)
    degenerate = CaptureRegion(0.999, 0.999, 0.0001, 0.0001)
    assert region_mean(frame, degenerate) == 50.0


# ---------------------------------------------------------------------------
# Task A2: band_region_from_localization
# ---------------------------------------------------------------------------


def test_band_region_normalizes_probe_px_to_unit_rect():
    loc = ScorebarLocalization(
        x_left=240, x_right=1680, y_top=18, y_bottom=63, confidence=0.9
    )
    region = band_region_from_localization(loc, probe_w=1920, probe_h=1080)
    assert abs(region.x - 240 / 1920) < 1e-6
    assert abs(region.y - 18 / 1080) < 1e-6
    assert abs(region.w - (1680 - 240) / 1920) < 1e-6
    assert abs(region.h - (63 - 18) / 1080) < 1e-6
    assert region.confidence == 0.9
    assert region.source == "band"


def test_band_region_clamps_into_unit_square():
    loc = ScorebarLocalization(
        x_left=-5, x_right=1925, y_top=-2, y_bottom=70, confidence=0.5
    )
    region = band_region_from_localization(loc, probe_w=1920, probe_h=1080)
    assert region.x >= 0.0 and region.y >= 0.0
    assert region.x + region.w <= 1.0 + 1e-9
    assert region.y + region.h <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# Task A3: detect_scorebar_band_region (localize 多フレーム consensus)
# ---------------------------------------------------------------------------


def test_band_consensus_takes_median_of_localizations():
    locs = [
        ScorebarLocalization(238, 1678, 18, 63, 0.8),
        ScorebarLocalization(240, 1680, 18, 63, 0.9),
        ScorebarLocalization(242, 1682, 20, 65, 0.7),
        None,
    ]
    calls = iter(locs)
    region = detect_scorebar_band_region(
        duration=400.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda _t: next(calls),
        num_samples=4,
    )
    assert abs(region.x - 240 / 1920) < 1e-3
    assert region.source == "band"
    assert region.confidence > 0.0


def test_band_consensus_all_miss_falls_back_full_frame():
    region = detect_scorebar_band_region(
        duration=400.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda _t: None,
        num_samples=4,
    )
    assert region.is_full_frame()


def test_band_consensus_below_min_hits_falls_back_full_frame():
    locs = [ScorebarLocalization(240, 1680, 18, 63, 0.9), None, None, None]
    calls = iter(locs)
    region = detect_scorebar_band_region(
        duration=400.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda _t: next(calls),
        num_samples=4,
        min_hits=2,
    )
    assert region.is_full_frame()


def test_band_consensus_rejects_noise_and_picks_dominant_cluster():
    from allaganeye.video.capture_region import (
        ScorebarLocalization,
        detect_scorebar_band_region,
    )

    # 4 true (y~0, high conf) + 3 noise (y~540-582, varied conf incl one 0.69)
    locs = [
        ScorebarLocalization(600, 1315, 0, 45, 1.0),
        ScorebarLocalization(600, 1315, 0, 45, 1.0),
        ScorebarLocalization(604, 1311, 12, 57, 0.52),
        ScorebarLocalization(600, 1315, 0, 45, 1.0),
        ScorebarLocalization(1116, 1919, 540, 585, 0.21),
        ScorebarLocalization(508, 1288, 582, 627, 0.28),
        ScorebarLocalization(0, 778, 558, 603, 0.69),
    ]
    calls = iter(locs)
    region = detect_scorebar_band_region(
        duration=400.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda _t: next(calls),
        num_samples=7,
    )
    # must converge on the true cluster (y~0), NOT the noise-mixed median (y~0.24)
    assert region.y < 0.05, f"expected true cluster y~0, got {region.y}"
    assert abs(region.x - 600 / 1920) < 0.05


def test_band_consensus_balanced_split_median_falls_between_clusters():
    # 3 true (y~0-12, high conf) vs 3 noise (y~540-582, low conf): an exact
    # count tie where a plain median of y_top lands in the gap (~276px / y~0.26),
    # producing a between-clusters garbage band. Dominant-cluster selection breaks
    # the tie by mean confidence (true 0.84 > noise 0.39) and recovers y~0.
    locs = [
        ScorebarLocalization(600, 1315, 0, 45, 1.0),
        ScorebarLocalization(600, 1315, 0, 45, 1.0),
        ScorebarLocalization(604, 1311, 12, 57, 0.52),
        ScorebarLocalization(1116, 1919, 540, 585, 0.21),
        ScorebarLocalization(508, 1288, 582, 627, 0.28),
        ScorebarLocalization(0, 778, 558, 603, 0.69),
    ]
    calls = iter(locs)
    region = detect_scorebar_band_region(
        duration=400.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda _t: next(calls),
        num_samples=6,
    )
    assert region.y < 0.05, f"expected true cluster y~0, got {region.y}"
    assert abs(region.x - 600 / 1920) < 0.05


def test_band_region_localize_fn_unknown_sentinel_not_counted():
    # #824 site 6/10: UNKNOWN は hit でも miss でもなく consensus から除外。
    from allaganeye.video.probe_state import PresenceState

    def _loc(y_top: int) -> ScorebarLocalization:
        return ScorebarLocalization(
            x_left=240, x_right=1680, y_top=y_top, y_bottom=y_top + 45, confidence=0.9
        )

    calls = iter(
        [PresenceState.UNKNOWN] + [_loc(y_top=12)] * 3 + [PresenceState.UNKNOWN] * 4
    )
    region = detect_scorebar_band_region(
        duration=80.0,
        probe_w=1920,
        probe_h=1080,
        localize_fn=lambda t: next(calls),
        num_samples=8,
        min_hits=2,
    )
    assert not region.is_full_frame()  # 有効 3 hit で consensus 成立


# ---------------------------------------------------------------------------
# Task B1: consensus_scorebar_localization core
# ---------------------------------------------------------------------------


def test_consensus_scorebar_localization_dominant_cluster_median():
    def _loc(y_top: int) -> ScorebarLocalization:
        return ScorebarLocalization(
            x_left=240, x_right=1680, y_top=y_top, y_bottom=y_top + 45, confidence=0.9
        )

    locs = [_loc(y_top=12), _loc(y_top=18), _loc(y_top=12), _loc(y_top=540)]
    seq = iter(locs + [None] * 4)
    result = consensus_scorebar_localization(
        duration=80.0, localize_fn=lambda t: next(seq), num_samples=8, min_hits=2
    )
    assert result is not None and result.y_top == 12  # dominant cluster median


def test_consensus_scorebar_localization_scattered_returns_none():
    # FP only (clusters below min_hits) -> None.
    def _loc(y_top: int) -> ScorebarLocalization:
        return ScorebarLocalization(
            x_left=240, x_right=1680, y_top=y_top, y_bottom=y_top + 45, confidence=0.9
        )

    seq = iter([_loc(y_top=100), _loc(y_top=300), _loc(y_top=500)] + [None] * 5)
    # y tol=60: 100/300/500 are each in separate clusters with 1 hit -> min_hits=2 -> None
    assert (
        consensus_scorebar_localization(
            duration=80.0, localize_fn=lambda t: next(seq), num_samples=8, min_hits=2
        )
        is None
    )


# ---------------------------------------------------------------------------
# A-Task 1: detect_mask_free_region + _maximal_ones_rectangle
# ---------------------------------------------------------------------------


def _rect_overlaps(rect_px, block_px) -> bool:
    ax0, ay0, ax1, ay1 = rect_px
    bx0, by0, bx1, by1 = block_px
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _frames_with_mask(h, w, mask_block, values=(5, 200, 5, 200)):
    """Game pixels cycle bright/dark across frames; mask_block stays bright (200)."""
    bx0, by0, bx1, by1 = mask_block
    frames = []
    for v in values:
        f = np.full((h, w), v, dtype=np.uint8)
        f[by0:by1, bx0:bx1] = 200  # static bright mask -> min never < dark
        frames.append(f)
    return frames


def test_maximal_ones_rectangle_simple_block():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1:4, 1:4] = 1  # 3x3 block of ones at (x=1..3, y=1..3)
    assert _maximal_ones_rectangle(mask) == (1, 1, 4, 4)


def test_maximal_ones_rectangle_empty_is_none():
    assert _maximal_ones_rectangle(np.zeros((4, 4), dtype=np.uint8)) is None


def test_detect_mask_free_region_excludes_bright_mask():
    # 20x20, bright static mask at bottom-left (cols 0..10, rows 10..20).
    frames = _frames_with_mask(20, 20, (0, 10, 10, 20))
    region = detect_mask_free_region(frames)
    assert not region.is_full_frame()
    # Returned rectangle must not intersect the mask block.
    px = (
        round(region.x * 20),
        round(region.y * 20),
        round((region.x + region.w) * 20),
        round((region.y + region.h) * 20),
    )
    assert not _rect_overlaps(px, (0, 10, 10, 20))


def test_detect_mask_free_region_full_game_snaps_full_frame():
    # Every pixel cycles bright/dark -> game everywhere -> FULL_FRAME.
    frames = [np.full((20, 20), v, dtype=np.uint8) for v in (5, 200, 5, 200)]
    assert detect_mask_free_region(frames).is_full_frame()


def test_detect_mask_free_region_tiny_game_is_full_frame():
    # Only a 2x2 game patch (rest stays bright) -> below min_area_frac -> FULL_FRAME.
    frames = []
    for v in (5, 200):
        f = np.full((20, 20), 200, dtype=np.uint8)
        f[0:2, 0:2] = v
        frames.append(f)
    assert detect_mask_free_region(frames).is_full_frame()


def test_detect_mask_free_region_single_frame_is_full_frame():
    assert detect_mask_free_region([np.zeros((20, 20), dtype=np.uint8)]).is_full_frame()


class TestRegionTimelineSerialization:
    """#810: metadata.json capture_regions round-trip contract."""

    def test_to_dict_includes_fallback_reason_null(self):
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = RegionTimeline(coarse=FULL_FRAME).to_dict()
        assert d["fallback_reason"] is None
        assert d["segments"] == []
        assert d["coarse"]["source"] == "fallback"

    def test_to_dict_includes_fallback_reason_value(self):
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = RegionTimeline(
            coarse=FULL_FRAME, fallback_reason="consensus_miss"
        ).to_dict()
        assert d["fallback_reason"] == "consensus_miss"

    def test_round_trip_with_segments(self):
        from allaganeye.video.capture_region import CaptureRegion, RegionTimeline

        band = CaptureRegion(0.1, 0.0, 0.76, 0.042, confidence=0.9, source="band")
        seg = CaptureRegion(0.1, 0.05, 0.8, 0.7, confidence=0.8, source="tierB")
        timeline = RegionTimeline(
            coarse=band,
            segments=[((60.0, 1200.0), seg)],
            fallback_reason=None,
        )
        restored = RegionTimeline.from_dict(timeline.to_dict())
        assert restored == timeline

    def test_from_dict_accepts_legacy_shape_without_fallback_reason(self):
        # to_dict は常に emit するが、from_dict は防御的に欠落を None 扱いする
        from allaganeye.video.capture_region import FULL_FRAME, RegionTimeline

        d = {"coarse": FULL_FRAME.to_dict(), "segments": []}
        restored = RegionTimeline.from_dict(d)
        assert restored.fallback_reason is None
