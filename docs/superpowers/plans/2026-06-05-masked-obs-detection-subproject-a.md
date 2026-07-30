# masked + ultrawide OBS 検出 (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** チャット隠しマスク画像を重ねた全画面 OBS 録画 (ultrawide 含む) を、標準 detect が 0 blackout で全滅したとき mask-free 領域の輝度で再検出し、position-independent な localize 分類で試合分割できるようにする。

**Architecture:** 標準 full-frame Pass 1 が 0 blackout を返したとき (または `--masked` 強制時) のみ走る純粋な追加経路 `_detect_masked_fallback` を `detect_match_boundaries` 内の明示 gate (`not vtuber and (masked or not blackout_times)`) で起動する。fallback は (1) static-overlay で mask-free 矩形を検出 → (2) parked Phase 1 region 機構 (`region=`) で Pass1/Pass2 を再実行 → (3) parked Phase 2 localize 分類器 (`localize=True`) で試合境界を分類 → (4) 既存 segment 抽出。OBS 5 baseline は full-frame で必ず blackout を拾うため gate が False のまま = 標準 path のコードは構造的に不変 (bit-exact)。

**Tech Stack:** Python 3.12 / numpy / opencv-python-headless / ffmpeg / Typer。既存 `allaganeye.video.{detector,scorebar,gpu_detector,capture_region}` の parked Phase 0/1/2 機構を土台に再利用する。

---

## 設計不変条件 (全タスク共通、違反したら STOP)

- **bit-exact mandate**: `vtuber=False` かつ標準 Pass1 が blackout を 1 つでも返す録画では、`detect_match_boundaries` の実行 path は現行と完全一致しなければならない。masked 経路は gate (`not vtuber and (masked or not blackout_times)`) の内側のみ。OBS 5 baseline (Task 7) で必ず構造確認する。
- **隔離 > DRY**: `_detect_masked_fallback` は標準 path の scan/refine/classify を共有関数に抽出せず**意図的に複製**する (既存 factored helper は呼ぶ)。標準 path body を触る refactor は bit-exact を 2 度壊した教訓 (spec §10 R1) のため禁止。複製箇所には cross-reference コメントを付ける。
- **localize 分類器のみ共有**: VTuber 固有 (band-anchor `_resolve_detect_region` / `--vtuber` user flag) は再利用しない。共有するのは position-independent 分類器のみ。その選択子をこの plan で `vtuber` → `localize` に正名化する (Task 4)。

## 再利用する既存機構 (再実装禁止)

| シンボル | 場所 | 役割 |
| --- | --- | --- |
| `CaptureRegion` / `FULL_FRAME` / `region_mean` / `_maybe_snap_full_frame` | `capture_region.py` | 正規化矩形 + 縮退 snap |
| `detect_region_blackout_overlap` (S3) / `_OVERLAP_BRIGHT=60` / `_OVERLAP_DARK=20` / `_MIN_REGION_AREA_FRAC=0.08` | `capture_region.py` | Task 1 の発想の土台 + 共有定数 |
| `_scan_cpu(region=)` / `scan_gpu(region=)` / `_refine_blackout_regions(region=)` / `_frame_brightness(region=)` | `detector.py` / `gpu_detector.py` | Phase 1 region threading |
| `_group_blackout_regions` / `_expand_regions_with_transitions` / `_borderline_pseudo_regions` / `_merge_regions` / `_filter_and_extract_segments` | `detector.py` | 検出パイプライン部品 |
| `_scaled_height` / `_BLACKOUT_THRESHOLD_UPPER_MARGIN` / `_TRANSITION_THRESHOLD` / `_ENABLE_BORDERLINE_REFINEMENT` / `_REFINED_MIN_BLACKOUT` | `detector.py` | 共有定数・ヘルパ |
| `filter_blackouts_with_scorebar` / `classify_blackout` / `_classify_blackout_localize` / `_merge_boundary_pairs` / `_probe_scorebar_context(with_localize=)` / `_localize_present_from_raw` | `scorebar.py` | Phase 2 localize 分類 |
| `SplitConfig` / `_run_detection` の `detect_kwargs` / CLI `--vtuber` flag | `config.py` / `commands/split_matches.py` / `cli.py` | CLI plumbing |

## File Structure

- Modify: `allaganeye/video/capture_region.py` — `detect_mask_free_region` + `_maximal_ones_rectangle` を追加 (S3 を hole-free 矩形に精緻化)。
- Modify: `allaganeye/video/detector.py` — `_decode_gray_raw` 抽出 + `_probe_frame_gray2d` / `_resolve_masked_region` / `_detect_masked_fallback` 追加 + `detect_match_boundaries` に `masked` param と gate branch、`filter_blackouts_with_scorebar` 呼び出しを `localize=` に追従。
- Modify: `allaganeye/video/scorebar.py` — 分類器選択子 `vtuber` → `localize` 正名化 (`classify_blackout` / `filter_blackouts_with_scorebar` / `_merge_boundary_pairs`)。
- Modify: `allaganeye/config.py` — `SplitConfig.masked: bool = False`。
- Modify: `allaganeye/cli.py` — `--masked` option (split + detect)、`--vtuber` を `hidden=True` 化、`--vtuber`/`--masked` 排他。
- Modify: `allaganeye/commands/split_matches.py` — `detect_kwargs` に `"masked": config.masked`。
- Test: `tests/test_capture_region.py` / `tests/test_detector.py` / `tests/test_scorebar.py` / `tests/test_config.py` / `tests/test_cli.py` / `tests/test_l3_phase2_parity.py` / `tests/test_split_matches.py` / `tests/test_scorebar_v2.py`。

---

## Task 1: mask-free 矩形検出 (`detect_mask_free_region`)

S3 (`detect_region_blackout_overlap`) は game の最大連結成分**bbox** を返すためマスク穴を含みうる。本タスクは game mask 上の**最大 all-ones 矩形** (hole-free) を返す形に精緻化する。

