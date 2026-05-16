# #676 — GUI 5 画面横断 file path 表示統一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5 画面 (drop / detecting / complete / preview / export) で「ファイル名主表示 + 親ディレクトリ副表示」の 2 段構造に統一し、同名ファイルの識別を可能にする。

**Architecture:** Bottom-up approach A — 共有 util (`splitPath`) + 共有 CSS module + 横断 doc §1.6 を先に確定させてから、画面別に TDD で 1 chapter = 1 commit を積み上げる。各 chapter は独立 commit にして review-pr の per-finding 摘出を容易にする。最後に integration smoke test + 全 CI gate (lint / typecheck / test / build / cargo check) で締める。

**Tech Stack:** TypeScript / React 19 / Vite / CSS Modules / Zustand / vitest / @testing-library/react / jest-axe / markdownlint-cli2

**Spec:** [docs/superpowers/specs/2026-05-15-676-cross-screen-path-display-design.md](../specs/2026-05-15-676-cross-screen-path-display-design.md)

**Gating:** Lane V Phase 2 (#694) merged via PR #745 (commit 7b65bf4) — 5 screen 編集の base 安定済。

**Task 依存関係**: Task 1-3 が foundation (任意順だが互いに独立) → Task 4-8 (画面別、任意順、ただし Task 1-3 完了後) → Task 9 (integration + final verify、Task 4-8 完了後)。

---

## Task 1: `splitPath()` util の TDD 実装

**Files:**

- Modify: `gui/src/utils/path.ts` (既存ファイルに関数追加、末尾)
- Test: `gui/src/utils/path.test.ts` (既存ファイルに describe ブロック追加、末尾)

- [ ] **Step 1: 失敗するテストを書く**

`gui/src/utils/path.test.ts` の末尾に追加:

```ts
import { splitPath } from './path';

describe('splitPath', () => {
  it('splits a Windows path', () => {
    expect(splitPath('E:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'E:\\videos' });
  });

  it('splits a POSIX path', () => {
    expect(splitPath('/tmp/foo.mp4'))
      .toEqual({ fileName: 'foo.mp4', parentDir: '/tmp' });
  });

  it('strips \\\\?\\ prefix before splitting', () => {
    expect(splitPath('\\\\?\\C:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:\\videos' });
  });

  it('returns empty parentDir for separator-less path', () => {
    expect(splitPath('foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: '' });
  });

  it('returns both empty for empty string', () => {
    expect(splitPath('')).toEqual({ fileName: '', parentDir: '' });
  });

  it('handles drive-root file', () => {
    expect(splitPath('C:\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:' });
  });
});
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/utils/path.test.ts 2>&1 | tail -20
```

Expected output:

```text
FAIL  src/utils/path.test.ts
  splitPath > splits a Windows path
    SyntaxError: ... splitPath is not exported ...
```

(エラーメッセージは正確に一致しなくてよい。`splitPath` 未定義 / 未 export の旨であれば pass)

- [ ] **Step 3: `splitPath` を実装**

`gui/src/utils/path.ts` の末尾 (`joinPath` の後) に追加:

```ts
/**
 * 絶対 path を fileName (basename) と parentDir に分解する。
 * Windows `\\?\` 拡張長 prefix は内部で {@link stripExtendedPathPrefix} を通す。
 * セパレータ末尾 / セパレータなし / parentDir 空 (= drive root) の edge case
 * もすべて空文字列にフォールバックする (例外を投げない、UI 表示用)。
 *
 * #676 — 5 画面 (drop / detecting / complete / preview / export) のファイルパス
 * 表示で共通利用。詳細は docs/ui-interaction-spec.md §1.6 参照。
 *
 * 例:
 *  - "E:\\videos\\foo.mkv"  → { fileName: "foo.mkv",  parentDir: "E:\\videos" }
 *  - "/tmp/foo.mp4"         → { fileName: "foo.mp4",  parentDir: "/tmp" }
 *  - "\\\\?\\C:\\foo.mkv"   → { fileName: "foo.mkv",  parentDir: "C:\\" }
 *  - "foo.mkv"              → { fileName: "foo.mkv",  parentDir: "" }
 *  - ""                     → { fileName: "",         parentDir: "" }
 */
export function splitPath(absPath: string): { fileName: string; parentDir: string } {
  if (!absPath) return { fileName: '', parentDir: '' };
  const normalized = stripExtendedPathPrefix(absPath);
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx < 0) return { fileName: normalized, parentDir: '' };
  return {
    fileName: normalized.slice(idx + 1),
    parentDir: normalized.slice(0, idx),
  };
}
```

- [ ] **Step 4: テストが通ることを確認**

```bash
cd gui && npx vitest run src/utils/path.test.ts 2>&1 | tail -10
```

Expected output:

```text
PASS  src/utils/path.test.ts
  splitPath (6 tests) 6 passed
Test Files  1 passed (1)
     Tests  ... passed
```

- [ ] **Step 5: lint + typecheck**

```bash
cd gui && npm run lint src/utils/path.ts src/utils/path.test.ts 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5
```

Expected: 0 error。

- [ ] **Step 6: Commit**

```bash
git add gui/src/utils/path.ts gui/src/utils/path.test.ts
git commit -F - <<'EOF'
feat(gui): #676 splitPath() util を追加 (path.ts)

絶対 path を { fileName, parentDir } に分解する純粋関数。
stripExtendedPathPrefix で \\?\ prefix を除去してから lastIndexOf
('/' or '\\') で分割。空文字列 / drive root / セパレータなしの
edge case は空文字列フォールバック (例外不投げ、UI 表示用)。

5 画面横断 file path 表示統一 (Lane III / Group E) の foundation。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 2: `path-display.module.css` 共有 CSS module 新設

**Files:**

- Create: `gui/src/styles/path-display.module.css`

CSS Module は単独テストしない (consumer 画面の screen test で間接的に検証される)。

- [ ] **Step 1: CSS module 新規作成**

`gui/src/styles/path-display.module.css`:

```css
/*
 * #676 — 5 画面 (drop / detecting / complete / preview / export) で共通の
 * 「ファイル名 + 親ディレクトリ」2 段表示。primary 側のフォントサイズは
 * 画面側 (e.g. DropScreen.module.css `.selectedName`) で指定し、本 module
 * は色味と truncate 規約のみ提供する。
 *
 * docs/ui-interaction-spec.md §1.6 「ファイルパス表示の原則」も参照。
 */

.pathDisplay {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0; /* flex 子のとき overflow を効かせるため */
}

.pathSecondary {
  font-family: var(--ae-font-mono);
  font-size: 11px;
  color: var(--ae-text-dim);
  /* left-side truncation (PR #655 .recentName と同設計):
     direction:rtl で ellipsis 位置を左に / unicode-bidi:plaintext で
     文字自体は LTR 描画を維持 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
  unicode-bidi: plaintext;
  min-width: 0;
}
```

- [ ] **Step 2: stylelint / typecheck (CSS Module の型生成を確認)**

```bash
cd gui && npm run typecheck 2>&1 | tail -5
```

Expected: 0 error。CSS Module は consumer がいないので import エラーは出ない。

- [ ] **Step 3: Commit**

```bash
git add gui/src/styles/path-display.module.css
git commit -F - <<'EOF'
feat(gui): #676 path-display.module.css 共有 CSS module を新設

5 画面 (drop / detecting / complete / preview / export) のファイルパス
表示で共通利用する CSS Module を新設:

- .pathDisplay: container (flex column + min-width:0)
- .pathSecondary: 親 dir 行 (11px / dim / mono、RTL ellipsis truncate)

primary 行 (fileName) の font-size は各画面の既存タイポグラフィ階層に
従うため CSS Module 側では指定しない。truncate ルールは PR #655 の
.recentName と同一設計 (direction:rtl + unicode-bidi:plaintext)。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 3: `ui-interaction-spec.md §1.6` 新設 + `a11y-policy.md` クロスリファレンス

**Files:**

- Modify: `docs/ui-interaction-spec.md` (§1.5 の直後に §1.6 を新設)
- Modify: `docs/a11y-policy.md` (`## disabled 理由表示` の直下にクロスリファレンス 1 節追加)

doc は markdownlint で検証する (`bash scripts/check-markdownlint.sh`)。

- [ ] **Step 1: `docs/ui-interaction-spec.md §1.6` を新設**

`docs/ui-interaction-spec.md` の `## 2. 画面別 UI 部品状態機械` (line 131) の **直前**に以下を挿入:

````markdown
### 1.6 ファイルパス表示の原則 (#676)

**原則**: ユーザーが現在扱っている動画ファイルを「どのフォルダのどのファイルか」識別できるよう、
5 画面 (drop / detecting / complete / preview / export) のすべての主要表示領域で
**絶対 path** を可視化する。fileName だけの表示は禁止 (同名ファイル区別不能のため)。

| 観点 | 規定 |
| --- | --- |
| 表示形式 | **fileName 主表示 (primary) + 親ディレクトリ副表示 (secondary)** の 2 段構造 |
| primary 行 | fileName のみ。font-size は各画面のタイポグラフィ階層に従う (13-16px、`--ae-text-bright`) |
| secondary 行 | parent dir のみ。`gui/src/styles/path-display.module.css` の `.pathSecondary` クラスを使用 (11px / `--ae-text-dim` / `--ae-font-mono`) |
| truncate | secondary 行は左側省略 (RTL ellipsis + `unicode-bidi:plaintext`)。`.pathSecondary` に集約 |
| hover ツールチップ | 必ず container `<div>` に `title={fullPath}` を付与。primary/secondary 個別ではなく container 1 個 |
| path source-of-truth | drop=`info.path` / detecting=`selectedVideoPath` / complete・preview・export=`videoSource` (= `selectedVideoPath ?? metadata.source`) |
| path 分解 | `gui/src/utils/path.ts` の `splitPath(absPath)` で `{fileName, parentDir}` を取得 (例外不投げ) |
| parentDir 空 | drive root などで parentDir が空文字列のとき、secondary 行は非表示 (primary 単独) |
| data-testid | container に `<screen>-path` を基本とする。1 画面に複数 path 表示があるとき or phase 固有のとき context 接尾辞を入れる (例: `drop-selected-path` は `phase=selected` 限定 / `detecting-path` (running) と `detecting-error-path` (error view) で区別) |
| a11y | `aria-label` 等の screen reader 専用属性は新規追加しない (a11y-policy.md 準拠)。`title` 属性 + visible text のみで識別性を担保 |
| recent list (§2.1.3) | **例外**: 行 layout 上 1 行 (フルパス + 左側省略) を維持。PR #655 で確立した `.recentName` をそのまま使用。本 §1.6 の 2 段構造は適用しない |

**アンチパターン**:

- fileName のみで親 dir を表示しない (#676 報告の SelectedCard / Detecting の旧実装が該当)
- `metadata.source` を直に文字列バインドし truncate / title を付けない (#676 報告の CompleteScreen 旧実装が該当)
- 画面ごとに truncate ルールを CSS にコピペ (drift の温床、共通 module で集約)

**参考実装**: 直近の録画リスト ([DropScreen.tsx:421-426](../gui/src/screens/DropScreen.tsx#L421), PR #655 Round 2) —
1 行版だが「直近 path 識別」の同種要求への先行解。本 §1.6 は SelectedCard を含む他全画面用の 2 段版。

**画面別適用箇所**: §2.1.4 (Drop SelectedCard) / §2.2.2 (Detecting Header) / §2.2.8 (Detecting error view、新規) /
§2.3.2 (Complete sourceBox) / §2.4.16 (Preview header path display、新規) / §2.5.2 (Export header) — 各節に「§1.6 準拠」リンク。
新規サブセクション (§2.2.8 / §2.4.16) は既存 anchor 互換のため各 §2 の末尾に追加する。

````

- [ ] **Step 2: `docs/a11y-policy.md` にクロスリファレンス 1 節追加**

`docs/a11y-policy.md` で `## disabled 理由表示` 節 (line 75 周辺) を読み、その節終了直後 (`## 動きの抑止 (prefers-reduced-motion)` の **直前**) に以下を挿入:

```markdown
## ファイルパス表示の `title` 属性

5 画面の path 表示は **[ui-interaction-spec.md §1.6](ui-interaction-spec.md)** が source of truth。
`title` 属性 (hover tooltip) で full path を出し、`aria-label` は新規追加しない方針 (a11y-policy 「scope 外」整合)。
```

- [ ] **Step 3: markdownlint で 0 error を確認**

```bash
bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md docs/a11y-policy.md 2>&1 | tail -5
```

Expected output:

```text
Summary: 0 error(s)
```

(`Summary: N error(s)` で N>0 なら出力を読んで修正。典型は MD028 連続 blockquote 空行 / MD056 table cell `|` escape — 直接該当しないが確認)

- [ ] **Step 4: Commit**

```bash
git add docs/ui-interaction-spec.md docs/a11y-policy.md
git commit -F - <<'EOF'
docs: #676 ui-interaction-spec.md §1.6 「ファイルパス表示の原則」を新設

5 画面 (drop / detecting / complete / preview / export) のファイルパス
表示の共通ルール (full path 必須 / title 必須 / RTL ellipsis truncate /
data-testid 命名 / a11y) を doc 化:

- ui-interaction-spec.md §1.6 を §1.5 の直後に新設
- 表示形式 / primary・secondary / source-of-truth / splitPath / aria
  方針 / recent list 例外 を表形式で明文化
- §2.X 部品節への参照リンクを明示 (§2.2.8 / §2.4.16 は後続 task で新設)
- a11y-policy.md にクロスリファレンス節 1 個追加 (title 属性は §1.6
  source of truth、aria-label 新規追加なし方針の整合)

横展開での再発 (PR #655 で recent list のみ partial fix だった経緯) を
構造的に防止する。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 4: Drop SelectedCard を 2 段構造に変更 (TDD)

**Files:**

- Modify: `gui/src/screens/DropScreen.tsx:463-503` (SelectedCard 内 `.selectedName`)
- Test: `gui/src/screens/DropScreen.test.tsx` (既存 test に describe ブロック追加、末尾)
- Modify: `docs/ui-interaction-spec.md` §2.1.4 SelectedCard (`例外 / edge case` 行に「§1.6 準拠」追記)

- [ ] **Step 1: 失敗するテストを書く**

`gui/src/screens/DropScreen.test.tsx` の末尾に追加 (既存テストの fixture / helper を再利用):

```tsx
import { within } from '@testing-library/react';

describe('#676 SelectedCard path display', () => {
  it('shows fileName primary and parentDir secondary with full path in title', async () => {
    // 既存 helper を流用 — 例: selectVideo / renderDropScreen 等。
    // 既存 test の "shows selected card" 等のセットアップに揃える。
    const probe = {
      path: 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv',
      fileName: '2026-01-16 21-14-05.mkv',
      width: 1920,
      height: 1080,
      fps: 60,
      durationSeconds: 7200,
      sizeBytes: 30_000_000_000,
      codec: 'h264',
    };
    const { findByTestId } = renderDropScreenWithProbe(probe); // 既存 helper or インライン作成

    const container = await findByTestId('drop-selected-path');
    expect(container).toHaveAttribute(
      'title',
      'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv',
    );
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });
});
```

> **注意**: 既存 DropScreen.test.tsx に `renderDropScreenWithProbe` や同等 helper があれば再利用。なければ既存 "shows selected card" テスト ([DropScreen.test.tsx:26 / :274 / :346](../gui/src/screens/DropScreen.test.tsx#L26) 周辺) のセットアップパターンをコピーしてインライン構築。helper 抽出は YAGNI で本 task では行わない。

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/screens/DropScreen.test.tsx -t "#676 SelectedCard" 2>&1 | tail -10
```

Expected: FAIL — `drop-selected-path` testid 不在 / fileName と parentDir の別行 render なし。

- [ ] **Step 3: SelectedCard を 2 段構造に変更**

`gui/src/screens/DropScreen.tsx` の冒頭 import に追加:

```tsx
import { splitPath } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
```

`SelectedCard` 関数の `<div className={styles.selectedName}>{info.fileName}</div>` (line 479 付近) を以下に置換:

```tsx
{(() => {
  const { fileName, parentDir } = splitPath(info.path);
  return (
    <div
      className={pathStyles.pathDisplay}
      title={info.path}
      data-testid="drop-selected-path"
    >
      <div className={styles.selectedName}>{fileName || '(video)'}</div>
      {parentDir && (
        <div className={pathStyles.pathSecondary}>{parentDir}</div>
      )}
    </div>
  );
})()}
```

- [ ] **Step 4: テストが通ることを確認**

```bash
cd gui && npx vitest run src/screens/DropScreen.test.tsx 2>&1 | tail -10
```

Expected: ALL pass。既存 SelectedCard 系テスト (line 26 / 274 / 346 周辺) も regression なく通ること。

- [ ] **Step 5: doc §2.1.4 に「§1.6 準拠」を 1 行追記**

`docs/ui-interaction-spec.md` §2.1.4 SelectedCard (line 202-210 付近) の `例外 / edge case` 行を以下に拡張:

```diff
-| 例外 / edge case | `probeInfo` が null になり得るが、phase=`selected` 時は guard ([:115-116](../gui/src/screens/DropScreen.tsx#L115)) で render しないため不整合は発生しない |
+| 例外 / edge case | `probeInfo` が null になり得るが、phase=`selected` 時は guard ([:115-116](../gui/src/screens/DropScreen.tsx#L115)) で render しないため不整合は発生しない。**§1.6 ファイルパス表示の原則に準拠** — `info.path` を `splitPath()` で分解、primary `.selectedName` (fileName) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={info.path}` の 2 段構造 (`data-testid="drop-selected-path"`、#676) |
```

- [ ] **Step 6: lint / typecheck / markdownlint**

```bash
cd gui && npm run lint 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5 && cd .. && bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md 2>&1 | tail -5
```

Expected: 全 0 error。

- [ ] **Step 7: Commit**

```bash
git add gui/src/screens/DropScreen.tsx gui/src/screens/DropScreen.test.tsx docs/ui-interaction-spec.md
git commit -F - <<'EOF'
feat(gui): #676 Drop SelectedCard を 2 段 path 表示に変更

SelectedCard の info.fileName 単行表示を、splitPath(info.path) 由来の
ファイル名主表示 + 親フォルダ副表示 (path-display.module.css) に変更:

- container <div> に title={info.path} + data-testid="drop-selected-path"
- primary .selectedName (16px / text-bright) は既存 CSS のまま流用
- secondary .pathSecondary (11px / dim / mono、RTL ellipsis truncate)
- parentDir 空時は secondary 行非表示 (drive root フォールバック)

テスト: DropScreen.test.tsx に SelectedCard render テスト 1 ケース追加
(title 属性 / fileName 行 / parentDir 行 を assert)。

doc: ui-interaction-spec.md §2.1.4 の edge case 行に「§1.6 準拠」と
data-testid 規約を追記。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 5: DetectingScreen running + error view を 2 段構造に変更 (TDD)

**Files:**

- Modify: `gui/src/screens/DetectingScreen.tsx:287-364` (parent `DetectingScreen`)
- Modify: `gui/src/screens/DetectingScreen.tsx:382-668` (`DetectingRunningView` 内 displayFile derivation + render)
- Modify: `gui/src/screens/DetectingScreen.tsx:719-792` (`DetectingErrorView` props + render)
- Test: `gui/src/screens/DetectingScreen.test.tsx` (既存 test に describe ブロック追加、末尾)
- Modify: `docs/ui-interaction-spec.md` §2.2.2 Header (既存) + 末尾に **§2.2.8 Detecting error view path display** 新設

- [ ] **Step 1: 失敗するテストを書く (running view + error view 2 ケース)**

`gui/src/screens/DetectingScreen.test.tsx` 末尾に追加:

```tsx
import { within } from '@testing-library/react';

describe('#676 DetectingScreen path display', () => {
  it('running header shows fileName primary and parentDir secondary with full path title', async () => {
    // 既存 test の running セットアップを流用。
    // selectedVideoPath を store 経由でセットし、DetectingScreen を render する helper を再利用。
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const { findByTestId } = renderDetectingScreenWithPath(fullPath, { phase: 'running' });

    const container = await findByTestId('detecting-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('error view shows fileName primary and parentDir secondary with full path title', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const { findByTestId } = renderDetectingScreenWithPath(fullPath, { phase: 'error' });

    const container = await findByTestId('detecting-error-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });
});
```

> **注意**: `renderDetectingScreenWithPath` は既存 DetectingScreen.test.tsx の running / error テストのセットアップを参考にインライン記述してよい (既存 store mocking パターンを踏襲)。`phase: 'error'` 経路は親 component の error state ・ error prop を立ててから render する。

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/screens/DetectingScreen.test.tsx -t "#676 DetectingScreen" 2>&1 | tail -15
```

Expected: 2 FAIL — `detecting-path` / `detecting-error-path` testid 不在。

- [ ] **Step 3: 親 `DetectingScreen` で `displayPath` を導出**

`gui/src/screens/DetectingScreen.tsx` の import に追加:

```tsx
import { splitPath } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
```

`DetectingScreen` (line 287 周辺) の `displayFile` derivation を以下に変更:

```diff
-const displayFile = selectedVideoPath?.split(/[/\\]/).pop() ?? '(video)';
+const displayPath = selectedVideoPath
+  ? { ...splitPath(selectedVideoPath), full: selectedVideoPath }
+  : { fileName: '(video)', parentDir: '', full: '' };
```

`DetectingErrorView` への prop 受け渡し (line 336 周辺) を以下に変更:

```diff
 <DetectingErrorView
   error={error}
   errorHint={errorHint}
-  displayFile={displayFile}
+  displayPath={displayPath}
   onRetry={handleRetry}
   onBack={() => navigate('drop')}
 />
```

`DetectingRunningView` への prop 受け渡し (line 346 周辺) に `displayPath` を追加:

```diff
 <DetectingRunningView
   key={runCount}
   phase={phase}
   selectedVideoPath={selectedVideoPath}
+  displayPath={displayPath}
   detectionParams={detectionParams}
   ...
 />
```

- [ ] **Step 4: `DetectingRunningView` の props 型と render を更新**

`DetectingRunningViewProps` interface (line 366 周辺) に追加:

```diff
 interface DetectingRunningViewProps {
   phase: DetectingPhase;
   selectedVideoPath: string | null;
+  displayPath: { fileName: string; parentDir: string; full: string };
   detectionParams: ReturnType<typeof useAppStateStore.getState>['detectionParams'];
   ...
 }
```

`function DetectingRunningView({ ... })` の destructuring に `displayPath` を追加 (line 383 周辺):

```diff
 function DetectingRunningView({
   phase,
   selectedVideoPath,
+  displayPath,
   detectionParams,
   ...
 }: DetectingRunningViewProps) {
```

ローカル derivation を削除 (line 564 周辺):

```diff
-const displayFile = selectedVideoPath?.split(/[/\\]/).pop() ?? '(video)';
```

Header の `.fileName` 表示 (line 577 周辺) を以下に置換:

```diff
-<div className={styles.fileName}>{displayFile}</div>
+<div
+  className={pathStyles.pathDisplay}
+  title={displayPath.full}
+  data-testid="detecting-path"
+>
+  <div className={styles.fileName}>{displayPath.fileName}</div>
+  {displayPath.parentDir && (
+    <div className={pathStyles.pathSecondary}>{displayPath.parentDir}</div>
+  )}
+</div>
```

- [ ] **Step 5: `DetectingErrorView` の props 型と render を更新**

`DetectingErrorViewProps` interface (line 719 周辺) を更新:

```diff
 interface DetectingErrorViewProps {
   error: string | null;
   errorHint: string | null;
-  displayFile: string;
+  displayPath: { fileName: string; parentDir: string; full: string };
   onRetry: () => void;
   onBack: () => void;
 }
```

`function DetectingErrorView({ ... })` の destructuring (line 732 周辺):

```diff
 function DetectingErrorView({
   error,
   errorHint,
-  displayFile,
+  displayPath,
   onRetry,
   onBack,
 }: DetectingErrorViewProps) {
```

error view の `.errorFile` 表示 (line 762 周辺) を以下に置換:

```diff
-<div className={styles.errorFile}>{displayFile}</div>
+<div
+  className={pathStyles.pathDisplay}
+  title={displayPath.full}
+  data-testid="detecting-error-path"
+>
+  <div className={styles.errorFile}>{displayPath.fileName}</div>
+  {displayPath.parentDir && (
+    <div className={pathStyles.pathSecondary}>{displayPath.parentDir}</div>
+  )}
+</div>
```

- [ ] **Step 6: テストが通ることを確認**

```bash
cd gui && npx vitest run src/screens/DetectingScreen.test.tsx 2>&1 | tail -15
```

Expected: ALL pass。既存 running / error 系テストも regression なし。

- [ ] **Step 7: doc §2.2.2 既存節に「§1.6 準拠」追記 + §2.2.8 新規節を末尾追加**

`docs/ui-interaction-spec.md` §2.2.2 Header (line 366-374 付近) の `例外 / edge case` 行を以下に拡張:

```diff
-| 例外 / edge case | `selectedVideoPath` が null の場合は `'(video)'` フォールバック。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で `meta` 行を `probing` event payload (`width` × `height` / `fps` / `codec` / `duration_s`) から実 ffprobe 結果に差し替え済 (`probing` 受信前の数百 ms は暫定 `phase: …` を表示) |
+| 例外 / edge case | `selectedVideoPath` が null の場合は fileName `'(video)'` フォールバック (parentDir は空文字列で secondary 行非表示)。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で `meta` 行を `probing` event payload (`width` × `height` / `fps` / `codec` / `duration_s`) から実 ffprobe 結果に差し替え済 (`probing` 受信前の数百 ms は暫定 `phase: …` を表示)。**§1.6 ファイルパス表示の原則に準拠** — `selectedVideoPath` を `splitPath()` で分解、primary `.fileName` (14px) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={selectedVideoPath}` (`data-testid="detecting-path"`、#676) |
```

§2.2 末尾 (§2.2.7 [中断] button の後、line 424 直後) に新規節を追加:

```markdown
#### §2.2.8 Detecting error view path display (#676)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([DetectingScreen.tsx:732-792](../gui/src/screens/DetectingScreen.tsx#L732) `DetectingErrorView` 内、`role="alert"` の error card 内部) |
| 状態 | `displayOnly`。phase=`error` のときのみ render される (error view) |
| 遷移トリガー | なし。`selectedVideoPath` 由来の `displayPath` prop に追従 |
| store mutation | なし |
| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `selectedVideoPath` を `splitPath()` で分解、primary `.errorFile` (13px / text-bright) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={selectedVideoPath}` (`data-testid="detecting-error-path"`)。`selectedVideoPath` が null の場合は fileName `'(video)'` + secondary 行非表示にフォールバック |
```

- [ ] **Step 8: lint / typecheck / markdownlint**

```bash
cd gui && npm run lint 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5 && cd .. && bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md 2>&1 | tail -5
```

Expected: 全 0 error。

- [ ] **Step 9: Commit**

```bash
git add gui/src/screens/DetectingScreen.tsx gui/src/screens/DetectingScreen.test.tsx docs/ui-interaction-spec.md
git commit -F - <<'EOF'
feat(gui): #676 DetectingScreen running + error view を 2 段 path 表示に変更

親 DetectingScreen で displayPath = {fileName, parentDir, full} を導出し、
running view (header .fileName) と error view (.errorFile) の両方に
prop で渡す形に統一:

- 親で splitPath(selectedVideoPath) を 1 回計算、子に prop 流す
- running view: data-testid="detecting-path" + title={full}
- error view: data-testid="detecting-error-path" + title={full}
- 既存 .fileName (14px) / .errorFile (13px) CSS は primary として流用
- selectedVideoPath null 時は fileName '(video)' + secondary 非表示

テスト: DetectingScreen.test.tsx に running / error の path 表示テスト
2 ケース追加。

doc:
- ui-interaction-spec.md §2.2.2 の edge case 行に「§1.6 準拠」追記
- §2.2.8 Detecting error view path display を末尾に新設

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 6: CompleteScreen topBar を 2 段構造に変更 (TDD)

**Files:**

- Modify: `gui/src/screens/CompleteScreen.tsx:97-102` (topBar `.sourceBox`)
- Test: `gui/src/screens/CompleteScreen.test.tsx` (既存 test に describe ブロック追加、末尾)
- Modify: `docs/ui-interaction-spec.md` §2.3.2 sourceBox

- [ ] **Step 1: 失敗するテストを書く**

`gui/src/screens/CompleteScreen.test.tsx` 末尾に追加:

```tsx
import { within } from '@testing-library/react';

describe('#676 CompleteScreen topBar path display', () => {
  it('shows fileName primary and parentDir secondary with title (videoSource = selectedVideoPath)', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    // 既存 test の setup helper を再利用 — metadata + selectedVideoPath を store にセット
    const { findByTestId } = renderCompleteScreenWith({
      metadataSource: 'C:\\different\\path.mkv',  // metadata.source は無視されることを確認
      selectedVideoPath: fullPath,
    });

    const container = await findByTestId('complete-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('falls back to metadata.source when selectedVideoPath is null (sample mode)', async () => {
    const metadataSource = 'C:\\sample\\demo.mkv';
    const { findByTestId } = renderCompleteScreenWith({
      metadataSource,
      selectedVideoPath: null,
    });

    const container = await findByTestId('complete-path');
    expect(container).toHaveAttribute('title', metadataSource);
    expect(within(container).getByText('demo.mkv')).toBeInTheDocument();
    expect(within(container).getByText('C:\\sample')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/screens/CompleteScreen.test.tsx -t "#676 CompleteScreen" 2>&1 | tail -15
```

Expected: 2 FAIL — `complete-path` testid 不在。

- [ ] **Step 3: CompleteScreen topBar を 2 段構造に変更**

`gui/src/screens/CompleteScreen.tsx` の import に追加 (既存 `useAppStateStore` import 隣):

```tsx
import { splitPath } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
```

`useAppStateStore` 由来の `selectedVideoPath` は line 54 で既に取得済 (既存 `thumbVideoPath` 用)。これを再利用。

`.sourceBox` (line 99-102 周辺) を以下に置換:

```diff
 <div className={styles.sourceBox}>
   <div className={styles.sourceCaption}>観測完了</div>
-  <div className={styles.sourceName}>{metadata.source}</div>
+  {(() => {
+    const src = selectedVideoPath ?? metadata.source;
+    const { fileName, parentDir } = splitPath(src);
+    return (
+      <div
+        className={pathStyles.pathDisplay}
+        title={src}
+        data-testid="complete-path"
+      >
+        <div className={styles.sourceName}>{fileName || '(video)'}</div>
+        {parentDir && (
+          <div className={pathStyles.pathSecondary}>{parentDir}</div>
+        )}
+      </div>
+    );
+  })()}
 </div>
```

- [ ] **Step 4: テストが通ることを確認**

```bash
cd gui && npx vitest run src/screens/CompleteScreen.test.tsx 2>&1 | tail -15
```

Expected: ALL pass。

- [ ] **Step 5: doc §2.3.2 に「§1.6 準拠」追記**

`docs/ui-interaction-spec.md` §2.3.2 sourceBox (line 463-471 付近) の `例外 / edge case` 行を以下に拡張:

```diff
-| 例外 / edge case | full path が長すぎる場合の overflow / ellipsis は CSS 任せ。a11y は plain text、screen reader はそのまま読み上げる。Phase 2.5 で basename + tooltip full path に変更する選択肢あり ([#587](https://github.com/Idios/kobutachan-allaganeye/issues/587)) |
+| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `videoSource` (= `selectedVideoPath ?? metadata.source`) を `splitPath()` で分解、primary `.sourceName` (13px / text-bright) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={videoSource}` (`data-testid="complete-path"`、#676)。sample mode 等 `selectedVideoPath` 不在時は `metadata.source` にフォールバックして同一構造で表示 |
```

`### §2.3` の冒頭、store 概要パラグラフ (line 434 周辺) に書かれている "(metadata / selectedMatchIndex / selectedVideoPath / hasBackup)" は既に `selectedVideoPath` を含むので追記不要。

- [ ] **Step 6: lint / typecheck / markdownlint**

```bash
cd gui && npm run lint 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5 && cd .. && bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md 2>&1 | tail -5
```

Expected: 全 0 error。

- [ ] **Step 7: Commit**

```bash
git add gui/src/screens/CompleteScreen.tsx gui/src/screens/CompleteScreen.test.tsx docs/ui-interaction-spec.md
git commit -F - <<'EOF'
feat(gui): #676 CompleteScreen topBar を 2 段 path 表示に変更

sourceBox の metadata.source 単行表示を、splitPath(videoSource) 由来の
ファイル名主表示 + 親フォルダ副表示に変更:

- videoSource = selectedVideoPath ?? metadata.source (Preview/Export と
  同 source-of-truth に統一、Complete だけ source 違い解消)
- container <div> に title={videoSource} + data-testid="complete-path"
- primary .sourceName (13px / text-bright) は既存 CSS のまま流用
- secondary .pathSecondary (11px / dim / mono、RTL ellipsis truncate)
- sample mode (selectedVideoPath null) では metadata.source フォールバック

テスト: CompleteScreen.test.tsx に topBar path 表示テスト 2 ケース追加
(selectedVideoPath 優先 / metadata.source フォールバック)。

doc: ui-interaction-spec.md §2.3.2 の edge case 行に「§1.6 準拠」追記。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 7: PreviewScreen header に path display 新規追加 (TDD)

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx:619-650` (header `.headerInfo` 内)
- Modify: `gui/src/screens/PreviewScreen.module.css` (`.headerFileName` クラス追加)
- Test: `gui/src/screens/PreviewScreen.test.tsx` (既存 test に describe ブロック追加、末尾)
- Modify: `docs/ui-interaction-spec.md` §2.4 末尾に **§2.4.16 Preview header path display** 新設

- [ ] **Step 1: 失敗するテストを書く**

`gui/src/screens/PreviewScreen.test.tsx` 末尾に追加:

```tsx
import { within } from '@testing-library/react';

describe('#676 PreviewScreen header path display', () => {
  it('shows fileName primary and parentDir secondary with title (videoSource)', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const { findByTestId } = renderPreviewScreenWith({
      selectedVideoPath: fullPath,
      metadataSource: 'C:\\different\\path.mkv',
    });

    const container = await findByTestId('preview-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('does not render path display when videoSource is null', async () => {
    const { queryByTestId } = renderPreviewScreenWith({
      selectedVideoPath: null,
      metadataSource: null,  // videoSource = null
    });

    expect(queryByTestId('preview-path')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx -t "#676 PreviewScreen" 2>&1 | tail -15
```

Expected: 1 FAIL (新規 testid 不在) + 1 PASS (no testid なら自動 pass)。

- [ ] **Step 3: PreviewScreen header に path display を追加**

`gui/src/screens/PreviewScreen.tsx` の import に追加:

```tsx
import { splitPath } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
```

`videoSource` は line 261 で既に定義済 (`const videoSource = selectedVideoPath ?? metadata?.source ?? null;`)。再利用。

`<div className={styles.headerInfo}>` (line 629 周辺) の **最初の子** として path display を挿入:

```diff
 <div className={styles.headerInfo}>
+  {videoSource && (() => {
+    const { fileName, parentDir } = splitPath(videoSource);
+    return (
+      <div
+        className={pathStyles.pathDisplay}
+        title={videoSource}
+        data-testid="preview-path"
+      >
+        <div className={styles.headerFileName}>{fileName || '(video)'}</div>
+        {parentDir && (
+          <div className={pathStyles.pathSecondary}>{parentDir}</div>
+        )}
+      </div>
+    );
+  })()}
   <div className={styles.caption}>境界調整 ⸱ BOUNDARY CALIBRATION</div>
   <div className={styles.nameRow}>
     ...
```

- [ ] **Step 4: `.headerFileName` CSS class 追加**

`gui/src/screens/PreviewScreen.module.css` の `.caption` (line 40 周辺) **直前**に追加:

```css
.headerFileName {
  font-family: var(--ae-font-body);
  font-size: 13px;
  color: var(--ae-text-bright);
  margin-bottom: 4px;
}
```

- [ ] **Step 5: テストが通ることを確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx 2>&1 | tail -15
```

Expected: ALL pass。既存 preview テストも regression なし。

- [ ] **Step 6: doc §2.4.16 を末尾に新設**

`docs/ui-interaction-spec.md` §2.4 末尾 (§2.4.15 emptyNote の後、`### §2.5 export` の **直前**) に新規節を追加:

```markdown
#### §2.4.16 header path display (#676)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([PreviewScreen.tsx:629](../gui/src/screens/PreviewScreen.tsx#L629) `.headerInfo` 内、`.caption` の上に配置) |
| 状態 | `displayOnly`。`videoSource` 不在 (sample mode 等で `selectedVideoPath` も `metadata.source` も null) のとき非 render |
| 遷移トリガー | `videoSource` (= `selectedVideoPath ?? metadata?.source ?? null`) 変化に追従 |
| store mutation | なし |
| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `videoSource` を `splitPath()` で分解、primary `.headerFileName` (13px / text-bright、PreviewScreen.module.css 新設) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={videoSource}` (`data-testid="preview-path"`、#676)。`videoSource === null` で領域全体を非表示 (条件付き render) |
```

- [ ] **Step 7: lint / typecheck / markdownlint**

```bash
cd gui && npm run lint 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5 && cd .. && bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md 2>&1 | tail -5
```

Expected: 全 0 error。

- [ ] **Step 8: Commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.module.css gui/src/screens/PreviewScreen.test.tsx docs/ui-interaction-spec.md
git commit -F - <<'EOF'
feat(gui): #676 PreviewScreen header に 2 段 path 表示を新規追加

.headerInfo 内、.caption 「境界調整」の上に splitPath(videoSource) 由来の
ファイル名主表示 + 親フォルダ副表示を新規追加:

- videoSource (= selectedVideoPath ?? metadata.source、line 261 既存定義)
- container <div> に title={videoSource} + data-testid="preview-path"
- primary .headerFileName (13px / text-bright、PreviewScreen.module.css 新設)
- secondary .pathSecondary (11px / dim / mono、RTL ellipsis truncate)
- videoSource null 時は領域全体を非表示 (条件付き render)
- 縦寸法 +28px (13px + 11px + gap) は overflow:auto で吸収

テスト: PreviewScreen.test.tsx に header path 表示テスト 2 ケース追加
(videoSource あり / videoSource null)。

doc: ui-interaction-spec.md §2.4.16 を §2.4 末尾に新設 (既存 anchor 互換)。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 8: ExportScreen header に path display 新規追加 (TDD)

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx:525-533` (header 左 div)
- Modify: `gui/src/screens/ExportScreen.module.css` (`.headerFileName` クラス追加)
- Test: `gui/src/screens/ExportScreen.test.tsx` (既存 test に describe ブロック追加、末尾)
- Modify: `docs/ui-interaction-spec.md` §2.5.2 header (caption + title) の `例外 / edge case` 行に追記

- [ ] **Step 1: 失敗するテストを書く**

`gui/src/screens/ExportScreen.test.tsx` 末尾に追加:

```tsx
import { within } from '@testing-library/react';

describe('#676 ExportScreen header path display', () => {
  it('shows fileName primary and parentDir secondary with title (videoSource)', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const { findByTestId } = renderExportScreenWith({
      selectedVideoPath: fullPath,
      metadataSource: 'C:\\different\\path.mkv',
    });

    const container = await findByTestId('export-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('does not render path display when videoSource is null', async () => {
    const { queryByTestId } = renderExportScreenWith({
      selectedVideoPath: null,
      metadataSource: null,
    });

    expect(queryByTestId('export-path')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: テストが失敗することを確認**

```bash
cd gui && npx vitest run src/screens/ExportScreen.test.tsx -t "#676 ExportScreen" 2>&1 | tail -15
```

Expected: 1 FAIL + 1 PASS (no testid なら queryByTestId 自動 null pass)。

- [ ] **Step 3: ExportScreen header に path display を追加**

`gui/src/screens/ExportScreen.tsx` の import に追加:

```tsx
import { splitPath } from '../utils/path';
import pathStyles from '../styles/path-display.module.css';
```

`videoSource` は line 126 で既に定義済。再利用。

`<div className={styles.header}>` 内の左 `<div>` (line 527-532 周辺) を以下に置換:

```diff
 <div>
+  {videoSource && (() => {
+    const { fileName, parentDir } = splitPath(videoSource);
+    return (
+      <div
+        className={pathStyles.pathDisplay}
+        title={videoSource}
+        data-testid="export-path"
+      >
+        <div className={styles.headerFileName}>{fileName || '(video)'}</div>
+        {parentDir && (
+          <div className={pathStyles.pathSecondary}>{parentDir}</div>
+        )}
+      </div>
+    );
+  })()}
   <div className={styles.caption}>エクスポート</div>
   <div className={styles.title}>
     {countedMatches.length} 試合を書き出す
   </div>
 </div>
```

- [ ] **Step 4: `.headerFileName` CSS class 追加**

`gui/src/screens/ExportScreen.module.css` の `.caption` (line 41 周辺) **直前**に追加:

```css
.headerFileName {
  font-family: var(--ae-font-body);
  font-size: 13px;
  color: var(--ae-text-bright);
  margin-bottom: 4px;
}
```

- [ ] **Step 5: テストが通ることを確認**

```bash
cd gui && npx vitest run src/screens/ExportScreen.test.tsx 2>&1 | tail -15
```

Expected: ALL pass。

- [ ] **Step 6: doc §2.5.2 に「§1.6 準拠」追記**

`docs/ui-interaction-spec.md` §2.5.2 header (line 799-807 付近) の `例外 / edge case` 行を以下に拡張:

```diff
-| 例外 / edge case | `countedMatches.length === 0` のとき "0 試合を書き出す" 表示で無意味だが、画面全体としては start ボタン disabled (`!videoSource`) で実害なし。0 件時の専用文言 + start 無効化は [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) 議論対象 |
+| 例外 / edge case | `countedMatches.length === 0` のとき "0 試合を書き出す" 表示で無意味だが、画面全体としては start ボタン disabled (`!videoSource`) で実害なし。0 件時の専用文言 + start 無効化は [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) 議論対象。**§1.6 ファイルパス表示の原則に準拠** — header caption/title の上に `videoSource` 由来の 2 段 path display を render (primary `.headerFileName` (13px) + secondary `.pathSecondary` 左側省略 + container `title={videoSource}`、`data-testid="export-path"`、#676)。`videoSource === null` で領域全体を非表示 |
```

- [ ] **Step 7: lint / typecheck / markdownlint**

```bash
cd gui && npm run lint 2>&1 | tail -5 && npm run typecheck 2>&1 | tail -5 && cd .. && bash scripts/check-markdownlint.sh docs/ui-interaction-spec.md 2>&1 | tail -5
```

Expected: 全 0 error。

- [ ] **Step 8: Commit**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.module.css gui/src/screens/ExportScreen.test.tsx docs/ui-interaction-spec.md
git commit -F - <<'EOF'
feat(gui): #676 ExportScreen header に 2 段 path 表示を新規追加

header 内の caption "エクスポート" / title "{N} 試合を書き出す" の
上に splitPath(videoSource) 由来のファイル名主表示 + 親フォルダ副表示を
新規追加 (PreviewScreen と 1:1 同等):

- videoSource (= selectedVideoPath ?? metadata.source、line 126 既存定義)
- container <div> に title={videoSource} + data-testid="export-path"
- primary .headerFileName (13px / text-bright、ExportScreen.module.css 新設)
- secondary .pathSecondary (11px / dim / mono、RTL ellipsis truncate)
- videoSource null 時は領域全体を非表示 (条件付き render)
- 縦寸法 +28px は header の flex layout で吸収

テスト: ExportScreen.test.tsx に header path 表示テスト 2 ケース追加。

doc: ui-interaction-spec.md §2.5.2 の edge case 行に「§1.6 準拠」追記。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

---

## Task 9: Integration smoke test + 最終 CI gate verification

**Files:**

- Modify: `gui/src/__tests__/flow.integration.test.tsx` (既存 file 末尾に test 追加)
- 検証: 全 CI gate (`npm run lint` / `typecheck` / `test` / `build` + `cargo check` + `markdownlint`)

- [ ] **Step 1: Integration smoke test を書く (失敗想定で先に書く)**

`gui/src/__tests__/flow.integration.test.tsx` の末尾 (or 適切な describe ブロック内) に追加:

```tsx
import { within } from '@testing-library/react';

describe('#676 cross-screen path display continuity', () => {
  it('keeps the full path visible across drop → detect → complete → preview → export', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const expectedFileName = '2026-01-16 21-14-05.mkv';
    const expectedParentDir = 'E:\\videos\\20260116';

    // 既存 integration test の flow runner / store setup を再利用。
    // 実 Tauri command の代わりに mock を仕込み、各画面に進ませる。
    const harness = await renderIntegrationFlow(); // 既存 helper

    // 1. Drop: SelectedCard 表示後
    await harness.dropVideo({ path: fullPath, fileName: expectedFileName });
    {
      const c = await harness.findByTestId('drop-selected-path');
      expect(c).toHaveAttribute('title', fullPath);
      expect(within(c).getByText(expectedFileName)).toBeInTheDocument();
      expect(within(c).getByText(expectedParentDir)).toBeInTheDocument();
    }

    // 2. Detecting (running)
    await harness.startDetect();
    {
      const c = await harness.findByTestId('detecting-path');
      expect(c).toHaveAttribute('title', fullPath);
    }

    // 3. Complete
    await harness.finishDetect();
    {
      const c = await harness.findByTestId('complete-path');
      expect(c).toHaveAttribute('title', fullPath);
    }

    // 4. Preview
    await harness.openPreviewForFirstMatch();
    {
      const c = await harness.findByTestId('preview-path');
      expect(c).toHaveAttribute('title', fullPath);
    }

    // 5. Export
    await harness.navigateToExport();
    {
      const c = await harness.findByTestId('export-path');
      expect(c).toHaveAttribute('title', fullPath);
    }
  });
});
```

> **注意**: 既存 [flow.integration.test.tsx](../../gui/src/__tests__/flow.integration.test.tsx) の helper シグネチャ (`renderIntegrationFlow` 等) が異なる場合は、現存 helper の API に合わせて読み替える。重要な assert は「各画面の `data-testid="<screen>-path"` container の `title` 属性が全画面で同じ `fullPath` を持つ」こと。

- [ ] **Step 2: integration smoke が通ることを確認**

```bash
cd gui && npx vitest run src/__tests__/flow.integration.test.tsx 2>&1 | tail -15
```

Expected: 新規ケース PASS、既存 flow ケースも regression なし。

> **もし FAIL する場合**: helper シグネチャの相違 (`renderIntegrationFlow` が存在しない / 引数が違う) が主因。`gui/src/__tests__/flow.integration.test.tsx` の冒頭で実際に使われている setup pattern を grep して、test code を現存 API に合わせる。Tauri mock の差異で対応すべきは store mutation 順序のみ。

- [ ] **Step 3: 全 CI gate を回す (machine-verified)**

```bash
cd gui && npm run lint 2>&1 | tail -10
```

Expected: 0 error。

```bash
cd gui && npm run typecheck 2>&1 | tail -10
```

Expected: 0 error。

```bash
cd gui && npm test 2>&1 | tail -30
```

Expected: 全 vitest test pass、jest-axe 違反なし。

```bash
cd gui && npm run build 2>&1 | tail -10
```

Expected: vite build 成功、`gui/dist/` 生成。

```bash
cd gui/src-tauri && cargo check 2>&1 | tail -10
```

Expected: 0 error。

```bash
bash scripts/check-markdownlint.sh 2>&1 | tail -5
```

Expected: 0 error。

> **いずれかが fail した場合**: 該当 task に戻って修正 (本 plan は inline 修正前提、ロールバックはしない)。

- [ ] **Step 4: Commit (integration smoke のみ、CI gate 結果はコミット対象外)**

```bash
git add gui/src/__tests__/flow.integration.test.tsx
git commit -F - <<'EOF'
test(gui): #676 cross-screen path display continuity integration smoke

drop → detect → complete → preview → export の画面遷移で、各画面の
data-testid="<screen>-path" container の title 属性が同じ fullPath を
保持することを確認する integration smoke を 1 ケース追加。

Drop SelectedCard / Detecting / Complete / Preview / Export の各
path 表示は単体 screen test で個別検証済 (Task 4-8)、本 test は
flow 全体での「path が遷移後も継続表示される」観点を担保する。

すべての CI gate (lint / typecheck / test / build / cargo check /
markdownlint) を pass。Lane III / Group E 完走。

Refs #676

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 5: PR 作成準備 (Iron Law 6 Pre-flight)**

PR は本 plan のスコープ外 (実装完了後にユーザー指示で実行)。実装完了後、PR 作成前に以下の手順を踏む:

1. **Step 0 ハードゲート**: `gh pr list --search "676" --state open` で他に同 issue 対応 PR が無いことを確認
2. **Step 1 base 同期**: `git fetch origin develop-0.2.0` で base を最新化
3. **Step 2 取り込み未済 commit 確認**: `git log HEAD..origin/develop-0.2.0 --oneline`、ゼロ件であることを確認 (あれば merge して CI 再走)
4. **Step 3 touched files 交差判定**: 取り込み未済 commit 群と本 PR の touched files が重なる場合は実機検証要 (本 PR は GUI TS/CSS/vitest/doc のみで実機検証 trigger 対象外、ただし重なりがあれば Lane III 着手前に再評価)
5. **Step 4 並行 PR 重複再確認**: `gh pr list --search "676" --state all` で再度確認

実機検証は **任意 (recommended)** — Preview/Export header の縦寸法 +28px のレイアウト確認を Idios に `AskUserQuestion` で依頼する形 (Iron Law 6 必須 trigger 対象外、念のため目視)。

---

## 自己レビュー結果 (writing-plans skill 規約)

### 1. Spec coverage

spec [§3.1 変更ファイル一覧](../specs/2026-05-15-676-cross-screen-path-display-design.md) の各 entry が本 plan のどの task でカバーされるか:

| spec 変更項目 | 本 plan の task |
| --- | --- |
| `gui/src/utils/path.ts` (`splitPath` 追加) | Task 1 |
| `gui/src/utils/path.test.ts` (新規テスト) | Task 1 |
| `gui/src/styles/path-display.module.css` (新規) | Task 2 |
| `docs/ui-interaction-spec.md` §1.6 新設 | Task 3 |
| `docs/a11y-policy.md` クロスリファレンス | Task 3 |
| Drop SelectedCard | Task 4 |
| Detecting running header | Task 5 |
| Detecting error view | Task 5 |
| Complete topBar | Task 6 |
| Preview header (新規領域) | Task 7 |
| Export header (新規領域) | Task 8 |
| 各 screen test | Task 4-8 |
| Integration smoke (`flow.integration.test.tsx`) | Task 9 |
| `docs/ui-interaction-spec.md` 各 §2.X cross-ref | Task 4-8 (各 screen task 内で対応する §2.X を更新) |
| §2.2.8 / §2.4.16 新規節 | Task 5 / Task 7 (それぞれの screen task 内で新設) |

→ 漏れなし。

### 2. Placeholder スキャン

- 「TBD」「TODO」「実装は後で」等の placeholder なし
- 「適切なエラーハンドリングを追加」等の vague 文言なし
- 各 step に actual code を埋め込み済
- Task N の参照は「Task 1-3 → Task 4-8 → Task 9」の依存順序明示のみ

### 3. 型 / 関数名整合性

- `splitPath(absPath: string): { fileName: string; parentDir: string }` (Task 1) と全 consumer task (4-8) の使い方が一致
- `DetectingErrorViewProps.displayPath: { fileName: string; parentDir: string; full: string }` (Task 5) と `DetectingRunningViewProps.displayPath` の型一致
- CSS Module class 名 `pathStyles.pathDisplay` / `pathStyles.pathSecondary` (Task 2) と全 consumer task (4-8) の usage 一致
- `data-testid`: `drop-selected-path` / `detecting-path` / `detecting-error-path` / `complete-path` / `preview-path` / `export-path` の 6 種、§1.6 doc / 全 test / Integration smoke (Task 9) で整合
- screen-specific CSS class: `.selectedName` (Drop) / `.fileName` (Detecting running) / `.errorFile` (Detecting error) / `.sourceName` (Complete) / `.headerFileName` (Preview / Export 新設) — 全 task で命名一致

→ 整合性 OK。
