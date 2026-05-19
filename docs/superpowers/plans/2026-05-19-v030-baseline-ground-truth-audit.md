# v0.3.0 OBS baseline ground-truth audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.3.0 の 5 OBS baseline 全件について Idios 手動 visual verification による ground truth を確立し、現 baseline との diff から silent miss / false positive / boundary shift を体系的に洗い出して `docs/v030-baseline-audit.md` に集約する。

**Architecture:** 2 つの新規 Python script (`scripts/audit-prepare.py` で pre-screen worksheet 生成、`scripts/audit-compare.py` で diff 抽出) + Idios manual viewing + finding 分類 docs。既存 `allaganeye/video/detector.py` の private brightness helper を直接 import し、`allaganeye/video/probe.py` で video metadata 取得。

**Tech Stack:** Python 3.13+ / numpy / opencv-python-headless (sample frame PNG export) / pytest / 既存 detector module。

**Spec reference:** [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](../specs/2026-05-19-v030-baseline-audit-design.md)

**Target issue:** [#796](https://github.com/Idios/kobutachan-allaganeye/issues/796)

---

## File Structure

| Path | 種別 | 責務 |
|---|---|---|
| `scripts/audit-prepare.py` | Create | Pre-screen worksheet generator (matches/gaps から境界抽出、brightness CSV / sample frame PNG / worksheet CSV を export) |
| `scripts/audit-compare.py` | Create | Diff extractor (baseline と ground truth を tolerance_sec で照合、silent_miss/false_positive/boundary_shift/agreed に分類、markdown table 出力) |
| `tests/test_audit_prepare.py` | Create | `audit-prepare.py` の unit + integration test (synthetic metadata.json fixture) |
| `tests/test_audit_compare.py` | Create | `audit-compare.py` の unit test (synthetic baseline + ground truth fixture) |
| `tests/baselines/v0.3.0/ground-truth/.gitkeep` | Create | Ground truth directory marker (Iteration 1/2 で `obs-*.json` が追加される) |
| `tests/baselines/v0.3.0/audit-worksheet/.gitignore` | Create | Worksheet output は git 管理外 (再生成可能、PNG/CSV のかさ嵩) |
| `tests/baselines/v0.3.0/ground-truth/obs-20260116.json` | Create (manual) | Iteration 1 Idios 手動 ground truth |
| `tests/baselines/v0.3.0/ground-truth/obs-20260118.json` | Create (manual) | Iteration 2 |
| `tests/baselines/v0.3.0/ground-truth/obs-20260119.json` | Create (manual) | Iteration 2 |
| `tests/baselines/v0.3.0/ground-truth/obs-20260127.json` | Create (manual) | Iteration 2 |
| `tests/baselines/v0.3.0/ground-truth/obs-20260209.json` | Create (manual) | Iteration 2 |
| `docs/v030-baseline-audit.md` | Create | Finding 集約 deliverable (recording 別 section + cross-recording summary) |
| `docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md` | Modify (light) | §4.1 の `python -m scripts.audit_prepare` 表記を `python scripts/audit-prepare.py` 形式に揃える (実装で hyphen 命名に確定) |

## Naming Convention

既存 `scripts/compare-baseline.py` / `scripts/generate-v030-baselines.py` family と整合させて **hyphen 命名 + 直接実行** (`python scripts/audit-prepare.py <args>`)。spec §4.1 の module import 形式は plan で更新する。

---

## Task 1: ground-truth ディレクトリ marker

**Files:**
- Create: `tests/baselines/v0.3.0/ground-truth/.gitkeep`
- Create: `tests/baselines/v0.3.0/audit-worksheet/.gitignore`

ground truth file を集約する dir と、git 管理外 worksheet output dir を作成。

- [ ] **Step 1: Create gitkeep**

```bash
mkdir -p tests/baselines/v0.3.0/ground-truth
echo "# Manual ground truth files for v0.3.0 audit (#796). See docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md" > tests/baselines/v0.3.0/ground-truth/.gitkeep
```

- [ ] **Step 2: Create worksheet gitignore**

```bash
mkdir -p tests/baselines/v0.3.0/audit-worksheet
cat > tests/baselines/v0.3.0/audit-worksheet/.gitignore <<'EOF'
# Audit worksheet output is regenerable from <recording>.metadata.json + video.
# Exclude all generated files but keep this .gitignore.
*
!.gitignore
EOF
```

- [ ] **Step 3: Verify**

Run: `git status --short`
Expected: 2 new files (`tests/baselines/v0.3.0/ground-truth/.gitkeep` and `tests/baselines/v0.3.0/audit-worksheet/.gitignore`)

- [ ] **Step 4: Commit**

```bash
git add tests/baselines/v0.3.0/ground-truth/.gitkeep tests/baselines/v0.3.0/audit-worksheet/.gitignore
git commit -m "$(cat <<'EOF'
chore(audit): #796 ground-truth dir + worksheet gitignore setup

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: audit-prepare.py — worksheet row builder (TDD)

**Files:**
- Create: `tests/test_audit_prepare.py`
- Create: `scripts/audit-prepare.py`

`<recording>.metadata.json` から境界 timestamp 一覧を抽出して worksheet row dict のリストを返す純粋関数 `build_worksheet_rows` を TDD で実装。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audit_prepare.py
"""Tests for scripts/audit-prepare.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit-prepare.py"


def _load_module() -> Any:
    """Load scripts/audit-prepare.py as a Python module."""
    spec = importlib.util.spec_from_file_location("audit_prepare", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sample_metadata() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "source": "20260116/2026-01-16 22-12-57.mkv",
        "source_duration": 7303.488,
        "source_fps": 60.0,
        "matches": [
            {
                "index": 1,
                "start_time": 49.125,
                "end_time": 1054.5,
                "duration": 1005.375,
                "type": "fl_match",
            },
            {
                "index": 2,
                "start_time": 1256.0,
                "end_time": 2178.75,
                "duration": 922.75,
                "type": "fl_match",
            },
        ],
        "gaps": [
            {
                "start_time": 2610.75,
                "end_time": 2976.25,
                "duration": 365.5,
            }
        ],
    }


def test_build_worksheet_rows_includes_all_boundaries(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    # 2 matches × 2 boundaries + 1 gap × 2 boundaries = 6 rows
    assert len(rows) == 6

    types = [r["boundary_type"] for r in rows]
    assert types == [
        "match_start",
        "match_end",
        "match_start",
        "match_end",
        "gap_start",
        "gap_end",
    ]


def test_build_worksheet_rows_timestamp_display_format(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    # 49.125 → "00:49.125"
    assert rows[0]["timestamp_sec"] == pytest.approx(49.125)
    assert rows[0]["timestamp_display"] == "00:49.125"
    # 2178.75 → "36:18.750"
    assert rows[3]["timestamp_display"] == "36:18.750"


def test_build_worksheet_rows_current_type(sample_metadata):
    mod = _load_module()
    rows = mod.build_worksheet_rows(sample_metadata)

    assert rows[0]["current_type"] == "fl_match"
    assert rows[4]["current_type"] == "gap"


def test_build_worksheet_rows_empty_inputs():
    mod = _load_module()
    rows = mod.build_worksheet_rows({"matches": [], "gaps": []})
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: FAIL with `FileNotFoundError` or `ModuleNotFoundError` for `audit-prepare.py`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/audit-prepare.py
"""Audit prepare: generate pre-screen worksheet for v0.3.0 baseline audit (#796).

Reads `tests/baselines/v0.3.0/<label>.metadata.json`, extracts match / gap
boundary timestamps, and emits a CSV worksheet + per-boundary brightness CSV
+ sample frame PNGs. Idios uses the worksheet to verify each boundary against
the source video and produces `tests/baselines/v0.3.0/ground-truth/<label>.json`.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def _format_timestamp(timestamp_sec: float) -> str:
    """Format seconds as MM:SS.fff (e.g., 2178.75 -> '36:18.750')."""
    minutes = int(timestamp_sec // 60)
    seconds = timestamp_sec - minutes * 60
    return f"{minutes:02d}:{seconds:06.3f}"


def build_worksheet_rows(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract boundary timestamps from metadata.json into worksheet rows.

    Each match contributes 2 rows (start, end). Each gap contributes 2 rows
    (gap_start, gap_end). Rows preserve the metadata.json ordering.
    """
    rows: list[dict[str, Any]] = []
    matches = metadata.get("matches", [])
    gaps = metadata.get("gaps", [])

    for match in matches:
        for kind, key in (("match_start", "start_time"), ("match_end", "end_time")):
            ts = float(match[key])
            rows.append(
                {
                    "index": match.get("index"),
                    "boundary_type": kind,
                    "timestamp_sec": ts,
                    "timestamp_display": _format_timestamp(ts),
                    "current_type": match.get("type", "unknown"),
                    "brightness_csv_ref": f"brightness-around-{ts:.3f}.csv",
                    "sample_frame_png_ref": f"frame-around-{ts:.3f}.png",
                    "idios_verdict": "",
                    "idios_note": "",
                }
            )

    for gap in gaps:
        for kind, key in (("gap_start", "start_time"), ("gap_end", "end_time")):
            ts = float(gap[key])
            rows.append(
                {
                    "index": None,
                    "boundary_type": kind,
                    "timestamp_sec": ts,
                    "timestamp_display": _format_timestamp(ts),
                    "current_type": "gap",
                    "brightness_csv_ref": f"brightness-around-{ts:.3f}.csv",
                    "sample_frame_png_ref": f"frame-around-{ts:.3f}.png",
                    "idios_verdict": "",
                    "idios_note": "",
                }
            )

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.parse_args(argv)
    print("Not yet implemented: full pipeline (Task 3-5).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Lint / type check**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py && ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py && pyright scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: all green. Fix any violations inline.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-prepare worksheet row builder (TDD)

Pure function build_worksheet_rows extracts match/gap boundary timestamps
from metadata.json into a list of dict rows for the worksheet CSV.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: audit-prepare.py — video path resolution (TDD)

**Files:**
- Modify: `tests/test_audit_prepare.py` (add new tests)
- Modify: `scripts/audit-prepare.py` (add `resolve_video_path`)

`metadata.json["source"]` (relative path) + `$ALLAGANEYE_SAMPLE_VIDEO_DIR` (env) から動画の絶対 path を解決する `resolve_video_path` を実装。

- [ ] **Step 1: Add failing tests**

Append to `tests/test_audit_prepare.py`:

```python
def test_resolve_video_path_uses_env_var(monkeypatch, tmp_path):
    mod = _load_module()
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    (video_dir / "20260116").mkdir()
    target = video_dir / "20260116" / "2026-01-16 22-12-57.mkv"
    target.write_bytes(b"")  # placeholder

    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))
    resolved = mod.resolve_video_path("20260116/2026-01-16 22-12-57.mkv")

    assert resolved == target


