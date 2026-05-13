# Issue #677 SideRail 全体削除 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GUI 左の SideRail (装飾アイコン 4 個 + 縦書き `ALLAGAN` ロゴ) を実装から完全に削除し、ユーザーが先頭アイコンを「クリック可能な選択 UI」と誤認する問題 ([#677](https://github.com/Idios/kobutachan-allaganeye/issues/677)) を根絶する。

**Architecture:** 単 PR で完結。TDD Red-Green-Refactor 順に: ① App.test.tsx に「SideRail 不在」の regression assertion を追加 → ② App.tsx から SideRail 参照を除去して新 test を pass + 旧 `renders the side rail on every screen` test を同時除去 → ③ SideRail コンポーネントの 3 file (`.tsx` / `.module.css` / `.test.tsx`) を物理削除 → ④ `docs/ui-architecture.md` / `docs/design/README.md` を実装と同期。`docs/design/bundle/project/variants/aether.jsx` は handoff bundle 不変ポリシー (Q2-α) により改変しない。

**Tech Stack:** React 19 + TypeScript + Vitest + @testing-library/react + jest-axe (GUI) / 既存 build / lint 構成

**Spec:** [docs/superpowers/specs/2026-05-13-issue-677-siderail-removal-design.md](../specs/2026-05-13-issue-677-siderail-removal-design.md)

**Session-id:** `eloquent-joliot-835af8`

---

## Task 1: Pre-flight (Iron Law 6)

**Files:** なし (検証のみ)

- [ ] **Step 1: base 同期確認**

Run:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit 一覧 (空でも OK)。出力が空でなければ touched files (`gui/src/App.tsx` / `gui/src/App.test.tsx` / `gui/src/components/SideRail.*` / `docs/ui-architecture.md` / `docs/design/README.md`) と交差していないかを確認。交差していれば `git merge origin/develop-0.2.0` で取り込み。

- [ ] **Step 2: 並行 PR 重複確認**

Run:

```bash
gh pr list --search "677" --state all
```

Expected: #677 を扱う既存 PR が無いこと (本 PR で対応するため)。出力に open PR があれば中断してユーザーに確認。

- [ ] **Step 3: 着手 worktree が正しい branch にいることを確認**

Run:

```bash
git branch --show-current
```

Expected: `claude/eloquent-joliot-835af8`

- [ ] **Step 4: SideRail への他依存が無いことを確認 (sanity check)**

Run:

```bash
grep -rn "SideRail" gui/src docs --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" --include="*.css" --include="*.md"
```

Expected: 以下の参照のみ:

- `gui/src/App.tsx:4` (import)
- `gui/src/App.tsx:15` (JSDoc)
- `gui/src/App.tsx:35` (`<SideRail />`)
- `gui/src/App.test.tsx:79` (test name)
- `gui/src/components/SideRail.tsx` 全行
- `gui/src/components/SideRail.module.css` 全行
- `gui/src/components/SideRail.test.tsx` 全行
- `docs/ui-architecture.md:344` / `:354` / `:364`
- `docs/design/README.md` (passing reference のみ)
- `docs/design/bundle/project/variants/aether.jsx:438-453` 等 (handoff mock、不変)
- `docs/superpowers/plans/*.md` / `specs/*.md` (過去 plan / 本 spec、不変)

予期せぬ参照 (gui/src 内の他 component / screen) が出たら中断して spec を再評価。

---

## Task 2: TDD Red — App.test.tsx に SideRail 不在 assertion を追加

**Files:**

- Modify: `gui/src/App.test.tsx:79-84` 周辺 (追加位置)

- [ ] **Step 1: 既存 test 構造を把握**

Run:

```bash
grep -n "^  it\|^})" gui/src/App.test.tsx
```

Expected: 7 件の `it(...)` ブロックが `describe('App routing', ...)` 内に並ぶ。最後の `it` が `'renders the side rail on every screen'` (L79)。

- [ ] **Step 2: SideRail 不在 assertion を追加**

`gui/src/App.test.tsx` の L79 `it('renders the side rail on every screen', ...)` ブロックの**直前**に、新 test を追加する。

