# Lane V Phase 2 Group I — unified `*ErrorState` refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `metadataStore` 6 pair + `recentStore` 2 pair の `*Error` / `*ErrorHint` 並列 16 field を 8 個の `*ErrorState: ErrorState | null` field に集約し、`appErrorMessage` / `appErrorHint` helper を `toErrorState` 経由に置換、PR #689 で確立した hint UI を維持しつつ store-level 並列構造を解消する (Issue [#694](https://github.com/Idios/kobutachan-allaganeye/issues/694))。

**Architecture:** 1 atomic PR、13 commit (helper 追加 → store 2 件 → 5 store consumer → 5 helper callsite migration → helper 削除 → docs)。Spec [`2026-05-14-lane-v-phase-2-group-i-design.md`](../specs/2026-05-14-lane-v-phase-2-group-i-design.md) を起点に Phase 1 PR #714 / #716 / #725 / #730 / #733 の規約を完全継承。TDD HARD-GATE 遵守 (Red-Green-Refactor)。Iron Law 6 PR Pre-flight (Step 0-4) + 実機検証 4 経路で完結。

**Tech Stack:** TypeScript 5.x / React 19 / Zustand / vitest / @testing-library/react / Tauri 2 (Rust 変更なし)

---

## Pre-flight (Task 0: 現状確認)

実装前に baseline を pin する。

- [ ] **Step 0-1: 現状の test count 確認**

Run: `cd gui && npm test -- --run 2>&1 | tail -5`
Expected: 全 pass、件数を控える (例: `605 passed`)。以降の Task で baseline + 新規 toErrorState 3-4 件で「baseline + 3-4 passed」を維持する。

- [ ] **Step 0-2: `appErrorMessage` / `appErrorHint` callsite 確認**

Run: `cd gui && grep -rn "appErrorMessage\|appErrorHint" src/ --include='*.ts' --include='*.tsx' | grep -v -E '\.test\.|/lib/appError'`
Expected: 7 file (metadataStore / recentStore / DetectingScreen / DropScreen / ExportScreen / PreviewScreen / ConfirmExitModal) で計 ~19 callsite (production 側のみ、test や appError.ts 自体は除外)。

- [ ] **Step 0-3: 既存 `*Error` / `*ErrorHint` field の使用箇所確認**

Run: `cd gui && grep -rn "loadError\|loadErrorHint\|applyError\|applyErrorHint\|restoreError\|restoreErrorHint\|conflictError\|conflictErrorHint\|draftSaveError\|draftSaveErrorHint\|draftLoadError\|draftLoadErrorHint\|addError\|addErrorHint" src/ --include='*.ts' --include='*.tsx' | wc -l`
Expected: 数十件 (production + test 両方含む)。

- [ ] **Step 0-4: PR Pre-flight Step 0 ハードゲート**

Run: `gh pr list --search "#694" --state open`
Expected: 0 件 (本 PR の並行 PR なし)。1 件以上見つかった場合は STOP、Idios に AskUserQuestion で確認。

- [ ] **Step 0-5: base 同期確認**

Run: `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline`
Expected: 取り込み未済 commit があれば内容を確認、本 PR の touched files (`gui/src/state/*` / `gui/src/lib/appError*` / `gui/src/components/*` / `gui/src/screens/*` / `docs/*`) と交差するなら `git merge origin/develop-0.2.0` で取り込む。

---

## Task 1: `ErrorState` interface + `toErrorState` helper を追加 (additive)

**Files:**
- Modify: `gui/src/lib/appError.ts`
- Modify: `gui/src/lib/appError.test.ts`

**目的**: 新 helper を追加するが、`appErrorMessage` / `appErrorHint` はまだ残す (Task 2-11 の callsite migration 完了まで build pass を維持)。

- [ ] **Step 1-1: 新 toErrorState の failing test を `appError.test.ts` の末尾に追加**

Edit `gui/src/lib/appError.test.ts` に以下を追記 (`import` に `toErrorState` も追加):

```ts
import {
  appErrorCodeIs,
  appErrorHint,
  appErrorMessage,
  isAppError,
  toErrorState,
} from './appError';

// ... 既存 describe ブロック (isAppError / appErrorMessage / appErrorCodeIs / appErrorHint) は維持 ...

describe('toErrorState', () => {
  it('normalizes AppError into ErrorState (with code / hint)', () => {
    const result = toErrorState({
      code: 'io.file_not_found',
      message: 'metadata.json not found',
      hint: 'ファイルパスを確認してください',
    });
    expect(result).toEqual({
      message: 'metadata.json not found',
      hint: 'ファイルパスを確認してください',
      code: 'io.file_not_found',
    });
  });

  it('coerces hint:undefined to null when AppError has no hint', () => {
    const result = toErrorState({
      code: 'io.read_failed',
      message: 'read fail',
    });
    expect(result).toEqual({
      message: 'read fail',
      hint: null,
      code: 'io.read_failed',
    });
  });

  it('coerces non-string hint to null (defensive)', () => {
    const result = toErrorState({
      code: 'io.read_failed',
      message: 'read fail',
      hint: 42 as unknown as string,
    });
    expect(result).toEqual({
      message: 'read fail',
      hint: null,
      code: 'io.read_failed',
    });
  });

  it('extracts Error.message with null hint / null code', () => {
    const result = toErrorState(new Error('boom'));
    expect(result).toEqual({
      message: 'boom',
      hint: null,
      code: null,
    });
  });

  it('coerces raw string to string with null hint / null code (legacy fallback)', () => {
    const result = toErrorState('legacy raw error');
    expect(result).toEqual({
      message: 'legacy raw error',
      hint: null,
      code: null,
    });
  });

  it('coerces null / undefined to their string representation', () => {
    expect(toErrorState(null)).toEqual({
      message: 'null',
      hint: null,
      code: null,
    });
    expect(toErrorState(undefined)).toEqual({
      message: 'undefined',
      hint: null,
      code: null,
    });
  });
});
```

- [ ] **Step 1-2: テストを実行して fail 確認 (Red)**

Run: `cd gui && npx vitest run src/lib/appError.test.ts 2>&1 | tail -20`
Expected: `toErrorState` describe ブロックが全 fail (`toErrorState is not defined` / `not a function`)。既存 `isAppError` / `appErrorMessage` / `appErrorCodeIs` / `appErrorHint` の describe は引き続き pass。

- [ ] **Step 1-3: `appError.ts` に `ErrorState` interface + `toErrorState` helper を追加**

Edit `gui/src/lib/appError.ts` の `appErrorHint` 直前 (line 62 付近) に以下を挿入:

