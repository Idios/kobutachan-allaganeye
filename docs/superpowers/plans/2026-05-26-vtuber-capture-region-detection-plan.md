# VTuber game capture 領域検出 Implementation Plan (Phase 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** VTuber 配信動画の game capture 矩形を自動検出するアルゴリズム候補 (S1/S2/S3) を実装し、実験 harness で gyawa benchmark に対し比較選定できる状態にする (scorebar #480 / minimap #481 / Pass1 本番 wiring は下流)。

**Architecture:** 純関数の領域検出器 (`allaganeye/video/capture_region.py`) を 3 候補実装 (TDD、synthetic frame)。正規化矩形 contract + 幾何メトリクス (IoU / 上端 px 誤差) を同モジュールに置く。`scripts/vtuber_region_experiment.py` が候補を benchmark + OBS baseline に適用して M1–M4 比較表を出力、`scripts/vtuber_region_spike.py` が crop→Pass1→scorebar の ±10s 実現可能性を実証。OBS では各検出器が `FULL_FRAME` に snap し回帰安全。最終選定は実測 (machine-unverifiable) で行い spec に追記。

**Tech Stack:** Python 3.12 / numpy / opencv-python-headless (`cv2`) / pytest (slow marker) / ffmpeg (frame probe)。既存 `allaganeye/video/detector.py` の `_EMBLEM_RELATIVE_POSITIONS` / `_emblem_and_check` / `_probe_frame_rgb_hires` / `_SCOREBAR_SCAN_*` を再利用。

**Spec:** [docs/superpowers/specs/2026-05-26-vtuber-capture-region-detection-design.md](../specs/2026-05-26-vtuber-capture-region-detection-design.md)

---

## 前提・規約 (実装者向け)

- **作業場所**: worktree `.claude/worktrees/l3-vtuber-capture-region/` (branch `claude/l3-vtuber-capture-region`)。main checkout ではない。Bash は `git -C <worktree>` か `cd <worktree> &&` で worktree を明示 (cwd ドリフト注意)。
- **commit**: 各タスク末尾。メッセージ末尾に空行 + `session: l3-vtuber-capture-region` + 空行 + `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`。issue 参照は `Refs #753` のみ (Closes/Fixes 禁止 = Iron Law 4)。日本語本文は `git commit -F <utf8-file>` で渡す (Windows Git Bash の inline 破損回避)。
- **TDD 厳守**: 各実装は failing test を先に書き、fail 確認 → 最小実装 → pass 確認 → commit。
- **lint/型**: タスク完了ごとに `ruff check .` / `ruff format --check .` / `pyright` / `pytest` (slow 除外) を pass させる (Iron Law 6)。Python のみの変更なので GUI チェックは不要。
- **machine-unverifiable**: gyawa benchmark / OBS baseline の実走を要するタスク (Wave D) は実機 (real video + GPU) と user 確認が必要。PR 本文では plain bullet `-` で記載し `[x]` を付けない (`docs/l2-workflow.md` §Self-Test Report 規約)。
- **guard**: gyawa benchmark は external だが trusted 扱い (user 確認 2026-05-26)。新規 external 動画を足す場合のみ `allaganeye-guard verify` 必須。

## File Structure

| ファイル | 責務 | 区分 |
| --- | --- | --- |
| `allaganeye/video/capture_region.py` | `CaptureRegion`/`RegionTimeline` 型、`FULL_FRAME`、幾何 (`iou`/`top_edge_error_px`/`_maybe_snap_full_frame`)、候補検出器 S1/S2/S3 | 新規 (production) |
| `tests/test_capture_region.py` | 上記の単体テスト (synthetic frame) | 新規 |
| `scripts/vtuber_region_experiment.py` | 実験 harness: 候補を動画に適用し M1–M4 比較表を出力 (importable, underscore 名) | 新規 |
| `tests/scripts/test_vtuber_region_experiment.py` | harness の集計・整形ロジック単体テスト | 新規 |
| `scripts/vtuber_region_spike.py` | e2e spike: crop→Pass1→scorebar の ±10s 実現可能性 | 新規 (spike) |
| `tests/scripts/test_vtuber_region_spike.py` | `match_within_tolerance` の単体テスト | 新規 |
| `tests/baselines/v0.3.0/vtuber-primary-regions.json` | proxy 正解矩形 (annotation 成果物) | 新規 (data) |
| `docs/superpowers/specs/2026-05-26-...-design.md` | §6.3/§11 に実測値・選定結果を追記 (Wave D) | 既存修正 |

---

## Wave 0: proxy 正解矩形 (annotation)

### Task 0.1: gyawa benchmark の正解矩形を作成

proxy メトリクス (M1) の ground truth。抽出済みフレーム (`%TEMP%\allaganeye-vtuber-frames\*.jpg`、なければ再抽出) を目視し、各レイアウトの game capture 矩形を正規化座標で記録する。

**Files:**

- Create: `tests/baselines/v0.3.0/vtuber-primary-regions.json`

- [ ] **Step 1: フレームを (再) 抽出して目視**

Run (worktree から、ffmpeg path は環境に合わせる):

