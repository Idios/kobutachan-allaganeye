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

    # quorum 平滑化: in_match_flags[i] は probe i が in-match かどうか
    in_match_flags = [False] * n
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        in_match_flags[i] = sum(evid[lo:hi]) >= quorum

    # in-match run を収集 (各 run = (start_idx, end_idx) inclusive)。
    # この形は revert 済みの V2 hard-gap break (e11f381) の下準備として導入されたが、
    # prev_in フラグ方式と挙動同値で run 単位の filter が読み取りやすいため残す
    # (review F24)。境界条件は TestSegmentTimelineRunCollection が pin する。
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

    return [
        {"start": probes[run_s].t, "end": probes[run_e].t, "type": "fl_match"}
        for run_s, run_e in in_match_runs
        if probes[run_e].t - probes[run_s].t >= min_match_duration
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

_PRE_V4_STATS_KEYS: tuple[str, ...] = (
    "vtuber_timeline_probes",
    "vtuber_anchor_confidence",
    "vtuber_gaps_tested",
    "vtuber_gaps_merged",
    "vtuber_merge_overridden",
)
"""V2 通過後 - V4 検証前に main stats へ書く key。

V4 全滅 -> None 縮退時にはここを丸ごと pop する (放棄した timeline の統計を
legacy 縮退 run の verbose に出さない)。新しい stat を足して pop を忘れる死角は
tests/test_vtuber_timeline.py の AST 完全性 test が gate する。"""

_POST_V4_STATS_KEYS: tuple[str, ...] = (
    "vtuber_v4_dropped",
    "vtuber_low_confidence_segments",
)
"""V4 空チェック通過後にのみ書く key (縮退 run では書かれないので pop 不要)。"""


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
    # DetectionStats は total=False なので空 dict で初期化できる。
    # 素の `dict` 注釈 + type: ignore にすると型の食い違いを恒久的に隠すため使わない。
    local_stats: DetectionStats = {}
    boundaries = detector._validate_match_segments(
        video_path,
        boundaries,
        anchor,
        workers,
        local_stats,
        duration_hint,
        on_all_drop="empty",
    )
    if not boundaries:
        # V4 が全 segment を drop した場合も None (defense-in-depth、空 authoritative 禁止)
        # on_all_drop="empty" が発火した場合もここに落ちる。
        # legacy 縮退 run の verbose に放棄した timeline 統計が出ないよう
        # V2 通過後に set した vtuber_* キーを main stats から pop する。
        if stats is not None:
            for _k in _PRE_V4_STATS_KEYS:
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
300s 超の gap は真の境界のみとみなす。

min_match_duration の default (300s) と数値が一致するだけの独立した定数で、
--min-match-duration を変えても追従しない (config は > 0 しか検査しないため
300 未満の値も設定できる)。"""

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
候補となる後続 run: evidence probe 数 >= END_FAR_RESCUE_MIN_EVIDENCE かつ
run 末尾 t < mid かつ run 末尾 t >= lo - END_FAR_RESCUE_S."""

END_FAR_RESCUE_MIN_EVIDENCE = 3
"""hybrid rescue の候補 run に必要な「実 evidence probe 数」。

index span (run[1] - run[0] + 1) ではなく実数で数える: _tolerant_runs(tol=10) は
最大 10 probe の False gap を跨いで run を結合するため、evidence 2 個でも
span 12 の run になりうる (span で数えると 2 個の孤立 hit を collapse と誤認する)。"""

BOUNDARY_BLACKOUT_MIN_PROBES = 1
"""boundary marker とみなす blackout run の最小 probe 数 (=1s @GAP_STRIDE)。

in-match guard を通過した blackout run はそれ自体が物理境界の証拠なので、
長さでは足切りしない (境界 blackout は 1-3s しかないことがある: PoC sec.2)。
snap (_snap_start) と裁定 (adjudicate_gap) の双方でこの値を使う。"""

INTRA_MATCH_FLICKER_MAX_PROBES = 4
"""in-match guard を適用する blackout run の最大長 (probe 数)。

この値以下の run のみ in-match guard (前後 evidence チェック) を適用する。
この値を超える run は guard をスキップして常に境界 marker として採用する。

根拠 (GT 実測):
- in-match 瞬断の実測最大: 2 probe (shinryu M5: t=5780-5781、t=8460-8461)
- 真の zone-in 境界の実測最小: 1 probe (shirurori [1490,1490])
- shirurori M3 問題の境界: 9 probe ([2714,2722])
  -> この zone-in の前後に evidence が両方あるため guard が誤発火し境界を棄却
  -> matched 6/7 -> 試合 2 本が 1 本に結合する regression (R1d 問題)

4 に設定する理由:
- 2 probe 以下 (瞬断) は guard 対象 (正しく除外)
- 5 probe 以上は guard スキップ (shirurori 9 probe を正しく境界として採用)
- 3-4 probe の短い真境界は guard 対象だが、真の境界では
  evidence_after=False (境界後は試合開始前 lobby) が多いため guard は不発になる

この値より長い blackout は evidence 近接に関わらず境界とみなす。"""

PEEK_BLACKOUT_MIN_PROBES = 2
"""in-match guard が構造的に効かない領域で boundary blackout run に要求する最小 probe 数。

BOUNDARY_BLACKOUT_MIN_PROBES より厳しいのは意図的: in-match guard は run の
前後「両方」に evidence があることで発火するため、probe 列の端 (guard の
before / after 窓が窓外にはみ出す領域) では「見えないから発火しない」だけで、
guard 通過を境界の証拠にできない。その分の noise margin として 2 probe (=2s)
を要求する。

適用箇所: peek 窓 (_has_peek_boundary_blackout) のみ。
窓が次 segment の「内部」から始まるため窓左端 run の before 窓が構造的に空で、
「境界の外」へ probe 窓を延長する経路が存在しない (peek 窓は次試合の内部が起点)。
よって probe を増やして決定可能にする手段がなく noise margin で代替する。

snap 窓 (_snap_start) の端切れは呼び出し側が probe 窓を延長して再判定する
(SNAP_WINDOW_EXTEND_MAX_S 参照)。edge_min_run 引数は R1c で撤廃済み。"""

SNAP_WINDOW_EXTEND_MAX_S = 15.0
"""snap 窓が guard 判定に不十分な場合に caller が行う 1 回の延長上限 (秒)。

INTRA_EVIDENCE_BEFORE_S(5s) + INTRA_EVIDENCE_AFTER_S(10s) を任意の run に
対してカバーできる余裕 + バッファ。動画先頭/末尾で物理的に延長不可の場合は
「損失方向に倒さない」既定 (= _boundary_blackout_runs が截断窓のまま評価し、
有片側 evidence だけでは guard が発火しないため run を採用) を使う。
1 回だけ延長を許可する (繰り返しは probe 増加を通常ケースまで拡大させる)。"""


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


def _boundary_blackout_runs(
    probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
    frozen_max: float = FROZEN_MAX,
    min_run: int = BOUNDARY_BLACKOUT_MIN_PROBES,
    max_flicker_probes: int = INTRA_MATCH_FLICKER_MAX_PROBES,
) -> list[tuple[int, int]]:
    """in-match guard を通過した blackout run (= 真の境界 marker) を返す (純関数)。

    物理規則の単一実装 (#895 P3 review F1/F14/F15、R1d で run 長 gate 追加):
    - blackout run = band_b <= blackout_b_max の「連続」 probe。UNKNOWN
      (band_b None) は blackout ではないので run を分断する。
      呼び出し側で valid (band_b not None) に filter してから渡すと
      UNKNOWN を挟んだ 2 run が 1 run に連結し、guard を run 全体の端点で
      評価してしまう (旧 adjudicate_gap の穴) ため、必ず生の probe 列を渡す。
    - in-match guard: run 長 <= max_flicker_probes の短い run のみに適用する。
      run 先頭 t から INTRA_EVIDENCE_BEFORE_S 以内前と
      run 末尾 t から INTRA_EVIDENCE_AFTER_S 以内後の「両方」に evidence probe が
      あれば試合中の瞬断 (intra-match flicker) とみなして除外する。
      run 長 > max_flicker_probes の長い run は guard をスキップして常に
      境界 marker として採用する (R1d: shirurori 9 probe zone-in 誤排除修正)。
    - min_run 未満の run は除外する (peek 窓のみ厳しめ: PEEK_BLACKOUT_MIN_PROBES)。

    guard スキップの根拠 (GT 実測):
    - in-match 瞬断の実測最大: 2 probe (shinryu M5 実測)
    - 真の zone-in の実測最小: 1 probe
    - INTRA_MATCH_FLICKER_MAX_PROBES=4 で 2 probe 瞬断は guard 対象、
      5+ probe は guard スキップ (shirurori 9 probe zone-in を正しく採用)

    probe 窓の端で guard 窓が切れている短い run は「窓外の evidence が見えないから
    guard が発火しない」だけで、run 長では真の zone-in と in-match 瞬断を区別できない。
    この pure 関数は窓端の截断を検出するが補正は行わない。呼び出し側が
    _snap_window_needs_extension で截断を検知し probe 窓を延長してから再呼び出しする
    (SNAP_WINDOW_EXTEND_MAX_S 上限、延長不可時は損失方向に倒さない既定を使う)。

    この関数を snap (_snap_start) / 裁定 (adjudicate_gap) / merge override が
    共有することで「blackout run のどれが境界か」の規則を一元化する。
    """
    probes_list = list(probes)
    flags = _evidence_flags(probes_list, frozen_max=frozen_max)
    out: list[tuple[int, int]] = []
    if not probes_list:
        return out
    for start, end in _blackout_runs(probes_list, blackout_b_max):
        t_start = probes_list[start].t
        t_end = probes_list[end].t
        run_len = end - start + 1
        if run_len < min_run:
            continue
        # run 長 > max_flicker_probes の長い run は guard をスキップして常に採用する。
        # 真の zone-in (例: shirurori 9 probe) は前後に evidence があっても境界。
        # in-match 瞬断は実測最大 2 probe であり、max_flicker_probes=4 なら安全マージンあり。
        if run_len > max_flicker_probes:
            out.append((start, end))
            continue
        has_evidence_before = any(
            flags[j]
            for j in range(0, start)
            if t_start - probes_list[j].t <= INTRA_EVIDENCE_BEFORE_S
        )
        has_evidence_after = any(
            flags[j]
            for j in range(end + 1, len(probes_list))
            if probes_list[j].t - t_end <= INTRA_EVIDENCE_AFTER_S
        )
        if has_evidence_before and has_evidence_after:
            continue  # intra-match flicker
        out.append((start, end))
    return out


def _snap_window_needs_extension(
    probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
) -> tuple[float, float]:
    """snap 窓の guard が probe 列端で截断されているか判定する (純関数)。

    blackout run のうち「guard 窓が probe 列の端で切れているもの」を探し、
    決定可能にするために必要な延長量 (秒) を (before_ext, after_ext) で返す。
    どちらも 0.0 なら截断なし (延長不要)。

    - before_ext > 0: 左端で before 窓が切れている run が存在する。
      probe 窓を before_ext 秒分、左に広げれば決定可能になる可能性がある。
    - after_ext > 0: 右端で after 窓が切れている run が存在する。
      probe 窓を after_ext 秒分、右に広げれば決定可能になる可能性がある。

    呼び出し側は延長後に probe_gap を再取得し _boundary_blackout_runs を再評価する。
    物理的に延長できない場合 (t=0 / 動画末尾) は _boundary_blackout_runs の
    截断窓評価結果がそのまま使われ「損失方向に倒さない」既定として機能する。
    """
    probes_list = list(probes)
    if not probes_list:
        return 0.0, 0.0
    t_window_lo = probes_list[0].t
    t_window_hi = probes_list[-1].t
    before_ext = 0.0
    after_ext = 0.0
    for start, end in _blackout_runs(probes_list, blackout_b_max):
        t_start = probes_list[start].t
        t_end = probes_list[end].t
        gap_before = t_start - t_window_lo
        if gap_before < INTRA_EVIDENCE_BEFORE_S:
            before_ext = max(before_ext, INTRA_EVIDENCE_BEFORE_S - gap_before)
        gap_after = t_window_hi - t_end
        if gap_after < INTRA_EVIDENCE_AFTER_S:
            after_ext = max(after_ext, INTRA_EVIDENCE_AFTER_S - gap_after)
    return before_ext, after_ext


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
    後続 evidence run のうち「実 evidence probe 数 >= END_FAR_RESCUE_MIN_EVIDENCE
    かつ run 末尾 t < mid かつ run 末尾 t >= lo - END_FAR_RESCUE_S」を満たす
    最後のものに候補を置換する。置換後も候補 t < mid の中点制約を適用。
    run 長を index span で数えないこと (F19): _tolerant_runs は tol 個までの
    False を跨いで結合するため、span では evidence 2 個の run が >= 3 に見える。

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
            # index span ではなく実 evidence probe 数で数える (F19)
            run_evidence = sum(1 for j in range(run[0], run[1] + 1) if flags[j])
            run_end_t = probes_list[run[1]].t
            if (
                run_evidence >= END_FAR_RESCUE_MIN_EVIDENCE
                and run_end_t < mid
                and run_end_t >= rescue_threshold
            ):
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
    frozen_max: float = FROZEN_MAX,
    tol: int = SNAP_FLICKER_TOL,
) -> float | None:
    """start snap: blackout run 優先 (evidence は fallback)。

    優先順:
    1. (lo, hi] 内に完全に収まる最後の blackout run の run end -> 無条件採用。
    2. (hi, ext_hi] 内の最初の blackout run の run end -> 採用 (ext_hi 指定時のみ)
       (V2 粗 start が真の zone-in より前のケース: 拡張窓の外側 blackout を救済)
    3. trailing evidence run (run end が probes 末尾 EDGE_PROBE_LIMIT 以内):
       run 先頭 t > (lo + hi) / 2 のときのみ採用 (中点制約: 大外れ根絶)
    4. None -> caller は粗い edge を維持する。

    Priority 1 / 2 の候補はどちらも _boundary_blackout_runs で in-match guard を
    通過した run に限る (F4): ext_hi 窓は「次試合の内部」を指すため、guard なしだと
    次試合の瞬断 blackout を new_start にして粗 start より後ろへ頭欠けさせる
    (製品 invariant「試合内容の損失ゼロ」に抵触する)。

    probe 窓端で guard 窓が切れている run は caller が _snap_window_needs_extension で
    検出し probe 窓を延長してから再呼び出しすることで決定可能にする (R1c 設計)。
    延長不可 (動画先頭等) の場合は截断窓のまま評価し「損失方向に倒さない」
    既定 (= guard が片側しか見えなければ run を採用) として機能する。

    GT 物理定義: start = 境界 blackout (zone-in 暗転) 明け。
    blackout run end を new_start とするのは「暗転が終わった直後が試合開始」の物理直訳。
    in-match 瞬断: blackout の前後に evidence (present AND moving) がある -> 境界ではない。
    """
    if not probes:
        return None
    probes_list = list(probes)
    flags = _evidence_flags(probes_list, frozen_max=frozen_max)
    b_runs = _boundary_blackout_runs(
        probes_list,
        blackout_b_max=blackout_b_max,
        frozen_max=frozen_max,
    )

    # Priority 1: (lo, hi] 内の最後の blackout run end
    last_in_range: tuple[int, int] | None = None
    for brun in b_runs:
        brun_t_end = probes_list[brun[1]].t
        if lo < brun_t_end <= hi:
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

    # `or` ではなく `is not None` (F12): t=0.0 は正当な候補であり
    # 「候補なし」ではない (0.0 or prev_end は粗 edge へ silent 縮退する)。
    end_cand = _snap_end(probes, prev_end, next_start)
    new_end = end_cand if end_cand is not None else prev_end
    start_cand = _snap_start(
        probes,
        prev_end,
        next_start,
        ext_hi=ext_hi,
        blackout_b_max=blackout_b_max,
    )
    new_start = start_cand if start_cand is not None else next_start

    if new_end >= new_start:
        return prev_end, next_start
    return new_end, new_start


