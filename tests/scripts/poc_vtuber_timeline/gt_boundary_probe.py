"""GT annotation instrument: dense-probe candidate boundaries for all sources.

For each (source, edge) candidate, probes [edge-90, edge+90] at 1s with
at-anchor presence + band MAD + band brightness, then derives:
  - collapse: last t of the leading sustained-present run (frozen-excluded)
  - recovery: first t of the trailing sustained-present run (frozen-excluded)
  - blackout runs in the window (band_b <= 30)
Writes one JSON per source with per-edge evidence for GT adjudication.

Independence scope (accurate statement; PR #915 review F22 corrected an
earlier overclaim of "independent of the production V3 snap logic"):

  NOT independent -- the measurement layer is production code. `probe_gap`
  is imported from `allaganeye.video.vtuber_timeline`, so at-anchor presence
  / band MAD / band brightness are exactly the primitives the detector uses,
  and `_runs` below is a verbatim copy of production `_tolerant_runs`.

  Independent -- only the post-signal edge derivation: 1s dense stride (vs
  the detector's 10s scan), frozen-present exclusion (band_mad >= FROZEN_MAX),
  sustained-run / blackout-run selection, and the fact that every value that
  reached tests/baselines/v0.3.0/vtuber-gt/*.json was human-adjudicated from
  this evidence dump.

  So circularity is removed in the DECISION layer (V3 snap / merge / V2
  segmentation), not in the MEASUREMENT layer: a systematic bias inside
  `probe_gap` would move GT and detector together and this script would not
  catch it. That residual class is covered by human review of the dump, not
  by the instrument.

Drift policy: `_runs` is intentionally pinned (NOT re-synced to production)
so re-running this instrument reproduces the recorded GT; `_check_runs_pin`
compares it against production `_tolerant_runs` at startup and prints a
non-fatal WARNING on divergence, which must be recorded in the GT provenance
before any re-annotation.

sys.path policy: repo root を sys.path の先頭に insert する (append しない)。
計測器は install 版ではなく repo 版 `allaganeye` を測る必要があるため。
shadowing 懸念への手当は import 直前のコメントを参照。

Input validation: `_resolve_out_path` (label 正規表現 + out_dir 内包)、argv 個数、
config 型、`_check_runs_pin` の 4 つの guard は
`tests/scripts/test_gt_boundary_probe.py` で「発火する側」を実証している
(no-op 出荷の防止)。

Usage:
    python tests/scripts/poc_vtuber_timeline/gt_boundary_probe.py <config.json> <out_dir>

config.json format:
    [{"label": "kyuma", "video": "E:/...", "anchor": "532,1147,0,45,0.8",
      "edges": [20, 820, 1170, ...]}, ...]
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# insert(0) (not append): 計測器は「repo 版 allaganeye」を測らなければならない。
# append にすると allaganeye が site-packages に install された環境で install 版が
# 先に解決され、計測器が repo の変更を測っていないことに気付けない (silent に別の
# コードを計測する = GT 注釈の provenance が崩れる)。
# shadowing 懸念 (PR #915 review F21) への手当:
#   - 追加する path は repo root 1 本のみ (site-packages 等は触らない)
#   - 本 script が import するのは stdlib と `allaganeye.*` だけで、repo root
#     直下に stdlib と衝突する top-level module 名は存在しない
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from allaganeye.video.capture_region import ScorebarLocalization
from allaganeye.video.vtuber_timeline import probe_gap

WINDOW_S = 90.0
FROZEN_MAX = 1.0
BLACKOUT_B_MAX = 30.0
FLICKER_TOL = 10  # sustained run: allow gaps up to this many absent probes

# label は出力ファイル名に使われるため、path separator / 親参照 / 絶対 path を
# 構文的に排除する (config は原則ローカル authored だが「外部入力 -> パス結合」
# の無検証パターン自体を塞ぐ。PR #915 review F21)
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _runs(flags: list[bool], tol: int) -> list[tuple[int, int]]:
    """True runs allowing gaps <= tol (indices inclusive).

    Pinned copy of production `_tolerant_runs` (see module docstring, drift
    policy). Do not re-sync automatically; `_check_runs_pin` reports drift.
    """
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


def _check_runs_pin() -> bool:
    """Compare the pinned `_runs` copy with production `_tolerant_runs`.

    Non-fatal: divergence is allowed by design (the copy is frozen so old GT
    stays reproducible) but must be recorded in the GT provenance.

    この green は何を見逃すか: sample pattern 上の一致しか見ないので、未サンプル
    の入力空間で production が別挙動になっても気付けない。かつ `probe_gap`
    (measurement 層) の semantics 変更はそもそも検知対象外。
    """
    try:
        from allaganeye.video.vtuber_timeline import _tolerant_runs
    except ImportError:
        print(
            "WARNING: production _tolerant_runs not importable "
            "(renamed/removed?); _runs pin unverified",
            file=sys.stderr,
        )
        return False
    patterns: list[tuple[list[bool], int]] = [
        ([], 10),
        ([True], 0),
        ([False, False], 3),
        ([True, False, True], 0),
        ([True, False, True], 1),
        ([True] * 3 + [False] * 11 + [True] * 3, FLICKER_TOL),
        ([True] * 3 + [False] * 10 + [True] * 3, FLICKER_TOL),
        ([False] * 4 + [True] * 2 + [False] * 20 + [True], 2),
    ]
    for flags, tol in patterns:
        mine, theirs = _runs(list(flags), tol), _tolerant_runs(flags, tol=tol)
        if mine != theirs:
            print(
                f"WARNING: _runs pin drifted from production _tolerant_runs "
                f"(tol={tol}, flags={flags}): local={mine} production={theirs}. "
                f"Record this in the GT provenance before re-annotating.",
                file=sys.stderr,
            )
            return False
    return True


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


def _resolve_out_path(out_dir: Path, label: object) -> Path:
    """Validate a config-supplied label and resolve its output path.

    Rejects absolute paths, separators and parent refs syntactically, then
    re-checks containment on the resolved path (defense in depth: the regex
    is the real gate, the containment check catches regex mistakes).
    """
    if not isinstance(label, str) or not _SAFE_LABEL_RE.match(label):
        raise ValueError(
            f"unsafe or missing 'label' in config: {label!r} "
            f"(allowed: {_SAFE_LABEL_RE.pattern})"
        )
    out = (out_dir / f"{label}_boundaries.json").resolve()
    if out.parent != out_dir.resolve():
        raise ValueError(f"label escapes out_dir: {label!r} -> {out}")
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: gt_boundary_probe.py <config.json> <out_dir>",
            file=sys.stderr,
        )
        return 2
    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not isinstance(config, list):
        print("config.json must be a list of source objects", file=sys.stderr)
        return 2
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    _check_runs_pin()
    # 全 label を probe 開始前に検証する (数十分の probe 後に失敗させない)
    out_paths = [
        _resolve_out_path(out_dir, src.get("label") if isinstance(src, dict) else None)
        for src in config
    ]
    for src, out in zip(config, out_paths, strict=True):
        xl, xr, yt, yb, cf = (float(v) for v in src["anchor"].split(","))
        anchor = ScorebarLocalization(int(xl), int(xr), int(yt), int(yb), cf)
        video = Path(src["video"])
        t0 = time.time()
        edges = [analyze_edge(video, anchor, float(e)) for e in src["edges"]]
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