**Files:**

- Modify: `allaganeye/video/capture_region.py`
- Test: `tests/test_capture_region.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_capture_region.py` の末尾に追加:

```python
import numpy as np

from allaganeye.video.capture_region import (
    FULL_FRAME,
    detect_mask_free_region,
    _maximal_ones_rectangle,
)


def _rect_overlaps(rect_px, block_px) -> bool:
    ax0, ay0, ax1, ay1 = rect_px
    bx0, by0, bx1, by1 = block_px
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def _frames_with_mask(h, w, mask_block, values=(5, 200, 5, 200)):
    """Game pixels cycle bright/dark across frames; mask_block stays bright (200)."""
    bx0, by0, bx1, by1 = mask_block
    frames = []
    for v in values:
        f = np.full((h, w), v, dtype=np.uint8)
        f[by0:by1, bx0:bx1] = 200  # static bright mask -> min never < dark
        frames.append(f)
    return frames


def test_maximal_ones_rectangle_simple_block():
    mask = np.zeros((4, 5), dtype=np.uint8)
    mask[1:4, 1:4] = 1  # 3x3 block of ones at (x=1..3, y=1..3)
    assert _maximal_ones_rectangle(mask) == (1, 1, 4, 4)


def test_maximal_ones_rectangle_empty_is_none():
    assert _maximal_ones_rectangle(np.zeros((4, 4), dtype=np.uint8)) is None


def test_detect_mask_free_region_excludes_bright_mask():
    # 20x20, bright static mask at bottom-left (cols 0..10, rows 10..20).
    frames = _frames_with_mask(20, 20, (0, 10, 10, 20))
    region = detect_mask_free_region(frames)
    assert not region.is_full_frame()
    # Returned rectangle must not intersect the mask block.
    px = (
        round(region.x * 20),
        round(region.y * 20),
        round((region.x + region.w) * 20),
        round((region.y + region.h) * 20),
    )
    assert not _rect_overlaps(px, (0, 10, 10, 20))


def test_detect_mask_free_region_full_game_snaps_full_frame():
    # Every pixel cycles bright/dark -> game everywhere -> FULL_FRAME.
    frames = [np.full((20, 20), v, dtype=np.uint8) for v in (5, 200, 5, 200)]
    assert detect_mask_free_region(frames).is_full_frame()


def test_detect_mask_free_region_tiny_game_is_full_frame():
    # Only a 2x2 game patch (rest stays bright) -> below min_area_frac -> FULL_FRAME.
    frames = []
    for v in (5, 200):
        f = np.full((20, 20), 200, dtype=np.uint8)
        f[0:2, 0:2] = v
        frames.append(f)
    assert detect_mask_free_region(frames).is_full_frame()


def test_detect_mask_free_region_single_frame_is_full_frame():
    assert detect_mask_free_region([np.zeros((20, 20), dtype=np.uint8)]).is_full_frame()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_capture_region.py -k "mask_free or maximal_ones" -v`
Expected: FAIL with `ImportError: cannot import name 'detect_mask_free_region'`.

- [ ] **Step 3: Implement `_maximal_ones_rectangle` + `detect_mask_free_region`**

`allaganeye/video/capture_region.py` の `detect_region_blackout_overlap` 直後に追加:

```python
def _maximal_ones_rectangle(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Largest all-ones axis-aligned rectangle in a binary mask (histogram stack).

    Returns ``(x0, y0, x1, y1)`` half-open (x1/y1 exclusive) of the maximum-area
    all-ones rectangle, or ``None`` when the mask has no set pixels.  O(H*W):
    per-row histogram heights + largest-rectangle-in-histogram with a sentinel.
    """
    h, w = mask.shape
    heights = np.zeros(w, dtype=np.int32)
    best_area = 0
    best: tuple[int, int, int, int] | None = None
    for y in range(h):
        heights = np.where(mask[y] > 0, heights + 1, 0)
        hh = heights.tolist()
        stack: list[int] = []
        x = 0
        while x <= w:
            cur = hh[x] if x < w else 0
            if not stack or hh[stack[-1]] <= cur:
                stack.append(x)
                x += 1
            else:
                top = stack.pop()
                height = hh[top]
                left = 0 if not stack else stack[-1] + 1
                width = x - left
                area = height * width
                if area > best_area:
                    best_area = area
                    best = (left, y - height + 1, left + width, y + 1)
    return best


def detect_mask_free_region(
    frames: list[np.ndarray],
    *,
    bright_thresh: float = _OVERLAP_BRIGHT,
    dark_thresh: float = _OVERLAP_DARK,
    min_area_frac: float = _MIN_REGION_AREA_FRAC,
) -> CaptureRegion:
    """Largest hole-free game rectangle for masked recordings (#753 masked-OBS).

    Refines S3 (``detect_region_blackout_overlap``): instead of the largest game
    *component bbox* (which can contain mask holes), returns the largest solid
    all-game *rectangle* (maximal all-ones rectangle over the game mask), so the
    measurement region excludes bright static masks composited over gameplay.

    game pixel = max brightness > ``bright_thresh`` AND min brightness <
    ``dark_thresh`` (brightens during play, darkens during a blackout).  Bright
    static masks never darken (min stays high) -> excluded.  Always-dark bars
    never brighten -> excluded.  Unmasked full-frame game -> every pixel is game
    -> snaps to FULL_FRAME.  Fewer than 2 frames, no game pixels, or a max
    rectangle below ``min_area_frac`` of the frame -> FULL_FRAME (safe degenerate:
    the masked-fallback caller treats FULL_FRAME as "no mask region found").
    """
    if len(frames) < 2:
        return FULL_FRAME
    stack = np.stack(frames).astype(np.float32)
    pmax = stack.max(axis=0)
    pmin = stack.min(axis=0)
    game_mask = ((pmax > bright_thresh) & (pmin < dark_thresh)).astype(np.uint8)
    rect = _maximal_ones_rectangle(game_mask)
    if rect is None:
        return FULL_FRAME
    x0, y0, x1, y1 = rect
    h, w = game_mask.shape
    if (x1 - x0) * (y1 - y0) < min_area_frac * w * h:
        return FULL_FRAME
    region = CaptureRegion(
        x0 / w,
        y0 / h,
        (x1 - x0) / w,
        (y1 - y0) / h,
        confidence=0.8,
        source="tierA",
    ).clamp()
    return _maybe_snap_full_frame(region)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_capture_region.py -k "mask_free or maximal_ones" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/capture_region.py tests/test_capture_region.py
git commit -m "feat(l3): mask-free 矩形検出 detect_mask_free_region (S3 を hole-free 化, masked-OBS A1)"
```

