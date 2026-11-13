"""KO / ASSIST インジケータ検出 (#1106 作業項目 2-3)。

実測の正: `docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`

設計の要点:

- **絶対座標を使わない**。位置とサイズはプレイヤーの HUD 設定と画面解像度で変わるため、
  常時表示の戦意値ゲージの**バー左キャップ**をアンカーにして動画ごとに解決する
- **アンカーは複数フレームの合意で決める**。1 フレームの照合は曖昧で、背景の偶発一致が
  0.6 前後まで出る (実測)。HUD 要素は位置もスケールも動かないのに対し背景の一致は
  フレームごとに散るので、合意 (同一位置 + 同一スケール) を取ると真のアンカーだけが残る
- **テキストは 3 分岐**。`K.O.!!` -> ko / `ASSISTED!` -> assist / それ以外 -> 無視。
  `BOOSTED!` (ドローン撃破による戦意値上昇) は「それ以外」の実例で、既定で無視される
- **照合はグリフ画素だけの masked NCC**。背景を含む通常の template matching は背景相関に
  支配され、KO / ASSIST / BOOSTED を分離できない (実測: BOOSTED が ASSIST に 0.62 まで
  乗る)。グリフ (テンプレートの明るい画素 + その縁取り) だけの重み付き NCC にすると
  正例 0.65 以上 / 負例 0.48 以下まで分離する
- **スケールはバンド内で探索する**。アンカー由来のスケールはテキストの実スケールと
  最大 15% ずれる (実測: バー比 0.82 に対しテキスト比 0.87) ため、-10% から +20% を
  0.05 刻みで振って最良を採る
- **コントラスト線形変換に不変**。NCC はゲインに依存しないので、フェードイン / アウト中の
  テキストも同じスコアで拾える。一方それゆえ「暗い背景が形だけ似ている」場合も高く出るので、
  グリフ位置が実際に明るいことを要求するゲートを併用する
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np

from allaganeye.video.refs import load_templates

# ---------------------------------------------------------------------------
# 参照レイアウト (1080p / 4K 表示を FHD 録画) の実測値。
#
# すべて「参照フレームの画素座標」であり、実装の定数ではない。
# 実行時はアンカー位置 + スケール s で写像する。
# ---------------------------------------------------------------------------

# アンカーテンプレート (バー左キャップ) の左上 = (_ANCHOR_X, _ANCHOR_Y)、サイズは npz 側。
_ANCHOR_X = 618.0
_ANCHOR_Y = 614.0

# ゲージバー本体 (実測: x 626-779 / y 618-631、幅 153 px)。
_REF_BAR = (626.0, 618.0, 779.0, 631.0)

# テキスト帯の相対幾何 (note 4-5)。バー幅 w 基準。
_BAND_LEFT_RATIO = 0.5
_BAND_RIGHT_RATIO = 0.15
_BAND_TOP_RATIO = 0.05
_BAND_BOTTOM_RATIO = 0.30

# アンカー探索のスケール。参照解像度 1080p に対し、1080p の別 HUD 設定 (実測 0.80) から
# ネイティブ 4K (2.0) までを覆う。
_DEFAULT_SCALES: tuple[float, ...] = tuple(round(0.50 + 0.05 * i, 2) for i in range(31))

# バンド内のテキストスケール探索。
_DEFAULT_SCALE_FACTORS: tuple[float, ...] = (0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20)

# 判定する種類。順序は判定の同点崩しには使わない (スコア / 閾値の比で決める)。
_TEXT_KINDS: tuple[str, ...] = ("ko", "assist")

# 判定閾値。実測分布の間隙に置いてある (生値は docstring の表を参照)。
#   ko     : 正例 0.65-1.00 / 負例 <= 0.48
#   assist : 正例 0.78-1.00 / 負例 <= 0.47 (BOOSTED は 0.47 で棄却)
_MIN_SCORE = {"ko": 0.55, "assist": 0.68}

# グリフ画素の明度ゲート。NCC はゲイン不変なので、暗い背景が形だけ似た場合を弾く。
_BRIGHT_CORE = 150
_MIN_BRIGHT_FRACTION = 0.45

# 「この位置は採用しない」を表す NCC マップ上の番兵値。NCC の下限 (-1) より下にする。
_GATED_OUT = -2.0

# アンカー照合のハイパス (局所平均を引いて背景輝度の支配を弱める)。
_HIGH_PASS_KERNEL = 11

# アンカー候補の山登り: 1 フレームあたりの候補数と、候補間の最小間隔 (px)。
_PEAKS_PER_FRAME = 10
_PEAK_NMS_PX = 16

# テキストバンドの最小寸法。これ未満は「レイアウトとフレームの不整合」として扱う
# (正しいレイアウトのバンドは 200x43 程度)。
_MIN_BAND_PX = 16

# 合意判定の許容幅。
_CONSENSUS_DX = 10.0
_CONSENSUS_DY = 6.0
_CONSENSUS_DS = 0.08
_MIN_SUPPORT = 2

# 合意の受理下限 (平均スコア)。真のアンカーは 0.78-0.95、静止しているだけの別 UI は
# 0.63 だったので 0.70 を境にする。ここを外すと、アンカーが写っていない動画で
# 静止オーバーレイをアンカーと誤認し、「解決できたように見えて実は全滅」する。
_MIN_CONFIDENCE = 0.70


def _import_cv2() -> Any:
    """cv2 を遅延 import する (未インストール環境で module import を壊さない)。"""
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
    """px 座標の矩形 (連続値。切り出し時に round する)。"""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class IndicatorLayout:
    """動画ごとに解決したジオメトリ (アンカー位置 + スケール)。"""

    scale: float
    x: float
    y: float
    support: int = 1
    confidence: float = 0.0
    source: str = "anchor"  # "anchor" | "user"

    def text_band(self) -> Rect:
        """インジケータテキストの探索帯域 (バー幅 w 基準の相対幾何)。"""
        bar_x0 = self.x + (_REF_BAR[0] - _ANCHOR_X) * self.scale
        bar_x1 = self.x + (_REF_BAR[2] - _ANCHOR_X) * self.scale
        bar_y1 = self.y + (_REF_BAR[3] - _ANCHOR_Y) * self.scale
        w = bar_x1 - bar_x0
        return Rect(
            bar_x0 - _BAND_LEFT_RATIO * w,
            bar_y1 - _BAND_TOP_RATIO * w,
            bar_x1 + _BAND_RIGHT_RATIO * w,
            bar_y1 + _BAND_BOTTOM_RATIO * w,
        )


@dataclass(frozen=True)
class IndicatorHit:
    """1 フレームで検出したインジケータ。"""

    kind: str  # "ko" | "assist"
    score: float
    band: Rect


@dataclass(frozen=True)
class IndicatorEvent:
    """連続する検出をまとめた 1 表示区間。"""

    kind: str
    start: float
    end: float
    score: float
    samples: int


@dataclass(frozen=True)
class TextMatch:
    """1 テンプレートの最良一致。"""

    kind: str
    score: float
    scale_factor: float
    bright_fraction: float


@dataclass
class _OpenEvent:
    """グルーピング中の可変状態。"""

    kind: str
    start: float
    end: float
    score: float
    samples: int


# ---------------------------------------------------------------------------
# 画像演算
# ---------------------------------------------------------------------------


def _high_pass(gray: np.ndarray, kernel: int = _HIGH_PASS_KERNEL) -> np.ndarray:
    """局所平均を引く (背景の明暗に照合が引っ張られるのを弱める)。"""
    cv2 = _import_cv2()
    blurred = cv2.blur(gray.astype(np.float32), (kernel, kernel))
    return cv2.addWeighted(gray.astype(np.float32), 1.0, blurred, -1.0, 128.0)


def _resize(img: np.ndarray, width: int, height: int) -> np.ndarray:
    cv2 = _import_cv2()
    return cv2.resize(
        img, (max(8, width), max(8, height)), interpolation=cv2.INTER_AREA
    )


@lru_cache(maxsize=1)
def _glyph_mask_shapes() -> tuple[tuple[int, int], ...]:
    templates = load_templates()
    return tuple(templates[key].shape for key in ("ko", "assist"))


def _glyph_core(tpl: np.ndarray) -> np.ndarray:
    """明るい画素 (グリフのコア)。壊れたテンプレートでは全域を使う。"""
    core = (tpl >= _BRIGHT_CORE).astype(np.uint8)
    if int(core.sum()) < 20:
        core = np.ones_like(core)
    return core


def _glyph_mask(tpl: np.ndarray) -> np.ndarray:
    """グリフ画素 + 3x3 膨張 (縁取りを含める)。NCC の重みに使う。"""
    cv2 = _import_cv2()
    return cv2.dilate(_glyph_core(tpl), np.ones((3, 3), np.uint8))


def _ncc_map(patch: np.ndarray, tpl: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """マスク画素だけの正規化相互相関マップ (各位置の左上が添字)。

    OpenCV の masked matching は TM_CCORR / TM_SQDIFF 専用で平均を引かないため、
    「マスク内平均を引いた NCC」を filter2D + TM_CCORR で直接組む。
    マップを返すのは、明度ゲートを**位置の選択前**に掛けるため (最大値だけを返すと、
    暗い高スコア位置が本物の明るい位置を隱す)。
    """
    cv2 = _import_cv2()
    p = patch.astype(np.float32)
    t = tpl.astype(np.float32)
    m = mask.astype(np.float32)
    m_sum = float(m.sum())
    height, width = t.shape[:2]
    res_h = p.shape[0] - height + 1
    res_w = p.shape[1] - width + 1
    if m_sum < 1.0 or res_h < 1 or res_w < 1:
        return np.full((0, 0), _GATED_OUT, np.float32)
    t_sum = float((m * t).sum())
    var_t = float((m * t * t).sum()) - t_sum * t_sum / m_sum
    if var_t <= 1e-6:
        return np.full((res_h, res_w), _GATED_OUT, np.float32)
    sum_p = cv2.filter2D(p, -1, m, anchor=(0, 0), borderType=cv2.BORDER_REFLECT)[
        :res_h, :res_w
    ]
    sum_p2 = cv2.filter2D(p * p, -1, m, anchor=(0, 0), borderType=cv2.BORDER_REFLECT)[
        :res_h, :res_w
    ]
    corr = cv2.matchTemplate(p, m * t, cv2.TM_CCORR)
    var_p = sum_p2 - sum_p * sum_p / m_sum
    denom = np.sqrt(np.clip(var_p, 0.0, None) * var_t)
    return np.where(
        denom > 1e-6,
        (corr - sum_p * t_sum / m_sum) / np.maximum(denom, 1e-6),
        _GATED_OUT,
    ).astype(np.float32)


def _bright_map(patch: np.ndarray, core: np.ndarray) -> np.ndarray:
    """各位置での「グリフ画素が実際に明るい割合」マップ (0..1)。"""
    cv2 = _import_cv2()
    height, width = core.shape[:2]
    res_h = patch.shape[0] - height + 1
    res_w = patch.shape[1] - width + 1
    total = float(core.sum())
    if total < 1.0 or res_h < 1 or res_w < 1:
        return np.zeros((0, 0), np.float32)
    bright = (patch >= _BRIGHT_CORE).astype(np.float32)
    sums = cv2.filter2D(
        bright,
        -1,
        core.astype(np.float32),
        anchor=(0, 0),
        borderType=cv2.BORDER_REFLECT,
    )[:res_h, :res_w]
    return (sums / total).astype(np.float32)


# ---------------------------------------------------------------------------
# 分類 (ko / assist / それ以外)
# ---------------------------------------------------------------------------


def match_text(
    patch: np.ndarray,
    templates: dict[str, np.ndarray] | None = None,
    *,
    scale: float = 1.0,
    scale_factors: Sequence[float] = _DEFAULT_SCALE_FACTORS,
) -> dict[str, TextMatch]:
    """バンドパッチを全テンプレートで照合し、種類ごとの最良一致を返す。

    `patch` はバンドを切り出した生画像。`scale` はアンカー由来のスケールで、
    パッチを参照サイズへ正規化するのに使う (テンプレートは参照サイズのまま)。

    位置とスケールの選択は**明度ゲートを通った候補の中**で行う。NCC はコントラスト
    不変なので、減光したコピーや暗い背景のほうが高スコアになりうる。ゲート通過後に
    選ぶと本物を取り逃すため、通過候補が一つも無い場合だけ全体最良に落とす
    (その場合は `bright_fraction` が基準未満になるので判定側で棄却される)。
    """
    tpls = templates if templates is not None else load_templates()
    unset = {
        kind: TextMatch(
            kind=kind, score=_GATED_OUT, scale_factor=1.0, bright_fraction=0.0
        )
        for kind in _TEXT_KINDS
    }
    qualified: dict[str, TextMatch] = dict(unset)
    overall: dict[str, TextMatch] = dict(unset)
    for factor in scale_factors:
        effective = scale * factor
        normalised = _resize(
            patch,
            round(patch.shape[1] / effective),
            round(patch.shape[0] / effective),
        )
        for kind in _TEXT_KINDS:
            tpl = tpls[kind]
            ncc = _ncc_map(normalised, tpl, _glyph_mask(tpl))
            if ncc.size == 0:
                continue
            bright = _bright_map(normalised, _glyph_core(tpl))
            gated = np.where(bright >= _MIN_BRIGHT_FRACTION, ncc, _GATED_OUT)
            overall[kind] = _better(overall[kind], ncc, factor, bright)
            qualified[kind] = _better(qualified[kind], gated, factor, bright)
    return {
        kind: (qualified[kind] if qualified[kind].score > _GATED_OUT else overall[kind])
        for kind in _TEXT_KINDS
    }


def _better(
    current: TextMatch,
    score_map: np.ndarray,
    scale_factor: float,
    bright_map: np.ndarray,
) -> TextMatch:
    """マップの最大値が現状より良ければ `TextMatch` を置き換える。"""
    index = np.unravel_index(int(np.argmax(score_map)), score_map.shape)
    score = float(score_map[index])
    if score <= current.score:
        return current
    return TextMatch(
        kind=current.kind,
        score=score,
        scale_factor=scale_factor,
        bright_fraction=float(bright_map[index]),
    )


def classify_text(
    patch: np.ndarray,
    templates: dict[str, np.ndarray] | None = None,
    *,
    scale: float = 1.0,
) -> tuple[str, float]:
    """バンドパッチを `ko` / `assist` / `other` に分類する。

    `other` は「既知テンプレートに合格しない表示」で、`BOOSTED!` などが該当する。
    合格しなかった場合も第 2 要素には最良スコアを入れる (調査用)。
    """
    matches = match_text(patch, templates, scale=scale)
    passed = [
        (match.score / _MIN_SCORE[match.kind], match)
        for match in matches.values()
        if match.score >= _MIN_SCORE[match.kind]
        and match.bright_fraction >= _MIN_BRIGHT_FRACTION
    ]
    if not passed:
        return "other", max(match.score for match in matches.values())
    passed.sort(key=lambda item: item[0], reverse=True)
    return passed[0][1].kind, passed[0][1].score


def detect_indicator(
    frame_gray: np.ndarray,
    layout: IndicatorLayout,
    templates: dict[str, np.ndarray] | None = None,
) -> IndicatorHit | None:
    """1 フレームからインジケータを検出する。`other` は `None` を返す。

    バンドがフレームに収まらない場合は `ValueError`。ここで `None` を返すと、
    キャリブレーションの誤りが「インジケータが 1 回も出なかった」と区別できず、
    黙ってイベント 0 件になる。
    """
    band = layout.text_band()
    height, width = frame_gray.shape[:2]
    x0 = max(0, round(band.x0))
    y0 = max(0, round(band.y0))
    x1 = min(width, round(band.x1))
    y1 = min(height, round(band.y1))
    if (x1 - x0) < _MIN_BAND_PX or (y1 - y0) < _MIN_BAND_PX:
        raise ValueError(
            "テキストバンドがフレームに収まっていません "
            f"(band={band}, frame={width}x{height})。"
            "レイアウトの解決結果とフレームの解像度が食い違っています。"
        )
    kind, score = classify_text(frame_gray[y0:y1, x0:x1], templates, scale=layout.scale)
    if kind == "other":
        return None
    return IndicatorHit(kind=kind, score=score, band=band)


# ---------------------------------------------------------------------------
# キャリブレーション (複数フレームの合意)
# ---------------------------------------------------------------------------


def _peak_candidates(
    frame: np.ndarray,
    tpl: np.ndarray,
    scales: Sequence[float],
    *,
    peaks: int = _PEAKS_PER_FRAME,
    nms: int = _PEAK_NMS_PX,
) -> list[tuple[float, float, int, int]]:
    """多スケール照合の上位候補 (score, scale, x, y) を重複除去して返す。"""
    cv2 = _import_cv2()
    frame_h, frame_w = frame.shape[:2]
    found: list[tuple[float, float, int, int]] = []
    for scale in scales:
        width = max(6, round(tpl.shape[1] * scale))
        height = max(6, round(tpl.shape[0] * scale))
        if width >= frame_w or height >= frame_h:
            continue
        scaled = cv2.resize(tpl, (width, height), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(frame, scaled, cv2.TM_CCOEFF_NORMED)
        work = result.copy()
        for _ in range(peaks):
            _, score, _, loc = cv2.minMaxLoc(work)
            if score <= -1.0:
                break
            found.append((float(score), float(scale), int(loc[0]), int(loc[1])))
            work[
                max(0, loc[1] - nms) : loc[1] + nms,
                max(0, loc[0] - nms) : loc[0] + nms,
            ] = -2.0
    found.sort(key=lambda item: -item[0])
    kept: list[tuple[float, float, int, int]] = []
    for cand in found:
        if all(
            abs(cand[2] - other[2]) > nms
            or abs(cand[3] - other[3]) > nms
            or abs(cand[1] - other[1]) > 0.12
            for other in kept
        ):
            kept.append(cand)
        if len(kept) >= peaks:
            break
    return kept


def calibrate_layout(
    frames: Sequence[np.ndarray | None],
    templates: dict[str, np.ndarray] | None = None,
    *,
    scales: Sequence[float] = _DEFAULT_SCALES,
    min_support: int = _MIN_SUPPORT,
    min_confidence: float = _MIN_CONFIDENCE,
) -> IndicatorLayout | None:
    """複数フレームの合意からスケールとアンカー位置を解決する。

    1 フレームでも当たればよいのではなく、**同じ位置と同じスケールで複数フレームが
    一致すること**を要求する。合意の中では**平均スコアが最大のもの**を採る
    (配信オーバーレイのような「静止しているがアンカーではない」要素は、多くの
    フレームで一致するがスコアが低い。実測 0.63 対 真のアンカー 0.78-0.95)。
    さらに `min_confidence` 未満の合意は棄却する。

    戻り値が `None` のときは「アンカーを解決できなかった」であり、検出ゼロとは
    区別して呼び出し側が警告すること。
    """
    tpls = templates if templates is not None else load_templates()
    anchor = _high_pass(tpls["anchor"])

    buckets: dict[tuple[int, int, int], dict[int, tuple[float, float, int, int]]] = {}
    for index, frame in enumerate(frames):
        if frame is None:
            continue
        filtered = _high_pass(frame)
        for score, scale, x, y in _peak_candidates(filtered, anchor, scales):
            key = (
                round(x / _CONSENSUS_DX),
                round(y / _CONSENSUS_DY),
                round(scale / _CONSENSUS_DS),
            )
            per_frame = buckets.setdefault(key, {})
            current = per_frame.get(index)
            if current is None or score > current[0]:
                per_frame[index] = (score, scale, x, y)

    best: IndicatorLayout | None = None
    best_rank: tuple[float, int] | None = None
    for per_frame in buckets.values():
        support = len(per_frame)
        if support < min_support:
            continue
        values = list(per_frame.values())
        mean_score = float(np.mean([value[0] for value in values]))
        rank = (mean_score, support)
        if best_rank is not None and rank <= best_rank:
            continue
        best_rank = rank
        best = IndicatorLayout(
            scale=float(np.mean([value[1] for value in values])),
            x=float(np.median([value[2] for value in values])),
            y=float(np.median([value[3] for value in values])),
            support=support,
            confidence=mean_score,
        )
    if best is not None and best.confidence < min_confidence:
        return None
    return best


def resolve_layout(
    frames: Sequence[np.ndarray | None],
    templates: dict[str, np.ndarray] | None = None,
    *,
    scales: Sequence[float] = _DEFAULT_SCALES,
    min_support: int = _MIN_SUPPORT,
    min_confidence: float = _MIN_CONFIDENCE,
) -> IndicatorLayout | None:
    """同梱テンプレートでキャリブレーションする (アンカー解決の入口)。"""
    return calibrate_layout(
        frames,
        templates,
        scales=scales,
        min_support=min_support,
        min_confidence=min_confidence,
    )


# ---------------------------------------------------------------------------
# 検出ループ
# ---------------------------------------------------------------------------


def group_detections(
    detections: Iterable[tuple[float, str | None, float]],
    *,
    max_gap: float = 0.25,
    min_samples: int = 2,
) -> list[IndicatorEvent]:
    """時刻順の検出列をイベントにまとめる。

    `detections` は `(時刻, 種類 or None, スコア)`。`min_samples` 未満の短い塊は
    単発ノイズとして捨てる。
    """
    events: list[IndicatorEvent] = []
    current: _OpenEvent | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.samples >= min_samples:
            events.append(
                IndicatorEvent(
                    kind=current.kind,
                    start=current.start,
                    end=current.end,
                    score=current.score,
                    samples=current.samples,
                )
            )
        current = None

    for timestamp, kind, score in detections:
        if (
            current is not None
            and kind is not None
            and kind == current.kind
            and timestamp - current.end <= max_gap
        ):
            current.end = timestamp
            current.score = max(current.score, score)
            current.samples += 1
            continue
        flush()
        if kind is not None:
            current = _OpenEvent(
                kind=kind, start=timestamp, end=timestamp, score=score, samples=1
            )
    flush()
    return events


def scan_indicators(
    frames: Iterable[tuple[float, np.ndarray]],
    layout: IndicatorLayout,
    templates: dict[str, np.ndarray] | None = None,
    *,
    max_gap: float = 0.25,
    min_samples: int = 2,
) -> list[IndicatorEvent]:
    """`(時刻, フレーム)` の列を走査してインジケータの表示区間を返す。

    連続 KO の更新は 0.15-0.35 秒間隔で来るため、呼び出し側は 0.1 秒以下で
    フレームを供給すること (note 4-9)。
    """
    tpls = templates if templates is not None else load_templates()

    def generator() -> Iterable[tuple[float, str | None, float]]:
        for timestamp, frame in frames:
            hit = detect_indicator(frame, layout, tpls)
            yield timestamp, (hit.kind if hit else None), (hit.score if hit else 0.0)

    return group_detections(generator(), max_gap=max_gap, min_samples=min_samples)


__all__ = [
    "IndicatorEvent",
    "IndicatorHit",
    "IndicatorLayout",
    "Rect",
    "TextMatch",
    "calibrate_layout",
    "classify_text",
    "detect_indicator",
    "group_detections",
    "match_text",
    "resolve_layout",
    "scan_indicators",
]
