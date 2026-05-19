"""Audit prepare: generate pre-screen worksheet for v0.3.0 baseline audit (#796).

Reads `tests/baselines/v0.3.0/<label>.metadata.json`, extracts match / gap
boundary timestamps, and emits a CSV worksheet + per-boundary brightness CSV
+ sample frame PNGs. Idios uses the worksheet to verify each boundary against
the source video and produces `tests/baselines/v0.3.0/ground-truth/<label>.json`.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.1
"""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _format_timestamp(timestamp_sec: float) -> str:
    """Format seconds as HH:MM:SS.fff (e.g., 2178.75 -> '00:36:18.750')."""
    hours = int(timestamp_sec // 3600)
    remaining = timestamp_sec - hours * 3600
    minutes = int(remaining // 60)
    seconds = remaining - minutes * 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def build_worksheet_rows(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract boundary timestamps from metadata.json into worksheet rows.

    Each match contributes 2 rows (start, end). Each gap contributes 2 rows
    (gap_start, gap_end). Rows preserve the metadata.json ordering.
    """
    rows: list[dict[str, Any]] = []
    matches = metadata.get("matches", [])
    gaps = metadata.get("gaps", [])

    for match in matches:
        for kind, key in (("match_start", "start_time"), ("match_end", "end_time")):
            ts = float(match[key])
            rows.append(
                {
                    "index": match.get("index"),
                    "boundary_type": kind,
                    "timestamp_sec": ts,
                    "timestamp_display": _format_timestamp(ts),
                    "current_type": match.get("type", "unknown"),
                    "brightness_csv_ref": f"brightness-around-{ts:.3f}.csv",
                    "sample_frame_png_ref": f"frame-around-{ts:.3f}.png",
                    "idios_verdict": "",
                    "idios_note": "",
                }
            )

    for gap in gaps:
        for kind, key in (("gap_start", "start_time"), ("gap_end", "end_time")):
            ts = float(gap[key])
            rows.append(
                {
                    "index": None,
                    "boundary_type": kind,
                    "timestamp_sec": ts,
                    "timestamp_display": _format_timestamp(ts),
                    "current_type": "gap",
                    "brightness_csv_ref": f"brightness-around-{ts:.3f}.csv",
                    "sample_frame_png_ref": f"frame-around-{ts:.3f}.png",
                    "idios_verdict": "",
                    "idios_note": "",
                }
            )

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.parse_args(argv)
    print("Not yet implemented: full pipeline (Task 3-5).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
