"""Tests for parallel export pool (#761).

Mocks run_export_attempt to focus on concurrency / cancel / partial
failure semantics. Codex review #3 enforces cancel-without-queue-size
condition.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.pool import ExportMatch, export_matches
from allaganeye.export.schema import ExportError, ExportResult


def _slots(n: int) -> list[EncoderSlot]:
    return [
        EncoderSlot(
            slot_index=i, encoder_kind=H264Encoder.LIBX264, display_label=f"libx264#{i}"
        )
        for i in range(n)
    ]


def _matches(n: int) -> list[ExportMatch]:
    return [
        ExportMatch(
            index=i, start=float(i * 10), end=float((i + 1) * 10), type_label="match"
        )
        for i in range(n)
    ]


def test_runs_n_workers_in_parallel(tmp_path: Path):
    """concurrency = len(slots): max in-flight workers = N."""
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / f"out_{kwargs.get('start', 0)}.mp4",
            duration_ms=50,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(10),
            slots=_slots(3),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 10
    assert summary.failure == 0
    assert max_in_flight == 3  # never exceed slot count


def test_cancel_stops_remaining(tmp_path: Path):
    """cancel_event set -> workers stop pulling. summary.cancelled = True."""
    cancel = threading.Event()
    started = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                cancel.set()
        time.sleep(0.02)
        if cancel.is_set():
            raise ExportError(kind="cancelled", message="user")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=20,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(20),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    assert summary.cancelled is True
    # All 20 matches must not all finish (cancelled mid-run)
    assert summary.success + summary.failure < 20


def test_cancel_marks_true_even_with_empty_queue(tmp_path: Path):
    """Codex review #3: when cancel_event fires after all items dequeued,
    queue.qsize() AND condition would yield cancelled=False (incorrect).
    Single cancel_event.is_set() check correctly reports cancelled=True."""
    cancel = threading.Event()
    lock = threading.Lock()
    n_done = 0

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal n_done
        with lock:
            n_done += 1
            if n_done == 3:
                # set cancel immediately after all matches complete
                cancel.set()
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(3),
            slots=_slots(1),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    # All 3 succeed, but cancel_event is set so cancelled=True
    assert summary.success == 3
    assert summary.cancelled is True


def test_partial_failure_other_workers_continue(tmp_path: Path):
    """Other workers continue even when 1 worker returns a failure."""

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        if kwargs.get("start") == 10.0:  # match index 1
            raise ExportError(kind="ffmpeg.exit_failed", message="boom")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(5),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 4
    assert summary.failure == 1
    assert summary.cancelled is False


def test_empty_queue_returns_zero_summary(tmp_path: Path):
    summary = export_matches(
        matches=[],
        slots=_slots(3),
        source_video=tmp_path / "in.mp4",
        output_dir=tmp_path,
        codec="h264",
        name_pattern="{idx:03}.mp4",
        progress_cb=lambda ev: None,
        cancel_event=threading.Event(),
    )
    assert summary.success == 0
    assert summary.failure == 0
    assert summary.cancelled is False


def test_empty_slots_raises(tmp_path: Path):
    """0 slots is not executable -> ValueError (caller bug)."""
    with pytest.raises(ValueError):
        export_matches(
            matches=_matches(1),
            slots=[],
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
