"""e2e 実現可能性 spike: crop->Pass1->scorebar の +-10s 実証 (#753, spec section 7 M3)。

finding #4 (spec section 2.2): VTuber 動画では overlay により frame 全体の平均
輝度が暗転中も ~52 に張り付き、Pass 1 の blackout 判定 (threshold 15) が試合
境界を取りこぼす。本 spike は game 領域で crop した輝度なら境界が復活することを
実証する: 全 frame 輝度 vs 領域 crop 輝度で blackout 遷移を検出し、それぞれ
vtuber-primary-ground-truth.json の 5 試合 start と +-10s で照合する。

本番 Pass1 wiring ではなく feasibility 確認 (machine-unverifiable, real video 要)。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from allaganeye.ffmpeg_path import find_ffmpeg

_GRAY_W = 320
_GRAY_H = 180
_GRAY_SIZE = _GRAY_W * _GRAY_H


def match_within_tolerance(
    detected: list[float], ground_truth: list[float], tol: float = 10.0
) -> tuple[int, list[float]]:
    """各 ground_truth 時刻に +-tol 内の detected があれば matched。

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


def crop_region_mean(
    frame: np.ndarray, region: tuple[float, float, float, float]
) -> float:
    """正規化矩形 *region* (x,y,w,h) で frame を crop し平均輝度を返す。

    crop が空になる場合は frame 全体の平均で fallback。
    """
    h, w = frame.shape[:2]
    x, y, ww, hh = region
    x0 = max(0, min(round(x * w), w - 1))
    y0 = max(0, min(round(y * h), h - 1))
    x1 = max(x0 + 1, min(round((x + ww) * w), w))
    y1 = max(y0 + 1, min(round((y + hh) * h), h))
    return float(frame[y0:y1, x0:x1].mean())


def blackout_boundary_candidates(
    samples: list[tuple[float, float]], threshold: float
) -> tuple[list[float], list[float]]:
    """(timestamp, brightness) 列から明暗遷移時刻を返す。

    Returns (recover_times, drop_times):
    - recover = 暗->明 (brightness が threshold 以下から超へ) = 試合開始の候補。
    - drop    = 明->暗 (threshold 超から以下へ)             = 試合終了の候補。
    *samples* は時刻昇順を仮定。
    """
    recovers: list[float] = []
    drops: list[float] = []
    prev_dark: bool | None = None
    for t, b in samples:
        dark = b <= threshold
        if prev_dark is not None:
            if dark and not prev_dark:
                drops.append(t)
            elif not dark and prev_dark:
                recovers.append(t)
        prev_dark = dark
    return recovers, drops


# ---------------------------------------------------------------------------
# ffmpeg sampling (machine-unverifiable: real video 要)
# ---------------------------------------------------------------------------


def _probe_gray_frame(video_path: Path, timestamp: float) -> np.ndarray | None:
    """320x180 グレースケール単フレームを ndarray で返す。"""
    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-s",
        f"{_GRAY_W}x{_GRAY_H}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or len(result.stdout) < _GRAY_SIZE:
        return None
    return np.frombuffer(result.stdout[:_GRAY_SIZE], dtype=np.uint8).reshape(
        _GRAY_H, _GRAY_W
    )


def _run_spike(args: argparse.Namespace) -> list[float]:
    """benchmark を sampling -> 全 frame / 領域 crop の両輝度で blackout 検出。

    crop 領域は vtuber-primary-regions.json の矩形 (本ベンチは A=B 静的)。
    full-frame では試合境界が masked され、crop では復活することを実証する。
    Returns crop 由来の recover 時刻 (= 検出した試合 start 候補)。
    """
    regions_data = json.loads(args.regions.read_text(encoding="utf-8"))
    r0 = regions_data["regions"][0]
    region = (r0["x"], r0["y"], r0["w"], r0["h"])
    print(f"[spike] crop region (normalized) = {region}")

    gt = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    matches = gt["matches"]
    gt_starts = [float(m["start_time"]) for m in matches]
    gt_ends = [float(m["end_time"]) for m in matches]
    cap = args.max_time if args.max_time else max(gt_ends) + 90.0

    timestamps = [float(t) for t in np.arange(0.0, cap, args.interval)]
    print(
        f"[spike] sampling {len(timestamps)} frames over 0..{cap:.0f}s "
        f"@ {args.interval}s (threshold={args.threshold})"
    )
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        frames = list(
            ex.map(lambda t: _probe_gray_frame(args.benchmark, t), timestamps)
        )
    elapsed = time.time() - t_start
    print(f"[spike] decode wall-time = {elapsed:.1f}s")

    full_samples: list[tuple[float, float]] = []
    crop_samples: list[tuple[float, float]] = []
    for t, f in zip(timestamps, frames, strict=True):
        if f is None:
            continue
        full_samples.append((t, float(f.mean())))
        crop_samples.append((t, crop_region_mean(f, region)))

    full_recovers, _ = blackout_boundary_candidates(full_samples, args.threshold)
    crop_recovers, crop_drops = blackout_boundary_candidates(
        crop_samples, args.threshold
    )

    full_matched, full_misses = match_within_tolerance(
        full_recovers, gt_starts, args.tol
    )
    crop_matched, crop_misses = match_within_tolerance(
        crop_recovers, gt_starts, args.tol
    )
    crop_end_matched, _ = match_within_tolerance(crop_drops, gt_ends, args.tol)

    n = len(gt_starts)
    print()
    print("=== M3 spike result (crop unlocks Pass 1) ===")
    print(
        f"  full-frame brightness : start {full_matched}/{n} within +-{args.tol}s "
        f"(misses={full_misses})"
    )
    print(
        f"  region-crop brightness: start {crop_matched}/{n} within +-{args.tol}s "
        f"(misses={crop_misses})"
    )
    print(
        f"  region-crop brightness: end   {crop_end_matched}/{n} within +-{args.tol}s"
    )
    return crop_recovers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-ground-truth.json"),
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-regions.json"),
    )
    parser.add_argument("--tol", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=2.5)
    parser.add_argument("--threshold", type=float, default=15.0)
    parser.add_argument("--max-time", type=float, default=0.0)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)

    gt_data = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    starts = [float(m["start_time"]) for m in gt_data["matches"]]
    detected = _run_spike(args)
    matched, misses = match_within_tolerance(detected, starts, args.tol)
    print(f"\nmatched {matched}/{len(starts)} within +-{args.tol}s; misses={misses}")
    return 0 if matched == len(starts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