旧 test はこのタスクでは残す (このタスクが Red であることを担保するため)。具体的には `it('does not render an in-app title bar (Windows native chrome is used instead)', ...)` ブロックの**直後**、`it('renders the side rail on every screen', ...)` ブロックの**直前**に挿入。

挿入する内容:

```tsx
  it('does not render a side rail (SideRail removed in #677)', () => {
    render(<App />);
    expect(
      screen.queryByRole('navigation', { name: 'Allagan Eye navigation' }),
    ).toBeNull();
  });
```

- [ ] **Step 3: 新 test が FAIL し、他 test は PASS することを確認 (Red 確認)**

Run:

```bash
cd gui && npm test -- --run src/App.test.tsx
```

Expected:

- `does not render a side rail (SideRail removed in #677)` が **FAIL** (理由: nav 要素がまだ存在する)
- 残 7 test (drop / detecting / complete / preview / export / no-title-bar / renders-side-rail) が **PASS**
- 合計: 1 failed, 7 passed

この Red 状態が TDD の前提となる。

- [ ] **Step 4: commit (Red commit、TDD discipline の記録)**

Run:

```bash
git add gui/src/App.test.tsx
git commit -m "$(cat <<'EOF'
test(gui): add regression test for SideRail removal (Refs #677)

App.test.tsx に SideRail 不在を assert する test を追加 (TDD Red)。
本 commit 時点では SideRail が App.tsx に残っているため new test は
FAIL、旧 'renders the side rail on every screen' は PASS。

次 commit で App.tsx から SideRail を除去 + 旧 test 削除して Green に
する。

Refs #677

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: 1 file changed, +6 行程度。

---

## Task 3: TDD Green — App.tsx から SideRail 参照を除去 + 旧 test 削除

**Files:**

- Modify: `gui/src/App.tsx:4` (import 削除)
- Modify: `gui/src/App.tsx:15` (JSDoc 修正)
- Modify: `gui/src/App.tsx:35` (`<SideRail />` 削除)
- Modify: `gui/src/App.test.tsx:79-84` 旧 test 削除

- [ ] **Step 1: App.tsx から import を削除**

Edit `gui/src/App.tsx`:

old_string:

```tsx
import { SideRail } from './components/SideRail';
```

new_string: (削除 = 空文字列に置換ではなく、行ごと消す。Edit ツールで空文字列に置換する場合は前後改行も含めて指定)

具体的な Edit ツール呼び出し:

- old_string: `import { ConflictModal } from './components/ConflictModal';\nimport { DraftRestoreModal } from './components/DraftRestoreModal';\nimport { SideRail } from './components/SideRail';\nimport { StateSwitcher } from './components/StateSwitcher';`
- new_string: `import { ConflictModal } from './components/ConflictModal';\nimport { DraftRestoreModal } from './components/DraftRestoreModal';\nimport { StateSwitcher } from './components/StateSwitcher';`

- [ ] **Step 2: App.tsx の JSDoc を修正**

Edit `gui/src/App.tsx`:

- old_string:

```text
 * Root component. Wires the fixed shell (SideRail + StateSwitcher) and
```

- new_string:

```text
 * Root component. Wires the fixed shell (StateSwitcher) and
```

- [ ] **Step 3: App.tsx から `<SideRail />` 行を削除**

Edit `gui/src/App.tsx`:

- old_string:

```tsx
      <div className={styles.body}>
        <SideRail />
        <main className={styles.main}>
```

- new_string:

```tsx
      <div className={styles.body}>
        <main className={styles.main}>
```

- [ ] **Step 4: App.test.tsx から旧 test を削除**

Edit `gui/src/App.test.tsx`:

- old_string:

```tsx
  it('renders the side rail on every screen', () => {
    render(<App />);
    expect(
      screen.getByRole('navigation', { name: 'Allagan Eye navigation' }),
    ).toBeInTheDocument();
  });
