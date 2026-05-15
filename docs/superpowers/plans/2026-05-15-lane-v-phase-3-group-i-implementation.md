# Lane V Phase 3 / Group I — #699 AppError stale docstring 更新 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** issue #699 (AppError 関連 stale docstring を post-#663 状態に更新) を完遂するため、#694 (PR #745) で `appErrorMessage` / `appErrorHint` helper が削除されたあと残存していた dangling 参照 3 箇所を post-#663/#694 状態に同期する doc-only PR を作る。

**Architecture:** 1 PR / 2 commit / 3 file の docstring・comment のみ変更。commit 1 = `gui/src-tauri/src/error.rs` + `gui/src-tauri/tests/extract_brightness_window.rs` (Rust 側) / commit 2 = `docs/ui-interaction-spec.md` (doc 側)。挙動変更ゼロ (`///` docstring と `//` comment のみ、関数 signature / body / test assertion は不変)。

**Tech Stack:** Rust (gui/src-tauri), Markdown (docs/), gh CLI, git, markdownlint-cli2 v0.22.1。

**Spec:** [docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md](../specs/2026-05-15-lane-v-phase-3-group-i-design.md) (commit `35e884e`)。

---

## TDD Note — doc-only PR の扱い (重要)

本 plan は `superpowers:test-driven-development` の通常 Red-Green-Refactor flow を**適用しない**。理由:

- 本 PR は production code の挙動を一切変更しない (`///` docstring と `//` comment のみ、関数 signature / body / `#[allow(dead_code)]` attribute・test assertion 不変)
- 「先に書く failing test」が存在しない (挙動が変わらないため)

代わりに「**挙動変更ゼロの証明**」で TDD の趣旨 (挙動の保証) を担保する:

1. `cargo test` (lib + integration) が既存 baseline のまま全 pass する (件数不変)
2. PR diff が `error.rs` は `///` 行のみ・`extract_brightness_window.rs` は `//` 行のみ・`ui-interaction-spec.md` は Markdown 散文のみであることを `git diff` で逐条確認
3. `with_hint` 関数 signature / body・test assertion・`#[allow(dead_code)]` attribute が変更されていないことを確認

詳細は spec §6.1。

---

## Pre-flight 既実施分

本 brainstorming セッション内で以下を実施済 (実装時に再確認する):

