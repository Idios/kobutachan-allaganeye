"""L4 イベントから切り抜きクリップを計画する (#135 / #1050 Phase A)。

L4 (`allaganeye indicators`) が metadata.json に書いた `events[]` を、試合区間で
クランプした「前後マージン付きの切り抜き区間」へ変換する。ここは **純関数だけ**で
ffmpeg を呼ばない (実行は `allaganeye.export.pool.export_matches` を再利用する)。

仕様 (Idios 判断 2026-11-16):

- 既定は **イベント 1 件 = 1 クリップ**ではなく、**近接イベントを束ねて 1 クリップ**に
  する (`--gap`、既定 5 秒)。同じ試合の中で「次のイベント開始 - 今の区間終端 <= gap」
  なら同一クリップへ畳む
- 前後マージンは `--pre` / `--post` (既定 10 秒ずつ)
- 切り出し元は**元録画**で、範囲は試合区間 `matches[i]` にクランプする
- どの試合にも属さないイベント (`match_index: null`) は**対象外**（クランプ先が無い）。
  件数は `ClipPlan.outside_events` で返し、呼び出し側が warning として出す
- 既知でない `signal_id` も切り抜く（前方互換）。表示・ファイル名の種別は
  `signal_id` から作る
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any
from collections.abc import Iterable, Mapping

DEFAULT_PRE_SECONDS = 10.0
"""イベント開始の何秒前から切り抜くか (#135 / #1050 の既定)。"""

DEFAULT_POST_SECONDS = 10.0
"""イベント終端の何秒後まで切り抜くか。"""

DEFAULT_GAP_SECONDS = 5.0
"""この秒数以内に次のイベントが始まるなら同一クリップへ束ねる。"""

_SIGNAL_SHORT_LABELS: dict[str, str] = {
    "ko_indicator": "ko",
    "assist_indicator": "assist",
}

_UNSAFE_LABEL_RE = re.compile(r"[^a-z0-9_]+")
_MAX_LABEL_LEN = 32


@dataclass(frozen=True)
class Clip:
    """1 本の切り抜き区間 (元録画の絶対秒)。

    `index` は 1 始まりで、`--name-pattern` の `{idx}` に入る。
    """

    index: int
    match_index: int
    start: float
    end: float
    signal_ids: tuple[str, ...]
    event_indexes: tuple[int, ...] = ()
    """このクリップに含まれるイベントの **1 始まりの並び順** (元 `events[]` の位置)。"""

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def type_label(self) -> str:
        """`--name-pattern` の `{type}` に入れる種別ラベル。"""
        return clip_type_label(self.signal_ids)


@dataclass(frozen=True)
class ClipPlan:
    """計画結果。`clips` は元録画の時刻順（試合 index 昇順 -> 開始昇順）。"""

    clips: tuple[Clip, ...]
    outside_events: int
    """試合区間を持たないため対象外にしたイベント数。"""
    merged_events: int
    """他のイベントと束ねた結果、単独クリップにならなかったイベント数。"""


def filter_clips(plan: ClipPlan, event_indexes: Iterable[int]) -> ClipPlan:
    """`event_indexes` (1 始まりの `events[]` 位置) を含むクリップだけ残す。

    GUI の「選択した 1 件だけ切り抜く」用 (#1131 Q2 C)。クリップ番号は 1 から
    振り直す (`--name-pattern` の `{idx}` が飛ばないように)。索引が 1 つも
    クリップに含まれない場合は空の計画になる。

    `merged_events` は **残したクリップの中だけ** で数え直す (全件時の値を
    そのまま出すと、1 本だけ切り抜いたのに「3 件を束ねた」と報告してしまう)。
    試合区間の外にあるイベント数 `outside_events` は選択と無関係なので保持する。
    """
    wanted = set(event_indexes)
    if not wanted:
        # 未指定 = 絞り込まない (CLI の `--event-index` 省略と同じ意味)。
        return plan
    kept = [clip for clip in plan.clips if wanted.intersection(clip.event_indexes)]
    reindexed = tuple(
        Clip(
            index=position,
            match_index=clip.match_index,
            start=clip.start,
            end=clip.end,
            signal_ids=clip.signal_ids,
            event_indexes=clip.event_indexes,
        )
        for position, clip in enumerate(kept, start=1)
    )
    return ClipPlan(
        clips=reindexed,
        outside_events=plan.outside_events,
        merged_events=sum(len(clip.event_indexes) - 1 for clip in reindexed),
    )


def clip_type_label(signal_ids: Iterable[str]) -> str:
    """`signal_ids` からファイル名用の種別ラベルを作る。

    単一信号は短縮名 (`ko` / `assist`)。未知の `signal_id` は小文字化して
    ファイル名に入れられる文字だけ残す。複数混在は短縮名を `_` で連結する。
    """
    labels: list[str] = []
    for signal_id in signal_ids:
        short = _SIGNAL_SHORT_LABELS.get(signal_id)
        if short is None:
            short = _UNSAFE_LABEL_RE.sub("_", signal_id.lower()).strip("_") or "unknown"
        if short not in labels:
            labels.append(short)
    if not labels:
        return "clip"
    label = "_".join(sorted(labels))
    return label[:_MAX_LABEL_LEN]


def _finite_seconds(value: object) -> float | None:
    """秒として使える値を float で返す。使えなければ None。

    - `bool` は `int` の派生なので除外する
    - NaN / inf は ffmpeg の `-ss` / `-to` に渡せない
    - JSON の 401 桁整数などは `float()` が OverflowError を投げる
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _match_spans(
    matches: Iterable[object],
) -> dict[int, tuple[float, float]]:
    spans: dict[int, tuple[float, float]] = {}
    for match in matches:
        if not isinstance(match, Mapping):
            continue
        index = match.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            continue
        start = _finite_seconds(match.get("start_time"))
        end = _finite_seconds(match.get("end_time"))
        if start is None or end is None or end <= start:
            continue
        spans[index] = (start, end)
    return spans


def plan_clips(
    events: Iterable[object],
    matches: Iterable[object],
    *,
    pre: float = DEFAULT_PRE_SECONDS,
    post: float = DEFAULT_POST_SECONDS,
    gap: float = DEFAULT_GAP_SECONDS,
) -> ClipPlan:
    """イベント列を切り抜き区間へ変換する。

    束ねの判定は「**そのクリップの現時点の終端**から `gap` 秒以内に次のイベントが
    始まるか」で行う（イベントを畳むたびに終端が伸びるので、連鎖も 1 本になる）。
    """
    spans = _match_spans(matches)
    ordered: list[tuple[int, float, float, str, int]] = []
    outside = 0
    for position, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            # metadata は手編集されうる。`[null]` で AttributeError を投げると
            # exit code が入力エラー (2) から外れるので、型で弾く。
            outside += 1
            continue
        timestamp = _finite_seconds(event.get("timestamp"))
        raw_end = event.get("end")
        end = _finite_seconds(timestamp if raw_end is None else raw_end)
        signal_id = event.get("signal_id")
        match_index = event.get("match_index")
        if timestamp is None or end is None:
            # NaN / inf / 桁あふれを ffmpeg の -ss / -to に渡さない。
            outside += 1
            continue
        if not isinstance(signal_id, str) or not signal_id:
            outside += 1
            continue
        if not isinstance(match_index, int) or isinstance(match_index, bool):
            outside += 1
            continue
        if match_index not in spans:
            outside += 1
            continue
        start_s = timestamp
        end_s = max(end, start_s)
        ordered.append((match_index, start_s, end_s, signal_id, position))

    ordered.sort(key=lambda item: (item[0], item[1], item[2]))

    groups: list[dict[str, Any]] = []
    for match_index, start_s, end_s, signal_id, position in ordered:
        current = groups[-1] if groups else None
        if (
            current is not None
            and current["match_index"] == match_index
            and start_s - current["end"] <= gap
        ):
            current["end"] = max(current["end"], end_s)
            if signal_id not in current["signal_ids"]:
                current["signal_ids"].append(signal_id)
            current["events"] += 1
            current["positions"].append(position)
            continue
        groups.append(
            {
                "match_index": match_index,
                "start": start_s,
                "end": end_s,
                "signal_ids": [signal_id],
                "events": 1,
                "positions": [position],
            }
        )

    clips: list[Clip] = []
    for group in groups:
        span_start, span_end = spans[group["match_index"]]
        # 録画先頭より前は切り抜けない (壊れた metadata で match start が負でも
        # ffmpeg に負の -ss を渡さない)。
        start = round(max(0.0, span_start, group["start"] - pre), 2)
        end = round(min(span_end, group["end"] + post), 2)
        if end <= start:
            continue
        clips.append(
            Clip(
                index=len(clips) + 1,
                match_index=int(group["match_index"]),
                start=start,
                end=end,
                signal_ids=tuple(sorted(group["signal_ids"])),
                event_indexes=tuple(sorted(int(p) for p in group["positions"])),
            )
        )

    merged = sum(int(group["events"]) - 1 for group in groups)
    return ClipPlan(clips=tuple(clips), outside_events=outside, merged_events=merged)


__all__ = [
    "DEFAULT_GAP_SECONDS",
    "DEFAULT_POST_SECONDS",
    "DEFAULT_PRE_SECONDS",
    "Clip",
    "ClipPlan",
    "clip_type_label",
    "filter_clips",
    "plan_clips",
]
