# Presence ベース検出エンジン Phase 1 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** scorebar 有無 (presence/absence) を検出信号とする match 境界検出アルゴリズムと、その精度を ground truth と突合する offline 検証ハーネスを、production 非配線の additive モジュールとして実装し、OBS 5 source で GT-accuracy gate を通す。

**Architecture:** P1 の `localize_scorebar` (1920x1080 RGB frame → `ScorebarLocalization | None`) を present/absent 信号源として再利用する。新規 `allaganeye/video/presence.py` に「純粋なアルゴリズム (debounce/segment 化・境界二分探索)」と「I/O オーケストレーション (time grid sampling)」を責務分離して配置。検証は `tests/presence_harness.py` (純粋な比較メトリクス) + slow sample-gated テストで行う。既存の brightness Pass1 (`detect_match_boundaries`) には一切手を入れない (Phase 3 でカットオーバー)。

**Tech Stack:** Python 3 / numpy / opencv-python-headless / pytest / 既存 ffmpeg probe ヘルパ (`_probe_frame_rgb_hires`)。

---

## 背景と不変条件 (実装者向け前提)

このプロジェクトは FF14 PvP「フロントライン (FL)」の長時間録画を試合単位に分割する CLI ツール。現行の検出は **brightness ベース** (暗転を検出して試合境界とする) だが、VTuber 配信のように game 画面が overlay で囲まれた録画では brightness が overlay に汚染され機能しない。

設計判断 (spec `docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md` 参照):

- **FL の scorebar** (画面上部中央の GC 紋章 3 点を含む HUD) は試合中だけ表示される。これを「試合中かどうか」の信号にする。
- `localize_scorebar(frame)` (実装済) が frame 内に scorebar を見つければ `ScorebarLocalization` を、無ければ `None` を返す。**非 None = present = 試合中**。
- scorebar は試合中に**短時間消える**ことがある (死亡時の全画面暗転・全画面 UI 等)。よって segment 化には**両方向 debounce** (短い absent gap と短い present spike を吸収) が必要。
- **Phase 1 は production に配線しない**。新モジュールは既存の検出経路から呼ばれない。CLI 出力・baseline・既存テストは一切変わらない (回帰リスクゼロ)。

**絶対に守ること:**

- 既存ファイル `allaganeye/video/detector.py` / `scorebar.py` / `commands/*.py` の**ロジックを変更しない**。`detector.py` からは関数を **import するだけ** (Phase 1 で touch するのは新規ファイルのみ)。
- TDD: 各 production 関数は**失敗するテストを先に書く** (Red → Green → Refactor)。
- このリポジトリでは bare `pytest` / `ruff` は PATH 外。**必ず `python -m pytest` / `python -m ruff` / `python -m pyright`** を使う。
- 作業ブランチは `claude/l3-p2-region-detection` (この worktree)。base への push やマージはしない。

## 再利用する既存コード (確認済みのシグネチャ)

これらは**変更せず import するだけ**:

- `allaganeye/video/detector.py`:
  - `_probe_frame_rgb_hires(video_path: Path, timestamp: float) -> bytes | None`
    1920x1080 の RGB24 raw bytes を返す。失敗時 None。`np.frombuffer(raw, dtype=np.uint8).reshape(1080, 1920, 3)` で frame 化。
  - `_SCOREBAR_V2_PROBE_WIDTH = 1920` / `_SCOREBAR_V2_PROBE_HEIGHT = 1080`
- `allaganeye/video/capture_region.py`:
  - `localize_scorebar(frame: np.ndarray) -> ScorebarLocalization | None`
    入力は (1080, 1920, 3) uint8 RGB。`ScorebarLocalization(x_left, x_right, y_top, y_bottom, confidence: float)`。
- `allaganeye/video/probe.py`:
  - `probe_video(video_path: Path) -> ProbeResult` — `result["duration"]` (float 秒) を使う。
- `tests/baselines/v0.3.0/ground-truth/obs-*.json` (5 本) — OBS の手動 GT。スキーマ:
  `{"source_file": "...", "tolerance_sec": 5, "matches": [{"index", "start_time", "end_time", "duration", "type"}]}`
- `tests/conftest.py`:
  - `sample_video_dir` fixture — `ALLAGANEYE_SAMPLE_VIDEO_DIR` 未設定なら skip。
  - `slow` marker — 動画が要るテストに付与。

## ファイル構成

| ファイル | 新規/変更 | 責務 |
| --- | --- | --- |
| `allaganeye/video/presence.py` | 新規 | presence 検出アルゴリズム。データ構造 + 純粋関数 (segment/refine) + I/O (scan/detect) |
| `tests/test_presence.py` | 新規 | presence.py の高速単体テスト (動画不要) |
| `tests/presence_harness.py` | 新規 | GT 読込 + 検出結果との比較メトリクス (純粋) + 手動実行 CLI |
| `tests/test_presence_harness.py` | 新規 | presence_harness.py の高速単体テスト (動画不要) |
| `tests/test_presence_validation.py` | 新規 | slow・sample-gated。OBS 実動画で GT-accuracy gate を assert |

**この計画では上記 5 ファイル以外を変更しない。**

---

## Task 1: データ構造とモジュール骨格

**Files:**

- Create: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` を新規作成:

```python
"""Unit tests for presence-based match detection (no video required)."""

from __future__ import annotations

from allaganeye.video.presence import PresenceMatch, PresenceSample


