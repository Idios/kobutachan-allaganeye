# AppError migration 完遂 (Lane I-A / #663) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #665 で完了済の `Result<T, AppError>` migration を踏まえ、#663 の残作業 (legacy fallback 撤去 / per-code default hint 全 80 site 適用 / frontend hint 表示 / docs 整合) を 1 PR で完遂する。

**Architecture:** Rust `error.rs` に per-code default hint helper を導入 → 全 80 site で `.with_default_hint()` chain → frontend store/screens で per-store error+hint pair + inline 2 行目 render → docs / issue body を実態と整合させる。詳細は spec [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](../specs/2026-05-08-l2-appError-migration-completion-design.md) (commit `c3a1ddf`) を source of truth とする。

**Tech Stack:** Rust (Tauri 2 backend) / TypeScript + React 19 + Zustand (frontend) / vitest + cargo test / Tauri 2 invoke + serde JSON / markdownlint-cli2 / `gh` CLI for issue body update.

**Iron Law 整合 (本 plan で担保):**

- Iron Law 1 (受け入れ条件): spec § 12 を逐条検証可能な list として保持
- Iron Law 3 (scope creep): non-goals (spec § 3) を遵守、scope 外検出時は scope-guard skill 起動
- Iron Law 4 (Closes 禁止): commit / PR 本文に `Refs #663` のみ、issue クローズは別 step (`/close-issue`)
- Iron Law 5 (曖昧 AskUserQuestion): 5 経路の実機検証は Phase 6 で `AskUserQuestion` で Idios に依頼
- Iron Law 6 (PR Pre-flight + 実機検証): Phase 6 で完全準拠

---

## File structure (touched files)

```text
gui/src-tauri/src/
  error.rs              ← Phase 1 (helper + From impl + 6 new tests)
  lib.rs                ← Phase 2 (80 sites mechanical)

gui/src/state/
  metadataStore.ts      ← Phase 3 (5 errorHint state + catch + remove legacy fallback)
  metadataStore.test.ts ← Phase 3 (8 rewrite + 5 new)
  recentStore.ts        ← Phase 3 (addErrorHint + loadErrorHint)
  recentStore.test.ts   ← Phase 3 (2 new)

gui/src/components/
  ConflictModal.test.tsx ← Phase 3 (test data fix)
  RestoreButton.tsx      ← Phase 4 (hint 2nd line)
  RestoreButton.module.css ← Phase 4 (.error → .errorHint pair)
  RestoreButton.test.tsx ← Phase 4 (2 new tests)

gui/src/screens/
  DropScreen.tsx + .test.tsx           ← Phase 4 (local errorHint state + render)
  DetectingScreen.tsx + .test.tsx      ← Phase 4 (local errorHint state + render)
  PreviewScreen.tsx + .test.tsx        ← Phase 4 (store applyErrorHint render)
  ExportScreen.tsx + .test.tsx         ← Phase 4 (per-match errorHint reducer)

gui/src/styles/tokens.css
  + 各 module.css                      ← Phase 4 (.errorHint shared style)

docs/
  tauri-commands.md      ← Phase 5 (hint mapping table)
  ui-architecture.md     ← Phase 5 (§ 4.x AppError code 一覧)
  ui-interaction-spec.md ← Phase 5 (§ 1.5.x error.code 分岐ルール)

(Issue body)
  #663                   ← Phase 5 (gh issue edit)
```

**Commit 構成 (Phase = 1 commit):**

1. `feat(gui): AppError::default_hint_for_code helper を追加 (Refs #663)` — Phase 1
2. `refactor(gui): lib.rs 全 80 site に .with_default_hint() を適用 (Refs #663)` — Phase 2
3. `feat(gui): metadataStore / recentStore に *ErrorHint state を追加 + legacy fallback 削除 (Refs #663)` — Phase 3
4. `feat(gui): 各 screen の inline error に hint 2 行目を追加 (Refs #663)` — Phase 4
5. `docs: AppError default hint mapping を docs に整合させる (Refs #663)` — Phase 5

Phase 6 は PR 提出 step で commit を伴わない (Pre-flight + 実機検証 + PR 作成のみ)。

---

## Task 0: Pre-flight (worktree state verification)

**Files:**

- Read: spec `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`
- Verify: `git status` clean, branch `claude/tender-khayyam-03d618`

- [ ] **Step 1: Confirm working directory and branch**

```bash
pwd
# Expected: /e/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/tender-khayyam-03d618

git branch --show-current
# Expected: claude/tender-khayyam-03d618

git status
# Expected: nothing to commit, working tree clean (or only spec commit c3a1ddf)
```

- [ ] **Step 2: Read the spec for full context**