```ts
/**
 * Store の inline error slot に詰める正規化済み構造。AppError と異なり:
 * - `hint` / `code` は legacy raw String や `Error` instance では `null`
 * - `stacktrace` は inline UI 用途では運ばない (ErrorModal 等の別経路で扱う)
 *
 * #694 で導入 (Lane V Phase 2)。catch path で
 * `set({ loadErrorState: toErrorState(e) })` の 1 行に短縮するための型。
 */
export interface ErrorState {
  message: string;
  hint: string | null;
  code: string | null;
}

/**
 * invoke の reject value (AppError / Error / raw String / null/undefined) を
 * ErrorState に正規化する。
 *
 * - AppError → `{ message, hint: hint ?? null, code }`
 * - Error instance → `{ message: e.message, hint: null, code: null }`
 * - その他 (raw String / null / undefined) → `{ message: String(e), hint: null, code: null }`
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
```

- [ ] **Step 1-4: テストを実行して pass 確認 (Green)**

Run: `cd gui && npx vitest run src/lib/appError.test.ts 2>&1 | tail -20`
Expected: 全 pass (既存 + 新規 toErrorState 6 件)。

- [ ] **Step 1-5: lint / typecheck**

Run: `cd gui && npm run lint && npm run typecheck`
Expected: exit 0 (warning / error なし)。

- [ ] **Step 1-6: Commit**

```bash
git add gui/src/lib/appError.ts gui/src/lib/appError.test.ts
git commit -m "$(printf 'feat(gui): #694 ErrorState interface + toErrorState helper を追加 (additive)\n\nLane V Phase 2 / Group I — *ErrorState unified refactor の前段。\n\n- ErrorState interface: {message, hint, code} の正規化型\n- toErrorState(e): AppError / Error / raw String / null/undefined を ErrorState に\n  集約する helper\n- 既存 appErrorMessage / appErrorHint は Task 2-11 の callsite migration 完了まで\n  残置 (build pass 維持のため)\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: `metadataStore.ts` を `*ErrorState` 形に migration

**Files:**
- Modify: `gui/src/state/metadataStore.ts` (state interface + 5 catch path + 5 success path + lifecycle 終端)
- Modify: `gui/src/state/metadataStore.test.ts` (~80 assertion 書き換え)

**目的**: 6 pair = 12 state field を 6 個の `*ErrorState: ErrorState | null` field に集約。catch path で `appErrorMessage(e)` + `appErrorHint(e)` の 2 行を `toErrorState(e)` の 1 行に短縮。Spec §5.4 lifecycle matrix を厳守。

- [ ] **Step 2-1: `metadataStore.test.ts` の assertion を `*ErrorState` 形に書き換え (Red)**

Edit `gui/src/state/metadataStore.test.ts`:

(a) `*Error` / `*ErrorHint` への直接アクセスを `*ErrorState` 経由に書換。代表 pattern:

```ts
// Before
expect(useMetadataStore.getState().loadError).toBe('not found');
expect(useMetadataStore.getState().loadErrorHint).toBe('check path');

// After
expect(useMetadataStore.getState().loadErrorState).toEqual({
  message: 'not found',
  hint: 'check path',
  code: 'io.file_not_found',
});
```

(b) `setState` で error を set している箇所も書換:

```ts
// Before
useMetadataStore.setState({ loadError: 'msg', loadErrorHint: 'hint' });

// After
useMetadataStore.setState({
  loadErrorState: { message: 'msg', hint: 'hint', code: null },
});
```

(c) lifecycle 規約 pinning test (PR #714 由来) は §5.4 matrix の field 名のみ書換、構造は維持。`null` reset の assertion は `expect(s.loadErrorState).toBeNull()` に。

対象 field: `loadError` / `loadErrorHint` / `applyError` / `applyErrorHint` / `restoreError` / `restoreErrorHint` / `conflictError` / `conflictErrorHint` / `draftSaveError` / `draftSaveErrorHint` / `draftLoadError` / `draftLoadErrorHint` の 12 個 → 6 個の `*ErrorState`。

- [ ] **Step 2-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/state/metadataStore.test.ts 2>&1 | tail -30`
Expected: 多数 fail (production 側がまだ旧 field 名)。assertion の TypeScript 型エラー (`Property 'loadErrorState' does not exist`) が出ても継続。

- [ ] **Step 2-3: `metadataStore.ts` の State interface を `*ErrorState` 形に書換**

Edit `gui/src/state/metadataStore.ts` line 26-133 の `MetadataState` interface:

```ts
export interface MetadataState {
  metadata: Metadata | null;
  filePath: string | null;
  dirty: boolean;
  /** #694 (Phase 2): load 失敗時の error 構造。`AppError.code` も保持される。 */
  loadErrorState: ErrorState | null;
  applying: boolean;
  /** #694: apply 失敗時の error 構造。`state.mtime_conflict` は別 slot (conflictErrorState) に分岐。 */
  applyErrorState: ErrorState | null;

  hasBackup: boolean;
  restoring: boolean;
  /** #694: restore 失敗時の error 構造。 */
  restoreErrorState: ErrorState | null;

  loadedMtimeMs: number | null;
  /**
   * #514: external mtime conflict の error 構造 (#694 でフィールド名 + 型を変更)。
   * Non-null means the UI must surface the "overwrite / reload / cancel" modal.
   */
  conflictErrorState: ErrorState | null;
  pendingDraft: Metadata | null;
  /** #694: draft 読み込み失敗時の error 構造。 */
  draftLoadErrorState: ErrorState | null;
  draftSaving: boolean;
  /** #694: draft 保存失敗時の error 構造。 */
  draftSaveErrorState: ErrorState | null;

  // 既存 action signatures は変更なし
  load: (path: string) => Promise<void>;
  updateMatch: (index: number, patch: MatchEditPatch) => void;
  apply: () => Promise<void>;
  reset: () => void;
  clear: () => void;
  restore: () => Promise<void>;
  refreshBackupStatus: () => Promise<void>;
  applyOverwrite: () => Promise<void>;
  reloadAfterConflict: () => Promise<void>;
  dismissConflict: () => void;
  saveDraft: () => Promise<void>;
  loadDraft: () => Promise<void>;
  clearDraft: () => Promise<void>;
  restoreDraft: () => void;
  discardDraft: () => Promise<void>;
  discardEdits: () => Promise<void>;
  loadSample: () => void;
}
```

Edit line 4 import (まだ `appErrorMessage` / `appErrorHint` は残しつつ `ErrorState` / `toErrorState` を import 追加):

```ts
import {
  appErrorCodeIs,
  toErrorState,
  type ErrorState,
} from '../lib/appError';
```

(`appErrorMessage` / `appErrorHint` import は削除 — もう使わない。`appErrorCodeIs` は `state.mtime_conflict` 分岐で継続使用。)

- [ ] **Step 2-4: 初期 state と全 catch / success / lifecycle path を書換**

Edit `gui/src/state/metadataStore.ts`:

(a) 初期 state (line 232-255 付近、`return { metadata: null, ...`):

```ts
return {
  metadata: null,
  filePath: null,
  dirty: false,
  loadErrorState: null,
  applying: false,
  applyErrorState: null,

  hasBackup: false,
  restoring: false,
  restoreErrorState: null,

  loadedMtimeMs: null,
  conflictErrorState: null,
  pendingDraft: null,
  draftLoadErrorState: null,
  draftSaving: false,
  draftSaveErrorState: null,

  load: async (path) => { /* ... */ },
  // ... 以下既存
```

