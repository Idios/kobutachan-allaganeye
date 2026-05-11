# Group C (#633 #645 #677) PreviewScreen / sample mode UX — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lane II-a / Group C の 3 issue (sample mode 全画面 read-only / preview 微細タイムライン / SideRail 削除) を canonical 3 PR で順次消化し、PreviewScreen 周辺の UX 品質を v0.2.0 リリース基準に揃える。

**Architecture:** 3 chapter = 3 PR の直列構成。共通 SampleModeBanner / MicroTimeline 新 component と既存 DisabledTooltip / RestoreButton 改修で構成。Tauri command 1 個 (extract_brightness_window) を新設して PreviewScreen 微細タイムライン用 brightness data を on-demand 取得。SideRail 全体削除で App.tsx 改修。

**Tech Stack:** React 19 + TypeScript + Vitest + zustand (GUI) / Rust + Tauri 2 + serde + ts-rs (backend) / FFmpeg subprocess

**Spec:** [docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md](../specs/2026-05-11-group-c-preview-sample-mode-design.md)

---

## File Structure

### Chapter 1 (PR #633) — sample mode 全画面 read-only

| 操作 | ファイル | 責務 |
| --- | --- | --- |
| 新規 | `gui/src/components/SampleModeBanner.tsx` | sample mode 検知 + 上部 banner 描画 (~30 行) |
| 新規 | `gui/src/components/SampleModeBanner.module.css` | banner styling (~20 行) |
| 新規 | `gui/src/components/SampleModeBanner.test.tsx` | banner 表示条件 + a11y attribute 検証 |
| 改修 | `gui/src/screens/CompleteScreen.tsx` | banner 統合 |
| 改修 | `gui/src/screens/CompleteScreen.test.tsx` | sample mode banner test |
| 改修 | `gui/src/screens/PreviewScreen.tsx` | banner 統合 + 編集系 disabled + 主要 CTA inline hint |
| 改修 | `gui/src/screens/PreviewScreen.test.tsx` | sample mode disabled / inline hint test |
| 改修 | `gui/src/screens/ExportScreen.tsx` | banner 統合 + disabled CTAs |
| 改修 | `gui/src/screens/ExportScreen.test.tsx` | sample mode disabled CTAs test |
| 改修 | `gui/src/components/RestoreButton.tsx` | sample mode reason 切替 + inlineHint=true 化 |
| 改修 | `docs/ui-interaction-spec.md` | §1.2 / §1.4 / §2.3 / §2.4 / §2.5 注記解消 |

### Chapter 2 (PR #645) — preview 微細タイムライン (±5s)

| 操作 | ファイル | 責務 |
| --- | --- | --- |
| 改修 | `gui/src-tauri/src/lib.rs` | `extract_brightness_window` command + `BrightnessWindow` struct |
| 改修 | `gui/src-tauri/src/error.rs` | (必要なら) ffmpeg.* error code の hint 確認 |
| 新規 | `gui/src-tauri/tests/extract_brightness_window.rs` | Rust integration test (実 ffmpeg call) |
| 新規 | `gui/src/components/MicroTimeline.tsx` | ±5s SVG timeline component (~80 行) |
| 新規 | `gui/src/components/MicroTimeline.module.css` | MicroTimeline styling (~30 行) |
| 新規 | `gui/src/components/MicroTimeline.test.tsx` | mount + threshold / blackout / boundary marker test |
| 改修 | `gui/src/screens/PreviewScreen.tsx` | MicroTimeline 統合 (real + sample synthetic + error) |
| 改修 | `gui/src/screens/PreviewScreen.test.tsx` | invoke / loaded / error / sample synthetic test |
| 改修 | `docs/ui-interaction-spec.md` | §2.4 に MicroTimeline 状態機械追加 |
| 改修 | `docs/tauri-commands.md` | extract_brightness_window 追加 |

### Chapter 3 (PR #677) — SideRail 全体削除

| 操作 | ファイル | 責務 |
| --- | --- | --- |
| 削除 | `gui/src/components/SideRail.tsx` | コンポーネント削除 |
| 削除 | `gui/src/components/SideRail.module.css` | スタイル削除 |
| 削除 | `gui/src/components/SideRail.test.tsx` | テスト削除 |
| 改修 | `gui/src/App.tsx` | import + render 削除 |
| 改修 | `gui/src/App.test.tsx` | SideRail 関連 assertion 削除 / 5 画面 jest-axe 確認 |
| 改修 | `gui/src/App.module.css` | (必要なら) `.body` 内の SideRail 関連 selector cleanup |
| 改修 | `docs/design/bundle/project/variants/aether.jsx` | inline rail mock に「production 削除済」comment 追記 |

---

## Inter-chapter sequencing (Iron Law 6 Pre-flight)

**PR 順**: #633 → #645 → #677

各 PR 着手前 Pre-flight (毎 chapter で必須):

1. `git fetch origin develop-0.2.0`
2. `git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認
3. 取り込み未済の commit が触る path と当 chapter の touched files が交差すれば `git merge origin/develop-0.2.0` で取り込み + 自動チェック再実行
4. `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認

**追加 chapter-specific チェック**:

- #633 着手時: Lane V Phase 1 (#691 / #693 / #695 / #697 / #698) の並行 PR を `gh pr list --search "#691 OR #693 OR #695 OR #697 OR #698" --state open` で確認。先着 merge → rebase
- #645 着手時: Lane I-B Group B #644 (lib.rs brightness_samples) の merge 状況を `gh pr list --search "#644"` で確認。**#644 merge 後**を推奨
- #677 着手時: 衝突 risk 最小、PR 順序自由

---

## Chapter 1 (PR #633) — sample mode 全画面 read-only 化

**対象 issue**: [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) (P2)
**派生元**: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589)
**PR 順**: 1 本目

### Task 1.1: Pre-flight checks for PR #633

**Files:** (changes only) `git fetch` / `gh pr list` 結果のみ

- [ ] **Step 1: base 同期**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

Expected: 取り込み未済 commit が一覧表示される (空でも OK)。

- [ ] **Step 2: touched files との交差確認**

取り込み未済 commit が以下のいずれかを触る場合は `git merge origin/develop-0.2.0` を実行:

- `gui/src/components/SampleModeBanner.tsx` (新規なので衝突しない)
- `gui/src/components/RestoreButton.tsx`
- `gui/src/screens/CompleteScreen.tsx` / `PreviewScreen.tsx` / `ExportScreen.tsx`
- `gui/src/components/DisabledTooltip.tsx`
- `docs/ui-interaction-spec.md`

- [ ] **Step 3: 並行 worktree PR 確認**

```bash
gh pr list --search "#633" --state all
gh pr list --search "#691 OR #693 OR #695 OR #697 OR #698" --state open
```

Expected: 既存 PR が #633 に対してなければ進む、Lane V Phase 1 PR 並行中なら衝突可能性を確認 (DropScreen 触る #698 と #633 は file 重複なし、metadataStore 触る #691 は表示挙動に間接影響あり)。

- [ ] **Step 4: 着手 issue の AC を再確認**

```bash
gh issue view 633 --json body | jq -r .body | head -60
```

Expected: 受け入れ条件 10 項目を確認 (spec §2.6 と一致)。

### Task 1.2: SampleModeBanner component (TDD)

**Files:**

- Create: `gui/src/components/SampleModeBanner.tsx`
- Create: `gui/src/components/SampleModeBanner.module.css`
- Create: `gui/src/components/SampleModeBanner.test.tsx`

- [ ] **Step 1: テストを先に書く**

```tsx
// gui/src/components/SampleModeBanner.test.tsx
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { SampleModeBanner } from './SampleModeBanner';
import { useMetadataStore } from '../state/metadataStore';

describe('SampleModeBanner', () => {
  afterEach(() => {
    // store を default state に戻す
    useMetadataStore.setState({ filePath: null, metadata: null });
  });

  it('renders banner in sample mode (filePath=null + metadata=non-null)', () => {
    useMetadataStore.setState({
      filePath: null,
      metadata: { matches: [], duration: 0 } as any,
    });
    render(<SampleModeBanner />);
    const banner = screen.getByRole('status');
    expect(banner).toHaveTextContent('サンプル動画です');
    expect(banner).toHaveAttribute('aria-live', 'polite');
  });

  it('does not render in real-file mode (filePath=non-null)', () => {
    useMetadataStore.setState({
      filePath: '/some/path.mp4',
      metadata: { matches: [], duration: 0 } as any,
    });
    render(<SampleModeBanner />);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('does not render in initial idle (metadata=null)', () => {
    useMetadataStore.setState({ filePath: null, metadata: null });
    render(<SampleModeBanner />);
    expect(screen.queryByRole('status')).toBeNull();
  });
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/components/SampleModeBanner.test.tsx
```

Expected: FAIL — `Cannot find module './SampleModeBanner'`。

- [ ] **Step 3: SampleModeBanner.tsx を実装**

```tsx
// gui/src/components/SampleModeBanner.tsx
import { useMetadataStore } from '../state/metadataStore';
import styles from './SampleModeBanner.module.css';

/**
 * #633 / docs/ui-interaction-spec.md §1.4: sample mode 起動時の上部 inline banner.
 *
 * sample mode = `metadataStore.loadSample()` 経由で in-memory metadata がロード
 * された状態 (`filePath === null && metadata !== null`)。初期 idle (metadata=null)
 * と通常 file (filePath=path) は banner 非表示。
 */
export function SampleModeBanner() {
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );
  if (!isSample) return null;
  return (
    <div className={styles.banner} role="status" aria-live="polite">
      サンプル動画です。実際の動画を選択すると保存できます。
    </div>
  );
}
```

- [ ] **Step 4: SampleModeBanner.module.css を実装**

```css
/* gui/src/components/SampleModeBanner.module.css */
.banner {
  background: var(--ae-gold-dim);
  color: var(--ae-bg);
  padding: 8px 16px;
  font-size: 13px;
  border-bottom: 1px solid var(--ae-gold);
  text-align: center;
  font-family: var(--ae-font-ui);
}
```