def test_presence_sample_fields():
    s = PresenceSample(time=12.0, present=True, confidence=0.9)
    assert s.time == 12.0
    assert s.present is True
    assert s.confidence == 0.9


def test_presence_match_fields():
    m = PresenceMatch(start=10.0, end=900.0)
    assert m.start == 10.0
    assert m.end == 900.0
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'allaganeye.video.presence'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` を新規作成:

```python
"""Presence-based match detection (scorebar present/absent as the signal).

Phase 1 of the presence-detection engine (spec
docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md).
This module is ADDITIVE and NOT wired into the production detection path;
it exists for the offline validation harness only.  The brightness-based
``detector.detect_match_boundaries`` remains the production detector until
the Phase 3 cutover.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PresenceSample:
    """One time-grid sample: whether the scorebar is present at ``time``."""

    time: float
    present: bool
    confidence: float


@dataclass(frozen=True)
class PresenceMatch:
    """A detected FL match segment in seconds (presence-based)."""

    start: float
    end: float
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): presence 検出のデータ構造 (Phase 1 Task 1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `segment_presence` — debounce + segment 化 (アルゴリズムの中核)

サンプル列 (present/absent) を試合 segment にまとめる純粋関数。`t_gap` 未満の absent gap は試合内として吸収、`t_min_match` 未満の present run は破棄。

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` の末尾に追記:

```python
from allaganeye.video.presence import segment_presence


def _samples(spec: list[tuple[float, bool]]) -> list[PresenceSample]:
    return [PresenceSample(time=t, present=p, confidence=1.0) for t, p in spec]


def test_segment_single_match():
    # present 0..900 (stride 100) -> one match
    samples = _samples([(t, True) for t in range(0, 1000, 100)])
    matches = segment_presence(samples, t_gap=30.0, t_min_match=60.0)
    assert matches == [PresenceMatch(start=0.0, end=900.0)]


def test_segment_two_matches_split_by_long_gap():
    # match A 0..200, absent 300..600 (gap 400 >= t_gap), match B 700..900
    spec = [(t, True) for t in (0, 100, 200)]
    spec += [(t, False) for t in (300, 400, 500, 600)]
    spec += [(t, True) for t in (700, 800, 900)]
    matches = segment_presence(_samples(spec), t_gap=120.0, t_min_match=60.0)
    assert matches == [
        PresenceMatch(start=0.0, end=200.0),
        PresenceMatch(start=700.0, end=900.0),
    ]


def test_segment_absorbs_short_absent_gap():
    # short absent at 300 only (gap from 200 to 400 = 200 < t_gap=300) -> merged
    spec = [(t, True) for t in (0, 100, 200)]
    spec += [(300, False)]
    spec += [(t, True) for t in (400, 500, 600)]
    matches = segment_presence(_samples(spec), t_gap=300.0, t_min_match=60.0)
    assert matches == [PresenceMatch(start=0.0, end=600.0)]


def test_segment_drops_short_present_spike():
    # isolated present spike 400..450 (duration 50 < t_min_match=60) -> dropped
    spec = [(t, False) for t in (0, 100, 200, 300)]
    spec += [(400, True), (450, True)]
    spec += [(t, False) for t in (600, 700, 800)]
    matches = segment_presence(_samples(spec), t_gap=120.0, t_min_match=60.0)
    assert matches == []


def test_segment_empty_input():
    assert segment_presence([], t_gap=30.0, t_min_match=60.0) == []
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -k segment -v`
Expected: FAIL — `ImportError: cannot import name 'segment_presence'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` の末尾に追記:

```python
def segment_presence(
    samples: Sequence[PresenceSample],
    *,
    t_gap: float,
    t_min_match: float,
) -> list[PresenceMatch]:
    """Collapse present/absent samples into match segments.

    Two-directional debounce:
    - absent gaps shorter than ``t_gap`` between two present runs are
      absorbed (treated as in-match: covers mid-match scorebar loss such
      as death blackout / full-screen UI).
    - present runs shorter than ``t_min_match`` are discarded (transient
      false positives).

    ``samples`` must be sorted by ``time`` ascending.  Returns matches with
    start/end at the first/last present sample time of each surviving run
    (boundary refinement to sub-stride precision happens separately in
    :func:`detect_matches_by_presence`).
    """
    # 1. Build present runs as mutable [start, end] pairs.
    present_runs: list[list[float]] = []
    current: list[float] | None = None
    for s in samples:
        if s.present:
            if current is None:
                current = [s.time, s.time]
            else:
                current[1] = s.time
        else:
            if current is not None:
                present_runs.append(current)
                current = None
    if current is not None:
        present_runs.append(current)

    # 2. Merge runs whose inter-run gap is shorter than t_gap.
    merged: list[list[float]] = []
    for run in present_runs:
        if merged and run[0] - merged[-1][1] < t_gap:
            merged[-1][1] = run[1]
        else:
            merged.append(list(run))

    # 3. Drop runs shorter than t_min_match; emit matches.
    return [
        PresenceMatch(start=r[0], end=r[1])
        for r in merged
        if r[1] - r[0] >= t_min_match
    ]
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): segment_presence debounce/segment 化 (Phase 1 Task 2)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `refine_boundary` — 境界の二分探索 (純粋・DI)

present/absent の遷移区間を二分探索して遷移時刻を `tol` 精度で特定する。`present_at` コールバックを注入し、動画なしで単体テスト可能にする。

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` の末尾に追記:

```python
from allaganeye.video.presence import refine_boundary


def test_refine_boundary_finds_transition_forward():
    # scorebar present for t < 500, absent for t >= 500 (match end)
    present_at = lambda t: t < 500.0
    # bracket: t_true=480 (present), t_false=520 (absent)
    edge = refine_boundary(480.0, 520.0, present_at, tol=1.0)
    assert abs(edge - 500.0) <= 1.0


def test_refine_boundary_finds_transition_backward():
    # scorebar absent for t < 300, present for t >= 300 (match start)
    present_at = lambda t: t >= 300.0
    # bracket: t_true=320 (present), t_false=280 (absent)
    edge = refine_boundary(320.0, 280.0, present_at, tol=1.0)
    assert abs(edge - 300.0) <= 1.0


def test_refine_boundary_respects_tolerance():
    present_at = lambda t: t < 500.0
    edge = refine_boundary(480.0, 520.0, present_at, tol=0.1)
    assert abs(edge - 500.0) <= 0.1
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -k refine -v`
Expected: FAIL — `ImportError: cannot import name 'refine_boundary'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` の `segment_presence` の後に追記:

```python
def refine_boundary(
    t_true: float,
    t_false: float,
    present_at: Callable[[float], bool],
    *,
    tol: float,
) -> float:
    """Binary-search the present<->absent transition between two times.

    Precondition: ``present_at(t_true)`` is True and ``present_at(t_false)``
    is False.  ``t_true`` and ``t_false`` may be in either order (forward =
    match end, backward = match start).  Returns the midpoint of the final
    bracket, accurate to within ``tol`` seconds.
    """
    lo_true = t_true
    hi_false = t_false
    while abs(lo_true - hi_false) > tol:
        mid = (lo_true + hi_false) / 2.0
        if present_at(mid):
            lo_true = mid
        else:
            hi_false = mid
    return (lo_true + hi_false) / 2.0
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): refine_boundary 二分探索 (Phase 1 Task 3)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `localize_present_at` — frame 取得 → localize ブリッジ

実動画の時刻 `t` から hi-res frame を取り出し、`localize_scorebar` にかけて `PresenceSample` を返す。既存ヘルパ 2 つを mock して高速テストする。

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` の末尾に追記:

```python
import numpy as np

from allaganeye.video.capture_region import ScorebarLocalization


def test_localize_present_at_present(monkeypatch):
    import allaganeye.video.presence as presence

    fake_frame_bytes = (np.zeros((1080, 1920, 3), dtype=np.uint8)).tobytes()
    monkeypatch.setattr(
        presence, "_probe_frame_rgb_hires", lambda vp, t: fake_frame_bytes
    )
    monkeypatch.setattr(
        presence,
        "localize_scorebar",
        lambda frame: ScorebarLocalization(
            x_left=600, x_right=1300, y_top=20, y_bottom=65, confidence=0.8
        ),
    )
    from pathlib import Path

    sample = presence.localize_present_at(Path("dummy.mkv"), 123.0)
    assert sample.time == 123.0
    assert sample.present is True
    assert sample.confidence == 0.8


def test_localize_present_at_absent(monkeypatch):
    import allaganeye.video.presence as presence

    fake_frame_bytes = (np.zeros((1080, 1920, 3), dtype=np.uint8)).tobytes()
    monkeypatch.setattr(
        presence, "_probe_frame_rgb_hires", lambda vp, t: fake_frame_bytes
    )
    monkeypatch.setattr(presence, "localize_scorebar", lambda frame: None)
    from pathlib import Path

    sample = presence.localize_present_at(Path("dummy.mkv"), 50.0)
    assert sample.present is False
    assert sample.confidence == 0.0


def test_localize_present_at_probe_failure(monkeypatch):
    import allaganeye.video.presence as presence

    monkeypatch.setattr(presence, "_probe_frame_rgb_hires", lambda vp, t: None)
    from pathlib import Path

    sample = presence.localize_present_at(Path("dummy.mkv"), 7.0)
    assert sample.present is False
    assert sample.confidence == 0.0
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -k localize_present_at -v`
Expected: FAIL — `AttributeError: ... has no attribute 'localize_present_at'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` の import 群に追記 (ファイル冒頭の `from dataclasses import dataclass` の下):

```python
from pathlib import Path

import numpy as np

from allaganeye.video.capture_region import localize_scorebar
from allaganeye.video.detector import (
    _SCOREBAR_V2_PROBE_HEIGHT,
    _SCOREBAR_V2_PROBE_WIDTH,
    _probe_frame_rgb_hires,
)
```

そしてファイル末尾に関数を追記:

```python
def localize_present_at(video_path: Path, timestamp: float) -> PresenceSample:
    """Probe one hi-res frame and report scorebar presence at ``timestamp``.

    Bridges the production frame source (``_probe_frame_rgb_hires``, 1920x1080
    RGB24) and the P1 localizer (``localize_scorebar``).  Probe failure or
    a None localization both yield ``present=False`` (safe absent).
    """
    raw = _probe_frame_rgb_hires(video_path, timestamp)
    if raw is None:
        return PresenceSample(time=timestamp, present=False, confidence=0.0)
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(
        _SCOREBAR_V2_PROBE_HEIGHT, _SCOREBAR_V2_PROBE_WIDTH, 3
    )
    loc = localize_scorebar(frame)
    if loc is None:
        return PresenceSample(time=timestamp, present=False, confidence=0.0)
    return PresenceSample(time=timestamp, present=True, confidence=loc.confidence)
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし (private import の `_probe_frame_rgb_hires` 等で ruff 警告が出る場合は `# noqa` ではなく、これらが同 package 内 import である点を確認。問題が出たら `allaganeye.video.detector` からの import はそのまま許容される)

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): localize_present_at frame→localize ブリッジ (Phase 1 Task 4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `scan_presence` — time grid サンプリング (I/O オーケストレーション)

`0..duration` を `stride` 間隔で走査し、各時刻で `sample_fn` を並列実行して `PresenceSample` 列を返す。`sample_fn` を注入して高速テストする。

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` の末尾に追記:

```python
from allaganeye.video.presence import scan_presence


def test_scan_presence_grid_and_order():
    from pathlib import Path

    # synthetic sample_fn: present for 200 <= t < 500
    def sample_fn(t: float) -> PresenceSample:
        return PresenceSample(time=t, present=(200.0 <= t < 500.0), confidence=1.0)

    samples = scan_presence(
        Path("dummy.mkv"), duration=600.0, stride=100.0, workers=2, sample_fn=sample_fn
    )
    # times must be sorted and cover 0,100,...,600
    assert [s.time for s in samples] == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    assert [s.present for s in samples] == [
        False, False, True, True, True, False, False
    ]
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -k scan_presence -v`
Expected: FAIL — `ImportError: cannot import name 'scan_presence'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` の import 群に追記:

```python
from concurrent.futures import ThreadPoolExecutor
```

ファイル末尾に追記:

```python
def _grid_timestamps(duration: float, stride: float) -> list[float]:
    """Inclusive 0..duration grid at ``stride`` spacing (duration endpoint kept)."""
    if stride <= 0:
        raise ValueError("stride must be > 0")
    n = int(duration // stride)
    times = [round(i * stride, 6) for i in range(n + 1)]
    if not times or times[-1] < duration:
        times.append(round(duration, 6))
    return times


def scan_presence(
    video_path: Path,
    duration: float,
    *,
    stride: float,
    workers: int,
    sample_fn: Callable[[float], PresenceSample] | None = None,
) -> list[PresenceSample]:
    """Sample scorebar presence across the whole video on a uniform grid.

    ``sample_fn`` maps a timestamp to a :class:`PresenceSample`; it defaults
    to :func:`localize_present_at` bound to ``video_path`` (the production
    path).  Tests inject a synthetic ``sample_fn`` to stay fast.  Results are
    returned sorted by time ascending.
    """
    if sample_fn is None:
        def sample_fn(t: float) -> PresenceSample:  # noqa: E306
            return localize_present_at(video_path, t)

    times = _grid_timestamps(duration, stride)
    results: dict[float, PresenceSample] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(sample_fn, t): t for t in times}
        for fut in futures:
            sample = fut.result()
            results[futures[fut]] = sample
    return [results[t] for t in times]
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし (`def sample_fn` の再代入で pyright が文句を言う場合は、内部名を `sample_fn = _default` のように別関数で定義して回避: 下記参照)

> pyright が `sample_fn` 再代入を嫌う場合の代替実装:
>
> ```python
>     resolved_fn = sample_fn
>     if resolved_fn is None:
>         resolved_fn = lambda t: localize_present_at(video_path, t)  # noqa: E731
> ```
>
> 以降 `resolved_fn` を使う。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): scan_presence time-grid サンプリング (Phase 1 Task 5)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `detect_matches_by_presence` — トップレベル統合 (scan → segment → refine)

scan で得たサンプルを segment 化し、各 match の start/end を 1 stride 幅の bracket で二分探索して精緻化する。

**Files:**

- Modify: `allaganeye/video/presence.py`
- Test: `tests/test_presence.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence.py` の末尾に追記:

```python
from allaganeye.video.presence import detect_matches_by_presence


def test_detect_matches_by_presence_end_to_end(monkeypatch):
    import allaganeye.video.presence as presence
    from pathlib import Path

    # Ground physics: scorebar present for 250 <= t < 740.
    def present_phys(t: float) -> bool:
        return 250.0 <= t < 740.0

    monkeypatch.setattr(
        presence,
        "localize_present_at",
        lambda vp, t: PresenceSample(time=t, present=present_phys(t), confidence=1.0),
    )

    matches = detect_matches_by_presence(
        Path("dummy.mkv"),
        duration=1000.0,
        stride=100.0,
        t_gap=120.0,
        t_min_match=60.0,
        tol=1.0,
        workers=2,
    )
    assert len(matches) == 1
    # coarse run is 300..700 (grid); refine pulls start->250, end->740
    assert abs(matches[0].start - 250.0) <= 1.0
    assert abs(matches[0].end - 740.0) <= 1.0


def test_detect_matches_present_at_video_edges(monkeypatch):
    import allaganeye.video.presence as presence
    from pathlib import Path

    # present for the entire video -> match spans [0, duration], no refine
    monkeypatch.setattr(
        presence,
        "localize_present_at",
        lambda vp, t: PresenceSample(time=t, present=True, confidence=1.0),
    )
    matches = detect_matches_by_presence(
        Path("dummy.mkv"),
        duration=500.0,
        stride=100.0,
        t_gap=120.0,
        t_min_match=60.0,
        tol=1.0,
        workers=2,
    )
    assert matches == [PresenceMatch(start=0.0, end=500.0)]
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence.py -k detect_matches -v`
Expected: FAIL — `ImportError: cannot import name 'detect_matches_by_presence'`

- [ ] **Step 3: 最小実装**

`allaganeye/video/presence.py` の末尾に追記:

```python
def detect_matches_by_presence(
    video_path: Path,
    duration: float,
    *,
    stride: float,
    t_gap: float,
    t_min_match: float,
    tol: float,
    workers: int,
) -> list[PresenceMatch]:
    """Top-level presence detector: scan -> segment -> refine boundaries.

    1. ``scan_presence`` samples the whole video on a ``stride`` grid.
    2. ``segment_presence`` debounces and yields coarse matches (boundaries
       at sample times).
    3. each coarse boundary is refined within a one-stride bracket using
       ``refine_boundary``.  Matches touching the video edges (t<=0 or
       t>=duration within one stride) keep the edge unrefined.
    """
    samples = scan_presence(
        video_path, duration, stride=stride, workers=workers
    )
    coarse = segment_presence(samples, t_gap=t_gap, t_min_match=t_min_match)

    def present_at(t: float) -> bool:
        return localize_present_at(video_path, t).present

    refined: list[PresenceMatch] = []
    for m in coarse:
        if m.start - stride < 0.0:
            start = 0.0
        else:
            start = refine_boundary(m.start, m.start - stride, present_at, tol=tol)
        if m.end + stride > duration:
            end = duration
        else:
            end = refine_boundary(m.end, m.end + stride, present_at, tol=tol)
        refined.append(PresenceMatch(start=start, end=end))
    return refined
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check allaganeye/video/presence.py tests/test_presence.py && python -m ruff format --check allaganeye/video/presence.py tests/test_presence.py && python -m pyright allaganeye/video/presence.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add allaganeye/video/presence.py tests/test_presence.py
git commit -m "feat(l3): detect_matches_by_presence 統合 (Phase 1 Task 6)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: ハーネス — GT 読込とデータ構造

GT JSON (OBS/VTuber 共通スキーマ) を読み込む純粋関数。

**Files:**

- Create: `tests/presence_harness.py`
- Test: `tests/test_presence_harness.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence_harness.py` を新規作成:

```python
"""Unit tests for the presence validation harness (no video required)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.presence_harness import GroundTruth, GroundTruthMatch, load_ground_truth


