"""KO / ASSIST インジケータ検出の単体テスト (#1106)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

合成フレームに同梱テンプレートを貼り付けて、
キャリブレーション（スケール + 位置の解決）と分類（ko / assist / other）を検証する。
実動画での検証は `test_indicators_slow.py`（slow マーカー）が担う。
"""

from __future__ import annotations

import numpy as np
import pytest

from allaganeye.video.indicators import (
    IndicatorLayout,
    Rect,
    calibrate_layout,
    classify_text,
    detect_indicator,
    resolve_layout,
)
from allaganeye.video.refs import load_templates


def _noise(h: int, w: int, seed: int = 0, level: int = 60) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, level, size=(h, w), dtype=np.uint8)


def _paste(frame: np.ndarray, patch: np.ndarray, x: int, y: int) -> None:
    h, w = patch.shape[:2]
    frame[y : y + h, x : x + w] = patch


def test_text_band_follows_documented_geometry() -> None:
    """band は実測値から導いた相対幾何（4-5）どおりに出る。"""
    layout = IndicatorLayout(scale=1.0, bar=Rect(647.0, 775.0, 620.0, 630.0))
    band = layout.text_band()
    # w = 128 -> x0 = 647 - 64 = 583 / x1 = 775 + 19.2 = 794.2
    #               y0 = 630 - 6.4 = 623.6 / y1 = 630 + 38.4 = 668.4
    assert band.x0 == pytest.approx(583.0)
    assert band.x1 == pytest.approx(794.2)
    assert band.y0 == pytest.approx(623.6)
    assert band.y1 == pytest.approx(668.4)


@pytest.mark.parametrize("scale", [0.7, 1.0, 1.4])
def test_calibrate_finds_scale_and_position(scale: float) -> None:
    """別スケール・別位置に貼ったゲージからスケールと位置を復元できる。"""
    import cv2

    templates = load_templates()
    gauge = templates["gauge"]
    tw = round(gauge.shape[1] * scale)
    th = round(gauge.shape[0] * scale)
    scaled = cv2.resize(gauge, (tw, th), interpolation=cv2.INTER_AREA)

    frame = _noise(1080, 1920)
    x, y = 900, 300
    _paste(frame, scaled, x, y)

    layout = calibrate_layout(frame, gauge)
    assert layout is not None, "calibration should find the gauge"
    assert layout.scale == pytest.approx(scale, abs=0.11)
    # バー左端 = 貼り付け位置 + 62 * s
    assert layout.bar.x0 == pytest.approx(x + 62.0 * scale, abs=6.0)


def test_calibrate_returns_none_without_gauge() -> None:
    """ゲージが無いフレームでは None を返す（誤検出しない）。"""
    templates = load_templates()
    frame = _noise(1080, 1920, seed=7)
    assert calibrate_layout(frame, templates["gauge"]) is None


@pytest.mark.parametrize(
    ("key", "expected"),
    [("ko", "ko"), ("assist", "assist")],
)
def test_classify_recognises_known_text(key: str, expected: str) -> None:
    """同梱テンプレートを貼った帯域は正しく分類される。"""
    templates = load_templates()
    patch = _noise(60, 260, seed=3)
    tpl = templates[key]
    _paste(patch, tpl, 40, 12)
    kind, score = classify_text(patch, templates)
    assert kind == expected
    assert score >= 0.55


def test_classify_other_text_is_not_a_hit() -> None:
    """既知テンプレートに一致しない表示（例: BOOSTED!）は other になる。"""
    templates = load_templates()
    patch = _noise(60, 260, seed=11)
    # 既知テキストと形が違う「太い横棒 + 縦棒」を描く
    patch[20:30, 60:200] = 235
    patch[20:50, 100:112] = 235
    kind, _ = classify_text(patch, templates)
    assert kind == "other"


def test_detect_end_to_end_at_other_scale() -> None:
    """ゲージ + KO テキストを別スケールで貼ったフレームから ko を検出する。"""
    import cv2

    templates = load_templates()
    scale = 0.8
    gauge = cv2.resize(
        templates["gauge"],
        (
            round(templates["gauge"].shape[1] * scale),
            round(templates["gauge"].shape[0] * scale),
        ),
        interpolation=cv2.INTER_AREA,
    )
    frame = _noise(1080, 1920, seed=5)
    gx, gy = 700, 500
    _paste(frame, gauge, gx, gy)

    # 真のバー位置から帯域を計算し、そこへ KO テンプレートを同じスケールで貼る
    bar_w = 128.0 * scale
    bar_x0 = gx + 62.0 * scale
    bar_y1 = gy + 55.0 * scale
    band_y0 = round(bar_y1 - 0.05 * bar_w)
    tx = round(bar_x0 + (bar_w - templates["ko"].shape[1] * scale) / 2)
    ko = cv2.resize(
        templates["ko"],
        (
            round(templates["ko"].shape[1] * scale),
            round(templates["ko"].shape[0] * scale),
        ),
        interpolation=cv2.INTER_AREA,
    )
    _paste(frame, ko, tx, band_y0 + 2)

    layout = calibrate_layout(frame, templates["gauge"])
    assert layout is not None
    hit = detect_indicator(frame, layout, templates)
    assert hit is not None
    assert hit.kind == "ko"


def test_resolve_layout_uses_bundled_templates() -> None:
    """resolve_layout は同梱テンプレートでキャリブレーションする。"""

    templates = load_templates()
    frame = _noise(1080, 1920, seed=9)
    _paste(frame, templates["gauge"], 1000, 400)
    layout = resolve_layout(frame)
    assert layout is not None
    assert layout.source == "anchor"
