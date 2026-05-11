# L2 Lane I-A: AppError migration 完遂 (legacy fallback 撤去 + per-code default hint 全 80 site 適用) 設計

> **Status**: v0.2.0 リリースゲート Lane I-A (Group A) — wave 0 起点 (Lane I-B = Group B の前提)
> **Scope**: [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) 単独 (1 spec / 1 章 / 1 PR)
> **session**: `tender-khayyam-03d618` (2026-05-08 brainstorming、Idios + Claude Opus 4.7)
> **依存元 PR**: [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) (`AppError` struct 導入) / [#665](https://github.com/Idios/kobutachan-allaganeye/pull/665) (`Result<T, AppError>` 23 commands migration、本 spec の前提として `ea9bca9` で完了済)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | OPEN | **本 spec で対応** (issue body は実態に合わせて PR 内で更新) |
| [#614](https://github.com/Idios/kobutachan-allaganeye/issues/614) | CLOSED (PR #661 で完了) | `AppError` struct + `install_panic_hook` + `ErrorModal` 導入元、本 spec で再 open しない |
| [#619](https://github.com/Idios/kobutachan-allaganeye/issues/619) | CLOSED (PR #665 で完了) | `Result<T, AppError>` 23 commands migration を Round 1 review (`ea9bca9`) で完遂、本 spec はこの上に乗る |
| [#514](https://github.com/Idios/kobutachan-allaganeye/issues/514) | CLOSED | `state.mtime_conflict` で ConflictModal を出す経路、本 spec の legacy fallback 撤去で「`startsWith('conflict:')`」も削除 |
| [#624](https://github.com/Idios/kobutachan-allaganeye/issues/624) | OPEN (Lane IV-b) | pr-checklist CI bug、本 spec の Self-Test Report 記法 (bullet) で回避 (本 spec で修正対象ではない) |

## §1 Background — PR #665 で核心 migration は完了済み

[#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) の元 issue body は「legacy 17 Tauri command の `Result<T, String>` を `AppError::to_wire_string()` で返す形に migrate」と書かれているが、実際には PR #665 (`ea9bca9: 23 commands を Result<T, AppError> に migrate`) で **23 commands の `Result<T, String>` → `Result<T, AppError>` migration が既に完遂**している。`to_wire_string()` 自体は production 未使用で削除され ([gui/src-tauri/src/error.rs](gui/src-tauri/src/error.rs) のテストコメント参照)、現在は Tauri が `serde::Serialize` 経由で structured object を直接 frontend に届ける形。

そのため本 spec が扱う #663 の残作業は次の 4 軸に整理される。

- **(A) Legacy `startsWith('conflict:')` fallback 撤去**
  ([gui/src/state/metadataStore.ts:209](gui/src/state/metadataStore.ts:209) の `appErrorCodeIs(e, 'state.mtime_conflict') || msg.startsWith('conflict:')` から後半削除)
- **(B) Per-code default hint helper 追加と全 80 site への適用**
  (Rust `AppError` に `default_hint_for_code()` + `with_default_hint()` を追加、lib.rs 全 80 site で chain)
- **(C) Frontend での hint 表示**
  (各 store の error フィールドに `*ErrorHint` ペアを追加、各 inline error の 2 行目に hint を render)
- **(D) docs / issue body 整合**
  (`docs/tauri-commands.md` / `docs/ui-architecture.md` / `docs/ui-interaction-spec.md` 更新 + 元 issue body 書き換え)

## §2 Goals

1. legacy raw String error を許容する `startsWith('conflict:')` fallback を完全に撤去し、`appErrorCodeIs(e, 'state.mtime_conflict')` のみで分岐させる (PR #663 の核心受け入れ条件)
2. 24 codes (or-pattern 展開後 #692) の AppError code に対する default 日本語 hint を `error.rs` の 1 つの mapping table に集約し、全 80 site の `AppError::new(...)` に `.with_default_hint()` を chain する (= site 個別の hint 揺れを発生させずに 80 site 網羅)
3. frontend が AppError の `code` で error 種別を判定し、hint があれば inline error の 2 行目に表示する規約を確立する
4. AppError code 体系と使い分けを `docs/tauri-commands.md` / `ui-architecture.md` § 4 / `ui-interaction-spec.md` § 1.5 に明文化し、新規 command 追加時の指針を残す
5. 元 issue 本文を「PR #665 後の残作業として何を完遂したか」が読み取れる形に書き換える (Iron Law 4 整合: PR / commit には Closes/Fixes 禁止、issue 本体に記録を残す)

## §3 Non-goals (scope 外明記)

- **ErrorModal (#614) への AppError 統合**: `ErrorModal` は uncaught panic / React error 用の経路であり、Tauri command 経路は catch ブロックで処理する規約を維持する
- **`globalErrorListener.ts` への AppError parse 追加**: Tauri command の reject は invoke 側 catch で処理する設計、`'tauri-command'` errorCategory は将来別 issue (handle 漏れ統合観測等) に備える reservation のままとする
- **`ConflictModal` での AppError hint 表示**: modal 内に既に compose hint テキスト (`「上書き」で外部変更を破棄...`) があるため、AppError の `state.mtime_conflict` default hint は「modal の表示には乗せない」として scope 外
- **新規 Tauri command の追加 / 削除**: 機能拡張は別 issue (Lane I-B = Group B 等)
- **自動 telemetry / Sentry crash reporter 統合**: 元 issue scope 外明記
- **関連 issue (#619 / #614 等 CLOSED 群) の body 修正**: 本 spec では触らない
- **Lane I-B (Group B) の作業先取り**: lib.rs 共有 issue (`#679` / `#648` / `#644`) は Lane I-A merge 後に着手の規約を厳守

## §4 Architecture (4-layer)

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Rust error.rs (pure helper module)                              │
│   - default_hint_for_code(code: &str) -> Option<&'static str>             │
│   - AppError::with_default_hint(self) -> Self                             │
│   - 24 codes (or-pattern 展開後 #692) への日本語 hint mapping table                                │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓ chain
┌──────────────────────────────────────────────────────────────────────────┐
│ Layer 2: Rust lib.rs (mechanical migration)                              │
│   - 全 80 site で `AppError::new(code, msg).with_default_hint()` 形式に    │
│   - From<io::Error> / From<serde_json::Error> も hint chain 経路に乗る   │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓ Tauri serialize → invoke reject (frontend)
┌──────────────────────────────────────────────────────────────────────────┐
│ Layer 3: Frontend state (per-store error+hint pair)                      │
│   - metadataStore: 5 error / 5 errorHint state                            │
│   - recentStore: addError + addErrorHint 等                               │
│   - 各 catch site で `appErrorMessage(e)` + `appErrorHint(e)` 併用       │
│   - metadataStore:209 の `|| msg.startsWith('conflict:')` を削除          │
└──────────────────────────────────────────────────────────────────────────┘
                              ↓ subscribe
┌──────────────────────────────────────────────────────────────────────────┐
│ Layer 4: Frontend UI (inline error 2-line render)                        │
│   - 5 screen + RestoreButton で hint があれば 2 行目を `var(--ae-text-dim)` で render│
│   - hint 専用 CSS class (`.errorHint`)                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

各 layer は独立したテスト可能ユニット。Layer 1 は pure (no I/O)、Layer 2 は mechanical (compile check + 既存 cargo test 全 pass で全 site 通過保証)、Layer 3 は store unit test、Layer 4 は component test。

## §5 Layer 1 設計: Rust `error.rs`

### §5.1 既存 API の温存と修正

```rust
impl AppError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self { ... }   // 温存
    pub fn with_hint(mut self, hint: impl Into<String>) -> Self { ... }                // #[allow(dead_code)] 削除
    #[allow(dead_code)] pub fn with_stacktrace(mut self, stacktrace: impl Into<String>) -> Self { ... } // 温存 (将来 Sentry 用)
}
impl From<std::io::Error> for AppError { ... }      // 内部に hint chain 追加 (§5.3)
impl From<serde_json::Error> for AppError { ... }   // 同上
impl From<String> for AppError { ... }              // 温存 (`internal.error` で hint None)
```

**`with_hint` の `#[allow(dead_code)]` は温存する** (production code は `with_default_hint` を使い、`with_default_hint` 内部で `self.hint` に直接代入するため `with_hint` は経由しない。`with_hint` は test (`error.rs::tests::serialize_app_error_roundtrips` および本 spec § 5.4 の `with_default_hint_does_not_overwrite_explicit_hint`) と将来 Approach C への hybrid 移行時の override 用 API として温存する。test 経路でしか使われないため、非 test build (`cargo build`) で dead code warning が出ないよう `#[allow(dead_code)]` を保持する)。

### §5.2 新規 API — `with_default_hint()` と `default_hint_for_code()`

```rust
impl AppError {
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
}

/// AppError code に対する日本語 default hint を返す。未登録 code は None。
/// 24 codes (or-pattern `io.would_block | io.timed_out` を 2 codes に展開後、22 hint
/// + 2 None = 24)。現在の lib.rs inventory: io.* / parse.* / state.* / subprocess.* /
/// validation.* / path.* / platform.* / internal.*。
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

### §5.3 `From<...>` impl の hint chain

`From<io::Error>` と `From<serde_json::Error>` は `?` 演算子で自動変換され call site で `.with_default_hint()` が呼ばれない。impl 内で自動 hint 付与する (= 設計選択 (i)、§設計セクション 2 で承認済)。

```rust
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        let code = match e.kind() { /* 既存 */ };
        AppError::new(code, e.to_string()).with_default_hint()  // ← 追加
    }
}
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        AppError::new("parse.json_invalid", e.to_string()).with_default_hint()  // ← 追加
    }
}
impl From<String> for AppError {
    fn from(message: String) -> Self {
        AppError::new("internal.error", message)
        // hint None で問題ない (default_hint_for_code でも internal.error は None マップ)
    }
}
```

### §5.4 Layer 1 の test (TDD red 起点、cargo test --lib)

```rust
#[cfg(test)]
mod tests {
    use super::*;
    // 既存 2 件 (serialize_app_error_roundtrips / app_error_display_format) は温存

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
        // 意図的 None 群
        assert!(default_hint_for_code("subprocess.cancelled").is_none());
        assert!(default_hint_for_code("internal.error").is_none());
        assert!(default_hint_for_code("unknown.code").is_none());
    }

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
}
```

## §6 Layer 2 設計: Rust `lib.rs` (mechanical migration)

全 80 site の `AppError::new(code, format!("..."))` を `AppError::new(code, format!("...")).with_default_hint()` chain に変更する。

- mechanical 操作なので site ごとの個別判断は不要
- `cargo check` で type 整合確認、`cargo test --lib` で既存 149 件 + Layer 1 新 6 件 = 155 件 pass を担保
- `with_hint` の `#[allow(dead_code)]` は §5.1 の決定通り温存 (削除しない)

### §6.1 例 (apply_changes 周辺、`state.mtime_conflict` の `AppError::new(...)` 呼び出し箇所)

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

## §7 Layer 3 設計: Frontend state (per-store error+hint pair)

### §7.1 metadataStore.ts の state field 拡張

| 既存 | 新規 (hint pair 追加) | 用途 |
| --- | --- | --- |
| `loadError: string \| null` | `loadErrorHint: string \| null` | DropScreen の load 失敗 |
| `applyError: string \| null` | `applyErrorHint: string \| null` | apply path |
| `restoreError: string \| null` | `restoreErrorHint: string \| null` | RestoreButton (#516) |
| `draftSaveError: string \| null` | `draftSaveErrorHint: string \| null` | draft save |
| `draftLoadError: string \| null` | `draftLoadErrorHint: string \| null` | draft load |
| `conflictError: string \| null` | (追加なし) | ConflictModal は scope 外 |

`DEFAULT_STATE` / `dismissError` 系も対応。

### §7.2 catch block の変更 pattern

```typescript
// before
try {
  ...
} catch (e) {
  set({ applying: false, applyError: appErrorMessage(e) });
}

// after
try {
  ...
} catch (e) {
  set({
    applying: false,
    applyError: appErrorMessage(e),
    applyErrorHint: appErrorHint(e),
  });
}
```

### §7.3 legacy `startsWith('conflict:')` fallback の撤去

```typescript
// metadataStore.ts:209 (before)
if (appErrorCodeIs(e, 'state.mtime_conflict') || msg.startsWith('conflict:')) {
  set({ applying: false, conflictError: msg });
  return;
}

// after
if (appErrorCodeIs(e, 'state.mtime_conflict')) {
  set({ applying: false, conflictError: msg });
  return;
}
```

直前 line 206-208 のコメント (「#619: structured AppError 化以後は code-based 判定を優先...」) も以下の趣旨に書き換え:

> #663: PR #665 で全 23 commands が AppError 化済のため、legacy raw String fallback は廃止する。code === 'state.mtime_conflict' のみで分岐する。

### §7.4 recentStore.ts の対応

`add_recent` / `clear_recent` / `read_recent` の catch path で同パターンを適用 (state field 名は実コード参照、追加方針は metadataStore と同じ「error + errorHint pair」)。

- Lane V Phase 1 #691 (PR #716) で 5 catch path × 5 `*ErrorHint` の clear matrix
  を test で pin、規約を明文化。本 spec で残された non-symmetric pattern
  (load() catch の partial clear) は採用案 **X** (symmetric 化) で削除し、各
  catch path を self-only に揃えた。

## §8 Layer 4 設計: Frontend UI (inline error 2-line render)

### §8.1 影響 component と変更内容

| component | 変更内容 |
| --- | --- |
| [DropScreen.tsx](gui/src/screens/DropScreen.tsx) | 既存 `setError(e.message)` を `setError(message)` + `setErrorHint(hint)` に拡張、card 内で 2 行目 render |
| [DetectingScreen.tsx](gui/src/screens/DetectingScreen.tsx) | `start_detect` 失敗時の inline error に hint 行追加 |
| [CompleteScreen.tsx](gui/src/screens/CompleteScreen.tsx) | RestoreButton 経由なので screen レベルでは追加変更不要 |
| [PreviewScreen.tsx](gui/src/screens/PreviewScreen.tsx) | preview load / apply error 等で hint 行追加 |
| [ExportScreen.tsx](gui/src/screens/ExportScreen.tsx) | per-match export error に hint 行追加 |
| [RestoreButton.tsx](gui/src/components/RestoreButton.tsx) | inline `role="alert"` 内で hint を 2 行目 render |

### §8.2 render pattern (例)

```tsx
{applyError && (
  <div role="alert" className={styles.errorBox}>
    <p className={styles.errorMessage}>{applyError}</p>
    {applyErrorHint && (
      <p className={styles.errorHint}>💡 {applyErrorHint}</p>
    )}
  </div>
)}
```

a11y: `role="alert"` は wrapper に維持、hint は補足情報として `<p>` を続ける (`docs/a11y-policy.md` の Modal / inline error 規約に整合させる; `aria-describedby` の追加は jest-axe テストで violation の有無を確認した上で判断)。

### §8.3 CSS

`gui/src/styles/tokens.css` (or 各 module.css) に共通 hint スタイルを追加:

```css
.errorHint {
  margin-top: var(--ae-spacing-xs);
  color: var(--ae-text-dim);
  font-size: var(--ae-text-sm);
  line-height: 1.5;
}
```

`var(--ae-text-dim)` は既存の補助色 token。red 系 error と区別される。

## §9 Test 戦略

### §9.1 Rust (cargo test --lib)

| test name | 検証内容 |
| --- | --- |
| `default_hint_covers_all_known_codes` (新) | 24 codes (or-pattern 展開後 #692) 全部 + 例外で None |
| `with_default_hint_attaches_known_code` (新) | hint chain 成功 |
| `with_default_hint_does_not_overwrite_explicit_hint` (新) | guard logic |
| `with_default_hint_returns_no_hint_for_unknown_code` (新) | 未登録 code |
| `from_io_error_attaches_default_hint` (新) | From impl の hint chain |
| `from_serde_json_error_attaches_default_hint` (新) | From impl の hint chain |
| 既存 149 件 | regression check (hint をテストしていない既存に影響なし) |

### §9.2 Frontend (vitest)

| test file | 追加 / 変更 | 検証内容 |
| --- | --- | --- |
| [gui/src/lib/appError.test.ts](gui/src/lib/appError.test.ts) | 影響なし | 既存 helper test 既に網羅済 |
| [gui/src/state/metadataStore.test.ts](gui/src/state/metadataStore.test.ts) | 既存 8 件書き換え + 新規 5 件 | (a) AppError 形式 reject で `applyError` + `applyErrorHint` 設定、(b) `state.mtime_conflict` で conflictError 振り分け、(c) legacy raw String reject で `applyError` のみ (hint=null)、(d-f) load/restore/draftSave/draftLoad の hint pair |
| `gui/src/state/recentStore.test.ts` | 新規 2 件 | addError + addErrorHint 設定 |
| [gui/src/components/ConflictModal.test.tsx](gui/src/components/ConflictModal.test.tsx) | 既存 6 件の test data 修正 | `'conflict: x'` → `'x'` (legacy prefix 撤去後の form) |
| `gui/src/components/RestoreButton.test.tsx` | 新規 2 件 | hint 表示時 2 行目 render / hint=null 時 2 行目非表示 |
| `gui/src/screens/DropScreen.test.tsx` | 新規 1 件 | error card で hint 表示 |
| `gui/src/screens/DetectingScreen.test.tsx` | 新規 1 件 | start_detect 失敗時 hint 表示 |
| `gui/src/screens/PreviewScreen.test.tsx` | 新規 1 件 | preview load error の hint 表示 |
| `gui/src/screens/ExportScreen.test.tsx` | 新規 1 件 | per-match error の hint 表示 |
| jest-axe a11y チェック (該当 component) | 既存 + 必要に応じ新規 | hint 含む alert で a11y violation がないこと |

合計: 既存 ~566 件 + 新規 13-15 件 + 既存修正 ~14 件 = ~595 件。

### §9.3 実機検証 (Iron Law 6 — `gui/src-tauri/**` + state 系変更につき必須)

5 経路を `AskUserQuestion` で Idios に手動依頼:

1. `state.mtime_conflict` 経路 — metadata.json を 2 つの allaganeye-gui プロセスで同時 edit → apply、ConflictModal 表示 + scope 外宣言通り AppError hint は modal に出ない
2. `io.permission_denied` 経路 — read-only な metadata.json を編集→apply、inline error 2 行目に "Portable ZIP install dir が user-writable な..." hint
3. `io.file_not_found` 経路 — metadata.json を削除して GUI から再 load、inline error 2 行目に "ファイルが見つかりません..." hint
4. `parse.json_invalid` 経路 — metadata.json を破損させて load、inline error 2 行目に "JSON ファイルが破損..." hint
5. `subprocess.spawn_failed` 経路 — ffprobe を一時 rename して probe、inline error 2 行目に "外部プロセスの起動に失敗..." hint

## §10 Doc 整合 (3 ファイル)

### §10.1 [docs/tauri-commands.md](docs/tauri-commands.md)

既存 master table に hint 列を加えるか、末尾に「AppError default hint mapping」 section を追加し、24 codes (or-pattern 展開後 #692) 全件を 1 表にまとめる (本 spec § 5.2 が source of truth、tauri-commands.md はその外部 mirror)。

```markdown
## AppError default hint mapping (`gui/src-tauri/src/error.rs::default_hint_for_code`)

> 本 table の文言は `gui/src-tauri/src/error.rs` の `default_hint_for_code()` と
> 完全一致させる (CI で integrity check は今回入れないが、文言変更時は両方を
> 同 PR で更新する規約)。

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

### §10.2 [docs/ui-architecture.md](docs/ui-architecture.md) § 4 「エラー伝搬フロー (#614)」

末尾に AppError code 一覧 + 使い分けを §4.x として追記:

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
  message のみ取得、hint は null (PR #663 で legacy raw を返す command は
  存在しないが、helper の互換性は温存)
```

### §10.3 [docs/ui-interaction-spec.md](docs/ui-interaction-spec.md) § 1.5 「エラー表示の一貫性」

§ 1.5.x として追記:

```markdown
### 1.5.x AppError `code` ベースの分岐ルール (#663)

Tauri command 失敗時の error 表示は以下を厳守する:

1. `appErrorCodeIs(e, 'state.mtime_conflict')` で apply path → ConflictModal (modal 表示)
2. その他の AppError code → inline error
   - 1 行目: `appErrorMessage(e)` (赤系: `var(--ae-text-error)`)
   - 2 行目: `appErrorHint(e)` (灰系: `var(--ae-text-dim)`、`💡` 等の prefix で
     アクション提示と分かるように)
3. catch ブロック以外で error を扱わない (`alert()` / `console.error` のみは禁止)
4. globalErrorListener が拾うのは uncaught (window.error / unhandledrejection /
   panic) のみ。catch 済 Tauri command error は ErrorModal に出さない (規約)
```

## §11 Issue body 更新

`gh issue edit 663 --body-file -` で update。書き換え方針:

- **概要**: 「PR #665 で 23 commands が `Result<T, AppError>` に migrate 済。本 issue は仕上げ部分 (legacy fallback 撤去 / hint production 適用 / docs 整合) を扱う」
- **背景**: 旧 body の `to_wire_string()` 表記を削除し、現実態 (Tauri serde Serialize 経由) に書き換え
- **作業内容**: 4 軸 (A/B/C/D) で再構成
- **受け入れ条件**: §12 と同期させる
- **スコープ外**: §3 と同期させる

`feedback_gh_command_ja_heredoc.md` 準拠で `printf | --body-file -` または HEREDOC を使う (inline 引数日本語禁止)。

## §12 受け入れ条件 (本 spec で確定する list)

- [ ] (A) [gui/src/state/metadataStore.ts:209](gui/src/state/metadataStore.ts:209) の `|| msg.startsWith('conflict:')` が削除されている
- [ ] (A) `metadataStore.test.ts` の `'conflict: ...'` raw String テストが AppError object 形式に書き換わっている
- [ ] (A) `ConflictModal.test.tsx` の test data から `'conflict:'` prefix が消えている
- [ ] (B) [gui/src-tauri/src/error.rs](gui/src-tauri/src/error.rs) に `default_hint_for_code()` + `with_default_hint()` が追加され、24 codes (or-pattern 展開後 #692) 分の日本語 hint が table に存在する
- [ ] (B) `From<std::io::Error>` / `From<serde_json::Error>` の impl 内で `.with_default_hint()` が呼ばれている
- [ ] (B) [gui/src-tauri/src/lib.rs](gui/src-tauri/src/lib.rs) の全 80 site の `AppError::new(code, msg)` に `.with_default_hint()` が chain されている
- [ ] (C) `metadataStore` に `loadErrorHint` / `applyErrorHint` / `restoreErrorHint` / `draftSaveErrorHint` / `draftLoadErrorHint` の 5 state が追加されている
- [ ] (C) `recentStore` に対応する hint pair が追加されている
- [ ] (C) 5 screen + RestoreButton の inline error が hint があれば 2 行目を `var(--ae-text-dim)` で render する
- [ ] (D) [docs/tauri-commands.md](docs/tauri-commands.md) に AppError default hint mapping table が追加されている
- [ ] (D) [docs/ui-architecture.md](docs/ui-architecture.md) § 4 に `code` 体系と使い分け節 (§4.x) が追加されている
- [ ] (D) [docs/ui-interaction-spec.md](docs/ui-interaction-spec.md) § 1.5 に `error.code` ベース分岐ルール節 (§1.5.x) が追加されている
- [ ] (D) issue #663 body が PR #665 後の状態を反映する形に書き換わっている
- [ ] cargo check / cargo test --lib (新 6 件 + 既存 149 件 = 155 件 pass)
- [ ] npm run lint / typecheck / test (新 13-15 件 + 既存 ~566 件 = ~580 件 pass) / build
- [ ] CI PR 全 7 job pass (`python` / `gui-frontend` / `gui-rust` / `doc-tauri-commands-drift` / `installer-pester` / `markdownlint` / `validate-checklist`) ※ `build-windows` / `version-check` は `release.yml` 専用で PR CI には含まれない
- [ ] Iron Law 6 実機検証 5 経路 (§9.3) を Idios が PASS 確認

## §13 Risks & 対策

| Risk | 対策 |
| --- | --- |
| **80 site への chain 追加で diff 大きい (lib.rs +80 行)** | mechanical change なのでレビュー負担は文言の方に集中。`docs/tauri-commands.md` の hint table で文言を 1 ヶ所に集約 |
| **24 codes (or-pattern 展開後 #692) の日本語 hint 文言の言い回し review が散在する** | spec self-review で文言を 1 表に集約、user review で一括承認/差し戻し、本 spec § 5.2 が source of truth |
| **既存 metadataStore.test.ts / ConflictModal.test.tsx の rewrite で regression リスク** | TDD 順序 (red→green) で書き換え、削除前後で test 件数が同等以上であることを確認 |
| **Iron Law 3 scope creep**: hint 文言を整える過程で「ついでに message も整える」誘惑 | scope-guard skill 適用、message 変更は別 issue 起票 |
| **Iron Law 6 PR Pre-flight**: Lane I-A 起点だが他 lane と並行する可能性 | base merge 取り込み + `gh pr list --search "#663"` 並行確認、PR 作成時に再確認 |
| **Iron Law 6 実機検証**: gui/src-tauri/** + state 系の変更で実機検証必要 | §9.3 5 経路を `AskUserQuestion` で Idios に依頼 |
| **CI PR 全 7 job pass**: `python` / `gui-frontend` / `gui-rust` / `doc-tauri-commands-drift` / `installer-pester` / `markdownlint` / `validate-checklist` (`build-windows` / `version-check` は `release.yml` 専用) | PR pre-flight で全 job のローカル相当チェックを通す |
| **legacy fallback の test 削除で「想定外 input でも動いていた挙動」を失う** | issue body に明記 (string prefix 判定撤廃 = legacy form は明示的に非サポート)。helper の `appErrorMessage` / `appErrorHint` が legacy raw String / Error instance を null hint で受け流す互換性は温存 |
| **`with_hint` 直接呼び出しの混在**: production 全 site は `.with_default_hint()` chain を使うため `with_hint` は test と将来 hybrid 移行用 API として残る | §5.1 で `#[allow(dead_code)]` 温存と確定。test (`error.rs::tests`) では `with_hint` を使い続ける |

## §14 実装順序 (TDD-driven、5 phase / 5 commit)

### Phase 1: Rust error.rs (pure helper)

1. test 6 件 red — `cargo test --lib` で fail
2. `default_hint_for_code` 実装 → green
3. `with_default_hint` 実装 → green
4. `From<io::Error>` / `From<serde_json::Error>` の hint chain 追加 → green
5. `with_hint` の `#[allow(dead_code)]` は温存 (§5.1 参照)、`with_stacktrace` も同様に温存

**commit**: `feat(gui): AppError::default_hint_for_code helper を追加 (Refs #663)`

### Phase 2: Rust lib.rs (mechanical migration)

1. 全 80 site の `AppError::new(code, msg)` を `.with_default_hint()` chain に書き換え
2. `cargo check` / `cargo test --lib` で 155 件 pass 確認 (cargo check で warning なし、特に `with_hint` 関連 warning が出ないことを確認)

**commit**: `refactor(gui): lib.rs 全 80 site に .with_default_hint() を適用 (Refs #663)`

### Phase 3: Frontend state stores (test 先行)

1. `metadataStore.test.ts` に hint pair の failing test 追加 (5 種類)
2. `metadataStore.ts` に `*ErrorHint` state 追加 → green
3. catch block で `appErrorHint(e)` 取り込み → green
4. legacy `|| msg.startsWith('conflict:')` 削除 → 既存 test red
5. 既存 test (8 件) の AppError 化リライト → green
6. `recentStore.ts` も同パターン
7. `npm run typecheck` / `npm test -- --run` 全 pass

**commit**: `feat(gui): metadataStore / recentStore に *ErrorHint state を追加 + legacy fallback 削除 (Refs #663)`

### Phase 4: Frontend UI (各 screen の inline error 2 行目)

1. `RestoreButton.test.tsx` に hint 表示 failing test 追加
2. `RestoreButton.tsx` で hint 2 行目 render → green
3. 各 screen test に hint 表示 failing test 追加
4. 各 screen の `*Error` render を 2 行目構造に拡張 → green
5. CSS (`tokens.css` / module.css) に `.errorHint` class 追加
6. `npm run lint` / `typecheck` / `test` / `build` 全 pass

**commit**: `feat(gui): 各 screen の inline error に hint 2 行目を追加 (Refs #663)`

### Phase 5: Docs + Issue body

1. `docs/tauri-commands.md` に hint mapping table 追加
2. `docs/ui-architecture.md` § 4 に AppError code 一覧 + 使い分け追記
3. `docs/ui-interaction-spec.md` § 1.5 に error.code ベース分岐ルール追記
4. `bash scripts/check-markdownlint.sh` 全 pass
5. `gh issue edit 663 --body-file -` で issue body 書き換え (`feedback_gh_command_ja_heredoc.md` 準拠)

**commit**: `docs: AppError default hint mapping を docs に整合させる (Refs #663)`

## §15 PR 作成 Pre-flight (Iron Law 6 完全準拠)

```bash
# 1. base 同期
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
# 取り込み未済 commit が touched files (gui/src-tauri/src/error.rs / lib.rs /
# gui/src/state/* / gui/src/components/* / gui/src/screens/* / docs/*) と交差するなら
git merge origin/develop-0.2.0
# CI 該当 job のローカル相当を再実行

# 2. 並行 worktree 確認
gh pr list --search "#663" --state all
gh pr list --state open --search "claude/"

# 3. 自動チェック (path 別)
cd gui/src-tauri && cargo check && cargo test --lib
cd gui && npm run lint && npm run typecheck && npm test -- --run && npm run build
bash scripts/check-markdownlint.sh
ruff check . && ruff format --check . && pyright && pytest

# 4. PR 本文に Self-Test Report (machine-verified [x] + machine-unverifiable plain bullet)
# 5. 実機検証 5 経路 (§9.3) を AskUserQuestion で Idios に依頼 → PASS 確認後にレビュー依頼
```

## §16 PR 規約

- ベース branch: `develop-0.2.0`
- 1 PR = 1 issue (#663)、`Refs #663` のみ (Closes/Fixes 禁止 = Iron Law 4)
- Self-Test Report 規約 (`docs/l2-workflow.md`)
- session-id: `tender-khayyam-03d618` を PR 本文に明記
- マージ後 `/close-issue` skill で base ブランチで実測再検証 + 手動 close
- (A) PR 内修正優先 (`docs/l2-workflow.md`)、レビュー摘出は原則 PR 内追加修正

## §17 Diff 規模見積もり (final)

| 領域 | 追加 | 削除 |
| --- | --- | --- |
| Rust (`gui/src-tauri/src/error.rs` + `lib.rs`) | +210 | -2 |
| Frontend state | +40 | -3 |
| Frontend UI (screens / components / CSS) | +90 | 0 |
| Frontend tests | +120 | -25 |
| Docs (`tauri-commands.md` / `ui-architecture.md` / `ui-interaction-spec.md`) | +90 | -10 |
| Issue body (`gh issue edit`、code diff には含まれない) | +30 | -50 |
| **合計 (code diff)** | **+550** | **-40** |

## §18 References

- [docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md](docs/superpowers/plans/2026-05-07-l2-v020-roadmap.md) — Lane I-A 位置付け (wave 0 起点)
- [docs/l2-workflow.md](docs/l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [docs/tauri-commands.md](docs/tauri-commands.md) — Tauri command master 一覧 (PR #665 で新設)
- [docs/ui-architecture.md](docs/ui-architecture.md) § 4 — エラー伝搬フロー
- [docs/ui-interaction-spec.md](docs/ui-interaction-spec.md) § 1.5 — エラー表示の一貫性
- [docs/a11y-policy.md](docs/a11y-policy.md) — Modal / inline error の a11y 規約
- [gui/src-tauri/src/error.rs](gui/src-tauri/src/error.rs) — `AppError` struct 本体 (PR #661 で導入)
- [gui/src-tauri/src/lib.rs](gui/src-tauri/src/lib.rs) — 80 site の AppError::new 呼び出し
- [gui/src/lib/appError.ts](gui/src/lib/appError.ts) — frontend narrowing helper (PR #665 で新設)
- [gui/src/state/metadataStore.ts](gui/src/state/metadataStore.ts) — legacy fallback の所在
- PR [#661](https://github.com/Idios/kobutachan-allaganeye/pull/661) — `AppError` struct 導入
- PR [#665](https://github.com/Idios/kobutachan-allaganeye/pull/665) — `Result<T, AppError>` 23 commands migration (本 spec の前提)
- Iron Law (`.claude/hooks/session-start.sh`) — 1 (受け入れ条件) / 3 (scope creep) / 4 (Closes 禁止) / 5 (曖昧 AskUserQuestion) / 6 (PR Pre-flight + 実機検証)

## §19 Memory feedback / 関連メモ

本 spec 関連で実行時に参照すべきメモ:

- `feedback_gh_command_ja_heredoc.md` — `gh issue edit` の日本語本文は `printf | --body-file -` または HEREDOC
- `feedback_taskstop_child_process_leak.md` — `npm run tauri dev` 等を `run_in_background` した後の child プロセス残留対策 (実機検証時に該当)
- `feedback_skill_revision_empirical.md` — skill 改修時 (`/review-pr` 等) は empirical-prompt-tuning が有効
