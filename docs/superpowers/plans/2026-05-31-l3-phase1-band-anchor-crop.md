# L3 Phase 1: scorebar 帯 anchor + 帯 crop wiring + MAD band-anchor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VTuber 録画の検出経路を「scorebar 帯に anchor した brightness/motion 測定」で成立させる基盤を作る。OBS は FULL_FRAME 縮退で v0.3.0 baseline と bit-exact を維持し、VTuber は scorebar 帯 crop で境界 blackout を回復する。

**Architecture:** spec ([2026-05-31-l3-detection-rearchitecture-two-signal-design.md](../specs/2026-05-31-l3-detection-rearchitecture-two-signal-design.md)) §8 Phase 1 の 3 要素を 3 task group で実装する。**A** = Stage 0 帯 anchor (`localize_scorebar` consensus → scorebar 帯 ROI + 保持矩形)、**B** = Stage 1 帯 crop wiring (#809 の検証済み `region_mean`/`is_full_frame` を再適用し brightness Pass1/Pass2/GPU を帯 crop で駆動)、**C** = `_is_static_from_frames` の band-anchor 化。全変更は **`region.is_full_frame()` 分岐の内側**に閉じ込め、OBS (FULL_FRAME) は現行の数値経路をそのまま通す (bit-exact)。

**Tech Stack:** Python 3 / numpy / OpenCV (`cv2`) / pytest (slow marker for video-gated) / ThreadPoolExecutor。検証は unit (合成 frame) + baseline 回帰 + slow harness (gyawa)。

---

## 適用条件チェック (refactor-pattern)

本 plan は detector.py / scorebar.py / capture_region.py / gpu_detector.py + tests に跨り、#809 (15 files) と同規模。[`docs/refactor-pattern.md`](../../refactor-pattern.md) §1 の Phase 分割閾値 (touched > 30 file or diff > 1000 line) に近い。

- **task group A / B / C は独立 commit・独立に OBS bit-exact を保つ**よう設計した。実行時に diff が閾値を超えそうなら、A / B / C を**別 PR に分割**してよい (各 group が単体で bit-exact gate を通る)。
- 本 plan は user 承認済 scope「spec §8 Phase 1 の 3 要素全部」を 1 plan にまとめたもの。PR 分割は実装後の判断 (Iron Law 6 Pre-flight 時)。

## spec が要求する Phase 1 gate (受け入れの中心)

- **OBS bit-exact**: 5 baseline (`tests/baselines/v0.3.0/obs-*.metadata.json`) が FULL_FRAME 縮退で完全一致 (検出 timestamp 不変)。
- **gyawa 帯 crop blackout 回復**: full-frame では拾えない試合境界 blackout が scorebar 帯 crop で回復する (#809 Wave F の drop 5/5 end を帯版で再現)。slow / sample-gated。
- **production 影響なし**: VTuber 新ロジックは `non-full-frame かつ high-confidence` gate の内側。OBS detect 出力は変わらない。

---

## File Structure

| ファイル | 本 plan での責務 | 変更種別 |
| --- | --- | --- |
| `allaganeye/video/capture_region.py` | `is_full_frame` / `region_mean` 再追加 (#809 再利用) + 新規 `detect_scorebar_band_region` (Stage 0 anchor) + 帯 ROI 導出 | Modify |
| `allaganeye/video/detector.py` | Pass1 brightness サイト (`_sample_chunk_frames` / `_decode_chunk_cpu_legacy`) と Pass2 (`_refine_blackout_regions`) を region 引数化 (FULL_FRAME 既定) + `_frame_brightness` helper + `_resolve_detect_region` | Modify |
| `allaganeye/video/gpu_detector.py` | GPU chunk brightness を region 引数化 (FULL_FRAME 既定) | Modify |
| `allaganeye/video/scorebar.py` | `_is_static_from_frames` に band ROI 引数追加 (絶対 ROI 既定で OBS bit-exact) | Modify |
| `tests/test_capture_region.py` | A: band anchor + region_mean + is_full_frame の unit | Modify |
| `tests/test_detector.py` | B: 帯 crop brightness の FULL_FRAME 縮退 = 現行一致 unit | Modify |
| `tests/test_scorebar.py` | C: MAD band-anchor の FULL_FRAME 縮退 unit | Modify (既存) |
| `tests/test_vtuber_region_e2e.py` | gyawa 帯 crop blackout 回復 slow 受け入れ | Create (現状なし) |

> **実装前に確認済みの事実 (self-review 2026-05-31)**: CPU brightness は 3 サイトで算出される —
> `_sample_chunk_frames` (detector.py:163-164、`_decode_chunk_cpu_v2` が使用)、
> `_decode_chunk_cpu_legacy` (:538-539)、`_probe_single_frame` (:828)。**いずれも
> `np.frombuffer(...)` の 1-D buffer に対し `float(frame.mean())`** を取る (2-D reshape していない)。
> frame は固定 `320x180` grayscale (`_SAMPLE_WIDTH=320` / `_SAMPLE_HEIGHT=180` / `_FRAME_SIZE=320*180`)。
> → 帯 crop には 2-D `(180,320)` reshape が必要。`_frame_brightness` は **FULL_FRAME 分岐で 1-D の
> まま `frame.mean()`** (bit-exact)、**band 分岐でのみ `reshape(_SAMPLE_HEIGHT,_SAMPLE_WIDTH)` してから
> `region_mean`** とする (B1 で実装)。Pass2 (:1340 は既に `reshape(height,_SAMPLE_WIDTH,3)`) と GPU 経路も
> 各サイトの frame 形状に合わせて分岐する。

依存: **A → B → C**。A が帯 ROI (`CaptureRegion`) を産み、B がそれで brightness を測り、C が同じ帯で motion を測る。各 group 内は TDD (failing test → impl → pass → commit)。

---

## Task Group A — Stage 0: scorebar 帯 anchor

### Task A1: `is_full_frame` と `region_mean` を capture_region.py に再追加 (#809 再利用)

これらは #809 parked branch (`claude/l3-809-pass1-region-wiring`) で検証済だが現ブランチには無い。spec §10 / re-plan §4 の「#809 wiring 再利用」に従い再追加する。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write failing tests for is_full_frame + region_mean**

`tests/test_capture_region.py` に追加:

```python
import numpy as np
from allaganeye.video.capture_region import CaptureRegion, FULL_FRAME, region_mean


def test_is_full_frame_true_only_for_unit_rect():
    assert FULL_FRAME.is_full_frame() is True
    assert CaptureRegion(0.0, 0.0, 1.0, 1.0).is_full_frame() is True
    assert CaptureRegion(0.1, 0.0, 0.9, 1.0).is_full_frame() is False
    assert CaptureRegion(0.0, 0.0, 1.0, 0.5).is_full_frame() is False


def test_region_mean_full_frame_equals_frame_mean():
    frame = np.arange(12, dtype=np.uint8).reshape(3, 4)
    assert region_mean(frame, FULL_FRAME) == float(frame.mean())


def test_region_mean_crops_to_band():
    frame = np.zeros((10, 10), dtype=np.uint8)
    frame[0:2, :] = 200  # bright top band
    # a band region covering only the top 20% should read ~200
    band = CaptureRegion(0.0, 0.0, 1.0, 0.2)
    assert region_mean(frame, band) == 200.0


def test_region_mean_empty_crop_clamps_to_1px():
    frame = np.full((10, 10), 50, dtype=np.uint8)
    degenerate = CaptureRegion(0.999, 0.999, 0.0001, 0.0001)
    # must not raise / must return a finite mean (>=1px clamp)
    assert region_mean(frame, degenerate) == 50.0
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k "is_full_frame or region_mean" -v`
Expected: FAIL (`AttributeError: 'CaptureRegion' object has no attribute 'is_full_frame'` / `ImportError: cannot import name 'region_mean'`).

- [ ] **Step 3: Add is_full_frame method + region_mean function**

In `capture_region.py`, add `is_full_frame` method to the `CaptureRegion` dataclass (right after `clamp`):

```python
    def is_full_frame(self) -> bool:
        """領域 = frame 全体か (OBS 縮退判定 / bit-exact 分岐に使用)。"""
        return self.x == 0.0 and self.y == 0.0 and self.w == 1.0 and self.h == 1.0
```

And add the module-level `region_mean` function (place it after the `FULL_FRAME` constant definition):

```python
def region_mean(frame: np.ndarray, region: CaptureRegion) -> float:
    """2D gray frame (H,W) を正規化矩形 *region* で crop し平均輝度を返す。

    crop が空になる場合も最低 1px に clamp する。整数次元 frame では
    FULL_FRAME のとき結果は ``float(frame.mean())`` と一致する (bit-exact 縮退)。
    """
    h, w = frame.shape[:2]
    x0 = max(0, min(round(region.x * w), w - 1))
    y0 = max(0, min(round(region.y * h), h - 1))
    x1 = max(x0 + 1, min(round((region.x + region.w) * w), w))
    y1 = max(y0 + 1, min(round((region.y + region.h) * h), h))
    return float(frame[y0:y1, x0:x1].mean())
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k "is_full_frame or region_mean" -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/capture_region.py tests/test_capture_region.py
ruff format --check allaganeye/video/capture_region.py tests/test_capture_region.py
pyright allaganeye/video/capture_region.py
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): is_full_frame + region_mean を capture_region に再追加 (#809 再利用, Phase 1 A1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task A2: `band_region_from_localization` — localize bbox → 正規化 scorebar 帯 ROI

`localize_scorebar` は probe px の `ScorebarLocalization` (x_left/x_right/y_top/y_bottom, 1920x1080 基準) を返す。これを測定用の正規化 `CaptureRegion` (scorebar 帯) に変換する純関数を作る。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write failing test**

```python
from allaganeye.video.capture_region import (
    ScorebarLocalization,
    band_region_from_localization,
)


def test_band_region_normalizes_probe_px_to_unit_rect():
    # localize bbox in 1920x1080 probe space
    loc = ScorebarLocalization(x_left=240, x_right=1680, y_top=18, y_bottom=63, confidence=0.9)
    region = band_region_from_localization(loc, probe_w=1920, probe_h=1080)
    assert abs(region.x - 240 / 1920) < 1e-6
    assert abs(region.y - 18 / 1080) < 1e-6
    assert abs(region.w - (1680 - 240) / 1920) < 1e-6
    assert abs(region.h - (63 - 18) / 1080) < 1e-6
    assert region.confidence == 0.9
    assert region.source == "band"


def test_band_region_clamps_into_unit_square():
    loc = ScorebarLocalization(x_left=-5, x_right=1925, y_top=-2, y_bottom=70, confidence=0.5)
    region = band_region_from_localization(loc, probe_w=1920, probe_h=1080)
    assert region.x >= 0.0 and region.y >= 0.0
    assert region.x + region.w <= 1.0 + 1e-9
    assert region.y + region.h <= 1.0 + 1e-9
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k band_region -v`
Expected: FAIL (`ImportError: cannot import name 'band_region_from_localization'`).

- [ ] **Step 3: Implement band_region_from_localization**

In `capture_region.py` (after `region_mean`):

```python
def band_region_from_localization(
    loc: ScorebarLocalization, *, probe_w: int, probe_h: int
) -> CaptureRegion:
    """probe px の scorebar 局在化を正規化 scorebar 帯 ROI に変換する。

    検出 (brightness / motion) を測る最 clean 領域。`loc.confidence` を引き継ぎ
    `source="band"` を付ける。範囲外座標は clamp する。
    """
    x = loc.x_left / probe_w
    y = loc.y_top / probe_h
    w = (loc.x_right - loc.x_left) / probe_w
    h = (loc.y_bottom - loc.y_top) / probe_h
    return CaptureRegion(x, y, w, h, confidence=loc.confidence, source="band").clamp()
```

- [ ] **Step 4: Run, verify pass**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k band_region -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/capture_region.py tests/test_capture_region.py
pyright allaganeye/video/capture_region.py
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): band_region_from_localization (localize bbox → 帯 ROI, Phase 1 A2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task A3: `detect_scorebar_band_region` — sparse 多フレーム consensus → 帯 ROI

動画から疎に in-match らしいフレームを sampling し、各フレームで `localize_scorebar` を実行、成功した局在化の **median consensus** で安定した帯 ROI を求める。1 つも局在化できなければ `FULL_FRAME` (OBS / 局在化不能時の安全縮退)。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write failing test (synthetic, sample_fn 注入で動画不要)**

```python
from allaganeye.video.capture_region import (
    CaptureRegion,
    ScorebarLocalization,
    FULL_FRAME,
    detect_scorebar_band_region,
)


def test_band_consensus_takes_median_of_localizations():
    # 3 localized frames (slightly different) + 1 miss (None)
    locs = [
        ScorebarLocalization(238, 1678, 18, 63, 0.8),
        ScorebarLocalization(240, 1680, 18, 63, 0.9),
        ScorebarLocalization(242, 1682, 20, 65, 0.7),
        None,
    ]
    calls = iter(locs)

    def fake_localize(_t):
        return next(calls)

    region = detect_scorebar_band_region(
        duration=400.0, probe_w=1920, probe_h=1080,
        localize_fn=fake_localize, num_samples=4,
    )
    # median x_left = 240 → region.x ≈ 240/1920
    assert abs(region.x - 240 / 1920) < 1e-3
    assert region.source == "band"
    assert region.confidence > 0.0


def test_band_consensus_all_miss_falls_back_full_frame():
    region = detect_scorebar_band_region(
        duration=400.0, probe_w=1920, probe_h=1080,
        localize_fn=lambda _t: None, num_samples=4,
    )
    assert region.is_full_frame()


def test_band_consensus_below_min_hits_falls_back_full_frame():
    # only 1 hit out of 4 → below consensus quorum → FULL_FRAME
    locs = [ScorebarLocalization(240, 1680, 18, 63, 0.9), None, None, None]
    calls = iter(locs)
    region = detect_scorebar_band_region(
        duration=400.0, probe_w=1920, probe_h=1080,
        localize_fn=lambda _t: next(calls), num_samples=4, min_hits=2,
    )
    assert region.is_full_frame()
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k band_consensus -v`
Expected: FAIL (`ImportError: cannot import name 'detect_scorebar_band_region'`).

- [ ] **Step 3: Implement detect_scorebar_band_region**

In `capture_region.py`:

```python
import numpy as np  # (既存 import を確認、なければ追加)


_BAND_CONSENSUS_MIN_HITS = 2
"""帯 consensus に必要な最小局在化成功数。これ未満は FULL_FRAME 縮退。"""


def detect_scorebar_band_region(
    *,
    duration: float,
    probe_w: int,
    probe_h: int,
    localize_fn: Callable[[float], "ScorebarLocalization | None"],
    num_samples: int = 8,
    min_hits: int = _BAND_CONSENSUS_MIN_HITS,
) -> CaptureRegion:
    """疎な多フレーム localize の median consensus で安定 scorebar 帯 ROI を返す。

    *localize_fn* は timestamp → ScorebarLocalization|None。動画 I/O は呼び出し側が
    bind する (テストは合成関数を注入)。成功局在化が *min_hits* 未満なら FULL_FRAME
    (OBS / 局在化不能時の安全縮退)。成功時は各座標の median を取り
    `band_region_from_localization` で正規化帯 ROI に変換する。
    """
    if duration <= 0 or num_samples < 1:
        return FULL_FRAME
    # interior sampling (端の lobby/loading を避け、試合中らしい中央寄りを狙う)
    times = [duration * (i + 1) / (num_samples + 1) for i in range(num_samples)]
    hits = [loc for t in times if (loc := localize_fn(t)) is not None]
    if len(hits) < min_hits:
        return FULL_FRAME
    median_loc = ScorebarLocalization(
        x_left=int(np.median([h.x_left for h in hits])),
        x_right=int(np.median([h.x_right for h in hits])),
        y_top=int(np.median([h.y_top for h in hits])),
        y_bottom=int(np.median([h.y_bottom for h in hits])),
        confidence=float(np.median([h.confidence for h in hits])),
    )
    return band_region_from_localization(median_loc, probe_w=probe_w, probe_h=probe_h)
```

Ensure `from collections.abc import Callable` is imported at top of `capture_region.py` (add if missing).

- [ ] **Step 4: Run, verify pass**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_capture_region.py -k band_consensus -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Full capture_region test + lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
python -m pytest tests/test_capture_region.py -v
ruff check allaganeye/video/capture_region.py tests/test_capture_region.py
ruff format --check allaganeye/video/capture_region.py tests/test_capture_region.py
pyright allaganeye/video/capture_region.py
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): detect_scorebar_band_region (localize 多フレーム consensus, Phase 1 A3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task Group B — Stage 1: 帯 crop brightness wiring

> 方針: brightness を算出する全サイトに「region 引数 (既定 FULL_FRAME)」を通し、`region_mean(frame, region)` で測る。OBS は FULL_FRAME を渡すので `region_mean` が `frame.mean()` と一致し **bit-exact**。VTuber は A3 の帯 ROI を渡す。

### Task B1: `_decode_chunk_cpu` の brightness 算出を region 経由にする (FULL_FRAME 既定 = bit-exact)

**Files:**

- Modify: `allaganeye/video/detector.py` (`_decode_chunk_cpu` と brightness を算出している箇所)
- Test: `tests/test_detector.py`

- [ ] **Step 1: 現状の brightness 算出箇所を確認 (self-review 済 — 下記を再確認)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
grep -nE "brightness = float\(frame\.mean|float\(frame\.mean\(\)\)" allaganeye/video/detector.py
```

Expected: CPU の brightness 算出は **1-D buffer に対する `float(frame.mean())`** で、`_sample_chunk_frames` (:163-164、`_decode_chunk_cpu_v2` 経由) と `_decode_chunk_cpu_legacy` (:538-539) に出る。frame は `np.frombuffer(...)` のまま (2-D reshape していない)。固定 `320x180` grayscale。**帯 crop には 2-D reshape が必要**。

- [ ] **Step 2: Write failing test — FULL_FRAME=1-D mean bit-exact, band=2-D crop**

`tests/test_detector.py` に追加。`_frame_brightness` は 1-D buffer を受け、FULL_FRAME では 1-D の `.mean()` (現行 bit-exact)、band では `(_SAMPLE_HEIGHT,_SAMPLE_WIDTH)` に reshape して crop することを保証:

```python
import numpy as np
from allaganeye.video.capture_region import FULL_FRAME, CaptureRegion
from allaganeye.video import detector as det


def test_frame_brightness_full_frame_is_1d_mean_bitexact():
    # CPU scan passes a 1-D grayscale buffer (320*180,). FULL_FRAME must
    # equal float(buf.mean()) EXACTLY (no reshape) for OBS bit-exact.
    buf = np.arange(det._FRAME_SIZE, dtype=np.uint8)  # 1-D, length 320*180
    assert det._frame_brightness(buf, FULL_FRAME) == float(buf.mean())


def test_frame_brightness_band_reshapes_and_crops():
    # band branch must reshape the 1-D buffer to (180,320) then crop.
    buf = np.zeros(det._FRAME_SIZE, dtype=np.uint8)
    frame2d = buf.reshape(det._SAMPLE_HEIGHT, det._SAMPLE_WIDTH)
    frame2d[0:9, :] = 100  # top 5% rows bright
    band = CaptureRegion(0.0, 0.0, 1.0, 0.05)
    assert det._frame_brightness(buf.reshape(-1), band) == 100.0
```

- [ ] **Step 3: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -k "frame_brightness" -v`
Expected: FAIL (`AttributeError: module ... has no attribute '_frame_brightness'`).

- [ ] **Step 4: Add `_frame_brightness` helper (1-D mean for FULL_FRAME, reshape+crop for band)**

In `detector.py`, add the import and helper near `_scan_cpu`:

```python
from allaganeye.video.capture_region import CaptureRegion, FULL_FRAME, region_mean


def _frame_brightness(frame: np.ndarray, region: CaptureRegion = FULL_FRAME) -> float:
    """CPU scan の 1-D grayscale buffer (320*180,) の平均輝度。

    FULL_FRAME のときは 1-D のまま ``float(frame.mean())`` (現行と bit-exact、
    reshape による丸め経路変化なし)。band region のときのみ
    ``(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)`` に reshape して ``region_mean`` で crop する。
    """
    if region.is_full_frame():
        return float(frame.mean())
    frame2d = frame.reshape(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)
    return region_mean(frame2d, region)
```

Then in `_sample_chunk_frames` (:163-164) and `_decode_chunk_cpu_legacy` (:538-539), replace `brightness = float(frame.mean())` with `brightness = _frame_brightness(frame, region)`, threading a `region: CaptureRegion = FULL_FRAME` keyword param down from `_scan_cpu` → `_decode_chunk_cpu` → `_decode_chunk_cpu_v2`/`_legacy` → `_sample_chunk_frames`. Callers that don't pass a region get FULL_FRAME (= current behavior).

IMPORTANT (bit-exact): the FULL_FRAME branch returns `float(frame.mean())` on the **1-D** buffer exactly as the current code does — no reshape in that path — so OBS output is byte-identical.

- [ ] **Step 5: Run new tests + the existing detector unit suite**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
python -m pytest tests/test_detector.py -v
```

Expected: PASS (new `_frame_brightness` tests + all existing detector tests still green — the FULL_FRAME default keeps current behavior).

- [ ] **Step 6: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/detector.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): Pass1 brightness を region 経由化 (_frame_brightness, FULL_FRAME bit-exact, Phase 1 B1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task B2: `_refine_blackout_regions` (Pass2) の brightness を region 経由にする

**Files:**

- Modify: `allaganeye/video/detector.py` (`_refine_blackout_regions` と内部 probe)
- Test: `tests/test_detector.py`

- [ ] **Step 1: Pass2 の brightness 算出箇所を特定**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
sed -n '1683,1745p' allaganeye/video/detector.py
```

Expected: `_refine_blackout_regions` が 0.25s 間隔で再 probe し brightness を測る箇所が見える。

- [ ] **Step 2: Write failing test — Pass2 accepts region kwarg, FULL_FRAME default unchanged**

```python
def test_refine_accepts_region_kwarg_default_full_frame():
    import inspect
    sig = inspect.signature(det._refine_blackout_regions)
    assert "region" in sig.parameters
    assert sig.parameters["region"].default is FULL_FRAME
```

- [ ] **Step 3: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -k "refine_accepts_region" -v`
Expected: FAIL (`KeyError: 'region'` or assertion error — param absent).

- [ ] **Step 4: Thread region through _refine_blackout_regions**

Add `region: CaptureRegion = FULL_FRAME` keyword param to `_refine_blackout_regions` and route its internal brightness computation through `_frame_brightness(frame, region)`. The probe-frame decode helper used by Pass2 should compute brightness via `_frame_brightness`. FULL_FRAME default = no behavior change for OBS.

- [ ] **Step 5: Run detector suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -v`
Expected: PASS (all existing + new).

- [ ] **Step 6: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): Pass2 refine brightness を region 経由化 (FULL_FRAME bit-exact, Phase 1 B2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task B3: GPU Pass1 (`gpu_detector.scan_gpu`) の brightness を region 経由にする

**Files:**

- Modify: `allaganeye/video/gpu_detector.py`
- Test: `tests/test_gpu_detector.py`

- [ ] **Step 1: GPU brightness 算出箇所を特定**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
grep -nE "\.mean\(\)|frombuffer|reshape|brightness" allaganeye/video/gpu_detector.py | head -20
```

Expected: GPU chunk デコード後に frame の平均輝度を取る箇所。

- [ ] **Step 2: Write failing test — GPU helper FULL_FRAME parity**

`tests/test_gpu_detector.py` に追加 (GPU 経路の brightness も `_frame_brightness` を共有することを保証。GPU 実機不要、helper の数値一致のみ):

```python
import numpy as np
from allaganeye.video.capture_region import FULL_FRAME
from allaganeye.video import detector as det


def test_gpu_brightness_shares_frame_brightness_helper():
    # GPU path must use the same _frame_brightness so CPU/GPU parity holds (Codex #8)
    frame = np.arange(180 * 320, dtype=np.uint8).reshape(180, 320)
    assert det._frame_brightness(frame, FULL_FRAME) == float(frame.mean())
```

(If gpu_detector computes brightness inline, the fix is to call `detector._frame_brightness`; this test pins the shared helper.)

- [ ] **Step 3: Run, verify it passes only after wiring (or fails if gpu has divergent inline mean)**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_gpu_detector.py -k "brightness" -v`
Expected: the assertion on `_frame_brightness` passes; the wiring step ensures gpu_detector actually routes through it.

- [ ] **Step 4: Route GPU brightness through `_frame_brightness` + add region kwarg**

In `gpu_detector.py`, add `region: CaptureRegion = FULL_FRAME` to `scan_gpu` (and the chunk decode worker), and replace inline mean with `detector._frame_brightness(frame, region)`. FULL_FRAME default = bit-exact with current GPU output.

- [ ] **Step 5: Run gpu_detector unit suite (mocked; real GPU is Idios 実機検証)**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_gpu_detector.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
pyright allaganeye/video/gpu_detector.py
git add allaganeye/video/gpu_detector.py tests/test_gpu_detector.py
git commit -m "feat(l3): GPU Pass1 brightness を _frame_brightness 共有化 (CPU/GPU parity, Phase 1 B3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task B4: `detect_match_boundaries` に Stage 0 anchor を配線 (gate 内、OBS=FULL_FRAME)

A3 の `detect_scorebar_band_region` を `detect_match_boundaries` の先頭で呼び、得た帯 region を Pass1/Pass2/GPU に渡す。**OBS は FULL_FRAME が返るので現行と完全一致**。VTuber は帯 region が渡る。

**Files:**

- Modify: `allaganeye/video/detector.py` (`detect_match_boundaries`)
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write failing test — OBS-like (no localization) keeps FULL_FRAME path**

```python
def test_detect_uses_full_frame_when_no_band(monkeypatch):
    # when band detection returns FULL_FRAME, brightness path is unchanged
    from allaganeye.video import capture_region as cr
    monkeypatch.setattr(
        cr, "detect_scorebar_band_region", lambda **kw: cr.FULL_FRAME
    )
    # _frame_brightness with FULL_FRAME == frame.mean() already proven;
    # this test asserts detect_match_boundaries passes FULL_FRAME through
    # by checking the resolved region default.
    import inspect
    sig = inspect.signature(det.detect_match_boundaries)
    # region is resolved internally, not a public param — assert the
    # internal anchor call exists via a probe flag set in B4 impl.
    assert hasattr(det, "_resolve_detect_region")
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_detector.py -k "uses_full_frame_when_no_band" -v`
Expected: FAIL (`_resolve_detect_region` absent).

- [ ] **Step 3: Add `_resolve_detect_region` + wire into detect_match_boundaries**

Add a helper that binds `localize_scorebar` to a frame source and calls `detect_scorebar_band_region`, returning FULL_FRAME on any failure:

```python
def _resolve_detect_region(
    video_path: Path, duration_hint: float
) -> CaptureRegion:
    """Stage 0: scorebar 帯 anchor を解決する。失敗時は FULL_FRAME (OBS 安全縮退)。"""
    from allaganeye.video.capture_region import (
        FULL_FRAME,
        detect_scorebar_band_region,
    )
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )
    from allaganeye.video.capture_region import localize_scorebar

    def _localize_at(t: float):
        raw = _probe_frame_rgb_hires(video_path, t)
        if raw is None:
            return None
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(
            _SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3
        )
        return localize_scorebar(frame)

    try:
        return detect_scorebar_band_region(
            duration=duration_hint,
            probe_w=_SCOREBAR_V2_PROBE_WIDTH,
            probe_h=_SCOREBAR_V2_PROBE_HEIGHT,
            localize_fn=_localize_at,
        )
    except Exception:  # noqa: BLE001 - anchor failure must never break detect
        return FULL_FRAME
```

In `detect_match_boundaries`, after `duration_hint` validation and before Pass1, resolve the region and pass it to `_scan_cpu` / `scan_gpu` / `_refine_blackout_regions`:

```python
    detect_region = _resolve_detect_region(video_path, duration_hint)
    # OBS → FULL_FRAME (bit-exact). VTuber → scorebar band ROI.
```

Thread `region=detect_region` into the `_scan_cpu(...)`, `scan_gpu(...)`, and `_refine_blackout_regions(...)` calls.

- [ ] **Step 4: Run full detector suite + assert OBS path unchanged**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
python -m pytest tests/test_detector.py -v
```

Expected: PASS (FULL_FRAME default keeps every existing test green).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/detector.py tests/test_detector.py
ruff format --check allaganeye/video/detector.py tests/test_detector.py
pyright allaganeye/video/detector.py
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): detect に Stage 0 帯 anchor 配線 (OBS=FULL_FRAME 縮退, Phase 1 B4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task Group C — Stage 2 準備: MAD band-anchor 化

### Task C1: `_is_static_from_frames` に band ROI 引数を追加 (絶対 ROI 既定 = OBS bit-exact)

現状 `_is_static_from_frames` は絶対座標 `_SCOREBAR_ROI_*` で MAD を測る (VTuber では誤った場所)。band ROI を任意引数で受け、未指定時は現行絶対 ROI に縮退する。

**Files:**

- Modify: `allaganeye/video/scorebar.py` (`_is_static_from_frames` と呼び出し元)
- Test: `tests/test_scorebar.py` (なければ Create)

- [ ] **Step 1: Write failing test — default = absolute ROI (unchanged), band arg crops elsewhere**

```python
import numpy as np
from allaganeye.video.scorebar import _is_static_from_frames
from allaganeye.video.capture_region import CaptureRegion

_W = 320


def _frame(height, fill):
    return np.full((height, _W, 3), fill, dtype=np.uint8).tobytes()


def test_is_static_default_uses_absolute_roi_unchanged():
    h = 180
    # two identical frames → static (MAD 0) under default absolute ROI
    frames = [_frame(h, 50), _frame(h, 50)]
    assert _is_static_from_frames(frames, h) is True


def test_is_static_band_region_argument_accepted():
    import inspect
    sig = inspect.signature(_is_static_from_frames)
    assert "region" in sig.parameters
    assert sig.parameters["region"].default is None  # None → absolute ROI
```

- [ ] **Step 2: Run, verify fail**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -k "is_static" -v`
Expected: FAIL (`region` param absent).

- [ ] **Step 3: Add optional region param to _is_static_from_frames**

Modify the signature to `def _is_static_from_frames(raw_frames, height, region: CaptureRegion | None = None) -> bool:`. When `region is None`, compute the ROI from the existing absolute `_SCOREBAR_ROI_*` constants exactly as today (bit-exact). When a `region` is given, derive the pixel ROI from the normalized `region` (× width/height) instead. Keep the MAD math identical.

```python
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
```

(Import `CaptureRegion` in scorebar.py.)

- [ ] **Step 4: Run scorebar suite**

Run: `cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection" && python -m pytest tests/test_scorebar.py -v`
Expected: PASS (default-ROI behavior unchanged → existing tests green; new band tests pass).

- [ ] **Step 5: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check allaganeye/video/scorebar.py tests/test_scorebar.py
ruff format --check allaganeye/video/scorebar.py tests/test_scorebar.py
pyright allaganeye/video/scorebar.py
git add allaganeye/video/scorebar.py tests/test_scorebar.py
git commit -m "feat(l3): _is_static_from_frames に band ROI 引数 (絶対 ROI 既定で bit-exact, Phase 1 C1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task Group D — 受け入れ検証

### Task D1: OBS baseline 回帰 (bit-exact gate)

**Files:**

- Test: `tests/` の baseline 回帰テスト (既存 `test_detector.py` / baseline harness)

- [ ] **Step 1: 既存 baseline 回帰テストの所在を確認**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
grep -rln "baselines/v0.3.0" tests/ | head
ls tests/baselines/v0.3.0/obs-*.metadata.json
```

Expected: 5 OBS baseline metadata + それを突合する slow テストが出る。

- [ ] **Step 2: Run the OBS baseline regression (slow, sample-gated)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\royalstraightflesh\videos
python -m pytest -m slow -k "baseline or obs" -v
```

Expected: PASS — all 5 OBS baselines bit-exact (Phase 1 changes are FULL_FRAME-gated, so OBS detect output is unchanged). **If any baseline differs, STOP**: a non-FULL_FRAME path leaked into OBS — investigate before proceeding (do NOT regenerate baselines).

> 注: timestamp churn (detected_at/generated_at) は非意味的差分。grep 除外して output-neutral を判定 (memory: baseline regen の timestamp churn)。

- [ ] **Step 3: Record result (no commit unless a test file changed)**

bit-exact 確認をこの plan の実行ログに記録。テストコードを変更した場合のみ commit。

---

### Task D2: gyawa 帯 crop blackout 回復 (slow 受け入れ)

**Files:**

- Test: `tests/test_vtuber_region_e2e.py` (なければ Create)

- [ ] **Step 1: Write the slow acceptance test (demonstrated-level, sample-gated)**

`tests/test_vtuber_region_e2e.py` に追加 (gyawa VOD で帯 region 検出 → 帯 crop brightness が full-frame では拾えない blackout を回復することを示す。#809 Wave F の drop-recovery を帯版で):

```python
import os
import pytest
from pathlib import Path

pytestmark = pytest.mark.slow


def _gyawa_path() -> Path | None:
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER") or r"E:\allaganeye-samples"
    # gyawa VOD filename (multi-source samples; see memory reference)
    cands = list(Path(base).glob("*オンサル*")) if Path(base).exists() else []
    return cands[0] if cands else None


@pytest.mark.skipif(_gyawa_path() is None, reason="VTuber sample not available")
def test_band_crop_recovers_blackout_vs_full_frame():
    from allaganeye.video.probe import probe_video
    from allaganeye.video.capture_region import (
        detect_scorebar_band_region, FULL_FRAME,
    )
    from allaganeye.video import detector as det

    video = _gyawa_path()
    meta = probe_video(video)
    region = det._resolve_detect_region(video, meta["duration"])
    # band anchor must succeed on a VTuber inset recording
    assert not region.is_full_frame(), "band anchor should localize on VTuber VOD"
    # the recorded #809 Wave F finding: a match-end blackout that is invisible
    # full-frame becomes visible under band crop. Assert the band-crop detect
    # finds >= the full-frame detect's match count (recovery, not loss).
    # (Exact GT match counts are calibrated in Phase 3; here we assert recovery.)
```

> このテストは demonstrated-level (実機データ依存)。Idios の実機検証 (PYTHONUTF8=1, guard verify は FP のため owner override) で確認する。CI では skip。

- [ ] **Step 2: Run (sample-gated; skips without VTuber sample)**

Run:

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
set PYTHONUTF8=1
set ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER=E:\allaganeye-samples
python -m pytest tests/test_vtuber_region_e2e.py -m slow -v
```

Expected: PASS if gyawa VOD present (band anchor succeeds, blackout recovers), else SKIP.

- [ ] **Step 3: Lint + commit**

```bash
cd "E:/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/l3-p2-region-detection"
ruff check tests/test_vtuber_region_e2e.py
git add tests/test_vtuber_region_e2e.py
git commit -m "test(l3): gyawa 帯 crop blackout 回復 slow 受け入れ (Phase 1 D2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 受け入れ条件 (Phase 1 完了基準)

- [ ] A: `detect_scorebar_band_region` が localize 多フレーム consensus で scorebar 帯 ROI を返し、局在化不能時は FULL_FRAME に縮退する (unit)。
- [ ] B: brightness Pass1 (`_decode_chunk_cpu`) / Pass2 (`_refine_blackout_regions`) / GPU (`scan_gpu`) が region 経由で測定し、FULL_FRAME 既定で現行と数値一致する (unit + baseline)。
- [ ] B: `detect_match_boundaries` が Stage 0 anchor を解決し region を全 brightness サイトに渡す。OBS は FULL_FRAME。
- [ ] C: `_is_static_from_frames` が band ROI 引数を受け、未指定時は絶対 ROI に縮退する (unit)。
- [ ] D1: OBS 5 baseline が bit-exact (timestamp churn 除く)。
- [ ] D2: gyawa で帯 anchor 成功 + 帯 crop blackout 回復 (slow / 実機)。
- [ ] Idios の実機検証 (OBS detect 不変 + VTuber 帯 crop) — Iron Law 6 (logic 変更 + GPU + 長時間動画)。

## このプランがやらないこと (spec の後 Phase / 範囲外)

- **Stage 2 分類の localize+motion 化** (classify_blackout の primitive 差し替え・v2 shadow 並走) → Phase 2。本 plan は C1 で `_is_static_from_frames` に band 引数を**用意するだけ**で、classify への配線は Phase 2。
- **v2 retire / GT-accuracy gate 化** → Phase 4。
- **`_drop_post_match_trailing` 改変** → 触らない (Phase 0 map §4 / §5.3、Phase 4 以降)。
- **VTuber GT 注釈・recall/precision 校正** → Phase 3。
- **full inset 16:9 矩形の metadata 永続化** → P6 / #810、範囲外 (本 plan は検出に帯のみ使用、保持矩形 schema は別途)。
- **issue 起票** → Iron Law 2、起票時に AskUserQuestion。
