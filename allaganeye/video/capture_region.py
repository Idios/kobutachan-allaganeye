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

_LOCALIZE_TARGET_RATIO = 2.0
"""confidence が 1.0 に達する emblem margin 倍率 (最弱 emblem の sat/edge が
閾値の TARGET 倍で満点)。clear な in-match frame で ~1.0 に出るよう選定。"""


def _scorebar_saturated_runs(band: np.ndarray, cv2) -> list[tuple[int, int]]:
    """band (Hb,W,3 uint8 RGB) の saturated column run を width-gate して全件返す。

    `detector._find_scorebar_horizontal_range` の per-pixel mask + col-ratio +
    gap-merge を共有しつつ、center-straddling 選択 (#803) を撤廃する。返す run は
    `_SCOREBAR_SCAN_MIN_WIDTH_PX`..`_SCOREBAR_SCAN_MAX_WIDTH_PX` の幅のもののみ。
    """
    from allaganeye.video.detector import (
        _SCOREBAR_SCAN_COL_RATIO,
        _SCOREBAR_SCAN_MAX_GAP_PX,
        _SCOREBAR_SCAN_MAX_WIDTH_PX,
        _SCOREBAR_SCAN_MIN_WIDTH_PX,
        _SCOREBAR_SCAN_SAT_THRESHOLD,
        _SCOREBAR_SCAN_VAL_THRESHOLD,
    )

    bgr = cv2.cvtColor(band, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    pixel_mask = (sat > _SCOREBAR_SCAN_SAT_THRESHOLD) & (
        val > _SCOREBAR_SCAN_VAL_THRESHOLD
    )
    col_saturated = pixel_mask.mean(axis=0) >= _SCOREBAR_SCAN_COL_RATIO

    width = band.shape[1]
    raw_runs: list[tuple[int, int]] = []
    i = 0
    while i < width:
        if col_saturated[i]:
            j = i
            while j < width and col_saturated[j]:
                j += 1
            raw_runs.append((i, j - 1))
            i = j
        else:
            i += 1

    if not raw_runs:
        return []

    merged: list[tuple[int, int]] = [raw_runs[0]]
    for start, end in raw_runs[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end - 1 <= _SCOREBAR_SCAN_MAX_GAP_PX:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    runs: list[tuple[int, int]] = []
    for start, end in merged:
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
    )

    min_ratio: float | None = None
    for _name, x1, y1, x2, y2 in positions:
        region = frame[y1:y2, x1:x2, :]
        if region.size == 0:
            return None
        bgr = cv2.cvtColor(region, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        val = hsv[:, :, 2].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)
        bright_mask = val > 30
        if bright_mask.sum() > 5:
            mean_sat = float(sat[bright_mask].mean())
        else:
            mean_sat = 0.0

        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edge_density = float(np.sqrt(sobel_x**2 + sobel_y**2).mean())

        if mean_sat <= _EMBLEM_SAT_THRESHOLD or edge_density <= _EMBLEM_EDGE_THRESHOLD:
            return None
        ratio = min(
            mean_sat / _EMBLEM_SAT_THRESHOLD,
            edge_density / _EMBLEM_EDGE_THRESHOLD,
        )
        min_ratio = ratio if min_ratio is None else min(min_ratio, ratio)
    return min_ratio


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
        _EMBLEM_RELATIVE_POSITIONS,
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
    best: tuple[float, int, int, int] | None = None  # (margin, x_left, x_right, y)
    for y in range(0, y_max, stride):
        band = frame[y : y + band_h]
        for x_left, x_right in _scorebar_saturated_runs(band, cv2):
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


_BAND_CONSENSUS_MIN_HITS = 2
"""帯 consensus に必要な最小局在化成功数。これ未満は FULL_FRAME 縮退。"""

_CLUSTER_Y_TOL = 60
"""y_top クラスタリングの許容差 (probe px)。これ以内の y_top は同一クラスタ。

localize は per-frame noisy で、真の scorebar (y_top~0) と下部 HUD 誤検出
(y_top~540-582) が混在しうる。両者を別クラスタに分け dominant を選ぶための
許容差。scorebar 帯高 ~45px に対し十分広く、真クラスタ内の +-stride ばらつき
(18 vs 20 等) は 1 クラスタにまとめる。
"""


def detect_scorebar_band_region(
    *,
    duration: float,
    probe_w: int,
    probe_h: int,
    localize_fn: Callable[[float], ScorebarLocalization | None],
    num_samples: int = 8,
    min_hits: int = _BAND_CONSENSUS_MIN_HITS,
) -> CaptureRegion:
    """疎な多フレーム localize の dominant-cluster consensus で安定 scorebar 帯 ROI を返す。

    *localize_fn* は timestamp -> ScorebarLocalization|None。動画 I/O は呼び出し側が
    bind する (テストは合成関数を注入)。成功局在化が *min_hits* 未満なら FULL_FRAME
    (OBS / 局在化不能時の安全縮退)。成功時は hits を y_top で `_CLUSTER_Y_TOL`
    クラスタリングし、最大クラスタ (同数なら平均 confidence) の各座標 median を取り
    `band_region_from_localization` で正規化帯 ROI に変換する。これにより真の
    scorebar (y_top~0) と下部 HUD 誤検出が混在しても between-clusters の garbage
    band を避ける (spec section 3.6)。
    """
    if duration <= 0 or num_samples < 1:
        return FULL_FRAME
    times = [duration * (i + 1) / (num_samples + 1) for i in range(num_samples)]
    hits = [loc for t in times if (loc := localize_fn(t)) is not None]
    if len(hits) < min_hits:
        return FULL_FRAME
    # localize is per-frame noisy (upper-half best-hit scan can lock onto lower
    # HUD; spec section 3.6). Cluster hits by y_top and take the largest cluster
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
        return FULL_FRAME
    median_loc = ScorebarLocalization(
        x_left=int(np.median([h.x_left for h in best])),
        x_right=int(np.median([h.x_right for h in best])),
        y_top=int(np.median([h.y_top for h in best])),
        y_bottom=int(np.median([h.y_bottom for h in best])),
        confidence=float(np.median([h.confidence for h in best])),
    )
    return band_region_from_localization(median_loc, probe_w=probe_w, probe_h=probe_h)