```

- new_string: (空文字列 — テスト block を完全に削除)

末尾の blank line / `});` (describe close) は維持されること。

- [ ] **Step 5: App.test.tsx が全 test PASS することを確認 (Green 確認)**

Run:

```bash
cd gui && npm test -- --run src/App.test.tsx
```

Expected: 7 test 全 PASS (`drop` / `detecting` / `complete` / `preview` / `export` / `does not render in-app title bar` / `does not render a side rail (SideRail removed in #677)`)。0 failed.

- [ ] **Step 6: SideRail.test.tsx は依然 PASS することを確認 (まだ削除前)**

Run:

```bash
cd gui && npm test -- --run src/components/SideRail.test.tsx
```

Expected: 1 test PASS (`renders ALLAGAN wordmark and 4 decorative icons`)。SideRail.tsx 自体はまだ存在するため。次タスクで物理削除する。

- [ ] **Step 7: TypeScript 型チェック**

Run:

```bash
cd gui && npm run typecheck
```

Expected: 0 error。App.tsx の `import` 削除によって型エラーが出ないこと。

- [ ] **Step 8: commit (Green commit)**

Run:

```bash
git add gui/src/App.tsx gui/src/App.test.tsx
git commit -m "$(cat <<'EOF'
refactor(gui): remove SideRail render from App (Refs #677)

App.tsx から SideRail import / JSX / JSDoc 言及を除去し、
App.test.tsx の旧 'renders the side rail on every screen' test を
削除。

これにより Task 2 で追加した 'does not render a side rail
(SideRail removed in #677)' test が PASS する (TDD Green)。

SideRail コンポーネントファイル自体 (.tsx / .module.css / .test.tsx)
は次 commit で物理削除する。

Refs #677

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: 2 files changed。

---

## Task 4: Refactor — SideRail コンポーネント 3 file を物理削除

**Files:**

- Delete: `gui/src/components/SideRail.tsx`
- Delete: `gui/src/components/SideRail.module.css`
- Delete: `gui/src/components/SideRail.test.tsx`

- [ ] **Step 1: 3 file を削除**

Run:

```bash
git rm gui/src/components/SideRail.tsx gui/src/components/SideRail.module.css gui/src/components/SideRail.test.tsx
```

Expected: 3 file が staged delete 状態になる。

- [ ] **Step 2: 全 GUI test が PASS することを確認**

Run:

```bash
cd gui && npm test -- --run
```

Expected: 全 test PASS。`SideRail.test.tsx` は削除済みなので test count が減る。他 test (App.test.tsx 含む) は不変。

- [ ] **Step 3: TypeScript 型チェック**

Run:

```bash
cd gui && npm run typecheck
```

Expected: 0 error。

- [ ] **Step 4: ESLint チェック**

Run:

```bash
cd gui && npm run lint
```

Expected: 0 error / warning。Unused import 等の警告が出ないこと。

- [ ] **Step 5: Vite build**

Run:

```bash
cd gui && npm run build
```

Expected: build 成功、`gui/dist/` 生成。SideRail 関連の import エラーが出ないこと。

- [ ] **Step 6: Rust 型チェック (Tauri backend に影響無いことを sanity check)**

Run:

```bash
cd gui/src-tauri && cargo check
```

Expected: 0 error (warnings は cli の元から有るもののみ)。SideRail 削除は Rust 側に影響しないが、PR チェックリスト遵守のため実行。

- [ ] **Step 7: commit**

Run:

```bash
git commit -m "$(cat <<'EOF'
refactor(gui): delete SideRail component files (Refs #677)

dead code となった以下 3 file を物理削除:

- gui/src/components/SideRail.tsx (25 行)
- gui/src/components/SideRail.module.css (46 行)
- gui/src/components/SideRail.test.tsx (14 行)

Task 3 で App.tsx から render を除去済のため consumer は存在せず、
npm run lint / typecheck / test / build 全 pass を確認。

CSS 変数 (--ae-bg-deep / --ae-gold-rgb / --ae-font-ui 等) は他
17+ file が共有しているため tokens.css には触れない。

Refs #677

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: 3 files deleted, -85 行程度。

---

## Task 5: Doc 更新 — docs/ui-architecture.md

**Files:**

- Modify: `docs/ui-architecture.md:344` (§8 リサイズ方針)
- Modify: `docs/ui-architecture.md:354` (§9 App 階層図)
- Modify: `docs/ui-architecture.md:364` (§9 components/ 一覧)
- Modify: `docs/ui-architecture.md` (§9 末尾に SideRail 削除注記を追加)

- [ ] **Step 1: §8 リサイズ方針の SideRail 言及行を修正**

Edit `docs/ui-architecture.md`:

- old_string:

```text
  - SideRail 48px 固定、メイン領域 `flex: 1`
```

- new_string:

```text
  - メイン領域 `flex: 1` (body 全幅、旧 SideRail は #677 で削除済)
```

- [ ] **Step 2: §9 App 階層図から SideRail 行を削除**

Edit `docs/ui-architecture.md`:

- old_string:

```text
└── body
    ├── SideRail            (ALLAGAN + 4 アイコン)
    └── main
```

- new_string:

```text
└── body
    └── main
```

- [ ] **Step 3: §9 components/ 一覧から SideRail を削除**

Edit `docs/ui-architecture.md`:

- old_string: `├── SideRail / StateSwitcher                      (shell)`
- new_string: `├── StateSwitcher                                 (shell)`

- [ ] **Step 4: §9 末尾 (既存「カスタム title bar は無し」注記の直後) に SideRail 削除注記を追加**

Edit `docs/ui-architecture.md`:

- old_string:

```text
注: **カスタム title bar は無し** (prototype の WindowChrome は handoff 時点の
MacOS 風デザインだったが、L2 は Windows-only (#451) のため Tauri のネイティブ
Windows title bar に一本化。`tauri.conf.json` の `title: "Allagan Eye"` が
表示される)。
```

- new_string:

```text
注: **カスタム title bar は無し** (prototype の WindowChrome は handoff 時点の
MacOS 風デザインだったが、L2 は Windows-only (#451) のため Tauri のネイティブ
Windows title bar に一本化。`tauri.conf.json` の `title: "Allagan Eye"` が
表示される)。

注: **SideRail (旧 ALLAGAN + 4 装飾アイコン) は削除済** (#677、2026-05-13)。
`body` の唯一の子は `main` で、48px 帯はなくなり main が body 全幅。
`docs/design/bundle/project/variants/aether.jsx` の mock には残るが handoff
snapshot として保持しており、production 実装からは削除されている。
```

- [ ] **Step 5: markdownlint で構文を確認**

Run:

```bash
bash scripts/check-markdownlint.sh docs/ui-architecture.md
```

Expected: 0 error (該当 file)。

- [ ] **Step 6: 差分を目視確認**

Run:

```bash
git diff docs/ui-architecture.md
```

Expected: 上記 4 つの編集のみ。他 section に変更が漏れていないこと。

---

## Task 6: Doc 更新 — docs/design/README.md (handoff bundle divergence note)

**Files:**

- Modify: `docs/design/README.md` (bundle/ 説明 code block 直後に divergence note を追加)

- [ ] **Step 1: bundle/ 説明 code block 直後に divergence 注記を追加**

Edit `docs/design/README.md`:

- old_string:

````text
            ├── neon.jsx              — B variant (参考、採用しない)
            └── ops.jsx               — C variant (参考、採用しない)
```

## `gui/` — Tauri GUI 実装ディレクトリ (L2)
````

- new_string:

````text
            ├── neon.jsx              — B variant (参考、採用しない)
            └── ops.jsx               — C variant (参考、採用しない)
```

注: 実装側では #677 で SideRail コンポーネントを mock から削除済 (handoff
snapshot としての `aether.jsx` は変更不可ポリシーにより保持、production
実装と乖離あり)。

## `gui/` — Tauri GUI 実装ディレクトリ (L2)
````

(注: 上記 old_string / new_string は code fence の closing ` ``` ` と次 section heading を含むため 4-backtick fence で囲んでいる。Edit ツール呼び出し時は backtick の literal をそのまま渡す。)

- [ ] **Step 2: markdownlint で構文を確認**

Run:

```bash
bash scripts/check-markdownlint.sh docs/design/README.md
```

Expected: 0 error。MD022 (heading-blanks: 見出し前後の blank) と MD028 (blockquote 連結) に違反していないこと。

- [ ] **Step 3: 差分を目視確認**

Run:

```bash
git diff docs/design/README.md
```

Expected: 上記 1 つの編集のみ (divergence 注記 1 段落 + blank line 追加)。

- [ ] **Step 4: commit (Task 5 + Task 6 をまとめて 1 commit)**

Run:

```bash
git add docs/ui-architecture.md docs/design/README.md
git commit -m "$(cat <<'EOF'
docs: sync SideRail removal in ui-architecture / design README (Refs #677)

docs/ui-architecture.md:
- §8 リサイズ方針から SideRail 48px 固定の言及を削除し main が
  body 全幅であることを反映
- §9 App 階層図から SideRail ブランチを削除
- §9 components/ 一覧から SideRail を削除し StateSwitcher のみに
- §9 末尾に SideRail 削除注記を追加 (旧「title bar 無し」注記と同列)

docs/design/README.md:
- bundle/ 説明 code block 直後に divergence 注記を追加
  (aether.jsx mock は handoff snapshot として保持、production 実装は
  #677 で SideRail を削除済)

docs/design/bundle/project/variants/aether.jsx は handoff bundle
不変ポリシー (docs/design/README.md「変更不可、参照のみ」) により
改変しない。

Refs #677

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: 2 files changed。

---

## Task 7: 最終 verification (Iron Law 6 PR 作成前自動チェック)

**Files:** なし (検証のみ)

- [ ] **Step 1: 全 GUI test を最後に再実行**

Run:

```bash
cd gui && npm test -- --run
```

Expected: 全 test PASS。`SideRail.test.tsx` は削除済 (collect されない)、`App.test.tsx` の 7 test (`renders the drop screen` 等 5 件 + `does not render in-app title bar` + `does not render a side rail`) 含め全 PASS。

- [ ] **Step 2: ESLint**

Run:

```bash
cd gui && npm run lint
```

Expected: 0 error / 0 warning。

- [ ] **Step 3: TypeScript 型チェック**

Run:

```bash
cd gui && npm run typecheck
```

Expected: 0 error。

- [ ] **Step 4: Vite build**

Run:

```bash
cd gui && npm run build
```

Expected: build 成功、`gui/dist/index.html` 等生成。

- [ ] **Step 5: Rust 型チェック**

Run:

```bash
cd gui/src-tauri && cargo check
```

Expected: 0 error。

- [ ] **Step 6: markdownlint 全 file (CI 同等)**

Run:

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 7: SideRail 残存参照の最終 scan**

Run:

```bash
grep -rn "SideRail" gui/src docs --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" --include="*.css" --include="*.md" 2>&1 | grep -v "docs/design/bundle/" | grep -v "docs/superpowers/"
```

Expected: 期待される残存参照のみ:

- `docs/ui-architecture.md` (削除済 / 注記中の言及 1 行のみ、`旧 SideRail` 等)
- `docs/design/README.md` (divergence 注記中の 1 行のみ)
- それ以外の `gui/src` 配下からの参照は 0 件

bundle/ と superpowers/ 配下は unchanged (handoff bundle / spec / plan として SideRail への言及が残ることが正)。

- [ ] **Step 8: Iron Law 6 PR Pre-flight 再確認**

Run:

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "677" --state all
```

Expected: 取り込み未済 commit 0、並行 PR 0 (Task 1 から状態変化していないこと)。新規 commit があれば touched files との交差を再確認し、必要なら merge して Step 1-6 を再実行。

---

## Task 8: PR 作成 + push

**Files:** なし (リモート操作のみ)

- [ ] **Step 1: branch を push**

Run:

```bash
git push -u origin claude/eloquent-joliot-835af8
```

Expected: push 成功。

- [ ] **Step 2: PR を作成**

PR 本文ファイルを準備:

```bash
cat > /tmp/pr-body-677.md <<'EOF'
## 概要

[#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) GUI 左 SideRail 全体削除。装飾アイコン (`◈ ◇ ◆ ⎊`) のうち先頭が `iconActive` で強調表示され「クリック可能な選択 UI」と誤認させる問題を、SideRail コンポーネントごと物理削除する形で解消する。

## 変更内容

### 削除 (3 file)

- `gui/src/components/SideRail.tsx`
- `gui/src/components/SideRail.module.css`
- `gui/src/components/SideRail.test.tsx`

### 改修 (4 file)

- `gui/src/App.tsx`: import / JSX / JSDoc から SideRail 言及を除去
- `gui/src/App.test.tsx`: 旧 `renders the side rail on every screen` test を削除し、`does not render a side rail (SideRail removed in #677)` regression test を追加
- `docs/ui-architecture.md`: §8 リサイズ方針・§9 階層図 / components 一覧から SideRail 言及を削除、§9 末尾に削除注記を追加
- `docs/design/README.md`: handoff bundle 説明部に divergence note を追加 (aether.jsx mock は snapshot として保持、production 実装と乖離あり)

### 不変 (明示)

- `gui/src/styles/tokens.css`: `--ae-bg-deep` / `--ae-gold-rgb` / `--ae-font-ui` は他 17 file が共有のため不変
- `gui/src/App.module.css`: `.body` / `.main` flex layout は SideRail 非依存のため不変
- `docs/design/bundle/project/variants/aether.jsx`: handoff bundle 不変ポリシー (docs/design/README.md「変更不可、参照のみ」) に従い不変

## 受入条件 (#677 逐条検証)

- [x] 4 つのアイコン (`◈ ◇ ◆ ⎊`) を画面から除去 ((a) または (b) のいずれか採用) → **(b) SideRail 全体削除** で達成 (App.tsx から `<SideRail />` 除去)
- [x] `SideRail.test.tsx` の関連 assertion 更新 → `SideRail.test.tsx` 自体を削除 + App.test.tsx で `does not render a side rail` regression test を追加
- [x] 関連 design doc (`aether.jsx` 等) の整合性確認 (削除と乖離する場合はコメントで明示) → `docs/design/README.md` に divergence 注記を追加、`docs/ui-architecture.md` から SideRail 記述を除去
- [x] `jest-axe` で a11y violation が発生しないこと → 既存 8 箇所 (5 screen + 3 modal) の axe テスト全 PASS

## Self-Test Report

### machine-verified

- [x] `cd gui && npm test -- --run` 全 PASS
- [x] `cd gui && npm run lint` 0 error
- [x] `cd gui && npm run typecheck` 0 error
- [x] `cd gui && npm run build` 成功
- [x] `cd gui/src-tauri && cargo check` 0 error
- [x] `bash scripts/check-markdownlint.sh` 0 error

### machine-unverifiable (Idios 実機検証依頼)

- `cd gui && npm run tauri dev` で 5 screen (`drop` / `detecting` / `complete` / `preview` / `export`) を順に表示
- 左端 48px 帯 (旧 SideRail) が完全に消えていること
- 5 screen の main コンテンツが想定どおり左端まで広がっていること
- 視覚的な regression (層レイアウトの崩れ・余白の不整合・StateSwitcher の位置ずれ等) がないこと

## Pre-flight (Iron Law 6)

- [x] `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` で取り込み未済 commit 確認、touched files との交差なし
- [x] `gh pr list --search "677"` で並行 worktree PR 重複なし
- [x] base sync 完了

## Session

session-id: `eloquent-joliot-835af8`

Refs #677
EOF
```

PR を作成:

```bash
gh pr create \
  --base develop-0.2.0 \
  --head claude/eloquent-joliot-835af8 \
  --title "refactor(gui): SideRail 全体削除 (Refs #677)" \
  --body-file /tmp/pr-body-677.md
```

Expected: PR URL が返る (`https://github.com/Idios/kobutachan-allaganeye/pull/<num>`)。`Closes` / `Fixes` / `Resolves` keyword が本文に含まれていないことを再確認 (Iron Law 4)。

- [ ] **Step 3: PR 本文を確認**

Run:

```bash
gh pr view --json title,body,baseRefName,headRefName
```

Expected: `Refs #677` のみ含まれ、`Closes #677` / `Fixes #677` / `Resolves #677` は含まれない。base = `develop-0.2.0`、head = `claude/eloquent-joliot-835af8`。

- [ ] **Step 4: CI を待つ**

Run:

```bash
gh pr checks --watch
```

Expected: 全 check PASS。failure があれば `/iterate-review <PR#>` で対応するか、本セッション内で fix する判断を行う (本 plan のスコープ外)。

---

## Task 9: マージ後の handoff (Wave 2 で対応、本 plan のスコープ外)

**Files:** なし

- 本 PR がマージされたら、`/close-issue #677` skill を起動して受入条件をマージ後 base ブランチで実測再検証し、ユーザー承認のもと `gh issue close #677` を実行する (Iron Law 4: 手動クローズ厳守)
- 派生 issue / 残タスクがあれば `/close-issue` 内のトリアージで (B) 新 issue / (C) 既存 issue 追記 に振り分ける
- **本 plan の範囲は PR 作成完了まで**。`/close-issue` は別 session / 別 timing で起動する

---

## Plan Self-Review

### 1. Spec coverage

| Spec 要素 | 該当 Task |
| --- | --- |
| §1 Goal (SideRail 全体削除) | Task 3 + Task 4 |
| §2 Background | 本 plan 冒頭の Goal / Architecture に反映 |
| §3 Decisions (Q1=b / Q2=α / 戦略 A) | Architecture + Task 4 (Q1) + Task 6 (Q2) |
| §4 Scope in/out | Task 1 (sanity) + Task 4-6 |
| §5.1 削除 3 file | Task 4 |
| §5.2 改修 App.tsx | Task 3 |
| §5.2 改修 App.test.tsx | Task 2 + Task 3 |
| §5.2 改修 ui-architecture.md | Task 5 |
| §5.2 改修 design/README.md | Task 6 |
| §5.3 不変ファイル | Task 4 Step 7 commit message で明示 / Task 6 commit message で明示 |
| §6 Data flow 影響なし | (検証なし、本 plan で扱う触れない範囲を明示) |
| §7.1 unit/integration test | Task 2 + Task 3 + Task 4 + Task 7 |
| §7.2 jest-axe | Task 4 Step 2 (全 GUI test 内に含まれる) + Task 7 Step 1 |
| §7.3 受入条件 4 項目 | Task 8 PR 本文の checkbox section |
| §7.4 実機検証 | Task 8 PR 本文の machine-unverifiable section |
| §8 PR / Iron Law | Task 1 (Pre-flight) + Task 7 (verification) + Task 8 (PR 作成、Refs #677) |
| §9 Risk / Open | Task 4 + Task 7 で残存参照 scan 実施 |

ギャップ: なし。

### 2. Placeholder scan

Plan 内に「TBD」「TODO」「implement later」「fill in details」「add appropriate error handling」等の placeholder は存在しない。すべての code edit に exact old_string / new_string、すべての検証に exact command + expected output を記載済み。

### 3. Type / 識別子一貫性

- `does not render a side rail (SideRail removed in #677)` (test 名) は Task 2 Step 2 で定義、Task 3 Step 5・Task 7 Step 1 で参照 — 一致
- `renders the side rail on every screen` (旧 test 名) は Task 3 Step 4 で削除対象として参照 — 一致
- 行番号 (App.tsx L4 / L15 / L35、App.test.tsx L79、ui-architecture.md L344 / L354 / L364) は spec と一貫
- 環境依存 path (`/tmp/pr-body-677.md`) は Bash tool が POSIX path を expand する。Windows でも Git Bash 経由で動作するが、必要に応じて `./pr-body-677.md` 等に変更してよい

修正不要、self-review pass。
