# P1: robust scorebar 局在化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 任意の 1920x1080 単フレームから FL scorebar を位置独立 (game inset の x/y 位置・HUD スケール非依存) に局在化し span/位置/confidence を返す純粋関数 `localize_scorebar` を追加する (re-plan #753 の P1)。

**Architecture:** Additive (D1)。新規 `localize_scorebar` + helper を `allaganeye/video/capture_region.py` に追加し、wired・OBS 検証済の `detector.py` primitive (`_has_scorebar_v2` / `_find_scorebar_horizontal_range` / `_emblem_and_check`) は一切変更しない。アルゴリズムは方式1 (all-y band scan × width-gated 全 run × emblem 3点 AND gate、#803 center-straddling を撤廃)。unwired な S2 (`detect_region_scorebar_band`) は本 PR で退役。

**Tech Stack:** Python 3 / numpy / opencv-python-headless (cv2) / pytest。TDD hard-gate (Red→Green→Refactor)。

**Spec:** [2026-05-29-p1-robust-scorebar-localization-design.md](../specs/2026-05-29-p1-robust-scorebar-localization-design.md)

**作業 worktree/branch:** `claude/l3-vtuber-replan` (`.claude/worktrees/l3-vtuber-replan`)

**実装方針メモ (spec §5.2/§5.3 の案 A/案 B 決定):** 本計画は **案 A (zero-touch)** を採る。P1 は自前の `_scorebar_saturated_runs` / `_emblem_and_margin` を持ち、`detector.py` の wired 関数を編集しない。emblem sat/edge 計算は `_emblem_and_check` と意図的に同一ロジックを複製し、Task 7 の OBS parity test が drift を検出する。案 B (共有 extract) は P1 land 後の任意 cleanup とする。

---

## File Structure

| ファイル | 変更 | 責務 |
| --- | --- | --- |
| `allaganeye/video/capture_region.py` | Modify | `ScorebarLocalization` dataclass + `localize_scorebar` + `_scorebar_saturated_runs` + `_emblem_and_margin` + `_LOCALIZE_TARGET_RATIO` を追加。`detect_region_scorebar_band` (S2) を削除 |
| `tests/test_capture_region.py` | Modify | localize 系テストを追加。S2 (`detect_region_scorebar_band`) のテスト・import を削除 |

`detector.py` / `scorebar.py` は **変更しない** (D1)。

---

## Task 1: `ScorebarLocalization` dataclass + 定数

**Files:**

- Modify: `allaganeye/video/capture_region.py` (CaptureRegion dataclass の直後、`FULL_FRAME` 定義の前あたり)
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the failing test**

`tests/test_capture_region.py` の import 行を更新し (まだ `detect_region_scorebar_band` は残す。削除は Task 6)、`ScorebarLocalization` を import に追加:

```python
from allaganeye.video.capture_region import (
    FULL_FRAME,
    CaptureRegion,
    RegionTimeline,
    ScorebarLocalization,
    _maybe_snap_full_frame,
    detect_region_blackout_overlap,
    detect_region_scorebar_band,
    detect_region_variance,
    iou,
    top_edge_error_px,
)
```

ファイル末尾に追加:

```python
# ---------------------------------------------------------------------------
# P1: localize_scorebar (re-plan #753)
# ---------------------------------------------------------------------------


def test_scorebar_localization_is_frozen_with_fields():
    loc = ScorebarLocalization(
        x_left=100, x_right=700, y_top=300, y_bottom=345, confidence=0.9
    )
    assert (loc.x_left, loc.x_right, loc.y_top, loc.y_bottom) == (100, 700, 300, 345)
    assert loc.confidence == 0.9
    import dataclasses

    with __import__("pytest").raises(dataclasses.FrozenInstanceError):
        loc.x_left = 0  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_capture_region.py::test_scorebar_localization_is_frozen_with_fields -v`
Expected: FAIL — `ImportError: cannot import name 'ScorebarLocalization'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/video/capture_region.py` の `CaptureRegion` クラス定義の直後 (`FULL_FRAME = ...` の前) に追加:

```python
@dataclass(frozen=True)
class ScorebarLocalization:
    """FL scorebar 帯を 1920x1080 probe frame 内で局在化した結果 (P1, re-plan #753).

    座標はすべて probe px (inclusive)。consumer (P2) が /1920,/1080 で正規化する。
    """

    x_left: int
    x_right: int
    y_top: int
    y_bottom: int
    confidence: float
```

同ファイルの定数群 (`_BAND_Y_MAX_FRAC` 付近) に追加:

```python
_LOCALIZE_TARGET_RATIO = 2.0
"""confidence が 1.0 に達する emblem margin 倍率 (最弱 emblem の sat/edge が
閾値の TARGET 倍で満点)。clear な in-match frame で ~1.0 に出るよう選定。"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_capture_region.py::test_scorebar_localization_is_frozen_with_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): add ScorebarLocalization dataclass (P1, re-plan #753)"
```

---

## Task 2: `_scorebar_saturated_runs` (width-gated 全 run、center 前提なし)

`_find_scorebar_horizontal_range` の (a)〜(c) ロジックを複製し、(d) center-straddling 選択を撤廃して **width-gate を通過した全 run** を返す。これが #803 center 前提の撤廃点。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_capture_region.py` の import に `_scorebar_saturated_runs` を追加 (capture_region から):

```python
from allaganeye.video.capture_region import (
    FULL_FRAME,
    CaptureRegion,
    RegionTimeline,
    ScorebarLocalization,
    _maybe_snap_full_frame,
    _scorebar_saturated_runs,
    detect_region_blackout_overlap,
    detect_region_scorebar_band,
    detect_region_variance,
    iou,
    top_edge_error_px,
)
```

ファイル末尾に追加:

```python
def _sat_band(width_runs, h=45, w=1920):
    """指定 (x_left, x_right) 範囲を saturated blue で塗った band (h,w,3) を返す。"""
    band = np.full((h, w, 3), 40, dtype=np.uint8)
    for x_left, x_right in width_runs:
        band[:, x_left : x_right + 1] = (50, 50, 200)
    return band


def test_saturated_runs_finds_centered_run():
    import cv2

    band = _sat_band([(500, 1400)])
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    x_left, x_right = runs[0]
    assert abs(x_left - 500) <= 2 and abs(x_right - 1400) <= 2


def test_saturated_runs_finds_off_center_run():
    # 中心 (x=960) をまたがない左寄り帯。_find_scorebar_horizontal_range は
    # center-straddling で None を返すが、P1 はこれを拾えねばならない (#803 撤廃)。
    import cv2

    band = _sat_band([(100, 700)])
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    x_left, x_right = runs[0]
    assert abs(x_left - 100) <= 2 and abs(x_right - 700) <= 2


def test_saturated_runs_drops_narrow_and_overwide():
    import cv2

    # narrow (<500px) と overwide (>1440px) はどちらも width gate で除外。
    band = _sat_band([(0, 300), (700, 1300)])  # 301px run, 601px run
    runs = _scorebar_saturated_runs(band, cv2)
    assert len(runs) == 1
    assert abs(runs[0][0] - 700) <= 2 and abs(runs[0][1] - 1300) <= 2

    overwide = _sat_band([(100, 1800)])  # 1701px
    assert _scorebar_saturated_runs(overwide, cv2) == []


def test_saturated_runs_blank_returns_empty():
    import cv2

    band = np.full((45, 1920, 3), 40, dtype=np.uint8)
    assert _scorebar_saturated_runs(band, cv2) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_capture_region.py -k saturated_runs -v`
Expected: FAIL — `ImportError: cannot import name '_scorebar_saturated_runs'`

- [ ] **Step 3: Write implementation**

`allaganeye/video/capture_region.py` の `detect_region_scorebar_band` の **直前** に追加:

```python
def _scorebar_saturated_runs(band: np.ndarray, cv2) -> list[tuple[int, int]]:
    """band (Hb,W,3 uint8 RGB) の saturated column run を width-gate して全件返す。

    `detector._find_scorebar_horizontal_range` の per-pixel mask + col-ratio +
    gap-merge を共有しつつ、center-straddling 選択 (#803) を撤廃する。返す run は
    `_SCOREBAR_SCAN_MIN_WIDTH_PX`..`_SCOREBAR_SCAN_MAX_WIDTH_PX` の幅のもののみ。
    """
    from allaganeye.video.detector import (
        _SCOREBAR_SCAN_COL_RATIO,
        _SCOREBAR_SCAN_MAX_GAP_PX,
        _SCOREBAR_SCAN_MAX_WIDTH_PX,
        _SCOREBAR_SCAN_MIN_WIDTH_PX,
        _SCOREBAR_SCAN_SAT_THRESHOLD,
        _SCOREBAR_SCAN_VAL_THRESHOLD,
    )

    bgr = cv2.cvtColor(band, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    pixel_mask = (sat > _SCOREBAR_SCAN_SAT_THRESHOLD) & (
        val > _SCOREBAR_SCAN_VAL_THRESHOLD
    )
    col_saturated = pixel_mask.mean(axis=0) >= _SCOREBAR_SCAN_COL_RATIO

    width = band.shape[1]
    raw_runs: list[tuple[int, int]] = []
    i = 0
    while i < width:
        if col_saturated[i]:
            j = i
            while j < width and col_saturated[j]:
                j += 1
            raw_runs.append((i, j - 1))
            i = j
        else:
            i += 1

    if not raw_runs:
        return []

    merged: list[tuple[int, int]] = [raw_runs[0]]
    for start, end in raw_runs[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end - 1 <= _SCOREBAR_SCAN_MAX_GAP_PX:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    runs: list[tuple[int, int]] = []
    for start, end in merged:
        span_width = end - start + 1
        if _SCOREBAR_SCAN_MIN_WIDTH_PX <= span_width <= _SCOREBAR_SCAN_MAX_WIDTH_PX:
            runs.append((start, end))
    return runs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_capture_region.py -k saturated_runs -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): add _scorebar_saturated_runs (all width-gated runs, no center gate)"
```

---

## Task 3: `_emblem_and_margin` (3点 AND の margin 版)

`_emblem_and_check` と **同一の sat/edge 計算** を行い、3点すべて通過なら最弱 margin (min ratio、>1.0)、1点でも不通過なら `None` を返す。OBS parity は Task 7 で担保。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the failing tests**

import に `_emblem_and_margin` を追加し、ファイル末尾に追加:

```python
def _frame_with_emblem_box(fill, x1=600, y1=2, x2=665, y2=40):
    """1920x1080 frame の 1 box を指定 fill で塗る。stripe=高 sat/edge を作る用。"""
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    region = f[y1:y2, x1:x2]
    if fill == "stripe":
        for col in range(region.shape[1]):
            region[:, col] = (200, 30, 30) if (col // 2) % 2 == 0 else (0, 0, 0)
    else:
        region[:] = fill
    return f, [("e", x1, y1, x2, y2)]


def test_emblem_and_margin_strong_emblem_returns_ratio_above_one():
    import cv2

    f, positions = _frame_with_emblem_box("stripe")
    margin = _emblem_and_margin(f, positions, cv2)
    assert margin is not None and margin > 1.0


def test_emblem_and_margin_flat_region_returns_none():
    import cv2

    # 単色 (低 edge) は edge 閾値を割るので None。
    f, positions = _frame_with_emblem_box((50, 50, 200))
    assert _emblem_and_margin(f, positions, cv2) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_capture_region.py -k emblem_and_margin -v`
Expected: FAIL — `ImportError: cannot import name '_emblem_and_margin'`

- [ ] **Step 3: Write implementation**

`_scorebar_saturated_runs` の直後に追加:

```python
def _emblem_and_margin(
    frame: np.ndarray,
    positions: list[tuple[str, int, int, int, int]],
    cv2,
) -> float | None:
    """3点 emblem AND。全通過なら最弱 margin (min ratio>1.0)、不通過なら None。

    `detector._emblem_and_check` と同一の sat (bright pixel) / Sobel edge 計算を
    用いる (OBS parity は plan Task 7 で担保)。各 position は (name,x1,y1,x2,y2)。
    """
    from allaganeye.video.detector import (
        _EMBLEM_EDGE_THRESHOLD,
        _EMBLEM_SAT_THRESHOLD,
    )

    min_ratio: float | None = None
    for _name, x1, y1, x2, y2 in positions:
        region = frame[y1:y2, x1:x2, :]
        if region.size == 0:
            return None
        bgr = cv2.cvtColor(region, cv2.COLOR_RGB2BGR)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

        val = hsv[:, :, 2].astype(np.float32)
        sat = hsv[:, :, 1].astype(np.float32)
        bright_mask = val > 30
        if bright_mask.sum() > 5:
            mean_sat = float(sat[bright_mask].mean())
        else:
            mean_sat = 0.0

        sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        edge_density = float(np.sqrt(sobel_x**2 + sobel_y**2).mean())

        if mean_sat <= _EMBLEM_SAT_THRESHOLD or edge_density <= _EMBLEM_EDGE_THRESHOLD:
            return None
        ratio = min(
            mean_sat / _EMBLEM_SAT_THRESHOLD,
            edge_density / _EMBLEM_EDGE_THRESHOLD,
        )
        min_ratio = ratio if min_ratio is None else min(min_ratio, ratio)
    return min_ratio
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_capture_region.py -k emblem_and_margin -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): add _emblem_and_margin (margin variant of emblem 3-point AND)"
```

---

## Task 4: `localize_scorebar` (all-y × all-run scan)

方式1 本体。位置独立 (off-center 復元) を駆動テストにする。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the failing tests**

import に `localize_scorebar` を追加し、ファイル末尾に追加 (`_hires_with_scorebar_at` は既存の S2 テスト helper を再利用):

```python
def test_localize_centered_in_match_returns_localization():
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    loc = localize_scorebar(f)
    assert loc is not None
    assert abs(loc.x_left - 500) <= 4 and abs(loc.x_right - 1400) <= 4
    assert abs(loc.y_top - 120) <= 6  # stride 既定 6
    assert loc.y_bottom == loc.y_top + 45
    assert 0.0 < loc.confidence <= 1.0


def test_localize_off_center_inset_position_independent():
    # 中心 (x=960) をまたがない左寄り inset。退役した S2 (_find_scorebar_horizontal_range
    # center-straddling) では検出不能だった位置独立ケース (P1 の存在意義)。
    f = _hires_with_scorebar_at(y_top=300, x_left=100, x_right=700)
    loc = localize_scorebar(f)
    assert loc is not None
    assert abs(loc.x_left - 100) <= 4 and abs(loc.x_right - 700) <= 4
    assert abs(loc.y_top - 300) <= 6


def test_localize_blank_frame_returns_none():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    f = np.full(
        (_SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3), 40, dtype=np.uint8
    )
    assert localize_scorebar(f) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_capture_region.py -k localize -v`
Expected: FAIL — `ImportError: cannot import name 'localize_scorebar'`

- [ ] **Step 3: Write implementation**

`_emblem_and_margin` の直後に追加:

```python
def localize_scorebar(
    frame: np.ndarray,
    *,
    stride: int = _BAND_SCAN_STRIDE,
    target_ratio: float = _LOCALIZE_TARGET_RATIO,
) -> ScorebarLocalization | None:
    """1920x1080 RGB frame から FL scorebar を位置独立に局在化する (P1, #753).

    y を stride 全走査し、各 band で width-gated 全 run に emblem 3点 AND をかけ、
    通過候補のうち emblem margin が最大の (run, y) を返す (best-hit)。best-hit に
    より y_top 精度が ±stride/2 に上がり confidence が最良整合の margin になる。
    試合外 / cv2 不在 / 形状不一致は None。OBS 分類 path からは呼ばれない
    (Additive、§7)。
    """
    try:
        import cv2
    except ImportError:
        return None

    from allaganeye.video.detector import (
        _EMBLEM_RELATIVE_POSITIONS,
        _SCOREBAR_SCAN_Y_END,
        _SCOREBAR_SCAN_Y_START,
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W = _SCOREBAR_V2_PROBE_WIDTH
    H = _SCOREBAR_V2_PROBE_HEIGHT
    if frame.shape[:2] != (H, W):
        return None

    band_h = _SCOREBAR_SCAN_Y_END - _SCOREBAR_SCAN_Y_START
    y_max = int(H * _BAND_Y_MAX_FRAC)
    best: tuple[float, int, int, int] | None = None  # (margin, x_left, x_right, y)
    for y in range(0, y_max, stride):
        band = frame[y : y + band_h]
        for x_left, x_right in _scorebar_saturated_runs(band, cv2):
            bar_w = x_right - x_left
            positions: list[tuple[str, int, int, int, int]] = []
            valid = True
            for name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS:
                px1 = int(x_left + cx_rel * bar_w - hw_rel * bar_w)
                px2 = int(x_left + cx_rel * bar_w + hw_rel * bar_w)
                py1 = y + ey1
                py2 = y + ey2
                if px1 < 0 or px2 > W or py1 < 0 or py2 > H or px2 <= px1:
                    valid = False
                    break
                positions.append((name, px1, py1, px2, py2))
            if not valid:
                continue
            margin = _emblem_and_margin(frame, positions, cv2)
            if margin is not None and (best is None or margin > best[0]):
                best = (margin, x_left, x_right, y)

    if best is None:
        return None
    margin, x_left, x_right, y = best
    confidence = max(0.0, min(1.0, (margin - 1.0) / (target_ratio - 1.0)))
    return ScorebarLocalization(
        x_left=x_left,
        x_right=x_right,
        y_top=y,
        y_bottom=y + band_h,
        confidence=confidence,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_capture_region.py -k localize -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): add localize_scorebar all-y x all-run scan (P1, re-plan #753)"
```

---

## Task 5: localize_scorebar robustness / negative / 異常系 coverage

§8.1 scale / §8.2 negative / §8.5 異常系 を網羅する。Task 4 の実装で全 pass するはず。fail したら実装を修正する (bounds guard / width gate)。

**Files:**

- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the tests**

ファイル末尾に追加:

```python
def test_localize_scale_variation_recovers_span():
    # HUD スケール差を span 幅で模擬。narrow と wide の両方で復元できること。
    for x_left, x_right in [(700, 1220), (300, 1620)]:
        f = _hires_with_scorebar_at(y_top=60, x_left=x_left, x_right=x_right)
        loc = localize_scorebar(f)
        assert loc is not None, (x_left, x_right)
        assert abs(loc.x_left - x_left) <= 4 and abs(loc.x_right - x_right) <= 4


def test_localize_off_center_band_without_emblems_returns_none():
    # 中心をまたがない右寄りの単色帯 (emblem なし)。all-run 化しても emblem-AND
    # が落とすので None。#803 (post-match 広帯) 防御が center 前提なしで成立する確証。
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:45, 1400:1919] = (50, 50, 200)  # 519px 右寄り帯、紋章なし
    assert localize_scorebar(f) is None


def test_localize_overwide_band_returns_none():
    f = _hires_with_scorebar_at(y_top=2, x_left=120, x_right=1810)
    assert localize_scorebar(f) is None


def test_localize_uniform_cyan_banner_returns_none():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:55, :] = (60, 200, 200)  # 全幅単色 cyan (>max width かつ紋章なし)
    assert localize_scorebar(f) is None


def test_localize_wrong_shape_returns_none():
    f = np.full((100, 100, 3), 40, dtype=np.uint8)
    assert localize_scorebar(f) is None


def test_localize_returns_none_without_cv2(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("simulated missing cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    assert localize_scorebar(f) is None
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_capture_region.py -k localize -v`
Expected: PASS (全 localize テストが pass)。fail した場合は `localize_scorebar` の bounds guard / width gate を見直して修正し、再実行。

- [ ] **Step 3: Commit**

```bash
git add tests/test_capture_region.py
git commit -m "test(l3): localize_scorebar scale/negative/error coverage (#803 guard, cv2-absent)"
```

---

## Task 6: S2 (`detect_region_scorebar_band`) 退役

unwired・superseded な S2 を削除し、そのテストを除去する (D3)。`localize_scorebar` が後継。

**Files:**

- Modify: `allaganeye/video/capture_region.py` (関数削除)
- Modify: `tests/test_capture_region.py` (import + 3 テスト削除)

- [ ] **Step 1: 参照が production に無いことを確認**

Run: `git grep -n "detect_region_scorebar_band" -- allaganeye`
Expected: `allaganeye/video/capture_region.py` の定義行のみ (他の production 参照なし)。もし他に参照があれば STOP して原因調査 (本計画の前提が崩れる)。

- [ ] **Step 2: S2 関数を削除**

`allaganeye/video/capture_region.py` から `def detect_region_scorebar_band(...)` 関数全体 (docstring 含む、`return None` まで) を削除する。`_BAND_SCAN_STRIDE` / `_BAND_Y_MAX_FRAC` は `localize_scorebar` で使うため **残す**。`_GAME_ASPECT` は S2 削除後 dead になる (使用箇所が S2 のみ) ため本 Task で **併せて削除** する (P2 で game rect 逆算時に `16/9` を再導入、spec §10)。

- [ ] **Step 3: S2 テストと import を削除**

`tests/test_capture_region.py` から:

- import 文の `detect_region_scorebar_band,` 行を削除
- 以下 3 テストを削除: `test_scorebar_band_at_offset_y_returns_inset_top` / `test_scorebar_band_overwide_returns_none` / `test_scorebar_band_uniform_cyan_banner_rejected`

`_hires_with_scorebar_at` helper は localize テストが使うため **残す**。

- [ ] **Step 4: 全テスト + 参照確認**

Run: `pytest tests/test_capture_region.py -v`
Expected: PASS (S2 テストが消え、localize テスト群が残って全 pass)

Run: `git grep -n "detect_region_scorebar_band"`
Expected: 出力なし (定義・テスト・import すべて消えた)

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "refactor(l3): retire unwired S2 detect_region_scorebar_band (superseded by localize_scorebar)"
```

---

## Task 7: OBS parity test (F4-b、案 A の drift guard)

`localize_scorebar` と wired な `_has_scorebar_v2` が同一フレームで合致することを確認し、emblem 計算の意図的複製 (案 A) が drift していないことを担保する。

**Files:**

- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the tests**

ファイル末尾に追加:

```python
def test_localize_agrees_with_has_scorebar_v2_in_match():
    # 絶対 emblem 位置に重なる span を描くと _has_scorebar_v2 Primary が True。
    # localize_scorebar も relative 位置で検出 -> 両者が in-match で合致 (OBS parity)。
    from allaganeye.video.detector import _has_scorebar_v2

    f = _hires_with_scorebar_at(y_top=0, x_left=600, x_right=1318)
    assert localize_scorebar(f) is not None
    assert _has_scorebar_v2(f.tobytes()) is True


def test_localize_agrees_with_has_scorebar_v2_non_match():
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_HEIGHT,
        _SCOREBAR_V2_PROBE_WIDTH,
        _has_scorebar_v2,
    )

    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    assert localize_scorebar(f) is None
    assert _has_scorebar_v2(f.tobytes()) is False
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_capture_region.py -k agrees_with_has_scorebar_v2 -v`
Expected: PASS (2 passed)。fail する場合は `_emblem_and_margin` の sat/edge 計算が `_emblem_and_check` と乖離している可能性 → 計算を一致させる。

- [ ] **Step 3: Commit**

```bash
git add tests/test_capture_region.py
git commit -m "test(l3): OBS parity between localize_scorebar and _has_scorebar_v2 (F4-b)"
```

---

## Task 8: 全自動チェック + 実機検証 handoff

**Files:** なし (検証のみ)

- [ ] **Step 1: Python 自動チェックを全 pass させる (Iron Law 6)**

Run (worktree root で):

```bash
ruff check .
ruff format --check .
pyright
pytest
```

Expected: すべて pass (`pytest` は slow 除外で全 green)。失敗は本 PR 内で修正してから次へ。

- [ ] **Step 2: 実機 sanity (gyawa、§8.3) — 手動**

サンプル VOD (gyawa) の in-match 時刻で `localize_scorebar` が非 None、lobby/transition で None になることを手動確認する。`ALLAGANEYE_SAMPLE_VIDEO_DIR` 設定済み前提で、以下を python で実行 (`<gyawa.mkv>` と `<in_match_sec>` / `<lobby_sec>` は実 VOD から指定):

```bash
python -c "import numpy as np; from allaganeye.video.detector import _probe_frame_rgb_hires, _SCOREBAR_V2_PROBE_WIDTH as W, _SCOREBAR_V2_PROBE_HEIGHT as H; from allaganeye.video.capture_region import localize_scorebar; from pathlib import Path; p=Path(r'<gyawa.mkv>'); b=_probe_frame_rgb_hires(p, <in_match_sec>); f=np.frombuffer(b,np.uint8).reshape(H,W,3); print('in-match:', localize_scorebar(f))"
```

Expected: in-match 時刻で `ScorebarLocalization(...)` が出力され、span/y が game inset 上端と整合。lobby 時刻 (`<lobby_sec>`) で `None`。結果を PR 本文に記録 (machine-unverifiable bullet)。

- [ ] **Step 3: 実機検証依頼の用意 (Iron Law 6)**

`localize_scorebar` は detector 隣接の新ロジックのため、PR 作成時に Idios へ実機検証 (gyawa VOD での localization 目視確認) を `AskUserQuestion` で依頼する。Step 2 の結果を添える。

- [ ] **Step 4: D4 マージ gate の明示**

PR 本文に「**multi-source 検証 (受け入れ条件 6) 未達のためマージ保留**。追加 VTuber source 入手・`allaganeye-guard verify` 通過・localization 確認まで land しない」と明記する (spec §3 D4 / §8.6-6)。chain は方針 (i): 実装・レビューは進め、マージのみ保留。

---

## Self-Review (この計画 vs spec)

**1. Spec coverage:**

| spec | 対応タスク |
| --- | --- |
| §4 API (`ScorebarLocalization` / `localize_scorebar`) | Task 1, 4 |
| §5.2 saturated_runs (#803 撤廃) | Task 2 |
| §5.3 emblem_and_margin | Task 3 |
| §5.1/§5.4 scan 本体 | Task 4 |
| §6 confidence (best-hit margin) | Task 4 (`target_ratio` / clamp / best-hit / range assert `0<conf<=1`) |
| §7.2 None 契約 / §7.3 小 inset | Task 4, 5 |
| §8.1 合成 position/scale | Task 4, 5 |
| §8.2 negative (#803 含む) | Task 5 |
| §8.4 OBS parity (F4-b) | Task 7 (F4-a は既存 baseline 回帰で自明) |
| §8.5 異常系 | Task 5 |
| §8.6-4 S2 退役 | Task 6 |
| §8.6-5 全チェック | Task 8 |
| §8.6-6 multi-source マージ gate (D4) | Task 8 (手動 gate、コード化対象外) |

**2. Placeholder scan:** Task 8 Step 2 の `<gyawa.mkv>` / `<in_match_sec>` は実 VOD 依存の手動検証値で、自動テストではない (data-gated)。自動テスト (Task 1-7) に placeholder はなく完全なコードを記載済み。

**3. Type consistency:** `ScorebarLocalization(x_left,x_right,y_top,y_bottom,confidence)` は Task 1 定義と Task 4 生成・全テストで一致。`_scorebar_saturated_runs(band, cv2)->list[(int,int)]` / `_emblem_and_margin(frame,positions,cv2)->float|None` のシグネチャは Task 2/3 定義と Task 4 呼び出しで一致。

**結論:** spec の全項目に対応タスクあり。自動化可能な §8.1-8.5/§8.6-1〜5 は Task 1-7 で TDD 実装、手動/data-gated な §8.3 実機・§8.6-6 multi-source は Task 8 で gate 化。
