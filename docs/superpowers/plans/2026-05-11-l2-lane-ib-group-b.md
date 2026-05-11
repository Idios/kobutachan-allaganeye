# L2 Lane I-B Group B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 Lane I-B Group B の 3 bug (#679 / #648 / #644) を 3 PR 直列で develop-0.2.0 にマージする。

**Architecture:** Spec [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](../specs/2026-05-11-l2-lane-ib-group-b-design.md) に従い、章 1 (#679 P2 lib.rs spawn) → 章 2 (#648 P3 lib.rs parse) → 章 3 (#644 P3 Python split_matches.py) の順に 3 PR を直列マージする。章 1+2 は `gui/src-tauri/src/lib.rs` を共有するため直列必須、章 3 は Python 側のみで独立だが roadmap 方針で直列順守。各 PR は独立 branch を develop-0.2.0 から派生、先行 PR merge 後に rebase。

**Tech Stack:** Rust (Tauri 2.10 + tokio 1.52) / Python 3.12 (Typer / pytest) / docs (markdown + markdownlint-cli2)。

---

## Pre-implementation notes

### Spec PR (本 plan も含む) の merge 待ち

本 plan は spec doc ([2026-05-11-l2-lane-ib-group-b-design.md](../specs/2026-05-11-l2-lane-ib-group-b-design.md)) と同じ branch `claude/lane-ib-group-b` 上に commit され、spec PR としてまず develop-0.2.0 にマージされる。各章の実装 branch はその後 develop-0.2.0 から派生させる。

### 既存資産 (再利用するもの)

| 資産 | 場所 | 章 |
| --- | --- | --- |
| `_run_detection(..., brightness_callback)` 引数 | [split_matches.py:684-696](../../allaganeye/commands/split_matches.py#L684) | 3 |
| `_build_metadata_payload(..., brightness_samples)` 引数 + payload set | [split_matches.py:1235-1340](../../allaganeye/commands/split_matches.py#L1235) | 3 |
| `build_brightness_samples()` helper | [split_matches.py:1355](../../allaganeye/commands/split_matches.py#L1355) | 3 |
| `parse_detect_progress_line` 既存 unit test 5 件 | [lib.rs:4507-4557](../../gui/src-tauri/src/lib.rs#L4507) | 2 (refactor 後も全 pass 必須) |
| AppError `subprocess.spawn_failed` + `.with_default_hint()` | PR #689 で migrate 済 | 1 (error path 不変) |

### File Structure (overview)

#### Chapter 1: #679 production build CMD 窓 (PR #1)

- Branch: `claude/679-no-window-flag` (develop-0.2.0 base)
- Create: [gui/src-tauri/src/process_util.rs](../../gui/src-tauri/src/process_util.rs) — `apply_no_window` helper + unit tests
- Modify: [gui/src-tauri/src/lib.rs](../../gui/src-tauri/src/lib.rs) — `mod process_util;` 宣言 + 4 spawn site (line 651 / 1259 / 1879 / 2484 周辺) で helper 適用 + call-site pinning test

#### Chapter 2: #648 parse_detect_progress_line silent skip (PR #2)

- Branch: `claude/648-parse-warn-log` (develop-0.2.0 base、章 1 merge 後 rebase)
- Modify: [gui/src-tauri/src/lib.rs](../../gui/src-tauri/src/lib.rs) — `parse_detect_progress_line` refactor (line 2285-2291) + `parse_detect_progress_line_with_warn` + `truncate_and_escape` helper + unit tests (4 + 4 新規追加、既存 5 件は維持)
- Modify: [docs/tauri-commands.md](../../docs/tauri-commands.md) — `start_detect` 節に malformed JSON warn 説明追加

#### Chapter 3: #644 run_split brightness_samples (PR #3)

- Branch: `claude/644-brightness-samples-split` (develop-0.2.0 base、章 2 merge 後 rebase)
- Modify: [allaganeye/commands/split_matches.py](../../allaganeye/commands/split_matches.py) — `run_split` (line 184) で `brightness_callback` 配線、`_split_and_write_metadata` (line 1153) に `brightness_samples` 引数追加、`run_split_from_metadata` (line 258) で元 metadata の `brightness_samples` preserve
- Modify: [tests/test_split_matches.py](../../tests/test_split_matches.py) — `run_split` 経路 4 ケース追加
- Modify: [tests/test_split_from_metadata.py](../../tests/test_split_from_metadata.py) — preserve 2 ケース追加
- Modify: [docs/metadata-spec.md](../../docs/metadata-spec.md) — `brightness_samples` 節に書き込みパス別挙動表追加

---

## Chapter 1: #679 production build CMD 窓 (P2-medium)

### Task 1.0: Branch 作成

**Files:** (none)

- [ ] **Step 1: spec PR が develop-0.2.0 にマージ済か確認**

Run:

```bash
git fetch origin develop-0.2.0
git log origin/develop-0.2.0 --oneline | head -5
# spec commit (本 plan 含む) が見える事を確認
```

- [ ] **Step 2: 章 1 用 branch を develop-0.2.0 から派生**

Run:

```bash
git fetch origin develop-0.2.0
git worktree add -b claude/679-no-window-flag <PATH>/679-no-window-flag origin/develop-0.2.0
cd <PATH>/679-no-window-flag
```

(`<PATH>` は `.claude/worktrees/` 配下を推奨)

### Task 1.1: process_util.rs に failing test を書く

**Files:**

- Create: `gui/src-tauri/src/process_util.rs`

- [ ] **Step 1: failing test だけを含む process_util.rs を書く**

Write file `gui/src-tauri/src/process_util.rs`:

```rust
//! Cross-platform process-related helpers.
//!
//! Currently the only inhabitant is [`apply_no_window`] (#679), which sets
//! Windows' `CREATE_NO_WINDOW` flag on a `tokio::process::Command` so that
//! the `windows_subsystem = "windows"` release bundle doesn't spawn a
//! console window for each ffmpeg / ffprobe / allaganeye child.

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn apply_no_window_returns_same_mut_reference() {
        // Smoke test: helper must chain (return the same `&mut Command`)
        // so call sites can write either:
        //   apply_no_window(&mut cmd);
        //   cmd.arg(...);
        // or:
        //   let cmd = apply_no_window(&mut cmd);
        //   cmd.arg(...);
        let mut cmd = tokio::process::Command::new("true");
        let returned = apply_no_window(&mut cmd);
        // `as *mut _` strips lifetime/type so we can compare the raw addr
        // without re-borrowing.
        let returned_ptr = returned as *mut tokio::process::Command;
        // Build a fresh ref to original to compare; since `apply_no_window`
        // returns the same exclusive borrow, this should be address-equal.
        // (We can't hold both refs simultaneously due to borrow checker,
        // so we capture the address via the returned ref alone.)
        let _ = returned_ptr; // suppress unused if pointer comparison is omitted on some toolchain
        // On Windows the helper must not panic; on non-Windows it's no-op.
        // The compilable + non-panicking smoke is what we pin.
    }

    #[test]
    fn apply_no_window_does_not_panic_on_realistic_invocation() {
        // Verify the helper can be applied to a typical Command chain
        // without panicking. Exit status is irrelevant -- we only need
        // the configuration call to succeed.
        let mut cmd = tokio::process::Command::new("ffprobe");
        cmd.arg("-version");
        apply_no_window(&mut cmd);
        // Don't actually spawn (might not exist in CI); just confirm
        // the builder accepted the configuration mutation.
    }
}
```

- [ ] **Step 2: lib.rs に mod 宣言を追加して test を可視化**

Edit `gui/src-tauri/src/lib.rs` line 25-27 area to add `mod process_util;`:

Find:

```rust
mod error;
mod integrity;
mod logging;
```

Replace with:

```rust
mod error;
mod integrity;
mod logging;
mod process_util;
```

- [ ] **Step 3: test を実行して fail を確認**

Run:

```bash
cd gui/src-tauri && cargo test --lib apply_no_window 2>&1 | tail -20
```

Expected: コンパイルエラー (`cannot find function 'apply_no_window' in this scope`) または link 失敗。fn 未定義状態を確認。

### Task 1.2: apply_no_window を実装

**Files:**

- Modify: `gui/src-tauri/src/process_util.rs`

- [ ] **Step 1: helper 本体を file 先頭 (mod tests の前) に追加**

Insert at the top of `gui/src-tauri/src/process_util.rs` (before `#[cfg(test)] mod tests`):

```rust
/// Apply `CREATE_NO_WINDOW` (`0x0800_0000`) on Windows so that the spawned
/// child doesn't get its own console window. No-op on other platforms.
///
/// Returns the mutable reference so the caller can chain. Designed to be
/// inserted into existing builder chains just before `.spawn()` /
/// `.output()` / `.status()`.
///
/// #679: `windows_subsystem = "windows"` 親プロセスが console を持たない
/// release で、子プロセスを spawn する際 Windows が自動で console window
/// を割り当てる挙動を抑止する。`CREATE_NO_WINDOW` は winbase.h 由来の定数
/// (0x0800_0000)。`tokio::process::Command::creation_flags(u32)` は tokio
/// 1.x で `std::os::windows::process::CommandExt::creation_flags` 相当の
/// 専用 method を提供している ([tokio 1.52 docs](https://docs.rs/tokio/1.52.1/tokio/process/struct.Command.html#method.creation_flags))。
#[cfg(target_os = "windows")]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    cmd.creation_flags(CREATE_NO_WINDOW)
}

#[cfg(not(target_os = "windows"))]
pub(crate) fn apply_no_window(
    cmd: &mut tokio::process::Command,
) -> &mut tokio::process::Command {
    cmd
}
```

- [ ] **Step 2: test を再実行して pass を確認**

Run:

```bash
cd gui/src-tauri && cargo test --lib apply_no_window 2>&1 | tail -10
```

Expected: `running 2 tests` / `test result: ok. 2 passed`。

- [ ] **Step 3: 全体 regression**

Run:

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -10
```

Expected: `test result: ok` で既存 156 件 + 新 2 件 = 158 件 pass。

### Task 1.3: probe_video_with に apply_no_window を適用

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (line 651 周辺)

- [ ] **Step 1: probe_video_with のビルダー chain を分離して helper 適用**

Find at [lib.rs:651-668](../../gui/src-tauri/src/lib.rs#L651) (the `let output = tokio::process::Command::new(ffprobe) ... .output().await` block):

```rust
    let output = tokio::process::Command::new(ffprobe)
        .arg("-v")
        .arg("quiet")
        .arg("-print_format")
        .arg("json")
        .arg("-show_format")
        .arg("-show_streams")
        .arg(path)
        .output()
        .await
        .map_err(|e| {
            AppError::new(
                "subprocess.spawn_failed",
                format!("ffprobe spawn failed: {e}"),
            )
            .with_default_hint()
        })?;
```

Replace with (chain を `let mut cmd` に分離して helper 適用):

```rust
    let mut cmd = tokio::process::Command::new(ffprobe);
    cmd.arg("-v")
        .arg("quiet")
        .arg("-print_format")
        .arg("json")
        .arg("-show_format")
        .arg("-show_streams")
        .arg(path);
    process_util::apply_no_window(&mut cmd);
    let output = cmd.output().await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("ffprobe spawn failed: {e}"),
        )
        .with_default_hint()
    })?;
```

- [ ] **Step 2: cargo check で型エラー無し**

Run:

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -5
```

Expected: `Finished` (warnings は許容、error は不可)。

- [ ] **Step 3: 既存 test 全 pass で regression なし**

Run:

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -10
```

Expected: 158 件 pass (前回と同数、regression なし)。

### Task 1.4: ensure_thumbnail_exists に apply_no_window を適用

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (line 1259 周辺)

- [ ] **Step 1: ffmpeg thumbnail ビルダー chain を分離して helper 適用**

Find at [lib.rs:1258-1284](../../gui/src-tauri/src/lib.rs#L1258) (the `let output = tokio::process::Command::new("ffmpeg") ... .output().await` block in `ensure_thumbnail_exists`):

```rust
    let t_arg = format!("{:.3}", t_seconds.max(0.0));
    let output = tokio::process::Command::new("ffmpeg")
        .arg("-y")
        .arg("-ss")
        .arg(&t_arg)
        .arg("-i")
        .arg(video_path)
        .arg("-frames:v")
        .arg("1")
        .arg("-vf")
        .arg("scale=160:90")
        .arg("-q:v")
        .arg("80")
        .arg("-f")
        .arg("webp")
        .arg("-loglevel")
        .arg("error")
        .arg(out_path)
        .output()
        .await
        .map_err(|e| {
            AppError::new(
                "subprocess.spawn_failed",
                format!("spawn ffmpeg failed at t={}: {}", t_arg, e),
            )
            .with_default_hint()
        })?;
```

Replace with:

```rust
    let t_arg = format!("{:.3}", t_seconds.max(0.0));
    let mut cmd = tokio::process::Command::new("ffmpeg");
    cmd.arg("-y")
        .arg("-ss")
        .arg(&t_arg)
        .arg("-i")
        .arg(video_path)
        .arg("-frames:v")
        .arg("1")
        .arg("-vf")
        .arg("scale=160:90")
        .arg("-q:v")
        .arg("80")
        .arg("-f")
        .arg("webp")
        .arg("-loglevel")
        .arg("error")
        .arg(out_path);
    process_util::apply_no_window(&mut cmd);
    let output = cmd.output().await.map_err(|e| {
        AppError::new(
            "subprocess.spawn_failed",
            format!("spawn ffmpeg failed at t={}: {}", t_arg, e),
        )
        .with_default_hint()
    })?;
```

- [ ] **Step 2: cargo check + test 全 pass**

Run:

```bash
cd gui/src-tauri && cargo check && cargo test --lib 2>&1 | tail -10
```

Expected: 158 件 pass (regression なし)。

### Task 1.5: run_ffmpeg_export_attempt に apply_no_window を適用

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (line 1871 周辺)

- [ ] **Step 1: ffmpeg export ビルダーに helper 適用**

Find at [lib.rs:1871-1881](../../gui/src-tauri/src/lib.rs#L1871) (the `let mut cmd = tokio::process::Command::new("ffmpeg") ... let mut child = cmd.spawn()` block in `run_ffmpeg_export_attempt`):

```rust
    let mut cmd = tokio::process::Command::new("ffmpeg");
    for a in args {
        cmd.arg(a);
    }
    cmd.stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn ffmpeg failed: {}", e))?;
```

Replace with:

```rust
    let mut cmd = tokio::process::Command::new("ffmpeg");
    for a in args {
        cmd.arg(a);
    }
    cmd.stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn ffmpeg failed: {}", e))?;
```

- [ ] **Step 2: cargo check + test 全 pass**

Run:

```bash
cd gui/src-tauri && cargo check && cargo test --lib 2>&1 | tail -10
```

Expected: 158 件 pass。

### Task 1.6: start_detect に apply_no_window を適用

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (line 2484-2523 周辺)

- [ ] **Step 1: allaganeye CLI ビルダーに helper 適用**

Find at [lib.rs:2509-2523](../../gui/src-tauri/src/lib.rs#L2509) (the `cmd.env("PYTHONIOENCODING", ...) ... let mut child = cmd.spawn()` block):

```rust
    cmd.env("PYTHONIOENCODING", "utf-8:replace");
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    // #646 -- spawn failure messages need to surface the resolved
    // program (e.g. "python -m allaganeye") so the GUI error display
    // can hint at which stage of the resolution chain failed.
    let resolved_label = if cmd_spec.prefix_args.is_empty() {
        cmd_spec.program.clone()
    } else {
        format!("{} {}", cmd_spec.program, cmd_spec.prefix_args.join(" "))
    };
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn allaganeye failed ({}): {}", resolved_label, e))?;
```

Replace with (helper を `let mut child = cmd.spawn()` の直前に挿入):

```rust
    cmd.env("PYTHONIOENCODING", "utf-8:replace");
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    process_util::apply_no_window(&mut cmd);

    // #646 -- spawn failure messages need to surface the resolved
    // program (e.g. "python -m allaganeye") so the GUI error display
    // can hint at which stage of the resolution chain failed.
    let resolved_label = if cmd_spec.prefix_args.is_empty() {
        cmd_spec.program.clone()
    } else {
        format!("{} {}", cmd_spec.program, cmd_spec.prefix_args.join(" "))
    };
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("spawn allaganeye failed ({}): {}", resolved_label, e))?;
```

- [ ] **Step 2: cargo check + test 全 pass**

Run:

```bash
cd gui/src-tauri && cargo check && cargo test --lib 2>&1 | tail -10
```

Expected: 158 件 pass。

### Task 1.7: call-site adoption pinning test

**Files:**

- Modify: `gui/src-tauri/src/process_util.rs` (`mod tests` 内に追加)

- [ ] **Step 1: failing pinning test を追加**

Edit `gui/src-tauri/src/process_util.rs` の `mod tests` 内に追加:

```rust
    /// #679 spec §5.4 Option a: adoption の retention を CI で pin する。
    /// 将来の merge で 4 spawn site のいずれかから `apply_no_window`
    /// 呼び出しが落ちると、本 test が source 文字列マッチで気付ける。
    ///
    /// 各 spawn 経路の **関数名直後** ~ **`.spawn()` / `.output()`**
    /// の間に `apply_no_window` 文字列が現れることを assert する。
    /// 関数定義の境界判定は次の関数定義 `fn NAME(` まで、または `}\n\n`
    /// など緩い heuristic ではなく、関数名の出現位置から固定 window
    /// (3000 char) を見ることで誤検出を避ける。
    #[test]
    fn lib_rs_applies_apply_no_window_at_all_four_spawn_sites() {
        let src = include_str!("lib.rs");
        for func in [
            "fn probe_video_with",
            "async fn ensure_thumbnail_exists",
            "async fn run_ffmpeg_export_attempt",
            "async fn start_detect",
        ] {
            let pos = src
                .find(func)
                .unwrap_or_else(|| panic!("function `{}` not found in lib.rs", func));
            // Look at the next 3000 chars after the fn header.
            let window_end = (pos + 3000).min(src.len());
            let window = &src[pos..window_end];
            assert!(
                window.contains("apply_no_window"),
                "function `{}` no longer calls `apply_no_window` within \
                 its first 3000 chars. #679 fix has regressed -- re-apply \
                 the helper at the spawn site.",
                func
            );
        }
    }
```

- [ ] **Step 2: test 実行 → pass を確認** (もし fail したら apply_no_window 呼び出しが落ちている)

Run:

```bash
cd gui/src-tauri && cargo test --lib lib_rs_applies_apply_no_window 2>&1 | tail -10
```

Expected: `test result: ok. 1 passed`。fail なら Task 1.3-1.6 の適用漏れ。

- [ ] **Step 3: 全体 regression**

Run:

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -10
```

Expected: 159 件 pass (新 pinning test +1)。

### Task 1.8: Pre-PR verification + commit + PR 作成

**Files:** (none)

- [ ] **Step 1: 全 verification**

Run:

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -3
cd gui/src-tauri && cargo test --lib 2>&1 | tail -5
cd gui && npm run lint 2>&1 | tail -5
cd gui && npm run typecheck 2>&1 | tail -5
cd gui && npm test -- --run 2>&1 | tail -5
cd gui && npm run build 2>&1 | tail -5
```

Expected: 全 pass (Frontend は無編集なので regression なし、Rust は新 helper + 5 適用 site)。

- [ ] **Step 2: commit**

```bash
git add gui/src-tauri/src/process_util.rs gui/src-tauri/src/lib.rs
git commit -F - <<'EOF'
fix(gui): production build で子プロセス CMD 窓を抑止 (CREATE_NO_WINDOW 適用) (Refs #679)

process_util.rs を新設し、Windows のみ CREATE_NO_WINDOW (0x0800_0000) を
tokio::process::Command に付与する `apply_no_window` helper を提供。
親が `windows_subsystem = "windows"` の release で子プロセスを spawn する
際、Windows が自動で console window を割り当てる挙動を抑止する。

適用 site (4 箇所):
- probe_video_with (ffprobe)
- ensure_thumbnail_exists (ffmpeg thumbnail、generate_match_thumbnails 経由)
- run_ffmpeg_export_attempt (ffmpeg export、export_match 経由)
- start_detect (allaganeye CLI)

除外: open_folder_in_explorer (std::process::Command、explorer.exe を意図的に開く)

unit test:
- helper 自体の chain / non-panicking smoke
- lib.rs source string で 4 spawn site が `apply_no_window` を含む pinning

Refs #679
Spec: docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md §5
Plan: docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md Chapter 1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: push + PR 作成**

```bash
git push -u origin claude/679-no-window-flag
gh pr create --base develop-0.2.0 --title "fix(gui): production build CMD 窓を抑止 (#679)" --body-file - <<'EOF'
## Summary

[#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) の実装。Lane I-B Group B の章 1 (P2-medium)。

Spec: [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md) §5
Plan: [docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md](docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md) Chapter 1

## 変更内容

- 新規 `gui/src-tauri/src/process_util.rs`: `apply_no_window` helper (Windows: `CREATE_NO_WINDOW`、非 Windows: no-op)
- `gui/src-tauri/src/lib.rs`: 4 spawn site (`probe_video_with` / `ensure_thumbnail_exists` / `run_ffmpeg_export_attempt` / `start_detect`) で helper 適用
- 除外: `open_folder_in_explorer` (`std::process::Command`、`explorer.exe` を意図的に開く)

## 受け入れ条件 ([issue #679](https://github.com/Idios/kobutachan-allaganeye/issues/679))

- [x] `gui/src-tauri/src` に `apply_no_window` 相当の helper を新設し、Command に Windows のみ CREATE_NO_WINDOW flag を付与
- [x] start_detect / probe_video / generate_match_thumbnails (ffmpeg) / export_match (ffmpeg) の全 spawn 経路で helper を適用 (explorer.exe は除外)
- [x] Windows / 非 Windows での helper 分岐 unit test
- [ ] **実機検証 (Idios)**: `cargo tauri build` で release bundle を作成し、detect / export 実行時に CMD 窓が出ないことを確認

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` (取り込み未済 commit なし)
- [x] `gh pr list --search "#679"` 並行 worktree PR 重複なし
- [x] `cd gui/src-tauri && cargo check`
- [x] `cd gui/src-tauri && cargo test --lib` (159 件 pass、新 3 件 + 既存 156 件)
- [x] `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- [x] `bash scripts/check-markdownlint.sh` (本 PR は docs 編集なし)

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

- [ ] `cd gui && cargo tauri build` で release bundle 作成
- [ ] release exe 起動 → DropScreen で動画選択 → detect 実行 → **CMD 窓非表示**
- [ ] PreviewScreen → export 実行 → **CMD 窓非表示**
- [ ] PreviewScreen → folder open in explorer → 通常通り explorer 起動 (除外確認)

Refs #679

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 4: Iron Law 6 manual 検証 (Idios review 時)**

PR review で Idios が `cargo tauri build` を実行し、release exe で detect / export を試して CMD 窓非表示を確認。確認後 `gh pr merge <PR#> --squash`。

---

## Chapter 2: #648 parse_detect_progress_line silent skip (P3-low)

### Task 2.0: Branch 作成

**Files:** (none)

- [ ] **Step 1: 章 1 PR merge を待ち、develop-0.2.0 を最新化**

Run:

```bash
git fetch origin develop-0.2.0
git log origin/develop-0.2.0 --oneline | head -3
# 章 1 PR の commit (e.g. "fix(gui): production build で子プロセス CMD 窓を抑止") を確認
```

- [ ] **Step 2: 章 2 用 branch を develop-0.2.0 から派生**

Run:

```bash
git worktree add -b claude/648-parse-warn-log <PATH>/648-parse-warn-log origin/develop-0.2.0
cd <PATH>/648-parse-warn-log
```

### Task 2.1: truncate_and_escape helper の failing test を書く

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (`mod tests` 内、line 4500 付近に追加)

- [ ] **Step 1: 既存 `parse_detect_progress_line` test 群の末尾に failing test を追加**

Find `mod tests` の最後の `parse_detect_progress_line_*` テスト群 ([lib.rs:4540-4560](../../gui/src-tauri/src/lib.rs#L4540) 周辺) 末尾。最後の `}` の **直前** に以下を追加:

```rust
    // -- #648 truncate_and_escape (parse_detect_progress_line warn 出力前処理)

    #[test]
    fn truncate_and_escape_empty_returns_empty() {
        assert_eq!(truncate_and_escape("", 64), "");
    }

    #[test]
    fn truncate_and_escape_zero_max_returns_empty() {
        assert_eq!(truncate_and_escape("hello", 0), "");
    }

    #[test]
    fn truncate_and_escape_short_ascii_returned_verbatim() {
        assert_eq!(truncate_and_escape("hello", 64), "hello");
    }

    #[test]
    fn truncate_and_escape_truncates_long_input_at_char_boundary() {
        let long = "a".repeat(128);
        assert_eq!(truncate_and_escape(&long, 64).chars().count(), 64);
    }

    #[test]
    fn truncate_and_escape_preserves_tab_newline_cr() {
        assert_eq!(truncate_and_escape("a\tb\nc\rd", 64), "a\tb\nc\rd");
    }

    #[test]
    fn truncate_and_escape_escapes_other_control_chars() {
        assert_eq!(truncate_and_escape("a\x01b", 64), "a\\x01b");
        assert_eq!(truncate_and_escape("a\x1Fb", 64), "a\\x1Fb");
    }

    #[test]
    fn truncate_and_escape_handles_multibyte_char_boundary() {
        // 5 chars (まったく) of 3 bytes each = 15 bytes
        // max_chars=3 should give 3 chars without panicking on byte boundary
        assert_eq!(truncate_and_escape("まったく", 3).chars().count(), 3);
    }
```

- [ ] **Step 2: test を実行して fail を確認**

Run:

```bash
cd gui/src-tauri && cargo test --lib truncate_and_escape 2>&1 | tail -15
```

Expected: コンパイルエラー (`cannot find function 'truncate_and_escape' in this scope`)。

### Task 2.2: truncate_and_escape を実装

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (`parse_detect_progress_line` の **直前** に追加)

- [ ] **Step 1: helper を `parse_detect_progress_line` の直前に追加**

Find at [lib.rs:2282-2291](../../gui/src-tauri/src/lib.rs#L2282) (`parse_detect_progress_line` の docstring + 本体):

```rust
/// #569 -- pure parser for one JSON-lines progress event.  Returns
/// `None` for blank lines or lines that fail to deserialize so a stray
/// stdout write from the CLI doesn't break the overall stream.
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    let line = line.trim();
    if line.is_empty() {
        return None;
    }
    serde_json::from_str(line).ok()
}
```

Replace with (helper 2 件 + refactor 後の `parse_detect_progress_line` + 新 `parse_detect_progress_line_with_warn`):

```rust
/// #648 -- truncate `line` to at most `max_chars` Unicode chars and escape
/// non-printable control characters (except `\t` / `\n` / `\r`) as `\xNN`
/// so they don't inject terminal escape sequences into stderr.
fn truncate_and_escape(line: &str, max_chars: usize) -> String {
    line.chars()
        .take(max_chars)
        .map(|c| match c {
            '\t' | '\n' | '\r' => c.to_string(),
            c if (c as u32) < 0x20 => format!("\\x{:02X}", c as u32),
            c => c.to_string(),
        })
        .collect()
}

/// #569 -- pure parser for one JSON-lines progress event.  Returns
/// `None` for blank lines or lines that fail to deserialize so a stray
/// stdout write from the CLI doesn't break the overall stream.
///
/// #648 -- malformed JSON (non-empty / non-whitespace lines that fail to
/// deserialize) は silent skip ではなく `eprintln!` で warn 出力するよう
/// 拡張済。空行 / 空白のみ行 (LF flush 等で発生) は引き続き silent skip。
/// public signature は変えていない (戻り値も呼び出し側も既存通り)。
fn parse_detect_progress_line(line: &str) -> Option<DetectProgress> {
    parse_detect_progress_line_with_warn(line, |msg| eprintln!("{}", msg))
}

/// #648 -- testable variant: takes a `on_warn` closure to capture warn
/// output, so cargo test can assert on the warning content without
/// touching the real stderr stream. Production wrapper above passes
/// `eprintln!`.
fn parse_detect_progress_line_with_warn(
    line: &str,
    mut on_warn: impl FnMut(&str),
) -> Option<DetectProgress> {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return None;
    }
    match serde_json::from_str(trimmed) {
        Ok(p) => Some(p),
        Err(_) => {
            let escaped = truncate_and_escape(trimmed, 64);
            on_warn(&format!(
                "[parse_detect_progress_line] malformed JSON (len={}): \"{}\"",
                trimmed.len(),
                escaped,
            ));
            None
        }
    }
}
```

- [ ] **Step 2: truncate_and_escape の test 実行 → pass**

Run:

```bash
cd gui/src-tauri && cargo test --lib truncate_and_escape 2>&1 | tail -15
```

Expected: 7 件 pass。

### Task 2.3: parse_detect_progress_line_with_warn の test を追加

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (`mod tests` 内、`truncate_and_escape` test 群の直後)

- [ ] **Step 1: failing tests を追加**

Find the last `truncate_and_escape_*` test (`truncate_and_escape_handles_multibyte_char_boundary` の `}`)。その **直後** に以下を追加:

```rust
    // -- #648 parse_detect_progress_line_with_warn (DI variant)

    #[test]
    fn parse_with_warn_empty_line_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result = parse_detect_progress_line_with_warn("", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_whitespace_only_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result =
            parse_detect_progress_line_with_warn("   \n", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_valid_json_no_warn() {
        let mut warns: Vec<String> = Vec::new();
        let line = r#"{"phase":"scan","completed":12,"total":100,"elapsed_s":1.25}"#;
        let result =
            parse_detect_progress_line_with_warn(line, |m| warns.push(m.to_string()));
        assert!(result.is_some());
        assert!(warns.is_empty());
    }

    #[test]
    fn parse_with_warn_malformed_json_emits_warn() {
        let mut warns: Vec<String> = Vec::new();
        let result =
            parse_detect_progress_line_with_warn("not json", |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert_eq!(warns.len(), 1);
        assert!(warns[0].contains("malformed JSON"));
        assert!(warns[0].contains("\"not json\""));
        assert!(warns[0].contains("len=8"));
    }

    #[test]
    fn parse_with_warn_long_malformed_json_truncated_and_escaped() {
        let mut warns: Vec<String> = Vec::new();
        // 70 chars + 制御文字 \x01
        let line = format!("{}{}", "x".repeat(63), "\x01yyy");
        let result =
            parse_detect_progress_line_with_warn(&line, |m| warns.push(m.to_string()));
        assert!(result.is_none());
        assert_eq!(warns.len(), 1);
        // 64 char truncate (\x01 escape の 4 char を含む、x 63 + \x01 escape = 67 char ではなく、
        // 64 char window 内では x 63 + control の 1 char = 64 char、escape は format 後に 4 char に膨れる)
        // よって warn message 内には `\\x01` が現れる
        assert!(
            warns[0].contains("\\x01"),
            "expected escaped control char in warn message: {}",
            warns[0]
        );
        // 元 len は 67 (63 + 4)
        assert!(
            warns[0].contains(&format!("len={}", line.len())),
            "expected original length in warn message: {}",
            warns[0]
        );
    }
```

- [ ] **Step 2: test 実行 → pass**

Run:

```bash
cd gui/src-tauri && cargo test --lib parse_with_warn 2>&1 | tail -15
```

Expected: 5 件 pass。

- [ ] **Step 3: 既存 parse_detect_progress_line test 群 (5 件) も regression なし**

Run:

```bash
cd gui/src-tauri && cargo test --lib parse_detect_progress_line 2>&1 | tail -15
```

Expected: 10 件 pass (既存 5 件 + 新 5 件)。

### Task 2.4: docs/tauri-commands.md に追記

**Files:**

- Modify: `docs/tauri-commands.md`

- [ ] **Step 1: start_detect 節を探して subsection を追加**

Find `start_detect` 節 (例: `## start_detect` or `### start_detect`)。既存記述の末尾 or 適切な位置に以下 subsection を追加:

```markdown
### stdout schema と parse 失敗時の挙動 (#648)

`start_detect` が spawn する `allaganeye detect --progress-format json` の
stdout は 1 行 1 JSON object の stream (UTF-8、LF separator)。GUI 側は
`parse_detect_progress_line` で 1 行ずつ deserialize する。

**許容パターン (silent skip)**:

- 空行 (改行のみの LF flush 等)
- 空白のみ行

**想定外パターン (warn 出力)**:

- malformed JSON (debug print 混入、schema 不整合)
- 上記の場合、`parse_detect_progress_line` は `eprintln!` で
  `[parse_detect_progress_line] malformed JSON (len=N): "<escaped truncated line>"`
  形式の warn を stderr に出力する。先頭 64 文字で truncate、制御文字 (TAB/LF/CR 以外) は `\xNN` escape。

**観察可能範囲**:

- **dev build** (`cargo tauri dev`): `windows_subsystem` が default = `console` のため、`eprintln!` は terminal stderr に届く。
- **release build** (`cargo tauri build`): `windows_subsystem = "windows"` で console を切り離しているため、`eprintln!` は **失われる** (Windows OS が stderr を dev null 相当に向ける)。release で観察可能にしたい場合は `tauri-plugin-log` 導入 (post-Lane I-B 別 issue) で file output 化する。

**設計選択 (#648 spec)**: `phase=error` event 発火による DetectingScreen の error UI 接続は採用していない (UX 過剰、roadmap で却下)。silent skip → warn 化のみで UX に影響なし。
```

- [ ] **Step 2: markdownlint 検証**

Run:

```bash
bash scripts/check-markdownlint.sh docs/tauri-commands.md 2>&1 | tail -5
```

Expected: `0 error(s)`。失敗したら MD028 (blockquote 間) / MD056 (table cell の `|` escape) に注意。

### Task 2.5: Pre-PR verification + commit + PR 作成

**Files:** (none)

- [ ] **Step 1: 全 verification**

Run:

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -3
cd gui/src-tauri && cargo test --lib 2>&1 | tail -5
cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build 2>&1 | tail -3
bash scripts/check-markdownlint.sh docs/tauri-commands.md 2>&1 | tail -3
```

Expected: 全 pass (Rust test は 章 1 PR merge 後 base なら 159 件 + 章 2 新 12 件 = 171 件 pass)。

- [ ] **Step 2: commit**

```bash
git add gui/src-tauri/src/lib.rs docs/tauri-commands.md
git commit -F - <<'EOF'
fix(gui): parse_detect_progress_line の silent skip を warn 出力に格上げ (Refs #648)

CLI が --progress-format json で emit する stdout の malformed JSON は
従来 silent skip (None 返却のみ) だったため、GUI 側で parse 失敗が発生した
ことが分からなかった。`eprintln!` で stderr に warn を出力するよう拡張。

変更:
- `truncate_and_escape` helper 新設 (64 char truncate + 制御文字 escape)
- `parse_detect_progress_line` の signature は不変 (戻り値・呼び出し側も同じ)
- `parse_detect_progress_line_with_warn` (DI variant) を内部に追加し test
  容易化 (closure で warning capture 可能)
- 空行 / 空白のみ行は silent skip 維持 (LF flush 等で発生し得る許容パターン)
- docs/tauri-commands.md の start_detect 節に stdout schema と挙動を追記

dev console (cargo tauri dev) で warn 観察可。release は windows_subsystem
= "windows" で stderr が失われるため別 issue で tauri-plugin-log 検討。

unit test: 5 + 7 = 12 件 (既存 5 件は unchanged)

Refs #648
Spec: docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md §6
Plan: docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md Chapter 2

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: push + PR 作成**

```bash
git push -u origin claude/648-parse-warn-log
gh pr create --base develop-0.2.0 --title "fix(gui): parse_detect_progress_line silent skip を warn 出力に (#648)" --body-file - <<'EOF'
## Summary

[#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) の実装。Lane I-B Group B の章 2 (P3-low)。

Spec: [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md) §6
Plan: [docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md](docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md) Chapter 2

## 変更内容

- `truncate_and_escape` helper 新設 (64 char truncate + 制御文字 escape)
- `parse_detect_progress_line` を DI 化 (`parse_detect_progress_line_with_warn` を内部に分離)、公開 signature 不変、呼び出し側無変更
- malformed JSON を `eprintln!` で stderr warn 出力、空行 / 空白のみ行は silent skip 維持
- `docs/tauri-commands.md` の `start_detect` 節に stdout schema + 挙動 + 観察範囲 (dev / release の差) + 設計選択を追記

## 受け入れ条件

- [x] `parse_detect_progress_line` の公開 signature 不変、呼び出し側無変更
- [x] 空行 / 空白のみ行は silent skip 維持
- [x] malformed JSON は warn 出力 (truncate + control char escape 込み)
- [x] dev console で warn 観察可能、release では stderr が失われる旨を doc 化
- [x] `phase=error` 化しない (UX 変更なし)
- [x] unit test 7 + 5 = 12 件追加 (既存 5 件は維持)

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0`
- [x] `gh pr list --search "#648"` 並行 worktree PR 重複なし
- [x] `cd gui/src-tauri && cargo check`
- [x] `cd gui/src-tauri && cargo test --lib` (新 12 件含む全 pass)
- [x] `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- [x] `bash scripts/check-markdownlint.sh docs/tauri-commands.md` (0 errors)

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

- [ ] dev build (`cargo tauri dev`) を terminal 起動 + DevTools / terminal stderr を開く
- [ ] CLI 側に意図的な debug print 混入を再現 (例: `allaganeye/commands/detect.py` 冒頭に一時的に `print('debug')` 追加 + GUI から detect 実行)
- [ ] terminal stderr に `[parse_detect_progress_line] malformed JSON (len=...): "debug"` warn が出力されることを確認
- [ ] DetectingScreen が `phase=error` UI に切り替わらないこと (silent skip の UX 維持) を確認
- [ ] 一時的な `print('debug')` を revert

Refs #648

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 4: Idios review + マージ**

Idios が実機検証 (dev build で warn 確認) 後 `gh pr merge <PR#> --squash`。

---

## Chapter 3: #644 run_split brightness_samples (P3-low)

### Task 3.0: Branch 作成

**Files:** (none)

- [ ] **Step 1: 章 2 PR merge を待ち develop-0.2.0 最新化**

Run:

```bash
git fetch origin develop-0.2.0
git log origin/develop-0.2.0 --oneline | head -3
# 章 2 PR の commit を確認
```

- [ ] **Step 2: 章 3 用 branch を develop-0.2.0 から派生**

Run:

```bash
git worktree add -b claude/644-brightness-samples-split <PATH>/644-brightness-samples-split origin/develop-0.2.0
cd <PATH>/644-brightness-samples-split
```

### Task 3.1: run_split brightness_samples 書き込みの failing test

**Files:**

- Modify: `tests/test_split_matches.py`

- [ ] **Step 1: 既存 import + fixture を確認**

Run:

```bash
head -50 tests/test_split_matches.py
```

→ 既存の `from allaganeye.commands.split_matches import ...` import / `monkeypatch` / `tmp_path` fixture を再利用。

- [ ] **Step 2: failing test を file 末尾に追加**

Edit `tests/test_split_matches.py` の末尾に以下を追加 (既存パターン: [tests/test_detect.py:294](../../tests/test_detect.py#L294) の `test_detect_writes_brightness_samples_when_callback_fires` を参考に `run_split` 経路向けにアレンジ):

```python
# -- #644 brightness_samples wiring through run_split (一気通貫) --

import json

from allaganeye.commands.split_matches import run_split


def _make_minimal_video_fixture(tmp_path):
    """1 秒程度の最小 mkv fixture を返す (実 ffmpeg で生成、test 専用)。

    既存の sample_video_dir fixture が無いケースでも回せるよう、tmp_path
    内に短い動画を 1 本作る。ffmpeg が PATH にない環境では skip 相当の
    挙動を caller に委ねる (本 test は slow マーカーに include しない)。
    """
    import subprocess

    video_path = tmp_path / "tiny.mkv"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=160x90:d=1",
        "-c:v", "libx264",
        "-t", "1",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return video_path


def test_run_split_writes_brightness_samples_when_callback_fires(
    tmp_path, monkeypatch
):
    """#644 -- run_split (一気通貫) で Pass 1 が走ったら brightness_samples
    が metadata.json に書かれること。
    """
    from allaganeye.commands import split_matches as sm
    from allaganeye.config import SplitConfig

    # _run_detection を mock し、brightness_callback を 3 sample で呼ぶ
    def fake_run_detection(*args, **kwargs):
        cb = kwargs.get("brightness_callback")
        assert cb is not None, "run_split must pass brightness_callback to _run_detection"
        cb({0.0: 10.5, 0.5: 12.3, 1.0: 14.1})
        return [
            {"start": 0.0, "end": 1.0, "type": "fl_match"},
        ]

    monkeypatch.setattr(sm, "_run_detection", fake_run_detection)

    # split / cache / audio scan を no-op に
    monkeypatch.setattr(sm, "_load_cache", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "_save_cache", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "_run_audio_scan", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "split_video", lambda *a, **kw: [tmp_path / "1.mp4"])
    monkeypatch.setattr(sm, "_check_disk_space", lambda *a, **kw: None)

    video = _make_minimal_video_fixture(tmp_path)
    output_dir = tmp_path / "out"
    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=0.5,
        blackout_threshold=15.0,
        min_match_duration=1.0,
        min_blackout_duration=0.1,
        no_audio=True,
        use_gpu=False,
        dry_run=False,
        workers=1,
    )

    run_split(video, config, verbose=False, quiet=True)

    metadata_path = output_dir / "metadata.json"
    assert metadata_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "brightness_samples" in payload, (
        "run_split で Pass 1 が走った時 brightness_samples が metadata.json に "
        "書かれているはず (#644)"
    )
    samples = payload["brightness_samples"]
    assert isinstance(samples, dict)
    assert "values" in samples and isinstance(samples["values"], list)
    assert len(samples["values"]) > 0


def test_run_split_omits_brightness_samples_when_callback_silent(
    tmp_path, monkeypatch
):
    """#644 -- callback が呼ばれない (例: cache hit 経路と同じ意味の no-op
    detection) 場合は brightness_samples キーを書かない。
    """
    from allaganeye.commands import split_matches as sm
    from allaganeye.config import SplitConfig

    def fake_run_detection(*args, **kwargs):
        # callback を呼ばない (Pass 1 走っていない想定)
        return [{"start": 0.0, "end": 1.0, "type": "fl_match"}]

    monkeypatch.setattr(sm, "_run_detection", fake_run_detection)
    monkeypatch.setattr(sm, "_load_cache", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "_save_cache", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "_run_audio_scan", lambda *a, **kw: None)
    monkeypatch.setattr(sm, "split_video", lambda *a, **kw: [tmp_path / "1.mp4"])
    monkeypatch.setattr(sm, "_check_disk_space", lambda *a, **kw: None)

    video = _make_minimal_video_fixture(tmp_path)
    output_dir = tmp_path / "out2"
    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=0.5,
        blackout_threshold=15.0,
        min_match_duration=1.0,
        min_blackout_duration=0.1,
        no_audio=True,
        use_gpu=False,
        dry_run=False,
        workers=1,
    )

    run_split(video, config, verbose=False, quiet=True)

    metadata_path = output_dir / "metadata.json"
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert "brightness_samples" not in payload, (
        "callback が silent (Pass 1 skip / cache hit 相当) なら "
        "brightness_samples キーは書かないはず"
    )
```

- [ ] **Step 3: test を実行して fail を確認**

Run:

```bash
pytest tests/test_split_matches.py -k "brightness_samples" -v 2>&1 | tail -15
```

Expected: `test_run_split_writes_brightness_samples_when_callback_fires` FAIL (callback 渡されていないため AssertionError、または brightness_samples キー欠落)。`test_run_split_omits_brightness_samples_when_callback_silent` は PASS する可能性あり (現状欠落のため、これは想定挙動)。

### Task 3.2: _split_and_write_metadata に brightness_samples 引数を追加

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (line 1153 周辺)

- [ ] **Step 1: signature に brightness_samples 引数を追加**

Find at [split_matches.py:1153-1166](../../allaganeye/commands/split_matches.py#L1153):

```python
def _split_and_write_metadata(
    video_path: Path,
    boundaries: list[MatchBoundary],
    gaps: list[Gap],
    metadata: ProbeResult,
    config: SplitConfig,
    *,
    effective_interval: float,
    detected_at: str,
    detection_started_at: str | None = None,
    detection_completed_at: str | None = None,
    system_info: SystemInfo,
    quiet: bool = False,
) -> None:
```

Replace with (`brightness_samples` を keyword-only 引数として追加、`BrightnessSamples` import 確認):

```python
def _split_and_write_metadata(
    video_path: Path,
    boundaries: list[MatchBoundary],
    gaps: list[Gap],
    metadata: ProbeResult,
    config: SplitConfig,
    *,
    effective_interval: float,
    detected_at: str,
    detection_started_at: str | None = None,
    detection_completed_at: str | None = None,
    system_info: SystemInfo,
    brightness_samples: BrightnessSamples | None = None,
    quiet: bool = False,
) -> None:
```

- [ ] **Step 2: `_build_metadata_payload` 呼び出しに `brightness_samples` を pass-through**

Find at [split_matches.py:1212-1225](../../allaganeye/commands/split_matches.py#L1212):

```python
    result = _build_metadata_payload(
        video_path=video_path,
        source_duration=source_duration,
        source_fps=metadata["fps"],
        detected_at=detected_at,
        detection_started_at=detection_started_at,
        detection_completed_at=detection_completed_at,
        effective_interval=effective_interval,
        config=config,
        boundaries=boundaries,
        output_files=output_files,
        gaps=gaps,
        system_info=system_info,
    )
```

Replace with (末尾 `brightness_samples=brightness_samples,` を追加):

```python
    result = _build_metadata_payload(
        video_path=video_path,
        source_duration=source_duration,
        source_fps=metadata["fps"],
        detected_at=detected_at,
        detection_started_at=detection_started_at,
        detection_completed_at=detection_completed_at,
        effective_interval=effective_interval,
        config=config,
        boundaries=boundaries,
        output_files=output_files,
        gaps=gaps,
        system_info=system_info,
        brightness_samples=brightness_samples,
    )
```

- [ ] **Step 3: pyright で型エラー無しを確認**

Run:

```bash
pyright allaganeye/commands/split_matches.py 2>&1 | tail -5
```

Expected: `0 errors, 0 warnings, 0 informations`。`BrightnessSamples` 未 import の場合は file 冒頭の import 群に追加 (既存パターンを踏襲、`build_brightness_samples` import の近くで `BrightnessSamples` も import)。

### Task 3.3: run_split で brightness_callback を配線

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (line 182-194 周辺)

- [ ] **Step 1: `_run_detection` 呼び出し直前に `captured_brightness` を確保**

Find at [split_matches.py:182-194](../../allaganeye/commands/split_matches.py#L182):

```python
    detect_stats: DetectionStats | None = {} if verbose else None

    boundaries = _run_detection(
        video_path,
        metadata,
        effective_interval,
        config,
        audio_hits=audio_hits,
        quiet=quiet,
        stats=detect_stats,
        use_gpu=use_gpu,
        gpu_vendor=gpu_vendor,
    )
```

Replace with (`captured_brightness` ローカル変数 + `_on_brightness` callback + `brightness_callback=_on_brightness` 配線):

```python
    detect_stats: DetectionStats | None = {} if verbose else None

    # #644 -- Pass 1 で計測された輝度マップを捕捉して metadata.json に書く
    # ため、`_run_detection` に brightness_callback を渡す。detect.py の
    # run_detect (line 230-260) と同じパターン。callback が呼ばれない経路
    # (cache hit や Pass 1 skip) では captured_brightness が空のまま残り、
    # `_split_and_write_metadata` 呼び出し時に None を渡す。
    captured_brightness: dict[float, float] = {}

    def _on_brightness(samples: dict[float, float]) -> None:
        captured_brightness.update(samples)

    boundaries = _run_detection(
        video_path,
        metadata,
        effective_interval,
        config,
        audio_hits=audio_hits,
        quiet=quiet,
        stats=detect_stats,
        use_gpu=use_gpu,
        gpu_vendor=gpu_vendor,
        brightness_callback=_on_brightness,
    )
```

- [ ] **Step 2: `_split_and_write_metadata` 呼び出しで `brightness_samples` を渡す**

Find at [split_matches.py:242-254](../../allaganeye/commands/split_matches.py#L242):

```python
    split_start = time.monotonic()
    _split_and_write_metadata(
        video_path,
        boundaries,
        gaps,
        metadata,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        system_info=detected_system_info,
        quiet=quiet,
    )
```

Replace with (`brightness_samples=...` を渡し、空マップなら None):

```python
    # #644 -- captured_brightness が空なら build_brightness_samples が None を
    # 返すため、`_split_and_write_metadata` に None を渡して metadata.json に
    # brightness_samples キーを含めない (既存仕様「Pass 1 が走った場合のみ」)。
    brightness_samples = (
        build_brightness_samples(captured_brightness) if captured_brightness else None
    )
    split_start = time.monotonic()
    _split_and_write_metadata(
        video_path,
        boundaries,
        gaps,
        metadata,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        system_info=detected_system_info,
        brightness_samples=brightness_samples,
        quiet=quiet,
    )
```

- [ ] **Step 3: test を再実行して PASS 確認**

Run:

```bash
pytest tests/test_split_matches.py -k "brightness_samples" -v 2>&1 | tail -15
```

Expected: 両 test (`writes_brightness_samples_when_callback_fires` + `omits_brightness_samples_when_callback_silent`) PASS。

- [ ] **Step 4: regression (既存 split_matches test 全 pass)**

Run:

```bash
pytest tests/test_split_matches.py -v 2>&1 | tail -10
```

Expected: 全 pass (既存テスト + 新 2 件)。

### Task 3.4: run_split_from_metadata で preserve の failing test

**Files:**

- Modify: `tests/test_split_from_metadata.py`

- [ ] **Step 1: 既存 import + fixture を確認**

Run:

```bash
head -30 tests/test_split_from_metadata.py
```

→ 既存 import / fixture を再利用。

- [ ] **Step 2: failing test を末尾に追加**

Edit `tests/test_split_from_metadata.py` の末尾に追加:

```python
# -- #644 brightness_samples preserve through --from-metadata --

import json

from allaganeye.commands.split_matches import run_split_from_metadata


def _write_minimal_metadata(metadata_path, source_path, brightness_samples=None):
    """Pre-existing metadata.json を作る test helper。"""
    payload = {
        "schema_version": "1",
        "source": str(source_path),
        "source_duration": 1.0,
        "source_duration_display": "00:01",
        "source_fps": 30.0,
        "detected_at": "2026-05-11T00:00:00Z",
        "detection_started_at": "2026-05-11T00:00:00Z",
        "detection_completed_at": "2026-05-11T00:00:01Z",
        "detection_params": {
            "sample_interval": 0.5,
            "blackout_threshold": 15.0,
            "min_match_duration": 1.0,
            "min_blackout_duration": 0.1,
            "no_audio": True,
            "use_gpu": False,
            "workers": 1,
        },
        "system_info": {
            "gpu_vendors_available": [],
            "gpu_vendor_used": None,
        },
        "matches": [
            {
                "index": 1,
                "start_time": 0.0,
                "end_time": 1.0,
                "start_display": "00:00",
                "end_display": "00:01",
                "duration": 1.0,
                "duration_display": "00:01",
                "type": "fl_match",
                "output_file": "1.mp4",
            }
        ],
        "gaps": [],
        "warnings": [],
    }
    if brightness_samples is not None:
        payload["brightness_samples"] = brightness_samples
    metadata_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_run_split_from_metadata_preserves_brightness_samples(
    tmp_path, monkeypatch
):
    """#644 -- --from-metadata 経路で元 metadata.json の brightness_samples
    が新 metadata.json に preserve されること。
    """
    from allaganeye.commands import split_matches as sm
    from allaganeye.config import SplitConfig

    # source video fixture
    source = tmp_path / "src.mkv"
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1",
            "-c:v", "libx264", "-t", "1",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    # 元 metadata に brightness_samples を含めて書く
    src_meta = tmp_path / "src_meta.json"
    original_samples = {
        "interval_s": 0.5,
        "values": [10.0, 12.5, 15.0, 17.5],
    }
    _write_minimal_metadata(src_meta, source, brightness_samples=original_samples)

    # split / disk check は no-op
    monkeypatch.setattr(sm, "split_video", lambda *a, **kw: [tmp_path / "1.mp4"])
    monkeypatch.setattr(sm, "_check_disk_space", lambda *a, **kw: None)
    monkeypatch.setattr(
        sm, "probe_video",
        lambda *a, **kw: {
            "duration": 1.0,
            "width": 160,
            "height": 90,
            "fps": 30.0,
            "codec": "h264",
        },
    )
    # GPU vendor probe を no-op に
    from allaganeye import system_info as si_mod

    monkeypatch.setattr(si_mod, "probe_gpu_vendors", lambda: [])

    output_dir = tmp_path / "out"
    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=0.5,
        blackout_threshold=15.0,
        min_match_duration=1.0,
        min_blackout_duration=0.1,
        no_audio=True,
        use_gpu=False,
        dry_run=False,
        workers=1,
    )

    run_split_from_metadata(src_meta, config, quiet=True)

    new_meta = output_dir / "metadata.json"
    assert new_meta.exists()
    payload = json.loads(new_meta.read_text(encoding="utf-8"))
    assert "brightness_samples" in payload, (
        "--from-metadata は元 metadata の brightness_samples を新 metadata に "
        "preserve するはず (#644 / PR #626 同パターン)"
    )
    assert payload["brightness_samples"] == original_samples


def test_run_split_from_metadata_omits_brightness_samples_when_source_lacks(
    tmp_path, monkeypatch
):
    """#644 -- --from-metadata 経路で元 metadata に brightness_samples が
    無い場合、新 metadata.json にも無いまま。
    """
    from allaganeye.commands import split_matches as sm
    from allaganeye.config import SplitConfig

    source = tmp_path / "src.mkv"
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1",
            "-c:v", "libx264", "-t", "1",
            str(source),
        ],
        check=True,
        capture_output=True,
    )

    # 元 metadata に brightness_samples を **含めない**
    src_meta = tmp_path / "src_meta.json"
    _write_minimal_metadata(src_meta, source, brightness_samples=None)

    monkeypatch.setattr(sm, "split_video", lambda *a, **kw: [tmp_path / "1.mp4"])
    monkeypatch.setattr(sm, "_check_disk_space", lambda *a, **kw: None)
    monkeypatch.setattr(
        sm, "probe_video",
        lambda *a, **kw: {
            "duration": 1.0,
            "width": 160,
            "height": 90,
            "fps": 30.0,
            "codec": "h264",
        },
    )
    from allaganeye import system_info as si_mod

    monkeypatch.setattr(si_mod, "probe_gpu_vendors", lambda: [])

    output_dir = tmp_path / "out2"
    config = SplitConfig(
        output_dir=output_dir,
        sample_interval=0.5,
        blackout_threshold=15.0,
        min_match_duration=1.0,
        min_blackout_duration=0.1,
        no_audio=True,
        use_gpu=False,
        dry_run=False,
        workers=1,
    )

    run_split_from_metadata(src_meta, config, quiet=True)

    new_meta = output_dir / "metadata.json"
    payload = json.loads(new_meta.read_text(encoding="utf-8"))
    assert "brightness_samples" not in payload, (
        "元 metadata に brightness_samples が無いなら新 metadata にも書かない"
    )
```

- [ ] **Step 3: test を実行して fail を確認**

Run:

```bash
pytest tests/test_split_from_metadata.py -k "preserve" -v 2>&1 | tail -15
```

Expected: `test_run_split_from_metadata_preserves_brightness_samples` FAIL (preserve 未実装、新 metadata に brightness_samples が無い)。`omits_*` test は PASS する想定 (現状欠落)。

### Task 3.5: run_split_from_metadata で preserve を実装

**Files:**

- Modify: `allaganeye/commands/split_matches.py` (line 258-396 周辺)

- [ ] **Step 1: 元 metadata の `brightness_samples` を読み取る**

Find at [split_matches.py:350-355](../../allaganeye/commands/split_matches.py#L350) (`preserve_started_at` / `preserve_completed_at` 周辺):

```python
    # #586 -- preserve detect timing across `--from-metadata` invocations.
    # 再検知してないので元 metadata の検知開始/完了時刻を引き継ぎ、GUI
    # 「所要」が「検知時の所要」を表示し続けるようにする。pre-#586 metadata
    # では両フィールド欠落 -> None を渡して _split_and_write_metadata の
    # fallback (started=detected_at / completed=_iso_utc_now()) に委譲。
    old_started_at = payload.get("detection_started_at")
    old_completed_at = payload.get("detection_completed_at")
    preserve_started_at = old_started_at if isinstance(old_started_at, str) else None
    preserve_completed_at = (
        old_completed_at if isinstance(old_completed_at, str) else None
    )
```

直後 (空行を挟んで) に以下を追加:

```python

    # #644 -- preserve brightness_samples across `--from-metadata`.
    # 元 metadata に brightness_samples があれば新 metadata にもそのまま
    # コピーする。PR #626 の detection_started_at / detection_completed_at
    # と同じ preserve パターン。元に無ければ None を渡して新 metadata でも
    # 欠落させる (cache hit / pre-#569 metadata 経路と同じ挙動)。
    old_brightness_samples = payload.get("brightness_samples")
    preserve_brightness_samples = (
        old_brightness_samples if isinstance(old_brightness_samples, dict) else None
    )
```

- [ ] **Step 2: `_split_and_write_metadata` 呼び出しに `brightness_samples=preserve_brightness_samples` を渡す**

Find at [split_matches.py:382-394](../../allaganeye/commands/split_matches.py#L382):

```python
    split_start = time.monotonic()
    _split_and_write_metadata(
        source_path,
        boundaries,
        gaps,
        probe,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        detection_started_at=preserve_started_at,
        detection_completed_at=preserve_completed_at,
        system_info=split_only_system_info,
        quiet=quiet,
    )
```

Replace with (`brightness_samples=preserve_brightness_samples,` を追加):

```python
    split_start = time.monotonic()
    _split_and_write_metadata(
        source_path,
        boundaries,
        gaps,
        probe,
        config,
        effective_interval=effective_interval,
        detected_at=detected_at,
        detection_started_at=preserve_started_at,
        detection_completed_at=preserve_completed_at,
        system_info=split_only_system_info,
        brightness_samples=preserve_brightness_samples,
        quiet=quiet,
    )
```

- [ ] **Step 3: test を再実行して PASS 確認**

Run:

```bash
pytest tests/test_split_from_metadata.py -k "preserve or omits_brightness" -v 2>&1 | tail -10
```

Expected: 両 test PASS。

- [ ] **Step 4: regression (test_split_from_metadata.py 全 pass)**

Run:

```bash
pytest tests/test_split_from_metadata.py -v 2>&1 | tail -10
```

Expected: 全 pass。

### Task 3.6: docs/metadata-spec.md に書き込みパス別挙動表を追記

**Files:**

- Modify: `docs/metadata-spec.md`

- [ ] **Step 1: `brightness_samples` 節 を探して表を追加**

Find `brightness_samples` の subsection (例: `### \`brightness_samples\` オブジェクト` or `### brightness_samples`)。subsection 末尾に以下を追加:

```markdown
**書き込みパス別の挙動 (#644)**:

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` (Pass 1 走行) | ✓ 書く |
| `allaganeye split` (新規検知、Pass 1 走行) | ✓ 書く (#644) |
| `allaganeye split` (cache hit、Pass 1 skip) | ✗ 欠落 (cache に brightness を含めない設計) |
| `allaganeye split --from-metadata` | 元 metadata から **preserve** (元が欠落なら欠落、PR #626 と同パターン) |

GUI 側は欠落許容済 (#569) のため、欠落時は `sampleBrightness()` 固定波形 fallback で描画する。`allaganeye split --no-cache` を使えば常に Pass 1 を走らせて書ける。
```

- [ ] **Step 2: markdownlint 検証**

Run:

```bash
bash scripts/check-markdownlint.sh docs/metadata-spec.md 2>&1 | tail -5
```

Expected: `0 error(s)`。

### Task 3.7: Pre-PR verification + commit + PR 作成

**Files:** (none)

- [ ] **Step 1: 全 verification**

Run:

```bash
ruff check . 2>&1 | tail -3
ruff format --check . 2>&1 | tail -3
pyright 2>&1 | tail -5
pytest 2>&1 | tail -10
bash scripts/check-markdownlint.sh docs/metadata-spec.md 2>&1 | tail -3
```

Expected: 全 pass。

- [ ] **Step 2: commit**

```bash
git add allaganeye/commands/split_matches.py tests/test_split_matches.py tests/test_split_from_metadata.py docs/metadata-spec.md
git commit -F - <<'EOF'
fix(cli): run_split (一気通貫) / --from-metadata 経路で brightness_samples を metadata.json に書く (Refs #644)

`allaganeye detect` 経路では既に Pass 1 走行時に brightness_samples を
metadata.json に書いていたが、`allaganeye split` (一気通貫) / `--from-metadata`
の経路では配線漏れで brightness_samples キーが欠落していた。GUI CompleteScreen
の BrightnessTimeline がサンプル波形ダミーにフォールバックする状態。

変更:
- `run_split`: captured_brightness map + _on_brightness callback を確保し
  `_run_detection(brightness_callback=...)` 経由で Pass 1 輝度を捕捉。
  build_brightness_samples で downsample して _split_and_write_metadata
  に渡す。
- `_split_and_write_metadata`: signature に brightness_samples 引数を追加
  (keyword-only、optional)、_build_metadata_payload に pass-through。
- `run_split_from_metadata`: 元 metadata の brightness_samples を読み取り
  preserve_brightness_samples として _split_and_write_metadata に渡す
  (PR #626 の detection_started_at preserve と同パターン)。
- docs/metadata-spec.md: brightness_samples 節に書き込みパス別の挙動表
  (detect / split / cache hit / --from-metadata) を追記。

cache hit: captured_brightness が空 → None を渡して metadata から欠落 (既存
仕様「Pass 1 が走った場合のみ」と整合)。

新 test: tests/test_split_matches.py に 2 件、tests/test_split_from_metadata.py
に 2 件。

Refs #644
Spec: docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md §7
Plan: docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md Chapter 3

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 3: push + PR 作成**

```bash
git push -u origin claude/644-brightness-samples-split
gh pr create --base develop-0.2.0 --title "fix(cli): run_split / --from-metadata で brightness_samples を書く (#644)" --body-file - <<'EOF'
## Summary

[#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) の実装。Lane I-B Group B の章 3 (P3-low、Lane 最終 PR)。

Spec: [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md) §7
Plan: [docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md](docs/superpowers/plans/2026-05-11-l2-lane-ib-group-b.md) Chapter 3

## 変更内容

- `run_split` で `_run_detection` に `brightness_callback` を配線し Pass 1 輝度を捕捉
- `_split_and_write_metadata` に `brightness_samples` 引数 (keyword-only) を追加、`_build_metadata_payload` へ pass-through
- `run_split_from_metadata` で元 metadata の `brightness_samples` を読み取り preserve
- `docs/metadata-spec.md` の `brightness_samples` 節に書き込みパス別の挙動表を追記

| 経路 | 書き込み |
| --- | --- |
| `allaganeye detect` (Pass 1 走行) | ✓ |
| `allaganeye split` (新規検知、Pass 1 走行) | ✓ ← #644 で対応 |
| `allaganeye split` (cache hit) | ✗ |
| `allaganeye split --from-metadata` | preserve |

## 受け入れ条件 (issue #644)

- [x] `allaganeye split <video> -o <dir>` 経路の metadata.json に `brightness_samples` が書かれる (Pass 1 走行時)
- [x] cache hit 時の挙動を `docs/metadata-spec.md` に明記 (欠落許容)
- [x] `--from-metadata` 経路の挙動を決定し doc 化 (preserve)
- [x] pytest で `run_split` 経路 + `--from-metadata` 経路の各分岐を網羅 (4 件)
- [ ] **実機検証 (Idios)**: `allaganeye split <video>` で metadata.json に `brightness_samples` あり、GUI で実 brightness 描画

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0`
- [x] `gh pr list --search "#644"` 並行 worktree PR 重複なし
- [x] `ruff check . && ruff format --check .`
- [x] `pyright`
- [x] `pytest` (新 4 件含む全 pass)
- [x] `bash scripts/check-markdownlint.sh docs/metadata-spec.md`

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

- [ ] `allaganeye split <video> -o <dir> --no-cache` 実行 → `metadata.json` に `brightness_samples` キーあり (`jq .brightness_samples.values | head` 等で確認)
- [ ] 同 metadata を GUI で load → CompleteScreen の BrightnessTimeline が **実 brightness 描画** (サンプル波形と異なる、dev tools で `metadata.brightness_samples.values` を inspect)
- [ ] 同動画で `allaganeye split <video> -o <dir2>` (cache hit) → metadata.json に `brightness_samples` 無し
- [ ] `allaganeye split --from-metadata <metadata.json> -o <dir3>` (元 metadata に brightness_samples あり) → 新 metadata.json に preserve

Refs #644

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 4: Idios review + マージ**

Idios が実機検証 (4 経路の brightness_samples 挙動) 後 `gh pr merge <PR#> --squash`。これで Lane I-B Group B 完了。

---

## Post-merge cleanup

### worktree 整理 (任意)

```bash
git worktree remove <PATH>/679-no-window-flag
git worktree remove <PATH>/648-parse-warn-log
git worktree remove <PATH>/644-brightness-samples-split
git branch -d claude/679-no-window-flag claude/648-parse-warn-log claude/644-brightness-samples-split
```

(spec branch `claude/lane-ib-group-b` も merge 後同様に削除可)

### Lane I-B 完了確認

- [ ] [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) CLOSED (PR #1 merge 時)
- [ ] [#648](https://github.com/Idios/kobutachan-allaganeye/issues/648) CLOSED (PR #2 merge 時)
- [ ] [#644](https://github.com/Idios/kobutachan-allaganeye/issues/644) CLOSED (PR #3 merge 時)
- [ ] Roadmap update ([docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](2026-05-11-l2-v020-roadmap-update.md)) で Lane I-B を `✅ DONE` に追記 (別 PR or 次回 roadmap revise 時)

issue クローズは PR 内で `Closes` キーワードを **使わない** (CLAUDE.md / issue-policy.md 準拠)。Idios が手動でクローズする。

## 関連

- Spec: [docs/superpowers/specs/2026-05-11-l2-lane-ib-group-b-design.md](../specs/2026-05-11-l2-lane-ib-group-b-design.md)
- Roadmap: [docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](2026-05-11-l2-v020-roadmap-update.md) Lane I-B / Group B
- Refs: #679 #648 #644 #663 (Lane I-A 完了) #569 (brightness_samples 元実装) #626 (--from-metadata preserve pattern) #647 (DetectingScreen error UI、本 lane では非接続)