Read `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` end-to-end. The spec is the source of truth for all design decisions (24 codes (or-pattern 展開後 #692) を hint mapping に集約, 4-layer architecture, scope boundaries).

- [ ] **Step 3: Verify Iron Law base sync**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: empty (no new commits to pull) OR list of new commits. If non-empty AND any commit touches `gui/src-tauri/src/error.rs|lib.rs|gui/src/state/*|gui/src/components/*|gui/src/screens/*|docs/*`, run `git merge origin/develop-0.2.0` and re-run automated checks. (`docs/l2-workflow.md` § PR 作成 Pre-flight に従う)

- [ ] **Step 4: Verify no parallel worktree PR for #663**

```bash
gh pr list --search "#663" --state all
gh pr list --state open --search "claude/"
```

Expected: no other open PR claiming #663. If a parallel PR exists, halt and ask user via `AskUserQuestion`.

---

## Phase 1: Rust `error.rs` (default hint helper + From impl chains)

### Task 1.1: TDD `default_hint_for_code` helper

**Files:**

- Modify: `gui/src-tauri/src/error.rs`

- [ ] **Step 1: Write the failing test for `default_hint_covers_all_known_codes`**

Add inside the existing `mod tests` in `gui/src-tauri/src/error.rs`:

```rust
    #[test]
    fn default_hint_covers_all_known_codes() {
        let with_hint = [
            "state.mtime_conflict",
            "io.file_not_found", "io.read_failed", "io.write_failed",
            "io.delete_failed", "io.backup_failed",
            "io.permission_denied", "io.already_exists",
            "io.would_block", "io.timed_out", "io.error",
            "parse.json_invalid", "parse.json_serialize_failed",
            "parse.schema_invalid", "parse.ffprobe_output_invalid",
            "subprocess.spawn_failed", "subprocess.exit_failed",
            "validation.path_invalid", "validation.not_a_file", "validation.range_invalid",
            "path.install_dir_unresolved", "platform.unsupported",
        ];
        for code in with_hint {
            assert!(default_hint_for_code(code).is_some(), "missing hint for code: {}", code);
        }
        assert!(default_hint_for_code("subprocess.cancelled").is_none());
        assert!(default_hint_for_code("internal.error").is_none());
        assert!(default_hint_for_code("unknown.code").is_none());
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast default_hint_covers_all_known_codes 2>&1 | tail -20
```

Expected: FAIL with `cannot find function default_hint_for_code in this scope` or similar.

- [ ] **Step 3: Implement `default_hint_for_code` (top-level fn in error.rs, OUTSIDE the `tests` mod)**

Add the following just before the existing `#[derive(Debug, Clone, Serialize)] pub struct PanicPayload` block (i.e. after the `From<String>` impl, before `PanicPayload`):

```rust
/// AppError code に対する日本語 default hint を返す。未登録 code は None。
/// 24 codes (or-pattern `io.would_block | io.timed_out` を 2 codes に展開後、22 hint
/// + 2 None = 24)。現在の lib.rs inventory: io.* / parse.* / state.* / subprocess.* /
/// validation.* / path.* / platform.* / internal.*。
/// 文言は `docs/tauri-commands.md` の AppError default hint mapping table と一致させる
/// (本 fn が source of truth、docs は mirror、#692 で CI integrity check 化済)。
fn default_hint_for_code(code: &str) -> Option<&'static str> {
    match code {
        // state
        "state.mtime_conflict" => Some(
            "metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください"
        ),
        // io (manual call site)
        "io.file_not_found" => Some(
            "ファイルが見つかりません。パスを確認するか、allaganeye split を再実行してください"
        ),
        "io.read_failed" => Some(
            "ファイルの読み込みに失敗しました。ディスク状況・ファイルロック状態を確認してください"
        ),
        "io.write_failed" => Some(
            "ファイルの書き込みに失敗しました。空き容量と書き込み権限 (Portable ZIP の install dir が user-writable か) を確認してください"
        ),
        "io.delete_failed" => Some(
            "ファイル / フォルダの削除に失敗しました。他プロセスでロックされていないか確認してください"
        ),
        "io.backup_failed" => Some(
            "バックアップファイルの作成に失敗しました。allaganeye 出力フォルダの空き容量と書き込み権限を確認してください"
        ),
        // io (auto from std::io::Error::ErrorKind via From impl)
        "io.permission_denied" => Some(
            "ファイルへのアクセス権限がありません。Portable ZIP install dir が user-writable な場所か、ファイル / フォルダが読み取り専用でないか確認してください"
        ),
        "io.already_exists" => Some(
            "ファイルが既に存在します。出力先を変更するか既存ファイルを削除してください"
        ),
        "io.would_block" | "io.timed_out" => Some(
            "I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください"
        ),
        "io.error" => Some(
            "I/O エラーが発生しました。詳細は logs フォルダを確認してください"
        ),
        // parse
        "parse.json_invalid" => Some(
            "JSON ファイルが破損しています。バックアップ (.bak) からの復元か allaganeye split のやり直しを検討してください"
        ),
        "parse.json_serialize_failed" => Some(
            "JSON 書き出しに失敗しました。同梱 issue テンプレートでバグ報告してください"
        ),
        "parse.schema_invalid" => Some(
            "metadata.json の構造が期待形式と異なります。allaganeye のバージョンと metadata 生成バージョンが一致しているか確認してください"
        ),
        "parse.ffprobe_output_invalid" => Some(
            "ffprobe の出力を解釈できませんでした。ffmpeg / ffprobe を最新の BtbN LGPL ビルドに更新してください"
        ),
        // subprocess
        "subprocess.spawn_failed" => Some(
            "外部プロセスの起動に失敗しました。ffmpeg / Python / 同梱 runtime が壊れていないか確認してください"
        ),
        "subprocess.exit_failed" => Some(
            "外部プロセスが異常終了しました。logs フォルダの最新ログから詳細を確認してください"
        ),
        "subprocess.cancelled" => None, // ユーザー操作によるキャンセルは hint 不要 (UI 側で「キャンセルされました」を表示で十分)
        // validation
        "validation.path_invalid" => Some(
            "入力されたパスが不正です。ファイル名と拡張子を確認してください (対応: mp4 / mkv / mov / m4v)"
        ),
        "validation.not_a_file" => Some(
            "指定されたパスはファイルではありません (フォルダや symlink ではなく動画ファイルを選択してください)"
        ),
        "validation.range_invalid" => Some(
            "入力された数値が許容範囲外です。フォーム下のヒント表示を確認してください"
        ),
        // path / platform / internal
        "path.install_dir_unresolved" => Some(
            "Portable ZIP の install dir を特定できませんでした。allaganeye-gui.exe を ZIP 展開後の元のフォルダ構成のまま起動してください"
        ),
        "platform.unsupported" => Some(
            "本機能は現在の OS では未対応です。Windows での起動が必要です"
        ),
        "internal.error" => None, // 内部エラーで具体的アクションがない (詳細は logs 参照を message 側で示す方針)
        _ => None,
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast default_hint_covers_all_known_codes 2>&1 | tail -10
```

Expected: PASS (`test tests::default_hint_covers_all_known_codes ... ok`).

### Task 1.2: TDD `with_default_hint` method

**Files:**

- Modify: `gui/src-tauri/src/error.rs`

- [ ] **Step 1: Write 3 failing tests**

Add inside `mod tests` (in `gui/src-tauri/src/error.rs`):

```rust
    #[test]
    fn with_default_hint_attaches_known_code() {
        let e = AppError::new("io.read_failed", "could not read").with_default_hint();
        assert!(e.hint.is_some());
        assert!(e.hint.unwrap().contains("ディスク状況"));
    }

    #[test]
    fn with_default_hint_does_not_overwrite_explicit_hint() {
        let e = AppError::new("io.read_failed", "msg")
            .with_hint("custom hint")
            .with_default_hint();
        assert_eq!(e.hint.as_deref(), Some("custom hint"));
    }

    #[test]
    fn with_default_hint_returns_no_hint_for_unknown_code() {
        let e = AppError::new("unknown.code", "msg").with_default_hint();
        assert!(e.hint.is_none());
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast with_default_hint 2>&1 | tail -20
```

Expected: 3 FAIL with `no method named with_default_hint found for struct AppError`.

- [ ] **Step 3: Implement `with_default_hint` method**

Add inside the existing `impl AppError { ... }` block in `gui/src-tauri/src/error.rs` (right after `with_stacktrace`):

```rust
    /// code に対する default hint を attach する。すでに hint が設定されている場合は
    /// 上書きせず保持する (call site で `.with_hint("...")` を先に書いた場合の override
    /// が効く設計、将来 Approach C への hybrid 移行時に必要)。
    pub fn with_default_hint(mut self) -> Self {
        if self.hint.is_some() {
            return self;
        }
        self.hint = default_hint_for_code(&self.code).map(String::from);
        self
    }
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast with_default_hint 2>&1 | tail -10
```

Expected: 3 PASS.

### Task 1.3: TDD `From<io::Error>` and `From<serde_json::Error>` hint chain

**Files:**

- Modify: `gui/src-tauri/src/error.rs`

- [ ] **Step 1: Write 2 failing tests**

Add inside `mod tests` (in `gui/src-tauri/src/error.rs`):

```rust
    #[test]
    fn from_io_error_attaches_default_hint() {
        let io_err = std::io::Error::new(std::io::ErrorKind::NotFound, "x");
        let e: AppError = io_err.into();
        assert_eq!(e.code, "io.file_not_found");
        assert!(e.hint.is_some());
    }

    #[test]
    fn from_serde_json_error_attaches_default_hint() {
        let json_err = serde_json::from_str::<serde_json::Value>("{ invalid").unwrap_err();
        let e: AppError = json_err.into();
        assert_eq!(e.code, "parse.json_invalid");
        assert!(e.hint.is_some());
    }
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast from_io_error from_serde_json_error 2>&1 | tail -20
```

Expected: 2 FAIL with `assertion 'left == right' failed` (e.hint is None instead of Some(...)).

- [ ] **Step 3: Update From impls to chain `.with_default_hint()`**

In `gui/src-tauri/src/error.rs`, modify the existing `From<std::io::Error>` impl by appending `.with_default_hint()` at the final expression:

```rust
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        let code = match e.kind() {
            std::io::ErrorKind::NotFound => "io.file_not_found",
            std::io::ErrorKind::PermissionDenied => "io.permission_denied",
            std::io::ErrorKind::AlreadyExists => "io.already_exists",
            std::io::ErrorKind::WouldBlock => "io.would_block",
            std::io::ErrorKind::TimedOut => "io.timed_out",
            _ => "io.error",
        };
        AppError::new(code, e.to_string()).with_default_hint()
    }
}
```

And the `From<serde_json::Error>` impl:

```rust
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::new("parse.json_invalid", e.to_string()).with_default_hint()
    }
}
```

Leave `From<String>` unchanged — `internal.error` correctly maps to None hint.

- [ ] **Step 4: Run tests to verify pass**

```bash
cd gui/src-tauri && cargo test --lib --no-fail-fast from_io_error from_serde_json_error 2>&1 | tail -10
```

Expected: 2 PASS.

### Task 1.4: Phase 1 full test pass + commit

- [ ] **Step 1: Run full cargo test --lib**

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -30
```

Expected: `test result: ok. 155 passed; 0 failed` (149 existing + 6 new).

- [ ] **Step 2: Run cargo check for warnings**

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -20
```

Expected: no warnings, especially no `with_hint` dead-code warning (it's used by the existing `serialize_app_error_roundtrips` test and the new `with_default_hint_does_not_overwrite_explicit_hint` test, so `#[allow(dead_code)]` continues to suppress non-test build warnings).

- [ ] **Step 3: Commit Phase 1**

```bash
cd ../..  # back to worktree root
git add gui/src-tauri/src/error.rs
git commit -m "$(cat <<'EOF'
feat(gui): AppError::default_hint_for_code helper を追加 (Refs #663)

PR #665 で Result<T, AppError> migration が完了済の状態を踏まえ、24 codes (or-pattern 展開後 #692)
(state / io.manual / io.auto / parse / subprocess / validation / path /
platform / internal) に対する日本語 default hint を error.rs の 1 mapping
table に集約。

主な追加:

- default_hint_for_code(code: &str) -> Option<&'static str> (24 codes、or-pattern 展開後 #692)
- AppError::with_default_hint(self) -> Self (既存 hint があれば上書きしない)
- From<std::io::Error> / From<serde_json::Error> impl 内で
  .with_default_hint() を chain (?演算子で自動 hint 付与)
- 6 件の TDD red→green test (default_hint_covers_all_known_codes /
  with_default_hint_attaches_known_code /
  with_default_hint_does_not_overwrite_explicit_hint /
  with_default_hint_returns_no_hint_for_unknown_code /
  from_io_error_attaches_default_hint /
  from_serde_json_error_attaches_default_hint)

Phase 1/5 (spec docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md §5、commit c3a1ddf 参照)。

Refs #663

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success, 1 file changed.

---

## Phase 2: Rust `lib.rs` mechanical migration

### Task 2.1: Add `.with_default_hint()` chain to all 80 sites

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`

- [ ] **Step 1: Verify the current count is 80**

```bash
grep -c 'AppError::new(' gui/src-tauri/src/lib.rs
```

Expected: `80`. If this number changed (e.g. after a base merge), pause and reconcile with the spec.

- [ ] **Step 2: Apply mechanical chain to all 80 sites**

For each `AppError::new(code, message_expr)` invocation in `gui/src-tauri/src/lib.rs`, append `.with_default_hint()` at the end of the expression chain (before any `?`, `.into()`, or terminating `;`).

Two patterns occur. **Pattern A** (call as expression terminating an `Err(...)` constructor):

```rust
// before
return Err(AppError::new(
    "state.mtime_conflict",
    format!("expected mtime {} got {}", expected, actual),
));

// after
return Err(AppError::new(
    "state.mtime_conflict",
    format!("expected mtime {} got {}", expected, actual),
).with_default_hint());
```

**Pattern B** (used in `.map_err(|_| AppError::new(...))` or `.ok_or_else(|| AppError::new(...))`):

```rust
// before
.map_err(|e| {
    AppError::new(
        "io.read_failed",
        format!("read recent.json: {}", e),
    )
})?;

// after
.map_err(|e| {
    AppError::new(
        "io.read_failed",
        format!("read recent.json: {}", e),
    )
    .with_default_hint()
})?;
```

Approach: walk through the file linearly (search-and-edit). After each batch of ~20 edits, run `cargo check` to surface syntax errors early. Useful command to find remaining sites:

```bash
# Find AppError::new sites that are NOT already followed by .with_default_hint()
grep -n 'AppError::new(' gui/src-tauri/src/lib.rs | head
```

After the walk, verify no site was missed:

```bash
# Count sites that have AppError::new on a line — should be 80
grep -c 'AppError::new(' gui/src-tauri/src/lib.rs
# Count sites that already have .with_default_hint() called somewhere within ~10 lines after AppError::new
# (rough sanity check — every AppError::new should have a corresponding .with_default_hint())
grep -c 'with_default_hint' gui/src-tauri/src/lib.rs
```

Expected after migration: both `80`. If `with_default_hint` count is less, find missing sites by searching `AppError::new` and checking each.

- [ ] **Step 3: Run cargo check to verify compile**

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -30
```

Expected: `Finished` with no errors. Warnings are acceptable but should be reviewed (no new warnings expected — `with_default_hint` returns `Self` so chain is type-compatible).

- [ ] **Step 4: Run full cargo test --lib**

```bash
cd gui/src-tauri && cargo test --lib 2>&1 | tail -20
```

Expected: `test result: ok. 155 passed; 0 failed` (existing 149 + Phase 1 added 6, all still passing — chain is non-breaking since hint is additive).

- [ ] **Step 5: Commit Phase 2**

```bash
cd ../..
git add gui/src-tauri/src/lib.rs
git commit -m "$(cat <<'EOF'
refactor(gui): lib.rs 全 80 site に .with_default_hint() を適用 (Refs #663)

Phase 1 で追加した default_hint_for_code mapping を実際に通すため、lib.rs
の全 80 site の AppError::new(code, msg) 呼び出しに .with_default_hint()
を chain。22 unique codes が production AppError 経由で hint 付き object
として frontend に届くようになる。

mechanical migration のみ。新規ロジックなし、既存 cargo test --lib 155 件
すべて pass (regression なし)。From<io::Error> / From<serde_json::Error>
経路の自動 hint 付与は Phase 1 の impl 改修で完了済。

Phase 2/5 (spec §6 mechanical 章)。

Refs #663

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success, 1 file changed.

---

## Phase 3: Frontend stores (metadataStore + recentStore) + legacy fallback removal

### Task 3.1: Pre-read frontend store + test files

**Files:**

- Read: `gui/src/state/metadataStore.ts` / `recentStore.ts` / corresponding `.test.ts` files

- [ ] **Step 1: Re-read metadataStore.ts**

Identify the 5 catch blocks that produce error state (current line refs from spec § 7):

- `runApply` catch (line 204-214) — sets `applyError` / `conflictError`
- `load` catch (line 262-275) — sets `loadError`
- `restore` catch (line 335-340) — sets `restoreError`
- `saveDraft` catch (line 384-388) — sets `draftSaveError`
- `loadDraft` catch (line 416-421) — sets `draftLoadError`

Note: Each catch must set `*ErrorHint: appErrorHint(e)` in addition to `*Error: appErrorMessage(e)`. The `runApply` catch also branches on conflict — `conflictError` does NOT get a hint (scope-out per spec § 3).

- [ ] **Step 2: Re-read recentStore.ts**

Identify the 2 catch blocks:

- `load` catch (line 59-64) — sets `loadError`
- `add` catch (line 74-76) — sets `addError`

- [ ] **Step 3: Identify the existing 8 conflict test cases in metadataStore.test.ts**

```bash
grep -n "'conflict:" gui/src/state/metadataStore.test.ts
```

Expected: 4-8 lines containing legacy raw-string conflict test cases. Each one needs to be rewritten to construct an `AppError`-shaped object instead.

### Task 3.2: TDD metadataStore *ErrorHint state fields

**Files:**

- Modify: `gui/src/state/metadataStore.ts`
- Modify: `gui/src/state/metadataStore.test.ts`

- [ ] **Step 1: Write 5 failing tests**

Add to `gui/src/state/metadataStore.test.ts` (in a new `describe` block at end of file or grouped with existing apply/load tests):

```typescript
describe('AppError hint pair (#663)', () => {
  beforeEach(() => {
    useMetadataStore.getState().clear();
  });

  it('apply path: applyErrorHint is set when AppError carries hint', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async (cmd) => {
      if (cmd === 'apply_changes') {
        // Tauri rejects with the AppError-shaped object directly
        throw {
          code: 'io.write_failed',
          message: 'disk full',
          hint: 'check free disk space',
        };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      metadata: { source: 'x', matches: [] } as never,
      filePath: '/tmp/m.json',
      loadedMtimeMs: 1000,
    });
    await useMetadataStore.getState().apply();
    const s = useMetadataStore.getState();
    expect(s.applyError).toBe('disk full');
    expect(s.applyErrorHint).toBe('check free disk space');
  });

  it('load path: loadErrorHint is set when AppError carries hint', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async () => {
      throw {
        code: 'io.file_not_found',
        message: 'no such file',
        hint: 'check path',
      };
    });
    await useMetadataStore.getState().load('/tmp/missing.json');
    const s = useMetadataStore.getState();
    expect(s.loadError).toBe('no such file');
    expect(s.loadErrorHint).toBe('check path');
  });

  it('restore path: restoreErrorHint is set', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async (cmd) => {
      if (cmd === 'restore_from_original') {
        throw { code: 'io.backup_failed', message: 'no backup', hint: 'create backup first' };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({ filePath: '/tmp/m.json' });
    await useMetadataStore.getState().restore();
    const s = useMetadataStore.getState();
    expect(s.restoreError).toBe('no backup');
    expect(s.restoreErrorHint).toBe('create backup first');
  });

  it('saveDraft path: draftSaveErrorHint is set', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async (cmd) => {
      if (cmd === 'save_draft') {
        throw { code: 'io.write_failed', message: 'disk full', hint: 'free space' };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      filePath: '/tmp/m.json',
      metadata: { source: 'x', matches: [] } as never,
    });
    await useMetadataStore.getState().saveDraft();
    const s = useMetadataStore.getState();
    expect(s.draftSaveError).toBe('disk full');
    expect(s.draftSaveErrorHint).toBe('free space');
  });

  it('loadDraft path: draftLoadErrorHint is set', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async (cmd) => {
      if (cmd === 'load_draft') {
        throw { code: 'parse.json_invalid', message: 'bad json', hint: 'corrupt draft' };
      }
      throw new Error(`unexpected invoke: ${cmd}`);
    });
    useMetadataStore.setState({
      filePath: '/tmp/m.json',
      metadata: { source: 'x', matches: [] } as never,
    });
    await useMetadataStore.getState().loadDraft();
    const s = useMetadataStore.getState();
    expect(s.draftLoadError).toBe('bad json');
    expect(s.draftLoadErrorHint).toBe('corrupt draft');
  });

  it('legacy raw-Error reject keeps hint null', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async () => {
      throw new Error('plain error string');
    });
    await useMetadataStore.getState().load('/tmp/x.json');
    const s = useMetadataStore.getState();
    expect(s.loadError).toBe('plain error string');
    expect(s.loadErrorHint).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd gui && npm test -- --run metadataStore.test.ts 2>&1 | tail -40
```

Expected: 6 FAIL with `Property 'applyErrorHint' does not exist on type 'MetadataState'` (TypeScript) or `expect(undefined).toBe('check free disk space')` (runtime).

- [ ] **Step 3: Add 5 errorHint state fields + import `appErrorHint`**

In `gui/src/state/metadataStore.ts`:

a) Update import on line 4:

```typescript
import { appErrorCodeIs, appErrorHint, appErrorMessage } from '../lib/appError';
```

b) Add 5 fields to `MetadataState` interface (next to their corresponding `*Error` fields):

```typescript
  loadError: string | null;
  loadErrorHint: string | null;       // ← 新規 (#663)

  applying: boolean;
  applyError: string | null;
  applyErrorHint: string | null;       // ← 新規 (#663)

  // ...

  /** #516: last restore error message, if any. */
  restoreError: string | null;
  /** #663: hint for restoreError, if AppError carried one. */
  restoreErrorHint: string | null;     // ← 新規

  // ...

  /** #517: last draft load error (corrupt draft / parse failure). */
  draftLoadError: string | null;
  /** #663: hint for draftLoadError. */
  draftLoadErrorHint: string | null;   // ← 新規

  draftSaving: boolean;
  // ...
  draftSaveError: string | null;
  /** #663: hint for draftSaveError. */
  draftSaveErrorHint: string | null;   // ← 新規
```

c) Add 5 fields to default state (the `return { ... }` of `create<>` at lines ~217-235):

```typescript
  loadError: null,
  loadErrorHint: null,         // ← 新規
  applying: false,
  applyError: null,
  applyErrorHint: null,        // ← 新規

  hasBackup: false,
  restoring: false,
  restoreError: null,
  restoreErrorHint: null,      // ← 新規

  loadedMtimeMs: null,
  conflictError: null,
  pendingDraft: null,
  draftLoadError: null,
  draftLoadErrorHint: null,    // ← 新規
  draftSaving: false,
  draftSaveError: null,
  draftSaveErrorHint: null,    // ← 新規
```

d) Update the `clear()` action (line ~305) to reset all 5 hint fields:

