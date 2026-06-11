# NVENC parallel export design (#761)

- 日付: 2026-05-18
- 起票元: issue [#761](https://github.com/Idios/kobutachan-allaganeye/issues/761) [task] L3: NVENC 並列 export 基盤化
- 関連 issue: [#762](https://github.com/Idios/kobutachan-allaganeye/issues/762) (multi-vendor 並列、本 spec の後続)、[#765](https://github.com/Idios/kobutachan-allaganeye/issues/765) (NVDEC saturation 計測記録)、[#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) (vendor-aware encoder 選択、本 spec の前提)
- 作成者: brainstorming session 2026-05-18 (Claude + Idios)
- Adversarial review: Codex 2026-05-18 (12 findings、verdict PROCEED-WITH-FIXES、全 mandatory fix を spec に反映済)
- 関連 docs: [docs/refactor-pattern.md](../../refactor-pattern.md)、[docs/l2-workflow.md](../../l2-workflow.md)、[docs/cli-spec.md](../../cli-spec.md)、[docs/system-architecture.md](../../system-architecture.md)

## 1. 背景と動機

GUI export の試合切り出しは現状 [`gui/src/screens/ExportScreen.tsx:354-398`](../../../gui/src/screens/ExportScreen.tsx#L354) で `for...of queue` + `await invoke('export_match')` の strict sequential である。1 invoke = 1 ffmpeg = 1 NVENC session 占有のため、NVENC 物理 engine を複数搭載する GPU (RTX 5090 = 3 engine, RTX 4090 = 2 engine 等) でも常に 1 engine しか稼働しない。Task Manager の GPU > Video Encode が ~33% (RTX 5090) / ~50% (RTX 4090) で固定される。

[#765](https://github.com/Idios/kobutachan-allaganeye/issues/765) で detect 側 NVDEC は既に 2 engine をほぼ完全 saturate (active phase で sum 185-200%) していることを確認済み。一方 export 側は前述の通り 1 engine のみで未飽和。N 並列化で理想 ~3x スループット改善を狙う。

CLI 側には現状 H.264 再エンコード export 機能が存在しない (`allaganeye split` は `-c copy` 無劣化分割のみ)。GUI と整合する形で CLI にも export を新設し、**Python 側に orchestration / encoder slot / ffmpeg runner を一本化**して GUI は subprocess で呼び出す (`start_detect` と同形のアーキテクチャ)。これにより [#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) の Rust 側ロジック (libx264 fallback retry, H264Encoder enum 等) は Python へ移行し、CLI/GUI で重複ゼロを実現する。

## 2. Goals と non-goals

### Goals

- **G1**: CLI で `allaganeye export <metadata.json> --codec h264 [--concurrency N]` が動作する
- **G2**: GUI ExportScreen の「書き出し開始」が CLI と同じ Python core を経由して N 並列実行する
- **G3**: NVENC 物理 engine 数を SKU table で自動検出 (RTX 5090=3, RTX 4090=2, …)、env 変数 `ALLAGANEYE_EXPORT_CONCURRENCY` で override 可
- **G4**: cancel 経路 (CLI=SIGINT / GUI=`kill_tracked_processes`) で全 in-flight ffmpeg を秒以内に kill
- **G5**: libx264 fallback retry を per-slot 独立に動作させる (1 slot だけ失敗しても他 slot は NVENC 続行)
- **G6**: Rust 側 export ロジック (`H264Encoder` / `select_h264_encoder` / `run_ffmpeg_export_attempt` / `export_match` / `select_h264_encoder_for_export`) を削除し、Python から呼び出される subprocess wrapper (`start_export` / `enumerate_h264_encoders`) のみを残す
- **G7**: 既存 progress event スキーマ (`export-progress` Tauri event with `match_index` keyed payload) を後方互換に保ち、frontend `setMatchStates` ロジックは無改修
- **G8**: 実機検証 (Iron Law 6): RTX 5090 で N=3 並列実行時に Task Manager の Video Encode engine ~90%+ 持続を目視確認

### Non-goals

- **N1**: multi-vendor 並列 (NVENC + AMF / NVENC + QSV mixed slot) は [#762](https://github.com/Idios/kobutachan-allaganeye/issues/762) スコープ。本 spec の `EncoderSlot` 抽象は #762 でそのまま拡張できる形にする
- **N2**: detect (split) 側の並列度調整は [#765](https://github.com/Idios/kobutachan-allaganeye/issues/765) で記録済の通り既に飽和しており本 spec のスコープ外
- **N3**: live NVENC contention probe (`nvidia-smi --query-gpu=encoder.stats.sessionCount`) は不採用 (§9 参照)
- **N4**: GUI の per-match cancel UI 追加 (現状は global cancel のみ、本 spec も同様)
- **N5**: `gui/src-tauri/` の export 以外 (detect / preview / restore / 配信形式変換等) のリファクタは対象外

## 3. アーキテクチャ全体図

```text
CLI 経路:
  $ allaganeye export <metadata.json> --codec h264 [opts]
    └── allaganeye/commands/export.py  (Typer command entry)
          └── allaganeye/export/pool.py  export_matches(matches, slots, ...)
                ├── ThreadPoolExecutor(max_workers=len(slots))
                ├── worker 0 → ffmpeg_runner.run_export_attempt() → ffmpeg #0 (NVENC engine A)
                ├── worker 1 → ffmpeg_runner.run_export_attempt() → ffmpeg #1 (NVENC engine B)
                └── worker 2 → ffmpeg_runner.run_export_attempt() → ffmpeg #2 (NVENC engine C)
          progress: rich progress bars on stderr / --json で JSON lines on stdout

GUI 経路 (start_detect と同じパターン):
  ExportScreen.tsx handleStartExport
    └── invoke('start_export', { metadataJson, outputDir, codec, namePattern, excludedIndexes })
          └── gui/src-tauri/src/lib.rs  start_export Tauri command
                ├── PROCESS_TRACKER に Python child を Job Object 付きで track
                ├── spawn python -m allaganeye export --stdin --json ...
                ├── Python の stdin に metadataJson を write して close
                ├── stdout 各 JSON line を parse → app.emit("export-progress", ...) で frontend へ転送
                └── Python exit 時に ExportSummary を Tauri command return として frontend に返す
          frontend:
            - export-progress listener (既存) が match_index keyed payload を受け setMatchStates 更新
            - Promise resolve で final summary を読み、CANCEL/ERROR/COMPLETE のいずれかを reducer dispatch
```

**要旨**: pool もメインスレッドも完全に Python 側。GUI Rust は単に Python subprocess を起動して JSON lines を Tauri event に橋渡しする「dumb wrapper」になる。

## 4. Python モジュール構成

| ファイル | 責務 |
| --- | --- |
| `allaganeye/export/__init__.py` | public API re-export (`export_matches`, `enumerate_h264_encoders`, `probe_nvenc_engine_count`, `H264Encoder`, `EncoderSlot`, `ExportSummary`, `ExportResult`, `ExportError`) |
| `allaganeye/export/encoder.py` | `H264Encoder` enum、`EncoderSlot` dataclass、`select_h264_encoder()`、`enumerate_h264_encoders()` |
| `allaganeye/export/nvenc_probe.py` | `probe_nvenc_engine_count(gpu_models: list[str]) -> int` SKU table + env override |
| `allaganeye/export/ffmpeg_runner.py` | `run_export_attempt(...)` 1 ffmpeg 起動 + libx264 fallback retry (Rust から移植) |
| `allaganeye/export/pool.py` | `export_matches(matches, slots, ...) -> ExportSummary` ThreadPoolExecutor orchestrator |
| `allaganeye/export/schema.py` | wire 用 dataclass (`ProgressEvent`, `ExportResult`, `ExportError`, `ExportSummary`)、JSON serializer |
| `allaganeye/commands/export.py` | Typer `export` コマンド本体 |
| `allaganeye/commands/encoder_slots.py` | Typer hidden `encoder-slots` コマンド (GUI subprocess 用、JSON 配列出力) |
| `allaganeye/cli.py` | **既存 `app.command()` decorator 単一ファイル style (line 22-66, 256-257, 411-412 周辺) を踏襲** (Codex review #7): `commands.export.export` と `commands.encoder_slots.encoder_slots` を import し、`@app.command(...)` decorator を `cli.py` で wrap (sub-app パターンは採用しない、既存 split/detect/debug-brightness と同形) |

### 4.1 `encoder.py`

```python
from enum import Enum
from dataclasses import dataclass

class H264Encoder(Enum):
    LIBX264 = "libx264"
    NVENC = "h264_nvenc"
    QSV = "h264_qsv"
    AMF = "h264_amf"
    
    @property
    def display_label(self) -> str:
        return {
            H264Encoder.LIBX264: "libx264 (CPU)",
            H264Encoder.NVENC: "NVENC",
            H264Encoder.QSV: "QSV",
            H264Encoder.AMF: "AMF",
        }[self]
    
    def quality_args(self) -> tuple[str, ...]:
        # Rust gui/src-tauri/src/lib.rs:1621-1642 から移植 (#591 baseline)
        return {
            H264Encoder.LIBX264: ("-crf", "18", "-preset", "medium"),
            H264Encoder.NVENC: ("-rc", "vbr", "-cq", "19", "-preset", "p5"),
            H264Encoder.QSV: ("-global_quality", "20", "-look_ahead", "1", "-preset", "medium"),
            H264Encoder.AMF: ("-quality", "quality", "-rc", "cqp", "-qp_i", "19", "-qp_p", "21"),
        }[self]

@dataclass(frozen=True)
class EncoderSlot:
    slot_index: int           # 0-based
    encoder_kind: H264Encoder
    display_label: str        # "NVENC #1" 等、UI 表示用

def select_h264_encoder(vendors: list[str], preference: list[str]) -> H264Encoder:
    """Rust gui/src-tauri/src/lib.rs:1666-1678 と等価な実装。"""
    for pref in preference:
        if pref in vendors:
            match pref:
                case "nvidia": return H264Encoder.NVENC
                case "intel": return H264Encoder.QSV
                case "amd": return H264Encoder.AMF
    return H264Encoder.LIBX264

def enumerate_h264_encoders(
    vendors: list[str],
    preference: list[str],
    gpu_models: list[str],
) -> list[EncoderSlot]:
    """Phase 1 (#761): NVENC 選択時のみ N slots、他は 1 slot。
    Phase 2 (#762) で iGPU encoder を追加した mixed slot 列を返すよう拡張する。"""
    primary = select_h264_encoder(vendors, preference)
    if primary == H264Encoder.NVENC:
        n = probe_nvenc_engine_count(gpu_models)
        return [
            EncoderSlot(i, H264Encoder.NVENC, f"NVENC #{i+1}")
            for i in range(n)
        ]
    return [EncoderSlot(0, primary, primary.display_label)]
```

### 4.2 `nvenc_probe.py`

```python
import os

# (GPU model substring (lowercased), NVENC engine count)
# 値は NVIDIA 公式 spec sheet 基準。新 SKU 追加時は本テーブルを更新する。
_SKU_TABLE: tuple[tuple[str, int], ...] = (
    # RTX 50 series
    ("rtx 5090", 3),
    ("rtx 5080", 2), ("rtx 5070", 2),
    ("rtx 5060", 1),
    # RTX 40 series
    ("rtx 4090", 2), ("rtx 4080", 2), ("rtx 4070", 2),
    ("rtx 4060", 1),
)
_DEFAULT_NVENC_COUNT = 1  # Codex review #9: 不明 NVIDIA カードは保守的に 1 (1-engine card
                          # の subprocess setup overhead を避けるため、過去の挙動と互換)。
                          # 2 にすると 1-engine card で timeshare → 速度低下なし but
                          # 何も得しない動作。user が高 N を望むなら env override で。

def probe_nvenc_engine_count(gpu_models: list[str]) -> int:
    """SKU substring match → engine count. env override 優先、不明なら _DEFAULT_NVENC_COUNT。
    
    Codex review #12 対応: 複数 NVIDIA GPU 環境では substring match を**最初に hit した
    SKU の値を保守的に最小化**する。例: [RTX 5090, RTX 4060] が同時検出された場合、
    Phase 1 (#761) では vendor 選択ロジックが NVIDIA primary を 1 つだけ選ぶため
    実質 1 GPU しか使わないが、誤って高い N を選んで弱い側で session 過剰 init を
    避けるため min を取る (将来 #762 で per-adapter binding に拡張)。
    
    env var ALLAGANEYE_EXPORT_CONCURRENCY は contention scenario (例: OBS 録画中) に
    user が manual 設定するためのエスケープハッチ。"""
    override = os.environ.get("ALLAGANEYE_EXPORT_CONCURRENCY", "").strip()
    if override.isdigit() and int(override) > 0:
        return int(override)
    
    lc = [m.lower() for m in gpu_models]
    matched_counts: list[int] = []
    for needle, count in _SKU_TABLE:
        if any(needle in m for m in lc):
            matched_counts.append(count)
    if matched_counts:
        return min(matched_counts)  # Codex review #12: 複数 GPU は保守的最小値
    return _DEFAULT_NVENC_COUNT
```

### 4.3 `ffmpeg_runner.py`

Rust [`run_ffmpeg_export_attempt`](../../../gui/src-tauri/src/lib.rs#L2059) と [`export_match`](../../../gui/src-tauri/src/lib.rs#L2186) の libx264 fallback retry を移植。public API:

```python
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

@dataclass(frozen=True)
class ExportAttemptResult:
    output_path: Path
    duration_ms: int
    encoder_used: H264Encoder      # 最終的に成功した encoder (fallback 含む)
    fallback_from: H264Encoder | None  # libx264 retry が発生したときの元 encoder

class ExportError(Exception):
    def __init__(self, kind: str, message: str, hint: str | None = None):
        self.kind = kind
        self.message = message
        self.hint = hint

def run_export_attempt(
    video: Path,
    start: float,
    end: float,
    output: Path,
    codec: ExportCodec,
    encoder: H264Encoder,
    *,
    progress_cb: Callable[[float, str], None],  # (percent, stage)
    fallback_cb: Callable[[H264Encoder, H264Encoder, str], None] | None = None,
    cancel_event: threading.Event,
) -> ExportAttemptResult:
    """1 試合分の ffmpeg を起動して終了まで wait。
    
    挙動:
    - vendor-resolved encoder で 1 回目を起動
    - 成功 → ExportAttemptResult を返す
    - GPU encoder init 失敗 (is_gpu_encoder_failure で stderr 文字列マッチ) →
      fallback_cb を呼んでから libx264 で再試行
    - 再試行も失敗 → ExportError raise
    - cancel_event set → ffmpeg を SIGKILL してから ExportError("cancelled") raise
    """
    ...

def is_gpu_encoder_failure(stderr_text: str, encoder: H264Encoder) -> bool:
    """Rust の同名関数を移植。encoder 別の init 失敗パターン文字列マッチ。"""
    ...
```

**ffmpeg args**: `-progress pipe:2` を渡し stderr で進捗を受ける既存パターンを踏襲。`-y` で出力上書き、`-c:v <encoder>` + `quality_args` + `-c:a copy` 等。

**memory note (Iron Law)**: `feedback_ffmpeg_qsv_stderr_pattern.md` に記録済の ffmpeg 8.1 QSV stderr パターン (`Error creating a MFX session`) を `is_gpu_encoder_failure` に確実に含める。

### 4.4 `pool.py`

```python
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue, Empty
from dataclasses import dataclass, field

@dataclass
class ExportSummary:
    success: int = 0
    failure: int = 0
    skipped: int = 0
    cancelled: bool = False
    results: dict[int, ExportAttemptResult] = field(default_factory=dict)
    errors: dict[int, ExportError] = field(default_factory=dict)

def export_matches(
    matches: list[Match],          # Match dataclass (allaganeye.matches 由来)
    slots: list[EncoderSlot],
    *,
    source_video: Path,
    output_dir: Path,
    codec: ExportCodec,
    name_pattern: str,
    progress_cb: Callable[[ProgressEvent], None],
    cancel_event: threading.Event | None = None,
) -> ExportSummary:
    """N workers (= len(slots)) で並列実行。
    
    Cancel: cancel_event set → 各 worker は次の queue.get_nowait 後に脱出、
    in-flight な ffmpeg は run_export_attempt 内で kill される。
    libx264 fallback retry は per-attempt 完結 → 並列の他 worker に影響しない。"""
    cancel_event = cancel_event or threading.Event()
    queue: Queue[Match] = Queue()
    for m in matches:
        queue.put(m)
    
    summary = ExportSummary()
    summary_lock = threading.Lock()
    
    def worker(slot: EncoderSlot):
        while not cancel_event.is_set():
            try: m = queue.get_nowait()
            except Empty: return
            
            output_path = output_dir / format_name(m, name_pattern, codec)
            
            def per_match_progress(percent: float, stage: str):
                progress_cb(ProgressEvent.progress(m.index, percent, stage))
            
            def per_match_fallback(from_enc, to_enc, msg):
                progress_cb(ProgressEvent.fallback(m.index, from_enc, to_enc, msg))
            
            try:
                result = run_export_attempt(
                    source_video, m.start, m.end, output_path, codec, slot.encoder_kind,
                    progress_cb=per_match_progress,
                    fallback_cb=per_match_fallback,
                    cancel_event=cancel_event,
                )
                progress_cb(ProgressEvent.result(m.index, result))
                with summary_lock:
                    summary.success += 1
                    summary.results[m.index] = result
            except ExportError as e:
                progress_cb(ProgressEvent.error(m.index, e))
                with summary_lock:
                    summary.failure += 1
                    summary.errors[m.index] = e
    
    with ThreadPoolExecutor(max_workers=len(slots), thread_name_prefix="export-worker") as ex:
        futures = [ex.submit(worker, slot) for slot in slots]
        for f in futures: f.result()  # 例外伝搬
    
    # Codex review #3: queue.qsize() > 0 条件は不可。in-flight ffmpeg を kill
    # した直後に queue が空 (全 match dequeue 済) でも cancellation は発生済。
    # `cancel_event.is_set()` 単独、または worker が ExportError(kind="cancelled")
    # を返したフラグで判定する。
    summary.cancelled = cancel_event.is_set() or any(
        e.kind == "cancelled" for e in summary.errors.values()
    )
    return summary
```

**ThreadPoolExecutor を選ぶ理由**: 各 worker は ffmpeg subprocess wait で I/O block。Python GIL の影響なし。`ProcessPoolExecutor` だと cancel_event の共有が IPC manager 経由になり面倒。

## 5. Wire protocol (Python → Rust → Frontend)

`--json` mode で stdout に 1 行 1 イベント (JSON Lines, each line terminated with `\n`)。**全 worker が共有する単一 stdout への書き込みは writer lock 経由で serialize** (Codex review #4 指摘): 複数 worker が `json.dumps()` + `\n` + `flush=True` を別々に呼ぶと CPython の GIL があっても改行までの atomic 性は保証されない (例: thread A が `{"type":` 出力中に thread B が割り込む可能性)。`pool.py` は 1 個の `threading.Lock` または専用 emitter thread (queue.Queue 経由) を介して `sys.stdout.write(json.dumps(ev) + "\n"); sys.stdout.flush()` を排他実行する。

スキーマ:

```typescript
type WireEvent =
  | { type: "progress"; match_index: number; percent: number; stage: "encoding" | "done" }
  | { type: "fallback"; match_index: number; fallback_from: string; fallback_to: string; message: string }
  | { type: "result"; match_index: number; output_path: string; duration_ms: number; encoder_used: string }
  | { type: "error"; match_index: number; error_kind: string; error_message: string; error_hint: string | null }
  | { type: "summary"; success: number; failure: number; skipped: number; cancelled: boolean }
```

- 各 line は **JSON object 1 個**、改行で区切る (ndjson)
- 終端: `summary` event を 1 回だけ出力してから process exit
- Python は `sys.stdout` を `flush=True` で 1 line ごとに flush して buffer 滞留を防ぐ

Rust 側 [`start_export`](#7-rust-側変更-librs) Tauri command は以下のように変換:

| Wire event | Rust 動作 |
| --- | --- |
| `progress` | `app.emit("export-progress", ExportProgress { match_index, percent, stage: "encoding"\|"done" })` |
| `fallback` | `app.emit("export-progress", ExportProgress { match_index, stage: "fallback", message, fallback_from: "h264_nvenc -> libx264" })` |
| `result` | 内部の `results` map に蓄積 (frontend には export-progress の done 経由で per-match 状態が伝わる) |
| `error` | `app.emit("export-progress", ExportProgress { match_index, stage: "error", message, hint })` |
| `summary` | Tauri command の最終 return value (`ExportSummary { success, failure, skipped, cancelled }`) |

**frontend 互換性**: 既存 `ExportProgress` payload schema ([`ExportScreen.tsx:42-49`](../../../gui/src/screens/ExportScreen.tsx#L42)) と完全一致。frontend `setMatchStates` ロジックは無改修。

## 6. CLI コマンド仕様

```bash
# 通常モード (metadata.json をディスクから読む)
allaganeye export <metadata_path> [--output-dir DIR] [--codec copy|h264]
                                  [--concurrency N] [--name-pattern PATTERN]
                                  [--quiet|--json] [--include I,J,K|--exclude I,J,K]

# stdin モード (GUI subprocess 用、in-memory edited metadata を渡す)
echo '<metadata-json>' | allaganeye export --stdin [...同上 flag]

# 必須引数:
#   metadata_path: detect/split で出力した metadata.json (--stdin と排他)

# 任意:
#   --stdin                 metadata を stdin から読む (GUI 連携用、in-memory edits をサポート)
#   --output-dir DIR        出力先 (default: source video の dirname)
#   --codec copy|h264       default: copy (無劣化分割) / h264 (再エンコード)
#   --concurrency N         slot 数 override (default: encoder.enumerate から自動決定)
#   --name-pattern PATTERN  {idx:03}_{type}_{start}.mp4 等 (default: GUI と同じ)
#   --quiet                 progress bar 抑制 (出力 path のみ)
#   --json                  stdout に JSON lines emit (GUI subprocess 用、--quiet と排他)
#   --include / --exclude   match index による絞り込み (1-based、metadata の matches[].index)

# Exit code:
#   0: 全 match success (skipped を除く)
#   1: 1 件以上 failure
#   2: 入力 error (metadata 不正、output dir 不存在 等)
#   130: SIGINT (Ctrl+C) で cancel
```

**stdin モードを設けた理由**: GUI ExportScreen は in-memory に編集済 metadata を保持しており、ディスクの metadata.json と差異がある場合がある (例: sample mode は `filePath === null` でディスクファイルなし、または preview 画面で時刻調整後 apply_changes 未実行の状態)。フロントエンドが現在の in-memory 状態を Python に直接渡すパスを `--stdin` で確保する。

stdin に流す JSON は metadata.json と同形式 (`source`, `matches[]`, `system_info` を含む)。Python 側は `json.load(sys.stdin)` で読み、それ以外の処理は通常モードと同一。

Phase 2 (#762) では `--encoder-preference nvidia,amd,intel` 等の追加 flag で multi-vendor slot を制御可能にする (本 spec では実装しない、API 設計のみ意識)。

[`docs/cli-spec.md`](../../cli-spec.md) と [`docs/output-spec.md`](../../output-spec.md) も後追いで更新する。

## 7. Rust 側変更 (lib.rs)

### 7.1 削除

| 対象 | lines | 移行先 |
| --- | --- | --- |
| `H264Encoder` enum | [1597-1653](../../../gui/src-tauri/src/lib.rs#L1597) | Python `encoder.py` |
| `select_h264_encoder` | [1666-1678](../../../gui/src-tauri/src/lib.rs#L1666) | Python `encoder.py` |
| `ExportCodec` enum | [1580-1586](../../../gui/src-tauri/src/lib.rs#L1580) | Python `schema.py` (Tauri command 引数として string で受ける) |
| `ExportResult` struct | [1683-1688](../../../gui/src-tauri/src/lib.rs#L1683) | `ExportSummary` の一部に統合 |
| `ExportProgress` struct | [1698-](../../../gui/src-tauri/src/lib.rs#L1698) | 既存 schema を維持 (frontend 互換性) |
| `run_ffmpeg_export_attempt` | [2059-2184](../../../gui/src-tauri/src/lib.rs#L2059) | Python `ffmpeg_runner.py` |
| `export_match` Tauri command | [2186-2348](../../../gui/src-tauri/src/lib.rs#L2186) | 新 `start_export` (§7.2) |
| `EncoderInfo` struct | [2385-2390](../../../gui/src-tauri/src/lib.rs#L2385) | 新 `EncoderSlot` 配列 |
| `select_h264_encoder_for_export` Tauri command | [2397-2408](../../../gui/src-tauri/src/lib.rs#L2397) | 新 `enumerate_h264_encoders` (§7.3) |
| `is_gpu_encoder_failure` | [1738-](../../../gui/src-tauri/src/lib.rs#L1738) | Python `ffmpeg_runner.py` |
| `ffmpeg_args_for_export` | [1926-](../../../gui/src-tauri/src/lib.rs#L1926) | Python `ffmpeg_runner.py` |
| `validate_export_request` | [1767-](../../../gui/src-tauri/src/lib.rs#L1767) | Python (Rust 側に最低限 sanity check は残す) |
| `tests::select_h264_encoder_*` 系 | 関連箇所 | Python `tests/test_export_encoder.py` |

### 7.2 新 `start_export` Tauri command

```rust
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartExportRequest {
    /// 完全な metadata 内容 (in-memory edited 状態を反映)。Python へは
    /// stdin 経由でこの JSON を渡し、ディスク上の metadata.json を読まない
    /// 設計にすることで sample mode (filePath=null) や未保存編集も
    /// サポートする。
    pub metadata_json: serde_json::Value,
    pub output_dir: String,
    pub codec: String,                // "copy" | "h264"
    pub name_pattern: String,
    pub excluded_indexes: Vec<u32>,
}

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
    // 1. python_path() で Python 実行ファイル解決
    // 2. tokio::process::Command で `python -m allaganeye export --stdin --json
    //    --output-dir <dir> --codec <c> --name-pattern <p> [--exclude ...]` を spawn
    //    (stdin はパイプ、stdout もパイプ)
    // 3. Windows: Job Object 付きで track_child (start_detect と同パターン、
    //    PROCESS_TRACKER に登録、descendant ffmpeg を kill 時に reap)
    // 4. stdin に req.metadata_json を JSON serialize して write して close
    // 5. stdout を BufReader::lines で 1 行ずつ読む
    //    - "progress"/"fallback"/"error" → app.emit("export-progress", ...)
    //    - "result" → 内部蓄積
    //    - "summary" → 最終 return value 用に保持
    // 6. Python process が exit したら untrack_child + summary を return
    // 7. 途中 cancel (kill_tracked_processes) で Python が SIGKILL されたら
    //    Job Object が ffmpeg descendant を全 reap、summary は cancelled=true
}
```

実装上の参照: [`start_detect`](../../../gui/src-tauri/src/lib.rs#L2820) (line range は untrack_child 周辺) と同じパターン。Job Object 付き track の例も同箇所。

### 7.3 新 `enumerate_h264_encoders` Tauri command

```rust
#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EnumerateEncodersRequest {
    pub vendors: Vec<String>,
    pub preference: Vec<String>,
    pub gpu_models: Vec<String>,
}

#[derive(Debug, serde::Serialize)]
pub struct EncoderSlot {
    pub slot_index: u32,
    pub encoder_kind: String,    // "Libx264" | "Nvenc" | "Qsv" | "Amf"
    pub display_label: String,
}

#[tauri::command]
async fn enumerate_h264_encoders(
    req: EnumerateEncodersRequest,
) -> Result<Vec<EncoderSlot>, AppError> {
    // `python -m allaganeye encoder-slots --vendors=... --preference=... --gpu-models=...`
    // を spawn して stdout の JSON 配列を parse して返す
    // (一度の呼び出しで完結、JobObject 不要、PROCESS_TRACKER 不要)
}
```

Python 側に対応する hidden CLI sub-command `allaganeye encoder-slots` を `commands/encoder_slots.py` (新規) で実装する。出力例:

```json
[{"slot_index": 0, "encoder_kind": "Nvenc", "display_label": "NVENC #1"},
 {"slot_index": 1, "encoder_kind": "Nvenc", "display_label": "NVENC #2"},
 {"slot_index": 2, "encoder_kind": "Nvenc", "display_label": "NVENC #3"}]
```

### 7.4 追加変更

- [`gui/src-tauri/src/lib.rs:3303` 周辺と `3332` 周辺の `tauri::generate_handler!` 2 箇所](../../../gui/src-tauri/src/lib.rs#L3303) (build profile cfg で分岐) から `export_match` / `select_h264_encoder_for_export` を削除し `start_export` / `enumerate_h264_encoders` を追加 (`main.rs` ではないので注意 — Codex review #1 指摘)
- [`gui/src-tauri/capabilities/default.json`](../../../gui/src-tauri/capabilities/default.json) は per-command permission を要求しない構造 (`core:default` 等の generic な許可のみ) のため、`tauri::generate_handler!` で登録すれば追加 entry 不要。レビュー時に Tauri 2 の policy が変わっていないか確認する
- [`gui/src-tauri/src/lib.rs:2757-2766`](../../../gui/src-tauri/src/lib.rs#L2757) で `start_detect` が使う `cmd.env("PYTHONIOENCODING", "utf-8:replace")` パターンを `start_export` / `enumerate_h264_encoders` でも同様に適用 (Iron Law 6 encoding boundary audit 担保、#656 修正パターン再利用、Codex review #2 指摘)
- Rust 側 stdout reader は UTF-8 lossy decode (`BufReader::lines` + UTF-8 invalid byte は U+FFFD 置換) を使い、cp932 / 不正バイトでパースが落ちないことを保証する

## 8. Frontend 変更 (ExportScreen.tsx)

### 8.1 `handleStartExport` の置換

```ts
async function handleStartExport() {
  if (!metadata) return;
  if (!videoSource) return;
  cancelRequestedRef.current = false;
  
  // setup matchStates (既存ロジック)
  const nextStates: Record<number, MatchState> = {};
  const includedIndexes: number[] = [];
  for (const m of metadata.matches) {
    if (m.type_override === 'skip' || excludedIndexes.has(m.index)) {
      nextStates[m.index] = { status: 'skipped', percent: 0 };
    } else {
      nextStates[m.index] = { status: 'pending', percent: 0 };
      includedIndexes.push(m.index);
    }
  }
  setMatchStates(nextStates);
  const startMs = Date.now();
  setExportStartMs(startMs);
  setNowMs(startMs);
  dispatch({ type: 'START_CLICKED' });
  
  try {
    const summary = await invoke<ExportSummary>('start_export', {
      req: {
        // in-memory metadata 全体を渡す (filePath=null の sample mode + 未保存編集を吸収)
        // ※ Python 側は stdin から読むため、dispatch 経路は変えない (Tauri 内で stdin に流す)
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
    // 想定外 (Python subprocess spawn 失敗 / metadata parse 失敗 等)
    const errorState = toErrorState(e);
    // global error 表示
    dispatch({ type: 'EXPORT_ERROR' });
  }
}
```

per-match の `setMatchStates` 更新は **既存の `export-progress` event listener** がそのまま処理する。設計上 listener は frontend mount 時に常時購読されているため、本変更とは独立。

### 8.2 `handleCancelClicked` (無変更)

```ts
function handleCancelClicked() {
  cancelRequestedRef.current = true;
  dispatch({ type: 'CANCEL_CLICKED' });
  void invoke('kill_tracked_processes').catch(() => undefined);
  // → Python subprocess kill + Job Object で全 ffmpeg descendant も reaped
}
```

### 8.3 encoder slot 表示

ExportScreen mount 時に encoder slot を取得して "NVENC ×3" のように表示:

```ts
const [encoderSlots, setEncoderSlots] = useState<EncoderSlot[]>([]);

useEffect(() => {
  if (!metadata?.system_info) return;
  invoke<EncoderSlot[]>('enumerate_h264_encoders', {
    req: {
      vendors: metadata.system_info.gpu_vendors_available ?? [],
      preference: metadata.system_info.vendor_preference ?? [],
      gpuModels: metadata.system_info.gpu ?? [],
    },
  }).then(setEncoderSlots).catch(() => setEncoderSlots([]));
}, [metadata?.source]);  // source video path 変化で再 enumerate

// 表示: encoderSlots.length > 1 ? `${encoderSlots[0].display_label.split(' ')[0]} ×${encoderSlots.length}` : encoderSlots[0]?.display_label
```

UI コピーは "NVENC ×3 (並列書き出し)" 等、 [`docs/ui-interaction-spec.md`](../../ui-interaction-spec.md) §「ExportScreen 」 と合わせて確定。

### 8.4 削除する frontend コード

- [`select_h264_encoder_for_export`](../../../gui/src/screens/ExportScreen.tsx) を呼ぶ箇所 (旧 single-encoder UI、`encoderInfo` state 周辺) は `enumerate_h264_encoders[0]` で legacy 表示を保持
- [`for (const m of queue) await invoke('export_match', ...)`](../../../gui/src/screens/ExportScreen.tsx#L354) のループは丸ごと削除し §8.1 に置換

## 9. NVENC contention 方針

### 9.1 想定 scenario

| 状況 | 我々の N 並列 ffmpeg の挙動 |
| --- | --- |
| 他に NVENC 使用なし | N ffmpeg → 各 engine 1 個ずつ → 理想 ~Nx |
| OBS が 1 engine 使用中 | N ffmpeg → init 全部成功、driver が timeshare で割り当て → ~(N-0.5)x ぐらいに低下 |
| 他アプリが全 engine 占有 | N ffmpeg → init 成功、全部 timeshare → スループット低下大 |
| 古い NVIDIA card (session limit あり、稀) | ffmpeg init 失敗 → libx264 fallback retry (per-slot 独立) |

### 9.2 policy

- **SKU table = 物理 engine 上限を返す**。他アプリの使用状況は考慮しない
- **timeshare はパフォーマンス低下のみで error にならない**。`is_gpu_encoder_failure` は session **init 失敗** だけを捕捉する (これは正しい振る舞い)
- **env var `ALLAGANEYE_EXPORT_CONCURRENCY` で manual override**: OBS 録画中なら user が `=2` 設定して 1 engine を OBS に残す
- **live probe は不採用**: `nvidia-smi --query-gpu=encoder.stats.sessionCount` は probe 直前の現在値で、export 中に他アプリ起動すれば即陳腐化。ジッターが頻発する

### 9.3 user-facing 周知

- [`docs/cli-spec.md`](../../cli-spec.md) の `export` セクションに env var 説明を追記
- GUI ExportScreen の encoder 表示欄に hover/tooltip で "OBS 等が NVENC を使用中の場合はパフォーマンスが低下することがあります" 程度の補足 (実装は #761 内で OK、scope 拡張せず最小限)

## 10. テスト戦略

### 10.1 Python unit test

| ファイル | 対象 |
| --- | --- |
| `tests/test_export_encoder.py` | `select_h264_encoder`: vendor 別 first match / libx264 fallback / 空 vendors。`enumerate_h264_encoders`: NVENC のとき N slot、QSV/AMF/libx264 のとき 1 slot |
| `tests/test_export_nvenc_probe.py` | RTX 5090→3, RTX 4090→2, RTX 4060→1, 不明 NVIDIA→2, env override 各種, 空 list → 2 |
| `tests/test_export_ffmpeg_runner.py` | mock subprocess.Popen で: 成功 path / GPU init 失敗 → libx264 retry / libx264 も失敗 / cancel_event 設定で早期終了 / progress callback 呼び出し |
| `tests/test_export_pool.py` | concurrency 上限遵守 (同時実行 worker 数 = len(slots))、cancel で in-flight 中断、partial failure で他 worker 続行、空 matches / 空 slots エラー |
| `tests/test_export_schema.py` | `ProgressEvent` JSON ラウンドトリップ、各 type の serializer |
| `tests/test_export_cli.py` (slow) | 実 ffmpeg + 短い test video で end-to-end。実機 NVENC は CI で動かないので libx264 で動作確認 |
| `tests/test_encoder_slots_cli.py` | `allaganeye encoder-slots --vendors=... --preference=... --gpu-models=...` の JSON 出力 |
| `tests/test_export_wire_protocol.py` (slow) | **wire protocol integration test (Codex review #5 追加)**: 実 Python subprocess を spawn し ndjson stdout を読み、`progress`/`fallback`/`result`/`error`/`summary` 各 type が正しい順序 + フォーマットで出ることを assert。Rust 側は本テストの代わりに lib.rs::tests で `parse_wire_event_*` を mock 文字列で網羅する |

### 10.2 Rust unit test

`gui/src-tauri/src/lib.rs::tests`:

- 既存 `select_h264_encoder_*` 系 test は Python に移行したので削除
- 新規: `parse_wire_event_*` (JSON line → enum 変換)、`start_export_returns_summary_on_exit` (mock Python subprocess で動作確認)、`enumerate_h264_encoders_invokes_python` (subprocess spawn + JSON parse)

### 10.3 Frontend test

`gui/src/screens/__tests__/ExportScreen.test.tsx`:

- mock invoke で `start_export` が 1 回だけ呼ばれること
- mock `export-progress` event を発火させて per-match `setMatchStates` が更新されること
- mock `start_export` reject で `EXPORT_ERROR` dispatch
- cancel ボタンで `kill_tracked_processes` が呼ばれること
- `enumerate_h264_encoders` の戻り値で encoder 表示が "NVENC ×3" のように描画されること

### 10.4 実機検証 (Iron Law 6)

PR レビュー時に Idios が実機で:

- RTX 5090 環境で N=3 並列 export → Task Manager の Video Encode engine ~90%+ 持続を 30 秒以上目視 (受け入れ条件 G8)
- 同時に OBS 録画起動して N=3 で export → 全 ffmpeg init 成功、ジッターはあれど全 match 完了 (env override なし)
- `ALLAGANEYE_EXPORT_CONCURRENCY=2` 設定で N=2 並列実行を確認
- cancel ボタン押下で全 ffmpeg が 2 秒以内に消えることを Task Manager で確認
- CLI: `allaganeye export <metadata> --codec h264` で並列実行を確認 (`nvidia-smi dmon -s u` で NVENC sum が貼り付くこと)

`AskUserQuestion` で user に明示的に依頼する (Iron Law 6 サブ条「mock テスト pass = 実機検証不要 は Red Flag」)。

## 11. 受け入れ条件 (#761 拡張版)

`gh issue edit 761` で以下を `## 確認項目 / 作業項目` に追記する:

- [ ] **CLI**: `allaganeye export <metadata.json> --codec h264` で N 並列 export が動作する (新コマンド追加、SIGINT で全 ffmpeg kill)
- [ ] **GUI**: ExportScreen の「書き出し開始」が CLI と同じ Python core を経由して N 並列実行する (`start_export` / `enumerate_h264_encoders` Tauri command 経由)
- [ ] **GUI sample mode**: filePath=null の sample mode + 未保存編集状態でも export 動作する (in-memory metadata を stdin 経由で Python に渡す)
- [ ] **共有**: CLI と GUI が同じ `allaganeye/export/` module を経由 (重複ロジックなし、Rust 側 export ロジック削除)
- [ ] NVENC engine count probe (SKU table + env override `ALLAGANEYE_EXPORT_CONCURRENCY`)
- [ ] cancel: 全 in-flight ffmpeg が秒以内に kill される (CLI=SIGINT, GUI=`kill_tracked_processes` 経由 Job Object reaping)
- [ ] **GUI ウィンドウクローズ** (Codex review #11): export 進行中に `[×]` でウィンドウを閉じた際、確認ダイアログ → 確定で全 ffmpeg + Python subprocess が Task Manager > Details で 2 秒以内に reaped されること。Phase 1 (#761) では新規 close handler 追加せず、既存 `on_window_event` (lib.rs:3059-3068) CloseRequested → `prevent_close` + frontend 通知 → frontend が cancel/cleanup を dispatch する path + `force_exit_app` + `kill_tracked_processes` 経由で対応
- [ ] libx264 fallback retry: 並列実行中の 1 slot が失敗しても他 slot は続行
- [ ] 既存 progress event schema (`export-progress` Tauri event with `match_index` keyed payload) は後方互換
- [ ] 出力ファイルが ffprobe で妥当な codec / 解像度 / 長さ (byte-exact 比較は encoder 並列度依存で不可)
- [ ] 実機検証 (Iron Law 6): RTX 5090 で N=3 並列 → Task Manager Video Encode engine ~90%+ 持続 30 秒以上
- [ ] disk I/O / memory: 同一 source の N 並列 read で stuck しない (NVMe Gen4 想定、HDD 環境は best effort)
- [ ] テスト: Python unit (encoder / nvenc_probe / ffmpeg_runner / pool / schema)、Rust unit (wire 変換)、frontend (mock invoke)、CLI smoke、実機検証

## 12. Phase 構成と PR 戦略

user 判断により **1 PR ノンストップ**で出す。

[docs/refactor-pattern.md](../../refactor-pattern.md) §1 の閾値は **additions + deletions の合算 (churn)** で判定する (Codex review #8 指摘で再計算)。本 spec の churn 見積もり:

- Rust 削除: -400 line (deletions count = 400)
- Python 新規: +1500 line (additions = 1500)
- frontend: +200 / -100 line (additions = 200, deletions = 100)
- docs: +50 line (additions, 既存 cli-spec.md / output-spec.md 追記)
- **churn = 1500 + 400 + 200 + 100 + 50 = 約 2250 line** ([docs/refactor-pattern.md](../../refactor-pattern.md) §1 の 1000 line 閾値の **2.25 倍**)

waive の根拠:

- 機能境界が明確 (export だけ。detect/preview/restore/その他は touch しない)
- Python module は新設なので既存コードへの影響が限定的 (新ファイル比率 高)
- Rust 削除箇所は連続 (export_match + 周辺の 5-6 関数)、半端な状態で commit する利点がない (Phase B (GUI 切替) で旧 export_match を一時的に残す案は維持コストが上回る)
- frontend 変更は handleStartExport 1 関数 + encoder 表示部のみ (UI 全体は無改修)
- 機能 dependency: Python core (Phase A) → GUI 切替 (Phase B) → NVENC 並列 enabling (Phase C) は完全直列。Phase C 単独で merge すると Phase A/B が pending 状態のため、結局 Phase A+B+C を 1 PR で出すしかない構造
- user (Idios) が 1 PR を明示選択

reviewer への負担緩和措置:

- commit を機能単位で 5-8 個に分割 (Phase A 相当の Python core / wire protocol / Rust 切替 / frontend 切替 / test) し、commit ごとに review しやすくする
- Self-Test Report 内に file-by-file diff summary を記載
- PR 本文に `## レビュー指針` を載せて重点 review ポイント (encoding boundary / wire protocol / cancel semantics) を誘導

予想 touched files 一覧:

| カテゴリ | ファイル数 |
| --- | --- |
| Python new (`allaganeye/export/{__init__,encoder,nvenc_probe,ffmpeg_runner,pool,schema}.py`, `allaganeye/commands/{export,encoder_slots}.py`) | 8 |
| Python test new (`tests/test_export_*.py`、`test_encoder_slots_cli.py`) | 8 |
| Python existing (`allaganeye/cli.py`) | 1 |
| Rust (`gui/src-tauri/src/lib.rs`) | 1 |
| Frontend (`gui/src/screens/ExportScreen.tsx`、関連 test、state、`gui/src-tauri/capabilities/default.json` 必要時のみ) | ~3-5 |
| Docs (`docs/cli-spec.md`、`docs/output-spec.md`、本 spec) | 3 |
| 合計 | ~24-27 |

PR 提出時は self-test report を `docs/l2-workflow.md §Self-Test Report 規約` に従って書き、実機検証 trigger を `AskUserQuestion` で user に依頼する。

## 13. Migration / cleanup

- Python `H264Encoder` の string value (`"h264_nvenc"` 等) を ffmpeg `-c:v` に直接渡せる形式にすることで、Rust 側 `ffmpeg_codec_name()` 相当の関数を不要にする
- 旧 Rust `select_h264_encoder_for_export` への frontend 呼び出しを完全削除し、frontend には `enumerate_h264_encoders` 経由でしか slot 情報が来ない設計にする
- 旧 `EncoderInfo` type を frontend から削除 (`EncoderSlot[]` で置換)
- `gui/src-tauri/src/lib.rs::tests` の `select_h264_encoder_*` 系 test は Python に移行したので削除 (テスト範囲は維持)
- 古い metadata.json (system_info 欄なし) の対応: `enumerate_h264_encoders` が空 vendors を受けた場合に `[Libx264]` 1 slot を返す挙動を維持

## 14. リスクと未確定事項

### R1: Python startup overhead (subprocess 起動コスト)

GUI が `start_export` を invoke するたびに Python subprocess を起動するため、毎回 ~200ms (Windows) のオーバーヘッドがある。export は通常 1 回の操作で N 試合まとめて処理するため、N=10 試合 + 1 回の subprocess 起動 = 200ms / 10 = 20ms per match のオーバーヘッド → 無視できる。

`enumerate_h264_encoders` は ExportScreen mount 時 1 回のみ呼ぶため、これも無視できる。

### R2: Job Object による descendant reaping の信頼性

`start_detect` で既に実証済みのパターンを再利用 ([docs/process-tree-orphan-audit.md](../../process-tree-orphan-audit.md))。export でも同じパターンを適用する。

### R3: cancel race condition

cancel 直後に Python が新 match を queue.get_nowait しないことを保証するには `cancel_event` を queue.get の前で必ずチェックする必要がある (§4.4 の worker 実装で対応済)。

### R4: ffmpeg progress filter の version 依存

[#575](https://github.com/Idios/kobutachan-allaganeye/issues/575) で ffmpeg 8.1 の `fps` filter version 依存が記録済。export では `-progress pipe:2` の `out_time_ms` を使うため `fps` filter は経由しない → R4 は対象外。

### R5: 大量 NVENC session の安定性

RTX 5090 で 3 並列を継続実行した場合の driver 安定性 (memory leak / driver crash 等) は実機検証で確認。問題があれば SKU table を保守的に (e.g. RTX 5090 → 2) 調整する。

### R6: encoder 別 quality 同等性

NVENC / QSV / AMF / libx264 で生成される H.264 stream の bitrate / VMAF は encoder 別に異なる。本 spec では Rust の既存値 ([line 1621-1642](../../../gui/src-tauri/src/lib.rs#L1621)) をそのまま Python に移植する。Phase 2 (#762) での品質チューニングは別 issue。

### R7: SKU table カバレッジ

`_SKU_TABLE` は RTX 40/50 系のみカバー。古い NVIDIA カード (GTX 1660, RTX 2080 等) や future SKU は default の **1** にフォールバック (Codex review #9 で 2 → 1 に変更)。1-engine カードでも 1 session 起動なら setup overhead 最小化。user が複数 engine の高 N を望むなら env override で。新 SKU リリース時に table 追加が必要。

### R8: libx264 fallback 中の CPU 競合 (Codex review #10)

並列 3 slot のうち 1 slot が NVENC init 失敗で libx264 fallback すると、その slot が CPU を集約消費する。残り 2 slot は NVENC でも fallback slot の CPU 負荷で全体スループットが落ちる可能性。Phase 1 (#761) では **functional な regression がない (各 slot は完了する) ため許容**し、性能チューニング (libx264 fallback 時に他 slot を一時的に dec 並列度下げる等) は別 issue (Phase 2 以降) に defer する。Self-Test Report で実機計測時にこの scenario の挙動を観察し、悪化が大きければ #761 内で対応するか別 issue 起票するかを user 判断とする。

### R9: ウィンドウクローズ時の export cleanup (Codex review #11)

ユーザーが export 進行中に GUI ウィンドウを `[×]` で閉じた場合、現状の `force_exit_app` ([gui/src-tauri/src/lib.rs:1533](../../../gui/src-tauri/src/lib.rs#L1533)) は app.exit(0) する前に `on_window_event` で `prevent_close` が走るため、frontend が cleanup する余地がある。本 spec の Python subprocess は `PROCESS_TRACKER` 経由で管理されているため、`force_exit_app` 前に `kill_tracked_processes` が呼ばれていれば Job Object 経由で全 ffmpeg descendant が reaped される。

**Phase 1 (#761) 実装決定**: 新規 WindowCloseRequested handler は追加しない。既存 `on_window_event` (lib.rs:3059-3068) の CloseRequested → `prevent_close` + frontend 通知 → frontend が cancel/cleanup を dispatch する path を維持し、`force_exit_app` + `kill_tracked_processes` 経由で全 Python + ffmpeg subprocess を reap する。実機検証 (Iron Law 6 trigger): export 進行中に [×] → 確認ダイアログ → 確定で全プロセスが Task Manager > Details で 2 秒以内に reaped されること。

## 15. 後続 issue への影響

- **#762 (multi-vendor 並列)**: 本 spec の `EncoderSlot` 列を mixed (例 `[Nvenc; 3, Amf; 1]`) にするだけで成立。`enumerate_h264_encoders` の戻り値生成ロジックのみ拡張、pool は無改修
- **#765 (NVDEC saturation 計測記録)**: 本 spec 実装後に export 並列化前後の比較計測を追記 (clos 後の参考データ)
- **新 issue**: SKU table 自動更新の仕組み (NVIDIA から spec sheet を引っ張ってくる cron 等) は Phase 2 以降の改善余地

## 16. 参考

- [issue #761 task body](https://github.com/Idios/kobutachan-allaganeye/issues/761) — original scope (GUI only) と作業項目
- [issue #762 multi-vendor 並列](https://github.com/Idios/kobutachan-allaganeye/issues/762) — 後続 issue、`EncoderSlot` 拡張のターゲット
- [issue #765 NVDEC saturation 記録](https://github.com/Idios/kobutachan-allaganeye/issues/765) — detect 側計測結果、export 並列化動機の根拠
- [issue #591 vendor-aware encoder 選択](https://github.com/Idios/kobutachan-allaganeye/issues/591) — Rust 側既存実装、本 spec で Python に移植する対象
- [`gui/src-tauri/src/lib.rs:2186-2348`](../../../gui/src-tauri/src/lib.rs#L2186) — 現状 `export_match` 実装
- [`gui/src/screens/ExportScreen.tsx:354-398`](../../../gui/src/screens/ExportScreen.tsx#L354) — 現状 sequential loop
- [`allaganeye/system_info.py:406-431`](../../../allaganeye/system_info.py#L406) — `probe_gpu_vendors()` 既存実装
- [docs/refactor-pattern.md](../../refactor-pattern.md) — Phase 分割 trigger
- [docs/l2-workflow.md](../../l2-workflow.md) — Iron Law 6 (PR Pre-flight, 実機検証 trigger)
- [docs/cli-spec.md](../../cli-spec.md) — 後追いで `export` セクション追記
- [docs/system-architecture.md](../../system-architecture.md) — CLI/GUI 統合方針 (start_detect パターン)
