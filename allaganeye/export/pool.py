"""Parallel match-export orchestrator (#761).

Starts N workers via ThreadPoolExecutor; each worker pulls matches from a
shared queue and launches one ffmpeg via run_export_attempt. cancel_event
propagates to workers and kills in-flight ffmpeg processes. See spec section 4.4.
"""

from __future__ import annotations

import math
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
    type_label: str  # "match" / "non_fl" / etc. -- used by name_pattern
    video_filter: str | None = (
        None  # #481: optional ffmpeg -vf filter string (minimap crop etc.)
    )


def _format_filename(m: ExportMatch, pattern: str) -> str:
    """Render the output filename per ``pattern``.

    Tokens: ``{idx}`` / ``{idx:03}`` / ``{type}`` / ``{start}`` / ``{date}``.
    Mirrors gui/src/utils/filename.ts ``formatMatchFilename`` (#932).
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
    """H-MM-SS / MM-SS form (`:` is invalid in Windows filenames).

    Mirrors gui/src/utils/filename.ts ``formatStartForFilename`` so the GUI
    preview and the CLI's actual output agree past the 1-hour mark
    (audit P2-20). Non-finite / negative inputs clamp to 0.
    """
    if not math.isfinite(seconds) or seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}-{m:02d}-{s:02d}"
    return f"{m:02d}-{s:02d}"


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
    """Run N workers (= len(slots)) in parallel and return an aggregated summary.

    cancel_event:
        When set, workers exit on the next queue.get_nowait(). In-flight
        ffmpeg processes are killed inside run_export_attempt
        (ExportError(kind='cancelled')).

    Codex review #3: summary.cancelled is determined solely by
    ``cancel_event.is_set()``. Do NOT AND with ``queue.qsize() > 0`` -- that
    would produce a false negative if cancel fires after all items are dequeued.
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

            output_path = output_dir / _format_filename(m, name_pattern)
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
                    video_filter=m.video_filter,
                )
                # match_index is overwritten by the caller value in ExportResult
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
            f.result()  # propagate exceptions (workers catch internally, so normally None)

    # Codex review #3: cancel check uses cancel_event.is_set() alone
    summary.cancelled = cancel_event.is_set() or bool(cancelled_results)
    return summary
