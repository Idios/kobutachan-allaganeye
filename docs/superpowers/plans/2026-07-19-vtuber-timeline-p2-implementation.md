# VTuber timeline 分割検出 P2 (V3+V4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** timeline 粗分割 (V2) の偽分割を V3 (merge 裁定 + 境界 snap) で解消し、V4 (segment 検証 + 低信頼フラグ) と timeline 固有統計を配線する — gate: きゅま 15→11 / gyawa 6/6 維持 / OBS bit-exact。

**Architecture:** `vtuber_timeline.py` に V3 純関数 (`adjudicate_gap` / `snap_segment_edges`) + I/O (`probe_gap`) + orchestration (`refine_segments`) を追加し、`detect_matches_timeline` を V0→V1→V2→V3→V4 に拡張。V4 は masked L2 の既存 `_validate_match_segments` (detector.py:928) を流用。統計は `DetectionStats` の新 key + `_print_detection_stats` の guarded section。

**Tech Stack:** Python 3.11+ / numpy / 既存 primitive (`localize_scorebar_at_anchor` / `_probe_frame_rgb_hires` / `_validate_match_segments`) / pytest。

## Global Constraints

- OBS default (`vtuber=False`) と `--masked` はコード経路非接触。新コードは `--vtuber` gate 内 + `vtuber_timeline.py` のみ。`_print_detection_stats` / `DetectionStats` への追加は key-guarded (OBS run はその key を set しない)
- spec §2.1 パラメータ: MERGE_RATE 10% / FROZEN_MAX 1.0 / merge 対象 gap 上限 300s (= min_match_duration)。V3 gap probe は 1s stride、blackout エッジ精密化は 0.25s

> **note (P2 final review)**: 実装では 0.25s 局所再 probe を不採用とし 1s 系列 snap に簡素化 (spec V3 (b) erratum 参照。SNAP_STRIDE は撤去済み)

- positive marker 優先: gap 内に band blackout または凍結 run があれば anchor rate に関わらず「boundary」(merge 禁止)。spec §2 V3 (a)
- 縮退 floor 不変: V3/V4 が例外を出しても timeline 全体を壊さない (V3 失敗 → V2 粗分割のまま採用 + warning / V4 は既存 fail-safe)
- fps filter 禁止 (すべて `-ss` 単発 probe)
- production 文字列に cp932 非安全記号 (U+2192/2014/2248/2265/00B1/2081/2082/2713) を入れない (tests/test_ascii_guard.py。日本語は OK)
- コミットは task ごと + Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
- 各 task 完了時に `python -m ruff check . && python -m ruff format --check . && python -m pyright` を pass (format 差分は `ruff format <files>` 適用可)。pipeline の exit code masking に注意 (`| tail` を挟むと失敗を見逃す — 各コマンドを個別実行)

---

### Task 1: `GapProbe` + `adjudicate_gap` 純関数 (V3-a 裁定)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py` (追記)

**Interfaces:**

- Produces: `GapProbe(t: float, present: bool, band_mad: float | None, band_b: float | None)` (frozen dataclass、`band_b`/`band_mad` None = decode 失敗) / `adjudicate_gap(probes: Sequence[GapProbe], *, merge_rate: float = MERGE_RATE, frozen_max: float = FROZEN_MAX, frozen_run_min: int = FROZEN_RUN_MIN_PROBES, blackout_b_max: float = BLACKOUT_B_MAX) -> str` (returns `"merge"` | `"boundary"`) / 定数 `MERGE_GAP_MAX = 300.0`, `MERGE_RATE = 0.10`, `FROZEN_MAX = 1.0`, `FROZEN_RUN_MIN_PROBES = 10`, `BLACKOUT_B_MAX = 30.0`, `GAP_STRIDE = 1.0`, `SNAP_STRIDE = 0.25`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vtuber_timeline.py に追記
from allaganeye.video.vtuber_timeline import (
    BLACKOUT_B_MAX,
    FROZEN_MAX,
    GapProbe,
    adjudicate_gap,
)