def test_load_ground_truth(tmp_path: Path):
    gt_file = tmp_path / "gt.json"
    gt_file.write_text(
        json.dumps(
            {
                "source_file": "20260116/rec.mkv",
                "tolerance_sec": 5,
                "matches": [
                    {"index": 1, "start_time": 49, "end_time": 1054},
                    {"index": 2, "start_time": 1256, "end_time": 2178},
                ],
            }
        ),
        encoding="utf-8",
    )
    gt = load_ground_truth(gt_file)
    assert isinstance(gt, GroundTruth)
    assert gt.source_file == "20260116/rec.mkv"
    assert gt.tolerance_sec == 5.0
    assert gt.matches == [
        GroundTruthMatch(start=49.0, end=1054.0),
        GroundTruthMatch(start=1256.0, end=2178.0),
    ]
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence_harness.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.presence_harness'`

- [ ] **Step 3: 最小実装**

`tests/presence_harness.py` を新規作成:

```python
"""Offline validation harness for presence-based detection (Phase 1).

Compares presence-detected match segments against ground-truth annotations
(OBS baselines + VTuber manual GT) and reports matched / missed / spurious
counts and boundary errors.  Pure comparison logic lives here so it can be
unit-tested without video; the slow end-to-end runs live in
``tests/test_presence_validation.py``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GroundTruthMatch:
    """A ground-truth FL match interval in seconds."""

    start: float
    end: float


@dataclass(frozen=True)
class GroundTruth:
    """Parsed ground-truth file."""

    source_file: str
    tolerance_sec: float
    matches: list[GroundTruthMatch]


def load_ground_truth(path: Path) -> GroundTruth:
    """Load a ground-truth JSON (OBS / VTuber shared schema)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [
        GroundTruthMatch(start=float(m["start_time"]), end=float(m["end_time"]))
        for m in data["matches"]
    ]
    return GroundTruth(
        source_file=str(data["source_file"]),
        tolerance_sec=float(data["tolerance_sec"]),
        matches=matches,
    )
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence_harness.py -v`
Expected: PASS

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check tests/presence_harness.py tests/test_presence_harness.py && python -m ruff format --check tests/presence_harness.py tests/test_presence_harness.py && python -m pyright tests/presence_harness.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add tests/presence_harness.py tests/test_presence_harness.py
git commit -m "feat(l3): 検証ハーネス GT 読込 (Phase 1 Task 7)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: ハーネス — `compare_segments` メトリクス (純粋)