(b) `runApply()` (line 192-230) を全面書換:

```ts
async function runApply(overwrite: boolean): Promise<void> {
  const { metadata, filePath, loadedMtimeMs } = get();
  if (!metadata || !filePath) return;
  set({
    applying: true,
    applyErrorState: null,
    conflictErrorState: null,
  });
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

(c) `load()` (line 257-310) を全面書換:

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

(d) `clear()` (line 339-364) を全面書換:

```ts
clear: () => {
  cancelDraftSave();
  set({
    metadata: null,
    filePath: null,
    dirty: false,
    loadErrorState: null,
    applying: false,
    applyErrorState: null,
    hasBackup: false,
    restoring: false,
    restoreErrorState: null,
    loadedMtimeMs: null,
    conflictErrorState: null,
    pendingDraft: null,
    draftLoadErrorState: null,
    draftSaving: false,
    draftSaveErrorState: null,
  });
},
```

(e) `restore()` (line 366-382) を書換:

```ts
restore: async () => {
  const { filePath } = get();
  if (!filePath) return;
  set({ restoring: true, restoreErrorState: null });
  try {
    await invoke('restore_from_original', { path: filePath });
    await get().load(filePath);
    set({ restoring: false });
  } catch (e) {
    set({ restoring: false, restoreErrorState: toErrorState(e) });
  }
},
```

(f) `reloadAfterConflict()` (line 405-415) と `dismissConflict()` (line 417-419) を書換:

```ts
reloadAfterConflict: async () => {
  const { filePath } = get();
  if (!filePath) {
    set({ conflictErrorState: null });
    return;
  }
  await get().load(filePath);
},

dismissConflict: () => {
  set({ conflictErrorState: null });
},
```

(g) `saveDraft()` (line 421-438) を書換:

```ts
saveDraft: async () => {
  const { filePath, metadata } = get();
  if (!filePath || !metadata) return;
  set({ draftSaving: true, draftSaveErrorState: null });
  try {
    await invoke('save_draft', { path: filePath, draft: metadata });
  } catch (e) {
    set({ draftSaveErrorState: toErrorState(e) });
  } finally {
    set({ draftSaving: false });
  }
},
```

(h) `loadDraft()` (line 440-470) を書換:

```ts
loadDraft: async () => {
  const { filePath, metadata } = get();
  if (!filePath || !metadata) return;
  try {
    const raw = await invoke<unknown>('load_draft', { path: filePath });
    if (raw === null || raw === undefined) {
      set({ pendingDraft: null, draftLoadErrorState: null });
      return;
    }
    const parsed = MetadataSchema.parse(raw) as unknown as Metadata;
    if (
      normalizeSourcePath(parsed.source) !==
      normalizeSourcePath(metadata.source)
    ) {
      await invoke('clear_draft', { path: filePath });
      set({ pendingDraft: null, draftLoadErrorState: null });
      return;
    }
    set({ pendingDraft: parsed, draftLoadErrorState: null });
  } catch (e) {
    set({ pendingDraft: null, draftLoadErrorState: toErrorState(e) });
  }
},
```

(i) `loadSample()` (line 519-544) を書換:

```ts
loadSample: () => {
  cancelDraftSave();
  set({
    metadata: sampleMetadata,
    filePath: null,
    dirty: false,
    loadErrorState: null,
    applying: false,
    applyErrorState: null,
    hasBackup: false,
    restoring: false,
    restoreErrorState: null,
    loadedMtimeMs: null,
    conflictErrorState: null,
    pendingDraft: null,
    draftLoadErrorState: null,
    draftSaving: false,
    draftSaveErrorState: null,
  });
},
```

- [ ] **Step 2-5: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/state/metadataStore.test.ts 2>&1 | tail -30`
Expected: 全 pass (既存件数維持)。fail が残れば Step 2-1 / 2-4 の assertion / 実装の対応を確認し再修正。

- [ ] **Step 2-6: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。`appErrorMessage` / `appErrorHint` を `metadataStore.ts` 内から削除したため import 文も対応していることを確認。

- [ ] **Step 2-7: Commit**

```bash
git add gui/src/state/metadataStore.ts gui/src/state/metadataStore.test.ts
git commit -m "$(printf 'refactor(gui): #694 metadataStore を *ErrorState 形に migration\n\nLane V Phase 2 / Group I — *ErrorState unified refactor。\n\n- 6 pair (loadError / applyError / restoreError / conflictError / draftSaveError /\n  draftLoadError × hint pair) → 6 個の *ErrorState: ErrorState | null\n- 5 catch path (load / runApply / restore / saveDraft / loadDraft) で\n  toErrorState(e) 経由に統一、appErrorMessage / appErrorHint 呼び出しは廃止\n- lifecycle 規約は Phase 1 PR #714 (#691) を field 名のみ書換で完全継承\n  (catch path self-only、終端 clear/loadSample で全 reset、load() catch のみ\n   conflictErrorState を file-state リセットとして touch)\n- metadataStore.test.ts の assertion を *ErrorState.message / .hint / .code 経由に\n  書換、既存件数維持\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: `recentStore.ts` を `*ErrorState` 形に migration

**Files:**
- Modify: `gui/src/state/recentStore.ts` (state interface + 2 catch path + 2 success path + lifecycle 終端)
- Modify: `gui/src/state/recentStore.test.ts` (assertion 書き換え)

- [ ] **Step 3-1: `recentStore.test.ts` の assertion を `*ErrorState` 形に書換 (Red)**

Edit `gui/src/state/recentStore.test.ts`:

(a) field 直接アクセスを `*ErrorState` 経由に書換:

```ts
// Before
expect(useRecentStore.getState().loadError).toBe('err msg');
expect(useRecentStore.getState().loadErrorHint).toBe('reload');

// After
expect(useRecentStore.getState().loadErrorState).toEqual({
  message: 'err msg',
  hint: 'reload',
  code: 'io.read_failed',
});
```

(b) `setState` も書換:

```ts
// Before
useRecentStore.setState({ loadError: 'msg', loadErrorHint: null });

// After
useRecentStore.setState({
  loadErrorState: { message: 'msg', hint: null, code: null },
});
```

対象 field: `loadError` / `loadErrorHint` / `addError` / `addErrorHint` の 4 個 → 2 個の `*ErrorState`。

- [ ] **Step 3-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/state/recentStore.test.ts 2>&1 | tail -20`
Expected: 多数 fail (production 側がまだ旧 field 名)。

- [ ] **Step 3-3: `recentStore.ts` を `*ErrorState` 形に書換**

Edit `gui/src/state/recentStore.ts`:

(a) line 4 import 書換:

```ts
import { toErrorState, type ErrorState } from '../lib/appError';
```

(`appErrorMessage` / `appErrorHint` import を削除。)

(b) `RecentState` interface (line 23-53):

