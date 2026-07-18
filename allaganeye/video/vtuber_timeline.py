# allaganeye/video/vtuber_timeline.py
"""VTuber presence x motion timeline detection (V0-V2, spec 2026-07-17).

`--vtuber` 専用の境界候補 generator。blackout 起点 (candidate-classify) では
境界 blackout が 1-3s しかなく系統的に under-detect するため (PoC report §2)、
「試合中である」証拠 (at-anchor presence AND band motion) の timeline から
試合区間を直接切り出す。OBS / masked path からは import されない。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from collections.abc import Sequence

if TYPE_CHECKING:
    from allaganeye.video.capture_region import ScorebarLocalization
    from allaganeye.video.detector import MatchBoundary

logger = logging.getLogger(__name__)

TIMELINE_STRIDE = 10.0
"""V1 scan stride (seconds). PoC: 6 source で試合構造を再現、4h VOD ≈ 3-6 分."""

TIMELINE_PAIR_DT = 0.5
"""Motion 測定用フレームペアの時間差 (seconds)."""

TIMELINE_MAD_MIN = 1.5
"""band MAD の evidence 閾値。PoC: 試合中最低 ≥2.2 vs 凍結画面 ≤0.83."""

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
hit 率 (~21% @conf>=0.5、PoC report §3) でも期待 ~10 hits を確保する."""

_VT_ANCHOR_MIN_CONF = 0.5
"""VTuber anchor の conf 事前フィルタ。masked の 0.7 は Onsal true hit
(median 0.589) を殺すため使わない (PoC report §3)。FP は dominant cluster
の y 投票で抑制する."""

_VT_ANCHOR_MIN_HITS = 5


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
