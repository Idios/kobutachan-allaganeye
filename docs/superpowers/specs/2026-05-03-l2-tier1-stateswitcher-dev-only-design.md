# L2 Tier 1: StateSwitcher を dev only に絞り込む設計

> **Status**: v0.2.0 リリースゲート Tier 1 (コア UX) スコープ
> **Scope**: [#653](https://github.com/Idios/kobutachan-allaganeye/issues/653) 単独 (1 spec / 1 章)
> **session**: `dazzling-mestorf-10914f` (2026-05-03 brainstorming)

## 関連 issue 整理 (本 spec 着手時の Tier 1 確定)

| issue | 状態 | 処置 |
| --- | --- | --- |
| [#653](https://github.com/Idios/kobutachan-allaganeye/issues/653) | OPEN | **本 spec で対応** |
| [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (graceful kill) | OPEN | `on_window_event` + `ConfirmExitModal` + `kill_tracked_processes` + `force_exit_app` + WebView2 race 対策 + a11y 完了済 → 別途 `/close-issue 523` (中間ファイル cleanup verify のみ) |
| [#574](https://github.com/Idios/kobutachan-allaganeye/issues/574) (metadata 自動再現) | CLOSED (not planned, 2026-05-02) | recentStore で十分カバー、Portable ZIP 哲学整合度低、機能不要判断 |
| [#573](https://github.com/Idios/kobutachan-allaganeye/issues/573) (argv 動画 path 起動) | CLOSED (not planned, 2026-05-03) | CLI で argv サポート済、GUI 重複不要判断 |

## §1 Background

PR #641 実機検証で発覚:

- `CompleteScreen` の上部アクションバー (`[元に戻す]` / `[境界を調整]` / `[全試合書き出し]` / `[× 閉じる]`) が、右上の dev 用 `StateSwitcher` と**物理的に重なる**
- `StateSwitcher.module.css` line 1-14 で `.switcher` が `position: absolute; top: 8px; right: 8px; z-index: 50` で float、topBar.actions より前面に出てボタンクリック不可
- `StateSwitcher.tsx` line 15-19 元設計コメント `Dev-only screen switcher` と、`App.tsx` line 33 で常時 render している現状の乖離

修正方針は issue body 候補 (1)-(4) のうち **(1) `import.meta.env.DEV` で dev only** に確定 (2026-05-03 brainstorming で Idios 判断)。元設計意図に最も忠実 + production 副作用なし。

## §2 Goals

- production 配布版 (Tauri bundle / Portable ZIP) で `StateSwitcher` を render しない → topBar との重複を原理的に解消
- dev session では従来通り表示 → screen 強制遷移用 dev 機能を維持
- 全画面 (drop / detecting / complete / preview / export) で横展開確認 → 他画面でも同様の重複が起こりうるため

## §3 Architecture

### Gating 位置

- **`gui/src/components/StateSwitcher.tsx` 関数本体先頭** に early return を追加:

  ```tsx
  export function StateSwitcher() {
    if (!import.meta.env.DEV) return null;
    // ... 既存の dev 用 5 タブ render
  }
  ```

- 採用理由 (component-local 責務):
  - component 自身が production で no-op となり、callsite (`App.tsx`) は不変
  - 他画面で `StateSwitcher` を import した場合も自動的に production 安全
  - PR #587 の a11y guard pattern (component 内で `useFocusTrap` / `useEscapeKey` 完結) と整合

### `App.tsx` callsite

- 不変 (`<StateSwitcher />` を `{cond && ...}` で囲まない)
- gating は component 内部に閉じる

### CSS 変更なし

- `StateSwitcher.module.css` の z-index / position は dev で従来通り維持
- production では render されないので CSS の影響はない

### `import.meta.env.DEV` の挙動

- Vite が build mode で `true` (dev) / `false` (prod) を inline 展開 (`gui/src/main.tsx` line 11 / line 22 で既に同パターン使用)
- production build (`vite build` / `npm run tauri build`) で dead code elimination が effective

### 他画面の波及確認

- `Grep "StateSwitcher" gui/src/` で `App.tsx` のみが import (確認済)
- 他画面 (drop / detecting / complete / preview / export) は `<StateSwitcher />` を直接 render していないため、`App.tsx` の callsite 1 箇所だけが production 表示判定の入口

## §4 Test

### 既存 test (regression guard)

- `gui/src/components/StateSwitcher.test.tsx` の DEV 時 render assertion (5 タブが描画される) は維持

### 新規 test (PROD gate)

- vitest で `import.meta.env.DEV = false` を `vi.stubEnv` でスタブ → render 結果が `null` (DOM 不在) になることを assert
- vitest config 既存の `defineConfig({ test: { environment: 'jsdom', ... } })` の枠内で完結、追加 dependency 不要

### E2E 観点 (machine-unverifiable, Idios 実機検証)

- production build で StateSwitcher 非表示 + CompleteScreen topBar 全ボタンクリック可能の目視確認
- 他画面 (drop / detecting / preview / export) でも StateSwitcher 非表示確認 (横展開)

## §5 Verification

### machine-verifiable (CI / 自動チェック)

- `cd gui && npm run lint` (eslint 全 pass)
- `cd gui && npm run typecheck` (`tsc --noEmit` 全 pass)
- `cd gui && npm test` (vitest 既存 + 新規 PROD gate test 全 pass)
- `cd gui && npm run build` (vite production build pass)
- `cd gui/src-tauri && cargo check` (Rust 側変更なしの regression 担保)
- `bash scripts/check-markdownlint.sh` (本 spec doc / plan doc 含む全 markdown pass)

### machine-unverifiable (Idios 実機検証)

- `cd gui && npm run tauri dev` で StateSwitcher が従来通り表示
- `cd gui && npm run tauri build` 後の production exe で StateSwitcher 非表示
- CompleteScreen topBar 4 ボタン全クリック可能 (production)
- 他画面 (drop / detecting / preview / export) でも StateSwitcher 非表示確認

## §6 Cross-cutting / PR 構成

### Iron Law 整合

- **Iron Law 1**: 受け入れ条件全項目 (issue #653 の 5 項目) を逐条検証して LGTM
- **Iron Law 3**: scope creep 禁止、本 PR では `StateSwitcher.tsx` + `StateSwitcher.test.tsx` のみ touch (App.tsx / module.css は変更なし)
- **Iron Law 4**: PR / commit に `Closes` / `Fixes` / `Resolves` 禁止、`Refs #653` のみ
- **Iron Law 6**: PR 作成 Pre-flight (`git fetch origin develop-0.2.0` + 取り込み未済 commit 確認 + 並行 worktree PR 重複確認) 必須

### PR 構成

- 1 PR (1 issue scope = 1 PR、L2 workflow §1 PR = 1 scope 整合)
- base: `develop-0.2.0`
- title (案): `fix: StateSwitcher を dev only に絞り込み topBar との重複を解消 (Refs #653)`
- session-id: `dazzling-mestorf-10914f` を PR 本文末尾に記載
- Self-Test Report: `docs/l2-workflow.md §Self-Test Report 規約` に準拠 (machine-verifiable は `[x]`、machine-unverifiable は plain `-`)

### 受け入れ条件 mapping (issue #653)

| # | 受け入れ条件 | 本 spec での担保 |
| --- | --- | --- |
| 1 | CompleteScreen の topBar.actions が StateSwitcher と物理的に重ならず操作可能 | §3 production gating で原理的解消、§5 Idios 実機目視 |
| 2 | 他画面 (drop / detecting / preview / export) でも StateSwitcher との重複なし | §3 全画面で StateSwitcher が render されない、§5 Idios 横展開確認 |
| 3 | 修正方針 (1)-(4) の中から Idios 選択した案で実装 | (1) DEV only 確定、§3 component-local gating で実装 |
| 4 | vitest で StateSwitcher の表示条件 (dev only か常時か) を pin | §4 PROD gate test 新規 + DEV render test 維持 |
| 5 | eslint / typecheck / vitest 全通過 | §5 machine-verifiable で全 path 走査 |

## §7 References

- 本 spec: 2026-05-03 brainstorming session `dazzling-mestorf-10914f`
- 元 issue: [#653](https://github.com/Idios/kobutachan-allaganeye/issues/653) bug / l2a-gui / P2-medium
- 元設計コメント: `gui/src/components/StateSwitcher.tsx:15-19` "Dev-only screen switcher"
- 関連 file:
  - `gui/src/components/StateSwitcher.tsx` (本 spec の主たる修正先)
  - `gui/src/components/StateSwitcher.test.tsx` (PROD gate test 追加先)
  - `gui/src/components/StateSwitcher.module.css` (変更なし、参照のみ)
  - `gui/src/App.tsx:33` (callsite、変更なし)
  - `gui/src/main.tsx:11`, `:22` (`import.meta.env` 既存使用パターン)
- 関連 PR:
  - [PR #641](https://github.com/Idios/kobutachan-allaganeye/pull/641) (実機検証で本 bug 発覚)
  - [PR #587](https://github.com/Idios/kobutachan-allaganeye/pull/587) (a11y guard component-local pattern の前例)
- L2 workflow / Iron Law:
  - [`docs/l2-workflow.md`](../../l2-workflow.md) §PR 作成 path 別自動チェック / §Self-Test Report 規約 / §1 PR = 1 scope
  - `.claude/hooks/session-start.sh` Iron Law 1, 3, 4, 6