```ts
export interface RecentState {
  entries: RecentEntry[];
  loaded: boolean;
  /**
   * Last load failure. #698: DropScreen 上部に inline notice として表示される。
   * dismiss なし、次回 load 成功で自動消去。#694 で ErrorState 型に集約。
   */
  loadErrorState: ErrorState | null;
  /**
   * Last add failure. #698: DropScreen 上部に notice として表示 (loadError 不在
   * 時の fallback)。#694 で ErrorState 型に集約。
   */
  addErrorState: ErrorState | null;

  load: () => Promise<void>;
  add: (path: string) => Promise<void>;
  clear: () => Promise<void>;
  reset: () => void;
}
```

(c) store 初期化と action 実装全体を書換:

```ts
export const useRecentStore = create<RecentState>((set) => ({
  entries: [],
  loaded: false,
  loadErrorState: null,
  addErrorState: null,

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
}));
```

- [ ] **Step 3-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/state/recentStore.test.ts 2>&1 | tail -20`
Expected: 全 pass (既存件数維持)。

- [ ] **Step 3-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 3-6: Commit**

```bash
git add gui/src/state/recentStore.ts gui/src/state/recentStore.test.ts
git commit -m "$(printf 'refactor(gui): #694 recentStore を *ErrorState 形に migration\n\nLane V Phase 2 / Group I — *ErrorState unified refactor。\n\n- 2 pair (loadError / addError × hint pair) → 2 個の\n  *ErrorState: ErrorState | null\n- 2 catch path (load / add) で toErrorState(e) 経由に統一\n- recentStore.test.ts の assertion を *ErrorState.message / .hint / .code 経由に書換\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: `RestoreButton.tsx` を `restoreErrorState` selector に migration

**Files:**
- Modify: `gui/src/components/RestoreButton.tsx` (selector + render path)
- Modify: `gui/src/components/RestoreButton.test.tsx` (assertion + setState)

- [ ] **Step 4-1: `RestoreButton.test.tsx` の error 関連 setState / assertion を書換 (Red)**

Edit `gui/src/components/RestoreButton.test.tsx`:

`useMetadataStore.setState({ restoreError: ..., restoreErrorHint: ... })` を以下に書換:

```ts
useMetadataStore.setState({
  restoreErrorState: {
    message: '権限がありません',
    hint: 'ファイルの権限を確認してください',
    code: 'io.permission_denied',
  },
});
```

assertion (例: `screen.getByText('権限がありません')`、`screen.getByText('💡 ファイルの権限を確認してください')`) は文言が同じなのでそのまま。

`onRestored` 経路の check (`useMetadataStore.getState().restoreError === null`) は `restoreErrorState === null` に書換。

- [ ] **Step 4-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/components/RestoreButton.test.tsx 2>&1 | tail -20`
Expected: production 側が旧 field のため fail。

- [ ] **Step 4-3: `RestoreButton.tsx` の selector / render path を書換**

Edit `gui/src/components/RestoreButton.tsx` line 55-59:

```tsx
// Before
const restoreError = useMetadataStore((s) => s.restoreError);
const restoreErrorHint = useMetadataStore((s) => s.restoreErrorHint);

