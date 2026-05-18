"""Thread-safe stdout JSON Lines emitter (#761).

Codex review #4: when multiple ThreadPoolExecutor workers call
``sys.stdout.write`` directly, CPython's GIL guarantees atomicity of
``json.dumps`` alone, but the full sequence
``write(json_str)`` -> ``write("\\n")`` -> ``flush()`` can interleave
(observed in practice: newlines mixed with prior events). This class uses
``threading.Lock`` to guarantee one-line-emit atomicity.
"""

from __future__ import annotations

import sys
import threading
from typing import IO

from allaganeye.export.schema import ProgressEvent


class WireWriter:
    """Serialize ProgressEvent emission to a single output stream."""

    def __init__(self, *, stream: IO[str] | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    def emit(self, event: ProgressEvent) -> None:
        """Write one ndjson line and flush. Thread-safe."""
        line = event.to_json_line()
        with self._lock:
            self._stream.write(line)
            self._stream.flush()
