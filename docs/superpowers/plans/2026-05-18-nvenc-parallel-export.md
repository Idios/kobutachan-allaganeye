# NVENC Parallel Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** issue #761 解決。CLI + GUI 両側で H.264 export を Python 一本化し、NVENC 物理 engine 数に応じた N 並列実行で ~3x スループット改善を実現する。

**Architecture:** Python `allaganeye/export/` 新設で encoder/SKU probe/ffmpeg runner/parallel pool を集約。GUI Tauri は subprocess (`start_detect` 同形) で Python を呼び出す薄い wrapper になる。in-memory metadata は stdin 経由で Python に渡し sample mode を維持。

**Tech Stack:** Python 3.13 (Typer + ThreadPoolExecutor + json), Rust (tokio::process), TypeScript (React + Tauri 2), pytest + vitest + cargo test, ffmpeg 8.1 LGPL build (BtbN)

**Spec:** [docs/superpowers/specs/2026-05-18-nvenc-parallel-export-design.md](../specs/2026-05-18-nvenc-parallel-export-design.md)

---

## File Structure

### Python (新規)

| Path | Responsibility |
| --- | --- |
| `allaganeye/export/__init__.py` | public API re-export (H264Encoder / EncoderSlot / export_matches / enumerate_h264_encoders / probe_nvenc_engine_count / ExportSummary / ExportError) |
| `allaganeye/export/schema.py` | wire 用 dataclass (ProgressEvent, ExportResult, ExportSummary, ExportError) + JSON serializer |
| `allaganeye/export/encoder.py` | H264Encoder enum, EncoderSlot dataclass, select_h264_encoder, enumerate_h264_encoders |
| `allaganeye/export/nvenc_probe.py` | probe_nvenc_engine_count (SKU table + env override + multi-GPU min) |
| `allaganeye/export/ffmpeg_runner.py` | run_export_attempt (1 ffmpeg + libx264 fallback retry), is_gpu_encoder_failure |
| `allaganeye/export/pool.py` | export_matches (ThreadPoolExecutor + 共有 writer lock) |
| `allaganeye/export/wire.py` | WireWriter (stdout JSON Lines emitter with threading.Lock) |
| `allaganeye/commands/export.py` | Typer `export` command (rich progress / --json / --stdin) |
| `allaganeye/commands/encoder_slots.py` | Typer hidden `encoder-slots` command (GUI subprocess用、JSON 配列出力) |

### Python (変更)

| Path | Responsibility |
| --- | --- |
| `allaganeye/cli.py` | `export` / `encoder-slots` を typer app に登録 (既存 `@app.command()` style) |

### Python tests (新規)

| Path | Responsibility |
| --- | --- |
| `tests/test_export_schema.py` | ProgressEvent / ExportSummary JSON ラウンドトリップ |
| `tests/test_export_encoder.py` | select_h264_encoder / enumerate_h264_encoders 各シナリオ |
| `tests/test_export_nvenc_probe.py` | SKU table / env override / 不明 GPU / 多 GPU min |
| `tests/test_export_ffmpeg_runner.py` | mock subprocess で libx264 fallback / cancel / progress |
| `tests/test_export_pool.py` | concurrency 上限 / cancel / partial failure / writer lock |
| `tests/test_export_wire_protocol.py` (slow) | 実 subprocess で ndjson out / Python→stdout 順序整合 |
| `tests/test_export_cli.py` (slow) | 実 libx264 で end-to-end export |
| `tests/test_encoder_slots_cli.py` | encoder-slots CLI の JSON 配列出力 |

### Rust (変更)

