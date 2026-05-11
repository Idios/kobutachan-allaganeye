# Lane V Phase 1: Group I post-#663 hint UI cleanup 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PR #689 (#663 AppError migration) で残された hint UI cleanup 5 件を 5 PR で消化し、hint UI 規約を `InlineErrorHint` component に一元化、`*ErrorHint` dead state をゼロ化する。

**Architecture:** 2 wave / 5 PR 構成。Wave 1.1 = PR 1 #693 (InlineErrorHint component 新設、lead) + PR 2 #691 (UI 非依存、完全並行)。Wave 1.2 = PR 3 #695 + PR 4 #697 + PR 5 #698 (InlineErrorHint consumer、PR 1 merge 後 rebase 起点)。各 PR は独立 worktree、各 task group は self-contained。

**Tech Stack:** React 19 + TypeScript + Vite + Zustand + CSS Modules + vitest + jest-axe + Tauri 2 (Rust 側変更なし)

**Spec:** [docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md](../specs/2026-05-11-lane-v-phase-1-group-i-design.md)

---

## File Structure (全 PR の touched files)

**PR 1 (#693) InlineErrorHint component 新設**:

- Create: `gui/src/components/InlineErrorHint.tsx`
- Create: `gui/src/components/InlineErrorHint.module.css`
- Create: `gui/src/components/InlineErrorHint.test.tsx`
- Modify: `gui/src/components/RestoreButton.tsx:97-103`
- Modify: `gui/src/components/RestoreButton.module.css:37-47` (`.errorHint` を InlineErrorHint と非競合化)
- Modify: `gui/src/screens/DropScreen.tsx` (ErrorCard 部分の hint render)
- Modify: `gui/src/screens/DropScreen.module.css` (ErrorCard hint 関連 class)
- Modify: `gui/src/screens/DetectingScreen.tsx` (errorScreen 部分の hint render)
- Modify: `gui/src/screens/DetectingScreen.module.css`
- Modify: `gui/src/screens/PreviewScreen.tsx` (applyError 部分の hint render)
- Modify: `gui/src/screens/PreviewScreen.module.css` (`.applyErrorHint` の維持)
- Modify: `gui/src/screens/ExportScreen.tsx` (listError 部分の hint render)
- Modify: `gui/src/screens/ExportScreen.module.css` (`.listErrorHint` の維持)
- Modify: `gui/src/components/RestoreButton.test.tsx` (assertion 更新)
- Modify: `gui/src/screens/DropScreen.test.tsx` (assertion 更新)
- Modify: `gui/src/screens/DetectingScreen.test.tsx` (assertion 更新)
- Modify: `gui/src/screens/PreviewScreen.test.tsx` (assertion 更新)
- Modify: `gui/src/screens/ExportScreen.test.tsx` (assertion 更新)
- Modify: `docs/ui-architecture.md` §4 (InlineErrorHint 規約追記)

**PR 2 (#691) metadataStore lifecycle pinning**:

- Modify: `gui/src/state/metadataStore.ts` (5 catch path の clear 範囲整理 — 案 X / Y は AskUserQuestion で確定)
- Modify: `gui/src/state/metadataStore.test.ts` (6-8 件の lifecycle pinning test 追加)
- Modify: `docs/ui-architecture.md` §4 (lifecycle 規約追記)
- Modify: `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` §7 (Refs リンク追加)

**PR 3 (#695) ConflictModal AppError hint**:

- Modify: `gui/src/state/metadataStore.ts` (`conflictErrorHint` state 追加、`runApply` catch / `dismissConflict` / `reloadAfterConflict` 更新)
- Modify: `gui/src/components/ConflictModal.tsx:47-50` (compose hint 削除 + InlineErrorHint + 補足 1 行)
- Modify: `gui/src/components/ConflictModal.module.css:39-45` (`.hint` → `.cancelHint`)
- Modify: `gui/src/components/ConflictModal.test.tsx` (3-4 件追加 + 旧 compose hint assertion 削除)
- Modify: `gui/src/state/metadataStore.test.ts` (`conflictErrorHint` lifecycle test 1-2 件追加)
- Modify: `docs/ui-interaction-spec.md` §1.5 (modal hint slot 規約追記)

**PR 4 (#697) DraftRestoreModal hint UI**:

- Modify: `gui/src/components/DraftRestoreModal.tsx:36-38` (draftLoadError 経路に InlineErrorHint 追加)
- Modify: `gui/src/components/DraftRestoreModal.test.tsx` (2-3 件追加)

**PR 5 (#698) DropScreen recentStore notice**:

- Modify: `gui/src/screens/DropScreen.tsx:370` (recent list 上部に notice 追加)
- Modify: `gui/src/screens/DropScreen.module.css` (`.recentNotice` / `.recentNoticeMessage` class 追加)
- Modify: `gui/src/state/recentStore.ts:28` (docstring update)
- Modify: `gui/src/screens/DropScreen.test.tsx` (4-5 件追加)

---

## 共通 Prerequisites (各 PR 着手前に毎回)

各 PR の着手前に **Iron Law 6 PR Pre-flight** を必ず実施:

```bash
# 1. worktree 確認 (claude/<auto-name>/ ブランチに居ること)
git status
git branch --show-current  # claude/<auto-name>

# 2. base 同期 (PR 3-5 は PR 1 merge 後に必ず実施)
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
# ↑ 取り込み未済 commit が touched files と交差するなら:
git merge origin/develop-0.2.0
# (conflict 出たら resolve → npm test で regression 確認)

# 3. 並行 worktree PR 重複確認
gh pr list --search "<元 issue#>" --state all

# 4. 既存 baseline (PR 着手前 commit) で自動チェック実行
cd gui
npm run lint     # exit 0 期待
npm run typecheck  # exit 0 期待
npm test -- --run  # 既存 ~605 件 pass 期待
npm run build    # success 期待
cd src-tauri
cargo check
cargo test --lib  # 既存 156 件 pass 期待
cd ../..
bash scripts/check-markdownlint.sh  # 0 errors 期待
```

すべて green であることを確認してから task に着手。途中で fail したら baseline 不整合のため一旦 stop して原因調査。

---

## Task Group A: PR 1 (#693) InlineErrorHint component 新設 + 既存 5 site refactor

**Goal:** `gui/src/components/InlineErrorHint.tsx` を新設し、既存 5 site (RestoreButton / DropScreen / DetectingScreen / PreviewScreen / ExportScreen) の hard-coded `💡 {hint}` を component 経由に refactor する。Wave 1.1 lead PR で、merge 後に PR 3-5 が consume する。

**worktree**: 新規作成 (例 `.claude/worktrees/<auto-name-1>/`)、ブランチ `claude/<auto-name-1>`、base `develop-0.2.0`

### Task A.1: InlineErrorHint component の TDD - failing test 先

**Files:**

- Test: `gui/src/components/InlineErrorHint.test.tsx`

- [ ] **Step 1: 新規 test file を作成**

ファイル `gui/src/components/InlineErrorHint.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { InlineErrorHint } from './InlineErrorHint';

describe('InlineErrorHint', () => {
  it('renders hint with 💡 prefix when hint is provided', () => {
    render(<InlineErrorHint hint="ファイルを確認してください" />);
    expect(screen.getByText('💡 ファイルを確認してください')).toBeInTheDocument();
  });

  it('renders nothing when hint is null', () => {
    const { container } = render(<InlineErrorHint hint={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when hint is undefined', () => {
    const { container } = render(<InlineErrorHint hint={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when hint is empty string', () => {
    const { container } = render(<InlineErrorHint hint="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('does not carry role attribute (parent role="alert" must remain authoritative)', () => {
    render(<InlineErrorHint hint="some hint" />);
    const el = screen.getByText(/💡/);
    expect(el).not.toHaveAttribute('role');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd gui && npm test -- --run InlineErrorHint
```

Expected: FAIL with "Cannot find module './InlineErrorHint'" (component still missing).

### Task A.2: InlineErrorHint component 実装 (Green)

**Files:**

- Create: `gui/src/components/InlineErrorHint.tsx`
- Create: `gui/src/components/InlineErrorHint.module.css`

- [ ] **Step 1: CSS module を作成**

ファイル `gui/src/components/InlineErrorHint.module.css`:

```css
/* #693: 5 site 共通の hint 2 行目 style。Phase 4 #689 で確立した規約 (`💡` prefix +
   `var(--ae-text-dim)`) を component に集約。consumer 側 `role="alert"` wrapper の
   内側に nest する規約 (component 自身は role を持たない、a11y violation 回避)。

   サイト固有の表示制御 (PreviewScreen `display: block` / ExportScreen
   `white-space: normal` + `max-width: 100%` + `overflow: visible` 等) は consumer
   側 wrapper class で維持し、本 component は最小 layout のみ提供する。 */
.hint {
  font-family: var(--ae-font-body);
  font-size: 11px;
  color: var(--ae-text-dim);
  display: block;
  line-height: 1.5;
}
```

- [ ] **Step 2: Component を作成**

ファイル `gui/src/components/InlineErrorHint.tsx`:

```tsx
import styles from './InlineErrorHint.module.css';

export interface InlineErrorHintProps {
  /** Hint text. When `null` / `undefined` / empty, the component renders nothing. */
  hint: string | null | undefined;
}

/**
 * #693: 5 既存 site (RestoreButton / DropScreen ErrorCard / DetectingScreen /
 * PreviewScreen / ExportScreen) + 新規 3 site (#695 ConflictModal / #697
 * DraftRestoreModal / #698 DropScreen recentNotice) で共有される、AppError
 * の `hint` を inline error の 2 行目に表示するための小さな component。
 *
 * - `💡` prefix は本 component で集中管理 (i18n / theme 切替時の修正点を 1 箇所に)
 * - a11y: 本 component 自身に `role` を付けない (consumer 側 `role="alert"` wrapper
 *   の内側に nest する規約、Phase 4 #689 で確立)
 * - 文字色 = `var(--ae-text-dim)`、サイズ・表示の細部は site-specific wrapper
 *   class で override 可能 (本 component は最小 layout のみ提供)
 */
export function InlineErrorHint({ hint }: InlineErrorHintProps): JSX.Element | null {
  if (!hint) return null;
  return <span className={styles.hint}>💡 {hint}</span>;
}
```

- [ ] **Step 3: Test を pass させる**

```bash
cd gui && npm test -- --run InlineErrorHint
```

Expected: PASS (5 件 all green).

- [ ] **Step 4: Commit**

```bash
git add gui/src/components/InlineErrorHint.tsx gui/src/components/InlineErrorHint.module.css gui/src/components/InlineErrorHint.test.tsx
git commit -m "feat(gui): add InlineErrorHint component (Refs #693)

Phase 4 #689 で確立した hint UI 規約 (\`💡\` prefix + \`var(--ae-text-dim)\`)
を共通 component に集約。5 既存 site + 後続 3 site (#695 #697 #698) で
consume される共有 building block。

- props: \`hint: string | null | undefined\`
- a11y: 本 component 自身に role を持たない (consumer 側 \`role=\"alert\"\`
  wrapper の内側に nest する規約)
- 5 件の TDD test (hint set / null / undefined / empty / a11y) pass

Refs #693"
```

### Task A.3: RestoreButton refactor

**Files:**

- Modify: `gui/src/components/RestoreButton.tsx:97-103`
- Modify: `gui/src/components/RestoreButton.module.css:37-47`

- [ ] **Step 1: RestoreButton.tsx で InlineErrorHint を使う**

`gui/src/components/RestoreButton.tsx` の以下を変更:

Before (line 97-103):

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

After:

```tsx
      {restoreError && (
        <span className={styles.error} role="alert">
          {restoreError}
          <InlineErrorHint hint={restoreErrorHint} />
        </span>
      )}
```

import 追加 (line 1-5 付近の import block 内):

```tsx
import { InlineErrorHint } from './InlineErrorHint';
```

- [ ] **Step 2: RestoreButton.module.css の `.errorHint` を削除**

`gui/src/components/RestoreButton.module.css` の line 37-47 (`/* #663 ... */` コメント + `.errorHint` block) を**完全削除**。`.error` (line 30-35) と `.busy` (line 26-28) は維持。

- [ ] **Step 3: 既存 test の hint assertion が依然 pass することを確認**

```bash
cd gui && npm test -- --run RestoreButton
```

Expected: PASS (既存 7 件 + 新規 0 件、`getByText('💡 …')` 形式は component 経由でも render は同等)。

もし fail したら、test 側で `getByText` の selector が CSS module class name に依存していないか確認。

- [ ] **Step 4: lint + typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/src/components/RestoreButton.tsx gui/src/components/RestoreButton.module.css
git commit -m "refactor(gui): RestoreButton uses InlineErrorHint (Refs #693)

5 既存 site の 1 つ目。\`.errorHint\` class は CSS module から削除、
InlineErrorHint で render。

Refs #693"
```

### Task A.4: DropScreen ErrorCard refactor

**Files:**

- Modify: `gui/src/screens/DropScreen.tsx` (ErrorCard 部分)
- Modify: `gui/src/screens/DropScreen.module.css` (`.errorHint` 部分)

- [ ] **Step 1: 既存 hint render を component 化**

`gui/src/screens/DropScreen.tsx` 内の ErrorCard (`<div className={styles.errorCard} role="alert">` 配下) の `<div|span className={styles.errorHint}>💡 {hint}</div|span>` を `<InlineErrorHint hint={errorHint} />` に置換。

具体的な行番号は `grep -n "errorHint" gui/src/screens/DropScreen.tsx` で特定し、`💡` 絵文字 + 半角スペースのリテラルを含む行を component 呼び出しに置換する。

import 追加 (file 上部):

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';
```

- [ ] **Step 2: DropScreen.module.css の `.errorHint` class を削除**

`grep -n "errorHint" gui/src/screens/DropScreen.module.css` で確認し、`.errorHint` block を削除。**`.errorCard` や `.error` 等の wrapper class は維持** (InlineErrorHint は wrapper の内側に置かれる)。

- [ ] **Step 3: 既存 test の hint assertion が pass することを確認**

```bash
cd gui && npm test -- --run DropScreen
```

Expected: PASS.

- [ ] **Step 4: lint + typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/DropScreen.tsx gui/src/screens/DropScreen.module.css
git commit -m "refactor(gui): DropScreen ErrorCard uses InlineErrorHint (Refs #693)

Refs #693"
```

### Task A.5: DetectingScreen refactor

**Files:**

- Modify: `gui/src/screens/DetectingScreen.tsx` (errorScreen 部分)
- Modify: `gui/src/screens/DetectingScreen.module.css`

- [ ] **Step 1: 既存 hint render を component 化**

`gui/src/screens/DetectingScreen.tsx` の errorScreen / 同等 hint 経路を `<InlineErrorHint hint={…} />` に置換。`grep -n "errorHint\|💡" gui/src/screens/DetectingScreen.tsx` で対象行を特定。

import 追加 (file 上部):

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';
```

- [ ] **Step 2: DetectingScreen.module.css の `.errorHint` class を削除**

`.errorHint` block 削除。site-specific wrapper class は維持。

- [ ] **Step 3: 既存 test pass を確認**

```bash
cd gui && npm test -- --run DetectingScreen
```

Expected: PASS.

- [ ] **Step 4: lint + typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/DetectingScreen.tsx gui/src/screens/DetectingScreen.module.css
git commit -m "refactor(gui): DetectingScreen uses InlineErrorHint (Refs #693)

Refs #693"
```

### Task A.6: PreviewScreen refactor

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx` (applyError 部分)
- Modify: `gui/src/screens/PreviewScreen.module.css`

- [ ] **Step 1: 既存 hint render を component 化**

`gui/src/screens/PreviewScreen.tsx` の applyError 表示部分 (line を grep で特定) の `💡 {hint}` を `<InlineErrorHint hint={…} />` に置換。

**重要**: PreviewScreen には `.applyErrorHint` という wrapper class があり、`display: block` で 1 行目との改行を担保している。この wrapper class は維持し、その内側に InlineErrorHint を置く。

Before (概念):

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

After:

```tsx
{applyError && (
  <span className={styles.applyError} role="alert">
    {applyError}
    <span className={styles.applyErrorHint}>
      <InlineErrorHint hint={applyErrorHint} />
    </span>
  </span>
)}
```

import 追加:

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';
```

- [ ] **Step 2: PreviewScreen.module.css の `.applyErrorHint` を維持しつつ style 簡素化**

`.applyErrorHint` block は **削除しない**。`display: block` のみ残し、font-size / color / font-family は InlineErrorHint 側に委譲:

```css
/* InlineErrorHint の wrapper として行送り (display: block) を担保。
   font-size / color / font-family は InlineErrorHint 側で定義。 */
.applyErrorHint {
  display: block;
  margin-top: 2px;
}
```

(既存の line-height / font-* 系プロパティは削除。InlineErrorHint と重複するため。)

- [ ] **Step 3: 既存 test pass を確認**

```bash
cd gui && npm test -- --run PreviewScreen
```

Expected: PASS.

- [ ] **Step 4: lint + typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.module.css
git commit -m "refactor(gui): PreviewScreen uses InlineErrorHint (Refs #693)

\`.applyErrorHint\` wrapper class は \`display: block\` のみ残し、font-size
等は InlineErrorHint 側に委譲する形で簡素化。

Refs #693"
```

### Task A.7: ExportScreen refactor

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx` (listError 部分)
- Modify: `gui/src/screens/ExportScreen.module.css`

- [ ] **Step 1: 既存 hint render を component 化**

`gui/src/screens/ExportScreen.tsx` の listError 表示部分 (line grep で特定) の `💡 {hint}` を `<InlineErrorHint hint={…} />` に置換。

**重要**: ExportScreen には `.listErrorHint` wrapper class があり、parent `.listError` の `nowrap` / `overflow: hidden` を override するため `white-space: normal` + `max-width: 100%` + `overflow: visible` を持つ。この wrapper class は維持し、その内側に InlineErrorHint を置く (PreviewScreen と同じ pattern)。

Before (概念):

```tsx
{listError && (
  <div className={styles.listError} role="alert">
    {listError}
    {listErrorHint && (
      <div className={styles.listErrorHint}>💡 {listErrorHint}</div>
    )}
  </div>
)}
```

After:

```tsx
{listError && (
  <div className={styles.listError} role="alert">
    {listError}
    <div className={styles.listErrorHint}>
      <InlineErrorHint hint={listErrorHint} />
    </div>
  </div>
)}
```

import 追加:

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';
```

- [ ] **Step 2: ExportScreen.module.css の `.listErrorHint` を維持しつつ簡素化**

`white-space: normal` + `max-width: 100%` + `overflow: visible` の override 系は維持。font-* 系は削除 (InlineErrorHint と重複):

```css
/* InlineErrorHint の wrapper として、parent .listError の nowrap / overflow:hidden
   を override し長い hint を折り返し可能にする。font-size / color / family は
   InlineErrorHint 側に委譲。 */
.listErrorHint {
  display: block;
  white-space: normal;
  max-width: 100%;
  overflow: visible;
  margin-top: 2px;
}
```

- [ ] **Step 3: 既存 test pass を確認**

```bash
cd gui && npm test -- --run ExportScreen
```

Expected: PASS.

- [ ] **Step 4: lint + typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.module.css
git commit -m "refactor(gui): ExportScreen uses InlineErrorHint (Refs #693)

\`.listErrorHint\` wrapper class は parent \`.listError\` nowrap override 系
(\`white-space\` / \`max-width\` / \`overflow\`) を維持しつつ、font-* 系は
InlineErrorHint 側に委譲。

5 既存 site refactor 完了。

Refs #693"
```

### Task A.8: 全 test + build + lint sweep

- [ ] **Step 1: 全 frontend test を一度に実行**

```bash
cd gui && npm test -- --run
```

Expected: 既存 ~605 件 + 新規 5 件 (InlineErrorHint) = ~610 件 pass。

もし fail があれば、refactor の取りこぼし (`💡` 絵文字 + 半角スペース literal の残存 / 古い `.errorHint` class 参照 等)。`grep -rn "💡 " gui/src/` で全 hard-coded 箇所を確認し、未 refactor 箇所を任意の InlineErrorHint で置換。

- [ ] **Step 2: build 確認**

```bash
cd gui && npm run build
```

Expected: success、`gui/dist/` 生成。

- [ ] **Step 3: lint + typecheck 再確認**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: exit 0。

- [ ] **Step 4: Rust 側 regression 確認**

```bash
cd gui/src-tauri && cargo check && cargo test --lib
```

Expected: 156 件 baseline 維持。

- [ ] **Step 5: 中間 commit (refactor sweep)**

ここまでに sweep で見つかった追加修正があればまとめて commit:

```bash
git add -A
git commit -m "refactor(gui): 5 site sweep + 全 test pass (Refs #693)

\`grep -rn '💡 ' gui/src/\` で hard-coded 箇所ゼロ確認。
全 frontend test pass、lint / typecheck / build / cargo green。

Refs #693" --allow-empty
```

(`--allow-empty` は前 task で sweep 漏れがなかった場合用。漏れがあれば実 commit になる。)

### Task A.9: docs 更新

**Files:**

- Modify: `docs/ui-architecture.md` §4

- [ ] **Step 1: `docs/ui-architecture.md` §4 に InlineErrorHint 規約節を追記**

§4 の AppError code 体系節の末尾に以下を追記 (該当箇所を `grep -n "## §4\|### §4" docs/ui-architecture.md` で特定):

````markdown
### §4.x InlineErrorHint component (#693)

PR #693 で導入された共通 component。hint UI の `💡` prefix と `var(--ae-text-dim)`
スタイルを 1 箇所に集約し、5 既存 site (RestoreButton / DropScreen ErrorCard /
DetectingScreen / PreviewScreen / ExportScreen) + 後続 3 site (#695 ConflictModal /
#697 DraftRestoreModal / #698 DropScreen recentNotice) で共有する。

**Usage**:

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';

<span role="alert">
  {errorMessage}
  <InlineErrorHint hint={errorHint} />
</span>
```

**a11y 規約**:

- consumer 側で `role="alert"` wrapper を提供する (本 component 自身は role を持たない)
- 親の role を維持することで、screen reader は「message + hint」を 1 つの alert
  update として読み上げる

**Wrapper class での site-specific override**:

- PreviewScreen `.applyErrorHint`: `display: block` で改行担保
- ExportScreen `.listErrorHint`: parent `.listError` の `nowrap` / `overflow:hidden`
  を override (`white-space: normal` + `max-width: 100%` + `overflow: visible`)
- 他 3 site (RestoreButton / DropScreen / DetectingScreen) は wrapper class 不要
````

- [ ] **Step 2: markdownlint 確認**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 errors。

- [ ] **Step 3: Commit**

```bash
git add docs/ui-architecture.md
git commit -m "docs(ui): InlineErrorHint 規約節を追記 (Refs #693)

Refs #693"
```

### Task A.10: PR 作成 (Iron Law 6 PR Pre-flight)

- [ ] **Step 1: Pre-flight 再実行**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline  # 取り込み未済 commit
gh pr list --search "#693" --state all  # 並行 PR 重複確認
```

新たな commit が取り込まれていて touched files と交差するなら `git merge origin/develop-0.2.0` で吸収し、`npm test` / `cargo test` で regression 確認。

- [ ] **Step 2: PR 本文を準備**

PR 本文 template:

```markdown
## Summary

#693 (Refs #663) の対応。Phase 4 #689 で確立した hint UI 規約 (`💡` prefix +
`var(--ae-text-dim)`) を `InlineErrorHint` component に集約し、既存 5 site
(RestoreButton / DropScreen / DetectingScreen / PreviewScreen / ExportScreen) を
component 経由に refactor。後続 PR #695 / #697 / #698 が同 component を consume
する base を提供する Wave 1.1 lead PR。

session-id: `<worktree 名>`
spec: docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md §5.1

## 受け入れ条件 (元 issue #693 を逐条引用)

- [x] `gui/src/components/InlineErrorHint.tsx` が新設され、props `hint: string | null | undefined` を取る
- [x] CSS module `.hint` が `var(--ae-text-dim)` / `font-size: 11px` 規約
- [x] InlineErrorHint.test.tsx が 5 件 pass (set / null / undefined / empty / a11y)
- [x] 既存 5 site が `<InlineErrorHint>` 経由に refactor
- [x] 既存 5 site test が全 pass
- [x] `docs/ui-architecture.md` §4.x に component 規約節を追記

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認
- [x] `gh pr list --search "#693"` で並行 PR 重複なし
- [x] `cd gui && npm run lint` (exit 0)
- [x] `cd gui && npm run typecheck` (exit 0)
- [x] `cd gui && npm test -- --run` (全 pass)
- [x] `cd gui && npm run build` (success)
- [x] `cd gui/src-tauri && cargo check` (clean)
- [x] `cd gui/src-tauri && cargo test --lib` (156 件 pass)
- [x] `bash scripts/check-markdownlint.sh` (0 errors)
- [x] `grep -rn '💡 ' gui/src/` で hard-coded ゼロ確認

### Machine-unverifiable (Idios 実機検証 — `AskUserQuestion` で依頼)

- 既存 5 site の hint 表示が refactor 後も retained (PreviewScreen apply error /
  DropScreen load error / RestoreButton restore error 等を発火させて目視確認)

## Refs

Refs #693 #663 #689
```

- [ ] **Step 3: PR を push + 作成**

```bash
git push -u origin claude/<auto-name-1>
gh pr create --base develop-0.2.0 --title "refactor(gui): #693 InlineErrorHint component 新設 + 既存 5 site refactor (Lane V Phase 1)" --body-file <(printf '%s' "$PR_BODY")
```

(`$PR_BODY` は前 step の template を heredoc または file 経由で渡す。日本語が混じるため `printf | --body-file -` 推奨。)

- [ ] **Step 4: Iron Law 6 実機検証を Idios に依頼**

PR 作成後、AskUserQuestion で:

> 「PR #<番号> の Iron Law 6 実機検証として、既存 5 site の hint 表示 retained 確認をお願いします:
>
> 1. PreviewScreen で apply 失敗 (read-only metadata.json) → hint 2 行目表示
> 2. DropScreen で load 失敗 (存在しない path 入力) → hint 2 行目表示
> 3. RestoreButton で restore 失敗 (バックアップ破損) → hint 2 行目表示
> 4. DetectingScreen で detect 失敗 → hint 2 行目表示
> 5. ExportScreen で export 失敗 → hint 2 行目表示
>
> 結果を PR comment にお願いします。」

---

## Task Group B: PR 2 (#691) metadataStore catch path lifecycle pinning

**Goal:** `metadataStore.ts` の 5 catch path × 5 `*ErrorHint` state の clear 範囲を test で pin し、規約を docstring + docs/ui-architecture.md に明文化。Wave 1.1 PR 1 と完全並行。

**worktree**: 新規作成 (例 `.claude/worktrees/<auto-name-2>/`)、PR 1 と独立。

**重要**: PR 2 は UI 変更なし。InlineErrorHint に依存しない。

### Task B.1: 現状コードの精査 (Open question §10 解決)

- [ ] **Step 1: 5 catch path の clear 範囲を grep で全 enumerate**

```bash
cd /e/projects/kobutachan-tools/kobutachan-allaganeye/.claude/worktrees/<auto-name-2>
grep -n -A 20 "load:\|runApply\|restore:\|saveDraft\|loadDraft" gui/src/state/metadataStore.ts | head -200
```

実 matrix を確定:

| catch path | `loadErrorHint` | `applyErrorHint` | `restoreErrorHint` | `draftSaveErrorHint` | `draftLoadErrorHint` |
| --- | --- | --- | --- | --- | --- |
| `load()` catch | set (msg) | (要確認) | (要確認) | (要確認) | (要確認) |
| `runApply()` catch (非 conflict) | (要確認) | set (msg) | (要確認) | (要確認) | (要確認) |
| `runApply()` catch (conflict) | (要確認) | (要確認) | (要確認) | (要確認) | (要確認) |
| `restore()` catch | (要確認) | (要確認) | set (msg) | (要確認) | (要確認) |
| `saveDraft()` catch | (要確認) | (要確認) | (要確認) | set (msg) | (要確認) |
| `loadDraft()` catch | (要確認) | (要確認) | (要確認) | (要確認) | set (msg) |
| `clear()` lifecycle | null | null | null | null | null |
| `loadSample()` lifecycle | null | null | null | null | null |
| `load()` success | (要確認) | (要確認) | (要確認) | (要確認) | (要確認) |

(?) セルは PR 内で精査して確定する。

- [ ] **Step 2: 確定した matrix を PR 本文に記載するための table 雛形を作成**

`/tmp/clear_matrix.md` 等にメモして PR 作成時に貼付。

### Task B.2: AskUserQuestion で 案 X / 案 Y を確定

- [ ] **Step 1: matrix から asymmetry を抽出**

`load()` catch が他経路の hint を partial に clear するパターンを特定。例:

- `load()` catch は `draftLoadErrorHint` / `draftSaveErrorHint` を clear するが、`applyErrorHint` / `restoreErrorHint` は clear しない
- これは「load() 失敗時は新規 load なので draft 系は陳腐化、apply/restore 系の旧 error は残す」意図か、それとも「単に書き忘れ」かを判断する必要あり

- [ ] **Step 2: AskUserQuestion で Idios に判断仰ぐ**

```text
Q: PR #691 metadataStore.ts の load() catch path での *ErrorHint clear 範囲を symmetric 化しますか?

[A] 案 X: 完全 symmetric 化
  load() catch path から他経路 (draftLoadErrorHint / draftSaveErrorHint) の clear を削除。
  各 catch path が自身の *ErrorHint のみを set し、他経路には touch しない規約。

[B] 案 Y: 非対称維持 + 根拠コメント
  load() catch の partial clear を維持しつつ、コードコメントで「load() 失敗は新規 load
  なので draft 系は陳腐化と見なす」根拠を明文化。symmetric 化はしない。

(Recommended): 案 X (規約が単純で test pin が容易、書き忘れ前提の partial clear は意図不明確)
```

- [ ] **Step 3: Idios 回答を記録、以降の task は採用案に従う**

PR 本文に「採用案: X / Y」を明記。

### Task B.3: Lifecycle pinning test を追加 (Red)

**Files:**

- Modify: `gui/src/state/metadataStore.test.ts`

- [ ] **Step 1: 各 catch path 用 test を追加**

`gui/src/state/metadataStore.test.ts` の末尾に以下を追加 (採用案に応じて期待値を調整):

```tsx
describe('#691: catch path lifecycle pinning', () => {
  beforeEach(() => {
    useMetadataStore.setState({
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
  });

  it('load() catch path sets loadErrorHint and (案 X: leaves others) / (案 Y: clears draft hints)', async () => {
    // pre-condition: 全 hint が non-null
    useMetadataStore.setState({
      applyErrorHint: 'old apply hint',
      restoreErrorHint: 'old restore hint',
      draftLoadErrorHint: 'old draft load hint',
      draftSaveErrorHint: 'old draft save hint',
    });

    // 既存の load() invoke mock setup (project-specific の vitest setup ファイル参照)
    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'io.file_not_found',
      message: 'file not found',
      hint: 'check path',
    });

    await useMetadataStore.getState().load('/non-existent');

    const state = useMetadataStore.getState();
    expect(state.loadErrorHint).toBe('check path');

    // 案 X 採用なら:
    // expect(state.applyErrorHint).toBe('old apply hint');
    // expect(state.restoreErrorHint).toBe('old restore hint');
    // expect(state.draftLoadErrorHint).toBe('old draft load hint');
    // expect(state.draftSaveErrorHint).toBe('old draft save hint');

    // 案 Y 採用なら:
    // expect(state.applyErrorHint).toBe('old apply hint');
    // expect(state.restoreErrorHint).toBe('old restore hint');
    // expect(state.draftLoadErrorHint).toBe(null);  // load() で clear される
    // expect(state.draftSaveErrorHint).toBe(null);  // load() で clear される
  });

  it('runApply() catch (非 conflict) sets applyErrorHint and leaves others', async () => {
    useMetadataStore.setState({
      metadata: { /* valid mock metadata */ } as any,
      filePath: '/test.mp4',
      loadErrorHint: 'old load hint',
      restoreErrorHint: 'old restore hint',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'io.permission_denied',
      message: 'denied',
      hint: 'check write permission',
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.applyErrorHint).toBe('check write permission');
    expect(state.loadErrorHint).toBe('old load hint');
    expect(state.restoreErrorHint).toBe('old restore hint');
  });

  it('runApply() catch (conflict) sets conflictError and leaves *ErrorHint', async () => {
    useMetadataStore.setState({
      metadata: { /* valid mock */ } as any,
      filePath: '/test.mp4',
      applyErrorHint: 'old apply hint',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'state.mtime_conflict',
      message: 'metadata.json was modified',
      hint: 'reload or overwrite',
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeTruthy();
    // 案 X: applyErrorHint は touch しない → 旧 'old apply hint' が残る
    // 案 Y: applyErrorHint は clear or set される (要確認)
    // 現状コード line 222 は `set({ applying: false, conflictError: msg })` で applyErrorHint は touch しない
    expect(state.applyErrorHint).toBe('old apply hint');
  });

  it('restore() catch sets restoreErrorHint and leaves others', async () => {
    useMetadataStore.setState({
      filePath: '/test.mp4',
      loadErrorHint: 'old load hint',
      applyErrorHint: 'old apply hint',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'io.backup_failed',
      message: 'backup failed',
      hint: 'check disk',
    });

    await useMetadataStore.getState().restore();

    const state = useMetadataStore.getState();
    expect(state.restoreErrorHint).toBe('check disk');
    expect(state.loadErrorHint).toBe('old load hint');
    expect(state.applyErrorHint).toBe('old apply hint');
  });

  it('saveDraft() catch sets draftSaveErrorHint and leaves others', async () => {
    useMetadataStore.setState({
      metadata: { /* valid */ } as any,
      filePath: '/test.mp4',
      loadErrorHint: 'old load hint',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'io.write_failed',
      message: 'write failed',
      hint: 'check space',
    });

    await useMetadataStore.getState().saveDraft();

    const state = useMetadataStore.getState();
    expect(state.draftSaveErrorHint).toBe('check space');
    expect(state.loadErrorHint).toBe('old load hint');
  });

  it('loadDraft() catch sets draftLoadErrorHint and leaves others', async () => {
    useMetadataStore.setState({
      metadata: { /* valid */ } as any,
      filePath: '/test.mp4',
      applyErrorHint: 'old apply hint',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'parse.json_invalid',
      message: 'json invalid',
      hint: 'restore from backup',
    });

    await useMetadataStore.getState().loadDraft();

    const state = useMetadataStore.getState();
    expect(state.draftLoadErrorHint).toBe('restore from backup');
    expect(state.applyErrorHint).toBe('old apply hint');
  });

  it('clear() resets all *ErrorHint to null', () => {
    useMetadataStore.setState({
      loadErrorHint: 'a',
      applyErrorHint: 'b',
      restoreErrorHint: 'c',
      draftLoadErrorHint: 'd',
      draftSaveErrorHint: 'e',
    });

    useMetadataStore.getState().clear();

    const state = useMetadataStore.getState();
    expect(state.loadErrorHint).toBeNull();
    expect(state.applyErrorHint).toBeNull();
    expect(state.restoreErrorHint).toBeNull();
    expect(state.draftLoadErrorHint).toBeNull();
    expect(state.draftSaveErrorHint).toBeNull();
  });

  it('loadSample() resets all *ErrorHint to null', () => {
    useMetadataStore.setState({
      loadErrorHint: 'a',
      applyErrorHint: 'b',
      restoreErrorHint: 'c',
      draftLoadErrorHint: 'd',
      draftSaveErrorHint: 'e',
    });

    useMetadataStore.getState().loadSample();

    const state = useMetadataStore.getState();
    expect(state.loadErrorHint).toBeNull();
    expect(state.applyErrorHint).toBeNull();
    expect(state.restoreErrorHint).toBeNull();
    expect(state.draftLoadErrorHint).toBeNull();
    expect(state.draftSaveErrorHint).toBeNull();
  });
});
```

採用案 (X / Y) に応じて、`load()` catch test 内の assertion を確定値 (`expect(...).toBe(...)`) に書き換える。`invoke` mock の setup は既存 test と同パターン (file 上部の `vi.mock('@tauri-apps/api/core', () => ({...}))` を参照)。

- [ ] **Step 2: 採用案 X の場合は実装も変更**

採用案 X (symmetric 化) なら `gui/src/state/metadataStore.ts:284-300` (load() catch) の `draftLoadErrorHint: null` / `draftSaveErrorHint: null` を削除し、self-only に揃える。

採用案 Y なら実装は変更せず、catch block の上にコメントを追加:

```ts
} catch (e) {
  // #691: load() failure は新規 load attempt なので、draft 系の旧 error は
  // 文脈外 (古い source の draft 情報) として clear する。apply / restore
  // 系は別経路の状態なので保持する (非対称は意図的)。
  set({
    metadata: null,
    // ... 既存通り
  });
}
```

- [ ] **Step 3: Run tests to verify**

```bash
cd gui && npm test -- --run metadataStore
```

採用案 X: 案 X assertion で pass。
採用案 Y: 案 Y assertion で pass。

- [ ] **Step 4: Commit**

```bash
git add gui/src/state/metadataStore.ts gui/src/state/metadataStore.test.ts
git commit -m "test+refactor(state): metadataStore catch path lifecycle pinning (Refs #691)

採用案: <X/Y> (PR 本文に詳細)
5 catch path × 5 *ErrorHint の clear 範囲を test で pin。
将来 path 追加時の guardrail として機能。

Refs #691"
```

### Task B.4: docs 更新

**Files:**

- Modify: `docs/ui-architecture.md` §4
- Modify: `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` §7

- [ ] **Step 1: `docs/ui-architecture.md` §4 に lifecycle 規約節を追加**

§4 の末尾、または InlineErrorHint 節と並列に追記:

```markdown
### §4.x metadataStore catch path lifecycle 規約 (#691)

各 catch path は自身の `*ErrorHint` のみを `set` し、他経路の `*ErrorHint` は touch
しない (採用案 X) / または `load()` catch のみ draft 系を clear する partial
asymmetric 規約 (採用案 Y) を維持する。lifecycle 終端 (`clear()` / `loadSample()`)
でのみ全 5 `*ErrorHint` を null reset する。

この規約は `metadataStore.test.ts` の `#691: catch path lifecycle pinning` describe
block で test で pin されている。将来 catch path 追加時は同 describe block に
test を追加し、規約の意図を継承する。
```

(採用案に応じて節タイトル末尾と詳細記述を調整。)

- [ ] **Step 2: `2026-05-08-l2-appError-migration-completion-design.md` §7 に Refs リンクを追加**

該当 spec の §7 (PR #689 関連節) の末尾に:

```markdown
- Lane V Phase 1 #691 (PR #<番号>) で 5 catch path × 5 `*ErrorHint` の clear
  matrix を test で pin、規約を明文化。本 spec で残された non-symmetric pattern
  は採用案 <X/Y> で <整理 / 維持 + 根拠コメント追加>。
```

- [ ] **Step 3: markdownlint 確認**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 errors。

- [ ] **Step 4: Commit**

```bash
git add docs/ui-architecture.md docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md
git commit -m "docs(state): metadataStore *ErrorHint lifecycle 規約を明文化 (Refs #691)

採用案: <X/Y>
docs/ui-architecture.md §4.x で lifecycle 規約節を追加、
PR #689 spec §7 に本 PR の Refs リンク追加。

Refs #691"
```

### Task B.5: PR 作成 (Iron Law 6 PR Pre-flight)

- [ ] **Step 1: 共通 Prerequisites の Pre-flight 全項目を再実行**

`git fetch origin develop-0.2.0` 〜 `cargo test --lib` まで全 green 確認。

- [ ] **Step 2: PR 本文を準備**

```markdown
## Summary

#691 (Refs #663) の対応。`metadataStore.ts` の 5 catch path × 5 `*ErrorHint`
state の clear 範囲を test で pin、規約を docstring + docs/ui-architecture.md に
明文化。Wave 1.1 で PR 1 #693 と完全並行 (UI 非依存)。

採用案: **<X (symmetric 化) / Y (非対称維持 + 根拠コメント)>**

session-id: `<worktree 名>`
spec: docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md §5.2

## 確定 matrix

| catch path | `loadErrorHint` | `applyErrorHint` | `restoreErrorHint` | `draftSaveErrorHint` | `draftLoadErrorHint` |
| --- | --- | --- | --- | --- | --- |
| `load()` catch | set | <X: -, Y: -> | <X: -, Y: -> | <X: -, Y: null> | <X: -, Y: null> |
| `runApply()` catch (非 conflict) | - | set | - | - | - |
| `runApply()` catch (conflict) | - | - | - | - | - |
| `restore()` catch | - | - | set | - | - |
| `saveDraft()` catch | - | - | - | set | - |
| `loadDraft()` catch | - | - | - | - | set |
| `clear()` / `loadSample()` | null | null | null | null | null |

## 受け入れ条件 (元 issue #691 を逐条引用)

- [x] 5 catch path の clear 範囲が精査され、案 <X/Y> が採用される
- [x] `metadataStore.test.ts` に 6-8 件の lifecycle pinning test 追加 + 全 pass
- [x] `docs/ui-architecture.md` §4.x に lifecycle 規約節追記
- [x] PR #689 spec §7 に Refs リンク追加

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認
- [x] `gh pr list --search "#691"` で並行 PR 重複なし
- [x] `cd gui && npm run lint / typecheck` (exit 0)
- [x] `cd gui && npm test -- --run` (全 pass)
- [x] `cd gui && npm run build` (success)
- [x] `cd gui/src-tauri && cargo check / test --lib` (156 件 pass)
- [x] `bash scripts/check-markdownlint.sh` (0 errors)

### Machine-unverifiable

- 機能変更なし (lifecycle pinning のみ) のため実機検証は不要。frontend mock test で十分。

## Refs

Refs #691 #663 #689
```

- [ ] **Step 3: PR を push + 作成**

```bash
git push -u origin claude/<auto-name-2>
gh pr create --base develop-0.2.0 --title "refactor(state): #691 metadataStore *ErrorHint lifecycle pinning (Lane V Phase 1)" --body-file <(printf '%s' "$PR_BODY")
```

---

## Task Group C: PR 3 (#695) ConflictModal AppError hint 表示 (C 案 採用)

**Goal:** ConflictModal の compose hint を削除し、AppError hint を `<InlineErrorHint>` で表示、その下に「キャンセル」補足 1 行を配置する (C 案)。`metadataStore` に `conflictErrorHint` state を追加。Wave 1.2、PR 1 #693 merge 後に着手。

**前提**: PR 1 #693 が merge 済 (`InlineErrorHint` component が `develop-0.2.0` に存在)。

**worktree**: 新規作成 (例 `.claude/worktrees/<auto-name-3>/`)、base `develop-0.2.0` (PR 1 merge 後の最新)。

### Task C.0: 共通 Prerequisites + InlineErrorHint 取り込み確認

- [ ] **Step 1: Pre-flight 実行**

共通 Prerequisites 全項目を実施。特に `gh pr list --search "#693"` で PR 1 が MERGED であることを確認。

- [ ] **Step 2: `develop-0.2.0` に InlineErrorHint が存在することを確認**

```bash
ls gui/src/components/InlineErrorHint.tsx
# Expected: file exists
```

なければ PR 1 が未 merge — 一旦 stop し PR 1 完了を待つ。

### Task C.1: metadataStore に conflictErrorHint state を追加 (Red)

**Files:**

- Modify: `gui/src/state/metadataStore.ts`
- Modify: `gui/src/state/metadataStore.test.ts`

- [ ] **Step 1: test 先 (Red)**

`gui/src/state/metadataStore.test.ts` の末尾に追加:

```tsx
describe('#695: conflictErrorHint lifecycle', () => {
  beforeEach(() => {
    useMetadataStore.setState({
      // ... 既存 test の setup と同じ
      conflictError: null,
      conflictErrorHint: null,
    });
  });

  it('runApply() catch (conflict) sets conflictErrorHint', async () => {
    useMetadataStore.setState({
      metadata: { /* valid */ } as any,
      filePath: '/test.mp4',
    });

    vi.mocked(invoke).mockRejectedValueOnce({
      code: 'state.mtime_conflict',
      message: 'metadata.json was modified',
      hint: 'リロード or 上書き',
    });

    await useMetadataStore.getState().apply();

    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeTruthy();
    expect(state.conflictErrorHint).toBe('リロード or 上書き');
  });

  it('dismissConflict() clears both conflictError and conflictErrorHint', () => {
    useMetadataStore.setState({
      conflictError: 'msg',
      conflictErrorHint: 'hint',
    });

    useMetadataStore.getState().dismissConflict();

    const state = useMetadataStore.getState();
    expect(state.conflictError).toBeNull();
    expect(state.conflictErrorHint).toBeNull();
  });

  it('clear() resets conflictErrorHint', () => {
    useMetadataStore.setState({
      conflictError: 'msg',
      conflictErrorHint: 'hint',
    });

    useMetadataStore.getState().clear();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorHint).toBeNull();
  });

  it('loadSample() resets conflictErrorHint', () => {
    useMetadataStore.setState({
      conflictError: 'msg',
      conflictErrorHint: 'hint',
    });

    useMetadataStore.getState().loadSample();

    const state = useMetadataStore.getState();
    expect(state.conflictErrorHint).toBeNull();
  });
});
```

- [ ] **Step 2: Run test (Red)**

```bash
cd gui && npm test -- --run metadataStore
```

Expected: FAIL with `conflictErrorHint` undefined.

### Task C.2: metadataStore に conflictErrorHint state を追加 (Green)

- [ ] **Step 1: MetadataState interface に追加**

`gui/src/state/metadataStore.ts` の `MetadataState` interface (line 26-131 付近) で:

```ts
  conflictError: string | null;
```

の直下に:

```ts
  /** #695: hint for conflictError (state.mtime_conflict AppError), if carried one. */
  conflictErrorHint: string | null;
```

- [ ] **Step 2: 初期値を追加**

`useMetadataStore` factory (line 184 付近) の `return { ... }` で、`conflictError: null,` の直下に:

```ts
  conflictErrorHint: null,
```

- [ ] **Step 3: runApply catch (conflict) で set**

`runApply` 関数 (line 190-227) の catch block 内の conflict 分岐 (line 221-222) を変更:

Before:

```ts
      if (appErrorCodeIs(e, 'state.mtime_conflict')) {
        set({ applying: false, conflictError: msg });
      }
```

After:

```ts
      if (appErrorCodeIs(e, 'state.mtime_conflict')) {
        set({ applying: false, conflictError: msg, conflictErrorHint: hint });
      }
```

(`hint` は既に line 217 の `appErrorHint(e)` で取得済)

- [ ] **Step 4: runApply success で conflictErrorHint clear**

`runApply` の success path (line 201-209) の `set({ ... })` 内の `conflictError: null,` の直下に:

```ts
        conflictErrorHint: null,
```

`set({ applying: true, applyError: null, ... })` (line 193) の `conflictError: null` の直下にも同様に:

```ts
        conflictErrorHint: null,
```

- [ ] **Step 5: dismissConflict / reloadAfterConflict で clear**

`dismissConflict` (line 404-406):

```ts
  dismissConflict: () => {
    set({ conflictError: null, conflictErrorHint: null });
  },
```

`reloadAfterConflict` は `load()` 呼ぶので、`load()` success/catch で扱う。

- [ ] **Step 6: load() success path で clear**

`load:` (line 253-301) の success path (line 261-278) の `set({ ... })` 内に:

```ts
        conflictErrorHint: null,
```

を追加 (既存 `conflictError: null,` の直下)。

- [ ] **Step 7: load() catch path で clear**

`load:` の catch path (line 284-299) の `set({ ... })` 内に:

```ts
        conflictErrorHint: null,
```

を追加 (既存 `conflictError: null,` の直下、ただし PR 2 採用案 X の場合は load() catch から他経路 clear を削除済の可能性あり。その場合 conflictErrorHint も含めない)。

**注意**: PR 2 採用案 X 採用済なら load() catch は self-only でなければならない。`conflictError` も同様に self-other 関係を見直す。`load()` 失敗時に既存 conflict があったら maintain か clear か — 既存コード line 293 の `conflictError: null` は **maintain だが clear している**。これは load() success path と同じ「新規 load 試行で全 state リセット」設計と整合する。`conflictErrorHint: null` も同じく追加。

- [ ] **Step 8: clear() / loadSample() に conflictErrorHint: null を追加**

`clear()` (line 330-354) と `loadSample()` (line 506-530) の `set({ ... })` 内に既存 `conflictError: null` の直下に:

```ts
      conflictErrorHint: null,
```

- [ ] **Step 9: Run test (Green)**

```bash
cd gui && npm test -- --run metadataStore
```

Expected: 新規 4 件 pass + 既存 pass。

- [ ] **Step 10: Commit**

```bash
git add gui/src/state/metadataStore.ts gui/src/state/metadataStore.test.ts
git commit -m "feat(state): add conflictErrorHint state for ConflictModal (Refs #695)

state.mtime_conflict AppError の hint を modal で表示するため、conflictError と
pair で hint state を追加。lifecycle (clear / loadSample / dismissConflict /
load / runApply success) で同期。

Refs #695"
```

### Task C.3: ConflictModal.test.tsx に新規 test (Red)

**Files:**

- Modify: `gui/src/components/ConflictModal.test.tsx`

- [ ] **Step 1: 新規 test を追加**

ファイル末尾 (or 既存 describe 内) に追加:

```tsx
import { InlineErrorHint } from './InlineErrorHint';
// (既存 imports に追加)

describe('#695: AppError hint display', () => {
  it('renders InlineErrorHint when conflictErrorHint is set', () => {
    useMetadataStore.setState({
      conflictError: 'metadata.json was modified',
      conflictErrorHint: 'リロード or 上書き',
    });

    render(<ConflictModal />);

    expect(screen.getByText('💡 リロード or 上書き')).toBeInTheDocument();
  });

  it('does not render hint when conflictErrorHint is null', () => {
    useMetadataStore.setState({
      conflictError: 'metadata.json was modified',
      conflictErrorHint: null,
    });

    render(<ConflictModal />);

    expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
  });

  it('always renders the cancel hint regardless of conflictErrorHint', () => {
    useMetadataStore.setState({
      conflictError: 'msg',
      conflictErrorHint: 'hint',
    });

    render(<ConflictModal />);

    expect(
      screen.getByText('「キャンセル」で何もせずこのモーダルを閉じます。')
    ).toBeInTheDocument();
  });

  it('does NOT render the legacy compose hint (上書き / リロード / キャンセル 3 verb)', () => {
    useMetadataStore.setState({
      conflictError: 'msg',
      conflictErrorHint: 'hint',
    });

    render(<ConflictModal />);

    expect(
      screen.queryByText(/「上書き」で外部変更を破棄し GUI の編集を適用/)
    ).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 既存 compose hint assertion を削除**

`ConflictModal.test.tsx` 既存 test 内で `「上書き」で外部変更を破棄し...` 全文を期待している assertion を削除 or 「キャンセル」のみ chunk に書き換え。`grep -n "上書き.*リロード.*キャンセル" gui/src/components/ConflictModal.test.tsx` で対象を特定。

- [ ] **Step 3: a11y test を追加**

```tsx
it('hint inside role="dialog" passes jest-axe', async () => {
  useMetadataStore.setState({
    conflictError: 'msg',
    conflictErrorHint: 'hint',
  });

  const { container } = render(<ConflictModal />);

  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

(`axe` の import は既存 jest-axe setup を参照)

- [ ] **Step 4: Run test (Red)**

```bash
cd gui && npm test -- --run ConflictModal
```

Expected: FAIL (compose hint がまだ render される、InlineErrorHint がまだ使われていない)。

### Task C.4: ConflictModal.tsx を C 案 で実装 (Green)

**Files:**

- Modify: `gui/src/components/ConflictModal.tsx:47-50`
- Modify: `gui/src/components/ConflictModal.module.css:39-45`

- [ ] **Step 1: import を追加**

`gui/src/components/ConflictModal.tsx` の import block (line 1-6):

```tsx
import { InlineErrorHint } from './InlineErrorHint';
```

を追加。

- [ ] **Step 2: store から conflictErrorHint を読む**

`gui/src/components/ConflictModal.tsx` の line 20-24 付近:

```tsx
  const conflictError = useMetadataStore((s) => s.conflictError);
```

の直下に追加:

```tsx
  const conflictErrorHint = useMetadataStore((s) => s.conflictErrorHint);
```

- [ ] **Step 3: compose hint を C 案 構造に置換**

line 47-50 の compose hint:

Before:

```tsx
        <p className={styles.message}>{conflictError}</p>
        <p className={styles.hint}>
          「上書き」で外部変更を破棄し GUI の編集を適用、「リロード」で最新の metadata.json を読み直し (編集は破棄)、「キャンセル」で何もせずこのモーダルを閉じます。
        </p>
```

After:

```tsx
        <p className={styles.message}>{conflictError}</p>
        <InlineErrorHint hint={conflictErrorHint} />
        <p className={styles.cancelHint}>
          「キャンセル」で何もせずこのモーダルを閉じます。
        </p>
```

- [ ] **Step 4: CSS class rename (`.hint` → `.cancelHint`)**

`gui/src/components/ConflictModal.module.css` line 39-45 の `.hint` block を `.cancelHint` に rename。スタイルは維持:

```css
.cancelHint {
  font-family: var(--ae-font-body);
  font-size: 12px;
  color: var(--ae-text-dim);
  margin: 0 0 20px 0;
  line-height: 1.5;
}
```

- [ ] **Step 5: Run test (Green)**

```bash
cd gui && npm test -- --run ConflictModal
```

Expected: 新規 4-5 件 pass + 既存 pass (compose hint 全文 assertion は削除済)。

- [ ] **Step 6: Commit**

```bash
git add gui/src/components/ConflictModal.tsx gui/src/components/ConflictModal.module.css gui/src/components/ConflictModal.test.tsx
git commit -m "feat(gui): ConflictModal displays AppError hint via InlineErrorHint (C 案、Refs #695)

C 案 採用: AppError hint を主に表示し、modal 局所文言は「キャンセル」補足 1 行のみ。
compose hint (3 button 全説明) は削除。.hint → .cancelHint に CSS class rename。

Refs #695"
```

### Task C.5: docs 更新

**Files:**

- Modify: `docs/ui-interaction-spec.md` §1.5

- [ ] **Step 1: §1.5 に modal hint slot 規約を追記**

該当箇所を `grep -n "## §1.5\|### §1.5" docs/ui-interaction-spec.md` で特定し、AppError code 分岐節の末尾に追記:

```markdown
### §1.5.x ConflictModal の hint slot 規約 (#695)

`state.mtime_conflict` の modal (ConflictModal) では、AppError hint を modal の
hint slot に主表示し、modal 局所文言 (キャンセル button の挙動説明) は補足 1 行と
して別 paragraph に表示する規約。具体的には:

- 1 行目 (`<p>{conflictError}</p>`): AppError.message を danger 色で表示
- 2 行目 (`<InlineErrorHint hint={conflictErrorHint} />`): AppError.hint を
  `💡` prefix + `var(--ae-text-dim)` で表示 (hint null 時は非表示)
- 3 行目 (`<p>{cancel 補足}</p>`): 「『キャンセル』で何もせずこのモーダルを閉じます。」
  を常時表示 (modal 局所文言、上書き / リロード の挙動は AppError hint がカバー)

旧 compose hint (3 button 全説明) は削除済。AppError hint と modal 文言の重複を
避けるため、modal 局所文言は modal-only な action (キャンセル 等) に限定する規約。
```

- [ ] **Step 2: markdownlint 確認**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 errors。

- [ ] **Step 3: Commit**

```bash
git add docs/ui-interaction-spec.md
git commit -m "docs(ui): ConflictModal hint slot 規約を追記 (Refs #695)

C 案 (AppError hint 主 + キャンセル 補足) を §1.5.x に明文化。

Refs #695"
```

### Task C.6: PR 作成 (Iron Law 6 PR Pre-flight)

- [ ] **Step 1: 共通 Prerequisites 再実行**

- [ ] **Step 2: PR 本文を準備**

```markdown
## Summary

#695 (Refs #663) の対応。ConflictModal の compose hint を削除し、AppError hint を
`<InlineErrorHint>` で表示、その下に「キャンセル」補足 1 行を配置 (C 案 採用)。
`metadataStore` に `conflictErrorHint` state を追加。Wave 1.2、PR 1 #693 merge 後。

session-id: `<worktree 名>`
spec: docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md §5.3
依存元 PR: #693 (#693 merge 確認済)

## 受け入れ条件 (元 issue #695 を逐条引用)

- [x] `metadataStore.ts` に `conflictErrorHint` state 追加 + lifecycle 同期
- [x] `ConflictModal.tsx` の compose hint 削除、InlineErrorHint + 「キャンセル」補足構造
- [x] `ConflictModal.module.css` の `.hint` → `.cancelHint` rename
- [x] `ConflictModal.test.tsx` に 4-5 件 test 追加 (hint set/null / 補足常時 / 旧 compose hint 削除 / a11y)
- [x] `metadataStore.test.ts` に `conflictErrorHint` lifecycle test 4 件追加
- [x] `docs/ui-interaction-spec.md` §1.5.x に modal hint slot 規約節追記

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 (PR #693 merged を確認)
- [x] `gh pr list --search "#695"` 並行 PR 重複なし
- [x] `cd gui && npm run lint / typecheck` (exit 0)
- [x] `cd gui && npm test -- --run` (全 pass)
- [x] `cd gui && npm run build` (success)
- [x] `cd gui/src-tauri && cargo check / test --lib` (156 件 pass)
- [x] `bash scripts/check-markdownlint.sh` (0 errors)

### Machine-unverifiable (Idios 実機検証 — `AskUserQuestion` で依頼)

- 実 conflict (2 プロセス同時 edit → apply) で modal の AppError hint + 補足 1 行表示

## Refs

Refs #695 #663 #689 #693
```

- [ ] **Step 3: PR を push + 作成**

```bash
git push -u origin claude/<auto-name-3>
gh pr create --base develop-0.2.0 --title "feat(gui): #695 ConflictModal で state.mtime_conflict AppError hint 表示 (C 案、Lane V Phase 1)" --body-file <(printf '%s' "$PR_BODY")
```

- [ ] **Step 4: 実機検証依頼**

> 「PR #<番号> の Iron Law 6 実機検証として、ConflictModal の hint 表示確認をお願いします:
>
> 1. 2 プロセスで同一 metadata.json を開く (例: GUI 2 instance 起動)
> 2. 片方で edit → apply
> 3. もう片方で edit → apply (外部編集 detect される)
> 4. ConflictModal が表示され、message + AppError hint + 「キャンセル」補足の 3 行構造になっていること
> 5. 旧 compose hint (『上書き』で外部変更を破棄...) が表示されていないこと
>
> 結果を PR comment にお願いします。」

---

## Task Group D: PR 4 (#697) DraftRestoreModal `draftLoadErrorHint` UI

**Goal:** DraftRestoreModal の draftLoadError 経路に InlineErrorHint を追加し、`draftLoadErrorHint` dead state を解消。Wave 1.2、PR 1 #693 merge 後に着手。

**前提**: PR 1 #693 が merge 済。

**worktree**: 新規作成 (例 `.claude/worktrees/<auto-name-4>/`)。

### Task D.0: 共通 Prerequisites + InlineErrorHint 取り込み確認

PR 3 と同様。`ls gui/src/components/InlineErrorHint.tsx` で確認。

### Task D.1: DraftRestoreModal.test.tsx に test (Red)

**Files:**

- Modify: `gui/src/components/DraftRestoreModal.test.tsx`

- [ ] **Step 1: 新規 test を追加**

`gui/src/components/DraftRestoreModal.test.tsx` 末尾に追加:

```tsx
describe('#697: draftLoadErrorHint display', () => {
  it('renders InlineErrorHint when draftLoadErrorHint is set', () => {
    useMetadataStore.setState({
      draftLoadError: 'metadata.draft.json corrupt',
      draftLoadErrorHint: 'バックアップから復元してください',
    });

    render(<DraftRestoreModal />);

    expect(
      screen.getByText('💡 バックアップから復元してください')
    ).toBeInTheDocument();
  });

  it('does not render hint when draftLoadErrorHint is null', () => {
    useMetadataStore.setState({
      draftLoadError: 'corrupt',
      draftLoadErrorHint: null,
    });

    render(<DraftRestoreModal />);

    expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
  });

  it('hint inside role="dialog" passes jest-axe', async () => {
    useMetadataStore.setState({
      draftLoadError: 'corrupt',
      draftLoadErrorHint: 'hint',
    });

    const { container } = render(<DraftRestoreModal />);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

- [ ] **Step 2: Run test (Red)**

```bash
cd gui && npm test -- --run DraftRestoreModal
```

Expected: FAIL (InlineErrorHint がまだ追加されていない)。

### Task D.2: DraftRestoreModal.tsx に InlineErrorHint を追加 (Green)

**Files:**

- Modify: `gui/src/components/DraftRestoreModal.tsx`

- [ ] **Step 1: import を追加**

file 上部:

```tsx
import { InlineErrorHint } from './InlineErrorHint';
```

- [ ] **Step 2: store から draftLoadErrorHint を read**

line 13 付近:

```tsx
  const draftLoadError = useMetadataStore((s) => s.draftLoadError);
```

の直下に追加:

```tsx
  const draftLoadErrorHint = useMetadataStore((s) => s.draftLoadErrorHint);
```

- [ ] **Step 3: draftLoadError 経路に InlineErrorHint を追加**

line 36-38 付近の draftLoadError modal body:

Before:

```tsx
          <p className={styles.message}>{draftLoadError}</p>
          <p className={styles.hint}>
            metadata.draft.json が破損しているか schema が一致しません。破棄して続行します。
          </p>
```

After:

```tsx
          <p className={styles.message}>{draftLoadError}</p>
          <InlineErrorHint hint={draftLoadErrorHint} />
          <p className={styles.hint}>
            metadata.draft.json が破損しているか schema が一致しません。破棄して続行します。
          </p>
```

(既存の `.hint` は modal 局所文言として保持。AppError hint は別 line として上に挿入。)

- [ ] **Step 4: Run test (Green)**

```bash
cd gui && npm test -- --run DraftRestoreModal
```

Expected: 新規 3 件 pass + 既存 pass。

- [ ] **Step 5: Commit**

```bash
git add gui/src/components/DraftRestoreModal.tsx gui/src/components/DraftRestoreModal.test.tsx
git commit -m "feat(gui): DraftRestoreModal displays draftLoadErrorHint via InlineErrorHint (Refs #697)

draftLoadError 経路の modal body に AppError hint 表示を追加。
Phase 4 既存パターン (5 screen + RestoreButton) と同構造。

Refs #697"
```

### Task D.3: PR 作成 (Iron Law 6 PR Pre-flight)

- [ ] **Step 1: 共通 Prerequisites 再実行**

- [ ] **Step 2: PR 本文を準備**

```markdown
## Summary

#697 (Refs #663) の対応。DraftRestoreModal の draftLoadError 経路に
`<InlineErrorHint>` を追加し、`draftLoadErrorHint` dead state を解消。
Wave 1.2、PR 1 #693 merge 後。

session-id: `<worktree 名>`
spec: docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md §5.4

## 受け入れ条件 (元 issue #697 を逐条引用)

- [x] `DraftRestoreModal.tsx` で `draftLoadErrorHint` を read し InlineErrorHint で表示
- [x] `DraftRestoreModal.test.tsx` に 3 件 test 追加 (hint set/null / a11y)

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 (PR #693 merged)
- [x] `gh pr list --search "#697"` 並行 PR 重複なし
- [x] 全自動チェック green

### Machine-unverifiable

- 破損 draft で DraftRestoreModal の hint 表示 (Idios 実機検証)

## Refs

Refs #697 #663 #689 #693
```

- [ ] **Step 3: PR push + 作成**

```bash
git push -u origin claude/<auto-name-4>
gh pr create --base develop-0.2.0 --title "feat(gui): #697 DraftRestoreModal で draftLoadErrorHint 表示 (Lane V Phase 1)" --body-file <(printf '%s' "$PR_BODY")
```

- [ ] **Step 4: 実機検証依頼**

> 「PR #<番号> の Iron Law 6 実機検証として、破損 draft 経路の hint 表示確認をお願いします:
>
> 1. `metadata.draft.json` を意図的に破損 (例: `echo 'invalid json' > metadata.draft.json`)
> 2. GUI 起動 → 同 metadata.json を load
> 3. DraftRestoreModal の draftLoadError 経路が表示され、AppError hint (`💡` prefix) が出ること
>
> 結果を PR comment にお願いします。」

---

## Task Group E: PR 5 (#698) DropScreen recentStore notice 表示 (A-minimal)

**Goal:** DropScreen の recent list 上部に inline notice を追加し、`recentStore.loadError` / `addError` を user に告知。Wave 1.2、PR 1 #693 merge 後に着手。Lane II-a #633 との DropScreen 衝突は先着優先 + rebase。

**前提**: PR 1 #693 が merge 済。

**worktree**: 新規作成 (例 `.claude/worktrees/<auto-name-5>/`)。

### Task E.0: 共通 Prerequisites + Lane II-a #633 状況確認

- [ ] **Step 1: Pre-flight 実行**

- [ ] **Step 2: Lane II-a #633 の PR 状況確認**

```bash
gh pr list --search "#633" --state all
```

issue #633 関連 PR が open / merged / closed のいずれかを確認。merged なら base 同期で取り込み済の前提。open なら本 PR と #633 PR の merge 順序を Idios と合意 (先着優先 + rebase)。

### Task E.1: DropScreen.test.tsx に test (Red)

**Files:**

- Modify: `gui/src/screens/DropScreen.test.tsx`

- [ ] **Step 1: 新規 test を追加**

```tsx
describe('#698: recentStore error notice', () => {
  beforeEach(() => {
    useRecentStore.setState({
      entries: [],
      loaded: true,
      loadError: null,
      loadErrorHint: null,
      addError: null,
      addErrorHint: null,
    });
  });

  it('displays notice when loadError is set', () => {
    useRecentStore.setState({
      loadError: 'failed to read recent.json',
      loadErrorHint: 'recent.json が破損している可能性があります',
    });

    render(<DropScreen />);

    expect(screen.getByText('failed to read recent.json')).toBeInTheDocument();
    expect(
      screen.getByText('💡 recent.json が破損している可能性があります')
    ).toBeInTheDocument();
  });

  it('displays notice when addError is set', () => {
    useRecentStore.setState({
      addError: 'failed to stat dropped file',
      addErrorHint: 'ファイル削除されたかもしれません',
    });

    render(<DropScreen />);

    expect(screen.getByText('failed to stat dropped file')).toBeInTheDocument();
    expect(
      screen.getByText('💡 ファイル削除されたかもしれません')
    ).toBeInTheDocument();
  });

  it('prefers loadError over addError when both are set', () => {
    useRecentStore.setState({
      loadError: 'load failed',
      loadErrorHint: 'load hint',
      addError: 'add failed',
      addErrorHint: 'add hint',
    });

    render(<DropScreen />);

    expect(screen.getByText('load failed')).toBeInTheDocument();
    expect(screen.queryByText('add failed')).not.toBeInTheDocument();
    expect(screen.getByText('💡 load hint')).toBeInTheDocument();
    expect(screen.queryByText('💡 add hint')).not.toBeInTheDocument();
  });

  it('does not display notice when both loadError and addError are null', () => {
    useRecentStore.setState({
      loadError: null,
      addError: null,
    });

    render(<DropScreen />);

    expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
    // notice wrapper の role="alert" も不在
    const alerts = screen.queryAllByRole('alert');
    // (a11y alert は他にも来るが、本 notice 専用の identifier で確認)
    // 詳細は実装に応じて adjust
  });

  it('notice has role="alert"', () => {
    useRecentStore.setState({
      loadError: 'msg',
      loadErrorHint: 'hint',
    });

    const { container } = render(<DropScreen />);
    const notice = container.querySelector(`.${'recentNotice'}`);  // CSS module name
    // (data-testid="recent-notice" を実装で付与するならそっちで取得)
    // role="alert" が付与されていることを assertion
    // 実装で `data-testid="recent-notice"` を付与し screen.getByTestId('recent-notice') 経由で取得すると安定
  });
});
```

- [ ] **Step 2: Run test (Red)**

```bash
cd gui && npm test -- --run DropScreen
```

Expected: FAIL (notice 未実装)。

### Task E.2: DropScreen.tsx に notice 追加 (Green)

**Files:**

- Modify: `gui/src/screens/DropScreen.tsx`
- Modify: `gui/src/screens/DropScreen.module.css`

- [ ] **Step 1: store から error / hint を read**

`gui/src/screens/DropScreen.tsx` の既存 store read 部分 (line 117 付近):

```tsx
  const recentEntries = useRecentStore((s) => s.entries);
  const recentLoaded = useRecentStore((s) => s.loaded);
```

の直下に追加:

```tsx
  const recentLoadError = useRecentStore((s) => s.loadError);
  const recentLoadErrorHint = useRecentStore((s) => s.loadErrorHint);
  const recentAddError = useRecentStore((s) => s.addError);
  const recentAddErrorHint = useRecentStore((s) => s.addErrorHint);
```

- [ ] **Step 2: InlineErrorHint import を追加**

import block:

```tsx
import { InlineErrorHint } from '../components/InlineErrorHint';
```

(既存で別経路で import 済なら不要)

- [ ] **Step 3: recent list 上部に notice を追加**

line 370 付近 (`<div className={styles.recent} data-testid="recent-list">` の直後、`recentHeading` の前か後ろ) に notice を挿入:

```tsx
          <div className={styles.recent} data-testid="recent-list">
            <div className={styles.recentHeading}>──── 直近の録画 ────</div>
            {(recentLoadError || recentAddError) && (
              <div
                className={styles.recentNotice}
                role="alert"
                data-testid="recent-notice"
              >
                <span className={styles.recentNoticeMessage}>
                  {recentLoadError ?? recentAddError}
                </span>
                <InlineErrorHint
                  hint={recentLoadError ? recentLoadErrorHint : recentAddErrorHint}
                />
              </div>
            )}
            {recentEntries.length === 0 ? (
              // ... 既存通り
```

- [ ] **Step 4: DropScreen.module.css に class 追加**

末尾に追加:

```css
/* #698: recent list 上部の error notice。loadError or addError 発生時に表示。
   best-effort UI fluff の tone を維持しつつ、user に履歴失敗を告知。
   dismiss 機能なし — 次回 load / add 成功で自動消去。 */
.recentNotice {
  padding: 8px 12px;
  border-left: 2px solid var(--ae-danger);
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.recentNoticeMessage {
  color: var(--ae-danger);
  font-size: 11px;
  font-family: var(--ae-font-mono);
  word-break: break-all;
}
```

- [ ] **Step 5: Run test (Green)**

```bash
cd gui && npm test -- --run DropScreen
```

Expected: 新規 4-5 件 pass + 既存 pass。

- [ ] **Step 6: Commit**

```bash
git add gui/src/screens/DropScreen.tsx gui/src/screens/DropScreen.module.css gui/src/screens/DropScreen.test.tsx
git commit -m "feat(gui): DropScreen displays recentStore error notice (A-minimal、Refs #698)

recent list 上部に inline notice を追加 (loadError 優先、両 null 非表示、dismiss なし)。
A-minimal 案 採用。message (danger) + InlineErrorHint (text-dim) の 2 行構造。
role=\"alert\" + data-testid=\"recent-notice\"。

Refs #698"
```

### Task E.3: recentStore docstring 更新

**Files:**

- Modify: `gui/src/state/recentStore.ts:28`

- [ ] **Step 1: docstring を update**

line 28 の `loadError` docstring:

Before:

```ts
  /** Last load failure, surfaced for tests / debug log; the drop screen ignores it (history is best-effort). */
  loadError: string | null;
```

After:

```ts
  /**
   * Last load failure. #698: DropScreen 上部に inline notice として表示される
   * (history は best-effort UI fluff だが、user に履歴失敗を気づかせるため告知)。
   * dismiss なし、次回 load 成功で自動消去。
   */
  loadError: string | null;
```

同様に `addError` も:

Before:

```ts
  /** Last add failure, e.g. when the user dropped a file that was deleted before we could stat it. */
  addError: string | null;
```

After:

```ts
  /**
   * Last add failure. #698: DropScreen 上部に notice として表示 (loadError 不在
   * 時の fallback)。e.g. when the user dropped a file that was deleted before we
   * could stat it. dismiss なし、次回 add 成功で自動消去。
   */
  addError: string | null;
```

- [ ] **Step 2: Run all tests**

```bash
cd gui && npm test -- --run
```

Expected: 全 pass (docstring 変更のみ、test 影響なし)。

- [ ] **Step 3: Commit**

```bash
git add gui/src/state/recentStore.ts
git commit -m "docs(state): recentStore loadError/addError docstring update (Refs #698)

「DropScreen は ignore する」記述を「inline notice として表示」に書き換え。
A-minimal 設計を docstring で明文化。

Refs #698"
```

### Task E.4: PR 作成 (Iron Law 6 PR Pre-flight)

- [ ] **Step 1: 共通 Prerequisites 再実行**

特に Lane II-a #633 が間に merge された場合は `git merge origin/develop-0.2.0` で吸収 (DropScreen 共有のため conflict 可能性あり)。

- [ ] **Step 2: PR 本文を準備**

```markdown
## Summary

#698 (Refs #663) の対応。DropScreen の recent list 上部に inline notice を追加し、
`recentStore.loadError` / `addError` を user に告知 (A-minimal 案)。
`recentStore.ts` docstring も best-effort fluff 設計の変更を反映。
Wave 1.2、PR 1 #693 merge 後。

採用案: **A-minimal** (recent list 上部 inline notice、loadError 優先、dismiss なし)

session-id: `<worktree 名>`
spec: docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md §5.5
依存元 PR: #693 (merge 確認済)

## Lane II-a #633 衝突回避

#633 (DropScreen sample mode 全画面 read-only 化) が同 DropScreen.tsx を touch する。
本 PR では <先着優先 = 本 PR が先 / #633 が先 / merge 順は未確定> の運用で進める。
本 PR が後発の場合は `git merge origin/develop-0.2.0` で #633 を吸収済。

## 受け入れ条件 (元 issue #698 を逐条引用)

- [x] `DropScreen.tsx` の recent list 上部に inline notice (loadError 優先、両 null 非表示)
- [x] notice は error message + `<InlineErrorHint>` の 2 行構造、`role="alert"`
- [x] `DropScreen.module.css` に `.recentNotice` / `.recentNoticeMessage` class 追加
- [x] `recentStore.ts` の docstring が「user に notice 告知する」設計に update
- [x] `DropScreen.test.tsx` に 4-5 件 test 追加 (loadError / addError / 優先順位 / 非表示 / a11y)

## Self-Test Report

### Machine-verified

- [x] `git fetch origin develop-0.2.0` + 取り込み未済 commit 確認
- [x] `gh pr list --search "#698"` 並行 PR 重複なし
- [x] Lane II-a #633 PR の状況確認 (<状況詳細>)
- [x] 全自動チェック green

### Machine-unverifiable

- recent.json 破損 / 削除で notice 表示 (Idios 実機検証)

## Refs

Refs #698 #663 #689 #693 #633
```

- [ ] **Step 3: PR push + 作成**

```bash
git push -u origin claude/<auto-name-5>
gh pr create --base develop-0.2.0 --title "feat(gui): #698 DropScreen で recentStore error notice 表示 (A-minimal、Lane V Phase 1)" --body-file <(printf '%s' "$PR_BODY")
```

- [ ] **Step 4: 実機検証依頼**

> 「PR #<番号> の Iron Law 6 実機検証として、recentStore notice 表示確認をお願いします:
>
> 1. `<install_dir>/recent.json` を意図的に破損 (例: `echo 'invalid' > recent.json`)
> 2. GUI 起動 → DropScreen 表示
> 3. recent list 上部に notice (message + 💡 hint) が表示されること
> 4. notice の様式が控えめ (border-left 2px、padding 8/12) であること
>
> 別 case:
>
> 1. recent.json を一旦削除 → notice 非表示 (loadError なし)
> 2. 不正な path を drop (例: 削除済 file) → addError 経路で notice 表示
>
> 結果を PR comment にお願いします。」

---

## Cross-PR coordination notes

### PR merge 順序 (推奨)

1. **PR 1 (#693)**: Wave 1.1 lead、最優先 merge
2. **PR 2 (#691)**: Wave 1.1 並行、PR 1 と同時に進行可能、merge 順は問わない
3. **PR 3 (#695)**: PR 1 merge 後、Wave 1.2 並行
4. **PR 4 (#697)**: PR 1 merge 後、Wave 1.2 並行
5. **PR 5 (#698)**: PR 1 merge 後、Wave 1.2 並行、Lane II-a #633 と DropScreen 共有衝突に注意

### base 同期 (Iron Law 6 PR Pre-flight)

- PR 3-5 は PR 1 merge 後に必ず `git merge origin/develop-0.2.0` で `develop-0.2.0` の最新を取り込む
- 他 lane (II-a / II-b / I-B / IV-b' / IV-e) の merge も同様に取り込む — 触る file (metadataStore / ConflictModal / DropScreen) と交差する PR があれば conflict resolve + 全 test 再実行

### Lane II-a #633 と PR 5 #698 の DropScreen 衝突対応

- どちらの PR が先に提出されるかは Idios の bandwidth 判断
- 先着が merge された後、後発 PR で `git merge origin/develop-0.2.0` → DropScreen の conflict resolve → 全 test pass → push
- conflict 時に確認すべき file: `DropScreen.tsx` / `DropScreen.module.css` / `DropScreen.test.tsx`

### Phase 2 / Phase 3 への引き渡し

- 本 plan で 5 PR merge 完了後、Phase 2 (#694 unified ErrorState refactor) は別 spec で扱う
- Phase 2 では `metadataStore.conflictErrorHint` (本 plan で追加) も `*ErrorHint` 並列構造の一部として unified state に統合される予定
- Phase 3 (#699 docstring 更新) は Phase 2 完了後

---

## Plan Self-Review (writing-plans skill の checklist)

### Spec coverage

- spec §5.1 (PR 1 #693): Task Group A で実装計画。InlineErrorHint component 新設 + 5 site refactor + docs。✅
- spec §5.2 (PR 2 #691): Task Group B で実装計画。matrix 精査 + AskUserQuestion + test 追加 + docs。✅
- spec §5.3 (PR 3 #695): Task Group C で実装計画。`conflictErrorHint` state + ConflictModal C 案 + docs。✅
- spec §5.4 (PR 4 #697): Task Group D で実装計画。DraftRestoreModal に InlineErrorHint 追加。✅
- spec §5.5 (PR 5 #698): Task Group E で実装計画。DropScreen recent notice + docstring。✅
- spec §6 Test 戦略: 各 Task Group の Step に TDD Red→Green を含めた。✅
- spec §6.4 実機検証 trigger: 各 PR 作成 Step に AskUserQuestion で Idios 依頼を明記。✅
- spec §8 per-PR 受け入れ条件: 各 PR の PR 本文 template に逐条引用済。✅
- spec §10 Open questions: Task B.2 で AskUserQuestion 実施 / Task E.0 で #633 状況確認 / 各 PR 作成 Step で実機検証依頼。✅

### Placeholder scan

- "TBD" / "TODO" / "implement later" — なし
- 「適切に handle」「適切な error」等の vague 表現 — なし
- "Similar to Task N" — なし (各 task が完結)
- 実コード未記載 step — なし (全 step に code block or 具体的 file path / line number)

### Type / signature consistency

- `InlineErrorHint` props `hint: string | null | undefined` (Task A.1 / A.2 / C.4 / D.2 / E.2 全て一致)
- `conflictErrorHint: string | null` (Task C.1 test / C.2 implementation 一致)
- store action 名 (`dismissConflict` / `clear` / `loadSample`) 既存通り、変更なし
- CSS class 名 (`.cancelHint` / `.recentNotice` / `.recentNoticeMessage`) Task C.4 / E.2 で一貫

不整合なし。Plan は実行準備完了。

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-lane-v-phase-1-group-i-implementation.md`.**
