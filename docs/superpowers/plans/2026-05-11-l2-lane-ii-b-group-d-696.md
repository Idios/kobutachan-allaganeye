# L2 Lane II-b: Group D + #696 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ExportScreen + ErrorModal + globalErrorListener 周辺の 4 件 ([#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) P2 / [#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) / [#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) / [#696](https://github.com/Idios/kobutachan-allaganeye/issues/696)) を **4 PR 直列** で消化し、user が実エラーに遭遇したときの UX を底上げする。

**Architecture:**

- 1 spec / 4 章 / 4 PR 直列 (#678 → #669 → #680 → #696)。
- §2.1 (#678): 残 4 site の `String(e)` を既存 `appErrorMessage(e)` に置き換え + 一部 site で `appErrorHint` UI を追加。
- §2.2 (#669): `gui/src/lib/issueReportUrl.ts` を新設 (8KB budget + 段階削減) + 新 Tauri command `read_error_log_tail` (当日 log + 前日 fallback) + `ErrorModal` の Issue 報告 link を pre-fill URL に差し替え + `formatSystemInfo()` helper 新設。
- §2.3 (#680): `deriveDefaultOutDir` を `<dirname>/output` → `<dirname>` に修正。
- §2.4 (#696): `globalErrorListener.onUnhandledRejection` に `isAppError` 分岐を追加 + `ErrorModal` の default title 分岐に `'tauri-command'` を追加。

**Tech Stack:** React 19 / TypeScript / Vite / Tauri 2.x / Zustand / vitest / jest-axe / Rust (Tauri backend) / cargo test / markdownlint

**Spec:** [`docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md`](../specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md) (commit 2c2e695)

**Iron Law 厳守:**

- **1. NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED**: 各 PR 本文に元 issue の受け入れ条件全項目を逐条引用 + 対応 diff / test を逐条引用。
- **3. NO SCOPE CREEP WITHOUT NEW ISSUE**: §2.1 で `String(e)` site が 4 か所超で見つかれば別 issue 起票判断。§2.3 で別 setOutDir 経路発見も別 issue。
- **4. NO Closes / Fixes / Resolves KEYWORDS**: PR 本文・commit に Closes/Fixes/Resolves 禁止、`Refs #N` のみ。マージ後 `/close-issue` で手動 close。
- **6. NO PR CREATION WITHOUT VERIFIED CHECKS**: 全 PR で `cd gui && npm run lint && npm run typecheck && npm test && npm run build` ✅ + §2.2 のみ `cd gui/src-tauri && cargo check && cargo test` ✅ + path 別 自動チェック + 実機検証を AskUserQuestion で依頼。

---

## File Structure

### 新規 file

| path | 責務 |
| --- | --- |
| `gui/src/lib/issueReportUrl.ts` | (§2.2) GitHub Issue form pre-fill URL builder (`buildIssueReportUrl`) + truncation helper (`truncateLogToBudget`)。`actual` / `environment` / `log_file_attachment` の 3 field を 8KB budget 内で組み立てる |
| `gui/src/lib/issueReportUrl.test.ts` | (§2.2) builder の vitest (8KB boundary / 4 段階削減 / CJK encoding / 切り詰め通知 / 空 logExcerpt) |
| `gui/src/lib/systemInfo.ts` | (§2.2) `formatSystemInfo(systemInfo: SystemInfo)` を export。`metadata.system_info` を bug_report.yml の `environment` placeholder 形式 (allaganeye 0.2.0 (ffmpeg ..., ...) / CPU: ... / GPU: ... / Memory: ...) で renders |
| `gui/src/lib/systemInfo.test.ts` | (§2.2) formatter の vitest (`system_info` 完全形 / GPU 不在 / 部分欠落 / null) |

### 修正 file

| path | 修正概要 |
| --- | --- |
| `gui/src/screens/ExportScreen.tsx` | (§2.1) `handleOpenFolder` catch を `appErrorMessage(e)` + `appErrorHint(e)` の 2 行表示に変更 (line 425 周辺) / (§2.3) `deriveDefaultOutDir` の return 値を `parent` のみに修正 + docstring 更新 (line 948-959 周辺) |
| `gui/src/screens/ExportScreen.test.tsx` | (§2.1) handleOpenFolder catch の test を AppError struct / Error / string / null / undefined の 5 ケースに拡張 / (§2.3) `deriveDefaultOutDir` テスト + flow integration test の default 値 assertion を新仕様に更新 |
| `gui/src/screens/PreviewScreen.tsx` | (§2.1) `register_video` catch を `appErrorMessage(e)` に置き換え (line 245)。既存 `videoErrorHint` 枠なしのため hint UI 追加なし (spec §2.1 規約) |
| `gui/src/screens/PreviewScreen.test.tsx` | (§2.1) `register_video` 失敗の test に AppError struct ケースを追加 |
| `gui/src/components/ConfirmExitModal.tsx` | (§2.1) save catch (line 41) + discard catch (line 66) を `appErrorMessage(e)` に置き換え + `errorHint` 行表示を追加 (#663 modal 整合) |
| `gui/src/components/ConfirmExitModal.test.tsx` | (§2.1) probe / kill 失敗時の test に AppError struct ケースを追加 + hint 表示 assertion |
| `gui/src/components/ErrorModal.tsx` | (§2.2) `Issue で報告` link の `href` を `useState<string>(BASE_URL)` + `useEffect` で builder 経由に変更 / (§2.4) default title 分岐に `'tauri-command'` を追加 |
| `gui/src/components/ErrorModal.test.tsx` | (§2.2) pre-fill URL が `actual` / `environment` / `log_file_attachment` の 3 field を含むこと assert / (§2.4) `errorCategory: 'tauri-command'` の default title + 閉じる button assertion + jest-axe a11y |
| `gui/src/lib/globalErrorListener.ts` | (§2.4) `onUnhandledRejection` に `isAppError(reason)` 分岐を追加 (line 92-115 周辺)、`'tauri-command'` errorCategory + recoverable で `showError` |
| `gui/src/lib/globalErrorListener.test.ts` | (§2.4) AppError struct reject 流入時 `'tauri-command'` category が errorStore に流れる test + 既存 `'js-promise'` 経路の regression |
| `gui/src-tauri/src/lib.rs` | (§2.2) `read_error_log_tail(line_count: usize) -> Result<String, AppError>` 新 command 追加 + `invoke_handler` 登録 / (§2.4) `dev_force_unhandled_apperror` 開発用 command を追加 (実機検証用、debug builds only) |
| `docs/tauri-commands.md` | (§2.2) `read_error_log_tail` 新 command を表 / 詳細 sections に追記 + (§2.4) `dev_force_unhandled_apperror` を debug-only command として追記 |
| `docs/ui-architecture.md` | (§2.4) §4 (エラーハンドリング) に「catch 漏れ AppError は `'tauri-command'` errorCategory で ErrorModal fallback 表示」 + (§2.2) 「ErrorModal の Issue 報告 link は bug_report.yml の `actual`/`environment`/`log_file_attachment` を pre-fill」を追記 |

### 触らない file (Iron Law 3 確認用)

- `gui/src/state/errorStore.ts` — `'tauri-command'` errorCategory は既に line 16 で定義済 ([`errorStore.ts:12-18`](../../../gui/src/state/errorStore.ts))、本 lane では既存 type を populate するのみ
- `gui/src/lib/appError.ts` — `appErrorMessage`/`appErrorHint`/`isAppError` は #663 で既に実装済、本 lane では import するのみ
- `.github/ISSUE_TEMPLATE/bug_report.yml` — Group G PR #688 で凍結済、本 lane では field id (`actual`/`environment`/`log_file_attachment`) を使うのみ
- `gui/src/state/metadataStore.ts` — §2.2 で `system_info` を読むだけで mutation なし

---

## 共通: PR 単位 Pre-flight 手順 (4 PR で再利用)

各 PR 着手時に必ず実行する:

```bash
# 1. 最新の develop-0.2.0 を fetch
git fetch origin develop-0.2.0

# 2. 取り込み未済 commit 確認
git log HEAD..origin/develop-0.2.0 --oneline

# 3. 取り込み未済が当 PR touched files と交差なら merge して自動チェック再実行
git merge origin/develop-0.2.0  # 必要時のみ
cd gui && npm run lint && npm run typecheck && npm test && npm run build && cd ..

# 4. 並行 worktree PR 重複確認
gh pr list --search "<元 issue#>" --state all
```

加えて章別 Pre-flight (§4.2 spec):

- **§2.1 (PR 1) 着手時**: 4 site の grep を再確認 (codebase の変化で site 数が増えていないか)
  - 確認 grep: `cd gui/src && grep -rn 'String(e)' --include='*.ts' --include='*.tsx'`
  - 期待 site 数: **4 か所** (ExportScreen handleOpenFolder / PreviewScreen register_video / ConfirmExitModal ×2)
  - 4 か所超なら scope-guard で AskUserQuestion (別 issue 起票 or scope 拡大の判断)
- **§2.2 (PR 2) 着手時**: bug_report.yml の field id を確認
  - 確認: `grep -E '^\s*id:' .github/ISSUE_TEMPLATE/bug_report.yml`
  - 期待 id: `reproduction` / `expected` / `actual` / `environment` / `log_file_attachment` / `consent`
- **§2.3 (PR 3) 着手時**: 報告画像 `..._allaganeye` 形式が実機で再現するか **着手前** に Idios に AskUserQuestion で確認 (再現したら scope 拡大の判断を取り直す)
- **§2.4 (PR 4) 着手時**: §2.2 (#669) PR がマージ済か確認 (ErrorModal `reportUrl` 変更 base 上で §2.4 default title 分岐を追加)

---

## 共通: Self-Test Report 規約 (4 PR 本文テンプレ共通部分)

各 PR 本文に以下 section を含める ([`docs/l2-workflow.md`](../../l2-workflow.md) §「Self-Test Report 規約」 準拠):

```markdown
## Self-Test Report

### Machine-verified

- [x] `cd gui && npm run lint` — 0 errors
- [x] `cd gui && npm run typecheck` — 0 errors
- [x] `cd gui && npm test` — N tests passed
- [x] `cd gui && npm run build` — bundle generated
<!-- §2.2 のみ追加 -->
- [x] `cd gui/src-tauri && cargo check` — 0 errors
- [x] `cd gui/src-tauri && cargo test` — N tests passed

### Machine-unverifiable

- 実機 Tauri 起動による UI 反映 (Idios 実機検証で確認、結果は本 PR の review コメントで報告)
```

---

## 共通: 4 PR 順序の再確認 (Iron Law 3 + roadmap §4.5)

```text
PR 1 (§2.1 #678) → merge → /close-issue → PR 2 (§2.2 #669) → merge → /close-issue →
PR 3 (§2.3 #680) → merge → /close-issue → PR 4 (§2.4 #696) → merge → /close-issue
```

各 PR は前 PR が **マージ済** であることを着手の前提とする。**(plan / spec の commit は PR 1 内)** とする (本 plan file + spec file が同一 PR で commit される)。

---

## PR 1: §2.1 #678 — 残 4 site の `String(e)` → `appErrorMessage(e)` migration

### PR 1 の元 issue 受け入れ条件 ([#678](https://github.com/Idios/kobutachan-allaganeye/issues/678) より引用)

> - [ ] `gui/src/utils/formatTauriError.ts` (or 同等) を新設し、`AppError` struct を読みやすい文字列に変換する helper を実装
> - [ ] 全画面の `invoke` catch block (Drop / Detecting / Preview / Complete / Export 各画面) で helper を適用
> - [ ] unit test: `AppError` struct / `Error` instance / 文字列 / null / undefined / 空 object の各ケースで期待通りの文字列を返す
> - [ ] export_match 失敗の e2e 再現確認 (sample 動画で意図的に失敗させる、もしくは Rust 側 mock invoke で AppError を return)
> - [ ] 既存の各画面 vitest テスト更新 (error 表示の assertion を新フォーマットに合わせる)

**brainstorming 決定** (spec §1.4 #2): issue 本文の「helper を新設」は `appErrorMessage` (#663 で既に存在) と重複のため、**既存 helper を使い残 4 site に適用** する形で受け入れ条件を解釈する。PR 本文で「issue 本文と現状の差分」セクションを設け、helper 新設→既存利用への解釈変更を明記する。

### Task 1.1: §2.1 ExportScreen `handleOpenFolder` catch を `appErrorMessage(e)` + `appErrorHint(e)` に置き換える

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx:418-427` (handleOpenFolder 関数本体)
- Test: `gui/src/screens/ExportScreen.test.tsx` (handleOpenFolder catch path test)

- [ ] **Step 1: spec §2.1 規約に従って test を先に書く (Red)**

`gui/src/screens/ExportScreen.test.tsx` の handleOpenFolder catch path test として以下を追加:

```ts
import { appErrorMessage, appErrorHint } from '../lib/appError';

describe('ExportScreen handleOpenFolder catch', () => {
  it('renders AppError struct message + hint as 2-line error (#678)', async () => {
    const appError = {
      code: 'io.file_not_found',
      message: '指定された出力先が見つかりません',
      hint: 'パスを確認してください',
    };
    // mock invoke('open_folder_in_explorer') -> Promise.reject(appError)
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'open_folder_in_explorer') throw appError;
      return undefined;
    });
    const { getByText, getByRole } = render(<ExportScreen />);
    // ... setup phase 'completed'
    fireEvent.click(getByRole('button', { name: 'フォルダを開く' }));
    await waitFor(() => {
      expect(getByText('指定された出力先が見つかりません')).toBeInTheDocument();
      expect(getByText('パスを確認してください')).toBeInTheDocument();
    });
  });

  it('renders Error instance message only when no hint (#678)', async () => {
    const err = new Error('Some error');
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'open_folder_in_explorer') throw err;
      return undefined;
    });
    // ... similar render + click
    await waitFor(() => {
      expect(screen.getByText('Some error')).toBeInTheDocument();
      // hint は表示されないことを assert
      expect(screen.queryByTestId('open-folder-error-hint')).not.toBeInTheDocument();
    });
  });

  it('renders String(e) result for raw value (#678)', async () => {
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'open_folder_in_explorer') throw 'simple string';
      return undefined;
    });
    // ... render + click
    await waitFor(() => {
      expect(screen.getByText('simple string')).toBeInTheDocument();
    });
  });

  it('renders Unknown error for null/undefined reject (#678)', async () => {
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'open_folder_in_explorer') throw null;
      return undefined;
    });
    // ... render + click
    await waitFor(() => {
      // `appErrorMessage(null)` returns 'null' via String(null), should not be '[object Object]'
      const errorEl = screen.queryByRole('alert');
      expect(errorEl?.textContent).not.toBe('[object Object]');
    });
  });
});
```

- [ ] **Step 2: test を実行して FAIL を確認 (Red 確定)**

```bash
cd gui && npm test -- ExportScreen.test.tsx -t 'handleOpenFolder'
```

期待: 4 new tests FAIL (テスト追加分の expect が現行コード `String(e)` で `[object Object]` が出るため)

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/screens/ExportScreen.tsx` の以下 3 箇所を修正:

