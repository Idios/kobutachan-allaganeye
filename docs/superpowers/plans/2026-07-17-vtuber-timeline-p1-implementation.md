# VTuber timeline 分割検出 P1 (V0-V2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `--vtuber` 指定時の試合検出を presence×motion timeline segmentation (V0 anchor + V1 scan + V2 粗分割) に切り替え、anchor 失敗時は現行 band-crop path へ縮退する。

**Architecture:** 新モジュール `allaganeye/video/vtuber_timeline.py` に V0-V2 を実装し、`detector.py` の `--vtuber` 分岐先頭から呼ぶ。V2 は純関数 (合成データで TDD)。cache key に `vtuber_algo` を追加 (masked_algo と同型)。spec: `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md`、実測根拠: 同日 PoC report。

**Tech Stack:** Python 3.11+ (pyproject requires-python 準拠) / numpy / 既存 primitive (`consensus_scorebar_localization` / `localize_scorebar_at_anchor` / `_probe_frame_rgb_hires`) / pytest。

## Global Constraints

- OBS default (`vtuber=False`) と `--masked` はコード経路非接触 (bit-exact 構造保証)。`vtuber_timeline` の import は `if vtuber:` 分岐内の lazy import のみ
- パラメータは spec §2.1 の値をそのまま定数化: stride 10.0s / pair Δ0.5s / MAD_MIN 1.5 / WINDOW 9 / QUORUM 2。anchor は VTuber 専用値: 48 samples / conf 0.5 / min hits 5 (masked の 24/0.7/5 は Onsal で true hit を殺すため使わない、PoC report §3)
- fps filter 禁止 (すべて `-ss` 単発 probe、#575)
- コミットは task ごと。Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
- 各 task 完了時に `python -m ruff check . && python -m ruff format --check . && python -m pyright` を pass させる

---

### Task 1: `segment_timeline` 純関数 (V2 粗分割)

**Files:**

- Create: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py`

**Interfaces:**

- Produces: `TimelineProbe(t: float, present: bool, band_mad: float | None)` (frozen dataclass、`band_mad=None` = decode 失敗) / `segment_timeline(probes: Sequence[TimelineProbe], *, min_match_duration: float, mad_min: float = TIMELINE_MAD_MIN, window: int = TIMELINE_WINDOW, quorum: int = TIMELINE_QUORUM) -> list[MatchBoundary]` / 定数 `TIMELINE_STRIDE = 10.0`, `TIMELINE_PAIR_DT = 0.5`, `TIMELINE_MAD_MIN = 1.5`, `TIMELINE_WINDOW = 9`, `TIMELINE_QUORUM = 2`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vtuber_timeline.py
"""Unit tests for the VTuber presence x motion timeline (V0-V2, spec 2026-07-17)."""

from __future__ import annotations

from allaganeye.video.vtuber_timeline import (
    TIMELINE_MAD_MIN,
    TimelineProbe,
    segment_timeline,
)


def _probes(spec: str, stride: float = 10.0) -> list[TimelineProbe]:
    """Build probes from a compact string: M=match evidence, l=lobby(absent),
    f=frozen-present (present but band_mad < mad_min), u=unknown (decode fail)."""
    out: list[TimelineProbe] = []
    for i, ch in enumerate(spec):
        t = i * stride
        if ch == "M":
            out.append(TimelineProbe(t=t, present=True, band_mad=5.0))
        elif ch == "l":
            out.append(TimelineProbe(t=t, present=False, band_mad=8.0))
        elif ch == "f":
            out.append(TimelineProbe(t=t, present=True, band_mad=0.3))
        elif ch == "u":
            out.append(TimelineProbe(t=t, present=False, band_mad=None))
        else:  # pragma: no cover - guard for typos in test specs
            raise ValueError(ch)
    return out


class TestSegmentTimeline:
    def test_single_match_with_lobby_flanks(self):
        # 6 lobby / 40 match / 6 lobby probes (10s stride) -> one segment >= 300s
        probes = _probes("l" * 6 + "M" * 40 + "l" * 6)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1
        assert segs[0]["type"] == "fl_match"
        # segment must cover the match core (window smoothing may extend edges)
        assert segs[0]["start"] <= 70.0
        assert segs[0]["end"] >= 440.0

    def test_short_island_dropped_by_duration_prior(self):
        # 20 probes (200s) of evidence < min_match_duration -> no segment
        probes = _probes("l" * 10 + "M" * 20 + "l" * 10)
        assert segment_timeline(probes, min_match_duration=300.0) == []

    def test_fn_dropout_bridged_by_window_quorum(self):
        # in-match presence FN run of 3 probes (30s) inside a long match is
        # bridged by the rolling window (>=2 of 9 evidence)
        probes = _probes("M" * 20 + "lll" + "M" * 20)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1

    def test_long_absent_gap_splits_two_matches(self):
        # 200s absent gap (20 probes) -> two separate segments (PoC: true
        # boundaries show ~0% presence; window quorum cannot bridge 20 probes)
        probes = _probes("M" * 40 + "l" * 20 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2

    def test_frozen_present_is_not_evidence(self):
        # replay/staging screens: present but frozen (band_mad < mad_min)
        # must not extend or create segments (PoC report section 7.4)
        probes = _probes("M" * 40 + "f" * 20 + "l" * 10 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2
        # first segment must not absorb the frozen run's tail
        assert segs[0]["end"] <= 40 * 10.0 + 5 * 10.0

    def test_unknown_probes_are_not_evidence(self):
        probes = _probes("M" * 40 + "u" * 20 + "M" * 40)
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 2

    def test_empty_input(self):
        assert segment_timeline([], min_match_duration=300.0) == []

    def test_mad_threshold_boundary(self):
        # band_mad exactly at threshold counts as evidence (>=)
        probes = [
            TimelineProbe(t=i * 10.0, present=True, band_mad=TIMELINE_MAD_MIN)
            for i in range(40)
        ]
        segs = segment_timeline(probes, min_match_duration=300.0)
        assert len(segs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vtuber_timeline.py -v`
Expected: FAIL (ModuleNotFoundError: allaganeye.video.vtuber_timeline)

- [ ] **Step 3: Write the implementation**

```python
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
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
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
) -> "list[MatchBoundary]":
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vtuber_timeline.py -v`
Expected: 8 passed

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): vtuber_timeline V2 粗分割の純関数 segment_timeline (Refs #895)"
```

---

### Task 2: `resolve_vtuber_anchor` (V0)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py` (追記)

**Interfaces:**

- Consumes: `consensus_scorebar_localization(duration, localize_fn, num_samples, min_hits)` (capture_region.py:671) / `localize_from_rgb_bytes(raw, height, width)` / `_probe_frame_rgb_hires(video_path, t)` / `PresenceState.UNKNOWN` (probe_state.py)
- Produces: `resolve_vtuber_anchor(video_path: Path, duration_hint: float) -> ScorebarLocalization | None` / 定数 `_VT_ANCHOR_NUM_SAMPLES = 48`, `_VT_ANCHOR_MIN_CONF = 0.5`, `_VT_ANCHOR_MIN_HITS = 5`

実装は `detector._resolve_scorebar_anchor` (detector.py:478、masked #822) を鏡写しにして VTuber 定数へ差し替える。**masked の 24 samples / conf 0.7 をそのまま使ってはいけない**: Onsal の true hit は median conf 0.589 (PoC report §3) で 0.7 に届かず anchor が枯れる。48 samples / conf 0.5 なら きゅま (hit 率 20.8%) で期待 ~10 hits ≥ min 5。

- [ ] **Step 1: Write the failing tests** (consensus は注入 localize_fn で純粋にテストできるため、`resolve_vtuber_anchor` は `_probe_frame_rgb_hires` を monkeypatch してテストする)

```python
# tests/test_vtuber_timeline.py に追記
from pathlib import Path
from unittest.mock import patch

import numpy as np

from allaganeye.video.capture_region import ScorebarLocalization
from allaganeye.video.vtuber_timeline import (
    _VT_ANCHOR_MIN_CONF,
    resolve_vtuber_anchor,
)


class TestResolveVtuberAnchor:
    def _run(self, localize_results):
        """localize_from_rgb_bytes を順に localize_results を返す stub にして実行。"""
        raw = b"\x00" * (1920 * 1080 * 3)
        with (
            patch(
                "allaganeye.video.vtuber_timeline._probe_frame_rgb_hires",
                return_value=raw,
            ),
            patch(
                "allaganeye.video.capture_region.localize_from_rgb_bytes",
                side_effect=localize_results,
            ),
        ):
            return resolve_vtuber_anchor(Path("dummy.mp4"), duration_hint=3600.0)

    def test_onsal_grade_confidence_resolves(self):
        # conf 0.55-0.6 (masked の 0.7 filter では全滅する帯域) が通ること
        hit = ScorebarLocalization(532, 1147, 0, 45, 0.58)
        results = [hit] * 10 + [None] * 38
        anchor = self._run(results)
        assert anchor is not None
        assert anchor.y_top == 0

    def test_low_conf_hits_are_prefiltered(self):
        # conf < 0.5 のみ -> miss 扱いで anchor 不成立
        weak = ScorebarLocalization(532, 1147, 0, 45, _VT_ANCHOR_MIN_CONF - 0.1)
        anchor = self._run([weak] * 48)
        assert anchor is None

    def test_insufficient_hits(self):
        hit = ScorebarLocalization(532, 1147, 0, 45, 0.9)
        anchor = self._run([hit] * 4 + [None] * 44)  # < _VT_ANCHOR_MIN_HITS
        assert anchor is None

    def test_decode_failure_returns_none_gracefully(self):
        with patch(
            "allaganeye.video.vtuber_timeline._probe_frame_rgb_hires",
            return_value=None,
        ):
            assert (
                resolve_vtuber_anchor(Path("dummy.mp4"), duration_hint=3600.0) is None
            )
```

- [ ] **Step 2: Run to verify FAIL** — `python -m pytest tests/test_vtuber_timeline.py::TestResolveVtuberAnchor -v` → ImportError (resolve_vtuber_anchor)

- [ ] **Step 3: Implement**

```python
# vtuber_timeline.py に追記 (import 部)
from pathlib import Path

# module 冒頭の import に追加:
#   from allaganeye.video.detector import _probe_frame_rgb_hires  は循環になるため
#   関数内 lazy import とする (detector -> vtuber_timeline の向きが正)

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
) -> "ScorebarLocalization | None":
    """V0: per-video scorebar anchor を疎サンプル consensus で解決する。

    detector._resolve_scorebar_anchor (#822 masked) と同構造だが VTuber 定数
    (48 samples / conf 0.5 / min hits 5) を使う。None = 解決不能 (caller は
    現行 band-crop path へ縮退する)。例外は握り潰して None (縮退 floor)。
    """
    from allaganeye.video import capture_region
    from allaganeye.video.capture_region import consensus_scorebar_localization
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
        _probe_frame_rgb_hires,
    )
    from allaganeye.video.probe_state import PresenceState

    def _localize_at(t: float):
        raw = _probe_frame_rgb_hires(video_path, t)
        if raw is None:
            return PresenceState.UNKNOWN
        loc = capture_region.localize_from_rgb_bytes(
            raw,
            height=_SCOREBAR_V2_PROBE_HEIGHT,
            width=_SCOREBAR_V2_PROBE_WIDTH,
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
```

注: test は `allaganeye.video.capture_region.localize_from_rgb_bytes` を patch するため、実装は `capture_region.localize_from_rgb_bytes(...)` の **module 属性経由**で呼ぶこと (上のコードの通り)。`_probe_frame_rgb_hires` は vtuber_timeline の名前空間へ lazy import されるため patch 先は `allaganeye.video.vtuber_timeline._probe_frame_rgb_hires` — これを成立させるため、module 冒頭で `from allaganeye.video.detector import _probe_frame_rgb_hires` を **関数内でなく module レベルで行うと循環 import になる**。解決: module レベルでは import せず、関数内で `from allaganeye.video import detector` して `detector._probe_frame_rgb_hires` を呼ぶ形でもよいが、その場合 test の patch 先は `allaganeye.video.detector._probe_frame_rgb_hires` に変える。**実装者はどちらかに統一し、test と実装で patch 先を一致させること** (推奨: 関数内 `from allaganeye.video import detector` + patch 先 `allaganeye.video.detector._probe_frame_rgb_hires`)。

- [ ] **Step 4: Run to verify PASS** — `python -m pytest tests/test_vtuber_timeline.py -v` → 12 passed

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): resolve_vtuber_anchor V0 (VTuber 専用 consensus パラメータ) (Refs #895)"
```

---

### Task 3: `scan_timeline` (V1) + `detect_matches_timeline` (orchestration)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py` (追記)

**Interfaces:**

- Consumes: Task 1 の `TimelineProbe` / `segment_timeline`、Task 2 の `resolve_vtuber_anchor`、`localize_scorebar_at_anchor(frame, anchor)` (capture_region.py:465)、`band_region_from_localization(loc, probe_w, probe_h)` (capture_region.py:97)、`RegionTimeline` (capture_region.py:113)
- Produces: `scan_timeline(video_path, duration_hint, anchor, *, workers=None, progress_callback=None) -> list[TimelineProbe]` / `detect_matches_timeline(video_path, duration_hint, *, min_match_duration, workers=None, progress_callback=None) -> tuple[list[MatchBoundary], RegionTimeline] | None`
- `UNKNOWN_ABORT_RATIO = 0.5`: probe の 50% 超が decode 失敗なら timeline を信頼せず None (縮退)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vtuber_timeline.py に追記
from allaganeye.video.vtuber_timeline import (
    TIMELINE_PAIR_DT,
    detect_matches_timeline,
    scan_timeline,
)


def _synthetic_frame(brightness: int) -> bytes:
    return bytes([brightness]) * (1920 * 1080 * 3)


class TestScanTimeline:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_probe_pair_computes_band_mad(self):
        # frame1=100, frame2=110 -> band MAD = 10 (band 領域も全画素同値のため)
        frames = {0.0: _synthetic_frame(100), TIMELINE_PAIR_DT: _synthetic_frame(110)}

        def fake_probe(video_path, t):
            return frames.get(t)

        with (
            patch(
                "allaganeye.video.detector._probe_frame_rgb_hires",
                side_effect=fake_probe,
            ),
            patch(
                "allaganeye.video.capture_region.localize_scorebar_at_anchor",
                return_value=self.ANCHOR,
            ),
        ):
            probes = scan_timeline(
                Path("dummy.mp4"), duration_hint=10.0, anchor=self.ANCHOR
            )
        assert len(probes) == 1
        assert probes[0].present is True
        assert probes[0].band_mad is not None
        assert abs(probes[0].band_mad - 10.0) < 0.01

    def test_decode_failure_yields_unknown_probe(self):
        with patch(
            "allaganeye.video.detector._probe_frame_rgb_hires", return_value=None
        ):
            probes = scan_timeline(
                Path("dummy.mp4"), duration_hint=30.0, anchor=self.ANCHOR
            )
        assert all(p.band_mad is None and p.present is False for p in probes)


class TestDetectMatchesTimeline:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _fake_scan(self, spec: str):
        return _probes(spec)

    def test_anchor_miss_returns_none(self):
        with patch(
            "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
            return_value=None,
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=3600.0, min_match_duration=300.0
                )
                is None
            )

    def test_success_returns_boundaries_and_region(self):
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=self._fake_scan("l" * 6 + "M" * 40 + "l" * 6),
            ),
        ):
            result = detect_matches_timeline(
                Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
            )
        assert result is not None
        boundaries, region_timeline = result
        assert len(boundaries) == 1
        assert region_timeline.coarse.source == "band"
        assert region_timeline.fallback_reason is None

    def test_majority_unknown_aborts_to_none(self):
        # 50% 超 decode 失敗 -> timeline を信頼せず None (縮退 floor)
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=self._fake_scan("M" * 10 + "u" * 42),
            ),
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
                )
                is None
            )
