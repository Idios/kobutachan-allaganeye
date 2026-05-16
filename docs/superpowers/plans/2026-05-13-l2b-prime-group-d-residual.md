# Lane II-b' Group D 残 (#680 + #696) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ExportScreen の出力先 default を `<parent>` のみに修正 (#680) し、Tauri command の catch 漏れ AppError を ErrorModal に `'tauri-command'` カテゴリで fallback 表示する経路を追加する (#696)。1 PR / 2 章 / TDD HARD-GATE 順守で Lane II-b' (= Group D 残) を完走する。

**Architecture:** いずれも既存の小さな関数/分岐の拡張で、新規 type / 新規 API は不要。`errorStore` の `'tauri-command'` カテゴリ union と `isAppError` type guard は既存資産を流用する。修正は (a) `deriveDefaultOutDir` (1 関数) の return 値変更、(b) `globalErrorListener.onUnhandledRejection` の先頭に `isAppError` 分岐を 1 ケース追加、(c) `ErrorModal.defaultTitle` の switch に 1 ケース追加、(d) `docs/ui-architecture.md` §4 に新規 §4.9 を 1 段落追加、の 4 点。

**Tech Stack:** TypeScript / React 19 / Zustand / vitest / Tauri 2 / markdownlint-cli2 v0.22.1

**Spec:** [docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md](../specs/2026-05-13-l2b-prime-group-d-residual-design.md)

**Session-id:** `interesting-kirch-6bcbfa`

---

## File Structure (touched files)