def _gap_probes(spec: str, stride: float = 1.0) -> list[GapProbe]:
    """M=present+moving (in-match FN run), l=absent+moving (lobby),
    f=present+frozen (replay/result 静止), b=blackout (band_b ~0),
    u=unknown (decode 失敗)."""
    out: list[GapProbe] = []
    for i, ch in enumerate(spec):
        t = i * stride
        if ch == "M":
            out.append(GapProbe(t=t, present=True, band_mad=8.0, band_b=95.0))
        elif ch == "l":
            out.append(GapProbe(t=t, present=False, band_mad=6.0, band_b=110.0))
        elif ch == "f":
            out.append(GapProbe(t=t, present=True, band_mad=0.4, band_b=120.0))
        elif ch == "b":
            out.append(GapProbe(t=t, present=False, band_mad=2.0, band_b=5.0))
        elif ch == "u":
            out.append(GapProbe(t=t, present=False, band_mad=None, band_b=None))
        else:  # pragma: no cover
            raise ValueError(ch)
    return out


class TestAdjudicateGap:
    def test_fn_run_merges(self):
        # きゅま 2660-2910 型: 散発 present ~24% + 常時 moving -> merge
        probes = _gap_probes(("M" + "lll") * 60)  # 25% present, 240 probes
        assert adjudicate_gap(probes) == "merge"

    def test_true_lobby_is_boundary(self):
        # 真の lobby: present ~1.5% -> boundary
        probes = _gap_probes("l" * 100 + "M" + "l" * 99)  # 0.5%
        assert adjudicate_gap(probes) == "boundary"

    def test_blackout_marker_forces_boundary(self):
        # rate が高くても blackout marker があれば boundary (positive marker 優先)
        probes = _gap_probes("M" * 30 + "bbb" + "M" * 30)
        assert adjudicate_gap(probes) == "boundary"

    def test_frozen_run_forces_boundary(self):
        # 振り返り/リザルト型: present だが凍結 run (>= FROZEN_RUN_MIN_PROBES)
        # -> rate 33% でも boundary (きゅま 5710-5980 の replay 防御)
        probes = _gap_probes("f" * 15 + "l" * 30)
        assert adjudicate_gap(probes) == "boundary"

    def test_short_frozen_blip_does_not_force_boundary(self):
        # 凍結 run が FROZEN_RUN_MIN_PROBES 未満なら marker 不成立 -> rate 判定
        probes = _gap_probes(("M" + "lll") * 20 + "fff" + ("M" + "lll") * 20)
        assert adjudicate_gap(probes) == "merge"

    def test_empty_or_all_unknown_is_boundary(self):
        # 証拠なしで merge しない (保守側)
        assert adjudicate_gap([]) == "boundary"
        assert adjudicate_gap(_gap_probes("u" * 20)) == "boundary"

    def test_rate_threshold_boundary_case(self):
        # rate == merge_rate (10%) は merge (>= 判定)
        probes = _gap_probes(("M" + "l" * 9) * 20)  # exactly 10%
        assert adjudicate_gap(probes) == "merge"
```

- [ ] **Step 2: Run to verify FAIL** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py::TestAdjudicateGap -v` → ImportError (GapProbe)

- [ ] **Step 3: Implement** — `vtuber_timeline.py` に追記:

```python
MERGE_GAP_MAX = 300.0
"""V3 merge 裁定の対象 gap 上限 (秒)。実測 FN run 最大 ~250s (PoC §5)。
300s 超の gap は真の境界のみ (min_match_duration と同値)."""

MERGE_RATE = 0.10
"""merge 裁定の anchor presence rate 閾値。FN run ~24% vs 真 lobby ~1.5%
(1s stride、PoC §5) の 15 倍分離の中間."""

FROZEN_MAX = 1.0
"""凍結 probe の band MAD 上限。リザルト/replay 静止 0.13-0.83 (PoC §3)."""

FROZEN_RUN_MIN_PROBES = 10
"""凍結 marker とみなす最小連続 probe 数 (=10s @1s)。リザルト/replay の
静止表示は 30s+ 持続 (PoC §7.4)、試合中の瞬間静止と区別する."""

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

    判定順序 (spec §2 V3 (a)、positive marker 優先):
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
```

- [ ] **Step 4: Run to verify PASS** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py -v` → 25 passed (既存 18 + 新 7)

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check .
python -m ruff format --check .
python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): V3-a adjudicate_gap 純関数 (merge 裁定 + positive marker) (Refs #895)"
```

---

### Task 2: `snap_segment_edges` 純関数 (V3-b 境界 snap)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py` (追記)

