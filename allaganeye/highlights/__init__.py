"""L6 (former L4): ハイライトの価値評価。

現行は rule-based (#1049)。本 package は「信号 -> ストリーク -> スコア」の
純関数だけを持ち、I/O (metadata.json の読み書き / CLI / GUI) は持たない。
"""

from allaganeye.highlights.scoring import (
    DEFAULT_ASSIST_WEIGHT,
    DEFAULT_KO_WEIGHT,
    DEFAULT_WEIGHTS,
    DEFAULT_WINDOW_SECONDS,
    Highlight,
    ScoredStreak,
    ScoringEvent,
    ScoringWeights,
    Streak,
    group_streaks,
    rank_streaks,
    score_events,
    score_streak,
    scoring_events_from_metadata,
    to_highlights,
)

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
