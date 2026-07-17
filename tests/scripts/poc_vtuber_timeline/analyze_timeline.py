"""Analyze a PoC timeline CSV: presence runs, brightness plateaus, boundary candidates.

Presence smoothing: a probe is PRESENT when found=1 and conf >= --conf.  Runs of
consecutive ABSENT probes >= --min-gap-probes form candidate non-match gaps.
Prints segments (present runs) and gaps with brightness stats, optionally
compares against a reference boundary list (JSON: [{start, end}, ...]).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = []
        for r in csv.DictReader(f):
            if r["err"]:
                continue
            rows.append(
                {
                    "t": float(r["t"]),
                    "b": float(r["brightness"]) if r["brightness"] else None,
                    "found": r["found"] == "1",
                    "conf": float(r["conf"]) if r["conf"] else 0.0,
                    "y": int(r["y_top"]) if r["y_top"] else None,
                }
            )
        return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--conf", type=float, default=0.3)
    ap.add_argument(
        "--min-gap-probes",
        type=int,
        default=3,
        help="min consecutive absent probes for a gap",
    )
    ap.add_argument(
        "--ref-json",
        type=Path,
        default=None,
        help="reference boundaries [{start,end},...]",
    )
    args = ap.parse_args()

    rows = load_rows(args.csv_path)
    stride = rows[1]["t"] - rows[0]["t"] if len(rows) > 1 else 0

    # presence run-length encoding
    runs: list[dict] = []  # {state, t0, t1, n}
    for r in rows:
        state = r["found"] and r["conf"] >= args.conf
        if runs and runs[-1]["state"] == state:
            runs[-1]["t1"] = r["t"]
            runs[-1]["n"] += 1
            runs[-1]["bsum"] += r["b"] or 0.0
        else:
            runs.append(
                {
                    "state": state,
                    "t0": r["t"],
                    "t1": r["t"],
                    "n": 1,
                    "bsum": r["b"] or 0.0,
                }
            )

    # merge short absent runs (< min_gap_probes) into surrounding present context
    print(f"rows={len(rows)} stride={stride:.0f}s conf>={args.conf}")
    print(
        f"\n--- absent gaps (>= {args.min_gap_probes} probes = {args.min_gap_probes * stride:.0f}s) ---"
    )
    for run in runs:
        if not run["state"] and run["n"] >= args.min_gap_probes:
            mean_b = run["bsum"] / run["n"]
            print(
                f"  gap {run['t0']:8.0f} - {run['t1']:8.0f}  ({run['t1'] - run['t0']:6.0f}s, "
                f"{run['n']:3d} probes, mean brightness {mean_b:6.1f})"
            )

    # coarse segments: present-dominant regions between long gaps
    print(
        f"\n--- coarse present segments (gaps < {args.min_gap_probes} probes bridged) ---"
    )
    segs: list[list[float]] = []
    for run in runs:
        if run["state"]:
            if segs and run["t0"] - segs[-1][1] <= args.min_gap_probes * stride:
                segs[-1][1] = run["t1"]
            else:
                segs.append([run["t0"], run["t1"]])
    for s in segs:
        if s[1] - s[0] >= 120:
            print(f"  seg {s[0]:8.0f} - {s[1]:8.0f}  ({(s[1] - s[0]) / 60:5.1f} min)")

    if args.ref_json and args.ref_json.exists():
        ref = json.loads(args.ref_json.read_text(encoding="utf-8"))
        print("\n--- reference boundaries ---")
        for m in ref:
            print(
                f"  ref {m['start']:8.1f} - {m['end']:8.1f}  ({(m['end'] - m['start']) / 60:5.1f} min)"
            )


if __name__ == "__main__":
    main()
