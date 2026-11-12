"""KO / ASSIST インジケータ検出 (#1106 作業項目 2-3)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

設計の要点:

- **絶対座標を使わない**。プレイヤーの HUD 設定と画面解像度で位置・サイズが変わるため、
  常時表示の戦意値ゲージをアンカーとして **動画ごとにキャリブレーション**する
- ゲージが無いフレームでは `None` を返す（誤検出しない）
- テキストは **`K.O.!!` -> ko / `ASSISTED!` -> assist / それ以外 -> 無視** の 3 分岐で扱う。
  `BOOSTED!`（ドローン撃破による戦意値上昇）は「それ以外」の実例で、既定で無視される
- スケールの正規化は **ROI 側を参照サイズへリサイズ**する 1 通りに固定（テンプレートは参照サイズ）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from allaganeye.video.refs import load_templates

# 参照レイアウト (1080p / 4K 表示を FHD 録画) の実測値。
# ゲージテンプレート (50x200) 内でのバーの位置: frame x 647-775 / y 620-630、
# テンプレート原点 (585, 575) を引いた値。
_REF_BAR_IN_TEMPLATE = (62.0, 190.0, 45.0, 55.0)
_REF_BAR_WIDTH = _REF_BAR_IN_TEMPLATE[1] - _REF_BAR_IN_TEMPLATE[0]

# 帯域の相対幾何 (spec 4-5)。バー幅 w 基準。
_BAND_LEFT_RATIO = 0.5
_BAND_RIGHT_RATIO = 0.15
_BAND_TOP_RATIO = 0.05
_BAND_BOTTOM_RATIO = 0.30

_DEFAULT_SCALES: tuple[float, ...] = tuple(round(0.5 + 0.1 * i, 2) for i in range(21))
_MIN_SCORE = 0.55


def _import_cv2() -> Any:
    """cv2 を遅延 import する（未インストール環境で module import を壊さない）。"""
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - 環境依存
        raise ImportError(
            "KO / ASSIST 検出には opencv が必要です。`pip install opencv-python-headless` "
            "を実行してください。"
        ) from exc
    return cv2


@dataclass(frozen=True)
class Rect:
    """px 座標の矩形（half-open ではなく境界値として扱う）。"""

    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class IndicatorLayout:
    """動画ごとに解決したジオメトリ（ゲージ位置 + スケール）。"""

    scale: float
    bar: Rect
    confidence: float = 1.0
    source: str = "anchor"  # "anchor" | "user" | "fallback"

    def text_band(self) -> Rect:
        """インジケータテキストの探索帯域（バー幅 w 基準の相対幾何）。"""
        w = self.bar.width
        return Rect(
            self.bar.x0 - _BAND_LEFT_RATIO * w,
            self.bar.x1 + _BAND_RIGHT_RATIO * w,
            self.bar.y1 - _BAND_TOP_RATIO * w,
            self.bar.y1 + _BAND_BOTTOM_RATIO * w,
        )


@dataclass(frozen=True)
class IndicatorHit:
    """検出したインジケータ。"""

    kind: str  # "ko" | "assist"
    score: float
    band: Rect


def calibrate_layout(
    frame_gray: np.ndarray,
    gauge_template: np.ndarray,
    *,
    scales: tuple[float, ...] = _DEFAULT_SCALES,
    min_score: float = _MIN_SCORE,
) -> IndicatorLayout | None:
    """多スケール探索でゲージを検出し、スケールとバー位置を返す。

    ゲージが見つからない（スコアが `min_score` 未満）場合は `None`。
    """
    cv2 = _import_cv2()
    frame_h, frame_w = frame_gray.shape[:2]
    best_score = -1.0
    best_scale: float | None = None
    best_loc: tuple[int, int] | None = None

    for scale in scales:
        tw = max(8, round(gauge_template.shape[1] * scale))
        th = max(8, round(gauge_template.shape[0] * scale))
        if tw >= frame_w or th >= frame_h:
            continue
        tpl = cv2.resize(gauge_template, (tw, th), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(frame_gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if score > best_score:
            best_score, best_scale, best_loc = float(score), scale, loc

    if best_scale is None or best_loc is None or best_score < min_score:
        return None

    s = best_scale
    mx, my = best_loc
    bar = Rect(
        mx + _REF_BAR_IN_TEMPLATE[0] * s,
        mx + _REF_BAR_IN_TEMPLATE[1] * s,
        my + _REF_BAR_IN_TEMPLATE[2] * s,
        my + _REF_BAR_IN_TEMPLATE[3] * s,
    )
    return IndicatorLayout(scale=s, bar=bar, confidence=best_score)


def _best_score(cv2: Any, patch: np.ndarray, template: np.ndarray) -> float:
    if (template.shape[0] > patch.shape[0]) or (template.shape[1] > patch.shape[1]):
        return 0.0
    result = cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(result)
    return float(score)


def classify_text(
    patch: np.ndarray,
    templates: dict[str, np.ndarray] | None = None,
    *,
    min_score: float = _MIN_SCORE,
) -> tuple[str, float]:
    """帯域画像を `ko` / `assist` / `other` に分類する。

    `other` は「既知テンプレートに一致しない表示」で、`BOOSTED!` などが該当する。
    """
    cv2 = _import_cv2()
    tpls = templates if templates is not None else load_templates()
    ko_score = _best_score(cv2, patch, tpls["ko"])
    assist_score = _best_score(cv2, patch, tpls["assist"])

    if ko_score >= min_score and ko_score >= assist_score:
        return "ko", ko_score
    if assist_score >= min_score and assist_score > ko_score:
        return "assist", assist_score
    return "other", max(ko_score, assist_score)


def _normalise_patch(cv2: Any, patch: np.ndarray, scale: float) -> np.ndarray:
    """ROI を参照スケールへ正規化する（テンプレートは参照サイズのまま使う）。"""
    if abs(scale - 1.0) < 1e-6:
        return patch
    h = max(8, round(patch.shape[0] / scale))
    w = max(8, round(patch.shape[1] / scale))
    return cv2.resize(patch, (w, h), interpolation=cv2.INTER_AREA)


def detect_indicator(
    frame_gray: np.ndarray,
    layout: IndicatorLayout,
    templates: dict[str, np.ndarray] | None = None,
    *,
    min_score: float = _MIN_SCORE,
) -> IndicatorHit | None:
    """1 フレームからインジケータを検出する。`other` は `None` を返す。"""
    cv2 = _import_cv2()
    band = layout.text_band()
    frame_h, frame_w = frame_gray.shape[:2]
    x0 = max(0, round(band.x0))
    x1 = min(frame_w, round(band.x1))
    y0 = max(0, round(band.y0))
    y1 = min(frame_h, round(band.y1))
    if (x1 - x0) < 8 or (y1 - y0) < 8:
        return None

    patch = _normalise_patch(cv2, frame_gray[y0:y1, x0:x1], layout.scale)
    kind, score = classify_text(patch, templates, min_score=min_score)
    if kind == "other":
        return None
    return IndicatorHit(kind=kind, score=score, band=band)


def resolve_layout(
    frame_gray: np.ndarray,
    templates: dict[str, np.ndarray] | None = None,
    *,
    scales: tuple[float, ...] = _DEFAULT_SCALES,
    min_score: float = _MIN_SCORE,
) -> IndicatorLayout | None:
    """同梱テンプレートでキャリブレーションする（アンカー探索の入口）。"""
    tpls = templates if templates is not None else load_templates()
    return calibrate_layout(
        frame_gray, tpls["gauge"], scales=scales, min_score=min_score
    )


__all__ = [
    "IndicatorHit",
    "IndicatorLayout",
    "Rect",
    "calibrate_layout",
    "classify_text",
    "detect_indicator",
    "resolve_layout",
]

# 参照レイアウトのバー幅（テスト・キャリブレーション整合性確認用）。
REFERENCE_BAR_WIDTH_PX = _REF_BAR_WIDTH
