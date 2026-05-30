"""Unit tests for presence-based match detection (no video required)."""

from __future__ import annotations

from collections.abc import Sequence

from allaganeye.video.presence import (
    PresenceMatch,
    PresenceSample,
    refine_boundary,
    segment_presence,
)


def test_presence_sample_fields():
    s = PresenceSample(time=12.0, present=True, confidence=0.9)
    assert s.time == 12.0
    assert s.present is True
    assert s.confidence == 0.9


def test_presence_match_fields():
    m = PresenceMatch(start=10.0, end=900.0)
    assert m.start == 10.0
    assert m.end == 900.0


def _samples(spec: Sequence[tuple[float, bool]]) -> list[PresenceSample]:
    return [PresenceSample(time=t, present=p, confidence=1.0) for t, p in spec]


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
