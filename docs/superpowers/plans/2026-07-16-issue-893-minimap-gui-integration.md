# minimap crop GUI 統合 (#893) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GUI 上で minimap (エリアマップ) crop を完結させる — 動画上の overlay で領域を確認・調整し、実行・進捗表示・完了後の `minimap_regions` 反映まで CLI 併用なしで行える。

**Architecture:** export 同型の 3 層構成。CLI `minimap` に `--json` (JSON Lines wire) と `--expected-mtime` (write-back の compare-and-swap guard) を追加 → Tauri `start_minimap` / `detect_minimap_regions` command が subprocess を path 渡しで起動し `minimap-progress` event を emit → 新規 `MinimapScreen` が video + ドラッグ選択 overlay + 進捗を提供。metadata は positional path 渡しで CLI が disk を fresh read + merge write-back し、`--expected-mtime` CAS で #514 外部編集 clobber を構造的に防ぐ。

**Tech Stack:** Python (typer / dataclass) / Rust (Tauri 2 / tokio) / React 19 + TS + Zustand + zod / vitest + jest-axe / pytest / cargo test。

## Global Constraints

- **released 経路非接触**: `detector.py` / `scorebar.py` / `detect` / `split` / `export` の既存経路・cache key を変更しない。新設は minimap の `--json`/`--expected-mtime` mode と GUI 画面のみ。
- **metadata は positional path 渡し** (`--stdin` を追加しない)。CLI が disk を fresh read し既存 merge 保全ロジックを使う。
- **write-back CAS**: crop の `--expected-mtime <ms>` は `write_metadata_atomic` 直前に `st_mtime_ns // 1_000_000` を再計算し `!=` expected なら write せず conflict exit。ms 値は Rust `file_mtime_ms` (`modified().duration_since(UNIX_EPOCH).as_millis()`) と一致する floor-ms、exact 比較。
- **event 名は `minimap-progress`** (export の `export-progress` と別チャネル)。payload 形は export の `ExportProgressPayload` と同一。
- **commit の Co-Authored-By は `Claude Fable 5 <noreply@anthropic.com>`** 固定。
- **conflict exit code**: minimap crop の CAS 不一致は **exit code 6** (新設。既存 0/1/2/3/4/5/7/130 と衝突しない) とし、Rust が code 6 を `state.mtime_conflict` AppError にマップする。
- **命名**: `MinimapScreen` / `start_minimap` / `detect_minimap_regions` / `minimap-progress` / `reloadFromDisk` / `MinimapProposal`。
- **PR 分割**: Phase 1 (Task 1-6、CLI + Rust + store backbone) = PR 1、Phase 2 (Task 7-12、UI + navigation + docs) = PR 2。#893 は Phase 2 merge 後に close。
- **spec**: `docs/superpowers/specs/2026-07-16-issue-893-minimap-gui-integration-design.md` が SSoT。

---

## Phase 1 — Backbone (invariant-critical) — PR 1

新設した exit code 6・schema・wire・CLI 契約は Phase 1 で全て決着させる。Phase 1 の deliverable は「GUI 無しで CLI `minimap --json`/`--expected-mtime` が動き、Tauri command と store reload が cargo/vitest test で green」であること。

### Task 1: CLI minimap crop `--json` mode

**Files:**

- Modify: `allaganeye/commands/minimap.py` (register() 内の `minimap` 関数 signature + crop モードの progress_cb)
- Test: `tests/test_minimap_command.py` (既存があれば追記、無ければ新規)

**Interfaces:**

- Consumes: 既存 `allaganeye.export.wire.WireWriter` / `allaganeye.export.schema.ProgressEvent` / `export_matches(progress_cb=…)`。
- Produces: `allaganeye minimap <path> --region X,Y,W,H --json` が crop の per-match `result`/`error`/`fallback` + 末尾 `summary` を ndjson で stdout に emit する契約。

- [ ] **Step 1: Write the failing test**

`tests/test_minimap_command.py` に追加:

```python
import json
from pathlib import Path
from typer.testing import CliRunner
from allaganeye.cli import app
from allaganeye.export.schema import ExportSummary
import allaganeye.commands.minimap as minimap_mod

runner = CliRunner(mix_stderr=False)


def _write_metadata(tmp_path: Path, source: Path) -> Path:
    meta = {
        "schema_version": "1",
        "source": str(source),
        "matches": [
            {"index": 1, "type": "fl_match", "start_time": 60.0, "end_time": 120.0},
        ],
    }
    p = tmp_path / "metadata.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    return p


def test_minimap_json_emits_ndjson_result_and_summary(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)

    # Stub probe (frame size) and export_matches (encode) so no ffmpeg runs.
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    def fake_export_matches(*, matches, progress_cb, **kwargs):
        from allaganeye.export.schema import ProgressEvent

        for m in matches:
            progress_cb(
                ProgressEvent.result(
                    match_index=m.index,
                    output_path=Path("out") / f"{m.index:03}.mp4",
                    duration_ms=1000,
                    encoder_used="libx264",
                )
            )
        return ExportSummary(
            success=len(matches), failure=0, skipped=0, cancelled=False
        )

    monkeypatch.setattr(minimap_mod, "export_matches", fake_export_matches)

    result = runner.invoke(
        app,
        ["minimap", str(meta_path), "--region", "10,20,300,400", "--json"],
    )
    assert result.exit_code == 0, result.stdout
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    types = [ln["type"] for ln in lines]
    assert "result" in types
    assert types[-1] == "summary"
    assert lines[-1]["success"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_minimap_command.py::test_minimap_json_emits_ndjson_result_and_summary -v`
Expected: FAIL (`--json` オプション未定義で `no such option` / exit_code != 0)。

- [ ] **Step 3: Add `--json` option + wire the crop progress_cb**

`allaganeye/commands/minimap.py`:

1. import に追加 (ファイル冒頭の import 群):

```python
import sys
from allaganeye.export.wire import WireWriter
```

1. `minimap` 関数の signature に `quiet` の直後へ追加:

```python
json_mode: Annotated[
    bool,
    typer.Option(
        "--json",
        help="Emit JSON Lines on stdout (GUI subprocess mode).",
    ),
] = (False,)
```

1. 関数本体冒頭 (docstring 直後) に排他チェックを追加:

```python
        if json_mode and quiet:
            raise typer.BadParameter("--json and --quiet are mutually exclusive")
```

1. crop モードの `progress_cb` 定義 (現状 `if quiet: … else: …` の 2 分岐) を 3 分岐に置換。`export.py` line 286-323 と同型:

```python
        writer: WireWriter | None = None
        if json_mode:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            writer = WireWriter(stream=sys.stdout)

            def progress_cb(ev: ProgressEvent) -> None:
                assert writer is not None
                writer.emit(ev)

        elif quiet:

            def progress_cb(ev: ProgressEvent) -> None:
                pass

        else:
            # (既存の plain-text progress_cb をそのまま残す)
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
```

1. `export_matches(...)` 呼び出し後、summary 判定の前 (`if summary.cancelled:` の直前) に summary emit を追加:

```python
        if json_mode and writer is not None:
            writer.emit(ProgressEvent.summary(summary))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_minimap_command.py::test_minimap_json_emits_ndjson_result_and_summary -v`
Expected: PASS。

- [ ] **Step 5: Guard existing plain-text mode is unbroken**

Run: `pytest tests/test_minimap_command.py -v`
Expected: 既存 crop/提案テストも PASS (plain-text mode 非破壊)。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/commands/minimap.py tests/test_minimap_command.py
git commit -m "feat(#893): minimap crop --json wire mode (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: CLI minimap `--expected-mtime` CAS guard

**Files:**

- Modify: `allaganeye/commands/minimap.py` (signature + write-back 直前の re-stat)
- Test: `tests/test_minimap_command.py`

**Interfaces:**

- Consumes: 既存 `write_metadata_atomic(metadata_path, payload)` (Task で触る箇所は minimap.py の `# ------ 8. write-back` 節)。
- Produces: `--expected-mtime <ms:int>` 指定時、`write_metadata_atomic` 直前に `metadata_path.stat().st_mtime_ns // 1_000_000` を再計算し `!= expected` なら write せず **exit code 6** で中断する契約。省略時は guard skip。

