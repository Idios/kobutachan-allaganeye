# L2 Lane VII Group M Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L2 Lane VII Group M ([#727](https://github.com/Idios/kobutachan-allaganeye/issues/727)) gui spawn 統一 — `gui/src-tauri/src/lib.rs:1842-1862` の `open_folder_in_explorer` を `std::process::Command` から `tokio::process::Command` に切り替え、lib.rs 内 6 spawn site を tokio 系で統一する。

**Architecture:** Spec [docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md](../specs/2026-05-13-l2-lane-vii-group-m-design.md) §5 の Approach A (Direct minimal swap) に従い、当該関数を 1 回の Edit で (1) `fn` → `async fn` 化、(2) `std::process::Command` → `tokio::process::Command`、(3) doc comment 3 段落追記 (#727 切替経緯 / `apply_no_window` 非適用 / PROCESS_TRACKER 非登録) を行う。既存 5 spawn site の `process_util::apply_no_window` adoption + PROCESS_TRACKER 設計は不変、frontend 側 `invoke('open_folder_in_explorer')` も Promise 返却で挙動同一のため touch せず。1 spec / 1 章 / single PR (spec doc + impl の 2 commit) で完結。

**Tech Stack:** Rust (Tauri 2.10 + tokio 1.52) / Frontend (Vite + React 19 + TS) / Python 3.12 / docs (markdown + markdownlint-cli2)。

---

## Pre-implementation notes

### 既に done

- **Spec doc 作成 + commit 済**: [docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md](../specs/2026-05-13-l2-lane-vii-group-m-design.md) は branch `claude/fervent-brahmagupta-3f4c94` の commit `308fcda` でステージ済。本 plan も同 branch に追加 commit する。
- **worktree 作成 済**: 現セッションは `.claude/worktrees/fervent-brahmagupta-3f4c94/` で動作中、branch `claude/fervent-brahmagupta-3f4c94`、base `develop-0.2.0`。新規 worktree / branch 作成は不要。
- **brainstorming session 完了**: `fervent-brahmagupta-3f4c94` (2026-05-13、Idios + Claude Opus 4.7) で Q1-Q4 全 design choice 確定。

### 既存資産 (再利用するもの、編集しない)

| 資産 | 場所 | 章 |
| --- | --- | --- |
| `validate_open_folder_request` (path 検証 helper) | [lib.rs:~1808](../../gui/src-tauri/src/lib.rs#L1808) | 1 (不変、既存 3 unit test がそのまま regression 担保) |
| `validate_open_folder_request_*` 3 unit test | [lib.rs:~4752-4775](../../gui/src-tauri/src/lib.rs#L4752) | 1 (不変、pass 維持) |
| `process_util::apply_no_window` helper | [process_util.rs](../../gui/src-tauri/src/process_util.rs) | 1 (不変、open_folder_in_explorer には適用しない、§3.3 で明示) |
| `lib_rs_applies_apply_no_window_at_all_spawn_sites` adoption test | [process_util.rs:80](../../gui/src-tauri/src/process_util.rs#L80) | 1 (5 site のまま、open_folder_in_explorer を 6 番目として追加しない、pass 維持) |
| AppError `subprocess.spawn_failed` + `.with_default_hint()` | PR #689 (Lane I-A) で migrate 済 | 1 (error path 不変、新規 AppError code 追加なし) |
| frontend `invoke('open_folder_in_explorer')` (ErrorModal / ExportScreen) | [ErrorModal.tsx:139](../../gui/src/components/ErrorModal.tsx#L139) / [ExportScreen.tsx:424](../../gui/src/screens/ExportScreen.tsx#L424) | 1 (Promise 返却で挙動同一、touch しない) |
| `ExportScreen.test.tsx` invoke mock | [ExportScreen.test.tsx:482-500](../../gui/src/screens/ExportScreen.test.tsx#L482) | 1 (mock 経由で impl 不可視、不変 pass) |

### File Structure (overview)

**Chapter 1: #727 open_folder_in_explorer tokio 統一 (single PR)**

- Branch: `claude/fervent-brahmagupta-3f4c94` (既存 worktree、develop-0.2.0 base)
- Modify: [gui/src-tauri/src/lib.rs](../../gui/src-tauri/src/lib.rs) — 行 1830-1862 (`open_folder_in_explorer` の doc comment + 関数本体) を 1 回の Edit で書き換え
- 触らない: `gui/src-tauri/src/process_util.rs` / `gui/src-tauri/Cargo.toml` / frontend 全ファイル / Python 全ファイル / docs 全ファイル (spec doc は別 commit で既に追加済)
- 追加: spec doc (`docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md`、commit `308fcda` で済) + 本 plan (commit を本 plan 適用前に追加)
- 新規 unit test: なし (spec §5.6.2 justification、spawn 部は Iron Law 6 UAT で担保)

### Iron Law 整合 (`.claude/hooks/session-start.sh` / [docs/l2-workflow.md](../../docs/l2-workflow.md))

- **Iron Law 1**: 受け入れ条件逐条検証 — issue #727 は umbrella issue (受け入れ条件は明示されておらず spec §2 Goals が代替)。PR 本文の Self-Test Report で goals 各項を `[x]` 化
- **Iron Law 2**: 3 件以上の bulk 操作なし
- **Iron Law 3**: scope creep 禁止 — 本 plan は #727 の (1) のみ scope (§3 Non-goals 9 項目で明文化)
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #727` のみ
- **Iron Law 6**: PR 作成 Pre-flight (base sync + 並行 PR 確認) + 自動チェック全 pass + Iron Law 6 実機検証 (Idios UAT)

---

## Chapter 1: #727 open_folder_in_explorer tokio 統一

### Task 1.0: Pre-flight (base sync + 並行 PR 確認 + baseline test)

**Files:** (none)

- [ ] **Step 1: develop-0.2.0 を fetch して取り込み未済 commit を確認**

Run:

```bash
cd E:\projects\kobutachan-tools\kobutachan-allaganeye\.claude\worktrees\fervent-brahmagupta-3f4c94
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected:

- 取り込み未済 commit が無ければ output は空 — そのまま Step 3 へ
- 取り込み未済 commit がある場合: その commit の touched files に `gui/src-tauri/src/lib.rs` が含まれているかを `git show --stat <commit-sha>` で確認

- [ ] **Step 2: 取り込み未済 commit が `gui/src-tauri/src/lib.rs` を touch していれば merge する**

判定:

- 上記 Step 1 の commit が **`gui/src-tauri/src/lib.rs` を含まない** 場合: merge 不要、Step 3 へ
- **含む場合**: 以下を実行

```bash
git merge origin/develop-0.2.0
# コンフリクトが出たら手動解決 + git add + git commit
```

Expected: clean merge (本 plan 着手時点で `gui/src-tauri/src/lib.rs:1842-1862` 周辺を触る並行 PR が無いことを §6.1 single PR 前提 + Lane VII 並行安全度 high で確認済)。コンフリクトが出る場合は spec §6.2 Pre-flight に従い手動解決 + `cd gui/src-tauri && cargo check && cargo test --lib` で regression 確認。

- [ ] **Step 3: 並行 worktree PR の重複確認**

Run:

```bash
gh pr list --search "#727" --state all
```

Expected: 本 plan 着手時点で `#727` を扱う他 worktree PR は存在しない。存在する場合は **STOP** して `AskUserQuestion` で並行 PR との関係をユーザーに確認 (Iron Law 6 PR 作成 Pre-flight、`docs/l2-workflow.md` §「PR 作成 Pre-flight」)。

- [ ] **Step 4: baseline で既存 test が全 pass することを確認**

Run:

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -10
```

Expected: `test result: ok. X passed; 0 failed` (`X` は HEAD `308fcda` 時点の test 数、PR #720 以降の追加 test を含む)。`failed` が 1 件でもあれば本 plan 着手前に root cause を解明する必要あり (本 plan は green-from-green の refactor 前提)。

- [ ] **Step 5: baseline frontend 全 pass 確認**

Run:

```bash
cd gui && npm run lint 2>&1 | tail -5
cd gui && npm run typecheck 2>&1 | tail -5
cd gui && npm test -- --run 2>&1 | tail -5
cd gui && npm run build 2>&1 | tail -5
```

Expected: 全 pass。fail があれば Step 4 と同様 root cause 解明先行。

- [ ] **Step 6: baseline Python 全 pass 確認**

Run:

```bash
ruff check . 2>&1 | tail -5
ruff format --check . 2>&1 | tail -5
pyright 2>&1 | tail -5
pytest 2>&1 | tail -10
```

Expected: 全 pass (Iron Law 6 で「Python のみだから GUI 側不要」は Red Flag 同様、本 plan は GUI 側変更だが Python 側 baseline も green である必要あり)。

### Task 1.1: open_folder_in_explorer を tokio::process::Command に切り替え

**Files:**

- Modify: [gui/src-tauri/src/lib.rs:1830-1862](../../gui/src-tauri/src/lib.rs#L1830) (`open_folder_in_explorer` の doc comment + 関数本体)

- [ ] **Step 1: 編集対象の Read で現状を確認**

Run (informational、Edit ツールが file state を tracking するため必須ではないが、context 確認用):

```bash
sed -n '1830,1862p' gui/src-tauri/src/lib.rs
```

Expected: 後述 Step 2 の `old_string` と完全一致 (一致しない場合は line 番号 drift。`grep -n "fn open_folder_in_explorer" gui/src-tauri/src/lib.rs` で正確な位置を再特定してから次 Step へ)。

- [ ] **Step 2: 1 回の Edit で doc comment + signature + body を一括書き換え**

Use the `Edit` tool on `gui/src-tauri/src/lib.rs`:

`old_string`:

```rust
/// `path` をプラットフォーム固有のファイルマネージャ (Windows: explorer.exe)
/// で開く。
///
/// 旧実装は `tauri-plugin-shell` の `open` を使っていたが、`shell:allow-open`
/// permission の default scope が URL (`mailto:` / `tel:` / `https?://`) しか
/// 許可せず、ローカル path は `Scoped command argument failed regex
/// validation` で reject される。`open` の scope を path 許可に拡張する代わ
/// りに、Windows の `explorer.exe` を直接 spawn する独自 command を用意して
/// 確実に動かす (#545 review、2026-04-25)。
///
/// Windows のみ対応 (CLAUDE.md に「対応プラットフォーム: Windows のみ」と
/// 明記)。将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐する。
#[tauri::command]
fn open_folder_in_explorer(path: String) -> Result<(), AppError> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        use std::process::Command;
        Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| {
                AppError::new(
                    "subprocess.spawn_failed",
                    format!("failed to launch explorer: {}", e),
                )
                .with_default_hint()
            })?;
    }

    Ok(())
}
```

`new_string`:

```rust
/// `path` をプラットフォーム固有のファイルマネージャ (Windows: explorer.exe)
/// で開く。
///
/// 旧実装は `tauri-plugin-shell` の `open` を使っていたが、`shell:allow-open`
/// permission の default scope が URL (`mailto:` / `tel:` / `https?://`) しか
/// 許可せず、ローカル path は `Scoped command argument failed regex
/// validation` で reject される。`open` の scope を path 許可に拡張する代わ
/// りに、Windows の `explorer.exe` を直接 spawn する独自 command を用意して
/// 確実に動かす (#545 review、2026-04-25)。
///
/// **#727 (2026-05-13)**: 元 `std::process::Command` から `tokio::process::Command`
/// に切り替え、lib.rs 内 6 spawn site (probe_video_with / ensure_thumbnail_exists
/// / run_ffmpeg_export_attempt / start_detect / extract_brightness_window_impl
/// / 本関数) を `tokio::process::Command` 系で統一する refactor (gui spawn 統一)。
///
/// **apply_no_window 非適用**: explorer.exe は Win32 GUI subsystem アプリで
/// そもそも console window を生成しないため、`process_util::apply_no_window`
/// (= CREATE_NO_WINDOW flag) の purpose (windows_subsystem="windows" 親で
/// release 時の console 割当抑止) と一致しない。本関数は `process_util.rs`
/// adoption test (`lib_rs_applies_apply_no_window_at_all_spawn_sites`) の検査
/// 対象外として扱う。
///
/// **PROCESS_TRACKER 非登録**: explorer.exe はユーザーの file manager UI
/// であり、本 app が close されても残るべき。`track_child` を呼ばないことで
/// `kill_tracked_processes` (CloseRequested flow #523) の影響を受けない。
///
/// Windows のみ対応 (CLAUDE.md に「対応プラットフォーム: Windows のみ」と
/// 明記)。将来 Linux / macOS 対応する際は `xdg-open` / `open` で分岐する。
#[tauri::command]
async fn open_folder_in_explorer(path: String) -> Result<(), AppError> {
    validate_open_folder_request(&path)?;

    #[cfg(target_os = "windows")]
    {
        // #727 -- spawn explorer.exe via tokio::process::Command for parity
        // with the other 5 spawn sites (probe_video_with /
        // ensure_thumbnail_exists / run_ffmpeg_export_attempt / start_detect
        // / extract_brightness_window_impl). The returned Child is dropped
        // immediately: explorer.exe is the user's file manager UI and should
        // outlive this Tauri app; Windows has no zombie process model so
        // the drop is safe.
        tokio::process::Command::new("explorer.exe")
            .arg(&path)
            .spawn()
            .map_err(|e| {
                AppError::new(
                    "subprocess.spawn_failed",
                    format!("failed to launch explorer: {}", e),
                )
                .with_default_hint()
            })?;
    }

    Ok(())
}
```

差分概要:

- 既存 1 段落 (#545 経緯) と末尾 1 段落 (Windows のみ対応) の間に **3 段落 (#727 / `apply_no_window` 非適用 / PROCESS_TRACKER 非登録) を挿入**
- `fn open_folder_in_explorer` → `async fn open_folder_in_explorer`
- `use std::process::Command;` 行を削除
- `Command::new("explorer.exe")` → `tokio::process::Command::new("explorer.exe")` (フルパス、他 5 spawn site と同 idiom)
- spawn 直前に inline comment `// #727 -- ...` 追加 (Child drop の根拠を記録)
- error message (`failed to launch explorer:`) / AppError code (`subprocess.spawn_failed`) / `.with_default_hint()` は不変
- `validate_open_folder_request(&path)?` 行は不変

- [ ] **Step 3: cargo check で型エラー無し**

Run:

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -10
```

Expected: `Finished` で終了 (warning は許容、error は不可)。`async fn` 化により signature 変更したが `#[tauri::command]` macro が sync/async 両対応のため compile pass。tokio runtime 依存は既に他 5 spawn site で確立済のため新規 import は不要。

- [ ] **Step 4: cargo test --lib で既存 test が全 pass (regression check)**

Run:

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -10
```

Expected:

- `test result: ok` で baseline (Task 1.0 Step 4) と同じ test 数が pass
- 特に確認:
  - `process_util::tests::lib_rs_applies_apply_no_window_at_all_spawn_sites` — 5 site (probe_video_with / ensure_thumbnail_exists / run_ffmpeg_export_attempt / start_detect / extract_brightness_window_impl) のまま pass (open_folder_in_explorer は追加されない)
  - `tests::validate_open_folder_request_*` 3 件 — path validation 不変、pass 維持
  - `tests::track_child_*` 系 — PROCESS_TRACKER に open_folder は登録されないため不変、pass 維持

fail があれば Task 1.1 Step 2 の Edit を読み返して signature / spawn 部分の typo / インデント乱れを修正。`cargo test --lib --no-run -- --quiet 2>&1 | head -50` で compile error の詳細を取得。

### Task 1.2: Frontend regression check

**Files:** (none、本 plan は frontend 編集なし)

- [ ] **Step 1: npm run lint**

Run:

```bash
cd gui && npm run lint 2>&1 | tail -10
```

Expected: 0 error (本 plan は frontend touch せず、baseline (Task 1.0 Step 5) と同 result)。

- [ ] **Step 2: npm run typecheck**

Run:

```bash
cd gui && npm run typecheck 2>&1 | tail -10
```

Expected: 0 error。frontend `invoke('open_folder_in_explorer', ...)` の signature は文字列名指定なので Rust 側 sync/async 変更は frontend 型に影響しない。

- [ ] **Step 3: npm test (vitest)**

Run:

```bash
cd gui && npm test -- --run 2>&1 | tail -15
```

Expected: 全 pass。特に [`gui/src/screens/ExportScreen.test.tsx:482-500`](../../gui/src/screens/ExportScreen.test.tsx#L482) (`invoke('open_folder_in_explorer')` mock テスト) が baseline と同じ pass を維持。

- [ ] **Step 4: npm run build**

Run:

```bash
cd gui && npm run build 2>&1 | tail -10
```

Expected: `vite build` succeed + bundle 生成 (`gui/dist/`)。

### Task 1.3: Python regression check

**Files:** (none、本 plan は Python 編集なし)

- [ ] **Step 1: ruff check**

Run:

```bash
ruff check . 2>&1 | tail -10
```

Expected: `All checks passed!` または equivalent (本 plan は Python touch せず、baseline (Task 1.0 Step 6) と同 result)。

- [ ] **Step 2: ruff format --check**

Run:

```bash
ruff format --check . 2>&1 | tail -10
```

Expected: `X files already formatted` (baseline と同 file 数)。

- [ ] **Step 3: pyright**

Run:

```bash
pyright 2>&1 | tail -10
```

Expected: `0 errors` (Information / Warning は baseline と同数なら許容)。

- [ ] **Step 4: pytest**

Run:

```bash
pytest 2>&1 | tail -10
```

Expected: `passed` で baseline (Task 1.0 Step 6) と同 test 数。Python 側は本 plan で全く触れていないので、ここで fail するのは flaky test の可能性 → 1 回 retry し、それでも fail なら STOP して `AskUserQuestion` で報告。

### Task 1.4: markdownlint regression check

**Files:** (none、本 plan は docs 編集なし。spec doc + 本 plan は spec commit `308fcda` で markdownlint 0 errors を確認済)

- [ ] **Step 1: bash scripts/check-markdownlint.sh**

Run:

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: `Summary: 0 error(s)` (本 plan は docs touch せず、spec commit `308fcda` 時点と同 result の `142 file(s) / 0 error(s)` 程度)。

### Task 1.5: Commit + push

**Files:** (none、Task 1.1 で modify した `gui/src-tauri/src/lib.rs` を stage)

- [ ] **Step 1: 変更内容を git diff で確認**

Run:

```bash
git diff gui/src-tauri/src/lib.rs 2>&1 | head -120
```

Expected: Task 1.1 Step 2 の `old_string` → `new_string` 差分のみ。他ファイルや他関数への影響なし。

- [ ] **Step 2: stage + commit**

Run:

```bash
git add gui/src-tauri/src/lib.rs
git commit -F - <<'EOF'
refactor(gui): open_folder_in_explorer を tokio::process::Command に統一 (Refs #727)

`gui/src-tauri/src/lib.rs:1842-1862` の `open_folder_in_explorer` を
`std::process::Command` から `tokio::process::Command` に切り替え、
lib.rs 内 6 spawn site (probe_video_with / ensure_thumbnail_exists /
run_ffmpeg_export_attempt / start_detect / extract_brightness_window_impl /
本関数) を `tokio::process::Command` 系で統一 (gui spawn 統一の完成)。

`fn` → `async fn` 化で他 5 spawn site (全て `async fn`) と convention 統一。
`#[tauri::command]` は sync/async 両対応のため frontend `invoke()` は Promise
返却で挙動同一、`ExportScreen.test.tsx` / `ErrorModal.tsx` への影響なし。

doc comment に 3 段落追加:
- #727 切替経緯 (lib.rs 内 6 spawn site の tokio 統一)
- apply_no_window 非適用 (explorer.exe は Win32 GUI subsystem、purpose
  alignment 不成立、process_util.rs adoption test は 5 site のまま)
- PROCESS_TRACKER 非登録 (explorer.exe は user UI、CloseRequested flow
  #523 の kill 対象外を維持)

scope 外 (派生 issue 候補、post-v0.2.0 別 issue):
- (2) 5 spawn site の `tauri-plugin-shell::Command` 全面移行
- (3) Windows process group orphan 挙動の audit

Refs #727
Spec: docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md §5
Plan: docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md Chapter 1

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: `[claude/fervent-brahmagupta-3f4c94 <new-sha>] refactor(gui): open_folder_in_explorer ...` で 1 file changed。

- [ ] **Step 3: 本 plan を別 commit として追加 (まだ commit していなければ)**

Run:

```bash
git status --short
```

`docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md` が未 commit なら:

```bash
git add docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md
git commit -F - <<'EOF'
docs: L2 Lane VII Group M plan (#727 gui spawn 統一) 追加 (Refs #727)

Lane VII Group M の implementation plan。Chapter 1 (single PR、single
chapter) で open_folder_in_explorer を tokio::process::Command に切り替え、
Task 1.0 (Pre-flight + baseline) → Task 1.1 (Edit + cargo check + test) →
Task 1.2-1.4 (Frontend / Python / markdownlint regression) → Task 1.5
(commit + push) → Task 1.6 (PR 作成) → Task 1.7 (Iron Law 6 UAT handoff)
の 8 task で完結。

Refs #727
Spec: docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 4: push**

Run:

```bash
git push -u origin claude/fervent-brahmagupta-3f4c94 2>&1 | tail -10
```

Expected: `* [new branch]      claude/fervent-brahmagupta-3f4c94 -> claude/fervent-brahmagupta-3f4c94` または既存 branch の場合 fast-forward push success。

### Task 1.6: PR 作成

**Files:** (none)

- [ ] **Step 1: gh pr create で本 plan の Self-Test Report 付き PR を作成**

Run:

```bash
gh pr create --base develop-0.2.0 --title "refactor(gui): #727 open_folder_in_explorer を tokio::process::Command に統一 (gui spawn 統一、Lane VII)" --body-file - <<'EOF'
## Summary

[#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) の実装。L2 Wave 1 Lane VII Group M (1 spec / 1 章 / single PR、P3-low refactor)。

`gui/src-tauri/src/lib.rs:1842-1862` の `open_folder_in_explorer` を `std::process::Command` から `tokio::process::Command` に切り替え、lib.rs 内 6 spawn site (probe_video_with / ensure_thumbnail_exists / run_ffmpeg_export_attempt / start_detect / extract_brightness_window_impl / 本関数) を **tokio::process::Command 系で統一** (gui spawn 統一の完成)。

- **Spec**: [docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md](docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md)
- **Plan**: [docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md](docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md)
- **Roadmap**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md) Group M
- **session-id**: `fervent-brahmagupta-3f4c94`

## 変更内容

- `gui/src-tauri/src/lib.rs:1842-1862` (`open_folder_in_explorer`)
  - `fn` → `async fn` (`#[tauri::command]` で frontend `invoke()` は Promise 返却、挙動同一)
  - `use std::process::Command;` 削除、`Command::new("explorer.exe")` → `tokio::process::Command::new("explorer.exe")` (フルパス参照、他 5 spawn site と同 idiom)
  - doc comment に 3 段落追記 (#727 切替経緯 / `apply_no_window` 非適用 / PROCESS_TRACKER 非登録)
  - inline comment 追加 (`// #727 -- spawn explorer.exe via tokio ...`、Child drop の根拠)
  - error message / AppError code (`subprocess.spawn_failed`) / `.with_default_hint()` は不変
- `docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md` 新規 (spec doc、commit `308fcda`)
- `docs/superpowers/plans/2026-05-13-l2-lane-vii-group-m.md` 新規 (本 plan)

## scope 外 (派生 issue 候補、post-v0.2.0 別 issue)

- **(2) 5 spawn site の `tauri-plugin-shell::Command` 全面移行** — Tauri 2 公式 API 移行 (戦略的価値あり、`process_util::apply_no_window` / `PROCESS_TRACKER` 全面再設計が必要なため別 issue)
- **(3) Windows process group orphan 挙動の audit** — 親 kill 時の子プロセス group 挙動精査 (audit task、別 issue)

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` (取り込み未済 commit なし、または `gui/src-tauri/src/lib.rs` と非交差)
- [x] `gh pr list --search "#727" --state all` 並行 worktree PR 重複なし
- [x] `cd gui/src-tauri && cargo check`
- [x] `cd gui/src-tauri && cargo test --lib` (baseline と同 test 数 pass、`process_util::tests::lib_rs_applies_apply_no_window_at_all_spawn_sites` / `tests::validate_open_folder_request_*` 3 件 / `tests::track_child_*` 系すべて pass)
- [x] `cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- [x] `ruff check . && ruff format --check . && pyright && pytest`
- [x] `bash scripts/check-markdownlint.sh` (142 files / 0 errors)

### Machine-unverifiable (Iron Law 6 実機検証 — Idios)

#### dev build (`cd gui && npm run tauri dev`)

- [ ] 動画 detect → PreviewScreen → ExportScreen → 完了画面で「フォルダを開く」 → explorer ウィンドウ正常表示
- [ ] ExportScreen エラー → ErrorModal → 「ログフォルダを開く」 → explorer ウィンドウ正常表示
- [ ] path validation エラー再現 (存在しないパス等) → AppError UI 経路で ErrorModal 表示

#### release bundle (`cd gui && cargo tauri build`)

- [ ] release exe (`gui/src-tauri/target/release/bundle/.../allaganeye-gui.exe`) 起動
- [ ] DropScreen で動画選択 → detect 実行 → **CMD 窓非表示** (#679 regression check)
- [ ] PreviewScreen → export 実行 → **CMD 窓非表示** (#679 regression check)
- [ ] export 完了 → 「フォルダを開く」クリック → explorer 正常表示 + **CMD 窓非表示** (本 refactor 確認 + #679 regression check)
- [ ] ErrorModal → 「ログフォルダを開く」 → explorer 正常表示 + CMD 窓非表示

EOF
```

Expected: `https://github.com/Idios/kobutachan-allaganeye/pull/<N>` URL が返る。

- [ ] **Step 2: PR URL を控える**

PR URL を以降の Task 1.7 / `/iterate-review` 等で使用するため記録する (PR # は Step 1 の output から)。

### Task 1.7: Iron Law 6 実機検証 (Idios UAT) handoff

**Files:** (none)

- [ ] **Step 1: AskUserQuestion で Idios に UAT 実施を依頼**

`gui/src-tauri/**` 編集を含むため Iron Law 6 で実機検証が必須。CLAUDE.md memory `project_system_info_schema_gap.md` / Iron Law 6 文言「mock テスト pass = 実機検証不要 は Red Flag」に従い、AskUserQuestion で明示的に依頼する。

Use the `AskUserQuestion` tool with the question:

> 「PR `#<N>` を作成しました。Iron Law 6 実機検証 (dev build + release bundle の `open_folder_in_explorer` 挙動 + #679 CMD 窓 regression check) を実施いただけますか?」

Options (sample、Recommended は α 維持):

- (α) 今すぐ dev + release 両方で UAT を実施 (Recommended、spec §7.2 全 8 項目)
- (β) dev build のみ先行で UAT 実施、release bundle は後日 (UAT 部分結果で先に review 段階へ進む)
- (γ) UAT を `/iterate-review` 後に後回し (review-fix ループ完了後にまとめて実施)
- (δ) 別の方法で対応 (詳細は次のターンで)

Expected: Idios の選択に応じて分岐:

- (α) / (β) の場合: Idios が UAT を実施 → 結果を PR comment または次のターンで報告 → 報告を受けて Step 2 へ
- (γ) の場合: `/iterate-review` を本 PR に対して実行 (本 plan の terminal state、UAT は別タイミングで)
- (δ) の場合: Idios の指示に従う

- [ ] **Step 2: UAT 結果に応じて PR body の machine-unverifiable section を更新**

UAT で全項目 pass の場合:

```bash
gh pr edit <PR#> --body-file <updated-body.md>
```

(`<updated-body.md>` は machine-unverifiable section の `- [ ]` を `- [x]` に置換した body) または GitHub UI で checkbox を check して edit。

UAT で 1 項目でも fail の場合: STOP して `AskUserQuestion` で次の判断 (PR 内追加修正 / scope 拡大評価 / 別 issue 起票) を Idios に確認 (Iron Law 5 ambiguous 判断点 + `feedback_iterate_review_no_scope_creep_option.md` のメモリに従い、選択肢に「scope 拡大」を含めない)。

### Task 1.8: terminal state (本 plan 完了、`/iterate-review` handoff)

**Files:** (none)

- [ ] **Step 1: 本 plan の terminal state を確認**

本 plan は **PR 作成 + Iron Law 6 UAT handoff** までを scope とする。PR review-fix ループは `/iterate-review <PR#>` が担当 (CLAUDE.md §「/iterate-review workflow と (A) 強優先方針」)。

terminal state での残作業:

1. Idios が UAT を実施し PR body machine-unverifiable section を `- [x]` 化 (Task 1.7)
2. `/iterate-review <PR#>` で review-fix ループを自走させる (本 plan scope 外)
3. PR merge 後、Wave 2 release gate で `/close-issue 727` を実行し受け入れ条件 (本 plan の §5 Goals 4 項) を実測再検証 + 手動クローズ

本 plan の Task 1.0-1.7 がすべて完了したら、ユーザーに以下を報告:

- PR URL
- machine-verified 全 pass
- Iron Law 6 UAT の Idios 進捗 (Task 1.7 Step 1 の Idios 選択)
- 次の handoff (`/iterate-review` / `/close-issue` / spec self-test ループ 等)

---

## Spec coverage check (self-review、本 plan に対する spec 各項対応)

| spec section | 内容 | plan task |
| --- | --- | --- |
| §0 関連 issue / PR 状態整理 | umbrella issue / 派生 candidate / 既存 helper の前提整理 | Pre-implementation notes (既存資産表) |
| §1.1 #727 概要 | Q1-Q4 design choice の正当化 | Pre-implementation notes (既に done) |
| §1.2 現状コード | lib.rs:1842-1862 の現 impl | Task 1.1 Step 1 (Read で確認) |
| §1.3 他 5 spawn site | 6 site 表 + tokio 統一の論拠 | Task 1.1 Step 2 (refactor、commit message にも記載) |
| §1.4 frontend 呼び出し元 | impact なしの根拠 | Task 1.2 (Frontend regression check) |
| §2 Goals | 4 つの goal | Task 1.5 commit message + PR body Self-Test Report |
| §3 Non-goals | 9 項目 | Task 1.5 commit message + PR body「scope 外」 |
| §4 Architecture | ASCII 図 | (実装段階では参照のみ、plan の文書化対象外) |
| §5.1 signature 変更 | `fn` → `async fn` | Task 1.1 Step 2 |
| §5.2 spawn body 変更 | tokio Command + inline comment | Task 1.1 Step 2 |
| §5.3 doc comment 拡充 | 3 段落追加 | Task 1.1 Step 2 |
| §5.4 data flow / error handling | validate / cfg / spawn failure / Child drop | Task 1.1 Step 2 (doc comment に明示) + Task 1.1 Step 4 (regression test) |
| §5.5 frontend / call site への影響 | ErrorModal / ExportScreen / test.tsx 不変 | Task 1.2 (Frontend regression check) |
| §5.6.1 既存 unit test (不変、regression check) | 3 系統 (validate / process_util adoption / track_child) | Task 1.1 Step 4 |
| §5.6.2 新規 unit test なし (justification) | spawn は UAT、validate は既存 cover | Task 1.1 Step 4 + Task 1.7 UAT |
| §5.7 派生 issue 候補 | (2) tauri-plugin-shell / (3) process group orphan | Task 1.5 commit message + PR body「scope 外」 |
| §6.1 single PR | PR 構成 / title / commit message / session-id | Task 1.5 / Task 1.6 |
| §6.2 base 同期 Pre-flight | git fetch / log / merge / regression / parallel PR 確認 | Task 1.0 |
| §6.3 release timeline | Wave 1 merge → Wave 2 /close-issue | Task 1.8 (handoff) |
| §7.1 Machine-verified | 5 系統 (cargo / npm / ruff / pyright / pytest / markdownlint) | Task 1.0 baseline + Task 1.2 / 1.3 / 1.4 + PR Self-Test Report |
| §7.2 Machine-unverifiable (Iron Law 6 UAT) | dev 3 項目 + release 5 項目 | Task 1.7 |
| §8 Self-Test Report テンプレ | PR body 構造 | Task 1.6 Step 1 |

全 spec section に対応 task あり、coverage gap なし。

---

## 関連

Refs [#727](https://github.com/Idios/kobutachan-allaganeye/issues/727) [#679](https://github.com/Idios/kobutachan-allaganeye/issues/679) [#545](https://github.com/Idios/kobutachan-allaganeye/pull/545) [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645)

Spec: [docs/superpowers/specs/2026-05-13-l2-lane-vii-group-m-design.md](../specs/2026-05-13-l2-lane-vii-group-m-design.md)
Roadmap: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](2026-05-13-l2-v020-roadmap-update.md) Group M