// After
const restoreErrorState = useMetadataStore((s) => s.restoreErrorState);
```

line 84 (onRestored 条件) も書換:

```tsx
// Before
if (useMetadataStore.getState().restoreError === null && onRestored) {

// After
if (useMetadataStore.getState().restoreErrorState === null && onRestored) {
```

line 105-110 (render path):

```tsx
{restoreErrorState && (
  <span className={styles.error} role="alert">
    {restoreErrorState.message}
    <InlineErrorHint hint={restoreErrorState.hint} />
  </span>
)}
```

- [ ] **Step 4-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/components/RestoreButton.test.tsx 2>&1 | tail -20`
Expected: 全 pass。

- [ ] **Step 4-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 4-6: Commit**

```bash
git add gui/src/components/RestoreButton.tsx gui/src/components/RestoreButton.test.tsx
git commit -m "$(printf 'refactor(gui): #694 RestoreButton を restoreErrorState selector に migration\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: `ConflictModal.tsx` を `conflictErrorState` selector に migration

**Files:**
- Modify: `gui/src/components/ConflictModal.tsx`
- Modify: `gui/src/components/ConflictModal.test.tsx`

- [ ] **Step 5-1: `ConflictModal.test.tsx` の setState / assertion を書換 (Red)**

Edit `gui/src/components/ConflictModal.test.tsx`:

```ts
useMetadataStore.setState({
  conflictErrorState: {
    message: 'metadata.json が外部で変更されました',
    hint: '他プロセスでの書き換えを確認してください',
    code: 'state.mtime_conflict',
  },
});
```

assertion の `screen.getByText('metadata.json ...')` と `💡 他プロセス...` はそのまま。modal 表示条件 (`!!conflictError`) の test がある場合は `!!conflictErrorState` に書換。

- [ ] **Step 5-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/components/ConflictModal.test.tsx 2>&1 | tail -20`
Expected: 多数 fail。

- [ ] **Step 5-3: `ConflictModal.tsx` の selector / render path を書換**

Edit `gui/src/components/ConflictModal.tsx`:

(a) line 21-22 (selector):

```tsx
const conflictErrorState = useMetadataStore((s) => s.conflictErrorState);
```

(`conflictError` / `conflictErrorHint` の 2 selector を削除。)

(b) line 32 (isOpen 判定):

```tsx
const isOpen = !!conflictErrorState;
```

(c) line 36 (early return):

```tsx
if (!conflictErrorState) return null;
```

(d) line 49-50 (message + hint render):

```tsx
<p className={styles.message}>{conflictErrorState.message}</p>
<InlineErrorHint hint={conflictErrorState.hint} />
```

- [ ] **Step 5-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/components/ConflictModal.test.tsx 2>&1 | tail -20`
Expected: 全 pass。

- [ ] **Step 5-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 5-6: Commit**

```bash
git add gui/src/components/ConflictModal.tsx gui/src/components/ConflictModal.test.tsx
git commit -m "$(printf 'refactor(gui): #694 ConflictModal を conflictErrorState selector に migration\n\nPhase 1 PR #725 の hint 主 + キャンセル補足 1 行 layout を継承。\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 6: `DraftRestoreModal.tsx` を `draftLoadErrorState` + `conflictErrorState` 条件に migration

**Files:**
- Modify: `gui/src/components/DraftRestoreModal.tsx`
- Modify: `gui/src/components/DraftRestoreModal.test.tsx`

- [ ] **Step 6-1: `DraftRestoreModal.test.tsx` の setState / assertion を書換 (Red)**

Edit `gui/src/components/DraftRestoreModal.test.tsx`:

```ts
useMetadataStore.setState({
  draftLoadErrorState: {
    message: 'draft が破損しています',
    hint: 'metadata.draft.json を確認してください',
    code: 'parse.json_invalid',
  },
});
```

`draftLoadErrorHint` を assert していた test は `draftLoadErrorState.hint` の挙動として書換 (UI 表示は変わらないので `getByText('💡 ...')` はそのまま)。`conflictError` 条件 ((conflictError) return null) の test も `conflictErrorState` 条件に書換。

- [ ] **Step 6-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/components/DraftRestoreModal.test.tsx 2>&1 | tail -20`
Expected: 多数 fail。

- [ ] **Step 6-3: `DraftRestoreModal.tsx` の selector / 条件 / render path を書換**

Edit `gui/src/components/DraftRestoreModal.tsx`:

(a) line 14-16 (selector):

```tsx
const draftLoadErrorState = useMetadataStore((s) => s.draftLoadErrorState);
const conflictErrorState = useMetadataStore((s) => s.conflictErrorState);
```

(`draftLoadError` / `draftLoadErrorHint` / `conflictError` の 3 selector を 2 に集約。)

(b) line 22 (conflict 優先):

```tsx
if (conflictErrorState) return null;
```

(c) line 23 (modal 表示判定):

```tsx
if (!pendingDraft && !draftLoadErrorState) return null;
```

(d) line 25 (draft error 分岐):

```tsx
if (draftLoadErrorState) {
```

(e) line 38-39 (message + hint render):

```tsx
<p className={styles.message}>{draftLoadErrorState.message}</p>
<InlineErrorHint hint={draftLoadErrorState.hint} />
```

- [ ] **Step 6-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/components/DraftRestoreModal.test.tsx 2>&1 | tail -20`
Expected: 全 pass。

- [ ] **Step 6-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 6-6: Commit**

```bash
git add gui/src/components/DraftRestoreModal.tsx gui/src/components/DraftRestoreModal.test.tsx
git commit -m "$(printf 'refactor(gui): #694 DraftRestoreModal を draftLoadErrorState + conflictErrorState 条件に migration\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 7: `DropScreen.tsx` を `loadErrorState` / `addErrorState` selector + helper callsite に migration

**Files:**
- Modify: `gui/src/screens/DropScreen.tsx` (recent notice selector + 2 catch path で `appErrorMessage` / `appErrorHint` → `toErrorState`)
- Modify: `gui/src/screens/DropScreen.test.tsx`

**注**: local useState の `[error, errorHint]` pair pattern 自体は触らない (scope creep 防止)。`setError(...)` / `setErrorHint(...)` 呼び出し前に `toErrorState(e)` を 1 回呼んで `.message` / `.hint` を渡す形に。

- [ ] **Step 7-1: `DropScreen.test.tsx` の setState / assertion を書換 (Red)**

Edit `gui/src/screens/DropScreen.test.tsx`:

recent notice 関連の setState を書換:

```ts
useRecentStore.setState({
  loadErrorState: {
    message: 'history file が読めません',
    hint: '~/.allaganeye/recent.json を確認してください',
    code: 'io.read_failed',
  },
});
```

`addError` 系も同様。`loadError` / `addError` 優先順位 test の assertion は文言ベース (`getByText('history file...')`) なのでそのまま。

- [ ] **Step 7-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/screens/DropScreen.test.tsx 2>&1 | tail -20`
Expected: 多数 fail。

- [ ] **Step 7-3: `DropScreen.tsx` の recent notice selector を書換 + helper callsite を `toErrorState` に**

Edit `gui/src/screens/DropScreen.tsx`:

(a) line 13 import 書換 (`appErrorMessage` / `appErrorHint` を `toErrorState` に置換):

```ts
import { toErrorState } from '../lib/appError';
```

(b) line 122-125 (recent selector を 4 → 2 に集約):

```tsx
const recentLoadErrorState = useRecentStore((s) => s.loadErrorState);
const recentAddErrorState = useRecentStore((s) => s.addErrorState);
```

(c) line 380-388 / 522-528 等の render 箇所 (`recentLoadError ?? recentAddError` で優先順位):

```tsx
const noticeState = recentLoadErrorState ?? recentAddErrorState;
// ...
{noticeState && (
  <div className={styles.recentNotice} role="alert">
    <span className={styles.recentNoticeMessage}>{noticeState.message}</span>
    <InlineErrorHint hint={noticeState.hint} />
  </div>
)}
```

(d) line 152-154 / 176-178 等の local useState catch path (2 箇所):

```tsx
} catch (e) {
  const errorState = toErrorState(e);
  setError(errorState.message);
  setErrorHint(errorState.hint);
}
```

(local useState の `error` / `errorHint` pair pattern は維持。`setError` / `setErrorHint` の呼び出し signature も維持。)

- [ ] **Step 7-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/screens/DropScreen.test.tsx 2>&1 | tail -20`
Expected: 全 pass。

- [ ] **Step 7-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 7-6: Commit**

```bash
git add gui/src/screens/DropScreen.tsx gui/src/screens/DropScreen.test.tsx
git commit -m "$(printf 'refactor(gui): #694 DropScreen を *ErrorState selector + toErrorState callsite に migration\n\n- recent notice: recentStore loadErrorState / addErrorState selector に書換 (4 → 2)\n- 2 local useState catch path: appErrorMessage(e) + appErrorHint(e) を\n  toErrorState(e).message / .hint 経由に統一 (local useState pair pattern 維持)\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 8: `PreviewScreen.tsx` を `applyErrorState` selector + helper callsite に migration

**Files:**
- Modify: `gui/src/screens/PreviewScreen.tsx` (applyError selector + 4 helper callsite)
- Modify: `gui/src/screens/PreviewScreen.test.tsx`

- [ ] **Step 8-1: `PreviewScreen.test.tsx` の setState / assertion を書換 (Red)**

Edit `gui/src/screens/PreviewScreen.test.tsx`:

```ts
useMetadataStore.setState({
  applyErrorState: {
    message: '書き込み失敗',
    hint: 'ディスク容量を確認してください',
    code: 'io.write_failed',
  },
});
```

`applyError` / `applyErrorHint` の直接アクセス test もすべて `applyErrorState` 経由に書換。

- [ ] **Step 8-2: テスト実行で fail 確認 (Red)**

Run: `cd gui && npx vitest run src/screens/PreviewScreen.test.tsx 2>&1 | tail -20`
Expected: 多数 fail。

- [ ] **Step 8-3: `PreviewScreen.tsx` の selector / render path / helper callsite を書換**

Edit `gui/src/screens/PreviewScreen.tsx`:

(a) line 17-18 import 書換 (`appErrorMessage` / `appErrorHint` を `toErrorState` に):

```ts
import { toErrorState } from '../lib/appError';
```

(b) line 101-104 (selector 2 → 1):

```tsx
const applyErrorState = useMetadataStore((s) => s.applyErrorState);
```

(c) line 834-838 (applyError 表示):

```tsx
{applyErrorState && (
  <span className={styles.applyError} role="alert">
    {applyErrorState.message}
    <span className={styles.applyErrorHint}>
      <InlineErrorHint hint={applyErrorState.hint} />
    </span>
  </span>
)}
```

(d) line 283 / 474 / 811-812 等 4 callsite を `toErrorState` 経由に書換:

```tsx
// line 283: setVideoError
const errorState = toErrorState(e);
setVideoError(errorState.message);
// ...

// line 474: AppError-shape construction
: { code: 'unknown.error', message: toErrorState(e).message },

// line 811-812: overlayError 表示
<span>{toErrorState(overlayError).message}</span>
<InlineErrorHint hint={toErrorState(overlayError).hint} />
```

(注: line 811-812 は同一 `e` に対して 2 回 `toErrorState` を呼ぶ無駄を避けるため、render 上で 1 回計算して両方に渡す形が望ましい:)

```tsx
{overlayError && (() => {
  const overlayState = toErrorState(overlayError);
  return (
    <>
      <span>{overlayState.message}</span>
      <InlineErrorHint hint={overlayState.hint} />
    </>
  );
})()}
```

または `useMemo`:

```tsx
const overlayState = useMemo(
  () => (overlayError ? toErrorState(overlayError) : null),
  [overlayError],
);
// ...
{overlayState && (
  <>
    <span>{overlayState.message}</span>
    <InlineErrorHint hint={overlayState.hint} />
  </>
)}
```

実装時に書き味で判断。

- [ ] **Step 8-4: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/screens/PreviewScreen.test.tsx 2>&1 | tail -20`
Expected: 全 pass。

- [ ] **Step 8-5: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 8-6: Commit**

```bash
git add gui/src/screens/PreviewScreen.tsx gui/src/screens/PreviewScreen.test.tsx
git commit -m "$(printf 'refactor(gui): #694 PreviewScreen を applyErrorState selector + toErrorState callsite に migration\n\n- applyError selector を applyErrorState に集約 (2 → 1)\n- 4 callsite (setVideoError catch / AppError-shape construction / overlayError 表示) を\n  toErrorState 経由に統一\n- wrapper class .applyErrorHint (display: block) は維持\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 9: `DetectingScreen.tsx` の helper callsite を `toErrorState` に migration

**Files:**
- Modify: `gui/src/screens/DetectingScreen.tsx` (onError callsite 1 個)
- Modify: `gui/src/screens/DetectingScreen.test.tsx` (該当 test があれば)

**注**: DetectingScreen は store-level `*Error` を消費していない (local error 管理は親 component 経由 `onError` callback)。本 task は helper migration のみ。

- [ ] **Step 9-1: `DetectingScreen.test.tsx` で helper 関連 test を確認 (Red 段階で fail しなければ skip)**

Run: `cd gui && grep -n 'appErrorMessage\|appErrorHint' src/screens/DetectingScreen.test.tsx`
Expected: 該当行があればコメントのみ (test 中の assertion ではない場合が多い)。assertion で helper が直接呼ばれる test があれば、対応する setState 文を書換。なければ skip。

- [ ] **Step 9-2: `DetectingScreen.tsx` の onError callsite を `toErrorState` 経由に書換**

Edit `gui/src/screens/DetectingScreen.tsx`:

(a) line 8 import:

```ts
import { toErrorState } from '../lib/appError';
```

(`appErrorMessage` / `appErrorHint` を削除。)

(b) line 534 onError callsite:

```tsx
const errorState = toErrorState(e);
onError(errorState.message, errorState.hint);
```

- [ ] **Step 9-3: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/screens/DetectingScreen.test.tsx 2>&1 | tail -10`
Expected: 全 pass。

- [ ] **Step 9-4: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 9-5: Commit**

```bash
git add gui/src/screens/DetectingScreen.tsx gui/src/screens/DetectingScreen.test.tsx
git commit -m "$(printf 'refactor(gui): #694 DetectingScreen の onError callsite を toErrorState 経由に migration\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 10: `ExportScreen.tsx` の helper callsite を `toErrorState` に migration

**Files:**
- Modify: `gui/src/screens/ExportScreen.tsx` (3 callsite)
- Modify: `gui/src/screens/ExportScreen.test.tsx` (該当 test があれば)

- [ ] **Step 10-1: `ExportScreen.test.tsx` で helper 関連 test を確認**

Run: `cd gui && grep -n 'appErrorMessage\|appErrorHint' src/screens/ExportScreen.test.tsx`
Expected: 該当行はコメントのみ (実 assertion で呼ばれていれば対応)。

- [ ] **Step 10-2: `ExportScreen.tsx` の 3 callsite を `toErrorState` 経由に書換**

Edit `gui/src/screens/ExportScreen.tsx`:

(a) line 9 import:

```ts
import { toErrorState } from '../lib/appError';
```

(b) line 382-385 per-match catch:

```tsx
const errorState = toErrorState(e);
const msg = errorState.message;
const hint = errorState.hint;
```

(c) line 443-444 openFolder catch:

```tsx
const errorState = toErrorState(e);
setOpenFolderError(errorState.message);
setOpenFolderErrorHint(errorState.hint);
```

その他 callsite (例: 他の catch path) も同 pattern で書換。

- [ ] **Step 10-3: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/screens/ExportScreen.test.tsx 2>&1 | tail -10`
Expected: 全 pass。

- [ ] **Step 10-4: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 10-5: Commit**

```bash
git add gui/src/screens/ExportScreen.tsx gui/src/screens/ExportScreen.test.tsx
git commit -m "$(printf 'refactor(gui): #694 ExportScreen の 3 helper callsite を toErrorState 経由に migration\n\nlocal useState pair pattern は維持。\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 11: `ConfirmExitModal.tsx` の helper callsite を `toErrorState` に migration

**Files:**
- Modify: `gui/src/components/ConfirmExitModal.tsx` (2 catch path)
- Modify: `gui/src/components/ConfirmExitModal.test.tsx` (該当 test があれば)

- [ ] **Step 11-1: `ConfirmExitModal.test.tsx` で helper 関連 test を確認**

Run: `cd gui && grep -n 'appErrorMessage\|appErrorHint' src/components/ConfirmExitModal.test.tsx`
Expected: 該当行はコメントのみ (実 assertion で呼ばれていれば対応)。

- [ ] **Step 11-2: `ConfirmExitModal.tsx` の 2 catch path を `toErrorState` 経由に書換**

Edit `gui/src/components/ConfirmExitModal.tsx`:

(a) line 7 import:

```ts
import { toErrorState } from '../lib/appError';
```

(b) line 44-45 / 71-72 catch path 2 箇所:

```tsx
} catch (e) {
  const errorState = toErrorState(e);
  setError(errorState.message);
  setErrorHint(errorState.hint);
}
```

(local useState `error` / `errorHint` pair pattern は維持。)

- [ ] **Step 11-3: テスト実行で pass 確認 (Green)**

Run: `cd gui && npx vitest run src/components/ConfirmExitModal.test.tsx 2>&1 | tail -10`
Expected: 全 pass。

- [ ] **Step 11-4: lint / typecheck**

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck`
Expected: exit 0。

- [ ] **Step 11-5: Commit**

```bash
git add gui/src/components/ConfirmExitModal.tsx gui/src/components/ConfirmExitModal.test.tsx
git commit -m "$(printf 'refactor(gui): #694 ConfirmExitModal の 2 helper callsite を toErrorState 経由に migration\n\nlocal useState pair pattern は維持。\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 12: `appErrorMessage` / `appErrorHint` helper 削除 + appError.test.ts cleanup

**Files:**
- Modify: `gui/src/lib/appError.ts` (helper 2 個削除)
- Modify: `gui/src/lib/appError.test.ts` (describe ブロック 2 個削除)

**目的**: Task 2-11 で全 callsite が `toErrorState` に migration 済。helper を削除する。

- [ ] **Step 12-1: callsite ゼロを確認**

Run: `cd gui && grep -rn "appErrorMessage\|appErrorHint" src/ --include='*.ts' --include='*.tsx' | grep -v -E '^/.*\.test\.|/lib/appError'`
Expected: ヒットなし (test ファイルと appError.ts 自体以外で 0 件)。1 件以上残っていれば該当 Task に戻って対応。

- [ ] **Step 12-2: `gui/src/lib/appError.ts` から `appErrorMessage` / `appErrorHint` を削除**

Edit `gui/src/lib/appError.ts`:

(a) line 33-43 (`appErrorMessage` 関数) を削除。
(b) line 54-65 (`appErrorHint` 関数) を削除。
(c) `appErrorHint` の上の `**将来用**` 等の docstring も整合更新。

削除後の `appError.ts` には `AppError` interface / `isAppError` / `appErrorCodeIs` / `ErrorState` interface / `toErrorState` の 5 export のみ残る。

- [ ] **Step 12-3: `gui/src/lib/appError.test.ts` から旧 describe ブロックを削除**

Edit `gui/src/lib/appError.test.ts`:

(a) `describe('appErrorMessage', () => {...})` ブロック全体 (line 54-73 付近) を削除。
(b) `describe('appErrorHint', () => {...})` ブロック全体 (line 103-133 付近) を削除。
(c) import 文から `appErrorHint` / `appErrorMessage` を削除:

```ts
import {
  appErrorCodeIs,
  isAppError,
  toErrorState,
} from './appError';
```

- [ ] **Step 12-4: テスト + lint + typecheck + build を全 pass 確認**

Run: `cd gui && npm test -- --run 2>&1 | tail -10`
Expected: 全 pass、件数は「Task 0 baseline - (削除した旧 helper test 件数) + 6 (toErrorState 新規)」と一致。

Run: `cd gui && npm run lint -- --max-warnings 0 && npm run typecheck && npm run build 2>&1 | tail -10`
Expected: exit 0 (3 command 全 pass)。

- [ ] **Step 12-5: Commit**

```bash
git add gui/src/lib/appError.ts gui/src/lib/appError.test.ts
git commit -m "$(printf 'refactor(gui): #694 appErrorMessage / appErrorHint helper を削除\n\nTask 2-11 で全 callsite (7 file) が toErrorState 経由に migration 済のため\n削除。残る export:\n- AppError interface\n- isAppError type guard\n- appErrorCodeIs predicate (catch path の state.mtime_conflict 等分岐用)\n- ErrorState interface\n- toErrorState normalizer\n\nappError.test.ts の旧 describe (appErrorMessage / appErrorHint) は完全削除、\ntoErrorState の 6 件 describe のみ残る。\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 13: docs update (ui-architecture.md + spec Refs)

**Files:**
- Modify: `docs/ui-architecture.md` (§4 lifecycle 規約節を `*ErrorState` 形に書換)
- Modify: `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` (§7 に Phase 2 Refs 追加)

- [ ] **Step 13-1: `docs/ui-architecture.md` §4 を `*ErrorState` 形に書換**

`docs/ui-architecture.md` の §4 で `*ErrorHint` / `*Error` を言及している節を `*ErrorState` 形に書換。具体内容:

- 「`*Error` / `*ErrorHint` 並列構造」「pair atomicity 規約」等の表現 → 「`*ErrorState: ErrorState | null` 単一 field 規約」「型レベル atomicity」に書換
- lifecycle catch path table の field 名を `*Error` から `*ErrorState` に
- `appErrorMessage(e)` / `appErrorHint(e)` 呼び出しの説明 → `toErrorState(e)` 経由の説明
- 「`appErrorMessage` / `appErrorHint` helper」言及 → 削除済 + `toErrorState` の説明

実装時に該当節を Read → 段落単位で書換。表 (cf. spec §5.4 matrix) があれば spec を正として同形に更新。

- [ ] **Step 13-2: spec §7 に Phase 2 完遂 Refs 追加**

Edit `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md` の §7 (関連 doc) の末尾に以下を追記:

```markdown
- [docs/superpowers/specs/2026-05-14-lane-v-phase-2-group-i-design.md](2026-05-14-lane-v-phase-2-group-i-design.md) — Phase 2: `*ErrorState` unified refactor (Issue #694)。本 spec で構築した `*ErrorHint` 並列構造を unified `*ErrorState: ErrorState | null` に集約する後段
```

- [ ] **Step 13-3: markdownlint で docs 更新が CI を破らないことを確認**

Run: `bash scripts/check-markdownlint.sh 2>&1 | tail -10`
Expected: exit 0、新規 violation なし。MD028 (連続 blockquote 間) / MD056 (table cell 内の `|`) 等に注意。

- [ ] **Step 13-4: Commit**

```bash
git add docs/ui-architecture.md docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md
git commit -m "$(printf 'docs: #694 ui-architecture.md §4 と #663 spec §7 を Phase 2 完遂に合わせて update\n\n- docs/ui-architecture.md §4: *Error / *ErrorHint 並列構造の説明を *ErrorState\n  単一 field 規約に書換、lifecycle table を *ErrorState 形に更新、\n  appErrorMessage / appErrorHint 呼び出し言及を toErrorState 経由に置換\n- docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md §7\n  に Phase 2 spec (2026-05-14-lane-v-phase-2-group-i-design.md) の Refs リンク追加\n\nRefs #694\n\nCo-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>')"
```

---

## Task 14: PR Pre-flight + PR 作成 + 実機検証依頼

**Files:**
- No edits — verification + PR creation

- [ ] **Step 14-1: Pre-flight Step 0 (ハードゲート、再確認)**

Run: `gh pr list --search "#694" --state open`
Expected: 0 件。1 件以上見つかれば STOP、Idios に AskUserQuestion で確認。

- [ ] **Step 14-2: Pre-flight Step 1 - 2 (base 同期再確認)**

Run: `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline`
Expected: 取り込み未済 commit があれば touched files との交差判定 (本 PR の touched: `gui/src/state/*.ts` / `gui/src/state/*.test.ts` / `gui/src/lib/appError*` / `gui/src/components/*.tsx` / `gui/src/components/*.test.tsx` / `gui/src/screens/*.tsx` / `gui/src/screens/*.test.tsx` / `docs/ui-architecture.md` / `docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`)。交差なければ continue、交差すれば `git merge origin/develop-0.2.0`。

- [ ] **Step 14-3: Pre-flight Step 3 - 4 (touched file 交差 + 並行 PR 再確認)**

Run: `gh pr list --search "#694" --state all`
Expected: 0 件 + (CLOSED) があれば内容確認 (本 PR との重複なし)。

- [ ] **Step 14-4: 自動チェック全 pass 確認**

Run:

```bash
cd gui && npm run lint -- --max-warnings 0 && npm run typecheck && npm test -- --run && npm run build
cd gui/src-tauri && cargo check && cargo test --lib
bash scripts/check-markdownlint.sh
```

Expected: 全 exit 0、test count は baseline + 6 (toErrorState 新規) - (削除した旧 helper test 件数)。

- [ ] **Step 14-5: PR 本文を作成**

PR 本文には以下を含める (`docs/l2-workflow.md` §Self-Test Report 規約に従う):

```markdown
## 概要

Issue #694 (Lane V Phase 2 / Group I) — `*Error` / `*ErrorHint` 並列構造を unified `*ErrorState: ErrorState | null` に集約する refactor。Phase 1 PR #714 / #716 / #725 / #730 / #733 の規約を完全継承。

## Issue #694 受け入れ条件の逐条検証

(spec §8 の 15 項目を逐条引用 + 対応 commit / diff / test を引用)

## Issue body 誤記の訂正

Issue #694 body は「metadataStore 5 pair」と記載しているが、Phase 1 PR #725 で `conflictError` / `conflictErrorHint` pair が追加され、現状は **6 pair**。本 PR は 6 pair すべてを `*ErrorState` 化する (spec §0 / §7 参照)。

## Self-Test Report

機械検証可能項目 (`[x]`):

- [x] `cd gui && npm run lint -- --max-warnings 0` exit 0
- [x] `cd gui && npm run typecheck` exit 0
- [x] `cd gui && npm test -- --run` 全 pass (baseline + 6 件)
- [x] `cd gui && npm run build` exit 0
- [x] `cd gui/src-tauri && cargo check` exit 0 (Rust 変更なし)
- [x] `cd gui/src-tauri && cargo test --lib` exit 0 (baseline 維持)
- [x] `bash scripts/check-markdownlint.sh` exit 0
- [x] PR Pre-flight Step 0-4 全 pass

機械検証不能項目 (plain bullet `-`):

- Iron Law 6 実機検証 4 経路 (load 失敗 / state.mtime_conflict / restore 失敗 / recent 破損) を Idios PR comment で PASS 確認 → Idios 依頼中

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 14-6: PR push + 作成**

Run:

```bash
git push -u origin claude/romantic-mccarthy-6c34fd
gh pr create --base develop-0.2.0 --head claude/romantic-mccarthy-6c34fd \
  --title 'refactor(gui): #694 *Error / *ErrorHint 並列構造を unified *ErrorState に集約 (Lane V Phase 2)' \
  --body-file <(printf '上記 PR 本文')
```

(本文が長文 + 日本語のため `--body-file -` 経由で `printf` から渡す。HEREDOC でも可。)

- [ ] **Step 14-7: Idios に実機検証 4 経路を AskUserQuestion で依頼**

PR 作成後、AskUserQuestion で以下 4 経路を Idios に依頼:

| 経路 | 確認内容 |
| --- | --- |
| metadata.json load 失敗 (存在しないファイル) | DropScreen / DetectingScreen で `loadErrorState.message` + hint render |
| apply 中の `state.mtime_conflict` (2 process 同時 edit) | ConflictModal で `conflictErrorState.message` + hint + キャンセル補足 1 行 |
| restore 失敗 (backup なしで restore button 押下) | RestoreButton inline で `restoreErrorState.message` + hint |
| recent.json 破損 / 削除 | DropScreen 上部 notice で `loadErrorState` 優先表示 |

Idios の PASS / 修正依頼コメントを待つ。

- [ ] **Step 14-8: `/iterate-review` で review loop 自走**

Run: `/iterate-review <PR#>` (PR 番号は Step 14-6 で取得した値)。
Expected: review-fix ループが収束 (全 finding ゼロ / Round 5 / 発散検知のいずれか)。最終 summary コメントが投稿される。

---

## Self-Review Checklist (plan 完成時に手動チェック)

実装着手前に以下を確認:

- [ ] spec §8 受け入れ条件 15 項目すべてに対応する Task / Step がある
- [ ] 「TBD」「TODO」「fill in details」「Add appropriate ...」等の placeholder ゼロ
- [ ] 型 / signature の一貫性 (`ErrorState` / `toErrorState` / `*ErrorState` field 名)
- [ ] commit メッセージのフォーマット (`type(scope): #694 <description>` + Refs + Co-Authored-By)
- [ ] Iron Law 1 / 3 / 4 / 5 / 6 の遵守確認 (acceptance criteria 引用、scope-guard、Closes 禁止、AskUserQuestion、Pre-flight)
- [ ] 各 Task の Step 数が 4-6 ステップ程度に収まり、各 Step が 2-5 分で完了可能

---

## 補足: 例外的なケースの判断

### Task 6 conflictError condition

`DraftRestoreModal.tsx` line 22 の `if (conflictError) return null;` は ConflictModal 同時表示を回避する規約 (#517 × #514)。本 refactor では `conflictErrorState` truthy 判定に書換 (条件意味は不変)。テスト追加は不要 (既存 test で挙動 pin 済)。

### Task 8 overlayError の `toErrorState` 二重呼び出し回避

PreviewScreen の overlayError 表示で `toErrorState` を 2 回呼ぶことを避けるため `useMemo` または IIFE で 1 回計算する pattern を採用 (実装時に書き味で判断)。perf 影響は微小だが、可読性向上のため。

### Task 14 PR 本文の Self-Test Report

`docs/l2-workflow.md` §「Self-Test Report 規約」で machine-verified `[x]` と machine-unverifiable plain bullet `-` を書き分け。実機検証は plain bullet で Idios 依頼中と明記。

### Iron Law 3 — local useState pair pattern を touch しない理由

DropScreen / PreviewScreen / DetectingScreen / ExportScreen / ConfirmExitModal の local `useState<[error, errorHint]>` pair pattern は本 refactor 対象外。理由: (a) store-level ErrorState 化と概念衝突しないが scope は別軸、(b) local state の集約は component 局所の責務、(c) Iron Law 3 ("ついでに直す" 禁止)。必要なら別 issue (#694 完了後) で扱う。

---

## 補足: 並行 worktree 衝突回避

本 PR は Lane V Phase 2 単独 (parallel worktree なし、roadmap で Phase 2 単線実行)。但し以下と touched files が交差する可能性があるため要確認:

- Lane V Phase 3 (#699 stale docstring update) — 本 PR merge 後着手のため衝突なし
- Lane II-b' Group D #696 (ErrorModal AppError 統合) — `gui/src/lib/appError.ts` を共有する可能性。Pre-flight Step 4 で再確認

衝突検出時は `docs/l2-workflow.md` §「並行 worktree PR 重複再確認」に従い、先着優先 + rebase で対応。