1. import 追加 (file 上部 import section):

   ```ts
   import { appErrorHint, appErrorMessage } from '../lib/appError';
   ```

   既に line 7 で import 済なら no-op。

2. `handleOpenFolder` 関数本体 (line 418-427):

   ```ts
   // 旧
   const [openFolderError, setOpenFolderError] = useState<string | null>(null);
   const [openFolderErrorHint, setOpenFolderErrorHint] = useState<string | null>(null);

   async function handleOpenFolder() {
     setOpenFolderError(null);
     setOpenFolderErrorHint(null);
     try {
       await invoke('open_folder_in_explorer', { path: outDir });
     } catch (e) {
       setOpenFolderError(appErrorMessage(e));
       setOpenFolderErrorHint(appErrorHint(e));
     }
   }
   ```

   `openFolderErrorHint` state を追加 (`useState<string | null>(null)`)。

3. UI 表示部分 (既存 `{openFolderError && ...}` block) に hint 行追加:

   ```tsx
   {openFolderError && (
     <p className={styles.openFolderError} role="alert">
       <span>{openFolderError}</span>
       {openFolderErrorHint && (
         <span className={styles.openFolderErrorHint} data-testid="open-folder-error-hint">
           💡 {openFolderErrorHint}
         </span>
       )}
     </p>
   )}
   ```

   既存 CSS module に `.openFolderError` / `.openFolderErrorHint` が無ければ追加 (1 行 hint の小さい text style)。

- [ ] **Step 4: test を実行して PASS 確認 (Green 確定)**

```bash
cd gui && npm test -- ExportScreen.test.tsx -t 'handleOpenFolder'
```

期待: 4 tests PASS

- [ ] **Step 5: 既存 ExportScreen test 全体が regression なく通ることを確認 (Refactor 前 sanity check)**

```bash
cd gui && npm test -- ExportScreen.test.tsx
```

期待: 既存 N tests + 新 4 tests がすべて PASS

- [ ] **Step 6: lint / typecheck も clean か確認**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 7: コミット (Task 1.1 単独)**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.test.tsx gui/src/screens/ExportScreen.module.css
git commit -F - <<'EOF'
refactor(gui): #678 ExportScreen handleOpenFolder catch を appErrorMessage(e) + appErrorHint(e) に置き換え (Lane II-b §2.1)

[object Object] 表示の解消、Refs #678
EOF
```

### Task 1.2: §2.1 PreviewScreen `register_video` catch を `appErrorMessage(e)` に置き換える

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx:230-252` (register_video useEffect)
- Test: `gui/src/screens/PreviewScreen.test.tsx`

