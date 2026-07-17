"""PoC dense-window probe: fine-grained signals around a candidate boundary.

For a time window, probes every --stride seconds; per probe decodes TWO frames
(t and t+0.5s) at 1920x1080 and records:
  - full-frame brightness
  - full-frame MAD between the pair (motion)
  - band MAD / band brightness within --band (y0:y1 px, from anchor or localize)
  - raw localize presence + conf

Usage:
    python tests/scripts/poc_vtuber_timeline/dense_window.py <video> <out_csv> --t0 3200 --t1 3600 [--stride 1]
        [--band-y0 0 --band-y1 60] [--band-x0 500 --band-x1 1200]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from allaganeye.video.capture_region import (
    ScorebarLocalization,
    localize_scorebar,
    localize_scorebar_at_anchor,
)
from allaganeye.video.detector import (
    _SCOREBAR_V2_PROBE_HEIGHT as H,
    _SCOREBAR_V2_PROBE_WIDTH as W,
    _probe_frame_rgb_hires,
)

PAIR_DT = 0.5


def probe_one(
    video: Path,
    t: float,
    band: tuple[int, int, int, int] | None,
    anchor: ScorebarLocalization | None,
) -> dict:
    row: dict = {
        "t": t,
        "brightness": "",
        "mad_full": "",
        "band_b": "",
        "band_mad": "",
        "found": 0,
        "y_top": "",
        "conf": "",
        "anchor_found": 0,
        "anchor_conf": "",
        "err": "",
    }
    try:
        raw1 = _probe_frame_rgb_hires(video, t)
        raw2 = _probe_frame_rgb_hires(video, t + PAIR_DT)
        if raw1 is None or raw2 is None:
            row["err"] = "decode_none"
            return row
        f1 = np.frombuffer(raw1, np.uint8).reshape(H, W, 3).astype(np.int16)
        f2 = np.frombuffer(raw2, np.uint8).reshape(H, W, 3).astype(np.int16)
        row["brightness"] = round(float(f1.mean()), 2)
        row["mad_full"] = round(float(np.abs(f1 - f2).mean()), 3)
        if band is not None:
            y0, y1, x0, x1 = band
            b1 = f1[y0:y1, x0:x1]
            b2 = f2[y0:y1, x0:x1]
            row["band_b"] = round(float(b1.mean()), 2)
            row["band_mad"] = round(float(np.abs(b1 - b2).mean()), 3)
        frame_u8 = f1.astype(np.uint8)
        loc = localize_scorebar(frame_u8)
        if loc is not None:
            row["found"] = 1
            row["y_top"] = loc.y_top
            row["conf"] = round(loc.confidence, 3)
        if anchor is not None:
            aloc = localize_scorebar_at_anchor(frame_u8, anchor)
            if aloc is not None:
                row["anchor_found"] = 1
                row["anchor_conf"] = round(aloc.confidence, 3)
    except Exception as exc:
        row["err"] = type(exc).__name__
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_csv", type=Path)
    ap.add_argument("--t0", type=float, required=True)
    ap.add_argument("--t1", type=float, required=True)
    ap.add_argument("--stride", type=float, default=1.0)
    ap.add_argument("--band-y0", type=int, default=None)
    ap.add_argument("--band-y1", type=int, default=None)
    ap.add_argument("--band-x0", type=int, default=0)
    ap.add_argument("--band-x1", type=int, default=W)
    ap.add_argument("--anchor", default=None, help="x_left,x_right,y_top,y_bottom,conf")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    band = None
    if args.band_y0 is not None and args.band_y1 is not None:
        band = (args.band_y0, args.band_y1, args.band_x0, args.band_x1)

    anchor = None
    if args.anchor:
        xl, xr, yt, yb, cf = (float(v) for v in args.anchor.split(","))
        anchor = ScorebarLocalization(int(xl), int(xr), int(yt), int(yb), cf)

    ts = [round(t, 2) for t in np.arange(args.t0, args.t1, args.stride)]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(lambda t: probe_one(args.video, t, band, anchor), ts))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        wr.writeheader()
        wr.writerows(results)
    print(
        f"done: {len(results)} probes in {time.time() - t0:.0f}s -> {args.out_csv}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