def test_resolve_video_path_missing_env_raises(monkeypatch):
    mod = _load_module()
    monkeypatch.delenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", raising=False)
    with pytest.raises(EnvironmentError, match="ALLAGANEYE_SAMPLE_VIDEO_DIR"):
        mod.resolve_video_path("20260116/2026-01-16 22-12-57.mkv")


def test_resolve_video_path_missing_file_raises(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        mod.resolve_video_path("20260116/not-there.mkv")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audit_prepare.py -v -k resolve_video_path`
Expected: 3 FAIL with `AttributeError: module 'audit_prepare' has no attribute 'resolve_video_path'`.

- [ ] **Step 3: Add implementation**

Insert after `build_worksheet_rows` in `scripts/audit-prepare.py`:

```python
import os


def resolve_video_path(source_relative: str) -> Path:
    """Resolve metadata.json `source` field to an absolute video path.

    Uses ``ALLAGANEYE_SAMPLE_VIDEO_DIR`` env var as the base directory.
    """
    base = os.environ.get("ALLAGANEYE_SAMPLE_VIDEO_DIR")
    if not base:
        raise EnvironmentError(
            "ALLAGANEYE_SAMPLE_VIDEO_DIR is not set. Point it to the directory "
            "containing the recording subdirs (see CLAUDE.md §動画サンプルデータ)."
        )
    candidate = Path(base) / source_relative
    if not candidate.exists():
        raise FileNotFoundError(
            f"Video not found: {candidate} (resolved from "
            f"ALLAGANEYE_SAMPLE_VIDEO_DIR={base!r} + source={source_relative!r})"
        )
    return candidate
```

Also move `import os` to the top-imports block if not already there.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: 7 PASS (4 from Task 2 + 3 new).

- [ ] **Step 5: Lint**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py && ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py && pyright scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-prepare resolve_video_path from env var

Resolves metadata.json source field against ALLAGANEYE_SAMPLE_VIDEO_DIR.
Raises EnvironmentError if env unset, FileNotFoundError if path missing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: audit-prepare.py — brightness CSV export (TDD)

**Files:**
- Modify: `tests/test_audit_prepare.py`
- Modify: `scripts/audit-prepare.py`

各境界 ±5s 範囲を 0.25s 間隔で brightness probe し CSV ファイルに出力する `export_brightness_csv` を実装。既存 `_probe_single_frame` を直接 import して再利用 (DRY)。

- [ ] **Step 1: Add failing test**

Append to `tests/test_audit_prepare.py`:

```python
def test_export_brightness_csv_writes_expected_rows(tmp_path, monkeypatch):
    mod = _load_module()

    # Stub _probe_single_frame to avoid needing a real video
    calls: list[float] = []

    def fake_probe(video_path, timestamp):
        calls.append(timestamp)
        # Synthetic brightness: dip near t=100
        return 5.0 if abs(timestamp - 100.0) < 1.0 else 80.0

    monkeypatch.setattr(mod, "_probe_single_frame", fake_probe)

    out_path = tmp_path / "brightness-around-100.000.csv"
    mod.export_brightness_csv(
        video_path=tmp_path / "fake.mkv",
        boundary_timestamp=100.0,
        out_path=out_path,
        window_sec=5.0,
        interval_sec=0.25,
    )

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8").strip().splitlines()
    # Header + (5s before + 5s after) / 0.25s + 1 = 41 rows
    assert content[0] == "timestamp,brightness"
    assert len(content) == 1 + 41
    # First data row should be at 95.000
    assert content[1].startswith("95.000,")
    # Last data row should be at 105.000
    assert content[-1].startswith("105.000,")
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_audit_prepare.py -v -k export_brightness_csv`
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add implementation**

Insert in `scripts/audit-prepare.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

from allaganeye.exceptions import VideoProcessingError
from allaganeye.video.detector import _probe_single_frame, _resolve_workers


def export_brightness_csv(
    *,
    video_path: Path,
    boundary_timestamp: float,
    out_path: Path,
    window_sec: float = 5.0,
    interval_sec: float = 0.25,
    workers: int | None = None,
) -> None:
    """Probe brightness in [boundary - window, boundary + window] at interval_sec.

    Writes CSV with header ``timestamp,brightness``. Probe failures are
    recorded as 255.0 (same convention as ``_probe_single_frame``).
    """
    start = max(boundary_timestamp - window_sec, 0.0)
    end = boundary_timestamp + window_sec
    timestamps: list[float] = []
    t = start
    while t <= end + 1e-6:
        timestamps.append(round(t, 3))
        t += interval_sec

    max_workers = _resolve_workers(workers)
    results: dict[float, float] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_single_frame, video_path, ts): ts for ts in timestamps
        }
        for future in as_completed(futures):
            ts = futures[future]
            try:
                results[ts] = future.result()
            except VideoProcessingError:
                results[ts] = 255.0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        f.write("timestamp,brightness\n")
        for ts in sorted(results):
            f.write(f"{ts:.3f},{results[ts]:.1f}\n")
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Lint**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py && ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py && pyright scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-prepare brightness CSV per boundary

±5s window at 0.25s interval, reuses _probe_single_frame from detector.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: audit-prepare.py — sample frame PNG export (TDD)

