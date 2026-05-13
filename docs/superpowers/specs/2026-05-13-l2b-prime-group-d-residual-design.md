# L2 Lane II-b': Group D 残 (#680 + #696) 設計 (ExportScreen default outDir + ErrorModal tauri-command fallback)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **Scope**: [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) (P3 bug) + [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (P3 task) の 2 件 (1 spec / 2 章 / 1 PR)
> **session**: `interesting-kirch-6bcbfa` (2026-05-13 brainstorming)
> **roadmap**: [`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`](../plans/2026-05-13-l2-v020-roadmap-update.md) §Lane II-b'
> **Supersedes (該当部分)**: [`docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md`](2026-05-11-l2-lane-ii-b-group-d-696-design.md) の §2.3 / §2.4 (旧 spec は #678 / #669 が CLOSED 済の前提で残 2 件のみ再設計)

## §1 Overview

Lane II-b' は 2026-05-11 plan の Lane II-b から `#678` (P2、CLOSED) / `#669` (P3、CLOSED) を消化した残作業。Group D 4 件中 2 件残: 「Export 画面の存在しない default フォルダ」と「catch 漏れ AppError の ErrorModal fallback 統合」を 1 PR で完結させる。

- [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) (P3 bug): `deriveDefaultOutDir` が `<parent>/output` を返す → 存在しないフォルダがプリセットされる UX 問題 → `<parent>` のみへ修正
- [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) (P3 task): `globalErrorListener.onUnhandledRejection` で `isAppError` 判定を追加、catch 漏れ AppError を `errorCategory: 'tauri-command'` で ErrorModal に流す。ErrorModal 側で `'tauri-command'` の `defaultTitle` ブランチを追加

### §1.1 章構成 (2 章 / 1 PR)

| 章 | issue | 優先度 | 主要修正 |
| --- | --- | --- | --- |
| **§2** | [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) | P3 (bug) | `gui/src/screens/ExportScreen.tsx` `deriveDefaultOutDir` の return 修正 + 既存 unit / integration test の expected 更新 |
| **§3** | [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) | P3 (task) | `gui/src/lib/globalErrorListener.ts` `onUnhandledRejection` に `isAppError` 分岐追加 + `gui/src/components/ErrorModal.tsx` の `defaultTitle` に `'tauri-command'` ケース追加 + `docs/ui-architecture.md` §4 追記 |

### §1.2 file 共有 matrix

| 章 | ExportScreen.tsx | ExportScreen.test.tsx | flow.integration.test.tsx | globalErrorListener.ts | globalErrorListener.test.ts | ErrorModal.tsx | ErrorModal.test.tsx | docs/ui-architecture.md |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| §2 #680 | ✓ (`deriveDefaultOutDir`) | ✓ (5 ケース expected) | ✓ (default 値 assertion) | | | | | |
| §3 #696 | | | | ✓ (`onUnhandledRejection`) | ✓ (新規 2 ケース) | ✓ (`defaultTitle` 分岐) | ✓ (新規 1 ケース) | ✓ (1-2 文追記) |

両章は **完全に独立した file 集合** を触る。commit 単位を分けて (§2 commit → §3 commit) 直列実装するが、merge は 1 PR で同時。

### §1.3 Lane II-b' の Wave 1 内位置づけ

[roadmap §3-bis](../plans/2026-05-13-l2-v020-roadmap-update.md) の衝突 matrix:

- Wave 1 initial batch 5 lane (II-a' / II-b' / IV-b'' / VI / VII) は file 衝突なしで並行可
- **Lane V Phase 2 (#694 unified ErrorState refactor) は本 Lane merge 後** に着手 (V P2 が ExportScreen / metadataStore / 5 screen / 3 modal consumer 一括 refactor を行うため、II-b' #680 の ExportScreen 編集と衝突)
- **Lane III (#676 横断 file path 表示統一) は V P2 merge 後** (5 screen 横断衝突回避)

### §1.4 採用した方針 (brainstorming で決定)

| # | 論点 | 選択肢 | 採用 | 根拠 |
| --- | --- | --- | --- | --- |
| 1 | PR 粒度 | (a) 1 PR / (b) 2 PR 直列 / (c) 2 PR 並行 | **(a) 1 PR** | Group D 完走単位を明確化、CI / review コスト最小、両 issue とも独立 file & 小規模変更で衝突なし |
| 2 | #696 errorHint fallback | (A) issue body 完全守 (`hint ?? null`) / (B) tauri-command 専用 generic / (C) listener 側 fallback | **(A) issue body 完全守** | Rust 側で順次 `with_hint()` を追加する future plan (`gui/src/lib/appError.ts:56-65` 記載) に乗る。Iron Law 3 厳守 (scope 拡大しない) |
| 3 | テスト / 防御強度 | (A) 最小実装 / (B) A + #680 regression 1 件 / (C) helper 抽出 + button visibility test | **(A) 最小実装** | issue body 仕様が十分具体的、既存 test infra (panic / integrity event の coverage) が同型 store mutation pattern を網羅、B/C は overhead に見合わない |

## §2 章 1 — #680 ExportScreen 出力先 default を `<parent>` のみへ

### §2.1 問題と現状

[`gui/src/screens/ExportScreen.tsx:1026-1037`](../../../gui/src/screens/ExportScreen.tsx) 抜粋:

```ts
export function deriveDefaultOutDir(videoSource: string | null): string {
  if (!videoSource) return '';
  const normalized = stripExtendedPathPrefix(videoSource);
  const sep = normalized.includes('\\') && !normalized.includes('/') ? '\\' : '/';
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx <= 0) return '';
  const parent = normalized.slice(0, idx);
  return `${parent}${sep}output`;  // ← 存在しないフォルダがプリセットされる
}
```

呼び出し (`gui/src/screens/ExportScreen.tsx:138`):

```ts
const [outDir, setOutDir] = useState<string>(() => deriveDefaultOutDir(videoSource));
```

`<dirname>/output` は Export 画面到達時には物理的に存在しない (Rust 側 `start_detect` が `fs::create_dir_all` するのは detect 出力先で、Export 出力先ではない)。ユーザー視点では「default 値が存在しないフォルダ」 → 不安・混乱。

ユーザー報告 (2026-05-07): 「出力先のフォルダは選択したソース動画ファイルと同じパスにして。今は存在しないフォルダをデフォルトにしているため」

**補足の不整合**: 報告画像では `E:\videos\<stem>_allaganeye` (= `deriveDetectOutputDir` の `<stem>_allaganeye` 形式) が表示されているが、コード上 `deriveDefaultOutDir` は `<parent>/output` のはず。実機ビルドで再現確認の上、正確な default 値生成経路を特定する (画像のパスは別 setOutDir 経路で設定されている可能性も含む)。

### §2.2 修正内容 (TDD: Red → Green → Refactor)

**Red — failing test を先に書く**:

1. `gui/src/screens/ExportScreen.test.tsx:52-78` の `describe('deriveDefaultOutDir', ...)` 内 5 ケースを新仕様の expected に更新 (現状の `<parent>/output` 期待は新実装で fail):
   - `'E:/videos/clip.mkv'` → `'E:/videos'` (旧: `'E:/videos/output'`)
   - `'E:\\videos\\clip.mkv'` → `'E:\\videos'` (旧: `'E:\\videos\\output'`)
   - `null` → `''` (変更なし)
   - `'clip.mkv'` → `''` (変更なし、parent なし)
   - `'\\\\?\\E:\\videos\\clip.mkv'` → `'E:\\videos'` (旧: `'E:\\videos\\output'`)
   - `'\\\\?\\C:\\foo\\bar.mp4'` → `'C:\\foo'` (旧: `'C:\\foo\\output'`)
   - `'\\\\?\\UNC\\server\\share\\clip.mkv'` → `'\\\\server\\share'` (旧: `'\\\\server\\share\\output'`、現行 expected を spec で再確認)
2. `gui/src/screens/flow.integration.test.tsx` 等で default 値を assert している箇所を新仕様 (`<parent>` のみ) に更新

**Green — 実装**:

1. [`gui/src/screens/ExportScreen.tsx:1026-1037`](../../../gui/src/screens/ExportScreen.tsx) を以下に修正:

```ts
/**
 * #680: source video の親ディレクトリを default 出力先に。
 * 旧実装 (#466 review #2) は `<parent>/output` を返していたが、
 * 「存在しないフォルダがプリセットされる」UX 問題のため、`<parent>` のみへ変更。
 *
 * #545 review #2 (2026-04-25): Windows の `\\?\` extended-length path prefix
 * は `stripExtendedPathPrefix` で取り除いてから親 dir を切り出す。
 * (なお Tauri 側からの flow としては `appStateStore.setSelectedVideoPath`
 * が pipeline 上の strip ポイントなので通常 prefix は来ないが、defense-in-depth
 * として deriveDefaultOutDir 内でも適用しておく。)
 */
export function deriveDefaultOutDir(videoSource: string | null): string {
  if (!videoSource) return '';
  const normalized = stripExtendedPathPrefix(videoSource);
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx <= 0) return '';
  return normalized.slice(0, idx);
}
```

- `sep` 変数は不要 (parent 末尾に `/output` を結合しないため) → 削除
- docstring を「#466 review #2」根拠から「#680」根拠に置き換え
- Tests 全 pass を確認

**Refactor**: 該当なし (関数を簡素化したのみ、API surface 不変)

### §2.3 受け入れ条件 (issue #680 逐条引用)

- [ ] `deriveDefaultOutDir` が `<dirname>` のみ返すよう変更
- [ ] 既存の `deriveDefaultOutDir` 単体テスト更新 (ケース: Windows / Unix / extended-length prefix `\\?\` / sample mode null)
- [ ] 既存の Export 一気通貫テスト (`flow.integration.test.tsx` 等) で default 値 assertion の更新
- [ ] **実機ビルドで再現確認 (Idios)**: 報告画像の `E:\videos\2026-04-17_15-13-31_allaganeye` 形式が現行ビルドで再現するか確認 (Iron Law 6 trigger: GUI Tauri 起動 = mock 不可)
- [ ] (再現する場合) 別 setOutDir 経路があれば `deriveDefaultOutDir` に統一する

### §2.4 Idios 実機検証 (Iron Law 6 trigger)

`AskUserQuestion` で以下 2 項目を依頼:

- **(a) 修正版 GUI Tauri 起動 → Export 画面で出力先 textbox 初期値が `<parent>` のみ (例: `E:\videos`、末尾 `\output` なし) か?**
- **(b) 報告画像の `E:\videos\<stem>_allaganeye` 形式が現行 (未修正) ビルドで再現するか?**
  - 再現する場合 → 別 setOutDir 経路の調査タスクとして本 Lane 内に追加 (issue body 条件付き受け入れ条件 #5、scope 内)
  - 再現しない場合 → 「screenshot was from older build / different code path」と判断し、本修正のみで close 待ち

## §3 章 2 — #696 ErrorModal AppError fallback (`'tauri-command'` errorCategory)

### §3.1 問題と現状

[#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) Phase 4 ([PR #689](https://github.com/Idios/kobutachan-allaganeye/pull/689)) で各 screen の inline error は `appErrorHint` 表示まで完成したが、`globalErrorListener.ts` で catch されない (= screen 側 invoke catch ブロック外で発生した) Tauri command の AppError reject は ErrorModal に流れない経路が残った。

[#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) PR #689 §3 (non-goals) で「ErrorModal への AppError 統合は scope 外、`'tauri-command'` errorCategory は将来別 issue で対応する reservation」と明記。本 issue (#696) はその reservation を消化する。

#### 既存 infra (流用可)

- [`gui/src/state/errorStore.ts:12-18`](../../../gui/src/state/errorStore.ts): `ErrorCategory` union に `'tauri-command'` 既定義 (populate 経路が未実装だった)
- [`gui/src/lib/appError.ts:27-31`](../../../gui/src/lib/appError.ts): `isAppError(e): e is AppError` type guard 既存
- [`gui/src/lib/globalErrorListener.ts:92-115`](../../../gui/src/lib/globalErrorListener.ts): `onUnhandledRejection` ハンドラ既存 (現状は `instanceof Error` / `typeof 'string'` / generic object 分岐のみ、AppError shape 判定なし)
- [`gui/src/components/ErrorModal.tsx:64-72`](../../../gui/src/components/ErrorModal.tsx): `defaultTitle` 分岐 (現状は `'integrity'` / `isPanic` / その他)

### §3.2 修正内容 (TDD: Red → Green → Refactor)

**Red — failing test を先に書く**:

1. `gui/src/lib/globalErrorListener.test.ts` 末尾に新規 describe 追加:
   - **case (a) — AppError with hint**: `unhandledrejection` event with `reason = { code: 'io.permission_denied', message: 'Permission denied', hint: 'ファイル権限を確認してください' }` (= AppError shape) を dispatch → `errorStore` に `errorCategory: 'tauri-command'`, `errorTitle: '処理中に予期しないエラーが発生しました'`, `errorMessage: 'Permission denied'`, `errorHint: 'ファイル権限を確認してください'`, `isPanic: false`, `isRecoverable: true` が反映される
   - **case (b) — AppError without hint**: `reason = { code, message }` のみ → `errorHint: null`
   - **case (c) — regression**: 非 AppError object reason (`{ foo: 'bar' }`) → 既存 `'js-promise'` path 保持 (`errorCategory: 'js-promise'`, `errorMessage: JSON.stringify(...)`)
2. `gui/src/components/ErrorModal.test.tsx` に新規 case 追加:
   - 'tauri-command' category + `errorTitle: '処理中に予期しないエラーが発生しました'` + `errorMessage` + `errorHint` set → render 結果に title / message / hint が DOM 上に出る
   - (defensive: `errorTitle: null` + category `'tauri-command'` の場合 `defaultTitle` ブランチで '処理中に予期しないエラーが発生しました' が出る、新規 1 ケース)

**Green — 実装**:

1. [`gui/src/lib/globalErrorListener.ts:92-115`](../../../gui/src/lib/globalErrorListener.ts) を修正:

```ts
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

import { isAppError } from './appError';  // ← 追加 import
import { useErrorStore } from '../state/errorStore';

// ... (既存の interface 定義はそのまま)

  const onUnhandledRejection = (e: PromiseRejectionEvent) => {
    const reason = e.reason;
    // #696: AppError-shaped reject (Tauri command の catch 漏れ) を
    // ErrorModal の最終 fallback として表示する。screen 側 invoke catch
    // 規約 (`appErrorMessage` + `appErrorHint`) が正しく書かれていれば本
    // 分岐は通らないが、Promise を投げ捨て / async race / try-catch 漏れ
    // 等の caught-miss シナリオで recoverable な modal を出す。
    if (isAppError(reason)) {
      showError({
        errorTitle: '処理中に予期しないエラーが発生しました',
        errorMessage: reason.message,
        errorHint: reason.hint ?? null,
        errorStack: null,
        errorCategory: 'tauri-command',
        isPanic: false,
        isRecoverable: true,
      });
      return;
    }
    // 既存 path (js-promise) はそのまま
    let message = 'Unhandled promise rejection';
    let stack: string | null = null;
    if (reason instanceof Error) {
      message = reason.message || message;
      stack = reason.stack ?? null;
    } else if (typeof reason === 'string') {
      message = reason;
    } else if (reason && typeof reason === 'object') {
      try {
        message = JSON.stringify(reason);
      } catch {
        message = String(reason);
      }
    }
    showError({
      errorMessage: message,
      errorStack: stack,
      errorCategory: 'js-promise',
      isPanic: false,
      isRecoverable: false,
    });
  };
```

続けて [`gui/src/components/ErrorModal.tsx:64-72`](../../../gui/src/components/ErrorModal.tsx) の `defaultTitle` 分岐を拡張 (defensive、`'integrity'` パターンと同形):

```ts
// #614 / #668 / #696: per-category default titles. errorTitle override always wins.
let defaultTitle: string;
if (errorCategory === 'tauri-command') {
  defaultTitle = '処理中に予期しないエラーが発生しました';
} else if (errorCategory === 'integrity') {
  defaultTitle = '同梱物の検証に失敗しました';
} else if (isPanic) {
  defaultTitle = 'アプリ内部でエラーが発生しました';
} else {
  defaultTitle = '予期しないエラーが発生しました';
}
const title = errorTitle || defaultTitle;
```

最後に [`docs/ui-architecture.md`](../../ui-architecture.md) §4 (エラーハンドリング) に 1-2 文追記:

> #696: catch 漏れ AppError (Tauri command の reject を screen 側 invoke catch で受けず Promise を投げ捨てた場合等) は `globalErrorListener.onUnhandledRejection` が `isAppError` で判定し、`errorCategory: 'tauri-command'` / `isRecoverable: true` で ErrorModal に流す。Recoverable な inline error UI (screen 各自の local state) とは独立した最終 fallback として機能する (modal は閉じる button で dismiss 可)。

**Refactor**: 該当なし (既存 `onUnhandledRejection` の分岐を先頭に 1 ケース追加したのみ)

### §3.3 表示パターン (errorCategory === 'tauri-command' 時の ErrorModal 構成)

issue #696 確認項目「ErrorModal.tsx で `errorCategory === 'tauri-command'` の表示パターンを定義 (recoverable / Issue で報告 / コピー button 構成)」に対応:

- **title**: `errorTitle` override ('処理中に予期しないエラーが発生しました') / `defaultTitle` も同テキスト
- **message**: `AppError.message` をそのまま `<p className={styles.message}>` で表示
- **hint block**: `errorHint` (= `AppError.hint`) があれば `<p>{errorHint}</p>`、なければ非表示。続けて generic '問題が継続する場合は…Issue 本文をコピー…Issue で報告する…' 行は既存通り表示
- **buttons**:
  - 詳細をコピー (常時): `errorMessage` + `errorStack` (= null) + `errorCategory` + `timestamp` を JSON コピー
  - Issue 本文をコピー (常時、hint block 内): `buildIssueReportBody` で markdown 構築 → clipboard
  - 閉じる (isRecoverable=true なので表示): `dismissError()`
  - アプリを終了 (isPanic=false なので**非表示**): 該当なし

`'integrity'` (isPanic=true / 閉じる無し / アプリを終了あり) との対比で、`'tauri-command'` は recoverable な「inline 失敗の補完」位置付け。

### §3.4 受け入れ条件 (issue #696 逐条引用)

- [ ] `globalErrorListener.ts` の `onUnhandledRejection` で `isAppError(e.reason)` を判定し、true なら `errorCategory: 'tauri-command'`, `errorTitle: '処理中に予期しないエラーが発生しました'`, `errorMessage: e.reason.message`, `errorHint: e.reason.hint ?? null` を `errorStore.showError` に流す
- [ ] `ErrorModal.tsx` で `errorCategory === 'tauri-command'` の表示パターンを定義 (recoverable / Issue で報告 / コピー button 構成)
- [ ] 既存 6 panic-related test に加え `'tauri-command' errorCategory` の test を追加
- [ ] `docs/ui-architecture.md` §4 (#663 で追加した分岐ルール) に「catch 漏れ AppError は ErrorModal fallback」の旨を追記

### §3.5 Idios 実機検証 (Iron Law 6 trigger)

AppError catch-miss シナリオを自然発生させるのは困難なため、以下のいずれかで検証依頼:

- **(i) 開発時 dev-only 強制再現** (推奨): 任意の screen の invoke catch block を一時的に `throw e;` で rethrow するパッチを当てて `cd gui && npm run tauri dev` 起動、適当な command (例: `load_metadata` を不正パスで) を失敗させ → ErrorModal が `'tauri-command'` 表記で開く / `閉じる` button で閉じれるか確認
- **(ii) (i) が現実的でない場合**: vitest unit test pass を以て machine-verified `[x]` 扱いとし、real-build は 「globalErrorListener.test.ts 既存 panic / integrity event は実機 build で過去 verified (PR #688 / PR #702 等)、本 patch は同一 store mutation pattern のみ追加」を Self-Test Report の `-` (unverifiable) 行で記載

## §4 PR / verification workflow

### §4.1 Pre-flight (Iron Law 6 #659 規約)

PR 作成直前に必ず実施 (`docs/l2-workflow.md` §「PR 作成 Pre-flight」 参照):

1. `git fetch origin develop-0.2.0`
2. `git log HEAD..origin/develop-0.2.0 --oneline` で未取り込み base commit 確認
3. 当 PR の touched files (`gui/src/screens/ExportScreen.tsx` / `gui/src/screens/ExportScreen.test.tsx` / `gui/src/screens/flow.integration.test.tsx` / `gui/src/lib/globalErrorListener.ts` / `gui/src/lib/globalErrorListener.test.ts` / `gui/src/components/ErrorModal.tsx` / `gui/src/components/ErrorModal.test.tsx` / `docs/ui-architecture.md`) と交差する base 変更があれば `git merge origin/develop-0.2.0` + 自動チェック再実行
4. `gh pr list --search "680 OR 696" --state all` で並行 worktree PR 重複確認

### §4.2 自動チェック (Iron Law 6 path 別)

GUI 変更を含むため以下を**全 pass** させる:

- `cd gui && npm run lint` (eslint)
- `cd gui && npm run typecheck` (tsc --noEmit)
- `cd gui && npm test` (vitest 全 suite + 本 spec で追加した新 case)
- `cd gui && npm run build` (vite build)
- `cd gui/src-tauri && cargo check` (Rust 側未変更だが慣行に従い実行)

ドキュメント編集を含むため:

- `bash scripts/check-markdownlint.sh` (CI と同 version で全 .md チェック、`docs/ui-architecture.md` 編集ありのため必須)

Python 側 (`ruff` / `pyright` / `pytest`) は変更なしのため不要。

### §4.3 TDD HARD-GATE 順守 (CLAUDE.md 規定)

各章ごとに **Red → Green → Refactor** 順序を厳守:

1. **§2 章 Red**: `ExportScreen.test.tsx:52-78` 5 ケースを新仕様 expected に更新、commit (single failing snapshot)
2. **§2 章 Green**: `deriveDefaultOutDir` の return を `<parent>` のみへ修正、test 全 pass、commit
3. **§3 章 Red**: `globalErrorListener.test.ts` に新規 3 ケース (case a/b/c) を追加 + `ErrorModal.test.tsx` に新規 2 ケース追加、commit (all failing)
4. **§3 章 Green**: `globalErrorListener.ts` の `isAppError` 分岐 + `ErrorModal.tsx` の `defaultTitle` 分岐を実装、test 全 pass、commit
5. **§3 章 docs**: `docs/ui-architecture.md` §4 追記、`markdownlint` pass、commit

### §4.4 Self-Test Report (`docs/l2-workflow.md` 規約)

PR 本文に以下の形式で記載:

**machine-verified** (`[x]` 印):

- [x] `cd gui && npm run lint && npm run typecheck && npm test && npm run build` 全 pass
- [x] `cd gui/src-tauri && cargo check` pass
- [x] `bash scripts/check-markdownlint.sh` pass
- [x] vitest 新規 case (#680: 5 既存ケース expected 更新 / #696: globalErrorListener 3 ケース + ErrorModal 2 ケース) 全 green

**machine-unverifiable** (plain bullet `-`):

- (#680) Idios 実機検証: GUI Tauri 起動 → Export 画面で出力先 textbox 初期値が `<parent>` のみ (末尾 `\output` なし) であることを目視確認
- (#680) Idios 実機検証: 報告画像の `<stem>_allaganeye` 形式が現行 (修正前) ビルドで再現するか確認 (再現時は別 setOutDir 経路の調査タスクを本 Lane 内で追加)
- (#696) Idios 実機検証: dev-only patch で screen 側 invoke catch を bypass → ErrorModal が `'tauri-command'` 表記で開き、`閉じる` button で dismiss できることを確認 (現実的でない場合は §3.5 (ii) の justification を記載)

### §4.5 PR 本文 / commit 規約

- **PR title**: `feat(gui): #680 #696 ExportScreen default outDir + ErrorModal tauri-command fallback`
- **PR base**: `develop-0.2.0`
- **PR body** 構成:
  1. **Refs** 行: `Refs #680 #696` (Iron Law 4: Closes / Fixes / Resolves 禁止)
  2. **受け入れ条件 (#680)**: §2.3 を逐条引用 + 対応 diff / test を逐条引用 (Iron Law 1)
  3. **受け入れ条件 (#696)**: §3.4 を逐条引用 + 対応 diff / test を逐条引用 (Iron Law 1)
  4. **Self-Test Report**: §4.4 形式
  5. **session-id**: `interesting-kirch-6bcbfa`
  6. **spec link**: 本ドキュメント (`docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md`)
- **commit message** 規約: `feat(gui): #680 <要約>` / `feat(gui): #696 <要約>` / `test(gui): ...` / `docs: #696 ui-architecture §4 ...` 等、Conventional Commits + `#N` で issue 紐付け

### §4.6 Post-merge handoff

- Wave 2 で `/close-issue` skill により #680 / #696 を実測再検証 + 手動 close (Iron Law 4)
- `/close-issue` 完了後、roadmap の **Lane V Phase 2 (#694) の gating 解除** を確認 (roadmap §3-bis 衝突注意点)
- 本 Lane で発生した観察事項 (再現条件不明な点、別 setOutDir 経路の発見等) は (A) PR 内追加修正、または別 issue 起票で triage (`docs/l2-workflow.md` §「(A) PR 内修正優先 規約」)

## §5 Out of scope (本 spec で扱わない)

- **Rust 側 AppError に `with_hint()` を後付け配る wholesale 拡張**: `gui/src/lib/appError.ts:56-65` で言及されている future plan。本 Lane では `AppError.hint` が null の場合 `errorHint: null` 流し (issue body 仕様完全守) として扱う。Iron Law 3 で scope creep 禁止
- **#694 unified ErrorState refactor**: Lane V Phase 2 で別途消化 (本 Lane merge 後 gating 解除)
- **`'tauri-command'` 以外の新 errorCategory 追加**: 必要が出たら別 issue
- **AppError stacktrace を ErrorModal の `errorStack` に表示**: `globalErrorListener.onUnhandledRejection` の `'tauri-command'` 分岐で `errorStack: null` 固定 (issue body 仕様)。`AppError.stacktrace` を表示したい場合は別 issue
- **screen 各自の invoke catch を `appErrorMessage` / `appErrorHint` に統一する全画面 audit**: #663 / #678 で完走済、本 Lane では追加 audit しない

## §6 リスクと対応策

| リスク | 対応策 |
| --- | --- |
| #680 修正後、別 setOutDir 経路 (報告画像の `_allaganeye` 形式) が現行ビルドで再現する | §2.4 (b) で Idios 実機検証 → 再現時は本 Lane 内で調査タスクを追加 (issue body 条件付き受け入れ条件)、scope 内 |
| #696 修正で globalErrorListener が screen の inline error と二重表示になる (catch 漏れケース) | 設計上、screen 各自の catch が正しく書かれていれば本分岐は通らない。catch 漏れ自体が bug なので、二重表示は intended な fallback 動作 (デバッグ価値あり)。`errorStore` first-write-wins で同一 modal 二重 open は防止される |
| Lane V Phase 2 (#694) の gating 確認漏れで V P2 が II-b' merge 前に着手される | roadmap §3-bis 衝突 matrix で明示済、本 spec §1.3 で再強調、PR merge 時点で V P2 着手者に通知 |
| dev-only patch (§3.5 (i)) の検証コードが誤って commit に混入 | TDD Red 段階の commit のみで使い、Green 完了後に revert (commit history に残るが working tree に残さない)、PR 作成前に `git diff origin/develop-0.2.0` で patch が含まれないことを確認 |
| markdownlint MD028 / MD056 違反 (memory feedback 既知) | `docs/ui-architecture.md` 追記時に連続 blockquote 空行 / pipe 文字 escape (table cell 内) を確認 (`feedback_markdownlint_typical_fixes.md`) |

## §7 関連ドキュメント

- [`docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md`](../plans/2026-05-13-l2-v020-roadmap-update.md) — 上位 roadmap (本 spec は Lane II-b' entry)
- [`docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md`](2026-05-11-l2-lane-ii-b-group-d-696-design.md) — 旧 spec (#678 / #669 完走で §2.3 / §2.4 が本 spec に supersede)
- [`docs/l2-workflow.md`](../../l2-workflow.md) §「PR 作成 Pre-flight」 / §「Self-Test Report 規約」 / §「(A) PR 内修正優先 規約」
- [`docs/ui-architecture.md`](../../ui-architecture.md) §4 (エラーハンドリング) — #696 で追記対象
- [`gui/src/lib/appError.ts`](../../../gui/src/lib/appError.ts) — `isAppError` type guard / `appErrorMessage` / `appErrorHint` helpers
- [`gui/src/state/errorStore.ts`](../../../gui/src/state/errorStore.ts) — `'tauri-command'` カテゴリ既定義
- [`gui/src/lib/globalErrorListener.ts`](../../../gui/src/lib/globalErrorListener.ts) — `onUnhandledRejection` 拡張対象
- [`gui/src/components/ErrorModal.tsx`](../../../gui/src/components/ErrorModal.tsx) — `defaultTitle` 分岐拡張対象
- [`gui/src/screens/ExportScreen.tsx`](../../../gui/src/screens/ExportScreen.tsx) — `deriveDefaultOutDir` 修正対象

### Iron Law 整合 (`.claude/hooks/session-start.sh`)

- **Iron Law 1**: 受け入れ条件逐条検証 — §2.3 / §3.4 を PR 本文で diff / test と逐条マッピング
- **Iron Law 3**: scope creep 禁止 — §5 で out-of-scope を明示
- **Iron Law 4**: Closes / Fixes / Resolves 禁止 — PR 本文 `Refs #680 #696`、Wave 2 で `/close-issue` 手動クローズ
- **Iron Law 6**: PR Pre-flight + path 別自動チェック + 実機検証 trigger — §4.1 / §4.2 / §2.4 / §3.5

### Memory feedback 適用

- `feedback_markdownlint_typical_fixes.md` — `docs/ui-architecture.md` 追記時に MD028 / MD056 確認
- `feedback_iterate_review_no_scope_creep_option.md` — 後続 `/iterate-review` セッションで scope 拡大選択肢を含めない
- `feedback_skill_revision_empirical.md` — 本 spec は brainstorming に直接従ったため empirical-prompt-tuning 不要 (skill 大幅改訂時用)
