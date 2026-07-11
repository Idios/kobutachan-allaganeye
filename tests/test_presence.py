"""Unit tests for presence-based match detection (no video required)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.capture_region import (
    ScorebarLocalization,
    localize_from_rgb_bytes,
)
from allaganeye.video.presence import (
    PresenceMatch,
    PresenceSample,
    PresenceState,
    detect_matches_by_presence,
    localize_present_at,
    refine_boundary,
    scan_presence,
    segment_presence,
)


def test_presence_sample_fields():
    s = PresenceSample(time=12.0, state=PresenceState.PRESENT, confidence=0.9)
    assert s.time == 12.0
    assert s.state is PresenceState.PRESENT
    assert s.confidence == 0.9


def test_presence_match_fields():
    m = PresenceMatch(start=10.0, end=900.0)
    assert m.start == 10.0
    assert m.end == 900.0


def _samples(spec: Sequence[tuple[float, bool]]) -> list[PresenceSample]:
    return [
        PresenceSample(
            time=t,
            state=PresenceState.PRESENT if p else PresenceState.ABSENT,
            confidence=1.0,
        )
        for t, p in spec
    ]


def test_segment_single_match():
    # present 0..900 (stride 100) -> one match
    samples = _samples([(t, True) for t in range(0, 1000, 100)])
    matches = segment_presence(samples, t_gap=30.0, t_min_match=60.0)
    assert matches == [PresenceMatch(start=0.0, end=900.0)]


def test_segment_two_matches_split_by_long_gap():
    # match A 0..200, absent 300..600 (gap 400 >= t_gap), match B 700..900
    spec = [(t, True) for t in (0, 100, 200)]
    spec += [(t, False) for t in (300, 400, 500, 600)]
    spec += [(t, True) for t in (700, 800, 900)]
    matches = segment_presence(_samples(spec), t_gap=120.0, t_min_match=60.0)
    assert matches == [
        PresenceMatch(start=0.0, end=200.0),
        PresenceMatch(start=700.0, end=900.0),
    ]


def test_segment_absorbs_short_absent_gap():
    # short absent at 300 only (gap from 200 to 400 = 200 < t_gap=300) -> merged
    spec = [(t, True) for t in (0, 100, 200)]
    spec += [(300, False)]
    spec += [(t, True) for t in (400, 500, 600)]
    matches = segment_presence(_samples(spec), t_gap=300.0, t_min_match=60.0)
    assert matches == [PresenceMatch(start=0.0, end=600.0)]


def test_segment_drops_short_present_spike():
    # isolated present spike 400..450 (duration 50 < t_min_match=60) -> dropped
    spec = [(t, False) for t in (0, 100, 200, 300)]
    spec += [(400, True), (450, True)]
    spec += [(t, False) for t in (600, 700, 800)]
    matches = segment_presence(_samples(spec), t_gap=120.0, t_min_match=60.0)
    assert matches == []


def test_segment_empty_input():
    assert segment_presence([], t_gap=30.0, t_min_match=60.0) == []


def test_refine_boundary_finds_transition_forward():
    # scorebar present for t < 500, absent for t >= 500 (match end)
    def present_at(t: float) -> bool:
        return t < 500.0

    # bracket: t_true=480 (present), t_false=520 (absent)
    edge = refine_boundary(480.0, 520.0, present_at, tol=1.0)
    assert abs(edge - 500.0) <= 1.0


def test_refine_boundary_finds_transition_backward():
    # scorebar absent for t < 300, present for t >= 300 (match start)
    def present_at(t: float) -> bool:
        return t >= 300.0

    # bracket: t_true=320 (present), t_false=280 (absent)
    edge = refine_boundary(320.0, 280.0, present_at, tol=1.0)
    assert abs(edge - 300.0) <= 1.0


def test_refine_boundary_respects_tolerance():
    def present_at(t: float) -> bool:
        return t < 500.0

    edge = refine_boundary(480.0, 520.0, present_at, tol=0.1)
    assert abs(edge - 500.0) <= 0.1


def test_localize_present_at_present(monkeypatch):
    import allaganeye.video.presence as presence

    fake_frame_bytes = (np.zeros((1080, 1920, 3), dtype=np.uint8)).tobytes()
    monkeypatch.setattr(
        presence, "_probe_frame_rgb_hires", lambda vp, t: fake_frame_bytes
    )
    monkeypatch.setattr(
        presence,
        "localize_from_rgb_bytes",
        lambda raw, *, height, width: ScorebarLocalization(
            x_left=600, x_right=1300, y_top=20, y_bottom=65, confidence=0.8
        ),
    )
    sample = presence.localize_present_at(Path("dummy.mkv"), 123.0)
    assert sample.time == 123.0
    assert sample.state is PresenceState.PRESENT
    assert sample.confidence == 0.8


def test_localize_present_at_absent(monkeypatch):
    import allaganeye.video.presence as presence

    fake_frame_bytes = (np.zeros((1080, 1920, 3), dtype=np.uint8)).tobytes()
    monkeypatch.setattr(
        presence, "_probe_frame_rgb_hires", lambda vp, t: fake_frame_bytes
    )
    monkeypatch.setattr(
        presence, "localize_from_rgb_bytes", lambda raw, *, height, width: None
    )
    sample = presence.localize_present_at(Path("dummy.mkv"), 50.0)
    assert sample.state is PresenceState.ABSENT
    assert sample.confidence == 0.0


def test_localize_present_at_probe_failure(monkeypatch):
    import allaganeye.video.presence as presence

    monkeypatch.setattr(presence, "_probe_frame_rgb_hires", lambda vp, t: None)
    sample = presence.localize_present_at(Path("dummy.mkv"), 7.0)
    assert sample.state is PresenceState.UNKNOWN
    assert sample.confidence == 0.0


def test_scan_presence_grid_and_order():
    # synthetic sample_fn: present for 200 <= t < 500
    def sample_fn(t: float) -> PresenceSample:
        return PresenceSample(
            time=t,
            state=PresenceState.PRESENT
            if (200.0 <= t < 500.0)
            else PresenceState.ABSENT,
            confidence=1.0,
        )

    samples = scan_presence(
        Path("dummy.mkv"), duration=600.0, stride=100.0, workers=2, sample_fn=sample_fn
    )
    # times must be sorted and cover 0,100,...,600
    assert [s.time for s in samples] == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    assert [s.state for s in samples] == [
        PresenceState.ABSENT,
        PresenceState.ABSENT,
        PresenceState.PRESENT,
        PresenceState.PRESENT,
        PresenceState.PRESENT,
        PresenceState.ABSENT,
        PresenceState.ABSENT,
    ]


def test_detect_matches_by_presence_end_to_end(monkeypatch):
    import allaganeye.video.presence as presence

    # Ground physics: scorebar present for 250 <= t < 740.
    def present_phys(t: float) -> bool:
        return 250.0 <= t < 740.0

    monkeypatch.setattr(
        presence,
        "localize_present_at",
        lambda vp, t, **_kw: PresenceSample(
            time=t,
            state=PresenceState.PRESENT if present_phys(t) else PresenceState.ABSENT,
            confidence=1.0,
        ),
    )

    matches = detect_matches_by_presence(
        Path("dummy.mkv"),
        duration=1000.0,
        stride=100.0,
        t_gap=120.0,
        t_min_match=60.0,
        tol=1.0,
        workers=2,
    )
    assert len(matches) == 1
    # coarse run is 300..700 (grid); refine pulls start->250, end->740
    assert abs(matches[0].start - 250.0) <= 1.0
    assert abs(matches[0].end - 740.0) <= 1.0


def test_detect_matches_present_at_video_edges(monkeypatch):
    import allaganeye.video.presence as presence

    # present for the entire video -> match spans [0, duration], no refine
    monkeypatch.setattr(
        presence,
        "localize_present_at",
        lambda vp, t, **_kw: PresenceSample(
            time=t, state=PresenceState.PRESENT, confidence=1.0
        ),
    )
    matches = detect_matches_by_presence(
        Path("dummy.mkv"),
        duration=500.0,
        stride=100.0,
        t_gap=120.0,
        t_min_match=60.0,
        tol=1.0,
        workers=2,
    )
    assert matches == [PresenceMatch(start=0.0, end=500.0)]


def test_scan_presence_isolates_single_probe_failure():
    """1 probe の VideoProcessingError で全 scan が abort しない (PR #823 R3).

    production の同型 pool (_probe_scorebar_context / _refine_blackout_regions)
    と同じ per-future 縮退。失敗 probe は UNKNOWN になる。
    """

    def fn(t: float) -> PresenceSample:
        if t == 2.0:
            raise VideoProcessingError("probe failed")
        return PresenceSample(time=t, state=PresenceState.PRESENT, confidence=1.0)

    samples = scan_presence(Path("v.mp4"), 4.0, stride=2.0, workers=2, sample_fn=fn)

    assert [s.time for s in samples] == [0.0, 2.0, 4.0]
    assert samples[0].state is PresenceState.PRESENT
    assert samples[1].state is PresenceState.UNKNOWN
    assert samples[1].confidence == 0.0
    assert samples[2].state is PresenceState.PRESENT


def test_scan_presence_all_probe_failures_raise():
    """全 probe 失敗 (ffmpeg 不在等の系統故障) は silent all-absent にせず fail-loud."""

    def fn(t: float) -> PresenceSample:
        raise VideoProcessingError("ffmpeg not found")

    with pytest.raises(VideoProcessingError):
        scan_presence(Path("v.mp4"), 4.0, stride=2.0, workers=2, sample_fn=fn)


def test_scan_presence_default_sampler_all_probe_none_fails_loud(monkeypatch):
    """default sampler 経由: 全 probe が raw None (decode 系統故障) でも fail-loud (R4).

    UNKNOWN の全滅 fail-loud guard は raw None -> UNKNOWN 写像後にカウントする。
    """
    import allaganeye.video.presence as presence

    monkeypatch.setattr(presence, "_probe_frame_rgb_hires", lambda vp, t: None)
    with pytest.raises(VideoProcessingError):
        scan_presence(Path("v.mp4"), 4.0, stride=2.0, workers=2)


def test_scan_presence_default_sampler_mixed_probe_none_stays_absent(monkeypatch):
    """default sampler 経由: 一部 probe のみ raw None なら scan は完走し UNKNOWN 化 (R4)."""
    import allaganeye.video.presence as presence

    loc = ScorebarLocalization(
        x_left=600, x_right=1300, y_top=20, y_bottom=65, confidence=0.8
    )
    monkeypatch.setattr(
        presence, "_probe_frame_rgb_hires", lambda vp, t: None if t == 2.0 else b"x"
    )
    monkeypatch.setattr(
        presence, "localize_from_rgb_bytes", lambda raw, *, height, width: loc
    )
    samples = scan_presence(Path("v.mp4"), 4.0, stride=2.0, workers=2)
    assert [s.state for s in samples] == [
        PresenceState.PRESENT,
        PresenceState.UNKNOWN,
        PresenceState.PRESENT,
    ]
    assert samples[1].confidence == 0.0


def test_scan_presence_partial_unknown_logged(caplog):
    """部分故障 (UNKNOWN >= 1) は UNKNOWN 数 / 総数 を warning で痕跡を残す (#824 sec.5.2-5.3)."""

    def fn(t: float) -> PresenceSample:
        if t == 0.0:
            return PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)
        return PresenceSample(time=t, state=PresenceState.PRESENT, confidence=1.0)

    with caplog.at_level(logging.WARNING, logger="allaganeye.video.presence"):
        samples = scan_presence(
            Path("dummy.mkv"), 10.0, stride=5.0, workers=2, sample_fn=fn
        )
    assert any(s.state is PresenceState.UNKNOWN for s in samples)
    assert any("UNKNOWN" in r.message and "1/3" in r.message for r in caplog.records)


def test_scan_presence_all_unknown_fails_loud():
    """全滅 (全 probe UNKNOWN) は VideoProcessingError (fail-loud) (#824 sec.5.2)."""

    def fn(t):
        return PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)

    with pytest.raises(VideoProcessingError):
        scan_presence(Path("dummy.mkv"), 10.0, stride=5.0, workers=2, sample_fn=fn)


