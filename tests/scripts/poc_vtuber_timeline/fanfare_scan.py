"""PoC fanfare scan: run bundled fanfare reference correlation on a VOD.

Records ALL peaks above a low threshold so the report can show the similarity
distribution (voice-over degradation check), not just production-threshold hits.

Usage:
    python tests/scripts/poc_vtuber_timeline/fanfare_scan.py <video> <out_json> [--threshold 0.5]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from allaganeye.audio.scan import scan_fanfare_hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("out_json", type=Path)
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args()

    t0 = time.time()
    hits = scan_fanfare_hits(args.video, threshold=args.threshold)
    payload = {
        "video": args.video.name,
        "threshold": args.threshold,
        "elapsed_sec": round(time.time() - t0, 1),
        "hits": [
            {
                "t": round(float(h["timestamp"]), 2),
                "sim": round(float(h["similarity"]), 3),
            }
            for h in hits
        ],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(
        f"done: {len(hits)} hits in {payload['elapsed_sec']}s -> {args.out_json}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
