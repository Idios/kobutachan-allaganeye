# L3 Phase 2: Stage 2 分類の localize 化 (VTuber 過分割解消) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VTuber (`--vtuber`) 経路の各 blackout を **scorebar present (localize) 単独**で `match_boundary` / `in_match` / `non_fl` 分類し、短い `in_match` (キャラダウン等の試合中暗転) を除去して VTuber を実用分割にする。OBS (`vtuber=False`) は現行 v2 分類器を一行も変えず bit-exact を維持する。

**Architecture:** spec [2026-05-31-l3-detection-rearchitecture-two-signal-design.md](../specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md) §8 Phase 2 + §8.1 確定事項。分類器は **OBS=v2 authoritative (不変) / VTuber=localize present 単独 authoritative** の 2 経路を `vtuber` flag で分岐する。motion (band-MAD) は **telemetry 収集のみ** (分類に AND しない、配線は Phase 3)。v2 vs localize の parity は production に入れず **harness 専用**で計測する。`localize_scorebar` は `_probe_scorebar_context` が既に decode 済の hi-res frame を再利用する (additive + flag-gate、OBS は localize 非計算)。VTuber では `_drop_post_match_trailing` (v2 直接プローブ) を call site で gate off し、v2 FN による VTuber 最終試合の silent 削除を防ぐ。

**Tech Stack:** Python 3 / numpy / OpenCV (`cv2`) / pytest (slow marker for video-gated) / ThreadPoolExecutor。検証は unit (合成 frame + monkeypatch) + baseline 回帰 + slow harness (OBS parity / VTuber split)。

---

## 適用条件チェック (refactor-pattern)

本 plan は `scorebar.py` / `detector.py` + tests に閉じる (capture_region.py / gpu_detector.py は触らない)。touched file ~5、diff は中規模で [`docs/refactor-pattern.md`](../../refactor-pattern.md) §1 の Phase 分割閾値 (touched > 30 file or diff > 1000 line) 未満。**Phase 0+1+2 をまとめて 1 PR** にする (user 方針: VTuber 実用化まで一貫 land)。

## spec が要求する Phase 2 gate (受け入れの中心)

- **OBS bit-exact**: 5 baseline (`tests/baselines/v0.3.0/obs-*.metadata.json`) が `vtuber=False` で完全一致 (検出 timestamp 不変)。v2 経路は構造的に不変。
- **VTuber 過分割解消**: `--vtuber` で band crop が拾う試合中暗転 (両側 present の in_match) が分類で除去され、過分割が減る (slow / 実機)。
- **production 影響なし**: localize 分類は `vtuber=True` の内側のみ。`vtuber=False` (= 既存 CLI default + 既存呼び出し) の出力は不変。

---

## File Structure