検出 segment と GT を tolerance 付きで突合し、matched / missed / spurious と境界誤差を返す。

**Files:**

- Modify: `tests/presence_harness.py`
- Test: `tests/test_presence_harness.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence_harness.py` の末尾に追記:

```python
from allaganeye.video.presence import PresenceMatch
from tests.presence_harness import ComparisonResult, compare_segments


def _gt(pairs):
    return [GroundTruthMatch(start=a, end=b) for a, b in pairs]


def test_compare_all_matched_within_tolerance():
    detected = [PresenceMatch(50.0, 1056.0), PresenceMatch(1257.0, 2176.0)]
    gt = _gt([(49.0, 1054.0), (1256.0, 2178.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert isinstance(res, ComparisonResult)
    assert res.matched == 2
    assert res.missed == 0
    assert res.spurious == 0
    assert res.max_boundary_error <= 2.0


def test_compare_missed_match():
    detected = [PresenceMatch(50.0, 1056.0)]
    gt = _gt([(49.0, 1054.0), (1256.0, 2178.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 1
    assert res.missed == 1
    assert res.spurious == 0


def test_compare_spurious_match():
    detected = [PresenceMatch(50.0, 1056.0), PresenceMatch(4000.0, 4500.0)]
    gt = _gt([(49.0, 1054.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 1
    assert res.missed == 0
    assert res.spurious == 1


def test_compare_boundary_outside_tolerance_is_not_matched():
    # end off by 40s (> tol) -> not a match -> missed + spurious
    detected = [PresenceMatch(50.0, 1100.0)]
    gt = _gt([(49.0, 1054.0)])
    res = compare_segments(detected, gt, tolerance=5.0)
    assert res.matched == 0
    assert res.missed == 1
    assert res.spurious == 1
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence_harness.py -k compare -v`
Expected: FAIL — `ImportError: cannot import name 'compare_segments'`

