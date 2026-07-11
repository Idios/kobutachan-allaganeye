"""#824 probe-failure semantics: 中立契約 module の unit (spec §5.1)."""

import dataclasses

import pytest

from allaganeye.video.probe_state import (
    PresenceSample,
    PresenceState,
    ProbeFailurePolicy,
)


def test_presence_state_members():
    assert {s.value for s in PresenceState} == {"present", "absent", "unknown"}


def test_presence_sample_is_frozen_tristate():
    s = PresenceSample(time=1.5, state=PresenceState.UNKNOWN, confidence=0.0)
    assert s.state is PresenceState.UNKNOWN
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.state = PresenceState.PRESENT  # type: ignore[misc]


def test_presence_sample_has_no_bool_escape_hatch():
    # #824 §5.1: `.present` property は UNKNOWN→False の silent 変換経路になるため
    # 提供しない (契約 pin)。
    s = PresenceSample(time=0.0, state=PresenceState.PRESENT, confidence=1.0)
    assert not hasattr(s, "present")


def test_probe_failure_policy_members():
    assert {p.value for p in ProbeFailurePolicy} == {"raise", "isolate"}
