"""Wire-protocol dataclasses for stdout JSON Lines (#761).

The CLI ``allaganeye export --json`` and the GUI subprocess emit one
JSON object per line on stdout. Rust ``start_export`` parses each line
into ``ExportProgress`` Tauri events. See spec section 5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExportResult:
    """Successful per-match export outcome."""

    match_index: int
    output_path: Path
    duration_ms: int
    encoder_used: str
    fallback_from: str | None = None  # set when libx264 retry kicked in


class ExportError(Exception):
    """Per-match export failure with optional corrective hint."""

    def __init__(self, kind: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.hint = hint


@dataclass
class ExportSummary:
    """Terminal aggregate emitted as the last JSON line."""

    success: int = 0
    failure: int = 0
    skipped: int = 0
    cancelled: bool = False


@dataclass(frozen=True)
class ProgressEvent:
    """One JSON line emitted on stdout (--json mode)."""

    payload: dict[str, Any]

    def to_json_line(self) -> str:
        """Serialize to a single ndjson line (terminated with ``\\n``)."""
        return json.dumps(self.payload, ensure_ascii=False) + "\n"

    @classmethod
    def progress(cls, match_index: int, percent: float, stage: str) -> ProgressEvent:
        return cls(
            {
                "type": "progress",
                "match_index": match_index,
                "percent": percent,
                "stage": stage,
            }
        )

    @classmethod
    def fallback(
        cls,
        match_index: int,
        fallback_from: str,
        fallback_to: str,
        message: str,
    ) -> ProgressEvent:
        return cls(
            {
                "type": "fallback",
                "match_index": match_index,
                "fallback_from": fallback_from,
                "fallback_to": fallback_to,
                "message": message,
            }
        )

    @classmethod
    def result(
        cls,
        match_index: int,
        output_path: Path,
        duration_ms: int,
        encoder_used: str,
    ) -> ProgressEvent:
        return cls(
            {
                "type": "result",
                "match_index": match_index,
                "output_path": output_path.as_posix(),
                "duration_ms": duration_ms,
                "encoder_used": encoder_used,
            }
        )

    @classmethod
    def error(cls, match_index: int, error: ExportError) -> ProgressEvent:
        return cls(
            {
                "type": "error",
                "match_index": match_index,
                "error_kind": error.kind,
                "error_message": error.message,
                "error_hint": error.hint,
            }
        )

    @classmethod
    def summary(cls, summary: ExportSummary) -> ProgressEvent:
        return cls(
            {
                "type": "summary",
                "success": summary.success,
                "failure": summary.failure,
                "skipped": summary.skipped,
                "cancelled": summary.cancelled,
            }
        )

    @classmethod
    def proposal(
        cls,
        match_index: int,
        region: dict[str, int] | None,
        confidence: float,
        scattered: bool,
    ) -> ProgressEvent:
        return cls(
            {
                "type": "proposal",
                "match_index": match_index,
                "region": region,
                "confidence": confidence,
                "scattered": scattered,
            }
        )