```typescript
  clear: () => {
    cancelDraftSave();
    set({
      metadata: null,
      filePath: null,
      dirty: false,
      loadError: null,
      loadErrorHint: null,
      applying: false,
      applyError: null,
      applyErrorHint: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      restoreErrorHint: null,
      loadedMtimeMs: null,
      conflictError: null,
      pendingDraft: null,
      draftLoadError: null,
      draftLoadErrorHint: null,
      draftSaving: false,
      draftSaveError: null,
      draftSaveErrorHint: null,
    });
  },
```

e) Update `loadSample()` action (line ~471) similarly:

```typescript
  loadSample: () => {
    cancelDraftSave();
    set({
      metadata: sampleMetadata,
      filePath: null,
      dirty: false,
      loadError: null,
      loadErrorHint: null,
      applying: false,
      applyError: null,
      applyErrorHint: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      restoreErrorHint: null,
      loadedMtimeMs: null,
      conflictError: null,
      pendingDraft: null,
      draftLoadError: null,
      draftLoadErrorHint: null,
      draftSaving: false,
      draftSaveError: null,
      draftSaveErrorHint: null,
    });
  },
```

- [ ] **Step 4: Update each catch block to set hint**

In `gui/src/state/metadataStore.ts`:

a) `runApply` catch (line ~204-214):

```typescript
    } catch (e) {
      const msg = appErrorMessage(e);
      const hint = appErrorHint(e);
      // #663: PR #665 で全 23 commands が AppError 化済のため、legacy raw String
      // fallback (msg.startsWith('conflict:')) は廃止する。code === 'state.mtime_conflict'
      // のみで分岐する。
      if (appErrorCodeIs(e, 'state.mtime_conflict')) {
        set({ applying: false, conflictError: msg });
      } else {
        set({ applying: false, applyError: msg, applyErrorHint: hint });
      }
    }
```

b) `load` catch (line ~262-275):

```typescript
    } catch (e) {
      set({
        metadata: null,
        filePath: null,
        dirty: false,
        loadError: appErrorMessage(e),
        loadErrorHint: appErrorHint(e),
        hasBackup: false,
        loadedMtimeMs: null,
        conflictError: null,
        pendingDraft: null,
        draftLoadError: null,
        draftSaveError: null,
      });
    }
```

c) `restore` catch (line ~335-340):

```typescript
    } catch (e) {
      set({
        restoring: false,
        restoreError: appErrorMessage(e),
        restoreErrorHint: appErrorHint(e),
      });
    }
```

d) `saveDraft` catch (line ~384-388):

```typescript
    } catch (e) {
      // Surface the failure via state — scheduleDraftSave's fire-and-forget
      // call would otherwise swallow the rejection silently (see F1 review).
      set({ draftSaveError: appErrorMessage(e), draftSaveErrorHint: appErrorHint(e) });
    } finally {
      set({ draftSaving: false });
    }
```

e) `loadDraft` catch (line ~416-421):

