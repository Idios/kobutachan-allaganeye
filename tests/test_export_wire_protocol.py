"""End-to-end wire protocol test (#761, Codex review #5).

Spawns a real Python subprocess (``python -m allaganeye export --stdin --json``)
with a libx264 codec + tiny test video and asserts that:
  1. stdout is parseable ndjson
  2. event ordering is sane (progress* -> result | error -> summary terminal)
  3. each match_index produces a terminal result or error event
  4. summary line is the LAST line

Skipped when ALLAGANEYE_SAMPLE_VIDEO_DIR / test video is unavailable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def short_test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a 6-second test video with ffmpeg (no external deps)."""
    out = tmp_path_factory.mktemp("export-wire") / "in.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=6:size=640x360:rate=30",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "30",
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
            "h264",
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
        assert all(s == "progress" or s == "fallback" for s in seq[:terminal_pos])


def test_wire_protocol_cancel_via_sigint(short_test_video: Path, tmp_path: Path):
    """SIGINT mid-export -> summary.cancelled = True, exit 130."""
    if os.name == "nt":
        pytest.skip(
            "SIGINT test requires POSIX signal semantics; Windows uses GenerateConsoleCtrlEvent"
        )
    metadata = {
        "source": str(short_test_video),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 6.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    proc = subprocess.Popen(
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
            "h264",
            "--name-pattern",
            "{idx:03}.mp4",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(metadata))
    proc.stdin.close()
    import signal
    import time

    time.sleep(0.5)  # let export start
    proc.send_signal(signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 130, (
        f"expected exit 130 (SIGINT), got {proc.returncode}; stderr={stderr}"
    )
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    last = json.loads(lines[-1])
    assert last["type"] == "summary"
    assert last["cancelled"] is True
