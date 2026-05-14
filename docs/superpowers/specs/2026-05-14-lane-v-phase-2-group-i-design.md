# L2 Lane V Phase 2: Group I `*ErrorState` unified refactor 設計

> **Status**: v0.2.0 リリースゲート Lane V Phase 2 (Group I の Phase 2)
> **Scope**: 1 PR (1 spec / 1 章) — [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694)
> **session**: `romantic-mccarthy-6c34fd` (2026-05-14 brainstorming、Idios + Claude Opus 4.7)
> **依存元 PR**: [#714](https://github.com/Idios/kobutachan-allaganeye/pull/714) / [#716](https://github.com/Idios/kobutachan-allaganeye/pull/716) / [#725](https://github.com/Idios/kobutachan-allaganeye/pull/725) / [#730](https://github.com/Idios/kobutachan-allaganeye/pull/730) / [#733](https://github.com/Idios/kobutachan-allaganeye/pull/733) (Lane V Phase 1、5/5 MERGED)
> **親 plan**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md](../plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md) §Group I (Phase 2-3)

## §0 関連 issue / PR の状態整理

| 参照先 | 状態 | 本 spec への関与 |
| --- | --- | --- |
| [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) | OPEN | **本 PR で完遂** (`*ErrorState: ErrorState \| null` unified refactor) |
| [#663](https://github.com/Idios/kobutachan-allaganeye/issues/663) | CLOSED (PR #689 merged) | AppError migration 起点 issue、本 spec は #663 + Phase 1 を受けた仕上げ |
| [#691](https://github.com/Idios/kobutachan-allaganeye/issues/691) | CLOSED (PR #714 merged) | metadataStore catch path lifecycle pinning、本 spec で `*ErrorState` 化を継承 |
| [#693](https://github.com/Idios/kobutachan-allaganeye/issues/693) | CLOSED (PR #716 merged) | InlineErrorHint component 新設、本 spec で API 不変のまま consumer 移行 |
| [#695](https://github.com/Idios/kobutachan-allaganeye/issues/695) | CLOSED (PR #725 merged) | ConflictModal AppError hint 表示、`conflictError` / `conflictErrorHint` pair が追加 (Issue #694 body は本 PR より前の記述で 5 pair としているが現在 6 pair) |
| [#697](https://github.com/Idios/kobutachan-allaganeye/issues/697) | CLOSED (PR #730 merged) | DraftRestoreModal hint UI 追加、本 spec で `draftLoadErrorState` 経由に切替 |
| [#698](https://github.com/Idios/kobutachan-allaganeye/issues/698) | CLOSED (PR #733 merged) | DropScreen recentStore notice 表示、本 spec で `loadErrorState` / `addErrorState` 経由に切替 |
| [#699](https://github.com/Idios/kobutachan-allaganeye/issues/699) | OPEN (Phase 3 へ) | AppError 関連 stale docstring 更新、本 PR merge 後着手 |

## §1 Background — Phase 1 で完備された hint UI 規約と並列構造の問題

Phase 1 (PR #714 / #716 / #725 / #730 / #733) の完了で以下が確立されている:

- `gui/src/lib/appError.ts` の helper (`appErrorMessage` / `appErrorHint` / `appErrorCodeIs` / `isAppError`)
- `gui/src/components/InlineErrorHint.tsx` (hint UI 共通 component、`hint: string \| null \| undefined`)
- `gui/src/state/metadataStore.ts` の **6 pair = 12 field** (`loadError` / `loadErrorHint`、`applyError` / `applyErrorHint`、`restoreError` / `restoreErrorHint`、`conflictError` / `conflictErrorHint`、`draftSaveError` / `draftSaveErrorHint`、`draftLoadError` / `draftLoadErrorHint`)
- `gui/src/state/recentStore.ts` の **2 pair = 4 field** (`loadError` / `loadErrorHint`、`addError` / `addErrorHint`)
- 8 consumer site (5 screen + 3 modal/component) で `InlineErrorHint` 経由の 2 行表示
- metadataStore lifecycle 規約 (catch path self-only、終端 clear / loadSample で全 reset、`load()` catch のみ `conflictError` / `conflictErrorHint` を file-state リセットの一部として touch — #691 案 X + #695 file-state 例外)

並列構造の問題点 ([#694](https://github.com/Idios/kobutachan-allaganeye/issues/694) body より):

- 1 つの error context (例: load 失敗) に対し 2 state field を同時に管理する必要があり、catch / success / clear の各 path で 2 set/clear が必要
- `*Error` と `*ErrorHint` の lifecycle 同期は規約レベル管理で型レベルで保証されない (片方 set し忘れる risk)
- AppError の `code` field は frontend に届いているが state field に保存されていない (将来 `error.code` を condition logic に使うとき再 parse 必要)

## §2 Goals

1. `metadataStore` 6 pair + `recentStore` 2 pair の `*Error` / `*ErrorHint` 並列 16 field を 8 個の `*ErrorState: ErrorState \| null` field に集約し、pair atomicity 規約を型レベルで保証する
2. `gui/src/lib/appError.ts` に `ErrorState` interface + `toErrorState(e: unknown): ErrorState` helper を追加、catch path を 1 行 set に簡素化する
3. `appErrorMessage` / `appErrorHint` 削除、`appErrorCodeIs` / `isAppError` 維持 (catch path 内 if 分岐の readability 確保)
4. AppError の `code` を state に保存し、将来の `error.code` ベース branching を再 parse 不要にする (`ErrorState.code: string \| null`、legacy raw String / Error instance の場合 `null`)
5. Phase 1 で確立した consumer 規約 (`InlineErrorHint` API / `role="alert"` wrapper / site-specific overflow 制御の wrapper class) を完全継承し、UI 表示挙動の regression をゼロにする
6. Iron Law 1〜6 厳守 (1 PR = 1 issue / `Refs #694` / PR Pre-flight Step 0-4 / Self-Test Report)

## §3 Non-goals (scope 外明記)

- **ErrorModal (#614) / globalErrorListener.ts の AppError 統合**: Lane II-b' Group D #696 で扱う
- **AppError 関連 stale docstring 更新 (#699 / Phase 3)**: 本 PR では `appErrorMessage` / `appErrorHint` 削除に伴う docstring の整合のみ実施 (`appError.ts:57-62` 等)。Rust 側 `error.rs:28-34` 含む残りは #699 で扱う
- **recentStore catch path symmetry refactor**: 別 issue で reservation 済 (Issue #694 body §「スコープ外」)
- **新規 Tauri command の追加 / 削除**: 本 PR は frontend のみ
- **Rust 側 `AppError` struct の変更** (`stacktrace` 含む): inline error 用途では `stacktrace` を運ばない方針 (将来 ErrorModal 経路で扱う)
- **自動 telemetry / Sentry crash reporter 統合**: v0.2.0 外
- **i18n フレームワーク導入**: 別 issue
- **`InlineErrorHint` の API 変更**: hint prop `string \| null \| undefined` を不変、`💡` prefix とスタイル規約も不変

## §4 Architecture (1 atomic PR / 4 commit 推奨構成)

Iron Law 3 (1 PR = 1 issue) と整合させるため **1 atomic PR** で完遂する。Diff は ~30 file / ~500 LOC 規模で大きいが、commit を意味単位に分けて review 可能性を確保する。

```text
═══════════════════════════════════════════════════════════════════════════
SINGLE PR (1/1)  —  Issue #694, Lane V Phase 2
═══════════════════════════════════════════════════════════════════════════
  commit 1: gui/src/lib/appError.{ts,test.ts}
            → ErrorState interface + toErrorState 追加
            → appErrorMessage / appErrorHint 削除
            → test 移行 (3-4 件追加、既存対応削除)
  commit 2: gui/src/state/metadataStore.{ts,test.ts}
            → 6 pair → 6 *ErrorState
            → catch path / lifecycle / clear / loadSample / dismissConflict /
              reloadAfterConflict 全 path 移行
            → lifecycle pinning test (#691 PR #714 由来) を *ErrorState 形に書換
  commit 3: gui/src/state/recentStore.{ts,test.ts}
            → 2 pair → 2 *ErrorState
            → catch path / lifecycle / clear / reset 移行
  commit 4: gui/src/components/*.tsx + gui/src/screens/*.tsx + 各 .test.tsx
            → 5 store-level consumer (RestoreButton / ConflictModal / DraftRestoreModal /
              DropScreen recent notice / PreviewScreen applyError) の selector 移行
            → 7 file (metadataStore / recentStore は commit 2-3 で対応済、DetectingScreen /
              DropScreen / ExportScreen / PreviewScreen / ConfirmExitModal) で
              appErrorMessage / appErrorHint callsite を toErrorState 経由に migration
            → appErrorMessage / appErrorHint helper 削除 + appError.ts / .test.ts 整理
            → InlineErrorHint API 不変、consumer wrapper class 維持
            → flow.integration.test.tsx に assertion 変更があれば更新 (現状 store error 参照なし)
            → docs/ui-architecture.md §4 lifecycle 規約更新
            → docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md §7 に Phase 2 Refs 追加
```

## §5 詳細設計

### §5.1 `ErrorState` interface + `toErrorState` helper (`gui/src/lib/appError.ts`)

```ts
export interface AppError {
  code: string;
  message: string;
  hint?: string;
  stacktrace?: string;
}

/**
 * Store の inline error slot に詰める正規化済み構造。AppError と異なり:
 * - `hint` / `code` は legacy raw String や `Error` instance では `null`
 * - `stacktrace` は inline UI 用途では運ばない (ErrorModal 等の別経路で扱う)
 */
export interface ErrorState {
  message: string;
  hint: string | null;
  code: string | null;
}

export function isAppError(e: unknown): e is AppError {
  if (typeof e !== 'object' || e === null) return false;
  const obj = e as Record<string, unknown>;
  return typeof obj.code === 'string' && typeof obj.message === 'string';
}

export function appErrorCodeIs(e: unknown, expected: string): boolean {
  return isAppError(e) && e.code === expected;
}

/**
 * invoke の reject value (AppError / Error / raw String) を ErrorState に正規化。
 * catch path で `set({ loadErrorState: toErrorState(e) })` の 1 行で完結する。
 */
export function toErrorState(e: unknown): ErrorState {
  if (isAppError(e)) {
    return {
      message: e.message,
      hint: typeof e.hint === 'string' ? e.hint : null,
      code: e.code,
    };
  }
  if (e instanceof Error) {
    return { message: e.message, hint: null, code: null };
  }
  return { message: String(e), hint: null, code: null };
}

// 削除: appErrorMessage / appErrorHint
```

### §5.2 `metadataStore.ts` 変更

State interface の 12 個の `*Error` / `*ErrorHint` field を 6 個の `*ErrorState: ErrorState \| null` に集約:

```ts
export interface MetadataState {
  metadata: Metadata | null;
  filePath: string | null;
  dirty: boolean;
  loadErrorState: ErrorState | null;         // was: loadError + loadErrorHint
  applying: boolean;
  applyErrorState: ErrorState | null;        // was: applyError + applyErrorHint

  hasBackup: boolean;
  restoring: boolean;
  restoreErrorState: ErrorState | null;      // was: restoreError + restoreErrorHint

  loadedMtimeMs: number | null;
  conflictErrorState: ErrorState | null;     // was: conflictError + conflictErrorHint
  pendingDraft: Metadata | null;
  draftLoadErrorState: ErrorState | null;    // was: draftLoadError + draftLoadErrorHint
  draftSaving: boolean;
  draftSaveErrorState: ErrorState | null;    // was: draftSaveError + draftSaveErrorHint

  // action signatures は不変
  load: (path: string) => Promise<void>;
  // ... 既存 action API
}
```

catch path の代表例 (`runApply`):

```ts
async function runApply(overwrite: boolean): Promise<void> {
  const { metadata, filePath, loadedMtimeMs } = get();
  if (!metadata || !filePath) return;
  set({ applying: true, applyErrorState: null, conflictErrorState: null });
  try {
    const normalized = normalizeForPersistence(metadata);
    const newMtime = await invoke<number>('apply_changes', {
      path: filePath,
      metadata: normalized,
      expectedMtimeMs: overwrite ? null : loadedMtimeMs,
    });
    set({
      metadata: normalized,
      dirty: false,
      applying: false,
      applyErrorState: null,
      loadedMtimeMs: newMtime,
      conflictErrorState: null,
    });
    await get().refreshBackupStatus();
    cancelDraftSave();
    await get().clearDraft();
  } catch (e) {
    const errorState = toErrorState(e);
    if (appErrorCodeIs(e, 'state.mtime_conflict')) {
      set({ applying: false, conflictErrorState: errorState });
    } else {
      set({ applying: false, applyErrorState: errorState });
    }
  }
}
```

`load()` catch path (Phase 1 #691 案 X + #695 file-state 例外を継承):

```ts
load: async (path) => {
  try {
    const raw = await invoke<unknown>('load_metadata', { path });
    const parsed = MetadataSchema.parse(raw);
    const mtime = await invoke<number | null>('get_metadata_mtime', { path });
    set({
      metadata: parsed as unknown as Metadata,
      filePath: path,
      dirty: false,
      loadErrorState: null,
      applyErrorState: null,
      restoreErrorState: null,
      loadedMtimeMs: mtime ?? null,
      conflictErrorState: null,
      pendingDraft: null,
      draftLoadErrorState: null,
      draftSaveErrorState: null,
    });
    await get().refreshBackupStatus();
    await get().loadDraft();
  } catch (e) {
    // #691 案 X 継承: catch path は self-only (loadErrorState のみ set)。
    // apply / restore / draft 系の旧 errorState は別経路の文脈なので保持する。
    // #695 file-state 例外: conflictErrorState は file-state リセットの一部として touch。
    set({
      metadata: null,
      filePath: null,
      dirty: false,
      loadErrorState: toErrorState(e),
      hasBackup: false,
      loadedMtimeMs: null,
      conflictErrorState: null,
      pendingDraft: null,
    });
  }
},
```

その他の path (`restore` / `saveDraft` / `loadDraft` / `clear` / `loadSample` / `dismissConflict` / `reloadAfterConflict` / `applyOverwrite`) も同 pattern。詳細は §5.4 lifecycle matrix を参照。

### §5.3 `recentStore.ts` 変更

```ts
export interface RecentState {
  entries: RecentEntry[];
  loaded: boolean;
  loadErrorState: ErrorState | null;       // was: loadError + loadErrorHint
  addErrorState: ErrorState | null;        // was: addError + addErrorHint

  load: () => Promise<void>;
  add: (path: string) => Promise<void>;
  clear: () => Promise<void>;
  reset: () => void;
}

async load() {
  try {
    const result = await invoke<unknown>('read_recent');
    const entries: RecentEntry[] = Array.isArray(result)
      ? (result as RecentEntry[])
      : [];
    set({ entries, loaded: true, loadErrorState: null });
  } catch (e) {
    set({ loadErrorState: toErrorState(e), loaded: true });
  }
},

async add(path) {
  try {
    const result = await invoke<unknown>('add_recent', { path });
    const entries: RecentEntry[] = Array.isArray(result)
      ? (result as RecentEntry[])
      : [];
    set({ entries, addErrorState: null });
  } catch (e) {
    set({ addErrorState: toErrorState(e) });
  }
},

async clear() {
  await invoke<void>('clear_recent');
  set({ entries: [], loadErrorState: null, addErrorState: null });
},

reset() {
  set({ entries: [], loaded: false, loadErrorState: null, addErrorState: null });
},
```

### §5.4 metadataStore lifecycle matrix (catch / success / 終端)

下表で「set」= path 自身が touch、「保持」= touch しない、「null」= 明示的に null reset。Phase 1 PR #714 (#691) で pin した規約をそのまま継承し field 名のみ `*ErrorState` 化。

| path | `loadErrorState` | `applyErrorState` | `restoreErrorState` | `conflictErrorState` | `draftSaveErrorState` | `draftLoadErrorState` | 関連 file-state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `load()` catch | set (自) | 保持 | 保持 | null (file-state) | 保持 | 保持 | clear `pendingDraft` / `loadedMtimeMs` / `hasBackup` |
| `load()` success | null | null | null | null | null | null | reset `pendingDraft` / `loadedMtimeMs` / `hasBackup` (fresh start) |
| `runApply()` 開始 | 保持 | null | 保持 | null | 保持 | 保持 | — |
| `runApply()` catch (`state.mtime_conflict`) | 保持 | 保持 | 保持 | set (自) | 保持 | 保持 | — |
| `runApply()` catch (それ以外) | 保持 | set (自) | 保持 | 保持 | 保持 | 保持 | — |
| `runApply()` success | 保持 | null | 保持 | null | 保持 | 保持 | `loadedMtimeMs` 更新、`clearDraft` |
| `restore()` 開始 | 保持 | 保持 | null | 保持 | 保持 | 保持 | — |
| `restore()` catch | 保持 | 保持 | set (自) | 保持 | 保持 | 保持 | — |
| `restore()` success | (load 経由で全 null) | (load 経由) | (load 経由) | (load 経由) | (load 経由) | (load 経由) | (load 経由) |
| `saveDraft()` 開始 | 保持 | 保持 | 保持 | 保持 | null | 保持 | `draftSaving=true` |
| `saveDraft()` catch | 保持 | 保持 | 保持 | 保持 | set (自) | 保持 | — |
| `saveDraft()` success | 保持 | 保持 | 保持 | 保持 | 保持 (開始時 null 済) | 保持 | `draftSaving=false` |
| `loadDraft()` catch | 保持 | 保持 | 保持 | 保持 | 保持 | set (自) | `pendingDraft=null` |
| `loadDraft()` success (draft あり) | 保持 | 保持 | 保持 | 保持 | 保持 | null | `pendingDraft` set |
| `loadDraft()` success (draft なし) | 保持 | 保持 | 保持 | 保持 | 保持 | null | `pendingDraft=null` |
| `dismissConflict()` | 保持 | 保持 | 保持 | null | 保持 | 保持 | — |
| `reloadAfterConflict()` (no filePath) | 保持 | 保持 | 保持 | null | 保持 | 保持 | — |
| `reloadAfterConflict()` (filePath あり) | (load 経由) | (load 経由) | (load 経由) | (load 経由) | (load 経由) | (load 経由) | (load 経由) |
| `clear()` 終端 | null | null | null | null | null | null | 全 file-state reset |
| `loadSample()` 終端 | null | null | null | null | null | null | sample に reset |

#### recentStore lifecycle matrix

| path | `loadErrorState` | `addErrorState` | 関連 state |
| --- | --- | --- | --- |
| `load()` catch | set (自) | 保持 | `loaded=true` |
| `load()` success | null | 保持 | `entries` 更新、`loaded=true` |
| `add()` catch | 保持 | set (自) | — |
| `add()` success | 保持 | null | `entries` 更新 |
| `clear()` 終端 | null | null | `entries=[]` |
| `reset()` 終端 | null | null | `entries=[]` / `loaded=false` |

### §5.5 Store-level consumer 5 site 変更

実コード調査の結果、store-level `*Error` / `*ErrorHint` を直接 `useMetadataStore` / `useRecentStore` selector で取り出している consumer は **5 site**。残り 3 site (DetectingScreen / ExportScreen / CompleteScreen) は store-level error 表示には参加せず、それぞれ local `useState` (`[error, errorHint]` pair) で error 管理しているため、本 refactor の selector 変更対象外 (§5.6 helper callsite migration には含まれる)。

| site | selector 変更 | 表示変更 |
| --- | --- | --- |
| [DropScreen.tsx](../../../gui/src/screens/DropScreen.tsx) (recent notice) | `useRecentStore` の `loadErrorState` / `addErrorState` (4 selector → 2) | `loadErrorState ?? addErrorState` で優先順位、`state?.message` 1 行目 + `<InlineErrorHint hint={state?.hint ?? null} />` 2 行目 |
| [PreviewScreen.tsx](../../../gui/src/screens/PreviewScreen.tsx) (applyError) | `useMetadataStore` の `applyErrorState` (2 selector → 1) | `state.message` + `<InlineErrorHint hint={state.hint} />` (wrapper class `.applyErrorHint` の `display: block` 維持) |
| [RestoreButton.tsx](../../../gui/src/components/RestoreButton.tsx) | `useMetadataStore` の `restoreErrorState` | `state.message` + `<InlineErrorHint hint={state.hint} />` |
| [ConflictModal.tsx](../../../gui/src/components/ConflictModal.tsx) | `useMetadataStore` の `conflictErrorState` | `state?.message` 1 行目 + `<InlineErrorHint hint={state?.hint ?? null} />` 2 行目 + `.cancelHint` 補足 1 行 (Phase 1 PR #725 layout 継承) |
| [DraftRestoreModal.tsx](../../../gui/src/components/DraftRestoreModal.tsx) | `useMetadataStore` の `draftLoadErrorState` + `conflictError` condition → `conflictErrorState` | `state?.message` + `<InlineErrorHint hint={state?.hint ?? null} />` (Phase 1 PR #730 pattern 継承) |

### §5.6 Helper callsite 7 file migration

`appErrorMessage` / `appErrorHint` 削除に伴い、全 callsite を `toErrorState` 経由に置換する。local `useState` の `[error, errorHint]` pair pattern 自体は touch しない (Iron Law 3 — scope creep 防止、必要なら別 issue として #694 完了後に検討)。

| file | callsite 数 | 変換 pattern |
| --- | --- | --- |
| `gui/src/state/metadataStore.ts` | 5 catch path (load / runApply / restore / saveDraft / loadDraft) | `const s = toErrorState(e); set({ <slot>ErrorState: s })` (conflict 分岐は `appErrorCodeIs(e, ...)` で同様に判定) |
| `gui/src/state/recentStore.ts` | 2 catch path (load / add) | `const s = toErrorState(e); set({ <slot>ErrorState: s, ... })` |
| `gui/src/screens/DetectingScreen.tsx` | 1 onError callsite (`onError(appErrorMessage(e), appErrorHint(e))`) | `const s = toErrorState(e); onError(s.message, s.hint)` (local pair pattern 保持) |
| `gui/src/screens/DropScreen.tsx` | 2 catch path (local useState `setError` / `setErrorHint`) | `const s = toErrorState(e); setError(s.message); setErrorHint(s.hint)` |
| `gui/src/screens/ExportScreen.tsx` | 3 callsite (per-match catch + openFolder catch 含む) | 同 (local pair pattern 保持) |
| `gui/src/screens/PreviewScreen.tsx` | 4 callsite (`setVideoError` / overlayError 表示 / AppError-shape `message: appErrorMessage(e)` 構築 等) | local useState 系は同 pattern、AppError-shape construction (`{ code: 'unknown.error', message: appErrorMessage(e) }`) は `message: toErrorState(e).message` |
| `gui/src/components/ConfirmExitModal.tsx` | 2 catch path (local useState) | 同 |

代表 consumer 例 (PreviewScreen `applyError`):

**Before**:

```tsx
const applyError = useMetadataStore((s) => s.applyError);
const applyErrorHint = useMetadataStore((s) => s.applyErrorHint);
// ...
{applyError && (
  <div className={styles.applyErrorBox} role="alert">
    <span className={styles.applyErrorMessage}>{applyError}</span>
    <span className={styles.applyErrorHint}>
      <InlineErrorHint hint={applyErrorHint} />
    </span>
  </div>
)}
```

**After**:

```tsx
const applyErrorState = useMetadataStore((s) => s.applyErrorState);
// ...
{applyErrorState && (
  <div className={styles.applyErrorBox} role="alert">
    <span className={styles.applyErrorMessage}>{applyErrorState.message}</span>
    <span className={styles.applyErrorHint}>
      <InlineErrorHint hint={applyErrorState.hint} />
    </span>
  </div>
)}
```

selector が 2 → 1 になり、null check が atomic になる。CSS / wrapper class は不変。

## §6 Test 戦略 / Iron Law 整合

### §6.1 TDD 規律 (HARD-GATE)

`superpowers:test-driven-development` HARD-GATE 適用。Red-Green-Refactor 順:

1. **Red phase**: 既存 test の field 名を新 ErrorState 形に書き換え (production code 未変更のため fail)。`toErrorState` の新規 test も failing で先に書く
2. **Green phase**: production code (helper / store / consumer) を新形に書き換え、test pass
3. **Refactor phase**: 重複 selector の destructuring 整理、wrapper class 名整合、commit 整理

Iron Law 3 (scope creep 禁止): Refactor phase で「ついでに」 lifecycle 規約を変更するのは禁止。§5.4 matrix 厳守、変更が必要なら新 issue を起票。

### §6.2 影響を受ける test ファイル

実コード調査で確認した、本 refactor で touch する test file:

| file | 主な assertion 変更 | 種別 |
| --- | --- | --- |
| `gui/src/lib/appError.test.ts` | `appErrorMessage` / `appErrorHint` test 削除、`toErrorState` test 追加 (3-4 件) | helper |
| `gui/src/state/metadataStore.test.ts` | 6 catch path + lifecycle 規約 pin (PR #714 由来)、`*ErrorState` 形に書換 | store |
| `gui/src/state/recentStore.test.ts` | `loadErrorState` / `addErrorState` set / clear | store |
| `gui/src/components/RestoreButton.test.tsx` | `restoreErrorState.message` / `.hint` render | store consumer |
| `gui/src/components/ConflictModal.test.tsx` | `conflictErrorState.message` / `.hint` + キャンセル補足 | store consumer |
| `gui/src/components/DraftRestoreModal.test.tsx` | `draftLoadErrorState.message` / `.hint` render | store consumer |
| `gui/src/components/ConfirmExitModal.test.tsx` | helper migration 後の挙動 retain (local useState 維持) | helper callsite |
| `gui/src/screens/DropScreen.test.tsx` | recent notice 表示 (`loadErrorState` / `addErrorState` 優先順位) + local useState helper migration | store consumer + helper |
| `gui/src/screens/PreviewScreen.test.tsx` | `applyErrorState` render + local useState helper migration + AppError shape construction | store consumer + helper |
| `gui/src/screens/DetectingScreen.test.tsx` | onError callsite の helper migration | helper callsite |
| `gui/src/screens/ExportScreen.test.tsx` | local useState helper migration | helper callsite |
| `gui/src/components/InlineErrorHint.test.tsx` | 変更なし (API 不変) | (touch なし) |
| `gui/src/screens/CompleteScreen.test.tsx` | 変更なし (store error 参照なし) | (touch なし) |
| `gui/src/__tests__/flow.integration.test.tsx` | 変更なし (store error 参照なし、要確認) | (touch なし想定) |

合計 **11 file** が touch される (touch なし想定 3 file を除く)。新規 test は `toErrorState` の 3-4 件のみ、既存 baseline は維持し合計「baseline + 3-4 件 pass」を目標とする。

### §6.3 自動チェック (Iron Law 6 PR Pre-flight)

PR 作成時に以下を全 pass させる:

- **Step 0 (ハードゲート)**: `gh pr list --search "#694" --state open` で並行 PR ゼロ確認 (<1s、build/verify の前)
- **Step 1**: `git fetch origin develop-0.2.0`
- **Step 2**: `git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認
- **Step 3**: touched files 交差判定 (本 PR の touched: `gui/src/state/*.ts` / `gui/src/state/*.test.ts` / `gui/src/lib/appError*` / `gui/src/components/*.tsx` / `gui/src/components/*.test.tsx` / `gui/src/screens/*.tsx` / `gui/src/screens/*.test.tsx` / `gui/src/__tests__/flow.integration.test.tsx` / `docs/ui-architecture.md` / `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`)
- **Step 4**: `gh pr list --search "#694" --state all` で並行 worktree PR 再確認

path 別自動チェック:

- `cd gui && npm run lint` (exit 0)
- `cd gui && npm run typecheck` (exit 0)
- `cd gui && npm test -- --run` (全 pass)
- `cd gui && npm run build` (success)
- `cd gui/src-tauri && cargo check` (Rust 変更なし、regression なし)
- `cd gui/src-tauri && cargo test --lib` (既存 baseline 維持)
- `bash scripts/check-markdownlint.sh` (docs 更新分)
- Python 変更なしだが念のため `ruff check . && ruff format --check . && pyright && pytest` も実行

### §6.4 Iron Law 6 実機検証

Rust 変更なしだが `gui/src/state/*` 挙動変更は GUI 起動経路に影響しうるため、PR 作成時に `AskUserQuestion` で Idios に以下 4 経路を依頼:

| 経路 | 確認内容 |
| --- | --- |
| metadata.json load 失敗 (存在しないファイル) | DropScreen / DetectingScreen で `loadErrorState.message` + hint render |
| apply 中の `state.mtime_conflict` (2 process 同時 edit) | ConflictModal で `conflictErrorState.message` + hint + キャンセル補足 1 行 |
| restore 失敗 (backup なし状態で restore button 押下) | RestoreButton inline で `restoreErrorState.message` + hint |
| recent.json 破損 / 削除 | DropScreen 上部 notice で `loadErrorState` 優先表示 |

Phase 1 (#714 / #716 / #725 / #730 / #733) と同経路の retest なので Idios の判断で軽量 spot check 可能。

### §6.5 CI 整合

PR CI 全 7 job (`python` / `gui-frontend` / `gui-rust` / `doc-tauri-commands-drift` / `installer-pester` / `markdownlint` / `validate-checklist`) を pass する想定:

- `gui-frontend`: 主戦場、必ず pass
- `gui-rust`: Rust 変更なし、regression check 必須
- `doc-tauri-commands-drift`: `docs/tauri-commands.md` と `error.rs` の drift 検査、本 lane では Rust 変更なしのため pass 維持
- `markdownlint`: docs/ui-architecture.md 更新分で関係
- `python` / `installer-pester` / `validate-checklist`: 影響なし、pass 維持

### §6.6 Iron Law 1〜6 整合

- **Iron Law 1**: PR 本文で Issue #694 受け入れ条件を逐条引用 + diff/test 引用 (`/enforce-acceptance-criteria` skill を `/review-pr` 時に必ず呼ぶ)
- **Iron Law 2**: 本 spec は 1 件の brainstorming 設計、bulk operation なし。merge 時の close は `/close-issue` skill で実施
- **Iron Law 3**: 1 PR = 1 issue 厳守、scope creep 検知時は `scope-guard` skill。Refactor phase で「ついでに」 lifecycle 規約を変更するのは禁止 (§6.1)
- **Iron Law 4**: PR / commit に Closes/Fixes 禁止、`Refs #694` のみ。merge 後 `/close-issue` で実測再検証
- **Iron Law 5**: brainstorming で 4 件の AskUserQuestion 実施済 (§7 採用方針サマリ)、PR 内で追加 ambiguity が出れば AskUserQuestion 実施
- **Iron Law 6**: §6.3 / §6.4 で全 PR に適用、Step 0-4 + path 別自動 + 実機検証

## §7 採用方針サマリ (brainstorming Q&A trace)

| 決定 | 採用 | 棄却 | 理由 |
| --- | --- | --- | --- |
| PR 戦略 (Q1) | 1 atomic PR | 2 PR (store 別) / 3 PR phased | Iron Law 3 と整合、中間状態 (旧/新 state 共存) を避ける、~30 file の mechanical rewrite で十分管理可能、commit を意味単位に分けて review 可能性確保 |
| Helper API (Q2) | `appErrorMessage` / `appErrorHint` 削除、`appErrorCodeIs` / `isAppError` 維持 | 全 4 維持 / 全 4 削除 | dead helper 化を避けつつ catch path 内 if 分岐の readability を維持、`appErrorCodeIs` は記号反転のない predicate として有用 |
| ErrorState shape (Q3) | `{message, hint, code}` | + stacktrace / discriminated union | inline error 用途には十分、`stacktrace` は ErrorModal 経路で扱う (本 PR scope 外)、discriminated union は consumer 側の narrowing コストが高すぎる |
| Conflict scope (Q4) | `conflictErrorState` 含む (Issue body 訂正は PR 本文に記録) | exclude / issue body 事前編集 | Store 内一貫性 + Phase 1 PR #725 で追加済 conflict pair を放置しない、issue body 編集は PR レビュー時に diff 確認できないため PR 本文での訂正記録を採用 |

## §8 受け入れ条件

- [ ] `gui/src/lib/appError.ts` に `ErrorState` interface + `toErrorState()` が追加され、`appErrorMessage` / `appErrorHint` が削除されている
- [ ] `gui/src/lib/appError.test.ts` で `toErrorState` の 3 分岐 (AppError / Error / raw String) + hint `undefined → null` 正規化が test されている (新規 3-4 件)
- [ ] `gui/src/state/metadataStore.ts` が 6 個の `*ErrorState: ErrorState \| null` field に集約され、12 個の `*Error` / `*ErrorHint` field が削除されている (load / apply / restore / conflict / draftSave / draftLoad)
- [ ] `gui/src/state/recentStore.ts` が 2 個の `*ErrorState: ErrorState \| null` field に集約され、4 個の `*Error` / `*ErrorHint` field が削除されている (load / add)
- [ ] `gui/src/state/metadataStore.test.ts` で §5.4 matrix が `*ErrorState` 形で pin されている (Phase 1 PR #714 規約継承)、既存件数維持
- [ ] `gui/src/state/recentStore.test.ts` で `loadErrorState` / `addErrorState` の set / clear が pin されている、既存件数維持
- [ ] **5 store-level consumer** (RestoreButton / ConflictModal / DraftRestoreModal / DropScreen recent notice / PreviewScreen applyError) が `*ErrorState` selector に切り替わっている
- [ ] **7 file の helper callsite** (metadataStore / recentStore / DetectingScreen / DropScreen / ExportScreen / PreviewScreen / ConfirmExitModal) で `appErrorMessage` / `appErrorHint` が `toErrorState` 経由に migration されている
- [ ] `appErrorMessage` / `appErrorHint` は repo 全体で callsite ゼロ、helper file からも削除されている
- [ ] local `useState` の `[error, errorHint]` pair pattern は (Iron Law 3 のため) touch されていない (DetectingScreen / DropScreen / ExportScreen / PreviewScreen / ConfirmExitModal の local state)
- [ ] `InlineErrorHint` component API (`hint: string \| null \| undefined`) は不変、consumer 側 wrapper class (`.applyErrorHint` / `.listErrorHint` 等の site-specific overflow 制御) は保持されている
- [ ] `gui/src/__tests__/flow.integration.test.tsx` の関連 assertion を確認 (現状 store error 参照なしのため touch なし想定、要 PR 内検証)
- [ ] 既存 test baseline が pass、`toErrorState` の新規 3-4 件で合計「baseline + 3-4 件 pass」
- [ ] `docs/ui-architecture.md` §4 の lifecycle 規約節が `*ErrorState` 形に更新されている (Pair atomicity 規約 → 単一 field 規約)
- [ ] `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` §7 に Phase 2 完遂 Refs リンク追加
- [ ] PR 本文に Issue #694 body の 5 pair 誤記 (Phase 1 PR #725 で conflict pair 追加済) を訂正記録
- [ ] Iron Law 6 PR Pre-flight (Step 0-4) 全 pass、CI 全 7 job pass
- [ ] Iron Law 6 実機検証 4 経路を Idios PR comment で PASS 確認

## §9 リスク表

| リスク | 影響 | 緩和策 |
| --- | --- | --- |
| 大規模 atomic PR で diff が見にくくレビュー困難 | レビューミス・regression 残留 | PR 本文に「mechanical rewrite + 新 helper」の明確な区分け、commit を §4 の 4 commit 構成で積んで読みやすく、`/iterate-review` で全 finding を消化 |
| `*ErrorState?.message` 経由で render が `null` 時に空 span になる UI 上の差 | 旧 `*Error: string \| null` の falsy 評価と微妙な違い | conditional rendering を `{loadErrorState && (...)}` で wrapping、`loadErrorState?.message` 単独で render しない (DOM 比較 test で挙動同等を pin) |
| `appErrorMessage` / `appErrorHint` の削除で外部参照 (今後の merge / cherry-pick) が壊れる | 別 lane の merge conflict | repo grep で callsite ゼロを確認、削除後に rebase 順位の高い lane (#699 / Phase 3) と coordinate |
| lifecycle matrix が `*ErrorState` 化で意図せず変わる | 「pair atomicity 規約 → 単一 field 規約」での挙動差 | Phase 1 PR #714 で pin した既存 lifecycle test を Red→Green で確認、Refactor phase で挙動変更しないことを cross-check、§5.4 matrix を実装時に逐条照合 |
| ConflictModal の「hint 主 + 補足 1 行」構造を refactor で誤って壊す | Phase 1 で UX 整備済の挙動 regression | PR #725 で確立した assertion (Phase 1 spec §5.3) を current test で必ず維持、`.cancelHint` 補足 1 行の常時表示 test を新形でも pin |
| `docs/ui-architecture.md` §4 の lifecycle 節更新で意味変化 | doc-drift | doc は本 PR 内で同時更新、`*ErrorHint` 文言を完全に `*ErrorState` に置換、別軸の意味変更は scope-guard で禁止 |
| Phase 3 #699 stale docstring 更新が本 PR の docstring と重なる | 順序依存 | 本 PR で `appError.ts:57-62` 等の stale 表現 (`appErrorHint` 関連) を helper 削除に合わせて update、#699 のスコープを「残った Rust / その他 docstring」に絞る (Phase 3 spec で確定) |
| `toErrorState` の hint `undefined → null` 正規化を忘れる callsite が出る | type level では検出できない silent inconsistency | helper 内で `typeof e.hint === 'string' ? e.hint : null` 経由を厳守、test で `hint: undefined` 入力 case を必ず pin |

## §10 Open questions

brainstorming で 4 件の AskUserQuestion (§7) で主要決定はすべて確定。残 open question は **PR 内で AskUserQuestion 実施** とする予定の項目:

- なし (本 spec に含めた決定で実装着手可能、追加 ambiguity が出れば PR 内で AskUserQuestion 実施)

## §11 関連 doc

- [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md](../plans/2026-05-13-l2-v020-roadmap-update-implementation-plan.md) §Group I — 親 plan
- [docs/superpowers/specs/2026-05-11-lane-v-phase-1-group-i-design.md](2026-05-11-lane-v-phase-1-group-i-design.md) — Phase 1 spec、本 spec の前提
- [docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md](2026-05-08-l2-appError-migration-completion-design.md) — #663 AppError migration 起点 spec、本 PR で §7 に Phase 2 Refs リンク追加
- [docs/ui-architecture.md](../../ui-architecture.md) §4 — 本 PR で lifecycle 規約節を `*ErrorState` 形に更新
- [docs/ui-interaction-spec.md](../../ui-interaction-spec.md) §1.5 — `error.code` ベース分岐ルール、本 PR 内で touch なし (`code` の state 保存追加に伴う読み手向け補足のみ)
- [docs/tauri-commands.md](../../tauri-commands.md) — AppError default hint mapping (PR #689 で導入済、本 PR では変更なし)
- [docs/l2-workflow.md](../../l2-workflow.md) §PR 作成 Pre-flight / §Self-Test Report 規約 / §実機検証 trigger 表 — 全項目で適用
- [docs/a11y-policy.md](../../a11y-policy.md) — `role="alert"` wrapper 規約、本 PR で DOM 構造不変のため既存規約準拠

---

**brainstorming 完了**。本 spec を起点に `writing-plans` skill で実装計画を策定する。