```typescript
    } catch (e) {
      set({
        pendingDraft: null,
        draftLoadError: appErrorMessage(e),
        draftLoadErrorHint: appErrorHint(e),
      });
    }
```

f) Also clear `*ErrorHint` on success paths where existing code clears `*Error`. Specifically in `load` success (line ~244-256), add hint clears:

```typescript
      set({
        metadata: parsed as unknown as Metadata,
        filePath: path,
        dirty: false,
        loadError: null,
        loadErrorHint: null,         // ← 追加
        applyError: null,
        applyErrorHint: null,        // ← 追加
        restoreError: null,
        restoreErrorHint: null,      // ← 追加
        loadedMtimeMs: mtime ?? null,
        conflictError: null,
        pendingDraft: null,
        draftLoadError: null,
        draftLoadErrorHint: null,    // ← 追加
        draftSaveError: null,
        draftSaveErrorHint: null,    // ← 追加
      });
```

`runApply` success (line ~191-198): the existing reset clears `applyError: null`, add `applyErrorHint: null`:

```typescript
      set({
        metadata: normalized,
        dirty: false,
        applying: false,
        applyError: null,
        applyErrorHint: null,       // ← 追加
        loadedMtimeMs: newMtime,
        conflictError: null,
      });
```

`runApply` start (line ~183) `set({ applying: true, applyError: null, conflictError: null })`:

```typescript
    set({ applying: true, applyError: null, applyErrorHint: null, conflictError: null });
```

`restore` start (line ~329) `set({ restoring: true, restoreError: null })`:

```typescript
    set({ restoring: true, restoreError: null, restoreErrorHint: null });
```

`saveDraft` start (line ~381) `set({ draftSaving: true, draftSaveError: null })`:

```typescript
    set({ draftSaving: true, draftSaveError: null, draftSaveErrorHint: null });
```

`loadDraft` early returns on null/stale draft (line ~399, ~412): add `draftLoadErrorHint: null` alongside `draftLoadError: null`:

```typescript
        set({ pendingDraft: null, draftLoadError: null, draftLoadErrorHint: null });
```

(both occurrences in loadDraft).

Successful loadDraft (line ~415):

```typescript
      set({ pendingDraft: parsed, draftLoadError: null, draftLoadErrorHint: null });
```

- [ ] **Step 5: Run tests to verify pass**

```bash
cd gui && npm test -- --run metadataStore.test.ts 2>&1 | tail -30
```

Expected: 6 new tests PASS. Existing tests still pass (regression check).

### Task 3.3: Remove legacy `startsWith('conflict:')` fallback + rewrite affected tests

**Files:**

- Modify: `gui/src/state/metadataStore.ts` (the line was already touched in Task 3.2, but verify the legacy clause is fully gone)
- Modify: `gui/src/state/metadataStore.test.ts`
- Modify: `gui/src/components/ConflictModal.test.tsx`

- [ ] **Step 1: Verify legacy fallback is gone**

```bash
grep -n "startsWith('conflict:')" gui/src/state/metadataStore.ts
```

Expected: no matches (already removed in Task 3.2 step 4a).

```bash
grep -n "msg.startsWith\|conflict:" gui/src/state/metadataStore.ts
```

Expected: only references in comments referring to the old behavior (e.g. "PR #665 で全 23 commands が AppError 化済のため、legacy raw String fallback (msg.startsWith('conflict:')) は廃止"). No production guard remains.

- [ ] **Step 2: Rewrite legacy `'conflict: ...'` test cases in metadataStore.test.ts**

```bash
grep -n "'conflict:" gui/src/state/metadataStore.test.ts
```

For each match, the legacy form is one of:

```typescript
// pattern A: mock invoke rejecting with raw Error
apply_changes_error: new Error('conflict: external modification detected (expected mtime 1700, got 1800)'),

// pattern B: direct setState for ConflictModal-type tests
useMetadataStore.setState({ conflictError: 'conflict: x', dirty: true });
```

Convert pattern A to AppError-shaped reject object:

```typescript
apply_changes_error: { code: 'state.mtime_conflict', message: 'external modification detected (expected mtime 1700, got 1800)' },
```

Convert pattern B by removing the `'conflict:'` prefix from the message:

```typescript
useMetadataStore.setState({ conflictError: 'x', dirty: true });
```

The matching `expect(state.conflictError).toContain('conflict:')` assertions should change to assert the message body (e.g. `expect(state.conflictError).toContain('external modification')`).

Walk through every grep'd line, applying the transform. Also handle the `apply_changes_error: new Error('conflict: stale')` patterns identically.

- [ ] **Step 3: Run tests to verify metadataStore.test.ts passes**

```bash
cd gui && npm test -- --run metadataStore.test.ts 2>&1 | tail -30
```

Expected: all tests PASS. If a test still fails because the conflict branch is taken on a non-conflict mock, double-check that the mock's reject shape is `{ code: 'state.mtime_conflict', message: ... }` and not the legacy raw string.

- [ ] **Step 4: Fix ConflictModal.test.tsx test data**

```bash
grep -n "'conflict:" gui/src/components/ConflictModal.test.tsx
```

For each match like `conflictError: 'conflict: external modification detected'`, drop the `conflict:` prefix:

```typescript
// before
useMetadataStore.setState({ conflictError: 'conflict: external modification detected' });
expect(screen.getByText(/conflict: external/)).toBeInTheDocument();

// after
useMetadataStore.setState({ conflictError: 'external modification detected' });
expect(screen.getByText(/external/)).toBeInTheDocument();
```

(The modal renders the message verbatim — the test was simply asserting on a string substring.)

- [ ] **Step 5: Run ConflictModal tests**

```bash
cd gui && npm test -- --run ConflictModal.test.tsx 2>&1 | tail -20
```

Expected: all PASS.

### Task 3.4: TDD recentStore hint pair

**Files:**

- Modify: `gui/src/state/recentStore.ts`
- Modify or create: `gui/src/state/recentStore.test.ts`

- [ ] **Step 1: Write 2 failing tests**

Add to `gui/src/state/recentStore.test.ts` (new tests at end of file):

```typescript
describe('AppError hint pair (#663)', () => {
  beforeEach(() => {
    useRecentStore.getState().reset();
  });

  it('load path: loadErrorHint is set when AppError carries hint', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async () => {
      throw {
        code: 'io.read_failed',
        message: 'broken recent.json',
        hint: 'delete the file and restart',
      };
    });
    await useRecentStore.getState().load();
    const s = useRecentStore.getState();
    expect(s.loadError).toBe('broken recent.json');
    expect(s.loadErrorHint).toBe('delete the file and restart');
  });

  it('add path: addErrorHint is set when AppError carries hint', async () => {
    const mockInvoke = vi.mocked(invoke);
    mockInvoke.mockImplementation(async () => {
      throw {
        code: 'io.write_failed',
        message: 'recent.json write failed',
        hint: 'check disk space',
      };
    });
    await useRecentStore.getState().add('/tmp/x.mp4');
    const s = useRecentStore.getState();
    expect(s.addError).toBe('recent.json write failed');
    expect(s.addErrorHint).toBe('check disk space');
  });
});
```

If `recentStore.test.ts` already exists, append these inside (or alongside) existing describe blocks. If not, create the file with the necessary imports (`vi`, `useRecentStore`, `invoke`, etc — pattern from `metadataStore.test.ts`).

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd gui && npm test -- --run recentStore.test.ts 2>&1 | tail -20
```

Expected: 2 FAIL (`addErrorHint` / `loadErrorHint` not in state).

- [ ] **Step 3: Add hint pair to recentStore.ts**

Modify `gui/src/state/recentStore.ts`:

a) Update import (line 4):

```typescript
import { appErrorHint, appErrorMessage } from '../lib/appError';
```

b) Update `RecentState` interface to add `loadErrorHint` / `addErrorHint`:

```typescript
export interface RecentState {
  entries: RecentEntry[];
  loaded: boolean;
  loadError: string | null;
  /** #663: hint for loadError, if AppError carried one. */
  loadErrorHint: string | null;
  addError: string | null;
  /** #663: hint for addError. */
  addErrorHint: string | null;

  load: () => Promise<void>;
  add: (path: string) => Promise<void>;
  clear: () => Promise<void>;
  reset: () => void;
}
```

c) Update default state in `create<RecentState>((set) => ({ ... }))` (line ~43):

```typescript
  entries: [],
  loaded: false,
  loadError: null,
  loadErrorHint: null,    // ← 新規
  addError: null,
  addErrorHint: null,     // ← 新規
```

d) Update `load` catch (line ~59-64):

```typescript
    } catch (e) {
      set({
        loadError: appErrorMessage(e),
        loadErrorHint: appErrorHint(e),
        loaded: true,
      });
    }
```

e) Update `add` catch (line ~74-76):

```typescript
    } catch (e) {
      set({ addError: appErrorMessage(e), addErrorHint: appErrorHint(e) });
    }
```

f) Update success paths to clear hint (line ~58 for load, ~73 for add):

```typescript
      set({ entries, loaded: true, loadError: null, loadErrorHint: null });
      // ...
      set({ entries, addError: null, addErrorHint: null });
