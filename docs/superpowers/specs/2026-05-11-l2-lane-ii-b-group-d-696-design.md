# L2 Lane II-b: Group D + #696 設計 (ExportScreen + ErrorModal + globalErrorListener)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **Scope**: [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) (P2) + [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) (P3) + [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) (P3) + [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (P3) の 4 件統合 (1 spec / 4 章 / 4 PR 直列)
> **session**: `youthful-thompson-abbfd6` (2026-05-11 brainstorming)
> **roadmap**: [`docs/superpowers/specs/2026-05-11-l2-v020-roadmap-update-design.md`](2026-05-11-l2-v020-roadmap-update-design.md) §Group D + #696

## §1 Overview

Lane II-b (Wave 1 main 3 lane の 1 つ) は **「user が実エラーに遭遇したときの UX」を底上げする 4 件** を直列消化する。

- [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) (P2): Export 失敗時 `[object Object]` 表示の解消 (= 残 4 site の `String(e)` → `appErrorMessage(e)`)
- [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) (P3): ErrorModal の bug_report テンプレ自動埋込 (GitHub URL pre-fill)
- [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) (P3): Export 出力先 default を `<dirname>` のみ (= 存在するフォルダ) に変更
- [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (P3): catch 漏れ AppError fallback (`'tauri-command'` errorCategory) を ErrorModal に統合

### §1.1 章構成 (4 章 / 4 PR 直列)

| 章 | issue | 優先度 | 主要 file | merge 順位 |
| --- | --- | --- | --- | --- |
| **§2.1** | [#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) | **P2** | 残 4 site の `String(e)` を `appErrorMessage(e)` 化 (handleOpenFolder / PreviewScreen register_video / ConfirmExitModal ×2) | **PR 1** |
| **§2.2** | [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) | P3 | `gui/src/lib/issueReportUrl.ts` 新設 + `ErrorModal.tsx` link URL を builder 経由 + 新 Tauri command `read_error_log_tail` | PR 2 |
| **§2.3** | [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) | P3 | `deriveDefaultOutDir` (`<dirname>/output` → `<dirname>`) + 既存テスト更新 | PR 3 |
| **§2.4** | [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) | P3 | `globalErrorListener.onUnhandledRejection` の `isAppError` 分岐 + ErrorModal `'tauri-command'` 表示パターン | PR 4 |

### §1.2 file 共有 matrix

| 章 | ExportScreen | ErrorModal | globalErrorListener | PreviewScreen | ConfirmExitModal | issueReportUrl (新規) | lib.rs |
| --- | --- | --- | --- | --- | --- | --- | --- |
| §2.1 #678 | ✓ (handleOpenFolder) | | | ✓ | ✓ | | |
| §2.2 #669 | | ✓ (link 構築) | | | | ✓ (新規) | ✓ (`read_error_log_tail` 新 command) |
| §2.3 #680 | ✓ (deriveDefaultOutDir) | | | | | | |
| §2.4 #696 | | ✓ (display 分岐) | ✓ (isAppError 経路) | | | | |

- **§2.1 と §2.3**: ExportScreen を触るが **異なる関数** (handleOpenFolder vs deriveDefaultOutDir) → rebase 楽
- **§2.2 と §2.4**: ErrorModal を触るが **異なる箇所** (link URL 生成 vs category 分岐) → §2.2 merge 後に §2.4 rebase
- §2.4 merge 時点で `globalErrorListener.ts` の `onUnhandledRejection` を拡張するため、§2.1 が触らない (handleOpenFolder のみ) ことで衝突なし

### §1.3 Lane II-b の Wave 1 内位置づけ

[roadmap §4.3](2026-05-11-l2-v020-roadmap-update-design.md) の衝突 matrix:

- Wave 1 main 3 lane (I-B / II-a / II-b) は **並行可能** (file 衝突なし)
- Lane V Phase 2 (#694 unified ErrorState refactor) は **本 Lane merge 後** に着手 (II-b の screen 編集が consumer 一括 refactor に響くため)

### §1.4 採用した方針 (brainstorming で決定)

| # | 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | PR 粒度 | (a) 4 PR 直列 / (b) ペア 2 PR / (c) 1 PR 統合 | **(a) 4 PR 直列** | Iron Law 3 厳守、l2-workflow.md「1 PR = 1 scope」原則、review コスト分散、file 共有あるが順次 merge で衝突回避 |
| 2 | #678 スコープ | (a) 既存 `appErrorMessage` を使い残 4 site に適用 / (b) 新 `formatTauriError.ts` 作成 / (c) ExportScreen のみ | **(a) 既存 helper 適用** | `appErrorMessage` は #663 で既に存在、DRY 違反回避。受け入れ条件「全画面の invoke catch」に厳密従う |
| 3 | #669 mapping | (a) actual + environment + log_file_attachment / (b) actual + environment のみ / (c) 5 field 全 pre-fill | **(a) 3 field** | Group G PR #688 で凍結済 field id 厳守、log は user の手動添付負担減 |
| 4 | #680 scope | (a) deriveDefaultOutDir のみ修正 / (b) 別経路統一 / (c) 実機再現後 spec 確定 | **(a) deriveDefaultOutDir のみ** | Iron Law 3 厳守、1 PR = 1 scope、別経路発見時は別 issue |
| 5 | #696 display | (a) title=「処理中に予期しないエラー」recoverable hint 表示 / (b) default override 最小 / (c) 再試行 button 追加 | **(a) issue 本文準拠** | user-facing で「ユーザー操作中の error」と「app panic」を区別 |
| 6 | #669 URL truncation | (a) log を段階削減 (300→150→75 行) / (b) 超過時 log 0 行 / (c) default 100 行 | **(a) 段階削減** | user 視点で「何が起きたか」は見える + 切り詰め通知で透明性確保 |

## §2 各章の実装詳細

### §2.1 #678 — 残 4 site の `String(e)` → `appErrorMessage(e)` migration

**対象 site** (grep で確認済の 4 か所):

| file:line | 関数 | 現状 | 修正後 |
| --- | --- | --- | --- |
| [`gui/src/screens/ExportScreen.tsx:425`](../../../gui/src/screens/ExportScreen.tsx) | `handleOpenFolder` catch | `setOpenFolderError(e instanceof Error ? e.message : String(e))` | `setOpenFolderError(appErrorMessage(e))` + `appErrorHint(e)` 適用検討 |
| [`gui/src/screens/PreviewScreen.tsx:245`](../../../gui/src/screens/PreviewScreen.tsx) | `register_video` catch | `setVideoError(e instanceof Error ? e.message : String(e))` | `setVideoError(appErrorMessage(e))` |
| [`gui/src/components/ConfirmExitModal.tsx:41`](../../../gui/src/components/ConfirmExitModal.tsx) | save catch | 同上 | `setError(appErrorMessage(e))` |
| [`gui/src/components/ConfirmExitModal.tsx:66`](../../../gui/src/components/ConfirmExitModal.tsx) | discard catch | 同上 | 同上 |

**`appErrorHint` 適用判断**: hint 表示が既存 UI に出る余地がある site のみ適用

- `handleOpenFolder` → `openFolderError` を 2 行 (message + hint) 表示にする (UI 軽微拡張)
- `PreviewScreen` register_video → 既に `videoErrorHint` 系の枠があれば適用、なければ message のみ
- `ConfirmExitModal` → modal 内表示で hint 行追加 (#663 の他 modal 整合)

**テスト** (各 component の vitest):

1. AppError struct (`{code, message, hint}`) 流入時 → message + hint 2 行が表示される
2. Error instance 流入時 → `e.message` がそのまま表示
3. raw string 流入時 → `String(e)` 結果が表示
4. null / undefined 流入時 → graceful fallback (空文字列 or `'Unknown error'`)
5. 既存 `String(e)` で `[object Object]` になっていたケースが解消されることの regression

### §2.2 #669 — `issueReportUrl.ts` builder + ErrorModal link 改造 + 新 Tauri command

#### §2.2.1 新規 file: [`gui/src/lib/issueReportUrl.ts`](../../../gui/src/lib/issueReportUrl.ts)

```ts
const URL_BUDGET = 7800; // 8KB safe limit, with margin
const PER_FIELD_BUDGET = { actual: 2000, environment: 2000 }; // log gets remainder
const LOG_LINE_STEPS = [300, 150, 75, 50, 0]; // 段階削減

export interface IssueReportInput {
  actual: string;      // errorMessage + (errorStack ? "\n\nStack:\n"+errorStack : "")
  environment: string; // metadata.system_info 由来 (新 helper `formatSystemInfo()`)
  logExcerpt: string;  // logs/error-YYYYMMDD.log 末尾 (Rust から取得)
  logPath: string;     // 切り詰め通知用
}

export function buildIssueReportUrl(input: IssueReportInput): string {
  // 内部で URLSearchParams 使用、超過時は logExcerpt を行単位で LOG_LINE_STEPS の段階削減
  // 削減発生時は末尾に「\n\n⚠️ ログが切り詰められました。完全なログは {logPath} を参照」追加
  // 0 行に至っても超過なら logExcerpt フィールドを丸ごと省略
}

export function truncateLogToBudget(log: string, budget: number, logPath: string): string {
  // 行単位で末尾 N 行を保持する補助関数
}
```

#### §2.2.2 新規 Tauri command: `read_error_log_tail(line_count: usize) -> Result<String, AppError>`

- [`gui/src-tauri/src/lib.rs`](../../../gui/src-tauri/src/lib.rs) に追加 (`get_log_dir` の隣)
- `<install_dir>/logs/error-YYYYMMDD.log` の末尾 N 行を返す
- 当日 log 不存在 / 空 → **前日 log にフォールバック** (1 日分のみ、それより前は user 手動添付)
- I/O failure → `io.read_failed` (default hint 経由)
- backend は `BufReader::lines()` + `VecDeque<String>` (capacity N) で末尾 N 行を保持
- `tauri::Builder` の `invoke_handler` に登録 + `docs/tauri-commands.md` に追記

#### §2.2.3 Modified: [`gui/src/components/ErrorModal.tsx`](../../../gui/src/components/ErrorModal.tsx)

- 既存 `const ISSUE_REPORT_URL = '...?template=bug_report.yml'` を **base URL** に降格 (default fallback)
- `const [reportUrl, setReportUrl] = useState<string>(ISSUE_REPORT_BASE_URL)` で初期 fallback
- `useEffect` で `errorOpen=true` になったタイミングに:
  1. `metadata.system_info` (= `useMetadataStore`) が読めれば `formatSystemInfo()` で environment 文字列構築
  2. `invoke<string>('read_error_log_tail', { lineCount: 300 })` で log 末尾取得
  3. `buildIssueReportUrl({...})` で final URL を構築し `setReportUrl`
  4. invoke 失敗 / metadata 無し → graceful fallback (= base URL のまま、actual だけ pre-fill)
- link tag `href={reportUrl}` に変更

**Group G #688 で凍結された field id**:

- `actual` (= 実際の動作)
- `environment` (= 環境情報)
- `log_file_attachment` (= ログファイル)

#### §2.2.4 テスト

1. `issueReportUrl.test.ts` (新規) — boundary case
   - 8KB ぴったり / 超過 1 度 / 超過で 4 段階削減
   - URLSearchParams encoding (CJK / 記号 / 改行)
   - 切り詰め通知の付加確認 (発生時のみ末尾追加)
2. `ErrorModal.test.tsx` — 既存 `'Issue で報告する'` link assertion を `reportUrl` 経由 URL が `actual=...&environment=...&log_file_attachment=...` を含むことに更新
3. `lib.rs` cargo test に:
   - `read_error_log_tail_returns_last_n_lines`
   - `read_error_log_tail_handles_missing_file` (空文字列 fallback)
   - `read_error_log_tail_falls_back_to_previous_day` (当日 log 空 / 不存在 → 前日 log)
   - `read_error_log_tail_handles_io_error` (`io.read_failed`)

### §2.3 #680 — `deriveDefaultOutDir` 修正

**対象**: [`gui/src/screens/ExportScreen.tsx:948-959`](../../../gui/src/screens/ExportScreen.tsx)

```diff
- return `${parent}${sep}output`;
+ return parent;
```

加えて関数 docstring を「親ディレクトリのみを返す。`<dirname>/output` だと存在しないフォルダがプリセットになる (#680)」に修正。

**テスト**: [`gui/src/screens/ExportScreen.test.tsx`](../../../gui/src/screens/ExportScreen.test.tsx) の既存 `deriveDefaultOutDir` 関連 test を新仕様に更新

- `'E:\\videos\\rec.mkv'` → `'E:\\videos'` (Windows)
- `'/home/user/videos/rec.mp4'` → `'/home/user/videos'` (Unix)
- `'\\\\?\\E:\\videos\\rec.mkv'` → `'E:\\videos'` (extended-length prefix)
- `null` → `''` (sample mode)

加えて flow integration test (`flow.integration.test.tsx` 等) で default 値 assertion を更新。

### §2.4 #696 — globalErrorListener `isAppError` 分岐 + ErrorModal 'tauri-command' display

#### §2.4.1 Modified: [`gui/src/lib/globalErrorListener.ts:92-115`](../../../gui/src/lib/globalErrorListener.ts) (`onUnhandledRejection`)

```diff
  const onUnhandledRejection = (e: PromiseRejectionEvent) => {
    const reason = e.reason;
+   // #696: AppError struct (Tauri command の reject value) は catch 漏れ
+   // fallback として 'tauri-command' category で recoverable 表示する
+   if (isAppError(reason)) {
+     showError({
+       errorTitle: '処理中に予期しないエラーが発生しました',
+       errorMessage: reason.message,
+       errorHint: reason.hint ?? null,
+       errorStack: reason.stacktrace ?? null,
+       errorCategory: 'tauri-command',
+       isPanic: false,
+       isRecoverable: true,
+     });
+     return;
+   }
    // 既存 fallback (Error / string / object)
    let message = 'Unhandled promise rejection';
    ...
  };
```

#### §2.4.2 Modified: [`gui/src/components/ErrorModal.tsx:51-60`](../../../gui/src/components/ErrorModal.tsx) (default title 分岐)

```diff
  let defaultTitle: string;
  if (errorCategory === 'integrity') {
    defaultTitle = '同梱物の検証に失敗しました';
+ } else if (errorCategory === 'tauri-command') {
+   defaultTitle = '処理中に予期しないエラーが発生しました';
  } else if (isPanic) {
    defaultTitle = 'アプリ内部でエラーが発生しました';
  } else {
    defaultTitle = '予期しないエラーが発生しました';
  }
```

`isRecoverable=true` で `[閉じる]` button が表示される (既存 default 経路で動作)。`[詳細をコピー]` `[ログフォルダを開く]` `[Issue で報告する]` link も既存ロジックで自動表示 (§2.2 が merge 済なら pre-fill 動作)。

#### §2.4.3 テスト

1. `globalErrorListener.test.ts` — `dispatchEvent(new PromiseRejectionEvent('unhandledrejection', { reason: { code: 'io.read_failed', message: '...', hint: '...' } }))` で errorStore が `'tauri-command'` category + recoverable + hint を持つことを assert
2. `ErrorModal.test.tsx` — `errorCategory: 'tauri-command'` を渡したときに default title が「処理中に...」かつ `[閉じる]` button が表示されることを assert
3. **regression**: 既存 isAppError でない unhandled rejection (Error / string / object) は既存パターン (`'js-promise'`) のまま流れる
4. jest-axe で `'tauri-command'` modal の a11y 通過確認 (既存 #587 infra)

### §2.5 docs 更新

- §2.2 (#669) のタイミング:
  - [`docs/tauri-commands.md`](../../tauri-commands.md) に `read_error_log_tail` 新 command を追記 (param spec / return / error code 表)
- §2.4 (#696) のタイミング:
  - [`docs/ui-architecture.md`](../../ui-architecture.md) §4 (エラーハンドリング) に「catch 漏れ AppError は `'tauri-command'` errorCategory で ErrorModal fallback 表示」を追記
  - ErrorModal の Issue 報告 link は bug_report.yml の `actual`/`environment`/`log_file_attachment` を pre-fill (§2.2 の内容) を追記

## §3 テスト戦略 + 実機検証

### §3.1 TDD アプローチ (各章 Red-Green-Refactor)

各章 1 PR = 1 章 内で **Red → Green → Refactor** を最低 1 サイクル回す。superpowers の TDD HARD-GATE 厳守。

| 章 | Red (failing test 作成) | Green (最小実装) | Refactor (整理) |
| --- | --- | --- | --- |
| §2.1 #678 | 各 site の test に AppError struct 流入時 `[object Object]` でなく helper 経由 message が表示される expect を追加 → Red | `appErrorMessage(e)` に置き換え → Green | 4 site で同パターンが冗長なら共通 catch helper 抽出 (`tryInvoke` 等は scope 外、別 issue 候補) |
| §2.2 #669 | `issueReportUrl.test.ts` で 8KB boundary + truncation policy を expect → Red | URLSearchParams + 段階削減ロジック実装 → Green | per-field budget 定数を引数化、log truncation を別 fn (`truncateLogToBudget`) に切り出し |
| §2.3 #680 | `deriveDefaultOutDir.test.ts` の expect を `'E:\\videos'` に更新 → 旧 `'E:\\videos\\output'` が Red | `return parent;` → Green | docstring 修正、関連変数名見直し |
| §2.4 #696 | `globalErrorListener.test.ts` で AppError reject 流入 → `'tauri-command'` category が errorStore に書かれることを expect → Red | `isAppError(reason)` 分岐追加 → Green | 既存 fallback 経路との順序が正しいか check (AppError → Error → string → object) |

### §3.2 自動テスト カバレッジ

| 章 | vitest (frontend) | cargo test (backend) | 備考 |
| --- | --- | --- | --- |
| §2.1 #678 | `ExportScreen.test.tsx` (handleOpenFolder) / `PreviewScreen.test.tsx` (register_video) / `ConfirmExitModal.test.tsx` (×2) に AppError struct / Error / string / null / undefined の 5 ケース追加 | (不要) | 既存 test の `String(e)` assertion を `appErrorMessage(e)` に置き換え |
| §2.2 #669 | `issueReportUrl.test.ts` 新規 (boundary + truncation 段階) / `ErrorModal.test.tsx` で reportUrl が pre-fill 内容を含むことを assert | `lib.rs` test に `read_error_log_tail_*` 系を追加 (§2.2.4) | URLSearchParams encoding (CJK / 記号 / 改行) も assert |
| §2.3 #680 | `ExportScreen.test.tsx` の deriveDefaultOutDir 関連 test を新仕様に更新 + flow integration test の default 値 assertion 更新 | (不要) | `deriveDetectOutputDir` (`<stem>_allaganeye`) は影響範囲外、test 変更なし |
| §2.4 #696 | `globalErrorListener.test.ts` に AppError reject case + `ErrorModal.test.tsx` に `'tauri-command'` category case 追加。regression: 既存 `'js-promise'` 経路は変わらず通ること | (不要) | jest-axe で `'tauri-command'` modal の a11y 通過確認 |

### §3.3 Self-Test Report 規約 ([`docs/l2-workflow.md`](../../l2-workflow.md) §「Self-Test Report 規約」 準拠)

各 PR 本文に以下を明記:

**Machine-verified (`[x]` 形式)**:

- `cd gui && npm run lint` ✅
- `cd gui && npm run typecheck` ✅
- `cd gui && npm test` ✅
- `cd gui && npm run build` ✅
- §2.2 で Rust 変更があれば `cd gui/src-tauri && cargo check` ✅ + `cargo test` ✅

**Machine-unverifiable (plain `-` bullet、実機検証は §3.4 表で別途依頼)**:

- 実機 Tauri 起動での UI 反映 (該当 issue ごとに §3.4 参照)

### §3.4 実機検証 trigger 表 (Iron Law 6)

各章で Idios (人間メンテナ) に AskUserQuestion で実機検証を依頼。mock test PASS だけでは結合検証にならない (Iron Law 6「mock テスト pass = 実機検証不要」は Red Flag)。

| 章 | 実機検証 | 確認内容 | trigger 根拠 |
| --- | --- | --- | --- |
| §2.1 #678 | **推奨** | 故意に出力先を不存在 path にして `Open folder` クリック → エラー表示が `[object Object]` でなく日本語 message + hint である | GUI Tauri 起動 (Iron Law 6 trigger) |
| §2.2 #669 | **必須** | ErrorModal を強制発生 (`dev_force_panic` 等) → `Issue で報告する` link クリック → GitHub form が `actual`/`environment`/`log_file_attachment` 3 field に内容反映 + log 切り詰め通知の有無確認 | GUI Tauri 起動 + ブラウザ + `gui/src-tauri/**` 変更 (Iron Law 6 trigger ×3) |
| §2.3 #680 | **必須** | GUI 起動 → 動画 drop → Detecting → Preview → Export 画面で 出力先 default が `<dirname>` (= ソース動画の親ディレクトリ) であることを確認 | GUI Tauri 起動 (Iron Law 6 trigger)。issue 本文の「報告画像の `..._allaganeye` 形式が再現するか」も併せて確認、再現する場合は別 issue 起票 |
| §2.4 #696 | **必須** | `dev_force_unhandled_apperror` 等の開発用 command を追加 (or 既存 dev command で AppError を catch せず Promise reject させる) → ErrorModal が `'tauri-command'` 表示パターン (title=「処理中に...」/ 閉じる button / hint 表示) で出ることを確認 | GUI Tauri 起動 (Iron Law 6 trigger)、`globalErrorListener.ts` ロジック変更 |

実機検証用 dev command (`dev_force_unhandled_apperror`) は §2.4 PR 内で追加するか、§2.4 完了後 別 issue で追加するかは、§2.4 着手時に判断。

### §3.5 PR 単位での verify 手順 (4 PR 共通)

[`docs/l2-workflow.md`](../../l2-workflow.md) §「PR 作成 path 別自動チェック」 に準拠:

```bash
# GUI 変更 (全 4 PR で必要)
cd gui
npm run lint
npm run typecheck
npm test
npm run build

# §2.2 (#669) で Rust 変更を含む PR のみ
cd gui/src-tauri
cargo check
cargo test
```

加えて Pre-flight:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline  # 取り込み未済 commit 確認
gh pr list --search "<元 issue#>" --state all  # 並行 worktree PR 重複確認
```

## §4 リスク / Pre-flight / Iron Law 整合

### §4.1 リスク表

| リスク | 影響 | 対応 |
| --- | --- | --- |
| §2.1 で `appErrorHint(e)` を新 UI 行として表示する判断が site ごとにブレる | 4 site で hint 表示の有無が不一致 → UX 不整合 | site ごとに「既存 hint 表示枠の有無」で判断。`PreviewScreen` には既に `videoErrorHint` 枠があるか調査し、なければ message 単独で migrate (hint 行追加は別 issue 候補) |
| §2.2 の `read_error_log_tail` 新 Tauri command が `gui/src-tauri/**` 変更で実機検証 trigger 増 | Idios の検証コスト増 | §2.2 PR で必須実機検証は「Issue 報告 link → GitHub form pre-fill 確認」1 点に集約、cargo test で I/O 系は完結 |
| §2.2 で `<install_dir>/logs/error-YYYYMMDD.log` が複数日にまたがる (深夜跨ぎでクラッシュ) | 当日 log 不存在で空文字列 → 報告コンテキスト欠落 | `read_error_log_tail` は 当日 log を最優先で読み、存在しないか空なら前日 log にフォールバック する。日付フォールバックは 1 日のみ |
| §2.2 URL 長制限超過時の段階削減が log の冒頭 (panic 直前の context) を捨てる方向 | 重要な context が失われる | 「末尾 N 行」 = panic 直前 N 行 なので、削減で消えるのは「より古い直前の出来事」。panic line 自体は保持 |
| §2.3 修正後、`<dirname>` が既存 file (動画ファイル) と書き出し output が同一フォルダになる | ソース動画と並べて output が見える → 1 試合動画 N 個で混乱 | issue #680 の user 要望 (「ソース動画と同じパスにして」) で user 明示判断。実機検証時に Idios 違和感あれば別 issue で「フォルダ自動命名 + 確認 modal」起票 |
| §2.4 で `isAppError` 分岐が Promise reject (string) や Object literal と誤判定 | `'tauri-command'` category が overshoot 、本来 `'js-promise'` であるべきものを取り違える | `isAppError` の判定基準は `code:string && message:string` の AND。これは Rust AppError serde 経路の固有 shape (PR #665 で migration 済)。ユーザーコードで偶然この shape を満たす reject は現状の codebase grep で該当なし。errorStore test で各種 non-AppError reject 形態の regression を追加 |
| §2.4 `'tauri-command'` category で first-write-wins が効き、その後の panic / integrity が表示されない | 後発の重大 error が握りつぶされる | errorStore.showError 既存の意図的設計 ([`errorStore.ts:67-71`](../../../gui/src/state/errorStore.ts))。`'tauri-command'` は recoverable=true なので user が閉じれば次の error 表示可。priority queue 化は別 issue 候補 |
| 4 PR 直列 merge 中に Lane V Phase 1 #698 (`DropScreen` 変更) や Lane II-a #633 (sample mode read-only) が並行 merge | screen file の rebase 衝突 | Lane II-b 4 PR は `DropScreen` を触らない (§2.1-§2.4 のいずれも DropScreen 編集なし) ので影響なし。`PreviewScreen` は §2.1 で 1 行 (245) のみ編集、Lane II-a が PreviewScreen 大規模 refactor を入れる場合は rebase 必要 (先着優先) |

### §4.2 Pre-flight チェックリスト (各章着手時)

各章 (= 各 PR) 着手時に必ず確認:

- [ ] `gh issue view <num>` で 受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] 取り込み未済が当 PR touched files と交差 → `git merge origin/develop-0.2.0` + 自動チェック再実行
- [ ] `gh pr list --search "<元 issue#>" --state all` で 並行 worktree PR 重複 確認 (Iron Law 6)
- [ ] 当章で `gui/src-tauri/**` を変更する場合、cargo check + cargo test の追加実行
- [ ] §2.1 着手時: §2.1 内 4 site の grep を再確認 (codebase の変化で site 数が増えていないか)
- [ ] §2.2 着手時: bug_report.yml の field id が `actual` / `environment` / `log_file_attachment` のまま凍結されていることを確認 (Group G PR #688 後の改変なし)
- [ ] §2.3 着手時: 報告画像の `..._allaganeye` 形式が実機で再現するか 着手前 に Idios 実機確認 (再現したら scope 拡大の判断を AskUserQuestion で取り直す)
- [ ] §2.4 着手時: §2.2 (#669) がマージ済か (`ErrorModal.tsx` の `reportUrl` 変更が §2.4 default title 分岐と衝突しない設計を再確認)

### §4.3 Iron Law 整合

| Iron Law | 整合点 |
| --- | --- |
| 1. NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED | 各 PR の元 issue 受け入れ条件を逐条引用 + 対応 diff/test 引用は `/review-pr` skill の `enforce-acceptance-criteria` で担保 |
| 2. NO BULK OPERATION WITHOUT AskUserQuestion | 4 PR 直列で各 PR は 1 issue scope、bulk 操作なし。マージ後の `/close-issue` も 1 issue ずつ |
| 3. NO SCOPE CREEP WITHOUT NEW ISSUE | §2.1 で `String(e)` site が 4 か所超に増えていたら → 別 issue 起票判断。§2.3 で別 setOutDir 経路発見 → 別 issue (§1.4 #4 で決定済)。`scope-guard` skill を着手中に invoke |
| 4. NO Closes / Fixes / Resolves KEYWORDS | 4 PR とも本文・コミットで `Refs #N` のみ使用、自動 close キーワード禁止。マージ後 `/close-issue` skill で手動 close |
| 5. NO INDEPENDENT JUDGMENT ON AMBIGUOUS POINTS | 本 brainstorming で 6 つの主要論点 (§1.4 表) はすべて AskUserQuestion で確定 |
| 6. NO PR CREATION WITHOUT VERIFIED CHECKS | §3.3 Self-Test Report 規約 + §3.5 path 別自動チェック + §3.4 実機検証依頼 + §4.2 Pre-flight チェックリスト で完全担保 |

### §4.4 Memory feedback (本 lane で意識する点)

- [`feedback_taskstop_child_process_leak.md`](C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_taskstop_child_process_leak.md) — `npm run tauri dev` background 起動時の子プロセス残留に注意 (実機検証時)
- [`feedback_gh_command_ja_heredoc.md`](C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_gh_command_ja_heredoc.md) — PR 本文・コミット msg 日本語は `printf | --body-file -` または HEREDOC
- [`feedback_markdownlint_typical_fixes.md`](C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_markdownlint_typical_fixes.md) — `docs/ui-architecture.md` / `docs/tauri-commands.md` 編集時の MD028/MD056 注意
- [`feedback_msys_path_conv_git_show.md`](C:\Users\idios\.claude\projects\E--projects-kobutachan-tools-kobutachan-allaganeye\memory\feedback_msys_path_conv_git_show.md) — Bash tool 経由 `git show <rev>:<path>` で path 変換問題

### §4.5 非ゴール

- その他 `String(e)` site の migration: §2.1 で確認した 4 site のみ対象。今後追加された catch site の sweep は別 issue (該当時点で `/review-pr` の sweep 規約で発見・別途起票)
- `tryInvoke` 等の共通 catch helper 抽出: §2.1 Refactor 段階で冗長と感じても本 lane scope 外。post-#663 Group I 系 (Lane V) や別 lane の判断
- ErrorState priority queue (catch 漏れ AppError 後の panic/integrity を表示): §4.1 のリスク表で示した課題は別 issue 候補
- ErrorModal `[再試行]` button: §1.4 #5 で却下済 (scope 拡大、retry callback の store 設計コスト)
- bug_report.yml の field id 変更: Group G で凍結済、本 lane では field id 既存値を使うのみ
- `deriveDetectOutputDir` (`<stem>_allaganeye`) の動作変更: §2.3 で別経路発見 → 別 issue 方針 (§1.4 #4 確定)

### §4.6 受け入れ条件 (本 design の)

本 design に基づく writing-plans 実行で、以下が満たされること:

- [ ] 新規 plan file `docs/superpowers/plans/2026-05-11-l2-lane-ii-b-group-d-696.md` が作成され、§2 (4 章詳細) を完全に表現している
- [ ] plan に §2.1 #678 / §2.2 #669 / §2.3 #680 / §2.4 #696 の 4 章 が、§2 (実装詳細) のとおりに記載されている
- [ ] plan で 4 PR の merge 順序が直列 (#678 → #669 → #680 → #696) と明記されている
- [ ] 各章の Pre-flight checklist (§4.2 章別項目) が plan に展開されている
- [ ] §3.4 実機検証 trigger 表 (各章の trigger / 確認内容 / 根拠) が plan に展開されている
- [ ] §3.3 Self-Test Report 規約と §3.5 path 別自動チェックが plan に明記され、各章 PR 本文テンプレに反映されている
- [ ] 各章で TDD Red-Green-Refactor サイクル (§3.1) が章ごとに展開されている
- [ ] 本 design file (`docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md`) と新規 plan file が同一 PR で commit される
