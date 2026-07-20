# allaganeye/video/vtuber_timeline.py
"""VTuber presence x motion timeline detection (V0-V4, spec 2026-07-17 sec. #895).

`--vtuber` 専用の境界候補 generator。blackout 起点 (candidate-classify) では
境界 blackout が 1-3s しかなく系統的に under-detect するため (PoC report sec. 2)、
「試合中である」証拠 (at-anchor presence AND band motion) の timeline から
試合区間を直接切り出す (V0-V2)。V3 は gap merge 裁定 + 境界 snap、V4 は
at-anchor presence quorum validation (#822 masked L2 と同 primitive)。
OBS / masked path からは import されない。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from allaganeye.video.capture_region import RegionTimeline, ScorebarLocalization
    from allaganeye.video.detector import DetectionStats, MatchBoundary

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
    除外する。境界精度は stride 相当 (精密化は V3 refine_segments で実施済み)。
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
hit 率 (~21% @conf>=0.5、PoC report sec. 3) でも期待 ~10 hits を確保する."""

_VT_ANCHOR_MIN_CONF = 0.5
"""VTuber anchor の conf 事前フィルタ。masked の 0.7 は Onsal true hit
(median 0.589) を殺すため使わない (PoC report sec. 3)。FP は dominant cluster
の y 投票で抑制する."""

_VT_ANCHOR_MIN_HITS = 5
"""VTuber anchor の minimum hit count。masked と同値の下限。
48 samples x 20.8% expected hit rate (Onsal PoC sec. 3) ~= 10 hits に対する
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


LOW_CONFIDENCE_SEGMENT_S = 1800.0
"""30min 超 segment は result-merge 型見逃しの疑い (spec sec.2 V4)."""


def detect_matches_timeline(
    video_path: Path,
    duration_hint: float,
    *,
    min_match_duration: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    stats: DetectionStats | None = None,
) -> tuple[list[MatchBoundary], RegionTimeline] | None:
    """V0 -> V1 -> V2 -> V3 -> V4 orchestration。None = timeline 不能 (caller が縮退)。

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
    # V2 空チェック通過後に stats を記録する (V2 が non-empty を保証してから)
    if stats is not None:
        stats["vtuber_timeline_probes"] = len(probes)
        stats["vtuber_anchor_confidence"] = float(anchor.confidence)
    # V3: gap merge 裁定 + 確定境界 snap
    boundaries = refine_segments(
        video_path, anchor, boundaries, workers=workers, stats=stats
    )
    # V4: at-anchor presence quorum validation (#822 masked L2 と同 primitive)
    # local_stats を使って _validate_match_segments を呼ぶ: main stats への
    # masked_segments_dropped キー混入と verbose 二重表示を防ぐ。
    # on_all_drop="empty" で全滅時は [] を返し、直後の None 縮退で legacy path へ。
    local_stats: dict = {}
    boundaries = detector._validate_match_segments(
        video_path,
        boundaries,
        anchor,
        workers,
        local_stats,  # type: ignore[arg-type]
        duration_hint,
        on_all_drop="empty",
    )
    if not boundaries:
        # V4 が全 segment を drop した場合も None (defense-in-depth、空 authoritative 禁止)
        # on_all_drop="empty" が発火した場合もここに落ちる。
        # legacy 縮退 run の verbose に放棄した timeline 統計が出ないよう
        # V2 通過後に set した vtuber_* キーを main stats から pop する。
        if stats is not None:
            for _k in (
                "vtuber_timeline_probes",
                "vtuber_anchor_confidence",
                "vtuber_gaps_tested",
                "vtuber_gaps_merged",
            ):
                stats.pop(_k, None)  # type: ignore[misc]
        logger.warning(
            "vtuber timeline: no segments after V4 validation; "
            "falling back to band-crop path"
        )
        return None
    # V4 統計は空チェック通過後にのみ書く: 縮退 run の main stats に放棄した
    # timeline の統計を残さない (Round 2 finding #1)。
    # vtuber_v4_dropped: local_stats の masked_segments_dropped を translate。
    if stats is not None:
        stats["vtuber_v4_dropped"] = local_stats.get("masked_segments_dropped", 0)
    # V4 30min 低信頼フラグ: result merge 型見逃しの疑いがある長尺 segment に警告
    low = [b for b in boundaries if b["end"] - b["start"] > LOW_CONFIDENCE_SEGMENT_S]
    for b in low:
        logger.warning(
            "vtuber timeline: segment %.0f-%.0f exceeds %.0fs; low-confidence "
            "(possible merged matches)",
            b["start"],
            b["end"],
            LOW_CONFIDENCE_SEGMENT_S,
        )
    if stats is not None:
        stats["vtuber_low_confidence_segments"] = len(low)
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
"""V3 merge 裁定の対象 gap 上限 (秒)。実測 FN run 最大 ~250s (PoC sec.5)。
300s 超の gap は真の境界のみ (min_match_duration と同値)."""

