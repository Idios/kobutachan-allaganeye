"""Generate labeled contact sheets from a VOD for visual GT annotation.

Extracts one frame per --stride seconds (320x180), tiles them 6x5 per sheet
with timestamp labels, writes PNG sheets.

Usage:
    python tests/scripts/poc_vtuber_timeline/contact_sheet.py <video> <out_dir> [--stride 60] [--t0 0] [--t1 0]
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from allaganeye.video.detector import _probe_frame_rgb_hires
from allaganeye.video.probe import probe_video

TW, TH = 320, 180
COLS, ROWS = 6, 5


def grab(video: Path, t: float) -> np.ndarray:
    raw = _probe_frame_rgb_hires(video, t)
    if raw is None:
        tile = np.zeros((TH, TW, 3), np.uint8)
    else:
        frame = np.frombuffer(raw, np.uint8).reshape(1080, 1920, 3)
        tile = cv2.resize(frame, (TW, TH), interpolation=cv2.INTER_AREA)
        tile = tile[:, :, ::-1].copy()  # RGB -> BGR for cv2 imwrite
    label = f"{int(t)}s {int(t) // 60}m"
    cv2.putText(tile, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
    cv2.putText(tile, label, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    return tile


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--stride", type=float, default=60.0)
    ap.add_argument("--t0", type=float, default=0.0)
    ap.add_argument("--t1", type=float, default=0.0)
    ap.add_argument("--prefix", default="sheet")
    args = ap.parse_args()

    total = float(probe_video(args.video)["duration"])
    t1 = args.t1 if args.t1 > 0 else total
    ts = [round(t, 1) for t in np.arange(args.t0, t1, args.stride)]
    args.out_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    with ThreadPoolExecutor(max_workers=16) as ex:
        tiles = list(ex.map(lambda t: grab(args.video, t), ts))

    per_sheet = COLS * ROWS
    n_sheets = (len(tiles) + per_sheet - 1) // per_sheet
    for s in range(n_sheets):
        chunk = tiles[s * per_sheet : (s + 1) * per_sheet]
        while len(chunk) < per_sheet:
            chunk.append(np.zeros((TH, TW, 3), np.uint8))
        rows = [np.hstack(chunk[r * COLS : (r + 1) * COLS]) for r in range(ROWS)]
        sheet = np.vstack(rows)
        out = args.out_dir / f"{args.prefix}_{s:02d}.png"
        cv2.imwrite(str(out), sheet)
    print(
        f"done: {len(ts)} frames -> {n_sheets} sheets in {time.time() - start:.0f}s at {args.out_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
