"""PoC sparse timeline scan for VTuber VOD boundary-signal research.

Probes a VOD every STRIDE seconds; per probe decodes one 1920x1080 frame and
records full-frame brightness + raw localize_scorebar output.  Output CSV feeds
the boundary-signal analysis (static plateau / presence gap / blackout).

Usage:
    python poc/scan_timeline.py <video> <out_csv> [--stride 10] [--start 0] [--end 0]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from allaganeye.video.capture_region import localize_scorebar
from allaganeye.video.detector import (
    _SCOREBAR_V2_PROBE_HEIGHT as H,
    _SCOREBAR_V2_PROBE_WIDTH as W,
    _probe_frame_rgb_hires,
)
from allaganeye.video.probe import probe_video


def probe_one(video: Path, t: float) -> dict:
    row: dict = {
        "t": t,
        "brightness": "",
        "found": 0,
        "y_top": "",
        "x_left": "",
        "x_right": "",
        "band_h": "",
        "conf": "",
        "err": "",
    }
    try:
        raw = _probe_frame_rgb_hires(video, t)
        if raw is None:
            row["err"] = "decode_none"
            return row
        frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        row["brightness"] = round(float(frame.mean()), 2)
        loc = localize_scorebar(frame)
        if loc is not None:
            row["found"] = 1
            row["y_top"] = loc.y_top
            row["x_left"] = loc.x_left
            row["x_right"] = loc.x_right
            row["band_h"] = loc.y_bottom - loc.y_top + 1
            row["conf"] = round(loc.confidence, 3)
    except Exception as exc:
        row["err"] = type(exc).__name__
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_csv", type=Path)
    ap.add_argument("--stride", type=float, default=10.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    meta = probe_video(args.video)
    total = float(meta["duration"])
    duration = args.end if args.end > 0 else total
    ts = [round(t, 2) for t in np.arange(args.start, duration, args.stride)]
    print(f"video={args.video.name} duration={total:.1f}s probes={len(ts)}", flush=True)

    t0 = time.time()
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, row in enumerate(ex.map(lambda t: probe_one(args.video, t), ts)):
            results.append(row)
            if (i + 1) % 100 == 0:
                el = time.time() - t0
                print(f"  {i + 1}/{len(ts)} probes, {el:.0f}s elapsed", flush=True)

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)
    ok = sum(1 for r in results if not r["err"])
    print(
        f"done: {len(results)} rows ({ok} ok) in {time.time() - t0:.0f}s -> {args.out_csv}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