```bash
FF="C:/Users/idios/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1-full_build/bin/ffmpeg.exe"
VID="E:/videos/gyawa_vatos/2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4"
OUT="$TEMP/allaganeye-vtuber-frames"; mkdir -p "$OUT"
for t in 1900 2361 4700 6900; do "$FF" -nostdin -v error -ss $t -i "$VID" -frames:v 1 -q:v 2 -y "$OUT/f$t.jpg"; done
```

レイアウト A (試合1 = 小さめ inset): `f1900`/`f2361`。レイアウト B (試合3/5 = 大きめ): `f4700`/`f6900`。各フレームの game 矩形 (cyan 帯の下端〜hotbar 下端、左 chat strip の右〜右 panel の左) を画像目視で px 推定 → 正規化 (px / 1920, px / 1080)。

- [ ] **Step 2: JSON を作成**

```jsonc
{
  "source_file": "2772549129-151803977-da21c691-9ed6-4068-9a8b-4726a8a519a8.mp4",
  "frame_width": 1920,
  "frame_height": 1080,
  "annotation_provider": "agent (visual estimate) + user verify",
  "annotated_at": "2026-05-26",
  "regions": [
    {"timestamp": 1900, "layout": "A", "x": 0.00, "y": 0.00, "w": 0.00, "h": 0.00},
    {"timestamp": 2361, "layout": "A", "x": 0.00, "y": 0.00, "w": 0.00, "h": 0.00},
    {"timestamp": 4700, "layout": "B", "x": 0.00, "y": 0.00, "w": 0.00, "h": 0.00},
    {"timestamp": 6900, "layout": "B", "x": 0.00, "y": 0.00, "w": 0.00, "h": 0.00}
  ]
}
```

(0.00 は目視推定値で置換すること。空欄を残さない。)

- [ ] **Step 3: user 確認 (machine-unverifiable)**

矩形を user (Idios) に提示し補正を受ける。これは目視成果物なので機械検証不可。確認後の値を JSON に確定。

- [ ] **Step 4: Commit**

```bash
git -C "<worktree>" add tests/baselines/v0.3.0/vtuber-primary-regions.json
git -C "<worktree>" commit -F <utf8-msg>   # "test(l3): vtuber primary 正解矩形 annotation (Refs #753)"
```

---

## Wave A: 領域 contract + 幾何メトリクス (TDD)

### Task A.1: `CaptureRegion` / `RegionTimeline` / `FULL_FRAME`

**Files:**

- Create: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_capture_region.py
from allaganeye.video.capture_region import CaptureRegion, RegionTimeline, FULL_FRAME


def test_full_frame_is_unit_square():
    assert (FULL_FRAME.x, FULL_FRAME.y, FULL_FRAME.w, FULL_FRAME.h) == (0.0, 0.0, 1.0, 1.0)


def test_clamp_bounds_region_into_unit_square():
    r = CaptureRegion(-0.1, 0.2, 1.5, 0.5).clamp()
    assert r.x == 0.0 and r.y == 0.2
    assert r.x + r.w <= 1.0 + 1e-9 and r.y + r.h <= 1.0 + 1e-9


def test_round_trip_dict():
    r = CaptureRegion(0.1, 0.2, 0.3, 0.4, confidence=0.8, source="tierB")
    assert CaptureRegion.from_dict(r.to_dict()) == r