```

g) Update `clear` (line ~80) and `reset` (line ~84) to clear hint:

```typescript
  async clear() {
    await invoke<void>('clear_recent');
    set({ entries: [], loadError: null, loadErrorHint: null, addError: null, addErrorHint: null });
  },

  reset() {
    set({ entries: [], loaded: false, loadError: null, loadErrorHint: null, addError: null, addErrorHint: null });
  },
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd gui && npm test -- --run recentStore.test.ts 2>&1 | tail -20
```

Expected: 2 new tests PASS, existing tests still PASS.

### Task 3.5: Phase 3 full test pass + commit

- [ ] **Step 1: Run full vitest**

```bash
cd gui && npm test -- --run 2>&1 | tail -30
```

Expected: all tests PASS (existing ~566 + new ~13 = ~580). If any failing, identify by name and fix.

- [ ] **Step 2: Run typecheck**

```bash
cd gui && npm run typecheck 2>&1 | tail -10
```

Expected: exit 0, no errors.

- [ ] **Step 3: Commit Phase 3**

```bash
cd ..
git add gui/src/state/metadataStore.ts gui/src/state/metadataStore.test.ts gui/src/state/recentStore.ts gui/src/state/recentStore.test.ts gui/src/components/ConflictModal.test.tsx
git commit -m "$(cat <<'EOF'
feat(gui): metadataStore / recentStore に *ErrorHint state を追加 + legacy fallback 削除 (Refs #663)

PR #665 で全 23 commands が Result<T, AppError> 化済のため、
metadataStore.ts:209 の legacy raw String fallback
`|| msg.startsWith('conflict:')` を撤去。code === 'state.mtime_conflict'
のみで ConflictModal 経路に分岐するシンプルな state machine に。

主な変更:

- metadataStore: loadErrorHint / applyErrorHint / restoreErrorHint /
  draftSaveErrorHint / draftLoadErrorHint の 5 state field を追加。
  各 catch block で appErrorHint(e) を取り込み、success path で null clear
- recentStore: loadErrorHint / addErrorHint を追加 (同パターン)
- conflictError には hint pair を追加しない (ConflictModal は spec § 3 で
  scope 外、modal 既存 compose hint と概念衝突回避)
- TDD red→green: metadataStore に新規 6 件 + recentStore に新規 2 件
- 既存 conflict 文字列ベース test (metadataStore.test.ts 8 件 +
  ConflictModal.test.tsx 6 件) を AppError object 形式 / prefix 削除版に書き換え

Phase 3/5 (spec §7)。

Refs #663

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success, 5 files changed.

---

## Phase 4: Frontend UI (5 screens + RestoreButton + CSS)

### Task 4.1: Add `.errorHint` shared CSS class

**Files:**

- Modify: `gui/src/styles/tokens.css` (token-only, no new selectors) — ALREADY has `--ae-text-dim`, no change needed
- Modify: `gui/src/components/RestoreButton.module.css` (new `.errorHint` class)
- (各 screen の `.module.css` でも同様の `.errorHint` を追加)

The pattern: each component defines its own `.errorHint` selector that uses the existing `--ae-text-dim` token. We do NOT introduce a new global utility class — keep CSS module isolation.

- [ ] **Step 1: Add `.errorHint` to RestoreButton.module.css**

Edit `gui/src/components/RestoreButton.module.css`. Append after the existing `.error` class (line 30-35):

```css
.errorHint {
  font-family: var(--ae-font-body);
  font-size: 10px;
  color: var(--ae-text-dim);
  margin-left: 8px;
  margin-top: 2px;
  display: block;
  line-height: 1.5;
}
```

- [ ] **Step 2: Add `.errorHint` to other module.css files used by error display**

For each of the following files, add a similar `.errorHint` class (style harmonized with the file's existing `.error` / `.errorMessage` selectors):

| File | Place after | Exact addition |
| --- | --- | --- |
| `gui/src/screens/DropScreen.module.css` | existing `.error` selector | `.errorHint { color: var(--ae-text-dim); font-size: 12px; margin-top: 6px; line-height: 1.5; }` |
| `gui/src/screens/DetectingScreen.module.css` | existing `.errorMessage` | `.errorHint { color: var(--ae-text-dim); font-size: 12px; margin-top: 8px; line-height: 1.5; }` |
| `gui/src/screens/PreviewScreen.module.css` | existing `.applyError` | `.applyErrorHint { color: var(--ae-text-dim); font-size: 11px; margin-left: 8px; line-height: 1.5; }` |
| `gui/src/screens/ExportScreen.module.css` | existing `.listError` | `.listErrorHint { color: var(--ae-text-dim); font-size: 11px; line-height: 1.5; display: block; margin-top: 2px; }` |

If any of these `.module.css` files lacks the "place after" anchor selector, search for `role="alert"` usage in the corresponding `.tsx` file and add the new class with a sensible local style.

- [ ] **Step 3: Verify lint passes**

```bash
cd gui && npm run lint 2>&1 | tail -10
```

Expected: exit 0.

### Task 4.2: TDD RestoreButton hint 2nd line

**Files:**

- Modify: `gui/src/components/RestoreButton.tsx`
- Modify: `gui/src/components/RestoreButton.test.tsx`

- [ ] **Step 1: Write 2 failing tests**

Add to `gui/src/components/RestoreButton.test.tsx`:

```typescript
describe('hint rendering (#663)', () => {
  it('renders restoreErrorHint as 2nd line when present', () => {
    useMetadataStore.setState({
      hasBackup: true,
      restoring: false,
      restoreError: 'backup not found',
      restoreErrorHint: 'create backup first',
    });
    render(<RestoreButton />);
    expect(screen.getByText('backup not found')).toBeInTheDocument();
    expect(screen.getByText(/create backup first/)).toBeInTheDocument();
  });

  it('does not render hint when restoreErrorHint is null', () => {
    useMetadataStore.setState({
      hasBackup: true,
      restoring: false,
      restoreError: 'plain message',
      restoreErrorHint: null,
    });
    render(<RestoreButton />);
    expect(screen.getByText('plain message')).toBeInTheDocument();
    expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd gui && npm test -- --run RestoreButton.test.tsx 2>&1 | tail -15
```

Expected: 2 FAIL.

- [ ] **Step 3: Update RestoreButton.tsx to render hint as 2nd line**

In `gui/src/components/RestoreButton.tsx`, change line 53 (`const restoreError = ...`) and the bottom render block:

```typescript
  const restoreError = useMetadataStore((s) => s.restoreError);
  const restoreErrorHint = useMetadataStore((s) => s.restoreErrorHint);
```

Update the JSX (line 92-97):

```tsx
      {restoreError && (
        <span className={styles.error} role="alert">
          {restoreError}
          {restoreErrorHint && (
            <span className={styles.errorHint}>💡 {restoreErrorHint}</span>
          )}
        </span>
      )}
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd gui && npm test -- --run RestoreButton.test.tsx 2>&1 | tail -15
```

Expected: 2 PASS, existing tests still PASS.

### Task 4.3: TDD DropScreen hint 2nd line + local errorHint state

**Files:**

- Modify: `gui/src/screens/DropScreen.tsx`
- Modify: `gui/src/screens/DropScreen.test.tsx`

- [ ] **Step 1: Write 1 failing test**

Add to `gui/src/screens/DropScreen.test.tsx` (in an existing describe or a new "hint rendering (#663)"):

```typescript
it('renders error hint as 2nd line when probe rejects with AppError', async () => {
  const mockInvoke = vi.mocked(invoke);
  mockInvoke.mockImplementation(async (cmd) => {
    if (cmd === 'probe_video') {
      throw {
        code: 'parse.ffprobe_output_invalid',
        message: 'ffprobe failed',
        hint: 'check ffmpeg version',
      };
    }
    throw new Error('unexpected');
  });

  render(<DropScreen />);
  // (simulate the probe trigger — adapt to existing test helpers; this may
  // require `await user.upload(...)` or calling the underlying handler.)
  // For brevity, we directly call setError analog by rendering the error card:
  //   alternative: test ErrorCard component in isolation if exposed.

  // Skeleton:
  await waitFor(() => {
    expect(screen.getByText('ffprobe failed')).toBeInTheDocument();
    expect(screen.getByText(/check ffmpeg version/)).toBeInTheDocument();
  });
});
```

Adapt to whatever test helpers DropScreen.test.tsx already uses for triggering probe failure.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gui && npm test -- --run DropScreen.test.tsx 2>&1 | tail -20
```

Expected: FAIL.

- [ ] **Step 3: Update DropScreen.tsx**

In `gui/src/screens/DropScreen.tsx`:

a) Add import for `appErrorHint`:

```typescript
import { appErrorHint, appErrorMessage } from '../lib/appError';
```

b) Add local `errorHint` state next to the existing `error` state (line ~129):

```typescript
const [error, setError] = useState<string | null>(null);
const [errorHint, setErrorHint] = useState<string | null>(null);
```

c) Update the catch blocks at lines ~142, ~164 (the patterns `setError(e instanceof Error ? e.message : String(e))`) to also set `errorHint`:

```typescript
} catch (e) {
  setError(appErrorMessage(e));
  setErrorHint(appErrorHint(e));
}
```

d) Update `setError(null)` calls (lines 133, 159, 265) to also reset `errorHint`:

```typescript
setError(null);
setErrorHint(null);
```

e) Update `ErrorCardProps` to receive `errorHint` and render it (line ~475):

```typescript
interface ErrorCardProps {
  error: string | null;
  errorHint: string | null;          // ← 新規
  onDismiss: () => void;
  onRetry: () => void;
}

function ErrorCard({ error, errorHint, onDismiss, onRetry }: ErrorCardProps) {
  // ... existing hooks ...
  return (
    <div ref={cardRef} className={styles.selectedCard} role="alert" data-testid="drop-error-card">
      <div className={styles.selectedHeading}>エラー</div>
      <div className={styles.error}>{error ?? 'probe failed'}</div>
      {errorHint && (
        <div className={styles.errorHint}>💡 {errorHint}</div>
      )}
      <div className={styles.actions}>
        {/* existing buttons */}
      </div>
    </div>
  );
}
```

f) Update the `ErrorCard` callsite in DropScreen to pass `errorHint`:

```typescript
<ErrorCard error={error} errorHint={errorHint} onDismiss={...} onRetry={...} />
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd gui && npm test -- --run DropScreen.test.tsx 2>&1 | tail -20
```

Expected: new test PASS, existing tests still PASS.

### Task 4.4: TDD DetectingScreen hint 2nd line + local errorHint state

**Files:**

- Modify: `gui/src/screens/DetectingScreen.tsx`
- Modify: `gui/src/screens/DetectingScreen.test.tsx`

- [ ] **Step 1: Write 1 failing test**

Add to `gui/src/screens/DetectingScreen.test.tsx`:

```typescript
it('renders error hint as 2nd line when start_detect rejects with AppError', async () => {
  const mockInvoke = vi.mocked(invoke);
  mockInvoke.mockImplementation(async (cmd) => {
    if (cmd === 'start_detect') {
      throw {
        code: 'subprocess.spawn_failed',
        message: 'failed to spawn allaganeye CLI',
        hint: 'verify Python install',
      };
    }
    throw new Error('unexpected');
  });

  // (render DetectingScreen with a fixture videoPath and let useEffect trigger the start_detect call.)
  render(<DetectingScreen video={...} />);
  await waitFor(() => {
    expect(screen.getByText(/failed to spawn/)).toBeInTheDocument();
    expect(screen.getByText(/verify Python/)).toBeInTheDocument();
  });
});
```

Adapt to existing test helpers / fixture pattern.

- [ ] **Step 2: Run to verify FAIL**

```bash
cd gui && npm test -- --run DetectingScreen.test.tsx 2>&1 | tail -20
```

- [ ] **Step 3: Update DetectingScreen.tsx**

a) Import `appErrorHint`:

```typescript
import { appErrorHint, appErrorMessage } from '../lib/appError';
```

b) Add local `errorHint` state next to `error` (line ~274):

```typescript
const [error, setError] = useState<string | null>(null);
const [errorHint, setErrorHint] = useState<string | null>(null);
```

c) Update the catch / setError sites (line ~322, 349 etc.) to set `errorHint`:

```typescript
setError(null);
setErrorHint(null);
// ...
} catch (e) {
  const msg = appErrorMessage(e);
  setError(msg);
  setErrorHint(appErrorHint(e));
}
```

d) Update the error render block (line ~733-741):

```tsx
<div className={styles.errorScreen} data-testid="detecting-error" role="alert">
  <div className={styles.errorHeading}>検知に失敗しました</div>
  <div className={styles.errorFile}>{displayFile}</div>
  <pre className={styles.errorMessage} data-testid="detecting-error-message">
    {error ?? 'unknown error'}
  </pre>
  {errorHint && (
    <div className={styles.errorHint} data-testid="detecting-error-hint">
      💡 {errorHint}
    </div>
  )}
  <div className={styles.actions}>
    {/* existing retry / back buttons */}
  </div>
