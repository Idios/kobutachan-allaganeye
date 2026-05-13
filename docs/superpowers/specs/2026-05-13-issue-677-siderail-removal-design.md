# Issue #677 SideRail 全体削除 — Design Spec

> **Status**: Draft (brainstorming approved 2026-05-13、Idios)
> **Lane**: II-a' (Group C 残、Wave 1 initial parallel batch)
> **Roadmap**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) §Group C
> **Related prior plan**: [docs/superpowers/plans/2026-05-11-group-c-preview-sample-mode.md](../plans/2026-05-11-group-c-preview-sample-mode.md) Chapter 3 (3-chapter 連結 plan の Chapter 1/2 は merge 済、Chapter 3 = 本 spec で更新の上 standalone 実行)
> **Session-id**: `eloquent-joliot-835af8`

## 1. Goal

GUI 左の SideRail (装飾アイコン 4 個 `◈ ◇ ◆ ⎊` + 縦書き `ALLAGAN` ロゴ) を実装から完全に削除し、ユーザーが先頭の `iconActive` ハイライトを「クリック可能な選択 UI」と誤認する問題 ([#677](https://github.com/Idios/kobutachan-allaganeye/issues/677)) を根絶する。

## 2. Background

- `gui/src/components/SideRail.tsx` は 48px 幅の縦 rail。回転した `ALLAGAN` ラベル + spacer + 4 装飾アイコンで構成。先頭アイコンのみ `iconActive` 系の枠線で強調表示される
- アイコンは `aria-hidden="true"` の純装飾で、`onClick` も `<button>` 化もされていない
- 元 design (`docs/design/bundle/project/variants/aether.jsx` lines 438-453) の inline rail を TS + CSS Modules に写経したもの。当初は「機能アイコンを後付けする前提の chrome」だった
- 2026-05-07 ユーザー報告: 「左下のUIが何かを選択しているように見えるがここには現状機能が無いのでボタンを一旦削除してほしい」 → Issue #677 起票

## 3. Decisions (brainstorming で確定)

| 決定 | 選択肢 | 採用 |
| --- | --- | --- |
| Q1: 修正方針 | (a) アイコン 4 個のみ削除 / (b) SideRail 全体削除 / (c) iconActive 強調 flatten | **(b)** |
| Q2: 関連 design doc 整合性 | (α) handoff bundle 不変 + 他 doc で乖離明記 / (β) aether.jsx 自体に comment 追記 / (γ) 何もしない | **(α)** |
| 実装戦略 | A. 単 PR 一括 / B. deprecate → delete 段階 / C. code と doc を PR 分割 | **A** |

(α) の根拠: `docs/design/README.md` で `bundle/` は「handoff bundle 原本 (変更不可、参照のみ)」と明記されており、aether.jsx 改変は不可侵原則に反する。divergence は `docs/design/README.md` 側で明記する。

## 4. Scope

### In scope

- SideRail コンポーネントの物理削除 (`.tsx` / `.module.css` / `.test.tsx`)
- `App.tsx` 参照削除 (import / JSX / JSDoc)
- `App.test.tsx` の SideRail 専用 assertion 削除
- 現在の状態を記述する doc の更新 (`docs/ui-architecture.md` / `docs/design/README.md`)

### Out of scope

- `docs/design/bundle/project/variants/aether.jsx` の改変 (Q2-α: 不変ポリシー保持)
- `gui/src/styles/tokens.css` の CSS 変数削除 (`--ae-bg-deep` / `--ae-gold-rgb` / `--ae-font-ui` 等は 17+ file が共有)
- `gui/src/App.module.css` の `.body` / `.main` 改修 (SideRail 非依存の flex layout、SideRail 除去後も意味を持つ)
- `StateSwitcher` / `Conflict|DraftRestore|ConfirmExit Modal` 等の他 shell 要素

## 5. File changes

### 5.1 削除 (3 file)

| ファイル | 行数 (現在) | 理由 |
| --- | --- | --- |
| `gui/src/components/SideRail.tsx` | 25 | コンポーネント本体、不要 |
| `gui/src/components/SideRail.module.css` | 46 | スタイル、不要 |
| `gui/src/components/SideRail.test.tsx` | 14 | 削除コンポーネントのテスト、不要 |

### 5.2 改修 (4 file)

#### `gui/src/App.tsx`

- L4 `import { SideRail } from './components/SideRail';` を削除
- L15 JSDoc `"Wires the fixed shell (SideRail + StateSwitcher)"` → `"Wires the fixed shell (StateSwitcher)"` に修正
- L35 `<SideRail />` を削除 (`.body` flex 内の唯一の sibling が `.main` だけになる)

期待される net diff: -3 行 (line 1 つは削除、line 2 つは編集による diff hunk)

#### `gui/src/App.test.tsx`

- L79-84 `it('renders the side rail on every screen', ...)` test 1 件を削除 (`<nav role="navigation" aria-label="Allagan Eye navigation">` 不在を前提とする)
- 残 6 test (drop / detecting / complete / preview / export / no-title-bar) は不変

#### `docs/ui-architecture.md`

- §8 (window resize 方針) の L344 行 (`SideRail 48px 固定、メイン領域 flex: 1`) を削除
- §9 (コンポーネント階層) の L354 行 (`├── SideRail            (ALLAGAN + 4 アイコン)`) を削除し、`body` の子が `main` 単独であることを反映
- §9 (`components/` listing) の L364 行 (`├── SideRail / StateSwitcher                      (shell)`) を `├── StateSwitcher                              (shell)` に修正
- §9 末尾もしくは body 構成説明部に「(注: 旧 SideRail は #677 で削除済、main が body の全幅)」の 1 行注記を追加

#### `docs/design/README.md`

- L203 付近の `bundle/` 説明 (handoff bundle 原本) の末尾に以下 1 行を追加:

  > 注: 実装側では #677 で SideRail コンポーネントを mock から削除済 (handoff snapshot としての aether.jsx は変更不可ポリシーにより保持、乖離あり)。

  位置: `bundle/` ファイル構成 tree の直後、L218 の `##` 見出し前

### 5.3 不変 (明示)

| ファイル | 理由 |
| --- | --- |
| `gui/src/styles/tokens.css` | `--ae-bg-deep` / `--ae-gold-rgb` / `--ae-font-ui` 等は他 17 file が共有 |
| `gui/src/App.module.css` | `.body` flex / `.main` は SideRail 除去後も layout 構造を担う |
| `docs/design/bundle/project/variants/aether.jsx` | handoff snapshot として不変ポリシー (Q2-α) |
| `docs/superpowers/plans/2026-05-11-group-c-preview-sample-mode.md` | 過去 plan の歴史記録として保持 (Chapter 3 は本 spec が supersede するが plan 自体は historical) |

## 6. Data flow / 状態遷移 / Error handling

影響なし。

- Zustand store (`appStateStore` / `metadataStore` / `recentStore`) はすべて SideRail 非依存
- Tauri command (`load_metadata` / `apply_changes` / `restore_from_original` / `export_match` 他) は SideRail 非依存
- screen / phase state machine (`drop` / `detecting` / `complete` / `preview` / `export`) は SideRail 非依存
- ErrorModal / ConflictModal / DraftRestoreModal / ConfirmExitModal も SideRail 非依存

## 7. Testing strategy

### 7.1 Unit / integration test

- `SideRail.test.tsx` (1 it block) → file ごと削除
- `App.test.tsx` の `renders the side rail on every screen` test → 1 it block 削除
- 残 App.test.tsx (6 test) と 5 screen test / 3 modal test は全て不変
- `gui/src/__tests__/flow.integration.test.tsx` は SideRail 非言及 (Grep 確認済) → 不変

### 7.2 a11y test (jest-axe)

`gui/src/test-setup.ts` で global に `toHaveNoViolations` を拡張済。既存の axe 検証カバレッジ:

| ファイル | 範囲 |
| --- | --- |
| `screens/DropScreen.test.tsx` | drop 画面 4 状態 |
| `screens/DetectingScreen.test.tsx` | detecting 画面 |
| `screens/CompleteScreen.test.tsx` | complete 画面 |
| `screens/PreviewScreen.test.tsx` | preview 画面 |
| `screens/ExportScreen.test.tsx` | export 画面 |
| `components/ConfirmExitModal.test.tsx` | confirm exit modal |
| `components/ConflictModal.test.tsx` | conflict modal |
| `components/DraftRestoreModal.test.tsx` | draft restore modal |

SideRail 削除によって追加される a11y 違反はない。むしろ「内部要素がすべて `aria-hidden="true"` の `<nav>`」が消えるため、表面的には改善方向のみ。

### 7.3 受入条件 mapping (#677 逐条 / Iron Law 1)

| 受入条件 | 達成方法 |
| --- | --- |
| (1) 4 つのアイコン (`◈ ◇ ◆ ⎊`) を画面から除去 ((a) or (b) のいずれか採用) | (b) `<SideRail />` 削除で 4 アイコン消滅 |
| (2) `SideRail.test.tsx` の関連 assertion 更新 | file ごと削除 + `App.test.tsx` の 1 件削除 |
| (3) 関連 design doc (`aether.jsx` 等) の整合性確認 (削除と乖離する場合はコメントで明示) | (α) `docs/design/README.md` に divergence note 追記、`docs/ui-architecture.md` から SideRail 記述削除 |
| (4) `jest-axe` で a11y violation が発生しないこと | 既存 8 箇所の axe テストで違反 0 を確認 (`npm test` で全 pass) |

### 7.4 実機検証 (Iron Law 6 trigger: GUI 変更)

mock テスト pass = 実機検証不要は Red Flag。Idios に以下を依頼:

- `cd gui && npm run tauri dev` で 5 screen (`drop` / `detecting` / `complete` / `preview` / `export`) を順に表示
- 左端 48px 帯 (旧 SideRail) が消えていることを目視確認
- 5 screen の main コンテンツが想定どおり左寄せまで広がっていることを確認 (`.main { flex: 1 }` は不変なので自動的に拡張される想定)

## 8. PR / Iron Law 整合

| 項目 | 内容 |
| --- | --- |
| base | `develop-0.2.0` |
| 本文 keyword | `Refs #677` のみ (Iron Law 4: `Closes` / `Fixes` / `Resolves` 禁止) |
| 1 PR = 1 scope | ✓ (SideRail 削除単一 scope) |
| session-id | `eloquent-joliot-835af8` |
| machine-verified (`[x]` で記載) | `npm run lint` / `npm run typecheck` / `npm test` / `npm run build` / `cd src-tauri && cargo check` |
| machine-unverifiable (plain `-` で記載) | Idios 実機検証 (§7.4) |
| Pre-flight | `git fetch origin develop-0.2.0` + `git log HEAD..origin/develop-0.2.0` で touched files 交差確認 / `gh pr list --search "677"` で並行 PR 重複確認 |
| close handoff | マージ後 `/close-issue #677` で実測再検証 (Wave 2 or 即時) |

## 9. Risk / Open questions

- **Risk** (低): `gui/src/styles/tokens.css` の特定変数が SideRail でしか使われていなかった場合に不要 token が残る可能性 → grep 確認済、`--ae-bg-deep` / `--ae-gold-rgb` / `--ae-font-ui` はすべて他 file 共有なので影響なし
- **Risk** (低): `App.module.css` の `.body` が SideRail 除去後に冗長になる可能性 → flex container として `.main` 配置を担い続けるため意味あり、削除しない
- **Open** (なし): brainstorming 段階で曖昧点はすべて Q1/Q2 で解消済

## 10. References

- Issue: [#677 SideRail のアイコンが選択 UI に見えるが機能なし](https://github.com/Idios/kobutachan-allaganeye/issues/677)
- 関連 PR (Group C 既消化分):
  - [PR #719 (Refs #633)](https://github.com/Idios/kobutachan-allaganeye/pull/719) sample mode 全画面 read-only
  - [PR #735 (Refs #645)](https://github.com/Idios/kobutachan-allaganeye/pull/735) FrameStrip brightness overlay
- 旧 plan (3-chapter joint): [docs/superpowers/plans/2026-05-11-group-c-preview-sample-mode.md](../plans/2026-05-11-group-c-preview-sample-mode.md)
- Roadmap: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) §Group C / Lane II-a'
- Iron Law: `.claude/hooks/session-start.sh`
- 関連 doc: [docs/ui-architecture.md](../../ui-architecture.md) / [docs/design/README.md](../../design/README.md) / [docs/l2-workflow.md](../../l2-workflow.md)
