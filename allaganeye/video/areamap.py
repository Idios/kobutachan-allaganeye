"""Area-map seed detection + per-match consensus (提案モード専用、Refs #481).

This module provides:
- ``detect_areamap_seed``: refs-free single-frame-set detector (ported from
  ``scripts/areamap_poc.py`` temporal-stability / static-component logic).
- ``resolve_match_regions``: per-match windowed consensus over ``detect_areamap_seed``.

cv2 is lazy-imported so that importing this module does NOT fail in environments
without opencv-python installed (same convention as capture_region.py).
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from allaganeye.video.capture_region import CaptureRegion

# detector 非変更の制約下での意図的な private 利用 (#481 plan D1):
# detector.py に公開 alias を追加できないため scorebar.py と同様の cross-module
# private import を採用する (repo 前例: scorebar.py <-> detector.py)。
from allaganeye.video.detector import _probe_frame_rgb_hires

# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

DetectResult = tuple[float, float, float, float, float] | None
"""(x, y, w, h, score) in normalized [0,1] coords, or None if not detected."""

DetectFn = Callable[[list[np.ndarray]], DetectResult]

# ---------------------------------------------------------------------------
# Constants (ported from scripts/areamap_poc.py Candidate A)
# ---------------------------------------------------------------------------

_FRAME_W = 1920
_FRAME_H = 1080

A_STD_THRESH: float = 12.0
A_MIN_AREA_FRAC: float = 0.03
A_AR_RANGE: tuple[float, float] = (0.6, 2.0)
A_MIN_EDGE_DENSITY: float = 0.05
A_MAX_DIM_FRAC: float = 0.95  # whole-frame blob guard (calm-scene degenerate case)

# --- seed-selection scoring (#481 実データ再設計) ---------------------------
# 旧: max edge density。実 OBS/VTuber 動画では チャット/パーティ欄など
# テキスト由来の高 edge density UI blob が最大となり誤選択していた (右側大 blob 問題)。
# 実測 (5 GT case) で エリアマップ (半透過 戦場全体図 overlay) は component 内 輝度が:
#   - 中庸に明るい帯 (mean_lum ~120-132) に集中
#   - 分散が低い (std_lum ~30-40) -- 一様な半透過パネル
# 一方 UI パネル (チャット/スコアボード/アバター) は高コントラスト文字/画像により
#   std_lum >= 55、mean_lum は極端 (暗い ~50-80 or 明るすぎ ~180-210) に振れる。
# よって「幾何・テクスチャ特徴」(component 内 色・輝度統計) による **soft scoring** に置換:
#   score = std_lum
#         + (輝度が [_SEED_LUM_FLOOR, _SEED_LUM_CEIL] を外れた距離)
#         + _SEED_STD_LUM_PENALTY * max(0, std_lum - _SEED_STD_LUM_MAX)
#   最小 score を seed に選ぶ。hard gate ではなく soft penalty にするのは、候補が
#   1 つしか無い退化ケース (D1 合成テスト等) でも必ず 1 つ返すため。複数候補時は
#   overlay 本体 (低 std_lum + 輝度帯内 penalty 0) が UI blob (高 std_lum / 極端輝度)
#   に勝つ。position prior・refs / map 照合は使わない (制約: temporal-stability のみ + 位置独立)。
_SEED_LUM_FLOOR: float = 105.0
_SEED_LUM_CEIL: float = 175.0
_SEED_STD_LUM_MAX: float = 50.0
_SEED_STD_LUM_PENALTY: float = 5.0


# ---------------------------------------------------------------------------
# Internal helpers (also re-exported to areamap_poc.py)
# ---------------------------------------------------------------------------


def _temporal_stack(frames: list[np.ndarray]):
    """Return (median_gray, std_gray) from an RGB frame list.

    Ported from ``scripts/areamap_poc.py::_temporal_stack``.
    """
    cv2 = _import_cv2()  # lazy
    grays = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) for f in frames]
    stack = np.stack(grays)
    return np.median(stack, axis=0), stack.std(axis=0)


def _static_components(
    med: np.ndarray, std: np.ndarray
) -> list[tuple[int, int, int, int, float]]:
    """(x, y, w, h, edge_density) candidates from the static-overlay mask.

    Ported from ``scripts/areamap_poc.py::_static_components``.
    """
    cv2 = _import_cv2()  # lazy
    h_img, w_img = med.shape
    static = (std < A_STD_THRESH).astype(np.uint8)
    kernel = np.ones((9, 9), np.uint8)
    static = cv2.morphologyEx(static, cv2.MORPH_CLOSE, kernel)
    static = cv2.morphologyEx(static, cv2.MORPH_OPEN, kernel)
    n, _labels, stats, _ = cv2.connectedComponentsWithStats(static)
    out: list[tuple[int, int, int, int, float]] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < A_MIN_AREA_FRAC * w_img * h_img:
            continue
        # calm-scene degeneracy guard: a whole-frame blob is never the areamap window
        if w >= A_MAX_DIM_FRAC * w_img and h >= A_MAX_DIM_FRAC * h_img:
            continue
        if not (A_AR_RANGE[0] <= w / max(h, 1) <= A_AR_RANGE[1]):
            continue
        roi = med[y : y + h, x : x + w].astype(np.uint8)
        edges = cv2.Canny(roi, 50, 150)
        density = float((edges > 0).mean())
        if density < A_MIN_EDGE_DENSITY:
            continue
        out.append((x, y, w, h, density))
    return out


def _component_luma_stats(
    frames: list[np.ndarray],
    med: np.ndarray,
    std: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> tuple[float, float]:
    """Return ``(mean_lum, std_lum)`` over the static-component pixels inside *bbox*.

    幾何・テクスチャ scoring 用 (#481)。``_static_components`` と同一 mask
    (同一 morphology) を再構築し、``bbox`` に対応する連結成分の pixel だけを
    temporal-median RGB から抽出して輝度統計を取る。bbox 全体でなく成分 mask に
    限定するのは、隣接背景を混ぜず overlay 本体の一様性を測るため。

    ``_static_components`` は成分 label を返さない (compare pin 固定のため signature
    非変更) ので、ここで再度 connectedComponents を実行し bbox 一致で成分を特定する。
    """
    cv2 = _import_cv2()  # lazy
    bx, by, bw, bh = bbox
    static = (std < A_STD_THRESH).astype(np.uint8)
    kernel = np.ones((9, 9), np.uint8)
    static = cv2.morphologyEx(static, cv2.MORPH_CLOSE, kernel)
    static = cv2.morphologyEx(static, cv2.MORPH_OPEN, kernel)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(static)
    # bbox 一致 (x, y, w, h) で成分 index を特定
    comp_idx = None
    for i in range(1, n):
        x, y, w, h, _area = stats[i]
        if int(x) == bx and int(y) == by and int(w) == bw and int(h) == bh:
            comp_idx = i
            break
    med_rgb = np.median(np.stack(frames).astype(np.float32), axis=0)
    roi_rgb = med_rgb[by : by + bh, bx : bx + bw]
    if comp_idx is None:
        # 一致成分が見つからない (理論上起きない) 場合は bbox 全体で近似
        px = roi_rgb.reshape(-1, 3)
    else:
        mask = labels[by : by + bh, bx : bx + bw] == comp_idx
        px = roi_rgb[mask] if mask.any() else roi_rgb.reshape(-1, 3)
    return float(px.mean()), float(px.std())


# ---------------------------------------------------------------------------
# Public API: detect_areamap_seed
# ---------------------------------------------------------------------------


def detect_areamap_seed(frames: list[np.ndarray]) -> DetectResult:
    """Detect the area-map seed region from a temporal stack of RGB frames.

    Refs-free detector: uses temporal stability + static connected components.

    Selection scoring (#481 実データ再設計): 旧実装は「最大 edge density」だったが、
    実 OBS/VTuber 動画では チャット/パーティ欄など高 edge density の UI blob を
    誤選択していた。エリアマップ (半透過 戦場全体図 overlay) は component 内 輝度が
    中庸に明るい帯 (``_SEED_LUM_FLOOR``..``_SEED_LUM_CEIL``) に集中し、輝度分散が低い
    (std_lum ~30-40) という 幾何・テクスチャ特徴を持つ。この特徴を soft penalty score
    (``_seed_score`` 参照) にした最小 score の成分を seed とする。soft penalty のため
    候補が 1 つしか無い退化ケースでも必ず 1 つ返す。position prior・refs / map 照合は
    使わない (制約: temporal-stability のみ + 位置独立)。

    Args:
        frames: List of (1080, 1920, 3) uint8 RGB frames.  At least 3 required.

    Returns:
        ``(x, y, w, h, score)`` in normalized [0,1] coordinates, or ``None``.
        ``score`` は該当成分の edge density (下流表示互換のため据え置き)。
    """
    if len(frames) < 3:
        return None
    med, std = _temporal_stack(frames)
    h_img, w_img = med.shape
    cands = _static_components(med, std)
    if not cands:
        return None
    # 各候補の component 内 輝度統計で soft scoring。最小 score を seed に選ぶ。
    best: tuple[float, tuple[int, int, int, int, float]] | None = None
    for x, y, w, h, density in cands:
        mean_lum, std_lum = _component_luma_stats(frames, med, std, (x, y, w, h))
        sc = _seed_score(mean_lum, std_lum)
        if best is None or sc < best[0]:
            best = (sc, (x, y, w, h, density))
    assert best is not None  # cands 非空なので必ず 1 つ選ばれる
    x, y, w, h, density = best[1]
    return (x / w_img, y / h_img, w / w_img, h / h_img, density)


def _seed_score(mean_lum: float, std_lum: float) -> float:
    """Seed selection score (lower is better, #481).

    エリアマップ overlay = 低 std_lum + 輝度帯 [``_SEED_LUM_FLOOR``,
    ``_SEED_LUM_CEIL``] 内。score は std_lum を基点に、輝度帯外れ距離 + std_lum
    超過分 (``_SEED_STD_LUM_PENALTY`` 倍) を加算した soft penalty。
    """
    lum_penalty = max(0.0, mean_lum - _SEED_LUM_CEIL) + max(
        0.0, _SEED_LUM_FLOOR - mean_lum
    )
    std_penalty = _SEED_STD_LUM_PENALTY * max(0.0, std_lum - _SEED_STD_LUM_MAX)
    return std_lum + lum_penalty + std_penalty


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchRegionResult:
    """Per-match consensus output from ``resolve_match_regions``."""

    match_index: int
    region: CaptureRegion  # 正規化。source="auto", confidence=一致 window 率
    scattered: bool  # window 間で bbox が揺れた (warning 対象)


# ---------------------------------------------------------------------------
# IoU helper
# ---------------------------------------------------------------------------


def _iou_xywh(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1 = ax0 + aw, ay0 + ah
    bx1, by1 = bx0 + bw, by0 + bh
    ix = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Public API: resolve_match_regions
# ---------------------------------------------------------------------------


def resolve_match_regions(
    video_path: Path,
    matches: list[tuple[int, float, float]],  # (match_index, start_time, end_time)
    *,
    windows: int = 3,
    frames_per_window: int = 5,
    edge_margin: float = 60.0,
    iou_cluster: float = 0.8,
    probe: Callable[[Path, float], bytes | None] | None = None,
    detect: DetectFn | None = None,
) -> tuple[list[MatchRegionResult], list[str]]:
    """試合ごとに windows 個の時間窓で検出し、IoU >= iou_cluster の多数派を採用。

    consensus 規約 (spec sec.8):
    - 多数派 cluster (>= ceil(windows/2)) の要素ごと中央値 bbox を採用
    - confidence = 多数派 window 数 / 検出成功 window 数
    - 非多数派 window が 1 つでもあれば scattered=True (warning)
    - 全 window 未検出 -> その match は結果 list に含めない
    戻り値第 2 要素は表示用 warning 文字列 list。
    """
    if probe is None:
        probe = _probe_frame_rgb_hires
    if detect is None:
        detect = detect_areamap_seed

    results: list[MatchRegionResult] = []
    warn_msgs: list[str] = []

    for match_index, start_time, end_time in matches:
        # --- サンプリング時刻を生成 ---
        usable_start = start_time + edge_margin
        usable_end = end_time - edge_margin
        min_usable_span = windows * frames_per_window * 2.0

        if usable_end - usable_start < min_usable_span:
            # マージン不足: [start_time, end_time] を均等分割
            usable_start = start_time
            usable_end = end_time

        # windows 個の中心時刻を均等配置
        if windows == 1:
            window_centers = [(usable_start + usable_end) / 2.0]
        else:
            step = (usable_end - usable_start) / (windows - 1)
            window_centers = [usable_start + i * step for i in range(windows)]

        # 各 window で frames_per_window フレームをサンプリング
        window_results: list[DetectResult] = []
        for center in window_centers:
            half_span = (frames_per_window - 1) * 2.0
            ts_start = center - half_span / 2.0
            ts_end = center + half_span / 2.0
            # 境界クランプ
            ts_start = max(start_time, ts_start)
            ts_end = min(end_time, ts_end)
            if frames_per_window == 1:
                timestamps = [center]
            else:
                timestamps = [
                    ts_start + i * (ts_end - ts_start) / (frames_per_window - 1)
                    for i in range(frames_per_window)
                ]
            frames: list[np.ndarray] = []
            for t in timestamps:
                raw = probe(video_path, t)
                if raw is None:
                    continue
                arr = np.frombuffer(raw, dtype=np.uint8).reshape(_FRAME_H, _FRAME_W, 3)
                frames.append(arr)
            det = detect(frames)
            window_results.append(det)

        # --- consensus ---
        valid_results = [r for r in window_results if r is not None]
        valid_count = len(valid_results)

        if valid_count == 0:
            warn_msgs.append(
                f"match {match_index}: all {windows} windows produced no detection -- skipped"
            )
            continue

        # IoU クラスタリング: valid_results の中から IoU >= iou_cluster の最大クラスタを選ぶ
        # greedy: 最初の要素を seed とするクラスタを試みるのではなく
        # 全ペアを比較して最大クラスタを見つける
        best_cluster: list[tuple[float, float, float, float, float]] = []
        for i, seed in enumerate(valid_results):
            cluster = [seed]
            seed_box = seed[:4]
            for j, other in enumerate(valid_results):
                if i == j:
                    continue
                other_box = other[:4]
                if _iou_xywh(seed_box, other_box) >= iou_cluster:
                    cluster.append(other)
            if len(cluster) > len(best_cluster):
                best_cluster = cluster

        majority_thresh = math.ceil(windows / 2)
        if len(best_cluster) < majority_thresh:
            # 多数派クラスタなし: 散布している -> 全 miss 扱いと同様 skip
            # (全 miss ではないが多数派なし = 信頼度ゼロ)
            warn_msgs.append(
                f"match {match_index}: no majority cluster (best={len(best_cluster)}/{windows}) -- skipped"
            )
            continue

        # 代表 bbox = 要素ごと median
        xs = [r[0] for r in best_cluster]
        ys = [r[1] for r in best_cluster]
        ws = [r[2] for r in best_cluster]
        hs = [r[3] for r in best_cluster]
        med_x = statistics.median(xs)
        med_y = statistics.median(ys)
        med_w = statistics.median(ws)
        med_h = statistics.median(hs)

        confidence = len(best_cluster) / valid_count
        scattered = (
            len(best_cluster) < valid_count
        )  # 外れ window が 1 つでもあれば True

        if scattered:
            warn_msgs.append(
                f"match {match_index}: {valid_count - len(best_cluster)} window(s) outside cluster -- possible map movement"
            )

        region = CaptureRegion(
            x=med_x,
            y=med_y,
            w=med_w,
            h=med_h,
            confidence=confidence,
            source="auto",
        ).clamp()
        results.append(
            MatchRegionResult(
                match_index=match_index,
                region=region,
                scattered=scattered,
            )
        )

    return results, warn_msgs


# ---------------------------------------------------------------------------
# Lazy cv2 import helper
# ---------------------------------------------------------------------------


def _import_cv2():
    """Lazy-import cv2, raising ImportError with a friendly message if absent."""
    try:
        import cv2  # type: ignore[import-untyped]

        return cv2
    except ImportError as e:
        raise ImportError(
            "opencv-python is required for areamap detection. "
            "Install it with: pip install opencv-python-headless"
        ) from e