</div>
```

- [ ] **Step 4: Run to verify PASS**

```bash
cd gui && npm test -- --run DetectingScreen.test.tsx 2>&1 | tail -20
```

### Task 4.5: TDD PreviewScreen hint 2nd line (uses store)

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx`
- Modify: `gui/src/screens/PreviewScreen.test.tsx`

- [ ] **Step 1: Write 1 failing test**

Add to `gui/src/screens/PreviewScreen.test.tsx`:

```typescript
it('renders applyErrorHint inline when present', () => {
  useMetadataStore.setState({
    metadata: { source: 'x', matches: [] } as never,
    filePath: '/tmp/m.json',
    applyError: 'disk full',
    applyErrorHint: 'free up space',
  });
  render(<PreviewScreen />);
  expect(screen.getByText('disk full')).toBeInTheDocument();
  expect(screen.getByText(/free up space/)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Update PreviewScreen.tsx**

a) Subscribe to `applyErrorHint` (next to existing `applyError` subscription on line 91):

```typescript
const applyError = useMetadataStore((s) => s.applyError);
const applyErrorHint = useMetadataStore((s) => s.applyErrorHint);
```

b) Update the inline error render (line 649-653):

```tsx
{applyError && (
  <span className={styles.applyError} role="alert">
    {applyError}
    {applyErrorHint && (
      <span className={styles.applyErrorHint}>💡 {applyErrorHint}</span>
    )}
  </span>
)}
```

- [ ] **Step 4: Run to verify PASS**

```bash
cd gui && npm test -- --run PreviewScreen.test.tsx 2>&1 | tail -15
```

### Task 4.6: TDD ExportScreen per-match hint + reducer update

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx`
- Modify: `gui/src/screens/ExportScreen.test.tsx`

- [ ] **Step 1: Write 1 failing test**

Add to `gui/src/screens/ExportScreen.test.tsx`:

```typescript
it('renders per-match error hint when export rejects with AppError', async () => {
  const mockInvoke = vi.mocked(invoke);
  mockInvoke.mockImplementation(async (cmd) => {
    if (cmd === 'export_match') {
      throw {
        code: 'subprocess.spawn_failed',
        message: 'ffmpeg spawn failed',
        hint: 'reinstall ffmpeg',
      };
    }
    throw new Error('unexpected');
  });

  // (render ExportScreen with a single-match fixture and trigger the export.)
  // Skeleton — adapt to existing patterns:
  // ...
  await waitFor(() => {
    expect(screen.getByText(/ffmpeg spawn failed/)).toBeInTheDocument();
    expect(screen.getByText(/reinstall ffmpeg/)).toBeInTheDocument();
  });
});
```

Adapt to ExportScreen's existing test setup (it uses a `matchStates` reducer with a per-match `error` field; the test should hit the catch at line ~358).

- [ ] **Step 2: Run to verify FAIL**

- [ ] **Step 3: Update ExportScreen.tsx**

a) Import `appErrorHint`:

```typescript
import { appErrorHint, appErrorMessage } from '../lib/appError';
```

b) Extend the per-match state row type with `errorHint: string | null`. Find the type definition (search `error?:` or `status:` near line 250) and add:

```typescript
interface MatchExportState {
  status: 'idle' | 'running' | 'done' | 'error';
  percent: number;
  error?: string;
  errorHint?: string;     // ← 新規
  fallbackNotice?: string;
  outputPath?: string;
}
```

c) Update the reducer / event handler at line ~258-260 (event-driven path):

```typescript
return {
  ...prev,
  [p.match_index]: {
    ...prior,
    status,
    percent: p.percent,
    error: p.stage === 'error' ? p.message : prior.error,
    errorHint: p.stage === 'error' ? (p.hint ?? null) : prior.errorHint,  // ← 新規 (event from Rust may include hint)
    fallbackNotice,
  },
};
```

(If the `export-progress` event payload doesn't include `hint`, this falls back to `null`. Future Rust-side enhancement can attach hint to event payloads — out of #663 scope.)

d) Update the `catch (e)` block at line ~352-359:

```typescript
} catch (e) {
  failureCount += 1;
  const msg = appErrorMessage(e);
  const hint = appErrorHint(e);
  setMatchStates((prev) => ({
    ...prev,
    [m.index]: { status: 'error', percent: 0, error: msg, errorHint: hint ?? undefined },
  }));
}
```

e) Update the per-match render at line ~859-861:

```tsx
{s.status === 'error' && s.error && (
  <span className={styles.listError} role="alert">
    {s.error.slice(0, 120)}
    {s.errorHint && (
      <span className={styles.listErrorHint}>💡 {s.errorHint}</span>
    )}
  </span>
)}
```

- [ ] **Step 4: Run to verify PASS**

```bash
cd gui && npm test -- --run ExportScreen.test.tsx 2>&1 | tail -15
```

### Task 4.7: Phase 4 full test pass + commit

- [ ] **Step 1: Run full vitest, lint, typecheck, build**

```bash
cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build 2>&1 | tail -30
```

Expected: all pass. If any failure, identify and fix.

- [ ] **Step 2: Commit Phase 4**

```bash
cd ..
git add gui/src/components/RestoreButton.tsx gui/src/components/RestoreButton.module.css gui/src/components/RestoreButton.test.tsx gui/src/screens/DropScreen.tsx gui/src/screens/DropScreen.module.css gui/src/screens/DropScreen.test.tsx gui/src/screens/DetectingScreen.tsx gui/src/screens/DetectingScreen.module.css gui/src/screens/DetectingScreen.test.tsx gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.module.css gui/src/screens/PreviewScreen.test.tsx gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.module.css gui/src/screens/ExportScreen.test.tsx
git commit -m "$(cat <<'EOF'
feat(gui): 各 screen の inline error に hint 2 行目を追加 (Refs #663)

Phase 3 で frontend store に追加した *ErrorHint state を、各 screen の
inline error 表示で 2 行目として render する。`var(--ae-text-dim)` 色で
1 行目 (赤系 error message) と区別され、user に対処方法を示す UX。

主な変更:

- RestoreButton: restoreErrorHint を span に追加 render
- DropScreen: local errorHint state を追加、ErrorCard に渡す
- DetectingScreen: local errorHint state、 errorScreen 内で render
- PreviewScreen: store applyErrorHint を inline error に追加
- ExportScreen: per-match reducer state を errorHint 拡張、listError 内で render
- 各 .module.css に `.errorHint` (or 派生) class を追加 (var(--ae-text-dim) 利用)
- TDD red→green: 各 screen + RestoreButton で計 6 件の新規 test

a11y: role="alert" は wrapper に維持、hint は補足情報として 2 行目に
連続させる (jest-axe で violation なし)。

Phase 4/5 (spec §8)。

Refs #663

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success.

---

## Phase 5: Docs + Issue body

### Task 5.1: Update docs/tauri-commands.md

**Files:**

- Modify: `docs/tauri-commands.md`

- [ ] **Step 1: Add hint mapping table at end of file**

Append the following section after the existing master command table (verify exact insertion point with `tail -20 docs/tauri-commands.md`):

```markdown
## AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)

> 本 table の文言は `gui/src-tauri/src/error.rs` の `default_hint_for_code()` と
> 完全一致させる (#692 で CI integrity check 化済 = `.github/scripts/check-error-hint-drift.sh`
> + `doc-error-hint-drift` job、文言変更時は両方を同 PR で更新する規約)。

| code | hint |
| --- | --- |
| `state.mtime_conflict` | metadata.json が他のプロセスで書き換えられました。「リロード」で最新を読み直すか、「上書き」で現在の編集を強制適用してください |
| `io.file_not_found` | ファイルが見つかりません。パスを確認するか、allaganeye split を再実行してください |
| `io.read_failed` | ファイルの読み込みに失敗しました。ディスク状況・ファイルロック状態を確認してください |
| `io.write_failed` | ファイルの書き込みに失敗しました。空き容量と書き込み権限 (Portable ZIP の install dir が user-writable か) を確認してください |
| `io.delete_failed` | ファイル / フォルダの削除に失敗しました。他プロセスでロックされていないか確認してください |
| `io.backup_failed` | バックアップファイルの作成に失敗しました。allaganeye 出力フォルダの空き容量と書き込み権限を確認してください |
| `io.permission_denied` | ファイルへのアクセス権限がありません。Portable ZIP install dir が user-writable な場所か、ファイル / フォルダが読み取り専用でないか確認してください |
| `io.already_exists` | ファイルが既に存在します。出力先を変更するか既存ファイルを削除してください |
| `io.would_block` / `io.timed_out` | I/O 処理がタイムアウト / ブロックされました。少し時間をおいて再試行してください |
| `io.error` | I/O エラーが発生しました。詳細は logs フォルダを確認してください |
| `parse.json_invalid` | JSON ファイルが破損しています。バックアップ (.bak) からの復元か allaganeye split のやり直しを検討してください |
| `parse.json_serialize_failed` | JSON 書き出しに失敗しました。同梱 issue テンプレートでバグ報告してください |
| `parse.schema_invalid` | metadata.json の構造が期待形式と異なります。allaganeye のバージョンと metadata 生成バージョンが一致しているか確認してください |
| `parse.ffprobe_output_invalid` | ffprobe の出力を解釈できませんでした。ffmpeg / ffprobe を最新の BtbN LGPL ビルドに更新してください |
| `subprocess.spawn_failed` | 外部プロセスの起動に失敗しました。ffmpeg / Python / 同梱 runtime が壊れていないか確認してください |
| `subprocess.exit_failed` | 外部プロセスが異常終了しました。logs フォルダの最新ログから詳細を確認してください |
| `subprocess.cancelled` | (hint なし: ユーザー操作によるキャンセルは UI 側で十分な情報を出す) |
| `validation.path_invalid` | 入力されたパスが不正です。ファイル名と拡張子を確認してください (対応: mp4 / mkv / mov / m4v) |
| `validation.not_a_file` | 指定されたパスはファイルではありません (フォルダや symlink ではなく動画ファイルを選択してください) |
| `validation.range_invalid` | 入力された数値が許容範囲外です。フォーム下のヒント表示を確認してください |
| `path.install_dir_unresolved` | Portable ZIP の install dir を特定できませんでした。allaganeye-gui.exe を ZIP 展開後の元のフォルダ構成のまま起動してください |
| `platform.unsupported` | 本機能は現在の OS では未対応です。Windows での起動が必要です |
| `internal.error` | (hint なし: 内部エラーで具体的アクションがない、message 側で logs 参照を案内) |
```

### Task 5.2: Update docs/ui-architecture.md § 4

**Files:**

- Modify: `docs/ui-architecture.md`

- [ ] **Step 1: Append §4.x at end of section §4 (line ~53)**

Locate the existing `## 4. エラー伝搬フロー (#614)` section. Append a new sub-section at the end of it (before the next `## 5.` section):