```

- [ ] **Step 2: Run to verify FAIL** — ImportError (scan_timeline)

- [ ] **Step 3: Implement**

```python
# vtuber_timeline.py に追記
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

UNKNOWN_ABORT_RATIO = 0.5
"""decode 失敗 probe がこの比率を超えたら timeline を放棄して縮退する."""

_BAND_PAD_PX = 10
"""band MAD 測定域の上下パディング (probe px)。PoC 計測と同値."""


def _band_slice(anchor) -> tuple[int, int, int, int]:
    """anchor から MAD 測定用の band px 範囲 (y0, y1, x0, x1) を返す。"""
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    y0 = max(0, anchor.y_top - _BAND_PAD_PX)
    y1 = min(_SCOREBAR_V2_PROBE_HEIGHT, anchor.y_bottom + _BAND_PAD_PX + 1)
    x0 = max(0, anchor.x_left)
    x1 = min(_SCOREBAR_V2_PROBE_WIDTH, anchor.x_right + 1)
    return y0, y1, x0, x1


def _probe_pair(video_path: Path, t: float, anchor) -> TimelineProbe:
    from allaganeye.video import capture_region, detector

    raw1 = detector._probe_frame_rgb_hires(video_path, t)
    raw2 = detector._probe_frame_rgb_hires(video_path, t + TIMELINE_PAIR_DT)
    if raw1 is None or raw2 is None:
        return TimelineProbe(t=t, present=False, band_mad=None)
    h, w = detector._SCOREBAR_V2_PROBE_HEIGHT, detector._SCOREBAR_V2_PROBE_WIDTH
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
    from allaganeye.video.capture_region import (
        RegionTimeline,
        band_region_from_localization,
    )
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
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
    region = RegionTimeline(
        coarse=band_region_from_localization(
            anchor,
            probe_w=_SCOREBAR_V2_PROBE_WIDTH,
            probe_h=_SCOREBAR_V2_PROBE_HEIGHT,
        ),
        segments=[],
        fallback_reason=None,
    )
    return boundaries, region
