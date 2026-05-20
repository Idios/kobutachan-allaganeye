"""Audit prepare: generate pre-screen worksheet for v0.3.0 baseline audit (#796).

Reads `tests/baselines/v0.3.0/<label>.metadata.json`, extracts match / gap
boundary timestamps, and emits a CSV worksheet + per-boundary brightness CSV
+ sample frame PNGs. Idios uses the worksheet to verify each boundary against
the source video and produces `tests/baselines/v0.3.0/ground-truth/<label>.json`.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.1
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Make `allaganeye` importable when this script is run directly via
# `python scripts/audit-prepare.py ...` from the project root (sys.path[0]
# is `scripts/` in that case, not the project root).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2  # type: ignore[import-untyped]  # noqa: E402
import numpy as np  # noqa: E402

from allaganeye.exceptions import VideoProcessingError  # noqa: E402
from allaganeye.video.detector import (  # noqa: E402
    _SAMPLE_WIDTH,
    _probe_frame_rgb,
    _probe_single_frame,
    _resolve_workers,
)

_DEFAULT_BASELINE_DIR = Path("tests/baselines/v0.3.0")
_DEFAULT_WORKSHEET_DIR = Path("tests/baselines/v0.3.0/audit-worksheet")

_WORKSHEET_FIELDS = [
    "index",
    "boundary_type",
    "timestamp_sec",
    "timestamp_display",
    "current_type",
    "brightness_csv_ref",
    "sample_frame_png_ref",
    "idios_verdict",
    "idios_note",
]


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


def resolve_video_path(source_relative: str) -> Path:
    """Resolve metadata.json `source` field to an absolute video path.

    Uses ``ALLAGANEYE_SAMPLE_VIDEO_DIR`` env var as the base directory.
    """
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not base:
        raise OSError(
            "ALLAGANEYE_SAMPLE_VIDEO_DIR is not set. Point it to the directory "
            "containing the recording subdirs (see CLAUDE.md §動画サンプルデータ)."
        )
    candidate = Path(base) / source_relative
    if not candidate.exists():
        raise FileNotFoundError(
            f"Video not found: {candidate} (resolved from "
            f"ALLAGANEYE_SAMPLE_VIDEO_DIR={base!r} + source={source_relative!r})"
        )
    return candidate


def export_brightness_csv(
    *,
    video_path: Path,
    boundary_timestamp: float,
    out_path: Path,
    window_sec: float = 5.0,
    interval_sec: float = 0.25,
    workers: int | None = None,
) -> None:
    """Probe brightness in [boundary - window, boundary + window] at interval_sec.

    Writes CSV with header ``timestamp,brightness``. Probe failures are
    recorded as 255.0 (same convention as ``_probe_single_frame``).
    """
    start = max(boundary_timestamp - window_sec, 0.0)
    end = boundary_timestamp + window_sec
    timestamps: list[float] = []
    t = start
    while t <= end + 1e-6:
        timestamps.append(round(t, 3))
        t += interval_sec

    max_workers = _resolve_workers(workers)
    results: dict[float, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, ts): ts for ts in timestamps
        }
        for future in as_completed(futures):
            ts = futures[future]
            try:
                results[ts] = future.result()
            except VideoProcessingError:
                results[ts] = 255.0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write("timestamp,brightness\n")
        for ts in sorted(results):
            f.write(f"{ts:.3f},{results[ts]:.1f}\n")


def export_sample_frames(
    *,
    video_path: Path,
    boundary_timestamp: float,
    out_dir: Path,
    height: int = 180,
) -> None:
    """Export 3 sample frames at boundary - 1s / boundary / boundary + 1s as PNG."""
    offsets = (-1.0, 0.0, 1.0)
    out_dir.mkdir(parents=True, exist_ok=True)

    for offset in offsets:
        ts = max(boundary_timestamp + offset, 0.0)
        try:
            raw = _probe_frame_rgb(video_path, ts, height=height)
        except Exception:
            raw = None
        if raw is None:
            continue
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, _SAMPLE_WIDTH, 3)
        out_path = out_dir / f"frame-around-{ts:07.3f}.png"
        cv2.imwrite(str(out_path), frame[:, :, ::-1])  # RGB -> BGR for cv2


def write_worksheet_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_WORKSHEET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in _WORKSHEET_FIELDS})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=_DEFAULT_BASELINE_DIR,
        help=f"Default: {_DEFAULT_BASELINE_DIR}",
    )
    parser.add_argument(
        "--worksheet-dir",
        type=Path,
        default=_DEFAULT_WORKSHEET_DIR,
        help=f"Default: {_DEFAULT_WORKSHEET_DIR}",
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=5.0,
        help="brightness window (default 5.0)",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=0.25,
        help="brightness sample interval (default 0.25)",
    )
    args = parser.parse_args(argv)

    metadata_path = args.baseline_dir / f"{args.recording_label}.metadata.json"
    if not metadata_path.exists():
        print(f"ERROR: {metadata_path} not found", file=sys.stderr)
        return 2

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rows = build_worksheet_rows(metadata)

    video_path = resolve_video_path(metadata["source"])

    worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
    write_worksheet_csv(rows, worksheet_csv)

    per_boundary_dir = args.worksheet_dir / args.recording_label
    for row in rows:
        ts = float(row["timestamp_sec"])
        export_brightness_csv(
            video_path=video_path,
            boundary_timestamp=ts,
            out_path=per_boundary_dir / row["brightness_csv_ref"],
            window_sec=args.window_sec,
            interval_sec=args.interval_sec,
        )
        export_sample_frames(
            video_path=video_path,
            boundary_timestamp=ts,
            out_dir=per_boundary_dir,
        )

    print(f"Worksheet: {worksheet_csv}", file=sys.stderr)
    print(f"Per-boundary artifacts: {per_boundary_dir}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