---

## Task 2: 単一フレーム grayscale 2D デコード (`_probe_frame_gray2d`)

mask-free 領域検出 (Task 3) には輝度スカラーではなく 2D フレーム配列が要る。`_probe_single_frame` の ffmpeg デコードを behavior-preserving に `_decode_gray_raw` へ抽出し、2D 版を追加する。

**Files:**

- Modify: `allaganeye/video/detector.py:858-911` (`_probe_single_frame`)
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_detector.py` の末尾に追加:

```python
import numpy as np

from allaganeye.video import detector as _det


def test_probe_frame_gray2d_returns_2d(monkeypatch):
    buf = bytes(range(256)) * (_det._FRAME_SIZE // 256 + 1)
    monkeypatch.setattr(_det, "_decode_gray_raw", lambda v, t: buf[: _det._FRAME_SIZE])
    frame = _det._probe_frame_gray2d(_det.Path("x.mp4"), 1.0)
    assert frame is not None
    assert frame.shape == (_det._SAMPLE_HEIGHT, _det._SAMPLE_WIDTH)
    assert frame.dtype == np.uint8


def test_probe_frame_gray2d_none_on_decode_failure(monkeypatch):
    monkeypatch.setattr(_det, "_decode_gray_raw", lambda v, t: None)
    assert _det._probe_frame_gray2d(_det.Path("x.mp4"), 1.0) is None


def test_probe_single_frame_regression_via_shared_decoder(monkeypatch):
    # Extraction must preserve _probe_single_frame brightness exactly.
    buf = bytes([10]) * _det._FRAME_SIZE
    monkeypatch.setattr(_det, "_decode_gray_raw", lambda v, t: buf)
    assert _det._probe_single_frame(_det.Path("x.mp4"), 1.0) == 10.0
    monkeypatch.setattr(_det, "_decode_gray_raw", lambda v, t: None)
    assert _det._probe_single_frame(_det.Path("x.mp4"), 1.0) == 255.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_detector.py -k "probe_frame_gray2d or regression_via_shared" -v`
Expected: FAIL with `AttributeError: ... has no attribute '_decode_gray_raw'`.

- [ ] **Step 3: Extract `_decode_gray_raw` and add `_probe_frame_gray2d`**

`allaganeye/video/detector.py`、現行 `_probe_single_frame` (lines 858-911) を以下で置換:

```python
def _decode_gray_raw(video_path: Path, timestamp: float) -> bytes | None:
    """Decode exactly one 320x180 grayscale frame to raw bytes via ffmpeg -ss.

    Shared by :func:`_probe_single_frame` (brightness) and
    :func:`_probe_frame_gray2d` (2D array).  Returns the first ``_FRAME_SIZE``
    bytes, or ``None`` on timeout / ffmpeg error / short read.  Raises
    ``VideoProcessingError`` only when ffmpeg is missing.
    """
    cmd = [
        find_ffmpeg(),
        "-threads",
        "1",
        "-ss",
        str(timestamp),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-s",
        f"{_SAMPLE_WIDTH}x{_SAMPLE_HEIGHT}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError as e:
        raise VideoProcessingError(
            "ffmpeg not found. Please install ffmpeg and ensure it is in PATH."
        ) from e
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    if len(result.stdout) < _FRAME_SIZE:
        return None
    return result.stdout[:_FRAME_SIZE]


def _probe_single_frame(
    video_path: Path,
    timestamp: float,
    region: CaptureRegion = FULL_FRAME,
) -> float:
    """Probe a single frame's mean brightness using ffmpeg -ss seek.

    Returns the mean brightness (0-255).  Returns 255.0 on probe failure
    (treated as non-blackout to avoid false positives).  Brightness is computed
    via :func:`_frame_brightness`, so *region* defaults to ``FULL_FRAME`` (the
    1-D ``float(frame.mean())`` path is byte-identical to the pre-region
    behavior; a band region reshapes the raw buffer and crops).
    """
    raw = _decode_gray_raw(video_path, timestamp)
    if raw is None:
        return 255.0
    frame = np.frombuffer(raw, dtype=np.uint8)
    return _frame_brightness(frame, region)


def _probe_frame_gray2d(video_path: Path, timestamp: float) -> np.ndarray | None:
    """Probe one 320x180 grayscale frame as a 2D ``(H, W)`` uint8 array.

    Returns ``None`` on probe failure.  Used by :func:`_resolve_masked_region`
    for static-overlay mask-free region detection (#753 masked-OBS).
    """
    raw = _decode_gray_raw(video_path, timestamp)
    if raw is None:
        return None
    return np.frombuffer(raw, dtype=np.uint8).reshape(_SAMPLE_HEIGHT, _SAMPLE_WIDTH)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_detector.py -k "probe_frame_gray2d or regression_via_shared or probe_single_frame" -v`
Expected: PASS (新規 3 + 既存 `_probe_single_frame` テスト全て green = 抽出が behavior-preserving)。

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "refactor(l3): grayscale decode を _decode_gray_raw に抽出 + _probe_frame_gray2d 追加 (masked-OBS A2)"
```

---

## Task 3: mask-free 領域解決 (`_resolve_masked_region`)

疎サンプルした 2D フレーム群を `detect_mask_free_region` に渡し、例外は FULL_FRAME に握り潰す orchestration。

**Files:**

- Modify: `allaganeye/video/detector.py` (import 群と `_resolve_detect_region` 近傍に追加)
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_detector.py` に追加:

```python
def _masked_frames():
    out = []
    for v in (5, 200, 5, 200):
        f = np.full((_det._SAMPLE_HEIGHT, _det._SAMPLE_WIDTH), v, dtype=np.uint8)
        f[120:180, 0:120] = 200  # static bright mask, bottom-left
        out.append(f)
    return out


def test_resolve_masked_region_finds_mask_free_rect(monkeypatch):
    seq = iter(_masked_frames() * 20)
    monkeypatch.setattr(
        _det, "_probe_frame_gray2d", lambda v, t: next(seq, _masked_frames()[0])
    )
    region = _det._resolve_masked_region(_det.Path("x.mp4"), 600.0, None)
    assert not region.is_full_frame()


def test_resolve_masked_region_full_frame_when_no_frames(monkeypatch):
    monkeypatch.setattr(_det, "_probe_frame_gray2d", lambda v, t: None)
    assert _det._resolve_masked_region(_det.Path("x.mp4"), 600.0, None).is_full_frame()


def test_resolve_masked_region_swallows_exceptions(monkeypatch):
    def boom(v, t):
        raise RuntimeError("decode blew up")

    monkeypatch.setattr(_det, "_probe_frame_gray2d", boom)
    assert _det._resolve_masked_region(_det.Path("x.mp4"), 600.0, None).is_full_frame()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_detector.py -k resolve_masked_region -v`
Expected: FAIL with `AttributeError: ... has no attribute '_resolve_masked_region'`.

- [ ] **Step 3: Implement `_resolve_masked_region`**

`allaganeye/video/detector.py`、`_resolve_detect_region` の直後に追加 (`ThreadPoolExecutor` は既に import 済 / `os` も import 済であることを確認: ファイル冒頭に無ければ `import os` を追加):

```python
_MASKED_REGION_SAMPLES = 48
"""Sparse frames sampled across the video for mask-free region detection.

Must span multiple blackouts so game pixels register a dark ``min``; 48 over a
multi-hour FL recording covers many match boundaries (spec section 5).
"""


def _resolve_masked_region(
    video_path: Path, duration_hint: float, workers: int | None
) -> CaptureRegion:
    """Detect the mask-free game rectangle for masked recordings (#753).

    Samples ``_MASKED_REGION_SAMPLES`` sparse grayscale frames and runs
    ``detect_mask_free_region``.  Any failure (decode, opencv, empty) degrades to
    FULL_FRAME so the masked-fallback caller can treat FULL_FRAME as "no mask
    region found" and defer to the standard result.  Never raises.
    """
    from allaganeye.video.capture_region import detect_mask_free_region

    try:
        n = _MASKED_REGION_SAMPLES
        times = [duration_hint * (i + 1) / (n + 1) for i in range(n)]
        max_workers = max(1, min(len(times), os.cpu_count() or 4))
        frames: list[np.ndarray] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for frame in pool.map(lambda t: _probe_frame_gray2d(video_path, t), times):
                if frame is not None:
                    frames.append(frame)
        if len(frames) < 2:
            return FULL_FRAME
        return detect_mask_free_region(frames)
    except Exception:
        return FULL_FRAME
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_detector.py -k resolve_masked_region -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): _resolve_masked_region (疎サンプル -> mask-free 矩形, 例外は FULL_FRAME 縮退, masked-OBS A3)"
```

---

## Task 4: 分類器選択子の正名化 (`vtuber` → `localize`)

scorebar 層の `vtuber` boolean は実体が「position-independent localize 分類を使う」選択子。VTuber と masked が共有するため `localize` に正名化する。`detect_match_boundaries` 自身の `vtuber` param (band-anchor / trailing gate を制御) は据え置く。

**Files:**

- Modify: `allaganeye/video/scorebar.py` (`classify_blackout` / `filter_blackouts_with_scorebar` / `_merge_boundary_pairs`)
- Modify: `allaganeye/video/detector.py:454` (`filter_blackouts_with_scorebar(..., vtuber=vtuber)` → `localize=vtuber`)
- Test: `tests/test_scorebar.py` / `tests/test_l3_phase2_parity.py` / `tests/test_split_matches.py` / `tests/test_scorebar_v2.py`

- [ ] **Step 1: Write the failing test (behavioral, selector routing)**

`tests/test_scorebar.py` に追加:

```python
from allaganeye.video import scorebar as _sb


def test_classify_blackout_localize_selector_routes(monkeypatch):
    monkeypatch.setattr(_sb, "_classify_blackout_localize", lambda *a, **k: "LOCALIZED")
    # localize=True -> position-independent path
    assert (
        _sb.classify_blackout(
            _sb.Path("x.mp4"), (10.0, 12.0), 100.0, 180, localize=True
        )
        == "LOCALIZED"
    )
    # localize=False -> v2 path (NOT the localize sentinel; probes return real result)
    monkeypatch.setattr(
        _sb, "_probe_scorebar_context", lambda *a, **k: ([None], [None], [None])
    )
    assert (
        _sb.classify_blackout(
            _sb.Path("x.mp4"), (10.0, 12.0), 100.0, 180, localize=False
        )
        != "LOCALIZED"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scorebar.py -k localize_selector_routes -v`
Expected: FAIL with `TypeError: classify_blackout() got an unexpected keyword argument 'localize'`.

- [ ] **Step 3: Rename the selector in scorebar.py + the detector call site**

`allaganeye/video/scorebar.py` で 3 関数の `vtuber: bool = False` キーワードを `localize: bool = False` に改名し、内部参照も追従:

- `classify_blackout` (line 388): `vtuber: bool = False` → `localize: bool = False`。本体 `if vtuber:` (line 418) → `if localize:`。docstring の "(VTuber)" 記述は "(position-independent: VTuber / masked)" に更新。
- `filter_blackouts_with_scorebar` (line 574): `vtuber: bool = False` → `localize: bool = False`。`classify_blackout(..., vtuber=vtuber)` (line 622) → `localize=localize`。末尾 `_merge_boundary_pairs(..., vtuber=vtuber)` (line 688) → `localize=localize`。
- `_merge_boundary_pairs` (line 701): `vtuber: bool = False` → `localize: bool = False`。本体 `if vtuber:` (line 736) → `if localize:`。

`allaganeye/video/detector.py` line 454、`filter_blackouts_with_scorebar` 呼び出しの `vtuber=vtuber,` を `localize=vtuber,` に変更 (detector の `vtuber` param 自体は据え置き)。

- [ ] **Step 4: Migrate existing test call sites**

scorebar 3 関数を `vtuber=` で呼ぶ既存テストを `localize=` に改名する。**`detect_match_boundaries(..., vtuber=...)` の呼び出しは改名しない** (別 param)。場所を特定:

Run: `grep -rn "vtuber=" tests/ | grep -E "classify_blackout|filter_blackouts_with_scorebar|_merge_boundary_pairs"`

ヒットした各行の `vtuber=` を `localize=` に置換 (主に `tests/test_scorebar.py` / `tests/test_l3_phase2_parity.py` / `tests/test_scorebar_v2.py` / `tests/test_split_matches.py`)。assertion は変更しない (挙動不変の rename)。

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_scorebar.py tests/test_scorebar_v2.py tests/test_l3_phase2_parity.py tests/test_split_matches.py -v`
Expected: PASS (新規 selector routing test + 既存 scorebar/parity 全て green)。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/scorebar.py allaganeye/video/detector.py tests/
git commit -m "refactor(l3): 分類器選択子を vtuber->localize に正名化 (VTuber/masked 共有, masked-OBS A4)"
```

---

## Task 5: masked fallback 本体 + gate branch (`_detect_masked_fallback`)

`detect_match_boundaries` に `masked` param と明示 gate branch を追加し、region 再検出 + localize 分類の隔離経路 `_detect_masked_fallback` を実装する。

**Files:**

- Modify: `allaganeye/video/detector.py` (`detect_match_boundaries` signature + branch、`_detect_masked_fallback` 追加)
- Test: `tests/test_detector.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_detector.py` に追加:

```python
def _zero_blackout_results():
    return {float(t): 200.0 for t in range(0, 600, 3)}


def test_masked_fallback_triggers_on_zero_blackout(monkeypatch):
    monkeypatch.setattr(_det, "_scan_cpu", lambda *a, **k: _zero_blackout_results())
    called = {}

    def fake_masked(video_path, **kw):
        called["hit"] = True
        return [{"start": 0.0, "end": 300.0}]

    monkeypatch.setattr(_det, "_detect_masked_fallback", fake_masked)
    out = _det.detect_match_boundaries(
        _det.Path("x.mp4"),
        duration_hint=600.0,
        use_gpu=False,
        src_resolution=(1920, 1080),
    )
    assert called.get("hit") is True
    assert out == [{"start": 0.0, "end": 300.0}]


def test_masked_fallback_not_triggered_when_blackouts_present(monkeypatch):
    # OBS bit-exact gate: blackouts present + masked=False -> fallback NOT called.
    results = _zero_blackout_results()
    results[300.0] = 2.0  # one blackout frame
    monkeypatch.setattr(_det, "_scan_cpu", lambda *a, **k: results)
    monkeypatch.setattr(_det, "_refine_blackout_regions", lambda *a, **k: [])
    called = {}
    monkeypatch.setattr(
        _det, "_detect_masked_fallback", lambda *a, **k: called.setdefault("hit", True)
    )
    _det.detect_match_boundaries(
        _det.Path("x.mp4"), duration_hint=600.0, use_gpu=False, src_resolution=None
    )
    assert "hit" not in called


def test_masked_fallback_forced_even_with_blackouts(monkeypatch):
    results = _zero_blackout_results()
    results[300.0] = 2.0
    monkeypatch.setattr(_det, "_scan_cpu", lambda *a, **k: results)
    monkeypatch.setattr(
        _det, "_detect_masked_fallback", lambda *a, **k: [{"start": 1.0, "end": 2.0}]
    )
    out = _det.detect_match_boundaries(
        _det.Path("x.mp4"),
        duration_hint=600.0,
        use_gpu=False,
        masked=True,
        src_resolution=(1920, 1080),
    )
    assert out == [{"start": 1.0, "end": 2.0}]


def test_detect_masked_fallback_returns_none_when_no_region(monkeypatch):
    monkeypatch.setattr(_det, "_resolve_masked_region", lambda *a, **k: _det.FULL_FRAME)
    scan_called = {}
    monkeypatch.setattr(
        _det, "_scan_cpu", lambda *a, **k: scan_called.setdefault("hit", True) or {}
    )
    out = _det._detect_masked_fallback(
        _det.Path("x.mp4"),
        duration_hint=600.0,
        sample_interval=3.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        use_gpu=False,
        workers=None,
        src_resolution=(1920, 1080),
        codec="h264",
        gpu_vendor=None,
        source_fps_num=60,
        source_fps_den=1,
        source_fps=None,
        audio_hits=None,
        stats=None,
    )
    assert out is None
    assert "hit" not in scan_called  # short-circuits before scanning


def test_detect_masked_fallback_wires_region_band_localize(monkeypatch):
    from allaganeye.video.capture_region import CaptureRegion

    fake_region = CaptureRegion(0.0, 0.0, 1.0, 0.3, source="tierA")
    monkeypatch.setattr(_det, "_resolve_masked_region", lambda *a, **k: fake_region)
    seen = {}

    def fake_scan(video_path, dur, si, thr, workers, cb, **kw):
        seen["scan_region"] = kw.get("region")
        return {0.0: 2.0, 3.0: 2.0, 100.0: 200.0}

    monkeypatch.setattr(_det, "_scan_cpu", fake_scan)

    def fake_refine(video_path, regions, thr, dur, workers, **kw):
        seen["refine_region"] = kw.get("region")
        return [(0.0, 3.0)]

    monkeypatch.setattr(_det, "_refine_blackout_regions", fake_refine)

    def fake_filter(video_path, regions, dur, height, workers, **kw):
        seen["band_region"] = kw.get("band_region")
        seen["localize"] = kw.get("localize")
        return regions, ["match_boundary"]

    monkeypatch.setattr(
        "allaganeye.video.scorebar.filter_blackouts_with_scorebar", fake_filter
    )
    monkeypatch.setattr(
        _det,
        "_filter_and_extract_segments",
        lambda *a, **k: [{"start": 0.0, "end": 9.0}],
    )

    out = _det._detect_masked_fallback(
        _det.Path("x.mp4"),
        duration_hint=600.0,
        sample_interval=3.0,
        blackout_threshold=15.0,
        min_match_duration=300.0,
        min_blackout_duration=3.0,
        use_gpu=False,
        workers=None,
        src_resolution=(1920, 1080),
        codec="h264",
        gpu_vendor=None,
        source_fps_num=60,
        source_fps_den=1,
        source_fps=None,
        audio_hits=None,
        stats=None,
    )
    assert out == [{"start": 0.0, "end": 9.0}]
    assert seen["scan_region"] is fake_region
    assert seen["refine_region"] is fake_region
    assert seen["band_region"] is _det.FULL_FRAME
    assert seen["localize"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_detector.py -k "masked_fallback" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'masked'` / `AttributeError: ... '_detect_masked_fallback'`).

- [ ] **Step 3: Add `masked` param + gate branch to `detect_match_boundaries`**

`allaganeye/video/detector.py`、`detect_match_boundaries` の signature に `vtuber: bool = False` の直後 (line 257 付近) へ追加:

```python
masked: bool = (False,)
```

`blackout_times` を計算する箇所 (lines 397-399) の**直後**、`_group_blackout_regions` 呼び出しの**前**に gate branch を挿入:

```python
    # Masked fallback (#753 masked-OBS): when standard full-frame Pass 1 finds no
    # blackout (bright chat-mask overlays hold the average above threshold), OR
    # --masked forces it, re-detect on a mask-free region with position-
    # independent classification.  Gated by `not vtuber and (masked or not
    # blackout_times)`: OBS baselines always have >=1 blackout so `not
    # blackout_times` is False -> the standard path below runs unchanged
    # (bit-exact; spec section 3 / R1).  VTuber uses its own path.
    if not vtuber and (masked or not blackout_times):
        masked_segments = _detect_masked_fallback(
            video_path,
            duration_hint=duration_hint,
            sample_interval=sample_interval,
            blackout_threshold=blackout_threshold,
            min_match_duration=min_match_duration,
            min_blackout_duration=min_blackout_duration,
            use_gpu=use_gpu,
            workers=workers,
            src_resolution=src_resolution,
            codec=codec,
            gpu_vendor=gpu_vendor,
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
            audio_hits=audio_hits,
            stats=stats,
        )
        if masked_segments is not None:
            return masked_segments
```

- [ ] **Step 4: Implement `_detect_masked_fallback`**

`allaganeye/video/detector.py`、`detect_match_boundaries` の直後に追加 (標準 path の scan/refine/classify を**意図的に複製** — 標準 path body を触らず隔離するため。既存 factored helper は呼ぶ):

```python
def _detect_masked_fallback(
    video_path: Path,
    *,
    duration_hint: float,
    sample_interval: float,
    blackout_threshold: float,
    min_match_duration: float,
    min_blackout_duration: float,
    use_gpu: bool,
    workers: int | None,
    src_resolution: tuple[int, int] | None,
    codec: str | None,
    gpu_vendor: str | None,
    source_fps_num: int | None,
    source_fps_den: int | None,
    source_fps: float | None,
    audio_hits: Sequence[BgmHit] | None,
    stats: DetectionStats | None,
) -> list[MatchBoundary] | None:
    """Masked-OBS detection: region-aware Pass 1/2 + localize classification.

    Returns segments, or ``None`` when no mask-free region is found (caller falls
    through to the standard single-segment result).  Deliberately duplicates the
    standard Pass1/Pass2/classify sequence (calling the same factored helpers)
    rather than sharing a core, so the standard OBS path is structurally
    unchanged (bit-exact mandate; spec section 3 / R1).  Uses ``band_region=
    FULL_FRAME`` + ``localize=True`` (full-frame position-independent scorebar;
    v2 absolute coords FN on ultrawide, spec section 5).  No trailing-drop:
    ``_drop_post_match_trailing`` probes v2 absolute coords which FN on
    ultrawide (same rationale as the VTuber gate, line 478).
    """
    region = _resolve_masked_region(video_path, duration_hint, workers)
    if region.is_full_frame():
        return None  # no mask region found -> defer to the standard result

    if use_gpu:
        from allaganeye.video.gpu_detector import scan_gpu

        try:
            results = scan_gpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                None,
                codec=codec,
                vendor=gpu_vendor,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                region=region,
            )
        except VideoProcessingError:
            results = _scan_cpu(
                video_path,
                duration_hint,
                sample_interval,
                blackout_threshold,
                workers,
                None,
                source_fps_num=source_fps_num,
                source_fps_den=source_fps_den,
                source_fps=source_fps,
                region=region,
            )
    else:
        results = _scan_cpu(
            video_path,
            duration_hint,
            sample_interval,
            blackout_threshold,
            workers,
            None,
            source_fps_num=source_fps_num,
            source_fps_den=source_fps_den,
            source_fps=source_fps,
            region=region,
        )

    pass1_blackout_threshold = blackout_threshold + _BLACKOUT_THRESHOLD_UPPER_MARGIN
    blackout_times = sorted(
        t for t, b in results.items() if b < pass1_blackout_threshold
    )
    blackout_regions = _group_blackout_regions(blackout_times, sample_interval)
    blackout_regions = _expand_regions_with_transitions(
        blackout_regions, results, sample_interval, _TRANSITION_THRESHOLD
    )
    if _ENABLE_BORDERLINE_REFINEMENT:
        borderline_regions = _borderline_pseudo_regions(
            results, blackout_threshold, duration_hint
        )
        if borderline_regions:
            blackout_regions = _merge_regions(
                blackout_regions + borderline_regions, sample_interval
            )

    refined_regions = _refine_blackout_regions(
        video_path,
        blackout_regions,
        blackout_threshold,
        duration_hint,
        workers,
        region=region,
    )

    classifications: list[str] | None = None
    if src_resolution is not None:
        from allaganeye.video.scorebar import filter_blackouts_with_scorebar

        height = _scaled_height(src_resolution[0], src_resolution[1])
        refined_regions, classifications = filter_blackouts_with_scorebar(
            video_path,
            refined_regions,
            duration_hint,
            height,
            workers,
            band_region=FULL_FRAME,
            localize=True,
            audio_hits=audio_hits,
            stats=stats,
        )

    effective_min = min(min_blackout_duration, _REFINED_MIN_BLACKOUT)
    return _filter_and_extract_segments(
        refined_regions,
        duration_hint,
        min_match_duration,
        effective_min,
        classifications=classifications,
        stats=stats,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_detector.py -k "masked_fallback" -v`
Expected: PASS (5 tests)。

- [ ] **Step 6: Run the full detector + scorebar suite (no regression)**

Run: `pytest tests/test_detector.py tests/test_scorebar.py tests/test_l3_phase2_parity.py -q`
Expected: PASS (既存 detect/parity の bit-exact unit が green)。

- [ ] **Step 7: Commit**

```bash
git add allaganeye/video/detector.py tests/test_detector.py
git commit -m "feat(l3): masked fallback 本体 + 0-blackout gate branch (隔離経路, masked-OBS A5)"
```

---

## Task 6: CLI / config plumbing (`--masked` / `--vtuber` hidden)

`SplitConfig.masked` を追加し、`--masked` CLI option (split + detect) を配線、`--vtuber` を hidden 化、両者排他にする。

**Files:**

- Modify: `allaganeye/config.py`
- Modify: `allaganeye/cli.py`
- Modify: `allaganeye/commands/split_matches.py:749-770`
- Test: `tests/test_config.py` / `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py` に追加:

```python
from allaganeye.config import SplitConfig


def test_split_config_masked_defaults_false():
    assert SplitConfig().masked is False
```

`tests/test_cli.py` に追加 (既存の CliRunner / `app` import パターンに合わせる):

```python
def test_split_masked_flag_sets_config(monkeypatch, tmp_path):
    import allaganeye.commands.split_matches as sm

    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    captured = {}
    monkeypatch.setattr(
        sm, "run_split", lambda vp, cfg, **k: captured.update(masked=cfg.masked)
    )
    from allaganeye.cli import app
    from typer.testing import CliRunner

    res = CliRunner().invoke(app, ["split", str(video), "--masked", "--dry-run"])
    assert res.exit_code == 0
    assert captured.get("masked") is True


def test_split_vtuber_and_masked_mutually_exclusive(tmp_path):
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    from allaganeye.cli import app
    from typer.testing import CliRunner

    res = CliRunner().invoke(app, ["split", str(video), "--vtuber", "--masked"])
    assert res.exit_code != 0
    assert (
        "mutually exclusive" in res.stdout.lower() or "exclusive" in res.stdout.lower()
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -k masked tests/test_cli.py -k "masked or mutually" -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'masked'` / mutex 未実装)。

- [ ] **Step 3: Add `SplitConfig.masked`**

`allaganeye/config.py`、`vtuber: bool = False` (line 24) の直後に追加:

```python
    masked: bool = False
```

- [ ] **Step 4: Add `--masked` option + hide `--vtuber` + mutex (split command)**

`allaganeye/cli.py` の `split` command で、`--vtuber` Option (lines 152-159) を `hidden=True` 付きに変更し、直後に `--masked` を追加:

```python
vtuber: Annotated[
    bool,
    typer.Option(
        "--vtuber",
        help="(experimental) VTuber recording (game inset): scorebar-band "
        "anchor detection. Under-detects irregular transitions; deferred (#480).",
        hidden=True,
    ),
] = (False,)
masked: Annotated[
    bool,
    typer.Option(
        "--masked",
        help="Masked recording: a chat-hiding image is composited over the "
        "full screen. Auto-detects a mask-free region and re-detects; this "
        "flag forces that path even when some blackouts are found.",
    ),
] = (False,)
```

mutual-exclusion チェック群 (lines 178-194 付近、`if gpu and no_gpu:` の近く) に追加:

```python
        if vtuber and masked:
            raise ConfigValidationError("--vtuber and --masked are mutually exclusive")
```

`split` の 2 つの `SplitConfig(...)` 構築 (from_metadata path line 211-223、通常 path line 239-252) それぞれの `vtuber=vtuber,` 直後に `masked=masked,` を追加。

- [ ] **Step 5: Add `--masked` + hide `--vtuber` + mutex (detect command)**

`allaganeye/cli.py` の `detect` command でも同様に: `--vtuber` Option (lines 332-339) に `hidden=True` を付け、直後に上記と同じ `--masked` Annotated option を追加。detect の mutex チェック箇所に `if vtuber and masked: raise ConfigValidationError(...)` を追加。`SplitConfig(...)` 構築 (line ~396-409) の `vtuber=vtuber,` 直後に `masked=masked,` を追加。

- [ ] **Step 6: Thread `masked` into `detect_kwargs`**

`allaganeye/commands/split_matches.py`、`_run_detection` の `detect_kwargs` (line 759 `"vtuber": config.vtuber,` の直後) に追加:

```python
        # L3 masked-OBS (#753): chat-mask overlay -> mask-free region fallback.
        # False (default) only auto-triggers on 0-blackout; True forces it.
        "masked": config.masked,
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_config.py tests/test_cli.py -q`
Expected: PASS (新規 + 既存 CLI/config 全て green、`--vtuber` は hidden でも機能継続)。

- [ ] **Step 8: Commit**

```bash
git add allaganeye/config.py allaganeye/cli.py allaganeye/commands/split_matches.py tests/test_config.py tests/test_cli.py
git commit -m "feat(l3): --masked CLI flag 配線 + --vtuber hidden 化 + 排他 (masked-OBS A6)"
```

---

## Task 7: 検証ゲート (unit / lint / bit-exact baseline / 実機 acceptance)

**Files:** (コード変更なし。ゲート実行のみ)

- [ ] **Step 1: 全 unit + lint + 型チェック**

Run (worktree ルートで):

```bash
ruff check .
ruff format --check .
pyright
pytest -q
```

Expected: 全 PASS (slow マーカー除外、1370+ tests)。失敗があれば該当タスクに戻って修正。

- [ ] **Step 2: markdownlint (新規 plan/doc)**

Run: `bash scripts/check-markdownlint.sh`
Expected: PASS (本 plan を含む全 .md)。

- [ ] **Step 3: OBS bit-exact baseline gate (slow / 実機 = Idios)**

`docs/testing-guide.md` §「baseline drift の判定」に従い、OBS 5 baseline の `detect` 出力が現行と一致することを確認する (masked branch が非 trigger であることの構造確認)。timestamp churn (detected_at / generated_at) は非意味的 → grep 除外で output-neutral 判定。

Run: `pytest -m slow -k "baseline or detector" -q` (sample video 環境)。
Expected: baseline diff なし (試合数・境界 timestamp が現行と一致)。

- [ ] **Step 4: masked サンプル acceptance (slow / 実機 = Idios)**

`E:\allaganeye-samples\20250527-29\` の 3 録画 (3440x1440 masked ultrawide) で:

```bash
allaganeye detect "E:\allaganeye-samples\20250527-29\20250527-29\2026-05-29 20-58-34.mkv" -o E:\allaganeye-samples\_masked_a_out
```

Expected: 標準 path が 0 blackout でも masked fallback が起動し、複数 match が検出される (現行の「1 match / 7h」全滅から改善)。Idios が出力動画の内容 (試合境界の妥当性) を目視確認。`--masked` 明示でも同等。CPU/GPU 双方で parity。

- [ ] **Step 5: Self-Test Report をまとめ、PR Pre-flight へ**

Iron Law 6 Pre-flight (Step 0 ハードゲート → base 同期 → 並行 PR 確認 → `/codex:adversarial-review`) を実施。machine-verified は `[x]`、実機検証 (Step 3/4 GPU・長時間・masked) は plain bullet で Self-Test Report に記載。ロジック変更 (`detector.py` / `scorebar.py`) を含むため Idios へ実機検証を `AskUserQuestion` で依頼。

---

## Self-Review (spec 突き合わせ)

**1. Spec coverage:**

| spec §/論点 | 実装タスク |
| --- | --- |
| §3 標準 path + masked fallback / §10 R1 bit-exact | Task 5 (gate branch + 隔離 `_detect_masked_fallback`) + Task 7 Step 3 baseline gate |
| §4.1 static-overlay 領域検出 (S3 精緻化 → mask-free 矩形) | Task 1 (`detect_mask_free_region`) + Task 2/3 (frame decode + orchestration) |
| §4.2 region-aware brightness (Phase 1 再利用) | Task 5 (`region=` を scan/refine に thread) |
| §4.3 localize present 分類 (Phase 2 再利用) | Task 4 (`localize` 選択子) + Task 5 (`localize=True`) |
| §4.4 起動 (0-blackout 自動 fallback + `--masked` override) | Task 5 (gate) + Task 6 (`--masked`) |
| §6 `--vtuber` hidden/experimental 化 | Task 6 |
| §6 やらないこと (partial mask 汎化 / per-pixel / GUI=B) | 範囲外 (本 plan は矩形 region + Sub-project A のみ) |
| §8 検証 (unit / bit-exact / masked acceptance / CPU-GPU parity) | Task 1-6 unit + Task 7 |

**2. Placeholder scan:** 各 code step に実コードを記載済。test rename (Task 4 Step 4) のみ grep ベースだが、対象関数を限定し置換ルールと検証 (Step 5 suite green) を明示。プレースホルダなし。

**3. Type consistency:** `CaptureRegion` / `FULL_FRAME` / `MatchBoundary` / `BgmHit` / `DetectionStats` は detector.py で import 済を使用。`detect_mask_free_region(frames) -> CaptureRegion`、`_probe_frame_gray2d(...) -> np.ndarray | None`、`_resolve_masked_region(...) -> CaptureRegion`、`_detect_masked_fallback(...) -> list[MatchBoundary] | None` で一貫。`localize` 選択子は scorebar 3 関数で統一。`detect_match_boundaries` の `vtuber`/`masked` は別 param (前者=band-anchor/trailing gate、後者=masked fallback) で混同なし。

**4. 既知の限界 (実装メモ、PR 本文に記載):**

- masked auto-fallback は標準 full-frame Pass 1 (長尺は GPU でも 19min 規模) の**後**に走るため、masked 動画では Pass 1 が実質 2 回走る。masked は稀な経路のため許容。`--masked` 明示時も標準 Pass 1 を 1 度走らせる (構造単純化のトレードオフ)。
- masked 経路では標準 `brightness_callback` が full-frame 結果で先に発火する (GUI timeline は Sub-project B が region 表示で対応)。
- mask-free 矩形が小さすぎる / 検出不能なら FULL_FRAME → fallback は None を返し標準結果 (1 segment) に縮退。ユーザーは Sub-project B の GUI 領域調整で対応 (spec §10 R2)。
