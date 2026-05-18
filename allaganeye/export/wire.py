"""Thread-safe stdout JSON Lines emitter (#761).

Codex review #4: 複数 ThreadPoolExecutor worker が直接 ``sys.stdout.write`` を
呼ぶと、CPython の GIL は ``json.dumps`` 単独の atomic 性を保証するが、
``write(json_str)`` → ``write("\\n")`` → ``flush()`` のシーケンス全体が
interleave 可能 (実測で改行が前イベントと混在する事例あり)。本クラスは
``threading.Lock`` で 1 line emit の atomic 性を保証する。
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
