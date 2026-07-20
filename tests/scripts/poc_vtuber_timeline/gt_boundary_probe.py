"""GT annotation instrument: dense-probe candidate boundaries for all sources.

For each (source, edge) candidate, probes [edge-90, edge+90] at 1s with
at-anchor presence + band MAD + band brightness, then derives:
  - collapse: last t of the leading sustained-present run (frozen-excluded)
  - recovery: first t of the trailing sustained-present run (frozen-excluded)
  - blackout runs in the window (band_b <= 30)
Writes one JSON per source with per-edge evidence for GT adjudication.

This is an ANNOTATION instrument independent of the production V3 snap logic
(reimplements edge derivation with frozen exclusion so GT is not circular
with detector output).

Usage:
    python tests/scripts/poc_vtuber_timeline/gt_boundary_probe.py <config.json> <out_dir>

config.json format:
    [{"label": "kyuma", "video": "E:/...", "anchor": "532,1147,0,45,0.8",
      "edges": [20, 820, 1170, ...]}, ...]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from allaganeye.video.capture_region import ScorebarLocalization
from allaganeye.video.vtuber_timeline import probe_gap

WINDOW_S = 90.0
FROZEN_MAX = 1.0
BLACKOUT_B_MAX = 30.0
FLICKER_TOL = 10  # sustained run: allow gaps up to this many absent probes


def _runs(flags: list[bool], tol: int) -> list[tuple[int, int]]:
    """True runs allowing gaps <= tol (indices inclusive)."""
    runs: list[tuple[int, int]] = []
    start = None
    gap = 0
    last_true = None
    for i, f in enumerate(flags):
        if f:
            if start is None:
                start = i
            last_true = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > tol and last_true is not None:
                runs.append((start, last_true))
                start = None
    if start is not None and last_true is not None:
        runs.append((start, last_true))
    return runs


def analyze_edge(video: Path, anchor, edge: float) -> dict:
    t0, t1 = max(0.0, edge - WINDOW_S), edge + WINDOW_S
    probes = probe_gap(video, anchor, t0, t1, stride=1.0)
    # match-evidence flag: present AND not frozen (result 表示は present+moving
    # で含まれ、replay/room の frozen-present は除外される)
    flags = [
        p.present and p.band_mad is not None and p.band_mad >= FROZEN_MAX
        for p in probes
    ]
    runs = _runs(flags, FLICKER_TOL)
    blackouts = []
    b_start = None
    for i, p in enumerate(probes):
        black = p.band_b is not None and p.band_b <= BLACKOUT_B_MAX
        if black and b_start is None:
            b_start = i
        elif not black and b_start is not None:
            blackouts.append((round(probes[b_start].t, 1), round(probes[i - 1].t, 1)))
            b_start = None
    if b_start is not None:
        blackouts.append((round(probes[b_start].t, 1), round(probes[-1].t, 1)))
    lead_end = (
        round(probes[runs[0][1]].t, 1) if runs and flags[0:5].count(True) else None
    )
    trail_start = (
        round(probes[runs[-1][0]].t, 1) if runs and flags[-5:].count(True) else None
    )
    present_rate = sum(1 for p in probes if p.present) / max(1, len(probes))
    return {
        "edge": edge,
        "window": [round(t0, 1), round(t1, 1)],
        "collapse": lead_end,
        "recovery": trail_start,
        "runs": [[round(probes[a].t, 1), round(probes[b].t, 1)] for a, b in runs],
        "blackouts": blackouts,
        "present_rate": round(present_rate, 3),
        "unknown": sum(1 for p in probes if p.band_b is None),
    }


def main() -> int:
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in config:
        xl, xr, yt, yb, cf = (float(v) for v in src["anchor"].split(","))
        anchor = ScorebarLocalization(int(xl), int(xr), int(yt), int(yb), cf)
        video = Path(src["video"])
        t0 = time.time()
        edges = [analyze_edge(video, anchor, float(e)) for e in src["edges"]]
        out = out_dir / f"{src['label']}_boundaries.json"
        out.write_text(
            json.dumps({"label": src["label"], "edges": edges}, indent=1),
            encoding="utf-8",
        )
        print(
            f"{src['label']}: {len(edges)} edges in {time.time() - t0:.0f}s -> {out}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