**Files:**
- Modify: `tests/test_audit_prepare.py`
- Modify: `scripts/audit-prepare.py`

各境界の -1s/0s/+1s で 3 frame を 320x180 grayscale PNG として出力。OpenCV (`cv2.imwrite`) で書き出す。

- [ ] **Step 1: Add failing test**

Append to `tests/test_audit_prepare.py`:

```python
def test_export_sample_frames_writes_three_pngs(tmp_path, monkeypatch):
    import numpy as np

    mod = _load_module()

    def fake_probe_rgb(video_path, timestamp, height):
        # Return a 320x180x3 black-and-mid frame
        frame = np.full((180, 320, 3), int(timestamp) % 256, dtype=np.uint8)
        return frame.tobytes()

    monkeypatch.setattr(mod, "_probe_frame_rgb", fake_probe_rgb)

    out_dir = tmp_path / "obs-fake"
    out_dir.mkdir()

    mod.export_sample_frames(
        video_path=tmp_path / "fake.mkv",
        boundary_timestamp=100.0,
        out_dir=out_dir,
        height=180,
    )

    pngs = sorted(out_dir.glob("frame-around-*.png"))
    assert len(pngs) == 3
    assert pngs[0].name == "frame-around-099.000.png"
    assert pngs[1].name == "frame-around-100.000.png"
    assert pngs[2].name == "frame-around-101.000.png"
    # Sanity: each file is non-empty
    for p in pngs:
        assert p.stat().st_size > 0
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_audit_prepare.py -v -k export_sample_frames`
Expected: FAIL.

- [ ] **Step 3: Add implementation**

Insert in `scripts/audit-prepare.py`:

```python
import cv2  # type: ignore[import-untyped]
import numpy as np

from allaganeye.video.detector import _SAMPLE_WIDTH, _probe_frame_rgb


def export_sample_frames(
    *,
    video_path: Path,
    boundary_timestamp: float,
    out_dir: Path,
    height: int = 180,
) -> None:
    """Export 3 sample frames at boundary - 1s / boundary / boundary + 1s as PNG."""
    offsets = (-1.0, 0.0, 1.0)
    out_dir.mkdir(parents=True, exist_ok=True)

    for offset in offsets:
        ts = max(boundary_timestamp + offset, 0.0)
        try:
            raw = _probe_frame_rgb(video_path, ts, height=height)
        except Exception:  # noqa: BLE001
            raw = None
        if raw is None:
            continue
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, _SAMPLE_WIDTH, 3)
        out_path = out_dir / f"frame-around-{ts:07.3f}.png"
        cv2.imwrite(str(out_path), frame[:, :, ::-1])  # RGB -> BGR for cv2
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: 9 PASS.

- [ ] **Step 5: Lint**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py && ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py && pyright scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: green. If pyright complains about cv2, add `# type: ignore[import-untyped]` to the import line (already in the snippet).

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-prepare sample frame PNG export (-1/0/+1s)

3 frames per boundary at 320x180 grayscale via OpenCV imwrite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: audit-prepare.py — main() integration (TDD)

**Files:**
- Modify: `tests/test_audit_prepare.py`
- Modify: `scripts/audit-prepare.py`

CLI 引数解決 + worksheet CSV write + brightness CSV / sample frame PNG の一括 export を担う `main()` を実装。Integration test では brightness/PNG step は stub し、worksheet CSV write の挙動を assert。

- [ ] **Step 1: Add failing test**

Append to `tests/test_audit_prepare.py`:

```python
def test_main_writes_worksheet_csv(tmp_path, monkeypatch):
    """End-to-end: main() reads metadata.json + writes worksheet CSV.

    Brightness/PNG step is stubbed; this verifies worksheet CSV shape only.
    """
    mod = _load_module()

    # Fake baseline dir with one metadata.json
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir()
    metadata = {
        "schema_version": "1",
        "source": "20260116/fake.mkv",
        "matches": [
            {"index": 1, "start_time": 49.125, "end_time": 1054.5, "duration": 1005.375, "type": "fl_match"},
        ],
        "gaps": [],
    }
    (baseline_dir / "obs-20260116.metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    # Fake video so resolve_video_path doesn't raise
    video_dir = tmp_path / "videos"
    (video_dir / "20260116").mkdir(parents=True)
    (video_dir / "20260116" / "fake.mkv").write_bytes(b"")
    monkeypatch.setenv("ALLAGANEYE_SAMPLE_VIDEO_DIR", str(video_dir))

    # Stub brightness / PNG exporters
    monkeypatch.setattr(mod, "export_brightness_csv", lambda **kw: None)
    monkeypatch.setattr(mod, "export_sample_frames", lambda **kw: None)

    worksheet_dir = tmp_path / "audit-worksheet"
    rc = mod.main([
        "obs-20260116",
        "--baseline-dir", str(baseline_dir),
        "--worksheet-dir", str(worksheet_dir),
    ])
    assert rc == 0

    worksheet_csv = worksheet_dir / "obs-20260116.csv"
    assert worksheet_csv.exists()
    lines = worksheet_csv.read_text(encoding="utf-8").strip().splitlines()
    # Header + 2 rows (match_start + match_end)
    assert len(lines) == 1 + 2
    assert lines[0].startswith("index,boundary_type,timestamp_sec,")
    assert "match_start" in lines[1]
    assert "match_end" in lines[2]
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_audit_prepare.py -v -k main_writes_worksheet`
Expected: FAIL (current `main()` is stub).

- [ ] **Step 3: Replace `main()` with full implementation**

In `scripts/audit-prepare.py`, replace the placeholder `main()`:

```python
import csv
import json


_DEFAULT_BASELINE_DIR = Path("tests/baselines/v0.3.0")
_DEFAULT_WORKSHEET_DIR = Path("tests/baselines/v0.3.0/audit-worksheet")

_WORKSHEET_FIELDS = [
    "index",
    "boundary_type",
    "timestamp_sec",
    "timestamp_display",
    "current_type",
    "brightness_csv_ref",
    "sample_frame_png_ref",
    "idios_verdict",
    "idios_note",
]


def write_worksheet_csv(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_WORKSHEET_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in _WORKSHEET_FIELDS})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=_DEFAULT_BASELINE_DIR,
        help=f"Default: {_DEFAULT_BASELINE_DIR}",
    )
    parser.add_argument(
        "--worksheet-dir",
        type=Path,
        default=_DEFAULT_WORKSHEET_DIR,
        help=f"Default: {_DEFAULT_WORKSHEET_DIR}",
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=5.0,
        help="brightness window (default 5.0)",
    )
    parser.add_argument(
        "--interval-sec",
        type=float,
        default=0.25,
        help="brightness sample interval (default 0.25)",
    )
    args = parser.parse_args(argv)

    metadata_path = args.baseline_dir / f"{args.recording_label}.metadata.json"
    if not metadata_path.exists():
        print(f"ERROR: {metadata_path} not found", file=sys.stderr)
        return 2

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    rows = build_worksheet_rows(metadata)

    video_path = resolve_video_path(metadata["source"])

    worksheet_csv = args.worksheet_dir / f"{args.recording_label}.csv"
    write_worksheet_csv(rows, worksheet_csv)

    per_boundary_dir = args.worksheet_dir / args.recording_label
    for row in rows:
        ts = float(row["timestamp_sec"])
        export_brightness_csv(
            video_path=video_path,
            boundary_timestamp=ts,
            out_path=per_boundary_dir / row["brightness_csv_ref"],
            window_sec=args.window_sec,
            interval_sec=args.interval_sec,
        )
        export_sample_frames(
            video_path=video_path,
            boundary_timestamp=ts,
            out_dir=per_boundary_dir,
        )

    print(f"Worksheet: {worksheet_csv}", file=sys.stderr)
    print(f"Per-boundary artifacts: {per_boundary_dir}", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_audit_prepare.py -v`
Expected: 10 PASS.

- [ ] **Step 5: Run full lint + type check**

Run: `ruff check scripts/audit-prepare.py tests/test_audit_prepare.py && ruff format --check scripts/audit-prepare.py tests/test_audit_prepare.py && pyright scripts/audit-prepare.py tests/test_audit_prepare.py`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-prepare.py tests/test_audit_prepare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-prepare main() CLI + worksheet CSV writer

