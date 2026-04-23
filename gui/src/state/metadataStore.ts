import { invoke } from '@tauri-apps/api/core';
import { create } from 'zustand';

import { sampleMetadata } from '../data/sampleMetadata';
import type { Match, Metadata, TypeOverride } from '../types/metadata';
import { MetadataSchema } from '../types/metadata.schema';

export type MatchEditPatch = Partial<
  Pick<Match, 'name' | 'type_override' | 'edited'>
>;

export interface MetadataState {
  metadata: Metadata | null;
  filePath: string | null;
  dirty: boolean;
  loadError: string | null;
  applying: boolean;
  applyError: string | null;

  /** #516: flips true after a successful `apply()` that created metadata.original.json. */
  hasBackup: boolean;
  /** #516: in-flight restore flag. */
  restoring: boolean;
  /** #516: last restore error message, if any. */
  restoreError: string | null;

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

  /** Phase 2 only: load the in-memory sample metadata (no filePath set). */
  loadSample: () => void;
}

const PERSISTABLE_TYPES = new Set<TypeOverride>(['fl_match', 'unknown']);

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
    set({ applying: true, applyError: null, conflictError: null });
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
        loadedMtimeMs: newMtime,
        conflictError: null,
      });
      await get().refreshBackupStatus();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.startsWith('conflict:')) {
        set({ applying: false, conflictError: msg });
      } else {
        set({ applying: false, applyError: msg });
      }
    }
  }

  return {
  metadata: null,
  filePath: null,
  dirty: false,
  loadError: null,
  applying: false,
  applyError: null,

  hasBackup: false,
  restoring: false,
  restoreError: null,

  loadedMtimeMs: null,
  conflictError: null,

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
        applyError: null,
        restoreError: null,
        loadedMtimeMs: mtime ?? null,
        conflictError: null,
      });
      await get().refreshBackupStatus();
    } catch (e) {
      set({
        metadata: null,
        filePath: null,
        dirty: false,
        loadError: e instanceof Error ? e.message : String(e),
        hasBackup: false,
        loadedMtimeMs: null,
        conflictError: null,
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
  },

  apply: async () => {
    await runApply(false);
  },

  reset: () => {
    set({ dirty: false });
  },

  clear: () => {
    set({
      metadata: null,
      filePath: null,
      dirty: false,
      loadError: null,
      applying: false,
      applyError: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      loadedMtimeMs: null,
      conflictError: null,
    });
  },

  restore: async () => {
    const { filePath } = get();
    if (!filePath) return;
    set({ restoring: true, restoreError: null });
    try {
      await invoke('restore_from_original', { path: filePath });
      // Reload metadata from disk; load() also refreshes hasBackup.
      await get().load(filePath);
      set({ restoring: false });
    } catch (e) {
      set({
        restoring: false,
        restoreError: e instanceof Error ? e.message : String(e),
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

  loadSample: () => {
    set({
      metadata: sampleMetadata,
      filePath: null,
      dirty: false,
      loadError: null,
      applying: false,
      applyError: null,
      hasBackup: false,
      restoring: false,
      restoreError: null,
      loadedMtimeMs: null,
      conflictError: null,
    });
  },
  };
});
