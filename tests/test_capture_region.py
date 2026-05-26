from allaganeye.video.capture_region import CaptureRegion, RegionTimeline, FULL_FRAME


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
