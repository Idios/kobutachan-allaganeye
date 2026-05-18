"""Parallel match-export orchestrator (#761).

ThreadPoolExecutor で N worker を起動し、共有 queue から match を pull。
各 worker は run_export_attempt で 1 ffmpeg を起動。cancel_event は worker
に伝搬し、in-flight ffmpeg を kill する。See spec §4.4.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from queue import Empty, Queue

from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.ffmpeg_runner import run_export_attempt
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)


@dataclass(frozen=True)
class ExportMatch:
    """Single match to export. Mirrors metadata.json matches[] entry."""

    index: int
    start: float
    end: float
    type_label: str  # "match" / "non_fl" / etc. — used by name_pattern


def _format_filename(m: ExportMatch, pattern: str, codec: str) -> str:
    """Render the output filename per ``pattern``.

    Tokens: ``{idx}`` / ``{idx:03}`` / ``{type}`` / ``{start}`` / ``{date}``.
    Mirrors gui/src/screens/ExportScreen.tsx formatName().
    """
    start_disp = _format_start_for_filename(m.start)
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    out = pattern
    out = out.replace("{idx:03}", f"{m.index:03d}")
    out = out.replace("{idx}", str(m.index))
    out = out.replace("{type}", m.type_label)
    out = out.replace("{start}", start_disp)
    out = out.replace("{date}", today)
    return out


def _format_start_for_filename(seconds: float) -> str:
    """mm-ss form (`:` is invalid in Windows filenames)."""
    minutes = int(seconds // 60)
    rem = int(seconds % 60)
    return f"{minutes:02d}-{rem:02d}"


def export_matches(
    matches: list[ExportMatch],
    slots: list[EncoderSlot],
    *,
    source_video: Path,
    output_dir: Path,
    codec: str,
    name_pattern: str,
    progress_cb: Callable[[ProgressEvent], None],
    cancel_event: threading.Event | None = None,
) -> ExportSummary:
    """N workers (= len(slots)) で並列実行し、aggregated summary を返す.

    cancel_event:
        set されると worker は次の queue.get_nowait() で抜ける。in-flight な
        ffmpeg は run_export_attempt 内で kill される (ExportError(kind='cancelled'))。

    Codex review #3: summary.cancelled は ``cancel_event.is_set()`` 単独で
    判定する。``queue.qsize() > 0`` を AND してはいけない (全 dequeue 済の
    状態で cancel された場合に false negative)。
    """
    if not slots:
        raise ValueError("export_matches: slots is empty (need at least 1)")
    cancel_event = cancel_event or threading.Event()

    queue: Queue[ExportMatch] = Queue()
    for m in matches:
        queue.put(m)

    summary = ExportSummary()
    summary_lock = threading.Lock()
    cancelled_results: list[bool] = []  # any worker saw cancel

    def worker(slot: EncoderSlot) -> None:
        while not cancel_event.is_set():
            try:
                m = queue.get_nowait()
            except Empty:
                return

            def on_progress(percent: float, stage: str, _idx: int = m.index) -> None:
                progress_cb(ProgressEvent.progress(_idx, percent, stage))

            def on_fallback(
                src: H264Encoder, dst: H264Encoder, msg: str, _idx: int = m.index
            ) -> None:
                progress_cb(ProgressEvent.fallback(_idx, src.value, dst.value, msg))

            output_path = output_dir / _format_filename(m, name_pattern, codec)
            try:
                result = run_export_attempt(
                    video=source_video,
                    start=m.start,
                    end=m.end,
                    output=output_path,
                    codec=codec,
                    encoder=slot.encoder_kind,
                    progress_cb=on_progress,
                    fallback_cb=on_fallback,
                    cancel_event=cancel_event,
                )
                # match_index は ExportResult が caller 値で上書きされる
                result_with_idx = ExportResult(
                    match_index=m.index,
                    output_path=result.output_path,
                    duration_ms=result.duration_ms,
                    encoder_used=result.encoder_used,
                    fallback_from=result.fallback_from,
                )
                progress_cb(
                    ProgressEvent.result(
                        m.index,
                        result_with_idx.output_path,
                        result_with_idx.duration_ms,
                        result_with_idx.encoder_used,
                    )
                )
                with summary_lock:
                    summary.success += 1
            except ExportError as e:
                progress_cb(ProgressEvent.error(m.index, e))
                with summary_lock:
                    summary.failure += 1
                if e.kind == "cancelled":
                    cancelled_results.append(True)

    with ThreadPoolExecutor(
        max_workers=len(slots), thread_name_prefix="export-worker"
    ) as ex:
        futures = [ex.submit(worker, slot) for slot in slots]
        for f in futures:
            f.result()  # 例外伝搬 (workers の例外は内部で catch されるので通常 None)

    # Codex review #3: cancel 判定は cancel_event.is_set() 単独で
    summary.cancelled = cancel_event.is_set() or bool(cancelled_results)
    return summary
