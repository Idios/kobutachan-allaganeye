"""KO / ASSIST 走査のチャンク並列 (#1140)。

`allaganeye indicators` の照合は 1 コアで約 217 フレーム/秒で、2.8 時間の録画
(10 fps 走査で約 10 万フレーム) では 8 分近くかかっていた。ffmpeg のデコードは
27.5 倍速なので、ボトルネックは Python 側の照合であり、`detector.py` と同じく
**区間を N 分割してチャンクごとに ffmpeg 1 本** にすればコア数分だけ速くなる。

分割は `detector.py` との違いに注意:

* 走査は **0.1 秒の固定グリッド** に乗っているので、チャンク境界を interval の
  倍数に揃える。ずれると境界でフレームが重複 / 欠落し、`group_detections` の
  サンプル数が変わる (= 結果が逐次走査と一致しなくなる)。
* キャリブレーションは 1 回だけ (呼び出し側の責務)。ここは走査だけを受ける。
* チャンク境界を跨ぐインジケータは、マージ後の列をそのまま
  `group_detections` に渡せば 1 イベントにまとまる (max_gap が interval の
  1.2 倍なので境界の 1 フレーム分の隙間は吸収される)。
"""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from allaganeye.video.frames import iter_gray_frames

__all__ = [
    "MAX_SCAN_WORKERS",
    "MIN_CHUNK_SECONDS",
    "Detection",
    "ScanChunk",
    "merge_detections",
    "plan_chunks",
    "resolve_scan_workers",
    "scan_detections",
]

#: `(時刻, 種類 or None, スコア)`。`group_detections` の入力と同じ形。
Detection = tuple[float, str | None, float]

#: 1 チャンクの最小映像長 (秒)。ffmpeg の起動 + 入力シークのコストを照合の
#: 節約で回収できる下限。これ未満の録画は分割しない (分割しても速くならない)。
MIN_CHUNK_SECONDS = 20.0

#: 同時に走らせるワーカー数の上限。**ここが SSoT**。docs 側は「auto」と書き、
#: 数値を複製しない (`docs/coding-conventions.md` の doc SSoT 規約)。
#: 照合は numpy / OpenCV で GIL を解放するのでスレッドでスケールするが、
#: これ以上はメモリ帯域と ffmpeg のデコードで頭打ちになる。
MAX_SCAN_WORKERS = 8


def resolve_scan_workers() -> int:
    """`--workers` を取らないコマンドのワーカー数 (auto)。"""
    return max(1, min(os.cpu_count() or 4, MAX_SCAN_WORKERS))


@dataclass(frozen=True)
class ScanChunk:
    """1 ワーカーが担当する区間 (秒)。"""

    start: float
    duration: float


def plan_chunks(
    *,
    total: float,
    interval: float,
    workers: int,
    min_chunk_seconds: float = MIN_CHUNK_SECONDS,
) -> list[ScanChunk]:
    """走査区間 ``[0, total)`` を interval グリッドに揃ったチャンクへ分ける。"""
    if total <= 0:
        return []
    if interval <= 0:
        raise ValueError(f"interval must be positive, got {interval}")
    worker_cap = max(1, int(workers))
    samples = max(1, math.ceil(total / interval - 1e-9))
    # 「短すぎるチャンクを作らない」を優先して、ワーカー数を区間長で頭打ちにする。
    by_length = (
        max(1, int(total // min_chunk_seconds)) if min_chunk_seconds > 0 else samples
    )
    chunk_count = max(1, min(worker_cap, by_length, samples))
    chunk_samples = max(1, math.ceil(samples / chunk_count))

    chunks: list[ScanChunk] = []
    start_sample = 0
    while start_sample < samples:
        take = min(chunk_samples, samples - start_sample)
        start = round(start_sample * interval, 6)
        ends_at_range = start_sample + take >= samples
        end = total if ends_at_range else round((start_sample + take) * interval, 6)
        chunks.append(ScanChunk(start=start, duration=max(0.0, end - start)))
        start_sample += take
    return chunks


def merge_detections(parts: Iterable[Iterable[Detection]]) -> list[Detection]:
    """チャンクごとの検出列を時刻順に 1 本へまとめる。

    境界で同じ時刻が 2 回来た場合は **最初の 1 件だけ** を残す。重複を残すと
    `group_detections` の `samples` が水増しされ、`min_samples` の判定が
    境界の位置で変わってしまう。
    """
    merged: list[Detection] = []
    seen: set[float] = set()
    for part in parts:
        for timestamp, kind, score in part:
            key = round(timestamp, 6)
            if key in seen:
                continue
            seen.add(key)
            merged.append((key, kind, score))
    merged.sort(key=lambda item: item[0])
    return merged


def scan_detections(
    video: Path | str,
    *,
    interval: float,
    total: float,
    frame_size: tuple[int, int] | None,
    crop: tuple[int, int, int, int] | None,
    workers: int,
    detect: Callable[[np.ndarray], tuple[str | None, float]],
    frames_factory: Callable[
        ..., Iterator[tuple[float, np.ndarray]]
    ] = iter_gray_frames,
    on_progress: Callable[[float], None] | None = None,
    progress_step: float = 30.0,
    stop: threading.Event | None = None,
) -> list[Detection]:
    """`[0, total)` を並列走査して ``(時刻, 種類, スコア)`` の列を返す。

    ``detect`` は 1 フレームを受けて ``(種類 or None, スコア)`` を返す関数。
    ``frames_factory`` は ``iter_gray_frames`` 互換の呼び出し形で、テストが
    合成フレームを注入するための差し替え口でもある。

    ``on_progress`` には **走査済みの動画秒数** を渡す (チャンクが並列なので
    単調増加する累積値。残り時間は呼び出し側が実時間と突き合わせて出す)。
    停止要求 (``stop``) が立つと各ワーカーは次のフレームを取りに行かず、
    走査中の ffmpeg はジェネレータの close で kill される。
    """
    chunks = plan_chunks(total=total, interval=interval, workers=workers)
    if not chunks:
        return []
    halt = stop if stop is not None else threading.Event()
    results: list[list[Detection]] = [[] for _ in chunks]
    progress_lock = threading.Lock()
    processed = 0.0
    next_progress = progress_step

    def run(index: int, chunk: ScanChunk) -> None:
        nonlocal processed, next_progress
        frames = frames_factory(
            video,
            fps=1.0 / interval,
            frame_size=frame_size,
            start=chunk.start,
            duration=chunk.duration,
            crop=crop,
        )
        collected: list[Detection] = []
        try:
            for timestamp, frame in frames:
                if halt.is_set():
                    break
                kind, score = detect(frame)
                collected.append((timestamp, kind, score))
                with progress_lock:
                    processed += interval
                    if on_progress is not None and processed >= next_progress:
                        on_progress(min(processed, total))
                        next_progress += progress_step
        finally:
            # 早期終了 / 例外でも ffmpeg を確実に止める (generator の finally)。
            close = getattr(frames, "close", None)
            if close is not None:
                close()
        results[index] = collected

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = [pool.submit(run, index, chunk) for index, chunk in enumerate(chunks)]
        try:
            for future in futures:
                future.result()
        except BaseException:
            halt.set()
            for future in futures:
                future.cancel()
            raise
    return merge_detections(results)
