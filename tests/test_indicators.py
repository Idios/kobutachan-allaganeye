"""KO / ASSIST インジケータ検出の単体テスト (#1106 作業項目 2-3)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

合成フレームに同梱テンプレートを貼り付けて、
キャリブレーション (複数フレームの合意によるスケール + 位置の解決)、
分類 (ko / assist / それ以外は無視)、イベントのグルーピングを検証する。
実動画での検証は `test_indicators_slow.py` (slow マーカー) が担う。
"""

from __future__ import annotations

import numpy as np
import pytest

from allaganeye.exceptions import InputFileError
from allaganeye.video.indicators import (
    IndicatorEvent,
    IndicatorLayout,
    Rect,
    calibrate_layout,
    classify_text,
    detect_indicator,
    group_detections,
    layout_from_payload,
    layout_to_payload,
    match_text,
    resolve_layout,
    scan_indicators,
    validate_layout_for_frame,
)
from allaganeye.video.refs import load_templates


def _noise(h: int, w: int, seed: int = 0, level: int = 60) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, level, size=(h, w), dtype=np.uint8)


def _paste(frame: np.ndarray, patch: np.ndarray, x: int, y: int) -> None:
    h, w = patch.shape[:2]
    frame[y : y + h, x : x + w] = patch


def _scaled(patch: np.ndarray, scale: float) -> np.ndarray:
    import cv2

    return cv2.resize(
        patch,
        (max(8, round(patch.shape[1] * scale)), max(8, round(patch.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _frame_with_anchor(
    scale: float, x: int, y: int, seed: int = 0, size: tuple[int, int] = (540, 960)
) -> np.ndarray:
    """アンカー (ゲージ左端) だけを貼った合成フレーム。"""
    templates = load_templates()
    frame = _noise(size[0], size[1], seed=seed)
    _paste(frame, _scaled(templates["anchor"], scale), x, y)
    return frame


def _band_patch(
    scale: float = 1.0, kind: str | None = None, seed: int = 0
) -> np.ndarray:
    """バンドサイズの合成パッチ。`kind` を渡すとそのテキストを貼る。"""
    layout = IndicatorLayout(scale=scale, x=618.0, y=614.0)
    band = layout.text_band()
    w = round(band.width / scale)
    h = round(band.height / scale)
    patch = _noise(h, w, seed=seed)
    if kind is not None:
        tpl = load_templates()[kind]
        _paste(patch, tpl, 40, 12)
    return patch


# ---------------------------------------------------------------------------
# 幾何
# ---------------------------------------------------------------------------


def test_text_band_follows_measured_geometry() -> None:
    """バンドは実測の相対幾何 (spec 4-5) どおりに出る。"""
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    band = layout.text_band()
    # バー = x 626-779 / y 618-631 (w = 153) を参照に:
    #   x0 = 626 - 0.5*153 = 549.5 / x1 = 779 + 0.15*153 = 801.95
    #   y0 = 631 - 0.05*153 = 623.35 / y1 = 631 + 0.30*153 = 676.9
    assert band.x0 == pytest.approx(549.5)
    assert band.x1 == pytest.approx(801.95)
    assert band.y0 == pytest.approx(623.35)
    assert band.y1 == pytest.approx(676.9)


def test_text_band_scales_with_layout() -> None:
    """スケールが変わればバンドも同じ比率で拡縮する (絶対座標を使わない)。"""
    base = IndicatorLayout(scale=1.0, x=618.0, y=614.0).text_band()
    big = IndicatorLayout(scale=2.0, x=618.0, y=614.0).text_band()
    assert big.width == pytest.approx(base.width * 2)
    assert big.height == pytest.approx(base.height * 2)


def test_rect_reports_size() -> None:
    rect = Rect(10.0, 20.0, 40.0, 60.0)
    assert rect.width == 30.0
    assert rect.height == 40.0


# ---------------------------------------------------------------------------
# キャリブレーション (複数フレームの合意)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scale", [0.8, 1.0, 1.4])
def test_calibrate_recovers_scale_and_position(scale: float) -> None:
    """同一位置にアンカーがある複数フレームからスケールと位置を復元できる。"""
    frames = [_frame_with_anchor(scale, 500, 250, seed=i) for i in range(4)]
    layout = calibrate_layout(frames)
    assert layout is not None, "calibration should find the anchor"
    assert layout.scale == pytest.approx(scale, abs=0.09)
    assert layout.x == pytest.approx(500, abs=6)
    assert layout.y == pytest.approx(250, abs=6)
    assert layout.support == 4


def test_calibrate_returns_none_without_anchor() -> None:
    """アンカーが無いフレームでは None を返す (誤検出しない)。"""
    frames = [_noise(540, 960, seed=i) for i in range(4)]
    assert calibrate_layout(frames) is None


def test_calibrate_requires_consensus_across_frames() -> None:
    """1 フレームだけの一致では採用しない (背景の偶発一致を捨てる)。"""
    frames = [_noise(540, 960, seed=i) for i in range(4)]
    _paste(frames[0], load_templates()["anchor"], 500, 250)
    assert calibrate_layout(frames) is None


def test_calibrate_ignores_inconsistent_positions() -> None:
    """フレームごとに位置が違うアンカーは合意にならない。"""
    tpl = load_templates()["anchor"]
    frames = []
    for i, (x, y) in enumerate(((120, 120), (360, 200), (600, 280), (820, 380))):
        frame = _noise(540, 960, seed=i)
        _paste(frame, tpl, x, y)
        frames.append(frame)
    assert calibrate_layout(frames) is None


def test_calibrate_rejects_low_confidence_consensus() -> None:
    """同じ位置に静止しているがアンカーではない要素は採用しない。

    配信オーバーレイのような「毎フレーム同じ位置にある」別 UI は合意条件 (同一位置 +
    同一スケール) を満たしてしまう。真のアンカーはスコアが高い (実測 0.78-0.95 対
    0.63) ので、信頼度の下限で棄却する。
    """
    other_ui = load_templates()["assist"][:20, :42]
    frames = []
    for seed in range(4):
        frame = _noise(540, 960, seed=seed)
        _paste(frame, other_ui, 500, 250)
        frames.append(frame)
    assert calibrate_layout(frames) is None


def test_resolve_layout_uses_bundled_templates() -> None:
    """resolve_layout は同梱テンプレートで複数フレームから解決する。"""
    frames = [
        _frame_with_anchor(1.0, 618, 614, seed=i, size=(1080, 1920)) for i in range(3)
    ]
    layout = resolve_layout(frames)
    assert layout is not None
    assert layout.source == "anchor"


# ---------------------------------------------------------------------------
# 分類 (ko / assist / それ以外は無視)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("key", "expected"), [("ko", "ko"), ("assist", "assist")])
def test_classify_recognises_known_text(key: str, expected: str) -> None:
    """同梱テンプレートを貼ったバンドは正しく分類される。"""
    kind, score = classify_text(_band_patch(kind=key, seed=3))
    assert kind == expected
    assert score >= 0.55


def test_classify_empty_band_is_other() -> None:
    """テキストが無いバンドは other になる。"""
    kind, _ = classify_text(_band_patch(seed=11))
    assert kind == "other"


def test_classify_unknown_text_is_other() -> None:
    """既知テンプレートに一致しない表示 (BOOSTED! など) は other になる。"""
    patch = _band_patch(seed=17)
    # 横棒 + 縦棒だけの「別の文字列」を描く
    patch[14:24, 60:200] = 235
    patch[14:46, 100:112] = 235
    patch[14:46, 150:162] = 235
    kind, _ = classify_text(patch)
    assert kind == "other"


def test_classify_works_on_bright_background() -> None:
    """背景が明るい (戦闘エフェクトで白飛びする) フレームでも分類できる。

    NCC はゲイン不変なので、背景輝度が上がってもテキストは同じように一致する。
    実測でも参照フレーム (493.5 秒) の背景は白いビームで明るい。
    """
    patch = _band_patch(seed=21)
    patch = np.clip(patch.astype(np.int16) + 80, 0, 255).astype(np.uint8)
    _paste(patch, load_templates()["assist"], 40, 12)
    kind, score = classify_text(patch)
    assert kind == "assist"
    assert score >= 0.55


def test_classify_prefers_bright_match_over_darker_higher_score() -> None:
    """暗いが高スコアな候補ではなく、明るい合格候補を採る。

    NCC はコントラスト不変なので、減光したコピーのほうがスコアが高くなりうる。
    明度ゲートを位置の選択前に掛けないと、本物のテキストを取り逃す。
    ここでは縮小したコピー (別スケール) を置いているので、スケールをまたぐ選択の検証。
    """
    patch = _noise(54, 252, seed=29)
    tpl = load_templates()["assist"]
    dimmed = (tpl.astype(np.float32) * 0.5).astype(np.uint8)
    _paste(patch, dimmed, 10, 4)
    _paste(patch, _scaled(tpl, 1.1), 60, 32)
    kind, score = classify_text(patch)
    assert kind == "assist"
    assert score >= 0.55


def test_match_text_gates_brightness_before_choosing_location() -> None:
    """同じスケール内で暗い高スコア位置と明るい位置が競合しても明るいほうを採る。

    スコアマップの最大値だけを取ると、暗い妨害物が正解を隱す。明度をマップの
    段階で適用してから最大値を取る必要がある。スケールを 1 つに固定するのは、
    別スケールの探索で偶然救済されるのを避け、選択順序の欠陥を直接狙うため。
    """
    rng = np.random.default_rng(31)
    patch = _noise(54, 252, seed=31)
    tpl = load_templates()["assist"]
    # 完全一致だが減光されたコピー (スコア 1.0 / 明度ゲートは落ちる)
    dimmed = (tpl.astype(np.float32) * 0.5).astype(np.uint8)
    _paste(patch, dimmed, 8, 4)
    # わずかにノイズが乗った本物 (スコアは僅かに低いが明るい)
    noisy = np.clip(
        tpl.astype(np.int16) + rng.integers(-6, 7, size=tpl.shape), 0, 255
    ).astype(np.uint8)
    _paste(patch, noisy, 60, 32)

    match = match_text(patch, scale_factors=(1.0,))["assist"]
    assert match.bright_fraction >= 0.45
    assert match.score >= 0.55
    assert classify_text(patch)[0] == "assist"


def test_classify_needs_bright_glyphs() -> None:
    """グリフが明るくない場合は採用しない (NCC がゲイン不変なことの裏返し)。"""
    patch = _band_patch(kind="assist", seed=23)
    faded = (patch.astype(np.float32) * 0.6).astype(np.uint8)
    kind, _ = classify_text(faded)
    assert kind == "other"


# ---------------------------------------------------------------------------
# 検出 (レイアウトからのバンド切り出し)
# ---------------------------------------------------------------------------


def test_detect_indicator_finds_text_in_band() -> None:
    """バンドに KO テキストが入っていれば検出する。"""
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    frame = _noise(1080, 1920, seed=5)
    band = layout.text_band()
    tpl = load_templates()["ko"]
    _paste(frame, tpl, round(band.x0) + 60, round(band.y0) + 6)
    hit = detect_indicator(frame, layout)
    assert hit is not None
    assert hit.kind == "ko"


def test_detect_indicator_returns_none_on_plain_frame() -> None:
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    assert detect_indicator(_noise(1080, 1920, seed=31), layout) is None


def test_detect_indicator_rejects_incompatible_layout() -> None:
    """レイアウトがフレームと整合しない場合は「検出なし」ではなくエラーにする。

    黙って None ( = イベントなし ) にすると、キャリブレーション失敗が
    「インジケータが 1 回も出なかった」と区別できなくなる。
    """
    layout = IndicatorLayout(scale=1.0, x=-5000.0, y=-5000.0)
    with pytest.raises(ValueError):
        detect_indicator(_noise(540, 960, seed=33), layout)


def test_detect_indicator_rejects_partially_clipped_band() -> None:
    """バンドの一部だけがフレーム外でもエラーにする (切り詰めて黙って続けない)。"""
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    with pytest.raises(ValueError):
        detect_indicator(_noise(650, 640, seed=35), layout)


def test_validate_layout_for_frame_accepts_resolved_layout() -> None:
    """実測レイアウト (スケール 1.0 / 0.8) はどちらもフレームに収まる。"""
    validate_layout_for_frame(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0),
        frame_width=1920,
        frame_height=1080,
    )
    validate_layout_for_frame(
        IndicatorLayout(scale=0.8, x=621.0, y=289.0),
        frame_width=1920,
        frame_height=1080,
    )


def test_validate_layout_for_frame_rejects_out_of_frame_band() -> None:
    """帯域がフレーム外へ出る layout は走査前に InputFileError で落とす。

    `detect_indicator` は走査中に `ValueError` を投げるが、それは CLI の exit code
    体系に乗らない traceback になる。
    """
    layout = IndicatorLayout(scale=1.0, x=0.0, y=0.0)
    with pytest.raises(InputFileError, match="収まっていません"):
        validate_layout_for_frame(layout, frame_width=1920, frame_height=1080)


def test_validate_layout_for_frame_rejects_tiny_band() -> None:
    """スケールが小さすぎて帯域が潰れる layout も拒否する。"""
    layout = IndicatorLayout(scale=0.02, x=100.0, y=100.0)
    with pytest.raises(InputFileError, match="小さすぎます"):
        validate_layout_for_frame(layout, frame_width=1920, frame_height=1080)


def test_validate_layout_for_frame_rejects_non_positive_frame_size() -> None:
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    with pytest.raises(ValueError):
        validate_layout_for_frame(layout, frame_width=0, frame_height=1080)


def test_validate_layout_for_frame_matches_the_real_crop_rounding() -> None:
    """丸めた幅ではなく、実際の切り出し端点の差で最小寸法を判定する。

    スケール 0.29 では band 高さが 15.53 なので `round(band.height)` は 16 で
    通過するが、`detect_indicator` は端点を別々に丸めるため 15 px になる。
    この 1 px 差を許すとキャリブレーション資産の検証をすり抜け、走査の最初の
    フレームで `ValueError` になる。
    """
    layout = IndicatorLayout(scale=0.29, x=100.0, y=100.0)
    with pytest.raises(InputFileError, match="小さすぎます"):
        validate_layout_for_frame(layout, frame_width=1920, frame_height=1080)
    with pytest.raises(ValueError):
        detect_indicator(np.zeros((1080, 1920), dtype=np.uint8), layout)


def test_detect_indicator_at_scaled_layout() -> None:
    """レイアウトが 0.8 倍でもバンド内のテキストを拾う。"""
    layout = IndicatorLayout(scale=0.8, x=621.0, y=289.0)
    frame = _noise(1080, 1920, seed=7)
    band = layout.text_band()
    tpl = _scaled(load_templates()["assist"], 0.8)
    _paste(frame, tpl, round(band.x0) + 10, round(band.y0) + 8)
    hit = detect_indicator(frame, layout)
    assert hit is not None
    assert hit.kind == "assist"


# ---------------------------------------------------------------------------
# グルーピング / スキャン
# ---------------------------------------------------------------------------


def test_group_detections_merges_consecutive_samples() -> None:
    """連続するヒットは 1 イベントにまとまり、開始/終了が記録される。"""
    detections = [
        (0.0, None, 0.2),
        (0.1, "assist", 0.9),
        (0.2, "assist", 0.95),
        (0.3, "assist", 0.8),
        (0.4, None, 0.3),
    ]
    events = group_detections(detections, max_gap=0.25, min_samples=2)
    assert events == [
        IndicatorEvent(kind="assist", start=0.1, end=0.3, score=0.95, samples=3)
    ]


def test_group_detections_drops_single_sample_blips() -> None:
    """1 サンプルだけの検出は捨てる (単発ノイズ対策)。"""
    detections = [(0.0, "ko", 0.6), (0.5, None, 0.1), (1.0, "ko", 0.7)]
    assert group_detections(detections, max_gap=0.25, min_samples=2) == []


def test_group_detections_splits_on_kind_change() -> None:
    detections = [
        (0.0, "ko", 0.7),
        (0.1, "ko", 0.7),
        (0.2, "assist", 0.9),
        (0.3, "assist", 0.9),
    ]
    events = group_detections(detections, max_gap=0.25, min_samples=2)
    assert [e.kind for e in events] == ["ko", "assist"]


def test_scan_indicators_returns_events_from_frames() -> None:
    """フレーム列から 0.1 秒刻みの検出を回してイベントを返す。"""
    layout = IndicatorLayout(scale=1.0, x=618.0, y=614.0)
    band = layout.text_band()
    tpl = load_templates()["assist"]
    frames = []
    for i in range(20):
        frame = _noise(1080, 1920, seed=40 + i)
        if 5 <= i <= 12:
            _paste(frame, tpl, round(band.x0) + 60, round(band.y0) + 6)
        frames.append((i * 0.1, frame))
    events = scan_indicators(frames, layout)
    assert len(events) == 1
    event = events[0]
    assert event.kind == "assist"
    assert event.start == pytest.approx(0.5)
    assert event.end == pytest.approx(1.2)
    assert event.samples == 8


# ---------------------------------------------------------------------------
# metadata への永続化 (#1106 作業項目 5)
# ---------------------------------------------------------------------------


def test_layout_payload_round_trip() -> None:
    """解決結果を metadata の payload にして戻すと同じ layout になる。"""
    layout = IndicatorLayout(
        scale=1.0, x=618.0, y=614.0, support=6, confidence=0.95, source="anchor"
    )
    payload = layout_to_payload(layout, frame_width=1920, frame_height=1080)
    assert payload == {
        "anchor_x": pytest.approx(618.0 / 1920),
        "anchor_y": pytest.approx(614.0 / 1080),
        "scale": 1.0,
        "support": 6,
        "confidence": 0.95,
        "source": "anchor",
    }
    restored = layout_from_payload(payload, frame_width=1920, frame_height=1080)
    assert restored == layout


def test_layout_payload_is_normalised() -> None:
    """保存は正規化座標 (capture_regions と同じ規約) で行う。"""
    layout = IndicatorLayout(scale=2.0, x=1236.0, y=1228.0, support=5, confidence=0.8)
    payload = layout_to_payload(layout, frame_width=3840, frame_height=2160)
    assert payload["anchor_x"] == pytest.approx(1236.0 / 3840)
    assert payload["anchor_y"] == pytest.approx(1228.0 / 2160)
    assert payload["scale"] == pytest.approx(2.0)


def test_layout_payload_scales_with_frame_size() -> None:
    """同じ payload を別解像度のフレームに適用すると比例して配置される。"""
    payload = layout_to_payload(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0),
        frame_width=1920,
        frame_height=1080,
    )
    restored = layout_from_payload(payload, frame_width=3840, frame_height=2160)
    assert restored.x == pytest.approx(1236.0)
    assert restored.y == pytest.approx(1228.0)
    assert restored.scale == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"anchor_x": 1.5}, "anchor_x"),
        ({"anchor_y": -0.1}, "anchor_y"),
        ({"scale": 0.0}, "scale"),
        ({"support": 0}, "support"),
        ({"confidence": 1.5}, "confidence"),
        ({"source": ""}, "source"),
        ({"anchor_x": "0.3"}, "anchor_x"),
        ({"support": 3.5}, "support"),
    ],
)
def test_layout_payload_rejects_invalid_values(override: dict, field: str) -> None:
    """壊れた payload はその場で落とす (黙って使わない)。"""
    payload = layout_to_payload(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0),
        frame_width=1920,
        frame_height=1080,
    )
    payload.update(override)
    with pytest.raises(InputFileError, match=field):
        layout_from_payload(payload, frame_width=1920, frame_height=1080)