Integrates row builder, brightness CSV, sample frame PNG into a single
CLI entrypoint. Writes worksheet CSV at <worksheet-dir>/<label>.csv plus
per-boundary CSV/PNG under <worksheet-dir>/<label>/.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: audit-compare.py — diff classification (TDD)

**Files:**
- Create: `tests/test_audit_compare.py`
- Create: `scripts/audit-compare.py`

baseline matches/gaps と ground truth matches を tolerance_sec で照合し、各 boundary を agreed / silent_miss / false_positive / boundary_shift に分類する純粋関数 `classify_findings` を TDD で実装。

- [ ] **Step 1: Write failing test**

```python
# tests/test_audit_compare.py
"""Tests for scripts/audit-compare.py."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit-compare.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("audit_compare", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_classify_findings_all_agreed():
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 49.125, "end_time": 1054.5, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 49, "end_time": 1055, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["agreed", "agreed"]


def test_classify_findings_silent_miss():
    """Ground truth has a boundary that baseline does not."""
    mod = _load_module()
    baseline = {"matches": []}
    ground_truth = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["silent_miss", "silent_miss"]


def test_classify_findings_false_positive():
    """Baseline has a boundary that ground truth does not."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ]
    }
    ground_truth = {"matches": [], "tolerance_sec": 1}
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["false_positive", "false_positive"]


def test_classify_findings_boundary_shift():
    """Same boundary count but timestamp drifts beyond tolerance."""
    mod = _load_module()
    baseline = {
        "matches": [
            {"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"},
        ]
    }
    ground_truth = {
        "matches": [
            # start within tolerance, end drifts by 5s
            {"index": 1, "start_time": 50.5, "end_time": 1005, "type": "fl_match"},
        ],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    types = [f["finding_type"] for f in findings]
    assert types == ["agreed", "boundary_shift"]


def test_classify_findings_includes_delta():
    """Each finding records baseline / ground truth ts and delta."""
    mod = _load_module()
    baseline = {
        "matches": [{"index": 1, "start_time": 50, "end_time": 1000, "type": "fl_match"}]
    }
    ground_truth = {
        "matches": [{"index": 1, "start_time": 53, "end_time": 1000, "type": "fl_match"}],
        "tolerance_sec": 1,
    }
    findings = mod.classify_findings(baseline, ground_truth)
    shift = findings[0]
    assert shift["finding_type"] == "boundary_shift"
    assert shift["baseline_ts"] == 50
    assert shift["ground_truth_ts"] == 53
    assert shift["delta_sec"] == pytest.approx(3.0)
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_audit_compare.py -v`
Expected: 5 FAIL.

- [ ] **Step 3: Implement audit-compare.py**

Create `scripts/audit-compare.py`:

```python
"""Audit compare: classify diffs between current baseline and Idios ground truth.

Compares matches[] from tests/baselines/v0.3.0/<label>.metadata.json against
tests/baselines/v0.3.0/ground-truth/<label>.json with tolerance_sec from the
ground truth file (default 1s). Emits a markdown finding table ready to paste
into docs/v030-baseline-audit.md.

See: docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md §3.3 / §5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _extract_boundaries(matches: list[dict[str, Any]]) -> list[tuple[int | None, str, float]]:
    """Return (index, kind, timestamp) for each match start/end."""
    out: list[tuple[int | None, str, float]] = []
    for m in matches:
        out.append((m.get("index"), "start", float(m["start_time"])))
        out.append((m.get("index"), "end", float(m["end_time"])))
    return out


def classify_findings(
    baseline: dict[str, Any], ground_truth: dict[str, Any]
) -> list[dict[str, Any]]:
    """Classify each ground_truth / baseline boundary into the 4 finding types."""
    tolerance = float(ground_truth.get("tolerance_sec", 1))
    b_boundaries = _extract_boundaries(baseline.get("matches", []))
    g_boundaries = _extract_boundaries(ground_truth.get("matches", []))

    matched_b: set[int] = set()
    findings: list[dict[str, Any]] = []

    # Walk ground truth: find best match in baseline within tolerance
    for g_idx, g_kind, g_ts in g_boundaries:
        best_b: int | None = None
        best_delta: float = float("inf")
        for i, (_b_idx, b_kind, b_ts) in enumerate(b_boundaries):
            if i in matched_b or b_kind != g_kind:
                continue
            delta = abs(g_ts - b_ts)
            if delta < best_delta:
                best_delta = delta
                best_b = i
        if best_b is not None and best_delta <= tolerance:
            matched_b.add(best_b)
            _b_idx_match, _b_kind_match, b_ts_match = b_boundaries[best_b]
            findings.append(
                {
                    "finding_type": "agreed",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": b_ts_match,
                    "ground_truth_ts": g_ts,
                    "delta_sec": g_ts - b_ts_match,
                }
            )
        elif best_b is not None and best_delta > tolerance:
            # Closest baseline boundary exists but outside tolerance -> shift
            matched_b.add(best_b)
            _b_idx_match, _b_kind_match, b_ts_match = b_boundaries[best_b]
            findings.append(
                {
                    "finding_type": "boundary_shift",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": b_ts_match,
                    "ground_truth_ts": g_ts,
                    "delta_sec": g_ts - b_ts_match,
                }
            )
        else:
            findings.append(
                {
                    "finding_type": "silent_miss",
                    "match_index_gt": g_idx,
                    "boundary": g_kind,
                    "baseline_ts": None,
                    "ground_truth_ts": g_ts,
                    "delta_sec": None,
                }
            )

    # Unmatched baseline boundaries -> false positive
    for i, (b_idx, b_kind, b_ts) in enumerate(b_boundaries):
        if i in matched_b:
            continue
        findings.append(
            {
                "finding_type": "false_positive",
                "match_index_gt": None,
                "match_index_baseline": b_idx,
                "boundary": b_kind,
                "baseline_ts": b_ts,
                "ground_truth_ts": None,
                "delta_sec": None,
            }
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording_label", help="e.g., obs-20260116")
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=Path("tests/baselines/v0.3.0"),
    )
    parser.add_argument(
        "--ground-truth-dir",
        type=Path,
        default=Path("tests/baselines/v0.3.0/ground-truth"),
    )
    args = parser.parse_args(argv)

    baseline_path = args.baseline_dir / f"{args.recording_label}.metadata.json"
    ground_truth_path = args.ground_truth_dir / f"{args.recording_label}.json"

    for p in (baseline_path, ground_truth_path):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 2

    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    ground_truth = json.loads(ground_truth_path.read_text(encoding="utf-8"))

    findings = classify_findings(baseline, ground_truth)
    print(format_markdown(findings, label=args.recording_label, baseline=baseline, ground_truth=ground_truth))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add the `format_markdown` stub at the bottom (filled in Task 8):

```python
def format_markdown(
    findings: list[dict[str, Any]],
    *,
    label: str,
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
) -> str:
    """Format findings as a markdown section. Filled in Task 8."""
    return f"## {label}\n\n(format_markdown stub — {len(findings)} findings)"
