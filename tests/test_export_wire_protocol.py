"""End-to-end wire protocol test (#761, Codex review #5; CI-wired in #844 W5).

Spawns a real Python subprocess (``python -m allaganeye export --stdin --json``)
with a tiny ffmpeg-generated test video and ``--codec copy`` (no re-encode, so
no libx264 dependency) and asserts that:
  1. stdout is parseable ndjson
  2. event ordering is sane (progress* -> result | error -> summary terminal)
  3. each match_index produces a terminal result or error event
  4. summary line is the LAST line
  5. progress events carry real usable fields (percent in 0-100, stage non-empty)
  6. result events carry real payload fields (output_path, duration_ms) AND the
     referenced output file actually exists on disk and is non-empty
  7. summary carries all four fields (success, failure, skipped, cancelled)

Runs in CI (BtbN LGPL ffmpeg has no libx264, but copy/remux + mpeg4 fixture
need none). Skipped only when no ffmpeg binary is discoverable.

Wire schema (schema.py, copy-path specific):
  progress : {type, match_index, percent: float 0-100, stage: str}
  result   : {type, match_index, output_path: posix str, duration_ms: int,
              encoder_used: str}  -- encoder_used present on copy path too
  error    : {type, match_index, error_kind, error_message, error_hint}
  summary  : {type, success, failure, skipped, cancelled}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from allaganeye.ffmpeg_path import find_ffmpeg


@pytest.fixture(scope="module")
def short_test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a 6-second all-intra mpeg4 test video (LGPL-ffmpeg safe).

    mpeg4 + ``-g 1`` makes every frame a keyframe so ``-c copy`` can cut at any
    boundary. Skipped when no ffmpeg binary is available.
    """
    try:
        ffmpeg = find_ffmpeg()
    except Exception:
        pytest.skip("ffmpeg binary not available")
    out = tmp_path_factory.mktemp("export-wire") / "in.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=640x360:rate=30",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "mpeg4",
            "-g",
            "1",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def test_wire_protocol_end_to_end(short_test_video: Path, tmp_path: Path):
    """Run real subprocess + verify ndjson events."""
    metadata = {
        "source": str(short_test_video),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 2.0, "type": "match"},
            {"index": 1, "start_time": 2.0, "end_time": 4.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "allaganeye",
            "export",
            "--stdin",
            "--json",
            "--output-dir",
            str(output_dir),
            "--codec",
            "copy",
            "--name-pattern",
            "{idx:03}.mp4",
        ],
        input=json.dumps(metadata),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert proc.returncode == 0, f"export failed: stderr={proc.stderr}"

    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    events = [json.loads(ln) for ln in lines]

    # Last line is summary
    assert events[-1]["type"] == "summary"
    assert events[-1]["success"] == 2
    assert events[-1]["failure"] == 0

    # Every match_index has exactly 1 terminal (result | error)
    terminals_per_match: dict[int, int] = {}
    for ev in events:
        if ev["type"] in ("result", "error"):
            terminals_per_match[ev["match_index"]] = (
                terminals_per_match.get(ev["match_index"], 0) + 1
            )
    assert terminals_per_match == {0: 1, 1: 1}

    # progress events for each match_index appear before its terminal
    for idx in (0, 1):
        seq = [ev["type"] for ev in events if ev.get("match_index") == idx]
        assert "progress" in seq
        terminal_pos = seq.index("result") if "result" in seq else seq.index("error")
        # --codec copy never emits fallback (that is a GPU-encoder-failure event
        # only), so every pre-terminal event for a match is a progress event.
        assert all(s == "progress" for s in seq[:terminal_pos])

    # --- payload shape assertions (Codex finding #1 / W5 contract hardening) ---

    # progress events: percent is a float in [0, 100]; stage is a non-empty string.
    # Only the fields the emitter actually populates (schema.py ProgressEvent.progress).
    progress_events = [ev for ev in events if ev["type"] == "progress"]
    assert progress_events, "expected at least one progress event"
    for ev in progress_events:
        assert isinstance(ev["match_index"], int), f"progress.match_index not int: {ev}"
        pct = ev["percent"]
        assert isinstance(pct, (int, float)), f"progress.percent not numeric: {ev}"
        assert 0.0 <= float(pct) <= 100.0, f"progress.percent out of range: {ev}"
        stage = ev["stage"]
        assert isinstance(stage, str) and stage, f"progress.stage not a non-empty str: {ev}"

    # result events: real payload fields present and well-typed; output file exists
    # on disk and is non-empty.  encoder_used is present on the copy path too
    # (schema.py always populates it) but we assert str-type only (codec-independent).
    result_events = [ev for ev in events if ev["type"] == "result"]
    assert len(result_events) == 2, f"expected 2 result events, got {len(result_events)}"
    for ev in result_events:
        assert isinstance(ev["match_index"], int), f"result.match_index not int: {ev}"

        out_path_str = ev.get("output_path")
        assert isinstance(out_path_str, str) and out_path_str, (
            f"result.output_path missing or not a str: {ev}"
        )

        dur = ev.get("duration_ms")
        assert isinstance(dur, int), f"result.duration_ms not int: {ev}"
        assert dur >= 0, f"result.duration_ms negative: {ev}"

        enc = ev.get("encoder_used")
        assert isinstance(enc, str) and enc, f"result.encoder_used not a non-empty str: {ev}"

        # Key anti-false-green: the referenced output file must exist and be non-empty.
        out_file = Path(out_path_str)
        assert out_file.exists(), (
            f"result.output_path references a file that does not exist: {out_path_str}"
        )
        assert out_file.stat().st_size > 0, (
            f"result.output_path references an empty file: {out_path_str}"
        )

    # summary: all four fields present with correct types (skipped/cancelled added in schema.py).
    summary_ev = events[-1]
    assert isinstance(summary_ev["success"], int), "summary.success not int"
    assert isinstance(summary_ev["failure"], int), "summary.failure not int"
    assert "skipped" in summary_ev, "summary missing 'skipped' field"
    assert isinstance(summary_ev["skipped"], int), "summary.skipped not int"
    assert "cancelled" in summary_ev, "summary missing 'cancelled' field"
    assert isinstance(summary_ev["cancelled"], bool), "summary.cancelled not bool"
