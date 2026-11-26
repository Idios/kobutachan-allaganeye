"""L6 (former L4): ハイライト候補の rule-based スコアリング (#1049)。

設計の正: `docs/superpowers/specs/2026-11-25-l6-streak-scoring-design.md`

- **ストリーク** = KO / ASSIST イベントを時間窓で束ねたもの。既定は **+-10 秒**
  (信号モデル spec 5.3 節の既定 +-5 秒からの**意図的な差**。理由は設計メモ 1 節 Q2)。
  窓は引数 (`window_seconds`) で変えられる。
- **束ね方**: 直前のイベント発生時刻から `window_seconds` 以内に始まるイベントを
  同じストリークへ入れる (連鎖)。終了時刻ではなく発生時刻の差で判定する。
- **スコア** = 重み付きの長さ (KO > ASSIST) + 密度 (`events / (span + window)`)。
  どちらも 0..1 に正規化し、`length_share` で混ぜる。
- **信号追加に耐える**ように、イベントは `ScoringEvent` へ正規化して受け取る。
  metadata の `signal_id` からの変換は `ScoringEvent.from_signal` が担い、
  未知の `signal_id` は `None` を返す (前方互換: 読み手は無視する)。

I/O (metadata.json の読み書き / CLI / GUI) は本 module の責務ではない。
`highlights[]` の write-back は L7 (#135) で行う。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal
from collections.abc import Iterable, Sequence

__all__ = [
    "DEFAULT_ASSIST_WEIGHT",
    "DEFAULT_KO_WEIGHT",
    "DEFAULT_WEIGHTS",
    "DEFAULT_WINDOW_SECONDS",
    "Highlight",
    "ScoredStreak",
    "ScoringEvent",
    "ScoringWeights",
    "Streak",
    "group_streaks",
    "rank_streaks",
    "score_events",
    "score_streak",
    "scoring_events_from_metadata",
    "to_highlights",
]

SignalKind = Literal["ko", "assist"]

# 既定の窓 (秒)。信号モデル spec 5.3 節は +-5 秒だが、+-5 秒では GT 実測で 71% が
# 単独イベントになりスコアが同点に潰れるため +-10 秒を既定にした (設計メモ 1 節 Q2)。
DEFAULT_WINDOW_SECONDS = 10.0

# KO 1 回の重み (基準)。
DEFAULT_KO_WEIGHT = 1.0

# ASSIST 1 回の重み。KO の 0.35 倍。
# KO は 1 試合の上限が小さく (GT 実測 4-11 回)、ASSIST はその 3-4 倍出るため、
# 同数なら KO の方を高く評価する。GT 検証 (設計メモ GT) で調整する前提の初期値。
DEFAULT_ASSIST_WEIGHT = 0.35

# 重み付き長さの飽和点。`w / (w + saturation)` で 0..1 に写す。
DEFAULT_SATURATION = 1.5

# 密度の満点 (events / 秒)。`span + window` 秒あたりの件数がこれで 1.0 になる。
DEFAULT_FULL_DENSITY = 0.25

# スコア内の長さ項の比率 (残りが密度項)。
DEFAULT_LENGTH_SHARE = 0.7

# metadata の signal_id -> 内部の kind。未知の signal_id は None (前方互換)。
_SIGNAL_KIND: dict[str, SignalKind] = {
    "ko_indicator": "ko",
    "assist_indicator": "assist",
}


@dataclass(frozen=True)
class ScoringEvent:
    """スコアリングに必要な最小のイベント表現。

    `position` / `signal_id` / `match_index` は provenance で、スコアには影響しない
    (`Highlight` の payload を組むときにだけ使う)。
    """

    kind: SignalKind
    start: float
    end: float
    position: int | None = None
    signal_id: str = ""
    match_index: int | None = None

    @classmethod
    def from_signal(
        cls,
        signal_id: str,
        timestamp: float,
        end: float,
        *,
        position: int | None = None,
        match_index: int | None = None,
    ) -> ScoringEvent | None:
        """metadata の `events[]` 1 件から作る。未知の `signal_id` は None。"""
        kind = _SIGNAL_KIND.get(signal_id)
        if kind is None:
            return None
        if not math.isfinite(timestamp) or not math.isfinite(end):
            return None
        return cls(
            kind=kind,
            start=timestamp,
            end=max(end, timestamp),
            position=position,
            signal_id=signal_id,
            match_index=match_index,
        )


@dataclass(frozen=True)
class ScoringWeights:
    """スコア式の重み。既定値は設計メモ 4 節が正。"""

    ko: float = DEFAULT_KO_WEIGHT
    assist: float = DEFAULT_ASSIST_WEIGHT
    saturation: float = DEFAULT_SATURATION
    full_density: float = DEFAULT_FULL_DENSITY
    length_share: float = DEFAULT_LENGTH_SHARE

    def __post_init__(self) -> None:
        for name in ("ko", "assist", "saturation", "full_density", "length_share"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"weights.{name} must be finite")
        if self.ko < 0 or self.assist < 0:
            raise ValueError("weights must be non-negative")
        if self.saturation <= 0 or self.full_density <= 0:
            raise ValueError("saturation / full_density must be positive")
        if not 0.0 <= self.length_share <= 1.0:
            raise ValueError("length_share must be within [0, 1]")


DEFAULT_WEIGHTS = ScoringWeights()


@dataclass(frozen=True)
class Streak:
    """時間窓で束ねられたイベント列 (発生時刻の昇順)。"""

    events: tuple[ScoringEvent, ...]

    @property
    def size(self) -> int:
        return len(self.events)

    @property
    def start(self) -> float:
        return self.events[0].start

    @property
    def end(self) -> float:
        return max(event.end for event in self.events)

    @property
    def span_seconds(self) -> float:
        """最初と最後のイベント発生時刻の差 (単独なら 0)。"""
        return self.events[-1].start - self.events[0].start

    @property
    def ko_count(self) -> int:
        return sum(1 for event in self.events if event.kind == "ko")

    @property
    def assist_count(self) -> int:
        return self.size - self.ko_count

    @property
    def match_index(self) -> int | None:
        """属する試合。束ねが試合をまたがないので全イベントが同じ値を持つ。"""
        for event in self.events:
            if event.match_index is not None:
                return event.match_index
        return None

    @property
    def positions(self) -> tuple[int, ...]:
        return tuple(
            event.position for event in self.events if event.position is not None
        )

    @property
    def signal_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for event in self.events:
            if event.signal_id and event.signal_id not in seen:
                seen.append(event.signal_id)
        return tuple(seen)


@dataclass(frozen=True)
class ScoredStreak:
    """ストリークとスコア。"""

    streak: Streak
    score: float


@dataclass(frozen=True)
class Highlight:
    """`metadata.highlights[]` の 1 件 (wire 形は L7 #135 で write-back する)。

    `start` / `end` は **イベントの活動区間** (最初の発生〜最後の終了)。
    前後秒数 (`--pre` / `--post`) での拡張は L7 が行う。
    """

    index: int
    match_index: int | None
    start: float
    end: float
    score: float
    event_positions: tuple[int, ...]
    signal_ids: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "match_index": self.match_index,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "score": self.score,
            "event_positions": list(self.event_positions),
            "signal_ids": list(self.signal_ids),
        }


def _match_sort_key(match_index: int | None) -> int:
    """試合区画の並びを決定的にするためのソートキー (`None` は先頭)。"""
    return -1 if match_index is None else match_index


def _position_sort_key(position: int | None) -> int:
    """同一時刻のイベントの並びを決定的にするためのソートキー (`None` は先頭)。"""
    return -1 if position is None else position


def group_streaks(
    events: Iterable[ScoringEvent],
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
) -> tuple[Streak, ...]:
    """イベントを時間窓で束ねる。並びは発生時刻の昇順。

    直前のイベント発生時刻から `window_seconds` 以内に始まるイベントを同じ
    ストリークへ連鎖させる (3 秒刻みの 3 件は 1 本、11 秒離れた 2 件は 2 本)。
    非有限の発生時刻を持つイベントは捨てる。

    **`match_index` ごとに分けてから連鎖する。** 連続する試合の最終イベントと
    次の試合の最初のイベントは、試合間の暗転が短いと窓に収まってしまう。
    またいで束ねると `Streak.match_index` が片方の試合を名乗り、L7 の
    クリップ範囲が別試合をまたぐ。区画を先に分けるのは、試合をまたいで
    並んでいるイベントが別の試合のイベントを挟んで連鎖判定を乱すのを避け、
    **入力順を並べ替えても結果が変わらない**ようにするため。
    """
    if not math.isfinite(window_seconds) or window_seconds < 0:
        raise ValueError("window_seconds must be a finite non-negative number")

    partitions: dict[int | None, list[ScoringEvent]] = {}
    for event in sorted(
        (event for event in events if math.isfinite(event.start)),
        key=lambda event: (
            event.start,
            event.end,
            event.kind,
            _position_sort_key(event.position),
        ),
    ):
        partitions.setdefault(event.match_index, []).append(event)

    groups: list[list[ScoringEvent]] = []
    for partition in partitions.values():
        current: list[ScoringEvent] = []
        for event in partition:
            if current and event.start - current[-1].start <= window_seconds:
                current.append(event)
            else:
                if current:
                    groups.append(current)
                current = [event]
        if current:
            groups.append(current)

    ordered_groups = sorted(
        groups,
        key=lambda group: (
            group[0].start,
            _match_sort_key(group[0].match_index),
            _position_sort_key(group[0].position),
            group[0].end,
            group[0].kind,
        ),
    )
    return tuple(Streak(events=tuple(group)) for group in ordered_groups)


def score_streak(
    streak: Streak,
    *,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> float:
    """1 ストリークのスコア (0..1、小数 3 桁)。

    長さ項 = `w / (w + saturation)` (w = KO 重み x KO 数 + ASSIST 重み x ASSIST 数)。
    密度項 = `min(1, size / (span + window) / full_density)`。

    比は**寄与する項だけを最大の重みで正規化してから**計算する。`w` を先に作ると、
    受理している有限値 (`ko=1e308` 等) で `inf` になり、比が 1.0 に
    潰れてしまう (数学的には 2/3 等になるべき場面)。
    """
    if not streak.events:
        raise ValueError("empty streak")
    if not math.isfinite(window_seconds) or window_seconds < 0:
        raise ValueError("window_seconds must be a finite non-negative number")

    # 比は**実際に寄与する項だけ**を、それらと saturation の最大値で正規化して作る。
    # 存在しない種別の重みまで割ると、極端な値が inf になって `inf * 0 = nan` で
    # 全体を汚す (KO だけのストリークが assist の重みで 0 点になる) ため。
    scale = weights.saturation
    if streak.ko_count:
        scale = max(scale, weights.ko)
    if streak.assist_count:
        scale = max(scale, weights.assist)
    weighted = 0.0
    if streak.ko_count:
        weighted += (weights.ko / scale) * streak.ko_count
    if streak.assist_count:
        weighted += (weights.assist / scale) * streak.assist_count
    saturation = weights.saturation / scale
    if weighted + saturation <= 0:
        length_term = 0.0
    else:
        length_term = weighted / (weighted + saturation)

    denominator = max(streak.span_seconds + window_seconds, 1e-6)
    density = streak.size / denominator
    density_term = min(1.0, density / weights.full_density)

    share = weights.length_share
    value = share * length_term + (1.0 - share) * density_term
    return round(min(1.0, max(0.0, value)), 3)


def score_events(
    events: Iterable[ScoringEvent],
    *,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    weights: ScoringWeights = DEFAULT_WEIGHTS,
) -> tuple[ScoredStreak, ...]:
    """束ねてスコアを付ける。並びは**発生時刻昇順** (元の順序を保つ)。"""
    streaks = group_streaks(events, window_seconds)
    return tuple(
        ScoredStreak(
            streak=streak,
            score=score_streak(streak, window_seconds=window_seconds, weights=weights),
        )
        for streak in streaks
    )


def rank_streaks(
    scored: Iterable[ScoredStreak],
) -> tuple[ScoredStreak, ...]:
    """スコア降順に並べる (同点は発生時刻昇順で安定)。"""
    return tuple(sorted(scored, key=lambda item: (-item.score, item.streak.start)))


def to_highlights(
    scored: Iterable[ScoredStreak],
) -> tuple[Highlight, ...]:
    """スコア順の `Highlight` 列 (index は 1 始まり) を作る。"""
    return tuple(
        Highlight(
            index=index,
            match_index=item.streak.match_index,
            start=item.streak.start,
            end=item.streak.end,
            score=item.score,
            event_positions=item.streak.positions,
            signal_ids=item.streak.signal_ids,
        )
        for index, item in enumerate(rank_streaks(scored), start=1)
    )


def _match_index_of(value: Any) -> int | None:
    """`match_index` を int に正規化する。

    JSON Schema の `integer` は `1.0` も許すが、Python の `json` は float で
    読む。ここで落とすと試合区画が消えて束ねが別試合をまたぐので、
    整数値の float は int に寄せる。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def scoring_events_from_metadata(
    events: Sequence[dict[str, Any]],
) -> tuple[ScoringEvent, ...]:
    """metadata の `events[]` から `ScoringEvent` 列を作る (未知の信号は捨てる)。

    `position` は 1 始まりの索引 (metadata の並びを保つ)。
    """
    converted: list[ScoringEvent] = []
    for index, raw in enumerate(events, start=1):
        signal_id = raw.get("signal_id")
        timestamp = raw.get("timestamp")
        end = raw.get("end")
        if not isinstance(signal_id, str):
            continue
        if not isinstance(timestamp, (int, float)) or not isinstance(end, (int, float)):
            continue
        match_index = _match_index_of(raw.get("match_index"))
        event = ScoringEvent.from_signal(
            signal_id,
            float(timestamp),
            float(end),
            position=index,
            match_index=match_index,
        )
        if event is not None:
            converted.append(event)
    return tuple(converted)
