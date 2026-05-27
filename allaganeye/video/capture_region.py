"""Game capture region detection for overlay-heavy (VTuber) recordings (#753).

Normalized-coordinate region contract + geometry helpers + candidate
detectors (S1 variance / S2 scorebar-band / S3 blackout-overlap).
On standard OBS recordings every detector resolves to ``FULL_FRAME`` so
downstream brightness/scorebar behavior is unchanged (v0.3.0 baseline
bit-exact; see spec section 3.4 / M4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CaptureRegion:
    """Game capture rectangle in normalized [0,1] frame coordinates."""

    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    source: str = "fallback"  # "tierA" | "tierB" | "fallback"

    def clamp(self) -> CaptureRegion:
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return CaptureRegion(x, y, w, h, self.confidence, self.source)

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "confidence": self.confidence,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CaptureRegion:
        return cls(
            d["x"],
            d["y"],
            d["w"],
            d["h"],
            d.get("confidence", 1.0),
            d.get("source", "fallback"),
        )


FULL_FRAME = CaptureRegion(0.0, 0.0, 1.0, 1.0, confidence=1.0, source="fallback")


@dataclass
class RegionTimeline:
    """Coarse region (Pass 1) + per-segment precise regions (#480/#481)."""

    coarse: CaptureRegion
    segments: list[tuple[tuple[float, float], CaptureRegion]] = field(
        default_factory=list
    )

    def to_dict(self) -> dict:
        return {
            "coarse": self.coarse.to_dict(),
            "segments": [
                {"time_range": [t0, t1], "region": r.to_dict()}
                for (t0, t1), r in self.segments
            ],
        }


_SNAP_FULL_FRAME_WH = 0.92
"""w と h が共にこの比率以上なら FULL_FRAME に snap。

OBS 録画では game = frame 全体のため検出器は frame 全域に近い矩形を返す。
わずかな端の欠けで IoU<1.0 になり baseline を壊すのを防ぐため full-frame
に snap し、Pass 1 輝度を現行と数値一致させる (spec section 3.4 / M4)。
"""


def iou(a: CaptureRegion, b: CaptureRegion) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def top_edge_error_px(a: CaptureRegion, b: CaptureRegion, frame_h: int) -> float:
    return abs(a.y - b.y) * frame_h


def _maybe_snap_full_frame(region: CaptureRegion) -> CaptureRegion:
    if region.w >= _SNAP_FULL_FRAME_WH and region.h >= _SNAP_FULL_FRAME_WH:
        return FULL_FRAME
    return region


_VAR_THRESHOLD = 80.0
"""グレースケール時間分散がこの値超で「動きあり」画素とみなす (tunable)。"""

_MIN_REGION_AREA_FRAC = 0.08
"""検出矩形の最小面積比。これ未満は誤検出として FULL_FRAME に fallback。"""


def _largest_component_region(
    mask: np.ndarray,
    *,
    min_area_frac: float,
    source: str,
    confidence: float | None = None,
) -> CaptureRegion:
    """連結成分の最大 bbox を正規化 CaptureRegion 化 (S1/S3 共通)。

    *mask* は uint8 2D。最大の非背景成分の bbox を返す。成分なし / 面積が
    min_area_frac 未満 / frame 全域に近い場合は FULL_FRAME。confidence が
    None なら成分の充填率 (画素数/bbox面積) を使う。
    """
    import cv2

    h, w = mask.shape
    n, _labels, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return FULL_FRAME
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = 1 + int(np.argmax(areas))
    bx, by = int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP])
    bw, bh = int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT])
    if bw * bh < min_area_frac * w * h:
        return FULL_FRAME
    conf = float(areas[idx - 1]) / (bw * bh) if confidence is None else confidence
    region = CaptureRegion(
        bx / w, by / h, bw / w, bh / h, confidence=conf, source=source
    ).clamp()
    return _maybe_snap_full_frame(region)