- [ ] **Step 3: 最小実装**

`tests/presence_harness.py` の import 群に追記:

```python
from allaganeye.video.presence import PresenceMatch
```

ファイル末尾に追記:

```python
@dataclass(frozen=True)
class ComparisonResult:
    """Outcome of comparing detected matches against ground truth."""

    matched: int
    missed: int
    spurious: int
    boundary_errors: list[float]

    @property
    def max_boundary_error(self) -> float:
        return max(self.boundary_errors) if self.boundary_errors else 0.0


def compare_segments(
    detected: Sequence[PresenceMatch],
    gt: Sequence[GroundTruthMatch],
    *,
    tolerance: float,
) -> ComparisonResult:
    """Greedy-match detected segments to GT within ``tolerance`` seconds.

    A detected segment matches a GT match iff both its start and end are
    within ``tolerance`` of the GT start/end.  Each GT and each detected
    segment is used at most once.  Unmatched GT -> missed; unmatched
    detected -> spurious.  ``boundary_errors`` holds, for every matched
    pair, the start error and the end error (seconds).
    """
    used_detected: set[int] = set()
    matched = 0
    boundary_errors: list[float] = []

    for g in gt:
        best_idx: int | None = None
        best_err: float | None = None
        for i, d in enumerate(detected):
            if i in used_detected:
                continue
            start_err = abs(d.start - g.start)
            end_err = abs(d.end - g.end)
            if start_err <= tolerance and end_err <= tolerance:
                worst = max(start_err, end_err)
                if best_err is None or worst < best_err:
                    best_err = worst
                    best_idx = i
        if best_idx is not None:
            used_detected.add(best_idx)
            matched += 1
            boundary_errors.append(abs(detected[best_idx].start - g.start))
            boundary_errors.append(abs(detected[best_idx].end - g.end))

    missed = len(gt) - matched
    spurious = len(detected) - len(used_detected)
    return ComparisonResult(
        matched=matched,
        missed=missed,
        spurious=spurious,
        boundary_errors=boundary_errors,
    )
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence_harness.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check tests/presence_harness.py tests/test_presence_harness.py && python -m ruff format --check tests/presence_harness.py tests/test_presence_harness.py && python -m pyright tests/presence_harness.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add tests/presence_harness.py tests/test_presence_harness.py
git commit -m "feat(l3): compare_segments 突合メトリクス (Phase 1 Task 8)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: ハーネス CLI — 手動実行エントリポイント

Phase 2 の閾値校正用に、動画 + GT + パラメータを受けてメトリクスを表示する `main()` を追加する。テストは引数パースのみ高速検証。

**Files:**

- Modify: `tests/presence_harness.py`
- Test: `tests/test_presence_harness.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_presence_harness.py` の末尾に追記:

```python
from tests.presence_harness import build_arg_parser


