"""L6 rule-based ストリークスコアリング (#1049) の単体テスト。

設計の正: `docs/superpowers/specs/2026-11-25-l6-streak-scoring-design.md`
GT 突合は `tests/test_highlight_scoring_gt.py` (slow マーカー) 側。
"""

from __future__ import annotations

import pytest

from allaganeye.highlights.scoring import (
    DEFAULT_WEIGHTS,
    DEFAULT_WINDOW_SECONDS,
    ScoringEvent,
    ScoringWeights,
    group_streaks,
    rank_streaks,
    score_events,
    score_streak,
    scoring_events_from_metadata,
    to_highlights,
)


def ko(start: float, end: float | None = None) -> ScoringEvent:
    return ScoringEvent(kind="ko", start=start, end=start + 1.5 if end is None else end)


def assist(start: float, end: float | None = None) -> ScoringEvent:
    return ScoringEvent(
        kind="assist", start=start, end=start + 1.5 if end is None else end
    )


class TestGroupStreaks:
    def test_empty_input_yields_no_streaks(self) -> None:
        assert group_streaks([]) == ()

    def test_single_event_is_its_own_streak(self) -> None:
        [streak] = group_streaks([ko(10.0)])
        assert streak.size == 1
        assert streak.start == 10.0

    def test_events_within_the_window_chain_together(self) -> None:
        # 3 / 6 / 9 秒: 直前から 3 秒刻みなので 1 本。
        streaks = group_streaks([ko(3.0), assist(6.0), ko(9.0)])
        assert len(streaks) == 1
        assert streaks[0].size == 3
        assert (streaks[0].ko_count, streaks[0].assist_count) == (2, 1)

    def test_gap_beyond_the_window_splits(self) -> None:
        # 既定 (10 秒) に対して 11 秒差なので 2 本。
        streaks = group_streaks([ko(10.0), ko(21.0)])
        assert [streak.size for streak in streaks] == [1, 1]

    def test_window_is_a_parameter(self) -> None:
        events = [ko(10.0), ko(16.0)]
        assert len(group_streaks(events, window_seconds=5.0)) == 2
        assert len(group_streaks(events, window_seconds=6.0)) == 1

    def test_window_default_is_ten_seconds(self) -> None:
        # 既定ちょうどは同じストリーク、超えたら別。
        assert len(group_streaks([ko(0.0), ko(10.0)])) == 1
        assert len(group_streaks([ko(0.0), ko(10.5)])) == 2

    def test_out_of_order_input_is_sorted(self) -> None:
        streaks = group_streaks([ko(9.0), assist(3.0), ko(6.0)])
        assert [event.start for event in streaks[0].events] == [3.0, 6.0, 9.0]

    def test_non_finite_starts_are_dropped(self) -> None:
        streaks = group_streaks([ko(float("nan")), ko(1.0)])
        assert len(streaks) == 1
        assert streaks[0].size == 1

    @pytest.mark.parametrize("window", [-1.0, float("nan"), float("inf")])
    def test_invalid_window_is_rejected(self, window: float) -> None:
        with pytest.raises(ValueError):
            group_streaks([ko(1.0)], window_seconds=window)

    def test_span_uses_event_start_times(self) -> None:
        [streak] = group_streaks([ko(10.0, 20.0), assist(12.0, 30.0)])
        assert streak.span_seconds == 2.0
        assert streak.end == 30.0

    def test_events_from_different_matches_never_group(self) -> None:
        # 連続する試合の境界は暗転が短いと窓に収まる。またいで束ねると
        # クリップ範囲が別試合にまたがるため、match_index で必ず切る。
        events = [
            ScoringEvent(kind="ko", start=100.0, end=101.5, match_index=1),
            ScoringEvent(kind="ko", start=102.0, end=103.5, match_index=2),
        ]
        assert [len(streak.events) for streak in group_streaks(events)] == [1, 1]
        assert [streak.match_index for streak in group_streaks(events)] == [1, 2]

    def test_match_index_none_is_its_own_partition(self) -> None:
        # `None` は独立した区画。同じ試合の 2 件は `None` のイベントを挟んでも連鎖する。
        events = [
            ScoringEvent(kind="ko", start=10.0, end=11.5, match_index=1),
            ScoringEvent(kind="ko", start=11.0, end=12.5),
            ScoringEvent(kind="ko", start=12.0, end=13.5, match_index=1),
        ]
        assert [
            (streak.match_index, streak.size) for streak in group_streaks(events)
        ] == [
            (1, 2),
            (None, 1),
        ]

    def test_input_order_does_not_change_the_grouping(self) -> None:
        # 同一時刻のイベントが別試合に属していても、入力順で結果が変わらないこと。
        a = ScoringEvent(kind="ko", start=0.0, end=1.0, match_index=1)
        b = ScoringEvent(kind="ko", start=0.0, end=1.0, match_index=2)
        c = ScoringEvent(kind="ko", start=1.0, end=2.0, match_index=1)
        expected = [
            (streak.start, streak.match_index, streak.size)
            for streak in group_streaks([a, b, c])
        ]
        for permutation in ([b, a, c], [c, b, a], [b, c, a]):
            actual = [
                (streak.start, streak.match_index, streak.size)
                for streak in group_streaks(permutation)
            ]
            assert actual == expected
        # 同一試合の a と c は 1 秒差なので同じストリークに入る。
        assert (0.0, 1, 2) in expected