**Interfaces:**

- Consumes: Task 1 の `GapProbe` / `BLACKOUT_B_MAX`
- Produces: `snap_segment_edges(prev_end: float, next_start: float, gap_probes: Sequence[GapProbe], *, blackout_b_max: float = BLACKOUT_B_MAX) -> tuple[float, float]` — 確定境界の両端を dense 系列から精密化した `(new_prev_end, new_next_start)`。spec §2 V3 (b) の「refine_boundary 二分探索」は **dense 系列のエッジ検出に置換** (presence は per-frame noisy で二分探索の単調性前提が成立しないため。spec erratum は Task 5 で記録)

- [ ] **Step 1: Write the failing tests**

```python
class TestSnapSegmentEdges:
    def test_blackout_snap_both_edges(self):
        # gap 内に blackout run 2 個 (きゅま M1/M2 型): prev_end は最初の
        # blackout run の先頭、next_start は最後の blackout run の末尾へ snap
        probes = _gap_probes("M" * 5 + "bb" + "l" * 20 + "bbb" + "M" * 5)
        new_end, new_start = snap_segment_edges(0.0, 35.0, probes)
        assert new_end == probes[5].t  # 最初の blackout run 先頭
        assert new_start == probes[29].t  # 最後の blackout run 末尾
        assert new_end < new_start

    def test_presence_edge_snap_without_blackout(self):
        # blackout なし: prev_end = 先頭 present run の末尾、
        # next_start = 末尾 present run の先頭
        probes = _gap_probes("M" * 8 + "l" * 30 + "M" * 6)
        new_end, new_start = snap_segment_edges(0.0, 44.0, probes)
        assert new_end == probes[7].t
        assert new_start == probes[38].t

    def test_no_evidence_keeps_coarse_edges(self):
        # 全 absent / 全 UNKNOWN: 粗い edge を維持 (悪化させない)
        probes = _gap_probes("l" * 20)
        assert snap_segment_edges(5.0, 25.0, probes) == (5.0, 25.0)
        assert snap_segment_edges(5.0, 25.0, []) == (5.0, 25.0)

    def test_crossed_edges_fall_back_to_coarse(self):
        # snap 結果が交差 (new_end >= new_start) したら粗い edge へ縮退
        probes = _gap_probes("bb")  # 単一 blackout run のみ
        new_end, new_start = snap_segment_edges(0.0, 2.0, probes)
        assert new_end < new_start
```

- [ ] **Step 2: Run to verify FAIL** — ImportError (snap_segment_edges)

- [ ] **Step 3: Implement**

```python
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


def snap_segment_edges(
    prev_end: float,
    next_start: float,
    gap_probes: Sequence[GapProbe],
    *,
    blackout_b_max: float = BLACKOUT_B_MAX,
) -> tuple[float, float]:
    """V3-b: 確定境界の両端を gap dense 系列から精密化する (純関数)。

    優先順: blackout run (OBS と同じ意味論 = 境界は blackout に snap) >
    presence run エッジ (先頭 present run の末尾 / 末尾 present run の先頭) >
    粗い edge 維持。snap 結果が交差する場合は粗い edge に縮退する
    (snap は改善のみ、悪化させない)。
    """
    probes = list(gap_probes)
    new_end, new_start = prev_end, next_start
    runs = _blackout_runs(probes, blackout_b_max)
    if runs:
        new_end = probes[runs[0][0]].t
        new_start = probes[runs[-1][1]].t
    else:
        present_idx = [i for i, p in enumerate(probes) if p.present]
        if present_idx:
            # 先頭 present run の末尾
            i = 0
            while i in present_idx or (i == 0 and probes and probes[0].present):
                if not probes[i].present:
                    break
                i += 1
                if i >= len(probes):
                    break
            if probes and probes[0].present:
                new_end = probes[i - 1].t
            # 末尾 present run の先頭
            j = len(probes) - 1
            if probes[j].present:
                while j > 0 and probes[j - 1].present:
                    j -= 1
                new_start = probes[j].t
    if new_end >= new_start:
        return prev_end, next_start
    return new_end, new_start
```

- [ ] **Step 4: Run to verify PASS** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py -v` → 29 passed

- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check .
python -m ruff format --check .
python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): V3-b snap_segment_edges 純関数 (blackout/presence エッジ snap) (Refs #895)"
```

