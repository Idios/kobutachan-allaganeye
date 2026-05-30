"""Unit tests for presence-based match detection (no video required)."""

from __future__ import annotations

from allaganeye.video.presence import PresenceMatch, PresenceSample


def test_presence_sample_fields():
    s = PresenceSample(time=12.0, present=True, confidence=0.9)
    assert s.time == 12.0
    assert s.present is True
    assert s.confidence == 0.9


def test_presence_match_fields():
    m = PresenceMatch(start=10.0, end=900.0)
    assert m.start == 10.0
    assert m.end == 900.0
