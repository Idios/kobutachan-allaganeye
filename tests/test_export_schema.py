"""Tests for export wire-protocol schema (#761)."""

from __future__ import annotations

import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from allaganeye.export.schema import (
    ExportError,
    ExportResult,  # noqa: F401  # imported to verify public API is importable
    ExportSummary,
    ProgressEvent,
)


def test_progress_event_progress_serializes_to_ndjson_line():
    ev = ProgressEvent.progress(match_index=0, percent=12.5, stage="encoding")
    line = ev.to_json_line()
    parsed = json.loads(line)
    assert parsed == {
        "type": "progress",
        "match_index": 0,
        "percent": 12.5,
        "stage": "encoding",
    }
    assert line.endswith("\n")


def test_progress_event_fallback_serializes():
    ev = ProgressEvent.fallback(
        match_index=2,
        fallback_from="h264_nvenc",
        fallback_to="libx264",
        message="NVENC init failed",
    )
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "fallback"
    assert parsed["fallback_from"] == "h264_nvenc"
    assert parsed["fallback_to"] == "libx264"


def test_progress_event_result_includes_output_path_and_encoder():
    absolute = Path(os.path.abspath("/tmp/match_001.mp4"))  # noqa: S108
    ev = ProgressEvent.result(
        match_index=1,
        output_path=absolute,
        duration_ms=12345,
        encoder_used="h264_nvenc",
    )
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "result"
    assert parsed["output_path"] == absolute.as_posix()
    assert parsed["duration_ms"] == 12345
    assert parsed["encoder_used"] == "h264_nvenc"


def test_progress_event_result_reports_absolute_path(tmp_path, monkeypatch):
    """A relative -o must still tell the user where the file actually landed.

    Reporting the path as given hides the destination whenever ``-o`` is
    relative -- including the Windows drive-relative form (``E:out``) that a
    lost shell quote turns ``E:\\a\\b`` into. Passing that through unchanged
    names a location the reader cannot act on.
    """
    monkeypatch.chdir(tmp_path)
    ev = ProgressEvent.result(
        match_index=2,
        output_path=Path("out") / "match_002.mp4",
        duration_ms=1,
        encoder_used="h264_nvenc",
    )
    reported = json.loads(ev.to_json_line())["output_path"]
    assert Path(reported).is_absolute(), reported
    expected = (Path(os.path.abspath(tmp_path)) / "out" / "match_002.mp4").as_posix()
    assert reported == expected


def test_progress_event_error_includes_hint():
    err = ExportError(
        kind="ffmpeg.exit_failed", message="exit 1", hint="see stderr tail"
    )
    ev = ProgressEvent.error(match_index=3, error=err)
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "error"
    assert parsed["error_kind"] == "ffmpeg.exit_failed"
    assert parsed["error_message"] == "exit 1"
    assert parsed["error_hint"] == "see stderr tail"


def test_progress_event_error_hint_none():
    err = ExportError(kind="cancelled", message="user requested")
    ev = ProgressEvent.error(match_index=0, error=err)
    parsed = json.loads(ev.to_json_line())
    assert parsed["error_hint"] is None


def test_export_summary_to_json_line():
    summary = ExportSummary(success=2, failure=1, skipped=0, cancelled=False)
    ev = ProgressEvent.summary(summary)
    parsed = json.loads(ev.to_json_line())
    assert parsed == {
        "type": "summary",
        "success": 2,
        "failure": 1,
        "skipped": 0,
        "cancelled": False,
    }


# --- WireWriter (Codex review #4 writer lock) ---


def test_wire_writer_serializes_single_event():
    from allaganeye.export.wire import WireWriter

    sink = io.StringIO()
    w = WireWriter(stream=sink)
    w.emit(ProgressEvent.progress(0, 25.0, "encoding"))
    lines = sink.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "progress"


def test_wire_writer_concurrent_writes_atomic():
    """Codex review #4: 複数 thread が同時 emit しても改行までの atomic 性が保たれる."""
    from allaganeye.export.wire import WireWriter

    sink = io.StringIO()
    w = WireWriter(stream=sink)

    def worker(idx: int):
        for p in range(100):
            w.emit(ProgressEvent.progress(idx, float(p), "encoding"))

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(worker, i) for i in range(4)]
        for f in futures:
            f.result()

    lines = sink.getvalue().splitlines()
    assert len(lines) == 400  # 4 workers x 100 events
    # Each line must be valid JSON (interleaved bytes would break parse)
    for line in lines:
        parsed = json.loads(line)
        assert parsed["type"] == "progress"


def test_progress_event_proposal_with_region():
    from allaganeye.export.schema import ProgressEvent

    ev = ProgressEvent.proposal(
        match_index=2,
        region={"x": 10, "y": 20, "w": 300, "h": 400},
        confidence=0.87,
        scattered=False,
    )
    import json

    payload = json.loads(ev.to_json_line())
    assert payload["type"] == "proposal"
    assert payload["match_index"] == 2
    assert payload["region"] == {"x": 10, "y": 20, "w": 300, "h": 400}
    assert payload["confidence"] == 0.87
    assert payload["scattered"] is False


def test_progress_event_proposal_none_region():
    from allaganeye.export.schema import ProgressEvent
    import json

    ev = ProgressEvent.proposal(
        match_index=3, region=None, confidence=0.0, scattered=False
    )
    assert json.loads(ev.to_json_line())["region"] is None


def test_wire_writer_flush_called_per_emit(monkeypatch: pytest.MonkeyPatch):
    """Flush is called on each emit so subprocess buffer reaches GUI without delay."""
    from allaganeye.export.wire import WireWriter

    flush_count = 0

    class FlushTracker(io.StringIO):
        def flush(self) -> None:
            nonlocal flush_count
            flush_count += 1

    sink = FlushTracker()
    w = WireWriter(stream=sink)
    w.emit(ProgressEvent.progress(0, 10.0, "encoding"))
    w.emit(ProgressEvent.progress(0, 20.0, "encoding"))
    assert flush_count == 2
