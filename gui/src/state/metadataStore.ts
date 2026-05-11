import { invoke } from '@tauri-apps/api/core';
import { create } from 'zustand';

import { appErrorCodeIs, appErrorHint, appErrorMessage } from '../lib/appError';
import { sampleMetadata } from '../data/sampleMetadata';
import type { Match, Metadata, TypeOverride } from '../types/metadata';
import { MetadataSchema } from '../types/metadata.schema';

export type MatchEditPatch = Partial<
  Pick<Match, 'name' | 'type_override' | 'edited'>
>;

/**
 * Normalize a filesystem path for source-equality comparison (#517, review).
 *
 * The current platform is Windows-only (see CLAUDE.md), so two paths that
 * differ only in separator (`\` vs `/`) or letter case should be treated as
 * pointing at the same file. Without normalization a draft whose source was
 * captured with one convention is dropped as stale even though it's the same
 * video — the draft the user was editing would be silently discarded.
 */
function normalizeSourcePath(p: string): string {
  return p.replace(/\\/g, '/').toLowerCase();
}

export interface MetadataState {
  metadata: Metadata | null;
  filePath: string | null;
  dirty: boolean;
  loadError: string | null;
  /** #663: hint for loadError, if AppError carried one. */
  loadErrorHint: string | null;
  applying: boolean;
  applyError: string | null;
  /** #663: hint for applyError, if AppError carried one. */
  applyErrorHint: string | null;

  /** #516: flips true after a successful `apply()` that created metadata.original.json. */
  hasBackup: boolean;
  /** #516: in-flight restore flag. */
  restoring: boolean;
  /** #516: last restore error message, if any. */
  restoreError: string | null;
  /** #663: hint for restoreError, if AppError carried one. */
  restoreErrorHint: string | null;

  /**
   * #514: mtime (ms since epoch) of metadata.json recorded at load time.
   * Passed to `apply_changes` so Rust can refuse to overwrite a file that
   * was modified externally between load and apply. `null` when no file is
   * loaded (sample mode or after `clear()`).
   */
  loadedMtimeMs: number | null;
  /**
   * #514: last conflict error produced by apply. Non-null means the UI must
   * surface the "overwrite / reload / cancel" modal. Resolved via
   * `applyOverwrite` / `reloadAfterConflict` / `dismissConflict`.
   */
  conflictError: string | null;
  /**
   * #517: a draft snapshot loaded from metadata.draft.json that differs from
   * the live metadata on disk. Non-null means the UI should ask the user
   * whether to restore or discard. Resolved via `restoreDraft()` /
   * `discardDraft()`.
   */
  pendingDraft: Metadata | null;
  /** #517: last draft load error (corrupt draft / parse failure). */
  draftLoadError: string | null;
  /** #663: hint for draftLoadError, if AppError carried one. */
  draftLoadErrorHint: string | null;
  /** #517: true while an auto-save (debounced saveDraft) is in flight. */
  draftSaving: boolean;
  /**
   * #517: last draft save error (disk full / permission denied / atomic
   * rename failure). Cleared on the next successful save. Surfacing this in
   * state lets the UI notify the user — otherwise save failures are silent
   * unhandled rejections and the "restore after crash" contract is weakened
   * (a save that never landed cannot be restored).
   */
  draftSaveError: string | null;
  /** #663: hint for draftSaveError, if AppError carried one. */
  draftSaveErrorHint: string | null;

  load: (path: string) => Promise<void>;
  updateMatch: (index: number, patch: MatchEditPatch) => void;
  apply: () => Promise<void>;
  reset: () => void;
  clear: () => void;

  /** #516: atomically copy metadata.original.json back over metadata.json, then reload. */
  restore: () => Promise<void>;
  /** #516: re-probe the filesystem to update hasBackup. Called after load / apply / restore. */
  refreshBackupStatus: () => Promise<void>;

  /** #514: re-apply with the mtime check bypassed (overwrite external edits). */
  applyOverwrite: () => Promise<void>;
  /** #514: discard in-memory edits and re-load metadata.json from disk. */
  reloadAfterConflict: () => Promise<void>;
  /** #514: close the conflict modal without side effects (edits stay in store). */
  dismissConflict: () => void;

