# L2 Lane V Phase 1: Group I post-#663 hint UI cleanup 5 件 batch 設計

> **Status**: v0.2.0 リリースゲート Lane V Phase 1 (Group I の Phase 1)
> **Scope**: 5 PR (1 spec / 5 章) — [#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) / [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) / [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) / [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) / [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698)
> **session**: `mystifying-fermat-24c196` (2026-05-11 brainstorming、Idios + Claude Opus 4.7)
> **依存元 PR**: [#689](https://github.com/Idios/kobutachan-allaganeye/pull/689) (#663 AppError migration 完遂、MERGED) — Round 1 review / final code review で flag された follow-up を本 spec で消化
> **親 plan**: [docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](../plans/2026-05-11-l2-v020-roadmap-update.md) §Group I

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) | OPEN | **PR 2 で対応** (metadataStore catch path lifecycle pinning) |
| [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) | OPEN | **PR 1 (lead) で対応** (InlineErrorHint component 新設 + 既存 5 site refactor) |
| [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) | OPEN | **PR 3 で対応** (ConflictModal AppError hint 表示) |
| [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) | OPEN | **PR 4 で対応** (DraftRestoreModal `draftLoadErrorHint` UI) |
| [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698) | OPEN | **PR 5 で対応** (DropScreen recentStore notice、案 A-minimal 採用) |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | CLOSED (PR #689 merged) | AppError migration 親 issue、本 spec は #689 の follow-up を消化 |
| [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) | OPEN (Phase 2 へ) | unified `*ErrorState: AppError\|null` refactor、Wave 1 main 3 lane merge 後着手のため本 spec 対象外 |
| [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) | OPEN (Phase 3 へ) | AppError 関連 stale docstring 更新、#694 merge 後着手のため本 spec 対象外 |
| [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) | OPEN (Lane II-a) | sample mode 全画面 read-only 化、DropScreen 共有のため #698 と「先着優先 + rebase」運用 |

## §1 Background — PR #689 で確立した hint UI 規約と残された 5 件

PR #689 (2026-05-08 merged) は #663 「legacy 17 Tauri command の AppError migration」を 5 phase で完遂した:

1. Rust `error.rs::default_hint_for_code()` + `with_default_hint()` を追加 (22 codes)
2. Rust `lib.rs` 全 80 site の `AppError::new(...)` に `.with_default_hint()` を chain
3. Frontend `metadataStore` に 5 `*ErrorHint` state + `recentStore` に 2 `*ErrorHint` state を追加
4. 5 screen + RestoreButton の inline error に hint 2 行目を render (`💡` prefix + `var(--ae-text-dim)`)
5. `docs/tauri-commands.md` / `ui-architecture.md` §4 / `ui-interaction-spec.md` §1.5 に AppError code 体系と分岐ルールを明文化

PR #689 Round 1 review および final code review (`Issue 9` ほか) で flag された 5 件は、いずれも「core scope (5 screen + RestoreButton) には含まれないが follow-up として必要」な項目で、本 spec で個別 PR として消化する。

5 件の性格:

- **#691** (refactor): metadataStore の 5 catch path × 5 `*ErrorHint` state の clear 範囲が非対称。`load()` catch だけ部分的に他経路の hint も clear する pre-existing pattern。lifecycle を test で pin + 規約明文化
- **#693** (task): `💡` emoji prefix が 5 site で hard-code (現状は emoji + space `💡 hint…` の形式)。i18n / theme 切替に対応するため共通化
- **#695** (task): ConflictModal は `state.mtime_conflict` AppError hint を未表示 (PR #689 で「compose hint と概念衝突回避のため scope 外」と留保)。dead state を解消
- **#697** (task): DraftRestoreModal の `draftLoadErrorHint` も dead state。Phase 4 既存パターン (5 screen + RestoreButton) に準じて UI 追加
- **#698** (task): DropScreen は recentStore の `loadError` / `addError` を ignore する設計だったが、`*ErrorHint` も dead state 化。notice 表示で UX 向上

## §2 Goals

1. PR #689 で残された 5 件の post-#663 follow-up を v0.2.0 リリースゲートに含めて消化し、`*ErrorHint` の dead state をゼロにする (#697 #698 で 3 hint pair を活かす)
2. hint UI の prefix・スタイル・a11y 規約を 1 つの `InlineErrorHint` component に集約し、5 既存 site + 新規 3 site (#695 #697 #698) で同 component を消費する (= 8 site で hint UI 統一)
3. metadataStore の 5 catch path × 5 `*ErrorHint` state の clear 範囲を test で pin し、将来 path 追加時の guardrail を設置する (#691)
4. ConflictModal の hint slot に AppError hint を主、modal 局所文言 (キャンセル の挙動) を補足 1 行で配置する規約を新設 (#695)
5. DropScreen が recentStore error を user に告知する規約 (best-effort fluff のまま subtle に notice、dismiss なし) を新設 (#698)
6. Lane V Phase 1 全 5 件で Iron Law 1〜6 を厳守 (1 PR = 1 issue / `Refs #N` / PR Pre-flight / 実機検証 trigger)

## §3 Non-goals (scope 外明記)

- **#694 unified `*ErrorState: AppError|null` refactor**: 5 store の `*Error` / `*ErrorHint` 並列構造を 1 つの `AppError|null` state に集約する大規模 refactor。consumer は 5 screen + 3 modal で広範囲、Wave 1 main 3 lane merge 後に Phase 2 として独立 spec で扱う
- **#699 AppError 関連 stale docstring 更新**: `gui/src/lib/appError.ts:57-62` / `gui/src-tauri/src/error.rs:28-34` 等の stale 文言の post-#663 状態への更新。#694 refactor 結果を反映するため Phase 3 として独立扱い
- **ErrorModal (#614) への AppError 統合**: Group D #696 (Wave 1 main / Lane II-b) で扱う
- **`globalErrorListener.ts` への AppError parse 追加**: PR #689 spec §3 scope 外明記、別 issue に reservation
- **新規 Tauri command の追加 / 削除**: Group B (Wave 1 main / Lane I-B) で扱う
- **自動 telemetry / Sentry crash reporter 統合**: v0.2.0 外
- **i18n フレームワーク導入**: #693 では prefix 共通化のみ、言語切替は別 issue
- **`markdownlint-cli2.yaml` の nested ignore**: Group J #700 (Lane IV-b') で扱う

## §4 Architecture (5 PR / 2 wave 構成)

```text
═══════════════════════════════════════════════════════════════════════════
WAVE 1.1  (lead + 完全独立 1 件、最大 2 PR 並行)
═══════════════════════════════════════════════════════════════════════════
  PR 1: #693 InlineErrorHint component 新設 + 既存 5 site refactor    (lead)
  PR 2: #691 metadataStore catch path lifecycle pinning  (UI 非依存、PR 1 と完全並行)

═══════════════════════════════════════════════════════════════════════════
WAVE 1.2  (PR 1 merge 後、3 PR 並行可)
═══════════════════════════════════════════════════════════════════════════
  PR 3: #695 ConflictModal AppError hint 表示             (InlineErrorHint consume)
  PR 4: #697 DraftRestoreModal hint UI 追加               (InlineErrorHint consume)
  PR 5: #698 DropScreen recentStore notice 表示           (InlineErrorHint consume)
═══════════════════════════════════════════════════════════════════════════
```

各 PR は独立 worktree (`.claude/worktrees/<auto-name>/`) で進行する。**PR 2 (#691) は UI / InlineErrorHint に非依存**のため Wave 1.1 で PR 1 と完全並行 (PR 提出・merge 順は問わない)。一方 **PR 3-5 は `InlineErrorHint` を consume するため PR 1 merge 後**に `git merge origin/develop-0.2.0` で base 同期して着手する。worktree 数の最大は 5 (全 PR の worktree を同時に存在させてもよいが、PR 3-5 の PR 提出は Wave 1.2 へ後回し)。

```text
                                 PR 1 (#693)
                            ┌──────────────────┐
                            │ InlineErrorHint  │
                            │ component 新設    │
                            │ + 既存 5 site     │
                            │ refactor          │
                            └─────────┬────────┘
                                      │ merge to develop-0.2.0
                                      │
                ┌─────────────────────┼─────────────────────┐
                │                     │                     │
                ▼                     ▼                     ▼
            PR 2 (#691)           PR 3 (#695)           PR 4 (#697)           PR 5 (#698)
        ┌──────────────┐     ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
        │ metadataStore│     │ ConflictModal│      │ DraftRestore │      │ DropScreen   │
        │ lifecycle    │     │ AppError hint│      │ Modal hint   │      │ recent notice│
        │ pinning      │     │ (C 案 採用)   │      │ UI 追加      │      │ (A-minimal)  │
        └──────────────┘     └──────────────┘      └──────────────┘      └──────────────┘
```

## §5 各 PR 章 (5 章)

### §5.1 PR 1 (#693): InlineErrorHint component 新設 + 既存 5 site refactor

**新規 file**:

- `gui/src/components/InlineErrorHint.tsx`
- `gui/src/components/InlineErrorHint.module.css`
- `gui/src/components/InlineErrorHint.test.tsx`

**Component API**:

```tsx
type InlineErrorHintProps = { hint: string | null | undefined };

export function InlineErrorHint({ hint }: InlineErrorHintProps): JSX.Element | null {
  if (!hint) return null;
  return <span className={styles.hint}>💡 {hint}</span>;
}
```

**a11y 規約**:

- consumer 側で `role="alert"` wrapper の **内側** に配置 (PR #689 Phase 4 規約を継承)
- `InlineErrorHint` 自身に `role` を付けない (重複防止、`role="alert"` の nest は a11y violation)

**CSS** (`InlineErrorHint.module.css`):

- `.hint`: `color: var(--ae-text-dim)` / `font-size: 11px` (Phase 4 で確立した値) / `font-family: var(--ae-font-body)` / `display: block` / `line-height: 1.5`
- consumer 側の site-specific override (PreviewScreen `display: block` / ExportScreen `white-space: normal` + `max-width: 100%` + `overflow: visible`) は consumer 側 wrapper class に残す (本 component は最小 layout のみ)

**既存 5 site refactor**:

| site | 変更点 |
| --- | --- |
| `gui/src/components/RestoreButton.tsx` | `<div className={styles.errorHint}>💡 {hint}</div>` → `<InlineErrorHint hint={errorHint} />` |
| `gui/src/screens/DropScreen.tsx` (ErrorCard 内) | 同上 |
| `gui/src/screens/DetectingScreen.tsx` (errorScreen 内) | 同上 |
| `gui/src/screens/PreviewScreen.tsx` (applyError 内) | 同上 (wrapper class `.applyErrorHint` の `display: block` を維持) |
| `gui/src/screens/ExportScreen.tsx` (listError 内) | 同上 (wrapper class `.listErrorHint` の `white-space: normal` 等を維持) |

**Test**:

- `InlineErrorHint.test.tsx` (新規 3-4 件):
  - hint set 時に `💡 {hint}` が render される
  - hint = `null` / `undefined` / `''` 時に何も render されない
  - component 自身に `role` 属性が無い (parent `role="alert"` を維持するため)
- 既存 5 site test (assertion 変更のみ、新規追加なし):
  - `getByText('💡 ...')` 形式は維持可能 (component 経由でも render は同等)
  - 必要に応じて `getByTestId` / `queryByText` を component の出力に合わせる

**Docs 更新**:

- `docs/ui-architecture.md` §4 に「`InlineErrorHint` component 規約 (a11y / wrapper class との分離)」を追記

### §5.2 PR 2 (#691): metadataStore catch path lifecycle pinning

**Scope**: `gui/src/state/metadataStore.ts` の 5 catch path × 5 `*ErrorHint` state の clear 範囲を test で pin、規約を docstring で明文化、`load()` catch の partial clear が意図でないなら symmetric 化。

**clear 範囲 matrix** (`(?)` セルは PR 実装時の調査タスク。spec ambiguity ではなく、コード精査前に確定できないため敢えて穴として残す):

| catch path | `loadErrorHint` | `applyErrorHint` | `restoreErrorHint` | `draftSaveErrorHint` | `draftLoadErrorHint` |
| --- | --- | --- | --- | --- | --- |
| `load()` catch | clear (自) | `(?)` 調査 | `(?)` 調査 | clear (他) | clear (他) |
| `runApply()` catch | — | set (自) | — | — | — |
| `restore()` catch | — | — | set (自) | — | — |
| `saveDraft()` catch | — | — | — | set (自) | — |
| `loadDraft()` catch | — | — | — | — | set (自) |
| `clear()` lifecycle 終端 | null | null | null | null | null |
| `loadSample()` lifecycle 終端 | null | null | null | null | null |

PR 2 実装時に `metadataStore.ts` を精査し `(?)` 2 セルを確定する (推測: 現状 `load()` は `applyErrorHint` / `restoreErrorHint` を **clear しない** — partial clear はそれが既存挙動だった `loadError` / `draftSaveErrorHint` / `draftLoadErrorHint` のみ。確定値はコード読みで確認後 PR 本文に記載)。

**判定方針** (PR 内で実装時に決定):

- 案 X: `load()` catch path の他経路 clear を **削除** (symmetric 化、各 catch は自身の hint のみ touch)
- 案 Y: `load()` catch path の他経路 clear を **維持**、根拠コメントを追加 (「load 失敗時は他経路の旧 error も陳腐化と見なす」等の根拠を明文化)

PR 内では現状コードを精査し、PR comment で Idios に AskUserQuestion で案 X / Y を確認。

**Test 追加** (`metadataStore.test.ts` 6-8 件):

- 5 catch path 各々で、自身の `*ErrorHint` が set + 他経路の `*ErrorHint` の保持/clear を pin
- `clear()` で全 `*ErrorHint` が null reset されることを pin
- `loadSample()` で全 `*ErrorHint` が null reset されることを pin

**Docs 更新**:

- `docs/ui-architecture.md` §4 に「metadataStore `*ErrorHint` lifecycle 規約 (catch path は自身のみ touch、終端 cleanup でのみ全 reset)」を追記
- `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` §7 に Lane V Phase 1 lifecycle pinning の Refs リンク追加

### §5.3 PR 3 (#695): ConflictModal AppError hint 表示 (C 案 採用)

**Store 変更** (`gui/src/state/metadataStore.ts`):

- 新 state `conflictErrorHint: string | null` を追加 (`conflictError: string | null` と pair)
- `runApply()` の `state.mtime_conflict` catch path で `appErrorHint(e)` から hint を取り出して set
- `dismissConflict()` / `applyOverwrite()` / `reloadAfterConflict()` の lifecycle で `conflictErrorHint` も併せて null reset

**UI 変更** (`gui/src/components/ConflictModal.tsx`):

```tsx
// Before (PR #689 後の現状)
<p className={styles.message}>{conflictError}</p>
<p className={styles.hint}>「上書き」で外部変更を破棄し...「キャンセル」で何もせずこのモーダルを閉じます。</p>

// After (PR 3 で変更)
<p className={styles.message}>{conflictError}</p>
<InlineErrorHint hint={conflictErrorHint} />
<p className={styles.cancelHint}>「キャンセル」で何もせずこのモーダルを閉じます。</p>
```

`conflictErrorHint` が null の場合 (legacy path や hint 未登録の将来 code) は補足 1 行のみ表示。

**CSS 変更** (`gui/src/components/ConflictModal.module.css`):

- 既存 `.hint` class を `.cancelHint` にリネーム (役割の変化を反映)
- スタイル維持 (`font-family: var(--ae-font-body)` / `font-size: 12px` / `color: var(--ae-text-dim)` / `margin: 0 0 20px 0`)
- InlineErrorHint との縦間隔調整が必要なら追加調整 (実装時に判断)

**Test 変更** (`ConflictModal.test.tsx` 3-4 件):

- 新規: `state.mtime_conflict` 発火時に `conflictErrorHint` が set され、`<InlineErrorHint>` 経由で render
- 新規: `conflictErrorHint` null 時に hint 行は非表示、補足 1 行のみ表示
- 新規: 補足 1 行「『キャンセル』で何もせずこのモーダルを閉じます。」が常に表示
- 削除: 既存 compose hint 「『上書き』で...『リロード』で...」全文を期待する assertion (compose hint 削除に伴い)
- a11y: jest-axe で `role="dialog"` 内側の hint structure に violation なし

**Docs 更新**:

- `docs/ui-interaction-spec.md` §1.5 に「modal hint slot は AppError hint 主 + modal 局所文言 (state.mtime_conflict は キャンセル 補足 1 行) の規約」を追記

### §5.4 PR 4 (#697): DraftRestoreModal `draftLoadErrorHint` UI 追加

**Store 変更**: なし (`draftLoadErrorHint` state は PR #689 Phase 3 で既に追加済)

**UI 変更** (`gui/src/components/DraftRestoreModal.tsx`):

```tsx
const draftLoadErrorHint = useMetadataStore((s) => s.draftLoadErrorHint);
// ...
{draftLoadError && (
  <div className={styles.errorBlock} role="alert">
    <span className={styles.errorMessage}>{draftLoadError}</span>
    <InlineErrorHint hint={draftLoadErrorHint} />
  </div>
)}
```

Phase 4 既存パターン (5 screen + RestoreButton) と同構造。

**CSS 変更** (`gui/src/components/DraftRestoreModal.module.css`):

- 既存 `draftLoadError` inline 表示の wrapper を `role="alert"` 化 (まだなら)
- InlineErrorHint との縦間隔 (`gap: 4px` 程度) を追加

**Test 変更** (`DraftRestoreModal.test.tsx` 2-3 件):

- 新規: `draftLoadErrorHint` set 時に hint render
- 新規: `draftLoadErrorHint` null 時に hint 非表示
- a11y: `role="dialog"` 内側の `role="alert"` nest が jest-axe violation なし

### §5.5 PR 5 (#698): DropScreen recentStore notice 表示 (A-minimal)

**Store 変更**: なし (`recentStore.loadError` / `addError` / `loadErrorHint` / `addErrorHint` は PR #689 Phase 3 で既に追加済)

**UI 変更** (`gui/src/screens/DropScreen.tsx`):

```tsx
const recentLoadError = useRecentStore((s) => s.loadError);
const recentLoadHint = useRecentStore((s) => s.loadErrorHint);
const recentAddError = useRecentStore((s) => s.addError);
const recentAddHint = useRecentStore((s) => s.addErrorHint);

// recent list セクション上部
{(recentLoadError || recentAddError) && (
  <div className={styles.recentNotice} role="alert">
    <span className={styles.recentNoticeMessage}>{recentLoadError ?? recentAddError}</span>
    <InlineErrorHint hint={recentLoadError ? recentLoadHint : recentAddHint} />
  </div>
)}
```

優先順位: `loadError` > `addError` (load 失敗は user が「履歴が出ない」と気づきやすい / add 失敗は補助操作の失敗で次回起動時に再 load される)。

**CSS 変更** (`gui/src/screens/DropScreen.module.css`):

- `.recentNotice`: コンテナ — `padding: 8px 12px` / `border-left: 2px solid var(--ae-danger)` / `margin-bottom: 8px` / `display: flex` / `flex-direction: column` / `gap: 4px`
- `.recentNoticeMessage`: 1 行目 — `color: var(--ae-danger)` / `font-size: 11px` / `font-family: var(--ae-font-mono)` / `word-break: break-all`
- (hint 2 行目は InlineErrorHint 内側のスタイル)

**Docstring 更新** (`gui/src/state/recentStore.ts`):

- 既存「history は best-effort UI fluff」「DropScreen は it [loadError] を ignore する」を update
- 「best-effort 設計だが、user に履歴失敗を気づかせるため DropScreen 上部に inline notice として表示する。dismiss なし、次回 load 成功で自動消去」に書き換え

**Test 変更** (`DropScreen.test.tsx` 4-5 件):

- 新規: `loadError` set 時に notice 表示 / hint も render
- 新規: `addError` set 時に notice 表示 / hint も render
- 新規: `loadError` + `addError` 両方 set 時に loadError 優先
- 新規: 両方 null 時に notice 非表示
- a11y: `role="alert"` + jest-axe violation なし

**Lane II-a #633 との衝突回避**: DropScreen 共有 (sample mode 全画面 read-only 化と本 #698 notice 表示が同 file)。先着優先 + rebase で吸収 (roadmap §3-bis 規約)。

## §6 Test 戦略 / Iron Law 整合

### §6.1 TDD 規律 (HARD-GATE)

`superpowers:test-driven-development` HARD-GATE 適用。全 5 PR で Red→Green→Refactor を遵守:

- 各 PR で production code を書く前に failing test を先に書く
- #693 は最も小さい component なので TDD 適用が容易
- #691 は test 追加そのものが scope の中心
- #695 / #697 / #698 は a11y + render test を先に書いてから UI 実装

### §6.2 新規 test 件数の見込み

| PR | 新規 test 件数 | 主な観点 |
| --- | --- | --- |
| #693 | 3-4 | InlineErrorHint render / null 非表示 / a11y (role 重複なし) |
| #691 | 6-8 | 5 catch path × clear matrix + clear() / loadSample() 終端 reset |
| #695 | 3-4 | hint set/null / 補足 1 行常時表示 / a11y |
| #697 | 2-3 | hint set/null / a11y |
| #698 | 4-5 | loadError / addError / 優先順位 / 非表示 / a11y |

合計新規 **18-24 件**。既存 ~605 件に積み増し、全 pass を維持。

### §6.3 自動チェック (Iron Law 6 PR Pre-flight)

各 PR で実施:

- `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` (取り込み未済 commit 確認)
- 当 PR の touched files と交差するなら `git merge origin/develop-0.2.0`
- `gh pr list --search "<元 issue#>" --state all` (並行 worktree PR 重複確認)
- `cd gui && npm run lint` (exit 0)
- `cd gui && npm run typecheck` (exit 0)
- `cd gui && npm test -- --run` (全 pass)
- `cd gui && npm run build` (success)
- `cd gui/src-tauri && cargo check` (本 spec は Rust 変更なしを想定、regression なし確認)
- `cd gui/src-tauri && cargo test --lib` (156 件 baseline 維持)
- `bash scripts/check-markdownlint.sh` (#691 #693 #695 #698 で docs 更新時)
- (Python 変更なしのため `ruff` / `pyright` / `pytest` は本 spec scope 外、ただし pre-flight として一応 pass 確認)

### §6.4 Iron Law 6 実機検証 trigger

| PR | 実機検証要否 | 検証経路 |
| --- | --- | --- |
| #693 | 推奨 | 既存 5 site の hint 表示が retained (PreviewScreen apply error / DropScreen load error 等を発火) |
| #691 | 不要 | 機能変更なし (lifecycle pinning のみ)、frontend mock test で十分 |
| #695 | 必須 | 実 conflict (2 プロセス同時 edit → apply) で modal の AppError hint + 補足 1 行表示 |
| #697 | 推奨 | 破損 draft で DraftRestoreModal の hint 表示 |
| #698 | 推奨 | recent.json 破損 / 削除で DropScreen 上部 notice 表示 |

PR 作成時に `AskUserQuestion` で Idios に依頼。

### §6.5 CI 8 job 整合

5 PR すべてで全 8 job (gui-rust / gui-frontend / build-windows / installer-pester / python / markdownlint / validate-checklist / version-check) を pass する想定:

- `gui-frontend`: 各 PR の主戦場、必ず pass
- `gui-rust`: Rust 変更なしを想定だが regression check 必須
- `build-windows`: 既存 build 維持
- `markdownlint`: docs 更新 PR (#691 / #693 / #695 / #698) で関係
- `python` / `installer-pester` / `version-check`: 影響なし、pass 維持

### §6.6 Iron Law 1〜6 整合

- **Iron Law 1**: 各 issue body の受け入れ条件を PR 本文で逐条引用 + diff/test 引用 (`/enforce-acceptance-criteria` skill を `/review-pr` 時に必ず呼ぶ)
- **Iron Law 2**: 本 spec は 5 件の brainstorming 設計のため bulk operation は無し。merge 時の close は `/close-issue` skill で個別実施
- **Iron Law 3**: 1 PR = 1 issue 厳守、scope creep 検知時は `scope-guard` skill
- **Iron Law 4**: PR / commit に Closes/Fixes 禁止、`Refs #<num>` のみ。merge 後 `/close-issue` で実測再検証
- **Iron Law 5**: §5.2 PR 2 #691 の symmetric 化案 X / Y の判断は PR 内で `AskUserQuestion` 実施
- **Iron Law 6**: §6.3 / §6.4 で全 PR に適用

## §7 関連 doc

- [docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md](../plans/2026-05-11-l2-v020-roadmap-update.md) §Group I — 親 plan
- [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](2026-05-08-l2-appError-migration-completion-design.md) §3 / §7 — PR #689 起点 spec、本 spec は §3 scope 外項目を消化
- [docs/ui-architecture.md](../../ui-architecture.md) §4 — 各 PR で更新 (lifecycle 規約 / InlineErrorHint 規約)
- [docs/ui-interaction-spec.md](../../ui-interaction-spec.md) §1.5 — #695 で更新 (modal hint slot 規約)
- [docs/tauri-commands.md](../../tauri-commands.md) — AppError default hint mapping (PR #689 で導入済、本 spec では変更なし)
- [docs/l2-workflow.md](../../l2-workflow.md) §PR 作成 Pre-flight / §Self-Test Report 規約 / §(A) PR 内修正優先 / §実機検証 trigger 表 — 全 PR で適用
- [docs/a11y-policy.md](../../a11y-policy.md) — InlineErrorHint の role 規約 (consumer 側 `role="alert"` 内側に配置) は本 doc と整合

## §8 受け入れ条件 (per-PR breakdown)

### §8.1 PR 1 (#693) 受け入れ条件

- [ ] `gui/src/components/InlineErrorHint.tsx` が新設され、props `hint: string | null | undefined` を取る
- [ ] `gui/src/components/InlineErrorHint.module.css` が新設され、`.hint` class が `var(--ae-text-dim)` / `font-size: 11px` 規約
- [ ] `gui/src/components/InlineErrorHint.test.tsx` が新規 3-4 件 (set / null / a11y) で pass
- [ ] 既存 5 site (RestoreButton / DropScreen / DetectingScreen / PreviewScreen / ExportScreen) が `<InlineErrorHint>` 経由に refactor
- [ ] 既存 5 site の test が全 pass (assertion 変更のみ)
- [ ] `docs/ui-architecture.md` §4 に InlineErrorHint 規約節を追記
- [ ] Iron Law 6 自動チェック (lint / typecheck / test / build / cargo check / markdownlint) 全 pass
- [ ] Iron Law 6 実機検証 (既存 5 site hint retained) を Idios PR comment で PASS 確認

### §8.2 PR 2 (#691) 受け入れ条件

- [ ] `gui/src/state/metadataStore.ts` の 5 catch path の clear 範囲が PR 内で精査され、案 X (symmetric 化) / 案 Y (非対称維持 + 根拠コメント) のいずれかが採用される
- [ ] `gui/src/state/metadataStore.test.ts` に 6-8 件の lifecycle pinning test が追加され全 pass
- [ ] `docs/ui-architecture.md` §4 に lifecycle 規約節を追記
- [ ] `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` §7 に本 PR の Refs リンク追加
- [ ] Iron Law 6 自動チェック全 pass
- [ ] (実機検証は不要、PR 本文に skip 根拠明記)

### §8.3 PR 3 (#695) 受け入れ条件

- [ ] `gui/src/state/metadataStore.ts` に `conflictErrorHint: string | null` state が追加され、`runApply()` の conflict catch path で set / lifecycle 終端で null reset
- [ ] `gui/src/components/ConflictModal.tsx` の compose hint が削除され、`<InlineErrorHint hint={conflictErrorHint} />` + 「キャンセル」補足 1 行に置換
- [ ] `gui/src/components/ConflictModal.module.css` の `.hint` が `.cancelHint` にリネーム
- [ ] `gui/src/components/ConflictModal.test.tsx` に 3-4 件の test が追加 (hint set/null / 補足常時 / a11y) + 旧 compose hint assertion 削除
- [ ] `docs/ui-interaction-spec.md` §1.5 に modal hint slot 規約節を追記
- [ ] Iron Law 6 自動チェック全 pass
- [ ] Iron Law 6 実機検証 (実 conflict で modal hint 表示) を Idios PR comment で PASS 確認

### §8.4 PR 4 (#697) 受け入れ条件

- [ ] `gui/src/components/DraftRestoreModal.tsx` で `draftLoadErrorHint` を read し、`<InlineErrorHint>` 経由で表示
- [ ] `gui/src/components/DraftRestoreModal.module.css` で必要なら wrapper class を追加
- [ ] `gui/src/components/DraftRestoreModal.test.tsx` に 2-3 件の test 追加 (hint set/null / a11y)
- [ ] Iron Law 6 自動チェック全 pass
- [ ] Iron Law 6 実機検証 (破損 draft で hint 表示) を Idios PR comment で PASS 確認

### §8.5 PR 5 (#698) 受け入れ条件

- [ ] `gui/src/screens/DropScreen.tsx` の recent list セクション上部に inline notice (loadError 優先、両方 null なら非表示) を追加
- [ ] notice は error message (1 行目) + `<InlineErrorHint>` (2 行目) の 2 行構造、`role="alert"`
- [ ] `gui/src/screens/DropScreen.module.css` に `.recentNotice` / `.recentNoticeMessage` class 追加
- [ ] `gui/src/state/recentStore.ts` の docstring が「user に notice 告知する」設計に update
- [ ] `gui/src/screens/DropScreen.test.tsx` に 4-5 件の test 追加 (loadError / addError / 優先順位 / 非表示 / a11y)
- [ ] Lane II-a #633 との rebase 順序合意 (先着優先 + rebase) を PR 本文に明記
- [ ] Iron Law 6 自動チェック全 pass
- [ ] Iron Law 6 実機検証 (recent.json 破損 / 削除で notice 表示) を Idios PR comment で PASS 確認

## §9 リスク表

| リスク | 影響 | 緩和策 |
| --- | --- | --- |
| InlineErrorHint の wrapper class 設計が不十分で site-specific overflow 制御を失う | PreviewScreen / ExportScreen で長い hint が truncate される | PR 1 の test で 5 既存 site の hint 長文 case (>100 chars) を必ず含める、wrapper class 維持を docstring で明文化 |
| #691 案 X (symmetric 化) で挙動変更が partial だと既存 test が壊れる | 既存 lifecycle 期待値が変わり regression | PR 2 で先に既存挙動を test で pin (Red)、symmetric 化 (Green)、最後に refactor で記述整理 |
| #695 conflict modal で AppError hint が null (legacy path) のケースで補足 1 行のみだと UX 弱化 | hint 未登録の将来 code で modal が情報不足 | PR 3 で `conflictErrorHint` null 時の挙動を test で pin、必要なら fallback message を考慮 (本 spec では `state.mtime_conflict` は必ず hint 持ちのため null path は将来枠) |
| Lane II-a #633 と #698 の DropScreen 衝突 | merge 順序によって片方が rebase 失敗 | 「先着優先 + rebase」運用、両 lane の作業者間で PR 提出順を事前合意 |
| #693 先行 merge が遅延すると PR 2-5 の base sync コスト増 | PR 2-5 で `git merge develop-0.2.0` を複数回繰り返す | PR 1 は単純な component 新設のみで scope 小、merge 迅速化を優先 |
| Phase 2 #694 で `*ErrorHint` 並列構造が unified state に refactor される | 本 spec で追加した `conflictErrorHint` state も再 refactor | 本 spec は Phase 1 として `*ErrorHint` 並列構造を継承、Phase 2 で `conflictErrorHint` も含めて一括 refactor (本 spec の choice は future-proof) |

## §10 Open questions (PR 内で AskUserQuestion 実施)

- §5.2 PR 2 #691: `load()` catch path の partial clear を symmetric 化 (案 X) するか、非対称維持 + 根拠コメント (案 Y) するか
- §5.5 PR 5 #698: Lane II-a #633 (DropScreen sample read-only) との PR 提出順を Idios がどう判断するか (先着優先の合意確認)
- §6.4 各 PR 実機検証経路の妥当性を PR 作成時に Idios PR comment で再確認

## §11 採用方針サマリ (brainstorming Q&A trace)

| 決定 | 採用 | 棄却 | 理由 |
| --- | --- | --- | --- |
| PR 戦略 (Q1) | 5 PR 並行 | 1 PR 統合 / 2 PR 段階 / Phase 1 細分化 | Iron Law 3 厳守、file 完全独立、独立レビュー可能 |
| #693 手法 (Q2) | InlineErrorHint component 新設 | CSS-only / hybrid | i18n / a11y 制御の明示性、consumer 1 行化、issue body 推奨と整合 |
| #695 hint layout (Q3) | C: AppError hint 主 + 「キャンセル」補足 1 行 | A 2 段 / B 完全置換 / D 現状維持 | 情報損失なし、重複最小、source-of-truth は error.rs に一元化、補足 1 行は modal 局所役割明確 |
| #698 strategy (Q4) | A-minimal: recent list 上部 inline notice | A-dismissable banner / B revert / A+B partial | best-effort tone 維持しつつ user に履歴失敗を告知、Phase 4 規約と一貫、dismiss なしで簡素 |
| Merge 順序 (Q5) | #693 先行 → component consumer 3 PR (#695 #697 #698) が rebase で取り込み。#691 は UI 非依存のため完全並行 (Q5 採用案を §4 で精緻化) | 完全独立 (#693 最後 sweep) / 完全独立 (Phase 2 sweep) | cleanest code state、refactor debt ゼロ、Iron Law 6 base sync と整合 |

---

**brainstorming 完了**。本 spec を起点に `writing-plans` skill で実装計画を策定する。
