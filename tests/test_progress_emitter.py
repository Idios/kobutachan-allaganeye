"""Tests for the JSON-lines progress emitter (#569).

The emitter is consumed by the Tauri GUI: it spawns ``allaganeye detect
--progress-format json`` and reads stdout line-by-line, parsing each
line as a stand-alone JSON object.  These tests pin the on-the-wire
shape so a regression in the writer surfaces here rather than as a
silent GUI desync.
"""

from __future__ import annotations

import io
import json

from allaganeye.detection.progress_emitter import (
    ProgressEmitter,
    disabled_emitter,
)


class _FakeClock:
    """Deterministic monotonic clock for elapsed_s assertions."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _read_lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_emit_writes_one_json_line_per_call():
    buf = io.StringIO()
    clock = _FakeClock()
    e = ProgressEmitter(enabled=True, stream=buf, clock=clock)

    clock.advance(1.5)
    e.emit("scan", completed=10, total=100)
    clock.advance(0.5)
    e.emit("scan", completed=20, total=100)

    lines = _read_lines(buf)
    assert len(lines) == 2
    assert lines[0] == {
        "phase": "scan",
        "completed": 10,
        "total": 100,
        "elapsed_s": 1.5,
    }
    assert lines[1] == {
        "phase": "scan",
        "completed": 20,
        "total": 100,
        "elapsed_s": 2.0,
    }


def test_emit_progress_attaches_completed_total():
    buf = io.StringIO()
    clock = _FakeClock()
    e = ProgressEmitter(enabled=True, stream=buf, clock=clock)

    e.emit_progress("refine", 1, 4, blackout_frames=0)

    [line] = _read_lines(buf)
    assert line["phase"] == "refine"
    assert line["completed"] == 1
    assert line["total"] == 4
    assert line["blackout_frames"] == 0
    assert "elapsed_s" in line


def test_disabled_emitter_writes_nothing():
    buf = io.StringIO()
    e = ProgressEmitter(enabled=False, stream=buf)

    e.emit("scan", completed=1, total=2)
    e.emit_progress("refine", 1, 2)

    assert buf.getvalue() == ""


def test_emit_drops_none_valued_extras():
    """None values should be dropped so the wire format stays compact.

    The CLI side passes ``None`` for optional context (e.g. eta_s when
    no estimate exists yet). The Rust parser treats absent keys as
    "unknown"; a literal ``null`` would force the parser to handle two
    cases.  Drop them at the source instead.
    """
    buf = io.StringIO()
    e = ProgressEmitter(enabled=True, stream=buf)

    e.emit("chunk", completed=1, total=4, eta_s=None)

    [line] = _read_lines(buf)
    assert "eta_s" not in line
    assert line["completed"] == 1
    assert line["total"] == 4


def test_emit_swallows_broken_pipe():
    """A broken-pipe write must not propagate up the call site.

    The detect pipeline is the source of truth for the metadata file --
    losing the GUI progress channel halfway through must not abort the
    detection itself.
    """

    class BrokenStream(io.StringIO):
        def write(self, _: str) -> int:  # type: ignore[override]
            raise BrokenPipeError("consumer hung up")

        def flush(self) -> None:
            return None

    e = ProgressEmitter(enabled=True, stream=BrokenStream())
    # Should not raise.
    e.emit("scan", completed=1, total=2)


def test_disabled_emitter_singleton_returns_disabled_instance():
    """The shared no-op emitter must short-circuit regardless of stream."""
    e = disabled_emitter()
    assert not e.enabled
    # Calling emit / emit_progress on the disabled singleton is harmless.
    e.emit("x")
    e.emit_progress("y", 1, 2)