  /** #517: write the current in-memory metadata to metadata.draft.json. */
  saveDraft: () => Promise<void>;
  /** #517: probe the filesystem for a draft; populates `pendingDraft` if the
   *  draft is valid and references the same source. Call after `load()`. */
  loadDraft: () => Promise<void>;
  /** #517: delete metadata.draft.json (post-apply cleanup). */
  clearDraft: () => Promise<void>;
  /** #517: apply `pendingDraft` to `metadata` and mark the store dirty so the
   *  user can re-apply. Does NOT touch disk — user still needs to press 適用. */
  restoreDraft: () => void;
  /** #517: drop `pendingDraft` and delete the on-disk draft file. */
  discardDraft: () => Promise<void>;

  /**
   * #589: drop in-memory edits and reset the store to the last persisted state.
   * Used by preview screen `[◀ 一覧へ]` / `[書き出し →]` confirm-OK paths
   * (silent loss prevention per ui-interaction-spec.md §1.3).
   *
   * Real mode (`filePath` あり): cancel any pending draft auto-save, drop the
   * on-disk draft so the next `load()` does not re-surface it as
   * `pendingDraft`, then re-load metadata.json. `dirty` becomes false.
   *
   * Sample mode (`filePath === null`): no disk to reload from — reset to the
   * sample fixture so the next preview re-entry sees pristine values.
   */
  discardEdits: () => Promise<void>;

  /** Phase 2 only: load the in-memory sample metadata (no filePath set). */
  loadSample: () => void;
}

const PERSISTABLE_TYPES = new Set<TypeOverride>(['fl_match', 'unknown']);

/** #517: draft auto-save debounce interval. Module-scoped so tests can
 *  override by importing `setDraftSaveDelay`. */
let draftSaveDelayMs = 500;
export function setDraftSaveDelay(ms: number): void {
  draftSaveDelayMs = ms;
}
let draftSaveTimer: ReturnType<typeof setTimeout> | null = null;
function scheduleDraftSave(trigger: () => void): void {
  if (draftSaveTimer !== null) {
    clearTimeout(draftSaveTimer);
  }
  draftSaveTimer = setTimeout(() => {
    draftSaveTimer = null;
    trigger();
  }, draftSaveDelayMs);
}
function cancelDraftSave(): void {
  if (draftSaveTimer !== null) {
    clearTimeout(draftSaveTimer);
    draftSaveTimer = null;
  }
}

function normalizeForPersistence(metadata: Metadata): Metadata {
  return {
    ...metadata,
    matches: metadata.matches.map((m) => {
      const start_time = m.edited?.start_time ?? m.start_time;
      const end_time = m.edited?.end_time ?? m.end_time;
      const duration = Math.max(0, end_time - start_time);
      const nextType =
        m.type_override && PERSISTABLE_TYPES.has(m.type_override)
          ? (m.type_override as 'fl_match' | 'unknown')
          : m.type;
      return {
        index: m.index,
        start_time,
        end_time,
        start_display: m.start_display,
        end_display: m.end_display,
        duration,
        duration_display: m.duration_display,
        type: nextType,
        output_file: m.output_file,
      };
    }),
  };
}