def test_build_arg_parser_defaults():
    parser = build_arg_parser()
    args = parser.parse_args(
        ["--video", "v.mkv", "--ground-truth", "gt.json"]
    )
    assert args.video == "v.mkv"
    assert args.ground_truth == "gt.json"
    assert args.stride == 4.0
    assert args.t_gap == 30.0
    assert args.t_min_match == 120.0
    assert args.tol == 1.0
    assert args.workers == 8


def test_build_arg_parser_overrides():
    parser = build_arg_parser()
    args = parser.parse_args(
        [
            "--video", "v.mkv",
            "--ground-truth", "gt.json",
            "--stride", "3",
            "--t-gap", "45",
            "--t-min-match", "90",
            "--tol", "0.5",
            "--workers", "16",
        ]
    )
    assert args.stride == 3.0
    assert args.t_gap == 45.0
    assert args.t_min_match == 90.0
    assert args.tol == 0.5
    assert args.workers == 16
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `python -m pytest tests/test_presence_harness.py -k arg_parser -v`
Expected: FAIL — `ImportError: cannot import name 'build_arg_parser'`

- [ ] **Step 3: 最小実装**

`tests/presence_harness.py` の import 群に追記:

```python
import argparse
```

ファイル末尾に追記 (暫定パラメータは spec §4.6 の暫定値。`t_gap=30 / t_min_match=120` は現行 `min_match_duration=300` より保守的に小さめ、Phase 2 で校正):