| ファイル | 本 plan での責務 | 変更種別 |
| --- | --- | --- |
| `allaganeye/video/scorebar.py` | `_localize_present_from_raw` 新規 + `_probe_scorebar_context` に `with_localize` (3-tuple 化) + `_band_mad_min` 抽出 (+#4 guard) + `_classify_blackout_localize` 新規 + `classify_blackout` / `filter_blackouts_with_scorebar` / `_merge_boundary_pairs` に `band_region`/`vtuber` 追加 | Modify |
| `allaganeye/video/detector.py` | `detect_match_boundaries` が `band_region`/`vtuber` を `filter_blackouts_with_scorebar` に渡す + `_drop_post_match_trailing` call site を `not vtuber` で gate | Modify |
| `tests/test_scorebar.py` | A/B/C の unit (probe 3-tuple / MAD guard / localize 分類 / 真理値表 / vtuber=False 不変) | Modify |
| `tests/test_detector.py` | D の unit (trailing-drop vtuber gate / band_region threading) | Modify |
| `tests/test_l3_phase2_parity.py` | OBS v2-vs-localize parity + VTuber split の slow 受け入れ (sample-gated) | Create |

> **実装前に確認済みの事実 (self-review 2026-06-01)**:
>
> - `classify_blackout` の既存 `region` 引数は **blackout (start,end) tuple** (CaptureRegion ではない)。新 ROI 引数は名前衝突を避け **`band_region`** とする。`filter_blackouts_with_scorebar` の `blackout_regions` も tuple list。
> - `_probe_scorebar_context` は既に lo-res (`_probe_frame_rgb`、motion 用) と hi-res (`_probe_frame_rgb_hires`、v2 用、`use_v2` 時のみ) を両方 decode し、hi_raws は v2 後に破棄している。localize はこの hi_raws を再利用する。
> - `_probe_scorebar_context` の呼び出しは scorebar.py 内 **5 箇所** (classify pre :277 / post :280 / re-probe pre :315 / re-probe post :318 / merge :562)。3-tuple 化で全 5 箇所の unpack を更新する。
> - `_drop_post_match_trailing` の呼び出しは detector.py:475-482 (`detect_match_boundaries` 内、`vtuber` がスコープにある)。`_has_scorebar_v2` (絶対座標) を直接プローブするため VTuber inset では全 probe FN → 最終試合 silent 削除 (Codex #1 CRITICAL 確認済)。
> - `_is_static_from_frames` は OBS v2 経路の short-static override (classify_blackout :354-370) で使われる **bit-exact 経路**。`region is None` (絶対 ROI) 分岐は一切変えない。#4 guard は `else` (band) 分岐にのみ追加する。
> - audio Fanfare promotion は `AUDIO_FROZEN=True` (`allaganeye/audio/__init__.py:48`、#327/#303) で inert。本 plan では触らない (Codex #6 は frozen 中 moot)。

依存: **A → B → C → D**。A が localize-present probe を産み、B が分類器を作り、C が filter/merge に通し、D が detector に配線する。各 group 内は TDD (failing test → impl → pass → commit)。

---

## Task Group A — localize-present primitive を probe context に追加 (P2-c / Codex #8)

### Task A1: `_localize_present_from_raw` + `_probe_scorebar_context` の `with_localize` (3-tuple 化)

`_probe_scorebar_context` が既に decode 済の hi-res frame に `localize_scorebar` をかけ、localize-present を **第 3 要素**として返す。OBS production は `with_localize=False` (既定) で localize 非計算、戻り値第 3 要素は全 None → 既存 5 caller は `, _` 追加だけで bit-exact。

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test**

`tests/test_scorebar.py` に追加:

```python
from allaganeye.video import scorebar as sb


def test_probe_context_3tuple_localize_none_by_default(monkeypatch):
    # with_localize omitted -> 3rd element all None, scorebar/raw unchanged.
    monkeypatch.setattr(sb, "_probe_frame_rgb", lambda v, t, h: f"lo{t}".encode())
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", lambda v, t: f"hi{t}".encode())
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: True)
    # _localize_present_from_raw must NOT be called when with_localize is False.
    monkeypatch.setattr(
        sb, "_localize_present_from_raw",
        lambda raw: (_ for _ in ()).throw(AssertionError("must not localize")),
    )
    scorebar, raw, loc = sb._probe_scorebar_context(
        Path("x.mp4"), [1.0, 2.0], height=180, workers=1
    )
    assert scorebar == [True, True]
    assert raw == [b"lo1.0", b"lo2.0"]
    assert loc == [None, None]


def test_probe_context_with_localize_populates_3rd(monkeypatch):
    monkeypatch.setattr(sb, "_probe_frame_rgb", lambda v, t, h: b"lo")
    monkeypatch.setattr(sb, "_probe_frame_rgb_hires", lambda v, t: f"hi{t}".encode())
    monkeypatch.setattr(sb, "_has_scorebar_v2", lambda raw: False)
    monkeypatch.setattr(sb, "_localize_present_from_raw", lambda raw: raw == b"hi1.0")
    scorebar, raw, loc = sb._probe_scorebar_context(
        Path("x.mp4"), [1.0, 2.0], height=180, workers=1, with_localize=True
    )
    assert loc == [True, False]
```

(`from pathlib import Path` が test 先頭にあることを確認、なければ追加。)

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "probe_context" -v`
Expected: FAIL (`ValueError: not enough values to unpack (expected 3, got 2)` / `AttributeError: ... _localize_present_from_raw`).

- [ ] **Step 3: Add `_localize_present_from_raw` + thread `with_localize` into `_probe_scorebar_context`**

`scorebar.py` の import に追加 (detector からの import ブロックへ `_SCOREBAR_V2_PROBE_HEIGHT`, `_SCOREBAR_V2_PROBE_WIDTH`、capture_region から `localize_scorebar`):

```python
from allaganeye.video.detector import (
    DetectionStats,
    _SAMPLE_WIDTH,
    _SCOREBAR_METHOD,
    _SCOREBAR_ROI_X_END,
    _SCOREBAR_ROI_X_START,
    _SCOREBAR_ROI_Y_END,
    _SCOREBAR_ROI_Y_START,
    _SCOREBAR_V2_PROBE_HEIGHT,
    _SCOREBAR_V2_PROBE_WIDTH,
    _has_scorebar,
    _has_scorebar_v2,
    _probe_frame_rgb,
    _probe_frame_rgb_hires,
    _resolve_workers,
)
from allaganeye.video.capture_region import CaptureRegion, FULL_FRAME, localize_scorebar
```

(既存の `from allaganeye.video.capture_region import CaptureRegion` 行は上の行で置換する。)

`_probe_scorebar_context` の直前に helper を追加:

```python
def _localize_present_from_raw(raw: bytes | None) -> bool | None:
    """hi-res RGB probe bytes -> localize-present (True/False). None on probe failure.

    Reshapes the 1920x1080 RGB probe buffer and runs the position-independent
    localizer (``localize_scorebar``).  A successfully decoded frame yields
    True/False (a clean localizer miss is treated as absent, not unknown, so
    majority vote behaves like the v2 path).  Only a missing frame (raw None)
    yields None.  Used by the VTuber classification path; OBS never calls it.
    """
    if raw is None:
        return None
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(
        _SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3
    )
    return localize_scorebar(frame) is not None
```

`_probe_scorebar_context` の signature に `with_localize: bool = False` を追加し、戻り値を 3-tuple にする。関数末尾の `return` 直前に localize 計算を追加:

```python
        # localize-present from the hi-res frames already decoded for v2
        # (additive; OBS production passes with_localize=False -> all None,
        # so existing callers stay bit-exact).
        localize_results: dict[float, bool | None] = {}
        if with_localize and use_v2:
            for t in unique_ts:
                localize_results[t] = _localize_present_from_raw(hi_raws.get(t))
        else:
            for t in unique_ts:
                localize_results[t] = None

    return (
        [scorebar_results[t] for t in timestamps],
        [raw_frames[t] for t in timestamps],
        [localize_results[t] for t in timestamps],
    )
```

signature 変更:

```python
def _probe_scorebar_context(
    video_path: Path,
    timestamps: list[float],
    height: int,
    workers: int | None,
    *,
    with_localize: bool = False,
) -> tuple[list[bool | None], list[bytes | None], list[bool | None]]:
```

そして scorebar.py 内の **5 つの呼び出し**を 3-tuple unpack に更新:

```python
# classify_blackout pre/post (:277, :280)
    pre_results, pre_frames, _pre_loc = _probe_scorebar_context(
        video_path, pre_timestamps, height, workers
    )
    post_results, post_frames, _post_loc = _probe_scorebar_context(
        video_path, post_timestamps, height, workers
    )
# re-probe pre/post (:315, :318)
            pre_re_results, _, _ = _probe_scorebar_context(
                video_path, pre_re_timestamps, height, workers
            )
            post_re_results, _, _ = _probe_scorebar_context(
                video_path, post_re_timestamps, height, workers
            )
# _merge_boundary_pairs gap probe (:562)
                probe_results, _, _ = _probe_scorebar_context(
                    video_path, probe_points, height, workers,
                )
```

- [ ] **Step 4: Run, verify pass + full scorebar suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (new probe_context tests + all existing scorebar tests green — 3-tuple change is unpack-only for existing callers).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
ruff format --check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): _probe_scorebar_context に with_localize (hi-res 再利用, 3-tuple, Phase 2 A1)

OBS は with_localize=False (既定) で localize 非計算・第3要素全None -> 既存 caller bit-exact。

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task Group B — localize present-only 分類器 (P2-a)

### Task B1: `_band_mad_min` 抽出 + band ROI guard (#4) — 絶対 ROI は bit-exact

`_is_static_from_frames` から min-MAD 算出を `_band_mad_min` に分離する (telemetry が float を取れるように)。`region is None` (絶対 ROI) 分岐は一切変えず OBS bit-exact。`else` (band) 分岐に空 ROI guard を追加 (Codex #4、7-8px@180p で nan 化を防ぐ)。

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test**

```python
import numpy as np
from allaganeye.video.scorebar import _band_mad_min, _is_static_from_frames
from allaganeye.video.capture_region import CaptureRegion

_W = 320


def _rgb(height, fill):
    return np.full((height, _W, 3), fill, dtype=np.uint8).tobytes()


def test_band_mad_min_absolute_roi_matches_is_static():
    # region=None path must stay bit-exact: identical frames -> MAD 0 -> static.
    frames = [_rgb(180, 50), _rgb(180, 50)]
    assert _band_mad_min(frames, 180) == 0.0
    assert _is_static_from_frames(frames, 180) is True


def test_band_mad_min_returns_none_for_degenerate_band():
    # a band so thin it collapses to an empty crop -> None (not nan, not 0).
    frames = [_rgb(180, 50), _rgb(180, 90)]
    degenerate = CaptureRegion(0.5, 0.5, 0.0, 0.0)
    assert _band_mad_min(frames, 180, degenerate) is None
    # _is_static_from_frames must not raise / must be False for degenerate band.
    assert _is_static_from_frames(frames, 180, degenerate) is False


def test_band_mad_min_none_for_under_two_frames():
    assert _band_mad_min([_rgb(180, 50)], 180) is None
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "band_mad_min" -v`
Expected: FAIL (`ImportError: cannot import name '_band_mad_min'`).

- [ ] **Step 3: Extract `_band_mad_min`, refactor `_is_static_from_frames`**

`_is_static_from_frames` を以下に置換 (絶対 ROI 分岐の式は現行のまま、band 分岐に guard 追加):

```python
def _band_mad_min(
    raw_frames: Sequence[bytes | None],
    height: int,
    region: CaptureRegion | None = None,
) -> float | None:
    """Min MAD of the scorebar ROI across consecutive frame pairs.

    Returns None when fewer than 2 valid frames are given, or when a band
    ``region`` collapses to an empty crop (degenerate / sub-pixel band at
    320x180; Codex #4).  ``region is None`` uses the absolute ``_SCOREBAR_ROI_*``
    ROI exactly as before (bit-exact).
    """
    valid = [r for r in raw_frames if r is not None]
    if len(valid) < 2:
        return None

    if region is None:
        x1 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_START)
        x2 = int(_SAMPLE_WIDTH * _SCOREBAR_ROI_X_END)
        y1 = int(height * _SCOREBAR_ROI_Y_START)
        y2 = int(height * _SCOREBAR_ROI_Y_END)
    else:
        x1 = max(0, int(region.x * _SAMPLE_WIDTH))
        x2 = min(_SAMPLE_WIDTH, int((region.x + region.w) * _SAMPLE_WIDTH))
        y1 = max(0, int(region.y * height))
        y2 = min(height, int((region.y + region.h) * height))
        if x2 <= x1 or y2 <= y1:
            return None  # degenerate band crop (Codex #4) -> no usable signal

    rois = []
    for raw in valid:
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, _SAMPLE_WIDTH, 3)
        rois.append(frame[y1:y2, x1:x2, :].astype(np.int16))

    mads = [float(np.mean(np.abs(rois[i] - rois[i + 1]))) for i in range(len(rois) - 1)]
    return min(mads)


def _is_static_from_frames(
    raw_frames: Sequence[bytes | None],
    height: int,
    region: CaptureRegion | None = None,
) -> bool:
    """Detect static screens (loading/result) via scorebar ROI frame diff.

    Returns False if fewer than 2 valid frames are provided or the band ROI is
    degenerate.  ``region is None`` keeps the absolute-ROI behavior (bit-exact).
    """
    min_mad = _band_mad_min(raw_frames, height, region)
    if min_mad is None:
        return False

    is_static = min_mad < _STATIC_SCREEN_MAD_THRESHOLD
    logger.debug(
        "static_screen: min=%.2f thr=%.1f region=%s -> %s",
        min_mad,
        _STATIC_SCREEN_MAD_THRESHOLD,
        "absolute" if region is None else "band",
        is_static,
    )
    return is_static
```

- [ ] **Step 4: Run scorebar suite (bit-exact guard for absolute ROI)**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (existing `_is_static_from_frames` tests green — absolute-ROI math unchanged; new `_band_mad_min` tests pass).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): _band_mad_min 抽出 + band ROI 空 guard (#4, 絶対 ROI bit-exact, Phase 2 B1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task B2: `_classify_blackout_localize` — present 単独分類器 + MAD telemetry

localize-present の pre/post majority で分類する (motion は AND しない、P2-a)。both-absent 時は v2 経路同様 region_width offset で re-probe する。band-MAD は logger.info で emit するだけ (Phase 3 校正用、分類に未使用)。

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test (localize results injected via monkeypatch)**

```python
def test_classify_localize_truth_table(monkeypatch):
    # Inject localize-present per probe set; assert the present-only labels.
    from allaganeye.video import scorebar as sb

    calls = {"n": 0}

    def fake_probe(video, ts, height, workers, *, with_localize=False):
        # pre call first, post call second (region_width re-probe not triggered
        # unless both not-True).
        calls["n"] += 1
        present = calls["n"] == 1  # pre present, post absent -> match_boundary
        return ([None] * len(ts), [b"f"] * len(ts), [present] * len(ts))

    monkeypatch.setattr(sb, "_probe_scorebar_context", fake_probe)
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 1.23)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 103.0), duration=400.0, height=180, workers=1
    )
    assert cls == "match_boundary"


