"""Per-source PoC pipeline: sparse raw scan -> anchor consensus -> at-anchor scan -> rule-B segments.

Usage:
    python poc/pipeline_source.py <video> <label> [--out-dir E:/allaganeye-samples/_poc_vtuber_retry]
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import subprocess
import sys
from pathlib import Path

POC = Path(__file__).parent


def run(cmd: list[str]) -> None:
    print("+", " ".join(str(c) for c in cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True)


def compute_anchor(csv_path: Path) -> tuple[str, tuple[int, int, int, int]] | None:
    hits = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["err"] or r["found"] != "1":
                continue
            if float(r["conf"]) >= 0.5:
                hits.append(
                    (
                        int(r["y_top"]),
                        int(r["x_left"]),
                        int(r["x_right"]),
                        int(r["band_h"]),
                    )
                )
    if len(hits) < 8:
        return None
    ys = sorted(h[0] for h in hits)
    clusters: list[list[int]] = []
    for y in ys:
        if clusters and y - clusters[-1][-1] <= 60:
            clusters[-1].append(y)
        else:
            clusters.append([y])
    dom = max(clusters, key=len)
    sel = [h for h in hits if dom[0] <= h[0] <= dom[-1]]
    if len(sel) < 8:
        return None
    yt = int(st.median(h[0] for h in sel))
    xl = int(st.median(h[1] for h in sel))
    xr = int(st.median(h[2] for h in sel))
    bh = int(st.median(h[3] for h in sel))
    anchor_str = f"{xl},{xr},{yt},{yt + bh - 1},0.8"
    band = (max(0, yt - 10), yt + bh + 10, xl, xr)
    return anchor_str, band


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("label")
    ap.add_argument(
        "--out-dir", type=Path, default=Path(r"E:\allaganeye-samples\_poc_vtuber_retry")
    )
    args = ap.parse_args()

    raw_csv = args.out_dir / f"{args.label}_timeline_10s.csv"
    if not raw_csv.exists():
        run(
            [
                sys.executable,
                str(POC / "scan_timeline.py"),
                str(args.video),
                str(raw_csv),
                "--stride",
                "10",
            ]
        )

    anchor = compute_anchor(raw_csv)
    if anchor is None:
        print(
            f"{args.label}: ANCHOR CONSENSUS FAILED (insufficient conf>=0.5 hits)",
            flush=True,
        )
        return 1
    anchor_str, band = anchor
    print(f"{args.label}: anchor={anchor_str} band={band}", flush=True)
    (args.out_dir / f"{args.label}_anchor.json").write_text(
        json.dumps({"anchor": anchor_str, "band": band}), encoding="utf-8"
    )

    from allaganeye.video.probe import probe_video

    duration = float(probe_video(args.video)["duration"])
    aa_csv = args.out_dir / f"{args.label}_full_atanchor_10s.csv"
    if not aa_csv.exists():
        run(
            [
                sys.executable,
                str(POC / "dense_window.py"),
                str(args.video),
                str(aa_csv),
                "--t0",
                "0",
                "--t1",
                str(duration),
                "--stride",
                "10",
                "--band-y0",
                str(band[0]),
                "--band-y1",
                str(band[1]),
                "--band-x0",
                str(band[2]),
                "--band-x1",
                str(band[3]),
                "--anchor",
                anchor_str,
            ]
        )
    run([sys.executable, str(POC / "simulate_segmentation.py"), str(aa_csv)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
