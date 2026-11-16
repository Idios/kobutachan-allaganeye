"""切り抜きクリップ計画の単体テスト (#135 / #1050 Phase A)。

`allaganeye/export/clips.py` は ffmpeg を呼ばない純関数なので、束ね・クランプ・
既定値の仕様をここで固定する。
"""

from __future__ import annotations

import pytest

from allaganeye.export.clips import (
    DEFAULT_GAP_SECONDS,
    DEFAULT_POST_SECONDS,
    DEFAULT_PRE_SECONDS,
    clip_type_label,
    plan_clips,
)

MATCHES = [
    {"index": 1, "start_time": 100.0, "end_time": 400.0},
    {"index": 2, "start_time": 500.0, "end_time": 800.0},
]


def _event(
    timestamp: float,
    *,
    end: float | None = None,
    signal_id: str = "ko_indicator",
    match_index: int | None = 1,
) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "timestamp": timestamp,
        "end": timestamp + 1.5 if end is None else end,
        "score": 0.9,
        "evidence": {"samples": 15},
        "match_index": match_index,
    }


def test_defaults_come_from_the_issue() -> None:
    assert (DEFAULT_PRE_SECONDS, DEFAULT_POST_SECONDS) == (10.0, 10.0)
    assert DEFAULT_GAP_SECONDS == 5.0


def test_single_event_uses_pre_and_post_margins() -> None:
    plan = plan_clips([_event(200.0)], MATCHES)
    assert len(plan.clips) == 1
    clip = plan.clips[0]
    assert clip.start == pytest.approx(190.0)
    assert clip.end == pytest.approx(211.5)
    assert clip.match_index == 1
    assert clip.signal_ids == ("ko_indicator",)
    assert clip.type_label == "ko"
    assert clip.index == 1


def test_nearby_events_merge_into_one_clip() -> None:
    """`--gap` 以内に始まるイベントは 1 本に束ねる（Q2 B）。"""
    events = [_event(200.0), _event(204.0, signal_id="assist_indicator")]
    plan = plan_clips(events, MATCHES)
    assert len(plan.clips) == 1
    clip = plan.clips[0]
    assert clip.start == pytest.approx(190.0)
    assert clip.end == pytest.approx(215.5)  # 204 + 1.5 + post
    assert clip.signal_ids == ("assist_indicator", "ko_indicator")
    assert clip.type_label == "assist_ko"
    assert plan.merged_events == 1


def test_gap_boundary_is_inclusive() -> None:
    """`timestamp - クリップ終端 == gap` は束ねる（<= 判定）。"""
    events = [_event(200.0, end=200.5), _event(205.5)]
    plan = plan_clips(events, MATCHES, gap=5.0)
    assert len(plan.clips) == 1


def test_just_beyond_gap_stays_separate() -> None:
    events = [_event(200.0, end=200.5), _event(205.6)]
    plan = plan_clips(events, MATCHES, gap=5.0)
    assert len(plan.clips) == 2
    assert plan.merged_events == 0


def test_gap_is_configurable() -> None:
    events = [_event(200.0, end=200.5), _event(212.0)]
    assert len(plan_clips(events, MATCHES, gap=5.0).clips) == 2
    assert len(plan_clips(events, MATCHES, gap=20.0).clips) == 1


def test_chained_events_stay_in_one_clip() -> None:
    """畳むたびに終端が伸びるので、間接的な連鎖も 1 本になる。"""
    events = [_event(200.0, end=200.5), _event(205.0), _event(209.0), _event(213.0)]
    plan = plan_clips(events, MATCHES, gap=5.0)
    assert len(plan.clips) == 1
    assert plan.merged_events == 3


def test_events_in_different_matches_never_merge() -> None:
    events = [_event(399.0), _event(500.5, match_index=2)]
    plan = plan_clips(events, MATCHES, gap=600.0)
    assert [clip.match_index for clip in plan.clips] == [1, 2]


def test_range_is_clamped_to_the_match_interval() -> None:
    events = [_event(101.0), _event(399.0)]
    plan = plan_clips(events, MATCHES, pre=10.0, post=10.0, gap=1000.0)
    clip = plan.clips[0]
    assert clip.start == pytest.approx(100.0)
    assert clip.end == pytest.approx(400.0)


def test_events_outside_every_match_are_skipped_and_counted() -> None:
    events = [
        _event(200.0),
        _event(50.0, match_index=None),
        _event(60.0, match_index=9),
    ]
    plan = plan_clips(events, MATCHES)
    assert len(plan.clips) == 1
    assert plan.outside_events == 2


