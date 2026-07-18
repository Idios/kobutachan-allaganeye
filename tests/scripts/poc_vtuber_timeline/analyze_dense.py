"""Summarize a dense-window CSV into a 10s-bucket signal table.

Per bucket prints: full brightness min/mean, band brightness min, full MAD mean,
band MAD mean, raw localize rate, at-anchor presence rate.  Static plateau and
blackout candidates become visible at a glance.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--bucket", type=float, default=10.0)
    args = ap.parse_args()

    rows = []
    with open(args.csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["err"]:
                continue
            rows.append(r)

    buckets: dict[int, list[dict]] = {}
    for r in rows:
        buckets.setdefault(int(float(r["t"]) // args.bucket), []).append(r)

    print(f"{args.csv_path.name}: {len(rows)} probes")
    print(" t0      bright(min/mean)  band_b(min)  mad_full  band_mad  loc%  anchor%")
    for k in sorted(buckets):
        rs = buckets[k]
        b = [float(r["brightness"]) for r in rs if r["brightness"]]
        bb = [float(r["band_b"]) for r in rs if r["band_b"]]
        mf = [float(r["mad_full"]) for r in rs if r["mad_full"]]
        bm = [float(r["band_mad"]) for r in rs if r["band_mad"]]
        loc = sum(1 for r in rs if r["found"] == "1") / len(rs)
        anc = sum(1 for r in rs if r["anchor_found"] == "1") / len(rs)
        print(
            f"{k * args.bucket:6.0f}  {min(b):6.1f}/{sum(b) / len(b):6.1f}   "
            f"{min(bb) if bb else -1:8.1f}   {sum(mf) / len(mf):7.2f}  "
            f"{sum(bm) / len(bm) if bm else -1:7.2f}  {loc * 100:4.0f}  {anc * 100:4.0f}"
        )


if __name__ == "__main__":
    main()