| Path | Responsibility |
| --- | --- |
| `gui/src-tauri/src/lib.rs` | 旧 export ロジック削除 + `start_export` / `enumerate_h264_encoders` 追加。generate_handler! は **lib.rs:3303 + 3332** の 2 箇所更新 (main.rs ではない、Codex review #1) |

### Frontend (変更)

| Path | Responsibility |
| --- | --- |
| `gui/src/screens/ExportScreen.tsx` | handleStartExport を 1 invoke 化、encoder slot 列表示 |
| `gui/src/screens/__tests__/ExportScreen.test.tsx` | テスト更新 |

### Docs (変更)

| Path | Responsibility |
| --- | --- |
| `docs/cli-spec.md` | `allaganeye export` section 追加 |
| `docs/output-spec.md` | export 出力仕様マトリクスに追記 |

---

## Implementation Tasks

### Task 1: schema.py — wire 用 dataclass

**Files:**

- Create: `allaganeye/export/__init__.py`
- Create: `allaganeye/export/schema.py`
- Test: `tests/test_export_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_schema.py`:

```python
"""Tests for export wire-protocol schema (#761)."""

from __future__ import annotations

import json
from pathlib import Path

from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)


def test_progress_event_progress_serializes_to_ndjson_line():
    ev = ProgressEvent.progress(match_index=0, percent=12.5, stage="encoding")
    line = ev.to_json_line()
    parsed = json.loads(line)
    assert parsed == {
        "type": "progress",
        "match_index": 0,
        "percent": 12.5,
        "stage": "encoding",
    }
    assert line.endswith("\n")


def test_progress_event_fallback_serializes():
    ev = ProgressEvent.fallback(
        match_index=2,
        fallback_from="h264_nvenc",
        fallback_to="libx264",
        message="NVENC init failed",
    )
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "fallback"
    assert parsed["fallback_from"] == "h264_nvenc"
    assert parsed["fallback_to"] == "libx264"


def test_progress_event_result_includes_output_path_and_encoder():
    ev = ProgressEvent.result(
        match_index=1,
        output_path=Path("/tmp/match_001.mp4"),
        duration_ms=12345,
        encoder_used="h264_nvenc",
    )
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "result"
    assert parsed["output_path"] == "/tmp/match_001.mp4"
    assert parsed["duration_ms"] == 12345
    assert parsed["encoder_used"] == "h264_nvenc"


def test_progress_event_error_includes_hint():
    err = ExportError(kind="ffmpeg.exit_failed", message="exit 1", hint="see stderr tail")
    ev = ProgressEvent.error(match_index=3, error=err)
    parsed = json.loads(ev.to_json_line())
    assert parsed["type"] == "error"
    assert parsed["error_kind"] == "ffmpeg.exit_failed"
    assert parsed["error_message"] == "exit 1"
    assert parsed["error_hint"] == "see stderr tail"


def test_progress_event_error_hint_none():
    err = ExportError(kind="cancelled", message="user requested")
    ev = ProgressEvent.error(match_index=0, error=err)
    parsed = json.loads(ev.to_json_line())
    assert parsed["error_hint"] is None


def test_export_summary_to_json_line():
    summary = ExportSummary(success=2, failure=1, skipped=0, cancelled=False)
    ev = ProgressEvent.summary(summary)
    parsed = json.loads(ev.to_json_line())
    assert parsed == {
        "type": "summary",
        "success": 2,
        "failure": 1,
        "skipped": 0,
        "cancelled": False,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'allaganeye.export'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/__init__.py`:

```python
"""Parallel H.264 export pipeline (#761).

Public API only — implementation details live in submodules.
"""

from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)

__all__ = [
    "ExportError",
    "ExportResult",
    "ExportSummary",
    "ProgressEvent",
]
```

`allaganeye/export/schema.py`:

```python
"""Wire-protocol dataclasses for stdout JSON Lines (#761).

The CLI ``allaganeye export --json`` and the GUI subprocess emit one
JSON object per line on stdout. Rust ``start_export`` parses each line
into ``ExportProgress`` Tauri events. See spec §5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExportResult:
    """Successful per-match export outcome."""

    match_index: int
    output_path: Path
    duration_ms: int
    encoder_used: str
    fallback_from: str | None = None  # set when libx264 retry kicked in


class ExportError(Exception):
    """Per-match export failure with optional corrective hint."""

    def __init__(self, kind: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.hint = hint


@dataclass
class ExportSummary:
    """Terminal aggregate emitted as the last JSON line."""

    success: int = 0
    failure: int = 0
    skipped: int = 0
    cancelled: bool = False


@dataclass(frozen=True)
class ProgressEvent:
    """One JSON line emitted on stdout (--json mode)."""

    payload: dict[str, Any]

    def to_json_line(self) -> str:
        """Serialize to a single ndjson line (terminated with ``\\n``)."""
        return json.dumps(self.payload, ensure_ascii=False) + "\n"

    @classmethod
    def progress(cls, match_index: int, percent: float, stage: str) -> ProgressEvent:
        return cls({
            "type": "progress",
            "match_index": match_index,
            "percent": percent,
            "stage": stage,
        })

    @classmethod
    def fallback(
        cls,
        match_index: int,
        fallback_from: str,
        fallback_to: str,
        message: str,
    ) -> ProgressEvent:
        return cls({
            "type": "fallback",
            "match_index": match_index,
            "fallback_from": fallback_from,
            "fallback_to": fallback_to,
            "message": message,
        })

    @classmethod
    def result(
        cls,
        match_index: int,
        output_path: Path,
        duration_ms: int,
        encoder_used: str,
    ) -> ProgressEvent:
        return cls({
            "type": "result",
            "match_index": match_index,
            "output_path": str(output_path),
            "duration_ms": duration_ms,
            "encoder_used": encoder_used,
        })

    @classmethod
    def error(cls, match_index: int, error: ExportError) -> ProgressEvent:
        return cls({
            "type": "error",
            "match_index": match_index,
            "error_kind": error.kind,
            "error_message": error.message,
            "error_hint": error.hint,
        })

    @classmethod
    def summary(cls, summary: ExportSummary) -> ProgressEvent:
        return cls({
            "type": "summary",
            "success": summary.success,
            "failure": summary.failure,
            "skipped": summary.skipped,
            "cancelled": summary.cancelled,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_schema.py -v`
Expected: PASS — all 6 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_schema.py
ruff format allaganeye/export tests/test_export_schema.py
pyright allaganeye/export tests/test_export_schema.py
git add allaganeye/export/ tests/test_export_schema.py
git commit -m "feat(export): wire-protocol schema (#761)

ProgressEvent, ExportResult, ExportSummary, ExportError dataclasses
for stdout JSON Lines emitted by allaganeye export --json.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: encoder.py — H264Encoder enum + EncoderSlot + select_h264_encoder

**Files:**

- Create: `allaganeye/export/encoder.py`
- Modify: `allaganeye/export/__init__.py`
- Test: `tests/test_export_encoder.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_encoder.py`:

```python
"""Tests for export encoder selection (#761).

Mirrors gui/src-tauri/src/lib.rs::tests::select_h264_encoder_* coverage
(those tests are removed in a later task as the logic moves to Python).
"""

from __future__ import annotations

import pytest

from allaganeye.export.encoder import (
    EncoderSlot,
    H264Encoder,
    select_h264_encoder,
)


def test_h264_encoder_ffmpeg_codec_name():
    assert H264Encoder.LIBX264.value == "libx264"
    assert H264Encoder.NVENC.value == "h264_nvenc"
    assert H264Encoder.QSV.value == "h264_qsv"
    assert H264Encoder.AMF.value == "h264_amf"


def test_h264_encoder_display_label():
    assert H264Encoder.NVENC.display_label == "NVENC"
    assert H264Encoder.LIBX264.display_label == "libx264 (CPU)"


def test_h264_encoder_quality_args_nvenc():
    """quality args mirror gui/src-tauri/src/lib.rs:1628-1630 (#591 baseline)."""
    args = H264Encoder.NVENC.quality_args()
    assert args == ("-rc", "vbr", "-cq", "19", "-preset", "p5")


def test_h264_encoder_quality_args_libx264():
    args = H264Encoder.LIBX264.quality_args()
    assert args == ("-crf", "18", "-preset", "medium")


def test_h264_encoder_quality_args_qsv():
    args = H264Encoder.QSV.quality_args()
    assert args == ("-global_quality", "20", "-look_ahead", "1", "-preset", "medium")


def test_h264_encoder_quality_args_amf():
    args = H264Encoder.AMF.quality_args()
    assert args == ("-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21")


# --- select_h264_encoder ---


def test_select_first_pref_match():
    assert select_h264_encoder(
        vendors=["nvidia", "amd"], preference=["nvidia", "amd", "intel"]
    ) == H264Encoder.NVENC


def test_select_skips_unavailable_first_pref():
    assert select_h264_encoder(
        vendors=["amd"], preference=["nvidia", "amd", "intel"]
    ) == H264Encoder.AMF


def test_select_intel_qsv():
    assert select_h264_encoder(
        vendors=["intel"], preference=["nvidia", "amd", "intel"]
    ) == H264Encoder.QSV


def test_select_libx264_fallback_when_no_vendor_match():
    assert select_h264_encoder(
        vendors=[], preference=["nvidia", "amd", "intel"]
    ) == H264Encoder.LIBX264


def test_select_libx264_fallback_when_pref_empty():
    assert select_h264_encoder(
        vendors=["nvidia"], preference=[]
    ) == H264Encoder.LIBX264


def test_select_libx264_fallback_unknown_vendor():
    """Unknown vendor strings (typos, future entries) ignored — libx264 fallback."""
    assert select_h264_encoder(
        vendors=["mali"], preference=["mali", "nvidia"]
    ) == H264Encoder.LIBX264


# --- EncoderSlot ---


def test_encoder_slot_is_frozen_dataclass():
    slot = EncoderSlot(slot_index=0, encoder_kind=H264Encoder.NVENC, display_label="NVENC #1")
    with pytest.raises(Exception):
        slot.slot_index = 1  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_encoder.py -v`
Expected: FAIL with `ImportError: cannot import name 'H264Encoder'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/encoder.py`:

```python
"""H.264 encoder selection logic (#761).

Ported from gui/src-tauri/src/lib.rs:1597-1678 (H264Encoder + select_h264_encoder)
so CLI and GUI share a single source of truth. See spec §4.1.

NOTE: enumerate_h264_encoders depends on probe_nvenc_engine_count which lives
in nvenc_probe.py — that import is added in Task 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class H264Encoder(Enum):
    """H.264 encoder identifiers.

    The ``value`` is the literal ``-c:v`` argument passed to ffmpeg.
    """

    LIBX264 = "libx264"
    NVENC = "h264_nvenc"
    QSV = "h264_qsv"
    AMF = "h264_amf"

    @property
    def display_label(self) -> str:
        return _DISPLAY_LABELS[self]

    def quality_args(self) -> tuple[str, ...]:
        """Vendor-specific quality / preset args.

        Ported from gui/src-tauri/src/lib.rs:1621-1642 (#591 baseline).
        Targets visual parity with libx264 CRF 18; RD curves differ per
        encoder so the mapping is approximate.
        """
        return _QUALITY_ARGS[self]


_DISPLAY_LABELS: dict[H264Encoder, str] = {
    H264Encoder.LIBX264: "libx264 (CPU)",
    H264Encoder.NVENC: "NVENC",
    H264Encoder.QSV: "QSV",
    H264Encoder.AMF: "AMF",
}

_QUALITY_ARGS: dict[H264Encoder, tuple[str, ...]] = {
    H264Encoder.LIBX264: ("-crf", "18", "-preset", "medium"),
    H264Encoder.NVENC: ("-rc", "vbr", "-cq", "19", "-preset", "p5"),
    H264Encoder.QSV: ("-global_quality", "20", "-look_ahead", "1", "-preset", "medium"),
    H264Encoder.AMF: ("-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21"),
}


@dataclass(frozen=True)
class EncoderSlot:
    """One parallel worker's encoder assignment.

    Phase 1 (#761): all NVENC slots are identical (just differ by ``slot_index``).
    Phase 2 (#762): slots may be mixed vendor (Nvenc#0, Nvenc#1, Amf#0).
    """

    slot_index: int
    encoder_kind: H264Encoder
    display_label: str


def select_h264_encoder(vendors: list[str], preference: list[str]) -> H264Encoder:
    """First vendor preference present in ``vendors`` → its encoder; libx264 fallback.

    Equivalent to gui/src-tauri/src/lib.rs:1666-1678. Unknown vendor strings
    in ``preference`` are skipped.
    """
    for pref in preference:
        if pref in vendors:
            match pref:
                case "nvidia":
                    return H264Encoder.NVENC
                case "intel":
                    return H264Encoder.QSV
                case "amd":
                    return H264Encoder.AMF
                case _:
                    continue
    return H264Encoder.LIBX264
```

Update `allaganeye/export/__init__.py`:

```python
"""Parallel H.264 export pipeline (#761)."""

from allaganeye.export.encoder import EncoderSlot, H264Encoder, select_h264_encoder
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)

__all__ = [
    "EncoderSlot",
    "ExportError",
    "ExportResult",
    "ExportSummary",
    "H264Encoder",
    "ProgressEvent",
    "select_h264_encoder",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_encoder.py -v`
Expected: PASS — all 13 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_encoder.py
ruff format allaganeye/export tests/test_export_encoder.py
pyright allaganeye/export tests/test_export_encoder.py
git add allaganeye/export/ tests/test_export_encoder.py
git commit -m "feat(export): H264Encoder enum + EncoderSlot + select_h264_encoder (#761)

Ported from gui/src-tauri/src/lib.rs:1597-1678 (#591 baseline).
Rust enum/function removal happens in a later task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: nvenc_probe.py — SKU table + env override + multi-GPU min

**Files:**

- Create: `allaganeye/export/nvenc_probe.py`
- Modify: `allaganeye/export/__init__.py`
- Test: `tests/test_export_nvenc_probe.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_nvenc_probe.py`:

```python
"""Tests for NVENC engine count probe (#761).

SKU table from spec §4.2. Codex review #9 enforces fallback=1 for
unknown NVIDIA cards.
"""

from __future__ import annotations

import pytest

from allaganeye.export.nvenc_probe import probe_nvenc_engine_count


# --- SKU table lookups ---


def test_rtx_5090_returns_3():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090 (32GB VRAM)"]) == 3


def test_rtx_5090_case_insensitive():
    assert probe_nvenc_engine_count(["nvidia geforce rtx 5090"]) == 3


def test_rtx_4090_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4090 (24GB VRAM)"]) == 2


def test_rtx_4080_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4080 (16GB VRAM)"]) == 2


def test_rtx_4070_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4070"]) == 2


def test_rtx_4060_returns_1():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 4060 (8GB VRAM)"]) == 1


def test_rtx_5080_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5080"]) == 2


def test_rtx_5070_returns_2():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5070"]) == 2


def test_rtx_5060_returns_1():
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5060"]) == 1


# --- Fallback ---


def test_unknown_nvidia_falls_back_to_1():
    """Codex review #9: 不明 NVIDIA は保守的に 1 (default は 1-engine 想定)."""
    assert probe_nvenc_engine_count(["NVIDIA GeForce GTX 1660"]) == 1


def test_empty_list_falls_back_to_1():
    assert probe_nvenc_engine_count([]) == 1


def test_non_nvidia_falls_back_to_1():
    """vendor 選択ロジック側で NVENC が選ばれた前提なのでここに来るのは異例。
    多くの環境では nvidia-smi 検出済みのはずだが、想定外も 1 で fallback。"""
    assert probe_nvenc_engine_count(["AMD Radeon RX 7900 XT"]) == 1


# --- env override ---


def test_env_override_takes_precedence(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "5")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 5


def test_env_override_invalid_falls_through(monkeypatch: pytest.MonkeyPatch):
    """Non-digit env value is ignored — SKU table consulted normally."""
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "auto")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


def test_env_override_zero_falls_through(monkeypatch: pytest.MonkeyPatch):
    """0 is invalid (would mean no workers) — fall back to SKU table."""
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "0")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


def test_env_override_empty_falls_through(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "")
    assert probe_nvenc_engine_count(["NVIDIA GeForce RTX 5090"]) == 3


# --- Multi-GPU conservative min (Codex review #12) ---


def test_multi_gpu_takes_minimum_engine_count():
    """RTX 5090 (3 engine) + RTX 4060 (1 engine) → 1 (conservative)."""
    assert (
        probe_nvenc_engine_count([
            "NVIDIA GeForce RTX 5090",
            "NVIDIA GeForce RTX 4060",
        ])
        == 1
    )


def test_multi_gpu_with_unknown_uses_min_of_known():
    """RTX 4090 (2) + unknown card → 2 (unknown doesn't pollute the table match)."""
    assert (
        probe_nvenc_engine_count([
            "NVIDIA GeForce RTX 4090",
            "Future Unknown Card 9000",
        ])
        == 2
    )


def test_multi_same_sku_returns_same_count():
    """2x RTX 5090 → 3 (matches present but min == 3)."""
    assert (
        probe_nvenc_engine_count([
            "NVIDIA GeForce RTX 5090",
            "NVIDIA GeForce RTX 5090",
        ])
        == 3
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_nvenc_probe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'allaganeye.export.nvenc_probe'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/nvenc_probe.py`:

```python
"""NVENC physical engine count probe via SKU table (#761).

See spec §4.2 / §9 for design rationale (live nvidia-smi probe rejected).
Codex review #9 sets fallback=1; review #12 enforces conservative min for
multi-GPU.
"""

from __future__ import annotations

import os

# (GPU model substring (lowercased), NVENC engine count)
# NVIDIA 公式 spec sheet 基準。新 SKU 追加時は本テーブルを更新。
_SKU_TABLE: tuple[tuple[str, int], ...] = (
    # RTX 50 series
    ("rtx 5090", 3),
    ("rtx 5080", 2),
    ("rtx 5070", 2),
    ("rtx 5060", 1),
    # RTX 40 series
    ("rtx 4090", 2),
    ("rtx 4080", 2),
    ("rtx 4070", 2),
    ("rtx 4060", 1),
)

_DEFAULT_NVENC_COUNT = 1
"""Codex review #9: 不明 NVIDIA カードは保守的に 1 (1-engine card の subprocess
setup overhead を避けるため)。user が高 N を望むなら env override で。"""


def probe_nvenc_engine_count(gpu_models: list[str]) -> int:
    """NVENC engine count を SKU table から決定する。

    優先順:
    1. env var ``ALLAGANEYE_EXPORT_CONCURRENCY`` が正の整数 → そのまま採用
       (OBS 録画中等の contention scenario に user が manual 設定するエスケープハッチ)
    2. ``gpu_models`` のいずれかが SKU table の substring に hit
       → 全 hit の **最小値** (Codex review #12: 複数 GPU 環境で弱い側に揃える)
    3. fallback → ``_DEFAULT_NVENC_COUNT`` (= 1)
    """
    override = os.environ.get("ALLAGANEYE_EXPORT_CONCURRENCY", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)

    lc = [m.lower() for m in gpu_models]
    matched_counts: list[int] = []
    for needle, count in _SKU_TABLE:
        if any(needle in m for m in lc):
            matched_counts.append(count)
    if matched_counts:
        return min(matched_counts)
    return _DEFAULT_NVENC_COUNT
```

Update `allaganeye/export/__init__.py` to add `probe_nvenc_engine_count`:

```python
"""Parallel H.264 export pipeline (#761)."""

from allaganeye.export.encoder import EncoderSlot, H264Encoder, select_h264_encoder
from allaganeye.export.nvenc_probe import probe_nvenc_engine_count
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)

__all__ = [
    "EncoderSlot",
    "ExportError",
    "ExportResult",
    "ExportSummary",
    "H264Encoder",
    "ProgressEvent",
    "probe_nvenc_engine_count",
    "select_h264_encoder",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_nvenc_probe.py -v`
Expected: PASS — all 17 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_nvenc_probe.py
ruff format allaganeye/export tests/test_export_nvenc_probe.py
pyright allaganeye/export tests/test_export_nvenc_probe.py
git add allaganeye/export/ tests/test_export_nvenc_probe.py
git commit -m "feat(export): NVENC engine count SKU probe (#761)

SKU table + ALLAGANEYE_EXPORT_CONCURRENCY env override + multi-GPU
conservative min. Default=1 for unknown NVIDIA (Codex review #9).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: encoder.py — enumerate_h264_encoders integration

**Files:**

- Modify: `allaganeye/export/encoder.py`
- Modify: `allaganeye/export/__init__.py`
- Modify: `tests/test_export_encoder.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_encoder.py`:

```python
# --- enumerate_h264_encoders ---


def test_enumerate_nvenc_returns_n_slots(monkeypatch: pytest.MonkeyPatch):
    """RTX 5090 → 3 slots, all NVENC."""
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    from allaganeye.export.encoder import enumerate_h264_encoders
    slots = enumerate_h264_encoders(
        vendors=["nvidia"],
        preference=["nvidia", "amd", "intel"],
        gpu_models=["NVIDIA GeForce RTX 5090"],
    )
    assert len(slots) == 3
    assert all(s.encoder_kind == H264Encoder.NVENC for s in slots)
    assert [s.slot_index for s in slots] == [0, 1, 2]
    assert [s.display_label for s in slots] == ["NVENC #1", "NVENC #2", "NVENC #3"]


def test_enumerate_amf_returns_1_slot():
    """AMD iGPU → 1 slot (Phase 2 #762 will add iGPU multi-slot if engine count > 1)."""
    from allaganeye.export.encoder import enumerate_h264_encoders
    slots = enumerate_h264_encoders(
        vendors=["amd"],
        preference=["nvidia", "amd", "intel"],
        gpu_models=["AMD Radeon Graphics"],
    )
    assert len(slots) == 1
    assert slots[0].encoder_kind == H264Encoder.AMF
    assert slots[0].display_label == "AMF"


def test_enumerate_qsv_returns_1_slot():
    from allaganeye.export.encoder import enumerate_h264_encoders
    slots = enumerate_h264_encoders(
        vendors=["intel"],
        preference=["nvidia", "amd", "intel"],
        gpu_models=["Intel UHD Graphics"],
    )
    assert len(slots) == 1
    assert slots[0].encoder_kind == H264Encoder.QSV


def test_enumerate_libx264_fallback_when_no_vendor(monkeypatch: pytest.MonkeyPatch):
    """Empty vendors → 1 libx264 slot (CPU-only env)."""
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    from allaganeye.export.encoder import enumerate_h264_encoders
    slots = enumerate_h264_encoders(
        vendors=[], preference=["nvidia", "amd", "intel"], gpu_models=[]
    )
    assert len(slots) == 1
    assert slots[0].encoder_kind == H264Encoder.LIBX264


def test_enumerate_nvenc_respects_env_override(monkeypatch: pytest.MonkeyPatch):
    """env=2 forces 2 slots even on RTX 5090 (would otherwise be 3)."""
    monkeypatch.setenv("ALLAGANEYE_EXPORT_CONCURRENCY", "2")
    from allaganeye.export.encoder import enumerate_h264_encoders
    slots = enumerate_h264_encoders(
        vendors=["nvidia"],
        preference=["nvidia", "amd", "intel"],
        gpu_models=["NVIDIA GeForce RTX 5090"],
    )
    assert len(slots) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_encoder.py -v -k enumerate`
Expected: FAIL with `ImportError: cannot import name 'enumerate_h264_encoders'`

- [ ] **Step 3: Add implementation to encoder.py**

Append to `allaganeye/export/encoder.py`:

```python
def enumerate_h264_encoders(
    vendors: list[str],
    preference: list[str],
    gpu_models: list[str],
) -> list[EncoderSlot]:
    """Vendor + GPU 検出結果から並列実行可能な encoder slot 列を作る。

    Phase 1 (#761): NVENC 選択時のみ N slots、他は 1 slot。
    Phase 2 (#762): mixed vendor slot 列 ``[Nvenc#0, Nvenc#1, Amf#0]`` を返す
    よう拡張可能 (本実装は単一 vendor のみ)。
    """
    # 局所 import で循環依存を避ける (nvenc_probe → encoder の参照は ないが念のため)
    from allaganeye.export.nvenc_probe import probe_nvenc_engine_count

    primary = select_h264_encoder(vendors, preference)
    if primary == H264Encoder.NVENC:
        n = probe_nvenc_engine_count(gpu_models)
        return [
            EncoderSlot(
                slot_index=i,
                encoder_kind=H264Encoder.NVENC,
                display_label=f"NVENC #{i+1}",
            )
            for i in range(n)
        ]
    return [
        EncoderSlot(
            slot_index=0,
            encoder_kind=primary,
            display_label=primary.display_label,
        )
    ]
```

Update `allaganeye/export/__init__.py`:

```python
from allaganeye.export.encoder import (
    EncoderSlot,
    H264Encoder,
    enumerate_h264_encoders,
    select_h264_encoder,
)
# (rest unchanged, add enumerate_h264_encoders to __all__)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_encoder.py -v`
Expected: PASS — all 18 tests green (13 from Task 2 + 5 new)

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_encoder.py
ruff format allaganeye/export tests/test_export_encoder.py
pyright allaganeye/export tests/test_export_encoder.py
git add allaganeye/export/ tests/test_export_encoder.py
git commit -m "feat(export): enumerate_h264_encoders → EncoderSlot list (#761)

Bridges select_h264_encoder + probe_nvenc_engine_count to produce
the parallel slot list consumed by pool.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: wire.py — WireWriter (stdout JSON Lines + threading.Lock)

**Files:**

- Create: `allaganeye/export/wire.py`
- Test: extend `tests/test_export_schema.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export_schema.py`:

```python
import io
import threading
from concurrent.futures import ThreadPoolExecutor


# --- WireWriter (Codex review #4 writer lock) ---


def test_wire_writer_serializes_single_event():
    from allaganeye.export.wire import WireWriter
    sink = io.StringIO()
    w = WireWriter(stream=sink)
    w.emit(ProgressEvent.progress(0, 25.0, "encoding"))
    lines = sink.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["type"] == "progress"


def test_wire_writer_concurrent_writes_atomic():
    """Codex review #4: 複数 thread が同時 emit しても改行までの atomic 性が保たれる."""
    from allaganeye.export.wire import WireWriter
    sink = io.StringIO()
    w = WireWriter(stream=sink)

    def worker(idx: int):
        for p in range(100):
            w.emit(ProgressEvent.progress(idx, float(p), "encoding"))

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(worker, i) for i in range(4)]
        for f in futures:
            f.result()

    lines = sink.getvalue().splitlines()
    assert len(lines) == 400  # 4 workers × 100 events
    # Each line must be valid JSON (interleaved bytes would break parse)
    for line in lines:
        parsed = json.loads(line)
        assert parsed["type"] == "progress"


def test_wire_writer_flush_called_per_emit(monkeypatch: pytest.MonkeyPatch):
    """flush ごとに subprocess buffer が滞留せず GUI に届くこと."""
    from allaganeye.export.wire import WireWriter
    flush_count = 0

    class FlushTracker(io.StringIO):
        def flush(self) -> None:
            nonlocal flush_count
            flush_count += 1

    sink = FlushTracker()
    w = WireWriter(stream=sink)
    w.emit(ProgressEvent.progress(0, 10.0, "encoding"))
    w.emit(ProgressEvent.progress(0, 20.0, "encoding"))
    assert flush_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_schema.py -v -k wire`
Expected: FAIL with `ModuleNotFoundError: No module named 'allaganeye.export.wire'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/wire.py`:

```python
"""Thread-safe stdout JSON Lines emitter (#761).

Codex review #4: 複数 ThreadPoolExecutor worker が直接 ``sys.stdout.write`` を
呼ぶと、CPython の GIL は ``json.dumps`` 単独の atomic 性を保証するが、
``write(json_str)`` → ``write("\\n")`` → ``flush()`` のシーケンス全体が
interleave 可能 (実測で改行が前イベントと混在する事例あり)。本クラスは
``threading.Lock`` で 1 line emit の atomic 性を保証する。
"""

from __future__ import annotations

import sys
import threading
from typing import IO

from allaganeye.export.schema import ProgressEvent


class WireWriter:
    """Serialize ProgressEvent emission to a single output stream."""

    def __init__(self, *, stream: IO[str] | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    def emit(self, event: ProgressEvent) -> None:
        """Write one ndjson line and flush. Thread-safe."""
        line = event.to_json_line()
        with self._lock:
            self._stream.write(line)
            self._stream.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_schema.py -v`
Expected: PASS — all 9 tests green (6 schema + 3 wire)

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_schema.py
ruff format allaganeye/export tests/test_export_schema.py
pyright allaganeye/export tests/test_export_schema.py
git add allaganeye/export/ tests/test_export_schema.py
git commit -m "feat(export): WireWriter thread-safe stdout JSON Lines emitter (#761)

Codex review #4: 1-line atomic emit via threading.Lock for parallel workers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: ffmpeg_runner.py — single-attempt ffmpeg + libx264 fallback retry

**Files:**

- Create: `allaganeye/export/ffmpeg_runner.py`
- Modify: `allaganeye/export/__init__.py`
- Test: `tests/test_export_ffmpeg_runner.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_ffmpeg_runner.py`:

```python
"""Tests for single-attempt ffmpeg runner + libx264 fallback (#761).

Ported from gui/src-tauri/src/lib.rs::tests run_ffmpeg_export_attempt /
is_gpu_encoder_failure coverage. Heavy mocking around subprocess.Popen.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.ffmpeg_runner import (
    is_gpu_encoder_failure,
    run_export_attempt,
)
from allaganeye.export.schema import ExportError


# --- is_gpu_encoder_failure ---


def test_nvenc_no_capable_devices():
    text = "[h264_nvenc @ 0xfff] No NVENC capable devices found"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_nvenc_init_failed():
    text = "Cannot load CUDA driver"
    assert is_gpu_encoder_failure(text, H264Encoder.NVENC)


def test_qsv_mfx_session_creation_failure():
    """Memory: feedback_ffmpeg_qsv_stderr_pattern.md notes 8.1 uses 'Error creating'."""
    text = "[h264_qsv @ 0xfff] Error creating a MFX session: -3 (unsupported)"
    assert is_gpu_encoder_failure(text, H264Encoder.QSV)


def test_amf_dll_failure():
    text = "DLL amfrt64.dll failed to open"
    assert is_gpu_encoder_failure(text, H264Encoder.AMF)


def test_libx264_never_triggers_fallback():
    """libx264 itself is the fallback target — fallback predicate is False."""
    text = "anything"
    assert not is_gpu_encoder_failure(text, H264Encoder.LIBX264)


def test_unrelated_error_not_classified_as_gpu_init():
    text = "Conversion failed!"
    assert not is_gpu_encoder_failure(text, H264Encoder.NVENC)


# --- run_export_attempt: success path ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_success(mock_popen: MagicMock, tmp_path: Path):
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(side_effect=[
        b"frame=  100 fps=30 q=23.0 size=    256kB time=00:00:01.00 bitrate=2097.2kbits/s speed=1x    \n",
        b"out_time_ms=1000000\n",
        b"progress=continue\n",
        b"out_time_ms=2000000\n",
        b"progress=end\n",
        b"",  # EOF
    ])
    proc.wait = MagicMock(return_value=0)
    proc.returncode = 0
    mock_popen.return_value = proc

    progress_calls: list[tuple[float, str]] = []

    def cb(percent: float, stage: str):
        progress_calls.append((percent, stage))

    result = run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=cb,
        fallback_cb=None,
        cancel_event=threading.Event(),
    )
    assert result.encoder_used == H264Encoder.NVENC
    assert result.fallback_from is None
    assert any(stage == "encoding" for _, stage in progress_calls)


# --- run_export_attempt: libx264 fallback ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_nvenc_init_fail_falls_back_to_libx264(
    mock_popen: MagicMock, tmp_path: Path
):
    """1st attempt (NVENC) returns non-zero with init-fail stderr → 2nd attempt libx264."""
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(side_effect=[
        b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
        b"",
    ])
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(side_effect=[
        b"out_time_ms=1000000\n",
        b"progress=end\n",
        b"",
    ])
    proc_libx264.wait = MagicMock(return_value=0)
    proc_libx264.returncode = 0

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    fallback_calls: list[tuple[H264Encoder, H264Encoder, str]] = []
    result = run_export_attempt(
        video=tmp_path / "in.mp4",
        start=0.0,
        end=10.0,
        output=tmp_path / "out.mp4",
        codec="h264",
        encoder=H264Encoder.NVENC,
        progress_cb=lambda p, s: None,
        fallback_cb=lambda f, t, m: fallback_calls.append((f, t, m)),
        cancel_event=threading.Event(),
    )
    assert result.encoder_used == H264Encoder.LIBX264
    assert result.fallback_from == H264Encoder.NVENC
    assert len(fallback_calls) == 1
    assert fallback_calls[0][0] == H264Encoder.NVENC
    assert fallback_calls[0][1] == H264Encoder.LIBX264


# --- run_export_attempt: cancel ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_cancel_event_kills_ffmpeg(
    mock_popen: MagicMock, tmp_path: Path
):
    """cancel_event が set されたら ffmpeg を kill して ExportError(kind='cancelled') raise."""
    proc = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.readline = MagicMock(return_value=b"out_time_ms=1000000\n")
    proc.wait = MagicMock(return_value=-9)  # SIGKILL
    proc.returncode = -9
    mock_popen.return_value = proc

    cancel = threading.Event()
    cancel.set()  # cancel 即時

    with pytest.raises(ExportError) as exc_info:
        run_export_attempt(
            video=tmp_path / "in.mp4",
            start=0.0,
            end=10.0,
            output=tmp_path / "out.mp4",
            codec="h264",
            encoder=H264Encoder.LIBX264,  # fallback 経路を回避
            progress_cb=lambda p, s: None,
            fallback_cb=None,
            cancel_event=cancel,
        )
    assert exc_info.value.kind == "cancelled"
    proc.kill.assert_called()


# --- run_export_attempt: libx264 retry also fails ---


@patch("allaganeye.export.ffmpeg_runner.subprocess.Popen")
def test_run_export_attempt_both_attempts_fail(
    mock_popen: MagicMock, tmp_path: Path
):
    proc_nvenc = MagicMock()
    proc_nvenc.stderr = MagicMock()
    proc_nvenc.stderr.readline = MagicMock(side_effect=[
        b"[h264_nvenc @ 0xfff] No NVENC capable devices found\n",
        b"",
    ])
    proc_nvenc.wait = MagicMock(return_value=1)
    proc_nvenc.returncode = 1

    proc_libx264 = MagicMock()
    proc_libx264.stderr = MagicMock()
    proc_libx264.stderr.readline = MagicMock(side_effect=[
        b"Error opening codec\n",
        b"",
    ])
    proc_libx264.wait = MagicMock(return_value=1)
    proc_libx264.returncode = 1

    mock_popen.side_effect = [proc_nvenc, proc_libx264]

    with pytest.raises(ExportError) as exc_info:
        run_export_attempt(
            video=tmp_path / "in.mp4",
            start=0.0,
            end=10.0,
            output=tmp_path / "out.mp4",
            codec="h264",
            encoder=H264Encoder.NVENC,
            progress_cb=lambda p, s: None,
            fallback_cb=lambda f, t, m: None,
            cancel_event=threading.Event(),
        )
    assert exc_info.value.kind == "ffmpeg.exit_failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_ffmpeg_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'allaganeye.export.ffmpeg_runner'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/ffmpeg_runner.py`:

```python
"""Single-match ffmpeg launcher + libx264 fallback retry (#761).

Ported from gui/src-tauri/src/lib.rs:1738-2348 (run_ffmpeg_export_attempt
+ export_match fallback logic). See spec §4.3.
"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from allaganeye.export.encoder import H264Encoder
from allaganeye.export.schema import ExportError, ExportResult
from allaganeye.ffmpeg_path import find_ffmpeg


_GPU_ENCODER_FAILURE_PATTERNS: dict[H264Encoder, tuple[str, ...]] = {
    # Patterns mirror gui/src-tauri/src/lib.rs:1738+ (#591). Memory:
    # feedback_ffmpeg_qsv_stderr_pattern.md notes ffmpeg 8.1 QSV uses
    # "Error creating a MFX session" (not pre-8.1 "Error initializing").
    H264Encoder.NVENC: (
        "no nvenc capable devices found",
        "cannot load cuda driver",
        "openencodesessionex failed",
    ),
    H264Encoder.QSV: (
        "error creating a mfx session",  # 8.1+
        "error initializing an internal mfx session",  # pre-8.1
        "no device available for encoder",
    ),
    H264Encoder.AMF: (
        "dll amfrt64.dll failed to open",
        "amf failed",
        "no opencl-supported device",
    ),
}


def is_gpu_encoder_failure(stderr_text: str, encoder: H264Encoder) -> bool:
    """True iff stderr indicates the GPU encoder failed to initialise."""
    if encoder == H264Encoder.LIBX264:
        return False
    text = stderr_text.lower()
    patterns = _GPU_ENCODER_FAILURE_PATTERNS.get(encoder, ())
    return any(p in text for p in patterns)


@dataclass(frozen=True)
class _AttemptOutcome:
    returncode: int
    stderr_tail: str


def _run_single_attempt(
    args: list[str],
    duration_s: float,
    progress_cb: Callable[[float, str], None],
    cancel_event: threading.Event,
) -> _AttemptOutcome:
    """1 ffmpeg process を起動して終了まで wait。

    stderr を 1 行ずつ読み、``out_time_ms`` を percent に変換して
    progress_cb に渡す。``cancel_event.is_set()`` を読み取り毎に確認し
    set されたら ``proc.kill()``。
    """
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stderr_tail_bytes: list[bytes] = []
    max_tail = 2048

    assert proc.stderr is not None
    while True:
        if cancel_event.is_set():
            proc.kill()
            break
        line = proc.stderr.readline()
        if not line:
            break
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        # 進捗パース (ffmpeg -progress pipe:2 format)
        if line_str.startswith("out_time_ms="):
            us = int(line_str.split("=", 1)[1] or "0")
            seconds = us / 1_000_000.0
            percent = (seconds / duration_s * 100.0) if duration_s > 0 else 0.0
            percent = max(0.0, min(100.0, percent))
            progress_cb(percent, "encoding")
            continue
        if line_str == "progress=end":
            progress_cb(100.0, "done")
            continue
        # それ以外は stderr_tail バッファに溜める
        stderr_tail_bytes.append(line)
        if sum(len(b) for b in stderr_tail_bytes) > max_tail * 2:
            # 末尾だけ残す
            while sum(len(b) for b in stderr_tail_bytes) > max_tail:
                stderr_tail_bytes.pop(0)

    returncode = proc.wait()
    tail = b"".join(stderr_tail_bytes).decode("utf-8", errors="replace")
    return _AttemptOutcome(returncode=returncode, stderr_tail=tail[-max_tail:])


def _build_ffmpeg_args(
    ffmpeg: Path,
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
) -> list[str]:
    """Construct the ffmpeg argv list. Mirrors gui/src-tauri/src/lib.rs:1926+."""
    args: list[str] = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "info",
        "-progress",
        "pipe:2",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(video),
    ]
    if codec == "copy":
        args.extend(["-c", "copy"])
    else:
        # h264 path
        args.extend(["-c:v", encoder.value])
        args.extend(list(encoder.quality_args()))
        args.extend(["-c:a", "copy"])
    args.append(str(output))
    return args


def run_export_attempt(
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: str,
    encoder: H264Encoder,
    *,
    progress_cb: Callable[[float, str], None],
    fallback_cb: Callable[[H264Encoder, H264Encoder, str], None] | None,
    cancel_event: threading.Event,
) -> ExportResult:
    """1 試合分の ffmpeg を起動して終了まで wait し、必要なら libx264 retry。

    - codec == "copy"  → encoder は無視、ffmpeg -c copy
    - codec == "h264" → encoder で起動、GPU init 失敗時に libx264 retry
    """
    ffmpeg = find_ffmpeg()
    duration = end - start
    started = time.monotonic()

    # 1st attempt
    args = _build_ffmpeg_args(ffmpeg, video, start, end, output, codec, encoder)
    outcome = _run_single_attempt(args, duration, progress_cb, cancel_event)

    if cancel_event.is_set():
        raise ExportError(kind="cancelled", message="export cancelled by user")

    if outcome.returncode == 0:
        return ExportResult(
            match_index=-1,  # caller (pool.py) overwrites
            output_path=output,
            duration_ms=int((time.monotonic() - started) * 1000),
            encoder_used=encoder.value,
            fallback_from=None,
        )

    # GPU encoder init failure → libx264 retry
    if (
        codec == "h264"
        and encoder != H264Encoder.LIBX264
        and is_gpu_encoder_failure(outcome.stderr_tail, encoder)
    ):
        if fallback_cb is not None:
            fallback_cb(
                encoder,
                H264Encoder.LIBX264,
                f"{encoder.display_label} の初期化に失敗したため libx264 で再試行します",
            )
        retry_args = _build_ffmpeg_args(
            ffmpeg, video, start, end, output, codec, H264Encoder.LIBX264
        )
        retry_outcome = _run_single_attempt(retry_args, duration, progress_cb, cancel_event)

        if cancel_event.is_set():
            raise ExportError(kind="cancelled", message="export cancelled by user")

        if retry_outcome.returncode == 0:
            return ExportResult(
                match_index=-1,
                output_path=output,
                duration_ms=int((time.monotonic() - started) * 1000),
                encoder_used=H264Encoder.LIBX264.value,
                fallback_from=encoder.value,
            )
        raise ExportError(
            kind="ffmpeg.exit_failed",
            message=f"libx264 retry exited with {retry_outcome.returncode}: "
            + retry_outcome.stderr_tail.strip(),
            hint="ffmpeg/codec を確認するか、入力動画を再確認してください",
        )

    # その他の失敗 (libx264 1st attempt fail, codec=copy fail, etc.)
    raise ExportError(
        kind="ffmpeg.exit_failed",
        message=f"ffmpeg ({encoder.value}) exited with {outcome.returncode}: "
        + outcome.stderr_tail.strip(),
        hint="ffmpeg/codec を確認するか、入力動画を再確認してください",
    )
```

Update `allaganeye/export/__init__.py` to add `run_export_attempt` + `is_gpu_encoder_failure`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_ffmpeg_runner.py -v`
Expected: PASS — all 10 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_ffmpeg_runner.py
ruff format allaganeye/export tests/test_export_ffmpeg_runner.py
pyright allaganeye/export tests/test_export_ffmpeg_runner.py
git add allaganeye/export/ tests/test_export_ffmpeg_runner.py
git commit -m "feat(export): ffmpeg runner with libx264 fallback retry (#761)

Ported from gui/src-tauri/src/lib.rs:1738-2348. Per-attempt cancel via
threading.Event; libx264 retry triggered by is_gpu_encoder_failure
pattern match (QSV uses 8.1 'Error creating a MFX session', per
feedback_ffmpeg_qsv_stderr_pattern.md memory).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: pool.py — ThreadPoolExecutor orchestrator + cancel semantics

**Files:**

- Create: `allaganeye/export/pool.py`
- Modify: `allaganeye/export/__init__.py`
- Test: `tests/test_export_pool.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_pool.py`:

```python
"""Tests for parallel export pool (#761).

Mocks run_export_attempt to focus on concurrency / cancel / partial
failure semantics. Codex review #3 enforces cancel-without-queue-size
condition.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.pool import ExportMatch, export_matches
from allaganeye.export.schema import ExportError, ExportResult


def _slots(n: int) -> list[EncoderSlot]:
    return [
        EncoderSlot(slot_index=i, encoder_kind=H264Encoder.LIBX264, display_label=f"libx264#{i}")
        for i in range(n)
    ]


def _matches(n: int) -> list[ExportMatch]:
    return [
        ExportMatch(index=i, start=float(i * 10), end=float((i + 1) * 10), type_label="match")
        for i in range(n)
    ]


def test_export_matches_runs_n_workers_in_parallel(tmp_path: Path):
    """concurrency = len(slots): max in-flight workers = N."""
    in_flight = 0
    max_in_flight = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / f"out_{kwargs.get('start', 0)}.mp4",
            duration_ms=50,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(10),
            slots=_slots(3),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 10
    assert summary.failure == 0
    assert max_in_flight == 3  # never exceed slot count


def test_export_matches_cancel_stops_remaining(tmp_path: Path):
    """cancel_event set → workers stop pulling. summary.cancelled = True."""
    cancel = threading.Event()
    started = 0
    lock = threading.Lock()

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal started
        with lock:
            started += 1
            if started == 2:
                cancel.set()
        time.sleep(0.02)
        if cancel.is_set():
            raise ExportError(kind="cancelled", message="user")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=20,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(20),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    assert summary.cancelled is True
    # 全 20 件 finish しないこと (cancel で打ち切り)
    assert summary.success + summary.failure < 20


def test_export_matches_cancel_marks_true_even_with_empty_queue(tmp_path: Path):
    """Codex review #3: queue.qsize() > 0 条件を残すと、cancel 直後に queue が
    たまたま空になった瞬間 cancelled=False になる。これは BUG なので NG."""
    cancel = threading.Event()
    lock = threading.Lock()
    n_done = 0

    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        nonlocal n_done
        with lock:
            n_done += 1
            if n_done == 3:
                # 全 match 終了直後に cancel set
                cancel.set()
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(3),
            slots=_slots(1),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=cancel,
        )
    # 全 3 件 success だが、cancel_event は set されているので cancelled=True
    assert summary.success == 3
    assert summary.cancelled is True


def test_export_matches_partial_failure_other_workers_continue(tmp_path: Path):
    """1 worker が failure を返しても他は続行する."""
    def fake_run(*args: Any, **kwargs: Any) -> ExportResult:
        if kwargs.get("start") == 10.0:  # match index 1
            raise ExportError(kind="ffmpeg.exit_failed", message="boom")
        return ExportResult(
            match_index=-1,
            output_path=tmp_path / "out.mp4",
            duration_ms=10,
            encoder_used="libx264",
        )

    with patch("allaganeye.export.pool.run_export_attempt", side_effect=fake_run):
        summary = export_matches(
            matches=_matches(5),
            slots=_slots(2),
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
    assert summary.success == 4
    assert summary.failure == 1
    assert summary.cancelled is False


def test_export_matches_empty_queue_returns_zero_summary(tmp_path: Path):
    summary = export_matches(
        matches=[],
        slots=_slots(3),
        source_video=tmp_path / "in.mp4",
        output_dir=tmp_path,
        codec="h264",
        name_pattern="{idx:03}.mp4",
        progress_cb=lambda ev: None,
        cancel_event=threading.Event(),
    )
    assert summary.success == 0
    assert summary.failure == 0
    assert summary.cancelled is False


def test_export_matches_empty_slots_raises(tmp_path: Path):
    """0 slot は実行不能 → ValueError (caller の bug)."""
    with pytest.raises(ValueError):
        export_matches(
            matches=_matches(1),
            slots=[],
            source_video=tmp_path / "in.mp4",
            output_dir=tmp_path,
            codec="h264",
            name_pattern="{idx:03}.mp4",
            progress_cb=lambda ev: None,
            cancel_event=threading.Event(),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_pool.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'allaganeye.export.pool'`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/export/pool.py`:

```python
"""Parallel match-export orchestrator (#761).

ThreadPoolExecutor で N worker を起動し、共有 queue から match を pull。
各 worker は run_export_attempt で 1 ffmpeg を起動。cancel_event は worker
に伝搬し、in-flight ffmpeg を kill する。See spec §4.4.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from typing import Callable

from allaganeye.export.encoder import EncoderSlot, H264Encoder
from allaganeye.export.ffmpeg_runner import run_export_attempt
from allaganeye.export.schema import (
    ExportError,
    ExportResult,
    ExportSummary,
    ProgressEvent,
)


@dataclass(frozen=True)
class ExportMatch:
    """Single match to export. Mirrors metadata.json matches[] entry."""

    index: int
    start: float
    end: float
    type_label: str  # "match" / "non_fl" / etc. — used by name_pattern


def _format_filename(m: ExportMatch, pattern: str, codec: str) -> str:
    """Render the output filename per ``pattern``.

    Tokens: ``{idx}`` / ``{idx:03}`` / ``{type}`` / ``{start}`` / ``{date}``.
    Mirrors gui/src/screens/ExportScreen.tsx formatName().
    """
    start_disp = _format_start_for_filename(m.start)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = pattern
    out = out.replace("{idx:03}", f"{m.index:03d}")
    out = out.replace("{idx}", str(m.index))
    out = out.replace("{type}", m.type_label)
    out = out.replace("{start}", start_disp)
    out = out.replace("{date}", today)
    return out


def _format_start_for_filename(seconds: float) -> str:
    """mm-ss form (`:` is invalid in Windows filenames)."""
    minutes = int(seconds // 60)
    rem = int(seconds % 60)
    return f"{minutes:02d}-{rem:02d}"


def export_matches(
    matches: list[ExportMatch],
    slots: list[EncoderSlot],
    *,
    source_video: Path,
    output_dir: Path,
    codec: str,
    name_pattern: str,
    progress_cb: Callable[[ProgressEvent], None],
    cancel_event: threading.Event | None = None,
) -> ExportSummary:
    """N workers (= len(slots)) で並列実行し、aggregated summary を返す.

    cancel_event:
        set されると worker は次の queue.get_nowait() で抜ける。in-flight な
        ffmpeg は run_export_attempt 内で kill される (ExportError(kind='cancelled'))。

    Codex review #3: summary.cancelled は ``cancel_event.is_set()`` 単独で
    判定する。``queue.qsize() > 0`` を AND してはいけない (全 dequeue 済の
    状態で cancel された場合に false negative)。
    """
    if not slots:
        raise ValueError("export_matches: slots is empty (need at least 1)")
    cancel_event = cancel_event or threading.Event()

    queue: Queue[ExportMatch] = Queue()
    for m in matches:
        queue.put(m)

    summary = ExportSummary()
    summary_lock = threading.Lock()
    cancelled_results: list[bool] = []  # any worker saw cancel

    def worker(slot: EncoderSlot) -> None:
        while not cancel_event.is_set():
            try:
                m = queue.get_nowait()
            except Empty:
                return

            def on_progress(percent: float, stage: str, _idx: int = m.index) -> None:
                progress_cb(ProgressEvent.progress(_idx, percent, stage))

            def on_fallback(
                src: H264Encoder, dst: H264Encoder, msg: str, _idx: int = m.index
            ) -> None:
                progress_cb(ProgressEvent.fallback(_idx, src.value, dst.value, msg))

            output_path = output_dir / _format_filename(m, name_pattern, codec)
            try:
                result = run_export_attempt(
                    video=source_video,
                    start=m.start,
                    end=m.end,
                    output=output_path,
                    codec=codec,
                    encoder=slot.encoder_kind,
                    progress_cb=on_progress,
                    fallback_cb=on_fallback,
                    cancel_event=cancel_event,
                )
                # match_index は ExportResult が caller 値で上書きされる
                result_with_idx = ExportResult(
                    match_index=m.index,
                    output_path=result.output_path,
                    duration_ms=result.duration_ms,
                    encoder_used=result.encoder_used,
                    fallback_from=result.fallback_from,
                )
                progress_cb(
                    ProgressEvent.result(
                        m.index,
                        result_with_idx.output_path,
                        result_with_idx.duration_ms,
                        result_with_idx.encoder_used,
                    )
                )
                with summary_lock:
                    summary.success += 1
            except ExportError as e:
                progress_cb(ProgressEvent.error(m.index, e))
                with summary_lock:
                    summary.failure += 1
                if e.kind == "cancelled":
                    cancelled_results.append(True)

    with ThreadPoolExecutor(
        max_workers=len(slots), thread_name_prefix="export-worker"
    ) as ex:
        futures = [ex.submit(worker, slot) for slot in slots]
        for f in futures:
            f.result()  # 例外伝搬 (workers の例外は内部で catch されるので通常 None)

    # Codex review #3: cancel 判定は cancel_event.is_set() 単独で
    summary.cancelled = cancel_event.is_set() or bool(cancelled_results)
    return summary
```

Update `allaganeye/export/__init__.py` to re-export `export_matches` and `ExportMatch`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_pool.py -v`
Expected: PASS — all 6 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/export tests/test_export_pool.py
ruff format allaganeye/export tests/test_export_pool.py
pyright allaganeye/export tests/test_export_pool.py
git add allaganeye/export/ tests/test_export_pool.py
git commit -m "feat(export): ThreadPoolExecutor parallel orchestrator (#761)

N workers = len(slots), shared queue, cancel_event propagation.
Codex review #3: cancel semantics decoupled from queue size.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: commands/encoder_slots.py — Typer hidden command (GUI subprocess用)

**Files:**

- Create: `allaganeye/commands/encoder_slots.py`
- Test: `tests/test_encoder_slots_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_encoder_slots_cli.py`:

```python
"""Tests for hidden 'allaganeye encoder-slots' CLI used by GUI subprocess."""

from __future__ import annotations

import json

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.encoder_slots import register

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()
    register(a)
    return a


def test_encoder_slots_outputs_json_array_for_nvenc(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors", "nvidia",
            "--preference", "nvidia,amd,intel",
            "--gpu-models", "NVIDIA GeForce RTX 5090",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert len(parsed) == 3
    assert all(s["encoder_kind"] == "Nvenc" for s in parsed)
    assert [s["slot_index"] for s in parsed] == [0, 1, 2]
    assert [s["display_label"] for s in parsed] == ["NVENC #1", "NVENC #2", "NVENC #3"]


def test_encoder_slots_libx264_when_no_vendors(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors", "",
            "--preference", "nvidia,amd,intel",
            "--gpu-models", "",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed == [{"slot_index": 0, "encoder_kind": "Libx264", "display_label": "libx264 (CPU)"}]


def test_encoder_slots_multiple_vendors_first_pref_wins(
    app: typer.Typer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("ALLAGANEYE_EXPORT_CONCURRENCY", raising=False)
    result = runner.invoke(
        app,
        [
            "encoder-slots",
            "--vendors", "nvidia,amd",
            "--preference", "amd,nvidia",
            "--gpu-models", "AMD Radeon,NVIDIA RTX 4060",
        ],
    )
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed == [{"slot_index": 0, "encoder_kind": "Amf", "display_label": "AMF"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_encoder_slots_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/commands/encoder_slots.py`:

```python
"""Hidden ``allaganeye encoder-slots`` CLI command (#761).

Used by GUI Tauri ``enumerate_h264_encoders`` to spawn a Python subprocess
once per ExportScreen mount, retrieving the EncoderSlot list as JSON.
"""

from __future__ import annotations

import json

import typer

from allaganeye.export.encoder import enumerate_h264_encoders


def _split_csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def register(app: typer.Typer) -> None:
    """Register the hidden command into ``app``. Called from ``allaganeye/cli.py``."""

    @app.command(name="encoder-slots", hidden=True)
    def encoder_slots(
        vendors: str = typer.Option("", "--vendors", help="Comma-separated vendor list."),
        preference: str = typer.Option(
            "nvidia,amd,intel",
            "--preference",
            help="Comma-separated vendor preference order.",
        ),
        gpu_models: str = typer.Option(
            "", "--gpu-models", help="Comma-separated GPU model names."
        ),
    ) -> None:
        """Return the parallel encoder slot list as a JSON array on stdout."""
        slots = enumerate_h264_encoders(
            vendors=_split_csv(vendors),
            preference=_split_csv(preference),
            gpu_models=_split_csv(gpu_models),
        )
        out = [
            {
                "slot_index": s.slot_index,
                "encoder_kind": s.encoder_kind.name.capitalize(),  # "Nvenc" / "Libx264" / ...
                "display_label": s.display_label,
            }
            for s in slots
        ]
        typer.echo(json.dumps(out, ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_encoder_slots_cli.py -v`
Expected: PASS — all 3 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/commands/encoder_slots.py tests/test_encoder_slots_cli.py
ruff format allaganeye/commands/encoder_slots.py tests/test_encoder_slots_cli.py
pyright allaganeye/commands/encoder_slots.py tests/test_encoder_slots_cli.py
git add allaganeye/commands/encoder_slots.py tests/test_encoder_slots_cli.py
git commit -m "feat(cli): hidden encoder-slots command for GUI subprocess (#761)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: commands/export.py — Typer `export` command (stdin / file / --json)

**Files:**

- Create: `allaganeye/commands/export.py`
- Test: `tests/test_export_cli.py` (基本検証 + slow integration は Task 11 で)

- [ ] **Step 1: Write the failing test**

`tests/test_export_cli.py`:

```python
"""Tests for 'allaganeye export' CLI (#761)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from allaganeye.commands.export import register
from allaganeye.export.schema import ExportSummary

runner = CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    a = typer.Typer()
    register(a)
    return a


def _make_metadata(tmp_path: Path) -> Path:
    """metadata.json on disk with 2 matches."""
    payload = {
        "schema_version": "1",
        "source": str(tmp_path / "in.mp4"),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 10.0, "type": "match"},
            {"index": 1, "start_time": 10.0, "end_time": 20.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": ["nvidia"],
            "vendor_preference": ["nvidia", "amd", "intel"],
            "gpu": ["NVIDIA GeForce RTX 5090"],
        },
    }
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@patch("allaganeye.commands.export.export_matches")
def test_export_positional_metadata_path(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=2, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        ["export", str(metadata_path), "--output-dir", str(tmp_path), "--codec", "h264", "--quiet"],
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_stdin_mode(mock_export: MagicMock, app: typer.Typer, tmp_path: Path):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    payload = json.dumps({
        "source": str(tmp_path / "in.mp4"),
        "matches": [{"index": 0, "start_time": 0.0, "end_time": 5.0, "type": "match"}],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    })
    result = runner.invoke(
        app,
        ["export", "--stdin", "--output-dir", str(tmp_path), "--codec", "copy", "--quiet"],
        input=payload,
    )
    assert result.exit_code == 0
    mock_export.assert_called_once()


@patch("allaganeye.commands.export.export_matches")
def test_export_json_mode_emits_summary_line(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    """--json mode で stdout の最後の行が summary event."""
    mock_export.return_value = ExportSummary(success=1, failure=0, cancelled=False)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        ["export", str(metadata_path), "--output-dir", str(tmp_path), "--codec", "h264", "--json"],
    )
    assert result.exit_code == 0
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    assert lines, "expected at least one JSON line"
    last = json.loads(lines[-1])
    assert last["type"] == "summary"


@patch("allaganeye.commands.export.export_matches")
def test_export_exclude_filters_matches(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=1, failure=0)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        [
            "export", str(metadata_path),
            "--output-dir", str(tmp_path),
            "--codec", "h264",
            "--exclude", "1",
            "--quiet",
        ],
    )
    assert result.exit_code == 0
    args, kwargs = mock_export.call_args
    # matches[] should have index 0 only after filter
    passed_matches = kwargs.get("matches") or args[0]
    assert [m.index for m in passed_matches] == [0]


def test_export_no_metadata_no_stdin_errors(app: typer.Typer):
    result = runner.invoke(app, ["export"])
    assert result.exit_code != 0  # Typer error: missing argument


@patch("allaganeye.commands.export.export_matches")
def test_export_returns_exit_1_on_failure(
    mock_export: MagicMock, app: typer.Typer, tmp_path: Path
):
    mock_export.return_value = ExportSummary(success=0, failure=2)
    metadata_path = _make_metadata(tmp_path)
    result = runner.invoke(
        app,
        ["export", str(metadata_path), "--output-dir", str(tmp_path), "--codec", "h264", "--quiet"],
    )
    assert result.exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_export_cli.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`allaganeye/commands/export.py`:

```python
"""``allaganeye export`` Typer command (#761).

Reads metadata.json (positional or --stdin), enumerates encoder slots,
runs ``export_matches`` (parallel), and emits progress.

Mode:
- default        rich text progress bars (single-line replace)
- --json         JSON Lines on stdout (used by GUI Tauri subprocess)
- --quiet        suppress all progress output
"""

from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path

import typer

from allaganeye.export.encoder import enumerate_h264_encoders
from allaganeye.export.pool import ExportMatch, export_matches
from allaganeye.export.schema import ExportSummary, ProgressEvent
from allaganeye.export.wire import WireWriter


def _parse_indexes_csv(value: str | None) -> set[int] | None:
    if value is None or not value.strip():
        return None
    out: set[int] = set()
    for tok in value.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.add(int(tok))
        except ValueError as e:
            raise typer.BadParameter(f"invalid index token: {tok!r}") from e
    return out


def _load_metadata(metadata_path: Path | None, use_stdin: bool) -> dict:
    if use_stdin:
        if metadata_path is not None:
            raise typer.BadParameter("--stdin is mutually exclusive with metadata_path")
        return json.load(sys.stdin)
    if metadata_path is None:
        raise typer.BadParameter("metadata_path is required unless --stdin is set")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def register(app: typer.Typer) -> None:
    """Wire the export command onto ``app`` (called from cli.py)."""

    @app.command(name="export")
    def export(
        metadata_path: Path | None = typer.Argument(
            None, exists=False, help="Path to metadata.json. Omit with --stdin."
        ),
        stdin: bool = typer.Option(
            False, "--stdin", help="Read metadata JSON from stdin (GUI subprocess mode)."
        ),
        output_dir: Path = typer.Option(
            ..., "--output-dir", "-o", help="Output directory for split MP4 files."
        ),
        codec: str = typer.Option(
            "copy", "--codec", help="Codec mode: 'copy' (no re-encode) or 'h264'."
        ),
        concurrency: int | None = typer.Option(
            None, "--concurrency", help="Override slot count (default: auto from SKU table)."
        ),
        name_pattern: str = typer.Option(
            "{idx:03}_{type}_{start}.mp4",
            "--name-pattern",
            help="Output filename pattern. Tokens: {idx} {idx:03} {type} {start} {date}.",
        ),
        quiet: bool = typer.Option(False, "--quiet", help="Suppress progress output."),
        json_mode: bool = typer.Option(
            False, "--json", help="Emit JSON Lines on stdout (GUI subprocess mode)."
        ),
        include: str | None = typer.Option(
            None, "--include", help="Comma-separated match indexes to include (others skipped)."
        ),
        exclude: str | None = typer.Option(
            None, "--exclude", help="Comma-separated match indexes to skip."
        ),
    ) -> None:
        """Parallel H.264 / copy export from metadata.json."""
        if codec not in ("copy", "h264"):
            raise typer.BadParameter(f"--codec must be 'copy' or 'h264', got {codec!r}")
        if json_mode and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")

        try:
            metadata = _load_metadata(metadata_path, stdin)
        except (OSError, json.JSONDecodeError) as e:
            typer.echo(f"error: cannot read metadata: {e}", err=True)
            raise typer.Exit(code=2) from e

        source_video = Path(metadata["source"])
        sys_info = metadata.get("system_info") or {}
        vendors = list(sys_info.get("gpu_vendors_available") or [])
        preference = list(sys_info.get("vendor_preference") or ["nvidia", "amd", "intel"])
        gpu_models = list(sys_info.get("gpu") or [])

        # Filter matches per include/exclude
        include_set = _parse_indexes_csv(include)
        exclude_set = _parse_indexes_csv(exclude) or set()
        all_matches = metadata.get("matches") or []
        filtered: list[ExportMatch] = []
        for raw in all_matches:
            idx = int(raw["index"])
            if include_set is not None and idx not in include_set:
                continue
            if idx in exclude_set:
                continue
            if raw.get("type_override") == "skip":
                continue
            filtered.append(
                ExportMatch(
                    index=idx,
                    start=float(raw.get("edited", {}).get("start_time") or raw["start_time"]),
                    end=float(raw.get("edited", {}).get("end_time") or raw["end_time"]),
                    type_label=str(raw.get("type", "match")),
                )
            )

        slots = enumerate_h264_encoders(
            vendors=vendors, preference=preference, gpu_models=gpu_models
        )
        if concurrency is not None and concurrency > 0:
            slots = slots[:concurrency]

        # Cancel: SIGINT (Ctrl+C) → cancel_event set → workers stop
        cancel_event = threading.Event()
        def _sigint_handler(signum: int, frame: object) -> None:
            cancel_event.set()
        signal.signal(signal.SIGINT, _sigint_handler)

        # Progress callback wiring
        if json_mode:
            writer = WireWriter(stream=sys.stdout)
            def progress_cb(ev: ProgressEvent) -> None:
                writer.emit(ev)
        elif quiet:
            def progress_cb(ev: ProgressEvent) -> None:  # noqa: ARG001
                pass
        else:
            # Plain text mode: 1 line per match start/done; no rich here to keep deps light
            def progress_cb(ev: ProgressEvent) -> None:
                if ev.payload["type"] == "result":
                    typer.echo(
                        f"[OK] match {ev.payload['match_index']:03d} "
                        f"-> {ev.payload['output_path']} ({ev.payload['encoder_used']})"
                    )
                elif ev.payload["type"] == "error":
                    typer.echo(
                        f"[FAIL] match {ev.payload['match_index']:03d}: "
                        f"{ev.payload['error_message']}",
                        err=True,
                    )
                elif ev.payload["type"] == "fallback":
                    typer.echo(
                        f"[fallback] match {ev.payload['match_index']:03d}: "
                        f"{ev.payload['fallback_from']} -> {ev.payload['fallback_to']}",
                        err=True,
                    )

        summary = export_matches(
            matches=filtered,
            slots=slots,
            source_video=source_video,
            output_dir=output_dir,
            codec=codec,
            name_pattern=name_pattern,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )

        if json_mode:
            writer = WireWriter(stream=sys.stdout)
            writer.emit(ProgressEvent.summary(summary))

        if summary.cancelled:
            raise typer.Exit(code=130)
        if summary.failure > 0 and summary.success == 0:
            raise typer.Exit(code=1)
        if summary.failure > 0:
            # partial failure also exit 1 to surface non-zero
            raise typer.Exit(code=1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_export_cli.py -v`
Expected: PASS — all 6 tests green

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/commands/export.py tests/test_export_cli.py
ruff format allaganeye/commands/export.py tests/test_export_cli.py
pyright allaganeye/commands/export.py tests/test_export_cli.py
git add allaganeye/commands/export.py tests/test_export_cli.py
git commit -m "feat(cli): allaganeye export Typer command (#761)

Positional metadata.json or --stdin, --codec copy|h264, --concurrency
override, --json mode for GUI subprocess, --include/--exclude indexes.
SIGINT handler sets cancel_event.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: cli.py — register export + encoder-slots commands

**Files:**

- Modify: `allaganeye/cli.py`

- [ ] **Step 1: Read existing cli.py registration site**

Run: `grep -n "@app.command" allaganeye/cli.py | head -5`
Expected: see existing `@app.command(name="split")` etc. decorators.

- [ ] **Step 2: Add registration**

At the bottom of `allaganeye/cli.py` (before `if __name__ == "__main__":`), add:

```python
# #761 -- register export + encoder-slots commands. Hidden commands stay
# out of `allaganeye --help` listings but remain dispatchable.
from allaganeye.commands import encoder_slots as _encoder_slots_cmd
from allaganeye.commands import export as _export_cmd

_export_cmd.register(app)
_encoder_slots_cmd.register(app)
```

- [ ] **Step 3: Verify via CLI help**

Run: `python -m allaganeye --help`
Expected: stdout includes `export` line (not `encoder-slots` because hidden).

Run: `python -m allaganeye export --help`
Expected: shows `--output-dir`, `--codec`, `--concurrency`, etc.

- [ ] **Step 4: Run full test suite to ensure no regression**

Run: `pytest tests/ -m "not slow" --tb=short -q`
Expected: All non-slow tests pass.

- [ ] **Step 5: Lint and commit**

```bash
ruff check allaganeye/cli.py
ruff format allaganeye/cli.py
pyright allaganeye/cli.py
git add allaganeye/cli.py
git commit -m "feat(cli): wire export + encoder-slots commands into Typer app (#761)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: tests/test_export_wire_protocol.py — slow integration test (Codex review #5)

**Files:**

- Create: `tests/test_export_wire_protocol.py`

- [ ] **Step 1: Write the failing test**

`tests/test_export_wire_protocol.py`:

```python
"""End-to-end wire protocol test (#761, Codex review #5).

Spawns a real Python subprocess (``python -m allaganeye export --stdin --json``)
with a libx264 codec + tiny test video and asserts that:
  1. stdout is parseable ndjson
  2. event ordering is sane (progress* → result | error → summary terminal)
  3. each match_index produces a terminal result or error event
  4. summary line is the LAST line

Skipped when ALLAGANEYE_SAMPLE_VIDEO_DIR / test video is unavailable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def short_test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a 6-second test video with ffmpeg (no external deps)."""
    out = tmp_path_factory.mktemp("export-wire") / "in.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc=duration=6:size=640x360:rate=30",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def test_wire_protocol_end_to_end(short_test_video: Path, tmp_path: Path):
    """Run real subprocess + verify ndjson events."""
    metadata = {
        "source": str(short_test_video),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 2.0, "type": "match"},
            {"index": 1, "start_time": 2.0, "end_time": 4.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    proc = subprocess.run(
        [
            sys.executable, "-m", "allaganeye",
            "export", "--stdin", "--json",
            "--output-dir", str(output_dir),
            "--codec", "h264",
            "--name-pattern", "{idx:03}.mp4",
        ],
        input=json.dumps(metadata),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert proc.returncode == 0, f"export failed: stderr={proc.stderr}"

    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    events = [json.loads(l) for l in lines]

    # Last line is summary
    assert events[-1]["type"] == "summary"
    assert events[-1]["success"] == 2
    assert events[-1]["failure"] == 0

    # Every match_index has exactly 1 terminal (result | error)
    terminals_per_match: dict[int, int] = {}
    for ev in events:
        if ev["type"] in ("result", "error"):
            terminals_per_match[ev["match_index"]] = (
                terminals_per_match.get(ev["match_index"], 0) + 1
            )
    assert terminals_per_match == {0: 1, 1: 1}

    # progress events for each match_index appear before its terminal
    for idx in (0, 1):
        seq = [ev["type"] for ev in events if ev.get("match_index") == idx]
        assert "progress" in seq
        terminal_pos = seq.index("result") if "result" in seq else seq.index("error")
        assert all(s == "progress" or s == "fallback" for s in seq[:terminal_pos])


def test_wire_protocol_cancel_via_sigint(short_test_video: Path, tmp_path: Path):
    """SIGINT mid-export → summary.cancelled = True, exit 130."""
    if os.name == "nt":
        pytest.skip("SIGINT test requires POSIX signal semantics; Windows uses GenerateConsoleCtrlEvent")
    metadata = {
        "source": str(short_test_video),
        "matches": [
            {"index": 0, "start_time": 0.0, "end_time": 6.0, "type": "match"},
        ],
        "system_info": {
            "gpu_vendors_available": [],
            "vendor_preference": ["nvidia"],
            "gpu": [],
        },
    }
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "allaganeye",
            "export", "--stdin", "--json",
            "--output-dir", str(output_dir),
            "--codec", "h264",
            "--name-pattern", "{idx:03}.mp4",
        ],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(metadata))
    proc.stdin.close()
    import time, signal
    time.sleep(0.5)  # let export start
    proc.send_signal(signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=10)
    assert proc.returncode == 130, f"expected exit 130 (SIGINT), got {proc.returncode}; stderr={stderr}"
    lines = [l for l in stdout.splitlines() if l.strip()]
    last = json.loads(lines[-1])
    assert last["type"] == "summary"
    assert last["cancelled"] is True
```

- [ ] **Step 2: Run test (slow)**

Run: `pytest tests/test_export_wire_protocol.py -v -m slow`
Expected: PASS (assumes ffmpeg available — same prerequisite as existing slow tests).

- [ ] **Step 3: Commit**

```bash
ruff check tests/test_export_wire_protocol.py
ruff format tests/test_export_wire_protocol.py
pyright tests/test_export_wire_protocol.py
git add tests/test_export_wire_protocol.py
git commit -m "test(export): wire protocol end-to-end integration (#761)

Codex review #5: real subprocess + ndjson parse + ordering check.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: lib.rs — delete legacy export code

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`

This task removes the Rust-side export logic that moves to Python. The
removed structs/functions are listed in spec §7.1. Do this BEFORE adding the
new Tauri commands so the new code can be written without name clashes.

- [ ] **Step 1: Locate each item via grep**

Run:

```bash
grep -n "fn run_ffmpeg_export_attempt\|fn export_match\|fn select_h264_encoder\|fn is_gpu_encoder_failure\|fn validate_export_request\|fn ffmpeg_args_for_export\|fn select_h264_encoder_for_export\|fn build_export_result\|enum H264Encoder\|enum ExportCodec\|struct ExportResult\|struct ExportProgress\|struct EncoderInfo" gui/src-tauri/src/lib.rs
```

Confirm line ranges roughly match spec §7.1.

- [ ] **Step 2: Delete the legacy items**

Open `gui/src-tauri/src/lib.rs` and delete (in order, top to bottom):

- `enum ExportCodec` (~1580-1586)
- `enum H264Encoder` + impl (~1597-1653)
- `fn select_h264_encoder` (~1666-1678)
- `struct ExportResult` (~1683-1688)
- `struct ExportProgress` (~1698- close brace) **Keep this** — referenced by emit() and frontend payload schema. Re-evaluate when adding new commands (Task 13).
  Actually: keep `ExportProgress` since `start_export` re-emits it on the `export-progress` Tauri event. Don't delete.
- `fn is_gpu_encoder_failure` (~1738+)
- `fn validate_export_request` (~1767+)
- `fn ffmpeg_args_for_export` (~1926+)
- `fn run_ffmpeg_export_attempt` (~2059-2184)
- `fn export_match` Tauri command (~2186-2348)
- `fn build_export_result` (~2370+)
- `struct EncoderInfo` (~2385-2390)
- `fn select_h264_encoder_for_export` Tauri command (~2397-2408)

Remove the corresponding entries from `tauri::generate_handler!` at **lib.rs:3303** AND **lib.rs:3332** (2 occurrences, Codex review #1):

- Remove `export_match,` and `select_h264_encoder_for_export,`

Delete the legacy unit tests inside `mod tests {}` that referenced the removed items:

- Any `select_h264_encoder_*` test
- Any `is_gpu_encoder_failure_*` test
- Any `validate_export_request_*` test
- Any `ffmpeg_args_for_export_*` test
- Any `run_ffmpeg_export_attempt_*` test

- [ ] **Step 3: Verify the crate still compiles**

Run: `cd gui/src-tauri && cargo check`
Expected: PASS (no broken references).

- [ ] **Step 4: Commit the deletion as a separate commit for reviewability**

```bash
git add gui/src-tauri/src/lib.rs
git commit -m "refactor(gui): remove legacy export logic before Python migration (#761)

Deletes H264Encoder enum, select_h264_encoder, run_ffmpeg_export_attempt,
export_match, select_h264_encoder_for_export, is_gpu_encoder_failure,
validate_export_request, ffmpeg_args_for_export, EncoderInfo, and
matching unit tests. ExportProgress struct is kept (still used by the
export-progress Tauri event re-emitted in start_export).

generate_handler! lists at lib.rs:3303 and :3332 (2 occurrences for
debug/release cfg) updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: lib.rs — add `enumerate_h264_encoders` Tauri command

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`

- [ ] **Step 1: Write a Rust unit test first**

In `gui/src-tauri/src/lib.rs::tests`, add:

```rust
#[cfg(test)]
mod enumerate_h264_encoders_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_python_json_array_output() {
        // The output mirror of `allaganeye encoder-slots --vendors=... --json`
        let raw = r#"[
            {"slot_index": 0, "encoder_kind": "Nvenc", "display_label": "NVENC #1"},
            {"slot_index": 1, "encoder_kind": "Nvenc", "display_label": "NVENC #2"}
        ]"#;
        let parsed: Vec<EncoderSlotJson> = serde_json::from_str(raw).unwrap();
        assert_eq!(parsed.len(), 2);
        assert_eq!(parsed[0].encoder_kind, "Nvenc");
    }

    #[test]
    fn empty_array_is_valid() {
        let raw = r#"[]"#;
        let parsed: Vec<EncoderSlotJson> = serde_json::from_str(raw).unwrap();
        assert!(parsed.is_empty());
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd gui/src-tauri && cargo test enumerate_h264_encoders_tests`
Expected: FAIL with `cannot find type 'EncoderSlotJson'`.

- [ ] **Step 3: Implement**

In `gui/src-tauri/src/lib.rs`, add (place after the existing PROCESS_TRACKER helpers, near the location of the deleted `select_h264_encoder_for_export`):

```rust
/// #761 -- Encoder slot returned from Python `allaganeye encoder-slots`.
///
/// `encoder_kind` is the title-cased enum variant name (`"Nvenc"`,
/// `"Libx264"`, `"Qsv"`, `"Amf"`) that the frontend renders as the
/// encoder badge ("NVENC ×3" etc.).
#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct EncoderSlotJson {
    pub slot_index: u32,
    pub encoder_kind: String,
    pub display_label: String,
}

/// #761 -- Request shape for `enumerate_h264_encoders`. Frontend supplies
/// the metadata.json `system_info` slice.
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EnumerateEncodersRequest {
    pub vendors: Vec<String>,
    pub preference: Vec<String>,
    pub gpu_models: Vec<String>,
}

/// #761 -- Spawn `python -m allaganeye encoder-slots --vendors=... \
/// --preference=... --gpu-models=...` and parse the JSON array on stdout.
///
/// Codex review #2: enforce `PYTHONIOENCODING=utf-8:replace` to match
/// `start_detect` cp932 mitigation pattern.
#[tauri::command]
async fn enumerate_h264_encoders(
    req: EnumerateEncodersRequest,
) -> Result<Vec<EncoderSlotJson>, AppError> {
    let python = resolve_python_path()?;
    let mut cmd = tokio::process::Command::new(&python);
    cmd.arg("-m").arg("allaganeye").arg("encoder-slots")
        .arg("--vendors").arg(req.vendors.join(","))
        .arg("--preference").arg(req.preference.join(","))
        .arg("--gpu-models").arg(req.gpu_models.join(","))
        .env("PYTHONIOENCODING", "utf-8:replace")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    let output = cmd.output().await.map_err(|e| {
        AppError::new("subprocess.spawn_failed", format!("encoder-slots spawn: {}", e))
            .with_default_hint()
    })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        return Err(AppError::new(
            "subprocess.exit_failed",
            format!("encoder-slots exit {}: {}", output.status, stderr),
        )
        .with_default_hint());
    }
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    serde_json::from_str::<Vec<EncoderSlotJson>>(&stdout).map_err(|e| {
        AppError::new(
            "subprocess.parse_failed",
            format!("encoder-slots stdout parse: {} (raw={})", e, stdout),
        )
        .with_default_hint()
    })
}
```

Add `enumerate_h264_encoders` to **BOTH** `generate_handler!` lists (lib.rs:3303 and lib.rs:3332).

- [ ] **Step 4: Run tests + cargo check**

Run: `cd gui/src-tauri && cargo test enumerate_h264_encoders_tests && cargo check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit -m "feat(gui): enumerate_h264_encoders Tauri command via Python (#761)

Spawns python -m allaganeye encoder-slots, parses JSON array, returns to
frontend. PYTHONIOENCODING=utf-8:replace (Codex review #2). Registered
in both generate_handler! variants (lib.rs:3303 + :3332).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: lib.rs — add `start_export` Tauri command (Python subprocess with stdin)

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`

- [ ] **Step 1: Write a Rust unit test for the wire-event parser first**

In `gui/src-tauri/src/lib.rs::tests`, add:

```rust
#[cfg(test)]
mod start_export_wire_tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn parses_progress_line() {
        let line = r#"{"type":"progress","match_index":2,"percent":33.5,"stage":"encoding"}"#;
        let ev = parse_wire_event(line).expect("parse");
        match ev {
            WireEvent::Progress { match_index, percent, stage } => {
                assert_eq!(match_index, 2);
                assert!((percent - 33.5).abs() < 0.001);
                assert_eq!(stage, "encoding");
            }
            _ => panic!("expected Progress"),
        }
    }

    #[test]
    fn parses_summary_line() {
        let line = r#"{"type":"summary","success":3,"failure":1,"skipped":0,"cancelled":false}"#;
        let ev = parse_wire_event(line).expect("parse");
        match ev {
            WireEvent::Summary { success, failure, skipped, cancelled } => {
                assert_eq!(success, 3);
                assert_eq!(failure, 1);
                assert_eq!(skipped, 0);
                assert!(!cancelled);
            }
            _ => panic!("expected Summary"),
        }
    }

    #[test]
    fn ignores_unknown_type() {
        let line = r#"{"type":"future_unknown","extra":"foo"}"#;
        assert!(matches!(parse_wire_event(line), Some(WireEvent::Unknown)));
    }

    #[test]
    fn ignores_malformed_json() {
        assert!(parse_wire_event("not json {").is_none());
    }

    #[test]
    fn ignores_empty_line() {
        assert!(parse_wire_event("").is_none());
    }
}
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd gui/src-tauri && cargo test start_export_wire_tests`
Expected: FAIL — `parse_wire_event` / `WireEvent` not defined.

- [ ] **Step 3: Implement WireEvent + parser**

In `gui/src-tauri/src/lib.rs`, add (near `ExportProgress` struct):

```rust
/// #761 -- Discriminated union of JSON-line events emitted by
/// `python -m allaganeye export --json`. See spec §5.
#[derive(Debug, serde::Deserialize)]
#[serde(tag = "type")]
pub enum WireEvent {
    #[serde(rename = "progress")]
    Progress { match_index: u32, percent: f64, stage: String },
    #[serde(rename = "fallback")]
    Fallback {
        match_index: u32,
        fallback_from: String,
        fallback_to: String,
        message: String,
    },
    #[serde(rename = "result")]
    Result {
        match_index: u32,
        output_path: String,
        duration_ms: u64,
        encoder_used: String,
    },
    #[serde(rename = "error")]
    Error {
        match_index: u32,
        error_kind: String,
        error_message: String,
        error_hint: Option<String>,
    },
    #[serde(rename = "summary")]
    Summary {
        success: u32,
        failure: u32,
        skipped: u32,
        cancelled: bool,
    },
    #[serde(other)]
    Unknown,
}

/// #761 -- Parse one ndjson line into `WireEvent`. `None` for empty / malformed.
fn parse_wire_event(line: &str) -> Option<WireEvent> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return None;
    }
    serde_json::from_str(trimmed).ok()
}
```

- [ ] **Step 4: Run wire-event tests**

Run: `cd gui/src-tauri && cargo test start_export_wire_tests`
Expected: PASS — 5 tests.

- [ ] **Step 5: Implement the `start_export` Tauri command**

Continuing in `gui/src-tauri/src/lib.rs`:

```rust
/// #761 -- Request shape for `start_export` Tauri command.
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartExportRequest {
    /// 完全な metadata 内容 (sample mode / 未保存編集対応のため stdin 経由で
    /// Python に渡す)。
    pub metadata_json: serde_json::Value,
    pub output_dir: String,
    pub codec: String, // "copy" | "h264"
    pub name_pattern: String,
    pub excluded_indexes: Vec<u32>,
}

/// #761 -- Aggregate returned to frontend after Python exits.
#[derive(Debug, serde::Serialize)]
pub struct ExportSummary {
    pub success: u32,
    pub failure: u32,
    pub skipped: u32,
    pub cancelled: bool,
}

#[tauri::command]
async fn start_export(
    app: tauri::AppHandle,
    req: StartExportRequest,
) -> Result<ExportSummary, AppError> {
    let python = resolve_python_path()?;
    let mut cmd = tokio::process::Command::new(&python);
    let exclude_arg = req
        .excluded_indexes
        .iter()
        .map(|i| i.to_string())
        .collect::<Vec<_>>()
        .join(",");
    cmd.arg("-m").arg("allaganeye").arg("export")
        .arg("--stdin").arg("--json")
        .arg("--output-dir").arg(&req.output_dir)
        .arg("--codec").arg(&req.codec)
        .arg("--name-pattern").arg(&req.name_pattern);
    if !exclude_arg.is_empty() {
        cmd.arg("--exclude").arg(&exclude_arg);
    }
    cmd.env("PYTHONIOENCODING", "utf-8:replace")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    let mut child = cmd.spawn().map_err(|e| {
        AppError::new("subprocess.spawn_failed", format!("start_export spawn: {}", e))
            .with_default_hint()
    })?;

    // Write metadata JSON to stdin and close
    {
        let mut stdin = child.stdin.take().ok_or_else(|| {
            AppError::new("subprocess.stdin_unavailable", "stdin missing on spawn")
                .with_default_hint()
        })?;
        use tokio::io::AsyncWriteExt;
        let serialized = serde_json::to_vec(&req.metadata_json).map_err(|e| {
            AppError::new("subprocess.serialize_failed", format!("metadata serialize: {}", e))
                .with_default_hint()
        })?;
        stdin.write_all(&serialized).await.ok();
        // dropping `stdin` closes the pipe
    }

    // Track via PROCESS_TRACKER (Job Object on Windows to reap ffmpeg descendants)
    #[cfg(target_os = "windows")]
    let tracked = TrackedChild { child, job: Some(create_job_for(&child)?) };
    #[cfg(not(target_os = "windows"))]
    let tracked = TrackedChild::no_job(child);

    let tracked_id = track_child(tracked).await;

    // Read stdout line-by-line + forward as Tauri events
    let mut summary_capture: Option<ExportSummary> = None;
    let stdout = {
        let map = process_tracker();
        let mut guard = map.lock().await;
        let tc = guard.get_mut(&tracked_id).expect("tracked just inserted");
        tc.child.stdout.take()
    };
    if let Some(stdout) = stdout {
        use tokio::io::{AsyncBufReadExt, BufReader};
        let reader = BufReader::new(stdout);
        let mut lines = reader.lines();
        while let Ok(Some(line)) = lines.next_line().await {
            match parse_wire_event(&line) {
                Some(WireEvent::Progress { match_index, percent, stage }) => {
                    let _ = app.emit(
                        "export-progress",
                        ExportProgress {
                            match_index,
                            percent,
                            stage,
                            message: None,
                            fallback_from: None,
                        },
                    );
                }
                Some(WireEvent::Fallback { match_index, fallback_from, fallback_to, message }) => {
                    let _ = app.emit(
                        "export-progress",
                        ExportProgress {
                            match_index,
                            percent: 0.0,
                            stage: "fallback".to_string(),
                            message: Some(message),
                            fallback_from: Some(format!("{} -> {}", fallback_from, fallback_to)),
                        },
                    );
                }
                Some(WireEvent::Result { match_index, .. }) => {
                    // No-op (frontend gets the done state via the next Progress "done" or implicit success)
                    let _ = app.emit(
                        "export-progress",
                        ExportProgress {
                            match_index,
                            percent: 100.0,
                            stage: "done".to_string(),
                            message: None,
                            fallback_from: None,
                        },
                    );
                }
                Some(WireEvent::Error { match_index, error_kind: _, error_message, error_hint }) => {
                    let _ = app.emit(
                        "export-progress",
                        ExportProgress {
                            match_index,
                            percent: 0.0,
                            stage: "error".to_string(),
                            message: Some(if let Some(hint) = error_hint {
                                format!("{} ({})", error_message, hint)
                            } else {
                                error_message
                            }),
                            fallback_from: None,
                        },
                    );
                }
                Some(WireEvent::Summary { success, failure, skipped, cancelled }) => {
                    summary_capture = Some(ExportSummary { success, failure, skipped, cancelled });
                }
                Some(WireEvent::Unknown) | None => {
                    // forward-compat: ignore unknown / non-JSON lines
                }
            }
        }
    }

    // Drain remainder of the child via untrack_child (handles concurrent kill_tracked_processes)
    let mut child = match untrack_child(tracked_id).await {
        Some(c) => c,
        None => {
            return Ok(ExportSummary {
                success: 0,
                failure: 0,
                skipped: 0,
                cancelled: true,
            });
        }
    };
    let _ = child.wait().await;

    Ok(summary_capture.unwrap_or(ExportSummary {
        success: 0,
        failure: 0,
        skipped: 0,
        cancelled: false,
    }))
}
```

Add `start_export` to **BOTH** `generate_handler!` lists.

- [ ] **Step 6: Cargo check + tests**

Run: `cd gui/src-tauri && cargo check && cargo test start_export_wire_tests && cargo test enumerate_h264_encoders_tests`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit -m "feat(gui): start_export Tauri command via Python subprocess (#761)

Spawns python -m allaganeye export --stdin --json with the in-memory
metadata piped to stdin. Job Object descendant reaping reuses start_detect
pattern (PROCESS_TRACKER with Job on Windows). Wire-event parser
(WireEvent enum + parse_wire_event) converts each ndjson line to
ExportProgress Tauri events.

PYTHONIOENCODING=utf-8:replace (Codex review #2). Both generate_handler!
variants registered (Codex review #1).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: ExportScreen.tsx — refactor handleStartExport + encoder slot display

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx`
- Modify: `gui/src/screens/__tests__/ExportScreen.test.tsx` (or create if absent)

- [ ] **Step 1: Read current state**

Run: `head -200 gui/src/screens/ExportScreen.tsx` and note:

- Existing `EncoderInfo` interface (lines 56-60) → replace with `EncoderSlot`
- Existing `encoderInfo` state via `select_h264_encoder_for_export` → switch to `enumerate_h264_encoders[0]` style with multi-slot
- handleStartExport for-loop (lines 354-398) → 1 invoke

- [ ] **Step 2: Write/update test first**

If `gui/src/screens/__tests__/ExportScreen.test.tsx` exists, augment; otherwise create:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ExportScreen } from '../ExportScreen';
import * as core from '@tauri-apps/api/core';
import * as event from '@tauri-apps/api/event';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));
vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(),
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({ open: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ExportScreen — NVENC parallel (#761)', () => {
  it('calls enumerate_h264_encoders on mount and shows "NVENC ×3"', async () => {
    (core.invoke as any).mockImplementation((cmd: string) => {
      if (cmd === 'enumerate_h264_encoders') {
        return Promise.resolve([
          { slot_index: 0, encoder_kind: 'Nvenc', display_label: 'NVENC #1' },
          { slot_index: 1, encoder_kind: 'Nvenc', display_label: 'NVENC #2' },
          { slot_index: 2, encoder_kind: 'Nvenc', display_label: 'NVENC #3' },
        ]);
      }
      return Promise.resolve();
    });
    // ... render ExportScreen with mock metadata having system_info
    // assert that "NVENC ×3" appears in the rendered output
  });

  it('invokes start_export ONCE with metadataJson + excludedIndexes', async () => {
    (core.invoke as any).mockImplementation((cmd: string, args: any) => {
      if (cmd === 'enumerate_h264_encoders') {
        return Promise.resolve([
          { slot_index: 0, encoder_kind: 'Nvenc', display_label: 'NVENC #1' },
        ]);
      }
      if (cmd === 'start_export') {
        return Promise.resolve({
          success: 2,
          failure: 0,
          skipped: 0,
          cancelled: false,
        });
      }
      return Promise.resolve();
    });
    // ... click 書き出し開始 button
    // assert (core.invoke as any).mock.calls includes ['start_export', {...}] once
  });

  it('forwards export-progress events to setMatchStates', async () => {
    let progressHandler: any;
    (event.listen as any).mockImplementation((name: string, cb: any) => {
      if (name === 'export-progress') {
        progressHandler = cb;
      }
      return Promise.resolve(() => undefined);
    });
    // ... fire mock event { payload: { match_index: 0, percent: 50, stage: 'encoding' } }
    // assert match 0 shows 50% in the rendered list
  });
});
```

(The skeleton is intentionally partial; flesh out in implementation per the existing test patterns in the repo.)

- [ ] **Step 3: Modify ExportScreen.tsx**

Replace the existing `EncoderInfo` interface + state with the multi-slot model:

```tsx
// Replace lines 56-70 (EncoderInfo + LIBX264_INFO constant) with:
interface EncoderSlot {
  slot_index: number;
  encoder_kind: 'Libx264' | 'Nvenc' | 'Qsv' | 'Amf';
  display_label: string;
}

const LIBX264_SLOT: EncoderSlot = {
  slot_index: 0,
  encoder_kind: 'Libx264',
  display_label: 'libx264 (CPU)',
};
```

Replace the `encoderInfo` state + useEffect with:

```tsx
const [encoderSlots, setEncoderSlots] = useState<EncoderSlot[]>([LIBX264_SLOT]);

useEffect(() => {
  if (!metadata?.system_info) {
    setEncoderSlots([LIBX264_SLOT]);
    return;
  }
  invoke<EncoderSlot[]>('enumerate_h264_encoders', {
    req: {
      vendors: metadata.system_info.gpu_vendors_available ?? [],
      preference: metadata.system_info.vendor_preference ?? ['nvidia', 'amd', 'intel'],
      gpuModels: metadata.system_info.gpu ?? [],
    },
  })
    .then((slots) => setEncoderSlots(slots.length > 0 ? slots : [LIBX264_SLOT]))
    .catch(() => setEncoderSlots([LIBX264_SLOT]));
}, [metadata?.source]);

const encoderBadge =
  encoderSlots.length > 1
    ? `${encoderSlots[0].display_label.split(' ')[0]} ×${encoderSlots.length}`
    : encoderSlots[0].display_label;
```

Replace `handleStartExport` (lines ~324-410) with the single-invoke version:

```tsx
async function handleStartExport() {
  if (!metadata) return;
  if (!videoSource) return;
  cancelRequestedRef.current = false;

  // Initialize per-match state (既存ロジック)
  const nextStates: Record<number, MatchState> = {};
  for (const m of metadata.matches) {
    if (m.type_override === 'skip' || excludedIndexes.has(m.index)) {
      nextStates[m.index] = { status: 'skipped', percent: 0 };
    } else {
      nextStates[m.index] = { status: 'pending', percent: 0 };
    }
  }
  setMatchStates(nextStates);
  const startMs = Date.now();
  setExportStartMs(startMs);
  setNowMs(startMs);
  dispatch({ type: 'START_CLICKED' });

  try {
    const summary = await invoke<{
      success: number;
      failure: number;
      skipped: number;
      cancelled: boolean;
    }>('start_export', {
      req: {
        metadataJson: metadata,
        outputDir: outDir,
        codec,
        namePattern,
        excludedIndexes: Array.from(excludedIndexes),
      },
    });
    if (summary.cancelled) dispatch({ type: 'CANCEL_CONFIRMED' });
    else if (summary.success === 0 && summary.failure > 0) dispatch({ type: 'EXPORT_ERROR' });
    else dispatch({ type: 'PROGRESS_COMPLETE' });
  } catch (e) {
    const errorState = toErrorState(e);
    // surface global error
    setMatchStates((prev) => ({
      ...prev,
      __global__: {
        status: 'error',
        percent: 0,
        error: errorState.message,
        errorHint: errorState.hint ?? undefined,
      } as MatchState,
    }));
    dispatch({ type: 'EXPORT_ERROR' });
  }
}
```

Render the encoder badge near the existing encoder display area; replace `encoderInfo.display_label` references with `encoderBadge`.

- [ ] **Step 4: Run vitest**

Run: `cd gui && npm run test`
Expected: tests pass (or update assertions to match new structure).

Run: `cd gui && npm run lint && npm run typecheck`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/__tests__/ExportScreen.test.tsx
git commit -m "feat(gui): ExportScreen single-invoke start_export + encoder slot badge (#761)

- Replace per-match invoke loop with 1 invoke('start_export', ...)
- Replace EncoderInfo state with EncoderSlot[] from enumerate_h264_encoders
- Display 'NVENC ×3' when 3 slots, else single label
- Forward summary.cancelled/failure/success to existing reducer dispatch

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: docs/cli-spec.md — add `export` section

**Files:**

- Modify: `docs/cli-spec.md`

- [ ] **Step 1: Read current cli-spec.md TOC and pick the section location**

Run: `grep -n "^##" docs/cli-spec.md | head -20`
Expected: identify where the `## split` / `## detect` / `## debug-brightness` sections live; add `## export` after them.

- [ ] **Step 2: Add the section**

Insert a new section in `docs/cli-spec.md` describing the `export` command:

```markdown
## export

並列 H.264 / copy export を試合分割済み metadata.json から実行する (#761)。

### Synopsis

```bash
allaganeye export <metadata_path> [--output-dir DIR] [--codec copy|h264]
                                  [--concurrency N] [--name-pattern PATTERN]
                                  [--quiet|--json] [--include I,J,K|--exclude I,J,K]

# GUI subprocess パス (stdin で metadata を受ける):
echo '<metadata-json>' | allaganeye export --stdin [...]
```

### Arguments

- `metadata_path` (positional) — detect/split が出力した metadata.json。`--stdin` と排他。
- `--stdin` — metadata を stdin から JSON で読む (GUI 連携用、in-memory edits をサポート)。
- `--output-dir DIR` — 出力先ディレクトリ。default は source video の dirname。
- `--codec copy|h264` — `copy` (FFmpeg `-c copy` 無劣化分割) / `h264` (NVENC / QSV / AMF / libx264 再エンコード)。default `copy`。
- `--concurrency N` — slot 数 override。指定しなければ `enumerate_h264_encoders` の自動検出 (SKU table) を採用。
- `--name-pattern PATTERN` — 出力ファイル名。tokens: `{idx}` / `{idx:03}` / `{type}` / `{start}` / `{date}`。default `{idx:03}_{type}_{start}.mp4`。
- `--include / --exclude` — 1-based match index (metadata の `matches[].index`) による絞り込み (カンマ区切り)。`--include` 指定で list 外は skip、`--exclude` 指定で list 内を skip。同時指定すると `--include ∩ ¬--exclude`。
- `--quiet` — progress 出力を抑制。
- `--json` — stdout に JSON Lines (`{"type":"progress",...}` 等) を吐く。`--quiet` と排他。GUI subprocess 用。

### NVENC engine count probe

`--codec h264` 選択時の slot 数は metadata.json `system_info.gpu`、`gpu_vendors_available`、`vendor_preference` から `enumerate_h264_encoders` が決定する:

- RTX 5090 = 3 slots, RTX 4090 / 4080 / 4070 = 2 slots, RTX 4060 = 1 slot
- 不明 NVIDIA = 1 slot (保守的)
- env 変数 `ALLAGANEYE_EXPORT_CONCURRENCY` で override 可能 (OBS 等の他アプリが NVENC engine を使用中の場合は値を下げる)

### Exit code

| code | 意味 |
| --- | --- |
| 0 | 全 match success |
| 1 | 1 件以上 failure (partial failure 含む) |
| 2 | 入力 error (metadata 不正、output dir 不存在 等) |
| 130 | SIGINT (Ctrl+C) で cancel |

<!-- markdownlint-disable-next-line MD040 -->
```

- [ ] **Step 3: Run markdownlint**

Run: `bash scripts/check-markdownlint.sh docs/cli-spec.md`
Expected: PASS (or auto-fix with `--fix`).

- [ ] **Step 4: Commit**

```bash
git add docs/cli-spec.md
git commit -m "docs(cli): allaganeye export command spec (#761)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: docs/output-spec.md — add export output matrix entries

**Files:**

- Modify: `docs/output-spec.md`

- [ ] **Step 1: Read current output-spec.md**

Run: `grep -n "^##" docs/output-spec.md | head -10`

- [ ] **Step 2: Add export matrix rows**

Locate the output combination matrix (`#405 マトリクス v2` per CLAUDE.md) and add rows for:

| Mode | Files emitted | Naming |
| --- | --- | --- |
| `export --codec copy` | `{idx:03}_{type}_{start}.mp4` per match | Stream-copy MP4 (no re-encode) |
| `export --codec h264` | `{idx:03}_{type}_{start}.mp4` per match | Re-encoded MP4 (NVENC / QSV / AMF / libx264 fallback) |
| `export --json` | stdout ndjson stream | One JSON line per progress / fallback / result / error / summary event |

- [ ] **Step 3: Lint and commit**

```bash
bash scripts/check-markdownlint.sh docs/output-spec.md
git add docs/output-spec.md
git commit -m "docs(output): export command output matrix entries (#761)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: gh issue edit #761 — extend acceptance criteria

**Files:**

- (GitHub state change, no local file)

- [ ] **Step 1: Fetch current issue body**

```bash
gh issue view 761 --json body -q .body > /tmp/issue761.md
```

- [ ] **Step 2: Append CLI + sample mode + window-close + writer-lock criteria**

Edit `/tmp/issue761.md` and append at the end of `## 確認項目 / 作業項目`:

```markdown
- [ ] **CLI**: `allaganeye export <metadata.json> --codec h264` で N 並列 export が動作する (新コマンド追加、SIGINT で全 ffmpeg kill)
- [ ] **GUI**: ExportScreen の「書き出し開始」が CLI と同じ Python core を経由して N 並列実行する (`start_export` / `enumerate_h264_encoders` Tauri command 経由)
- [ ] **GUI sample mode**: filePath=null の sample mode + 未保存編集状態でも export 動作する (in-memory metadata を stdin 経由で Python に渡す)
- [ ] **共有**: CLI と GUI が同じ `allaganeye/export/` module を経由 (重複ロジックなし、Rust 側 export ロジック削除)
- [ ] **JSON writer lock**: 並列 worker が `sys.stdout` に書く際に line atomic 性が保たれる (`threading.Lock` 経由、Codex review #4)
- [ ] **encoding boundary audit**: `PYTHONIOENCODING=utf-8:replace` を Rust subprocess 側で明示設定し UTF-8 lossy decode で cp932 fallback (Iron Law 6 + Codex review #2)
- [ ] **GUI ウィンドウクローズ**: export 進行中に `[×]` で閉じた際、`force_exit_app` 経由で `kill_tracked_processes` 相当の cleanup が走り全 ffmpeg / Python subprocess が reaped されること
```

- [ ] **Step 3: Push the updated body**

```bash
gh issue edit 761 --body-file /tmp/issue761.md
```

- [ ] **Step 4: Verify**

```bash
gh issue view 761 | grep -A 2 "CLI:"
```

Expected: new entries visible.

(No commit — pure GitHub state change.)

---

### Task 19: Run full test suite + lint + typecheck (Python + Rust + GUI)

**Files:**

- (No file changes, verification only)

- [ ] **Step 1: Python lint + typecheck + tests**

```bash
ruff check .
ruff format --check .
pyright
pytest -m "not slow" -q --tb=short
```

Expected: ALL PASS.

- [ ] **Step 2: Slow tests (export-related)**

```bash
pytest tests/test_export_wire_protocol.py tests/test_export_cli.py -v -m slow
```

Expected: PASS (skipped only when ffmpeg unavailable).

- [ ] **Step 3: Rust check + tests**

```bash
cd gui/src-tauri && cargo check && cargo test --no-fail-fast
```

Expected: PASS.

- [ ] **Step 4: GUI lint + typecheck + tests**

```bash
cd gui && npm run lint && npm run typecheck && npm test
```

Expected: PASS.

- [ ] **Step 5: GUI build (smoke)**

```bash
cd gui && npm run build
```

Expected: PASS (vite build emits `gui/dist/`).

- [ ] **Step 6: Markdown lint**

```bash
bash scripts/check-markdownlint.sh
```

Expected: PASS.

- [ ] **Step 7: Commit (if any lint auto-fixes were needed)**

```bash
git status
# Only commit if there are intentional lint fixes; otherwise skip.
```

---

### Task 20: Real-device verification (Iron Law 6 — Idios)

**Files:**

- (Manual verification, no code changes)

- [ ] **Step 1: AskUserQuestion to Idios**

Prompt Idios with the verification checklist:

> **Iron Law 6 実機検証依頼 (#761)**:
> 以下を RTX 5090 + Windows 11 環境で実施し、結果を報告してください。
>
> 1. **N=3 並列実行**: `allaganeye export <large-metadata.json> --codec h264` を実行し、Task Manager > Performance > GPU 0 > Video Encode が ~90%+ で 30 秒以上持続することを目視確認
> 2. **GUI 経路同等性**: GUI ExportScreen で同じ metadata を H.264 出力し、`nvidia-smi dmon -s u -d 1` で NVENC sum が CLI と同等に貼り付くこと
> 3. **OBS contention**: OBS 録画を開始した状態で `allaganeye export --codec h264` を起動し、全 ffmpeg init が成功する (libx264 fallback が出ない) こと
> 4. **env override**: `ALLAGANEYE_EXPORT_CONCURRENCY=2 allaganeye export ...` で 2 並列実行 (Task Manager で確認)
> 5. **cancel**: GUI 書き出し中に「キャンセル」ボタン押下で全 ffmpeg が 2 秒以内に消えることを Task Manager > Details で確認
> 6. **ウィンドウクローズ**: GUI 書き出し中に `[×]` でウィンドウを閉じ、子プロセス (ffmpeg / Python) が残らないこと
> 7. **長時間動画**: 2 時間超の OBS 録画 (30GB+) で N=3 export を実行、メモリリーク / 例外なしで完走
>
> 結果を `## 確認項目 / 作業項目` の checkbox に reflect してください。

- [ ] **Step 2: Wait for results**

User reports back; check each box on issue #761 only after the corresponding scenario passes.

(No commit — verification handoff.)

---

### Task 21: Open PR

**Files:**

- (PR creation, no local file changes)

- [ ] **Step 1: Verify all commits are local**

```bash
git log origin/develop-0.3.0..HEAD --oneline
```

Expected: ~16 commits covering Tasks 1-17.

- [ ] **Step 2: Push branch**

```bash
git push -u origin HEAD
```

- [ ] **Step 3: Pre-flight per [docs/l2-workflow.md](../../l2-workflow.md) §PR 作成 Pre-flight**

Run the 5-step pre-flight:

```bash
# Step 0: hard gate
gh pr list --search "761" --state open
# Expected: no parallel PR for 761

# Step 1: base sync
git fetch origin develop-0.3.0
# Step 2: unpulled commits
git log HEAD..origin/develop-0.3.0 --oneline
# Step 3: touched files intersection
git diff HEAD origin/develop-0.3.0 --name-only
# Step 4: parallel PR re-check
gh pr list --search "761" --state all
# Step 5: codex adversarial-review
/codex:adversarial-review focus="Iron Law 3 / encoding / GPU fallback / 同 issue 過去 PR root cause"
```

- [ ] **Step 4: Create PR**

```bash
gh pr create --base develop-0.3.0 --title "feat(export): NVENC parallel export (Python-first shared core) (#761)" --body "$(cat <<'EOF'
## Summary

issue #761 を解決し、CLI + GUI 両側で N 並列 NVENC export を実現する。Python 側に
orchestration / encoder slot / ffmpeg runner を一本化し、GUI は subprocess 経由
で呼び出す (`start_detect` と同形)。

## 主な変更

- Python `allaganeye/export/` を新設 (schema / encoder / nvenc_probe / ffmpeg_runner / pool / wire)
- `allaganeye export` Typer CLI コマンド追加 (--stdin / --json / --concurrency / --include / --exclude)
- `allaganeye encoder-slots` hidden CLI コマンド追加 (GUI subprocess 用)
- Rust 側 `H264Encoder` / `select_h264_encoder` / `export_match` / etc. を削除
- 新 Tauri command `start_export` / `enumerate_h264_encoders` (Python subprocess 経由、PYTHONIOENCODING=utf-8:replace)
- ExportScreen `handleStartExport` を 1 invoke 化、encoder slot 列表示
- spec: `docs/superpowers/specs/2026-05-18-nvenc-parallel-export-design.md`

## Codex adversarial review 反映 (12 findings)

[Codex review log](docs/superpowers/specs/2026-05-18-nvenc-parallel-export-design.md#adversarial-review)
の全 mandatory fix を実装に反映 (generate_handler! lib.rs:3303+:3332 / cancel semantics
without queue.qsize / writer lock / wire protocol integration test / default NVENC=1 /
multi-GPU conservative min etc.)

## Self-Test Report

- [x] `ruff check .` / `ruff format --check .` / `pyright`
- [x] `pytest -m "not slow"` 全 pass
- [x] `pytest tests/test_export_wire_protocol.py tests/test_export_cli.py -m slow` pass (ffmpeg 利用可能環境)
- [x] `cd gui/src-tauri && cargo check && cargo test --no-fail-fast` pass
- [x] `cd gui && npm run lint && npm run typecheck && npm test && npm run build` pass
- [x] `bash scripts/check-markdownlint.sh` pass
- 実機検証: Iron Law 6 trigger として user (Idios) に AskUserQuestion で依頼 (Task 20)

## レビュー指針

重点 review ポイント:
1. **encoding boundary** (Iron Law 6 + Codex #2): `PYTHONIOENCODING=utf-8:replace` の徹底
2. **wire protocol** (Codex #5): writer lock + 整合性
3. **cancel semantics** (Codex #3): `summary.cancelled` 判定が queue size に依存しないこと
4. **migration completeness**: Rust 側削除と Python 側追加が 1:1 で対応していること
5. **Phase waiver** (Codex #8): churn ~2250 line の判断根拠

EOF
)"
```

(後続のレビューは `/iterate-review` ループに委譲。)

---

## Self-Review

### Spec coverage check

- [x] G1 CLI export: Tasks 9-10
- [x] G2 GUI export via Python: Tasks 13-15
- [x] G3 SKU table + env override: Tasks 3-4
- [x] G4 cancel: Tasks 6-7-9-14
- [x] G5 libx264 fallback per-slot: Tasks 6-7
- [x] G6 Rust delete: Task 12
- [x] G7 progress event backward compat: Task 14 (ExportProgress kept)
- [x] G8 real device verification: Task 20

- [x] Codex review #1 (lib.rs generate_handler!): Tasks 12-13-14
- [x] Codex review #2 (PYTHONIOENCODING): Tasks 13-14
- [x] Codex review #3 (cancel semantics): Task 7
- [x] Codex review #4 (writer lock): Task 5
- [x] Codex review #5 (wire protocol integration test): Task 11
- [x] Codex review #6 (Tauri capability): Task 12 commit message + spec §7.4
- [x] Codex review #7 (Typer registration): Task 10
- [x] Codex review #8 (churn-based phase waiver): spec §12 (no extra task needed)
- [x] Codex review #9 (`_DEFAULT_NVENC_COUNT = 1`): Task 3
- [x] Codex review #10 (libx264 fallback CPU policy): spec R8 + acceptance criteria
- [x] Codex review #11 (window-close cleanup): Task 18 acceptance + Task 20 verification
- [x] Codex review #12 (multi-GPU conservative min): Task 3

### Placeholder scan

No "TBD", "add appropriate error handling", or vague references found. All function signatures, dataclass fields, and method names are consistent across tasks.

### Type consistency check

- `H264Encoder` enum values (`LIBX264 = "libx264"` etc.) consistent across Tasks 2, 6, 7, 9, 13, 14
- `EncoderSlot` fields (`slot_index`, `encoder_kind`, `display_label`) consistent across Tasks 2, 4, 8, 13, 14, 15
- Wire event types (`progress` / `fallback` / `result` / `error` / `summary`) consistent across Tasks 1, 9, 11, 14
- `ExportSummary` fields (`success` / `failure` / `skipped` / `cancelled`) consistent across Tasks 1, 7, 9, 11, 14, 15