```

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_audit_compare.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Lint**

Run: `ruff check scripts/audit-compare.py tests/test_audit_compare.py && ruff format --check scripts/audit-compare.py tests/test_audit_compare.py && pyright scripts/audit-compare.py tests/test_audit_compare.py`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-compare classify_findings (TDD)

Classifies each ground truth / baseline boundary into agreed /
silent_miss / false_positive / boundary_shift using tolerance_sec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: audit-compare.py — markdown formatter (TDD)

**Files:**
- Modify: `tests/test_audit_compare.py`
- Modify: `scripts/audit-compare.py`

`format_markdown` を仕上げる: recording metadata header + finding table を出力。

- [ ] **Step 1: Add failing test**

Append to `tests/test_audit_compare.py`:

```python
def test_format_markdown_contains_header_and_table():
    mod = _load_module()
    findings = [
        {
            "finding_type": "agreed",
            "match_index_gt": 1,
            "boundary": "start",
            "baseline_ts": 49.125,
            "ground_truth_ts": 49,
            "delta_sec": -0.125,
        },
        {
            "finding_type": "boundary_shift",
            "match_index_gt": 3,
            "boundary": "end",
            "baseline_ts": 3367.125,
            "ground_truth_ts": 3230.5,
            "delta_sec": -136.625,
        },
        {
            "finding_type": "silent_miss",
            "match_index_gt": 4,
            "boundary": "start",
            "baseline_ts": None,
            "ground_truth_ts": 4000.0,
            "delta_sec": None,
        },
    ]
    baseline = {"source": "20260116/2026-01-16.mkv", "matches": [{}, {}, {}]}
    ground_truth = {
        "source_dir_label": "obs-20260116",
        "tolerance_sec": 1,
        "matches": [{}, {}, {}, {}],
    }
    out = mod.format_markdown(
        findings, label="obs-20260116", baseline=baseline, ground_truth=ground_truth
    )
    assert "## obs-20260116" in out
    assert "Tolerance: ±1" in out
    assert "Ground truth: 4 matches" in out
    assert "Current baseline: 3 matches" in out
    # Table contains all 3 findings
    assert "agreed" in out
    assert "boundary_shift" in out
    assert "silent_miss" in out
    assert "-136.625" in out
```

- [ ] **Step 2: Run test, verify fail**

Run: `pytest tests/test_audit_compare.py -v -k format_markdown`
Expected: FAIL (stub returns wrong format).

- [ ] **Step 3: Replace stub with real implementation**

Replace `format_markdown` in `scripts/audit-compare.py`:

```python
_FINDING_ORDER = ("silent_miss", "false_positive", "boundary_shift", "agreed")


def _format_delta(delta: float | None) -> str:
    if delta is None:
        return "—"
    return f"{delta:+.3f}"


def _format_ts(ts: float | None) -> str:
    if ts is None:
        return "—"
    return f"{ts:.3f}"


def format_markdown(
    findings: list[dict[str, Any]],
    *,
    label: str,
    baseline: dict[str, Any],
    ground_truth: dict[str, Any],
) -> str:
    tolerance = ground_truth.get("tolerance_sec", 1)
    baseline_match_count = len(baseline.get("matches", []))
    gt_match_count = len(ground_truth.get("matches", []))
    source = baseline.get("source", "(unknown)")

    counts = {kind: 0 for kind in _FINDING_ORDER}
    for f in findings:
        counts[f["finding_type"]] = counts.get(f["finding_type"], 0) + 1

    lines: list[str] = []
    lines.append(f"## {label}")
    lines.append("")
    lines.append(f"- Source: `{source}`")
    lines.append(f"- Ground truth: {gt_match_count} matches (Idios manual)")
    lines.append(f"- Current baseline: {baseline_match_count} matches")
    lines.append(f"- Tolerance: ±{tolerance}s")
    lines.append(
        f"- Findings: {counts['silent_miss']} silent_miss / "
        f"{counts['false_positive']} false_positive / "
        f"{counts['boundary_shift']} boundary_shift / "
        f"{counts['agreed']} agreed"
    )
    lines.append("")
    lines.append("### Findings")
    lines.append("")
    lines.append("| # | Type | Match | Boundary | Baseline ts | Ground truth ts | Delta | Classification (a/b/c) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    sorted_findings = sorted(
        findings, key=lambda f: _FINDING_ORDER.index(f["finding_type"])
    )
    for i, f in enumerate(sorted_findings, start=1):
        match_idx = f.get("match_index_gt") or f.get("match_index_baseline") or "—"
        lines.append(
            f"| {i} "
            f"| {f['finding_type']} "
            f"| {match_idx} "
            f"| {f['boundary']} "
            f"| {_format_ts(f['baseline_ts'])} "
            f"| {_format_ts(f['ground_truth_ts'])} "
            f"| {_format_delta(f['delta_sec'])} "
            f"| (TBD by Idios) |"
        )
    return "\n".join(lines)
```

Note: the `(TBD by Idios)` classification column is intentional — Idios will fill it in `docs/v030-baseline-audit.md` per the §5 rubric. Do not generate a/b/c automatically.

- [ ] **Step 4: Run test, verify pass**

Run: `pytest tests/test_audit_compare.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Lint**

Run: `ruff check scripts/audit-compare.py tests/test_audit_compare.py && ruff format --check scripts/audit-compare.py tests/test_audit_compare.py && pyright scripts/audit-compare.py tests/test_audit_compare.py`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add scripts/audit-compare.py tests/test_audit_compare.py
git commit -m "$(cat <<'EOF'
feat(audit): #796 audit-compare markdown formatter

Outputs a docs/v030-baseline-audit.md-ready section with finding table
and per-type counts. Classification column left as 'TBD by Idios'.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Full suite verification

**Files:**
- (none changed)

実装した script / test 全件で lint / type / unit test を回し、既存 testsuite に regression がないか確認。

- [ ] **Step 1: Run scoped lint + tests**

Run: `ruff check . && ruff format --check . && pyright scripts/ tests/test_audit_prepare.py tests/test_audit_compare.py && pytest tests/test_audit_prepare.py tests/test_audit_compare.py -v`
Expected: all green.

- [ ] **Step 2: Run full pytest suite (excluding slow)**