def test_classify_localize_both_present_is_in_match(monkeypatch):
    from allaganeye.video import scorebar as sb
    monkeypatch.setattr(
        sb, "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False: (
            [None] * len(ts), [b"f"] * len(ts), [True] * len(ts)
        ),
    )
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 5.0)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 101.0), duration=400.0, height=180, workers=1
    )
    assert cls == "in_match"


def test_classify_localize_both_absent_is_non_fl(monkeypatch):
    from allaganeye.video import scorebar as sb
    monkeypatch.setattr(
        sb, "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False: (
            [None] * len(ts), [b"f"] * len(ts), [False] * len(ts)
        ),
    )
    monkeypatch.setattr(sb, "_band_mad_min", lambda *a, **k: 0.1)
    cls = sb._classify_blackout_localize(
        Path("x.mp4"), (100.0, 102.0), duration=400.0, height=180, workers=1
    )
    assert cls == "non_fl"
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "classify_localize" -v`
Expected: FAIL (`AttributeError: ... _classify_blackout_localize`).

- [ ] **Step 3: Implement `_classify_blackout_localize`**

`classify_blackout` の直前に追加:

```python
def _classify_blackout_localize(
    video_path: Path,
    region: tuple[float, float],
    duration: float,
    height: int,
    workers: int | None = None,
    *,
    band_region: CaptureRegion = FULL_FRAME,
) -> str:
    """Classify a blackout by position-independent scorebar presence (VTuber).

    Uses ``localize_scorebar`` majority on 3 pre + 3 post frames as the sole
    signal (motion is NOT ANDed in Phase 2 -- P2-a / spec section 8.1).  Mirrors
    the v2 re-probe fallback (#524) for the both-absent case.  Band-MAD is
    emitted to the log for Phase 3 calibration but does not affect the label.

    Returns ``"in_match"`` / ``"match_boundary"`` / ``"non_fl"`` / ``"unknown"``.
    """
    pre_timestamps = sorted(set(max(0.0, region[0] - d) for d in (3.0, 2.0, 1.0)))
    post_timestamps = sorted(set(min(duration, region[1] + d) for d in (1.0, 2.0, 3.0)))

    _, pre_frames, pre_loc = _probe_scorebar_context(
        video_path, pre_timestamps, height, workers, with_localize=True
    )
    _, post_frames, post_loc = _probe_scorebar_context(
        video_path, post_timestamps, height, workers, with_localize=True
    )
    pre_has = _majority_scorebar(pre_loc)
    post_has = _majority_scorebar(post_loc)

    # Re-probe further out when neither side localized a scorebar (#524 mirror):
    # a true boundary whose flanks both land in a fade/loading would otherwise
    # classify as non_fl and be dropped.
    if pre_has is not True and post_has is not True:
        region_width = region[1] - region[0]
        existing_pre = set(pre_timestamps)
        existing_post = set(post_timestamps)
        pre_re_ts = [
            t
            for t in sorted(
                set(max(0.0, region[0] - (region_width + d)) for d in (3.0, 2.0, 1.0))
            )
            if t not in existing_pre
        ]
        post_re_ts = [
            t
            for t in sorted(
                set(min(duration, region[1] + (region_width + d)) for d in (1.0, 2.0, 3.0))
            )
            if t not in existing_post
        ]
        if pre_re_ts:
            _, _, pre_re_loc = _probe_scorebar_context(
                video_path, pre_re_ts, height, workers, with_localize=True
            )
            pre_re = _majority_scorebar(pre_re_loc)
            if pre_re is not None:
                pre_has = pre_re
        if post_re_ts:
            _, _, post_re_loc = _probe_scorebar_context(
                video_path, post_re_ts, height, workers, with_localize=True
            )
            post_re = _majority_scorebar(post_re_loc)
            if post_re is not None:
                post_has = post_re

    # Band-MAD telemetry for Phase 3 calibration -- emitted only, NOT used in
    # classification (P2-a). Grep "VTUBER_MAD" in logs to collect distributions.
    pre_mad = _band_mad_min(pre_frames, height, band_region)
    post_mad = _band_mad_min(post_frames, height, band_region)
    logger.info(
        "VTUBER_MAD region=[%.1f-%.1f] pre_mad=%s post_mad=%s",
        region[0],
        region[1],
        f"{pre_mad:.3f}" if pre_mad is not None else "na",
        f"{post_mad:.3f}" if post_mad is not None else "na",
    )

    if pre_has is None or post_has is None:
        classification = "unknown"
    elif pre_has and post_has:
        classification = "in_match"
    elif pre_has or post_has:
        classification = "match_boundary"
    else:
        classification = "non_fl"

    logger.debug(
        "vtuber classify region [%.1f-%.1f] (%.1fs): pre=%s post=%s -> %s",
        region[0],
        region[1],
        region[1] - region[0],
        pre_has,
        post_has,
        classification,
    )
    return classification
