"""Simulate presence x motion timeline segmentation on a full at-anchor scan CSV.

Probe evidence: anchor_found AND band_mad >= --mad-min  (rule B)
                anchor_found only                        (rule A, for comparison)
Rolling window of --win probes; window in-match when evidence count >= --quorum.
Runs of in-match windows -> segments; segments < --min-dur dropped.

Compares against --ref-json [{start,end},...] when provided.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["err"]:
                continue
            rows.append(
                {
                    "t": float(r["t"]),
                    "anchor": r["anchor_found"] == "1",
                    "mad": float(r["band_mad"]) if r["band_mad"] else None,
                }
            )
    return rows


def segment(
    rows: list[dict],
    *,
    use_mad: bool,
    mad_min: float,
    win: int,
    quorum: int,
    min_dur: float,
) -> list[tuple[float, float]]:
    n = len(rows)
    evid = []
    for r in rows:
        e = r["anchor"]
        if use_mad and e:
            e = r["mad"] is not None and r["mad"] >= mad_min
        evid.append(e)
    half = win // 2
    state = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        state.append(sum(evid[lo:hi]) >= quorum)
    segs: list[list[float]] = []
    for i, s in enumerate(state):
        if s:
            t = rows[i]["t"]
            if segs and t - segs[-1][1] <= (rows[1]["t"] - rows[0]["t"]) * 1.5:
                segs[-1][1] = t
            else:
                segs.append([t, t])
    return [(a, b) for a, b in segs if b - a >= min_dur]


def match_refs(
    segs: list[tuple[float, float]], refs: list[dict], tol: float = 120.0
) -> None:
    for m in refs:
        best = None
        for a, b in segs:
            ov = min(b, m["end"]) - max(a, m["start"])
            if ov > 0 and (best is None or ov > best[2]):
                best = (a, b, ov)
        if best:
            ds, de = best[0] - m["start"], best[1] - m["end"]
            print(
                f"  ref {m['start']:7.0f}-{m['end']:7.0f} -> seg {best[0]:7.0f}-{best[1]:7.0f} "
                f"(dstart {ds:+6.0f}s dend {de:+6.0f}s)"
            )
        else:
            print(f"  ref {m['start']:7.0f}-{m['end']:7.0f} -> MISSED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path", type=Path)
    ap.add_argument("--mad-min", type=float, default=1.5)
    ap.add_argument("--win", type=int, default=9)
    ap.add_argument("--quorum", type=int, default=2)
    ap.add_argument("--min-dur", type=float, default=300.0)
    ap.add_argument("--ref-json", type=Path, default=None)
    args = ap.parse_args()

    rows = load(args.csv_path)
    print(
        f"{args.csv_path.name}: {len(rows)} probes, win={args.win} quorum={args.quorum} mad>={args.mad_min}"
    )
    for label, use_mad in (
        ("rule A (anchor only)", False),
        ("rule B (anchor AND moving)", True),
    ):
        segs = segment(
            rows,
            use_mad=use_mad,
            mad_min=args.mad_min,
            win=args.win,
            quorum=args.quorum,
            min_dur=args.min_dur,
        )
        print(f"\n{label}: {len(segs)} segments")
        for a, b in segs:
            print(f"  seg {a:7.0f} - {b:7.0f}  ({(b - a) / 60:5.1f} min)")
        if args.ref_json and args.ref_json.exists():
            refs = json.loads(args.ref_json.read_text(encoding="utf-8"))
            match_refs(segs, refs)


if __name__ == "__main__":
    main()
