"""VTuber game capture 領域検出 候補の実験 harness (#753, spec §6)。

候補 (S1/S2/S3) を gyawa benchmark + OBS baseline に適用し、proxy 矩形
(tests/baselines/v0.3.0/vtuber-primary-regions.json) に対する M1 (IoU /
上端 px 誤差)、M2 (cost)、M4 (OBS で FULL_FRAME か) を比較表で出力する。

Usage:
    python scripts/vtuber_region_experiment.py --benchmark <mp4> --obs <mkv>...
"""

from __future__ import annotations

import argparse
from pathlib import Path


def pick_winner(rows: list[dict]) -> dict | None:
    """OBS hard gate (M4) を通過した候補のうち mean_iou 最大を返す。"""
    eligible = [r for r in rows if r.get("obs_full_frame", True)]
    if not eligible:
        return None
    return max(eligible, key=lambda r: r["mean_iou"])


def format_comparison_table(rows: list[dict]) -> str:
    header = f"{'candidate':<10}{'mean_iou':>10}{'top_err_px':>12}{'cost_s':>10}"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r['candidate']:<10}{r.get('mean_iou', 0):>10.3f}"
            f"{r.get('mean_top_err_px', 0):>12.1f}{r.get('cost_s', 0):>10.1f}"
        )
    return "\n".join(lines)


def _run_on_benchmark(args: argparse.Namespace) -> list[dict]:
    """実走部 (machine-unverifiable, real video 要)。Task D.1 で実装・手動実行。

    benchmark の annotation timestamp 近傍フレームを抽出し S1/S2/S3 を適用、
    iou()/top_edge_error_px() で M1、時間で M2、OBS baseline で M4 を集計する。
    """
    raise NotImplementedError("Task D.1 で実走部を実装・手動実行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--obs", type=Path, nargs="*", default=[])
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-regions.json"),
    )
    args = parser.parse_args(argv)
    rows = _run_on_benchmark(args)
    print(format_comparison_table(rows))
    winner = pick_winner(rows)
    print(f"\nWINNER (M4 gate + max IoU): {winner['candidate'] if winner else 'NONE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