- [ ] **Step 1: Write the failing tests (fire + no-fire + backward-compat)**

```python
def test_minimap_expected_mtime_conflict_aborts_without_write(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )
    wrote = {"called": False}
    monkeypatch.setattr(
        minimap_mod,
        "write_metadata_atomic",
        lambda p, payload: wrote.__setitem__("called", True),
    )
    # export_matches must never run when the CAS aborts.
    monkeypatch.setattr(
        minimap_mod,
        "export_matches",
        lambda **k: (_ for _ in ()).throw(AssertionError("encode ran on conflict")),
    )
    # Pass a stale expected mtime (0) -> current mtime differs -> conflict.
    result = runner.invoke(
        app,
        [
            "minimap",
            str(meta_path),
            "--region",
            "10,20,300,400",
            "--json",
            "--expected-mtime",
            "0",
        ],
    )
    assert result.exit_code == 6, result.stdout
    assert wrote["called"] is False


def test_minimap_expected_mtime_match_writes(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )
    monkeypatch.setattr(
        minimap_mod,
        "export_matches",
        lambda **k: ExportSummary(success=1, failure=0, skipped=0, cancelled=False),
    )
    current_ms = meta_path.stat().st_mtime_ns // 1_000_000
    result = runner.invoke(
        app,
        [
            "minimap",
            str(meta_path),
            "--region",
            "10,20,300,400",
            "--json",
            "--expected-mtime",
            str(current_ms),
        ],
    )
    assert result.exit_code == 0, result.stdout
    written = json.loads(meta_path.read_text(encoding="utf-8"))
    assert written["minimap_regions"][0]["match_index"] == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_minimap_command.py -k expected_mtime -v`
Expected: FAIL (`--expected-mtime` 未定義)。

- [ ] **Step 3: Add `--expected-mtime` option + CAS**

`allaganeye/commands/minimap.py`:

1. signature に追加 (`json_mode` の直後):

```python
expected_mtime: Annotated[
    int | None,
    typer.Option(
        "--expected-mtime",
        help=(
            "Compare-and-swap guard (GUI subprocess mode): abort with "
            "exit 6 if metadata.json mtime (ms) differs at write time."
        ),
    ),
] = (None,)
```

1. write-back 節 (`payload["minimap_regions"] = minimap_entries` の直後、`write_metadata_atomic` の直前) に CAS を挿入:

```python
        # CAS guard (#893, Codex critical): re-stat right before the atomic
        # write. floor-ms must match Rust file_mtime_ms (as_millis). On mismatch
        # abort WITHOUT writing so an external edit between our read and write
        # is never clobbered (#514 class). exit 6 -> GUI ConflictModal.
        if expected_mtime is not None:
            try:
                current_mtime = metadata_path.stat().st_mtime_ns // 1_000_000
            except OSError:
                current_mtime = -1
            if current_mtime != expected_mtime:
                typer.echo(
                    "conflict: metadata.json was modified externally "
                    f"(expected mtime {expected_mtime}, got {current_mtime}); "
                    "not writing",
                    err=True,
                )
                raise typer.Exit(code=6)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_minimap_command.py -k expected_mtime -v`
Expected: PASS (both).

- [ ] **Step 5: Full command suite green**

Run: `pytest tests/test_minimap_command.py -v`
Expected: PASS (CAS off = backward compat 不変)。

- [ ] **Step 6: Commit**

```bash
git add allaganeye/commands/minimap.py tests/test_minimap_command.py
git commit -m "feat(#893): minimap write-back expected-mtime CAS guard (exit 6) (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI minimap proposal `--json` mode + proposal event

**Files:**

- Modify: `allaganeye/export/schema.py` (`ProgressEvent.proposal` classmethod)
- Modify: `allaganeye/commands/minimap.py` (提案モードの `--json` 分岐)
- Test: `tests/test_export_schema.py` (proposal event) / `tests/test_minimap_command.py` (提案 `--json`)

**Interfaces:**

- Consumes: 既存 `resolve_match_regions(source_video, match_tuples) -> (results, warns)`。`results` は各 `mr.match_index` / `mr.region` (`.x/.y/.w/.h/.confidence`) / `mr.scattered` を持つ。
- Produces: `ProgressEvent.proposal(match_index, region_dict_or_none, confidence, scattered)`。提案モード `--json` で 1 match 1 行 `{"type":"proposal","match_index":N,"region":{x,y,w,h}|null,"confidence":c,"scattered":bool}` を emit し exit 4。

- [ ] **Step 1: Write the failing schema test**

`tests/test_export_schema.py` に追加:

```python
def test_progress_event_proposal_with_region():
    from allaganeye.export.schema import ProgressEvent

    ev = ProgressEvent.proposal(
        match_index=2,
        region={"x": 10, "y": 20, "w": 300, "h": 400},
        confidence=0.87,
        scattered=False,
    )
    import json

    payload = json.loads(ev.to_json_line())
    assert payload["type"] == "proposal"
    assert payload["match_index"] == 2
    assert payload["region"] == {"x": 10, "y": 20, "w": 300, "h": 400}
    assert payload["confidence"] == 0.87
    assert payload["scattered"] is False