MERGE_RATE = 0.10
"""merge 裁定の anchor presence rate 閾値。FN run ~24% vs 真 lobby ~1.5%
(1s stride、PoC sec.5) の 15 倍分離の中間."""

FROZEN_MAX = 1.0
"""凍結 probe の band MAD 上限。リザルト/replay 静止 0.13-0.83 (PoC sec.3)."""

FROZEN_RUN_MIN_PROBES = 10
"""凍結 marker とみなす最小連続 probe 数 (=10s @1s)。リザルト/replay の
静止表示は 30s+ 持続 (PoC sec.7.4)、試合中の瞬間静止と区別する."""

BLACKOUT_B_MAX = 30.0
"""band brightness の blackout 閾値。境界 blackout は band_b ~0-7、
band crop の暗転 floor ~17-20 実測 (#809) に margin."""

GAP_STRIDE = 1.0
"""V3 gap dense probe の stride (秒)。blackout/presence edge snap もこの
1s 系列に対して行う (spec V3 (b) erratum: 0.25s の局所再 probe は
+-15s gate に対して over-engineering のため不採用)."""

EDGE_EXT_S = 45.0
"""V2 粗 edge の平滑ズレ吸収のための gap probe 拡張幅 (秒)。
probe_gap の t0/t1 をそれぞれ EDGE_EXT_S だけ外側に拡張する (#895 P3)."""

SNAP_FLICKER_TOL = 10
"""evidence run の flicker 許容 probe 数。この数以下の False gap は
True run 内に取り込んで 1 つの run にまとめる (#895 P3)."""

BLACKOUT_ADJACENCY_S = 30.0
"""blackout snap を許す evidence 隣接距離 (秒)。blackout run の前後
この秒数以内に evidence probe がなければ blackout は snap に使わない
(非隣接 blackout ドラッグを根絶する #895 P3)."""


@dataclass(frozen=True)
class GapProbe:
    """V3 gap dense probe。band_b (band 平均輝度) を持つ点が TimelineProbe と違う。

    band_mad / band_b が None = decode 失敗 (UNKNOWN、判定の分母から除外)。
    """

    t: float
    present: bool
    band_mad: float | None
    band_b: float | None


def _blackout_runs(
    probes: Sequence[GapProbe], blackout_b_max: float
) -> list[tuple[int, int]]:
    """band_b <= 閾値の連続 run を (start_idx, end_idx) inclusive で返す。"""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, p in enumerate(probes):
        is_black = p.band_b is not None and p.band_b <= blackout_b_max
        if is_black and start is None:
            start = i
        elif not is_black and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(probes) - 1))
    return runs


def _evidence_flags(
    probes: Sequence[GapProbe], *, frozen_max: float = FROZEN_MAX
) -> list[bool]:
    """match evidence = present AND not frozen (band_mad >= frozen_max)。UNKNOWN は False。

    frozen-present (replay/result 静止画面) は evidence にしない。
    UNKNOWN (band_mad=None) も evidence にしない。
    """
    return [
        p.present and p.band_mad is not None and p.band_mad >= frozen_max
        for p in probes
    ]


def _tolerant_runs(
    flags: Sequence[bool], tol: int = SNAP_FLICKER_TOL
) -> list[tuple[int, int]]:
    """True run を tol 個までの False gap を跨いで結合した (start_idx, end_idx) inclusive 列。

    PoC gt_boundary_probe._runs と同一アルゴリズム。将来の共用のため production 側に置く。
    """
    runs: list[tuple[int, int]] = []
    start: int | None = None
    gap = 0
    last_true: int | None = None
    for i, f in enumerate(flags):
        if f:
            if start is None:
                start = i
            last_true = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > tol and last_true is not None:
                runs.append((start, last_true))
                start = None
    if start is not None and last_true is not None:
        runs.append((start, last_true))
    return runs


