# L2 Tier 1 #653 StateSwitcher dev only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `StateSwitcher` を `import.meta.env.DEV` で gate し、production 配布版で render させない。`CompleteScreen` topBar との z-index 重複 ([#653](https://github.com/Idios/kobutachan-allaganeye/issues/653)) を原理的に解消する。

**Architecture:** `gui/src/components/StateSwitcher.tsx` 関数本体先頭に early return (`if (!import.meta.env.DEV) return null;`) を 1 行追加する component-local gating。`App.tsx` callsite と `StateSwitcher.module.css` は不変。vitest で PROD gate test (`vi.stubEnv('DEV', '')`) を新規追加し、既存 DEV render test と並走で regression guard。

**Tech Stack:** React 19 / TypeScript / Vite / Vitest 1.x / `import.meta.env.DEV` (Vite build mode flag)

---

## File Structure

| 区分 | path | 責務 |
| --- | --- | --- |
| Modify | `gui/src/components/StateSwitcher.tsx` | 関数本体先頭に DEV gate を追加 |
| Modify | `gui/src/components/StateSwitcher.test.tsx` | PROD gate failing test を追加 (既存 DEV render test は維持) |
| Unchanged | `gui/src/components/StateSwitcher.module.css` | z-index / position は dev で従来通り維持 |
| Unchanged | `gui/src/App.tsx` | callsite 不変 (`<StateSwitcher />`) |
| Unchanged | `gui/src/main.tsx` | `import.meta.env.PROD` / `DEV` 既存使用 (line 11 / 22)、本 issue では touch しない |

設計判断は spec [docs/superpowers/specs/2026-05-03-l2-tier1-stateswitcher-dev-only-design.md](../specs/2026-05-03-l2-tier1-stateswitcher-dev-only-design.md) §3 に確定済。

---

## Task 1: PROD gate failing test を追加 (TDD red)

**Files:**

- Modify: `gui/src/components/StateSwitcher.test.tsx`

- [ ] **Step 1: 既存 test ファイルを Read で確認**

  Read tool で `gui/src/components/StateSwitcher.test.tsx` 全体を読み、既存 3 件 (`renders all 5 screen labels` / `marks the active tab with aria-pressed="true"` / `navigates the app store on click`) のスタイルを確認する。

- [ ] **Step 2: 既存 test の import 行を更新し、新規 describe block を末尾に追加**

  既存ファイルは line 1-3 で `vitest` から `beforeEach`, `describe`, `expect`, `it` を import している。`afterEach` と `vi` を import に追加し、末尾に新規 describe block を追加する。

  最終的な `gui/src/components/StateSwitcher.test.tsx` 全文 (Edit tool で 2 箇所変更):

  ```tsx
  import { render, screen } from '@testing-library/react';
  import userEvent from '@testing-library/user-event';
  import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

  import { useAppStateStore } from '../state/appStateStore';
  import { StateSwitcher } from './StateSwitcher';

  beforeEach(() => {
    useAppStateStore.getState().reset();
  });

  describe('StateSwitcher', () => {
    it('renders all 5 screen labels', () => {
      render(<StateSwitcher />);
      expect(screen.getByRole('button', { name: 'インポート' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '検知中' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '一覧' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '境界調整' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '書出し' })).toBeInTheDocument();
    });

    it('marks the active tab with aria-pressed="true"', () => {
      render(<StateSwitcher />);
      const drop = screen.getByRole('button', { name: 'インポート' });
      expect(drop.getAttribute('aria-pressed')).toBe('true');
    });

    it('navigates the app store on click', async () => {
      const user = userEvent.setup();
      render(<StateSwitcher />);
      await user.click(screen.getByRole('button', { name: '一覧' }));
      expect(useAppStateStore.getState().screen).toBe('complete');
    });
  });

  // #653 -- production build (Tauri bundle / Portable ZIP) では
  // StateSwitcher を render しない。dev only に絞って topBar との
  // z-index 重複を原理的に解消する (spec 2026-05-03-l2-tier1-stateswitcher-dev-only-design.md §3)。
  describe('StateSwitcher production gating', () => {
    beforeEach(() => {
      // import.meta.env.DEV を falsy 値 (空文字列) に上書きして production を simulate。
      // Vite が DEV を boolean として配布する一方、vi.stubEnv は string で受け取る。
      // `if (!import.meta.env.DEV)` は falsy 判定なので空文字列で OK。
      vi.stubEnv('DEV', '');
    });
    afterEach(() => {
      vi.unstubAllEnvs();
    });

    it('returns null when import.meta.env.DEV is falsy (production build)', () => {
      const { container } = render(<StateSwitcher />);
      expect(container).toBeEmptyDOMElement();
    });
  });
  ```