def test_progress_event_proposal_none_region():
    from allaganeye.export.schema import ProgressEvent
    import json

    ev = ProgressEvent.proposal(
        match_index=3, region=None, confidence=0.0, scattered=False
    )
    assert json.loads(ev.to_json_line())["region"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_export_schema.py -k proposal -v`
Expected: FAIL (`proposal` classmethod なし)。

- [ ] **Step 3: Add `ProgressEvent.proposal`**

`allaganeye/export/schema.py` の `ProgressEvent` に追加 (`summary` classmethod の後):

```python
    @classmethod
    def proposal(
        cls,
        match_index: int,
        region: dict[str, int] | None,
        confidence: float,
        scattered: bool,
    ) -> ProgressEvent:
        return cls(
            {
                "type": "proposal",
                "match_index": match_index,
                "region": region,
                "confidence": confidence,
                "scattered": scattered,
            }
        )
```

- [ ] **Step 4: Run schema test to verify pass**

Run: `pytest tests/test_export_schema.py -k proposal -v`
Expected: PASS。

- [ ] **Step 5: Write the failing command test (proposal --json)**

`tests/test_minimap_command.py` に追加:

```python
def test_minimap_proposal_json_emits_proposal_lines_exit4(tmp_path, monkeypatch):
    source = tmp_path / "vid.mp4"
    source.write_bytes(b"\x00")
    meta_path = _write_metadata(tmp_path, source)
    monkeypatch.setattr(
        minimap_mod, "probe_video", lambda p: {"width": 1920, "height": 1080}
    )

    class _Region:
        x, y, w, h, confidence = 0.01, 0.02, 0.15, 0.20, 0.9

    class _MR:
        match_index = 1
        region = _Region()
        scattered = False

    monkeypatch.setattr(
        minimap_mod,
        "resolve_match_regions",
        lambda source, tuples: ([_MR()], []),
    )

    result = runner.invoke(app, ["minimap", str(meta_path), "--json"])
    assert result.exit_code == 4, result.stdout
    lines = [json.loads(ln) for ln in result.stdout.splitlines() if ln.strip()]
    prop = [ln for ln in lines if ln["type"] == "proposal"]
    assert prop and prop[0]["match_index"] == 1
    # normalized region -> pixel ints at 1920x1080
    assert prop[0]["region"] == {"x": 19, "y": 22, "w": 288, "h": 216}
```

- [ ] **Step 6: Run to verify failure**

Run: `pytest tests/test_minimap_command.py -k proposal_json -v`
Expected: FAIL (提案モードが `--json` を無視して plain-text を出す)。

- [ ] **Step 7: Wire proposal `--json` branch**

`allaganeye/commands/minimap.py` の提案モード節 (`# ------ 4a. 提案モード`)、`results, warns = resolve_match_regions(...)` の後の表示ロジックを `json_mode` で分岐。既存 plain-text ブロックは `else:` に残す:

```python
            for w in warns:
                typer.echo(w, err=True)
            if json_mode:
                if hasattr(sys.stdout, "reconfigure"):
                    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
                writer = WireWriter(stream=sys.stdout)
                for mr in results:
                    r = mr.region
                    region_px = {
                        "x": round(r.x * frame_w),
                        "y": round(r.y * frame_h),
                        "w": round(r.w * frame_w),
                        "h": round(r.h * frame_h),
                    }
                    writer.emit(
                        ProgressEvent.proposal(
                            match_index=mr.match_index,
                            region=region_px,
                            confidence=r.confidence,
                            scattered=mr.scattered,
                        )
                    )
                raise typer.Exit(code=4)
            # else: 既存の plain-text 表示ブロックをそのまま残す
            if not results:
                ...  # (既存コードのまま)
```

(既存 plain-text ブロックの末尾 `raise typer.Exit(code=4)` はそのまま。`json_mode` ブロックは早期 return するため二重にはならない。)

- [ ] **Step 8: Run to verify pass**

Run: `pytest tests/test_minimap_command.py -k proposal -v`
Expected: PASS。

- [ ] **Step 9: Full suites green**

Run: `pytest tests/test_minimap_command.py tests/test_export_schema.py -v`
Expected: PASS (plain-text 提案モード非破壊)。

- [ ] **Step 10: Commit**

```bash
git add allaganeye/export/schema.py allaganeye/commands/minimap.py tests/test_export_schema.py tests/test_minimap_command.py
git commit -m "feat(#893): minimap proposal --json emits proposal events (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Rust `start_minimap` command

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (新 command + `StartMinimapRequest` struct + `invoke_handler` 登録)
- Test: `gui/src-tauri/src/lib.rs` の `#[cfg(test)]` module (start_export の arg-build / parse test を mirror)

**Interfaces:**

- Consumes: 既存 `resolve_allaganeye_command` / `TrackedChild` / `track_child` / `PROCESS_TRACKER` / `AppError` / `ExportSummary` (Rust) / `drain_to_bounded_tail` / `file_mtime_ms`。
- Produces: `#[tauri::command] start_minimap(app, req: StartMinimapRequest) -> Result<ExportSummary, AppError>`。`req = {metadataPath, region, outputDir, namePattern, excludedIndexes: Vec<u32>, expectedMtimeMs: Option<u64>, overwrite: bool}`。**先頭で `minimap_write_guard(&req)?` を呼び、`overwrite=false` かつ mtime 不在なら spawn 前に `state.mtime_required` で fail-closed reject** (#893 R2 Codex HIGH)。CLI exit 6 → `AppError("state.mtime_conflict", …)` reject。stdout JSON Lines を `minimap-progress` event で emit。

- [ ] **Step 1: Write the failing test (request → argv)**

`gui/src-tauri/src/lib.rs` の test module に追加 (既存の start_export argv test を mirror。関数を `build_minimap_argv(&StartMinimapRequest) -> Vec<String>` に切り出して test 可能にする):

```rust
#[test]
fn minimap_argv_includes_region_and_expected_mtime() {
    let req = StartMinimapRequest {
        metadata_path: "C:/x/metadata.json".into(),
        region: "10,20,300,400".into(),
        output_dir: "C:/x/minimap".into(),
        name_pattern: "{idx:03}_{type}_{start}_minimap.mp4".into(),
        excluded_indexes: vec![2, 3],
        expected_mtime_ms: Some(1_700_000_000_000),
    };
    let argv = build_minimap_argv(&req);
    assert!(argv.contains(&"minimap".to_string()));
    assert!(argv.contains(&"C:/x/metadata.json".to_string()));
    assert!(argv.contains(&"--json".to_string()));
    assert!(argv.windows(2).any(|w| w[0] == "--region" && w[1] == "10,20,300,400"));
    assert!(argv.windows(2).any(|w| w[0] == "--expected-mtime" && w[1] == "1700000000000"));
    assert!(argv.windows(2).any(|w| w[0] == "--exclude" && w[1] == "2,3"));
}

#[test]
fn minimap_argv_omits_expected_mtime_when_none() {
    let req = StartMinimapRequest {
        metadata_path: "m.json".into(), region: "0,0,16,16".into(),
        output_dir: "o".into(), name_pattern: "p.mp4".into(),
        excluded_indexes: vec![], expected_mtime_ms: None,
    };
    let argv = build_minimap_argv(&req);
    assert!(!argv.iter().any(|a| a == "--expected-mtime"));
    assert!(!argv.iter().any(|a| a == "--exclude"));
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui/src-tauri && cargo test minimap_argv`
Expected: FAIL (`StartMinimapRequest` / `build_minimap_argv` 未定義)。

- [ ] **Step 3: Add struct + argv builder + command**

`gui/src-tauri/src/lib.rs`:

1. `StartExportRequest` の近くに追加:

```rust
#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct StartMinimapRequest {
    pub metadata_path: String,
    pub region: String,
    pub output_dir: String,
    pub name_pattern: String,
    #[serde(default)]
    pub excluded_indexes: Vec<u32>,
    #[serde(default)]
    pub expected_mtime_ms: Option<u64>,
    // #893 R2 (Codex HIGH): explicit overwrite intent. false (default) = guarded
    // (mtime required, see minimap_write_guard); true = deliberate post-Conflict
    // overwrite (CAS bypassed, --expected-mtime omitted).
    #[serde(default)]
    pub overwrite: bool,
}

// #893 R2: fail-closed guard — no unguarded write-back subprocess is ever
// spawned. Call FIRST in start_minimap, before resolve_allaganeye_command.
fn minimap_write_guard(req: &StartMinimapRequest) -> Result<(), AppError> {
    if !req.overwrite && req.expected_mtime_ms.is_none() {
        return Err(AppError::new(
            "state.mtime_required",
            "minimap crop requires an expected mtime unless overwrite is set (refusing an unguarded write-back)",
        )
        .with_default_hint());
    }
    Ok(())
}

fn build_minimap_argv(req: &StartMinimapRequest) -> Vec<String> {
    let mut argv = vec![
        "minimap".to_string(),
        req.metadata_path.clone(),
        "--json".to_string(),
        "--region".to_string(),
        req.region.clone(),
        "--output-dir".to_string(),
        req.output_dir.clone(),
        "--name-pattern".to_string(),
        req.name_pattern.clone(),
    ];
    // #893 R2: overwrite=true omits --expected-mtime so the CLI skips its CAS
    // (deliberate overwrite). When !overwrite the guard guarantees mtime is Some.
    if !req.overwrite {
        if let Some(m) = req.expected_mtime_ms {
            argv.push("--expected-mtime".to_string());
            argv.push(m.to_string());
        }
    }
    if !req.excluded_indexes.is_empty() {
        let joined = req
            .excluded_indexes
            .iter()
            .map(|i| i.to_string())
            .collect::<Vec<_>>()
            .join(",");
        argv.push("--exclude".to_string());
        argv.push(joined);
    }
    argv
}
```

1. `start_export` を丸ごと clone して `start_minimap` を作る。**start_export (lib.rs ~2904-末尾) をそのまま複製**し、以下の delta のみ変更:
   - 関数名 `start_minimap`、引数 `req: StartMinimapRequest`。
   - cmd 引数構築を `for a in build_minimap_argv(&req) { cmd.arg(a); }` に置換 (export の `cmd.arg("export").arg("--stdin")…` ブロックを削除)。
   - **stdin へ metadata を書く節を削除** (path 渡しなので不要)。`cmd.stdin(Stdio::piped())` も削除し `stdin(Stdio::null())`。
   - stdout の JSON Lines を parse して emit する event 名を `"export-progress"` → `"minimap-progress"` に変更。
   - 子プロセスの **exit code 6 を検知したら** `AppError::new("state.mtime_conflict", "conflict: metadata.json was modified externally")` で `Err` を返す (summary を success 扱いしない)。既存 start_export の「exit status で分岐して summary を返す」箇所に code 6 分岐を追加:

```rust
        // #893 -- CAS conflict from the CLI (exit 6) maps to the same #514
        // conflict AppError the apply() path uses, so the GUI can reuse
        // ConflictModal. Do NOT treat a summary line as success here.
        if code == Some(6) {
            return Err(AppError::new(
                "state.mtime_conflict",
                "conflict: metadata.json was modified externally during minimap write",
            )
            .with_default_hint());
        }
```

1. `tauri::generate_handler![…]` の 2 箇所 (invoke_handler + test builder、grep `get_metadata_mtime,` で見つかる ~3265 / ~3294) に `start_minimap,` を追加。

- [ ] **Step 4: Run to verify pass**

Run: `cd gui/src-tauri && cargo test minimap_argv`
Expected: PASS。

- [ ] **Step 5: cargo check (whole crate compiles)**

Run: `cd gui/src-tauri && cargo check`
Expected: no errors。

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit -m "feat(#893): start_minimap Tauri command (path-passing + exit6 conflict) (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Rust `detect_minimap_regions` command

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (新 command + `MinimapProposal` struct + handler 登録)
- Test: `gui/src-tauri/src/lib.rs` test module (proposal 行 parse)

**Interfaces:**

- Consumes: `resolve_allaganeye_command` / `TrackedChild` / `track_child` / `PROCESS_TRACKER`。
- Produces: `#[tauri::command] detect_minimap_regions(app, req: DetectMinimapRequest) -> Result<Vec<MinimapProposal>, AppError>`。`req = {metadataPath, excludedIndexes}`。CLI を提案モード (`minimap <path> --json`) で起動、stdout の `{"type":"proposal",…}` 行を集約。exit 4 は成功扱い。`MinimapProposal = {match_index, region: Option<RegionPx>, confidence, scattered}`。

- [ ] **Step 1: Write the failing test (proposal line parse)**

test module に追加。parse を `parse_proposal_line(&str) -> Option<MinimapProposal>` に切り出す:

```rust
#[test]
fn parse_proposal_line_reads_region_fields() {
    let line = r#"{"type":"proposal","match_index":2,"region":{"x":19,"y":22,"w":288,"h":216},"confidence":0.9,"scattered":false}"#;
    let p = parse_proposal_line(line).expect("parsed");
    assert_eq!(p.match_index, 2);
    let r = p.region.expect("region");
    assert_eq!((r.x, r.y, r.w, r.h), (19, 22, 288, 216));
    assert_eq!(p.scattered, false);
}

#[test]
fn parse_proposal_line_null_region() {
    let line = r#"{"type":"proposal","match_index":3,"region":null,"confidence":0.0,"scattered":false}"#;
    let p = parse_proposal_line(line).expect("parsed");
    assert!(p.region.is_none());
}

#[test]
fn parse_proposal_line_ignores_non_proposal() {
    assert!(parse_proposal_line(r#"{"type":"summary","success":1}"#).is_none());
}
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui/src-tauri && cargo test parse_proposal_line`
Expected: FAIL (未定義)。

- [ ] **Step 3: Add structs + parser + command**

```rust
#[derive(serde::Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct RegionPx { pub x: i64, pub y: i64, pub w: i64, pub h: i64 }

#[derive(serde::Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct MinimapProposal {
    pub match_index: u32,
    pub region: Option<RegionPx>,
    pub confidence: f64,
    pub scattered: bool,
}

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DetectMinimapRequest {
    pub metadata_path: String,
    #[serde(default)]
    pub excluded_indexes: Vec<u32>,
}

fn parse_proposal_line(line: &str) -> Option<MinimapProposal> {
    let v: serde_json::Value = serde_json::from_str(line).ok()?;
    if v.get("type")?.as_str()? != "proposal" {
        return None;
    }
    let region = match v.get("region") {
        Some(r) if r.is_object() => Some(RegionPx {
            x: r.get("x")?.as_i64()?,
            y: r.get("y")?.as_i64()?,
            w: r.get("w")?.as_i64()?,
            h: r.get("h")?.as_i64()?,
        }),
        _ => None,
    };
    Some(MinimapProposal {
        match_index: v.get("match_index")?.as_u64()? as u32,
        region,
        confidence: v.get("confidence").and_then(|c| c.as_f64()).unwrap_or(0.0),
        scattered: v.get("scattered").and_then(|s| s.as_bool()).unwrap_or(false),
    })
}
```

command 本体は `start_detect` (path 渡し + PROCESS_TRACKER + stdout drain) を mirror し、proposal 行を集約:

- cmd 引数 `["minimap", &req.metadata_path, "--json"]` + `--exclude` (excluded_indexes 非空時)。
- exit code は **4 を成功扱い** (`code == Some(4) || code == Some(0)` を OK、それ以外を AppError)。
- stdout を行ごとに `parse_proposal_line` に通し `Vec<MinimapProposal>` に push。
- PROCESS_TRACKER 登録で `kill_tracked_processes` / unmount kill 可能。

`generate_handler!` 2 箇所に `detect_minimap_regions,` 追加。

- [ ] **Step 4: Run to verify pass**

Run: `cd gui/src-tauri && cargo test parse_proposal_line`
Expected: PASS。

- [ ] **Step 5: cargo check**

Run: `cd gui/src-tauri && cargo check`
Expected: no errors。

- [ ] **Step 6: Commit**

```bash
git add gui/src-tauri/src/lib.rs
git commit -m "feat(#893): detect_minimap_regions Tauri command (proposal aggregation) (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: metadataStore `reloadFromDisk()`

**Files:**

- Modify: `gui/src/state/metadataStore.ts` (新 action + interface)
- Test: `gui/src/state/metadataStore.test.ts`

**Interfaces:**

- Consumes: 既存 Tauri `get_metadata_mtime` / `load_metadata` invoke、既存 `load()` の mtime 記録パターン。
- Produces: `reloadFromDisk(): Promise<void>` — filePath があれば mtime 再取得 → metadata 再読込 → `metadata` / `loadedMtimeMs` 更新 / `conflictErrorState`・`dirty` reset。冪等。

- [ ] **Step 1: Write the failing test**

`gui/src/state/metadataStore.test.ts` に追加 (既存の invoke mock パターンに合わせる):

```typescript
it('reloadFromDisk refreshes metadata + mtime and clears conflict', async () => {
  const fresh = { ...baseMetadata, minimap_regions: [{ match_index: 1, region: { x: 0.01, y: 0.02, w: 0.15, h: 0.2, confidence: 1, source: 'manual' } }] };
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'get_metadata_mtime') return Promise.resolve(999);
    if (cmd === 'load_metadata') return Promise.resolve(fresh);
    return Promise.resolve(null);
  });
  useMetadataStore.setState({ filePath: 'C:/x/metadata.json', loadedMtimeMs: 1, conflictErrorState: { code: 'x', message: 'y' } as any });

  await useMetadataStore.getState().reloadFromDisk();

  const s = useMetadataStore.getState();
  expect(s.metadata?.minimap_regions?.[0].match_index).toBe(1);
  expect(s.loadedMtimeMs).toBe(999);
  expect(s.conflictErrorState).toBeNull();
});