Run: `pytest -m "not slow" --tb=short`
Expected: no new failures vs main baseline. (`gui-frontend` CI failure in PR #793 is unrelated to this work.)

- [ ] **Step 3: Spec touch-up commit**

Update `docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md` §4.1: replace any `python -m scripts.audit_prepare` mention with `python scripts/audit-prepare.py`, matching the hyphen-naming convention used in `compare-baseline.py`. Use Edit tool to replace the specific line (no full rewrite):

```text
old: 両 script とも `python -m scripts.audit_prepare <label>` 形式で起動可能なよう module 配置を検討。
new: 両 script とも `python scripts/audit-prepare.py <label>` 形式で起動 (hyphen 命名、`compare-baseline.py` family と整合)。
```

```bash
git add docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md
git commit -m "$(cat <<'EOF'
docs(spec): #796 audit script invocation form matches compare-baseline.py

Replaces module-import form with direct hyphen-named script execution
to match the actual implementation and the existing scripts/ convention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Iteration 1 — obs-20260116 worksheet generation

**Files:**
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260116.csv`
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260116/brightness-around-*.csv`
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260116/frame-around-*.png`

audit-prepare.py を `obs-20260116` で本番実行し、Idios 視聴用 worksheet を生成。

- [ ] **Step 1: Verify env var is set**

Run: `echo $env:ALLAGANEYE_SAMPLE_VIDEO_DIR` (PowerShell) or `echo $ALLAGANEYE_SAMPLE_VIDEO_DIR` (bash)
Expected: a path that contains the recording subdir (e.g., `E:\royalstraightflesh\videos`).

If unset, STOP and ask Idios to set it per CLAUDE.md §動画サンプルデータ.

- [ ] **Step 2: Run audit-prepare**

Run: `python scripts/audit-prepare.py obs-20260116`
Expected: stderr shows worksheet path and per-boundary artifacts dir. May take 30s-2min depending on disk speed (12 boundaries × 41 brightness samples + 3 PNG = ~530 ffmpeg probes).

- [ ] **Step 3: Verify outputs**

Run: `Get-ChildItem tests/baselines/v0.3.0/audit-worksheet/obs-20260116*` (PowerShell)
Expected:
- `obs-20260116.csv` — 12 rows (6 matches × 2 boundaries + 0 gaps × 2)
- `obs-20260116/` dir containing `brightness-around-*.csv` (12 files) + `frame-around-*.png` (~36 files: 12 boundaries × 3 offsets)

- [ ] **Step 4: Spot-check worksheet**

Open `tests/baselines/v0.3.0/audit-worksheet/obs-20260116.csv` and verify:
- Header line is correct
- First match start: index=1, boundary_type=match_start, timestamp_sec=49.125, current_type=fl_match
- Match 3 end: timestamp_sec=3367.125 (= F1 example boundary that PR #793 changed to 3230.5 = note: baseline file is PR #793 head, so should reflect new value)

If baseline file has old timestamps (legacy fps filter values), STOP and confirm we're on PR #793 head: `git log --oneline -1 -- tests/baselines/v0.3.0/obs-20260116.metadata.json`.

- [ ] **Step 5: Skip commit (output is gitignored)**

`audit-worksheet/` is in `.gitignore` (Task 1). Do not commit generated artifacts.

---

## Task 11: Iteration 1 — Idios manual viewing (HANDOFF)

**Files (manual):**
- Create: `tests/baselines/v0.3.0/ground-truth/obs-20260116.json`

**THIS IS A MANUAL TASK — Idios performs the work.** The agent's role is to (1) verify the worksheet exists, (2) wait for Idios to upload the ground truth JSON, (3) sanity-check the JSON schema.

- [ ] **Step 1: Hand off to Idios**

Send Idios the following:

```
obs-20260116 worksheet が `tests/baselines/v0.3.0/audit-worksheet/obs-20260116.csv` に生成済。

手順:
1. CSV を Excel / LibreOffice / Numbers 等で開く
2. 各 boundary について player (VLC / mpv 等) で動画の該当 timestamp ±5s を再生
3. idios_verdict 列に判定を記入:
   - match_start / match_end / false_positive / uncertain
   - 必要なら CSV 末尾に行追加 (current_type=missing) で silent miss を記録
4. 完了後 `tests/baselines/v0.3.0/ground-truth/obs-20260116.json` を作成 (schema は spec §3.2 / `vtuber-primary-ground-truth.json` 参照)
```

- [ ] **Step 2: Wait for Idios completion**

Pause here. User reports when ground-truth/obs-20260116.json is ready.

- [ ] **Step 3: Validate JSON schema**

Run a quick Python validation:

```bash
python -c "
import json, sys
from pathlib import Path
p = Path('tests/baselines/v0.3.0/ground-truth/obs-20260116.json')
data = json.loads(p.read_text(encoding='utf-8'))
required = {'source_file', 'source_dir_label', 'ground_truth_provider', 'ground_truth_provided_at', 'tolerance_sec', 'matches'}
missing = required - set(data.keys())
assert not missing, f'Missing fields: {missing}'
for m in data['matches']:
    assert {'index', 'start_time', 'end_time', 'duration', 'type'} <= set(m.keys()), m
print(f'OK: {len(data[\"matches\"])} matches, tolerance={data[\"tolerance_sec\"]}s')
"
```

Expected: `OK: N matches, tolerance=1s`. If schema mismatch, ask Idios to fix or fix together.

- [ ] **Step 4: Commit ground truth**

```bash
git add tests/baselines/v0.3.0/ground-truth/obs-20260116.json
git commit -m "$(cat <<'EOF'
data(audit): #796 ground truth for obs-20260116 (Idios manual)

Iteration 1 proof of concept of the audit workflow. Establishes the
ground-truth schema for the remaining 4 baselines.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Iteration 1 — audit-compare run + finding classification

**Files:**
- Create: `docs/v030-baseline-audit.md`

audit-compare.py で diff 抽出 → markdown section をベースに Idios と finding 分類。

- [ ] **Step 1: Run audit-compare**

Run: `python scripts/audit-compare.py obs-20260116 > /tmp/obs-20260116-findings.md`
(Windows: `python scripts/audit-compare.py obs-20260116 | Out-File -Encoding utf8 $env:TEMP\obs-20260116-findings.md`)

Expected: a markdown section with header, finding counts, and table with `(TBD by Idios)` classification column.

- [ ] **Step 2: Review findings with Idios**

For each non-`agreed` finding, walk through the §5 rubric with Idios:

1. Run `python scripts/audit-prepare.py` already done — sample frames + brightness CSV are at `audit-worksheet/obs-20260116/`.
2. For silent_miss: check if a re-run of `allaganeye detect` on that segment would catch it (current detector behavior is in baseline = same outcome, so the finding reflects current state; classification depends on whether tuning would help → (b) — or it's a design trade-off → (c)).
3. For false_positive: same logic in reverse.
4. For boundary_shift: check if delta is within reasonable detector tolerance.

Fill the `Classification` column in the markdown with `(a)` / `(b)` / `(c)` based on the rubric. Add a `## Discussion` subsection per recording for nuanced findings.

- [ ] **Step 3: Create docs/v030-baseline-audit.md**

Write the audit doc starting with a top-level summary + obs-20260116 section. Template:

````markdown
# v0.3.0 OBS baseline audit (#796)

> **Status**: Iteration 1 / 5 (obs-20260116 PoC)
> **Spec**: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](superpowers/specs/2026-05-19-v030-baseline-audit-design.md)
> **PR #793 status**: draft (audit blocking)

## Cross-recording summary

(filled after all 5 baselines audited — Task 16)

## obs-20260116

(paste audit-compare.py output here, with Classification column filled)

### Discussion

(per-finding notes — what was checked, why classified as (a)/(b)/(c))
````

- [ ] **Step 4: Commit Iteration 1 audit doc**

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #796 Iteration 1 obs-20260116 findings

PoC iteration of the audit workflow. (a)/(b)/(c) classification
applied per §5 rubric. Cross-recording summary deferred to Task 16.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Iteration 1 retrospect — spec / script feedback

**Files:**
- (potentially) Modify: `docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md`
- (potentially) Modify: `scripts/audit-prepare.py` / `scripts/audit-compare.py`

Iteration 1 で発見した script bug / workflow gap / 不足を fix。

- [ ] **Step 1: Review with Idios**

Ask:
- Was the worksheet CSV easy to fill in (column names clear, sufficient detail)?
- Were brightness CSVs / PNGs useful, or wasted I/O?
- Did audit-compare output give enough info to classify findings?
- Any silent miss or FP that the worksheet failed to surface?

- [ ] **Step 2: Apply feedback inline**

Make small fixes (1-3 commits, each TDD if changing logic). Update spec doc if behavior changes materially.

- [ ] **Step 3: Re-run Task 9 lint + tests if code changed**

Run: `ruff check . && ruff format --check . && pyright scripts/ && pytest -m "not slow" --tb=short`
Expected: green.

- [ ] **Step 4: Commit feedback (if any)**

Commit messages per fix. If no feedback needed, skip this task.

---

## Task 14: Iteration 2 — remaining 4 baselines worksheet generation

**Files:**
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260118.csv` + per-boundary artifacts
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260119.csv` + per-boundary artifacts
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260127.csv` + per-boundary artifacts
- Generated: `tests/baselines/v0.3.0/audit-worksheet/obs-20260209.csv` + per-boundary artifacts

- [ ] **Step 1: Run audit-prepare for each**

```bash
for label in obs-20260118 obs-20260119 obs-20260127 obs-20260209; do
  python scripts/audit-prepare.py $label
done
```

Windows PowerShell:

```powershell
foreach ($label in 'obs-20260118','obs-20260119','obs-20260127','obs-20260209') {
  python scripts/audit-prepare.py $label
}
```

Expected: 4 worksheet CSVs + per-boundary dirs. obs-20260119 has the most matches (9) so will take longest. Total ~5-15 min wall time.

- [ ] **Step 2: Verify outputs**

For each label, confirm worksheet CSV exists and has expected row count (matches × 2 + gaps × 2 per `<label>.metadata.json`).

Expected row counts (from `tests/baselines/v0.3.0/README.md`):
- obs-20260118: 5 matches × 2 + 2 gaps × 2 = 14 rows
- obs-20260119: 9 matches × 2 + 1 gap × 2 = 20 rows
- obs-20260127: 3 matches × 2 + 2 gaps × 2 = 10 rows
- obs-20260209: 3 matches × 2 + 0 gaps × 2 = 6 rows

- [ ] **Step 3: Skip commit (worksheets are gitignored)**

---

## Task 15: Iteration 2 — Idios manual viewing for 4 baselines (HANDOFF)

**Files (manual):**
- Create: `tests/baselines/v0.3.0/ground-truth/obs-20260118.json`
- Create: `tests/baselines/v0.3.0/ground-truth/obs-20260119.json`
- Create: `tests/baselines/v0.3.0/ground-truth/obs-20260127.json`
- Create: `tests/baselines/v0.3.0/ground-truth/obs-20260209.json`

**MANUAL TASK — Idios.** Wall time: 1.5-3 hours.

- [ ] **Step 1: Hand off to Idios**

Send Idios:

```
4 worksheet が `tests/baselines/v0.3.0/audit-worksheet/obs-*.csv` に生成済。Iteration 1 と同じ手順で 4 件分 ground truth を作成してください。

オススメ順 (estimated time):
1. obs-20260209 (57m / 3 matches) — ~30-45 min
2. obs-20260127 (1h01m / 3 matches + 2 gaps) — ~45 min-1h
3. obs-20260118 (2h17m / 5 matches + 2 gaps、F3/F4 確認) — ~1-1.5h
4. obs-20260119 (2h33m / 9 matches) — ~1.5-2h
```

- [ ] **Step 2: Wait for Idios completion**

Pause until all 4 JSON files exist.

- [ ] **Step 3: Validate all 4 JSON schemas**

For each label, run the schema validation snippet from Task 11 Step 3.

- [ ] **Step 4: Commit ground truth**

```bash
git add tests/baselines/v0.3.0/ground-truth/obs-2026{0118,0119,0127,0209}.json
git commit -m "$(cat <<'EOF'
data(audit): #796 ground truth for remaining 4 baselines (Idios manual)

Iteration 2 batch (obs-20260118 / 0119 / 0127 / 0209). Together with
obs-20260116 (Iteration 1) this completes the 5-baseline ground truth set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Iteration 2 — audit-compare + finding classification + cross-recording summary

**Files:**
- Modify: `docs/v030-baseline-audit.md`

4 件分の audit-compare 出力 + finding 分類 + 全 5 件の summary を doc に集約。

- [ ] **Step 1: Run audit-compare for each**

```powershell
foreach ($label in 'obs-20260118','obs-20260119','obs-20260127','obs-20260209') {
  python scripts/audit-compare.py $label | Out-File -Encoding utf8 "$env:TEMP/$label-findings.md"
}
```

- [ ] **Step 2: Append each section to audit doc**

For each label, paste the markdown into `docs/v030-baseline-audit.md` after `## obs-20260116`. Order: 20260116 → 20260118 → 20260119 → 20260127 → 20260209.

For each non-`agreed` finding, fill in `(a)` / `(b)` / `(c)` classification with Idios per §5 rubric.

- [ ] **Step 3: Write cross-recording summary**

Replace the `## Cross-recording summary` placeholder with actual content:

```markdown
## Cross-recording summary

### Totals (all 5 baselines)

| Category | Count |
|---|---|
| Agreed (within ±1s) | (n_agreed) |
| Silent miss | (n_silent_miss) |
| False positive | (n_false_positive) |
| Boundary shift | (n_boundary_shift) |
| **Total findings** | (n_total) |

### Classification

| Class | Count | Notes |
|---|---|---|
| (a) baseline 修正 | (n_a) | baseline metadata.json regenerate 対象 |
| (b) detector tuning | (n_b) | 別 issue 起票 (Iron Law 2 bulk confirm 適用) |
| (c) 既知限界 | (n_c) | docs/video-processing.md 追記対象 |

### Decision input for #576 / PR #793 reexamination

(short 数行: PR #793 の accuracy が ground truth に対して何 % か / 残課題 / 次に着手すべき detector tuning issue 番号 list)
```

- [ ] **Step 4: Update audit doc status header**

Change `> Status: Iteration 1 / 5 (obs-20260116 PoC)` to `> Status: complete (5/5 baselines audited)`.

- [ ] **Step 5: Lint markdown**

Run: `bash scripts/check-markdownlint.sh docs/v030-baseline-audit.md`
Expected: green. Fix violations per `docs/markdownlint-guide.md`.

- [ ] **Step 6: Commit**

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #796 Iteration 2 4-baseline findings + cross-recording summary

Completes ground-truth audit for all 5 v0.3.0 OBS baselines. Findings
classified per §5 rubric ((a)/(b)/(c)). Input ready for #576 / PR #793
reexamination spec.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: (b) detector tuning — new issues (Iron Law 2 bulk confirm)

**Files (no repo files changed):**
- GitHub: new issues per (b) finding

(b) 該当 finding を別 issue で起票する。Iron Law 2 を厳守。

- [ ] **Step 1: List (b) findings**

Extract all `(b)` classifications from `docs/v030-baseline-audit.md` and group by detector subsystem (e.g., "sub-sample boundary detection", "scorebar misclassification", "audio promotion FP"). One issue per coherent root cause; do not split per-recording.

- [ ] **Step 2: Decide branch by count**

- 0 (b) findings → skip to Task 18.
- 1-2 (b) findings → ask Idios individually for each issue (no bulk confirm needed).
- 3+ (b) findings → **Iron Law 2 bulk confirm**: present a sample issue + "全件 OK / 個別調整 / やめる" 3-option AskUserQuestion to Idios.

- [ ] **Step 3: Create issues per `/create-task` skill**

For each issue, use the `/create-task` skill (or `gh issue create`) following `docs/issue-policy.md`. Title format: `[refactor] L3: detect tuning — <subsystem> (audit #796 から)` or `[task] L3: ...`. Body includes:
- Preamble (期待値 / 現状 / ユーザー影響・重要性)
- Cross-link to `docs/v030-baseline-audit.md#obs-<recording>` section
- Cross-link to #796
- Acceptance criteria (TBD by Idios per issue policy)
- Label `P2-medium` / `P3-low` per Idios judgment

- [ ] **Step 4: Cross-link issues back to audit doc**

For each created issue, update `docs/v030-baseline-audit.md` to add the issue number in the finding row's classification column: `(b) #<issue>` instead of bare `(b)`.

- [ ] **Step 5: Commit audit doc cross-links**

```bash
git add docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs(audit): #796 cross-link (b) findings to detector tuning issues

Adds new-issue numbers to the Classification column for (b) findings.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: (c) known limitation documentation

**Files:**
- Modify: `docs/video-processing.md` (if (c) finding exists)
- Modify: `CLAUDE.md` (if (c) finding warrants top-level mention)
- GitHub: P3-low issue for tracking

- [ ] **Step 1: Decide if doc update is needed**

- 0 (c) findings → skip task.
- 1+ (c) findings → proceed.

- [ ] **Step 2: Update docs/video-processing.md**

Add an entry under "既知の制限" (create section if not present) summarizing each (c) finding. Cross-link to `docs/v030-baseline-audit.md`.

- [ ] **Step 3: Decide CLAUDE.md mention**

If any (c) finding is widely relevant to future detector work (e.g., trade-off between `min_blackout_duration` and miss rate), add a one-line summary to `CLAUDE.md` §「検出の動作確認済み環境と制限事項」.

- [ ] **Step 4: Open P3-low tracking issue**

Create one P3-low issue summarizing the documented limitations, with cross-link to the audit doc. (Per spec §5 "(c) 既知限界 ... `P3-low 別 issue で実施`".)

- [ ] **Step 5: Lint markdown**

Run: `bash scripts/check-markdownlint.sh docs/video-processing.md docs/v030-baseline-audit.md CLAUDE.md`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add docs/video-processing.md CLAUDE.md docs/v030-baseline-audit.md
git commit -m "$(cat <<'EOF'
docs: #796 document (c) known limitations from baseline audit

Adds 'docs/video-processing.md §既知の制限' entries cross-linked to
docs/v030-baseline-audit.md. P3-low tracking issue: #<n>.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: PR Pre-flight (Iron Law 6 Step 0-5)

**Files (no changes):**
- (verification only)

Iron Law 6 Pre-flight 5 step を実行してから PR 作成。

- [ ] **Step 0: Hard gate — concurrent PRs**

Run: `gh pr list --search "796" --state open`
Expected: no open PR referencing #796 (other than the one we're about to push). If any, STOP and ask Idios.

- [ ] **Step 1: Base sync**

Run: `git fetch origin main`

- [ ] **Step 2: Identify unmerged base commits since branch point**

Run: `git log HEAD..origin/main --oneline`
Expected: list of commits on main since branch point. Note count.

- [ ] **Step 3: Touched files intersection check**

Run: `git diff origin/main..HEAD --name-only` and compare with `git diff HEAD~50..HEAD --name-only` on main. Identify any touched-file overlap with recent main commits → likely conflicts.

If overlap found, plan a rebase / merge.

- [ ] **Step 4: Parallel PR re-check**

Run: `gh pr list --search "796" --state all`
Expected: only the PR we're creating + closed PRs (if any retrospect).

- [ ] **Step 5: Codex adversarial review**

Run: `/codex:adversarial-review` (skill invocation) with focus:

```
audit script の reproducibility (deterministic worksheet generation across runs),
ground truth schema vs vtuber-primary-ground-truth.json consistency,
finding classification rubric の網羅性 (4 type × 3 class = 12 case 全部 covered か),
Iron Law 3 risk (scope creep into PR #793 modifications)
```

Address PROCEED_WITH_AMENDMENTS findings inline before PR.

- [ ] **Step 6: Path 別自動チェック final pass**

Run: `ruff check . && ruff format --check . && pyright scripts/ tests/test_audit_prepare.py tests/test_audit_compare.py && pytest -m "not slow" --tb=short`
Expected: all green. GUI side (npm / cargo) は本 PR 対象外。`bash scripts/check-markdownlint.sh` も green。

- [ ] **Step 7: Confirm with Idios**

Present Iron Law 6 result summary and ask Idios for go-ahead on PR creation.

---

## Task 20: PR creation

**Files (no changes):**
- GitHub: new PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin claude/hopeful-germain-8ffc43
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "feat(audit): #796 v0.3.0 OBS baseline ground-truth audit" --body-file - <<'EOF'
## Summary

- v0.3.0 の 5 OBS baseline 全件について Idios 手動 visual verification による ground truth を確立
- 現 baseline (PR #793 head) と ground truth の diff を体系的に洗い出し
- finding を (a) baseline 修正 / (b) detector tuning 別 issue / (c) 既知限界 の trichotomy で分類

## Spec / plan

- Spec: [docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md](docs/superpowers/specs/2026-05-19-v030-baseline-audit-design.md)
- Plan: [docs/superpowers/plans/2026-05-19-v030-baseline-ground-truth-audit.md](docs/superpowers/plans/2026-05-19-v030-baseline-ground-truth-audit.md)
- Target issue: #796

## Deliverables

- [x] `scripts/audit-prepare.py` — pre-screen worksheet generator
- [x] `scripts/audit-compare.py` — diff extractor + markdown formatter
- [x] `tests/test_audit_prepare.py` / `tests/test_audit_compare.py` — unit + integration tests
- [x] `tests/baselines/v0.3.0/ground-truth/obs-*.json` — 5 manual ground truth files (Idios)
- [x] `docs/v030-baseline-audit.md` — finding 集約 doc with (a/b/c) classification + cross-recording summary
- [ ] (b) detector tuning 別 issue 起票 (count: N)
- [ ] (c) 既知限界 docs/video-processing.md 追記 + P3-low 追跡 issue

## Acceptance criteria (issue #796)

(Map each from issue body — fill machine-verified vs unverifiable; see docs/l2-workflow.md §Self-Test Report 規約)

- [x] Idios が 5 OBS baseline を視覚確認、`tests/baselines/v0.3.0/ground-truth/<recording>.json` 全件揃う
- [x] 現 baseline と ground truth の diff を `docs/v030-baseline-audit.md` に列挙
- [x] 各 finding を (a/b/c) 分類
- [x] (b) 該当を別 issue 起票 (Iron Law 2 bulk confirm 適用)
- 残 condition: reexamination spec §4 追記 = 別 brainstorming (本 issue scope 外、§9 Out of scope)

## Self-Test Report

(checklist per docs/l2-workflow.md §Self-Test Report 規約)

- [x] `ruff check .` PASS
- [x] `ruff format --check .` PASS
- [x] `pyright scripts/ tests/` PASS
- [x] `pytest -m "not slow"` PASS (no new failures)
- [x] `bash scripts/check-markdownlint.sh` PASS
- [x] Iron Law 6 Pre-flight Step 0-5 全 PASS

Machine-unverifiable:
- Idios 視覚確認による ground truth 精度
- Iteration 1 PoC → Iteration 2 への workflow feedback

## Iron Law check

- Iron Law 1 ✅ — 受け入れ条件 mapping を PR 本文に逐条
- Iron Law 2 ✅ — (b) 別 issue 起票時に bulk confirm
- Iron Law 3 ✅ — scope strictly 5 baseline audit + (a/b/c) trichotomy
- Iron Law 4 ✅ — Closes / Fixes / Resolves 不使用、手動 close
- Iron Law 5 ✅ — brainstorming で AskUserQuestion 全件適用済
- Iron Law 6 ✅ — Pre-flight Step 0-5 全 pass、Codex adversarial-review PROCEED

## 関連

- 対象 issue: #796
- Blocking PR: #793 (#576 fps filter retirement) — 本 audit 完了後の reexamination spec で merge / defer 判断
- 関連 issue: #576 / #560 / #281 / #778 / #779
EOF
```

- [ ] **Step 3: Confirm PR URL**

The `gh pr create` command outputs the PR URL. Report to Idios.

- [ ] **Step 4: Skip merge — audit completion ≠ #793 reexamination**

Do not merge yet. The next session uses `/iterate-review <PR#>` (Iron Law 6 enforced) to address review findings. After merge, the **separate reexamination spec brainstorming** uses the merged audit as input.

---

## Self-Review

Reviewed against the spec sections:

- **§1 背景 / §1.2 本質的問題**: covered by overall plan goal + Task 16 cross-recording summary.
- **§2 採用方針**: hyphen naming (Task 9 spec touch-up), `.json` format (Task 11 schema), increment (Task 10-13 PoC / Task 14-16 batch), spec placement (Task 0 N/A — already committed), separate audit doc (Task 12), reexamination out of scope (Task 19/20 cross-link).
- **§3.1 Stage 1**: Tasks 2-6 (worksheet + brightness + PNG + main).
- **§3.2 Stage 2**: Task 11 (Iteration 1 manual) / Task 15 (Iteration 2 manual).
- **§3.3 Stage 3**: Task 7-8 (audit-compare diff + format) / Task 12 (Iteration 1 classify) / Task 16 (Iteration 2 classify + summary).
- **§4 Components**: every file in §4 has a creating Task.
- **§5 rubric**: enforced in Task 12 Step 2 / Task 16 Step 2 (Idios fills (a/b/c)).
- **§6 Increment plan**: Tasks 10-13 = Iteration 1, Tasks 14-16 = Iteration 2.
- **§7 Edge cases**: surface mention in Task 10 Step 1 (env var absence), Task 11 Step 3 (JSON schema validation), Task 17 Step 2 (Iron Law 2 bulk confirm), Task 14 Step 2 (row count sanity check).
- **§8 Testing**: scripts have unit + integration tests (Tasks 2-8). Audit doc verification = Task 16 Step 5 markdownlint + Task 17 Step 4 cross-link integrity.
- **§9 Out of scope**: enforced in Task 19/20 (PR body explicitly mentions reexamination spec is separate).
- **§10 Acceptance criteria mapping**: Task 20 PR body lists each.

**Placeholder scan**: No "TBD" / "TODO" / "implement later" / "Add error handling" / "Similar to Task N". Each step contains the actual content needed.

**Type consistency**: function names `build_worksheet_rows` / `resolve_video_path` / `export_brightness_csv` / `export_sample_frames` / `write_worksheet_csv` / `main` (audit-prepare); `classify_findings` / `_extract_boundaries` / `_format_delta` / `_format_ts` / `format_markdown` / `main` (audit-compare) — used consistently across all tasks.

**Gap fixes**: none required.
