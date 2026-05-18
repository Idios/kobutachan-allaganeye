"""Tests for export wire-protocol schema (#761)."""

from __future__ import annotations

import json
from pathlib import Path

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
    ev = ProgressEvent.result(
        match_index=1,
        output_path=Path("/tmp/match_001.mp4"),  # noqa: S108
        duration_ms=12345,
        encoder_used="h264_nvenc",
    )
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "result"
    assert parsed["output_path"] == "/tmp/match_001.mp4"  # noqa: S108
    assert parsed["duration_ms"] == 12345
    assert parsed["encoder_used"] == "h264_nvenc"


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