```markdown
### 4.x AppError code 体系と inline error の使い分け (#663)

Tauri command の `Result<T, AppError>` で frontend に届く構造化 error は、
`docs/tauri-commands.md` で master 一覧化されている。inline error 表示時は
`appErrorMessage(e)` を 1 行目に、`appErrorHint(e)` を 2 行目 (`var(--ae-text-dim)`)
に render する規約。code → default hint の mapping は
`gui/src-tauri/src/error.rs::default_hint_for_code` で一元管理。

#### 主な分岐ルール

- `code === 'state.mtime_conflict'` → ConflictModal を出す (apply path のみ)
- それ以外の `code` → inline error (2 行目に hint があれば render)
- legacy raw String (= AppError 化前の commands) → `appErrorMessage` で
  message のみ取得、hint は null になる (PR #663 で legacy raw を返す
  command は存在しないが、helper の互換性として温存)
```

### Task 5.3: Update docs/ui-interaction-spec.md § 1.5

**Files:**

- Modify: `docs/ui-interaction-spec.md`

- [ ] **Step 1: Append §1.5.x at end of section §1.5 (line ~80-100)**

Locate the existing `### 1.5 エラー表示の一貫性 (inline + toast)` section. Append a new sub-section after the existing content but before §1.6 (or the next top-level §2):

```markdown
#### 1.5.x AppError `code` ベースの分岐ルール (#663)

Tauri command 失敗時の error 表示は以下を厳守する:

1. `appErrorCodeIs(e, 'state.mtime_conflict')` で apply path → ConflictModal (modal 表示)
2. その他の AppError code → inline error
   - 1 行目: `appErrorMessage(e)` (赤系: `var(--ae-text-error)` ないし screen 固有 error 色)
   - 2 行目: `appErrorHint(e)` (灰系: `var(--ae-text-dim)`、`💡` 等の prefix で
     アクション提示と分かるように)
3. catch ブロック以外で error を扱わない (`alert()` / `console.error` のみは禁止)
4. globalErrorListener が拾うのは uncaught (window.error / unhandledrejection /
   panic) のみ。catch 済 Tauri command error は ErrorModal に出さない (規約)
```

### Task 5.4: Run markdownlint

- [ ] **Step 1: Run markdownlint**

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -10
```

Expected: `Summary: 0 error(s)`. Fix any reported issues inline.

### Task 5.5: Update issue #663 body

**Files:**

- External: `gh issue edit 663`

- [ ] **Step 1: Compose new issue body**

Use `printf` + `--body-file -` to avoid Japanese inline encoding issues (per `feedback_gh_command_ja_heredoc.md`):

```bash
printf '%s' '## 概要

PR #665 (`ea9bca9`) で `gui/src-tauri/src/lib.rs` の全 23 Tauri commands が
`Result<T, String>` → `Result<T, AppError>` に migration 完了済み。本 issue
ではその仕上げとして以下 4 軸を完遂する。

## 残作業 (4 軸)

### (A) Legacy `startsWith('conflict:')` fallback 撤去

`gui/src/state/metadataStore.ts:209` の `appErrorCodeIs(e, '"'"'state.mtime_conflict'"'"') || msg.startsWith('"'"'conflict:'"'"')` から後半 (legacy raw String fallback) を削除する。`code === '"'"'state.mtime_conflict'"'"'` のみで分岐する。

### (B) Per-code default hint helper 追加と全 80 site への適用

`gui/src-tauri/src/error.rs` に `default_hint_for_code()` + `with_default_hint()` を追加し、全 80 site の `AppError::new(...)` で chain する。`From<io::Error>` / `From<serde_json::Error>` も hint chain 経路に乗せる。

### (C) Frontend での hint 表示

各 store (metadataStore / recentStore) に `*ErrorHint` state pair を追加し、各 inline error の 2 行目に hint を render (`var(--ae-text-dim)` 色、`💡` prefix)。

### (D) docs / issue body 整合

- `docs/tauri-commands.md` に AppError default hint mapping table を追加
- `docs/ui-architecture.md` § 4 に AppError code 体系と使い分け追記
- `docs/ui-interaction-spec.md` § 1.5 に error.code ベース分岐ルール追記
- 本 issue body を更新 (本 update)

## 受け入れ条件