---

### Task 3: `probe_gap` (I/O) + `refine_segments` (V3 orchestration)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py`
- Test: `tests/test_vtuber_timeline.py` (追記)

**Interfaces:**

- Consumes: Task 1/2 の純関数、P1 の `_probe_pair` パターン (`detector._probe_frame_rgb_hires` / `capture_region.localize_scorebar_at_anchor` を関数内 module 属性参照 — patch 先は `allaganeye.video.detector._probe_frame_rgb_hires`)
- Produces: `probe_gap(video_path: Path, anchor, t0: float, t1: float, *, stride: float = GAP_STRIDE, workers: int | None = None) -> list[GapProbe]` / `refine_segments(video_path: Path, anchor, segments: list[MatchBoundary], *, workers: int | None = None, stats: "DetectionStats | None" = None) -> list[MatchBoundary]`
- `refine_segments` の契約: 隣接 pair ごとに gap = next.start - prev.end。gap <= MERGE_GAP_MAX → 全域 1s probe → `adjudicate_gap` → merge なら結合 (start=prev.start, end=next.end, type は prev を継承)、boundary なら `snap_segment_edges`。gap > MERGE_GAP_MAX → 両端 60s 窓のみ probe して snap (裁定不要 = 常に boundary)。probe/裁定の例外は per-gap に隔離し「snap なし・merge なし」で続行 + warning (V2 結果より悪化させない)。stats が渡されたら `vtuber_gaps_tested` / `vtuber_gaps_merged` を加算

- [ ] **Step 1: Write the failing tests**

```python
class TestRefineSegments:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _seg(self, s, e):
        return {"start": float(s), "end": float(e), "type": "fl_match"}

    def test_fn_gap_merges_segments(self):
        segs = [self._seg(0, 400), self._seg(500, 900)]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            return_value=_gap_probes(("M" + "lll") * 25),  # 25% -> merge
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert out == [self._seg(0, 900)]

    def test_true_boundary_snaps_edges(self):
        segs = [self._seg(0, 400), self._seg(500, 900)]
        gap = _gap_probes("M" * 5 + "bb" + "l" * 80 + "M" * 3)
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap", return_value=gap
        ) as pg:
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert len(out) == 2
        # blackout run 先頭 (相対 idx 5) へ end snap。probe_gap は t0=400 起点で
        # 呼ばれるため GapProbe.t は絶対時刻を持つ (mock は相対 t だが契約検証は
        # snap が適用されたことと 2 segment 維持で行う)
        assert out[0]["end"] != 400.0 or out[1]["start"] != 500.0
        pg.assert_called_once()

    def test_long_gap_probes_only_edge_windows(self):
        # gap > MERGE_GAP_MAX: 両端 60s 窓のみ probe (呼び出し 2 回)
        segs = [self._seg(0, 400), self._seg(900, 1300)]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            return_value=_gap_probes("l" * 60),
        ) as pg:
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert len(out) == 2
        assert pg.call_count == 2

    def test_gap_probe_exception_keeps_v2_result(self):
        # per-gap 例外隔離: probe 失敗 gap は snap/merge なしで V2 のまま
        segs = [self._seg(0, 400), self._seg(500, 900)]
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            side_effect=RuntimeError("decode"),
        ):
            out = refine_segments(Path("d.mp4"), self.ANCHOR, segs)
        assert out == segs

    def test_stats_counters(self):
        segs = [self._seg(0, 400), self._seg(500, 900)]
        stats: dict = {}
        with patch(
            "allaganeye.video.vtuber_timeline.probe_gap",
            return_value=_gap_probes(("M" + "lll") * 25),
        ):
            refine_segments(Path("d.mp4"), self.ANCHOR, segs, stats=stats)
        assert stats["vtuber_gaps_tested"] == 1
        assert stats["vtuber_gaps_merged"] == 1


class TestProbeGap:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def test_probe_includes_band_brightness(self):
        frames = {}

        def fake_probe(video_path, t):
            return _synthetic_frame(100) if t < 100 else _synthetic_frame(100)

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
            probes = probe_gap(Path("d.mp4"), self.ANCHOR, 10.0, 13.0)
        assert len(probes) == 3
        assert all(p.band_b is not None and abs(p.band_b - 100.0) < 0.5 for p in probes)
        assert all(p.present for p in probes)
```