_LONG_GAP_EDGE_WINDOW_S = 60.0
"""gap > MERGE_GAP_MAX のとき head (end 側) probe する窓幅 (秒)."""

LONG_GAP_START_BACK_S = 120.0
"""gap > MERGE_GAP_MAX のとき tail (start 側) で coarse start から後方へ probe する窓幅 (秒)。

旧値は _LONG_GAP_EDGE_WINDOW_S(60s) を共用していたが、shirurori M7 実測で
zone-in blackout (境界 blackout) が coarse start の 60s 超前にあり tail 窓に入らず
staging 18s 頭欠けが発生した (#895 P3 8周目 Idios 承認)。120s に拡大することで
境界 blackout を捕捉する。head 窓 (_LONG_GAP_EDGE_WINDOW_S=60s) は変更しない。"""


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


def _has_peek_boundary_blackout(
    probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
    frozen_max: float = FROZEN_MAX,
) -> bool:
    """peek 窓に「境界としての」blackout run があるか (in-match guard 適用済み)。

    旧 _has_blackout_run は guard なしの bare 判定だったため、次試合内部の
    瞬断 blackout でも merge を override していた (F1 と同 class)。

    frozen_max は _boundary_blackout_runs へ転送する (adjudicate_gap と同じ):
    default 一致で実行時は同値だが、caller が閾値を上書きしたときに
    「裁定は新閾値・peek override は旧 default」という乖離を作らない。
    """
    return bool(
        _boundary_blackout_runs(
            probes,
            blackout_b_max=blackout_b_max,
            frozen_max=frozen_max,
            min_run=PEEK_BLACKOUT_MIN_PROBES,
        )
    )


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
      blackout-peek override (#895 P3 4周目、review F1 で peek 単独へ縮小):
      adjudicate_gap が "merge" を返しても peek probe
      (next_start .. next_start + EDGE_EXT_S) に in-match guard を通過した
      blackout run (>= PEEK_BLACKOUT_MIN_PROBES) があれば boundary に override する
      (次試合の zone-in blackout = 物理境界の実在)。
      gap 内 (adj_probes) 後半を見る分岐は削除済み: guard なしの bare 判定
      だった旧実装は裁定側の in-match guard を打ち消していた (詳細は
      該当箇所のコメント)。
    - 第 2 パス (snap): merge 確定後の各境界に snap を適用する。
      snap 結果が segment を反転させる場合はループ末尾の交差 guard で棄却する。
      短 gap: probe_gap を再利用できる場合は第 1 パスで取得済みのものを使う。
      長 gap: 両端窓のみ probe (probe 2 回)。片側ずつ _snap_end / _snap_start を
      直接呼ぶ (snap_segment_edges の交差判定に「使わない側」を巻き込まない)。
      end 側 (head) 窓: [prev_end - EDGE_EXT_END_S, prev_end + _LONG_GAP_EDGE_WINDOW_S]
      (旧 EDGE_EXT_S=45s から EDGE_EXT_END_S=120s に拡大。shinryu M3 型対応)。
      start 側 (tail) 窓: [next_start - LONG_GAP_START_BACK_S, next_start + EDGE_EXT_S]
      (旧 _LONG_GAP_EDGE_WINDOW_S=60s から LONG_GAP_START_BACK_S=120s に拡大。
       shirurori M7 型: zone-in blackout が coarse start の 60s 超前にある場合対応)。

    per-gap 例外隔離: probe/裁定に失敗した gap は V2 の粗い結果を維持する
    (V3 は改善のみ、失敗しても悪化させない)。

    端 segment snap (Fix 3 / #895 P3 2周目、4周目で end 窓 120s に拡大):
    - 最初の segment の start 側: [max(0, first_start - EDGE_EXT_S), first_start + 60]
      を probe し trailing-run 方式で start snap (中点制約あり)。
    - 最後の segment の end 側: [max(0, last_end - EDGE_EXT_END_S), last_end + EDGE_EXT_S]
      を probe し leading-run 方式で end snap (中点制約あり)。
    詳細な lo/hi semantics と交差 guard は _snap_outer_edges の docstring を参照。
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
                    # blackout-peek override: peek 窓に境界 blackout run があれば boundary
                    # (shirurori 型: result 余韻 gap の直後に次試合の zone-in blackout が実在)
                    #
                    # gap 内 (adj_probes) の後半を見る旧分岐は削除した (F1):
                    # 旧実装は guard なしの bare 判定だったため、intra-match flicker が
                    # gap 後半にあるだけで必ず boundary に戻り、裁定側の in-match guard を
                    # 打ち消していた。
                    #
                    # 「同じ物理規則 (_boundary_blackout_runs) を後半に当てれば候補は
                    # 構造的に存在しない」が成り立つのは full list に当てた場合だけで、
                    # 削除の根拠にはしない: back-half slice に当てると slice 先頭から
                    # INTRA_EVIDENCE_BEFORE_S 以内に始まる run は before evidence を
                    # 切り落とされて guard を通過しうる (窓端で guard が効かない問題と
                    # 同 class)。分岐は削除済みなので現行の挙動には影響しない。
                    peek_probes = probe_gap(
                        video_path,
                        anchor,
                        orig_next_start,
                        orig_next_start + EDGE_EXT_S,
                        workers=workers,
                    )
                    if _has_peek_boundary_blackout(peek_probes):
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
            # 実挙動 (F23): 裁定に失敗した gap は merge されず boundary として
            # 第 2 パスへ進むため、この後 snap は適用される (粗い境界のまま
            # 据え置かれるわけではない)。
            logger.warning(
                "vtuber timeline: gap adjudication failed at %.0f-%.0f; "
                "treating gap as boundary (snap still applies)",
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
                t0_ext = max(0.0, prev_end_orig - EDGE_EXT_END_S)
                t1_ext = next_start_orig + EDGE_EXT_S
                probes = gap_probes_cache.get(i)
                if probes is None:
                    # cache miss (稀: 第 1 パスで exception した gap)
                    probes = probe_gap(
                        video_path, anchor, t0_ext, t1_ext, workers=workers
                    )
                # Bug A 修正 (#895 P3 6周目): probes 窓は next_start_orig + EDGE_EXT_S まで
                # 取得済みのため ext_hi を渡して Priority 2 (外側 blackout 救済) を有効化する。
                # R1c: guard 窓が probe 列端で切れている run があれば 1 回だけ窓を延長する。
                # 延長後に snap を再評価し guard が決定可能な状態で判定する。
                before_ext, after_ext = _snap_window_needs_extension(probes)
                if before_ext > 0.0 or after_ext > 0.0:
                    snap_t0 = probes[0].t if probes else t0_ext
                    snap_t1 = probes[-1].t + GAP_STRIDE if probes else t1_ext
                    new_snap_t0 = max(
                        0.0, snap_t0 - min(before_ext, SNAP_WINDOW_EXTEND_MAX_S)
                    )
                    new_snap_t1 = snap_t1 + min(after_ext, SNAP_WINDOW_EXTEND_MAX_S)
                    if new_snap_t0 < snap_t0 or new_snap_t1 > snap_t1:
                        try:
                            probes = probe_gap(
                                video_path,
                                anchor,
                                new_snap_t0,
                                new_snap_t1,
                                workers=workers,
                            )
                        except Exception:
                            logger.debug(
                                "vtuber timeline: snap window extension failed, using original probes",
                                exc_info=True,
                            )
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
                    next_start_orig - LONG_GAP_START_BACK_S,
                    next_start_orig + EDGE_EXT_S,
                    workers=workers,
                )
                # 片側ずつ _snap_end / _snap_start を直接呼ぶ (F20)。
                # snap_segment_edges 経由だと「使わない側」の候補も交差判定に
                # 参加するため、head 窓の無関係な blackout が end snap を、
                # tail 窓の無関係な evidence が start snap を silent に潰す。
                # gap > MERGE_GAP_MAX なので head 窓 (<= prev_end + 60) と
                # tail 窓 (>= next_start - 120) は重ならず、new_end < new_start は
                # 構造的に成立する (両者の交差判定は不要)。ただし new_end が
                # prev の start を、new_start が nxt の end を跨ぐ交差は別軸なので
                # ループ末尾の交差 guard で棄却する。
                head_end = _snap_end(
                    head, prev_end_orig, prev_end_orig + _LONG_GAP_EDGE_WINDOW_S
                )
                new_end = head_end if head_end is not None else prev_end_orig
                # ext_hi: tail probe は next_start + EDGE_EXT_S まで取得済み。
                # 粗 start を数秒はみ出す zone-in blackout run (実測 shirurori M7:
                # run 末尾 7713 > coarse 7710) を Priority 2 で救済する (Bug A 同 class)。
                # R1c: guard 窓が probe 列端で切れている run があれば 1 回だけ窓を延長する。
                before_ext_t, after_ext_t = _snap_window_needs_extension(tail)
                if before_ext_t > 0.0 or after_ext_t > 0.0:
                    tail_t0 = (
                        tail[0].t if tail else next_start_orig - LONG_GAP_START_BACK_S
                    )
                    tail_t1 = (
                        tail[-1].t + GAP_STRIDE
                        if tail
                        else next_start_orig + EDGE_EXT_S
                    )
                    new_tail_t0 = max(
                        0.0, tail_t0 - min(before_ext_t, SNAP_WINDOW_EXTEND_MAX_S)
                    )
                    new_tail_t1 = tail_t1 + min(after_ext_t, SNAP_WINDOW_EXTEND_MAX_S)
                    if new_tail_t0 < tail_t0 or new_tail_t1 > tail_t1:
                        try:
                            tail = probe_gap(
                                video_path,
                                anchor,
                                new_tail_t0,
                                new_tail_t1,
                                workers=workers,
                            )
                        except Exception:
                            logger.debug(
                                "vtuber timeline: tail snap window extension failed, using original tail",
                                exc_info=True,
                            )
                tail_start = _snap_start(
                    tail,
                    next_start_orig - LONG_GAP_START_BACK_S,
                    next_start_orig,
                    ext_hi=next_start_orig + EDGE_EXT_S,
                )
                new_start = tail_start if tail_start is not None else next_start_orig
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
        # 交差 guard (F3 と同 class、第 2 パス版):
        # snap 後の edge が segment を反転させないことを保証する。
        # 長 gap path は片側ずつ snap するため snap_segment_edges の交差判定を
        # 通らず、end 窓が prev_end - EDGE_EXT_END_S (120s) まで遡るので
        # prev の start を跨いだ end (= end < start の segment) を作れる。
        # --min-match-duration は config が > 0 しか検査しないため 120s 未満の
        # segment は合法に作れ、V4 _validate_match_segments は順序も長さも
        # 検査しないので、ここで棄却しないと反転 segment が metadata に載る。
        #
        # new_end < new_start (両者の交差) をここで再検査しないのは、
        # 短 gap は snap_segment_edges が交差時に粗 pair を返し、長 gap は
        # head 窓と tail 窓が重ならないため構造的に成立するから。後者は
        # _LONG_GAP_EDGE_WINDOW_S + LONG_GAP_START_BACK_S <= MERGE_GAP_MAX に
        # 依存するので、定数を動かしたときに落ちるよう test で pin してある。
        if new_end <= prev["start"]:
            new_end = prev_end_orig
        if new_start >= nxt["end"]:
            new_start = next_start_orig
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
    最後の segment end: [max(0, last_end - EDGE_EXT_END_S), last_end + EDGE_EXT_S] を
    probe し _snap_end で snap (evidence のみ + 中点制約)。
    shinryu M3 型: collapse が coarse end より ~80s 前にあるとき EDGE_EXT_END_S=120s で救済。
    失敗時は粗い edge 維持 (per-gap 例外隔離と同等)。

    lo/hi は probe 窓の両端ではなく「粗 edge semantics」で渡す (F2):
    _snap_end / _snap_start の中点制約は lo/hi を gap の両端とみなすため、
    窓の両端 (例: 最終 segment の [last_end-120, last_end+45]) を渡すと
    mid = last_end - 37.5 となり、真の collapse が粗 end 付近にある通常ケースで
    end snap が構造的に発火しなくなる (far collapse だけ通る dead 機能になる)。
    - first start: lo = 窓左端 (= 直前 segment の end 相当)、hi = 粗 start、
      ext_hi = 窓右端 (粗 start を数秒はみ出す zone-in blackout の救済)
    - last end: lo = 粗 end、hi = 窓右端 (= 次 segment の start 相当)

    交差 guard (F3): 単一 segment のとき start snap と end snap が同じ segment に
    かかるため end < start の不正 segment を作りうる。vtuber path は下流の
    filter を通らない (そのまま metadata に載る) ため、ここで棄却する。
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
            # guard 窓が probe 列端で切れている run があれば 1 回だけ窓を延長する (R1c)。
            # 延長後に _snap_start を再評価し、guard が決定可能な状態で判定する。
            # 延長不可 (t=0 等) または上限超過の場合は元の probes で評価し、
            # 「損失方向に倒さない」既定 (_boundary_blackout_runs の截断窓評価) を使う。
            before_ext, after_ext = _snap_window_needs_extension(probes)
            if before_ext > 0.0 or after_ext > 0.0:
                new_t0 = max(0.0, t0 - min(before_ext, SNAP_WINDOW_EXTEND_MAX_S))
                new_t1 = t1 + min(after_ext, SNAP_WINDOW_EXTEND_MAX_S)
                if new_t0 < t0 or new_t1 > t1:
                    try:
                        probes = probe_gap(
                            video_path, anchor, new_t0, new_t1, workers=workers
                        )
                    except Exception:
                        logger.debug(
                            "vtuber timeline: first-start snap window extension failed, using original probes",
                            exc_info=True,
                        )
            new_start = _snap_start(probes, t0, first_start, ext_hi=t1)
            if new_start is not None and new_start < first["end"]:
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
    # 短尺動画で負の -ss を ffmpeg に渡さない (F13、first start 側と同じ clamp)
    t0 = max(0.0, last_end - EDGE_EXT_END_S)  # 120s 巻き戻り (旧 60s から拡大)
    t1 = last_end + EDGE_EXT_S
    try:
        probes = probe_gap(video_path, anchor, t0, t1, workers=workers)
        if probes:
            new_end = _snap_end(probes, last_end, t1)
            if new_end is not None and new_end > last["start"]:
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
    1. in-match guard を通過した blackout run が 1 つでもあれば boundary
       (_boundary_blackout_runs = snap 側と共有する単一実装。Codex HIGH
       #895 P3 Pre-flight Step 5 + review F14/F15)。
       すべて intra-match flicker なら priority 1 は不成立として priority 2 へ進む。
       判定は valid ではなく「生の probe 列」に対して行う (F15): valid
       (band_b not None) に filter してから run を取ると、UNKNOWN probe を挟んだ
       2 つの blackout が 1 run に連結し、guard を連結 run の端点で評価して
       両方 intra-match に落としてしまう。
       変更根拠 (guard 導入時): 旧実装は bare any() で blackout probe を直接
       boundary marker にしていたため、試合中の瞬断 blackout を含む高率 gap が
       present rate 判定に到達できず boundary に固定されていた
       (V2 が試合中に分割した oversplit が残る)。
    2. 凍結 run (band_mad < frozen_max が frozen_run_min 連続) があれば boundary
       (リザルト/replay 静止画面 = 真の境界の証拠。presence の有無は問わない)
    3. valid probe の present rate >= merge_rate なら merge (試合中 FN run)、
       未満なら boundary (真の lobby)
    4. valid probe ゼロ (空 / 全 UNKNOWN) は boundary (証拠なしで merge しない)
    """
    valid = [p for p in probes if p.band_b is not None and p.band_mad is not None]
    if not valid:
        return "boundary"

    # Priority 1: blackout run + in-match guard (snap 側と物理規則を共有)
    if _boundary_blackout_runs(
        probes, blackout_b_max=blackout_b_max, frozen_max=frozen_max
    ):
        return "boundary"

    # Priority 2: 凍結 run (リザルト/replay 静止)
    run = 0
    for p in valid:
        if p.band_mad is not None and p.band_mad < frozen_max:
            run += 1
            if run >= frozen_run_min:
                return "boundary"
        else:
            run = 0

    # Priority 3: present rate
    present = sum(1 for p in valid if p.present)
    if present / len(valid) >= merge_rate:
        return "merge"
    return "boundary"