@pytest.mark.parametrize("missing", ["anchor_x", "scale", "support", "source"])
def test_layout_payload_requires_all_keys(missing: str) -> None:
    payload = layout_to_payload(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0),
        frame_width=1920,
        frame_height=1080,
    )
    del payload[missing]
    with pytest.raises(InputFileError, match=missing):
        layout_from_payload(payload, frame_width=1920, frame_height=1080)


def test_layout_payload_accepts_unknown_source() -> None:
    """source は自由文字列 (未知値も読める = 前方互換)。"""
    payload = layout_to_payload(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0, source="user"),
        frame_width=1920,
        frame_height=1080,
    )
    restored = layout_from_payload(payload, frame_width=1920, frame_height=1080)
    assert restored.source == "user"


def test_layout_payload_rejects_oversized_number() -> None:
    """巨大な整数 (float に変換できない) は traceback ではなく InputFileError。

    JSON の数値は桁数無制限なので、`float(value)` が `OverflowError` を投げる。
    これは `AllaganEyeError` ではないため catch をすり抜ける。
    """
    payload = {
        "anchor_x": 0.3,
        "anchor_y": 0.5,
        "scale": int("1" + "0" * 400),
        "support": 6,
        "confidence": 0.9,
        "source": "anchor",
    }
    with pytest.raises(InputFileError, match="scale"):
        layout_from_payload(payload, frame_width=1920, frame_height=1080)