- [ ] **Step 2: Run to verify FAIL** — ImportError (refine_segments / probe_gap)

- [ ] **Step 3: Implement**

```python
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
    """[t0, t1) を stride 間隔で dense probe する (V3 用、例外は probe 単位隔離)。"""
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
    segments: "list[MatchBoundary]",
    *,
    workers: int | None = None,
    stats=None,
) -> "list[MatchBoundary]":
    """V3: 隣接 segment 間 gap の merge 裁定 + 確定境界の snap。

    per-gap 例外隔離: probe/裁定に失敗した gap は V2 の粗い結果を維持する
    (V3 は改善のみ、失敗しても悪化させない)。
    """
    if len(segments) < 2:
        return list(segments)
    result: list[MatchBoundary] = [dict(segments[0])]
    for nxt in segments[1:]:
        prev = result[-1]
        gap = nxt["start"] - prev["end"]
        try:
            if gap <= MERGE_GAP_MAX:
                probes = probe_gap(
                    video_path, anchor, prev["end"], nxt["start"], workers=workers
                )
                if stats is not None:
                    stats["vtuber_gaps_tested"] = stats.get("vtuber_gaps_tested", 0) + 1
                if adjudicate_gap(probes) == "merge":
                    if stats is not None:
                        stats["vtuber_gaps_merged"] = (
                            stats.get("vtuber_gaps_merged", 0) + 1
                        )
                    prev["end"] = nxt["end"]
                    continue
                new_end, new_start = snap_segment_edges(
                    prev["end"], nxt["start"], probes
                )
            else:
                head = probe_gap(
                    video_path,
                    anchor,
                    prev["end"],
                    prev["end"] + _LONG_GAP_EDGE_WINDOW_S,
                    workers=workers,
                )
                tail = probe_gap(
                    video_path,
                    anchor,
                    nxt["start"] - _LONG_GAP_EDGE_WINDOW_S,
                    nxt["start"],
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
            result.append(dict(nxt))
            continue
        prev["end"] = new_end
        follower = dict(nxt)
        follower["start"] = new_start
        result.append(follower)
    return result
```

- [ ] **Step 4: Run to verify PASS** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py -v` → 36 passed
- [ ] **Step 5: Lint + commit**

```bash
python -m ruff check .
python -m ruff format --check .
python -m pyright
git add allaganeye/video/vtuber_timeline.py tests/test_vtuber_timeline.py
git commit -m "feat(l3): V3 probe_gap + refine_segments orchestration (Refs #895)"
```

---

### Task 4: V4 配線 + timeline 統計 (`detect_matches_timeline` の V3/V4 統合)

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py` (detect_matches_timeline 拡張)
- Modify: `allaganeye/video/detector.py` (`DetectionStats` TypedDict に新 key 追加のみ)
- Modify: `allaganeye/commands/split_matches.py` (`_print_detection_stats` に guarded section 追加)
- Test: `tests/test_vtuber_timeline.py` + `tests/test_split_matches.py` (追記)

**Interfaces:**