def test_region_timeline_to_dict_shape():
    tl = RegionTimeline(coarse=FULL_FRAME, segments=[((10.0, 20.0), FULL_FRAME)])
    d = tl.to_dict()
    assert d["coarse"]["w"] == 1.0
    assert d["segments"][0]["time_range"] == [10.0, 20.0]
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/test_capture_region.py -q` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: 最小実装**

```python
# allaganeye/video/capture_region.py
"""Game capture region detection for overlay-heavy (VTuber) recordings (#753).

Normalized-coordinate region contract + geometry helpers + candidate
detectors (S1 variance / S2 scorebar-band / S3 blackout-overlap).
On standard OBS recordings every detector resolves to ``FULL_FRAME`` so
downstream brightness/scorebar behavior is unchanged (v0.3.0 baseline
bit-exact; see spec §3.4 / M4).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaptureRegion:
    """Game capture rectangle in normalized [0,1] frame coordinates."""

    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0
    source: str = "fallback"  # "tierA" | "tierB" | "fallback"

    def clamp(self) -> "CaptureRegion":
        x = min(max(self.x, 0.0), 1.0)
        y = min(max(self.y, 0.0), 1.0)
        w = min(max(self.w, 0.0), 1.0 - x)
        h = min(max(self.h, 0.0), 1.0 - y)
        return CaptureRegion(x, y, w, h, self.confidence, self.source)

    def to_dict(self) -> dict:
        return {
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "confidence": self.confidence, "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CaptureRegion":
        return cls(d["x"], d["y"], d["w"], d["h"],
                   d.get("confidence", 1.0), d.get("source", "fallback"))


FULL_FRAME = CaptureRegion(0.0, 0.0, 1.0, 1.0, confidence=1.0, source="fallback")


@dataclass
class RegionTimeline:
    """Coarse region (Pass 1) + per-segment precise regions (#480/#481)."""

    coarse: CaptureRegion
    segments: list[tuple[tuple[float, float], CaptureRegion]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "coarse": self.coarse.to_dict(),
            "segments": [
                {"time_range": [t0, t1], "region": r.to_dict()}
                for (t0, t1), r in self.segments
            ],
        }
```

- [ ] **Step 4: pass 確認** — Run: `pytest tests/test_capture_region.py -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): CaptureRegion/RegionTimeline 領域 contract (Refs #753)`

### Task A.2: 幾何メトリクス `iou` / `top_edge_error_px` / `_maybe_snap_full_frame`

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテストを追加**

```python
from allaganeye.video.capture_region import iou, top_edge_error_px, _maybe_snap_full_frame


def test_iou_identical_is_one():
    r = CaptureRegion(0.1, 0.1, 0.5, 0.5)
    assert iou(r, r) == 1.0


def test_iou_disjoint_is_zero():
    a = CaptureRegion(0.0, 0.0, 0.2, 0.2)
    b = CaptureRegion(0.5, 0.5, 0.2, 0.2)
    assert iou(a, b) == 0.0


def test_top_edge_error_px_scales_by_height():
    a = CaptureRegion(0.0, 0.10, 1.0, 0.5)
    b = CaptureRegion(0.0, 0.12, 1.0, 0.5)
    assert round(top_edge_error_px(a, b, 1080)) == round(0.02 * 1080)


def test_snap_full_frame_when_region_covers_most_of_frame():
    near_full = CaptureRegion(0.01, 0.01, 0.97, 0.97, source="tierA")
    assert _maybe_snap_full_frame(near_full) == FULL_FRAME


def test_snap_keeps_small_inset_unchanged():
    inset = CaptureRegion(0.2, 0.1, 0.5, 0.5, source="tierA")
    assert _maybe_snap_full_frame(inset) is inset
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/test_capture_region.py -q` → FAIL (ImportError)

- [ ] **Step 3: 実装を追加**

```python
_SNAP_FULL_FRAME_WH = 0.92
"""w と h が共にこの比率以上なら FULL_FRAME に snap。

OBS 録画では game = frame 全体のため検出器は frame 全域に近い矩形を返す。
わずかな端の欠けで IoU<1.0 になり baseline を壊すのを防ぐため full-frame
に snap し、Pass 1 輝度を現行と数値一致させる (spec §3.4 / M4)。
"""


def iou(a: CaptureRegion, b: CaptureRegion) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def top_edge_error_px(a: CaptureRegion, b: CaptureRegion, frame_h: int) -> float:
    return abs(a.y - b.y) * frame_h


def _maybe_snap_full_frame(region: CaptureRegion) -> CaptureRegion:
    if region.w >= _SNAP_FULL_FRAME_WH and region.h >= _SNAP_FULL_FRAME_WH:
        return FULL_FRAME
    return region
```

- [ ] **Step 4: pass 確認** — Run: `pytest tests/test_capture_region.py -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): 領域 IoU/上端誤差/full-frame snap (Refs #753)`

---

## Wave B: 候補検出器 (TDD on synthetic frames)

各検出器は `np.ndarray` フレームを受け、`CaptureRegion` を返す。OBS 相当の合成フレームでは `FULL_FRAME` に縮退することをテストで保証する (M4)。

### Task B.1: S1 時間分散検出器 `detect_region_variance`

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
import numpy as np
from allaganeye.video.capture_region import detect_region_variance


def _stack_static_bg_with_moving_inset(n=12, h=180, w=320,
                                       inset=(0.30, 0.20, 0.40, 0.50)):
    """静止 bg (一定値) + inset 内だけフレームごとに乱数 = 高分散."""
    rng = np.random.default_rng(0)
    x0, y0, ww, hh = (int(inset[0] * w), int(inset[1] * h),
                      int(inset[2] * w), int(inset[3] * h))
    frames = []
    for _ in range(n):
        f = np.full((h, w), 50, dtype=np.uint8)  # static overlay-ish bg
        f[y0:y0 + hh, x0:x0 + ww] = rng.integers(0, 256, (hh, ww), dtype=np.uint8)
        frames.append(f)
    return frames, inset


def test_variance_finds_moving_inset():
    frames, inset = _stack_static_bg_with_moving_inset()
    r = detect_region_variance(frames)
    assert r.source == "tierA"
    # 検出矩形が inset を概ね包含 (中心が inset 内)
    assert inset[0] <= r.x + r.w / 2 <= inset[0] + inset[2]
    assert inset[1] <= r.y + r.h / 2 <= inset[1] + inset[3]


def test_variance_full_frame_motion_snaps_full():
    rng = np.random.default_rng(1)
    frames = [rng.integers(0, 256, (180, 320), dtype=np.uint8) for _ in range(12)]
    assert detect_region_variance(frames) == FULL_FRAME


def test_variance_static_frames_fall_back_full():
    frames = [np.full((180, 320), 50, dtype=np.uint8) for _ in range(12)]
    assert detect_region_variance(frames) == FULL_FRAME
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/test_capture_region.py -k variance -q` → FAIL (ImportError)

- [ ] **Step 3: 実装**

```python
import numpy as np  # ファイル先頭の import 群へ移動

_VAR_THRESHOLD = 80.0
"""グレースケール時間分散がこの値超で「動きあり」画素とみなす (tunable)。"""

_MIN_REGION_AREA_FRAC = 0.08
"""検出矩形の最小面積比。これ未満は誤検出として FULL_FRAME に fallback。"""


def detect_region_variance(
    frames: list["np.ndarray"],
    *,
    var_threshold: float = _VAR_THRESHOLD,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """S1: 時間分散の最大連結成分を game 領域とみなす (Tier A coarse)。

    *frames* は同形状の 2D グレースケール (H,W) uint8。OBS 録画は全域が
    動くため最大成分が frame 全域 → FULL_FRAME に snap。分散が無ければ
    (静止) FULL_FRAME に fallback。
    """
    import cv2

    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    var = stack.var(axis=0)
    h, w = var.shape
    mask = (var > var_threshold).astype(np.uint8)
    n, _labels, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return FULL_FRAME
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = 1 + int(np.argmax(areas))
    bx, by = int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP])
    bw, bh = int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT])
    if bw * bh < min_area_frac * w * h:
        return FULL_FRAME
    fill = float(areas[idx - 1]) / (bw * bh)
    region = CaptureRegion(bx / w, by / h, bw / w, bh / h,
                           confidence=fill, source="tierA").clamp()
    return _maybe_snap_full_frame(region)