- [ ] **Step 3: 新規 test を実行し fail することを確認 (TDD red)**

  Run:

  ```bash
  cd gui && npx vitest run src/components/StateSwitcher.test.tsx
  ```

  Expected:
  - 既存 3 件 PASS (`renders all 5 screen labels` / `marks the active tab` / `navigates the app store on click`)
  - 新規 1 件 FAIL: `returns null when import.meta.env.DEV is falsy (production build)` (現状 StateSwitcher は DEV gate を持たないので、`container` には switcher の `<div>` が render される → `toBeEmptyDOMElement()` が fail する)

  注: もし `vi.stubEnv('DEV', '')` が import.meta.env.DEV に伝搬しない (Vitest version 依存) 場合、 `vi.stubEnv('MODE', 'production')` に切り替えて再実行する。Vitest 1.x では `stubEnv` が `import.meta.env` の `DEV`/`PROD`/`MODE` 特殊キーに同期する仕様。

- [ ] **Step 4: red 確認後 commit (実装前のテスト追加 = 先行 commit)**

  ```bash
  git add gui/src/components/StateSwitcher.test.tsx
  git commit -m "$(cat <<'EOF'
  test: StateSwitcher production gating の failing test を追加 (#653)

  vi.stubEnv('DEV', '') で production build を simulate し、
  StateSwitcher が null を返すことを assert。現状実装は gate を
  持たないため fail する (TDD red)。

  Refs #653

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 2: StateSwitcher.tsx に DEV gate を実装 (TDD green)

**Files:**

- Modify: `gui/src/components/StateSwitcher.tsx`

- [ ] **Step 1: 既存 component を Read で確認**

  Read tool で `gui/src/components/StateSwitcher.tsx` 全体を読み、line 21 の関数定義 + line 24 の return を確認する。

- [ ] **Step 2: 関数本体先頭に DEV gate early return を追加**

  Edit tool で line 21-23 を以下のように更新:

  変更前:

  ```tsx
  export function StateSwitcher() {
    const screen = useAppStateStore((s) => s.screen);
    const navigate = useAppStateStore((s) => s.navigate);
  ```

  変更後:

  ```tsx
  export function StateSwitcher() {
    // #653 -- production build (Tauri bundle / Portable ZIP) では
    // render しない。CompleteScreen topBar との z-index 重複を原理的に
    // 解消する (spec 2026-05-03-l2-tier1-stateswitcher-dev-only-design.md §3)。
    // import.meta.env.DEV は Vite が build mode で `true` (dev) /
    // `false` (production) に inline 展開し、production build では
    // dead code elimination で本 component が tree から除去される。
    if (!import.meta.env.DEV) return null;
    const screen = useAppStateStore((s) => s.screen);
    const navigate = useAppStateStore((s) => s.navigate);
  ```

  注: hook (`useAppStateStore`) は early return より**後**に call する必要があるため、early return を hook より先に置く。React rules-of-hooks に整合 (条件分岐前 hook call では production で hook order が不一致になる、現状の DEV-only render では早期 return で問題なし)。

- [ ] **Step 3: 全 test を実行し全 PASS を確認 (TDD green)**

  Run:

  ```bash
  cd gui && npx vitest run src/components/StateSwitcher.test.tsx
  ```

  Expected:
  - 既存 3 件 PASS (DEV render は従来通り)
  - 新規 1 件 PASS (`returns null when import.meta.env.DEV is falsy (production build)`)
  - Total: 4/4 PASS

- [ ] **Step 4: commit**

  ```bash
  git add gui/src/components/StateSwitcher.tsx
  git commit -m "$(cat <<'EOF'
  fix: StateSwitcher を dev only に絞り topBar との z-index 重複を解消 (#653)

  関数本体先頭に `if (!import.meta.env.DEV) return null;` を追加。
  production build では dead code elimination で本 component が
  tree から除去され、CompleteScreen topBar (z-index 重複) との
  物理的衝突が原理的に消滅。

  hook (useAppStateStore) は early return より後で call するため
  React rules-of-hooks に整合。

  PR #641 実機検証で発覚した bug (元設計 "Dev-only screen switcher"
  コメントと常時 render の乖離) を解消。

  Refs #653

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Task 3: GUI path 自動チェック全 pass + 軽微 fix があれば commit

**Files:** (確認のみ、必要に応じて修正)

- [ ] **Step 1: lint / typecheck / vitest 全実行**

  Run:

  ```bash
  cd gui && npm run lint
  cd gui && npm run typecheck
  cd gui && npm test
  ```

  Expected:
  - eslint: 0 errors / 0 warnings (`StateSwitcher.tsx` の新コメント / new comment 行も pass)
  - tsc --noEmit: 0 errors
  - vitest: StateSwitcher 関連 4/4 PASS、project 全体も全 PASS

- [ ] **Step 2: vite production build 確認**

  Run:

  ```bash
  cd gui && npm run build
  ```

  Expected:
  - vite が `gui/dist/` を生成、ビルドエラーなし
  - bundle size 確認 (StateSwitcher が production tree から除去されることでわずかに減少、ただし数値検証は不要)

- [ ] **Step 3: cargo check (Rust 側変更なしの regression 担保)**

  Run:

  ```bash
  cd gui/src-tauri && cargo check
  ```

  Expected:
  - 0 errors (本 PR では Rust touch なし、念のため regression 担保)

- [ ] **Step 4: markdownlint (本 plan + 本 spec doc を含む全 .md)**

  Run:

  ```bash
  bash scripts/check-markdownlint.sh
  ```

  Expected:
  - 全 .md file 0 errors

- [ ] **Step 5: 軽微 fix があれば commit、なければ skip**

  もし Step 1-4 のいずれかで failure (eslint warning / typecheck / markdown lint) が出た場合は Edit tool で fix し、以下の commit をする (fix 対象のみ stage):

  ```bash
  git add <fixed files>
  git commit -m "$(cat <<'EOF'
  fix: lint / typecheck / markdownlint pass のための軽微 fix (#653)

  Refs #653

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

  fix が 0 件なら本 step skip。

---

## Task 4: PR Pre-flight (Iron Law 6) + PR 作成 + issue 完了コメント

**Files:** (確認のみ、変更なし)

- [ ] **Step 1: Iron Law 6 Pre-flight Step 1 - base ブランチ最新化確認**

  Run:

  ```bash
  git fetch origin develop-0.2.0
  git log HEAD..origin/develop-0.2.0 --oneline
  ```

  Expected:
  - 出力 0 行 (現 HEAD が origin/develop-0.2.0 を内包) または develop-0.2.0 に新規 commit が入っている場合は内容を確認

  注: 本 worktree は post-merge state (PR #672 マージ後 develop-0.2.0 を merge 済) なので通常 0 行のはず。

- [ ] **Step 2: 取り込み未済 commit が当 PR の touched files (`gui/src/components/StateSwitcher.tsx` / `gui/src/components/StateSwitcher.test.tsx`) と交差する場合のみ merge**

  もし Step 1 で取り込み未済 commit があり、上記 file を touch している場合:

  ```bash
  git merge origin/develop-0.2.0
  ```

  → conflict 解決 → Task 3 の自動チェック (lint / typecheck / vitest / build / cargo check / markdownlint) を再実行 → 全 pass 確認。

  交差しない場合は merge 不要。

- [ ] **Step 3: Iron Law 6 Pre-flight Step 2 - 並行 worktree PR 重複確認**

  Run:

  ```bash
  gh pr list --repo Idios/kobutachan-allaganeye --search "653" --state open
  ```

  Expected: 重複 PR なし。あれば内容確認 → ユーザーに報告 → 進行可否判断。

- [ ] **Step 4: ローカル commit を origin に push**

  Run:

  ```bash
  git push -u origin claude/dazzling-mestorf-10914f
  ```

  Expected: push 成功。

- [ ] **Step 5: PR 作成 (Iron Law 4: Closes/Fixes/Resolves 禁止、`Refs #653` のみ)**

  Run:

  ```bash
  gh pr create \
    --repo Idios/kobutachan-allaganeye \
    --base develop-0.2.0 \
    --head claude/dazzling-mestorf-10914f \
    --title "fix: StateSwitcher を dev only に絞り topBar との z-index 重複を解消 (Refs #653)" \
    --body "$(cat <<'EOF'
  ## Summary

  `StateSwitcher` を `import.meta.env.DEV` で gate し、production 配布版 (Tauri bundle / Portable ZIP) で render させないことで、`CompleteScreen` topBar との z-index 重複 (#653) を原理的に解消する。

  - `gui/src/components/StateSwitcher.tsx` 関数本体先頭に `if (!import.meta.env.DEV) return null;` 追加
  - `gui/src/components/StateSwitcher.test.tsx` に PROD gate failing test (`vi.stubEnv('DEV', '')`) を追加し、既存 DEV render test 3 件と並走で regression guard
  - `App.tsx` callsite / `StateSwitcher.module.css` は不変

  ## Spec / Plan

  - spec: [docs/superpowers/specs/2026-05-03-l2-tier1-stateswitcher-dev-only-design.md](docs/superpowers/specs/2026-05-03-l2-tier1-stateswitcher-dev-only-design.md) (commit 18f9b71)
  - plan: docs/superpowers/plans/2026-05-03-l2-tier1-stateswitcher-dev-only-implementation.md

  ## Refs

  Refs #653

  ## 受け入れ条件 mapping (issue #653)

  - [x] CompleteScreen topBar.actions が StateSwitcher と物理的に重ならず操作可能 → production gating で原理的解消 (machine-unverifiable: Idios 実機目視)
  - [x] 他画面 (drop / detecting / preview / export) でも StateSwitcher との重複なし → 全画面で render されない (machine-unverifiable: Idios 横展開確認)
  - [x] 修正方針 (1)-(4) の中から Idios 選択した案で実装 → (1) DEV only 確定、component-local gating で実装
  - [x] vitest で StateSwitcher の表示条件 (dev only か常時か) を pin → PROD gate test 新規 + DEV render test 維持
  - [x] eslint / typecheck / vitest 全通過 → Self-Test Report 参照

  ## Self-Test Report

  ### machine-verifiable
  - [x] `cd gui && npm run lint` → 0 errors
  - [x] `cd gui && npm run typecheck` → 0 errors
  - [x] `cd gui && npm test` → StateSwitcher 関連 4/4 PASS、project 全体も全 PASS
  - [x] `cd gui && npm run build` → vite production build pass
  - [x] `cd gui/src-tauri && cargo check` → 0 errors (Rust touch なし regression 担保)
  - [x] `bash scripts/check-markdownlint.sh` → 全 .md 0 errors
  - [x] Iron Law 6 Pre-flight: develop-0.2.0 fetch + 交差確認 + 並行 worktree PR 重複確認 完了

  ### machine-unverifiable (Idios 実機検証)
  - `cd gui && npm run tauri dev` で StateSwitcher が従来通り表示
  - `cd gui && npm run tauri build` 後の production exe で StateSwitcher 非表示
  - CompleteScreen topBar 4 ボタン全クリック可能 (production)
  - 他画面 (drop / detecting / preview / export) でも StateSwitcher 非表示確認

  session-id: dazzling-mestorf-10914f

  🤖 Generated with [Claude Code](https://claude.com/claude-code)
  EOF
  )"
  ```

  Expected: PR URL を取得 (例 `https://github.com/Idios/kobutachan-allaganeye/pull/<番号>`)。

- [ ] **Step 6: issue にコメント追記 (`docs/issue-policy.md §7 完了時` に従う)**

  Run (PR 番号を Step 5 の URL から取得):

  ```bash
  gh issue comment 653 --repo Idios/kobutachan-allaganeye --body "$(cat <<'EOF'
  完了: dazzling-mestorf-10914f → PR #<番号>

  StateSwitcher を `import.meta.env.DEV` で gate し production 配布版で render させない実装。topBar との z-index 重複を原理的に解消。Idios 実機検証 (dev / production build smoke + 全画面横展開) は PR レビュー段階で実施。
  EOF
  )"
  ```

  注: `<番号>` を Step 5 で取得した PR 番号に置換。日本語本文は HEREDOC で破損回避。

---

## Self-Review

(本 plan 著者である writing-plans skill による self-review。skill 指示 §"Self-Review" 準拠)

### 1. Spec coverage

| spec section | 担当 Task |
| --- | --- |
| §1 Background | (Task 全体で前提) |
| §2 Goals | Tasks 2 (gating 実装) + Task 3 verification |
| §3 Architecture - gating 位置 | Task 2 Step 2 |
| §3 Architecture - App.tsx callsite 不変 | (file structure で明示、変更タスクなし) |
| §3 Architecture - CSS 変更なし | (file structure で明示、変更タスクなし) |
| §3 Architecture - import.meta.env.DEV 挙動 | Task 2 Step 2 のコメントで言及 |
| §3 Architecture - 他画面波及確認 | (Grep 確認済、変更タスクなし) |
| §4 Test - 既存 test 維持 | Task 1 Step 2 (既存 3 件を template に維持) |
| §4 Test - PROD gate test | Task 1 Step 2 |
| §4 Test - E2E 観点 | Task 4 PR body machine-unverifiable |
| §5 Verification - machine-verifiable 全 path | Task 3 Step 1-4 |
| §5 Verification - machine-unverifiable | Task 4 PR body |
| §6 Cross-cutting / PR - Iron Law 1 受け入れ条件 mapping | Task 4 Step 5 PR body |
| §6 Cross-cutting / PR - Iron Law 3 scope | (file structure で touch ファイル明示) |
| §6 Cross-cutting / PR - Iron Law 4 Closes 禁止 | Task 4 Step 5 PR body (`Refs #653` のみ) |
| §6 Cross-cutting / PR - Iron Law 6 Pre-flight | Task 4 Steps 1-3 |
| §6 Cross-cutting / PR - 受け入れ条件 5 項目 mapping | Task 4 Step 5 PR body |

ギャップなし。全 spec section を Task でカバー。

### 2. Placeholder scan

- "TBD" / "TODO" / "implement later" / "fill in details" → なし
- "Add appropriate error handling" / "handle edge cases" → なし
- "Write tests for the above" → なし (test code は Task 1 Step 2 に full code 記載)
- "Similar to Task N" → なし
- 各 step が code block / 具体的 command を含む

### 3. Type consistency

- file path (`gui/src/components/StateSwitcher.tsx` / `.test.tsx`) は全 Task で一致
- 関数名 (`StateSwitcher`) / hook (`useAppStateStore`) / env key (`import.meta.env.DEV`) は全 Task で一致
- vitest API (`vi.stubEnv` / `vi.unstubAllEnvs` / `beforeEach` / `afterEach`) は全 Task で一致
- gh CLI 引数 (`--repo Idios/kobutachan-allaganeye` / `--base develop-0.2.0`) は全 step で一致
- commit message format (`<type>: <内容> (Refs #N)`) は全 commit step で一致

### 4. Ambiguity

- vi.stubEnv が DEV に伝搬しない場合の fallback (MODE='production') を Task 1 Step 3 注で明記
- early return を hook より先に置く理由 (rules-of-hooks 整合) を Task 2 Step 2 注で明記
- markdown lint 軽微 fix が 0 件なら commit skip (Task 3 Step 5)

ambiguity ゼロ。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-03-l2-tier1-stateswitcher-dev-only-implementation.md`. Two execution options:**

1. **Subagent-Driven (recommended)**: 各 Task を fresh subagent に dispatch、Task 間で 2-stage review (spec compliance + code quality)、高い並行性
2. **Inline Execution**: 本セッション内で `superpowers:executing-plans` を使い batch 実行 + checkpoint

**Which approach?**