def snap_segment_edges(
    prev_end: float,
    next_start: float,
    gap_probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
) -> tuple[float, float]:
    """V3-b (P3): 物理エッジ検出による確定境界精密化 (純関数)。

    evidence run (present AND not frozen) の先頭/末尾から境界を検出し、
    隣接条件付き blackout run で上書きする。frozen-present (replay/result)
    は evidence から除外する (frozen 除外 #895 P3)。

    処理順:
    1. _evidence_flags / _tolerant_runs で leading/trailing evidence run を検出
       - new_end: leading run の末尾 (probes 先頭 15 probe 以内に run start あり)
       - new_start: trailing run の先頭 (probes 末尾 15 probe 以内に run end あり)
    2. blackout run の隣接条件チェック (BLACKOUT_ADJACENCY_S 以内に evidence あり)
       - 条件を満たす blackout run で new_end / new_start を上書き
       - 条件を満たさない blackout は無視 (非隣接 blackout ドラッグ根絶 #895 P3)
    3. 交差 (new_end >= new_start) -> (prev_end, next_start) に縮退
    """
    probes = list(gap_probes)
    if not probes:
        return prev_end, next_start

    new_end, new_start = prev_end, next_start

    # Step 1: evidence run で leading/trailing edge を検出
    flags = _evidence_flags(probes)
    ev_runs = _tolerant_runs(flags)

    _EDGE_PROBE_LIMIT = (
        15  # run start/end が probes 先頭/末尾から何 probe 以内ならエッジとみなす
    )

    # new_end: leading evidence run の末尾 (run start が先頭 _EDGE_PROBE_LIMIT 以内)
    if ev_runs and ev_runs[0][0] < _EDGE_PROBE_LIMIT:
        new_end = probes[ev_runs[0][1]].t

    # new_start: trailing evidence run の先頭 (run end が末尾 _EDGE_PROBE_LIMIT 以内)
    if ev_runs and (len(probes) - 1 - ev_runs[-1][1]) < _EDGE_PROBE_LIMIT:
        new_start = probes[ev_runs[-1][0]].t

    # Step 2: blackout snap (隣接条件付き)
    b_runs = _blackout_runs(probes, blackout_b_max)

    # new_end の blackout 上書き: 最初の blackout run の start t から
    # 遡って BLACKOUT_ADJACENCY_S 以内に evidence probe があること
    for brun in b_runs:
        brun_t_start = probes[brun[0]].t
        adjacent = any(
            flags[i] and (brun_t_start - probes[i].t) <= BLACKOUT_ADJACENCY_S
            for i in range(brun[0])
        )
        if adjacent:
            new_end = probes[brun[0]].t
            break  # 最初の該当 run のみ

    # new_start の blackout 上書き: 最後の blackout run の end t から
    # 先 BLACKOUT_ADJACENCY_S 以内に evidence probe があること
    for brun in reversed(b_runs):
        brun_t_end = probes[brun[1]].t
        adjacent = any(
            flags[i] and (probes[i].t - brun_t_end) <= BLACKOUT_ADJACENCY_S
            for i in range(brun[1] + 1, len(probes))
        )
        if adjacent:
            new_start = probes[brun[1]].t
            break  # 最後の該当 run のみ

    # Step 3: 交差チェック -> 縮退
    if new_end >= new_start:
        return prev_end, next_start
    return new_end, new_start


_LONG_GAP_EDGE_WINDOW_S = 60.0
"""gap > MERGE_GAP_MAX のとき両端それぞれ probe する窓幅 (秒)."""


def _probe_gap_one(video_path: Path, t: float, anchor) -> GapProbe:
    from allaganeye.video import capture_region, detector

    raw1 = detector._probe_frame_rgb_hires(video_path, t)
    raw2 = detector._probe_frame_rgb_hires(video_path, t + TIMELINE_PAIR_DT)
    if raw1 is None or raw2 is None:
        return GapProbe(t=t, present=False, band_mad=None, band_b=None)
    h, w = detector._SCOREBAR_V2_PROBE_HEIGHT, detector._SCOREBAR_V2_PROBE_WIDTH
    f1 = np.frombuffer(raw1, np.uint8).reshape(h, w, 3)
    f2 = np.frombuffer(raw2, np.uint8).reshape(h, w, 3)
    y0, y1, x0, x1 = _band_slice(anchor)
    b1 = f1[y0:y1, x0:x1].astype(np.int16)
    b2 = f2[y0:y1, x0:x1].astype(np.int16)
    band_mad = float(np.abs(b1 - b2).mean()) if b1.size else 0.0
    band_b = float(b1.mean()) if b1.size else 0.0
    present = capture_region.localize_scorebar_at_anchor(f1, anchor) is not None
    return GapProbe(t=t, present=present, band_mad=band_mad, band_b=band_b)