- Consumes: `detector._validate_match_segments(video_path, segments, anchor, workers, stats, duration_hint)` (masked L2、#822。15 点 at-anchor quorum ≥2 + 全 UNKNOWN keep。**実装前に必ず読み、全滅 fail-safe (全 segment drop → 全件 keep + warning) の有無を確認**。なければ wrapper 側で实装)
- Produces: `detect_matches_timeline(video_path, duration_hint, *, min_match_duration, workers=None, progress_callback=None, stats=None) -> tuple[list[MatchBoundary], RegionTimeline] | None` (**return type annotation を明記** — P1 Minor #3 消化)。V2 後に V3 (`refine_segments`) → V4 (`_validate_match_segments` + 30min 低信頼 warning) を実行
- `DetectionStats` 追加 key (total=False なので additive): `vtuber_timeline_probes: int` / `vtuber_anchor_confidence: float` / `vtuber_gaps_tested: int` / `vtuber_gaps_merged: int` / `vtuber_v4_dropped: int` / `vtuber_low_confidence_segments: int`
- `_print_detection_stats`: `if "vtuber_timeline_probes" in stats:` guarded で 2 行表示 (`Timeline (vtuber): N probes, anchor conf X.XX` / `V3: N gaps tested, N merged; V4: N dropped, N low-confidence`)。OBS run は key 不在で無表示 (bit-exact 維持)
- V4 の 30min 低信頼: `end - start > 1800.0` の segment に `logger.warning` + stats 加算 (metadata schema は不変、spec §2.3)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vtuber_timeline.py
class TestDetectMatchesTimelineV3V4:
    ANCHOR = ScorebarLocalization(532, 1147, 0, 45, 0.8)

    def _run(self, scan_spec: str, stats=None):
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes(scan_spec),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: segs,
            ) as rs,
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=lambda vp, segs, a, w, st, d: segs,
            ) as vs,
        ):
            result = detect_matches_timeline(
                Path("d.mp4"),
                duration_hint=520.0,
                min_match_duration=300.0,
                stats=stats,
            )
        return result, rs, vs

    def test_v3_and_v4_are_wired(self):
        result, rs, vs = self._run("l" * 6 + "M" * 40 + "l" * 6)
        assert result is not None
        rs.assert_called_once()
        vs.assert_called_once()

    def test_low_confidence_flag_for_long_segment(self, caplog):
        import logging

        stats: dict = {}
        # 200 probes = 2000s の連続 match -> 30min 超 -> low-confidence warning
        with caplog.at_level(
            logging.WARNING, logger="allaganeye.video.vtuber_timeline"
        ):
            result, _, _ = self._run("M" * 200, stats=stats)
        assert result is not None
        assert stats.get("vtuber_low_confidence_segments") == 1
        assert "exceeds" in caplog.text or "low-confidence" in caplog.text

    def test_stats_populated(self):
        stats: dict = {}
        result, _, _ = self._run("l" * 6 + "M" * 40 + "l" * 6, stats=stats)
        assert stats["vtuber_timeline_probes"] == 52
        assert abs(stats["vtuber_anchor_confidence"] - 0.8) < 1e-9

    def test_v4_empty_after_validation_falls_back(self):
        # V4 が全 segment を drop した場合も None (縮退 floor、空 authoritative 禁止)
        with (
            patch(
                "allaganeye.video.vtuber_timeline.resolve_vtuber_anchor",
                return_value=self.ANCHOR,
            ),
            patch(
                "allaganeye.video.vtuber_timeline.scan_timeline",
                return_value=_probes("l" * 6 + "M" * 40 + "l" * 6),
            ),
            patch(
                "allaganeye.video.vtuber_timeline.refine_segments",
                side_effect=lambda vp, a, segs, **kw: segs,
            ),
            patch(
                "allaganeye.video.detector._validate_match_segments",
                side_effect=lambda vp, segs, a, w, st, d: [],
            ),
        ):
            assert (
                detect_matches_timeline(
                    Path("d.mp4"), duration_hint=520.0, min_match_duration=300.0
                )
                is None
            )
```

```python
# tests/test_split_matches.py
def test_print_detection_stats_vtuber_timeline_section(capsys):
    """timeline 統計 key があるときのみ vtuber section を表示 (OBS 無影響 pin)。"""
    from allaganeye.commands.split_matches import _print_detection_stats

    _print_detection_stats(
        {
            "vtuber_timeline_probes": 1449,
            "vtuber_anchor_confidence": 0.589,
            "vtuber_gaps_tested": 8,
            "vtuber_gaps_merged": 4,
            "vtuber_v4_dropped": 0,
            "vtuber_low_confidence_segments": 0,
        }
    )
    out = capsys.readouterr().out
    assert "Timeline (vtuber): 1449 probes" in out
    assert "anchor conf 0.59" in out
    assert "8 gaps tested, 4 merged" in out
```

- [ ] **Step 2: Run to verify FAIL** — TypeError (stats kwarg 未対応) / AssertionError (wiring 未実装)

- [ ] **Step 3: Implement**

`vtuber_timeline.py` の `detect_matches_timeline` を拡張 (V2 の空チェックは維持、その後に V3→V4→低信頼→再度空チェック):

```python
LOW_CONFIDENCE_SEGMENT_S = 1800.0
"""30min 超 segment は result-merge 型見逃しの疑い (spec §2 V4)."""


