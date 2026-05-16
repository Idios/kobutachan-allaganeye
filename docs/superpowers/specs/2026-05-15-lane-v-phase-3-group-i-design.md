# L2 Lane V Phase 3: Group I #699 AppError stale docstring 更新 設計

> **Status**: v0.2.0 リリースゲート Lane V Phase 3 (Group I の Phase 3、最終 phase)
>
> **Scope**: 1 PR (1 spec / 1 章) — [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699)
>
> **session**: `modest-darwin-6f2394` (2026-05-15 brainstorming、Idios + Claude Opus 4.7)
>
> **依存元 PR**: [#745](https://github.com/Idios/kobutachan-allaganeye/pull/745) (Lane V Phase 2 / #694、MERGED) — 本 spec が扱う dangling 参照の発生源
>
> **親 plan**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md](../plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md) §Group I (Phase 3)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) | OPEN | **本 PR で完遂** (AppError 関連 stale docstring 3 file 更新) |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | CLOSED (PR #689 merged) | AppError migration 起点。stale 表現を「post-#663 状態」に直す際の基準 |
| [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) | OPEN (PR #745 MERGED、`/close-issue` 待ち) | `*ErrorState` unified refactor。`appErrorMessage` / `appErrorHint` helper を削除し `toErrorState` に集約 → 本 spec が扱う dangling 参照の発生源。`appError.ts` 側の docstring 整合は #694 で実施済 |
| PR #745 レビューコメント (ExportScreen finding) | parked (#699 コメントの「案」) | **本 spec scope 外**。§7 Q2 参照 |

## §1 Background — #694 が #699 の前提を動かした

issue #699 body は #694 着手前 (PR #689 final code review 時点) の記述であり、現在の実態とずれている。#694 (PR #745, Lane V Phase 2) が `appErrorMessage` / `appErrorHint` helper を削除し `toErrorState` に集約したことで、#699 の前提が以下のように変化した:

1. **issue body 第 1 行 (`appError.ts:57-62` の `appErrorHint` docstring)** — `appErrorHint` 関数ごと #694 で削除済。Phase 2 plan Task 12(c) が「`appErrorHint` の上の `**将来用**` 等の docstring も整合更新」を実施済 → **本 PR の対象から外れる** (該当 docstring はもう存在しない)
2. **issue body 第 2 行 (`error.rs:28-34` の `with_hint` docstring)** — stale のまま残存 → 本 PR の core target
3. **#694 が新たに発生させた dangling 参照** — 削除された `appErrorMessage` / `appErrorHint` を指す参照が repo 内に 2 箇所残存。Phase 2 spec §11 は `docs/ui-interaction-spec.md` を「本 PR 内で touch なし」と明記しており、意図的に Phase 3 送りにされている

Phase 2 spec は §3 Non-goals と §9 リスク表で「#699 のスコープを『残った Rust / その他 docstring』に絞る **(Phase 3 spec で確定)**」と本 spec に明示委譲しており、本 spec がその確定版である。

issue #699 body には `## 受け入れ条件` セクションが存在しないため、受け入れ条件は本 spec §8 で定義する。

## §2 Goals

1. `error.rs:28-34` の `with_hint` docstring を post-#663 状態に更新する: 「将来用 / 現状 production code では未使用」表現を除去し、production 経路が `with_default_hint()` であること・`with_hint` は test と将来 Approach C hybrid 移行用の override API であること・`#[allow(dead_code)]` の意味 (test 専用 API) を明記する
2. #694 で削除された `appErrorMessage` / `appErrorHint` を指す dangling 参照 2 箇所 (`extract_brightness_window.rs:77` の test コメント / `ui-interaction-spec.md:107-109` の living spec doc) を現行 symbol (`toErrorState` / `ErrorState`) に更新する
3. **挙動変更ゼロ** (`///` docstring と `//` comment のみの変更、関数 signature / body / test assertion は不変) を保証する
4. Iron Law 1〜6 を厳守する (1 PR = 1 issue / `Refs #699` / PR Pre-flight Step 0-4 / Self-Test Report)

## §3 Non-goals (scope 外明記)

- **`gui/src/lib/appError.ts` の更新**: #694 (PR #745) で `appErrorHint` 関数ごと削除 + docstring 整合済。本 PR では touch しない
- **`error.rs:47-49` `with_default_hint` docstring の「将来 Approach C への hybrid 移行時に必要」記述**: #663 spec §5.1 で `with_hint` を「将来 Approach C への hybrid 移行時の override 用 API として温存」と意図的に決定済。**stale ではない** (実在する将来設計パスの記述) ため touch しない
- **`error.rs:96-105` `From<String>` impl docstring**: 既に post-#663 で正確 (「lib.rs 全 80 site の hint chain 規律と整合 (#663)」)。touch しない
- **`error.rs:41-45` `with_stacktrace` への docstring 新規追加**: 現状 docstring 無し。「docstring が無い」ことは stale ではない。新規追加は scope creep
- **`docs/superpowers/plans/*` / `docs/superpowers/specs/*` 内の `appErrorMessage` / `appErrorHint` 参照**: 歴史的設計文書 (point-in-time record)。書き換えは履歴改変になるため対象外
- **ExportScreen の local useState `[error, errorHint]` pair refactor**: PR #745 レビューコメントが #699 に「(C) 既存 issue 追記」案として追記した finding。ただしこれはコード refactor であり docstring 更新ではなく、doc-only (P3-low) の #699 に fold すると Iron Law 3 scope creep。§7 Q2 で「PR #745 コメントの『案』のまま据え置き、次回 roadmap update / 後続セッションで他の設計残債と一緒に再トリアージ」と決定。本 spec scope 外
- **挙動変更を伴う一切の変更**: 関数 signature / body / test assertion の変更はしない。本 PR は doc-only

## §4 Architecture (1 doc-only PR / 2 commit 推奨構成)

Iron Law 3 (1 PR = 1 issue) に従い 1 PR で完遂する。3 file はいずれも「#694 で削除された AppError symbol を指す stale 参照の post-#663/#694 同期」という単一概念であり、multi-PR 分割は意味がない。実質の唯一の自由度は commit 粒度で、意味単位として **2 commit** を推奨する (PR サイズが小さいため 1 commit でも可)。

```text
═══════════════════════════════════════════════════════════════════════════
SINGLE PR (1/1)  —  Issue #699, Lane V Phase 3 (Group I 最終 phase)
═══════════════════════════════════════════════════════════════════════════
  commit 1: gui/src-tauri/src/error.rs
            gui/src-tauri/tests/extract_brightness_window.rs
            → src-tauri 内の with_hint docstring + appErrorHint dangling
              コメントを post-#663/#694 状態に更新 (どちらも Rust 側)
  commit 2: docs/ui-interaction-spec.md
            → AppError code 分岐ルール節の appErrorMessage / appErrorHint
              参照を toErrorState 経由の ErrorState.message / .hint に更新
```

spec doc 自体 (本ファイル) は brainstorming 段階で別途 commit 済 (実装 PR には含めない)。

## §5 詳細設計

### §5.1 `gui/src-tauri/src/error.rs:28-34` — `with_hint` docstring

**Before (stale)**:

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

**After**:

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

**変更点の根拠**:

- 「将来用 — 現状 production code では未使用」→ post-#663 では誤り。`with_default_hint()` が production 経路 (lib.rs 全 80 site) であり、`with_hint` は「production 非経由」だが「未使用」ではない (test が参照)。issue body 対応方針の文言を採用
- dangling 参照 `gui/src/lib/appError.ts::appErrorHint で同じく保留中` を除去 — `appErrorHint` 関数は #694 で削除済
- 「将来 Approach C への hybrid 移行用 API」の framing は維持 — #663 spec §5.1 で意図的に温存決定された正確な記述
- `#[allow(dead_code)]` の意味 (test 専用 API のため非 test build で warning を出さない) を明記 — #663 spec §5.1 の決定理由を docstring に反映

### §5.2 `gui/src-tauri/tests/extract_brightness_window.rs:77` — test コメント

**Before (stale)**:

```rust
    // Pin the error contract so frontend `appErrorHint` can rely on it: the
    // failure path is ffmpeg returning non-zero exit (the binary is spawned
    // successfully but cannot open the input). `subprocess.exit_failed` is
    // ...
```

**After**:

```rust
    // Pin the error contract so the frontend hint rendering (`toErrorState`
    // → `ErrorState.hint`) can rely on it: the failure path is ffmpeg
    // returning non-zero exit (the binary is spawned successfully but cannot
    // open the input). `subprocess.exit_failed` is ...
```

**変更点の根拠**:

- test コメント内の dangling な `appErrorHint` 参照を現行 symbol に更新 — #694 で frontend の hint 描画は `toErrorState(e).hint` を `InlineErrorHint` component に渡す経路に変わった
- コメント後半の `subprocess.exit_failed` / `subprocess.spawn_failed` の契約説明は正確なので不変
- 変更は `//` コメント 1〜2 行の rewrap のみ (実装時の改行位置調整は許容)。test assertion・関数本体は一切 touch しない

### §5.3 `docs/ui-interaction-spec.md:107-109` — living spec doc

「AppError `code` ベースの分岐ルール (#663)」節の item 2。

**Before (stale)**:

```markdown
2. その他の AppError code → inline error
   - 1 行目: `appErrorMessage(e)` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `appErrorHint(e)` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
```

**After**:

```markdown
2. その他の AppError code → inline error
   - catch path で `toErrorState(e)` により `ErrorState { message, hint, code }` に正規化 (#694)
   - 1 行目: `ErrorState.message` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `ErrorState.hint` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
```

**変更点の根拠**:

- `appErrorMessage(e)` → `ErrorState.message` / `appErrorHint(e)` → `ErrorState.hint` — 両 helper は #694 で削除済
- `toErrorState(e)` による正規化ステップを 1 行追加 — post-#694 の実際の catch path フローを反映
- item 1 の `appErrorCodeIs(e, 'state.mtime_conflict')` は #694 で**維持された** live export なので touch しない (Phase 2 spec §2 goal 3)
- markdownlint 対象ファイルのため、リスト構造・インデントを維持し `bash scripts/check-markdownlint.sh` で検証する

### §5.4 touch しない箇所 (scope 境界の明示)

レビュー時の scope 確認用。以下は本 PR で**変更しない**:

| 箇所 | 理由 |
| --- | --- |
| `gui/src/lib/appError.ts` 全体 | #694 (PR #745) で `appErrorHint` 関数削除 + docstring 整合済 |
| `error.rs:47-49` `with_default_hint` 「将来 Approach C」記述 | #663 spec §5.1 で意図的に正確。stale ではない |
| `error.rs:96-105` `From<String>` impl docstring | 既に post-#663 で正確 |
| `error.rs:41-45` `with_stacktrace` | docstring 無し。「無い」は stale ではない。新規追加は scope creep |
| `docs/superpowers/plans/*` / `specs/*` の `appErrorHint` 参照 | 歴史的設計文書 (point-in-time record)。履歴改変対象外 |
| ExportScreen の local useState pair | §7 Q2 で据え置き決定。コード refactor は doc-only #699 の scope 外 |

## §6 Test 戦略 / Iron Law 整合

### §6.1 TDD 規律 — doc-only PR の扱い

`superpowers:test-driven-development` の HARD-GATE は「NO PRODUCTION CODE WITHOUT FAILING TEST FIRST」だが、本 PR は **production code の挙動を一切変更しない** (`error.rs` の `///` docstring と `extract_brightness_window.rs` の `//` comment のみ、`with_hint` の signature / body は不変)。よって「先に書く failing test」は存在せず、新規 test は書かない / 既存 test は変更しない。

TDD の趣旨 (挙動の保証) は、本 PR では「**挙動変更ゼロの証明**」に置き換えて担保する:

1. `cargo test` (lib + integration) が既存 baseline のまま全 pass する (件数不変)
2. PR diff が `error.rs` は `///` 行のみ・`extract_brightness_window.rs` は `//` 行のみ・`ui-interaction-spec.md` は Markdown 散文のみであることを PR 本文で逐条確認
3. `git diff` で関数 signature / body / `#[allow(dead_code)]` attribute・test assertion に変更が無いことを確認

### §6.2 自動チェック (Iron Law 6 PR Pre-flight)

PR 作成時、変更 path (`gui/src-tauri/**` + `docs/`) に応じて以下を全 pass させる。

**Pre-flight Step 0-4**:

- **Step 0 (ハードゲート)**: `gh pr list --search "#699" --state open` で並行 PR ゼロ確認 (<1s、build/verify の前)。本 spec 作成時点では 0 件
- **Step 1**: `git fetch origin develop-0.2.0`
- **Step 2**: `git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認
- **Step 3**: touched files 交差判定 — 本 PR の touched = `gui/src-tauri/src/error.rs` / `gui/src-tauri/tests/extract_brightness_window.rs` / `docs/ui-interaction-spec.md`
- **Step 4**: `gh pr list --search "#699" --state all` で並行 worktree PR 再確認

**path 別自動チェック**:

- `cd gui/src-tauri && cargo check` (exit 0、rustdoc コメントの破損が無いことを含めて確認)
- `cd gui/src-tauri && cargo test` (lib + integration、既存 baseline 全 pass / 件数不変)
- `bash scripts/check-markdownlint.sh` (`docs/ui-interaction-spec.md` 更新分、exit 0)
- Python ファイル変更なし → `ruff` / `pyright` / `pytest` は対象外 (念のため実行しても regression なし)
- GUI frontend (`gui/src/**`) 変更なし → `npm run lint` / `typecheck` / `test` / `build` は対象外

### §6.3 実機検証 — 不要

Iron Law 6 の実機検証 trigger は「ロジック変更 (`gui/src-tauri/**` 等)」だが、本 PR の `gui/src-tauri/**` 変更は **`///` docstring と `//` comment のみで挙動変更ゼロ**であり、ロジック変更ではない。GPU / audio / 長時間動画 / GUI Tauri 起動いずれの挙動も変わらないため、Idios への実機検証依頼は不要。

ただし透明性のため、PR 本文の Self-Test Report に「`gui/src-tauri/**` を touch するが docstring/comment のみ・挙動変更ゼロ・関数 body 不変」を明記し、レビュー (`/review-pr` / `/iterate-review`) でこの分類が妥当か確認できるようにする。「mock テスト pass = 実機検証不要」を装う Red Flag とは異なり、本件は**そもそも挙動が変わらない**ことが理由である点を明示する。

### §6.4 CI 整合

PR CI の全 job を pass する想定:

- `gui-rust` (`cargo check` / `cargo test`): docstring/comment のみのため pass、regression check 必須
- `doc-tauri-commands-drift`: `error.rs::default_hint_for_code` と `docs/tauri-commands.md` の drift 検査。`with_hint` docstring は `default_hint_for_code` と無関係、`docs/tauri-commands.md` も touch しないため drift 影響なし → pass 維持
- `markdownlint`: `docs/ui-interaction-spec.md` 更新分で関係 → §6.2 で事前 pass
- `python` / `gui-frontend` / `installer-pester` / `validate-checklist`: 影響なし、pass 維持

### §6.5 Iron Law 1〜6 整合

- **Iron Law 1**: #699 issue body には `## 受け入れ条件` が無いため本 spec §8 で定義。PR 本文で §8 各項目を逐条引用 + diff 引用。`/review-pr` 時に `/enforce-acceptance-criteria` skill を呼ぶ
- **Iron Law 2**: 本 spec は 1 件の brainstorming 設計、bulk operation なし。merge 後の #699 close は `/close-issue` skill で実施
- **Iron Law 3**: 1 PR = 1 issue 厳守。ExportScreen refactor finding は §3 / §7 Q2 で明示的に scope 外。実装中に「ついでに」他の docstring を直す誘惑が出たら `scope-guard` skill で判定 (§5.4 の touch しない箇所を厳守)
- **Iron Law 4**: PR / commit に Closes / Fixes / Resolves 禁止、`Refs #699` のみ。merge 後 `/close-issue` で実測再検証 (本 PR の場合「実測」= 3 file の diff 確認 + dangling 参照の grep ゼロ確認)
- **Iron Law 5**: brainstorming で 2 件の AskUserQuestion (§7) で scope を確定済。実装中に追加 ambiguity が出れば AskUserQuestion 実施
- **Iron Law 6**: §6.2 で Step 0-4 + path 別自動チェック、§6.3 で実機検証不要の理由を明記

## §7 採用方針サマリ (brainstorming Q&A trace)

| 決定 | 採用 | 棄却 | 理由 |
| --- | --- | --- | --- |
| sweep 範囲 (Q1) | 3 箇所すべて (`error.rs:28-34` + `extract_brightness_window.rs:77` + `ui-interaction-spec.md:107-109`) | `error.rs` のみ / コード内 2 箇所のみ | 3 つとも #694 で削除された AppError symbol を指す stale 参照で issue テーマ「AppError 関連 stale docstring を post-#663 状態に更新」に合致。Phase 2 spec が「その他 docstring」の確定を本 spec に明示委譲済 |
| PR #745 コメント (ExportScreen finding) の扱い (Q2) | PR #745 コメントの「案」のまま据え置き、次回 roadmap update / 後続セッションで再トリアージ | 別 issue 即起票 / out of scope 明示トリアージのみ | #699 は doc-only (P3-low) 維持が前提。ExportScreen の local useState pair refactor はコード refactor であり docstring 更新ではない。#699 に fold すると Iron Law 3 scope creep。新 issue 起票も含め判断は後送りとする |
| PR 戦略 | 1 doc-only PR / 2 commit | multi-PR 分割 / 他 lane に fold | Iron Law 3 (1 PR = 1 issue)。3 file は単一概念 (#694 stale 参照同期) で分割の意味がない。file territory も error.rs / test / spec doc で他 lane と独立 |
| TDD の適用 | 「挙動変更ゼロの証明」で代替 (§6.1) | 新規 test 追加 / 既存 test 改変 | docstring `///` + comment `//` のみで production 挙動が変わらないため「先に書く failing test」が存在しない。`cargo test` baseline 維持 + diff がコメント行限定であることの確認で担保 |

## §8 受け入れ条件

issue #699 body に `## 受け入れ条件` が無いため、issue body の対応方針 + §7 の Q1/Q2 決定から導出する。

- [ ] `gui/src-tauri/src/error.rs:28-34` の `with_hint` docstring が §5.1 After 相当に更新されている: 「将来用 / 現状 production code では未使用」表現が除去され、production 経路が `with_default_hint()` (lib.rs 全 80 site、#663) である旨が明記されている
- [ ] 同 docstring から dangling 参照 `gui/src/lib/appError.ts::appErrorHint` が除去されている
- [ ] 同 docstring に `#[allow(dead_code)]` の意味 (test 専用 API のため非 test build で dead-code warning を抑止) が明記されている
- [ ] 同 docstring の「将来 Approach C への hybrid 移行用 API」の framing は維持されている (#663 spec §5.1 整合)
- [ ] `gui/src-tauri/tests/extract_brightness_window.rs:77` 付近の test コメントから dangling `appErrorHint` 参照が除去され、現行 symbol (`toErrorState` / `ErrorState.hint`) に更新されている
- [ ] `docs/ui-interaction-spec.md` の「AppError `code` ベースの分岐ルール」節 item 2 の `appErrorMessage(e)` / `appErrorHint(e)` 参照が `toErrorState(e)` 経由の `ErrorState.message` / `ErrorState.hint` に更新されている
- [ ] 同節 item 1 の `appErrorCodeIs(...)` は #694 維持 export のため touch されていない
- [ ] `error.rs` の `with_hint` 関数 signature / body / `#[allow(dead_code)]` attribute は不変 (docstring `///` 行のみ変更)
- [ ] `extract_brightness_window.rs` の変更は `//` コメント行のみ (test assertion / 関数本体は不変)
- [ ] `gui/src/lib/appError.ts` は本 PR で touch されていない (#694 で対応済)
- [ ] `error.rs:47-49` `with_default_hint` docstring・`error.rs:96-105` `From<String>` docstring・`with_stacktrace` は本 PR で touch されていない (§5.4)
- [ ] repo 全体で `appErrorMessage` / `appErrorHint` への dangling 参照が `docs/superpowers/plans/*` `specs/*` の歴史的文書以外に残っていない (`git grep` で確認)
- [ ] `cargo check` / `cargo test` (lib + integration) が既存 baseline のまま全 pass (件数不変)
- [ ] `bash scripts/check-markdownlint.sh` が exit 0
- [ ] Iron Law 6 PR Pre-flight (Step 0-4) 全 pass、CI 全 job pass
- [ ] PR 本文に「docstring / comment のみ・挙動変更ゼロ・関数 body 不変」が明記され、Self-Test Report 規約 (machine-verified は `[x]`、machine-unverifiable は plain bullet) に準拠している

## §9 リスク表

| リスク | 影響 | 緩和策 |
| --- | --- | --- |
| docstring 更新の「ついで」に §5.4 の touch しない箇所 (例 `with_default_hint` の「将来 Approach C」) を直してしまう | Iron Law 3 scope creep、PR が doc-only でなくなる | §5.4 の touch しない箇所一覧を実装時に逐条照合。`scope-guard` skill で検知 |
| `ui-interaction-spec.md` の編集で markdownlint 違反 (MD028 / MD056 等) を踏む | CI `markdownlint` job fail | リスト構造・インデントを維持。編集後 `bash scripts/check-markdownlint.sh` をローカル実行。table 編集は無いため MD056 は低リスク |
| `extract_brightness_window.rs` のコメント rewrap で意図せず test コード行を巻き込む | 挙動変更ゼロが崩れる | 変更を `//` 行に限定。`git diff` で `//` 以外の行が変わっていないことを commit 前に確認 |
| `with_hint` docstring の文言が `error.rs::tests` の実際の test 関数名とずれる | docstring が再び不正確になる | §5.1 After で参照する test 名 (`serialize_app_error_roundtrips` / `with_default_hint_does_not_overwrite_explicit_hint`) は現行 `error.rs` の `#[cfg(test)]` ブロックに実在することを確認済。実装時に再 grep 確認 |
| #694 issue が `/close-issue` 未実施の OPEN 状態であることに起因する混乱 | #699 PR レビュー時に「#694 が未完では?」と誤解 | PR 本文で「#694 は PR #745 MERGED 済、issue close は `/close-issue` 待ち。本 PR は #745 merge 後の Phase 3」と明記 |
| ExportScreen finding を「据え置き」にしたことが将来忘れられる | 設計残債が untracked のまま放置 | PR #745 コメントは #699 に残置されたまま (削除しない)。本 spec §3 / §7 Q2 にも記録。次回 roadmap update 時の残債棚卸し対象 |

## §10 Open questions

brainstorming の 2 件の AskUserQuestion (§7 Q1 / Q2) で scope は確定済。残 open question は無し。実装中に追加 ambiguity が出れば PR 内で AskUserQuestion を実施する。

## §11 関連 doc

- [docs/superpowers/specs/2026-05-14-lane-v-phase-2-group-i-design.md](2026-05-14-lane-v-phase-2-group-i-design.md) — Phase 2 spec。§3 Non-goals / §9 リスク表で #699 のスコープを本 spec に委譲、§11 で `ui-interaction-spec.md` を Phase 3 送りと明記
- [docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md](2026-05-11-lane-v-phase-1-group-i-design.md) — Phase 1 spec。hint UI 規約の起点
- [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](2026-05-08-l2-appError-migration-completion-design.md) — #663 AppError migration 起点 spec。§5.1 で `with_hint` の `#[allow(dead_code)]` 温存と「将来 Approach C」を意図的に決定
- [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md](../plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md) §Group I — 親 plan、Lane V 3-phase 構成
- [docs/ui-interaction-spec.md](../../ui-interaction-spec.md) — 本 PR §5.3 で「AppError `code` ベースの分岐ルール」節を post-#694 に更新
- [docs/l2-workflow.md](../../l2-workflow.md) §PR 作成 Pre-flight / §Self-Test Report 規約 / §実機検証 trigger 表 — 全項目で適用
- [docs/tauri-commands.md](../../tauri-commands.md) — `doc-tauri-commands-drift` CI job の対象 (本 PR では touch なし、drift 影響なし)

---

## §12 Amendment Log

### 2026-05-15: Phase C Amendment — sweep 範囲 expand

Phase C subagent の repo-wide scan (`git grep -nE "appErrorMessage|appErrorHint" -- ':!docs/superpowers/'`) で brainstorming sweep に漏れていた dangling 参照 2 file を検出:

- `docs/ui-interaction-spec.md:693` (§2.4.9 FrameStrip overlay の inline 診断メッセージ記述) — Phase C 中に commit `a752fc0` で fix 済
- `docs/tauri-commands.md` lines 10 / 58 / 65 / 73 (frontend narrowing helper 列挙 + code example の 4 箇所) — Phase D で fix

user 承認 (AskUserQuestion 2026-05-15) のもと spec §8 AC「repo 全体で残っていない」を honor するため上記 5 site を本 PR scope に追加。本 spec §3 / §5 / §8 は brainstorming 時点の理解 (3 file) を記録した snapshot として保持し、最終的な PR scope は本 Amendment Log を併せて参照する。

追加 AC (本 PR 完遂条件に追加):

- [ ] `docs/ui-interaction-spec.md:693` (§2.4.9 FrameStrip overlay) の `appErrorMessage` + `InlineErrorHint` 参照が `toErrorState(e)` 経由の `overlayState.message` / `overlayState.hint` に更新されている (commit `a752fc0`)
- [ ] `docs/tauri-commands.md` line 10 / 58 / 65 / 73 の `appErrorMessage` 参照 4 箇所が `toErrorState` (および code example では `toErrorState(e).message`) に更新されている (Phase D)
- [ ] `git grep -nE "appErrorMessage|appErrorHint" -- ':!docs/superpowers/'` が 0 件 (repo-wide dangling-ref ゼロを実測確認)

学んだこと:

- brainstorming sweep は対象キーワードを限定して grep するだけでは不十分。`git grep -nE "<symbol>" -- ':!<exclude>'` を repo-wide で実行して全件確認するのがより堅実。次回類似 task では Q1 提示前に full grep を実施する
- spec §8 で「repo 全体で残っていない」と書いた AC は強い (完全達成の証明を要求する)。AC 文言を緩めるか、AC を honor して全件 fix するかが Phase C/D で問われた選択

### 2026-05-16: Round 1 Amendment — /iterate-review L31 + L107 number drift fix

/iterate-review (PR #746) Round 1 で `error.rs:31` 新規書き下ろし docstring の「lib.rs 全 80 site に適用済」が実測 85 と乖離していることを subagent が (A) で flag。user 承認 (AskUserQuestion 2026-05-16) のもと:

- **Finding #1 (A)**: `error.rs:31` の「80 site」→「80+ site」(count drift 耐性のある近似表記、Q2 で選択)
- **Q3 で「L31 + L107 同時修正」選択**: pre-existing `error.rs:107` `From<String>` impl docstring の同じ inaccuracy も併修
- **Finding #2 (C)**: `gui/src/state/recentStore.ts:34` JSDoc が旧 field 名 `loadError` を参照 (正は `loadErrorState`)。#699 コメントに 2 件 pre-tracked 済 (2026-05-14 PR #745 review + /close-issue (#694) Step 5 由来) のため (C) で deferred、本 PR scope 外

spec §5.4 は L107 (`error.rs:96-105 From<String> impl docstring`) を「touch しない」と記述していたが、Round 1 で touch することに retroactive 同意。spec §5.4 本体は brainstorming-time snapshot として保持し、最終 PR scope は本 Amendment Log を併せて参照する。

追加 AC (Round 1 由来):

- [ ] `error.rs:31` (with_hint docstring) の「80 site」が「80+ site」に修正されている
- [ ] `error.rs:107` (`From<String>` impl docstring) の「80 site」が「80+ site」に修正されている
- [ ] `git grep -nE "全 80 site" -- gui/src-tauri/src/error.rs` で 0 件 (実測、`80+` への置換が完全であることを確認)

学んだこと:

- /iterate-review subagent は doc-only PR でも新規書き下ろし行の factual accuracy 違反を (A) で flag する。Phase A code quality review の「minor 非 actionable」判断より strict (より正しい選択)
- 近似表記 (`80+ site`) は exact (`85 site`) より count drift 耐性が高く、保守負債を増やさない。次回類似 docstring 起草時は最初から近似表記を採用する

---

**brainstorming 完了**。本 spec を起点に `writing-plans` skill で実装計画を策定する。
