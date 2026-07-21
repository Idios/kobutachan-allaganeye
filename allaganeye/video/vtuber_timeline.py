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

    hard-gap break (V2 拡張 #895 P3 6周目): quorum 平滑化後の in-match run に対して
    raw evidence フラグ上で TIMELINE_HARD_GAP_PROBES 以上連続の非 evidence sub-run が
    あれば分割候補とする。両 fragment の evidence 範囲 duration が両方 min_match_duration
    以上のときのみ分割する (片方でも短い場合は分割しない = silent drop 防止)。
    分割境界: gap の直前 evidence probe t = end / 直後 evidence probe t = start。
    V3 (refine_segments) が gap を merge に戻す前提の分割であるため、
    in-match 長途切れは rate 判定で merge 候補になる設計。
    shirurori M7-M8: 59s gap で rolling quorum が bridge し V3 裁定に渡らない問題を解消。
    """
    n = len(probes)
    if n == 0:
        return []
    evid = [
        p.present and p.band_mad is not None and p.band_mad >= mad_min for p in probes
    ]
    half = window // 2

    # quorum 平滑化: in_match_flags[i] は probe i が in-match かどうか
    in_match_flags = [False] * n
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        in_match_flags[i] = sum(evid[lo:hi]) >= quorum

    # in-match run を収集 (各 run = (start_idx, end_idx) inclusive)
    in_match_runs: list[tuple[int, int]] = []
    run_start: int | None = None
    for i in range(n):
        if in_match_flags[i]:
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                in_match_runs.append((run_start, i - 1))
                run_start = None
    if run_start is not None:
        in_match_runs.append((run_start, n - 1))

    # hard-gap break: in-match run 内の raw evid で TIMELINE_HARD_GAP_PROBES 以上の
    # 非 evidence sub-run を検査し、fragment 両方が min_match_duration 以上なら分割する
    final_segs: list[tuple[float, float]] = []
    for run_s, run_e in in_match_runs:
        # この run の raw evid 部分列
        run_evid = evid[run_s : run_e + 1]  # 0-indexed within run

        # 非 evidence の連続 sub-run を探す
        gap_runs: list[
            tuple[int, int]
        ] = []  # (rel_start, rel_end) within run, inclusive
        g_start: int | None = None
        for rel_i, ev_flag in enumerate(run_evid):
            if not ev_flag:
                if g_start is None:
                    g_start = rel_i
            else:
                if g_start is not None:
                    gap_runs.append((g_start, rel_i - 1))
                    g_start = None
        if g_start is not None:
            gap_runs.append((g_start, len(run_evid) - 1))

        # TIMELINE_HARD_GAP_PROBES 以上の gap を分割候補として評価
        split_points: list[tuple[int, int]] = []  # (gap rel_start, gap rel_end)
        for g_s, g_e in gap_runs:
            if (g_e - g_s + 1) >= TIMELINE_HARD_GAP_PROBES:
                split_points.append((g_s, g_e))

        if not split_points:
            # 分割なし: run 全体を 1 segment として追加
            final_segs.append((probes[run_s].t, probes[run_e].t))
            continue

        # 分割: split_point ごとに fragment を切り出す
        # fragment の start/end は gap 両端の evidence probe t を使う
        fragments: list[tuple[float, float]] = []
        frag_abs_start = run_s  # abs index
        for g_s, g_e in split_points:
            # frag end: gap 直前の evidence probe (run 内 g_s - 1, abs = run_s + g_s - 1)
            frag_end_rel = g_s - 1
            if frag_end_rel < 0:
                # gap が run 先頭から始まる: fragment が空
                frag_abs_start = run_s + g_e + 1
                continue
            frag_end_abs = run_s + frag_end_rel
            # evidence 範囲: frag_abs_start から frag_end_abs の evid true 部分
            frag_ev_indices = [
                k for k in range(frag_abs_start, frag_end_abs + 1) if evid[k]
            ]
            if not frag_ev_indices:
                frag_abs_start = run_s + g_e + 1
                continue
            frag_start_t = probes[frag_ev_indices[0]].t
            frag_end_t = probes[frag_ev_indices[-1]].t
            fragments.append((frag_start_t, frag_end_t))
            frag_abs_start = run_s + g_e + 1

        # 最後の fragment: gap の次から run 末尾まで
        if frag_abs_start <= run_e:
            tail_ev_indices = [k for k in range(frag_abs_start, run_e + 1) if evid[k]]
            if tail_ev_indices:
                fragments.append(
                    (
                        probes[tail_ev_indices[0]].t,
                        probes[tail_ev_indices[-1]].t,
                    )
                )

        # fragment 全てが min_match_duration 以上のときのみ分割を採用する
        # (1 つでも短い fragment があれば分割しない = run 全体を 1 segment)
        if fragments and all(e - s >= min_match_duration for s, e in fragments):
            final_segs.extend(fragments)
        else:
            # 分割しない: run 全体を 1 segment
            final_segs.append((probes[run_s].t, probes[run_e].t))

    return [
        {"start": a, "end": b, "type": "fl_match"}
        for a, b in final_segs
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

MERGE_RATE = 0.15
"""merge 裁定の anchor presence rate 閾値。実測 rate 0.137 (meteor replay gap) を
boundary 側に倒すため 0.10 から 0.15 に引き上げ (Idios 承認 2026-07-21 #895 P3 4周目)。
FN run ~24% vs 真 lobby ~1.5% の分離は引き上げ後も十分。"""

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
start 側 snap 拡張・peek probe に使う (#895 P3)。"""

EDGE_EXT_END_S = 120.0
"""end snap probe の左側拡張幅 (秒)。
shinryu M3 型: collapse が粗 end より ~80s 前にある場合でも窓に収める
(旧 _LONG_GAP_EDGE_WINDOW_S=60s だと窓外になる #895 P3 4周目)。"""

SNAP_FLICKER_TOL = 10
"""evidence run の flicker 許容 probe 数。この数以下の False gap は
True run 内に取り込んで 1 つの run にまとめる (#895 P3)."""

EDGE_PROBE_LIMIT = 15
"""snap のエッジ採用条件: evidence run の start/end が gap probe 系列の
先頭/末尾から数えてこの probe 数以内にあるときのみ leading/trailing エッジと
みなす (系列中央の孤立 run を境界と誤認しない)."""

INTRA_EVIDENCE_BEFORE_S = 5.0
"""_snap_start in-match guard: blackout run 先頭 probe の t から before 側 (秒)。
この秒数以内に evidence probe があれば has_evidence_before=True。
120s 広窓先頭の前試合 evidence が guard を誤発火させないよう局所窓にする
(Bug B 修正: shikke M6 実測原因)."""

INTRA_EVIDENCE_AFTER_S = 10.0
"""_snap_start in-match guard: blackout run 末尾 probe の t から after 側 (秒)。
before=5s では shinryu 型瞬断 (直後 8s に evidence) が after を抜ける。
8s < 10s -> 成立 -> guard 発火 -> 除外できる。
after 側を before より広くすることで瞬断と zone-in の分離精度を上げる."""

END_FAR_RESCUE_S = 60.0
"""_snap_end: leading run が粗 end (lo) より END_FAR_RESCUE_S 超前に終端した場合に
hybrid 救済を試みる (Bug C 修正: kyuma M6 / meteor M5 実測原因)。
候補となる後続 run: 長さ >= 3 probe かつ run 末尾 t < mid かつ run 末尾 t >= lo - END_FAR_RESCUE_S."""

TIMELINE_HARD_GAP_PROBES = 5
"""V2 hard-gap break: quorum 後 in-match run 内に連続でこの probe 数以上の
非 evidence sub-run があれば分割候補とする (stride=10s で 50s)。
V3 (refine_segments) が gap を merge に戻す前提の分割。
fragment 下限ガード (両 fragment が min_match_duration 以上) で silent drop を防ぐ。
shirurori M7-M8: 59s gap で rolling quorum が bridge -> V3 裁定に渡らない問題を解消。"""


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


def _snap_end(
    probes: Sequence[GapProbe],
    lo: float,
    hi: float,
    *,
    tol: int = SNAP_FLICKER_TOL,
) -> float | None:
    """end snap: evidence run のみ (blackout は使わない)。

    leading evidence run の末尾を候補とし、(lo + hi) / 2 より前のときのみ採用。
    - run start が probes 先頭 EDGE_PROBE_LIMIT 以内 (leading run 条件)
    - 候補 t < (lo + hi) / 2 (中点制約: gap 後半に引っ張られない)

    Bug C 修正 (#895 P3 6周目): hybrid dropout rescue。
    leading run が lo - END_FAR_RESCUE_S より前に終端している場合
    (Onsal 明滅で真の collapse より 60s 超早く leading が終わる)、
    後続 evidence run のうち「長さ >= 3 probe かつ run 末尾 t < mid かつ
    run 末尾 t >= lo - END_FAR_RESCUE_S」を満たす最後のものに候補を置換する。
    置換後も候補 t < mid の中点制約を適用。

    end 側に blackout を使わない理由: in-match 瞬断 blackout (1-2 probe の真っ暗フレーム)
    が試合中に存在することがある (shinryu M5 実測)。blackout で end を決めると
    真のエンドではなく試合中の瞬断位置を返してしまう。
    None = 候補なし -> caller は粗い edge を維持する。
    """
    if not probes:
        return None
    probes_list = list(probes)
    mid = (lo + hi) / 2.0
    flags = _evidence_flags(probes_list)
    ev_runs = _tolerant_runs(flags, tol=tol)
    if not ev_runs or ev_runs[0][0] >= EDGE_PROBE_LIMIT:
        return None

    candidate = probes_list[ev_runs[0][1]].t

    # Bug C: hybrid rescue -- leading run が lo より END_FAR_RESCUE_S 以上早く終端 (dropout 疑い)
    rescue_threshold = lo - END_FAR_RESCUE_S
    if candidate < rescue_threshold:
        # 後続 run を探す: leading run より後の run (ev_runs[1:]) で eligible なものを探す
        eligible: float | None = None
        for run in ev_runs[1:]:
            run_len = run[1] - run[0] + 1
            run_end_t = probes_list[run[1]].t
            if run_len >= 3 and run_end_t < mid and run_end_t >= rescue_threshold:
                eligible = run_end_t  # 最後の eligible run を採用する (更新し続ける)
        if eligible is not None:
            candidate = eligible

    if candidate < mid:
        return candidate
    return None


def _snap_start(
    probes: Sequence[GapProbe],
    lo: float,
    hi: float,
    ext_hi: float | None = None,
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
    tol: int = SNAP_FLICKER_TOL,
) -> float | None:
    """start snap: blackout run 優先 (evidence は fallback)。

    優先順:
    1. (lo, hi] 内に完全に収まる最後の blackout run の run end -> 無条件採用。
       ただし in-match blackout を除外: blackout run end の後に evidence probe が
       存在する場合 (zone-in ではなく試合中の瞬断) はスキップする。
    2. (hi, ext_hi] 内の最初の blackout run の run end -> 採用 (ext_hi 指定時のみ)
       (V2 粗 start が真の zone-in より前のケース: 拡張窓の外側 blackout を救済)
    3. trailing evidence run (run end が probes 末尾 EDGE_PROBE_LIMIT 以内):
       run 先頭 t > (lo + hi) / 2 のときのみ採用 (中点制約: 大外れ根絶)
    4. None -> caller は粗い edge を維持する。

    GT 物理定義: start = 境界 blackout (zone-in 暗転) 明け。
    blackout run end を new_start とするのは「暗転が終わった直後が試合開始」の物理直訳。
    in-match 瞬断: blackout の後に evidence (present AND moving) が続く -> 境界ではない。
    """
    if not probes:
        return None
    probes_list = list(probes)
    flags = _evidence_flags(probes_list)
    b_runs = _blackout_runs(probes_list, blackout_b_max)

    # Priority 1: (lo, hi] 内の最後の blackout run end (in-match 瞬断を除外)
    last_in_range: tuple[int, int] | None = None
    for brun in b_runs:
        brun_t_end = probes_list[brun[1]].t
        if lo < brun_t_end <= hi:
            # in-match guard (Bug B 修正: 局所窓): blackout 前後の局所範囲に evidence が
            # 両方あれば試合中の瞬断とみなす。
            # 旧実装は窓全体 (range(0, brun[0])) を見ていたため 120s 広窓先頭の
            # 前試合 evidence が常に guard を発火させ、zone-in の採用が全滅していた。
            # 新実装: blackout run 先頭/末尾 probe の t から局所窓のみを検査する。
            # before: blackout run 先頭 probe t から INTRA_EVIDENCE_BEFORE_S 以内前
            # after: blackout run 末尾 probe t から INTRA_EVIDENCE_AFTER_S 以内後
            brun_t_start_v = probes_list[brun[0]].t
            brun_t_end_v = probes_list[brun[1]].t
            has_evidence_before = any(
                flags[j]
                for j in range(0, brun[0])
                if brun_t_start_v - probes_list[j].t <= INTRA_EVIDENCE_BEFORE_S
            )
            has_evidence_after = any(
                flags[j]
                for j in range(brun[1] + 1, len(probes_list))
                if probes_list[j].t - brun_t_end_v <= INTRA_EVIDENCE_AFTER_S
            )
            is_intra_match = has_evidence_before and has_evidence_after
            if not is_intra_match:
                last_in_range = brun
    if last_in_range is not None:
        return probes_list[last_in_range[1]].t

    # Priority 2: (hi, ext_hi] 内の最初の blackout run end
    if ext_hi is not None:
        for brun in b_runs:
            brun_t_end = probes_list[brun[1]].t
            if hi < brun_t_end <= ext_hi:
                return brun_t_end

    # Priority 3: trailing evidence run + 中点制約
    mid = (lo + hi) / 2.0
    ev_runs = _tolerant_runs(flags, tol=tol)
    if ev_runs and (len(probes_list) - 1 - ev_runs[-1][1]) < EDGE_PROBE_LIMIT:
        candidate = probes_list[ev_runs[-1][0]].t
        if candidate > mid:
            return candidate

    return None


def snap_segment_edges(
    prev_end: float,
    next_start: float,
    gap_probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
    ext_hi: float | None = None,
) -> tuple[float, float]:
    """V3-b (P3 4周目 + 6周目): 物理エッジ検出による確定境界精密化 (純関数)。

    物理規則の再設計 (#895 P3 4周目実測診断):
    - start 側: GT 物理定義 = 境界 blackout (zone-in 暗転) 明け。
      _snap_start で blackout run end を無条件採用 (中点制約なし)。
      blackout なし時のみ evidence trailing run + 中点制約 (fallback)。
    - end 側: in-match 瞬断 blackout があるため blackout は不使用。
      _snap_end で evidence leading run + 中点制約のみ。

    ext_hi (Bug A 修正 #895 P3 6周目): 内側 gap では probe 窓が next_start + EDGE_EXT_S まで
    取得済みのため ext_hi=next_start+EDGE_EXT_S を渡すことで _snap_start Priority 2
    (粗 gap の外側 blackout 救済) が内側 gap でも機能する。
    None 時は Priority 2 スキップ (旧挙動と同一)。

    交差 (new_end >= new_start) -> (prev_end, next_start) に縮退。
    """
    probes = list(gap_probes)
    if not probes:
        return prev_end, next_start

    new_end = _snap_end(probes, prev_end, next_start) or prev_end
    new_start = (
        _snap_start(
            probes,
            prev_end,
            next_start,
            ext_hi=ext_hi,
            blackout_b_max=blackout_b_max,
        )
        or next_start
    )

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


def _has_blackout_run(
    probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
    min_run: int = 2,
) -> bool:
    """probe 列に blackout run (連続 min_run probe 以上) があるか。"""
    b_runs = _blackout_runs(probes, blackout_b_max)
    return any((end - start + 1) >= min_run for start, end in b_runs)


def refine_segments(
    video_path: Path,
    anchor,
    segments: list[MatchBoundary],
    *,
    workers: int | None = None,
    stats: DetectionStats | None = None,
) -> list[MatchBoundary]:
    """V3: 隣接 segment 間 gap の merge 裁定 + 確定境界の snap。

    2 パス構成 (Fix 1 / #895 P3 2周目):
    - 第 1 パス (merge 裁定): V2 粗 edge のみを基準に gap <= MERGE_GAP_MAX
      を probe + adjudicate_gap で裁定し、merge 済み segment list を確定する。
      snap で edge が動いても次 gap の裁定入力が汚染されない (recall 退行根絶)。
      blackout-peek override (#895 P3 4周目): adjudicate_gap が "merge" を返しても
      adj_probes の後半 or peek probe に blackout run (>=2 probe) があれば
      boundary に override する (次試合の zone-in blackout = 物理境界の実在)。
    - 第 2 パス (snap): merge 確定後の各境界に snap を適用する。
      短 gap: probe_gap を再利用できる場合は第 1 パスで取得済みのものを使う。
      長 gap: 両端窓のみ probe (probe 2 回)。
      end 側窓: [prev_end - EDGE_EXT_END_S, prev_end + _LONG_GAP_EDGE_WINDOW_S]
      (旧 EDGE_EXT_S=45s から EDGE_EXT_END_S=120s に拡大。shinryu M3 型対応)。

    per-gap 例外隔離: probe/裁定に失敗した gap は V2 の粗い結果を維持する
    (V3 は改善のみ、失敗しても悪化させない)。

    端 segment snap (Fix 3 / #895 P3 2周目、4周目で end 窓 120s に拡大):
    - 最初の segment の start 側: [max(0, first_start - EDGE_EXT_S), first_start + 60]
      を probe し trailing-run 方式で start snap (中点制約あり)。
    - 最後の segment の end 側: [last_end - EDGE_EXT_END_S, last_end + EDGE_EXT_S]
      を probe し leading-run 方式で end snap (中点制約あり)。
    """
    if not segments:
        return []

    # --- 第 1 パス: merge 裁定 (粗 edge 基準、拡張なし probe) ---
    # Fix 1 (#895 P3 3周目): 裁定 probe は拡張なしで独立取得し全 probes を
    # adjudicate_gap に渡す (= P2 実装と bit-同一の入力)。snap 用の拡張あり
    # probe は第 2 パスで別途取得する。probe 格子の origin ズレによる裁定 flip を根絶。
    #
    # gap_probes_cache[i]: segment i と i+1 の間の拡張あり probes (短 gap のみ)
    merged: list[MatchBoundary] = [cast("MatchBoundary", dict(segments[0]))]
    gap_probes_cache: dict[
        int, list[GapProbe]
    ] = {}  # index = merged list の直前 segment idx

    for _seg_idx, nxt in enumerate(segments[1:]):
        orig_prev_end = merged[-1]["end"]
        orig_next_start = nxt["start"]
        gap = orig_next_start - orig_prev_end
        try:
            if gap <= MERGE_GAP_MAX:
                # 裁定 probe: 拡張なし (prev_end, next_start) -- P2 と bit-同一の入力
                adj_probes = probe_gap(
                    video_path, anchor, orig_prev_end, orig_next_start, workers=workers
                )
                if stats is not None:
                    stats["vtuber_gaps_tested"] = stats.get("vtuber_gaps_tested", 0) + 1
                if adjudicate_gap(adj_probes) == "merge":
                    # blackout-peek override: 後半 or peek に blackout run があれば boundary
                    # (shirurori 型: result 余韻 gap の末尾に次試合の zone-in blackout が実在)
                    mid_t = (orig_prev_end + orig_next_start) / 2.0
                    back_half = [p for p in adj_probes if p.t >= mid_t]
                    if _has_blackout_run(back_half):
                        # 後半 blackout -> boundary override
                        if stats is not None:
                            stats["vtuber_merge_overridden"] = (
                                stats.get("vtuber_merge_overridden", 0) + 1
                            )
                    else:
                        # peek: (orig_next_start, orig_next_start + EDGE_EXT_S) を追加取得
                        peek_probes = probe_gap(
                            video_path,
                            anchor,
                            orig_next_start,
                            orig_next_start + EDGE_EXT_S,
                            workers=workers,
                        )
                        if _has_blackout_run(peek_probes):
                            # peek blackout -> boundary override
                            if stats is not None:
                                stats["vtuber_merge_overridden"] = (
                                    stats.get("vtuber_merge_overridden", 0) + 1
                                )
                        else:
                            # merge 確定
                            if stats is not None:
                                stats["vtuber_gaps_merged"] = (
                                    stats.get("vtuber_gaps_merged", 0) + 1
                                )
                            merged[-1]["end"] = nxt["end"]
                            # merge した場合は probe cache を積まない (境界消滅)
                            continue
                # boundary (adjudicate_gap が boundary or override): snap 用拡張あり probe を cache
                t0_ext = max(0.0, orig_prev_end - EDGE_EXT_END_S)
                t1_ext = orig_next_start + EDGE_EXT_S
                snap_probes = probe_gap(
                    video_path, anchor, t0_ext, t1_ext, workers=workers
                )
                gap_probes_cache[len(merged) - 1] = snap_probes
            # 長 gap の場合は cache しない (第 2 パスで再 probe)
        except Exception:
            logger.warning(
                "vtuber timeline: gap adjudication failed at %.0f-%.0f; keeping "
                "coarse boundaries",
                orig_prev_end,
                orig_next_start,
                exc_info=True,
            )
        merged.append(cast("MatchBoundary", dict(nxt)))

    if len(merged) < 2:
        # 全 merge または 1 segment: 端 snap のみ適用して返す
        return _snap_outer_edges(video_path, anchor, merged, workers=workers)

    # --- 第 2 パス: snap (merge 確定後の各境界) ---
    result: list[MatchBoundary] = [cast("MatchBoundary", dict(merged[0]))]
    for i, nxt in enumerate(merged[1:]):
        prev = result[-1]
        prev_end_orig = prev["end"]
        next_start_orig = nxt["start"]
        gap = next_start_orig - prev_end_orig
        try:
            if gap <= MERGE_GAP_MAX:
                # 第 1 パスの cache を再利用 (i は merged の隣接 pair index)
                probes = gap_probes_cache.get(i)
                if probes is None:
                    # cache miss (稀: 第 1 パスで exception した gap)
                    t0_ext = max(0.0, prev_end_orig - EDGE_EXT_END_S)
                    t1_ext = next_start_orig + EDGE_EXT_S
                    probes = probe_gap(
                        video_path, anchor, t0_ext, t1_ext, workers=workers
                    )
                # Bug A 修正 (#895 P3 6周目): probes 窓は next_start_orig + EDGE_EXT_S まで
                # 取得済みのため ext_hi を渡して Priority 2 (外側 blackout 救済) を有効化する。
                new_end, new_start = snap_segment_edges(
                    prev_end_orig,
                    next_start_orig,
                    probes,
                    ext_hi=next_start_orig + EDGE_EXT_S,
                )
            else:
                # 長 gap: 両端窓のみ probe
                # end 側: EDGE_EXT_END_S (120s) 分巻き戻る (旧 EDGE_EXT_S=45s から拡大)
                head = probe_gap(
                    video_path,
                    anchor,
                    max(0.0, prev_end_orig - EDGE_EXT_END_S),
                    prev_end_orig + _LONG_GAP_EDGE_WINDOW_S,
                    workers=workers,
                )
                tail = probe_gap(
                    video_path,
                    anchor,
                    next_start_orig - _LONG_GAP_EDGE_WINDOW_S,
                    next_start_orig + EDGE_EXT_S,
                    workers=workers,
                )
                new_end, _ = snap_segment_edges(
                    prev_end_orig, prev_end_orig + _LONG_GAP_EDGE_WINDOW_S, head
                )
                _, new_start = snap_segment_edges(
                    next_start_orig - _LONG_GAP_EDGE_WINDOW_S, next_start_orig, tail
                )
        except Exception:
            logger.warning(
                "vtuber timeline: gap snap failed at %.0f-%.0f; keeping "
                "coarse boundaries",
                prev_end_orig,
                next_start_orig,
                exc_info=True,
            )
            result.append(cast("MatchBoundary", dict(nxt)))
            continue
        prev["end"] = new_end
        follower = cast("MatchBoundary", dict(nxt))
        follower["start"] = new_start
        result.append(follower)

    return _snap_outer_edges(video_path, anchor, result, workers=workers)


def _snap_outer_edges(
    video_path: Path,
    anchor,
    segments: list[MatchBoundary],
    *,
    workers: int | None = None,
) -> list[MatchBoundary]:
    """Fix 3 (#895 P3 2周目、4周目で end 窓 120s に拡大): 最初の start + 最後の end を snap。

    最初の segment start: [max(0, first_start - EDGE_EXT_S), first_start + 60] を
    probe し _snap_start で snap (blackout 優先、evidence fallback + 中点制約)。
    最後の segment end: [last_end - EDGE_EXT_END_S, last_end + EDGE_EXT_S] を probe し
    _snap_end で snap (evidence のみ + 中点制約)。
    shinryu M3 型: collapse が coarse end より ~80s 前にあるとき EDGE_EXT_END_S=120s で救済。
    失敗時は粗い edge 維持 (per-gap 例外隔離と同等)。
    """
    if not segments:
        return segments
    result = [cast("MatchBoundary", dict(s)) for s in segments]

    # --- 最初の segment start snap ---
    first = result[0]
    first_start = first["start"]
    t0 = max(0.0, first_start - EDGE_EXT_S)
    t1 = first_start + _LONG_GAP_EDGE_WINDOW_S
    try:
        probes = probe_gap(video_path, anchor, t0, t1, workers=workers)
        if probes:
            new_start = _snap_start(probes, t0, t1)
            if new_start is not None:
                first["start"] = new_start
    except Exception:
        logger.debug(
            "vtuber timeline: outer edge snap failed for first start %.0f",
            first_start,
            exc_info=True,
        )

    # --- 最後の segment end snap ---
    last = result[-1]
    last_end = last["end"]
    t0 = last_end - EDGE_EXT_END_S  # 120s 巻き戻り (旧 60s から拡大)
    t1 = last_end + EDGE_EXT_S
    try:
        probes = probe_gap(video_path, anchor, t0, t1, workers=workers)
        if probes:
            new_end = _snap_end(probes, t0, t1)
            if new_end is not None:
                last["end"] = new_end
    except Exception:
        logger.debug(
            "vtuber timeline: outer edge snap failed for last end %.0f",
            last_end,
            exc_info=True,
        )

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