```

- [ ] **Step 4: pass 確認** — Run: `pytest tests/test_capture_region.py -k variance -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): S1 時間分散 game 領域検出器 (Refs #753)`

### Task B.2: S2 scorebar 帯検出器 `detect_region_scorebar_band`

既存 `_find_scorebar_horizontal_range` (y=0..45 固定) を全 y 走査に一般化し、検出した帯を `_emblem_and_check` (GC 紋章 3 点 AND) で FL scorebar と検証してから game 矩形を逆算する。cyan 帯のような単色帯は紋章チェックで弾かれる (R2)。game は 16:9 前提で帯幅から高さを逆算。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテストを書く** (既存 `test_scorebar_v2.py` の合成フレーム作法を流用)

```python
from allaganeye.video.capture_region import detect_region_scorebar_band


def _hires_with_scorebar_at(y_top: int, x_left: int, x_right: int):
    """1920x1080 RGB: y_top 行に saturated 帯 + 3 紋章 (striped) を描く。

    紋章位置は detector._EMBLEM_RELATIVE_POSITIONS を帯 span に投影。
    """
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT,
        _EMBLEM_RELATIVE_POSITIONS,
    )
    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    bar_w = x_right - x_left
    # saturated blue 帯 (45px 高)
    f[y_top:y_top + 45, x_left:x_right + 1] = (50, 50, 200)
    for _name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS:
        cx = int(x_left + cx_rel * bar_w)
        hw = max(2, int(hw_rel * bar_w))
        region = f[y_top + ey1:y_top + ey2, cx - hw:cx + hw]
        for col in range(region.shape[1]):  # 2px 縞 = 高 sat + 高 edge
            region[:, col] = (200, 30, 30) if (col // 2) % 2 == 0 else (0, 0, 0)
    return f


def test_scorebar_band_at_offset_y_returns_inset_top():
    # game 上端を frame の y=120 付近にした VTuber 風レイアウト
    f = _hires_with_scorebar_at(y_top=120, x_left=500, x_right=1400)
    r = detect_region_scorebar_band(f)
    assert r is not None and r.source == "tierB"
    assert abs(r.y - 120 / 1080) < 0.03   # 上端が帯 y 付近


def test_scorebar_band_full_width_top_snaps_full():
    # OBS 相当: 帯が y=2 で frame 全幅 → FULL_FRAME
    f = _hires_with_scorebar_at(y_top=2, x_left=120, x_right=1810)
    assert detect_region_scorebar_band(f) == FULL_FRAME


def test_scorebar_band_uniform_cyan_banner_rejected():
    from allaganeye.video.detector import _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    W, H = _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT
    f = np.full((H, W, 3), 40, dtype=np.uint8)
    f[0:55, :] = (60, 200, 200)  # 単色 cyan 帯 (紋章なし)
    assert detect_region_scorebar_band(f) is None
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/test_capture_region.py -k scorebar_band -q` → FAIL

- [ ] **Step 3: 実装**

```python
_BAND_SCAN_STRIDE = 6
"""y 方向の走査刻み (px)。scorebar 帯の高さ ~45px に対し十分細かい。"""

_BAND_Y_MAX_FRAC = 0.55
"""scorebar を探す y の上限 (frame 高さ比)。game は frame 上〜中央寄り。"""

_GAME_ASPECT = 16.0 / 9.0
"""FF14 game capture のアスペクト比 (帯幅から game 高さを逆算)。"""


def detect_region_scorebar_band(
    frame: "np.ndarray",
    *,
    stride: int = _BAND_SCAN_STRIDE,
) -> CaptureRegion | None:
    """S2: FL scorebar 帯を全 y で探し、game 矩形を逆算 (Tier B precise)。

    *frame* は 1920x1080 RGB (H,W,3) uint8。検出帯を GC 紋章 3 点 AND で
    FL と検証してから返す。FL 帯が見つからなければ None (試合外フレーム
    や opencv 未導入)。OBS 相当 (帯が y~0, 全幅) は FULL_FRAME に snap。
    """
    try:
        import cv2  # noqa: F401
    except ImportError:
        return None
    from allaganeye.video.detector import (
        _SCOREBAR_V2_PROBE_WIDTH, _SCOREBAR_V2_PROBE_HEIGHT,
        _EMBLEM_RELATIVE_POSITIONS, _emblem_and_check,
        _find_scorebar_horizontal_range,
    )
    import cv2

    H = _SCOREBAR_V2_PROBE_HEIGHT
    W = _SCOREBAR_V2_PROBE_WIDTH
    if frame.shape[:2] != (H, W):
        return None
    y_max = int(H * _BAND_Y_MAX_FRAC)
    for y in range(0, y_max, stride):
        # 既存ヘルパは y=0..45 固定なので、その band を切り出して再利用する
        # ために frame を上方シフトした view を渡す。
        shifted = np.zeros_like(frame)
        band_h = min(45, H - y)
        shifted[0:band_h] = frame[y:y + band_h]
        span = _find_scorebar_horizontal_range(shifted.tobytes())
        if span is None:
            continue
        x_left, x_right = span
        bar_w = x_right - x_left
        positions = [
            (name,
             int(x_left + cx_rel * bar_w - hw_rel * bar_w), y + ey1,
             int(x_left + cx_rel * bar_w + hw_rel * bar_w), y + ey2)
            for name, cx_rel, hw_rel, ey1, ey2 in _EMBLEM_RELATIVE_POSITIONS
        ]
        if not _emblem_and_check(frame, positions, f"band y={y}", cv2):
            continue
        # FL scorebar 確定 -> game 矩形を逆算。scorebar 幅 ~= game 幅、
        # 上端 ~= game 上端。game 高さは 16:9 で逆算。
        gw = bar_w / W
        gx = x_left / W
        gy = y / H
        gh = (bar_w / _GAME_ASPECT) / H
        region = CaptureRegion(gx, gy, gw, gh, confidence=0.9, source="tierB").clamp()
        return _maybe_snap_full_frame(region)
    return None
```

> **実装注意**: `_find_scorebar_horizontal_range` に band を渡すため `shifted` view を作る方式は素朴。実装時に既存関数へ `y_start`/`y_end` 引数を足してゼロコピー化する案も可 (その場合は detector.py 側の変更となり、既存 V2 path に影響しないことを `test_scorebar_v2.py` 全 pass で確認すること)。

- [ ] **Step 4: pass 確認** — Run: `pytest tests/test_capture_region.py -k scorebar_band -q` → PASS。さらに既存 `pytest tests/test_scorebar_v2.py -q` が全 pass (detector.py を触った場合の回帰確認)。

- [ ] **Step 5: Commit** — `feat(l3): S2 scorebar 帯 game 領域検出器 (Refs #753)`

### Task B.3: S3 暗転重なり検出器 `detect_region_blackout_overlap`

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテストを書く**

```python
from allaganeye.video.capture_region import detect_region_blackout_overlap


def test_blackout_overlap_finds_region_that_goes_dark():
    h, w = 180, 320
    inset = (0.30, 0.20, 0.40, 0.50)
    x0, y0 = int(inset[0] * w), int(inset[1] * h)
    ww, hh = int(inset[2] * w), int(inset[3] * h)
    bright = np.full((h, w), 120, dtype=np.uint8)          # 全部明るい (試合中)
    dark_inset = bright.copy()
    dark_inset[y0:y0 + hh, x0:x0 + ww] = 2                  # inset だけ暗転、overlay は明るいまま
    frames = [bright, bright, dark_inset, dark_inset]
    r = detect_region_blackout_overlap(frames)
    assert r.source == "tierA"
    assert inset[0] <= r.x + r.w / 2 <= inset[0] + inset[2]
    assert inset[1] <= r.y + r.h / 2 <= inset[1] + inset[3]


def test_blackout_overlap_obs_full_frame_blackout_snaps_full():
    h, w = 180, 320
    bright = np.full((h, w), 120, dtype=np.uint8)
    dark = np.full((h, w), 2, dtype=np.uint8)              # 全画面暗転 = OBS
    assert detect_region_blackout_overlap([bright, bright, dark]) == FULL_FRAME
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/test_capture_region.py -k blackout_overlap -q` → FAIL

- [ ] **Step 3: 実装**

```python
_OVERLAP_BRIGHT = 60.0
"""「試合中は明るい」とみなす画素の最大輝度しきい (tunable)。"""

_OVERLAP_DARK = 20.0
"""「暗転で暗くなる」とみなす画素の最小輝度しきい (tunable)。"""


def detect_region_blackout_overlap(
    frames: list["np.ndarray"],
    *,
    bright_thresh: float = _OVERLAP_BRIGHT,
    dark_thresh: float = _OVERLAP_DARK,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """S3: 「明るい時もあるが暗転で暗くなる」画素 = game 領域 (spec finding #4)。

    overlay は常時明るい (min が下がらない) ため除外される。OBS は全画面が
    暗転する (mask が全域) → FULL_FRAME。
    """
    import cv2

    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    pmax = stack.max(axis=0)
    pmin = stack.min(axis=0)
    h, w = pmax.shape
    mask = ((pmax > bright_thresh) & (pmin < dark_thresh)).astype(np.uint8)
    n, _labels, stats, _c = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return FULL_FRAME
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = 1 + int(np.argmax(areas))
    bx, by = int(stats[idx, cv2.CC_STAT_LEFT]), int(stats[idx, cv2.CC_STAT_TOP])
    bw, bh = int(stats[idx, cv2.CC_STAT_WIDTH]), int(stats[idx, cv2.CC_STAT_HEIGHT])
    if bw * bh < min_area_frac * w * h:
        return FULL_FRAME
    region = CaptureRegion(bx / w, by / h, bw / w, bh / h,
                           confidence=0.8, source="tierA").clamp()
    return _maybe_snap_full_frame(region)
```

- [ ] **Step 4: pass 確認** — Run: `pytest tests/test_capture_region.py -k blackout_overlap -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): S3 暗転重なり game 領域検出器 (Refs #753)`

---

## Wave C: 実験 harness + e2e spike

### Task C.1: harness — 候補ランナー + 比較表

**Files:**

- Create: `scripts/vtuber_region_experiment.py`
- Test: `tests/scripts/test_vtuber_region_experiment.py`

- [ ] **Step 1: 失敗するテスト (集計・整形ロジックのみ)**

```python
# tests/scripts/test_vtuber_region_experiment.py
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "vtuber_region_experiment",
    Path(__file__).resolve().parents[2] / "scripts" / "vtuber_region_experiment.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def test_format_comparison_table_marks_best_iou():
    rows = [
        {"candidate": "S1", "mean_iou": 0.81, "mean_top_err_px": 30.0, "cost_s": 5.0},
        {"candidate": "S2", "mean_iou": 0.94, "mean_top_err_px": 8.0, "cost_s": 9.0},
    ]
    out = mod.format_comparison_table(rows)
    assert "S2" in out and "0.94" in out
    assert mod.pick_winner(rows)["candidate"] == "S2"  # 最大 IoU


def test_pick_winner_requires_obs_passing():
    rows = [
        {"candidate": "S1", "mean_iou": 0.99, "mean_top_err_px": 2.0, "obs_full_frame": False},
        {"candidate": "S2", "mean_iou": 0.90, "mean_top_err_px": 9.0, "obs_full_frame": True},
    ]
    # OBS hard gate: obs_full_frame=False は IoU が高くても不採用
    assert mod.pick_winner(rows)["candidate"] == "S2"
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/scripts/test_vtuber_region_experiment.py -q` → FAIL

- [ ] **Step 3: 実装 (集計ロジック + 実走 CLI)**

```python
# scripts/vtuber_region_experiment.py
"""VTuber game capture 領域検出 候補の実験 harness (#753, spec §6)。

候補 (S1/S2/S3) を gyawa benchmark + OBS baseline に適用し、proxy 矩形
(tests/baselines/v0.3.0/vtuber-primary-regions.json) に対する M1 (IoU /
上端 px 誤差)、M2 (cost)、M4 (OBS で FULL_FRAME か) を比較表で出力する。

Usage:
    python scripts/vtuber_region_experiment.py --benchmark <mp4> --obs <mkv>...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def pick_winner(rows: list[dict]) -> dict | None:
    """OBS hard gate (M4) を通過した候補のうち mean_iou 最大を返す。"""
    eligible = [r for r in rows if r.get("obs_full_frame", True)]
    if not eligible:
        return None
    return max(eligible, key=lambda r: r["mean_iou"])


def format_comparison_table(rows: list[dict]) -> str:
    header = f"{'candidate':<10}{'mean_iou':>10}{'top_err_px':>12}{'cost_s':>10}"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r['candidate']:<10}{r.get('mean_iou', 0):>10.3f}"
            f"{r.get('mean_top_err_px', 0):>12.1f}{r.get('cost_s', 0):>10.1f}"
        )
    return "\n".join(lines)


def _run_on_benchmark(...):  # 実走部 (ffmpeg sampling + 各検出器呼び出し)
    """machine-unverifiable: real video を要するため CI では走らせない。
    実装時に Task D.1 で手動実行する。下記を行う:
    - benchmark から annotation timestamp 近傍フレームを抽出
    - S1/S3 はグレースケール stack、S2 は 1920x1080 RGB を渡す
    - detect_* を呼び iou()/top_edge_error_px() で M1 を集計、時間で M2
    - OBS baseline で各検出器が FULL_FRAME を返すか (M4)
    """
    raise NotImplementedError("Task D.1 で実走部を実装・手動実行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--obs", type=Path, nargs="*", default=[])
    parser.add_argument(
        "--regions",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-regions.json"),
    )
    args = parser.parse_args(argv)
    rows = _run_on_benchmark(args)  # noqa: F841 (Task D.1)
    print(format_comparison_table(rows))
    winner = pick_winner(rows)
    print(f"\nWINNER (M4 gate + max IoU): {winner['candidate'] if winner else 'NONE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> `_run_on_benchmark` の本体は Task D.1 (実走) で埋める。Wave C では集計・整形・選定ロジック (`pick_winner`/`format_comparison_table`) のみ TDD 対象とし、実走は機械検証不可として分離する。

- [ ] **Step 4: pass 確認** — Run: `pytest tests/scripts/test_vtuber_region_experiment.py -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): 領域検出 実験 harness 集計ロジック (Refs #753)`

### Task C.2: e2e spike — crop→Pass1→scorebar ±10s

**Files:**

- Create: `scripts/vtuber_region_spike.py`
- Test: `tests/scripts/test_vtuber_region_spike.py`

- [ ] **Step 1: 失敗するテスト (±10s 照合ロジック)**

```python
# tests/scripts/test_vtuber_region_spike.py
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "vtuber_region_spike",
    Path(__file__).resolve().parents[2] / "scripts" / "vtuber_region_spike.py",
)
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)


def test_match_within_tolerance_all_hit():
    gt = [1433, 2624, 4253, 5684, 6609]
    detected = [1435, 2620, 4258, 5680, 6612]   # 全て ±10s 内
    matched, misses = mod.match_within_tolerance(detected, gt, tol=10)
    assert matched == 5 and misses == []


def test_match_within_tolerance_reports_miss():
    gt = [1433, 2624]
    detected = [1435]                            # 2624 は未検出
    matched, misses = mod.match_within_tolerance(detected, gt, tol=10)
    assert matched == 1 and misses == [2624]
```

- [ ] **Step 2: fail 確認** — Run: `pytest tests/scripts/test_vtuber_region_spike.py -q` → FAIL

- [ ] **Step 3: 実装**

```python
# scripts/vtuber_region_spike.py
"""e2e 実現可能性 spike: crop→Pass1→scorebar の ±10s 実証 (#753, spec §7 M3)。

選定 (または annotation) 領域で frame を crop し、領域内輝度で Pass 1 暗転
検知 → 試合 start/end を抽出し、vtuber-primary-ground-truth.json と ±10s で
照合する。本番 Pass1 wiring ではなく feasibility 確認 (machine-unverifiable)。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def match_within_tolerance(
    detected: list[float], ground_truth: list[float], tol: float = 10.0
) -> tuple[int, list[float]]:
    """各 ground_truth 時刻に ±tol 内の detected があれば matched。

    Returns (matched_count, [未検出の gt 時刻])。
    """
    matched = 0
    misses: list[float] = []
    for g in ground_truth:
        if any(abs(d - g) <= tol for d in detected):
            matched += 1
        else:
            misses.append(g)
    return matched, misses


def _run_spike(...):  # 実走部 (machine-unverifiable)
    """benchmark を sampling → region で crop → 輝度 → 暗転 → segment 抽出。
    Task D.1 で実装・手動実行。Pass 1 本体は再利用せず最小再実装 (feasibility)。
    """
    raise NotImplementedError("Task D.1 で実走部を実装・手動実行")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path("tests/baselines/v0.3.0/vtuber-primary-ground-truth.json"),
    )
    parser.add_argument("--tol", type=float, default=10.0)
    args = parser.parse_args(argv)
    gt_data = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    starts = [m["start_time"] for m in gt_data["matches"]]
    detected = _run_spike(args)  # Task D.1
    matched, misses = match_within_tolerance(detected, starts, args.tol)
    print(f"matched {matched}/{len(starts)} within +-{args.tol}s; misses={misses}")
    return 0 if matched == len(starts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: pass 確認** — Run: `pytest tests/scripts/test_vtuber_region_spike.py -q` → PASS

- [ ] **Step 5: Commit** — `feat(l3): e2e spike ±10s 照合ロジック (Refs #753)`

### Task C.3: M4 OBS 回帰 — full-frame 縮退の単体保証

Wave B の各 `*_full_frame*` / `*_snaps_full` テストで合成 OBS フレームの FULL_FRAME 縮退は既に保証済み。本タスクは「全検出器が FULL_FRAME を返す」横断テストを 1 本足し、回帰ゲートを明示する。

**Files:**

- Test: `tests/test_capture_region.py`

- [ ] **Step 1: 失敗するテスト**

```python
import pytest
from allaganeye.video.capture_region import (
    detect_region_variance, detect_region_blackout_overlap, FULL_FRAME,
)


def test_all_grayscale_detectors_snap_full_on_obs_like_input():
    rng = np.random.default_rng(2)
    motion = [rng.integers(0, 256, (180, 320), dtype=np.uint8) for _ in range(8)]
    assert detect_region_variance(motion) == FULL_FRAME
    bright = np.full((180, 320), 120, dtype=np.uint8)
    dark = np.full((180, 320), 2, dtype=np.uint8)
    assert detect_region_blackout_overlap([bright, bright, dark]) == FULL_FRAME
```

- [ ] **Step 2: fail 確認 → Step 3: (実装済みなので) pass 確認** — Run: `pytest tests/test_capture_region.py -k obs_like -q` → PASS (Wave B 実装で満たされる; fail する場合は閾値/ snap を調整)

- [ ] **Step 4: Commit** — `test(l3): OBS full-frame 縮退 横断回帰ゲート (Refs #753)`

> **machine-unverifiable (M4 完全版)**: 合成フレームの縮退に加え、実 OBS baseline での bit-exact は Task D.1 で `scripts/compare-baseline.py` を使って確認する (real video 要)。

---

## Wave D: 実験実走 + 選定 + 記録 (machine-unverifiable)

> 以降は real video (gyawa benchmark + OBS baseline 5 本) + GPU + user 確認を要する。CI では走らない。PR 本文では plain bullet で記載。

### Task D.1: harness/spike 実走部の実装と計測

- [ ] `vtuber_region_experiment.py::_run_on_benchmark` と `vtuber_region_spike.py::_run_spike` の実走部を実装 (ffmpeg sampling、`_probe_frame_rgb_hires` 流用、crop 輝度の Pass1 最小再実装)。
- [ ] `python scripts/vtuber_region_experiment.py --benchmark <gyawa> --obs <obs5本>` を実行し M1/M2/M4 比較表を取得。
- [ ] `python scripts/vtuber_region_spike.py --benchmark <gyawa>` を実行し ±10s/index 1-5 (M3) を確認。
- [ ] OBS baseline 5 本で `compare-baseline.py` により detect 出力 bit-exact (M4 完全版) を確認。
- [ ] 計測ログを worktree に保存 (PR の Self-Test Report に添付)。

### Task D.2: 勝者確定 + 敗者刈り込み

- [ ] `pick_winner` 結果と spec §6.3 選定手順 (M4 gate → M1 → M2 → M3) に基づき採用候補を確定。
- [ ] 不採用候補の検出器関数を `capture_region.py` から削除 (または `# experimental` として残すか user 判断)。
- [ ] 閾値定数 (`_VAR_THRESHOLD` 等) を実測に合わせて調整し、Wave B テストの許容値を必要なら更新。

### Task D.3: spec へ実測・選定を追記

- [ ] `docs/superpowers/specs/2026-05-26-...-design.md` §6.3 に M1–M4 実測表、§11 決定ログに採用候補を追記。
- [ ] §10 Open question 1 (検出シグナル最終選定) / 2 (再検出粒度) を実測に基づき close。
- [ ] Commit: `docs(l3): 領域検出 実験結果と選定を spec に追記 (Refs #753)`

### Task D.4: 下流 child issue 起票案の記録 (Iron Law 2 — 作成は user 確認後)

- [ ] spec §8.2 の issue 分解 (Pass1 wiring / #480 / #481 / metadata スキーマ) を起票文面案として worktree のメモか PR 本文に記録。
- [ ] **実際の `gh issue create` は行わない**。3 件以上の issue 操作になるため user 確認後に別途実施。

---

## 実機検証 trigger (PR 作成時に AskUserQuestion で依頼)

- 本 issue は新規モジュール中心で `detector.py` 本体ロジックは原則変更しない。ただし Task B.2 で `_find_scorebar_horizontal_range` に `y_start/y_end` 引数を足す改修を選んだ場合、既存 V2 path への回帰がないことを実 OBS 動画で確認 (`test_scorebar_v2.py` + baseline) する必要があり、実機検証 trigger に該当。
- Wave D の harness/spike 実走は GPU + 長尺動画 (gyawa 2h43m / OBS 5 本) を要し mock 不可 → user (Idios) に実機実行を依頼。

## Self-Review (この plan を書いた直後の自己点検)

- **Spec coverage**: spec §4 contract → Task A.1 / §5 S1-S3 → Task B.1-B.3 / §6 harness+M1-M4 → Task C.1,C.3,D.1 / §7 e2e spike → Task C.2,D.1 / §6.4 annotation → Task 0.1 / §8.2 issue 分解 → Task D.4 / §11 決定ログ更新 → Task D.3。全項目に対応タスクあり。
- **Placeholder**: `_run_on_benchmark`/`_run_spike` の本体は意図的に Task D.1 へ分離 (real-video 依存で TDD 不可)。それ以外に TODO/TBD なし。annotation JSON の 0.00 は「目視値で必ず置換」と明記。
- **型整合**: `CaptureRegion(x,y,w,h,confidence,source)` / `iou`/`top_edge_error_px`/`_maybe_snap_full_frame` / `detect_region_variance|scorebar_band|blackout_overlap` / `pick_winner`/`format_comparison_table` / `match_within_tolerance` — 全タスクで名称・引数一貫。検出器は S1/S3=グレースケール stack、S2=1920x1080 RGB 単フレームで統一。