def test_layout_payload_rejects_non_mapping() -> None:
    with pytest.raises(InputFileError):
        layout_from_payload([], frame_width=1920, frame_height=1080)  # type: ignore[arg-type]


def test_layout_payload_rejects_non_positive_frame_size() -> None:
    with pytest.raises(ValueError):
        layout_to_payload(
            IndicatorLayout(scale=1.0, x=618.0, y=614.0),
            frame_width=0,
            frame_height=1080,
        )


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"anchor_x": float("nan")}, "anchor_x"),
        ({"scale": float("inf")}, "scale"),
        ({"confidence": float("nan")}, "confidence"),
        ({"anchor_y": float("-inf")}, "anchor_y"),
    ],
)
def test_layout_payload_rejects_non_finite(override: dict, field: str) -> None:
    """NaN / inf は範囲比較をすり抜けるので有限性を先に検査する。

    JSON の `NaN` / `Infinity` / `1e309` は Python の json が読めてしまい、
    NaN は全ての比較が False になるため範囲チェックだけでは通ってしまう。
    """
    payload = layout_to_payload(
        IndicatorLayout(scale=1.0, x=618.0, y=614.0),
        frame_width=1920,
        frame_height=1080,
    )
    payload.update(override)
    with pytest.raises(InputFileError, match=field):
        layout_from_payload(payload, frame_width=1920, frame_height=1080)