def test_segment_presence_unknown_breaks_run():
    """#824 sec.5.4 site 2b: UNKNOWN sample は present run を構成しない (現行挙動維持)."""
    samples = [
        PresenceSample(0.0, PresenceState.PRESENT, 1.0),
        PresenceSample(1.0, PresenceState.UNKNOWN, 0.0),
        PresenceSample(2.0, PresenceState.PRESENT, 1.0),
    ]
    runs = segment_presence(samples, t_gap=0.5, t_min_match=0.0)
    assert len(runs) == 2


def test_localize_present_at_returns_unknown_on_decode_failure(monkeypatch):
    # #824 site 1: raw None (decode 失敗) は ABSENT でなく UNKNOWN。
    monkeypatch.setattr(
        "allaganeye.video.presence._probe_frame_rgb_hires", lambda *a: None
    )
    s = localize_present_at(Path("dummy.mkv"), 5.0)
    assert s.state is PresenceState.UNKNOWN and s.confidence == 0.0


def test_localize_present_at_has_no_raise_seam():
    # #824 sec.5.4 site 1: raise_on_probe_failure param は削除済み (bool seam 廃止)。
    import inspect

    assert (
        "raise_on_probe_failure"
        not in inspect.signature(localize_present_at).parameters
    )


def test_refine_unknown_treated_absent_with_warning(monkeypatch, caplog):
    """#824 sec.5.4 site 3: refine 中の UNKNOWN は absent 側へ bracket 更新 + warning
    (refine abort しない。既存 test_refine_probe_failure_warns_and_treats_absent の後継)。
    """
    import allaganeye.video.presence as presence

    grid = {0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0}

    def fake_localize(vp, t):
        if t not in grid:
            return PresenceSample(time=t, state=PresenceState.UNKNOWN, confidence=0.0)
        return PresenceSample(
            time=t,
            state=PresenceState.PRESENT
            if (200.0 <= t < 500.0)
            else PresenceState.ABSENT,
            confidence=1.0,
        )

    monkeypatch.setattr(presence, "localize_present_at", fake_localize)
    with caplog.at_level(logging.WARNING, logger="allaganeye.video.presence"):
        matches = presence.detect_matches_by_presence(
            Path("dummy.mkv"),
            duration=600.0,
            stride=100.0,
            t_gap=120.0,
            t_min_match=60.0,
            tol=50.0,
            workers=2,
        )
    assert len(matches) == 1
    assert any("UNKNOWN" in r.message and "refine" in r.message for r in caplog.records)


def test_localize_from_rgb_bytes_none_passthrough_and_decode():
    """共有 helper (R3 dedup): raw None -> None / 正常 bytes は decode して localizer へ."""
    assert localize_from_rgb_bytes(None, height=4, width=4) is None
    # 4x4 RGB の全黒 frame: decode は成功し、localizer は scorebar なし -> None
    raw = bytes(4 * 4 * 3)
    assert localize_from_rgb_bytes(raw, height=4, width=4) is None