def test_malformed_events_are_skipped() -> None:
    events: list[dict[str, object]] = [
        {"signal_id": "ko_indicator", "timestamp": "x", "end": 1.0, "match_index": 1},
        {"signal_id": "", "timestamp": 1.0, "end": 2.0, "match_index": 1},
        {"timestamp": 1.0, "end": 2.0, "match_index": 1},
        _event(200.0),
    ]
    plan = plan_clips(events, MATCHES)
    assert len(plan.clips) == 1
    assert plan.outside_events == 3


def test_clip_indexes_are_one_based_and_ordered() -> None:
    events = [_event(700.0, match_index=2), _event(200.0), _event(600.0, match_index=2)]
    plan = plan_clips(events, MATCHES)
    assert [clip.index for clip in plan.clips] == [1, 2, 3]
    assert [clip.match_index for clip in plan.clips] == [1, 2, 2]
    assert plan.clips[1].start < plan.clips[2].start


def test_unknown_signal_id_is_still_clipped() -> None:
    """未知 signal_id も落とさない（前方互換）。ラベルはファイル名安全に整形する。"""
    plan = plan_clips([_event(200.0, signal_id="kill_feed/v2")], MATCHES)
    assert len(plan.clips) == 1
    assert plan.clips[0].type_label == "kill_feed_v2"


def test_no_events_yields_an_empty_plan() -> None:
    plan = plan_clips([], MATCHES)
    assert plan.clips == ()
    assert plan.outside_events == 0
    assert plan.merged_events == 0


def test_matches_without_valid_spans_are_ignored() -> None:
    matches = [
        {"index": 1, "start_time": 10.0, "end_time": 5.0},
        {"index": 2},
        {"start_time": 1.0, "end_time": 2.0},
    ]
    plan = plan_clips([_event(200.0)], matches)
    assert plan.clips == ()
    assert plan.outside_events == 1


@pytest.mark.parametrize(
    ("signal_ids", "expected"),
    [
        (("ko_indicator",), "ko"),
        (("assist_indicator",), "assist"),
        (("assist_indicator", "ko_indicator"), "assist_ko"),
        ((), "clip"),
        (("Booster!!",), "booster"),
    ],
)
def test_clip_type_label(signal_ids: tuple[str, ...], expected: str) -> None:
    assert clip_type_label(signal_ids) == expected


def test_clip_start_never_goes_negative() -> None:
    """壊れた metadata (match start < 0) でも負の -ss を作らない。"""
    matches = [{"index": 1, "start_time": -30.0, "end_time": 100.0}]
    plan = plan_clips([_event(0.5, match_index=1)], matches, pre=10.0)
    assert plan.clips[0].start == 0.0


def test_non_finite_event_timestamps_are_skipped() -> None:
    """NaN / inf を ffmpeg の -ss / -to に渡さない (Codex review 2026-11-16)。"""
    events = [
        _event(float("nan")),
        {**_event(200.0), "end": float("inf")},
        _event(250.0),
    ]
    plan = plan_clips(events, MATCHES)
    assert [clip.start for clip in plan.clips] == [240.0]
    assert plan.outside_events == 2


def test_non_finite_match_spans_are_ignored() -> None:
    matches = [{"index": 1, "start_time": 100.0, "end_time": float("nan")}]
    plan = plan_clips([_event(200.0)], matches)
    assert plan.clips == ()
    assert plan.outside_events == 1


def test_non_object_members_are_skipped() -> None:
    """壊れた metadata (`[null]` / 文字列) で AttributeError を投げない。"""
    plan = plan_clips([None, "junk", _event(200.0)], [None, *MATCHES])
    assert len(plan.clips) == 1
    assert plan.outside_events == 2


def test_oversized_integer_timestamps_are_skipped() -> None:
    """JSON の 401 桁整数は float() が OverflowError を投げる (Codex review 2026-11-16)。"""
    huge = 10**400
    events = [
        {**_event(200.0), "timestamp": huge},
        {**_event(200.0), "end": huge},
        _event(250.0),
    ]
    plan = plan_clips(events, MATCHES)
    assert [clip.start for clip in plan.clips] == [240.0]
    assert plan.outside_events == 2


def test_oversized_integer_match_bounds_are_ignored() -> None:
    matches = [{"index": 1, "start_time": 0, "end_time": 10**400}]
    plan = plan_clips([_event(200.0)], matches)
    assert plan.clips == ()
    assert plan.outside_events == 1
