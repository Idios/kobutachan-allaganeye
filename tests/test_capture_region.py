from allaganeye.video.capture_region import (
    CaptureRegion,
    FULL_FRAME,
    RegionTimeline,
    _maybe_snap_full_frame,
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