def detect_matches_timeline(
    video_path: Path,
    duration_hint: float,
    *,
    min_match_duration: float,
    workers: int | None = None,
    progress_callback: Callable[[int, int, int], None] | None = None,
    stats=None,
) -> "tuple[list[MatchBoundary], RegionTimeline] | None":
    ...  # V0/V1/V2 は既存のまま (空 V2 チェック含む)
    # V2 の後 (boundaries 非空確定後) に追加:
    if stats is not None:
        stats["vtuber_timeline_probes"] = len(probes)
        stats["vtuber_anchor_confidence"] = float(anchor.confidence)
    from allaganeye.video import detector as _detector

    boundaries = refine_segments(
        video_path, anchor, boundaries, workers=workers, stats=stats
    )
    boundaries = _detector._validate_match_segments(
        video_path, boundaries, anchor, workers, stats, duration_hint
    )
    if stats is not None and "vtuber_v4_dropped" not in stats:
        stats["vtuber_v4_dropped"] = (
            0  # _validate_match_segments が設定しない場合の表示用 floor
        )
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
    if not boundaries:
        logger.warning(
            "vtuber timeline: no segments after V4 validation; "
            "falling back to band-crop path"
        )
        return None
    ...  # RegionTimeline 構築 + return は既存のまま
```

実装ノート: `_validate_match_segments` を読んで (a) drop 数を stats に載せる key 名が既にあるか (あればそれを表示に使い `vtuber_v4_dropped` は不要 — 表示側の key を合わせる)、(b) 全滅 fail-safe の有無を確認。全滅 fail-safe が「全 drop → keep」実装なら上の `if not boundaries` は実質 dead だが、defense-in-depth として維持 (P1 の空 segmentation gate と同じ思想)。

`detector.py` — `DetectionStats` TypedDict に 6 key を追加し、`detect_match_boundaries` の timeline 呼び出しに `stats=stats` を渡す (gate 内 1 行変更)。

`split_matches.py` — `_print_detection_stats` 末尾に:

```python
    if "vtuber_timeline_probes" in stats:
        typer.echo(
            f"  Timeline (vtuber): {stats['vtuber_timeline_probes']} probes, "
            f"anchor conf {stats.get('vtuber_anchor_confidence', 0.0):.2f}"
        )
        typer.echo(
            f"  V3: {stats.get('vtuber_gaps_tested', 0)} gaps tested, "
            f"{stats.get('vtuber_gaps_merged', 0)} merged; "
            f"V4: {stats.get('vtuber_v4_dropped', 0)} dropped, "
            f"{stats.get('vtuber_low_confidence_segments', 0)} low-confidence"
        )
```

- [ ] **Step 4: Run to verify PASS** — `PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py tests/test_detector.py tests/test_split_matches.py -q` → 全 pass (既存無破壊を必ず確認)
- [ ] **Step 5: フルスイート + lint + commit**

```bash
PYTHONUTF8=1 python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pyright
git add -A
git commit -m "feat(l3): V4 配線 + timeline 統計 (V3/V4 統合、30min 低信頼フラグ) (Refs #895)"
```

---

### Task 5: P2 送り Minor 3 件 + spec erratum

**Files:**

- Modify: `allaganeye/video/vtuber_timeline.py` (docstring の `U+00A7`→`sec.` / `U+00D7`→`x` 置換)
- Modify: `docs/superpowers/specs/2026-07-17-vtuber-timeline-detection-design.md` (erratum 1 件)
- Test: `tests/test_vtuber_timeline.py` (band_mad=None 分岐 test 1 本)

**Interfaces:** なし (独立した cleanup)

- [ ] **Step 1: band_mad=None 分岐 test を追加** (P1 final review Minor #1):

```python
class TestSegmentTimeline:  # 既存 class に追記
    def test_present_with_unknown_mad_is_not_evidence(self):
        # present=True でも band_mad=None (motion decode 失敗) は evidence にしない
        # (述語の band_mad is not None guard の直接 pin)
        probes = [
            TimelineProbe(t=i * 10.0, present=True, band_mad=None) for i in range(60)
        ]
        assert segment_timeline(probes, min_match_duration=300.0) == []
