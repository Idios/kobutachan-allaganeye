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


def test_export_matches_runs_n_workers_in_parallel(tmp_path: Path):
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


def test_export_matches_cancel_stops_remaining(tmp_path: Path):
    """cancel_event set → workers stop pulling. summary.cancelled = True."""
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
    # 全 20 件 finish しないこと (cancel で打ち切り)
    assert summary.success + summary.failure < 20


def test_export_matches_cancel_marks_true_even_with_empty_queue(tmp_path: Path):
    """Codex review #3: queue.qsize() > 0 条件を残すと、cancel 直後に queue が
    たまたま空になった瞬間 cancelled=False になる。これは BUG なので NG."""
    cancel = threading.Event()
    lock = threading.Lock()
    n_done = 0

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal n_done
        with lock:
            n_done += 1
            if n_done == 3:
                # 全 match 終了直後に cancel set
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
    # 全 3 件 success だが、cancel_event は set されているので cancelled=True
    assert summary.success == 3
    assert summary.cancelled is True


def test_export_matches_partial_failure_other_workers_continue(tmp_path: Path):
    """1 worker が failure を返しても他は続行する."""

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


def test_export_matches_empty_queue_returns_zero_summary(tmp_path: Path):
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


def test_export_matches_empty_slots_raises(tmp_path: Path):
    """0 slot は実行不能 → ValueError (caller の bug)."""
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
