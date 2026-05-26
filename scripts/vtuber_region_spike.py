"""e2e 実現可能性 spike: crop→Pass1→scorebar の ±10s 実証 (#753, spec §7 M3)。

選定 (または annotation) 領域で frame を crop し、領域内輝度で Pass 1 暗転
検知 → 試合 start/end を抽出し、vtuber-primary-ground-truth.json と ±10s で
照合する。本番 Pass1 wiring ではなく feasibility 確認 (machine-unverifiable)。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def match_within_tolerance(
    detected: list[float], ground_truth: list[float], tol: float = 10.0
) -> tuple[int, list[float]]:
    """各 ground_truth 時刻に ±tol 内の detected があれば matched。

    Returns (matched_count, [未検出の gt 時刻])。
    """
    matched = 0
    misses: list[float] = []
    for g in ground_truth:
        if any(abs(d - g) <= tol for d in detected):
            matched += 1
        else:
            misses.append(g)
    return matched, misses


def _run_spike(args: argparse.Namespace) -> list[float]:
    """実走部 (machine-unverifiable)。Task D.1 で実装・手動実行。

    benchmark を sampling → region で crop → 輝度 → 暗転 → segment 抽出。
    Pass 1 本体は再利用せず最小再実装 (feasibility)。
    """
    raise NotImplementedError("Task D.1 で実走部を実装・手動実行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-ground-truth.json"),
    )
    parser.add_argument("--tol", type=float, default=10.0)
    args = parser.parse_args(argv)
    gt_data = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    starts = [m["start_time"] for m in gt_data["matches"]]
    detected = _run_spike(args)
    matched, misses = match_within_tolerance(detected, starts, args.tol)
    print(f"matched {matched}/{len(starts)} within +-{args.tol}s; misses={misses}")
    return 0 if matched == len(starts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
