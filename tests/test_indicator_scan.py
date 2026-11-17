"""並列走査のチャンク計画・マージ・逐次等価性 (#1140)。

`allaganeye indicators` の照合は 1 コアで 217 フレーム/秒しか出ず、2.8 時間の
録画では約 8 分かかる。`detector.py` と同じく **チャンク並列** にして、
結果が逐次走査と完全に一致することをここで pin する。

実 ffmpeg / 実動画は使わない (合成フレームを注入する)。実測値は
`docs/testing-guide.md` の「KO / ASSIST 走査の実測」を参照。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from itertools import pairwise

import numpy as np
import pytest

from allaganeye.video.indicator_scan import (
    ScanChunk,
    merge_detections,
    plan_chunks,
    scan_detections,
)
from allaganeye.video.indicators import group_detections

INTERVAL = 0.1

#: 合成信号の窓。2 つ目と 3 つ目は **チャンク境界 (15s / 30s) を跨ぐ**。
WINDOWS = ((1.0, 1.4), (14.8, 15.2), (29.9, 30.3))

MARK_HIT = 15
MARK_IDLE = 0


def _synthetic_frame(timestamp: float) -> np.ndarray:
    """窓の中なら MARK_HIT、外なら MARK_IDLE の 2x2 フレーム。"""
    value = MARK_HIT if any(lo <= timestamp <= hi for lo, hi in WINDOWS) else MARK_IDLE
    return np.full((2, 2), value, dtype=np.uint8)


def _synthetic_detect(frame: np.ndarray) -> tuple[str | None, float]:
    if int(frame[0, 0]) == MARK_HIT:
        return "assist", 0.8
    return None, 0.0


def _sequential_reference(
    total: float, interval: float
) -> list[tuple[float, str | None, float]]:
    """並列化前の逐次走査 (0, interval, 2*interval, ... )。

    時刻は `iter_gray_frames` と同じくグリッド上の値に丸めてから判定する
    (丸めないと 14*0.1 = 1.4000000000000001 のように窓の端ちょうどを取り逃がす)。
    """
    count = int(np.ceil(total / interval))
    out: list[tuple[float, str | None, float]] = []
    for index in range(count):
        timestamp = round(index * interval, 6)
        out.append((timestamp, *_synthetic_detect(_synthetic_frame(timestamp))))
    return out


def _fake_frames(
    total: float,
    interval: float,
    *,
    log: list[ScanChunk] | None = None,
    stop: threading.Event | None = None,
    stop_after: int | None = None,
):
    """`iter_gray_frames` の代役。要求された区間のフレームを合成する。"""

    def factory(
        _video, *, fps, frame_size, start=0.0, duration=None, crop=None
    ) -> Iterator[tuple[float, np.ndarray]]:
        if log is not None:
            log.append(ScanChunk(start=start, duration=duration or 0.0))
        end = total if duration is None else min(start + duration, total)
        index = 0
        while True:
            if stop is not None and stop.is_set():
                return
            timestamp = round(start + index * interval, 6)
            if timestamp >= end - 1e-9:
                return
            yield timestamp, _synthetic_frame(timestamp)
            index += 1
            if stop_after is not None and index >= stop_after:
                if stop is not None:
                    stop.set()
                return

    return factory


# ---------------------------------------------------------------------------
# plan_chunks
# ---------------------------------------------------------------------------


def test_plan_chunks_covers_the_range_without_gaps_or_overlap() -> None:
    chunks = plan_chunks(total=100.0, interval=INTERVAL, workers=4)

    assert chunks[0].start == 0.0
    assert chunks[-1].start + chunks[-1].duration == pytest.approx(100.0)
    for left, right in pairwise(chunks):
        assert left.start + left.duration == pytest.approx(right.start)


def test_plan_chunks_aligns_boundaries_to_the_interval_grid() -> None:
    """境界がグリッドからずれると、チャンク間でフレームが重複 / 欠落する。"""
    chunks = plan_chunks(total=100.0, interval=INTERVAL, workers=4)

    for chunk in chunks:
        # 0.1 は二進小数で表せないので、商が整数に乗っているかで見る。
        assert chunk.start / INTERVAL == pytest.approx(round(chunk.start / INTERVAL))


def test_plan_chunks_does_not_split_short_videos() -> None:
    """短い動画はプロセス起動コストの方が高いので 1 チャンクにまとめる。"""
    assert len(plan_chunks(total=3.0, interval=INTERVAL, workers=8)) == 1


def test_plan_chunks_never_exceeds_the_worker_count() -> None:
    assert len(plan_chunks(total=10_000.0, interval=INTERVAL, workers=3)) <= 3


def test_plan_chunks_handles_non_multiple_durations() -> None:
    """総尺が interval の倍数でなくてもグリッドを崩さない。"""
    chunks = plan_chunks(total=100.03, interval=INTERVAL, workers=4)

    for chunk in chunks[:-1]:
        assert chunk.start / INTERVAL == pytest.approx(round(chunk.start / INTERVAL))
    assert chunks[-1].start + chunks[-1].duration == pytest.approx(100.03)


def test_plan_chunks_returns_nothing_for_an_empty_range() -> None:
    assert plan_chunks(total=0.0, interval=INTERVAL, workers=4) == []


# ---------------------------------------------------------------------------
# merge_detections
# ---------------------------------------------------------------------------


def test_merge_detections_sorts_by_timestamp() -> None:
    merged = merge_detections(
        [
            [(0.2, None, 0.0)],
            [(0.0, "ko", 0.9), (0.1, None, 0.0)],
        ]
    )

    assert [item[0] for item in merged] == [0.0, 0.1, 0.2]


def test_merge_detections_drops_duplicate_timestamps() -> None:
    """境界で同じ時刻が 2 回出ても 1 回に畳む (サンプル数を水増ししない)。"""
    merged = merge_detections(
        [
            [(0.1, "ko", 0.9)],
            [(0.1, "ko", 0.9), (0.2, None, 0.0)],
        ]
    )

    assert [item[0] for item in merged] == [0.1, 0.2]


# ---------------------------------------------------------------------------
# scan_detections
# ---------------------------------------------------------------------------


def test_scan_matches_the_sequential_scan_exactly() -> None:
    """並列走査の結果は逐次走査と完全一致する (順序・種類・スコア)。"""
    total = 60.0

    parallel = scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=total,
        frame_size=(1920, 1080),
        crop=None,
        workers=4,
        frames_factory=_fake_frames(total, INTERVAL),
        detect=_synthetic_detect,
    )

    assert parallel == _sequential_reference(total, INTERVAL)


def test_scan_groups_the_same_events_as_a_sequential_scan() -> None:
    """チャンク境界を跨ぐインジケータも 1 イベントにまとまる。"""
    total = 60.0
    max_gap = INTERVAL * 1.2

    parallel = scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=total,
        frame_size=(1920, 1080),
        crop=None,
        workers=4,
        frames_factory=_fake_frames(total, INTERVAL),
        detect=_synthetic_detect,
    )

    events = group_detections(parallel, max_gap=max_gap, min_samples=2)
    reference = group_detections(
        _sequential_reference(total, INTERVAL), max_gap=max_gap, min_samples=2
    )

    assert [(event.kind, event.start, event.end) for event in events] == [
        (event.kind, event.start, event.end) for event in reference
    ]
    assert len(events) == len(WINDOWS)


def test_scan_splits_work_across_chunks() -> None:
    seen: list[ScanChunk] = []
    scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=120.0,
        frame_size=(1920, 1080),
        crop=None,
        workers=4,
        frames_factory=_fake_frames(120.0, INTERVAL, log=seen),
        detect=_synthetic_detect,
    )

    assert len(seen) == 4


def test_scan_with_one_worker_is_a_single_chunk() -> None:
    seen: list[ScanChunk] = []
    scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=120.0,
        frame_size=(1920, 1080),
        crop=None,
        workers=1,
        frames_factory=_fake_frames(120.0, INTERVAL, log=seen),
        detect=_synthetic_detect,
    )

    assert len(seen) == 1


def test_scan_reports_progress_monotonically() -> None:
    processed: list[float] = []
    scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=120.0,
        frame_size=(1920, 1080),
        crop=None,
        workers=4,
        frames_factory=_fake_frames(120.0, INTERVAL),
        detect=_synthetic_detect,
        on_progress=processed.append,
        progress_step=10.0,
    )

    assert processed == sorted(processed)
    assert processed[-1] <= 120.0
    assert len(processed) >= 10


def test_scan_stops_when_the_stop_event_is_set() -> None:
    """停止要求後は新しいサンプルを積まない (キャンセルの初動)。"""
    stop = threading.Event()

    result = scan_detections(
        "unused.mp4",
        interval=INTERVAL,
        total=120.0,
        frame_size=(1920, 1080),
        crop=None,
        workers=1,
        frames_factory=_fake_frames(120.0, INTERVAL, stop=stop, stop_after=5),
        detect=_synthetic_detect,
        stop=stop,
    )

    assert len(result) == 5


def test_scan_propagates_detector_errors() -> None:
    """バンド不整合 (ValueError) を握り潰さない (#1106 の契約)。"""

    def boom(_frame: np.ndarray) -> tuple[str | None, float]:
        raise ValueError("テキストバンドがフレームに収まっていません")

    with pytest.raises(ValueError):
        scan_detections(
            "unused.mp4",
            interval=INTERVAL,
            total=120.0,
            frame_size=(1920, 1080),
            crop=None,
            workers=2,
            frames_factory=_fake_frames(120.0, INTERVAL),
            detect=boom,
        )


def test_a_failing_chunk_stops_the_siblings() -> None:
    """1 つのワーカーが落ちたら、他のチャンクの走査も止まる (codex P2)。

    `future.result()` を投入順に待つだけだと、後ろのチャンクが先に失敗しても
    前のチャンクの完了まで気づかない。長時間録画ではそれが数分の空走りになる。
    """
    produced = 0
    lock = threading.Lock()

    def factory(_video, *, fps, frame_size, start=0.0, duration=None, crop=None):
        """前半チャンクは IDLE、後半チャンク (start >= 100s) は HIT を出す。"""
        nonlocal produced
        mark = MARK_HIT if start >= 100.0 else MARK_IDLE
        index = 0
        while True:
            timestamp = round(start + index * INTERVAL, 6)
            if duration is not None and timestamp >= start + duration - 1e-9:
                return
            with lock:
                produced += 1
            time.sleep(0.001)  # 兄弟が先に走っている状況を作る
            yield timestamp, np.full((2, 2), mark, dtype=np.uint8)
            index += 1

    class Boom(Exception):
        pass

    def detect(frame: np.ndarray) -> tuple[str | None, float]:
        if int(frame[0, 0]) == MARK_HIT:
            raise Boom("second chunk failed")
        return None, 0.0

    with pytest.raises(Boom):
        scan_detections(
            "unused.mp4",
            interval=INTERVAL,
            total=200.0,
            frame_size=(1920, 1080),
            crop=None,
            workers=2,
            frames_factory=factory,
            detect=detect,
        )

    # 前半チャンク (1000 フレーム) を走り切っていれば、兄弟が止まっていない。
    assert produced < 600, f"sibling kept scanning: {produced} frames"