**重要**: PreviewScreen には `videoErrorHint` 枠が存在しない (grep 確認済、`videoError` のみ)。spec §2.1 規約「既存枠なし → message のみ」に従い hint UI 追加なし。`videoError` への `appErrorMessage(e)` 適用のみ。

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/screens/PreviewScreen.test.tsx` に以下 test を追加:

```ts
describe('PreviewScreen register_video catch (#678)', () => {
  it('renders AppError struct message (not [object Object])', async () => {
    const appError = { code: 'io.read_failed', message: '動画を開けませんでした', hint: 'ファイルを確認' };
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'register_video') throw appError;
      return undefined;
    });
    // ... setup metadata + videoSource
    const { findByText } = render(<PreviewScreen />);
    expect(await findByText('動画を開けませんでした')).toBeInTheDocument();
    // hint は PreviewScreen に既存枠なし → 表示しない (spec §2.1 規約)
    expect(screen.queryByText('ファイルを確認')).not.toBeInTheDocument();
  });

  it('renders Error message and string reject without [object Object] (#678)', async () => {
    // ... similar
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- PreviewScreen.test.tsx -t 'register_video catch'
```

期待: FAIL (現行 `String(e)` で `[object Object]` 化)

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/screens/PreviewScreen.tsx:245` の `setVideoError(e instanceof Error ? e.message : String(e));` を:

```ts
import { appErrorMessage } from '../lib/appError';

// ... line 245 周辺
} catch (e) {
  if (!cancelled) {
    setVideoUrl(null);
    setVideoError(appErrorMessage(e));
  }
}
```

import が既に上部にあれば追加不要。

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- PreviewScreen.test.tsx
```

期待: 新 test PASS + 既存 test 全て regression なく PASS

- [ ] **Step 5: lint / typecheck clean 確認**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: コミット**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.test.tsx
git commit -F - <<'EOF'
refactor(gui): #678 PreviewScreen register_video catch を appErrorMessage(e) に置き換え (Lane II-b §2.1)

[object Object] 表示の解消、Refs #678
EOF
```

### Task 1.3: §2.1 ConfirmExitModal save + discard catch を `appErrorMessage(e)` + `appErrorHint(e)` に置き換える

**Files:**

- Modify: `gui/src/components/ConfirmExitModal.tsx:25-68` (catch sites 2 か所 + hint state)
- Modify: `gui/src/components/ConfirmExitModal.module.css` (hint style 追加)
- Test: `gui/src/components/ConfirmExitModal.test.tsx`

**重要**: spec §2.1 規約「modal 内表示で hint 行追加 (#663 の他 modal 整合)」に従い hint UI を追加する。

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/components/ConfirmExitModal.test.tsx` に以下を追加:

```ts
describe('ConfirmExitModal catch (#678)', () => {
  it('renders AppError struct message + hint on probe failure', async () => {
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'is_process_running') {
        throw { code: 'internal.error', message: 'probe 失敗', hint: '再試行してください' };
      }
      return undefined;
    });
    render(<ConfirmExitModal />);
    // emit close-requested event
    window.dispatchEvent(new CustomEvent('close-requested'));
    await waitFor(() => {
      expect(screen.getByText('probe 失敗')).toBeInTheDocument();
      expect(screen.getByText(/再試行してください/)).toBeInTheDocument();
    });
  });

  it('renders message only when AppError has no hint', async () => {
    // ... similar but no hint field, assert hint テキストが表示されない
  });

  it('renders AppError struct message + hint on kill failure', async () => {
    // discard 経路 (line 66) の test
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- ConfirmExitModal.test.tsx -t '#678'
```

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/components/ConfirmExitModal.tsx` を以下に変更:

1. import 追加:

   ```ts
   import { appErrorHint, appErrorMessage } from '../lib/appError';
   ```

2. `errorHint` state を追加 (line 27 周辺):

   ```ts
   const [error, setError] = useState<string | null>(null);
   const [errorHint, setErrorHint] = useState<string | null>(null);
   ```

3. `handleCloseRequested` catch (line 41) を変更:

   ```ts
   } catch (e) {
     setError(appErrorMessage(e));
     setErrorHint(appErrorHint(e));
     setPending(true);
   }
   ```

4. `handleKillAndExit` catch (line 66) も同様:

   ```ts
   } catch (e) {
     setBusy(false);
     setError(appErrorMessage(e));
     setErrorHint(appErrorHint(e));
   }
   ```

5. `handleCancel` の `setError(null)` の隣に `setErrorHint(null)` を追加 (line 72)

6. UI 表示部分 (line 96-100 周辺) を 2 行表示に変更:

   ```tsx
   {error && (
     <p className={styles.message} role="alert">
       <span>{error}</span>
       {errorHint && (
         <span className={styles.errorHint}>💡 {errorHint}</span>
       )}
     </p>
   )}
   ```

7. `gui/src/components/ConfirmExitModal.module.css` に `.errorHint` を追加 (`display: block` / `font-size: 0.9em` / `opacity: 0.85` 程度):

   ```css
   .errorHint {
     display: block;
     font-size: 0.9em;
     opacity: 0.85;
     margin-top: 0.25rem;
   }
   ```

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- ConfirmExitModal.test.tsx
```

- [ ] **Step 5: lint / typecheck clean 確認**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: コミット**

```bash
git add gui/src/components/ConfirmExitModal.tsx gui/src/components/ConfirmExitModal.test.tsx gui/src/components/ConfirmExitModal.module.css
git commit -F - <<'EOF'
refactor(gui): #678 ConfirmExitModal save/discard catch を appErrorMessage(e) + appErrorHint(e) に置き換え (Lane II-b §2.1)

[object Object] 表示の解消 + hint 行追加 (#663 modal 整合)、Refs #678
EOF
```

### Task 1.4: PR 1 Self-Test + 実機検証依頼 + push + PR 作成

- [ ] **Step 1: 全 GUI 自動チェック (Self-Test Report の machine-verified)**

```bash
cd gui
npm run lint           # 0 errors
npm run typecheck      # 0 errors
npm test               # all PASS (新 Task 1.1-1.3 test 含む)
npm run build          # bundle 生成
cd ..
```

各コマンド出力を残し、PR 本文に貼り付ける用に control。

- [ ] **Step 2: spec / plan file の commit (PR 1 でまとめて入れる)**

```bash
# spec は既に commit 済 (2c2e695)、plan のみ追加
git add docs/superpowers/plans/2026-05-11-l2-lane-ii-b-group-d-696.md
git commit -F - <<'EOF'
docs: L2 Lane II-b plan (#678 → #669 → #680 → #696、4 PR 直列)

spec docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md (commit 2c2e695) に対する詳細実装計画。

Refs #678 #669 #680 #696
EOF
```

- [ ] **Step 3: Pre-flight 再実行 (push 直前、Iron Law 6)**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline  # 取り込み未済確認
gh pr list --search "#678 in:title,body" --state all  # 並行 PR 確認
```

取り込み未済が touched files と交差していれば `git merge origin/develop-0.2.0` + 自動チェック再実行。

- [ ] **Step 4: 実機検証 (Idios 依頼、AskUserQuestion で問い合わせ)**

AskUserQuestion で以下を問う:

- 質問: 「PR 1 (#678) の実機検証を依頼します。ローカルで `cd gui && npm run tauri dev` を起動し、(a) Export 画面で存在しない出力先を選択して `フォルダを開く` → エラー表示が日本語 message (+ hint 行) になっているか、(b) Preview 画面で破損動画を選択 → エラー表示が日本語 message になっているか、を確認してください。`[object Object]` が出ていなければ OK」
- 選択肢: `PASS (全 site で日本語表示確認)` / `PASS (一部 site のみ確認、他は次回)` / `FAIL (詳細をコメント)` / `スキップ (mock test 結果で承認)`
- Recommended: `PASS (全 site で日本語表示確認)`

検証結果は PR 本文の machine-unverifiable section に記録。`FAIL` の場合は実装に戻る。

- [ ] **Step 5: push + PR 作成**

```bash
git push -u origin claude/youthful-thompson-abbfd6
```

PR 作成 (PR 本文は `gh pr create` 引数で `--body-file` を使う。HEREDOC 注意 — memory `feedback_gh_command_ja_heredoc.md` 準拠で `printf | --body-file -` 推奨):

```bash
cat > /tmp/pr1-body.md <<'EOF'
## 概要

ExportScreen / PreviewScreen / ConfirmExitModal の残 4 site で `String(e)` を `appErrorMessage(e)` (+ 一部 site は `appErrorHint(e)`) に置き換え、AppError struct reject 時の `[object Object]` 表示を解消する。Refs #678 (Lane II-b §2.1)。

## 受け入れ条件と実装の対応 (Iron Law 1)

> - [x] `gui/src/utils/formatTauriError.ts` (or 同等) を新設し、`AppError` struct を読みやすい文字列に変換する helper を実装

→ **解釈変更**: `appErrorMessage` (`gui/src/lib/appError.ts`、#663 で実装済) を **既存 helper として使用**。spec §1.4 #2 で「DRY 違反回避」の判断を確定済。issue 本文の「新設」記述は post-#663 状態を反映していない (本 PR で is/解釈差分を解消)。

> - [x] 全画面の `invoke` catch block (Drop / Detecting / Preview / Complete / Export 各画面) で helper を適用

→ grep で確認した残 4 site (ExportScreen handleOpenFolder / PreviewScreen register_video / ConfirmExitModal ×2) に適用。Drop / Detecting / Complete は #663 で migration 済 (既に `appErrorMessage` 経由)。本 PR で 4 site を migrate。

> - [x] unit test: `AppError` struct / `Error` instance / 文字列 / null / undefined / 空 object の各ケースで期待通りの文字列を返す

→ Task 1.1 / 1.2 / 1.3 で各 component の vitest に 5 ケースを追加。

> - [x] export_match 失敗の e2e 再現確認 (sample 動画で意図的に失敗させる、もしくは Rust 側 mock invoke で AppError を return)

→ Task 1.4 Step 4 の実機検証で `フォルダを開く` を不存在 path で失敗させ、日本語 message + hint が表示されることを確認 (Idios 実機検証で実証)。

> - [x] 既存の各画面 vitest テスト更新 (error 表示の assertion を新フォーマットに合わせる)

→ Task 1.1 / 1.2 / 1.3 で既存 test の assertion を新フォーマット (`appErrorMessage` 経路) に更新。

## Self-Test Report

### Machine-verified

- [x] `cd gui && npm run lint` — 0 errors
- [x] `cd gui && npm run typecheck` — 0 errors
- [x] `cd gui && npm test` — N tests passed (+9 new)
- [x] `cd gui && npm run build` — bundle 生成

### Machine-unverifiable

- 実機 Tauri 起動 (Idios): handleOpenFolder / register_video の AppError 表示確認 (本文 §「実機検証結果」 参照)

## 実機検証結果

(Idios の AskUserQuestion 回答を貼り付け)

## 関連

Refs #678
spec: `docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md` §2.1
plan: `docs/superpowers/plans/2026-05-11-l2-lane-ii-b-group-d-696.md` §PR 1

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF

gh pr create --base develop-0.2.0 --head claude/youthful-thompson-abbfd6 --title "refactor(gui): #678 残 4 site の String(e) を appErrorMessage(e) に置き換え (Lane II-b §2.1)" --body-file /tmp/pr1-body.md
rm /tmp/pr1-body.md
```

- [ ] **Step 6: review iteration (別 skill `/iterate-review` に handoff)**

PR 作成後は `/iterate-review <PR#>` で review-fix ループを自走させる。Lane II-b §2.1 PR の review fix は本 plan の範囲外。

- [ ] **Step 7: マージ後 `/close-issue` skill で #678 を手動 close**

Iron Law 4 厳守 (auto-close keyword 禁止、手動 close)。

---

## PR 2: §2.2 #669 — `issueReportUrl` builder + `formatSystemInfo` + ErrorModal link + `read_error_log_tail` Tauri command

### PR 2 の元 issue 受け入れ条件 ([#669](https://github.com/Idios/kobutachan-allaganeye/issues/669) より引用)

> - [ ] ErrorModal の「Issue で報告」リンクが `bug_report.yml` テンプレ URL に query string で `description` / `system_info` / `crash_log_excerpt` を pre-fill
> - [ ] `description`: ErrorModal が握っている短い要約 (例: panic message 1 行 / Tauri command 名)
> - [ ] `system_info`: OS / アプリ version / GPU vendor / ffmpeg version など (`metadata.json` の `system_info` を再利用)
> - [ ] `crash_log_excerpt`: `logs/error-YYYYMMDD.log` の末尾 300 行に切り詰め
> - [ ] URL 長制限 (GitHub form pre-fill は 8KB 程度が安全圏) を超える場合は `crash_log_excerpt` を更に切り詰めて警告メッセージを末尾に追加
> - [ ] `#458` (同意チェック) 着手時に同意必須フィールドが追加されるため、本機能の query string も再調整するメモ
> - [ ] `docs/ui-architecture.md` §4 エラーハンドリング を更新

**brainstorming 決定** (spec §1.4 #3): field id は Group G PR #688 凍結済 `actual` / `environment` / `log_file_attachment` を使う (issue 本文の `description` / `system_info` / `crash_log_excerpt` は mapping 名)。PR 本文で mapping 表を明示。

### Task 2.1: §2.2 新規 Tauri command `read_error_log_tail` (Rust 側、TDD)

**Files:**

- Modify: `gui/src-tauri/src/lib.rs` (新 command 関数追加 + `invoke_handler` 登録)
- Modify: `gui/src-tauri/src/lib.rs` (`#[cfg(test)]` 内に cargo test を追加)

- [ ] **Step 1: failing cargo test を書く (Red)**

`gui/src-tauri/src/lib.rs` の `#[cfg(test)] mod tests { ... }` ブロックに以下を追加:

```rust
#[test]
fn read_error_log_tail_returns_last_n_lines() {
    use std::io::Write;
    use tempfile::TempDir;

    let tmp = TempDir::new().expect("tempdir");
    let log_dir = tmp.path().join("logs");
    std::fs::create_dir_all(&log_dir).unwrap();
    let date = chrono::Local::now().format("%Y%m%d").to_string();
    let log_path = log_dir.join(format!("error-{}.log", date));
    {
        let mut f = std::fs::File::create(&log_path).unwrap();
        for i in 0..500 {
            writeln!(f, "line {}", i).unwrap();
        }
    }
    // Inject log_dir via env or test helper (depending on implementation)
    // expectation: last 300 lines are returned (lines 200-499)
    let result = read_error_log_tail_inner(&log_dir, 300).unwrap();
    let lines: Vec<&str> = result.lines().collect();
    assert_eq!(lines.len(), 300);
    assert_eq!(lines[0], "line 200");
    assert_eq!(lines[299], "line 499");
}

#[test]
fn read_error_log_tail_falls_back_to_previous_day() {
    use std::io::Write;
    use tempfile::TempDir;

    let tmp = TempDir::new().expect("tempdir");
    let log_dir = tmp.path().join("logs");
    std::fs::create_dir_all(&log_dir).unwrap();
    let yesterday = (chrono::Local::now() - chrono::Duration::days(1))
        .format("%Y%m%d")
        .to_string();
    let log_path = log_dir.join(format!("error-{}.log", yesterday));
    {
        let mut f = std::fs::File::create(&log_path).unwrap();
        writeln!(f, "yesterday line").unwrap();
    }
    // 当日 log は存在しない → 前日 log にフォールバック
    let result = read_error_log_tail_inner(&log_dir, 300).unwrap();
    assert!(result.contains("yesterday line"));
}

#[test]
fn read_error_log_tail_returns_empty_for_missing_log() {
    use tempfile::TempDir;
    let tmp = TempDir::new().expect("tempdir");
    let log_dir = tmp.path().join("logs");
    std::fs::create_dir_all(&log_dir).unwrap();
    // 当日も前日も無し → 空文字列 (エラーでなく) を返す
    let result = read_error_log_tail_inner(&log_dir, 300).unwrap();
    assert_eq!(result, "");
}

#[test]
fn read_error_log_tail_returns_io_read_failed_on_permission_denied() {
    // Windows 上では permission_denied の simulate は難しいので
    // 代わりに log_dir 自体が file (dir でない) ケースで io.read_failed 系を返すか
    // または skip
    // 実装内で std::io::Error が出る場合の AppError code = io.read_failed (with_default_hint)
    // を assert
}
```

`tempfile` crate を `[dev-dependencies]` に追加。`chrono` は既存依存 (確認: `gui/src-tauri/Cargo.toml` で existing なら no-op)。

- [ ] **Step 2: cargo test を実行して FAIL 確認 (compile error 含む、Red 確定)**

```bash
cd gui/src-tauri && cargo test read_error_log_tail
```

期待: compile error (`read_error_log_tail_inner` 未定義)

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src-tauri/src/lib.rs` の `get_log_dir` (line 2675) の **直後** に以下を追加:

```rust
/// #669 -- Returns the tail of the install-dir log file (`<install_dir>/logs/error-YYYYMMDD.log`).
/// Falls back to previous day's log if today's is missing or empty.
/// Returns "" when neither today nor yesterday has a log (not an error).
/// Used by the frontend ErrorModal to pre-fill the bug_report.yml
/// `log_file_attachment` field.
#[tauri::command]
fn read_error_log_tail(line_count: usize) -> Result<String, AppError> {
    let log_dir = logging::log_dir().map_err(|e| {
        AppError::new(
            "path.install_dir_unresolved",
            format!("could not resolve log dir: {}", e),
        )
        .with_default_hint()
    })?;
    read_error_log_tail_inner(&log_dir, line_count)
}

/// Pure inner function for unit testing without log_dir() side effects.
fn read_error_log_tail_inner(log_dir: &std::path::Path, line_count: usize) -> Result<String, AppError> {
    use std::collections::VecDeque;
    use std::io::{BufRead, BufReader};

    let today = chrono::Local::now().format("%Y%m%d").to_string();
    let yesterday = (chrono::Local::now() - chrono::Duration::days(1))
        .format("%Y%m%d")
        .to_string();

    for date in &[today, yesterday] {
        let path = log_dir.join(format!("error-{}.log", date));
        if !path.exists() {
            continue;
        }
        let file = std::fs::File::open(&path).map_err(|e| {
            AppError::new("io.read_failed", format!("read log failed: {}", e))
                .with_default_hint()
        })?;
        let reader = BufReader::new(file);
        let mut tail: VecDeque<String> = VecDeque::with_capacity(line_count);
        for line in reader.lines() {
            let line = line.map_err(|e| {
                AppError::new("io.read_failed", format!("read line failed: {}", e))
                    .with_default_hint()
            })?;
            if tail.len() == line_count {
                tail.pop_front();
            }
            tail.push_back(line);
        }
        if !tail.is_empty() {
            let joined: Vec<String> = tail.into_iter().collect();
            return Ok(joined.join("\n"));
        }
        // empty file → try next date
    }
    Ok(String::new())
}
```

加えて `invoke_handler` 登録 (line 2800 周辺 + line 2826 周辺、2 か所):

```rust
tauri::generate_handler![
    // ... 既存 commands
    read_error_log_tail,
    // ...
]
```

- [ ] **Step 4: cargo test を実行して PASS 確認**

```bash
cd gui/src-tauri && cargo test read_error_log_tail
```

期待: 全 test PASS

- [ ] **Step 5: cargo check 全体を実行 (regression なし確認)**

```bash
cd gui/src-tauri && cargo check
```

期待: 0 errors

- [ ] **Step 6: コミット**

```bash
git add gui/src-tauri/src/lib.rs gui/src-tauri/Cargo.toml
git commit -F - <<'EOF'
feat(gui-tauri): #669 read_error_log_tail Tauri command 新設 (Lane II-b §2.2)

<install_dir>/logs/error-YYYYMMDD.log 末尾 N 行を返す。
当日 log 不存在 / 空なら前日 log へ fallback (1 日のみ)。
両方無しなら空文字列を返す (エラーでない)。

ErrorModal の bug_report URL pre-fill (#669) で
log_file_attachment field の元になる。

Refs #669
EOF
```

### Task 2.2: §2.2 `formatSystemInfo()` helper (TypeScript 側、TDD)

**Files:**

- Create: `gui/src/lib/systemInfo.ts`
- Create: `gui/src/lib/systemInfo.test.ts`

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/lib/systemInfo.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { formatSystemInfo } from './systemInfo';
import type { SystemInfo } from '../types/metadata.generated';

describe('formatSystemInfo (#669)', () => {
  const full: SystemInfo = {
    allaganeye_version: '0.2.0',
    ffmpeg_version: '8.1',
    python_version: '3.12.10',
    os_name: 'Windows 11',
    cpu_info: 'AMD Ryzen 9 9950X3D (16C/32T)',
    gpu_info: ['NVIDIA GeForce RTX 5090 (32GB VRAM)'],
    memory_total_gb: 61.6,
    disk_free_gb: 1359.5,
    disk_total_gb: 3726.0,
    disk_drive: 'E:',
    gpu_vendors_available: ['nvidia'],
    vendor_preference: ['nvidia', 'amd', 'intel'],
  };

  it('renders complete system_info in bug_report.yml placeholder format', () => {
    const out = formatSystemInfo(full);
    expect(out).toContain('allaganeye 0.2.0');
    expect(out).toContain('ffmpeg 8.1');
    expect(out).toContain('Windows 11');
    expect(out).toContain('CPU: AMD Ryzen 9 9950X3D');
    expect(out).toContain('GPU: NVIDIA GeForce RTX 5090');
    expect(out).toContain('Memory: 61.6 GB');
    expect(out).toContain('Disk: 1359.5 / 3726.0 GB free on E:');
  });

  it('handles missing GPU info', () => {
    const noGpu = { ...full, gpu_info: [] };
    const out = formatSystemInfo(noGpu);
    expect(out).toContain('GPU: (none detected)');
  });

  it('handles missing optional fields', () => {
    const partial: Partial<SystemInfo> = {
      allaganeye_version: '0.2.0',
      os_name: 'Windows 11',
    };
    const out = formatSystemInfo(partial as SystemInfo);
    expect(out).toContain('allaganeye 0.2.0');
    expect(out).toContain('Windows 11');
    // 欠落フィールドは空 line にせず "(unknown)" などで表示
  });

  it('returns "(no system_info)" for null input', () => {
    expect(formatSystemInfo(null)).toBe('(no system_info)');
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- systemInfo.test.ts
```

期待: compile error (`formatSystemInfo` 未定義)

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/lib/systemInfo.ts`:

```ts
import type { SystemInfo } from '../types/metadata.generated';

/**
 * #669 — Renders metadata.system_info into the bug_report.yml `environment`
 * placeholder format. Mirrors the formatting in `.github/ISSUE_TEMPLATE/bug_report.yml`
 * environment placeholder so external reporters get a familiar layout.
 */
export function formatSystemInfo(info: SystemInfo | null | undefined): string {
  if (!info) return '(no system_info)';

  const lines: string[] = [];
  const allaganeye = info.allaganeye_version ?? '(unknown version)';
  const ffmpeg = info.ffmpeg_version ?? '(unknown)';
  const python = info.python_version ?? '(unknown)';
  const os = info.os_name ?? '(unknown OS)';
  lines.push(`allaganeye ${allaganeye} (ffmpeg ${ffmpeg}, Python ${python}, ${os})`);

  const cpu = info.cpu_info ?? '(unknown)';
  lines.push(`  CPU: ${cpu}`);

  const gpu = info.gpu_info && info.gpu_info.length > 0
    ? info.gpu_info.join(', ')
    : '(none detected)';
  lines.push(`  GPU: ${gpu}`);

  if (info.memory_total_gb !== undefined && info.memory_total_gb !== null) {
    lines.push(`  Memory: ${info.memory_total_gb.toFixed(1)} GB`);
  }
  if (
    info.disk_free_gb !== undefined &&
    info.disk_free_gb !== null &&
    info.disk_total_gb !== undefined &&
    info.disk_total_gb !== null &&
    info.disk_drive
  ) {
    lines.push(
      `  Disk: ${info.disk_free_gb.toFixed(1)} / ${info.disk_total_gb.toFixed(1)} GB free on ${info.disk_drive}`,
    );
  }

  return lines.join('\n');
}
```

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- systemInfo.test.ts
```

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: コミット**

```bash
git add gui/src/lib/systemInfo.ts gui/src/lib/systemInfo.test.ts
git commit -F - <<'EOF'
feat(gui): #669 formatSystemInfo helper 新設 (Lane II-b §2.2)

metadata.system_info を bug_report.yml の environment placeholder
形式で render する純粋関数。GPU 不在 / 部分欠落 / null をハンドル。

Refs #669
EOF
```

### Task 2.3: §2.2 `buildIssueReportUrl` builder (TypeScript 側、TDD)

**Files:**

- Create: `gui/src/lib/issueReportUrl.ts`
- Create: `gui/src/lib/issueReportUrl.test.ts`

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/lib/issueReportUrl.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { buildIssueReportUrl, truncateLogToBudget } from './issueReportUrl';

const BASE = 'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';

describe('buildIssueReportUrl (#669)', () => {
  it('builds URL with actual + environment + log_file_attachment query params', () => {
    const url = buildIssueReportUrl({
      actual: 'panic: divide by zero',
      environment: 'allaganeye 0.2.0',
      logExcerpt: 'line 1\nline 2',
      logPath: 'C:\\logs\\error-20260511.log',
    });
    expect(url).toContain('template=bug_report.yml');
    expect(url).toContain('actual=');
    expect(url).toContain('environment=');
    expect(url).toContain('log_file_attachment=');
    // URLSearchParams で encode された値が含まれる
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('actual')).toBe('panic: divide by zero');
    expect(params.get('environment')).toBe('allaganeye 0.2.0');
    expect(params.get('log_file_attachment')).toBe('line 1\nline 2');
  });

  it('truncates log when total URL exceeds 8KB budget', () => {
    const bigLog = Array.from({ length: 1000 }, (_, i) => `line ${i}`.repeat(50)).join('\n');
    const url = buildIssueReportUrl({
      actual: 'panic',
      environment: 'env info',
      logExcerpt: bigLog,
      logPath: 'C:\\logs\\error-20260511.log',
    });
    expect(url.length).toBeLessThanOrEqual(7800 + BASE.length);
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('log_file_attachment')).toContain('ログが切り詰められました');
    expect(params.get('log_file_attachment')).toContain('C:\\logs\\error-20260511.log');
  });

  it('falls through 4 truncation steps before dropping log_file_attachment', () => {
    // very large actual + environment leaving < 50 lines budget
    const bigActual = 'a'.repeat(1800);
    const bigEnv = 'b'.repeat(1800);
    const bigLog = Array.from({ length: 400 }, (_, i) => `line ${i}`).join('\n');
    const url = buildIssueReportUrl({
      actual: bigActual,
      environment: bigEnv,
      logExcerpt: bigLog,
      logPath: 'C:\\logs\\error-20260511.log',
    });
    expect(url.length).toBeLessThanOrEqual(7800 + BASE.length);
    // log_file_attachment は 0 行に削減され、warning notice のみ
    const params = new URLSearchParams(url.split('?')[1]);
    const log = params.get('log_file_attachment') ?? '';
    // 50 行未満まで削減で notice 付き、それでも超過なら完全 drop で undefined
  });

  it('encodes CJK characters correctly', () => {
    const url = buildIssueReportUrl({
      actual: 'エラーが発生しました',
      environment: '環境情報',
      logExcerpt: 'ログ内容',
      logPath: 'C:\\ログ\\error.log',
    });
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('actual')).toBe('エラーが発生しました');
    expect(params.get('environment')).toBe('環境情報');
  });

  it('handles empty logExcerpt gracefully (no truncation notice)', () => {
    const url = buildIssueReportUrl({
      actual: 'panic',
      environment: 'env',
      logExcerpt: '',
      logPath: 'C:\\logs\\error.log',
    });
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('log_file_attachment') ?? '').not.toContain('ログが切り詰められました');
  });
});

describe('truncateLogToBudget (#669)', () => {
  it('returns log unchanged when within budget', () => {
    const log = 'line 1\nline 2';
    expect(truncateLogToBudget(log, 1000, 'C:\\logs\\error.log').text).toBe(log);
    expect(truncateLogToBudget(log, 1000, 'C:\\logs\\error.log').truncated).toBe(false);
  });

  it('reduces lines through steps 300→150→75→50→0', () => {
    const lines = Array.from({ length: 500 }, (_, i) => `line ${i}`);
    const log = lines.join('\n');
    // budget tight enough to force 150 lines
    const result = truncateLogToBudget(log, 1500, 'C:\\logs\\error.log');
    expect(result.text.split('\n').filter(l => l.startsWith('line')).length).toBeLessThanOrEqual(150);
    expect(result.truncated).toBe(true);
    expect(result.text).toContain('ログが切り詰められました');
  });

  it('drops log entirely when even 0-line notice exceeds budget', () => {
    const log = 'very long content...';
    // budget impossibly tight
    const result = truncateLogToBudget(log, 10, 'C:\\logs\\error.log');
    expect(result.text).toBe('');
    expect(result.dropped).toBe(true);
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- issueReportUrl.test.ts
```

期待: compile error (`buildIssueReportUrl` / `truncateLogToBudget` 未定義)

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/lib/issueReportUrl.ts`:

```ts
const BASE_URL = 'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';
const URL_BUDGET = 7800; // 8KB safe limit, with margin
const PER_FIELD_BUDGET = { actual: 2000, environment: 2000 };
const LOG_LINE_STEPS = [300, 150, 75, 50, 0];
const TRUNCATION_NOTICE = (logPath: string) =>
  `\n\n⚠️ ログが切り詰められました。完全なログは ${logPath} を参照してください。`;

export interface IssueReportInput {
  actual: string;
  environment: string;
  logExcerpt: string;
  logPath: string;
}

export interface TruncationResult {
  text: string;
  truncated: boolean;
  dropped: boolean;
}

/**
 * #669 — Truncate log content to fit within budget. Falls through line step
 * reductions (300→150→75→50→0). Returns dropped=true if even the 0-line
 * notice doesn't fit.
 */
export function truncateLogToBudget(
  log: string,
  budget: number,
  logPath: string,
): TruncationResult {
  const notice = TRUNCATION_NOTICE(logPath);
  // Try full log first
  if (encodeURIComponent(log).length <= budget) {
    return { text: log, truncated: false, dropped: false };
  }
  const lines = log.split('\n');
  for (const step of LOG_LINE_STEPS) {
    if (step === 0) {
      // 0 lines → notice only
      const noticeOnly = notice.trimStart();
      if (encodeURIComponent(noticeOnly).length <= budget) {
        return { text: noticeOnly, truncated: true, dropped: false };
      }
      // even notice doesn't fit
      return { text: '', truncated: true, dropped: true };
    }
    const truncated = lines.slice(-step).join('\n') + notice;
    if (encodeURIComponent(truncated).length <= budget) {
      return { text: truncated, truncated: true, dropped: false };
    }
  }
  return { text: '', truncated: true, dropped: true };
}

/**
 * #669 — Build the bug_report.yml pre-fill URL. Uses field id
 * `actual` / `environment` / `log_file_attachment` (frozen by Group G #688).
 * Truncates `log_file_attachment` if total URL exceeds 8KB safe limit.
 */
export function buildIssueReportUrl(input: IssueReportInput): string {
  const params = new URLSearchParams();
  // actual / environment はそれぞれ budget の上限まで切り詰める
  const actual =
    encodeURIComponent(input.actual).length > PER_FIELD_BUDGET.actual
      ? input.actual.slice(0, PER_FIELD_BUDGET.actual / 3) // pessimistic for CJK
      : input.actual;
  const environment =
    encodeURIComponent(input.environment).length > PER_FIELD_BUDGET.environment
      ? input.environment.slice(0, PER_FIELD_BUDGET.environment / 3)
      : input.environment;
  params.set('actual', actual);
  params.set('environment', environment);

  // log_file_attachment は残り budget で切り詰め
  const usedBudget = params.toString().length;
  const logBudget = URL_BUDGET - usedBudget - 'log_file_attachment='.length;
  const logResult = truncateLogToBudget(input.logExcerpt, Math.max(logBudget, 100), input.logPath);

  if (!logResult.dropped) {
    params.set('log_file_attachment', logResult.text);
  }

  return `${BASE_URL}&${params.toString()}`;
}
```

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- issueReportUrl.test.ts
```

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: コミット**

```bash
git add gui/src/lib/issueReportUrl.ts gui/src/lib/issueReportUrl.test.ts
git commit -F - <<'EOF'
feat(gui): #669 buildIssueReportUrl builder 新設 (Lane II-b §2.2)

bug_report.yml URL pre-fill helper。
actual / environment / log_file_attachment の 3 field を
8KB safe budget 内で組み立てる。
log_file_attachment は LOG_LINE_STEPS (300→150→75→50→0) で
段階削減し、切り詰め時は logPath への参照を notice で追加。

Refs #669
EOF
```

### Task 2.4: §2.2 ErrorModal の `Issue で報告` link を builder 経由に置き換え (vitest)

**Files:**

- Modify: `gui/src/components/ErrorModal.tsx` (useEffect で reportUrl 構築 + import 追加)
- Modify: `gui/src/components/ErrorModal.test.tsx`

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/components/ErrorModal.test.tsx` に以下を追加 (既存の `'Issue で報告する'` link 関連 test を新仕様に更新):

```ts
import { useErrorStore } from '../state/errorStore';
import { useMetadataStore } from '../state/metadataStore';

describe('ErrorModal Issue 報告 link (#669)', () => {
  beforeEach(() => {
    // mock invoke('read_error_log_tail')
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'read_error_log_tail') return 'last log line';
      if (cmd === 'get_log_dir') return 'C:\\install\\logs';
      return undefined;
    });
  });

  it('builds pre-fill URL with actual + environment + log_file_attachment when error opens', async () => {
    useMetadataStore.setState({
      metadata: {
        // ... metadata with system_info
        system_info: { allaganeye_version: '0.2.0', os_name: 'Windows 11' /* ... */ },
      } as any,
    });
    useErrorStore.getState().showError({
      errorMessage: 'panic: x',
      errorStack: 'stack trace here',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    const link = await screen.findByRole('link', { name: /Issue で報告/ });
    await waitFor(() => {
      expect(link.getAttribute('href')).toContain('actual=');
      expect(link.getAttribute('href')).toContain('environment=');
      expect(link.getAttribute('href')).toContain('log_file_attachment=');
      const url = new URL(link.getAttribute('href')!);
      const params = new URLSearchParams(url.search);
      expect(params.get('actual')).toContain('panic: x');
      expect(params.get('environment')).toContain('allaganeye 0.2.0');
      expect(params.get('log_file_attachment')).toContain('last log line');
    });
  });

  it('falls back to base URL when read_error_log_tail fails', async () => {
    vi.mocked(invoke).mockImplementation(async (cmd: string) => {
      if (cmd === 'read_error_log_tail') throw new Error('I/O');
      return undefined;
    });
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    const link = await screen.findByRole('link', { name: /Issue で報告/ });
    // base URL でも actual は pre-fill される (graceful fallback)
    expect(link.getAttribute('href')).toContain('template=bug_report.yml');
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- ErrorModal.test.tsx -t '#669'
```

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/components/ErrorModal.tsx` を変更:

1. 既存 const ISSUE_REPORT_URL を BASE_URL に降格 + import 追加:

   ```ts
   import { buildIssueReportUrl } from '../lib/issueReportUrl';
   import { formatSystemInfo } from '../lib/systemInfo';
   import { useMetadataStore } from '../state/metadataStore';
   import { useEffect } from 'react';

   const ISSUE_REPORT_BASE_URL =
     'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';
   ```

2. ErrorModal function 内に reportUrl state + useEffect 追加:

   ```tsx
   const [reportUrl, setReportUrl] = useState<string>(ISSUE_REPORT_BASE_URL);
   const metadata = useMetadataStore((s) => s.metadata);

   useEffect(() => {
     if (!errorOpen) return;
     const actual =
       (errorMessage ?? '') + (errorStack ? `\n\nStack:\n${errorStack}` : '');
     const environment = formatSystemInfo(metadata?.system_info ?? null);
     const logPathBase = logDir ? `${logDir}\\error-${todayDate()}.log` : '(unknown log path)';

     invoke<string>('read_error_log_tail', { lineCount: 300 })
       .then((logExcerpt) => {
         const url = buildIssueReportUrl({
           actual,
           environment,
           logExcerpt,
           logPath: logPathBase,
         });
         setReportUrl(url);
       })
       .catch(() => {
         // graceful fallback: actual + environment だけ pre-fill (log なし)
         const url = buildIssueReportUrl({
           actual,
           environment,
           logExcerpt: '',
           logPath: logPathBase,
         });
         setReportUrl(url);
       });
   }, [errorOpen, errorMessage, errorStack, metadata, logDir]);

   function todayDate(): string {
     return new Date().toISOString().slice(0, 10).replace(/-/g, '');
   }
   ```

3. link tag (line 119) の `href` を新 state に変更:

   ```tsx
   <a href={reportUrl} target="_blank" rel="noopener noreferrer">
     Issue で報告する
   </a>
   ```

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- ErrorModal.test.tsx
```

期待: 既存 ErrorModal test + 新 #669 test 全 PASS

- [ ] **Step 5: 全 vitest run (regression 検証)**

```bash
cd gui && npm test
```

- [ ] **Step 6: lint / typecheck / build**

```bash
cd gui && npm run lint && npm run typecheck && npm run build
```

- [ ] **Step 7: コミット**

```bash
git add gui/src/components/ErrorModal.tsx gui/src/components/ErrorModal.test.tsx
git commit -F - <<'EOF'
feat(gui): #669 ErrorModal の Issue 報告 link を pre-fill URL に差し替え (Lane II-b §2.2)

useEffect で errorOpen=true タイミングに:
- metadata.system_info から formatSystemInfo で environment 構築
- read_error_log_tail invoke で logs/error-*.log 末尾取得
- buildIssueReportUrl で 3 field 入り URL 構築
invoke 失敗 / metadata 無し は graceful fallback。

Refs #669
EOF
```

### Task 2.5: §2.2 docs/tauri-commands.md に `read_error_log_tail` を追記

**Files:**

- Modify: `docs/tauri-commands.md`

- [ ] **Step 1: 既存 doc 構造を確認**

```bash
head -50 docs/tauri-commands.md
grep -n '^##' docs/tauri-commands.md | head -20
```

既存 command の追記場所 (Tauri command 一覧表 / 個別 detail section) を確定。

- [ ] **Step 2: command 一覧表に行追加**

`read_error_log_tail` の行を `get_log_dir` の隣 (前後どちらでも構わない、既存 order に揃える) に追加:

```markdown
| `read_error_log_tail` | `line_count: usize` | `String` (空文字列含む) | (no event) | logs/error-YYYYMMDD.log 末尾 N 行。当日 log 不存在 → 前日 fallback (1 日のみ)。両日 missing → 空文字列。`io.read_failed` on I/O failure (#669) |
```

- [ ] **Step 3: 個別 detail section があれば section も追加**

`### read_error_log_tail` を追記:

```markdown
### `read_error_log_tail`

#### Signature

`fn read_error_log_tail(line_count: usize) -> Result<String, AppError>`

#### 用途

ErrorModal の Issue 報告 link (#669) で bug_report.yml の `log_file_attachment` field を pre-fill するため、`<install_dir>/logs/error-YYYYMMDD.log` の末尾 N 行を取得する。

#### Fallback 規則

- 当日 (YYYYMMDD) の log file が存在しない / 空 → 前日 log にフォールバック
- 前日 log も存在しない / 空 → 空文字列 (`""`) を返す (エラーでなく、ErrorModal 側で「log なし」として graceful 表示)

#### Error Codes

| code | 状況 |
| --- | --- |
| `path.install_dir_unresolved` | install dir が resolve できない (logging::log_dir() 失敗) |
| `io.read_failed` | log file の open / read が失敗 |
```

- [ ] **Step 4: markdownlint check**

```bash
bash scripts/check-markdownlint.sh
```

- [ ] **Step 5: コミット**

```bash
git add docs/tauri-commands.md
git commit -F - <<'EOF'
docs(tauri-commands): #669 read_error_log_tail 新 command を追記 (Lane II-b §2.2)

Refs #669
EOF
```

### Task 2.6: PR 2 Self-Test + 実機検証依頼 + push + PR 作成

- [ ] **Step 1: 全自動チェック (Self-Test machine-verified)**

```bash
cd gui && npm run lint && npm run typecheck && npm test && npm run build && cd ..
cd gui/src-tauri && cargo check && cargo test && cd ../..
```

- [ ] **Step 2: Pre-flight 再実行 + push**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#669 in:title,body" --state all
git push origin claude/youthful-thompson-abbfd6
```

- [ ] **Step 3: 実機検証 (Idios 依頼、AskUserQuestion で問い合わせ)**

AskUserQuestion で以下を問う:

- 質問: 「PR 2 (#669) の実機検証を依頼します。`cd gui && npm run tauri dev` で起動 → DevTools console で `await window.__aeInvoke('dev_force_panic')` を実行 → ErrorModal が出現 → `Issue で報告する` link クリック → GitHub の bug_report.yml form が開き、`actual` / `environment` / `log_file_attachment` の 3 field に内容が反映されていることを確認してください。長い log でも 8KB 制限内で表示され、切り詰め時は「ログが切り詰められました」notice が出ているか」
- 選択肢: `PASS (3 field 反映 + 切り詰め notice 確認)` / `PASS (3 field 反映、長 log は未確認)` / `FAIL (詳細をコメント)` / `スキップ (mock test のみで承認)`
- Recommended: `PASS (3 field 反映 + 切り詰め notice 確認)`

- [ ] **Step 4: PR 2 作成**

```bash
cat > /tmp/pr2-body.md <<'EOF'
## 概要

ErrorModal の「Issue で報告する」link を `bug_report.yml` の pre-fill URL に差し替え、外部 reporter の crash 報告コストを下げる。Refs #669 (Lane II-b §2.2)。

## 受け入れ条件と実装の対応 (Iron Law 1)

> - [x] ErrorModal の「Issue で報告」リンクが `bug_report.yml` テンプレ URL に query string で `description` / `system_info` / `crash_log_excerpt` を pre-fill

→ field id mapping (issue 本文 vs 実装): `description` → `actual` / `system_info` → `environment` / `crash_log_excerpt` → `log_file_attachment` (Group G PR #688 で凍結された field id を使用)。`gui/src/lib/issueReportUrl.ts` で 3 field を URLSearchParams 経由で構築。

> - [x] `description`: ErrorModal が握っている短い要約 (例: panic message 1 行 / Tauri command 名)

→ `errorMessage + (errorStack ? '\n\nStack:\n' + errorStack : '')` を `actual` field に。

> - [x] `system_info`: OS / アプリ version / GPU vendor / ffmpeg version など (`metadata.json` の `system_info` を再利用)

→ `gui/src/lib/systemInfo.ts` の `formatSystemInfo()` で `metadata.system_info` を bug_report.yml placeholder 形式に renders。`useMetadataStore` から読み込み。

> - [x] `crash_log_excerpt`: `logs/error-YYYYMMDD.log` の末尾 300 行に切り詰め

→ 新 Tauri command `read_error_log_tail(line_count: usize)` で `<install_dir>/logs/error-YYYYMMDD.log` 末尾 300 行を取得。当日 log 不存在 → 前日 log fallback (1 日)。両日 missing → 空文字列 graceful。

> - [x] URL 長制限 (GitHub form pre-fill は 8KB 程度が安全圏) を超える場合は `crash_log_excerpt` を更に切り詰めて警告メッセージを末尾に追加

→ `truncateLogToBudget()` で 7800 bytes safe budget 内に LOG_LINE_STEPS (300→150→75→50→0) で段階削減。切り詰め時は末尾に「ログが切り詰められました。完全なログは {logPath} を参照」追加。

> - [x] `#458` (同意チェック) 着手時に同意必須フィールドが追加されるため、本機能の query string も再調整するメモ

→ #458 着手時の調整メモを `docs/ui-architecture.md` §4 に明記 (本 PR で追記)。

> - [x] `docs/ui-architecture.md` §4 エラーハンドリング を更新

→ ErrorModal の Issue 報告 link が pre-fill URL を構築する旨と、`#458` 着手時の調整メモを追記 (本 PR で適用)。

## Self-Test Report

### Machine-verified

- [x] `cd gui && npm run lint` — 0 errors
- [x] `cd gui && npm run typecheck` — 0 errors
- [x] `cd gui && npm test` — N tests passed (+M new)
- [x] `cd gui && npm run build` — bundle 生成
- [x] `cd gui/src-tauri && cargo check` — 0 errors
- [x] `cd gui/src-tauri && cargo test` — N tests passed (+4 new)

### Machine-unverifiable

- 実機 Tauri 起動 (Idios): ErrorModal → Issue link クリック → GitHub form 3 field 反映確認

## 実機検証結果

(Idios の AskUserQuestion 回答を貼り付け)

## 関連

Refs #669
spec: `docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md` §2.2

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF

gh pr create --base develop-0.2.0 --head claude/youthful-thompson-abbfd6 --title "feat(gui): #669 ErrorModal の Issue 報告 link を bug_report.yml pre-fill URL に差し替え (Lane II-b §2.2)" --body-file /tmp/pr2-body.md
rm /tmp/pr2-body.md
```

- [ ] **Step 5: review iteration → マージ → `/close-issue` で #669 を手動 close**

---

## PR 3: §2.3 #680 — `deriveDefaultOutDir` 修正

### PR 3 の元 issue 受け入れ条件 ([#680](https://github.com/Idios/kobutachan-allaganeye/issues/680) より引用)

> - [ ] `deriveDefaultOutDir` が `<dirname>` のみ返すよう変更
> - [ ] 既存の `deriveDefaultOutDir` 単体テスト更新 (ケース: Windows / Unix / extended-length prefix `\?\` / sample mode null)
> - [ ] 既存の Export 一気通貫テスト (`flow.integration.test.tsx` 等) で default 値 assertion の更新
> - [ ] **実機ビルドで再現確認 (Idios)**: 報告画像の `E:\videos\2026-04-17_15-13-31_allaganeye` 形式が現行ビルドで再現するか確認 (Iron Law 6 trigger: GUI Tauri 起動 = mock 不可)
> - [ ] (再現する場合) 別 setOutDir 経路があれば deriveDefaultOutDir に統一する

**brainstorming 決定** (spec §1.4 #4): deriveDefaultOutDir 修正のみ実施、別経路発見時は別 issue (1 PR = 1 scope)。

### Task 3.1: §2.3 着手前の Pre-flight (Idios 実機再現確認)

- [ ] **Step 1: AskUserQuestion で再現確認依頼**

質問: 「PR 3 (#680) 着手前に、`develop-0.2.0` 最新ビルドの GUI で Export 画面の出力先 default 値を確認してください。報告画像の `E:\videos\..._allaganeye` 形式 (`<stem>_allaganeye`) が表示されますか? それともコード上の `<dirname>\output` 形式が表示されますか?」

選択肢:

- `<dirname>\output` 形式 (deriveDefaultOutDir のとおり) — Recommended の想定
- `<stem>_allaganeye` 形式 (報告画像のとおり、別 setOutDir 経路あり) → scope 拡大判断
- 両形式の混在 → 別経路あり、別 issue 起票

`<stem>_allaganeye` 形式が出る場合は、別 setOutDir 経路を grep 確認した上で本 PR を `deriveDefaultOutDir` 修正のみで進めるか、別 issue を起票してから本 PR を続けるかを再判断。

### Task 3.2: §2.3 `deriveDefaultOutDir` 修正 (TDD)

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx:948-959` (deriveDefaultOutDir 関数)
- Test: `gui/src/screens/ExportScreen.test.tsx` (deriveDefaultOutDir 関連 test 群)

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/screens/ExportScreen.test.tsx` の既存 deriveDefaultOutDir test を新仕様に更新:

```ts
describe('deriveDefaultOutDir (#680)', () => {
  it('returns Windows parent dir without /output suffix', () => {
    expect(deriveDefaultOutDir('E:\\videos\\rec.mkv')).toBe('E:\\videos');
  });

  it('returns Unix parent dir without /output suffix', () => {
    expect(deriveDefaultOutDir('/home/user/videos/rec.mp4')).toBe('/home/user/videos');
  });

  it('strips extended-length prefix then returns parent', () => {
    expect(deriveDefaultOutDir('\\\\?\\E:\\videos\\rec.mkv')).toBe('E:\\videos');
  });

  it('returns empty string for null videoSource (sample mode)', () => {
    expect(deriveDefaultOutDir(null)).toBe('');
  });

  it('returns empty string when no separator found', () => {
    expect(deriveDefaultOutDir('rec.mkv')).toBe('');
  });
});
```

加えて flow.integration.test.tsx の default 値 assertion (もし `'\\\\output'` で expect しているなら) を新仕様に更新:

```bash
grep -n 'output' gui/src/screens/flow.integration.test.tsx
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- -t '#680'
cd gui && npm test -- -t 'deriveDefaultOutDir'
```

期待: 新 assertion (`'E:\\videos'`) が現行 (`'E:\\videos\\output'`) で FAIL

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/screens/ExportScreen.tsx:948-959`:

```ts
/**
 * #466 review #2: source video の親ディレクトリを default に。
 * `videoSource` から `dirname` 相当を抽出する (Windows は `\\` も許容)。
 *
 * #545 review #2 (2026-04-25): Windows の `\\?\` extended-length path prefix
 * は `stripExtendedPathPrefix` で取り除いてから親 dir を切り出す。
 *
 * #680: 旧実装は `<parent>/output` を返していたが、存在しないフォルダが
 * デフォルトになる混乱の元になっていたため、親ディレクトリのみを返すよう
 * 変更。書き出し前にユーザーがフォルダピッカーで明示的に出力先を選ぶ運用。
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

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test
```

- [ ] **Step 5: lint / typecheck / build**

```bash
cd gui && npm run lint && npm run typecheck && npm run build
```

- [ ] **Step 6: コミット**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.test.tsx gui/src/screens/flow.integration.test.tsx
git commit -F - <<'EOF'
fix(gui): #680 deriveDefaultOutDir を <dirname>/output → <dirname> に変更 (Lane II-b §2.3)

存在しないフォルダがプリセットされる UX 不安を解消。

Refs #680
EOF
```

### Task 3.3: PR 3 Self-Test + 実機検証依頼 + push + PR 作成

- [ ] **Step 1: 全自動チェック**

```bash
cd gui && npm run lint && npm run typecheck && npm test && npm run build && cd ..
```

- [ ] **Step 2: Pre-flight + push**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#680 in:title,body" --state all
git push origin claude/youthful-thompson-abbfd6
```

- [ ] **Step 3: 実機検証 (Idios 依頼、AskUserQuestion)**

質問: 「PR 3 (#680) の実機検証を依頼します。`cd gui && npm run tauri dev` で起動 → 動画 drop → Detecting → Preview → Export 画面で **出力先 default が `<ソース動画の親ディレクトリ>` (= 存在するフォルダ)** であることを確認してください。`..._allaganeye` 形式が出る場合は別経路があるので別 issue 起票判断。」

選択肢:

- `PASS (<dirname> 表示確認)` (Recommended)
- `PASS (<dirname> 表示、ただし別経路 (_allaganeye 形式) も発見 → 別 issue 起票)`
- `FAIL (詳細をコメント)`
- `スキップ (mock test のみで承認)`

- [ ] **Step 4: PR 3 作成**

```bash
cat > /tmp/pr3-body.md <<'EOF'
## 概要

Export 画面の出力先 default 値を `<dirname>/output` (存在しないフォルダ) → `<dirname>` (ソース動画と同じ親ディレクトリ、存在保証) に変更する。Refs #680 (Lane II-b §2.3)。

## 受け入れ条件と実装の対応 (Iron Law 1)

> - [x] `deriveDefaultOutDir` が `<dirname>` のみ返すよう変更

→ `gui/src/screens/ExportScreen.tsx` の `deriveDefaultOutDir` の `return ${parent}${sep}output` を `return parent` に変更。

> - [x] 既存の `deriveDefaultOutDir` 単体テスト更新 (ケース: Windows / Unix / extended-length prefix `\?\` / sample mode null)

→ `ExportScreen.test.tsx` の deriveDefaultOutDir 関連 test を 5 ケース (Windows / Unix / extended-length / null / no separator) で新仕様に更新。

> - [x] 既存の Export 一気通貫テスト (`flow.integration.test.tsx` 等) で default 値 assertion の更新

→ flow integration test の `output` assertion を新仕様 `<dirname>` に更新。

> - [x] 実機ビルドで再現確認 (Idios)

→ Task 3.1 Step 1 (Pre-flight 実機再現確認) + Task 3.3 Step 3 (修正後実機確認) の 2 段で確認。

> - [x] (再現する場合) 別 setOutDir 経路があれば deriveDefaultOutDir に統一する

→ brainstorming で別経路発見時は別 issue 起票方針確定 (spec §1.4 #4)、本 PR ではスコープ外。Idios 実機検証で別経路発見の場合は本 PR とは別 issue で対応。

## Self-Test Report

### Machine-verified

- [x] `cd gui && npm run lint` — 0 errors
- [x] `cd gui && npm run typecheck` — 0 errors
- [x] `cd gui && npm test` — N tests passed (5 test cases updated)
- [x] `cd gui && npm run build` — bundle 生成

### Machine-unverifiable

- 実機 Tauri 起動 (Idios): 出力先 default が `<dirname>` (親ディレクトリ) であること確認

## 実機検証結果

(Idios の AskUserQuestion 回答を貼り付け)

## 関連

Refs #680
spec: `docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md` §2.3

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF

gh pr create --base develop-0.2.0 --head claude/youthful-thompson-abbfd6 --title "fix(gui): #680 Export 出力先 default を <dirname> に変更 (Lane II-b §2.3)" --body-file /tmp/pr3-body.md
rm /tmp/pr3-body.md
```

- [ ] **Step 5: review iteration → マージ → `/close-issue` で #680 を手動 close**

---

## PR 4: §2.4 #696 — globalErrorListener `isAppError` 分岐 + ErrorModal `'tauri-command'` display

### PR 4 の元 issue 受け入れ条件 ([#696](https://github.com/Idios/kobutachan-allaganeye/issues/696) より引用)

> - [ ] `globalErrorListener.ts` の `onUnhandledRejection` で `isAppError(e.reason)` を判定し、true なら `errorCategory: 'tauri-command'`, `errorTitle: '処理中に予期しないエラーが発生しました'`, `errorMessage: e.reason.message`, `errorHint: e.reason.hint ?? null` を errorStore.showError に流す
> - [ ] ErrorModal.tsx で `errorCategory === 'tauri-command'` の表示パターンを定義 (recoverable / Issue で報告 / コピー button 構成)
> - [ ] 既存 6 panic-related test に加え `'tauri-command'` errorCategory の test を追加
> - [ ] docs/ui-architecture.md §4 (#663 で追加した分岐ルール) に「catch 漏れ AppError は ErrorModal fallback」の旨を追記

**編集者註**: 上記引用は #696 原文の backtick balance (errorTitle 後 / `'tauri-command'` 前) を markdownlint 通過のため正規化。意味は完全保持。

### Task 4.1: §2.4 globalErrorListener に `isAppError` 分岐 (TDD)

**Files:**

- Modify: `gui/src/lib/globalErrorListener.ts:92-115` (onUnhandledRejection)
- Test: `gui/src/lib/globalErrorListener.test.ts`

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/lib/globalErrorListener.test.ts` に以下を追加:

```ts
describe('globalErrorListener onUnhandledRejection (#696)', () => {
  it('routes AppError struct reject to tauri-command category', async () => {
    installGlobalErrorListener();
    const appError = {
      code: 'io.read_failed',
      message: '読み込みに失敗',
      hint: 'ファイルを確認',
      stacktrace: 'stack here',
    };
    window.dispatchEvent(
      new PromiseRejectionEvent('unhandledrejection', {
        reason: appError,
        promise: Promise.reject(appError),
      }),
    );
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('tauri-command');
    expect(state.errorTitle).toBe('処理中に予期しないエラーが発生しました');
    expect(state.errorMessage).toBe('読み込みに失敗');
    expect(state.errorHint).toBe('ファイルを確認');
    expect(state.errorStack).toBe('stack here');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(true);
  });

  it('falls through to js-promise category for non-AppError reject (Error)', async () => {
    useErrorStore.getState().dismissError();
    installGlobalErrorListener();
    const err = new Error('plain error');
    window.dispatchEvent(
      new PromiseRejectionEvent('unhandledrejection', { reason: err, promise: Promise.reject(err) }),
    );
    expect(useErrorStore.getState().errorCategory).toBe('js-promise');
  });

  it('falls through to js-promise for string reject', async () => {
    useErrorStore.getState().dismissError();
    installGlobalErrorListener();
    window.dispatchEvent(
      new PromiseRejectionEvent('unhandledrejection', {
        reason: 'string reason',
        promise: Promise.reject('string reason'),
      }),
    );
    expect(useErrorStore.getState().errorCategory).toBe('js-promise');
  });

  it('falls through to js-promise for plain object without code/message shape', async () => {
    useErrorStore.getState().dismissError();
    installGlobalErrorListener();
    window.dispatchEvent(
      new PromiseRejectionEvent('unhandledrejection', {
        reason: { something: 'else' },
        promise: Promise.reject({ something: 'else' }),
      }),
    );
    expect(useErrorStore.getState().errorCategory).toBe('js-promise');
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- globalErrorListener.test.ts -t '#696'
```

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/lib/globalErrorListener.ts:92-115`:

```ts
import { isAppError } from './appError';

// ... installGlobalErrorListener function 内 ...

const onUnhandledRejection = (e: PromiseRejectionEvent) => {
  const reason = e.reason;
  // #696: AppError struct (Tauri command の reject value) は catch 漏れ
  // fallback として 'tauri-command' category で recoverable 表示する
  if (isAppError(reason)) {
    showError({
      errorTitle: '処理中に予期しないエラーが発生しました',
      errorMessage: reason.message,
      errorHint: reason.hint ?? null,
      errorStack: reason.stacktrace ?? null,
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    return;
  }
  // 既存 fallback (Error / string / object)
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

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- globalErrorListener.test.ts
```

- [ ] **Step 5: コミット**

```bash
git add gui/src/lib/globalErrorListener.ts gui/src/lib/globalErrorListener.test.ts
git commit -F - <<'EOF'
feat(gui): #696 globalErrorListener.onUnhandledRejection に isAppError 分岐 (Lane II-b §2.4)

catch 漏れ AppError struct を 'tauri-command' errorCategory で
ErrorModal fallback 表示する。既存 Error / string / object fallback
は維持。

Refs #696
EOF
```

### Task 4.2: §2.4 ErrorModal default title に `'tauri-command'` を追加 (TDD)

**Files:**

- Modify: `gui/src/components/ErrorModal.tsx:51-60` (default title 分岐)
- Test: `gui/src/components/ErrorModal.test.tsx`

- [ ] **Step 1: failing test を書く (Red)**

`gui/src/components/ErrorModal.test.tsx` に以下を追加:

```ts
describe("ErrorModal 'tauri-command' category (#696)", () => {
  it('shows default title 「処理中に予期しないエラーが発生しました」', () => {
    useErrorStore.getState().showError({
      errorMessage: '読み込みに失敗',
      errorHint: 'ファイルを確認',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(
      screen.getByRole('heading', { name: '処理中に予期しないエラーが発生しました' }),
    ).toBeInTheDocument();
  });

  it('shows 閉じる button (recoverable=true)', () => {
    useErrorStore.getState().showError({
      errorMessage: 'x',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByRole('button', { name: '閉じる' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'アプリを終了' })).not.toBeInTheDocument();
  });

  it('shows hint when AppError has hint', () => {
    useErrorStore.getState().showError({
      errorMessage: 'x',
      errorHint: 'やってみてください',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByText('やってみてください')).toBeInTheDocument();
  });

  it('passes jest-axe a11y check', async () => {
    useErrorStore.getState().showError({
      errorMessage: 'x',
      errorCategory: 'tauri-command',
      isPanic: false,
      isRecoverable: true,
    });
    const { container } = render(<ErrorModal />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("'tauri-command' override does not regress existing 'panic' default title", () => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().showError({
      errorMessage: 'panic msg',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    expect(
      screen.getByRole('heading', { name: 'アプリ内部でエラーが発生しました' }),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: test を実行して FAIL 確認**

```bash
cd gui && npm test -- ErrorModal.test.tsx -t '#696'
```

- [ ] **Step 3: minimum 実装 (Green)**

`gui/src/components/ErrorModal.tsx:51-60`:

```ts
// #614 / #668: per-category default titles. errorTitle override always wins.
let defaultTitle: string;
if (errorCategory === 'integrity') {
  defaultTitle = '同梱物の検証に失敗しました';
} else if (errorCategory === 'tauri-command') {
  // #696: catch 漏れ AppError fallback を user-facing で「ユーザー操作中の error」
  // として表現する (panic / integrity と区別)。
  defaultTitle = '処理中に予期しないエラーが発生しました';
} else if (isPanic) {
  defaultTitle = 'アプリ内部でエラーが発生しました';
} else {
  defaultTitle = '予期しないエラーが発生しました';
}
const title = errorTitle || defaultTitle;
```

- [ ] **Step 4: test を実行して PASS 確認**

```bash
cd gui && npm test -- ErrorModal.test.tsx
```

期待: 既存 ErrorModal test 全 + 新 #696 test 全 PASS、regression なし

- [ ] **Step 5: コミット**

```bash
git add gui/src/components/ErrorModal.tsx gui/src/components/ErrorModal.test.tsx
git commit -F - <<'EOF'
feat(gui): #696 ErrorModal default title 分岐に 'tauri-command' を追加 (Lane II-b §2.4)

catch 漏れ AppError fallback (errorCategory='tauri-command') 表示時の
default title を「処理中に予期しないエラーが発生しました」に。

Refs #696
EOF
```

### Task 4.3: §2.4 docs/ui-architecture.md §4 更新 + docs/tauri-commands.md (debug-only command 追記)

**Files:**

- Modify: `docs/ui-architecture.md` (§4 エラーハンドリング)
- Modify: `docs/tauri-commands.md` (もし dev_force_unhandled_apperror を追加するなら)

- [ ] **Step 1: docs/ui-architecture.md §4 を読み、catch 漏れ AppError fallback 節を追記**

```bash
grep -n '^### \|^## ' docs/ui-architecture.md | head -30
```

§4 (エラーハンドリング) の **既存「ErrorModal による表示」「inline error / hint」分岐ルール (#663 追加)** の直後に以下を挿入:

```markdown
#### catch 漏れ AppError fallback (#696)

通常の Tauri command の `Result<T, AppError>` 失敗は呼び出し側 catch block で受け取り、画面別の inline error / hint で表示する。例外的に **catch されずに unhandled promise rejection になった AppError** は `globalErrorListener.onUnhandledRejection` の `isAppError` 分岐で検出され、`errorCategory: 'tauri-command'` で ErrorModal に fallback 表示される。

- 表示 default title: 「処理中に予期しないエラーが発生しました」
- `isRecoverable: true` (閉じるボタンで継続可)
- `isPanic: false` (アプリを終了 button は出ない)
- `errorHint` は `AppError.hint` をそのまま表示

ErrorModal の Issue 報告 link (#669) は本 fallback でも `actual` / `environment` / `log_file_attachment` を pre-fill する。
```

加えて #669 (Issue 報告 link pre-fill) 関連も同 §4 に追記:

```markdown
#### Issue 報告 link の自動 pre-fill (#669)

ErrorModal の `[Issue で報告する]` link は `bug_report.yml` の URL に query string で以下 3 field を pre-fill する:

- `actual`: ErrorModal の `errorMessage` + (`errorStack` があれば `\n\nStack:\n{stack}`)
- `environment`: `metadata.system_info` を `formatSystemInfo()` (`gui/src/lib/systemInfo.ts`) で renders
- `log_file_attachment`: 新 Tauri command `read_error_log_tail` で `logs/error-YYYYMMDD.log` 末尾 300 行を取得 (当日 log 不存在 → 前日 fallback)

URL 全長 8KB safe budget を超える場合は `log_file_attachment` を LOG_LINE_STEPS (300→150→75→50→0) で段階削減し、末尾に「ログが切り詰められました」notice を追加する。

**#458 (同意チェック新設) 着手時の調整メモ**: 本機能の URL builder は現状 `actual` / `environment` / `log_file_attachment` の 3 field のみ pre-fill。#458 で同意必須 field (`consent`) が yaml form に追加された場合、その field の pre-fill 要否を再評価し、必要なら URL builder にも追加する。
```

- [ ] **Step 2: markdownlint check**

```bash
bash scripts/check-markdownlint.sh
```

- [ ] **Step 3: コミット**

```bash
git add docs/ui-architecture.md
git commit -F - <<'EOF'
docs(ui-architecture): #669 + #696 §4 エラーハンドリングに 2 節追記 (Lane II-b §2.4)

- catch 漏れ AppError fallback ('tauri-command' errorCategory)
- Issue 報告 link の自動 pre-fill (3 field + 段階削減 + #458 調整メモ)

Refs #669 #696
EOF
```

### Task 4.4: (Optional) §2.4 dev_force_unhandled_apperror 開発用 command 追加

実機検証で catch 漏れ AppError を意図的に発生させるための debug-only Tauri command。判断点: PR 4 内で同梱するか、別 issue で対応するか。

**判断基準**: dev_force_panic と同様、debug builds only の最小 command。実機検証の手間を減らすなら本 PR で同梱。

- [ ] **Step 1: PR 内で同梱する判断 (AskUserQuestion で Idios に確認)**

質問: 「PR 4 (#696) に `dev_force_unhandled_apperror` debug-only Tauri command を同梱しますか? (実機検証で catch 漏れ AppError を意図的に発生させるための開発用 command、`dev_force_panic` の AppError 版)」

選択肢:

- `本 PR に同梱 (#696 scope 内、Idios 実機検証コスト最小化)` (Recommended)
- `別 issue で対応 (PR 4 を最小に保つ)` → 別 issue 起票 + 本 PR Skip
- `dev_force_panic で代用 (catch 漏れ AppError は別途 grep で発見)` → Skip

- [ ] **Step 2 (同梱判断時): 実装**

`gui/src-tauri/src/lib.rs` の `dev_force_panic` (line 2701) の直後に:

```rust
/// #696 -- Dev-only command that returns an AppError reject from an async
/// Tauri command. Used by the frontend smoke test to verify the
/// `onUnhandledRejection` -> ErrorModal fallback wiring without a real
/// catch site. Caller deliberately does not catch the rejected Promise,
/// so the AppError becomes an unhandled rejection.
///
/// Frontend usage in DevTools console:
///   `window.__aeInvoke('dev_force_unhandled_apperror')`  // no .catch
#[cfg(debug_assertions)]
#[tauri::command]
async fn dev_force_unhandled_apperror() -> Result<(), AppError> {
    Err(AppError::new(
        "internal.error",
        "dev_force_unhandled_apperror invoked",
    )
    .with_hint("これは開発用テスト errror です。catch 漏れ経路の動作確認のため。"))
}
```

`tauri::generate_handler![]` に登録。

- [ ] **Step 3: cargo check + cargo test**

```bash
cd gui/src-tauri && cargo check && cargo test
```

- [ ] **Step 4: コミット**

```bash
git add gui/src-tauri/src/lib.rs
git commit -F - <<'EOF'
feat(gui-tauri): #696 dev_force_unhandled_apperror debug-only command 追加 (Lane II-b §2.4)

実機検証で catch 漏れ AppError fallback ('tauri-command' errorCategory)
を意図的に発生させるための開発用 Tauri command。
release builds では symbol 不在。

Refs #696
EOF
```

### Task 4.5: PR 4 Self-Test + 実機検証依頼 + push + PR 作成

- [ ] **Step 1: 全自動チェック**

```bash
cd gui && npm run lint && npm run typecheck && npm test && npm run build && cd ..
cd gui/src-tauri && cargo check && cargo test && cd ../..
```

- [ ] **Step 2: Pre-flight 再実行 + push**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#696 in:title,body" --state all
git push origin claude/youthful-thompson-abbfd6
```

- [ ] **Step 3: 実機検証 (Idios 依頼、AskUserQuestion)**

質問: 「PR 4 (#696) の実機検証を依頼します。`cd gui && npm run tauri dev` で起動 → DevTools console で `window.__aeInvoke('dev_force_unhandled_apperror')` (catch 漏れ実機テスト、本 PR で同梱した場合) → ErrorModal が `errorCategory='tauri-command'` で表示され、title が「処理中に予期しないエラーが発生しました」、hint 行が出ること、`閉じる` button で閉じて normal な app 操作に戻れることを確認してください。」

選択肢:

- `PASS (title / hint / 閉じる ボタン全確認)` (Recommended)
- `PASS (title / hint 確認、閉じる 後の継続使用 未確認)`
- `FAIL (詳細をコメント)`
- `スキップ (mock test のみで承認)`

- [ ] **Step 4: PR 4 作成**

```bash
cat > /tmp/pr4-body.md <<'EOF'
## 概要

catch 漏れた AppError struct (Promise reject されて catch されずに unhandled rejection に流れたケース) を `errorCategory='tauri-command'` で ErrorModal に fallback 表示する。Refs #696 (Lane II-b §2.4)。

## 受け入れ条件と実装の対応 (Iron Law 1)

> - [x] `globalErrorListener.ts` の `onUnhandledRejection` で `isAppError(e.reason)` を判定し、true なら `errorCategory: 'tauri-command'`, `errorTitle: '処理中に予期しないエラーが発生しました', `errorMessage: e.reason.message`, `errorHint: e.reason.hint ?? null` を errorStore.showError に流す

→ Task 4.1 で実装。既存 Error / string / object fallback の **前段** に AppError 分岐を追加。

> - [x] ErrorModal.tsx で `errorCategory === 'tauri-command'` の表示パターンを定義 (recoverable / Issue で報告 / コピー button 構成)

→ Task 4.2 で default title 分岐 (`'tauri-command'` → 「処理中に予期しないエラーが発生しました」) を追加。`isRecoverable=true` で `[閉じる]` button が表示される (既存 default 経路で動作)。`[詳細をコピー]` / `[ログフォルダを開く]` / `[Issue で報告する]` link も既存ロジックで自動表示 (#669 が merge 済なら pre-fill 動作)。

> - [x] 既存 6 panic-related test に加え `'tauri-command' errorCategory の test を追加

→ Task 4.1 で globalErrorListener test に 4 ケース、Task 4.2 で ErrorModal test に 5 ケース (default title / 閉じる button / hint / jest-axe a11y / regression check) を追加。

> - [x] docs/ui-architecture.md §4 (#663 で追加した分岐ルール) に「catch 漏れ AppError は ErrorModal fallback」の旨を追記

→ Task 4.3 で `docs/ui-architecture.md` §4 に 2 節 (catch 漏れ AppError fallback + Issue 報告 link 自動 pre-fill) を追記。

## Self-Test Report

### Machine-verified

- [x] `cd gui && npm run lint` — 0 errors
- [x] `cd gui && npm run typecheck` — 0 errors
- [x] `cd gui && npm test` — N tests passed (+9 new)
- [x] `cd gui && npm run build` — bundle 生成
- [x] `cd gui/src-tauri && cargo check` — 0 errors (Task 4.4 同梱時のみ)
- [x] `cd gui/src-tauri && cargo test` — N tests passed (Task 4.4 同梱時のみ)

### Machine-unverifiable

- 実機 Tauri 起動 (Idios): `dev_force_unhandled_apperror` (or 同等の catch 漏れ再現) → ErrorModal 'tauri-command' 表示確認

## 実機検証結果

(Idios の AskUserQuestion 回答を貼り付け)

## 関連

Refs #696
spec: `docs/superpowers/specs/2026-05-11-l2-lane-ii-b-group-d-696-design.md` §2.4

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF

gh pr create --base develop-0.2.0 --head claude/youthful-thompson-abbfd6 --title "feat(gui): #696 ErrorModal に catch 漏れ AppError fallback ('tauri-command') 統合 (Lane II-b §2.4)" --body-file /tmp/pr4-body.md
rm /tmp/pr4-body.md
```

- [ ] **Step 5: review iteration → マージ → `/close-issue` で #696 を手動 close**

---

## 実機検証 trigger 集約表

| PR | 章 | 実機検証必須/推奨 | 確認手順 |
| --- | --- | --- | --- |
| PR 1 | §2.1 #678 | 推奨 | `cd gui && npm run tauri dev` → Export 画面で 不存在 path → `フォルダを開く` → 日本語 message + hint 表示 / Preview 画面で破損動画 → 日本語 message 表示 |
| PR 2 | §2.2 #669 | **必須** | `cd gui && npm run tauri dev` → DevTools console で `await window.__aeInvoke('dev_force_panic')` → ErrorModal 出現 → `Issue で報告する` link クリック → GitHub form の `actual`/`environment`/`log_file_attachment` 3 field に内容反映確認 |
| PR 3 | §2.3 #680 | **必須** | `cd gui && npm run tauri dev` → 動画 drop → Export 画面で 出力先 default が `<dirname>` (親ディレクトリ、存在保証) であることを確認 |
| PR 4 | §2.4 #696 | **必須** | `cd gui && npm run tauri dev` → DevTools console で `window.__aeInvoke('dev_force_unhandled_apperror')` (Task 4.4 同梱時) または catch 漏れ自然発生で → ErrorModal が `'tauri-command'` 表示パターン (title 「処理中に...」 / 閉じる button / hint 表示) で出ること |

各 PR 着手時に AskUserQuestion で Idios に依頼し、結果を PR 本文の `## 実機検証結果` セクションに貼り付ける。

---

## 完了後 handoff (各 PR マージ後)

各 PR マージ後は `/close-issue` skill に handoff:

```bash
# PR マージ確認後
/close-issue <PR#>
```

`/close-issue` skill は:

1. マージ後の develop-0.2.0 で 受け入れ条件を実測再検証 (Iron Law 4 担保)
2. 未消化チェックボックスや残タスクを (B) 新 issue / (C) 既存 issue 追記 にトリアージ
3. ユーザー承認で `gh issue close` を実行

4 PR 順次:

```bash
# PR 1 マージ後
/close-issue <PR1#>
# → #678 close

# PR 2 マージ後
/close-issue <PR2#>
# → #669 close

# PR 3 マージ後
/close-issue <PR3#>
# → #680 close

# PR 4 マージ後
/close-issue <PR4#>
# → #696 close
```

---

## 補足: 4 PR 内で発生する scope creep の処理

各 PR の作業中に **scope 外の改修必要性**を発見した場合の判断フロー:

1. `scope-guard` skill を invoke (この skill の判断に従う)
2. 判断結果が「別 issue 起票」なら `/create-task` skill を invoke して新 issue を立てる
3. 判断結果が「scope 拡大」なら user (Idios) に AskUserQuestion で確認 (Iron Law 3)
4. 判断結果が「revert」なら該当変更を revert (本 PR の純度を保つ)

特に注意すべき scope creep パターン:

- §2.1 PR で **5 番目以降の `String(e)` site** を発見 → 別 issue (本 PR で sweep しない、roadmap #663 sweep 規約に沿った別 issue handoff)
- §2.2 PR で `formatSystemInfo` 実装中に metadata schema の不整合発見 → 別 issue (schema mutation は scope 外)
- §2.3 PR で別 setOutDir 経路 (`deriveDetectOutputDir` 等) を発見 → 別 issue (1 PR = 1 scope 原則)
- §2.4 PR で AppError priority queue が必要だと判明 → 別 issue (first-write-wins 既存設計は維持)