class TestScoreStreak:
    def test_score_is_bounded_and_rounded(self) -> None:
        [streak] = group_streaks([ko(1.0)])
        score = score_streak(streak)
        assert 0.0 <= score <= 1.0
        assert round(score, 3) == score

    def test_ko_outweighs_assist(self) -> None:
        [only_ko] = group_streaks([ko(1.0)])
        [only_assist] = group_streaks([assist(1.0)])
        assert score_streak(only_ko) > score_streak(only_assist)

    def test_more_events_score_higher_when_density_is_equal(self) -> None:
        # 同じ 1 秒間隔で件数だけ増やす。
        [one] = group_streaks([ko(1.0)])
        [two] = group_streaks([ko(1.0), ko(2.0)])
        [three] = group_streaks([ko(1.0), ko(2.0), ko(3.0)])
        assert score_streak(one) < score_streak(two) < score_streak(three)

    def test_tighter_events_score_higher_for_the_same_count(self) -> None:
        # 2 件を 0.5 秒差と 4.0 秒差で比べる (件数・KO 数は同じ)。
        [tight] = group_streaks([ko(1.0), ko(1.5)])
        [loose] = group_streaks([ko(1.0), ko(5.0)])
        assert score_streak(tight) > score_streak(loose)

    def test_assist_weight_is_applied(self) -> None:
        [streak] = group_streaks([assist(1.0)])
        low = score_streak(streak, weights=ScoringWeights(assist=0.1))
        high = score_streak(streak, weights=ScoringWeights(assist=0.9))
        assert low < high

    def test_window_changes_the_density_term(self) -> None:
        # 単独イベントは span=0 なので、密度項 = 1 / window で窓に反比例する。
        [streak] = group_streaks([ko(1.0)])
        assert score_streak(streak, window_seconds=5.0) < score_streak(
            streak, window_seconds=1.0
        )

    def test_extreme_weights_do_not_overflow(self) -> None:
        # 比は最大の重みで正規化するので、巨大な重みでも数学値のまま。
        weights = ScoringWeights(ko=1e308, saturation=1e308)
        [one] = group_streaks([ko(1.0)])
        # length 1/2 = 0.5, density 1/10/0.25 = 0.4 -> 0.7*0.5 + 0.3*0.4
        assert score_streak(one, weights=weights) == pytest.approx(0.470)
        [two] = group_streaks([ko(1.0), ko(2.0)])
        # length 2/3, density 2/11/0.25
        assert score_streak(two, weights=weights) == pytest.approx(0.685)

    def test_absent_signal_weight_does_not_change_the_score(self) -> None:
        # KO しかないストリークに ASSIST の重み (未使用) が影響してはいけない。
        # 極端な値でも `inf * 0 = nan` で汚さないこと。
        [streak] = group_streaks([ko(1.0)])
        normal = score_streak(streak, weights=ScoringWeights())
        for absent in (0.0, 1e308):
            assert score_streak(streak, weights=ScoringWeights(assist=absent)) == (
                normal
            )

    def test_invalid_weights_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            ScoringWeights(ko=-1.0)
        with pytest.raises(ValueError):
            ScoringWeights(length_share=1.5)
        with pytest.raises(ValueError):
            ScoringWeights(full_density=0.0)