it('reloadFromDisk is a no-op without filePath (sample mode)', async () => {
  useMetadataStore.setState({ filePath: null });
  await expect(useMetadataStore.getState().reloadFromDisk()).resolves.toBeUndefined();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/state/metadataStore.test.ts -t reloadFromDisk`
Expected: FAIL (`reloadFromDisk` 未定義)。

- [ ] **Step 3: Add `reloadFromDisk` to the store interface + impl**

`gui/src/state/metadataStore.ts`:

1. store の型 interface に追加 (他の action 宣言の近く):

```typescript
  /** #893: re-read metadata.json from disk (mtime + minimap_regions) after a
   *  minimap crop subprocess wrote to it. Idempotent; no-op in sample mode. */
  reloadFromDisk: () => Promise<void>;
```

1. store 実装に追加 (既存 `load` の直後):

```typescript
  reloadFromDisk: async () => {
    const path = get().filePath;
    if (!path) return; // sample mode: no disk to reload
    // #834 order: read mtime BEFORE contents so a concurrent writer between
    // the two calls leaves the stored mtime <= content's (conservative).
    const mtime = await invoke<number | null>('get_metadata_mtime', { path });
    const fresh = await invoke<Metadata>('load_metadata', { path });
    const parsed = MetadataSchema.parse(fresh);
    set({
      metadata: parsed,
      loadedMtimeMs: mtime ?? null,
      conflictErrorState: null,
      dirty: false,
    });
  },
```

(既存 `load()` が `MetadataSchema.parse` を使っていれば同じ import を再利用。使っていなければ `load()` と同じ検証経路に合わせる。)

- [ ] **Step 4: Run to verify pass**

Run: `cd gui && npx vitest run src/state/metadataStore.test.ts -t reloadFromDisk`
Expected: PASS。

- [ ] **Step 5: typecheck**

Run: `cd gui && npm run typecheck`
Expected: no errors (vitest は型検査しない教訓、controller が別途回す)。

- [ ] **Step 6: Commit**

```bash
git add gui/src/state/metadataStore.ts gui/src/state/metadataStore.test.ts
git commit -m "feat(#893): metadataStore.reloadFromDisk for post-minimap refresh (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Phase 1 完了ゲート (PR 1 作成前)

- [ ] `pytest tests/test_minimap_command.py tests/test_export_schema.py -v` 全 PASS
- [ ] `ruff check . && ruff format --check . && pyright`
- [ ] `cd gui/src-tauri && cargo check && cargo test`
- [ ] `cd gui && npm run typecheck && npx vitest run src/state/metadataStore.test.ts`
- [ ] Iron Law 6 Pre-flight (Step 0 重複 PR check → base 同期 → Step 5 Codex adversarial-review)
- [ ] PR 1 本文に「Phase 2 (UI) は後続 PR」「exit 6 / CAS / minimap-progress の契約」を明記

---

## Phase 2 — MinimapScreen UI + navigation + docs — PR 2

Phase 1 の CLI/Rust/store backbone に乗せる視覚層。

### Task 7: `'minimap'` screen + CompleteScreen 入口

**Files:**

- Modify: `gui/src/state/appStateStore.ts` (`AppScreen` union に `'minimap'`)
- Modify: `gui/src/screens/CompleteScreen.tsx` (アクションバーに「⬦ ミニマップ切抜き」ボタン)
- Modify: `gui/src/App.tsx` (or screen switch 箇所) で `'minimap'` → `<MinimapScreen/>` を分岐 (MinimapScreen は Task 8 で作成する仮の空 export をここで用意)
- Test: `gui/src/screens/CompleteScreen.test.tsx`

**Interfaces:**

- Consumes: `useAppStateStore().navigate`。
- Produces: `AppScreen` に `'minimap'`。CompleteScreen に minimap ボタン (matches 0 件時 disable)。

- [ ] **Step 1: Write the failing test**

`gui/src/screens/CompleteScreen.test.tsx` に追加:

```typescript
it('navigates to minimap screen on ミニマップ切抜き click', async () => {
  renderComplete(); // 既存 helper で metadata 込み render
  const btn = screen.getByRole('button', { name: 'ミニマップ切抜き' });
  fireEvent.click(btn);
  expect(useAppStateStore.getState().screen).toBe('minimap');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/screens/CompleteScreen.test.tsx -t minimap`
Expected: FAIL (ボタン無し)。

- [ ] **Step 3: Add union member + button + switch**

1. `gui/src/state/appStateStore.ts`:

```typescript
export type AppScreen =
  | 'drop'
  | 'detecting'
  | 'complete'
  | 'preview'
  | 'export'
  | 'minimap';
```

1. `gui/src/screens/CompleteScreen.tsx` のアクションバー、`⬦ 全試合書き出し` ボタンの直後に:

```tsx
          <button
            type="button"
            className={styles.exportAllButton}
            onClick={() => navigate('minimap')}
            disabled={metadata.matches.length === 0}
            aria-label="ミニマップ切抜き"
          >
            ⬦ ミニマップ切抜き
          </button>
```

1. 画面 switch (grep `'export'` で `App.tsx` or StateSwitcher の分岐箇所) に:

```tsx
        {screen === 'minimap' && <MinimapScreen />}
```

import 追加: `import { MinimapScreen } from './screens/MinimapScreen';`。Task 8 まで空 stub を `gui/src/screens/MinimapScreen.tsx` に置く: `export function MinimapScreen() { return <div data-testid="minimap-screen" />; }`。

- [ ] **Step 4: Run to verify pass**

Run: `cd gui && npx vitest run src/screens/CompleteScreen.test.tsx -t minimap`
Expected: PASS。

- [ ] **Step 5: typecheck**

Run: `cd gui && npm run typecheck`
Expected: no errors。

- [ ] **Step 6: Commit**

```bash
git add gui/src/state/appStateStore.ts gui/src/screens/CompleteScreen.tsx gui/src/App.tsx gui/src/screens/MinimapScreen.tsx
git commit -m "feat(#893): minimap screen route + CompleteScreen entry (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: MinimapScreen — video pane + scrubber

**Files:**

- Modify: `gui/src/screens/MinimapScreen.tsx` (stub → video pane)
- Create: `gui/src/screens/MinimapScreen.module.css`
- Test: `gui/src/screens/MinimapScreen.test.tsx`

**Interfaces:**

- Consumes: `register_video` invoke (PreviewScreen line ~271 と同型) / `useMetadataStore` / `useAppStateStore`。代表 match = 最初の `!post_match && type_override !== 'skip'` match、seek 先 = その中点。
- Produces: `<video data-testid="minimap-video">` + match セレクタ (`selectedFrameMatchIndex` local state)。

- [ ] **Step 1: Write the failing test**

```typescript
it('renders a video pane seeking the first eligible match', async () => {
  mockInvoke.mockImplementation((cmd: string) =>
    cmd === 'register_video' ? Promise.resolve({ url: 'http://127.0.0.1/v', token: 't' }) : Promise.resolve(null),
  );
  renderMinimap(); // helper: metadata with 2 matches, filePath set
  expect(await screen.findByTestId('minimap-video')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx -t video`
Expected: FAIL (stub に video 無し)。

- [ ] **Step 3: Implement video pane**

`gui/src/screens/MinimapScreen.tsx` — PreviewScreen の `register_video` useEffect (line 266-293) と `videoSource` (line 263-264) を移植。単一 `<video>` を表示し、代表 match の中点へ seek。match セレクタ (`<select>`) で `selectedFrameMatchIndex` を切替え、その match の中点へ seek。CSS は ExportScreen/PreviewScreen の tokens を流用。

```tsx
export function MinimapScreen() {
  const metadata = useMetadataStore((s) => s.metadata);
  const filePath = useMetadataStore((s) => s.filePath);
  const navigate = useAppStateStore((s) => s.navigate);
  const selectedVideoPath = useAppStateStore((s) => s.selectedVideoPath);
  const videoSource = selectedVideoPath ?? metadata?.source ?? null;
  const isSample = filePath === null && metadata !== null;

  const eligible = (metadata?.matches ?? []).filter(
    (m) => !m.post_match && m.type_override !== 'skip',
  );
  const [frameMatchIndex, setFrameMatchIndex] = useState<number | null>(
    eligible[0]?.index ?? null,
  );
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!videoSource) return;
    let cancelled = false;
    (async () => {
      try {
        const reg = await invoke<{ url: string; token: string }>('register_video', { path: videoSource });
        if (!cancelled) setVideoUrl(reg.url);
      } catch { if (!cancelled) setVideoUrl(null); }
    })();
    return () => { cancelled = true; };
  }, [videoSource]);

  // seek to the selected match midpoint whenever it changes
  useEffect(() => {
    const v = videoRef.current;
    const m = eligible.find((x) => x.index === frameMatchIndex);
    if (v && m) {
      const mid = ((m.edited?.start_time ?? m.start_time) + (m.edited?.end_time ?? m.end_time)) / 2;
      try { v.currentTime = mid; } catch { /* ignore */ }
    }
  }, [frameMatchIndex, videoUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className={styles.screen} data-testid="minimap-screen">
      <SampleModeBanner />
      <button type="button" onClick={() => navigate('complete')}>◀ 一覧へ</button>
      <div className={styles.videoPane}>
        {videoUrl ? (
          <video ref={videoRef} src={videoUrl} data-testid="minimap-video" preload="metadata" playsInline />
        ) : (<div>loading video…</div>)}
      </div>
      <select
        aria-label="frame match"
        value={frameMatchIndex ?? ''}
        onChange={(e) => setFrameMatchIndex(Number(e.target.value))}
      >
        {eligible.map((m) => (
          <option key={m.index} value={m.index}>
            match {String(m.index).padStart(3, '0')}
          </option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx -t video`
Expected: PASS。

- [ ] **Step 5: typecheck + commit**

```bash
cd gui && npm run typecheck
git add gui/src/screens/MinimapScreen.tsx gui/src/screens/MinimapScreen.module.css gui/src/screens/MinimapScreen.test.tsx
git commit -m "feat(#893): MinimapScreen video pane + match scrubber (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: MinimapScreen — drag-select overlay + 数値 region + validation

**Files:**

- Modify: `gui/src/screens/MinimapScreen.tsx` / `.module.css`
- Create: `gui/src/utils/region.ts` (座標変換 + validation の純関数)
- Test: `gui/src/utils/region.test.ts` / `gui/src/screens/MinimapScreen.test.tsx`

**Interfaces:**

- Produces: `gui/src/utils/region.ts`:
  - `elementRectToSourcePx(sel, displayRect, videoW, videoH): {x,y,w,h}` — letterbox (object-fit: contain) 補正込みで element 選択矩形を source pixel に変換。
  - `validateRegionPx(r, frameW, frameH): string | null` — CLI `_parse_region` と同じ境界 (負値 / w,h<16 / はみ出し)、error 文字列 or null。
  - `RegionPx = {x:number,y:number,w:number,h:number}`。

- [ ] **Step 1: Write the failing util tests (letterbox + validation)**

`gui/src/utils/region.test.ts`:

```typescript
import { elementRectToSourcePx, validateRegionPx } from './region';

it('maps element rect to source px with horizontal letterbox', () => {
  // 1920x1080 video shown in a 1000x480 box -> contain scale = 480/1080? no:
  // fitScale = min(1000/1920, 480/1080) = min(0.5208, 0.4444) = 0.4444
  // displayed video = 1920*0.4444=853.3 x 480, letterbox x-bar = (1000-853.3)/2=73.3
  const src = elementRectToSourcePx(
    { x: 73.3 + 0, y: 0, w: 853.3, h: 480 }, // full displayed video
    { width: 1000, height: 480 },
    1920, 1080,
  );
  expect(src.x).toBe(0);
  expect(src.y).toBe(0);
  expect(src.w).toBe(1920);
  expect(src.h).toBe(1080);
});

it('rejects width below 16', () => {
  expect(validateRegionPx({ x: 0, y: 0, w: 8, h: 100 }, 1920, 1080)).toMatch(/16/);
});

it('rejects out-of-frame', () => {
  expect(validateRegionPx({ x: 1900, y: 0, w: 100, h: 100 }, 1920, 1080)).toMatch(/frame|超|exceed/i);
});

it('accepts a valid region', () => {
  expect(validateRegionPx({ x: 10, y: 20, w: 300, h: 400 }, 1920, 1080)).toBeNull();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/utils/region.test.ts`
Expected: FAIL (`region.ts` 未作成)。

- [ ] **Step 3: Implement `region.ts`**

```typescript
export interface RegionPx { x: number; y: number; w: number; h: number }

/** element 座標系の選択矩形 sel を、object-fit:contain の letterbox を補正して
 *  source pixel に変換する。displayRect = video 要素の表示ボックス。 */
export function elementRectToSourcePx(
  sel: { x: number; y: number; w: number; h: number },
  displayRect: { width: number; height: number },
  videoW: number,
  videoH: number,
): RegionPx {
  const fitScale = Math.min(displayRect.width / videoW, displayRect.height / videoH);
  const shownW = videoW * fitScale;
  const shownH = videoH * fitScale;
  const barX = (displayRect.width - shownW) / 2;
  const barY = (displayRect.height - shownH) / 2;
  const toSrcX = (ex: number) => (ex - barX) / fitScale;
  const toSrcY = (ey: number) => (ey - barY) / fitScale;
  const x = Math.round(toSrcX(sel.x));
  const y = Math.round(toSrcY(sel.y));
  const w = Math.round(sel.w / fitScale);
  const h = Math.round(sel.h / fitScale);
  return {
    x: Math.max(0, Math.min(x, videoW)),
    y: Math.max(0, Math.min(y, videoH)),
    w: Math.max(0, Math.min(w, videoW)),
    h: Math.max(0, Math.min(h, videoH)),
  };
}

/** CLI `_parse_region` と同じ境界を検証。error message (日本語) or null。 */
export function validateRegionPx(r: RegionPx, frameW: number, frameH: number): string | null {
  if ([r.x, r.y, r.w, r.h].some((n) => !Number.isFinite(n) || n < 0)) {
    return '座標は 0 以上で指定してください';
  }
  if (r.w < 16) return '幅 (W) は 16px 以上にしてください';
  if (r.h < 16) return '高さ (H) は 16px 以上にしてください';
  if (r.x + r.w > frameW) return `X+W (${r.x + r.w}) がフレーム幅 (${frameW}) を超えています`;
  if (r.y + r.h > frameH) return `Y+H (${r.y + r.h}) がフレーム高さ (${frameH}) を超えています`;
  return null;
}
```

- [ ] **Step 4: Run util tests to verify pass**

Run: `cd gui && npx vitest run src/utils/region.test.ts`
Expected: PASS。

- [ ] **Step 5: Wire drag overlay + numeric input into MinimapScreen**

`MinimapScreen.tsx` に:

- `region` local state (`RegionPx | null`) + `regionError` (validateRegionPx の結果)。
- video 上に絶対配置した `div` overlay (`onMouseDown`/`onMouseMove`/`onMouseUp` で element 座標の矩形を作る)。`elementRectToSourcePx(sel, video.getBoundingClientRect(), video.videoWidth, video.videoHeight)` で `region` を更新。
- 数値入力 4 つ (`X,Y,W,H`, `aria-label` 付き, `type="number"`) で `region` と双方向同期。onChange で `setRegion` + `validateRegionPx`。
- `frameW/frameH` は `videoRef.current.videoWidth/Height`、fallback `metadata.source_resolution` (あれば) or 表示後に確定。

drag overlay の onMouseUp 例:

```tsx
  const onOverlayMouseUp = () => {
    const v = videoRef.current;
    if (!v || !dragStart || !dragCur) return;
    const rect = v.getBoundingClientRect();
    const sel = {
      x: Math.min(dragStart.x, dragCur.x) - rect.left,
      y: Math.min(dragStart.y, dragCur.y) - rect.top,
      w: Math.abs(dragCur.x - dragStart.x),
      h: Math.abs(dragCur.y - dragStart.y),
    };
    const px = elementRectToSourcePx(sel, { width: rect.width, height: rect.height }, v.videoWidth, v.videoHeight);
    setRegion(px);
    setRegionError(validateRegionPx(px, v.videoWidth, v.videoHeight));
    setDragStart(null); setDragCur(null);
  };
```

- [ ] **Step 6: Add MinimapScreen test for numeric sync + validation**

```typescript
it('shows a validation error for width below 16', () => {
  renderMinimap();
  fireEvent.change(screen.getByLabelText('region width'), { target: { value: '8' } });
  expect(screen.getByText(/16px 以上/)).toBeInTheDocument();
});
```

- [ ] **Step 7: Run to verify pass + typecheck**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx src/utils/region.test.ts && npm run typecheck`
Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add gui/src/screens/MinimapScreen.tsx gui/src/screens/MinimapScreen.module.css gui/src/utils/region.ts gui/src/utils/region.test.ts gui/src/screens/MinimapScreen.test.tsx
git commit -m "feat(#893): drag-select overlay + numeric region + letterbox transform (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: MinimapScreen — 自動検出ボタン (proposal) + pre-fill + cancel

**Files:**

- Modify: `gui/src/screens/MinimapScreen.tsx`
- Test: `gui/src/screens/MinimapScreen.test.tsx`

**Interfaces:**

- Consumes: `detect_minimap_regions` invoke → `MinimapProposal[]` (Task 5)。`kill_tracked_processes` invoke (cancel)。
- Produces: 「自動検出を試す」ボタン。成功 proposal を矩形に pre-fill (現在表示 match の proposal 優先、無ければ最高 confidence)。全 null → notice。loading 中は「中止」ボタン。

- [ ] **Step 1: Write the failing test**

```typescript
it('pre-fills region from the highest-confidence proposal', async () => {
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
    if (cmd === 'detect_minimap_regions')
      return Promise.resolve([
        { matchIndex: 1, region: { x: 10, y: 20, w: 300, h: 400 }, confidence: 0.9, scattered: false },
      ]);
    return Promise.resolve(null);
  });
  renderMinimap();
  fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
  expect(await screen.findByDisplayValue('300')).toBeInTheDocument(); // W input pre-filled
});

it('shows a notice when no proposal is produced', async () => {
  mockInvoke.mockImplementation((cmd: string) =>
    cmd === 'detect_minimap_regions'
      ? Promise.resolve([{ matchIndex: 1, region: null, confidence: 0, scattered: false }])
      : Promise.resolve(cmd === 'register_video' ? { url: 'u', token: 't' } : null),
  );
  renderMinimap();
  fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
  expect(await screen.findByText(/自動検出できません/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx -t 自動検出`
Expected: FAIL。

- [ ] **Step 3: Implement auto-detect**

```tsx
  const [detecting, setDetecting] = useState(false);
  const [detectNotice, setDetectNotice] = useState<string | null>(null);

  async function handleAutoDetect() {
    if (!filePath) return;
    setDetecting(true);
    setDetectNotice(null);
    try {
      const proposals = await invoke<Array<{
        matchIndex: number;
        region: RegionPx | null;
        confidence: number;
        scattered: boolean;
      }>>('detect_minimap_regions', {
        req: { metadataPath: filePath, excludedIndexes: Array.from(excluded) },
      });
      const withRegion = proposals.filter((p) => p.region !== null);
      const current = withRegion.find((p) => p.matchIndex === frameMatchIndex);
      const best = current ?? withRegion.sort((a, b) => b.confidence - a.confidence)[0];
      if (best?.region) {
        setRegion(best.region);
        const v = videoRef.current;
        setRegionError(v ? validateRegionPx(best.region, v.videoWidth, v.videoHeight) : null);
        if (best.scattered) setDetectNotice('警告: 試合中に領域が揺れています。手動で微調整してください。');
      } else {
        setDetectNotice('自動検出できませんでした。動画を見ながら手動で範囲を指定してください。');
      }
    } catch {
      setDetectNotice('自動検出に失敗しました。手動で範囲を指定してください。');
    } finally {
      setDetecting(false);
    }
  }

  function handleCancelDetect() {
    void invoke('kill_tracked_processes').catch(() => undefined);
  }
```

JSX: ボタン `自動検出を試す` (disabled = detecting || isSample)、detecting 中は `中止` ボタン + 「自動検出中…」表示、`detectNotice` を inline に表示。

- [ ] **Step 4: Run to verify pass + typecheck**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx -t 自動検出 && npm run typecheck`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/MinimapScreen.tsx gui/src/screens/MinimapScreen.test.tsx
git commit -m "feat(#893): auto-detect proposal pre-fill + cancel (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: MinimapScreen — 設定 + crop 実行 + 進捗 + dirty guard + reload + ConflictModal + jest-axe

**Files:**

- Modify: `gui/src/screens/MinimapScreen.tsx` / `.module.css`
- Create: `gui/src/screens/reducers/minimap.ts` (export reducer と同型 phase reducer)
- Test: `gui/src/screens/MinimapScreen.test.tsx`

**Interfaces:**

- Consumes: `start_minimap` invoke (Task 4) / `minimap-progress` event / `metadataStore.reloadFromDisk` (Task 6) / 既存 `ConflictModal` component / `open_folder_in_explorer` / `open({directory})` dialog。
- Produces: 出力先 / 命名 / include checkbox / 実行ボタン (dirty & region invalid & 対象0件で disable) / progressBox + per-match list / 完了後 reload / conflict → ConflictModal。

- [ ] **Step 1: Write the failing tests (execute → reload; dirty guard; conflict)**

```typescript
it('runs crop, then reloads metadata on success', async () => {
  const reload = vi.fn().mockResolvedValue(undefined);
  useMetadataStore.setState({ reloadFromDisk: reload, dirty: false, filePath: 'C:/x/metadata.json', loadedMtimeMs: 42 } as any);
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
    if (cmd === 'start_minimap') return Promise.resolve({ success: 1, failure: 0, skipped: 0, cancelled: false });
    return Promise.resolve(null);
  });
  renderMinimap();
  fireEvent.change(screen.getByLabelText('region width'), { target: { value: '300' } });
  // fill valid x,y,h too via helper...
  fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
  await waitFor(() => expect(reload).toHaveBeenCalled());
});

it('reloads even when start_minimap rejects after spawn', async () => {
  const reload = vi.fn().mockResolvedValue(undefined);
  useMetadataStore.setState({ reloadFromDisk: reload, dirty: false, filePath: 'C:/x/metadata.json' } as any);
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
    if (cmd === 'start_minimap') return Promise.reject({ code: 'subprocess.parse_failed', message: 'x' });
    return Promise.resolve(null);
  });
  renderMinimap();
  // ... fill valid region, click 切抜き開始
  await waitFor(() => expect(reload).toHaveBeenCalled());
});

it('surfaces ConflictModal on state.mtime_conflict', async () => {
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
    if (cmd === 'start_minimap') return Promise.reject({ code: 'state.mtime_conflict', message: 'conflict' });
    return Promise.resolve(null);
  });
  renderMinimap();
  // ... fill valid region, click 切抜き開始
  expect(await screen.findByTestId('conflict-modal')).toBeInTheDocument();
});

it('has no a11y violations (jest-axe)', async () => {
  const { container } = renderMinimap();
  expect(await axe(container)).toHaveNoViolations();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx -t 'crop|reload|Conflict|a11y'`
Expected: FAIL。

- [ ] **Step 3: Create the phase reducer**

`gui/src/screens/reducers/minimap.ts` — `gui/src/screens/reducers/export.ts` と同型:

```typescript
export type MinimapPhase = 'idle' | 'running' | 'completed' | 'error' | 'cancelling';
export type MinimapAction =
  | { type: 'START_CLICKED' }
  | { type: 'PROGRESS_COMPLETE' }
  | { type: 'EXPORT_ERROR' }
  | { type: 'CANCEL_CLICKED' }
  | { type: 'CANCEL_CONFIRMED' }
  | { type: 'RESTART' };

export function minimapReducer(state: MinimapPhase, action: MinimapAction): MinimapPhase {
  switch (action.type) {
    case 'START_CLICKED': return 'running';
    case 'PROGRESS_COMPLETE': return 'completed';
    case 'EXPORT_ERROR': return 'error';
    case 'CANCEL_CLICKED': return 'cancelling';
    case 'CANCEL_CONFIRMED': return 'idle';
    case 'RESTART': return 'idle';
    default: return state;
  }
}
```

- [ ] **Step 4: Implement settings + execution + progress + guard + reload**

`MinimapScreen.tsx` — ExportScreen (`start_export` invoke + `export-progress` listener + progressBox + per-match list + include checkbox、line 260-435 / 850-1058) を **`minimap-progress` / `start_minimap` に読み替えて移植**。追加 delta:

- **出力先** default = `<metadata dir>/minimap` (metadata.json の親 + `/minimap`)。参照ボタン (`open({directory})` + `stripExtendedPathPrefix`)。
- **命名規則** default `{idx:03}_{type}_{start}_minimap.mp4`。
- **include checkbox** = ExportScreen と同一 (post_match 強制除外)。`excluded` set。
- **実行ボタン disable** = `isSample || running || !region || regionError !== null || 対象0件`。
- **dirty guard**: onClick 先頭で `if (useMetadataStore.getState().dirty) { setDetectNotice('未保存の変更があります。先にプレビューで [適用] するか破棄してください。'); return; }`。
- **crop 実行**:

```tsx
  async function handleStartCrop(overwrite = false) {
    if (useMetadataStore.getState().dirty) {
      setDetectNotice('未保存の変更があります。先にプレビューで適用/破棄してください。');
      return;
    }
    if (!filePath || !region || regionError) return;
    dispatch({ type: 'START_CLICKED' });
    const regionStr = `${region.x},${region.y},${region.w},${region.h}`;
    try {
      const summary = await invoke<{ success: number; failure: number; skipped: number; cancelled: boolean }>(
        'start_minimap',
        {
          // #893 R2 (Codex HIGH): overwrite is an EXPLICIT intent flag. Normal
          // path = overwrite:false + real mtime (guarded). Post-ConflictModal
          // overwrite = handleStartCrop(true) -> overwrite:true + omit mtime.
          // start_minimap fail-closed rejects overwrite:false + missing mtime.
          req: {
            metadataPath: filePath,
            region: regionStr,
            outputDir: outDir,
            namePattern,
            excludedIndexes: Array.from(excluded),
            expectedMtimeMs: overwrite
              ? undefined
              : (useMetadataStore.getState().loadedMtimeMs ?? undefined),
            overwrite,
          },
        },
      );
      if (summary.cancelled) dispatch({ type: 'CANCEL_CONFIRMED' });
      else if (summary.success === 0 && summary.failure > 0) dispatch({ type: 'EXPORT_ERROR' });
      else dispatch({ type: 'PROGRESS_COMPLETE' });
    } catch (e) {
      if (isAppError(e) && e.code === 'state.mtime_conflict') {
        setShowConflict(true); // render existing ConflictModal
      } else {
        dispatch({ type: 'EXPORT_ERROR' });
      }
    } finally {
      // #893 Codex high: reload on EVERY terminal outcome (resolve OR reject)
      // once the subprocess was spawned, since write-back precedes encode.
      await useMetadataStore.getState().reloadFromDisk();
    }
  }
```

- **`minimap-progress` listener** = ExportScreen の `export-progress` listener (line 263-344) を event 名だけ変えて移植 (post_match 迷子 guard 含む)。
- **ConflictModal**: `showConflict` 時に既存 `<ConflictModal>` を render。overwrite 選択時は **`handleStartCrop(true)`** で再実行 (`overwrite: true` を渡し CAS guard を明示 bypass、`expectedMtimeMs` は自動で omit。#893 R2 で mtime 不在=overwrite の弱い信号を廃し明示 flag 化)、reload 選択で閉じるだけ (finally が既に reload 済)。

- [ ] **Step 5: Run to verify pass + typecheck**

Run: `cd gui && npx vitest run src/screens/MinimapScreen.test.tsx && npm run typecheck`
Expected: PASS (jest-axe 含む)。

- [ ] **Step 6: Commit**

```bash
git add gui/src/screens/MinimapScreen.tsx gui/src/screens/MinimapScreen.module.css gui/src/screens/reducers/minimap.ts gui/src/screens/MinimapScreen.test.tsx
git commit -m "feat(#893): minimap crop execution + progress + dirty guard + reload + conflict (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Docs (#818 SSoT gate)

**Files:**

- Modify: `docs/cli-spec.md` / `docs/output-spec.md` / `docs/ui-interaction-spec.md` / `docs/superpowers/specs/2026-06-29-v030-l3-roadmap.md` / `CLAUDE.md`
- Conditionally: `docs/system-architecture.md` / `docs/ui-architecture.md` / `docs/a11y-policy.md` / `docs/gui-development.md` / `docs/design/README.md` / `docs/l2-e2e-checklist.md`

**Interfaces:** N/A (doc only)。

- [ ] **Step 1: cli-spec / output-spec**

`docs/cli-spec.md`: `minimap` 節に `--json` (GUI subprocess mode、metadata は positional path) + `--expected-mtime <ms>` (CAS guard、conflict は exit 6) を追記。`docs/output-spec.md`: minimap の `--json` 出力行 (`result`/`error`/`fallback`/`summary`/`proposal`) + exit 6 を追記。**exit code 6 (write-back conflict) を Exit Codes 表に新設**: `CLAUDE.md` §Exit Codes と `docs/cli-spec.md` の該当表の両方へ「6 | metadata write-back の CAS 衝突 (外部変更検知、GUI が ConflictModal 表示)」を追加。

- [ ] **Step 2: ui-interaction-spec**

`docs/ui-interaction-spec.md` に MinimapScreen § 追加: 操作 (drag-select / 数値入力 / 自動検出 / 実行 / 中断) → 状態遷移 (minimapReducer) / store mutation (reloadFromDisk) / 例外処理 (region invalid / dirty guard / mtime conflict → ConflictModal)。

- [ ] **Step 3: roadmap SSoT + CLAUDE.md**

roadmap に「minimap crop GUI 統合 (#893)」を v0.3.0 scope として追記 (受け入れ条件 5)。`CLAUDE.md` の `gui/src/screens/` 記述に `MinimapScreen` を追加、minimap の GUI 完結を反映、コマンド例に必要なら注記。

- [ ] **Step 4: 条件付き doc は実確認して追記/据え置き**

`grep -n 'ExportScreen\|画面一覧\|screens' docs/{system-architecture,ui-architecture,a11y-policy,gui-development}.md docs/design/README.md docs/l2-e2e-checklist.md` で該当箇所を確認。画面列挙があれば minimap 追記、無ければ PR 本文に「変更不要の根拠」を明記。a11y-policy には drag 代替 = 数値入力 keyboard scope を 1 行追記。

- [ ] **Step 5: markdownlint**

Run: `bash scripts/check-markdownlint.sh`
Expected: PASS (違反あれば `--fix` + 手修正)。

- [ ] **Step 6: Commit**

```bash
git add docs/ CLAUDE.md
git commit -m "doc(#893): minimap GUI 統合 の cli/output/ui/roadmap/CLAUDE 反映 (Refs #893)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Phase 2 完了ゲート (PR 2 作成前)

- [ ] `cd gui && npm run lint && npm run typecheck && npm test && npm run build`
- [ ] `cd gui/src-tauri && cargo check && cargo test`
- [ ] `bash scripts/check-markdownlint.sh`
- [ ] **Tauri 実機検証** (Iron Law 6): AskUserQuestion で Idios に依頼。video 表示 → drag/自動検出 → crop → 進捗 → 完了 → minimap_regions 反映 (mtime conflict が出ないこと) + GPU encode/fallback。cache seed 方式 (`project_gui_verification_cache_seed`)、検証 metadata = `E:\royalstraightflesh\videos\20260116\..._allaganeye\`。
- [ ] Iron Law 6 Pre-flight (Step 0 重複 → base 同期 → Step 5 Codex adversarial-review)。focus = CAS/reload 経路 / released path 非回帰 / encoding。
- [ ] PR 2 merge 後、`/close-issue 893` で受け入れ条件 5 項目を base で実測再検証してから close。

---

### Self-Review (plan 執筆後)

- **Spec coverage**: AC1 (spec 承認) = 前段完了 / AC2 (overlay+crop+進捗完結) = Task 8-11 / AC3 (minimap_regions 反映 + #514 整合) = Task 2 (CAS) + Task 6 (reload) + Task 11 (finally reload + ConflictModal) / AC4 (checks + 実機) = 各完了ゲート / AC5 (roadmap SSoT) = Task 12。spec §全 → task マップ済。
- **Placeholder scan**: 各 code step に実コードを記載。条件付き doc (Task 12 Step 4) は grep 手順を明示。
- **Type consistency**: `RegionPx` (region.ts / Rust) / `MinimapProposal` (Rust serialize camelCase → TS `matchIndex`) / `start_minimap` req field 名 (camelCase serde) / `minimap-progress` payload = ExportProgressPayload 同形 を全 task で一貫。exit 6 / `state.mtime_conflict` を Task 2/4/11 で一貫使用。