```

- [ ] **Step 4: Run to verify PASS** — `python -m pytest tests/test_vtuber_timeline.py -v` → 17 passed

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): scan_timeline V1 + detect_matches_timeline orchestration (Refs #895)"
```

---

### Task 4: detector.py 配線 (`--vtuber` 分岐先頭で timeline を試行)

**Files:**

- Modify: `allaganeye/video/detector.py` (Stage 0 呼び出し部、detector.py:650 近辺 `detect_region, region_fallback_reason = ...` の直前)
- Test: `tests/test_detector.py` (追記。既存 `_detect_with_region_callback` (test_detector.py:2898) の monkeypatch パターンを踏襲)

**Interfaces:**

- Consumes: `vtuber_timeline.detect_matches_timeline` (Task 3)
- Produces: `detect_match_boundaries(vtuber=True)` は timeline 成功時にその boundaries を返し `region_callback` に band RegionTimeline を発火。timeline None 時は現行 band-crop path へ縮退 (既存コード無変更で続行)。`vtuber=False` は `vtuber_timeline` を import すらしない

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_detector.py に追記 (既存 import 群と _detect_with_region_callback の
# 近くに配置。既存 helper の kwargs/mock 構成をそのまま流用する)
def test_vtuber_timeline_path_used_when_available(monkeypatch):
    """vtuber=True で timeline が成功したらその boundaries を返す。"""
    from allaganeye.video import vtuber_timeline
    from allaganeye.video.capture_region import (
        FULL_FRAME,
        RegionTimeline,
        ScorebarLocalization,
        band_region_from_localization,
    )

    anchor = ScorebarLocalization(532, 1147, 0, 45, 0.8)
    expected = [{"start": 100.0, "end": 500.0, "type": "fl_match"}]
    region = RegionTimeline(
        coarse=band_region_from_localization(anchor, probe_w=1920, probe_h=1080)
    )
    monkeypatch.setattr(
        vtuber_timeline,
        "detect_matches_timeline",
        lambda *a, **k: (expected, region),
    )
    fired: list = []
    result = detect_match_boundaries(
        Path("dummy.mp4"),
        duration_hint=600.0,
        vtuber=True,
        region_callback=fired.append,
    )
    assert result == expected
    assert fired and fired[0].coarse.source == "band"


def test_vtuber_timeline_none_falls_back_to_band_crop(monkeypatch):
    """timeline None -> 既存 band-crop path が実行される (縮退 floor)。"""
    from allaganeye.video import vtuber_timeline

    monkeypatch.setattr(
        vtuber_timeline, "detect_matches_timeline", lambda *a, **k: None
    )
    # 既存 vtuber wiring test (test_detector.py:2865 近辺) と同じ mock 構成で
    # _resolve_detect_region 以降が呼ばれることを確認する。最小構成:
    called: list = []
    monkeypatch.setattr(
        "allaganeye.video.detector._resolve_detect_region",
        lambda *a, **k: called.append(1) or (FULL_FRAME, "consensus_miss"),
    )
    # Pass 1 以降は既存 helper のダミー probe mock を流用 (blackout なしで即返る)
    ...  # 既存 _detect_with_region_callback の内部 mock をこの test に展開する
    assert called  # _resolve_detect_region に到達した


def test_obs_path_does_not_call_timeline(monkeypatch):
    """vtuber=False では vtuber_timeline を一切呼ばない (構造保証の pin)。"""
    import allaganeye.video.vtuber_timeline as vt

    def _boom(*a, **k):  # pragma: no cover - 呼ばれたら失敗
        raise AssertionError("vtuber_timeline must not be called on OBS path")

    monkeypatch.setattr(vt, "detect_matches_timeline", _boom)
    # 既存の OBS wiring test (_detect_with_region_callback(monkeypatch, vtuber=False))
    # と同一の mock 構成で 1 回 detect を通し、例外が出ないことを確認する
    fired = _detect_with_region_callback(monkeypatch, vtuber=False)
    assert fired is not None
```

> 実装者への注意: `test_vtuber_timeline_none_falls_back_to_band_crop` の `...` 部分は
> 既存 `_detect_with_region_callback` (test_detector.py:2898) の mock 構成を読んで
> 同じダミー probe 群を並べること。この helper が `vtuber=` と `resolve_result=` を
> 受ける設計なので、可能なら helper に `timeline_result=` 引数を足して 3 test とも
> helper 経由に統一してよい (テストの重複コードを増やさない)。

- [ ] **Step 2: Run to verify FAIL** — `python -m pytest tests/test_detector.py -k vtuber_timeline -v` → FAIL (wiring 未実装なので timeline mock が使われない)

- [ ] **Step 3: Implement** — detector.py の Stage 0 呼び出し (detector.py:650 近辺) を次の形に変更:

```python
# V0-V2 (#895 / spec 2026-07-17): vtuber は timeline segmentation を先に試行。
# anchor 不成立 / probe 過半 UNKNOWN のときのみ従来の band-crop blackout path
# へ縮退する (現状より悪化しない floor)。OBS (vtuber=False) はこの分岐に
# 一切入らない = import もしない (bit-exact 構造保証)。
if vtuber:
    from allaganeye.video import vtuber_timeline

    timeline_result = vtuber_timeline.detect_matches_timeline(
        video_path,
        duration_hint,
        min_match_duration=min_match_duration,
        workers=workers,
        progress_callback=progress_callback,
    )
    if timeline_result is not None:
        timeline_boundaries, timeline_region = timeline_result
        if region_callback is not None:
            region_callback(timeline_region)
        # P1 契約: timeline path は Pass 1/2 を通らないため DetectionStats
        # (pass1/pass2 秒数等) と brightness_callback は未設定のまま返す。
        # `--vtuber -v` の pipeline 統計は空表示になるが `_print_detection_stats`
        # は全 key guarded で crash しない (実証済)。stats への timeline 固有
        # 統計 (probe 数 / anchor conf 等) の追加は P2 で V3 と合わせて設計する。
        return timeline_boundaries

# Stage 0 (#753 / B4-rev): resolve a scorebar-band anchor before any scan.
# (以下、既存コード無変更)
detect_region, region_fallback_reason = (
    _resolve_detect_region(video_path, duration_hint) if vtuber else (FULL_FRAME, None)
)
```

- [ ] **Step 4: Run to verify PASS** — `python -m pytest tests/test_detector.py -v` → 既存 + 新規 全 pass (OBS 系 test が 1 件も壊れないことを必ず確認)

- [ ] **Step 5: フルスイート + commit**

```bash
python -m pytest -q   # 並行/検出系変更のためフルスイート必須
python -m ruff check . && python -m ruff format --check . && python -m pyright
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): detector に vtuber timeline path を配線 (縮退 floor 付き) (Refs #895)"
```

---

### Task 5: cache key `vtuber_algo` (masked_algo と同型)

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (3 箇所: 定数 + params 書き込み split_matches.py:2022 近辺 + 比較 split_matches.py:2251 近辺 + verbose split_matches.py:697 近辺)
- Test: `tests/test_split_matches.py` (既存 masked_algo test 群を grep して同型を追記)

**Interfaces:**

- Produces: `_VTUBER_ALGO_VERSION = 2` (1 = legacy band-crop、key 欠落 legacy cache は 1 扱い)。vtuber 影響 run (params.vtuber or config.vtuber) のみ比較・invalidate。OBS cache は key 欠落でも hit し続ける (無関係ユーザーの再検知なし)

- [ ] **Step 1: Write the failing tests** — `grep -n "masked_algo" tests/test_split_matches.py` で既存 test 群 (mode-switch / legacy compat / 破損値) を特定し、vtuber_algo 版を同型で書く:

```python
def test_cache_miss_when_vtuber_algo_changes(tmp_path, ...):
    # vtuber=True cache (vtuber_algo なし = legacy 1) を新バージョン (2) の
    # vtuber run が読む -> miss (timeline 導入前の結果を再利用しない)
    ...


def test_obs_cache_hits_without_vtuber_algo_key(tmp_path, ...):
    # vtuber=False の legacy cache は key 欠落でも hit (無関係ユーザー保護)
    ...
```

(具体的な fixture 構成は既存 masked_algo test をコピーして flag 名を差し替える。cache 書き込み → 読み出しの往復で assert する既存パターンを踏襲)

- [ ] **Step 2: FAIL 確認** → **Step 3: Implement**

```python
# split_matches.py: _MASKED_ALGO_VERSION (75 行近辺) の直後に追加
_VTUBER_ALGO_VERSION = 2
"""vtuber-path detection algorithm version (cache key).

1 = legacy band-crop blackout path (キー欠落の legacy cache を含む) /
2 = timeline segmentation (V0-V2, #895)。vtuber 影響 run のみ比較する
(masked_algo と同じ invalidation 方針)。
"""

# params 書き込み (2022 近辺、"masked_algo" の次の行):
            "vtuber_algo": _VTUBER_ALGO_VERSION,

# 比較 (2267 近辺、masked_algo ブロックの直後に同型で):
    _raw_cached_vtuber_algo = params.get("vtuber_algo", 1)
    try:
        cached_vtuber_algo = int(_raw_cached_vtuber_algo)
    except (ValueError, TypeError):
        cached_vtuber_algo = -1
    vtuber_affected = params.get("vtuber", False) or config.vtuber
    if vtuber_affected and cached_vtuber_algo != _VTUBER_ALGO_VERSION:
        logger.debug("Cache vtuber algo mismatch")
        return None

# verbose (712 近辺、masked の algo_token と同型で vtuber run のとき表示):
    vtuber_algo_token = (
        f", vtuber_algo={int(params.get('vtuber_algo', 1))}" if cached_vtuber else ""
    )
```

(verbose の int() 破損値フォールバックは masked_algo 側の try/except パターン (split_matches.py:701) をそのまま踏襲する)

- [ ] **Step 4: PASS 確認** — `python -m pytest tests/test_split_matches.py -q`
- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check . && python -m ruff format --check . && python -m pyright
git add allaganeye/commands/split_matches.py tests/test_split_matches.py
git commit -m "feat(l3): cache key に vtuber_algo を追加 (timeline 導入の silent 再利用防止) (Refs #895)"
```

---

### Task 6: P1 gate 検証 (実機) + PR

**Files:** なし (検証と PR のみ)

- [ ] **Step 1: フルスイート + 全 lint**

```bash
python -m pytest -q                     # 期待: 全 pass
python -m ruff check . && python -m ruff format --check .
python -m pyright
bash scripts/check-markdownlint.sh
```

- [ ] **Step 2: OBS bit-exact gate (実機、slow)** — worktree では `ALLAGANEYE_INTEGRITY_SKIP=1`、cache 汚染防止に `--no-cache`:

```bash
python -m pytest tests/test_v030_baseline_regression.py -m slow -q
```

Expected: `test_class_a_bit_exact` 系 PASS (flag なし = 現行完全一致)

- [ ] **Step 3: VTuber 粗分割の PoC 模擬一致 (実機)** — gyawa + きゅま で `--vtuber` detect を実行し、boundaries が PoC 模擬 (PoC report §4: gyawa 6 segment / きゅま 15 segment ±1 probe) と一致することを確認:

```bash
ALLAGANEYE_INTEGRITY_SKIP=1 python -m allaganeye detect "E:\videos\gyawa_vatos\2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4" --vtuber --no-cache -o E:\allaganeye-samples\_p1_gate_gyawa
ALLAGANEYE_INTEGRITY_SKIP=1 python -m allaganeye detect "E:\allaganeye-samples\FF14 FL NEWきゅま(邪竜眼) ニーズヘッグ化するオンサル！ フィジカル向上委員会【 オンサルハカイル フロントライン 】 [v2782813946].mp4" --vtuber --no-cache -o E:\allaganeye-samples\_p1_gate_kyuma
```

Expected: gyawa = 6 matches (GT 漏れ分含む) / きゅま = 15 前後 (V3 前なので偽分割 4 箇所は残ってよい。PoC report §4 の rule B 表と突合)。10 分超になる場合は detached 実行 (`feedback_long_gpu_job_detached_execution`)。

- [ ] **Step 4: PR 作成** — Pre-flight Step 0-4 (l2-workflow) を実施し、develop-0.3.0 ベースで PR。本文に Self-Test Report (machine-verified: 上記 Step 1-2 / machine-unverifiable: Step 3 の実測値)。**ロジック変更 PR のため AskUserQuestion で Idios に実機確認を依頼する** (Iron Law 6)。

---

## Self-Review 記録

- spec §2 V0-V2 / §2.3 実装配置 / cache key: Task 1-5 が被覆。V3/V4 は P2 (plan 対象外)、性能退行実測と 6 source GT は P3 gate (spec §3.2) — P1 では OBS bit-exact + 粗分割一致のみ (spec §5 の P1 gate 定義どおり)
- 型整合: `TimelineProbe` / `segment_timeline` / `resolve_vtuber_anchor` / `scan_timeline` / `detect_matches_timeline` の署名は Task 間で一致 (Task 3 が Task 1/2 を consume)
- 既知の implementer 裁量点 (明示済み): Task 2 の patch 先統一 / Task 4 の既存 helper 流用 / Task 5 の既存 masked_algo test 踏襲
