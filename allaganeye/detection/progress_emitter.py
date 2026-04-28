"""JSON-lines progress emitter for the GUI (Tauri) wrapper (#569).

Background
----------
The Tauri GUI spawns ``allaganeye detect`` and needs phase + percent +
elapsed updates while the subprocess runs.  The CLI's normal verbose
output is rendered for a TTY (click progressbars + free-form ``typer.echo``
lines) and is brittle to parse from Rust.

This module emits a stream of one JSON object per line on a writable
stream (``sys.stdout`` by default) when explicitly enabled via
``--progress-format json``.  The Rust side reads ``BufReader::new(stdout).lines()``
and parses each line individually; partial / non-JSON lines are ignored
so a future stray ``print`` won't break parsing.

Schema (each line = one JSON object)
------------------------------------
``{"phase": str, "completed": int?, "total": int?, "elapsed_s": float, ...}``

Phases
~~~~~~
- ``"start"``                  emitted once when detect begins (no completed/total)
- ``"probing"``                ffprobe complete, before Pass 1 (no completed/total)
- ``"scan"``                   Pass 1 frame-brightness sampling
- ``"refine"``                 Pass 2 fine-grained probing
- ``"scorebar"``               scorebar classification
- ``"audio"``                  audio Fanfare scan (when --no-audio is off)
- ``"writing_metadata"``       just before metadata.json is written
- ``"done"``                   final, includes ``metadata_path`` field
- ``"error"``                  fatal failure, includes ``message`` field

Design notes
------------
* A *disabled* emitter is a no-op so call sites can drop the ``if`` check.
* ``flush`` is forced after every line: ffmpeg-style buffering would make
  the GUI's progress bar feel laggy.
* The class never raises -- a write failure (broken pipe, etc.) is
  swallowed silently because the subprocess has bigger problems than
  reporting them on the broken pipe.
"""

from __future__ import annotations

import json
import sys
import time
from typing import IO, Any


class ProgressEmitter:
    """Stream JSON-lines progress events to *stream*.

    Constructed once at the start of a detect run and threaded through
    the detection callbacks.  When *enabled* is False the public
    ``emit*`` methods return immediately and produce no output.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        stream: IO[str] | None = None,
        clock: Any = None,
    ) -> None:
        self.enabled = enabled
        self._stream = stream if stream is not None else sys.stdout
        self._clock = clock if clock is not None else time.monotonic
        self._start = self._clock()

    @property
    def elapsed_s(self) -> float:
        """Wall-clock seconds since emitter was constructed."""
        return self._clock() - self._start

    def emit(self, phase: str, **fields: Any) -> None:
        """Emit one JSON line with *phase* + *fields* + ``elapsed_s``.

        Unknown extra fields are passed through unchanged so callers can
        attach optional context (e.g. ``message`` for errors,
        ``metadata_path`` for the terminal ``done``).  Disabled emitters
        are a no-op.
        """
        if not self.enabled:
            return
        payload: dict[str, Any] = {"phase": phase}
        for k, v in fields.items():
            if v is None:
                continue
            payload[k] = v
        payload["elapsed_s"] = round(self.elapsed_s, 3)
        line = json.dumps(payload, ensure_ascii=False)
        try:
            self._stream.write(line + "\n")
            self._stream.flush()
        except (OSError, ValueError):
            # Broken pipe / closed stream -- the consumer is gone, nothing
            # actionable from inside detect. Don't propagate so the detect
            # itself still runs to completion.
            pass

    def emit_progress(
        self,
        phase: str,
        completed: int,
        total: int,
        **fields: Any,
    ) -> None:
        """Convenience wrapper for the most common ``(completed, total)`` shape.

        ``percent`` is *not* pre-computed so the consumer can render a
        rate-aware bar; total may be 0 for indeterminate phases (the GUI
        treats 0 as "spinner only").
        """
        self.emit(phase, completed=completed, total=total, **fields)


_DISABLED = ProgressEmitter(enabled=False)


def disabled_emitter() -> ProgressEmitter:
    """Return a process-wide singleton no-op emitter.

    Useful as a default argument so call sites don't have to special-case
    ``None`` checks (mirrors ``logging.NullHandler``).
    """
    return _DISABLED