```

- [ ] **Step 2: FAIL 確認 → 実は既存実装で PASS するはず** — このテストは guard の pin (RED にならない regression test)。`PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py -k unknown_mad -v` → PASS を確認 (RED cycle 不要の pin test であることを commit message に明記)
- [ ] **Step 3: docstring 置換** — `grep -n "U+00A7\|U+00D7" allaganeye/video/vtuber_timeline.py` の各行を `sec.` / `x` に置換 (例: `PoC report U+00A72` → `PoC report sec.2`)。ascii guard が green のままであること
- [ ] **Step 4: spec erratum 追記** — spec §2 V3 box の直後に:

```markdown
> **erratum (2026-07-19, P2 実装)**: V3 (b) の「presence 崩壊点/回復点 (refine_boundary 二分探索)」は
> **gap dense 系列 (1s) のエッジ検出に置換**した。at-anchor presence は per-frame に非単調
> (Onsal 40-60%) で二分探索の単調性前提が成立しないため。1s 系列の先頭/末尾 present run
> エッジで ±1-2s 精度を得る (実装: `snap_segment_edges`)。
```

- [ ] **Step 5: Lint (markdownlint 含む) + commit**

```bash
PYTHONUTF8=1 python -m pytest tests/test_vtuber_timeline.py -q
python -m ruff check .
python -m ruff format --check .
python -m pyright
bash scripts/check-markdownlint.sh
git add -A
git commit -m "chore(l3): P1 持ち越し Minor 3 件 + V3-b spec erratum (Refs #895)"
```

---

### Task 6: 実機 gate + PR (controller 実施)

**Files:** なし

- [ ] **Step 1: フルスイート + 全 lint** (Task 4/5 で実施済みなら最終確認のみ)
- [ ] **Step 2: OBS bit-exact gate (実機、detached)** — detector.py 変更ありのため必須:

```bash
# detached Start-Process + log (PowerShell、ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos)
python -m pytest tests/test_v030_baseline_regression.py -m slow -v
```

Expected: Class A 4/4 + Class B 1/1 PASSED

- [ ] **Step 3: VTuber P2 gate (実機、detached)** — きゅま + gyawa を `--vtuber --no-cache` で detect:

Expected: **きゅま 11 segments** (15→11: 偽分割 4 箇所 = 2660/2910, 6600/6640, 9320/9340, 13480/13500 が merge され、真の境界 6 箇所 = 2100-2210, 3350-3530, 4610-4730, 5710-5980 (振り返り = frozen marker), 6950-7160, 12630-12910 は維持) / **gyawa 6 segments 維持**。境界時刻は PoC GT (report sec.7.2) と ±15s 以内が望ましい (正式 gate は P3)

- [ ] **Step 4: PR 作成** — Pre-flight Step 0-4 → PR (base develop-0.3.0) → Self-Test Report (machine-verified: suite/lint/OBS gate/VTuber gate 実測値) → /iterate-review 自走。cache 注意: `--no-cache` 必須 (vtuber_algo は P2 で bump しない — V3/V4 は検出出力を変えるため **`_VTUBER_ALGO_VERSION` を 3 に bump する 1 行を Task 4 に含めること**。忘れると P1 timeline cache が silent 再利用される)

> **注 (Task 4 への追記事項)**: 上記のとおり `_VTUBER_ALGO_VERSION = 2 → 3` の bump が Task 4 の実装に含まれる (`feedback_detection_flag_cache_key`)。既存 test `test_vtuber_algo_version_is_2` は `_is_3` に改名・更新する。

---

## Self-Review 記録

- spec 被覆: §2 V3 (a) = Task 1+3 / V3 (b) = Task 2+3 / V4 = Task 4 / 統計・低信頼 = Task 4 / #895 P2 追記 (統計 + 縮退表示) = Task 4 (fallback 時は既存 warning + stats で可視化、progress バー 2 周は仕様として許容し P3 doc 同期で記載) / P1 持ち越し Minor = Task 5
- 型整合: `GapProbe` / `adjudicate_gap` / `snap_segment_edges` / `probe_gap` / `refine_segments` の署名は Task 間一致。`detect_matches_timeline` の stats kwarg は Task 4 で追加し detector 呼び出しも同時更新
- cache key bump (`_VTUBER_ALGO_VERSION` 3) は Task 4 に統合 (Task 6 の注を正とする)
- 既知の implementer 裁量点: `_validate_match_segments` の drop 数 stats key 実名確認 (Task 4 実装ノート) / snap の絶対時刻変換 (probe_gap は絶対 t を返すので snap は追加変換不要)