```

- [ ] **Step 4: Run, verify pass**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "classify_localize" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): _classify_blackout_localize (present 単独分類 + MAD telemetry, Phase 2 B2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task B3: `classify_blackout` に `band_region`/`vtuber` 追加 (vtuber=True で localize に委譲)

`classify_blackout` に `band_region`/`vtuber` を keyword 追加。`vtuber=True` のとき `_classify_blackout_localize` に委譲、`vtuber=False` は現行 v2 body を一切変えない (bit-exact)。

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test**

```python
def test_classify_blackout_vtuber_delegates_to_localize(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion
    seen = {}

    def fake_localize(video, region, duration, height, workers=None, *, band_region):
        seen["band"] = band_region
        return "in_match"

    monkeypatch.setattr(sb, "_classify_blackout_localize", fake_localize)
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    out = sb.classify_blackout(
        Path("x.mp4"), (10.0, 11.0), 400.0, 180, vtuber=True, band_region=band
    )
    assert out == "in_match"
    assert seen["band"] is band


def test_classify_blackout_obs_does_not_call_localize(monkeypatch):
    from allaganeye.video import scorebar as sb
    monkeypatch.setattr(
        sb, "_classify_blackout_localize",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("OBS must not localize")),
    )
    # vtuber defaults False -> must take the v2 path (probe returns absent here).
    monkeypatch.setattr(
        sb, "_probe_scorebar_context",
        lambda v, ts, h, w, *, with_localize=False: (
            [False] * len(ts), [b"f"] * len(ts), [None] * len(ts)
        ),
    )
    out = sb.classify_blackout(Path("x.mp4"), (10.0, 12.0), 400.0, 180)
    assert out == "non_fl"
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "classify_blackout_vtuber or classify_blackout_obs" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'vtuber'`).

- [ ] **Step 3: Add params + delegation**

`classify_blackout` の signature を変更:

```python
def classify_blackout(
    video_path: Path,
    region: tuple[float, float],
    duration: float,
    height: int,
    workers: int | None = None,
    *,
    band_region: CaptureRegion = FULL_FRAME,
    vtuber: bool = False,
) -> str:
```

docstring の直後 (関数本体の先頭、`pre_timestamps = ...` の前) に分岐を追加:

```python
    if vtuber:
        # VTuber path: position-independent localize as the sole signal
        # (spec section 8.1 P2-a). The OBS v2 body below is left untouched.
        return _classify_blackout_localize(
            video_path,
            region,
            duration,
            height,
            workers,
            band_region=band_region,
        )