```python
def build_arg_parser() -> argparse.ArgumentParser:
    """CLI for manual harness runs (Phase 2 threshold calibration)."""
    p = argparse.ArgumentParser(description="Presence detection validation harness")
    p.add_argument("--video", required=True, help="Path to source video")
    p.add_argument("--ground-truth", required=True, help="Path to ground-truth JSON")
    p.add_argument("--stride", type=float, default=4.0, help="Coarse grid stride (s)")
    p.add_argument("--t-gap", type=float, default=30.0, help="Min absent gap = boundary (s)")
    p.add_argument(
        "--t-min-match", type=float, default=120.0, help="Min present run = match (s)"
    )
    p.add_argument("--tol", type=float, default=1.0, help="Refinement tolerance (s)")
    p.add_argument("--workers", type=int, default=8, help="Parallel probe workers")
    return p


def main(argv: list[str] | None = None) -> int:
    """Run presence detection on one video and print metrics vs ground truth."""
    from allaganeye.video.presence import detect_matches_by_presence
    from allaganeye.video.probe import probe_video

    args = build_arg_parser().parse_args(argv)
    video = Path(args.video)
    gt = load_ground_truth(Path(args.ground_truth))
    duration = float(probe_video(video)["duration"])

    detected = detect_matches_by_presence(
        video,
        duration,
        stride=args.stride,
        t_gap=args.t_gap,
        t_min_match=args.t_min_match,
        tol=args.tol,
        workers=args.workers,
    )
    res = compare_segments(detected, gt.matches, tolerance=gt.tolerance_sec)
    print(f"source        : {gt.source_file}")
    print(f"detected      : {len(detected)} matches")
    print(f"ground truth  : {len(gt.matches)} matches (tol {gt.tolerance_sec}s)")
    print(f"matched       : {res.matched}")
    print(f"missed        : {res.missed}")
    print(f"spurious      : {res.spurious}")
    print(f"max boundary err: {res.max_boundary_error:.2f}s")
    return 0 if (res.missed == 0 and res.spurious == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: テストを実行して通過を確認**

Run: `python -m pytest tests/test_presence_harness.py -v`
Expected: PASS (全テスト)

- [ ] **Step 5: Lint / 型チェック**

Run: `python -m ruff check tests/presence_harness.py tests/test_presence_harness.py && python -m ruff format --check tests/presence_harness.py tests/test_presence_harness.py && python -m pyright tests/presence_harness.py`
Expected: エラーなし

- [ ] **Step 6: Commit**

```bash
git add tests/presence_harness.py tests/test_presence_harness.py
git commit -m "feat(l3): ハーネス CLI エントリポイント (Phase 1 Task 9)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: OBS 検証テスト (slow・sample-gated) — GT-accuracy gate

OBS 5 source の実動画で `detect_matches_by_presence` を回し、手動 GT に対して **missed/spurious ゼロ** と **境界誤差 ≤ tolerance** を assert する。これが Phase 1 の合格ゲート。

> このテストは動画が要るため `ALLAGANEYE_SAMPLE_VIDEO_DIR` 設定環境 (Idios のマシン) でのみ実行される。CI では skip される。**閾値 (stride/t_gap/t_min_match/tol) は暫定値で書き、実行して通らなければ Phase 1 完了報告時に Idios と校正する** (spec §4.6 / Task 完了後の実機検証 trigger)。

**Files:**

- Create: `tests/test_presence_validation.py`

- [ ] **Step 1: テストを書く (このタスクは TDD の「実機ゲート」なので、test = 実行可能な検証スクリプト)**

`tests/test_presence_validation.py` を新規作成:

```python
"""Slow, sample-gated OBS validation for presence detection (Phase 1 gate).

Runs the presence detector on each OBS source that has a manual ground-truth
file and asserts the GT-accuracy gate: zero missed, zero spurious, and all
boundary errors within the GT tolerance.  Requires ALLAGANEYE_SAMPLE_VIDEO_DIR.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from allaganeye.video.presence import detect_matches_by_presence
from allaganeye.video.probe import probe_video
from tests.presence_harness import compare_segments, load_ground_truth

_GT_DIR = Path(__file__).parent / "baselines" / "v0.3.0" / "ground-truth"

# Provisional thresholds (spec section 4.6). Calibrate with Idios if a gate
# fails on real footage during Phase 1 sign-off.
_STRIDE = 4.0
_T_GAP = 30.0
_T_MIN_MATCH = 120.0
_TOL = 1.0
_WORKERS = 8


def _obs_gt_files() -> list[Path]:
    return sorted(_GT_DIR.glob("obs-*.json"))


@pytest.mark.slow
@pytest.mark.parametrize("gt_file", _obs_gt_files(), ids=lambda p: p.stem)
def test_obs_presence_gt_accuracy(gt_file: Path, sample_video_dir: Path):
    gt = load_ground_truth(gt_file)
    video = sample_video_dir / gt.source_file
    if not video.exists():
        pytest.skip(f"sample video not found: {video}")

    duration = float(probe_video(video)["duration"])
    detected = detect_matches_by_presence(
        video,
        duration,
        stride=_STRIDE,
        t_gap=_T_GAP,
        t_min_match=_T_MIN_MATCH,
        tol=_TOL,
        workers=_WORKERS,
    )
    res = compare_segments(detected, gt.matches, tolerance=gt.tolerance_sec)

    assert res.missed == 0, f"{gt_file.stem}: missed {res.missed} matches"
    assert res.spurious == 0, f"{gt_file.stem}: {res.spurious} spurious matches"
    assert res.max_boundary_error <= gt.tolerance_sec, (
        f"{gt_file.stem}: boundary error {res.max_boundary_error:.1f}s "
        f"> tol {gt.tolerance_sec}s"
    )
```

