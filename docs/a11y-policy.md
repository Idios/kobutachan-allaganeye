# a11y Policy (アクセシビリティ方針)

> **Status**: 確定 (issue #587 で初版)。本 doc は GUI 全体の a11y cross-cutting 方針を定義し、UI 部品レベルの仕様は [ui-interaction-spec.md](ui-interaction-spec.md) を、開発手順は [gui-development.md](gui-development.md) を参照する。

このドキュメントは Allagan Eye GUI (gui/) のアクセシビリティ方針を集約する。各 PR で個別に実装方針を再導出しないよう、原則と scope 境界をここで一元化する。詳細仕様は [docs/ui-interaction-spec.md](ui-interaction-spec.md) と [docs/gui-development.md](gui-development.md) を参照。

## scope policy

### 対象 (本ツールが品質保証する観点)

- **キーボードのみで全機能操作可能** (Tab / Escape / Space / Enter / Arrow)
- **focus visible** が全 interactive 要素で表示 (`:focus-visible` outline)
- **マウスホバー時の disabled 理由表示** (詳細は [ui-interaction-spec.md §1.2](ui-interaction-spec.md))
- **`prefers-reduced-motion` 対応** (OS 設定で animation 抑止)
- **CSS variable (aetherTheme) のみ使用** (詳細は [gui-development.md](gui-development.md) `## CSS 慣例`)

### scope 外

- **読み上げソフト (screen reader) 対応**: Allagan Eye の想定ユーザーは FF14 PvP プレイヤーで、screen reader 利用ユースケースが存在しないため、`aria-label` / `aria-live` / `aria-describedby` / `role="status"` / `role="alert"` / `role="img"` / `role="dialog"` 等の screen reader 専用属性は **新規追加しない**
  - **既存実装は維持**: `role="dialog"` (ConflictModal / ConfirmExitModal / ErrorModal) や `role="alert"` (ErrorCard) などの既存属性は削除しない (後方互換 + axe-core 違反回避)
  - **例外: visible text のない icon-only button** (例: `gui/src/components/BrightnessTimeline.tsx` の SVG match block) は `aria-label` を最低限付与。**理由は「screen reader 対応」ではなく「axe-core button name 違反の回避」**
- **サンプル動画モード固有 polish**: `filePath === null` の sample mode 固有の挙動仕様は #569 (Phase 2.5) / #589 (Phase 4) で進行中。本 a11y policy では sample mode 固有 UI の polish (例: [適用] ボタンの sample 理由 tooltip) は scope 外として扱う

## キーボード操作 (画面別)

### 全画面共通

- **Tab**: 全 interactive 要素を順に巡回 (DOM 順 = 視覚順を維持)
- **Escape**: dialog / 確認カード / modal を閉じる (= キャンセル相当)
- **Space / Enter**: button 押下 / list 項目の確定 (active / selected)

### DropScreen

- SelectedCard / ErrorCard 表示中: Tab 内循環 (`useFocusTrap`)、Escape で取消 (`useEscapeKey`)

### DetectingScreen

- 中断ボタンに Tab 到達 + Enter で押下

### CompleteScreen

- 試合一覧: ↑↓ で選択移動 / Home, End で先頭, 末尾 / Enter, Space で詳細プレビュー遷移

### PreviewScreen

- ←→ : ±1 秒シーク
- Shift + ←→ : ±10 秒シーク
- Alt + ←→ : ±1 frame シーク (FPS 対応)
- Space : 再生 / 一時停止
- INPUT / TEXTAREA / SELECT focus 中は keyboard handler を suppress (text 入力を妨げない)

### ExportScreen

- Tab で全 button / input / checkbox に到達

### Modal (ConflictModal / ConfirmExitModal / ErrorModal)

- Tab で modal 内循環、Escape で「キャンセル」相当
- ErrorModal (#614) は `isRecoverable === true` 時のみ Escape で `dismissError()`、`isPanic === true` 時は Escape を無効化 (パニック時は誤操作で閉じないよう、明示的に「アプリを終了」ボタン押下を要求)

## focus 視覚化

`gui/src/styles/a11y.css` の global rule で全 interactive 要素に金色 outline を出す:

```css
:focus-visible {
  outline: 2px solid var(--ae-gold-bright);
  outline-offset: 2px;
  border-radius: 1px;
}
```

`:focus:not(:focus-visible)` (= マウス focus) は outline を抑止する。component 個別の override は SVG / 特殊な outline-offset の場合のみ。

## disabled 理由表示

**正は [docs/ui-interaction-spec.md §1.2](ui-interaction-spec.md)**。

- 副次ボタン: `<DisabledTooltip disabled reason>` で title 属性のみ
- 主要 CTA: `<DisabledTooltip disabled reason inlineHint>` で title + inline hint 両方
- 共通実装: `gui/src/components/DisabledTooltip.tsx`

scope 外で扱う `aria-describedby` は使わず、title 属性 (mouse hover) と visible inline text のみで構成する。

## 動きの抑止 (prefers-reduced-motion)

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}
```

`gui/src/styles/a11y.css` で global rule。AllaganSigil の回転 / LoadingSpinner / phase row の transition すべてが OS の motion 抑止設定に追従する。

## global CSS 責務分離

| ファイル | 責務 |
| --- | --- |
| `gui/src/styles/tokens.css` | aetherTheme の color / font tokens (`:root` カスタムプロパティ) + base reset (`html, body, #root`, box-sizing) |
| `gui/src/styles/a11y.css` | global `:focus-visible` outline, `@keyframes ae-spin`, `prefers-reduced-motion` |

`main.tsx` で tokens.css → a11y.css の順に load (`var(--ae-*)` 解決のため)。

## sample mode scope policy

`filePath === null` の sample mode 固有 UI (sample banner、sample 専用 disabled 理由 tooltip 等) の polish は本 a11y policy の対象外。設計は #569 (Phase 2.5) / #589 (Phase 4) で進行中。

## 実装 (#587)

### Hooks

| パス | 役割 |
| --- | --- |
| [`gui/src/hooks/useFocusTrap.ts`](../gui/src/hooks/useFocusTrap.ts) | dialog / カード表示中に Tab focus を内側で循環、解除時に previouslyFocused へ復元 |
| [`gui/src/hooks/useEscapeKey.ts`](../gui/src/hooks/useEscapeKey.ts) | active=true の間 Escape で handler 発火 |

### Components

| パス | 役割 |
| --- | --- |
| [`gui/src/components/DisabledTooltip.tsx`](../gui/src/components/DisabledTooltip.tsx) | `disabled === true` の時に `title` 属性 + 任意 inline hint で理由を提示 (§1.2 準拠) |
| [`gui/src/components/LoadingSpinner.tsx`](../gui/src/components/LoadingSpinner.tsx) | 回転 sigil + visible label。screen reader 用属性は付けない |

### Global CSS

| パス | 役割 |
| --- | --- |
| [`gui/src/styles/a11y.css`](../gui/src/styles/a11y.css) | global `:focus-visible` outline / `@keyframes ae-spin` / `prefers-reduced-motion` |

### 適用先サマリ

| 画面 / modal | a11y 補強 |
| --- | --- |
| DropScreen.SelectedCard / ErrorCard | useFocusTrap + useEscapeKey + LoadingSpinner |
| DetectingScreen [中断] | DisabledTooltip |
| CompleteScreen 試合一覧 | キーボード ↑↓ / Home / End / Enter / Space |
| CompleteScreen [境界を調整] | DisabledTooltip + inlineHint |
| CompleteScreen.module.css | `.listItem:hover` / `.previewFrame` glow |
| BrightnessTimeline 各 match block | tabIndex + role=button + aria-label (icon-only 例外) + Enter/Space |
| RestoreButton | DisabledTooltip (§2.3.4 + §2.4.13 を 1 箇所で消化) |
| PreviewScreen Pane | data-pane="in"/"out" + active border の cyan/gold 切替 |
| PreviewScreen .stepButton | hover state CSS |
| ExportScreen [◀ プレビュー] / [参照…] / [⬦ 書き出し開始] / [全選択] / [全解除] / 各 checkbox (skip) | DisabledTooltip 6 件 |
| ExportScreen .codecButton | hover state CSS |
| ConflictModal / ConfirmExitModal | useFocusTrap + useEscapeKey |

## 検証 (#587)

### automated (jest-axe + vitest)

`gui/src/test-setup.ts` で `expect.extend(toHaveNoViolations)` を仕込み、各 screen / modal の test で:

```ts
import { axe } from 'jest-axe';

it('has no axe violations', async () => {
  const { container } = render(<TheScreen />);
  expect(await axe(container)).toHaveNoViolations();
});
```

`npm test` (= `vitest run`) で違反検出 → CI 失敗。後戻り防止の自動ゲート。

### rule opt-out

screen reader scope 外のため、以下 rule は明示的に opt out している:

- **PreviewScreen `nested-interactive`**: Pane button が video / timecode input をネストする UX 上必要な構造のため、PreviewScreen の axe テストでのみ無効化 ([gui/src/screens/PreviewScreen.test.tsx](../gui/src/screens/PreviewScreen.test.tsx))。screen reader 利用ユースケースが本ツールに無いため許容

## 検証方法

1. **automated**: `npm test` で全 screen / modal が `expect(container).toHaveNoViolations()` (jest-axe) を通る
2. **manual keyboard**: マウスを触らずに drop → detecting → complete → preview → export を完了できる
3. **focus visible**: DevTools の `:focus-visible` 強制で全 interactive 要素が金色 outline を持つ
4. **prefers-reduced-motion**: OS 設定で「動きを減らす」を ON にして animation が停止する

## 参考

- [docs/ui-interaction-spec.md](ui-interaction-spec.md) — UI 部品レベルの仕様 (§1.2 disabled tooltip 等)
- [docs/ui-architecture.md](ui-architecture.md) — UI アーキテクチャ全体
- [docs/gui-development.md](gui-development.md) — GUI 開発手順 + CSS 慣例
- [docs/design/README.md](design/README.md) — Aether theme 設計