| 種類 | path | 責務 |
| --- | --- | --- |
| Modify | [gui/src/screens/ExportScreen.tsx](../../../gui/src/screens/ExportScreen.tsx) | `deriveDefaultOutDir` の return を `${parent}${sep}output` → `parent` のみへ変更 (#680) |
| Modify | [gui/src/screens/ExportScreen.test.tsx](../../../gui/src/screens/ExportScreen.test.tsx) | `describe('deriveDefaultOutDir')` の 5 it() block の expected を新仕様 (parent のみ) に更新 + it() 説明文を新仕様に書き換え (#680) |
| Modify | [gui/src/lib/globalErrorListener.ts](../../../gui/src/lib/globalErrorListener.ts) | `onUnhandledRejection` の先頭に `isAppError(reason)` 分岐を追加し `errorCategory: 'tauri-command'` で showError を call (#696) |
| Modify | [gui/src/lib/globalErrorListener.test.ts](../../../gui/src/lib/globalErrorListener.test.ts) | 新規 describe `unhandledrejection AppError fallback (#696)` を末尾追加、3 ケース (hint あり / hint なし / 非 AppError regression) (#696) |
| Modify | [gui/src/components/ErrorModal.tsx](../../../gui/src/components/ErrorModal.tsx) | `defaultTitle` 分岐の先頭に `errorCategory === 'tauri-command'` ケースを追加 (#696) |
| Modify | [gui/src/components/ErrorModal.test.tsx](../../../gui/src/components/ErrorModal.test.tsx) | 既存 `describe('ErrorModal')` の末尾に 'tauri-command' category の 2 ケース (errorTitle override / defaultTitle fallback) を追加 (#696) |
| Modify | [docs/ui-architecture.md](../../ui-architecture.md) | §4 末尾 (§4.8 の後) に新規 §4.9 「catch 漏れ AppError fallback (#696)」を 1 段落追加 (#696) |

`gui/src/__tests__/flow.integration.test.tsx` には default outDir assertion が無いため変更不要 (spec §2.2 で「等」と書いた範囲は ExportScreen.test.tsx のみで完結することを実装時に確認済)。

---

## Task 1: §2 #680 Red — deriveDefaultOutDir test を新仕様に更新 (failing 状態を作る)

**Files:**

- Modify: `gui/src/screens/ExportScreen.test.tsx:52-78`

- [ ] **Step 1.1: Edit ExportScreen.test.tsx の `describe('deriveDefaultOutDir')` block を新仕様に書き換え**

`gui/src/screens/ExportScreen.test.tsx` の 52-78 行 (現状) を以下のブロックに置き換える。it() の名前 (`appends /output`) と expected 値の両方を新仕様 (`<parent>` のみ) に変更:

```ts
// #680 (旧 #466 review #2): default 出力先生成ヘルパ
describe('deriveDefaultOutDir', () => {
  it('returns the parent dir of a forward-slash video path', () => {
    expect(deriveDefaultOutDir('E:/videos/clip.mkv')).toBe('E:/videos');
  });

  it('returns the parent dir of a backslash video path', () => {
    expect(deriveDefaultOutDir('E:\\videos\\clip.mkv')).toBe('E:\\videos');
  });

  it('returns empty string when videoSource is null or has no separator', () => {
    expect(deriveDefaultOutDir(null)).toBe('');
    expect(deriveDefaultOutDir('clip.mkv')).toBe('');
  });

  // #545 review #2: extended-length path prefix を strip してから derive
  it('strips Windows \\\\?\\ extended-length prefix before deriving', () => {
    expect(deriveDefaultOutDir('\\\\?\\E:\\videos\\clip.mkv')).toBe(
      'E:\\videos',
    );
    expect(deriveDefaultOutDir('\\\\?\\C:\\foo\\bar.mp4')).toBe('C:\\foo');
  });

  it('strips Windows \\\\?\\UNC\\ prefix to UNC form', () => {
    expect(
      deriveDefaultOutDir('\\\\?\\UNC\\server\\share\\clip.mkv'),
    ).toBe('\\\\server\\share');
  });
});
```

差分のポイント:

- it() の名前: `appends /output to the parent dir...` → `returns the parent dir...` (2 件)
- expected: `'E:/videos/output'` → `'E:/videos'` / `'E:\\videos\\output'` → `'E:\\videos'` / `'E:\\videos\\output'` (\\\\?\\E:) → `'E:\\videos'` / `'C:\\foo\\output'` → `'C:\\foo'` / `'\\\\server\\share\\output'` → `'\\\\server\\share'`
- describe コメントの根拠を `#466 review #2` → `#680 (旧 #466 review #2)` に更新

- [ ] **Step 1.2: Test を実行して FAIL することを確認**

Run:

```bash
cd gui && npm test -- ExportScreen.test.tsx 2>&1 | tail -40
```

Expected: 5 assertions fail with `Expected: "E:/videos"` etc. mismatching `Received: "E:/videos/output"` (現在の deriveDefaultOutDir の挙動が旧仕様のため)。他の test (`formatStartForFilename`, etc.) は引き続き pass。

- [ ] **Step 1.3: Red commit**

```bash
git add gui/src/screens/ExportScreen.test.tsx
git -c commit.gpgsign=false commit -m "test(gui): #680 deriveDefaultOutDir tests を <parent> のみ仕様に更新 (Red)

- 5 it() block の expected を 'E:/videos/output' 等 → 'E:/videos' 等へ
- it() 名前 'appends /output...' → 'returns the parent dir...' へ
- 現状実装は <parent>/output を返すため fail する想定 (Green は次 commit)

Refs #680"
```

---

## Task 2: §2 #680 Green — deriveDefaultOutDir 実装を新仕様に修正

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx:1015-1037`

- [ ] **Step 2.1: deriveDefaultOutDir の docstring + 実装を書き換える**

`gui/src/screens/ExportScreen.tsx` の 1015-1037 行 (現状の docstring + 関数本体) を以下に置き換える:

```ts
/**
 * #680: source video の親ディレクトリを default 出力先に。
 * 旧実装 (#466 review #2) は `<parent>/output` を返していたが、Export 画面
 * 到達時点では `<parent>/output` が物理的に存在しない (Rust 側
 * `start_detect` は detect 出力先のみ create_dir_all する) ため、ユーザーが
 * 「存在しないフォルダが default にプリセットされている」と混乱した。
 * <parent> のみへ変更し、必ず存在するフォルダを default とする。
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

差分のポイント:

- docstring を `#466 review #2` 根拠から `#680` 根拠に書き換え (#466 review #2 は #545 review #2 の前置きとして言及保持)
- `sep` 変数 (旧: `const sep = normalized.includes('\\') && !normalized.includes('/') ? '\\' : '/';`) と `parent` 変数 + `${parent}${sep}output` 結合を削除
- `return normalized.slice(0, idx);` で `<parent>` のみを返す

- [ ] **Step 2.2: Test を実行して PASS することを確認**

Run:

```bash
cd gui && npm test -- ExportScreen.test.tsx 2>&1 | tail -20
```

Expected: 全 case (deriveDefaultOutDir 5 件 + formatStartForFilename + ExportScreen 他テスト) PASS。

- [ ] **Step 2.3: Green commit**

```bash
git add gui/src/screens/ExportScreen.tsx
git -c commit.gpgsign=false commit -m "feat(gui): #680 deriveDefaultOutDir を <parent> のみ返す仕様に (Green)

- 旧 <parent>/output から <parent> のみへ変更 (存在しないフォルダの
  プリセット問題を解消)
- sep 結合は不要になったため削除
- docstring を #680 根拠に書き換え (#466 review #2 は前置きとして保持)

Refs #680"
```

---

## Task 3: §3 #696 Red — globalErrorListener + ErrorModal の新規 case を追加 (failing 状態を作る)

**Files:**

- Modify: `gui/src/lib/globalErrorListener.test.ts` (末尾追加)
- Modify: `gui/src/components/ErrorModal.test.tsx` (`describe('ErrorModal')` 末尾追加)

- [ ] **Step 3.1: globalErrorListener.test.ts 末尾に新 describe を追加**

`gui/src/lib/globalErrorListener.test.ts` の末尾 (233 行目の `});` の直後) に以下を追加:

```ts

describe('unhandledrejection AppError fallback (#696)', () => {
  let unlisten: (() => void) | null = null;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    invokeMock.mockReset();
    listenMock.mockReset();
    invokeMock.mockResolvedValue('C:\\install\\logs');
    listenMock.mockResolvedValue(() => {});
    unlisten = null;
  });

  afterEach(() => {
    if (unlisten) {
      try {
        unlisten();
      } catch {
        // ignore
      }
      unlisten = null;
    }
  });

  it('routes AppError reason to tauri-command category with hint', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: {
        code: 'io.permission_denied',
        message: 'Permission denied',
        hint: 'ファイル権限を確認してください',
      },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('tauri-command');
    expect(state.errorTitle).toBe('処理中に予期しないエラーが発生しました');
    expect(state.errorMessage).toBe('Permission denied');
    expect(state.errorHint).toBe('ファイル権限を確認してください');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(true);
  });

  it('routes AppError reason without hint to tauri-command (errorHint null)', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: {
        code: 'state.invalid',
        message: 'Invalid state',
      },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorCategory).toBe('tauri-command');
    expect(state.errorMessage).toBe('Invalid state');
    expect(state.errorHint).toBeNull();
  });

  it('non-AppError object reason still uses js-promise path (regression guard)', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: { foo: 'bar' },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorCategory).toBe('js-promise');
    expect(state.errorMessage).toBe('{"foo":"bar"}');
  });
});
```

- [ ] **Step 3.2: ErrorModal.test.tsx の `describe('ErrorModal')` block 末尾に 2 case を追加**

`gui/src/components/ErrorModal.test.tsx` の `it('has role=dialog and aria-modal', ...)` (231 行の `});` の直後、`describe('ErrorModal')` の閉じ `});` の直前) に以下 2 件を追加:

```ts

  // #696: tauri-command category
  it('renders tauri-command title from errorTitle override (#696)', () => {
    useErrorStore.getState().showError({
      errorTitle: '処理中に予期しないエラーが発生しました',
      errorMessage: 'Permission denied',
      errorHint: 'ファイル権限を確認してください',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByText('処理中に予期しないエラーが発生しました')).toBeTruthy();
    expect(screen.getByText('Permission denied')).toBeTruthy();
    expect(screen.getByText('ファイル権限を確認してください')).toBeTruthy();
  });

  it('uses tauri-command default title when errorTitle omitted (#696 defensive)', () => {
    useErrorStore.getState().showError({
      errorMessage: 'Invalid state',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByText('処理中に予期しないエラーが発生しました')).toBeTruthy();
  });
```

挿入位置: `it('has role=dialog and aria-modal', () => { ... });` の閉じ `});` の直後、その次の `});` (= `describe('ErrorModal', ...)` の閉じ) の直前。

- [ ] **Step 3.3: Test を実行して FAIL することを確認**

Run:

```bash
cd gui && npm test -- globalErrorListener.test.ts ErrorModal.test.tsx 2>&1 | tail -40
```

Expected:

- globalErrorListener.test.ts の新規 3 case: `errorCategory` を `'tauri-command'` で受け取る assert が fail (現状実装が `'js-promise'` を返すため case 1/2 が fail、case 3 は元々 pass のはずだが describe 内 setup により試走)
- ErrorModal.test.tsx の新規 2 case: `getByText('処理中に予期しないエラーが発生しました')` が見つからず fail (`defaultTitle` 分岐に `'tauri-command'` ケースが無いため)
- 既存 case は引き続き pass

- [ ] **Step 3.4: Red commit**

```bash
git add gui/src/lib/globalErrorListener.test.ts gui/src/components/ErrorModal.test.tsx
git -c commit.gpgsign=false commit -m "test(gui): #696 AppError fallback の failing case を追加 (Red)

- globalErrorListener.test.ts: unhandledrejection AppError fallback
  describe 新設 (3 case: hint あり / hint なし / 非 AppError regression)
- ErrorModal.test.tsx: tauri-command category の 2 case 追加
  (errorTitle override / defaultTitle fallback)
- Green は次 commit で globalErrorListener.ts + ErrorModal.tsx を実装

Refs #696"
```

---

## Task 4: §3 #696 Green — globalErrorListener + ErrorModal の実装

**Files:**

- Modify: `gui/src/lib/globalErrorListener.ts:1-4` (import 追加) and `gui/src/lib/globalErrorListener.ts:92-115` (`onUnhandledRejection` 分岐追加)
- Modify: `gui/src/components/ErrorModal.tsx:64-72` (`defaultTitle` 分岐追加)

- [ ] **Step 4.1: globalErrorListener.ts に `isAppError` import + `onUnhandledRejection` の `isAppError` 分岐を追加**

`gui/src/lib/globalErrorListener.ts` の 1-4 行目を以下に書き換える (import 追加):

```ts
import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

import { isAppError } from './appError';
import { useErrorStore } from '../state/errorStore';
```

次に 92-115 行目の `onUnhandledRejection` 関数本体を以下に書き換える (先頭に `isAppError` 分岐を追加):

```ts
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

差分のポイント:

- `import { isAppError } from './appError';` 追加 (アルファベット順、`./` paths は `../` paths より前)
- `onUnhandledRejection` 内で `const reason = e.reason;` の直後に `if (isAppError(reason)) { showError({...}); return; }` 分岐を挿入
- 既存の Error / string / object の fall-through は変更なし

- [ ] **Step 4.2: ErrorModal.tsx の `defaultTitle` 分岐に `'tauri-command'` ケースを先頭追加**

`gui/src/components/ErrorModal.tsx` の 64-72 行を以下に書き換える:

```tsx
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

差分のポイント:

- 1 行目のコメントを `#614 / #668` から `#614 / #668 / #696` へ更新
- `if (errorCategory === 'tauri-command')` 分岐を `if (errorCategory === 'integrity')` の前に挿入
- 他の分岐は変更なし

- [ ] **Step 4.3: Test を実行して PASS することを確認**

Run:

```bash
cd gui && npm test -- globalErrorListener.test.ts ErrorModal.test.tsx 2>&1 | tail -20
```

Expected: 全 case (既存 + Step 3.1 / 3.2 で追加した 5 件) PASS。

- [ ] **Step 4.4: Green commit**

```bash
git add gui/src/lib/globalErrorListener.ts gui/src/components/ErrorModal.tsx
git -c commit.gpgsign=false commit -m "feat(gui): #696 catch 漏れ AppError を ErrorModal fallback に統合 (Green)

- globalErrorListener.onUnhandledRejection に isAppError 分岐追加
  (先頭で判定し true なら errorCategory: 'tauri-command' /
  errorTitle: '処理中に予期しないエラーが発生しました' /
  errorHint: reason.hint ?? null / isRecoverable: true で showError)
- ErrorModal.defaultTitle 分岐に 'tauri-command' ケース追加 (defensive、
  'integrity' パターンと同形)
- isAppError は既存の gui/src/lib/appError.ts から import
- errorStore の 'tauri-command' union は既存 (populate 経路が無かっただけ)

Refs #696"
```

---

## Task 5: §3 #696 docs — ui-architecture.md §4 に §4.9 追加

**Files:**

- Modify: `docs/ui-architecture.md` (§4.8 の直後、§5 の直前)

- [ ] **Step 5.1: docs/ui-architecture.md に新規 §4.9 を追加**

`docs/ui-architecture.md` の §4.8 (`metadataStore *ErrorHint lifecycle 規約 (#691)`) 末尾、`## 5. 各画面の phase state` の直前に以下を挿入:

```markdown
### §4.9 catch 漏れ AppError fallback (#696)

screen 側 invoke catch で受け止められなかった AppError (Promise を投げ捨て / async race / try-catch 漏れ等) は [`globalErrorListener.onUnhandledRejection`](../gui/src/lib/globalErrorListener.ts) が `isAppError(reason)` で判定し、`errorCategory: 'tauri-command'` / `errorTitle: '処理中に予期しないエラーが発生しました'` / `errorHint: reason.hint ?? null` / `isPanic: false` / `isRecoverable: true` で ErrorModal に表示する。

screen 自身の recoverable inline error UI (各 screen の local state による表示、§4.7 / §4.8) とは独立した最終 fallback として機能し、modal は `閉じる` button で dismiss 可。`errorStore` の first-write-wins 規約により、既に他カテゴリの modal が open 中であれば本 fallback は dropped される。

PR #689 (Phase 4 of #663) で `'tauri-command'` カテゴリ自体は `errorStore` の union に予約済だったが、populate 経路 (本 fallback) は #696 で追加された。
```

挿入位置: `## 5. 各画面の phase state` (現状 205 行目) の直前。

- [ ] **Step 5.2: markdownlint を実行して PASS することを確認**

Run:

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -10
```

Expected: `Summary: 0 error(s)`。万一 MD028 (連続 blockquote 空行) や MD056 (table cell `|`) でエラーが出たら本 §4.9 セクションをを修正。

- [ ] **Step 5.3: Docs commit**

```bash
git add docs/ui-architecture.md
git -c commit.gpgsign=false commit -m "docs: #696 ui-architecture §4.9 catch 漏れ AppError fallback 追加

- §4.8 の直後、§5 の直前に新規 §4.9 を 1 段落で追加
- globalErrorListener.onUnhandledRejection の isAppError 分岐、
  errorCategory 'tauri-command' / isRecoverable: true の動作、
  screen inline error との独立性 (first-write-wins) を明記

Refs #696"
```

---

## Task 6: 全 path 自動チェック (Iron Law 6) + markdownlint final

**Files:** (検証のみ、変更なし)

- [ ] **Step 6.1: GUI lint / typecheck / test / build を実行**

Run:

```bash
cd gui && npm run lint && npm run typecheck && npm test && npm run build 2>&1 | tail -30
```

Expected: 全 step exit 0。test step は新規 5 case + 既存全 case PASS。build は `gui/dist/` を再生成する。

- [ ] **Step 6.2: Rust 側 cargo check を実行**

Run:

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -10
```

Expected: `Finished` で完了。本 PR は Rust 側未変更だが慣行に従い実行。

- [ ] **Step 6.3: markdownlint を全リポジトリで実行**

Run:

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: `Summary: 0 error(s)`。

- [ ] **Step 6.4: チェック結果を memo に記録 (PR 本文 Self-Test Report 用)**

各コマンドの結果 (PASS / FAIL + 1 行サマリ) を以下のような Markdown 表形式でメモする。PR 本文 §Self-Test Report (Task 8) で `[x]` 化する:

```text
[x] cd gui && npm run lint              -> PASS (0 errors, 0 warnings)
[x] cd gui && npm run typecheck         -> PASS (tsc --noEmit 0 errors)
[x] cd gui && npm test                  -> PASS (N test, all green、新規 5 case 含む)
[x] cd gui && npm run build             -> PASS (vite build OK, gui/dist/ 生成)
[x] cd gui/src-tauri && cargo check     -> PASS (Finished)
[x] bash scripts/check-markdownlint.sh  -> PASS (0 errors)
```

---

## Task 7: PR Pre-flight (Iron Law 6 #659 規約)

**Files:** (検証のみ、変更なし)

- [ ] **Step 7.1: base branch から未取り込み commit を確認**

Run:

```bash
git fetch origin develop-0.2.0 2>&1
git log HEAD..origin/develop-0.2.0 --oneline 2>&1 | head -30
```

Expected: 出力が空 (= base 取り込み済) or 1-N commit 表示。**当 PR の touched files (ExportScreen.tsx / ExportScreen.test.tsx / globalErrorListener.ts / globalErrorListener.test.ts / ErrorModal.tsx / ErrorModal.test.tsx / docs/ui-architecture.md) と交差する commit があれば** Step 7.2 へ。なければ Step 7.3 へ。

- [ ] **Step 7.2: 未取り込み base commit と touched files の交差を確認 (該当時のみ)**

Run:

```bash
git log HEAD..origin/develop-0.2.0 --name-only --format=format:"=== %h %s ===" 2>&1 | head -60
```

touched files (上記 7 ファイル) のいずれかが出現したら:

```bash
git merge origin/develop-0.2.0 2>&1
# conflict が出たら手動解消、conflict なしなら Task 6 (自動チェック) を再実行
```

- [ ] **Step 7.3: 並行 worktree PR 重複を確認**

Run:

```bash
gh pr list --search "680 OR 696" --state all 2>&1
```

Expected: 本 PR 以外で #680 / #696 を扱う open / draft PR が無いこと。重複があれば AskUserQuestion で対処確認 (Iron Law 2)。

- [ ] **Step 7.4: Idios 実機検証 (Iron Law 6 trigger) を AskUserQuestion で依頼**

以下 3 項目を `AskUserQuestion` (multi-question) で Idios に依頼する:

1. **(#680 a) 修正版 GUI Tauri 起動**: `cd gui && npm run tauri dev` で起動 → 動画ファイルを drop → 試合分割 → Export 画面で出力先 textbox 初期値が `<parent>` のみ (末尾 `\output` なし、例: `E:\videos`) になっているか?
2. **(#680 b) 報告画像形式の再現確認**: 現行 (未修正) ビルドで Export 画面で `E:\videos\<stem>_allaganeye` 形式が表示されるか? 再現する場合は本 Lane で別 setOutDir 経路を調査 (issue body 受け入れ条件 #5)、再現しなければ「screenshot was from older build」として本修正のみで close 待ち
3. **(#696) catch-miss シナリオ手動再現**: 任意 screen の invoke catch block を一時的に `throw e;` で rethrow → 不正パスで `load_metadata` 等を発火 → ErrorModal が `'処理中に予期しないエラーが発生しました'` 表記で開き、`閉じる` button で dismiss できるか確認? (現実的でなければ unit test pass を以て machine-verified 扱いとし、Self-Test Report の `-` (unverifiable) 行で justification 記載)

回答は Self-Test Report に反映 (Task 8 Step 8.2)。

---

## Task 8: PR 作成 + Self-Test Report

**Files:** (PR 本文のみ、コード変更なし)

- [ ] **Step 8.1: branch を origin に push**

Run:

```bash
git push -u origin claude/interesting-kirch-6bcbfa 2>&1
```

Expected: `Branch ... set up to track 'origin/claude/interesting-kirch-6bcbfa'`。

- [ ] **Step 8.2: PR body 草稿を作成 (HEREDOC 経由、UTF-8 担保)**

以下 HEREDOC で `pr_body.md` を作成 (記法は `feedback_gh_command_ja_heredoc.md` 参照)。プロジェクトルートで実行:

```bash
cat > /tmp/pr_body.md << 'EOF'
## 概要

Lane II-b' (= Group D 残) の 2 件 (#680 + #696) を 1 PR で消化する。

- **#680 (P3 bug)**: Export 画面の出力先 default を `<parent>/output` → `<parent>` のみへ変更 (存在しないフォルダのプリセット混乱を解消)
- **#696 (P3 task)**: globalErrorListener.onUnhandledRejection に isAppError 分岐を追加し、catch 漏れ AppError を ErrorModal に `'tauri-command'` カテゴリで fallback 表示する経路を実装

設計詳細は [docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md](docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md) を参照。

Refs #680 #696

## 受け入れ条件 (#680)

- [x] `deriveDefaultOutDir` が `<dirname>` のみ返すよう変更
  - diff: [gui/src/screens/ExportScreen.tsx:1015-1037](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/screens/ExportScreen.tsx#L1015-L1037) (sep 結合削除、return normalized.slice(0, idx))
- [x] 既存の `deriveDefaultOutDir` 単体テスト更新 (Windows / Unix / extended-length prefix `\\?\` / null)
  - diff: [gui/src/screens/ExportScreen.test.tsx:52-78](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/screens/ExportScreen.test.tsx#L52-L78) (5 it() block の expected + 名前を新仕様に)
- [x] 既存の Export 一気通貫テスト (`flow.integration.test.tsx` 等) で default 値 assertion の更新
  - 確認結果: `gui/src/__tests__/flow.integration.test.tsx` には `deriveDefaultOutDir` / `outDir` default の assertion が無く更新不要 (grep 0 hits)。`gui/src/utils/path.test.ts:42-43` の `joinPath('E:/videos/output', ...)` は `joinPath` 関数の単体テストで `deriveDefaultOutDir` の出力に依存しないため変更不要。
- (#680 a) **実機ビルドで再現確認 (Idios)**: 修正版 GUI Tauri 起動 → Export 画面 textbox 初期値が `<parent>` のみ
- (#680 b) **報告画像形式の再現確認 (Idios)**: 未修正ビルドで `E:\videos\<stem>_allaganeye` 形式が再現するか
- (再現時) 別 setOutDir 経路を `deriveDefaultOutDir` に統一 (条件付き)

## 受け入れ条件 (#696)

- [x] `globalErrorListener.ts` の `onUnhandledRejection` で `isAppError(e.reason)` を判定し、true なら `errorCategory: 'tauri-command'`, `errorTitle: '処理中に予期しないエラーが発生しました'`, `errorMessage: e.reason.message`, `errorHint: e.reason.hint ?? null` を `errorStore.showError` に流す
  - diff: [gui/src/lib/globalErrorListener.ts](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/lib/globalErrorListener.ts) (isAppError import 追加 + onUnhandledRejection 先頭に分岐挿入)
- [x] `ErrorModal.tsx` で `errorCategory === 'tauri-command'` の表示パターンを定義 (recoverable / Issue で報告 / コピー button 構成)
  - diff: [gui/src/components/ErrorModal.tsx:64-74](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/components/ErrorModal.tsx#L64-L74) (defaultTitle 分岐に 'tauri-command' ケース先頭追加、recoverable + Issue 本文をコピー + 詳細をコピー + 閉じる の既存構成を流用)
- [x] 既存 6 panic-related test に加え `'tauri-command'` errorCategory の test を追加
  - diff: [gui/src/lib/globalErrorListener.test.ts](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/lib/globalErrorListener.test.ts) (新規 describe 3 case) + [gui/src/components/ErrorModal.test.tsx](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/gui/src/components/ErrorModal.test.tsx) (新規 2 case)
- [x] `docs/ui-architecture.md` §4 に「catch 漏れ AppError は ErrorModal fallback」を追記
  - diff: [docs/ui-architecture.md](https://github.com/Idios/kobutachan-allaganeye/blob/claude/interesting-kirch-6bcbfa/docs/ui-architecture.md) (新規 §4.9 を 1 段落追加)
- (#696) **実機ビルドで catch-miss シナリオ確認 (Idios)**: dev-only rethrow patch で ErrorModal が `'tauri-command'` 表記で開く / `閉じる` で dismiss 可

## Self-Test Report

**machine-verified** (`[x]` 印):

- [x] `cd gui && npm run lint` -> PASS (0 errors)
- [x] `cd gui && npm run typecheck` -> PASS (tsc --noEmit OK)
- [x] `cd gui && npm test` -> PASS (新規 5 case + 既存全 case green)
- [x] `cd gui && npm run build` -> PASS (vite build, gui/dist/ 生成)
- [x] `cd gui/src-tauri && cargo check` -> PASS (Finished)
- [x] `bash scripts/check-markdownlint.sh` -> PASS (0 errors)

**machine-unverifiable** (plain bullet `-`、Idios 実機検証回答を反映):

- (#680 a) Idios 実機検証: 修正版 GUI 起動 → Export 画面 textbox 初期値が `<parent>` のみ (末尾 `\output` なし) であることを目視確認 [Task 7.4 回答を転記]
- (#680 b) Idios 実機検証: 未修正ビルドで `<stem>_allaganeye` 形式が再現するか [Task 7.4 回答を転記、再現時は本 PR 内追加修正 or 別 issue 起票]
- (#696) Idios 実機検証: dev-only patch で screen invoke catch を bypass → ErrorModal が `'tauri-command'` 表記で開き `閉じる` で dismiss 可 [Task 7.4 回答を転記、現実的でなければ unit test pass で代替の justification 記載]

## 関連

- 設計 spec: [docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md](docs/superpowers/specs/2026-05-13-l2b-prime-group-d-residual-design.md)
- 上位 roadmap: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md) Lane II-b'
- 旧 Group D 4 件 spec: [docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md](docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md) (本 PR は §2.3 / §2.4 部分を supersede)
- session-id: `interesting-kirch-6bcbfa`

## 後続

- Wave 2 で `/close-issue` skill により #680 / #696 を実測再検証 + 手動 close (Iron Law 4)
- 本 PR merge 後、Lane V Phase 2 (#694 unified ErrorState refactor) の gating 解除を確認 (roadmap §3-bis 衝突 matrix)
EOF
```

Step 7.4 で AskUserQuestion から得た Idios 回答に基づき `[Task 7.4 回答を転記]` の plain bullet を実際の回答に置き換える。

- [ ] **Step 8.3: PR を作成**

Run:

```bash
gh pr create \
  --base develop-0.2.0 \
  --head claude/interesting-kirch-6bcbfa \
  --title "feat(gui): #680 #696 ExportScreen default outDir + ErrorModal tauri-command fallback" \
  --body-file /tmp/pr_body.md \
  2>&1
```

Expected: PR URL を表示。

- [ ] **Step 8.4: PR URL を memo + close 後の handoff を伝達**

PR URL を `interesting-kirch-6bcbfa` session の TodoWrite に記録し、ユーザー (Idios) に handoff:

> Lane II-b' Group D 残 (#680 + #696) の PR を `<URL>` として作成しました。
>
> 受け入れ条件は machine-verified 部分は全 [x]、Idios 実機検証 (#680 textbox 初期値 / #680 `_allaganeye` 再現 / #696 catch-miss modal) は Task 7.4 で回答済の内容を Self-Test Report に反映済です。
>
> Wave 2 では `/close-issue #680` / `/close-issue #696` で実測再検証 + 手動クローズしてください (Iron Law 4)。本 PR merge 後、Lane V Phase 2 (#694) の gating が解除されます。

---

## Self-Review (plan vs spec)

### Spec coverage

| spec section | spec requirement | implementing task |
| --- | --- | --- |
| §2.1 / §2.2 | #680 deriveDefaultOutDir を `<parent>` のみ返すよう変更 | Task 2 (Green) |
| §2.2 Red | 既存 5 unit test の expected を新仕様へ更新 | Task 1 |
| §2.2 Green / §2.3 受け入れ条件 #3 | `flow.integration.test.tsx` 等の default 値 assertion 更新 | Task 8 PR body で「該当 file に対象 assertion なし、更新不要」を実証付き記載 (Step 8.2) |
| §2.3 受け入れ条件 | 5 項目を PR body で逐条引用 | Task 8 Step 8.2 (`受け入れ条件 (#680)` ブロック) |
| §2.4 Idios 実機検証 (a)(b) | AskUserQuestion で依頼 | Task 7 Step 7.4 |
| §3.1 / §3.2 Green | #696 globalErrorListener + ErrorModal 実装 | Task 4 |
| §3.2 Red | globalErrorListener.test.ts 3 case + ErrorModal.test.tsx 2 case | Task 3 (Step 3.1 / 3.2) |
| §3.3 表示パターン | recoverable / Issue 本文をコピー / 詳細をコピー / 閉じる の既存構成を流用 | Task 4 Step 4.2 (実装) + Task 3 Step 3.2 (test で validate) |
| §3.4 受け入れ条件 | 4 項目を PR body で逐条引用 | Task 8 Step 8.2 (`受け入れ条件 (#696)` ブロック) |
| §3.5 Idios 実機検証 (i)(ii) | AskUserQuestion で依頼 | Task 7 Step 7.4 |
| §4.1 Pre-flight | git fetch + log + gh pr list | Task 7 Step 7.1-7.3 |
| §4.2 自動チェック | lint / typecheck / test / build / cargo check / markdownlint | Task 6 |
| §4.3 TDD HARD-GATE | Red → Green → Refactor 各章 | Task 1 / 2 / 3 / 4 / 5 で順守 |
| §4.4 Self-Test Report | machine-verified `[x]` / unverifiable `-` | Task 8 Step 8.2 (Self-Test Report ブロック) |
| §4.5 PR 本文 | title / Refs #680 #696 / 受け入れ条件逐条 / Self-Test Report / session-id / spec link | Task 8 Step 8.2 / 8.3 |
| §4.6 Post-merge handoff | Wave 2 `/close-issue` + Lane V P2 gating 解除 | Task 8 Step 8.4 (handoff message に明記) |
| §5 Out of scope | Rust hint 拡張 / #694 / 他 errorCategory / stacktrace / 全画面 audit | 本 plan で扱わない (本 self-review で確認、新規 task なし) |
| §6 リスクと対応策 | 5 リスク | Task 2 (sep 変数残らない確認) / Task 4 (二重表示の intended fallback 動作) / Task 8 (V P2 gating 通知) / Task 7 (dev-only patch を commit に混入しない、Task 4 完了時点で `git diff` 確認) / Task 5 (MD028/MD056 確認) で対応 |

### Placeholder scan

`TBD` / `TODO` / `FIXME` / `implement later` / `add appropriate error handling` の検索結果 — 該当なし。`[Task 7.4 回答を転記]` は明示的なフィールド (Idios 回答を Task 7.4 で取得 → Task 8 Step 8.2 で記入する手順を文書化済) なので placeholder ではなく明示的な workflow handoff。

### Type / function signature consistency

- `deriveDefaultOutDir(videoSource: string | null): string` — Task 1 と Task 2 で同一 signature
- `isAppError(reason): reason is AppError` — Task 4 で既存 helper を流用 (`gui/src/lib/appError.ts:27-31`)
- `useErrorStore.showError(spec: ErrorSpec)` の `ErrorSpec` 各 field 名 (`errorTitle` / `errorMessage` / `errorHint` / `errorStack` / `errorCategory` / `isPanic` / `isRecoverable`) — Task 3 (test) と Task 4 (impl) で完全一致 (`gui/src/state/errorStore.ts:20-28` の interface 通り)
- `errorCategory: 'tauri-command'` — Task 3 / 4 / 5 すべてで同一 literal 文字列

---

## Risk Recap (per spec §6, 実装手順の中で対処済)

| リスク | 対応 task |
| --- | --- |
| #680 後の別 setOutDir 経路再現 | Task 7 Step 7.4 (a)(b) で Idios 検証 → 再現時は本 Lane 内で追加修正 (issue body 受け入れ条件 #5) |
| #696 二重表示懸念 | Task 4 で intended fallback として保持、Task 5 §4.9 docs で first-write-wins 規約を明示 |
| Lane V P2 gating 確認漏れ | Task 8 Step 8.4 handoff message で Idios に通知 |
| dev-only patch (#696 検証用) の commit 混入 | Task 7.4 (#696) で「現実的でなければ unit test pass で代替」と明示、patch を当てる場合は Task 6 / 7 完了後の clean state で実施し PR push 前に `git diff origin/develop-0.2.0` で patch なしを確認 |
| markdownlint MD028 / MD056 | Task 5 Step 5.2 で全リポジトリ markdownlint 実行 / Task 6 Step 6.3 で再確認 |