- [ ] **Step 5: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/components/SampleModeBanner.test.tsx
```

Expected: PASS (3/3 tests)。

- [ ] **Step 6: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: 両方 0 error。

- [ ] **Step 7: commit**

```bash
git add gui/src/components/SampleModeBanner.tsx gui/src/components/SampleModeBanner.module.css gui/src/components/SampleModeBanner.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): SampleModeBanner 共通 component 新設 (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode 全画面 read-only 化のため' 'の上部 inline banner を共通 component として新設。各画面 (Complete /' 'Preview / Export) が opt-in で配置する。' '' '判定式: filePath === null && metadata !== null' '- sample mode (loadSample 経由) のみ true' '- 初期 idle (metadata=null) / 通常 file は banner 非表示' '' 'aria-live=polite + role=status で screen reader 対応。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.3: RestoreButton sample mode reason 拡張 (TDD)

**Files:**

- Modify: `gui/src/components/RestoreButton.tsx`
- Modify: `gui/src/components/RestoreButton.test.tsx`

- [ ] **Step 1: テストを先に書く (sample mode reason 検証を追加)**

[gui/src/components/RestoreButton.test.tsx](../../gui/src/components/RestoreButton.test.tsx) の `describe('RestoreButton', ...)` ブロック末尾に以下を追加:

```tsx
it('shows sample mode reason when filePath=null && metadata=non-null', async () => {
  useMetadataStore.setState({
    filePath: null,
    metadata: { matches: [], duration: 0 } as any,
    hasBackup: false,
    restoring: false,
  });
  render(<RestoreButton />);
  const btn = screen.getByRole('button', { name: /元に戻す/ });
  expect(btn).toBeDisabled();
  expect(btn).toHaveAttribute('title', 'サンプル動画では保存できません');
  // inline hint も表示される (§1.2 主要 CTA 規約)
  expect(screen.getByText('サンプル動画では保存できません', { selector: 'span' })).toBeInTheDocument();
});

it('prefers restoring reason over sample mode', () => {
  useMetadataStore.setState({
    filePath: null,
    metadata: { matches: [], duration: 0 } as any,
    hasBackup: true,
    restoring: true,
  });
  render(<RestoreButton />);
  const btn = screen.getByRole('button', { name: /元に戻す/ });
  expect(btn).toHaveAttribute('title', '復元中です');
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/components/RestoreButton.test.tsx
```

Expected: FAIL — sample mode reason が表示されず、現在は disabled でない可能性も。

- [ ] **Step 3: RestoreButton.tsx を改修**

[gui/src/components/RestoreButton.tsx:51-69](../../gui/src/components/RestoreButton.tsx#L51) を以下で置き換える:

```tsx
export function RestoreButton({
  onRestored,
  confirmMessage = '編集前の状態に戻しますか？ 適用後の変更は破棄されます。',
  label = '元に戻す',
  confirmFn,
}: RestoreButtonProps) {
  const hasBackup = useMetadataStore((s) => s.hasBackup);
  const restoring = useMetadataStore((s) => s.restoring);
  const restoreError = useMetadataStore((s) => s.restoreError);
  const restoreErrorHint = useMetadataStore((s) => s.restoreErrorHint);
  const restore = useMetadataStore((s) => s.restore);
  // #633 / §1.4: sample mode (filePath=null + metadata=non-null) で disabled
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );

  const disabled = !hasBackup || restoring || isSample;
  // #633 / §1.2 主要 CTA: tooltip + inline hint 必須。reason 優先順:
  //   1. restoring (in-flight)
  //   2. isSample (サンプル動画)
  //   3. !hasBackup (バックアップなし)
  const reason = restoring
    ? '復元中です'
    : isSample
      ? 'サンプル動画では保存できません'
      : !hasBackup
        ? 'バックアップが存在しません'
        : '';
```

そして `<DisabledTooltip>` の prop に `inlineHint={true}` を追加 ([line 83](../../gui/src/components/RestoreButton.tsx#L83) 付近):

```tsx
<DisabledTooltip disabled={disabled} reason={reason} inlineHint={true}>
```

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/components/RestoreButton.test.tsx
```

Expected: PASS (既存 + 新規 2 件)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

Expected: 両方 0 error。

- [ ] **Step 6: commit**

```bash
git add gui/src/components/RestoreButton.tsx gui/src/components/RestoreButton.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): RestoreButton に sample mode reason + inline hint 追加 (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode read-only 化のため' 'RestoreButton に以下を追加:' '- isSample = filePath === null && metadata !== null で sample mode 検知' '- disabled 条件に isSample 追加 (sample mode で常に disabled)' '- reason 優先順: restoring → isSample → !hasBackup' '- §1.2 主要 CTA 規約に従い inlineHint=true (現状 false から変更)' '' 'CompleteScreen / PreviewScreen の両方で使われる component なので' 'ここを変えれば 2 画面で sample mode reason が出る。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.4: CompleteScreen に SampleModeBanner 統合 (TDD)

**Files:**

- Modify: `gui/src/screens/CompleteScreen.tsx`
- Modify: `gui/src/screens/CompleteScreen.test.tsx`

- [ ] **Step 1: テストを先に書く**

[gui/src/screens/CompleteScreen.test.tsx](../../gui/src/screens/CompleteScreen.test.tsx) に以下のテスト追加:

```tsx
it('renders SampleModeBanner in sample mode', () => {
  useMetadataStore.setState({
    filePath: null,
    metadata: { matches: [], duration: 0, /* 必要 fields */ } as any,
  });
  render(<CompleteScreen />);
  expect(screen.getByRole('status')).toHaveTextContent('サンプル動画です');
});

it('does not render SampleModeBanner in real-file mode', () => {
  useMetadataStore.setState({
    filePath: '/some/path.mp4',
    metadata: { matches: [], duration: 0, /* 必要 fields */ } as any,
  });
  render(<CompleteScreen />);
  expect(screen.queryByRole('status')).toBeNull();
});
```

(既存 test の setup 関数 / mock を踏襲。`useMetadataStore.setState` で必要 fields を補完する)

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/screens/CompleteScreen.test.tsx
```

Expected: FAIL — banner が見つからない。

- [ ] **Step 3: CompleteScreen.tsx を改修**

[gui/src/screens/CompleteScreen.tsx](../../gui/src/screens/CompleteScreen.tsx) の import に追加:

```tsx
import { SampleModeBanner } from '../components/SampleModeBanner';
```

そして `<div className={styles.screen}>` 直下、最初の child として `<SampleModeBanner />` を挿入:

```tsx
return (
  <div className={styles.screen} data-testid="complete-screen">
    <SampleModeBanner />
    {/* 既存の header / content */}
  </div>
);
```

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/screens/CompleteScreen.test.tsx
```

Expected: PASS (既存 + 新規 2 件)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: commit**

```bash
git add gui/src/screens/CompleteScreen.tsx gui/src/screens/CompleteScreen.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): CompleteScreen に SampleModeBanner 統合 (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode read-only 化のため' 'CompleteScreen の上部 (screen wrapper 直下) に SampleModeBanner' 'を配置。sample mode 時のみ表示、通常 file / 初期 idle で非表示。' '' 'CompleteScreen 自体には他の編集系部品はなく (list view のみ)、' 'RestoreButton 改修 (Task 1.3) で sample mode 対応済。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.5: PreviewScreen 編集系部品に DisabledTooltip 適用 (TDD)

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx`
- Modify: `gui/src/screens/PreviewScreen.test.tsx`

対象部品 (§2.2.1): matchName input / matchType select / Pane.tcInput ×2 / stepRow buttons ×6 / FrameStrip onSelectFrame

- [ ] **Step 1: テストを先に書く**

[gui/src/screens/PreviewScreen.test.tsx](../../gui/src/screens/PreviewScreen.test.tsx) に以下を追加:

```tsx
describe('PreviewScreen sample mode disabled', () => {
  beforeEach(() => {
    useMetadataStore.setState({
      filePath: null,
      metadata: { matches: [{ index: 1, start_time: 0, end_time: 60, name: 'test', type: 'fl_match' }], duration: 60 } as any,
    });
    useAppStateStore.setState({ selectedMatchIndex: 1 });
  });

  it('disables matchName input with tooltip', () => {
    render(<PreviewScreen />);
    const input = screen.getByLabelText(/match name|試合名/);
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables matchType select with tooltip', () => {
    render(<PreviewScreen />);
    const select = screen.getByLabelText(/種別|type/);
    expect(select).toBeDisabled();
    expect(select).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables stepRow buttons with tooltip (×6)', () => {
    render(<PreviewScreen />);
    const stepButtons = screen.getAllByRole('button', { name: /[+-]\d+(s|f|ms)/ });
    expect(stepButtons.length).toBeGreaterThanOrEqual(6);
    stepButtons.forEach((btn) => {
      expect(btn).toBeDisabled();
      expect(btn).toHaveAttribute('title', 'サンプル動画では保存できません');
    });
  });

  it('disables Pane tcInput (×2 IN/OUT) with tooltip', () => {
    render(<PreviewScreen />);
    const tcInputs = screen.getAllByLabelText(/タイムコード|TC/);
    expect(tcInputs.length).toBe(2);
    tcInputs.forEach((input) => {
      expect(input).toBeDisabled();
      expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
    });
  });

  // FrameStrip onSelectFrame は内部 button の disabled で検証
  it('disables FrameStrip frame click in sample mode', () => {
    render(<PreviewScreen />);
    // FrameStrip の thumb は role="button" で render される
    const frames = screen.queryAllByRole('button', { name: /frame/i });
    frames.forEach((f) => {
      expect(f).toBeDisabled();
    });
  });
});
```

(label / aria-label の正確な文字列は実コードを参照して調整、必要なら data-testid 採用)

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx -t 'sample mode disabled'
```

Expected: FAIL — disabled 属性なし or tooltip なし。

- [ ] **Step 3: PreviewScreen.tsx を改修 (sample mode 検知 + disabled 適用)**

[gui/src/screens/PreviewScreen.tsx](../../gui/src/screens/PreviewScreen.tsx) の関数本体に sample mode 検知を追加 (`useMetadataStore` 既存 import に乗せる):

```tsx
const isSample = useMetadataStore(
  (s) => s.filePath === null && s.metadata !== null,
);
const sampleReason = 'サンプル動画では保存できません';
```

各編集系部品の disabled 条件を拡張:

#### 3a. matchName input

既存 `disabled={!filePath}` を `disabled={!filePath || isSample}` に変更し、`<DisabledTooltip>` で wrap:

```tsx
import { DisabledTooltip } from '../components/DisabledTooltip';

<DisabledTooltip disabled={isSample} reason={sampleReason}>
  {(p) => (
    <input
      type="text"
      value={matchName}
      onChange={(e) => handleNameChange(e.target.value)}
      disabled={isSample || /* 既存 disabled 条件 */}
      aria-label="match name"
      {...p}
    />
  )}
</DisabledTooltip>
```

#### 3b. matchType select

同 pattern で wrap。

#### 3c. Pane.tcInput (×2 IN/OUT)

`Pane` component の tcInput に DisabledTooltip wrap。`Pane` が内部で受け取る場合は `Pane` 側に `disabled` / `disabledReason` prop を追加する。

#### 3d. stepRow buttons ×6

stepRow 全体を DisabledTooltip wrap、または各 button を個別 wrap。各 button に `disabled={isSample}` 追加。

```tsx
<div className={styles.stepRow}>
  {stepButtons.map((step) => (
    <DisabledTooltip key={step.label} disabled={isSample} reason={sampleReason}>
      {(p) => (
        <button
          type="button"
          onClick={() => handleStep(step.amount)}
          disabled={isSample}
          aria-label={step.label}
          {...p}
        >
          {step.label}
        </button>
      )}
    </DisabledTooltip>
  ))}
</div>
```

#### 3e. FrameStrip onSelectFrame

`FrameStrip` component に `disabled?: boolean` / `disabledReason?: string` prop を追加し、内部の各 frame button に渡す。

```tsx
<FrameStrip
  thumbs={thumbs}
  onSelectFrame={handleSelectFrame}
  disabled={isSample}
  disabledReason={sampleReason}
/>
```

`FrameStrip.tsx` 内部:

```tsx
{thumbs.map((t, i) => (
  <DisabledTooltip key={i} disabled={!!disabled} reason={disabledReason ?? ''}>
    {(p) => (
      <button
        type="button"
        onClick={() => onSelectFrame(t)}
        disabled={!!disabled}
        aria-label={`frame ${i}`}
        {...p}
      >
        {/* thumb img */}
      </button>
    )}
  </DisabledTooltip>
))}
```

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx -t 'sample mode disabled'
```

Expected: PASS (5 tests in describe)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.test.tsx gui/src/components/FrameStrip.tsx
git commit -m "$(printf '%s\n' 'feat(gui): PreviewScreen 編集系部品の sample mode disabled (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode read-only 化のため' 'PreviewScreen の編集系部品 (matchName / matchType / Pane.tcInput' '×2 / stepRow buttons ×6 / FrameStrip onSelectFrame) に' 'DisabledTooltip wrap で sample mode disabled + tooltip 適用。' '' 'reason 文字列: サンプル動画では保存できません (canonical 統一)' '' 'FrameStrip に disabled / disabledReason prop を新設し、' '内部の各 frame button を DisabledTooltip 経由で disabled 化。' '' '主要 CTA (適用 / 元に戻す / 書き出し) は Task 1.6 で対応 (inline hint 必須)。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.6: PreviewScreen 主要 CTA + Banner 統合 (TDD)

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx`
- Modify: `gui/src/screens/PreviewScreen.test.tsx`

対象部品 (§2.2.2): [適用] (tooltip + inline) / [書き出し] (tooltip + inline) + SampleModeBanner 配置

[元に戻す] は Task 1.3 の RestoreButton 改修で完了済。

- [ ] **Step 1: テストを先に書く**

[gui/src/screens/PreviewScreen.test.tsx](../../gui/src/screens/PreviewScreen.test.tsx) の `describe('PreviewScreen sample mode disabled', ...)` 内に追加:

```tsx
it('renders SampleModeBanner in sample mode', () => {
  render(<PreviewScreen />);
  expect(screen.getByRole('status')).toHaveTextContent('サンプル動画です');
});

it('disables [適用] CTA with tooltip + inline hint', () => {
  render(<PreviewScreen />);
  const applyBtn = screen.getByRole('button', { name: /適用/ });
  expect(applyBtn).toBeDisabled();
  expect(applyBtn).toHaveAttribute('title', 'サンプル動画では保存できません');
  // inline hint も必要
  const hints = screen.getAllByText('サンプル動画では保存できません');
  expect(hints.length).toBeGreaterThanOrEqual(2); // tooltip 文 + inline hint span
});

it('prefers applying reason over sample mode for [適用]', () => {
  // applying state を立てる (実装によって異なる、PreviewScreen 内 local state)
  // → このテストは applying state setter が露出していない場合は省略可
});

it('disables [書き出し] CTA with tooltip + inline hint', () => {
  render(<PreviewScreen />);
  const exportBtn = screen.getByRole('button', { name: /書き出し|エクスポート/ });
  expect(exportBtn).toBeDisabled();
  expect(exportBtn).toHaveAttribute('title', 'サンプル動画では保存できません');
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx -t 'SampleModeBanner|適用|書き出し'
```

Expected: FAIL。

- [ ] **Step 3: PreviewScreen.tsx を改修 (banner + 主要 CTA)**

PreviewScreen の return JSX で:

```tsx
import { SampleModeBanner } from '../components/SampleModeBanner';

// 既存の return (...)  全体を以下のように変更:
return (
  <div className={styles.screen} data-testid="preview-screen">
    <SampleModeBanner />
    {/* 既存の header / panes / stepRow / strip / actionsRow */}
  </div>
);
```

[適用] button の disabled / reason ロジックを拡張 ([PreviewScreen.tsx:651](../../gui/src/screens/PreviewScreen.tsx#L651) 付近):

```tsx
// 適用 button の disabled / reason 拡張
const applyDisabled = applying || !filePath || isSample;
const applyReason = applying
  ? '適用中…'
  : isSample
    ? sampleReason
    : !filePath
      ? 'ファイルが選択されていません'
      : '';

<DisabledTooltip disabled={applyDisabled} reason={applyReason} inlineHint={true}>
  {(p) => (
    <button
      type="button"
      onClick={handleApply}
      disabled={applyDisabled}
      aria-label="適用"
      {...p}
    >
      適用
    </button>
  )}
</DisabledTooltip>
```

[書き出し] button (PreviewScreen 内の navigate('export') 用 button) も同様に改修:

```tsx
const exportNavReason = isSample ? sampleReason : '';
<DisabledTooltip disabled={isSample} reason={exportNavReason} inlineHint={true}>
  {(p) => (
    <button
      type="button"
      onClick={handleExport}
      disabled={isSample}
      aria-label="書き出し"
      {...p}
    >
      書き出し
    </button>
  )}
</DisabledTooltip>
```

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx
```

Expected: ALL PASS (sample mode 関連 ~8 件 + 既存 全件)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): PreviewScreen に SampleModeBanner + 主要 CTA inline hint (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode read-only 化のため' 'PreviewScreen の上部 banner + 主要 CTA に sample mode 対応:' '- screen wrapper 直下に <SampleModeBanner />' '- [適用] CTA: applying → isSample → !filePath の優先順 + inline hint' '- [書き出し] (navigate) CTA: isSample で disabled + inline hint' '' '[元に戻す] (RestoreButton) は Task 1.3 で対応済。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.7: ExportScreen 主要 controls + Banner 統合 (TDD)

**Files:**

- Modify: `gui/src/screens/ExportScreen.tsx`
- Modify: `gui/src/screens/ExportScreen.test.tsx`

対象部品 (§2.2.3): [⬦ 書き出し開始] / 出力先 input / 命名規則 input / コーデック selector ×2 / per-match exclude checkbox / [全選択] / [全解除]

- [ ] **Step 1: テストを先に書く**

[gui/src/screens/ExportScreen.test.tsx](../../gui/src/screens/ExportScreen.test.tsx) に追加:

```tsx
describe('ExportScreen sample mode', () => {
  beforeEach(() => {
    useMetadataStore.setState({
      filePath: null,
      metadata: { matches: [{ index: 1, start_time: 0, end_time: 60, type: 'fl_match' }], duration: 60 } as any,
    });
  });

  it('renders SampleModeBanner', () => {
    render(<ExportScreen />);
    expect(screen.getByRole('status')).toHaveTextContent('サンプル動画です');
  });

  it('disables [⬦ 書き出し開始] with tooltip + inline hint', () => {
    render(<ExportScreen />);
    const startBtn = screen.getByRole('button', { name: /書き出し開始/ });
    expect(startBtn).toBeDisabled();
    expect(startBtn).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables 出力先 input', () => {
    render(<ExportScreen />);
    const input = screen.getByLabelText(/出力先|output/);
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables 命名規則 input', () => {
    render(<ExportScreen />);
    const input = screen.getByLabelText(/命名規則|naming/);
    expect(input).toBeDisabled();
  });

  it('disables コーデック selector', () => {
    render(<ExportScreen />);
    const selectors = screen.getAllByLabelText(/コーデック|codec/);
    selectors.forEach((s) => expect(s).toBeDisabled());
  });

  it('disables per-match exclude checkbox', () => {
    render(<ExportScreen />);
    const checkboxes = screen.getAllByRole('checkbox');
    checkboxes.forEach((cb) => expect(cb).toBeDisabled());
  });

  it('disables [全選択] / [全解除] buttons', () => {
    render(<ExportScreen />);
    const allBtn = screen.getByRole('button', { name: /全選択/ });
    const noneBtn = screen.getByRole('button', { name: /全解除/ });
    expect(allBtn).toBeDisabled();
    expect(noneBtn).toBeDisabled();
  });
});
```

(label の正確な文字列は実コード参照、necessary なら data-testid 採用)

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/screens/ExportScreen.test.tsx -t 'sample mode'
```

Expected: FAIL。

- [ ] **Step 3: ExportScreen.tsx を改修**

ExportScreen の return JSX:

```tsx
import { SampleModeBanner } from '../components/SampleModeBanner';
import { DisabledTooltip } from '../components/DisabledTooltip';

const isSample = useMetadataStore(
  (s) => s.filePath === null && s.metadata !== null,
);
const sampleReason = 'サンプル動画では保存できません';

return (
  <div className={styles.screen} data-testid="export-screen">
    <SampleModeBanner />
    {/* 既存の header / form / list / progressBox */}
  </div>
);
```

各 disabled control を DisabledTooltip wrap で改修。各 control の disabled 条件に `|| isSample` 追加、reason は `sampleReason`、主要 CTA / 主要 input は `inlineHint={true}` (issue body 通り)。

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/screens/ExportScreen.test.tsx
```

Expected: ALL PASS (新規 7 件 + 既存)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: commit**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): ExportScreen に SampleModeBanner + 全 disabled CTA tooltip (Refs #633)' '' 'docs/ui-interaction-spec.md §1.4 sample mode read-only 化のため' 'ExportScreen に以下を追加:' '- screen wrapper 直下に <SampleModeBanner />' '- 8 部品の sample mode disabled + tooltip + (主要 CTA は inline hint)' '  - [⬦ 書き出し開始]' '  - 出力先 input' '  - 命名規則 input' '  - コーデック selector ×2' '  - per-match exclude checkbox' '  - [全選択] / [全解除]' '' 'reason 文字列: サンプル動画では保存できません (canonical 統一)' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.8: ui-interaction-spec.md doc 整合

**Files:**

- Modify: `docs/ui-interaction-spec.md`

- [ ] **Step 1: §1.2 アンチパターン例の「派生 issue で対応予定」削除**

[docs/ui-interaction-spec.md](../../ui-interaction-spec.md) §1.2 アンチパターン文 (line 42 付近) を grep で確認:

```bash
grep -n "派生 issue で対応予定\|現状未実装\|§1.4 違反\|§1.2 違反" docs/ui-interaction-spec.md
```

各 hit を context 確認の上、本 PR で解消した旨に書き換える。例 (§1.2 line 42 付近):

> [PreviewScreen.tsx:651-657](../gui/src/screens/PreviewScreen.tsx#L651) の `applying || !filePath` による sample mode 永続 disabled が #589 該当ケース、tooltip / inline hint / 上部 banner は #589 派生 issue で対応予定)。

→ 解消後:

> [PreviewScreen.tsx:651-657](../gui/src/screens/PreviewScreen.tsx#L651) の `applying || !filePath` による sample mode 永続 disabled が #589 該当ケース、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で tooltip / inline hint / 上部 banner を実装し解消済。

- [ ] **Step 2: §1.4 表 (sample mode 部品種別) の「現状未実装」/「派生 issue」記述削除**

§1.4 の表 (line 70 付近) と本文の「派生 issue で対応予定」を本 PR で解消した旨に書き換える。

- [ ] **Step 3: §2.3 (complete) の RestoreButton 注記更新**

§2.3 RestoreButton 部品節に sample mode reason canonical を追記:

```text
| 例外 / edge case | sample mode (filePath=null + metadata=non-null) で disabled
+ tooltip + inline hint「サンプル動画では保存できません」(#633、§1.2 §1.4)
```

- [ ] **Step 4: §2.4 (preview) の各部品節更新**

[適用] / [書き出し] / 編集系部品 (matchName / matchType / Pane.tcInput / stepRow / FrameStrip) 各節に sample mode reason 追記。

- [ ] **Step 5: §2.5 (export) の各部品節更新**

8 部品それぞれの「例外 / edge case」に sample mode reason 追記。

- [ ] **Step 6: markdownlint で 0 error 確認**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 7: commit**

```bash
git add docs/ui-interaction-spec.md
git commit -m "$(printf '%s\n' 'docs: ui-interaction-spec §1.2 / §1.4 / §2.3-2.5 注記解消 (Refs #633)' '' 'PR #633 で sample mode 全画面 read-only 化を実装したことに伴い' '以下の注記を解消:' '- §1.2 アンチパターン例「派生 issue で対応予定」' '- §1.4 表「現状未実装」/「派生 issue で対応予定」' '- §2.3 RestoreButton: sample mode reason canonical 追記' '- §2.4 preview 各部品節: sample mode reason 追記' '- §2.5 export 各部品節: sample mode reason 追記' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 1.9: PR #633 全自動チェック実行

**Files:** changes only

- [ ] **Step 1: GUI 全テスト実行**

```bash
cd gui && npm test
```

Expected: ALL PASS。失敗があれば調査して修正。

- [ ] **Step 2: GUI lint / typecheck / build**

```bash
cd gui && npm run lint && npm run typecheck && npm run build
```

Expected: 各 0 error / 0 warning。

- [ ] **Step 3: cargo check**

```bash
cd gui/src-tauri && cargo check
```

Expected: 0 error / 0 warning。Chapter 1 では Rust 変更なし、影響ないこと確認。

- [ ] **Step 4: markdownlint**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 5: Iron Law 6 Pre-flight 再実行**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

新たに取り込み未済 commit があり当 PR の touched files と交差すれば `git merge origin/develop-0.2.0` + 再 lint。

- [ ] **Step 6: 並行 worktree PR 重複再確認**

```bash
gh pr list --search "#633" --state all
gh pr list --search "#691 OR #693 OR #695 OR #697 OR #698" --state open
```

Lane V Phase 1 PR が先着 merge されていれば rebase 検討。

### Task 1.10: PR #633 Idios 実機検証依頼 + PR submission

**Files:** PR creation only

- [ ] **Step 1: 実機検証依頼 (Iron Law 6)**

`AskUserQuestion` で Idios に依頼:

```text
PR #633 (sample mode 全画面 read-only 化) の実機検証依頼:

1. cd gui && npm run tauri dev で起動
2. StateSwitcher (右上) で sample mode に切替
3. 以下を visual 確認:
   - Complete / Preview / Export 各画面の上部に
     「サンプル動画です。実際の動画を選択すると保存できます。」banner
   - 各 disabled control の hover で tooltip
   - 主要 CTA (適用 / 元に戻す / 書き出し / 書き出し開始) の inline hint
4. StateSwitcher で real file 経路に戻し、banner 非表示確認
5. DropScreen / DetectingScreen で banner 非表示確認

Q: 実機検証 result は？
- (a) ALL PASS
- (b) 一部 NG (詳細指摘)
- (c) 実機検証 skip して PR 作成 (Iron Law 6 Red Flag、推奨しない)
```

- [ ] **Step 2: PR 作成 (実機検証 PASS 後)**

PR 本文を `printf | --body-file -` または HEREDOC で作成 (`feedback_gh_command_ja_heredoc.md` 参照):

```bash
gh pr create --base develop-0.2.0 --title "feat(gui): sample mode 全画面 read-only 化 (Refs #633)" --body-file - <<'EOF'
## 概要

docs/ui-interaction-spec.md §1.4 sample mode 全画面 read-only 化を実装。
Complete / Preview / Export 3 画面に共通 SampleModeBanner + 編集系部品 disabled
+ 主要 CTA inline hint を追加し、§1.2 disabled 理由表示も整備。

## Refs

- #633 (P2、本 PR で対応)
- 派生元: #589 (silent edit loss bug、partial close 後継)

## 設計

[docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md](docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md) §2 Chapter 1 参照。

## Self-Test Report

### Machine-verified

- [x] cd gui && npm test (ALL PASS)
- [x] cd gui && npm run lint (0 error)
- [x] cd gui && npm run typecheck (0 error)
- [x] cd gui && npm run build (0 error)
- [x] cd gui/src-tauri && cargo check (0 error、Rust 変更なし確認)
- [x] bash scripts/check-markdownlint.sh (0 error)

### Machine-unverifiable (Idios 実機検証済)

- Tauri 起動で sample mode 切替時に Complete / Preview / Export 上部 banner 表示
- 各 disabled control の tooltip / 主要 CTA の inline hint visual 確認
- real file 経路で banner 非表示確認
- DropScreen / DetectingScreen で banner 非表示確認

## Pre-flight (Iron Law 6)

- git fetch origin develop-0.2.0 + 取り込み未済 commit 確認 → merge 取り込み済
- gh pr list --search "#633" → 並行 PR なし
- gh pr list --search "#691 OR #693 OR #695 OR #697 OR #698" → Lane V Phase 1 PR と file 衝突なし

## 受け入れ条件 (#633、10 項目逐条)

| # | 項目 | 充足 |
| --- | --- | --- |
| 1 | 3 画面の上部 inline banner | Task 1.2 SampleModeBanner + Task 1.4/1.6/1.7 統合 |
| 2 | preview 編集系部品 disabled | Task 1.5 |
| 3 | export 主要 controls disabled | Task 1.7 |
| 4 | complete RestoreButton tooltip | Task 1.3 |
| 5 | 各 disabled に inline hint | §1.2 strict 解釈で主要 CTA inline + banner で代替 (spec §2.6 注記参照) |
| 6 | RestoreButton tooltip (hasBackup / restoring) | Task 1.3 (sample 追加) |
| 7 | preview [適用] tooltip (applying / sample) | Task 1.6 |
| 8 | export 各 disabled CTA tooltip | Task 1.7 |
| 9 | vitest (3 画面) | Task 1.4 / 1.5 / 1.6 / 1.7 |
| 10 | doc 注記解消 | Task 1.8 |

## session-id

cranky-sanderson-2872af

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 3: CI 結果確認**

PR 作成後、`gh pr checks <PR#>` で CI status 確認。fail があれば修正 + push。

---

## Chapter 2 (PR #645) — preview 微細タイムライン (±5s)

**対象 issue**: [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) (P3)
**派生元**: [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465)
**PR 順**: 2 本目 (#633 + #644 merge 後を推奨)

### Task 2.1: Pre-flight checks for PR #645

**Files:** changes only

- [ ] **Step 1: base 同期 + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

PR #633 が merge されていれば取り込み。

- [ ] **Step 2: lib.rs 共有 issue (#644) の merge 確認**

```bash
gh pr list --search "#644" --state all
```

`#644 merge 済`を推奨。未 merge なら待機 or rebase 計画立て。

- [ ] **Step 3: 並行 worktree PR 確認**

```bash
gh pr list --search "#645" --state all
```

Expected: 既存 PR なし。

- [ ] **Step 4: 着手 issue の AC を再確認**

```bash
gh issue view 645 --json body | jq -r .body | head -50
```

### Task 2.2: extract_brightness_window Tauri command (TDD)

**Files:**

- Modify: `gui/src-tauri/src/lib.rs`
- Modify: `gui/src-tauri/src/error.rs` (必要なら)
- Create: `gui/src-tauri/tests/extract_brightness_window.rs`

- [ ] **Step 1: 統合テストを先に書く**

```rust
// gui/src-tauri/tests/extract_brightness_window.rs
use std::env;
use std::path::PathBuf;

// Helper to skip if sample video not configured.
fn sample_video() -> Option<PathBuf> {
    env::var("ALLAGANEYE_AUDIO_TEST_VIDEO").ok().map(PathBuf::from)
}

#[tokio::test]
#[ignore] // requires real video file (set ALLAGANEYE_AUDIO_TEST_VIDEO)
async fn extract_brightness_window_returns_samples() {
    let Some(video) = sample_video() else {
        eprintln!("ALLAGANEYE_AUDIO_TEST_VIDEO not set, skipping");
        return;
    };
    // 1 sec interval guard (feedback_ffmpeg_test_interval.md)
    std::thread::sleep(std::time::Duration::from_secs(1));

    let result = allaganeye_gui::extract_brightness_window_impl(
        video.to_string_lossy().to_string(),
        10.0,  // t_start = 10s
        20.0,  // t_end = 20s
        10.0,  // fps = 10
    )
    .await
    .expect("should succeed");

    // 10 sec * 10 fps = 100 samples
    assert!((90..=110).contains(&result.samples.len()), "expected ~100 samples, got {}", result.samples.len());
    // each sample is 0.0..255.0
    for s in &result.samples {
        assert!((0.0..=255.0).contains(s), "sample out of range: {}", s);
    }
    // echoed fields
    assert_eq!(result.t_start, 10.0);
    assert_eq!(result.t_end, 20.0);
    assert_eq!(result.fps, 10.0);
}

#[tokio::test]
async fn extract_brightness_window_handles_missing_file() {
    let result = allaganeye_gui::extract_brightness_window_impl(
        "/nonexistent/path.mp4".to_string(),
        0.0,
        10.0,
        10.0,
    )
    .await;
    assert!(result.is_err());
}
```

(`allaganeye_gui` は crate 名、`Cargo.toml` の `name` に合わせる。`extract_brightness_window_impl` は実装本体を pub で expose する形を想定。Tauri command 関数は pub にしないので impl を切り出す。)

- [ ] **Step 2: テスト実行して失敗確認**

```bash
cd gui/src-tauri && cargo test --test extract_brightness_window
```

Expected: FAIL — `extract_brightness_window_impl` が未定義。

- [ ] **Step 3: BrightnessWindow struct + extract_brightness_window_impl + Tauri command 実装**

[gui/src-tauri/src/lib.rs](../../gui/src-tauri/src/lib.rs) に以下を追加 (既存 `generate_match_thumbnails` の近傍):

```rust
use serde::Serialize;
use ts_rs::TS;
use tokio::process::Command;
use std::process::Stdio;

#[derive(Debug, Clone, Serialize, TS)]
#[ts(export, export_to = "../../gui/src/types/")]
pub struct BrightnessWindow {
    pub samples: Vec<f64>,    // 0.0〜255.0
    pub t_start: f64,
    pub t_end: f64,
    pub fps: f64,
}

/// #645: extract per-frame avg brightness for a time window of a video.
/// Used by PreviewScreen MicroTimeline (±5s zoom around match boundary).
///
/// - Spawns ffmpeg with `-vf "fps={fps},scale=320:180,format=gray"`
/// - Reads raw gray bytes from stdout (320 * 180 = 57600 bytes/frame)
/// - Computes avg brightness per frame
pub async fn extract_brightness_window_impl(
    video_path: String,
    t_start: f64,
    t_end: f64,
    fps: f64,
) -> Result<BrightnessWindow, AppError> {
    let duration = (t_end - t_start).max(0.001);
    let ffmpeg = locate_ffmpeg()?;  // 既存 helper、なければ ffmpeg_path 経由

    let output = Command::new(&ffmpeg)
        .args([
            "-ss", &t_start.to_string(),
            "-i", &video_path,
            "-t", &duration.to_string(),
            "-vf", &format!("fps={},scale=320:180,format=gray", fps),
            "-f", "rawvideo",
            "-",
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .creation_flags(0x0800_0000)  // CREATE_NO_WINDOW for #679 対策 (Windows)
        .output()
        .await
        .map_err(|e| AppError::new(
            "ffmpeg.spawn_failed",
            format!("ffmpeg spawn failed: {}", e),
        ))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(AppError::new(
            "ffmpeg.exit_nonzero",
            format!("ffmpeg exited with {}: {}", output.status, stderr),
        ));
    }

    const FRAME_BYTES: usize = 320 * 180;
    let raw = output.stdout;
    let n_frames = raw.len() / FRAME_BYTES;

    let mut samples = Vec::with_capacity(n_frames);
    for i in 0..n_frames {
        let offset = i * FRAME_BYTES;
        let frame = &raw[offset..offset + FRAME_BYTES];
        let sum: u64 = frame.iter().map(|&b| b as u64).sum();
        let avg = sum as f64 / FRAME_BYTES as f64;
        samples.push(avg);
    }

    Ok(BrightnessWindow {
        samples,
        t_start,
        t_end,
        fps,
    })
}

#[tauri::command]
async fn extract_brightness_window(
    video_path: String,
    t_start: f64,
    t_end: f64,
    fps: f64,
) -> Result<BrightnessWindow, AppError> {
    extract_brightness_window_impl(video_path, t_start, t_end, fps).await
}
```

`tauri::Builder::default().invoke_handler(...)` の handler 配列に `extract_brightness_window` を追加。

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui/src-tauri && cargo test --test extract_brightness_window -- --include-ignored
```

Expected: 2 PASS (sample video 設定済の場合)。

`ALLAGANEYE_AUDIO_TEST_VIDEO` 未設定なら ignored test は skip、`extract_brightness_window_handles_missing_file` のみ PASS。

- [ ] **Step 5: cargo check + clippy**

```bash
cd gui/src-tauri && cargo check && cargo clippy -- -D warnings
```

Expected: 0 error / 0 warning。

- [ ] **Step 6: commit**

```bash
git add gui/src-tauri/src/lib.rs gui/src-tauri/tests/extract_brightness_window.rs
git commit -m "$(printf '%s\n' 'feat(tauri): extract_brightness_window command 新設 (Refs #645)' '' 'PreviewScreen MicroTimeline (±5s zoom) 用の brightness data' 'on-demand 取得 Tauri command を新設。' '' '実装方針:' '- ffmpeg -ss {t_start} -i {video} -t {dur} -vf fps={fps},scale=320:180,format=gray -f rawvideo -' '- stdout から raw gray bytes (320×180=57600 bytes/frame) を読み平均輝度計算' '- AppError 経路 (ffmpeg.spawn_failed / ffmpeg.exit_nonzero)' '- creation_flags(CREATE_NO_WINDOW) で production CMD 窓抑制 (#679 と同方針)' '' 'Rust integration test 2 件:' '- 実 ffmpeg call で ~100 sample 取得確認 (#[ignore]、ALLAGANEYE_AUDIO_TEST_VIDEO 必要)' '- 不在 file で error 確認' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 2.3: MicroTimeline component (TDD)

**Files:**

- Create: `gui/src/components/MicroTimeline.tsx`
- Create: `gui/src/components/MicroTimeline.module.css`
- Create: `gui/src/components/MicroTimeline.test.tsx`

- [ ] **Step 1: テストを先に書く**

```tsx
// gui/src/components/MicroTimeline.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MicroTimeline } from './MicroTimeline';

describe('MicroTimeline', () => {
  const samples = Array.from({ length: 100 }, (_, i) => {
    // simulate: bright (200) → blackout (5) at center → bright (200)
    if (i >= 45 && i <= 55) return 5;
    return 200;
  });

  it('renders SVG with viewBox', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('viewBox');
  });

  it('renders threshold line', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const thresholdLine = container.querySelector('[data-testid="threshold-line"]');
    expect(thresholdLine).not.toBeNull();
  });

  it('renders boundary marker at center', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const marker = container.querySelector('[data-testid="boundary-marker"]');
    expect(marker).not.toBeNull();
  });

  it('renders blackout band for samples below threshold', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const bands = container.querySelectorAll('[data-testid="blackout-band"]');
    expect(bands.length).toBeGreaterThanOrEqual(1);
  });

  it('renders axis labels (-5s / 0 / +5s)', () => {
    render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    expect(screen.getByText('-5s')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('+5s')).toBeInTheDocument();
  });

  it('renders waveform path', () => {
    const { container } = render(
      <MicroTimeline samples={samples} windowSeconds={10} threshold={15} />,
    );
    const path = container.querySelector('[data-testid="waveform-path"]');
    expect(path).not.toBeNull();
    expect(path).toHaveAttribute('d');
  });
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/components/MicroTimeline.test.tsx
```

Expected: FAIL — module not found。

- [ ] **Step 3: MicroTimeline.tsx を実装**

```tsx
// gui/src/components/MicroTimeline.tsx
import { useMemo } from 'react';

import { buildBrightnessPath, findBlackoutRegions } from '../utils/brightness';
import styles from './MicroTimeline.module.css';

export interface MicroTimelineProps {
  samples: readonly number[];
  windowSeconds: number;
  threshold: number;
}

/**
 * #645: ±5s zoom of brightness around a match boundary.
 *
 * - waveform path (gold)
 * - threshold line (danger color, dashed)
 * - blackout band (cyan, samples below threshold)
 * - boundary marker (vertical white dashed line at center)
 * - axis labels (-5s / 0 / +5s)
 *
 * Display-only (Q6 = A、no scrubbing). Reuses utils/brightness.ts.
 */
export function MicroTimeline({
  samples,
  windowSeconds,
  threshold,
}: MicroTimelineProps) {
  const W = 200;
  const H = 36;
  const axisOffset = H + 6;

  const path = useMemo(
    () => buildBrightnessPath(samples, W, H),
    [samples],
  );
  const blackouts = useMemo(
    () => findBlackoutRegions(samples, windowSeconds, threshold),
    [samples, windowSeconds, threshold],
  );
  const thresholdY = H - (threshold / 255) * H;

  return (
    <svg
      viewBox={`0 0 ${W} ${axisOffset + 8}`}
      className={styles.timeline}
      preserveAspectRatio="none"
      data-testid="micro-timeline"
    >
      {/* threshold line */}
      <line
        x1={0}
        x2={W}
        y1={thresholdY}
        y2={thresholdY}
        className={styles.thresholdLine}
        data-testid="threshold-line"
      />

      {/* blackout bands */}
      {blackouts.map((r, i) => {
        const x1 = (r.start / windowSeconds) * W;
        const x2 = (r.end / windowSeconds) * W;
        return (
          <rect
            key={i}
            x={x1}
            y={0}
            width={Math.max(1.5, x2 - x1)}
            height={H}
            className={styles.blackoutBand}
            data-testid="blackout-band"
          />
        );
      })}

      {/* waveform path */}
      {path && (
        <path
          d={path}
          className={styles.waveformPath}
          data-testid="waveform-path"
        />
      )}

      {/* boundary marker (center vertical line) */}
      <line
        x1={W / 2}
        x2={W / 2}
        y1={0}
        y2={H}
        className={styles.boundaryMarker}
        data-testid="boundary-marker"
      />

      {/* axis labels */}
      <text x={2} y={axisOffset + 6} fontSize="6" className={styles.axisLabel}>
        -5s
      </text>
      <text
        x={W / 2}
        y={axisOffset + 6}
        fontSize="6"
        textAnchor="middle"
        className={styles.axisLabel}
      >
        0
      </text>
      <text
        x={W - 2}
        y={axisOffset + 6}
        fontSize="6"
        textAnchor="end"
        className={styles.axisLabel}
      >
        +5s
      </text>
    </svg>
  );
}
```

- [ ] **Step 4: MicroTimeline.module.css を実装**

```css
/* gui/src/components/MicroTimeline.module.css */
.timeline {
  width: 100%;
  height: 50px;
  background: var(--ae-bg-deep);
  display: block;
}

.thresholdLine {
  stroke: var(--ae-danger);
  stroke-dasharray: 2, 2;
  stroke-width: 0.5;
}

.blackoutBand {
  fill: var(--ae-cyan);
  opacity: 0.18;
}

.waveformPath {
  fill: none;
  stroke: var(--ae-gold);
  stroke-width: 1;
}

.boundaryMarker {
  stroke: var(--ae-text);
  stroke-width: 0.5;
  stroke-dasharray: 1, 1;
}

.axisLabel {
  fill: var(--ae-text-dim);
  font-family: var(--ae-font-mono);
}
```

- [ ] **Step 5: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/components/MicroTimeline.test.tsx
```

Expected: PASS (6/6 tests)。

- [ ] **Step 6: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 7: commit**

```bash
git add gui/src/components/MicroTimeline.tsx gui/src/components/MicroTimeline.module.css gui/src/components/MicroTimeline.test.tsx
git commit -m "$(printf '%s\n' 'feat(gui): MicroTimeline component 新設 (Refs #645)' '' 'PreviewScreen ±5s zoom 用の輝度波形 + 閾値線 + blackout マーカー' '+ boundary marker + 軸ラベル を表示する小型 SVG component を新設。' '' '構成:' '- waveform path (gold、buildBrightnessPath utility 共有)' '- threshold line (danger 系、dashed)' '- blackout band (cyan 半透明、findBlackoutRegions utility 共有)' '- boundary marker (中央 vertical 白破線)' '- axis labels (-5s / 0 / +5s)' '' 'Display-only (Q6 = A、no scrubbing)。' 'BrightnessTimeline は不変、utils/brightness.ts を共有再利用。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 2.4: PreviewScreen に MicroTimeline 統合 (TDD)

**Files:**

- Modify: `gui/src/screens/PreviewScreen.tsx`
- Modify: `gui/src/screens/PreviewScreen.test.tsx`

- [ ] **Step 1: テストを先に書く**

PreviewScreen.test.tsx に以下追加:

```tsx
import { vi } from 'vitest';
// invoke を mock
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));
import { invoke } from '@tauri-apps/api/core';

describe('PreviewScreen MicroTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMetadataStore.setState({
      filePath: '/some/video.mp4',
      metadata: { matches: [{ index: 1, start_time: 100, end_time: 200, type: 'fl_match' }], duration: 300 } as any,
    });
    useAppStateStore.setState({ selectedMatchIndex: 1 });
  });

  it('invokes extract_brightness_window with ±5s window', async () => {
    (invoke as any).mockResolvedValueOnce({
      samples: Array.from({ length: 100 }, () => 200),
      t_start: 95,
      t_end: 105,
      fps: 10,
    });
    render(<PreviewScreen />);
    await vi.waitFor(() => {
      expect(invoke).toHaveBeenCalledWith('extract_brightness_window', {
        videoPath: '/some/video.mp4',
        tStart: 95,  // 100 - 5
        tEnd: 105,   // 100 + 5
        fps: 10.0,
      });
    });
  });

  it('renders MicroTimeline after invoke success', async () => {
    (invoke as any).mockResolvedValueOnce({
      samples: Array.from({ length: 100 }, () => 200),
      t_start: 95,
      t_end: 105,
      fps: 10,
    });
    render(<PreviewScreen />);
    expect(await screen.findByTestId('micro-timeline')).toBeInTheDocument();
  });

  it('renders inline error on invoke failure', async () => {
    (invoke as any).mockRejectedValueOnce({
      code: 'ffmpeg.spawn_failed',
      message: 'ffmpeg spawn failed: ENOENT',
      hint: 'ffmpeg バイナリが見つかりません',
    });
    render(<PreviewScreen />);
    expect(await screen.findByText(/ffmpeg spawn failed/)).toBeInTheDocument();
    expect(await screen.findByText(/ffmpeg バイナリが見つかりません/)).toBeInTheDocument();
  });

  it('renders synthetic in sample mode (no invoke)', async () => {
    useMetadataStore.setState({
      filePath: null,
      metadata: { matches: [{ index: 1, start_time: 100, end_time: 200, type: 'fl_match' }], duration: 300 } as any,
    });
    render(<PreviewScreen />);
    // 多少のtick wait
    await vi.waitFor(() => {
      expect(screen.getByTestId('micro-timeline')).toBeInTheDocument();
    });
    expect(invoke).not.toHaveBeenCalled();
    // sample caption 表示
    expect(screen.getByText(/サンプル波形/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: テストを実行して失敗を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx -t 'MicroTimeline'
```

Expected: FAIL。

- [ ] **Step 3: PreviewScreen.tsx を改修 (MicroTimeline 統合)**

```tsx
import { invoke } from '@tauri-apps/api/core';
import { MicroTimeline } from '../components/MicroTimeline';
import { buildLocalBrightness } from '../utils/brightness';
import { appErrorMessage, appErrorHint, toAppError, type AppError } from '../utils/appError';

// PreviewScreen 関数本体内に追加:
const detectionParams = useMetadataStore((s) => s.metadata?.detection_params);
const blackoutThreshold = detectionParams?.blackout_threshold ?? 15;

const [brightnessWindow, setBrightnessWindow] = useState<{
  samples: number[];
  t_start: number;
  t_end: number;
  fps: number;
} | null>(null);
const [microError, setMicroError] = useState<AppError | null>(null);

useEffect(() => {
  if (!selectedMatch) {
    setBrightnessWindow(null);
    setMicroError(null);
    return;
  }
  setBrightnessWindow(null);
  setMicroError(null);
  if (isSample) {
    // sample mode: synthetic
    setBrightnessWindow({
      samples: buildLocalBrightness(selectedMatch.start_time, 5, 10),
      t_start: selectedMatch.start_time - 5,
      t_end: selectedMatch.start_time + 5,
      fps: 10,
    });
    return;
  }
  if (!filePath) return;
  invoke<{ samples: number[]; t_start: number; t_end: number; fps: number }>(
    'extract_brightness_window',
    {
      videoPath: filePath,
      tStart: Math.max(0, selectedMatch.start_time - 5),
      tEnd: selectedMatch.start_time + 5,
      fps: 10.0,
    },
  )
    .then(setBrightnessWindow)
    .catch((e) => setMicroError(toAppError(e)));
}, [selectedMatch?.index, filePath, isSample]);
```

JSX (strip section 内、FrameStrip caption 直前) に追加:

```tsx
<div className={styles.strip}>
  <div className={styles.stripCaption}>
    微細タイムライン ⸱ ±5s{isSample && ' ⸱ サンプル波形'}
  </div>
  {brightnessWindow ? (
    <MicroTimeline
      samples={brightnessWindow.samples}
      windowSeconds={10}
      threshold={blackoutThreshold}
    />
  ) : microError ? (
    <div className={styles.microError} role="alert">
      <span>{appErrorMessage(microError)}</span>
      {appErrorHint(microError) && (
        <span className={styles.microErrorHint}>💡 {appErrorHint(microError)}</span>
      )}
    </div>
  ) : (
    <div className={styles.microTimelineLoading}>計測中…</div>
  )}
  <div className={styles.stripCaption}>候補フレーム ⸱ CANDIDATE FRAMES</div>
  <FrameStrip ... />
</div>
```

`PreviewScreen.module.css` に `microError` / `microErrorHint` / `microTimelineLoading` のスタイル追加 (既存 inline error / loading のパターン踏襲)。

- [ ] **Step 4: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/screens/PreviewScreen.test.tsx
```

Expected: ALL PASS (新規 4 件 + Chapter 1 既存 + 元来既存)。

- [ ] **Step 5: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 6: commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.test.tsx gui/src/screens/PreviewScreen.module.css
git commit -m "$(printf '%s\n' 'feat(gui): PreviewScreen に MicroTimeline 統合 (Refs #645)' '' 'PreviewScreen の strip section (FrameStrip caption 直前) に' 'MicroTimeline (±5s 微細タイムライン) を統合。' '' 'state 管理:' '- brightnessWindow / microError local state (metadataStore に持たない)' '- selectedMatch / filePath / isSample 変更で useEffect 発火' '- 通常 file: extract_brightness_window invoke で ffmpeg 経由取得' '- sample mode: buildLocalBrightness synthetic (caption に「サンプル波形」付)' '- error: inline error (appErrorMessage + appErrorHint、§1.5)' '' 'detection_params.blackout_threshold (default 15) を threshold に渡す。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 2.5: ui-interaction-spec.md + tauri-commands.md doc 更新

**Files:**

- Modify: `docs/ui-interaction-spec.md`
- Modify: `docs/tauri-commands.md`

- [ ] **Step 1: ui-interaction-spec.md §2.4 に MicroTimeline 部品節追加**

[docs/ui-interaction-spec.md](../../ui-interaction-spec.md) §2.4 (preview) の最後に新部品節を追加:

```markdown
#### §2.4.X MicroTimeline (±5s 微細タイムライン) — #645

| 項目 | 内容 |
|---|---|
| 種類 | SVG display (read-only、interaction なし) |
| 状態 | `loading` (取得中) / `loaded` (波形描画) / `error` (inline error) / `sample` (synthetic 波形 + 「サンプル波形」caption) |
| 遷移トリガー | selectedMatch 変更 / filePath 変更 / isSample 変更で useEffect 再発火。real file → invoke('extract_brightness_window') → loaded or error。sample mode → buildLocalBrightness synthetic |
| store mutation | なし (PreviewScreen 内 local state、`brightnessWindow` / `microError`) |
| 例外 / edge case | (1) ffmpeg spawn failed / exit nonzero → §1.5 inline error 表示 (appErrorMessage + appErrorHint)。 (2) sample mode は ffmpeg 不可なので synthetic 一律使用、caption に「サンプル波形」付与。 (3) selectedMatch=null → 何も表示しない |
```

- [ ] **Step 2: tauri-commands.md に extract_brightness_window 追加**

```bash
grep -n "## " docs/tauri-commands.md | head -20
```

で既存 command の節構造を確認し、同 pattern で `extract_brightness_window` 節を追加:

```markdown
## `extract_brightness_window` (#645)

PreviewScreen MicroTimeline (±5s zoom) 用の brightness data on-demand 取得 command。

### 引数

| 引数 | 型 | 説明 |
| --- | --- | --- |
| `video_path` | `string` | 動画 file の絶対 path |
| `t_start` | `number` (f64) | window 開始秒 (絶対時刻) |
| `t_end` | `number` (f64) | window 終了秒 (絶対時刻) |
| `fps` | `number` (f64) | サンプリング fps (default 10.0) |

### 戻り値

| field | 型 | 説明 |
| --- | --- | --- |
| `samples` | `number[]` | 0.0〜255.0 のフレーム平均輝度配列 (~`(t_end-t_start) * fps` 個) |
| `t_start` | `number` | 入力 echoed |
| `t_end` | `number` | 入力 echoed |
| `fps` | `number` | 入力 echoed |

### 失敗パス

| code | hint |
| --- | --- |
| `ffmpeg.spawn_failed` | ffmpeg バイナリが見つかりません。... |
| `ffmpeg.exit_nonzero` | ffmpeg がエラー終了しました。... |
```

(既存 hint 文言は `error.rs::default_hint_for_code` の現状に合わせる)

- [ ] **Step 3: markdownlint で 0 error 確認**

```bash
bash scripts/check-markdownlint.sh
```

- [ ] **Step 4: commit**

```bash
git add docs/ui-interaction-spec.md docs/tauri-commands.md
git commit -m "$(printf '%s\n' 'docs: ui-interaction-spec §2.4 + tauri-commands.md MicroTimeline 追記 (Refs #645)' '' 'PR #645 で MicroTimeline + extract_brightness_window 実装に伴い:' '- ui-interaction-spec.md §2.4 に MicroTimeline 部品節追加' '  (state: loading / loaded / error / sample)' '- tauri-commands.md に extract_brightness_window 節追加' '  (引数 / 戻り値 / 失敗パス)' '' 'Group J #692 (CI hint table drift check) と整合する error code' 'mapping を本 doc で予約。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 2.6: PR #645 全自動チェック実行

**Files:** changes only

- [ ] **Step 1: GUI 全テスト実行**

```bash
cd gui && npm test
```

- [ ] **Step 2: GUI lint / typecheck / build**

```bash
cd gui && npm run lint && npm run typecheck && npm run build
```

- [ ] **Step 3: cargo check + clippy + cargo test**

```bash
cd gui/src-tauri && cargo check && cargo clippy -- -D warnings && cargo test
```

(integration test の `#[ignore]` 付き sample video テストは `--include-ignored` で別途、可能なら実行)

- [ ] **Step 4: markdownlint**

```bash
bash scripts/check-markdownlint.sh
```

- [ ] **Step 5: Iron Law 6 Pre-flight 再実行**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#645 OR #644" --state all
```

### Task 2.7: PR #645 Idios 実機検証依頼 + PR submission

**Files:** PR creation only

- [ ] **Step 1: 実機検証依頼**

`AskUserQuestion` で Idios に依頼:

```text
PR #645 (preview 微細タイムライン ±5s) の実機検証依頼:

1. cd gui && npm run tauri dev で起動
2. 実動画 (ALLAGANEYE_SAMPLE_VIDEO_DIR) を選択
3. detect 完了後、Complete から match を 1 件選んで Preview に進む
4. 以下を visual 確認:
   - FrameStrip 直上に「微細タイムライン ⸱ ±5s」section
   - ~200ms で MicroTimeline 描画 (loading → loaded 遷移)
   - 試合切替で再取得 (loading → loaded)
   - 閾値線 / blackout band / boundary marker / axis labels (-5s/0/+5s) 視認
5. 動画 file 削除 (一時的) などで取得失敗を再現し inline error 確認
6. StateSwitcher で sample mode に切替し:
   - synthetic 波形描画
   - caption が「微細タイムライン ⸱ ±5s ⸱ サンプル波形」
   - invoke が呼ばれない (Network Inspector / log で確認)
7. ffmpeg 8.1 PTS offset (#575) で表示位置に違和感ないこと

Q: 実機検証 result は？
- (a) ALL PASS
- (b) 一部 NG (詳細指摘)
```

- [ ] **Step 2: PR 作成 (PASS 後)**

PR 本文 (HEREDOC):

```bash
gh pr create --base develop-0.2.0 --title "feat(gui): preview 微細タイムライン ±5s 実装 (Refs #645)" --body-file - <<'EOF'
## 概要

PreviewScreen に微細タイムライン (±5s 輝度波形 + 閾値線 + blackout マーカー
+ boundary marker + axis labels) を追加実装。Tauri command
extract_brightness_window で ffmpeg 経由 on-demand 取得。

## Refs

- #645 (P3、本 PR で対応)
- 派生元: #465 (close 時に検出した未消化作業)

## 設計

[docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md](docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md) §3 Chapter 2 参照。

## Self-Test Report

### Machine-verified

- [x] cd gui && npm test (ALL PASS)
- [x] cd gui && npm run lint / typecheck / build (各 0 error)
- [x] cd gui/src-tauri && cargo check / clippy / test (0 error)
- [x] bash scripts/check-markdownlint.sh (0 error)

### Machine-unverifiable (Idios 実機検証済)

- 実動画で MicroTimeline ~200ms 描画
- 試合切替で再取得
- 閾値線 / blackout band / boundary marker / axis labels visual 視認
- 取得失敗 inline error 表示
- sample mode で synthetic 波形 + caption「サンプル波形」
- ffmpeg 8.1 PTS offset 範囲内で表示違和感なし

## Pre-flight (Iron Law 6)

- git fetch origin develop-0.2.0 + 取り込み未済 commit 確認 → merge 取り込み済
- gh pr list --search "#645 OR #644" → #644 merge 済確認、並行 PR なし

## 受け入れ条件 (#645、6 項目逐条)

| # | 項目 | 充足 |
| --- | --- | --- |
| 1 | preview 画面 FrameStrip 周辺に微細タイムライン UI 部品配置 | Task 2.4 |
| 2 | 輝度波形データ取得経路の検討 (CSV vs ffmpeg subprocess) | Task 2.2 (Tauri command on-demand 採用、Q4 確定) |
| 3 | 閾値線 (detection_params.blackout_threshold) 描画 | Task 2.3 |
| 4 | 検知済 blackout region マーカー | Task 2.3 (findBlackoutRegions 共有 utility 経由) |
| 5 | vitest (mount / 閾値線 / マーカー描画) | Task 2.3 |
| 6 | docs/ui-interaction-spec.md §2.4 に部品状態機械追加 | Task 2.5 |

## session-id

cranky-sanderson-2872af

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 3: CI 結果確認**

```bash
gh pr checks <PR#>
```

---

## Chapter 3 (PR #677) — SideRail 全体削除

**対象 issue**: [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) (P3 bug)
**PR 順**: 3 本目 (独立、衝突 risk 最小)

### Task 3.1: Pre-flight checks for PR #677

**Files:** changes only

- [ ] **Step 1: base 同期 + 取り込み未済 commit 確認**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
```

- [ ] **Step 2: 並行 worktree PR 確認**

```bash
gh pr list --search "#677" --state all
```

Expected: 既存 PR なし (App.tsx / SideRail.tsx 触る他 PR がないこと)。

- [ ] **Step 3: SideRail 参照箇所の grep 洗い出し**

```bash
grep -rn "SideRail" gui/src docs --include="*.tsx" --include="*.ts" --include="*.css" --include="*.md"
```

Expected: 修正対象 file の一覧 (SideRail.tsx / SideRail.module.css / SideRail.test.tsx / App.tsx / App.test.tsx + design doc)。

- [ ] **Step 4: 着手 issue の AC を再確認**

```bash
gh issue view 677 --json body | jq -r .body | head -50
```

### Task 3.2: App.tsx + App.module.css から SideRail 削除 (TDD)

**Files:**

- Modify: `gui/src/App.tsx`
- Modify: `gui/src/App.test.tsx`
- Modify: `gui/src/App.module.css`

- [ ] **Step 1: テストを先に書く / 既存 SideRail assertion を削除予定とマーク**

[gui/src/App.test.tsx](../../gui/src/App.test.tsx) を確認:

```bash
grep -n "SideRail" gui/src/App.test.tsx
```

各 hit を確認し、SideRail render を assert している行を削除予定としてマーク。

新規 assertion (SideRail が存在しないこと):

```tsx
it('does not render SideRail (#677 で削除済)', () => {
  render(<App />);
  expect(screen.queryByLabelText('Allagan Eye navigation')).toBeNull();
});
```

- [ ] **Step 2: テストを実行して失敗を確認 (現状は SideRail がいるので fail)**

```bash
cd gui && npx vitest run src/App.test.tsx
```

Expected: FAIL — SideRail がまだ render されている。

- [ ] **Step 3: App.tsx を改修**

[gui/src/App.tsx:4](../../gui/src/App.tsx#L4) の `import { SideRail } from './components/SideRail';` を削除。

[gui/src/App.tsx:35](../../gui/src/App.tsx#L35) の `<SideRail />` を削除。

- [ ] **Step 4: App.module.css の cleanup**

[gui/src/App.module.css](../../gui/src/App.module.css) の `.body` rule を確認:

```css
.body {
  flex: 1;
  display: flex;
  min-height: 0;
}
```

`flex: 1; display: flex;` は維持 (StateSwitcher 等の右上 absolute 配置との整合)。SideRail 関連 selector があれば削除 (現状 .body 内に SideRail 専用 rule なし、`.main` の min-width は維持)。

- [ ] **Step 5: テストを再実行して pass を確認**

```bash
cd gui && npx vitest run src/App.test.tsx
```

Expected: PASS (SideRail render 削除済 + 新規 assertion PASS)。

- [ ] **Step 6: lint / typecheck**

```bash
cd gui && npm run lint && npm run typecheck
```

- [ ] **Step 7: commit**

```bash
git add gui/src/App.tsx gui/src/App.test.tsx gui/src/App.module.css
git commit -m "$(printf '%s\n' 'fix(gui): App.tsx から SideRail render 削除 (Refs #677)' '' '#677 ユーザー報告: 装飾 4 アイコンが選択 UI に見えるが機能なし' 'のため、SideRail 全体を App.tsx から削除 (Q7 = b 全体削除)。' '' '改修内容:' '- import { SideRail } 削除' '- <SideRail /> render 削除' '- App.module.css の SideRail 関連 selector 確認 (cleanup なし)' '- App.test.tsx の SideRail render assertion 削除 + 新規' '  「does not render SideRail」assertion 追加' '' 'main content 幅が +48px される。5 画面 layout 回帰確認は実機検証で実施。' '' 'ALLAGAN identity は AllaganCorner / AllaganFrame で継続維持。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 3.3: SideRail file 削除

**Files:**

- Delete: `gui/src/components/SideRail.tsx`
- Delete: `gui/src/components/SideRail.module.css`
- Delete: `gui/src/components/SideRail.test.tsx`

- [ ] **Step 1: file 削除**

```bash
rm gui/src/components/SideRail.tsx gui/src/components/SideRail.module.css gui/src/components/SideRail.test.tsx
```

- [ ] **Step 2: 残参照がないこと確認**

```bash
grep -rn "SideRail" gui/src --include="*.tsx" --include="*.ts" --include="*.css"
```

Expected: 0 hit (App.tsx / App.test.tsx / App.module.css は Task 3.2 で対応済)。

- [ ] **Step 3: 全テスト + lint / typecheck / build**

```bash
cd gui && npm test && npm run lint && npm run typecheck && npm run build
```

Expected: ALL PASS / 0 error。

- [ ] **Step 4: cargo check (Rust 影響なし確認)**

```bash
cd gui/src-tauri && cargo check
```

Expected: 0 error。

- [ ] **Step 5: commit**

```bash
git add gui/src/components/SideRail.tsx gui/src/components/SideRail.module.css gui/src/components/SideRail.test.tsx
git commit -m "$(printf '%s\n' 'fix(gui): SideRail.tsx / module.css / test 削除 (Refs #677)' '' 'App.tsx から SideRail render 削除済 (Task 3.2、別 commit) のため' 'コンポーネント本体 + スタイル + テストを削除。' '' '削除 file:' '- gui/src/components/SideRail.tsx' '- gui/src/components/SideRail.module.css' '- gui/src/components/SideRail.test.tsx' '' 'grep -rn SideRail gui/src で 0 hit 確認済。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 3.4: jest-axe verification (5 画面)

**Files:**

- Modify: `gui/src/App.test.tsx` (a11y assertion 拡張、既存パターンあれば踏襲)

- [ ] **Step 1: 既存 jest-axe pattern 確認**

```bash
grep -rn "jest-axe\|axe(" gui/src --include="*.test.tsx" | head -10
```

issue [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) で導入済の jest-axe usage を確認。既存 SideRail.test.tsx に jest-axe 検証があれば、その pattern を 5 画面に展開。

- [ ] **Step 2: 5 画面で jest-axe 違反なし確認**

App.test.tsx (または各 screen test) に SideRail 削除後の a11y violation 検証を追加:

```tsx
import { axe, toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

it.each([
  ['drop'],
  ['detecting'],
  ['complete'],
  ['preview'],
  ['export'],
])('has no a11y violations on %s screen', async (screen) => {
  useAppStateStore.setState({ screen });
  // 必要なら metadataStore も setup
  const { container } = render(<App />);
  const results = await axe(container);
  expect(results).toHaveNoViolations();
});
```

(既存パターンに合わせて調整)

- [ ] **Step 3: テスト実行して pass 確認**

```bash
cd gui && npx vitest run src/App.test.tsx -t 'a11y'
```

Expected: PASS (5 画面それぞれ 0 violation)。

- [ ] **Step 4: commit**

```bash
git add gui/src/App.test.tsx
git commit -m "$(printf '%s\n' 'test(gui): jest-axe で SideRail 削除後の 5 画面 a11y violation なし確認 (Refs #677)' '' '#677 受け入れ条件「jest-axe で a11y violation が発生しないこと」のため' 'App.test.tsx に 5 画面 (drop / detecting / complete / preview / export) の' 'a11y check を it.each で追加。' '' '0 violation を確認済。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 3.5: aether.jsx mockup に「production 削除済」comment 追記

**Files:**

- Modify: `docs/design/bundle/project/variants/aether.jsx`

- [ ] **Step 1: aether.jsx 該当箇所を確認**

```bash
sed -n '436,455p' docs/design/bundle/project/variants/aether.jsx
```

inline rail mock (lines 436-455) を確認。

- [ ] **Step 2: comment 追記**

[docs/design/bundle/project/variants/aether.jsx:436](../../docs/design/bundle/project/variants/aether.jsx#L436) の `{/* Side rail */}` を以下に書き換え:

```jsx
{/* Side rail
    [2026-05-11 #677] Production では SideRail.tsx を削除済 (アイコンが
    選択 UI に見えるが機能なし、ユーザー報告)。本 mockup は historical
    reference として残す。実 production の構造は App.tsx / AllaganCorner /
    AllaganFrame を参照。
*/}
```

- [ ] **Step 3: design doc 他参照確認**

```bash
grep -rn "SideRail\|side rail" docs/design docs/ui-architecture.md docs/design/README.md 2>&1
```

他 doc に SideRail 言及があれば、本 PR で削除済の旨に書き換え。

- [ ] **Step 4: markdownlint**

```bash
bash scripts/check-markdownlint.sh
```

Expected: 0 error。

- [ ] **Step 5: commit**

```bash
git add docs/design/bundle/project/variants/aether.jsx
# 必要なら他 doc も add
git commit -m "$(printf '%s\n' 'docs: aether.jsx mockup に SideRail production 削除済 comment 追記 (Refs #677)' '' '#677 で SideRail.tsx を削除したため、historical mockup である' 'aether.jsx の inline rail (lines 436-455) に「production 削除済」' 'comment を追記。実 production の構造は App.tsx 等を参照する旨明示。' '' 'Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

### Task 3.6: PR #677 全自動チェック実行

**Files:** changes only

- [ ] **Step 1: GUI 全テスト**

```bash
cd gui && npm test
```

- [ ] **Step 2: GUI lint / typecheck / build**

```bash
cd gui && npm run lint && npm run typecheck && npm run build
```

- [ ] **Step 3: cargo check**

```bash
cd gui/src-tauri && cargo check
```

- [ ] **Step 4: markdownlint**

```bash
bash scripts/check-markdownlint.sh
```

- [ ] **Step 5: Iron Law 6 Pre-flight 再実行**

```bash
git fetch origin develop-0.2.0
git log HEAD..origin/develop-0.2.0 --oneline
gh pr list --search "#677" --state all
```

### Task 3.7: PR #677 Idios 実機検証依頼 + PR submission

**Files:** PR creation only

- [ ] **Step 1: 実機検証依頼 (5 画面 layout 回帰)**

`AskUserQuestion` で Idios に依頼:

```text
PR #677 (SideRail 全体削除) の実機検証依頼:

1. cd gui && npm run tauri dev で起動
2. 5 画面巡回し layout 回帰確認:
   - DropScreen: D&D zone / 直近録画 list / SelectedCard レイアウト
   - DetectingScreen: AllaganSigil 中央配置 / progress bar 幅
   - CompleteScreen: BrightnessTimeline 幅 / matches list / sourceBox
   - PreviewScreen: panes (×2 video) 横並び / FrameStrip 幅 / MicroTimeline 幅
   - ExportScreen: 出力先 input / list / progressBox
3. 各画面で main content が +48px 広がり、過度な空白 / 切れ / overflow なし
4. ALLAGAN identity (AllaganCorner / AllaganFrame) が画面 identity を維持

Q: 実機検証 result は？
- (a) ALL PASS
- (b) 一部 NG (どの画面のどこか詳細指摘)
```

- [ ] **Step 2: PR 作成**

```bash
gh pr create --base develop-0.2.0 --title "fix(gui): SideRail 全体削除 (Refs #677)" --body-file - <<'EOF'
## 概要

#677 ユーザー報告「SideRail のアイコンが選択 UI に見えるが機能なし」のため、
SideRail コンポーネント全体を削除 (Q7 = b 全体削除)。main content 幅が +48px。

## Refs

- #677 (P3 bug、本 PR で対応)

## 設計

[docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md](docs/superpowers/specs/2026-05-11-group-c-preview-sample-mode-design.md) §4 Chapter 3 参照。

## 削除内容

- gui/src/components/SideRail.tsx
- gui/src/components/SideRail.module.css
- gui/src/components/SideRail.test.tsx
- gui/src/App.tsx の import + render

## 維持

- ALLAGAN identity は AllaganCorner (右上 ◈) と AllaganFrame (画面 frame) で継続

## Self-Test Report

### Machine-verified

- [x] cd gui && npm test (ALL PASS、jest-axe 5 画面 0 violation)
- [x] cd gui && npm run lint / typecheck / build (各 0 error)
- [x] cd gui/src-tauri && cargo check (0 error)
- [x] bash scripts/check-markdownlint.sh (0 error)
- [x] grep -rn SideRail gui/src で 0 hit

### Machine-unverifiable (Idios 実機検証済)

- 5 画面 layout 回帰確認 (Drop / Detecting / Complete / Preview / Export)
- 各画面で main content +48px 広がり、過度な空白 / 切れ / overflow なし
- ALLAGAN identity 維持 (AllaganCorner / AllaganFrame)

## Pre-flight (Iron Law 6)

- git fetch origin develop-0.2.0 + 取り込み未済 commit 確認 → merge 取り込み済
- gh pr list --search "#677" → 並行 PR なし

## 受け入れ条件 (#677、4 項目逐条)

| # | 項目 | 充足 |
| --- | --- | --- |
| 1 | 4 つのアイコン (◈ ◇ ◆ ⎊) を画面から除去 ((a) or (b)) | (b) 全体削除採用 (Task 3.2/3.3) |
| 2 | SideRail.test.tsx の関連 assertion 更新 | Task 3.3 (削除) + Task 3.4 (新規 assertion) |
| 3 | 関連 design doc (aether.jsx 等) の整合性確認 | Task 3.5 (comment 追記) |
| 4 | jest-axe で a11y violation が発生しないこと | Task 3.4 (5 画面 0 violation 確認) |

## session-id

cranky-sanderson-2872af

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
```

- [ ] **Step 3: CI 結果確認**

```bash
gh pr checks <PR#>
```

---

## Post-merge handoff (各 PR で)

各 PR が merge されたら `/close-issue` skill にハンドオフして元 issue を実測再検証 + close する (Iron Law 4)。

| PR | 元 issue | 受け入れ条件再検証ポイント |
| --- | --- | --- |
| PR #633 | #633 | base ブランチで sample mode 切替 + 3 画面の banner / disabled / tooltip 実機確認 |
| PR #645 | #645 | base ブランチで preview MicroTimeline 描画 / 取得失敗 / sample 動作確認 |
| PR #677 | #677 | base ブランチで 5 画面 layout 回帰 + jest-axe 0 violation 確認 |

`Closes` keyword は使わず手動 `gh issue close` (Iron Law 4)。