class TestScoreEventsAndRanking:
    def test_score_events_keeps_occurrence_order(self) -> None:
        scored = score_events([ko(40.0), assist(10.0), ko(25.0)])
        assert [item.streak.start for item in scored] == [10.0, 25.0, 40.0]

    def test_rank_streaks_sorts_by_score_then_time(self) -> None:
        scored = score_events([assist(10.0), ko(30.0), ko(30.5)])
        ranked = rank_streaks(scored)
        assert ranked[0].score == max(item.score for item in scored)
        assert ranked[0].streak.start == 30.0
        assert ranked[-1].streak.start == 10.0

    def test_to_highlights_numbers_by_rank(self) -> None:
        # 3 本になるよう窓 (10 秒) より大きく離す。
        highlights = to_highlights(score_events([assist(10.0), ko(30.0), ko(41.0)]))
        assert [item.index for item in highlights] == [1, 2, 3]
        assert highlights[0].start == 30.0
        assert highlights[-1].start == 10.0
        assert highlights[0].event_positions == ()
        payload = highlights[0].to_payload()
        assert set(payload) == {
            "index",
            "match_index",
            "start",
            "end",
            "score",
            "event_positions",
            "signal_ids",
        }


class TestMetadataConversion:
    def test_maps_known_signal_ids_and_keeps_positions(self) -> None:
        events = [
            {
                "signal_id": "ko_indicator",
                "timestamp": 10.0,
                "end": 11.0,
                "match_index": 2,
            },
            {
                "signal_id": "assist_indicator",
                "timestamp": 12.0,
                "end": 13.5,
                "match_index": 2,
            },
        ]
        converted = scoring_events_from_metadata(events)
        assert [(event.kind, event.position) for event in converted] == [
            ("ko", 1),
            ("assist", 2),
        ]
        [streak] = group_streaks(converted)
        assert streak.match_index == 2
        assert streak.positions == (1, 2)
        assert streak.signal_ids == ("ko_indicator", "assist_indicator")

    def test_unknown_signal_is_ignored_for_forward_compat(self) -> None:
        events = [
            {
                "signal_id": "future_signal",
                "timestamp": 1.0,
                "end": 2.0,
                "match_index": 1,
            },
            {
                "signal_id": "ko_indicator",
                "timestamp": 3.0,
                "end": 4.0,
                "match_index": 1,
            },
        ]
        converted = scoring_events_from_metadata(events)
        assert [event.kind for event in converted] == ["ko"]

    def test_float_match_index_is_normalised(self) -> None:
        # JSON の `1.0` は integer スキーマ上有効。落とすと試合区画が消える。
        events = [
            {
                "signal_id": "ko_indicator",
                "timestamp": 10.0,
                "end": 11.0,
                "match_index": 1.0,
            },
            {
                "signal_id": "ko_indicator",
                "timestamp": 12.0,
                "end": 13.0,
                "match_index": 2.0,
            },
        ]
        converted = scoring_events_from_metadata(events)
        assert [event.match_index for event in converted] == [1, 2]
        assert len(group_streaks(converted)) == 2

    def test_malformed_entries_are_skipped(self) -> None:
        events = [
            {"signal_id": "ko_indicator", "timestamp": "x", "end": 1.0},
            {"signal_id": "ko_indicator", "timestamp": 1.0},
            {"timestamp": 1.0, "end": 2.0},
        ]
        assert scoring_events_from_metadata(events) == ()

    def test_default_window_is_ten_seconds(self) -> None:
        # 信号モデル spec 5.3 節は +-5 秒だが、実測 (設計メモ 1 節 Q2) で +-10 秒に
        # 変更した。spec との差分は設計メモに記録してある。
        assert DEFAULT_WINDOW_SECONDS == 10.0
        assert DEFAULT_WEIGHTS.ko > DEFAULT_WEIGHTS.assist