def probe_gap(
    video_path: Path,
    anchor,
    t0: float,
    t1: float,
    *,
    stride: float = GAP_STRIDE,
    workers: int | None = None,
) -> list[GapProbe]:
    """[t0, t1) を stride 間隔で dense probe する (V3 用、例外は probe 単位隔離)."""
    ts = [round(t0 + i * stride, 2) for i in range(max(0, int((t1 - t0) / stride)))]
    if not ts:
        return []
    max_workers = workers or min(os.cpu_count() or 4, 16)

    def _one(t: float) -> GapProbe:
        try:
            return _probe_gap_one(video_path, t, anchor)
        except Exception:
            logger.debug("gap probe failed at t=%.1fs", t, exc_info=True)
            return GapProbe(t=t, present=False, band_mad=None, band_b=None)

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(_one, ts))


def refine_segments(
    video_path: Path,
    anchor,
    segments: list[MatchBoundary],
    *,
    workers: int | None = None,
    stats: DetectionStats | None = None,
) -> list[MatchBoundary]:
    """V3: 隣接 segment 間 gap の merge 裁定 + 確定境界の snap。

    per-gap 例外隔離: probe/裁定に失敗した gap は V2 の粗い結果を維持する
    (V3 は改善のみ、失敗しても悪化させない)。
    """
    if len(segments) < 2:
        return list(segments)
    result: list[MatchBoundary] = [cast("MatchBoundary", dict(segments[0]))]
    for nxt in segments[1:]:
        prev = result[-1]
        gap = nxt["start"] - prev["end"]
        try:
            if gap <= MERGE_GAP_MAX:
                # 短 gap: probe 範囲を EDGE_EXT_S だけ外側に拡張する (#895 P3)
                t0_ext = max(0.0, prev["end"] - EDGE_EXT_S)
                t1_ext = nxt["start"] + EDGE_EXT_S
                probes = probe_gap(video_path, anchor, t0_ext, t1_ext, workers=workers)
                if stats is not None:
                    stats["vtuber_gaps_tested"] = stats.get("vtuber_gaps_tested", 0) + 1
                # adjudicate_gap には中央 slice (t が [prev_end, next_start] 内のみ) を渡す
                central = [p for p in probes if prev["end"] <= p.t <= nxt["start"]]
                if adjudicate_gap(central) == "merge":
                    if stats is not None:
                        stats["vtuber_gaps_merged"] = (
                            stats.get("vtuber_gaps_merged", 0) + 1
                        )
                    prev["end"] = nxt["end"]
                    continue
                # snap には全 probes (拡張分含む) を渡す
                new_end, new_start = snap_segment_edges(
                    prev["end"], nxt["start"], probes
                )
            else:
                # 長 gap: 両端窓を EDGE_EXT_S だけ外側に拡張する (#895 P3)
                head = probe_gap(
                    video_path,
                    anchor,
                    max(0.0, prev["end"] - EDGE_EXT_S),
                    prev["end"] + _LONG_GAP_EDGE_WINDOW_S,
                    workers=workers,
                )
                tail = probe_gap(
                    video_path,
                    anchor,
                    nxt["start"] - _LONG_GAP_EDGE_WINDOW_S,
                    nxt["start"] + EDGE_EXT_S,
                    workers=workers,
                )
                new_end, _ = snap_segment_edges(
                    prev["end"], prev["end"] + _LONG_GAP_EDGE_WINDOW_S, head
                )
                _, new_start = snap_segment_edges(
                    nxt["start"] - _LONG_GAP_EDGE_WINDOW_S, nxt["start"], tail
                )
        except Exception:
            logger.warning(
                "vtuber timeline: gap refinement failed at %.0f-%.0f; keeping "
                "coarse boundaries",
                prev["end"],
                nxt["start"],
                exc_info=True,
            )
            result.append(cast("MatchBoundary", dict(nxt)))
            continue
        prev["end"] = new_end
        follower = cast("MatchBoundary", dict(nxt))
        follower["start"] = new_start
        result.append(follower)
    return result


def adjudicate_gap(
    probes: Sequence[GapProbe],
    *,
    merge_rate: float = MERGE_RATE,
    frozen_max: float = FROZEN_MAX,
    frozen_run_min: int = FROZEN_RUN_MIN_PROBES,
    blackout_b_max: float = BLACKOUT_B_MAX,
) -> str:
    """V3-a: 隣接 segment 間 gap が偽分割 (merge) か真の境界 (boundary) か。

    判定順序 (spec sec.2 V3 (a)、positive marker 優先):
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