- `gh pr list --search "#699" --state open` → 0 件
- `gh pr list --search "#699" --state all` → MERGED 5 件 (#745 / #709 / #733 / #738 / #519、いずれも本 issue を実装する PR ではない)
- `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0 --oneline` → in sync (取り込み未済 commit 0)
- 並行 worktree PR: 検出なし

実装時に Task 0 で再確認する。

---

## Task 0: PR 作成 Pre-flight Step 0-2 (ハードゲート + base sync 再確認)

**Files:** (実行のみ、変更なし)

- [ ] **Step 1: Step 0 ハードゲート — `gh pr list --search "#699" --state open`**

Run:

```bash
gh pr list --search "#699" --state open
```

Expected: 0 件 (空出力 / "no open pull requests")。
NG ケース: 1 件以上 → 並行 PR がある可能性。STOP して user に確認。

- [ ] **Step 2: Step 1 — base sync**

Run:

```bash
git fetch origin develop-0.2.0
```

Expected: exit 0。

- [ ] **Step 3: Step 2 — 取り込み未済 commit 確認**

Run:

```bash
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 空出力 (HEAD が origin/develop-0.2.0 を含む = in sync)。
NG ケース: commit 列挙される → `git merge origin/develop-0.2.0` で base 取り込み後、Task 0 を再実行。

---

## Task 1: `error.rs:28-34` `with_hint` docstring 更新

**Files:**

- Modify: `gui/src-tauri/src/error.rs:28-36`

- [ ] **Step 1: 現在の lines 28-36 を再確認**

Run: `Read` tool で `gui/src-tauri/src/error.rs` の lines 28-36 を読む。

Expected (実装時点 HEAD): 以下と一致 (差異があれば STOP して spec §5.1 と整合確認)。

```rust
    /// `hint` フィールドを設定する builder。
    ///
    /// 将来用 — 現状 production code では未使用 (test のみ参照、PR #665 Round 2
    /// 課題 5 (c) で保留決定)。lib.rs 側 AppError::new(...) の主要箇所に hint
    /// を後付けで配るための小規模拡張で活用予定 (例: `state.mtime_conflict`
    /// で「他プロセスでの書き換えを確認してください」等)。frontend 側 helper は
    /// `gui/src/lib/appError.ts::appErrorHint` で同じく保留中。
    #[allow(dead_code)]
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
```

- [ ] **Step 2: Edit で docstring を更新**

`Edit` tool で `gui/src-tauri/src/error.rs` に対し以下を実施:

`old_string` (上記 9 行ブロックそのまま):

```rust
    /// `hint` フィールドを設定する builder。
    ///
    /// 将来用 — 現状 production code では未使用 (test のみ参照、PR #665 Round 2
    /// 課題 5 (c) で保留決定)。lib.rs 側 AppError::new(...) の主要箇所に hint
    /// を後付けで配るための小規模拡張で活用予定 (例: `state.mtime_conflict`
    /// で「他プロセスでの書き換えを確認してください」等)。frontend 側 helper は
    /// `gui/src/lib/appError.ts::appErrorHint` で同じく保留中。
    #[allow(dead_code)]
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
```

`new_string`:

```rust
    /// `hint` フィールドを明示的に設定する builder (per-call-site override 用)。
    ///
    /// production code は `with_default_hint()` 経由で code 別 default hint を
    /// 設定する (#663 で lib.rs 全 80 site に適用済)。`with_hint` 自体は test
    /// (`serialize_app_error_roundtrips` /
    /// `with_default_hint_does_not_overwrite_explicit_hint`) と、将来 Approach C
    /// (per-call-site hint override) への hybrid 移行用 API として残す。
    /// `#[allow(dead_code)]` は production 非経由 (= test 専用 API) を示し、
    /// `cargo build` で dead-code warning を出さないためのもの。
    #[allow(dead_code)]
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
```

- [ ] **Step 3: diff 検査 — `///` 行のみ変更されていることを確認**

Run:

```bash
git diff -- gui/src-tauri/src/error.rs
```

Expected:

- 変更行はすべて `///` で始まる (docstring 行) または前後 context 行
- `#[allow(dead_code)]` 行は不変 (`@@` の context として現れるのみ)
- `pub fn with_hint(...)` 行は不変
- 削除行に「将来用 — 現状 production code では未使用」「PR #665 Round 2 課題 5 (c)」「`gui/src/lib/appError.ts::appErrorHint`」が含まれる (stale 表現除去確認)
- 追加行に「`with_default_hint()` 経由」「lib.rs 全 80 site」「Approach C」「test 専用 API」が含まれる (post-#663 表現確認)

NG ケース (即 STOP): `pub fn with_hint` signature が変わっている / `#[allow(dead_code)]` が消えた / `with_hint` body が変わった。

---

## Task 2: `extract_brightness_window.rs:77-82` test comment 更新

**Files:**

- Modify: `gui/src-tauri/tests/extract_brightness_window.rs:77-82`

- [ ] **Step 1: 現在の lines 75-85 を再確認**

Run: `Read` tool で `gui/src-tauri/tests/extract_brightness_window.rs` の lines 75-85 を読む。

Expected: lines 77-82 が以下と一致。

```rust
    // Pin the error contract so frontend `appErrorHint` can rely on it: the
    // failure path is ffmpeg returning non-zero exit (the binary is spawned
    // successfully but cannot open the input). `subprocess.exit_failed` is
    // the canonical code for that case in lib.rs (see ensure_thumbnail_exists
    // and probe_video_with). If ffmpeg itself is missing from PATH the code
    // is `subprocess.spawn_failed` — accept either, both have default hints.
```

- [ ] **Step 2: Edit で test コメントを更新**

`Edit` tool で `gui/src-tauri/tests/extract_brightness_window.rs` に対し以下を実施:

`old_string`:

```rust
    // Pin the error contract so frontend `appErrorHint` can rely on it: the
    // failure path is ffmpeg returning non-zero exit (the binary is spawned
    // successfully but cannot open the input). `subprocess.exit_failed` is
    // the canonical code for that case in lib.rs (see ensure_thumbnail_exists
    // and probe_video_with). If ffmpeg itself is missing from PATH the code
    // is `subprocess.spawn_failed` — accept either, both have default hints.
```

`new_string` (rewrap、内容意味は等価で symbol のみ post-#694 に更新):

```rust
    // Pin the error contract so the frontend hint rendering (`toErrorState`
    // → `ErrorState.hint`) can rely on it: the failure path is ffmpeg
    // returning non-zero exit (the binary is spawned successfully but cannot
    // open the input). `subprocess.exit_failed` is the canonical code for
    // that case in lib.rs (see ensure_thumbnail_exists and probe_video_with).
    // If ffmpeg itself is missing from PATH the code is `subprocess.spawn_failed`
    // — accept either, both have default hints.
```

注意: 行数が 6 → 7 に増える (rewrap のため)。`//` 以外の行 (test assertion / 関数本体) は touch しない。

- [ ] **Step 3: diff 検査 — `//` 行のみ変更されていることを確認**

Run:

```bash
git diff -- gui/src-tauri/tests/extract_brightness_window.rs
```

Expected:

- 変更行 (削除 + 追加) はすべて `//` で始まる
- `let result = ...` / `assert!(...)` / `let err = ...` 等の test code 行は不変 (context として現れるのみ)
- 削除行に「frontend `appErrorHint` can rely on it」が含まれる
- 追加行に「the frontend hint rendering (`toErrorState`」「`ErrorState.hint`」が含まれる
- `subprocess.exit_failed` / `subprocess.spawn_failed` の契約説明は維持されている

NG ケース (即 STOP): test code 行が変わった / コメントの後続ブロック (line 83-86 の `AppError` Display fmt 説明) を巻き込んだ。

---

## Task 3: Rust side 検証 + commit 1

**Files:** (実行 + commit のみ、新規変更なし)

- [ ] **Step 1: cargo check (rustdoc 破損も含めて確認)**

Run:

```bash
cd gui/src-tauri && cargo check
```

Expected: exit 0。warnings なし (`with_hint` の `#[allow(dead_code)]` 維持により dead-code warning なし)。

NG ケース: error / warning が出る → STOP して原因を確認。docstring の `///` syntax 崩れ・参照リンク (`[code]` 等) が rustdoc で broken と判定された等の可能性。

- [ ] **Step 2: cargo test (lib + integration、baseline 維持)**

Run:

```bash
cd gui/src-tauri && cargo test
```

Expected: 既存 test が全 pass (件数不変)。`error::tests::*` の 9 件 (`serialize_app_error_roundtrips` 等) + integration test `extract_brightness_window` も全 pass。

NG ケース: 件数変化 / fail → STOP。docstring/comment 変更で test に影響したのは異常。

- [ ] **Step 3: commit 1 (error.rs + extract_brightness_window.rs)**

Run:

```bash
git add gui/src-tauri/src/error.rs gui/src-tauri/tests/extract_brightness_window.rs
git commit -F - <<'EOF'
docs(gui): #699 src-tauri 側 AppError stale docstring/comment 更新

Lane V Phase 3 / Group I — #694 (PR #745) で発生した
post-#663 stale 表現と dangling 参照を解消。

- error.rs:28-34 with_hint docstring:
  「将来用 / 現状 production code では未使用」表現を除去、
  production 経路が with_default_hint() (lib.rs 全 80 site、#663)
  であることを明記。dangling 参照
  `gui/src/lib/appError.ts::appErrorHint` を除去。
  #[allow(dead_code)] の意味 (test 専用 API) を明記。
- extract_brightness_window.rs:77 test コメント:
  dangling `appErrorHint` 参照を toErrorState / ErrorState.hint
  に更新。test assertion / 関数本体は不変。

挙動変更ゼロ (docstring `///` と comment `//` のみ)。
cargo check / cargo test baseline pass を確認。

Refs #699

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: 1 commit created。`git log --oneline -1` で確認。

NG ケース: working tree が dirty (Task 1 / 2 で stage していない他の変更) → `git status` で確認、想定外の変更があれば STOP。

---

## Task 4: `ui-interaction-spec.md` item 2 更新

**Files:**

- Modify: `docs/ui-interaction-spec.md:107-111`

- [ ] **Step 1: 現在の lines 105-115 を再確認**

Run: `Read` tool で `docs/ui-interaction-spec.md` の lines 105-115 を読む。

Expected: lines 107-111 が以下と一致。

```markdown
2. その他の AppError code → inline error
   - 1 行目: `appErrorMessage(e)` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `appErrorHint(e)` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
```

- [ ] **Step 2: Edit で item 2 ブロックを更新**

`Edit` tool で `docs/ui-interaction-spec.md` に対し以下を実施:

`old_string`:

```markdown
2. その他の AppError code → inline error
   - 1 行目: `appErrorMessage(e)` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `appErrorHint(e)` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
```

`new_string` (item 2 の sub-list 先頭に `toErrorState` 正規化行を 1 件追加 + 残りを `ErrorState.message` / `ErrorState.hint` 参照に置換):

```markdown
2. その他の AppError code → inline error
   - catch path で `toErrorState(e)` により `ErrorState { message, hint, code }` に正規化 (#694)
   - 1 行目: `ErrorState.message` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `ErrorState.hint` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
```

注意:

- item 1 (line 106、`appErrorCodeIs(e, 'state.mtime_conflict')`) は #694 で**維持された** live export → touch しない
- item 3 / item 4 (lines 112-114) は touch しない
- リスト構造・インデント (3 スペース) を維持

- [ ] **Step 3: diff 検査 — Markdown 散文のみ変更されていることを確認**

Run:

```bash
git diff -- docs/ui-interaction-spec.md
```

Expected:

- 削除行に「`appErrorMessage(e)`」「`appErrorHint(e)`」が含まれる
- 追加行に「`toErrorState(e)`」「`ErrorState { message, hint, code }`」「`ErrorState.message`」「`ErrorState.hint`」が含まれる
- item 1 の `appErrorCodeIs(...)` 行は不変
- item 3 (catch ブロック以外で error を扱わない) / item 4 (globalErrorListener) は不変

NG ケース (即 STOP): item 1 が変わった / 他セクションを巻き込んだ / インデント崩れ。

---

## Task 5: Doc side 検証 + commit 2

**Files:** (実行 + commit のみ、新規変更なし)

- [ ] **Step 1: markdownlint check**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: `Summary: 0 error(s)`。

NG ケース: MD028 / MD056 / その他の rule 違反 → STOP。memory `feedback_markdownlint_typical_fixes.md` を参照して修正。インデント崩れによる MD007 / 連続 blockquote MD028 が出やすい。

- [ ] **Step 2: commit 2 (ui-interaction-spec.md)**

Run:

```bash
git add docs/ui-interaction-spec.md
git commit -F - <<'EOF'
docs: #699 ui-interaction-spec.md AppError code 分岐ルール節を post-#694 に更新

Lane V Phase 3 / Group I — #694 で削除された
appErrorMessage / appErrorHint への dangling 参照を解消。

§AppError code ベースの分岐ルール (#663) item 2 を post-#694
の実態 (toErrorState 経由の ErrorState.message / .hint) に更新。
item 1 の appErrorCodeIs(...) は #694 で維持された live export
なので touch なし。

bash scripts/check-markdownlint.sh pass を確認。

Refs #699

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

Expected: 1 commit created (commit 2)。`git log --oneline -2` で 2 commit (commit 1 + commit 2) を確認。

---

## Task 6: Repo-wide dangling-reference scan (acceptance 検証用)

**Files:** (検査のみ、変更なし)

- [ ] **Step 1: `appErrorMessage` / `appErrorHint` が歴史的文書以外に残っていないことを確認**

Run:

```bash
git grep -nE "appErrorMessage|appErrorHint" -- ':!docs/superpowers/'
```

Expected: 0 件 (空出力 / exit 1)。

歴史的文書 (`docs/superpowers/plans/*` / `docs/superpowers/specs/*`) は意図的に touch していないため、それらを除外した上で 0 件であるべき。

NG ケース: 何か出力される → 見落とした dangling 参照。spec §5.4 と照合し追加修正するか、scope 外であれば spec を再考。

- [ ] **Step 2: `with_hint` の callsite が test のみであることを再確認**

Run:

```bash
git grep -nE "\.with_hint\(" -- gui/src-tauri/
```

Expected: 出力は `gui/src-tauri/src/error.rs` の `tests` モジュール内 (`#[cfg(test)]` 配下) のみ。production code (`lib.rs` 等) に `.with_hint(` の呼び出しは無いことを確認 (= docstring の「production 非経由」記述が正しい)。

---

## Task 7: PR 作成 Pre-flight Step 3-4 + push + PR creation

**Files:** (PR creation、ローカル変更なし)

- [ ] **Step 1: Pre-flight Step 0 再確認 (push 直前ハードゲート)**

Run:

```bash
gh pr list --search "#699" --state open
```

Expected: 0 件 (Task 0 から状態不変であるべき)。1 件以上なら STOP。

- [ ] **Step 2: Pre-flight Step 3 — touched files 交差判定**

Run:

```bash
git diff --name-only origin/develop-0.2.0..HEAD
```

Expected (出力ファイル一覧):

```text
docs/superpowers/plans/2026-05-15-lane-v-phase-3-group-i-implementation.md
docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md
docs/ui-interaction-spec.md
gui/src-tauri/src/error.rs
gui/src-tauri/tests/extract_brightness_window.rs
```

(spec + plan は brainstorming / writing-plans で commit 済、本実装 PR と同 branch にある)

確認:

```bash
gh pr list --state open --json number,headRefName,files --jq '.[] | select(.files | map(.path) | any(. == "gui/src-tauri/src/error.rs" or . == "gui/src-tauri/tests/extract_brightness_window.rs" or . == "docs/ui-interaction-spec.md"))'
```

Expected: 空 (他 PR が同じ file に触れていない)。

NG ケース: 他 PR が `error.rs` / `extract_brightness_window.rs` / `ui-interaction-spec.md` を touch している → merge 順序を coordinate 必要、STOP して user に確認。

- [ ] **Step 3: Pre-flight Step 4 — `--state all` 並行 worktree PR 再確認**

Run:

```bash
gh pr list --search "#699" --state all
```

Expected: MERGED 5 件 (#745 / #709 / #733 / #738 / #519、いずれも #699 を実装する PR ではなく言及のみ)。OPEN 0 件。

新たに #699 を実装する OPEN PR が出ていないことを確認。

- [ ] **Step 4: branch push**

Run:

```bash
git push -u origin claude/modest-darwin-6f2394
```

Expected: push 成功。`To github-idios:...` 行が出る。

- [ ] **Step 5: PR 作成 (gh pr create)**

Run (HEREDOC で日本語本文を渡す、memory `feedback_gh_command_ja_heredoc.md` 適用):

```bash
gh pr create --base develop-0.2.0 --head claude/modest-darwin-6f2394 \
  --title "docs: #699 AppError stale docstring 更新 (Lane V Phase 3 / Group I)" \
  --body-file - <<'EOF'
## 概要

issue #699 (AppError 関連 stale docstring を post-#663 状態に更新) を完遂する Lane V Phase 3 / Group I の最終 PR。

#694 ([PR #745](https://github.com/Idios/kobutachan-allaganeye/pull/745)) で `appErrorMessage` / `appErrorHint` helper が削除されたあと残存していた dangling 参照 3 箇所を post-#663/#694 状態に同期する。

詳細設計: [docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md](docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md)
実装計画: [docs/superpowers/plans/2026-05-15-lane-v-phase-3-group-i-implementation.md](docs/superpowers/plans/2026-05-15-lane-v-phase-3-group-i-implementation.md)

## 変更内容

### commit 1: src-tauri 側 (error.rs + extract_brightness_window.rs)

- `gui/src-tauri/src/error.rs:28-34` `with_hint` docstring:
  - 「将来用 / 現状 production code では未使用」表現を除去
  - production 経路が `with_default_hint()` (lib.rs 全 80 site、#663) であることを明記
  - dangling 参照 `gui/src/lib/appError.ts::appErrorHint` (#694 で関数削除済) を除去
  - `#[allow(dead_code)]` の意味 (test 専用 API のため非 test build で dead-code warning を抑止) を明記
  - 「将来 Approach C への hybrid 移行用 API」の framing は維持 (#663 spec §5.1 整合)
- `gui/src-tauri/tests/extract_brightness_window.rs:77` test コメント:
  - dangling `appErrorHint` 参照を現行 symbol (`toErrorState` / `ErrorState.hint`) に更新
  - `subprocess.exit_failed` / `subprocess.spawn_failed` の契約説明は維持
  - test assertion・関数本体は touch なし

### commit 2: doc 側 (ui-interaction-spec.md)

- `docs/ui-interaction-spec.md` 「AppError `code` ベースの分岐ルール (#663)」節 item 2:
  - `appErrorMessage(e)` / `appErrorHint(e)` 参照を `toErrorState(e)` 経由の `ErrorState.message` / `ErrorState.hint` に更新
  - `toErrorState(e)` 正規化ステップを 1 行追加 (post-#694 の実際の catch path フロー反映)
  - item 1 の `appErrorCodeIs(...)` は #694 で維持された live export なので touch なし

## 受け入れ条件 (spec §8 から逐条転記)

- [ ] `gui/src-tauri/src/error.rs:28-34` の `with_hint` docstring が spec §5.1 After 相当に更新されている
- [ ] 同 docstring から dangling 参照 `gui/src/lib/appError.ts::appErrorHint` が除去されている
- [ ] 同 docstring に `#[allow(dead_code)]` の意味 (test 専用 API) が明記されている
- [ ] 同 docstring の「将来 Approach C への hybrid 移行用 API」の framing は維持されている (#663 spec §5.1 整合)
- [ ] `gui/src-tauri/tests/extract_brightness_window.rs:77` 付近の test コメントから dangling `appErrorHint` 参照が除去され、現行 symbol (`toErrorState` / `ErrorState.hint`) に更新されている
- [ ] `docs/ui-interaction-spec.md` の「AppError `code` ベースの分岐ルール」節 item 2 の `appErrorMessage(e)` / `appErrorHint(e)` 参照が `toErrorState(e)` 経由の `ErrorState.message` / `ErrorState.hint` に更新されている
- [ ] 同節 item 1 の `appErrorCodeIs(...)` は #694 維持 export のため touch されていない
- [ ] `error.rs` の `with_hint` 関数 signature / body / `#[allow(dead_code)]` attribute は不変 (docstring `///` 行のみ変更)
- [ ] `extract_brightness_window.rs` の変更は `//` コメント行のみ (test assertion / 関数本体は不変)
- [ ] `gui/src/lib/appError.ts` は本 PR で touch されていない (#694 で対応済)
- [ ] `error.rs:47-49` `with_default_hint` docstring・`error.rs:96-105` `From<String>` docstring・`with_stacktrace` は本 PR で touch されていない
- [ ] repo 全体で `appErrorMessage` / `appErrorHint` への dangling 参照が `docs/superpowers/plans/*` `specs/*` の歴史的文書以外に残っていない
- [ ] `cargo check` / `cargo test` (lib + integration) が既存 baseline のまま全 pass (件数不変)
- [ ] `bash scripts/check-markdownlint.sh` が exit 0
- [ ] Iron Law 6 PR Pre-flight (Step 0-4) 全 pass、CI 全 job pass
- [ ] PR 本文に「docstring / comment のみ・挙動変更ゼロ・関数 body 不変」が明記されている

## Self-Test Report

`docs/l2-workflow.md` §Self-Test Report 規約に準拠。machine-verified は `[x]`、machine-unverifiable は plain bullet `-`。

**path 別自動チェック (machine-verified)**:

- [x] `cd gui/src-tauri && cargo check` exit 0
- [x] `cd gui/src-tauri && cargo test` (lib + integration) baseline 全 pass、件数不変
- [x] `bash scripts/check-markdownlint.sh` exit 0
- [x] `git grep -nE "appErrorMessage|appErrorHint" -- ':!docs/superpowers/'` 0 件 (dangling 参照ゼロ)

**Pre-flight (machine-verified)**:

- [x] Step 0: `gh pr list --search "#699" --state open` 0 件
- [x] Step 1: `git fetch origin develop-0.2.0` 成功
- [x] Step 2: `git log HEAD..origin/develop-0.2.0 --oneline` 取り込み未済 0 件
- [x] Step 3: touched files (`error.rs` / `extract_brightness_window.rs` / `ui-interaction-spec.md`) で他 OPEN PR と交差なし
- [x] Step 4: `gh pr list --search "#699" --state all` で並行 worktree PR 再確認、新規 OPEN なし

**機能的影響 (machine-unverifiable)**:

- 挙動変更ゼロ: `error.rs` は `///` docstring のみ、`extract_brightness_window.rs` は `//` comment のみ、`ui-interaction-spec.md` は Markdown 散文のみ。関数 signature / body / `#[allow(dead_code)]` attribute・test assertion は不変
- Iron Law 6 実機検証は**不要** (spec §6.3): `gui/src-tauri/**` を touch するがロジック変更ではない (docstring/comment のみ)。GPU / audio / 長時間動画 / GUI Tauri 起動いずれの挙動も変わらないため

## Refs

- issue: #699
- spec: [docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md](docs/superpowers/specs/2026-05-15-lane-v-phase-3-group-i-design.md)
- plan: [docs/superpowers/plans/2026-05-15-lane-v-phase-3-group-i-implementation.md](docs/superpowers/plans/2026-05-15-lane-v-phase-3-group-i-implementation.md)
- 依存元 PR: [#745](https://github.com/Idios/kobutachan-allaganeye/pull/745) (#694, Lane V Phase 2、MERGED)
- 起点 issue: #663 ([PR #689](https://github.com/Idios/kobutachan-allaganeye/pull/689) で AppError migration 完遂)

## Notes

- `#694` issue は PR #745 MERGED 済だが `/close-issue` 未実施で OPEN 状態。本 PR は #745 merge 後の Phase 3 として独立進行。`#694` の close は本 PR とは別軸 (`/close-issue` skill のタイミング)
- PR #745 レビューコメントが #699 に追記した ExportScreen `openFolderError` / `openFolderErrorHint` local useState refactor finding は本 PR scope 外 (spec §3 / §7 Q2 — doc-only #699 に code refactor を fold すると Iron Law 3 scope creep)。次回 roadmap update / 後続セッションで他の設計残債と一緒に再トリアージ予定

[session=modest-darwin-6f2394]

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

Expected: PR URL 出力。

NG ケース: `gh pr create` が fail → 認証 / branch state を確認。日本語化け疑い時は `gh api` の `repos/.../pulls` POST も検討 (memory `feedback_gh_command_ja_heredoc.md`)。

- [ ] **Step 6: PR 作成後の hand-off**

PR URL を user に提示。次工程は CI 結果監視 → `/iterate-review <PR#>` で review-fix ループ自動化 (任意)。

post-merge は `/close-issue` skill で:

- 受け入れ条件 (上記 15 項目) を base ブランチで実測再検証
- #699 を `gh issue close` (Iron Law 4 manual close)
- 検出された残債は (B) 新 issue / (C) 既存 issue 追記 にトリアージ

---

## Self-Review チェック (plan 完成後、subagent 投入前)

実装 subagent が plan を読んで blocked なく実装できるか、以下を再確認:

### 1. Spec coverage

spec §2 Goals (4 項) と spec §8 受け入れ条件 (15 項) が plan の Task に網羅されているか:

- spec §2 Goal 1 (error.rs:28-34 with_hint docstring 更新) → Task 1
- spec §2 Goal 2 (dangling 参照 2 箇所更新) → Task 2 + Task 4
- spec §2 Goal 3 (挙動変更ゼロ保証) → Task 1 Step 3 / Task 2 Step 3 / Task 3 Step 1-2 / Task 4 Step 3
- spec §2 Goal 4 (Iron Law 1-6 厳守) → Task 0 (Pre-flight Step 0-2) + Task 7 (Step 0/3/4) + commit 規約 (`Refs #699`、Closes 禁止) + 受け入れ条件転記 + Self-Test Report
- spec §3 Non-goals (touch しない箇所 6 項) → Task 1-4 の diff 検査 Step + Task 6 の repo scan で逸脱検知

### 2. Placeholder scan

- [ ] "TBD" / "TODO" / "fill in" / "implement later" の有無 → 全 Task で具体的 `old_string` / `new_string` / コマンド・期待出力を明記済
- [ ] "Similar to Task N" の有無 → 各 Task で完全なコード/コマンドを記述済 (繰り返しになっても省略しない)
- [ ] "Add appropriate error handling" 等の vague 表現 → 無し
- [ ] "Write tests for the above" → 本 PR は doc-only で TDD 不適用、`TDD Note` 節で明示済

### 3. Type / 名称 consistency

- [ ] `with_hint` (signature 不変) — Task 1 / Task 6 で一貫
- [ ] `with_default_hint` (本 PR で touch なし) — spec §3 / Task 4 で touch しない明記
- [ ] `toErrorState` / `ErrorState.message` / `ErrorState.hint` — Task 2 (Rust comment) と Task 4 (Markdown) で同一名称
- [ ] `appErrorMessage` / `appErrorHint` (dangling、除去対象) — Task 1 / Task 2 / Task 4 で全件除去、Task 6 で repo scan
- [ ] `appErrorCodeIs` (live、touch なし) — Task 4 で明示維持

### 4. Commit / 規約 consistency

- [ ] commit 1 message (`docs(gui): #699 ...`) と commit 2 message (`docs: #699 ...`) が `Refs #699` + Co-Authored-By を持つ
- [ ] PR title・body に Closes / Fixes / Resolves が無い (Iron Law 4)
- [ ] PR body の受け入れ条件は spec §8 から逐条転記 (Iron Law 1)
- [ ] Self-Test Report は machine-verified を `[x]`、machine-unverifiable を plain bullet `-` で書き分け済

---

**Plan complete.** 起点 commit: spec `35e884e` (本 plan は別 commit)。
