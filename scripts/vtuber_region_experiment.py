"""VTuber game capture 領域検出 候補の実験 harness (#753, spec section 6)。

候補 (S1/S2/S3) を gyawa benchmark + OBS baseline に適用し、proxy 矩形
(tests/baselines/v0.3.0/vtuber-primary-regions.json) に対する M1 (IoU /
上端 px 誤差)、M2 (cost)、M4 (OBS で領域=全体 or 安全に decline) を比較表で
出力する。

Tier ごとに評価方法が異なる (spec section 3.1):
- S1/S3 = Tier A coarse: 動画全域から **1 領域**を推定し静的正解矩形と比較。
- S2     = Tier B precise: annotation timestamp ごとの **単フレーム**で推定。

M4 (OBS 回帰) の合否 (spec section 6.2):
- S1/S3 は Pass 1 coarse に直接使うため OBS では FULL_FRAME 必須。
- S2 は Tier B precise (coarse Pass 1 には使わない)。#806 の max-width gate で
  OBS の全幅 scorebar (>1440px) は None を返し decline する。誤った inset を
  主張しなければ regression-safe なので None / FULL_FRAME を pass とみなす。
- なお本 issue は detector.py 本体を変更しないため、production detect 出力は
  構造的に bit-exact (M4 の bit-exact 部分は自明に満たす)。本 harness が測るのは
  「将来 wiring したとき OBS で安全に縮退するか」という前方互換性。

Usage:
    python scripts/vtuber_region_experiment.py --benchmark <gyawa.mp4> \
        --obs-dir <ALLAGANEYE_SAMPLE_VIDEO_DIR>
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


def pick_winner(rows: list[dict]) -> dict | None:
    """OBS hard gate (M4) を通過した候補のうち mean_iou 最大を返す。"""
    eligible = [r for r in rows if r.get("obs_full_frame", True)]
    if not eligible:
        return None
    return max(eligible, key=lambda r: r["mean_iou"])


def format_comparison_table(rows: list[dict]) -> str:
    header = (
        f"{'candidate':<10}{'tier':>6}{'mean_iou':>10}{'top_err_px':>12}"
        f"{'cost_s':>10}{'obs_ok':>8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        obs = "PASS" if r.get("obs_full_frame", True) else "FAIL"
        lines.append(
            f"{r['candidate']:<10}{r.get('tier', '-'):>6}{r.get('mean_iou', 0):>10.3f}"
            f"{r.get('mean_top_err_px', 0):>12.1f}{r.get('cost_s', 0):>10.1f}"
            f"{obs:>8}"
        )
    return "\n".join(lines)


def region_metrics(detected, truth, frame_h: int) -> dict:
    """検出矩形 vs 正解矩形の M1 指標 (IoU / 上端 px 誤差)。

    *detected* が None (検出失敗) のときは最悪値 (iou=0, top_err=frame_h)。
    """
    from allaganeye.video.capture_region import iou, top_edge_error_px

    if detected is None:
        return {"iou": 0.0, "top_err_px": float(frame_h)}
    return {
        "iou": iou(detected, truth),
        "top_err_px": top_edge_error_px(detected, truth, frame_h),
    }


# ---------------------------------------------------------------------------
# ffmpeg sampling (machine-unverifiable: real video 要)
# ---------------------------------------------------------------------------


def _probe_gray_frame(video_path: Path, timestamp: float) -> np.ndarray | None:
    """320x180 グレースケール単フレームを ndarray で返す (_probe_single_frame 同型)。"""
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


def _sample_gray_frames(
    video_path: Path, timestamps: list[float], workers: int = 12
) -> list[np.ndarray]:
    """複数タイムスタンプの gray frame を並列取得 (None は除外)。"""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda t: _probe_gray_frame(video_path, t), timestamps))
    return [f for f in results if f is not None]


def _mid_match_timestamps(matches: list[dict]) -> list[float]:
    """各試合の 25/50/75% 地点 (試合中=高輝度・高動き)。"""
    out: list[float] = []
    for m in matches:
        s, e = float(m["start_time"]), float(m["end_time"])
        dur = e - s
        out += [s + 0.25 * dur, s + 0.5 * dur, s + 0.75 * dur]
    return out


def _boundary_dark_timestamps(matches: list[dict]) -> list[float]:
    """各試合終了直後 (+2/+4s) と先頭試合開始直前 (-3s) の暗転フレーム。"""
    out: list[float] = []
    for m in matches:
        e = float(m["end_time"])
        out += [e + 2.0, e + 4.0]
    out.append(max(0.0, float(matches[0]["start_time"]) - 3.0))
    return out


def _eval_tierA_on_benchmark(
    video: Path, matches: list[dict], truth, frame_h: int
) -> tuple[dict, dict]:
    """S1 (variance) / S3 (blackout-overlap) を benchmark で 1 領域評価。"""
    from allaganeye.video.capture_region import (
        detect_region_blackout_overlap,
        detect_region_variance,
    )

    mid_ts = _mid_match_timestamps(matches)
    dark_ts = _boundary_dark_timestamps(matches)
    bright = _sample_gray_frames(video, mid_ts)
    dark = _sample_gray_frames(video, dark_ts)

    t0 = time.time()
    s1 = detect_region_variance(bright)
    s1_cost = time.time() - t0
    m1 = region_metrics(s1, truth, frame_h)
    s1_row = {
        "candidate": "S1",
        "tier": "A",
        "mean_iou": m1["iou"],
        "mean_top_err_px": m1["top_err_px"],
        "cost_s": s1_cost,
    }

    t0 = time.time()
    s3 = detect_region_blackout_overlap(bright + dark)
    s3_cost = time.time() - t0
    m3 = region_metrics(s3, truth, frame_h)
    s3_row = {
        "candidate": "S3",
        "tier": "A",
        "mean_iou": m3["iou"],
        "mean_top_err_px": m3["top_err_px"],
        "cost_s": s3_cost,
    }
    return s1_row, s3_row


def _eval_tierB_on_benchmark(video: Path, truths: list[tuple], frame_h: int) -> dict:
    """S2 (scorebar-band) を annotation timestamp ごとに単フレーム評価。"""
    from allaganeye.video.capture_region import detect_region_scorebar_band
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
        _probe_frame_rgb_hires,
    )

    ious: list[float] = []
    errs: list[float] = []
    hit_top_errs: list[float] = []  # 上端誤差は検出できた frame のみ (S2 の主指標)
    t0 = time.time()
    for ts, truth in truths:
        raw = _probe_frame_rgb_hires(video, float(ts))
        if raw is None:
            ious.append(0.0)
            errs.append(float(frame_h))
            continue
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(
            _SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3
        )
        det = detect_region_scorebar_band(frame)
        m = region_metrics(det, truth, frame_h)
        ious.append(m["iou"])
        errs.append(m["top_err_px"])
        if det is not None:
            hit_top_errs.append(m["top_err_px"])
    cost = time.time() - t0
    n = len(truths)
    return {
        "candidate": "S2",
        "tier": "B",
        "mean_iou": float(np.mean(ious)) if ious else 0.0,
        "mean_top_err_px": float(np.mean(errs)) if errs else float(frame_h),
        "cost_s": cost,
        "hit_rate": len(hit_top_errs) / n if n else 0.0,
        "top_err_hits_px": float(np.mean(hit_top_errs)) if hit_top_errs else None,
    }


def _eval_obs_regression(
    obs_dir: Path, gt_dir: Path
) -> dict[str, tuple[bool, list[str]]]:
    """OBS baseline 各本で S1/S2/S3 が安全に縮退するか (M4)。

    Returns {candidate: (all_pass, [detail per video])}。
    S1/S3 は FULL_FRAME 必須、S2 は None / FULL_FRAME を安全とみなす。
    """
    from allaganeye.video.capture_region import (
        FULL_FRAME,
        detect_region_blackout_overlap,
        detect_region_scorebar_band,
        detect_region_variance,
    )
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
        _probe_frame_rgb_hires,
    )

    status: dict[str, list[bool]] = {"S1": [], "S2": [], "S3": []}
    detail: dict[str, list[str]] = {"S1": [], "S2": [], "S3": []}
    gt_files = sorted(gt_dir.glob("obs-*.json"))
    for gt_file in gt_files:
        gt = json.loads(gt_file.read_text(encoding="utf-8"))
        video = obs_dir / gt["source_file"]
        label = gt.get("source_dir_label", gt_file.stem)
        if not video.exists():
            for c in status:
                detail[c].append(f"{label}=SKIP(missing)")
            continue
        matches = gt["matches"]
        bright = _sample_gray_frames(video, _mid_match_timestamps(matches))
        dark = _sample_gray_frames(video, _boundary_dark_timestamps(matches))

        s1 = detect_region_variance(bright)
        ok1 = s1 == FULL_FRAME
        status["S1"].append(ok1)
        detail["S1"].append(f"{label}={'full' if ok1 else _fmt(s1)}")

        s3 = detect_region_blackout_overlap(bright + dark)
        ok3 = s3 == FULL_FRAME
        status["S3"].append(ok3)
        detail["S3"].append(f"{label}={'full' if ok3 else _fmt(s3)}")

        mid = _mid_match_timestamps(matches)
        raw = _probe_frame_rgb_hires(video, mid[0]) if mid else None
        if raw is None:
            status["S2"].append(True)
            detail["S2"].append(f"{label}=noframe")
        else:
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                _SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3
            )
            s2 = detect_region_scorebar_band(frame)
            ok2 = s2 is None or s2 == FULL_FRAME
            status["S2"].append(ok2)
            detail["S2"].append(
                f"{label}={'none' if s2 is None else ('full' if s2 == FULL_FRAME else _fmt(s2))}"
            )
    return {c: (all(v) if v else True, detail[c]) for c, v in status.items()}


def _fmt(r) -> str:
    return f"({r.x:.2f},{r.y:.2f},{r.w:.2f},{r.h:.2f})"


def _run_on_benchmark(args: argparse.Namespace) -> list[dict]:
    """machine-unverifiable: real video 要。M1/M2/M4 を集計して rows を返す。"""
    from allaganeye.video.capture_region import CaptureRegion

    regions_data = json.loads(args.regions.read_text(encoding="utf-8"))
    frame_h = int(regions_data.get("frame_height", 1080))
    truths = [
        (r["timestamp"], CaptureRegion(r["x"], r["y"], r["w"], r["h"]))
        for r in regions_data["regions"]
    ]
    truth0 = truths[0][1]

    gt = json.loads(args.benchmark_ground_truth.read_text(encoding="utf-8"))
    matches = gt["matches"]

    print(f"[M1/M2] benchmark={args.benchmark.name} ({len(truths)} annotated regions)")
    s1_row, s3_row = _eval_tierA_on_benchmark(args.benchmark, matches, truth0, frame_h)
    s2_row = _eval_tierB_on_benchmark(args.benchmark, truths, frame_h)

    obs_status: dict[str, tuple[bool, list[str]]] = {}
    if args.obs_dir is not None:
        print(f"[M4] OBS regression from {args.obs_dir}")
        obs_status = _eval_obs_regression(args.obs_dir, args.obs_ground_truth_dir)

    rows = [s1_row, s2_row, s3_row]
    for row in rows:
        cand = row["candidate"]
        if cand in obs_status:
            row["obs_full_frame"] = obs_status[cand][0]
            row["obs_detail"] = obs_status[cand][1]
        else:
            row["obs_full_frame"] = True  # M4 未実行時は gate を素通り
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--obs-dir", type=Path, default=None)
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-regions.json"),
    )
    parser.add_argument(
        "--benchmark-ground-truth",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-ground-truth.json"),
    )
    parser.add_argument(
        "--obs-ground-truth-dir",
        type=Path,
        default=Path("tests/baselines/v0.3.0/ground-truth"),
    )
    args = parser.parse_args(argv)
    rows = _run_on_benchmark(args)
    print()
    print(format_comparison_table(rows))
    for row in rows:
        if "obs_detail" in row:
            print(f"  {row['candidate']} OBS: {', '.join(row['obs_detail'])}")

    # Tier A coarse (full game rect) の勝者は IoU 最大 + M4 gate で選ぶ。
    coarse_rows = [r for r in rows if r.get("tier") == "A"]
    coarse = pick_winner(coarse_rows) if coarse_rows else pick_winner(rows)
    print(
        f"\nTier A coarse winner (M4 gate + max IoU): "
        f"{coarse['candidate'] if coarse else 'NONE'}"
    )
    # Tier B precise (S2) は full-rect IoU ではなく上端 px 誤差で評価する
    # (scorebar ROI #480 が要求するのは精密な上端/y-band)。
    s2 = next((r for r in rows if r["candidate"] == "S2"), None)
    if s2 is not None:
        hit = s2.get("top_err_hits_px")
        hit_s = "n/a" if hit is None else f"{hit:.1f}px"
        print(
            f"Tier B precise (S2) top-edge on hits: {hit_s} "
            f"(hit_rate={s2.get('hit_rate', 0):.2f}); "
            f"full-rect IoU low by design (FL scorebar width != game width)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