- [ ] **Step 2: collection が壊れていないことを確認 (動画なし環境でも collection は通る)**

Run: `python -m pytest tests/test_presence_validation.py -v`
Expected: 5 件が **skipped** (ALLAGANEYE_SAMPLE_VIDEO_DIR 未設定なら `sample_video_dir` fixture が skip) — collection error が出ないこと。

- [ ] **Step 3: Lint / 型チェック**

Run: `python -m ruff check tests/test_presence_validation.py && python -m ruff format --check tests/test_presence_validation.py && python -m pyright tests/test_presence_validation.py`
Expected: エラーなし

- [ ] **Step 4: Commit**

```bash
git add tests/test_presence_validation.py
git commit -m "test(l3): OBS presence GT-accuracy gate (slow, Phase 1 Task 10)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 5: (Idios 実機検証 trigger) 実動画で slow テストを実行**

> このステップは Idios のマシン (ALLAGANEYE_SAMPLE_VIDEO_DIR 設定済) で行う。Phase 1 の受け入れ判定。
>
> Run: `python -m pytest tests/test_presence_validation.py -m slow -v`
> Expected: 5 source すべて PASS。**失敗時**は missed/spurious/境界誤差を記録し、閾値 (`_STRIDE`/`_T_GAP`/`_T_MIN_MATCH`/`_TOL`) と localize recall を Idios と確認して校正 (spec §4.6 / R2)。校正は別 commit。
>
> 併せて wall-time をメモ (spec §6 性能確認)。長尺で実用外なら stride 調整を Phase 1 範囲で検討。

---

## Task 11: 全体テストと最終確認

**Files:** (変更なし — 検証のみ)

- [ ] **Step 1: 高速テスト全体を実行 (回帰がないこと)**

Run: `python -m pytest -q`
Expected: 既存テスト + 新規高速テストすべて PASS、slow は skip。**既存テストの結果が変わっていないこと** (Phase 1 は additive)。

- [ ] **Step 2: 全体 Lint / 型チェック**

Run: `python -m ruff check . && python -m ruff format --check . && python -m pyright`
Expected: エラーなし

- [ ] **Step 3: markdownlint (この計画 doc と spec)**

Run: `bash scripts/check-markdownlint.sh`
Expected: 0 errors

- [ ] **Step 4: 新モジュールが production から参照されていないことを確認 (Phase 1 非配線の担保)**

Run: `python -m pytest tests/test_detector.py tests/test_scorebar.py tests/test_detect.py -q`
Expected: 既存検出系テスト全 PASS (presence.py を import していないため影響なし)。

加えて、`allaganeye/` 配下の production コードが presence を import していないことを確認:

Run: `grep -rn "import presence\|from allaganeye.video.presence\|presence import" allaganeye/`
Expected: **0 件** (presence は tests からのみ参照される)。

- [ ] **Step 5: 最終 commit (もし未コミットの調整があれば)**

```bash
git status --short
# 差分がなければ何もしない。あれば:
git add -A && git commit -m "chore(l3): Phase 1 最終調整

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## 受け入れ条件 (Phase 1 完了判定 / 将来の issue `## 受け入れ条件` 原型)

- [ ] `allaganeye/video/presence.py` が presence (localize 非 None) + 両方向 debounce + fine refinement で match segment を返す (`detect_matches_by_presence`)。
- [ ] 高速単体テスト (動画不要): `segment_presence` / `refine_boundary` / `localize_present_at` / `scan_presence` / `detect_matches_by_presence` / `compare_segments` / `load_ground_truth` が全 PASS。
- [ ] offline 検証ハーネス (`tests/presence_harness.py`) が GT と検出結果を突合し matched/missed/spurious/境界誤差を返す。CLI (`main`) で手動実行可能。
- [ ] OBS 5 source の slow 検証テストが存在し、collection error なく skip/PASS する。
- [ ] **(実機ゲート)** Idios 環境で `tests/test_presence_validation.py -m slow` が 5 source すべて PASS (missed/spurious ゼロ、境界誤差 ≤ tolerance)。失敗時は閾値校正を経て PASS。
- [ ] 既存の brightness 検出経路 (`detector.py` / `scorebar.py` / CLI) は未変更。production は presence を import していない。既存テスト・baseline は不変。
- [ ] `ruff check` / `ruff format --check` / `pyright` / `markdownlint` 全 pass。

## Phase 1 がやらないこと (Phase 2/3 へ)

- VTuber 5 source の GT 注釈と VTuber 検証 → **Phase 2** (Idios 作業 + 閾値校正)。
- brightness Pass1 の撤去・production 配線・再 baseline・bit-exact → GT-accuracy gate 置換・#480 分類統合 → **Phase 3** (カットオーバー)。
- issue 起票/編集 (新 umbrella + sub-issue、#480 subsume、#809 redefine) → Iron Law 2 で起票時に AskUserQuestion。

## 参照

- spec: `docs/superpowers/specs/2026-05-29-presence-based-detection-engine-design.md`
- P1 基盤: `allaganeye/video/capture_region.py` (`localize_scorebar` / `ScorebarLocalization`)
- frame 取得: `allaganeye/video/detector.py` (`_probe_frame_rgb_hires`)
- GT データ: `tests/baselines/v0.3.0/ground-truth/obs-*.json`, `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json`
