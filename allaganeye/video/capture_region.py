"""Game capture region detection for overlay-heavy (VTuber) recordings (#753).

Normalized-coordinate region contract + geometry helpers + candidate
detectors (S1 variance / S2 scorebar-band / S3 blackout-overlap).
On standard OBS recordings every detector resolves to ``FULL_FRAME`` so
downstream brightness/scorebar behavior is unchanged (v0.3.0 baseline
bit-exact; see spec section 3.4 / M4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from allaganeye.video.probe_state import PresenceState


@dataclass(frozen=True)
class CaptureRegion:
    """Game capture rectangle in normalized [0,1] frame coordinates."""

    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    source: str = "fallback"  # "tierA" | "tierB" | "band" | "fallback"

    def clamp(self) -> CaptureRegion:
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return CaptureRegion(x, y, w, h, self.confidence, self.source)

    def is_full_frame(self) -> bool:
        """領域 = frame 全体か (OBS 縮退判定 / bit-exact 分岐に使用)。"""
        return self.x == 0.0 and self.y == 0.0 and self.w == 1.0 and self.h == 1.0

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


@dataclass(frozen=True)
class ScorebarLocalization:
    """FL scorebar 帯を 1920x1080 probe frame 内で局在化した結果 (P1, re-plan #753).

    座標はすべて probe px (inclusive)。consumer (P2) が /1920,/1080 で正規化する。
    """

    x_left: int
    x_right: int
    y_top: int
    y_bottom: int
    confidence: float


FULL_FRAME = CaptureRegion(0.0, 0.0, 1.0, 1.0, confidence=1.0, source="fallback")


def region_mean(frame: np.ndarray, region: CaptureRegion) -> float:
    """2D gray frame (H,W) を正規化矩形 *region* で crop し平均輝度を返す。

    crop が空になる場合も最低 1px に clamp する。整数次元 frame では
    FULL_FRAME のとき結果は ``float(frame.mean())`` と一致する (bit-exact 縮退)。
    """
    h, w = frame.shape[:2]
    x0 = max(0, min(round(region.x * w), w - 1))
    y0 = max(0, min(round(region.y * h), h - 1))
    x1 = max(x0 + 1, min(round((region.x + region.w) * w), w))
    y1 = max(y0 + 1, min(round((region.y + region.h) * h), h))
    return float(frame[y0:y1, x0:x1].mean())


def band_region_from_localization(
    loc: ScorebarLocalization, *, probe_w: int, probe_h: int
) -> CaptureRegion:
    """probe px の scorebar 局在化を正規化 scorebar 帯 ROI に変換する。

    検出 (brightness / motion) を測る最 clean 領域。`loc.confidence` を引き継ぎ
    `source="band"` を付ける。範囲外座標は clamp する。
    """
    x = loc.x_left / probe_w
    y = loc.y_top / probe_h
    w = (loc.x_right - loc.x_left) / probe_w
    h = (loc.y_bottom - loc.y_top) / probe_h
    return CaptureRegion(x, y, w, h, confidence=loc.confidence, source="band").clamp()


@dataclass
class RegionTimeline:
    """Coarse region (Pass 1) + per-segment precise regions (#480/#481).

    ``fallback_reason`` (#810) は band anchor 縮退の provenance:
    "anchor_error" (Stage 0 例外) / "consensus_miss" (consensus 不成立) /
    None (縮退なし)。free string (読み手は unknown 値を受容)。
    """

    coarse: CaptureRegion
    segments: list[tuple[tuple[float, float], CaptureRegion]] = field(
        default_factory=list
    )
    fallback_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "coarse": self.coarse.to_dict(),
            "segments": [
                {"time_range": [t0, t1], "region": r.to_dict()}
                for (t0, t1), r in self.segments
            ],
            "fallback_reason": self.fallback_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RegionTimeline:
        return cls(
            coarse=CaptureRegion.from_dict(d["coarse"]),
            segments=[
                (
                    (s["time_range"][0], s["time_range"][1]),
                    CaptureRegion.from_dict(s["region"]),
                )
                for s in d.get("segments", [])
            ],
            fallback_reason=d.get("fallback_reason"),
        )


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

_LOCALIZE_TARGET_RATIO = 2.0
"""confidence が 1.0 に達する emblem margin 倍率 (最弱 emblem の sat/edge が
閾値の TARGET 倍で満点)。clear な in-match frame で ~1.0 に出るよう選定。"""

_ANCHOR_Y_TOL = 60
"""at-anchor y 走査の許容幅 (probe px 片側)。anchor.y_top +- この値の範囲を走査する。

_CLUSTER_Y_TOL と同値にすることで consensus cluster 幅と整合させる。
実測: lobby FP (y~504) と in-match scorebar (y~0-20) の間隔は 480px 以上あり、
+- 60px の窓で完全分離できる。"""

_ANCHOR_X_IOU_MIN = 0.5
"""at-anchor x-range IoU の最小閾値。saturated run の x range と anchor の x range の
IoU がこの値未満のものは gate する。

x-IoU = intersection / union on the 1-D x intervals (x_left..x_right)。
0.5 は 50% 重複を要求し、x がずれた lobby 帯や重複しない偽帯を除去する。"""


def _scorebar_saturated_runs(band: np.ndarray, cv2) -> list[tuple[int, int]]:
    """band (Hb,W,3 uint8 RGB) の saturated column run を width-gate して全件返す。

    `detector._find_scorebar_horizontal_range` の per-pixel mask + col-ratio +
    gap-merge を共有しつつ、center-straddling 選択 (#803) を撤廃する。返す run は
    `_SCOREBAR_SCAN_MIN_WIDTH_PX`..`_SCOREBAR_SCAN_MAX_WIDTH_PX` の幅のもののみ。
    """
    from allaganeye.video.detector import (
        _SCOREBAR_SCAN_MAX_WIDTH_PX,
        _SCOREBAR_SCAN_MIN_WIDTH_PX,
        _saturated_column_runs,
    )

    runs: list[tuple[int, int]] = []
    for start, end in _saturated_column_runs(band, cv2):
        span_width = end - start + 1
        if _SCOREBAR_SCAN_MIN_WIDTH_PX <= span_width <= _SCOREBAR_SCAN_MAX_WIDTH_PX:
            runs.append((start, end))
    return runs


def _emblem_and_margin(
    frame: np.ndarray,
    positions: list[tuple[str, int, int, int, int]],
    cv2,
) -> float | None:
    """3点 emblem AND。全通過なら最弱 margin (min ratio>1.0)、不通過なら None。

    `detector._emblem_and_check` と同一の sat (bright pixel) / Sobel edge 計算を
    用いる (OBS parity は plan Task 7 で担保)。各 position は (name,x1,y1,x2,y2)。
    """
    from allaganeye.video.detector import (
        _EMBLEM_EDGE_THRESHOLD,
        _EMBLEM_SAT_THRESHOLD,
        _emblem_metrics,
    )

    min_ratio: float | None = None
    for _name, x1, y1, x2, y2 in positions:
        region = frame[y1:y2, x1:x2, :]
        if region.size == 0:
            return None
        mean_sat, edge_density = _emblem_metrics(region, cv2)
        if mean_sat <= _EMBLEM_SAT_THRESHOLD or edge_density <= _EMBLEM_EDGE_THRESHOLD:
            return None
        ratio = min(
            mean_sat / _EMBLEM_SAT_THRESHOLD,
            edge_density / _EMBLEM_EDGE_THRESHOLD,
        )
        min_ratio = ratio if min_ratio is None else min(min_ratio, ratio)
    return min_ratio


def _scan_scorebar_bands(
    frame: np.ndarray,
    *,
    y_start: int,
    y_stop: int,
    stride: int,
    x_gate: tuple[int, int] | None,
    band_h: int,
    W: int,
    H: int,
    cv2,
) -> tuple[float, int, int, int] | None:
    """Shared inner scanner for localize_scorebar and localize_scorebar_at_anchor.

    Scans y in range(y_start, y_stop, stride). For each band evaluates all
    width-gated saturated runs through the emblem 3-point AND filter.

    x_gate: if not None, a (x_left_anchor, x_right_anchor) pair; runs whose
    1-D x-interval IoU vs this gate is < _ANCHOR_X_IOU_MIN are skipped.

    Returns best (margin, x_left, x_right, y) tuple, or None if no candidate
    passes the filters. Does NOT import cv2 or validate frame shape -- callers
    are responsible for those checks.

    Uses _EMBLEM_RELATIVE_POSITIONS from detector for emblem position computation
    (same as the original localize_scorebar loop, bit-identical when x_gate=None
    and y range matches the original 0..y_max).
    """
    from allaganeye.video.detector import _EMBLEM_RELATIVE_POSITIONS

    best: tuple[float, int, int, int] | None = None  # (margin, x_left, x_right, y)
    for y in range(y_start, y_stop, stride):
        band = frame[y : y + band_h]
        for x_left, x_right in _scorebar_saturated_runs(band, cv2):
            # x-IoU gate: reject run if x overlap with anchor is insufficient.
            if x_gate is not None:
                ax_left, ax_right = x_gate
                inter_left = max(x_left, ax_left)
                inter_right = min(x_right, ax_right)
                inter = max(0, inter_right - inter_left)
                union = max(x_right, ax_right) - min(x_left, ax_left)
                if union <= 0 or inter / union < _ANCHOR_X_IOU_MIN:
                    continue
            bar_w = x_right - x_left
            positions: list[tuple[str, int, int, int, int]] = []
            valid = True
            for name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS:
                px1 = int(x_left + cx_rel * bar_w - hw_rel * bar_w)
                px2 = int(x_left + cx_rel * bar_w + hw_rel * bar_w)
                py1 = y + ey1
                py2 = y + ey2
                if px1 < 0 or px2 > W or py1 < 0 or py2 > H or px2 <= px1:
                    valid = False
                    break
                positions.append((name, px1, py1, px2, py2))
            if not valid:
                continue
            margin = _emblem_and_margin(frame, positions, cv2)
            if margin is not None and (best is None or margin > best[0]):
                best = (margin, x_left, x_right, y)
    return best


def localize_from_rgb_bytes(
    raw: bytes | None, *, height: int, width: int
) -> ScorebarLocalization | None:
    """RGB24 probe bytes を decode して :func:`localize_scorebar` にかける共有 helper.

    raw が None (probe 失敗) なら None を返す。probe 失敗と localizer miss を
    呼び出し側で区別したい場合は raw の None を先に判定すること
    (例: ``scorebar._localize_present_from_raw``)。呼び出し元 3 箇所
    (presence / scorebar / detector の帯 anchor) の reshape boilerplate を一元化し、
    probe 次元変更時の drift を防ぐ (PR #823 R3 dedup)。
    """
    if raw is None:
        return None
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
    return localize_scorebar(frame)


def localize_scorebar(
    frame: np.ndarray,
    *,
    stride: int = _BAND_SCAN_STRIDE,
    target_ratio: float = _LOCALIZE_TARGET_RATIO,
) -> ScorebarLocalization | None:
    """1920x1080 RGB frame から FL scorebar を位置独立に局在化する (P1, #753).

    y を stride 全走査し、各 band で width-gated 全 run に emblem 3点 AND をかけ、
    通過候補のうち emblem margin が最大の (run, y) を返す (best-hit)。best-hit に
    より y_top 精度が +-stride/2 に上がり confidence が最良整合の margin になる。
    試合外 / cv2 不在 / 形状不一致は None。OBS 分類 path からは呼ばれない
    (Additive、spec section 7)。
    """
    if target_ratio <= 1.0:
        raise ValueError("target_ratio must be > 1.0 (confidence denominator)")
    try:
        import cv2
    except ImportError:
        return None

    from allaganeye.video.detector import (
        _SCOREBAR_SCAN_Y_END,
        _SCOREBAR_SCAN_Y_START,
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W = _SCOREBAR_V2_PROBE_WIDTH
    H = _SCOREBAR_V2_PROBE_HEIGHT
    if frame.shape[:2] != (H, W):
        return None

    band_h = _SCOREBAR_SCAN_Y_END - _SCOREBAR_SCAN_Y_START
    y_max = int(H * _BAND_Y_MAX_FRAC)
    best = _scan_scorebar_bands(
        frame,
        y_start=0,
        y_stop=y_max,
        stride=stride,
        x_gate=None,
        band_h=band_h,
        W=W,
        H=H,
        cv2=cv2,
    )

    if best is None:
        return None
    margin, x_left, x_right, y = best
    confidence = max(0.0, min(1.0, (margin - 1.0) / (target_ratio - 1.0)))
    return ScorebarLocalization(
        x_left=x_left,
        x_right=x_right,
        y_top=y,
        y_bottom=y + band_h,
        confidence=confidence,
    )


def localize_scorebar_at_anchor(
    frame: np.ndarray,
    anchor: ScorebarLocalization,
    *,
    stride: int = _BAND_SCAN_STRIDE,
    target_ratio: float = _LOCALIZE_TARGET_RATIO,
) -> ScorebarLocalization | None:
    """1920x1080 RGB frame からアンカー位置周辺の FL scorebar を局在化する (#822).

    localize_scorebar の位置独立スキャンと同一の emblem 3 点 AND エンジンを
    anchor で絞り込んで適用する。これにより lobby FP (y 帯外) と x-range が
    大きくずれた偽帯を除去しつつ、full-scan が強い FP に敗北するケースを救済する。

    y スキャン域: band start が `max(0, anchor.y_top - _ANCHOR_Y_TOL)` から
    `anchor.y_top + _ANCHOR_Y_TOL` まで (stride 刻み、fencepost のため range stop は +stride)
    x gate: saturated run の x range と anchor x range の 1-D IoU >= _ANCHOR_X_IOU_MIN

    cv2 不在 / 形状不一致 / 候補なし は None。target_ratio <= 1.0 は ValueError。
    """
    if target_ratio <= 1.0:
        raise ValueError("target_ratio must be > 1.0 (confidence denominator)")
    try:
        import cv2
    except ImportError:
        return None

    from allaganeye.video.detector import (
        _SCOREBAR_SCAN_Y_END,
        _SCOREBAR_SCAN_Y_START,
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W = _SCOREBAR_V2_PROBE_WIDTH
    H = _SCOREBAR_V2_PROBE_HEIGHT
    if frame.shape[:2] != (H, W):
        return None

    band_h = _SCOREBAR_SCAN_Y_END - _SCOREBAR_SCAN_Y_START
    y_start = max(0, anchor.y_top - _ANCHOR_Y_TOL)
    # y_stop must extend so bands starting at anchor.y_top + _ANCHOR_Y_TOL are evaluated.
    # range(y_start, y_stop, stride) includes anchor.y_top + _ANCHOR_Y_TOL when
    # y_stop > anchor.y_top + _ANCHOR_Y_TOL, mirroring how y_max is used in localize_scorebar.
    y_stop = anchor.y_top + _ANCHOR_Y_TOL + stride
    # H clamp: 端 anchor でも band が frame 下端で欠けないようにする (latent guard)
    y_stop = min(y_stop, H - band_h + 1)
    x_gate = (anchor.x_left, anchor.x_right)

    best = _scan_scorebar_bands(
        frame,
        y_start=y_start,
        y_stop=y_stop,
        stride=stride,
        x_gate=x_gate,
        band_h=band_h,
        W=W,
        H=H,
        cv2=cv2,
    )

    if best is None:
        return None
    margin, x_left, x_right, y = best
    confidence = max(0.0, min(1.0, (margin - 1.0) / (target_ratio - 1.0)))
    return ScorebarLocalization(
        x_left=x_left,
        x_right=x_right,
        y_top=y,
        y_bottom=y + band_h,
        confidence=confidence,
    )


def localize_from_rgb_bytes_at_anchor(
    raw: bytes | None,
    anchor: ScorebarLocalization,
    *,
    height: int,
    width: int,
) -> ScorebarLocalization | None:
    """RGB24 probe bytes を decode して :func:`localize_scorebar_at_anchor` にかける helper.

    raw が None (probe 失敗) なら None を返す。localize_from_rgb_bytes の
    at-anchor 版: reshape boilerplate を共有しつつ anchor 制約を適用する (#822)。
    """
    if raw is None:
        return None
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
    return localize_scorebar_at_anchor(frame, anchor)


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


def _maximal_ones_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest all-ones axis-aligned rectangle in a binary mask (histogram stack).

    Returns ``(x0, y0, x1, y1)`` half-open (x1/y1 exclusive) of the maximum-area
    all-ones rectangle, or ``None`` when the mask has no set pixels.  O(H*W):
    per-row histogram heights + largest-rectangle-in-histogram with a sentinel.
    """
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int32)
    best_area = 0
    best: tuple[int, int, int, int] | None = None
    for y in range(h):
        heights = np.where(mask[y] > 0, heights + 1, 0)
        hh = heights.tolist()
        stack: list[int] = []
        x = 0
        while x <= w:
            cur = hh[x] if x < w else 0
            if not stack or hh[stack[-1]] <= cur:
                stack.append(x)
                x += 1
            else:
                top = stack.pop()
                height = hh[top]
                left = 0 if not stack else stack[-1] + 1
                width = x - left
                area = height * width
                if area > best_area:
                    best_area = area
                    best = (left, y - height + 1, left + width, y + 1)
    return best


def detect_mask_free_region(
    frames: list[np.ndarray],
    *,
    bright_thresh: float = _OVERLAP_BRIGHT,
    dark_thresh: float = _OVERLAP_DARK,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """Largest hole-free game rectangle for masked recordings (#753 masked-OBS).

    Refines S3 (``detect_region_blackout_overlap``): instead of the largest game
    *component bbox* (which can contain mask holes), returns the largest solid
    all-game *rectangle* (maximal all-ones rectangle over the game mask), so the
    measurement region excludes bright static masks composited over gameplay.

    game pixel = max brightness > ``bright_thresh`` AND min brightness <
    ``dark_thresh`` (brightens during play, darkens during a blackout).  Bright
    static masks never darken (min stays high) -> excluded.  Always-dark bars
    never brighten -> excluded.  Unmasked full-frame game -> every pixel is game
    -> snaps to FULL_FRAME.  Fewer than 2 frames, no game pixels, or a max
    rectangle below ``min_area_frac`` of the frame -> FULL_FRAME (safe degenerate:
    the masked-fallback caller treats FULL_FRAME as "no mask region found").
    """
    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    pmax = stack.max(axis=0)
    pmin = stack.min(axis=0)
    game_mask = ((pmax > bright_thresh) & (pmin < dark_thresh)).astype(np.uint8)
    rect = _maximal_ones_rectangle(game_mask)
    if rect is None:
        return FULL_FRAME
    x0, y0, x1, y1 = rect
    h, w = game_mask.shape
    if (x1 - x0) * (y1 - y0) < min_area_frac * w * h:
        return FULL_FRAME
    region = CaptureRegion(
        x0 / w,
        y0 / h,
        (x1 - x0) / w,
        (y1 - y0) / h,
        confidence=0.8,
        source="tierA",
    ).clamp()
    return _maybe_snap_full_frame(region)


_BAND_CONSENSUS_MIN_HITS = 2
"""帯 consensus に必要な最小局在化成功数。これ未満は FULL_FRAME 縮退。"""

_CLUSTER_Y_TOL = 60
"""y_top クラスタリングの許容差 (probe px)。これ以内の y_top は同一クラスタ。

localize は per-frame noisy で、真の scorebar (y_top~0) と下部 HUD 誤検出
(y_top~540-582) が混在しうる。両者を別クラスタに分け dominant を選ぶための
許容差。scorebar 帯高 ~45px に対し十分広く、真クラスタ内の +-stride ばらつき
(18 vs 20 等) は 1 クラスタにまとめる。
"""


def consensus_scorebar_localization(
    *,
    duration: float,
    localize_fn: Callable[[float], ScorebarLocalization | None | PresenceState],
    num_samples: int = 8,
    min_hits: int = _BAND_CONSENSUS_MIN_HITS,
) -> ScorebarLocalization | None:
    """疎な多フレーム localize の dominant-cluster consensus core。

    *localize_fn* は timestamp -> ScorebarLocalization|None|PresenceState。動画 I/O は
    呼び出し側が bind する (テストは合成関数を注入)。成功局在化が *min_hits* 未満なら
    None (OBS / 局在化不能時の安全縮退)。成功時は hits を y_top で
    `_CLUSTER_Y_TOL` クラスタリングし、最大クラスタ (同数なら平均 confidence) の各座標
    median を `ScorebarLocalization` として返す。これにより真の scorebar (y_top~0) と
    下部 HUD 誤検出が混在しても between-clusters の garbage band を避ける
    (spec sec. 3.6)。

    *localize_fn* の戻り値 sentinel:
    - ``PresenceState.UNKNOWN`` のみが decode 失敗 sentinel として有効 (hit/miss どちらにも
      数えない、consensus から除外)。他の PresenceState 値は ScorebarLocalization でないため
      hit としてカウントされず、実質 miss 扱いとなる。

    Returns ``None`` when:
    - *duration* <= 0 or *num_samples* < 1
    - fewer than *min_hits* successful localizations
    - dominant cluster has fewer than *min_hits* members
    """
    if duration <= 0 or num_samples < 1:
        return None
    times = [duration * (i + 1) / (num_samples + 1) for i in range(num_samples)]
    hits = [
        loc for t in times if isinstance((loc := localize_fn(t)), ScorebarLocalization)
    ]
    if len(hits) < min_hits:
        return None
    # localize is per-frame noisy (upper-half best-hit scan can lock onto lower
    # HUD; spec sec. 3.6). Cluster hits by y_top and take the largest cluster
    # (true scorebar is dominant across in-match samples), so a noise-mixed
    # median cannot produce a between-clusters garbage band.
    hits_sorted = sorted(hits, key=lambda h: h.y_top)
    clusters: list[list[ScorebarLocalization]] = []
    for h in hits_sorted:
        if clusters and h.y_top - clusters[-1][-1].y_top <= _CLUSTER_Y_TOL:
            clusters[-1].append(h)
        else:
            clusters.append([h])
    best = max(
        clusters,
        key=lambda c: (len(c), sum(h.confidence for h in c) / len(c)),
    )
    if len(best) < min_hits:
        return None
    return ScorebarLocalization(
        x_left=int(np.median([h.x_left for h in best])),
        x_right=int(np.median([h.x_right for h in best])),
        y_top=int(np.median([h.y_top for h in best])),
        y_bottom=int(np.median([h.y_bottom for h in best])),
        confidence=float(np.median([h.confidence for h in best])),
    )


def detect_scorebar_band_region(
    *,
    duration: float,
    probe_w: int,
    probe_h: int,
    localize_fn: Callable[[float], ScorebarLocalization | None | PresenceState],
    num_samples: int = 8,
    min_hits: int = _BAND_CONSENSUS_MIN_HITS,
) -> CaptureRegion:
    """疎な多フレーム localize の dominant-cluster consensus で安定 scorebar 帯 ROI を返す。

    `consensus_scorebar_localization` に consensus 計算を委譲し、結果を
    `band_region_from_localization` で正規化帯 ROI に変換する。縮退時は FULL_FRAME。
    """
    loc = consensus_scorebar_localization(
        duration=duration,
        localize_fn=localize_fn,
        num_samples=num_samples,
        min_hits=min_hits,
    )
    return (
        FULL_FRAME
        if loc is None
        else band_region_from_localization(loc, probe_w=probe_w, probe_h=probe_h)
    )