def detect_region_variance(
    frames: list[np.ndarray],
    *,
    var_threshold: float = _VAR_THRESHOLD,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """S1: 時間分散の最大連結成分を game 領域とみなす (Tier A coarse)。

    *frames* は同形状の 2D グレースケール (H,W) uint8。OBS 録画は全域が
    動くため最大成分が frame 全域 -> FULL_FRAME に snap。分散が無ければ
    (静止) FULL_FRAME に fallback。
    """
    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    var = stack.var(axis=0)
    mask = (var > var_threshold).astype(np.uint8)
    return _largest_component_region(mask, min_area_frac=min_area_frac, source="tierA")


_OVERLAP_BRIGHT = 60.0
"""画素の最大輝度がこの値を超えれば「試合中は明るい画素」とみなす下限しきい (tunable)。"""

_OVERLAP_DARK = 20.0
"""「暗転で暗くなる」とみなす画素の最小輝度しきい (tunable)。"""


_BAND_SCAN_STRIDE = 6
"""y 方向の走査刻み (px)。scorebar 帯の高さ ~45px に対し十分細かい。"""

_BAND_Y_MAX_FRAC = 0.55
"""scorebar を探す y の上限 (frame 高さ比)。game は frame 上〜中央寄り。"""

_GAME_ASPECT = 16.0 / 9.0
"""FF14 game capture のアスペクト比 (帯幅から game 高さを逆算)。"""


def detect_region_scorebar_band(
    frame: np.ndarray,
    *,
    stride: int = _BAND_SCAN_STRIDE,
) -> CaptureRegion | None:
    """S2: FL scorebar 帯を全 y で探し、game 矩形を逆算 (Tier B precise)。

    *frame* は 1920x1080 RGB (H,W,3) uint8。検出帯を GC 紋章 3 点 AND で
    FL と検証してから返す。FL 帯が見つからなければ None (試合外フレーム
    や opencv 未導入)。OBS の全体縮退は coarse 検出器 (S1/S3) の責務であり、
    scorebar 幅 > detector._SCOREBAR_SCAN_MAX_WIDTH_PX (1440, #806) の広帯は None。
    """
    try:
        import cv2
    except ImportError:
        return None
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_WIDTH,
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_SCAN_Y_START,
        _SCOREBAR_SCAN_Y_END,
        _EMBLEM_RELATIVE_POSITIONS,
        _emblem_and_check,
        _find_scorebar_horizontal_range,
    )

    H = _SCOREBAR_V2_PROBE_HEIGHT
    W = _SCOREBAR_V2_PROBE_WIDTH
    if frame.shape[:2] != (H, W):
        return None
    # _find_scorebar_horizontal_range は内部で y=_SCOREBAR_SCAN_Y_START.._END を
    # 走査するため、その窓高に合わせて band を切り出す (定数 drift 防止)。
    band_h = _SCOREBAR_SCAN_Y_END - _SCOREBAR_SCAN_Y_START
    y_max = int(H * _BAND_Y_MAX_FRAC)
    shifted = np.zeros_like(frame)
    for y in range(0, y_max, stride):
        shifted[band_h:] = 0
        shifted[0:band_h] = frame[y : y + band_h]
        span = _find_scorebar_horizontal_range(shifted.tobytes())
        if span is None:
            continue
        x_left, x_right = span
        bar_w = x_right - x_left
        positions = [
            (
                name,
                int(x_left + cx_rel * bar_w - hw_rel * bar_w),
                y + ey1,
                int(x_left + cx_rel * bar_w + hw_rel * bar_w),
                y + ey2,
            )
            for name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS
        ]
        if not _emblem_and_check(frame, positions, f"band y={y}", cv2):
            continue
        gw = bar_w / W
        gx = x_left / W
        gy = y / H
        gh = (bar_w / _GAME_ASPECT) / H
        region = CaptureRegion(gx, gy, gw, gh, confidence=0.9, source="tierB").clamp()
        return region
    return None


def detect_region_blackout_overlap(
    frames: list[np.ndarray],
    *,
    bright_thresh: float = _OVERLAP_BRIGHT,
    dark_thresh: float = _OVERLAP_DARK,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """S3: 「明るい時もあるが暗転で暗くなる」画素 = game 領域 (spec finding #4)。

    overlay は常時明るい (min が下がらない) ため除外される。OBS は全画面が
    暗転する (mask が全域) -> FULL_FRAME。
    """
    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    pmax = stack.max(axis=0)
    pmin = stack.min(axis=0)
    mask = ((pmax > bright_thresh) & (pmin < dark_thresh)).astype(np.uint8)
    return _largest_component_region(
        mask, min_area_frac=min_area_frac, source="tierA", confidence=0.8
    )