```

(以降の v2 body は変更しない。)

- [ ] **Step 4: Run scorebar suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (vtuber delegation + OBS-no-localize new tests + all existing v2 tests green).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): classify_blackout に vtuber gate (localize 委譲, OBS v2 不変, Phase 2 B3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task Group C — filter / merge 配線 (P2-e)

### Task C1: `filter_blackouts_with_scorebar` に `band_region`/`vtuber` を通す

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test**

```python
def test_filter_threads_vtuber_to_classify(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion
    seen = []

    def fake_classify(video, region, duration, height, workers=None, *, band_region, vtuber):
        seen.append((vtuber, band_region.source))
        return "match_boundary"

    monkeypatch.setattr(sb, "classify_blackout", fake_classify)
    monkeypatch.setattr(sb, "_merge_boundary_pairs", lambda *a, **k: (a[1], a[2]))
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    sb.filter_blackouts_with_scorebar(
        Path("x.mp4"), [(10.0, 12.0)], 400.0, 180, band_region=band, vtuber=True
    )
    assert seen == [(True, "band")]
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "filter_threads_vtuber" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'band_region'`).

- [ ] **Step 3: Add params + thread to classify/merge**

`filter_blackouts_with_scorebar` の signature に keyword 追加 (既存 keyword の並びへ):

```python
def filter_blackouts_with_scorebar(
    video_path: Path,
    blackout_regions: list[tuple[float, float]],
    duration: float,
    height: int,
    workers: int | None = None,
    *,
    band_region: CaptureRegion = FULL_FRAME,
    vtuber: bool = False,
    audio_hits: Sequence[BgmHit] | None = None,
    stats: DetectionStats | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[tuple[float, float]], list[str]]:
```

`classify_blackout` 呼び出し (現 :457) を更新:

```python
        classification = classify_blackout(
            video_path, region, duration, height, workers,
            band_region=band_region, vtuber=vtuber,
        )
```

末尾の `_merge_boundary_pairs` 呼び出し (現 :516) を更新:

```python
    return _merge_boundary_pairs(
        video_path, kept, classifications, duration, height, workers,
        band_region=band_region, vtuber=vtuber,
    )
```

- [ ] **Step 4: Run scorebar suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (new threading test + existing tests green — defaults keep OBS behavior).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): filter_blackouts_with_scorebar に band_region/vtuber 配線 (Phase 2 C1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

### Task C2: `_merge_boundary_pairs` の gap probe を VTuber で localize に切替

**Files:**

- Modify: `allaganeye/video/scorebar.py`
- Test: `tests/test_scorebar.py`

- [ ] **Step 1: Write failing test**

```python
def test_merge_gap_probe_uses_localize_when_vtuber(monkeypatch):
    from allaganeye.video import scorebar as sb
    from allaganeye.video.capture_region import CaptureRegion
    captured = {}

    def fake_probe(video, points, height, workers, *, with_localize=False):
        captured["with_localize"] = with_localize
        # gap shows no scorebar by either signal -> eligible to merge.
        return ([None] * len(points), [b"f"] * len(points), [False] * len(points))

    monkeypatch.setattr(sb, "_probe_scorebar_context", fake_probe)
    regions = [(10.0, 12.0), (30.0, 32.0)]
    cls = ["match_boundary", "match_boundary"]
    band = CaptureRegion(0.3, 0.0, 0.37, 0.04, source="band")
    merged, merged_cls = sb._merge_boundary_pairs(
        Path("x.mp4"), regions, cls, 400.0, 180, None, band_region=band, vtuber=True
    )
    assert captured["with_localize"] is True
    assert merged == [(10.0, 32.0)]  # localize-absent gap -> merged
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "merge_gap_probe_uses_localize" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'band_region'`).

- [ ] **Step 3: Add params + localize-aware gap signal**

`_merge_boundary_pairs` の signature に keyword 追加:

```python
def _merge_boundary_pairs(
    video_path: Path,
    regions: list[tuple[float, float]],
    classifications: list[str],
    duration: float,
    height: int,
    workers: int | None,
    *,
    band_region: CaptureRegion = FULL_FRAME,
    vtuber: bool = False,
) -> tuple[list[tuple[float, float]], list[str]]:
```

gap probe (現 :562-567) を signal 切替に置換:

```python
                if vtuber:
                    _, _, probe_signal = _probe_scorebar_context(
                        video_path, probe_points, height, workers,
                        with_localize=True,
                    )
                else:
                    probe_signal, _, _ = _probe_scorebar_context(
                        video_path, probe_points, height, workers,
                    )
                all_valid = all(r is not None for r in probe_signal)
                any_scorebar = any(r is True for r in probe_signal)
```

(以降の `if all_valid and not any_scorebar:` merge ロジックは不変。`probe_results` 参照を `probe_signal` に変更。ログ行の `probes=%s, probe_results` も `probe_signal` に更新。)

- [ ] **Step 4: Run scorebar suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (new merge test + existing merge tests green — `vtuber=False` keeps v2 gap probe).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -F - <<'EOF'
feat(l3): _merge_boundary_pairs の gap probe を VTuber で localize 化 (Phase 2 C2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task Group D — detector 配線 + trailing-drop gate (P2-d)

### Task D1: `detect_match_boundaries` で band_region/vtuber を渡し、trailing-drop を VTuber で gate off

**Files:**

- Modify: `allaganeye/video/detector.py`
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write failing test**

```python
def test_filter_call_receives_band_region_and_vtuber():
    # static check: detect threads detect_region + vtuber into the scorebar filter.
    import inspect
    from allaganeye.video import detector as det
    src = inspect.getsource(det.detect_match_boundaries)
    assert "band_region=detect_region" in src
    assert "vtuber=vtuber" in src


def test_trailing_drop_gated_off_for_vtuber():
    import inspect
    from allaganeye.video import detector as det
    src = inspect.getsource(det.detect_match_boundaries)
    # the trailing-drop call must be guarded so it never runs on the VTuber path.
    assert "if src_resolution is not None and not vtuber:" in src
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -k "band_region_and_vtuber or trailing_drop_gated" -v`
Expected: FAIL (strings absent).

- [ ] **Step 3: Thread params + gate trailing-drop**

`detect_match_boundaries` の `filter_blackouts_with_scorebar` 呼び出し (現 :448-457) に 2 kwarg を追加:

```python
        refined_regions, region_classifications = filter_blackouts_with_scorebar(
            video_path,
            refined_regions,
            duration_hint,
            height,
            workers,
            band_region=detect_region,
            vtuber=vtuber,
            audio_hits=audio_hits,
            stats=stats,
            progress_callback=scorebar_progress_callback,
        )
```

trailing-drop の gate (現 :475) を変更し、コメントも更新:

```python
    # #797: drop a trailing post-match run when its early candidate-match window
    # shows no scorebar at any strided probe point. Skipped for VTuber
    # (vtuber=True): _drop_post_match_trailing probes v2 (absolute coords) which
    # FNs on an inset scorebar and would silently drop a real VTuber final match
    # (spec section 8.1 P2-d / Codex #1). VTuber trailing is handled in Phase 3.
    if src_resolution is not None and not vtuber:
        segments = _drop_post_match_trailing(
            segments,
            video_path,
            duration_hint,
            stats,
            min_match_duration=min_match_duration,
        )
```

- [ ] **Step 4: Run detector suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -v`
Expected: PASS (new gate tests + all existing detector tests green — `vtuber=False` default keeps the trailing-drop running exactly as today for OBS).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/detector.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py
git add allaganeye/video/detector.py tests/test_detector.py
git commit -F - <<'EOF'
feat(l3): detect が band_region/vtuber を分類に配線 + trailing-drop を VTuber で gate off (Phase 2 D1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## Task Group E — 受け入れ検証

### Task E1: OBS bit-exact 回帰 + 全 unit + lint (subagent 実行可能分)

**Files:**

- Test: 既存 `tests/test_scorebar.py` / `tests/test_detector.py` / baseline harness

- [ ] **Step 1: 全 unit suite (動画不要、subagent が完走できる)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
python -m pytest -q
```

Expected: PASS (全 unit green、slow は自動 skip)。

- [ ] **Step 2: 型・lint (PR Pre-flight 前倒し)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check .
ruff format --check .
pyright
```

Expected: いずれも 0 error。

- [ ] **Step 3: OBS baseline bit-exact (slow / sample-gated、Idios 実機)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos
python -m pytest -m slow -k "baseline or obs" -v
```

Expected: PASS — 5 OBS baseline が bit-exact (`vtuber=False` で v2 経路不変)。**差分が出たら STOP**: `vtuber=False` 経路に変更が漏れている (baseline 再生成は禁止)。timestamp churn (detected_at/generated_at) は非意味的差分として grep 除外して判定 (memory: baseline regen の timestamp churn)。

- [ ] **Step 4: 結果記録 (テストコード変更時のみ commit)**

bit-exact 確認をこの plan の実行ログに記録。

---

### Task E2: VTuber split + v2/localize parity slow 受け入れ (sample-gated、Idios 実機)

**Files:**

- Create: `tests/test_l3_phase2_parity.py`

- [ ] **Step 1: Write the slow acceptance scaffold (demonstrated-level)**

`tests/test_l3_phase2_parity.py`:

```python
"""Phase 2 受け入れ (slow / sample-gated): VTuber 過分割解消 + OBS v2/localize parity.

実機データ依存 (Idios verify、PYTHONUTF8=1)。CI では sample 未設定で skip。
parity は production に入れない harness 計測 (spec section 8.1 P2-b)。
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def _vtuber_sample() -> Path | None:
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER") or r"E:\allaganeye-samples"
    cands = list(Path(base).glob("*オンサル*")) if Path(base).exists() else []
    return cands[0] if cands else None


@pytest.mark.skipif(_vtuber_sample() is None, reason="VTuber sample not available")
def test_vtuber_split_removes_in_match_overspilt():
    from allaganeye.video.probe import probe_video
    from allaganeye.video import detector as det

    video = _vtuber_sample()
    meta = probe_video(video)
    res = (meta["width"], meta["height"])
    # vtuber=True path: classifier removes in-match band-crop blackouts.
    matches_vtuber = det.detect_match_boundaries(
        video, duration_hint=meta["duration"], src_resolution=res, vtuber=True
    )
    # Phase 1 over-split baseline (vtuber=True without Phase 2 classify) split far
    # more; here we assert the classified result is a sane, small match count.
    assert 0 < len(matches_vtuber) <= 12, (
        f"VTuber split should be practical, got {len(matches_vtuber)} matches"
    )


def _obs_sample() -> Path | None:
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not base or not Path(base).exists():
        return None
    cands = list(Path(base).glob("*.mkv"))
    return cands[0] if cands else None


@pytest.mark.skipif(_obs_sample() is None, reason="OBS sample not available")
def test_obs_v2_vs_localize_presence_parity(caplog):
    """v2 (authoritative) と localize の scorebar-present を時間グリッドで突合。

    production には入れない harness 専用計測 (spec section 8.1 P2-b)。一様グリッドで
    v2-present と localize-present を比較し、不一致を per-sample ログ化する。long
    非試合区間 (lobby/result) を含む全域で v2/localize の FP/FN 差を可観測にする
    (Codex #3)。assert は緩く「不一致が極端でない」のみ (閾値校正は Phase 3)。
    """
    import logging

    from allaganeye.video.probe import probe_video
    from allaganeye.video import detector as det
    from allaganeye.video import scorebar as sb

    video = _obs_sample()
    meta = probe_video(video)
    duration = meta["duration"]

    # Uniform interior grid (avoid the very edges).
    n = 40
    times = [duration * (i + 1) / (n + 1) for i in range(n)]

    agree = 0
    disagree = 0
    with caplog.at_level(logging.INFO):
        for t in times:
            raw = det._probe_frame_rgb_hires(video, t)
            v2 = det._has_scorebar_v2(raw)
            loc = sb._localize_present_from_raw(raw)
            if v2 is None or loc is None:
                continue
            if v2 == loc:
                agree += 1
            else:
                disagree += 1
                logging.getLogger(__name__).info(
                    "PARITY_DIFF t=%.1f v2=%s localize=%s", t, v2, loc
                )
        total = agree + disagree
        logging.getLogger(__name__).info(
            "PARITY summary: %d/%d agree (%d diffs)", agree, total, disagree
        )

    assert total > 0, "no valid probes -- check sample video / opencv"
    # localize should broadly agree with v2 on OBS (the position-independent
    # localizer finds the same full-screen scorebar). A wildly low agreement
    # signals a regression worth Idios investigating; calibration is Phase 3.
    assert agree / total >= 0.6, f"v2/localize parity too low: {agree}/{total}"
```

> **注**: parity は時間グリッドの scorebar-present 突合で、refined-region 再構築を必要とせず runnable。per-blackout の classification-level parity (より精密) は Idios 実機で `det.detect_match_boundaries` を `stats` 付きで走らせて深掘りしてよい。CI では sample 未設定で skip。

- [ ] **Step 2: Run (sample-gated)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
set PYTHONUTF8=1
set ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER=E:\allaganeye-samples
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos
python -m pytest tests/test_l3_phase2_parity.py -m slow -v
```

Expected: VTuber/OBS sample があれば PASS (split 実用域 + parity diff ログ)、無ければ SKIP。

- [ ] **Step 3: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check tests/test_l3_phase2_parity.py
git add tests/test_l3_phase2_parity.py
git commit -F - <<'EOF'
test(l3): VTuber split + OBS v2/localize parity slow 受け入れ (Phase 2 E2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
EOF
```

---

## 受け入れ条件 (Phase 2 完了基準)

- [ ] A: `_probe_scorebar_context` が hi-res 再利用で localize-present を第3要素に返し、`with_localize=False` (既定) では全 None で既存 caller が bit-exact (unit)。
- [ ] B: `_classify_blackout_localize` が present 単独で in_match/match_boundary/non_fl を出し、band-MAD を `VTUBER_MAD` ログに emit する (分類に未使用、unit)。`_band_mad_min` の絶対 ROI 分岐は bit-exact、band 空 ROI は None (unit)。
- [ ] B: `classify_blackout(vtuber=True)` が localize に委譲し、`vtuber=False` は v2 body 不変 (unit)。
- [ ] C: `filter_blackouts_with_scorebar` / `_merge_boundary_pairs` が band_region/vtuber を通し、VTuber merge gap probe が localize を使う (unit)。
- [ ] D: `detect_match_boundaries` が分類に band_region/vtuber を配線し、`_drop_post_match_trailing` を `not vtuber` で gate off (unit)。
- [ ] E1: OBS 5 baseline が bit-exact (timestamp churn 除く、slow / 実機)。全 unit + ruff + pyright green。
- [ ] E2: VTuber で過分割が実用域に収束、OBS v2/localize parity diff がログ化される (slow / 実機)。
- [ ] Idios の実機検証 (OBS detect 不変 + VTuber `--vtuber` split 目視 + GPU) — Iron Law 6 (logic 変更 + GPU + 長時間動画)。

## このプランがやらないこと (後 Phase / 範囲外)

- **motion (band-MAD) を分類に AND する配線・閾値校正** → Phase 3 (本 plan は telemetry 収集のみ、spec §8.1 P2-a)。
- **v2 retire / GT-accuracy gate 化** → Phase 4。
- **`_drop_post_match_trailing` の非破壊化 / localize 化** → 触らない (VTuber は gate off のみ、map §4 / §5.3、Phase 4 以降)。
- **VTuber GT 注釈・recall/precision 校正・fallback フラグ** → Phase 3 (全画面 UI が片側 scorebar を隠す偽境界 R3/R3b の恒久対策含む)。
- **audio Fanfare promotion の VTuber 対応** → 不要 (`AUDIO_FROZEN=True` で inert)。将来 unfreeze 時に再評価する caveat のみ (spec §8.1 P2-g)。
- **issue 起票** → Iron Law 2、起票時に AskUserQuestion。
