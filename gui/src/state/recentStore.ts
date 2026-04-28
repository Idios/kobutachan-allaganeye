import { invoke } from '@tauri-apps/api/core';
import { create } from 'zustand';

/**
 * #571 — single entry in the persisted recent-videos history. Mirrors the
 * Rust `RecentEntryView` (lib.rs): the persisted fields plus a freshly
 * evaluated `exists` flag. `exists` is recomputed on every `load_recent`
 * round-trip; the GUI uses it to grey out items whose underlying file has
 * been moved or deleted.
 */
export interface RecentEntryView {
  path: string;
  fileName: string;
  sizeBytes: number;
  mtimeMs: number;
  addedAtMs: number;
  exists: boolean;
}

export interface RecentState {
  /** Latest snapshot from `~/.allaganeye/recent.json`, newest first. */
  entries: RecentEntryView[];
  /** Set true after the first successful `load()` so the UI can skip the empty-state flicker on subsequent re-mounts. */
  loaded: boolean;
  /** Last load failure, surfaced for tests / debug log; the drop screen ignores it (history is best-effort). */
  loadError: string | null;
  /** Last add failure, e.g. when the user dropped a file that was deleted before we could stat it. */
  addError: string | null;

  /** Read history from disk. Idempotent — safe to call on every DropScreen mount. */
  load: () => Promise<void>;
  /** Persist `path` to history (moves to top when already present), updating `entries` from the post-write snapshot. */
  add: (path: string) => Promise<void>;
  /** Wipe history both on disk and in memory. */
  clear: () => Promise<void>;
  /** Test helper — discard in-memory state without touching disk. */
  reset: () => void;
}

export const useRecentStore = create<RecentState>((set) => ({
  entries: [],
  loaded: false,
  loadError: null,
  addError: null,

  async load() {
    try {
      const result = await invoke<unknown>('read_recent');
      // Defensive: a stray mock or future schema drift could hand us a
      // non-array. Coerce to [] rather than letting `.length` blow up the
      // drop screen — the history is best-effort UI fluff.
      const entries: RecentEntryView[] = Array.isArray(result)
        ? (result as RecentEntryView[])
        : [];
      set({ entries, loaded: true, loadError: null });
    } catch (e) {
      set({
        loadError: e instanceof Error ? e.message : String(e),
        loaded: true,
      });
    }
  },

  async add(path) {
    try {
      const result = await invoke<unknown>('add_recent', { path });
      const entries: RecentEntryView[] = Array.isArray(result)
        ? (result as RecentEntryView[])
        : [];
      set({ entries, addError: null });
    } catch (e) {
      set({ addError: e instanceof Error ? e.message : String(e) });
    }
  },

  async clear() {
    await invoke<void>('clear_recent');
    set({ entries: [], loadError: null, addError: null });
  },

  reset() {
    set({ entries: [], loaded: false, loadError: null, addError: null });
  },
}));