export const useMetadataStore = create<MetadataState>((set, get) => {
  /**
   * #514 shared implementation for `apply` / `applyOverwrite`. When
   * `overwrite` is true the stored `loadedMtimeMs` is discarded so the Rust
   * side skips the conflict check.
   */
  async function runApply(overwrite: boolean): Promise<void> {
    const { metadata, filePath, loadedMtimeMs } = get();
    if (!metadata || !filePath) return;
    set({ applying: true, applyError: null, applyErrorHint: null, conflictError: null });
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
        applyError: null,
        applyErrorHint: null,
        loadedMtimeMs: newMtime,
        conflictError: null,
      });
      await get().refreshBackupStatus();
      // #517: successful apply means the on-disk state caught up with our
      // edits, so drop the draft.
      cancelDraftSave();
      await get().clearDraft();
    } catch (e) {
      const msg = appErrorMessage(e);
      const hint = appErrorHint(e);
      // #663: PR #665 で全 23 commands が AppError 化済のため、legacy raw String
      // fallback (msg.startsWith('conflict:')) は廃止する。code === 'state.mtime_conflict'
      // のみで分岐する。
      if (appErrorCodeIs(e, 'state.mtime_conflict')) {
        set({ applying: false, conflictError: msg });
      } else {
        set({ applying: false, applyError: msg, applyErrorHint: hint });
      }
    }
  }

  return {
  metadata: null,
  filePath: null,
  dirty: false,
  loadError: null,
  loadErrorHint: null,
  applying: false,
  applyError: null,
  applyErrorHint: null,

  hasBackup: false,
  restoring: false,
  restoreError: null,
  restoreErrorHint: null,

  loadedMtimeMs: null,
  conflictError: null,
  pendingDraft: null,
  draftLoadError: null,
  draftLoadErrorHint: null,
  draftSaving: false,
  draftSaveError: null,
  draftSaveErrorHint: null,

  load: async (path) => {
    try {
      const raw = await invoke<unknown>('load_metadata', { path });
      const parsed = MetadataSchema.parse(raw);
      // #514: record mtime alongside contents so subsequent apply can detect
      // external modifications. A missing mtime (file vanished between the
      // two calls) is recorded as null; apply will then skip the check.
      const mtime = await invoke<number | null>('get_metadata_mtime', { path });
      set({
        metadata: parsed as unknown as Metadata,
        filePath: path,
        dirty: false,
        loadError: null,
        loadErrorHint: null,
        applyError: null,
        applyErrorHint: null,
        restoreError: null,
        restoreErrorHint: null,
        loadedMtimeMs: mtime ?? null,
        conflictError: null,
        pendingDraft: null,
        draftLoadError: null,
        draftLoadErrorHint: null,
        draftSaveError: null,
        draftSaveErrorHint: null,
      });
      await get().refreshBackupStatus();
      // #517: automatically probe for a draft after a successful load. If one
      // exists and references the same source, the UI will surface a restore
      // modal via `pendingDraft`.
      await get().loadDraft();
    } catch (e) {
      // #691 案 X: catch path は self-only (loadError/loadErrorHint のみ set)。
      // apply / restore / draft 系の旧 error は別経路の文脈なので保持する
      // (load 失敗時に user に見せる context を消さない設計、lifecycle 終端
      // clear() / loadSample() でのみ全 *ErrorHint を null reset する規約)。
      set({
        metadata: null,
        filePath: null,
        dirty: false,
        loadError: appErrorMessage(e),
        loadErrorHint: appErrorHint(e),
        hasBackup: false,
        loadedMtimeMs: null,
        conflictError: null,
        pendingDraft: null,
      });
    }
  },

  updateMatch: (index, patch) => {
    const state = get();
    if (!state.metadata) return;
    const matches = state.metadata.matches.map((m) =>
      m.index === index ? { ...m, ...patch } : m,
    );
    set({
      metadata: { ...state.metadata, matches },
      dirty: true,
    });
    // #517: auto-save the edit buffer. Only makes sense when a real file is
    // loaded (sample mode has no backing path).
    if (get().filePath) {
      scheduleDraftSave(() => {
        void get().saveDraft();
      });
    }
  },

  apply: async () => {
    await runApply(false);
  },

  reset: () => {
    set({ dirty: false });
  },

  clear: () => {
    cancelDraftSave();
    set({
      metadata: null,
      filePath: null,
      dirty: false,
      loadError: null,
      loadErrorHint: null,
      applying: false,
      applyError: null,
      applyErrorHint: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      restoreErrorHint: null,
      loadedMtimeMs: null,
      conflictError: null,
      pendingDraft: null,
      draftLoadError: null,
      draftLoadErrorHint: null,
      draftSaving: false,
      draftSaveError: null,
      draftSaveErrorHint: null,
    });
  },

  restore: async () => {
    const { filePath } = get();
    if (!filePath) return;
    set({ restoring: true, restoreError: null, restoreErrorHint: null });
    try {
      await invoke('restore_from_original', { path: filePath });
      // Reload metadata from disk; load() also refreshes hasBackup.
      await get().load(filePath);
      set({ restoring: false });
    } catch (e) {
      set({
        restoring: false,
        restoreError: appErrorMessage(e),
        restoreErrorHint: appErrorHint(e),
      });
    }
  },

  refreshBackupStatus: async () => {
    const { filePath } = get();
    if (!filePath) {
      set({ hasBackup: false });
      return;
    }
    try {
      const exists = await invoke<boolean>('check_backup_exists', {
        path: filePath,
      });
      set({ hasBackup: !!exists });
    } catch {
      // Fall back to hasBackup=false on any probing error; not fatal.
      set({ hasBackup: false });
    }
  },

  applyOverwrite: async () => {
    await runApply(true);
  },

  reloadAfterConflict: async () => {
    const { filePath } = get();
    if (!filePath) {
      set({ conflictError: null });
      return;
    }
    await get().load(filePath);
  },

  dismissConflict: () => {
    set({ conflictError: null });
  },

  saveDraft: async () => {
    const { filePath, metadata } = get();
    if (!filePath || !metadata) return;
    // Clear any prior save error up-front so consumers see a fresh attempt.
    set({ draftSaving: true, draftSaveError: null, draftSaveErrorHint: null });
    try {
      await invoke('save_draft', { path: filePath, draft: metadata });
    } catch (e) {
      // Surface the failure via state — scheduleDraftSave's fire-and-forget
      // call would otherwise swallow the rejection silently (see F1 review).
      set({
        draftSaveError: appErrorMessage(e),
        draftSaveErrorHint: appErrorHint(e),
      });
    } finally {
      set({ draftSaving: false });
    }
  },

  loadDraft: async () => {
    const { filePath, metadata } = get();
    if (!filePath || !metadata) return;
    try {
      const raw = await invoke<unknown>('load_draft', { path: filePath });
      if (raw === null || raw === undefined) {
        set({ pendingDraft: null, draftLoadError: null, draftLoadErrorHint: null });
        return;
      }
      const parsed = MetadataSchema.parse(raw) as unknown as Metadata;
      // #517: if the draft was produced against a different source video,
      // it's stale — drop it rather than offering restore on the wrong file.
      // Normalize separator + case (Windows only) so the same file captured
      // with `C:\...` vs `C:/...` or `...MKV` vs `...mkv` round-trips as equal.
      if (
        normalizeSourcePath(parsed.source) !==
        normalizeSourcePath(metadata.source)
      ) {
        await invoke('clear_draft', { path: filePath });
        set({ pendingDraft: null, draftLoadError: null, draftLoadErrorHint: null });
        return;
      }
      set({ pendingDraft: parsed, draftLoadError: null, draftLoadErrorHint: null });
    } catch (e) {
      set({
        pendingDraft: null,
        draftLoadError: appErrorMessage(e),
        draftLoadErrorHint: appErrorHint(e),
      });
    }
  },

  clearDraft: async () => {
    const { filePath } = get();
    if (!filePath) {
      set({ pendingDraft: null });
      return;
    }
    try {
      await invoke('clear_draft', { path: filePath });
    } finally {
      set({ pendingDraft: null });
    }
  },

  restoreDraft: () => {
    const { pendingDraft } = get();
    if (!pendingDraft) return;
    // Apply the draft to the store as an in-memory edit. The user still has
    // to press 適用 to persist, which mirrors the normal edit flow and gives
    // them a chance to back out.
    set({
      metadata: pendingDraft,
      dirty: true,
      pendingDraft: null,
    });
  },

  discardDraft: async () => {
    await get().clearDraft();
  },

  discardEdits: async () => {
    const { filePath } = get();
    cancelDraftSave();
    if (filePath) {
      // #589: drop the on-disk draft first so the trailing loadDraft() inside
      // load() does not re-surface the discarded edits as pendingDraft.
      try {
        await get().clearDraft();
      } catch {
        // draft may not exist; the subsequent load() is the source of truth
      }
      await get().load(filePath);
    } else {
      get().loadSample();
    }
  },

  loadSample: () => {
    cancelDraftSave();
    set({
      metadata: sampleMetadata,
      filePath: null,
      dirty: false,
      loadError: null,
      loadErrorHint: null,
      applying: false,
      applyError: null,
      applyErrorHint: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      restoreErrorHint: null,
      loadedMtimeMs: null,
      conflictError: null,
      pendingDraft: null,
      draftLoadError: null,
      draftLoadErrorHint: null,
      draftSaving: false,
      draftSaveError: null,
      draftSaveErrorHint: null,
    });
  },
  };
});