- [ ] (A) `metadataStore.ts:209` の `|| msg.startsWith('"'"'conflict:'"'"')` が削除されている
- [ ] (A) `metadataStore.test.ts` の `'"'"'conflict: ...'"'"'` raw String テストが AppError object 形式に書き換わっている
- [ ] (A) `ConflictModal.test.tsx` の test data から `'"'"'conflict:'"'"'` prefix が消えている
- [ ] (B) `error.rs` に `default_hint_for_code()` + `with_default_hint()` が追加され、24 codes (or-pattern 展開後 #692) 分の日本語 hint が table に存在する
- [ ] (B) `From<std::io::Error>` / `From<serde_json::Error>` の impl 内で `.with_default_hint()` が呼ばれている
- [ ] (B) `lib.rs` の全 80 site の `AppError::new(code, msg)` に `.with_default_hint()` が chain されている
- [ ] (C) `metadataStore` に `loadErrorHint` / `applyErrorHint` / `restoreErrorHint` / `draftSaveErrorHint` / `draftLoadErrorHint` の 5 state が追加されている
- [ ] (C) `recentStore` に `loadErrorHint` / `addErrorHint` が追加されている
- [ ] (C) 5 screen + RestoreButton の inline error が hint があれば 2 行目を `var(--ae-text-dim)` で render する
- [ ] (D) `docs/tauri-commands.md` に AppError default hint mapping table が追加されている
- [ ] (D) `docs/ui-architecture.md` § 4 に `code` 体系と使い分け節 (§4.x) が追加されている
- [ ] (D) `docs/ui-interaction-spec.md` § 1.5 に `error.code` ベース分岐ルール節 (§1.5.x) が追加されている
- [ ] cargo check / cargo test --lib (新 6 件 + 既存 149 件 = 155 件 pass)
- [ ] npm run lint / typecheck / test (新 13-15 件 + 既存 ~566 件 = ~580 件 pass) / build
- [ ] CI PR 全 7 job pass (`python` / `gui-frontend` / `gui-rust` / `doc-tauri-commands-drift` / `installer-pester` / `markdownlint` / `validate-checklist`) ※ `build-windows` / `version-check` は `release.yml` 専用で PR CI には含まれない
- [ ] Iron Law 6 実機検証 5 経路 (state.mtime_conflict / io.permission_denied / io.file_not_found / parse.json_invalid / subprocess.spawn_failed) を Idios が PASS 確認

## スコープ外

- ErrorModal (#614) への AppError 統合
- `globalErrorListener.ts` への AppError parse 追加
- `ConflictModal` での AppError hint 表示 (modal 既存 compose hint と概念衝突回避)
- 新規 Tauri command の追加 / 削除
- 自動 telemetry / Sentry crash reporter 統合
- 関連 issue (#619 / #614 等 CLOSED 群) の body 修正

## 関連

- 派生元: #614 (PR #661、AppError struct 導入)、#619 (PR #665、`Result<T, AppError>` migration)
- 親 plan: `docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md` (Lane I-A)
- spec: `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`
' | gh issue edit 663 --body-file -
```

- [ ] **Step 2: Verify the issue body update**

```bash
gh issue view 663 --json body | head -50
```

Expected: new body content visible.

### Task 5.6: Phase 5 commit

- [ ] **Step 1: Commit Phase 5 (docs only — issue body update is via gh CLI, not in repo)**

```bash
git add docs/tauri-commands.md docs/ui-architecture.md docs/ui-interaction-spec.md
git commit -m "$(cat <<'EOF'
docs: AppError default hint mapping を docs に整合させる (Refs #663)

Phase 1-4 で追加した default_hint_for_code mapping (24 codes (or-pattern 展開後 #692)) と frontend
hint 表示規約を docs に明文化。docs/tauri-commands.md は error.rs の
mapping を mirror、ui-architecture.md / ui-interaction-spec.md は
inline error の 2 行構成と code-based 分岐ルールを規定。

主な追加:

- docs/tauri-commands.md: 末尾に AppError default hint mapping table
  (24 codes、or-pattern 展開後 #692、`error.rs::default_hint_for_code` と完全一致)
- docs/ui-architecture.md §4.x: AppError code 体系と inline error の
  使い分け、ConflictModal 経路と inline 経路の分岐ルール
- docs/ui-interaction-spec.md §1.5.x: appErrorCodeIs / appErrorMessage /
  appErrorHint の使用パターンと 1 行目 / 2 行目の色規約

Issue #663 body も同 PR で gh issue edit を通して update 済 (実態に整合)。

Phase 5/5 (spec §10-§11)。

Refs #663

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: commit success, 3 files changed.

---

## Phase 6: PR Pre-flight + 実機検証 + PR creation (no commit)

### Task 6.1: PR Pre-flight checks (Iron Law 6 完全準拠)

- [ ] **Step 1: base 同期確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

If output is non-empty AND any commit touches `gui/src-tauri/src/error.rs|lib.rs|gui/src/state/*|gui/src/components/*|gui/src/screens/*|docs/tauri-commands.md|docs/ui-architecture.md|docs/ui-interaction-spec.md`, run:

```bash
git merge origin/develop-0.2.0
# resolve any conflicts
```

Then re-run automated checks below.

- [ ] **Step 2: 並行 worktree PR 重複確認**

```bash
gh pr list --search "#663" --state all
gh pr list --state open --search "claude/"
```

Expected: no other open PR claiming #663. If exists, halt and ask Idios via `AskUserQuestion`.

### Task 6.2: 自動チェック (path 別 / Iron Law 6 — 失敗パターン A 防止)

- [ ] **Step 1: Rust check**

```bash
cd gui/src-tauri && cargo check && cargo test --lib 2>&1 | tail -10
```

Expected: 155 件 pass.

- [ ] **Step 2: GUI frontend check**

```bash
cd ../.. && cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build 2>&1 | tail -20
```

Expected: lint / typecheck / vitest (~580 件 pass) / build all green.

- [ ] **Step 3: Markdownlint**

```bash
cd .. && bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: 0 errors.

- [ ] **Step 4: Python regression check**

```bash
ruff check . && ruff format --check . && pyright && pytest 2>&1 | tail -10
```

Expected: pass (本 PR は GUI / docs のみで Python に影響なし。regression check)。

### Task 6.3: 実機検証依頼 (Iron Law 6 — 失敗パターン B 防止)

**Files:**

- Tool: `AskUserQuestion`

- [ ] **Step 1: Ask Idios for 5-route 実機検証**

Use `AskUserQuestion` with the following spec:

```text
Question: 実機検証 5 経路の結果を教えてください (allaganeye-gui を Tauri dev で起動して各 route を再現)。
Options:

- 全 5 PASS (PR 作成可)
- 一部 FAIL (詳細を Idios が記述)
- 後で実施 (PR 作成は保留、後続でアップデート)
- やめる
```

Provide the 5 routes inline:

1. `state.mtime_conflict`: metadata.json を 2 つの allaganeye-gui プロセスで同時 edit → apply、ConflictModal 表示 + AppError hint は modal に出ない
2. `io.permission_denied`: read-only な metadata.json を編集→apply、inline error 2 行目に "Portable ZIP install dir が user-writable な..." hint
3. `io.file_not_found`: metadata.json を削除して GUI から再 load、inline error 2 行目に "ファイルが見つかりません..." hint
4. `parse.json_invalid`: metadata.json を破損させて load、inline error 2 行目に "JSON ファイルが破損..." hint
5. `subprocess.spawn_failed`: ffprobe を一時 rename して probe、inline error 2 行目に "外部プロセスの起動に失敗..." hint

Wait for response before proceeding.

### Task 6.4: PR 作成 (Self-Test Report 添付)

- [ ] **Step 1: Push branch**

```bash
git push origin claude/tender-khayyam-03d618 2>&1 | tail -5
```

Expected: push success.

- [ ] **Step 2: Compose PR body and create PR**

```bash
printf '%s' '## Summary

[#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) (PR #665 後の AppError migration 完遂) の実装。

Lane I-A (wave 0 起点)。spec [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md)。session-id: `tender-khayyam-03d618`。

## 主な変更 (5 phase / 5 commit)

### Phase 1: Rust `error.rs` (default hint helper)

- `default_hint_for_code(code)` (24 codes、or-pattern 展開後 #692) + `with_default_hint()` 追加
- `From<io::Error>` / `From<serde_json::Error>` impl で hint chain
- 6 件の TDD 新 test (155 件 pass)

### Phase 2: Rust `lib.rs` mechanical

- 全 80 site の `AppError::new(...)` に `.with_default_hint()` chain
- regression なし

### Phase 3: Frontend stores

- `metadataStore`: `*ErrorHint` 5 state 追加 (load / apply / restore / draftSave / draftLoad)
- `recentStore`: `loadErrorHint` / `addErrorHint` 追加
- `metadataStore.ts:209` の legacy `|| msg.startsWith('"'"'conflict:'"'"')` を削除
- 既存 conflict 文字列 test (8 + 6 件) を AppError object 形式 / prefix 削除版に書き換え

### Phase 4: Frontend UI

- 5 screen + RestoreButton の inline error に hint 2 行目を追加 (`var(--ae-text-dim)` 色)
- 各 module.css に `.errorHint` (or 派生) class
- 各 screen / component test に hint 表示 test を追加

### Phase 5: Docs + issue body

- `docs/tauri-commands.md`: AppError default hint mapping table (24 codes、or-pattern 展開後 #692)
- `docs/ui-architecture.md` §4.x: AppError code 体系と inline 使い分け
- `docs/ui-interaction-spec.md` §1.5.x: error.code ベース分岐ルール
- Issue #663 body を実態に合わせて update (gh issue edit)

## 受け入れ条件 (issue #663 全 14 項目)

- [x] (A) `metadataStore.ts:209` の `|| msg.startsWith('"'"'conflict:'"'"')` が削除されている
- [x] (A) `metadataStore.test.ts` の `'"'"'conflict: ...'"'"'` raw String テストが AppError object 形式に書き換え
- [x] (A) `ConflictModal.test.tsx` の test data から `'"'"'conflict:'"'"'` prefix が消えている
- [x] (B) `error.rs` に `default_hint_for_code()` + `with_default_hint()` 追加、24 codes (or-pattern 展開後 #692) 日本語 hint
- [x] (B) `From<std::io::Error>` / `From<serde_json::Error>` で `.with_default_hint()`
- [x] (B) `lib.rs` 全 80 site の `AppError::new(...)` に `.with_default_hint()`
- [x] (C) `metadataStore` に 5 `*ErrorHint` state、`recentStore` に 2 hint pair 追加
- [x] (C) 5 screen + RestoreButton の inline error が hint を 2 行目に render
- [x] (D) docs 3 ファイル更新
- [x] (D) issue body 更新

## Self-Test Report

### Machine-verified (Iron Law 6 PR 作成 Pre-flight)

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` (取り込み未済 commit なし、または merge 完了)
- [x] `gh pr list --search "#663"` 並行 worktree PR 重複なし
- [x] `cd gui/src-tauri && cargo check` (warning なし)
- [x] `cd gui/src-tauri && cargo test --lib` (155 件 pass、新 6 件 + 既存 149 件)
- [x] `cd gui && npm run lint` (exit 0)
- [x] `cd gui && npm run typecheck` (exit 0)
- [x] `cd gui && npm test -- --run` (~580 件 pass、新 13-15 件 + 既存 ~566 件)
- [x] `cd gui && npm run build` (exit 0)
- [x] `bash scripts/check-markdownlint.sh` (0 errors)
- [x] `ruff check . && ruff format --check . && pyright && pytest` (Python regression なし)

### Machine-unverifiable (Iron Law 6 実機検証 — 失敗パターン B 防止)

- E2E #1: `state.mtime_conflict` 経路 (2 プロセス同時 edit → apply、ConflictModal 表示 + modal 既存 hint 維持、AppError hint は modal に出ない)
- E2E #2: `io.permission_denied` 経路 (read-only metadata.json apply、inline 2 行目に "Portable ZIP install dir..." hint)
- E2E #3: `io.file_not_found` 経路 (metadata.json 削除して再 load、inline 2 行目に "ファイルが見つかりません..." hint)
- E2E #4: `parse.json_invalid` 経路 (metadata.json 破損 load、inline 2 行目に "JSON ファイルが破損..." hint)
- E2E #5: `subprocess.spawn_failed` 経路 (ffprobe rename して probe、inline 2 行目に "外部プロセスの起動に失敗..." hint)

## 関連

Refs #663 #665 #661 #614 #619 #514

🤖 Generated with [Claude Code](https://claude.com/claude-code)
' | gh pr create --base develop-0.2.0 --head claude/tender-khayyam-03d618 --title 'refactor(gui): #663 AppError migration 完遂 (legacy fallback 撤去 + per-code default hint 全 80 site 適用) (Lane I-A)' --body-file -
```

Expected: PR created with link printed. Note the PR number for follow-up.

---

## Self-review

Spec coverage check (against `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`):

- ✅ §5 (Layer 1) — Task 1.1 / 1.2 / 1.3 cover `default_hint_for_code`, `with_default_hint`, From impl chains
- ✅ §6 (Layer 2) — Task 2.1 covers 80 sites mechanical migration
- ✅ §7 (Layer 3) — Task 3.2 / 3.3 / 3.4 cover store state, legacy fallback removal, recentStore
- ✅ §8 (Layer 4) — Task 4.1-4.6 cover CSS + RestoreButton + 4 screens
- ✅ §9 (Tests) — TDD red→green at every modification, regression check at end of each phase
- ✅ §9.3 (実機検証 5 経路) — Task 6.3 explicitly invokes `AskUserQuestion`
- ✅ §10 (Docs) — Task 5.1-5.4 cover all 3 doc files + markdownlint
- ✅ §11 (Issue body update) — Task 5.5 with `printf | gh issue edit` (per `feedback_gh_command_ja_heredoc.md`)
- ✅ §12 (受け入れ条件) — All 14 items mapped to specific tasks
- ✅ §13 (Risks) — Pre-flight (Task 6.1), automated checks (Task 6.2), 実機検証 (Task 6.3) all addressed
- ✅ §14 (実装順序 5 phase / 5 commit) — Phases 1-5 → 5 commits, Phase 6 = PR creation no commit
- ✅ §15 (PR Pre-flight) — Task 6.1 / 6.2
- ✅ §16 (PR 規約) — Task 6.4 PR body shows `Refs #663` only, session-id, Self-Test Report

Placeholder scan: No "TBD" / "TODO" / "implement later" remain. Each step has explicit code or commands. Some screen test skeletons (`render(<DropScreen />); /* simulate the probe trigger */`) are intentionally adaptive because they depend on existing test helpers — the executor reads the file first to mirror the established pattern.

Type consistency: `appErrorMessage` / `appErrorHint` / `appErrorCodeIs` are consistent across phases. `default_hint_for_code` / `with_default_hint` consistent. `*ErrorHint` field naming consistent (`loadErrorHint`, `applyErrorHint`, etc.) — no `loadHint` / `applyHintMessage` divergence.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-08-l2-appError-migration-completion.md`.** Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
