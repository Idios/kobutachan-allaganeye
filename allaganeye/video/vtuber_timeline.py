# allaganeye/video/vtuber_timeline.py
"""VTuber presence x motion timeline detection (V0-V2, spec 2026-07-17 U+00A7 #895).

`--vtuber` 専用の境界候補 generator。blackout 起点 (candidate-classify) では
境界 blackout が 1-3s しかなく系統的に under-detect するため (PoC report U+00A7 2)、
「試合中である」証拠 (at-anchor presence AND band motion) の timeline から
試合区間を直接切り出す。OBS / masked path からは import されない。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from allaganeye.video.capture_region import ScorebarLocalization
    from allaganeye.video.detector import MatchBoundary

logger = logging.getLogger(__name__)

TIMELINE_STRIDE = 10.0
"""V1 scan stride (seconds). PoC: 6 source で試合構造を再現、4h VOD ~= 3-6 分."""

TIMELINE_PAIR_DT = 0.5
"""Motion 測定用フレームペアの時間差 (seconds)."""

TIMELINE_MAD_MIN = 1.5
"""band MAD の evidence 閾値。PoC: 試合中最低 >=2.2 vs 凍結画面 <=0.83."""

TIMELINE_WINDOW = 9
"""rolling window の probe 数 (=90s @10s stride)。Onsal 弱 presence を bridge."""

TIMELINE_QUORUM = 2
"""window 内の evidence 最小数。lobby (~1-22% presence) を弾く."""


@dataclass(frozen=True)
class TimelineProbe:
    """V1 scan の 1 probe。band_mad=None は decode 失敗 (UNKNOWN、非 evidence)."""

    t: float
    present: bool
    band_mad: float | None


def segment_timeline(
    probes: Sequence[TimelineProbe],
    *,
    min_match_duration: float,
    mad_min: float = TIMELINE_MAD_MIN,
    window: int = TIMELINE_WINDOW,
    quorum: int = TIMELINE_QUORUM,
) -> list[MatchBoundary]:
    """V2: evidence timeline から粗い試合 segment を抽出する (純関数)。

    probe evidence = present AND band_mad >= mad_min。中心 rolling window
    (probe i の前後 window//2) に evidence が quorum 個以上ある probe を
    in-match とし、連続 in-match run を segment 化、min_match_duration 未満を
    除外する。境界精度は stride 相当 (精密化は P2 の V3)。
    """
    n = len(probes)
    if n == 0:
        return []
    evid = [
        p.present and p.band_mad is not None and p.band_mad >= mad_min for p in probes
    ]
    half = window // 2
    segs: list[list[float]] = []
    prev_in = False
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        in_match = sum(evid[lo:hi]) >= quorum
        if in_match:
            if prev_in:
                segs[-1][1] = probes[i].t
            else:
                segs.append([probes[i].t, probes[i].t])
        prev_in = in_match
    return [
        {"start": a, "end": b, "type": "fl_match"}
        for a, b in segs
        if b - a >= min_match_duration
    ]


_VT_ANCHOR_NUM_SAMPLES = 48
"""VTuber anchor consensus のサンプル数。masked (24) の倍: Onsal の低 conf
hit 率 (~21% @conf>=0.5、PoC report U+00A7 3) でも期待 ~10 hits を確保する."""

_VT_ANCHOR_MIN_CONF = 0.5
"""VTuber anchor の conf 事前フィルタ。masked の 0.7 は Onsal true hit
(median 0.589) を殺すため使わない (PoC report U+00A7 3)。FP は dominant cluster
の y 投票で抑制する."""

_VT_ANCHOR_MIN_HITS = 5
"""VTuber anchor の minimum hit count。masked と同値の下限。
48 samples U+00D7 20.8% expected hit rate (Onsal PoC U+00A7 3) ~= 10 hits に対する
安全マージン (約 50%) で、Onsal 最悪ケースでも解決できる範囲に設定。"""


def resolve_vtuber_anchor(
    video_path: Path, duration_hint: float
) -> ScorebarLocalization | None:
    """V0: per-video scorebar anchor を疎サンプル consensus で解決する。

    detector._resolve_scorebar_anchor (#822 masked) と同構造だが VTuber 定数
    (48 samples / conf 0.5 / min hits 5) を使う。None = 解決不能 (caller は
    現行 band-crop path へ縮退する)。例外は握り潰して None (縮退 floor)。
    """
    from allaganeye.video import capture_region, detector
    from allaganeye.video.capture_region import consensus_scorebar_localization
    from allaganeye.video.probe_state import PresenceState

    def _localize_at(t: float):
        raw = detector._probe_frame_rgb_hires(video_path, t)
        if raw is None:
            return PresenceState.UNKNOWN
        # capture_region.localize_from_rgb_bytes はモジュール属性経由で参照する。
        # テストがこの seam を patch するため、直接 import すると patch が効かなくなる。
        loc = capture_region.localize_from_rgb_bytes(
            raw,
            height=detector._SCOREBAR_V2_PROBE_HEIGHT,
            width=detector._SCOREBAR_V2_PROBE_WIDTH,
        )
        if loc is not None and loc.confidence < _VT_ANCHOR_MIN_CONF:
            return None
        return loc

    try:
        return consensus_scorebar_localization(
            duration=duration_hint,
            localize_fn=_localize_at,
            num_samples=_VT_ANCHOR_NUM_SAMPLES,
            min_hits=_VT_ANCHOR_MIN_HITS,
        )
    except Exception:
        logger.warning(
            "vtuber anchor consensus failed with exception; timeline path unavailable",
            exc_info=True,
        )
        return None


UNKNOWN_ABORT_RATIO = 0.5
"""decode 失敗 probe がこの比率を超えたら timeline を放棄して縮退する."""

_BAND_PAD_PX = 10
"""band MAD 測定域の上下パディング (probe px)。PoC 計測と同値."""


def _band_slice(anchor) -> tuple[int, int, int, int]:
    """anchor から MAD 測定用の band px 範囲 (y0, y1, x0, x1) を返す。"""
    from allaganeye.video import detector

    y0 = max(0, anchor.y_top - _BAND_PAD_PX)
    y1 = min(detector._SCOREBAR_V2_PROBE_HEIGHT, anchor.y_bottom + _BAND_PAD_PX + 1)
    x0 = max(0, anchor.x_left)
    x1 = min(detector._SCOREBAR_V2_PROBE_WIDTH, anchor.x_right + 1)
    return y0, y1, x0, x1


def _probe_pair(video_path: Path, t: float, anchor) -> TimelineProbe:
    """1 probe: frame pair decode + at-anchor presence + band MAD 計算。"""
    from allaganeye.video import capture_region, detector

    raw1 = detector._probe_frame_rgb_hires(video_path, t)
    raw2 = detector._probe_frame_rgb_hires(video_path, t + TIMELINE_PAIR_DT)
    if raw1 is None or raw2 is None:
        return TimelineProbe(t=t, present=False, band_mad=None)
    h = detector._SCOREBAR_V2_PROBE_HEIGHT
    w = detector._SCOREBAR_V2_PROBE_WIDTH
    f1 = np.frombuffer(raw1, np.uint8).reshape(h, w, 3)
    f2 = np.frombuffer(raw2, np.uint8).reshape(h, w, 3)
    y0, y1, x0, x1 = _band_slice(anchor)
    b1 = f1[y0:y1, x0:x1].astype(np.int16)
    b2 = f2[y0:y1, x0:x1].astype(np.int16)
    band_mad = float(np.abs(b1 - b2).mean()) if b1.size else 0.0
    present = capture_region.localize_scorebar_at_anchor(f1, anchor) is not None
    return TimelineProbe(t=t, present=present, band_mad=band_mad)


def scan_timeline(
    video_path: Path,
    duration_hint: float,
    anchor,
    *,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
) -> list[TimelineProbe]:
    """V1: 全域を TIMELINE_STRIDE 間隔で probe する (frame pair + at-anchor)。

    probe あたり decode 2 回 (`-ss` 単発 x2、fps filter 不使用 #575)。
    例外は probe 単位で UNKNOWN に隔離する (1 probe の失敗で scan を壊さない)。
    """
    ts = [
        round(i * TIMELINE_STRIDE, 2)
        for i in range(max(1, int(duration_hint / TIMELINE_STRIDE)))
    ]
    max_workers = workers or min(os.cpu_count() or 4, 16)
    results: list[TimelineProbe] = []

    def _one(t: float) -> TimelineProbe:
        try:
            return _probe_pair(video_path, t, anchor)
        except Exception:
            logger.debug("timeline probe failed at t=%.1fs", t, exc_info=True)
            return TimelineProbe(t=t, present=False, band_mad=None)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for i, probe in enumerate(ex.map(_one, ts)):
            results.append(probe)
            if progress_callback is not None:
                progress_callback(i + 1, len(ts), 0)
    return results


def detect_matches_timeline(
    video_path: Path,
    duration_hint: float,
    *,
    min_match_duration: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
):
    """V0 -> V1 -> V2 orchestration。None = timeline 不能 (caller が縮退)。

    Returns:
        (boundaries, region_timeline) | None
    """
    from allaganeye.video import detector
    from allaganeye.video.capture_region import (
        RegionTimeline,
        band_region_from_localization,
    )

    anchor = resolve_vtuber_anchor(video_path, duration_hint)
    if anchor is None:
        logger.warning(
            "vtuber timeline: anchor consensus miss; falling back to band-crop path"
        )
        return None
    probes = scan_timeline(
        video_path,
        duration_hint,
        anchor,
        workers=workers,
        progress_callback=progress_callback,
    )
    unknown = sum(1 for p in probes if p.band_mad is None)
    if probes and unknown / len(probes) > UNKNOWN_ABORT_RATIO:
        logger.warning(
            "vtuber timeline: %d/%d probes UNKNOWN (> %.0f%%); falling back",
            unknown,
            len(probes),
            UNKNOWN_ABORT_RATIO * 100,
        )
        return None
    boundaries = segment_timeline(probes, min_match_duration=min_match_duration)
    if not boundaries:
        # 縮退 floor (Codex R1 high): anchor 成功 + UNKNOWN 過半未満でも
        # presence x motion が 1 segment も形成しない場合、空結果を
        # authoritative にすると legacy band-crop 検出の機会を奪い
        # 「現状より悪化しない」floor が破れる。空 = timeline 不能として
        # None を返し、caller を legacy path へ縮退させる。
        logger.warning(
            "vtuber timeline: segmentation produced no segments; "
            "falling back to band-crop path"
        )
        return None
    region = RegionTimeline(
        coarse=band_region_from_localization(
            anchor,
            probe_w=detector._SCOREBAR_V2_PROBE_WIDTH,
            probe_h=detector._SCOREBAR_V2_PROBE_HEIGHT,
        ),
        segments=[],
        fallback_reason=None,
    )
    return boundaries, region


MERGE_GAP_MAX = 300.0
"""V3 merge 裁定の対象 gap 上限 (秒)。実測 FN run 最大 ~250s (PoC U+00A75)。
300s 超の gap は真の境界のみ (min_match_duration と同値)."""

MERGE_RATE = 0.10
"""merge 裁定の anchor presence rate 閾値。FN run ~24% vs 真 lobby ~1.5%
(1s stride、PoC U+00A75) の 15 倍分離の中間."""

FROZEN_MAX = 1.0
"""凍結 probe の band MAD 上限。リザルト/replay 静止 0.13-0.83 (PoC U+00A73)."""

FROZEN_RUN_MIN_PROBES = 10
"""凍結 marker とみなす最小連続 probe 数 (=10s @1s)。リザルト/replay の
静止表示は 30s+ 持続 (PoC U+00A77.4)、試合中の瞬間静止と区別する."""

BLACKOUT_B_MAX = 30.0
"""band brightness の blackout 閾値。境界 blackout は band_b ~0-7、
band crop の暗転 floor ~17-20 実測 (#809) に margin."""

GAP_STRIDE = 1.0
"""V3 gap dense probe の stride (秒)."""

SNAP_STRIDE = 0.25
"""blackout エッジ精密化の stride (秒)."""


@dataclass(frozen=True)
class GapProbe:
    """V3 gap dense probe。band_b (band 平均輝度) を持つ点が TimelineProbe と違う。

    band_mad / band_b が None = decode 失敗 (UNKNOWN、判定の分母から除外)。
    """

    t: float
    present: bool
    band_mad: float | None
    band_b: float | None


def adjudicate_gap(
    probes: Sequence[GapProbe],
    *,
    merge_rate: float = MERGE_RATE,
    frozen_max: float = FROZEN_MAX,
    frozen_run_min: int = FROZEN_RUN_MIN_PROBES,
    blackout_b_max: float = BLACKOUT_B_MAX,
) -> str:
    """V3-a: 隣接 segment 間 gap が偽分割 (merge) か真の境界 (boundary) か。

    判定順序 (spec U+00A72 V3 (a)、positive marker 優先):
    1. blackout marker (band_b <= blackout_b_max の probe) があれば boundary
    2. 凍結 run (band_mad < frozen_max が frozen_run_min 連続) があれば boundary
       (リザルト/replay 静止画面 = 真の境界の証拠。presence の有無は問わない)
    3. valid probe の present rate >= merge_rate なら merge (試合中 FN run)、
       未満なら boundary (真の lobby)
    4. valid probe ゼロ (空 / 全 UNKNOWN) は boundary (証拠なしで merge しない)
    """
    valid = [p for p in probes if p.band_b is not None and p.band_mad is not None]
    if not valid:
        return "boundary"
    if any(p.band_b is not None and p.band_b <= blackout_b_max for p in valid):
        return "boundary"
    run = 0
    for p in valid:
        if p.band_mad is not None and p.band_mad < frozen_max:
            run += 1
            if run >= frozen_run_min:
                return "boundary"
        else:
            run = 0
    present = sum(1 for p in valid if p.present)
    if present / len(valid) >= merge_rate:
        return "merge"
    return "boundary"
