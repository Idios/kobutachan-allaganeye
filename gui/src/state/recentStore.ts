import { invoke } from '@tauri-apps/api/core';
import { create } from 'zustand';

import { appErrorHint, appErrorMessage } from '../lib/appError';

/**
 * #571 — single entry in the persisted recent-videos history. Mirrors the
 * Rust `RecentEntry` struct (lib.rs).
 *
 * PR #655 Round 2: dropped the `exists` flag. The Rust side now prunes
 * missing files on every `read_recent` / `add_recent` so the frontend
 * always sees a clean list — there's no grey-out / "file not found"
 * notice UX anymore.
 */
export interface RecentEntry {
  path: string;
  fileName: string;
  sizeBytes: number;
  mtimeMs: number;
  addedAtMs: number;
}

export interface RecentState {
  /** Latest snapshot from `~/.allaganeye/recent.json`, newest first. */
  entries: RecentEntry[];
  /** Set true after the first successful `load()` so the UI can skip the empty-state flicker on subsequent re-mounts. */
  loaded: boolean;
  /**
   * Last load failure. #698: DropScreen 上部に inline notice として表示される
   * (history は best-effort UI fluff だが、user に履歴失敗を気づかせるため告知)。
   * dismiss なし、次回 load 成功で自動消去 (recentStore lifecycle)。
   */
  loadError: string | null;
  /** #663: hint for loadError, if AppError carried one. */
  loadErrorHint: string | null;
  /**
   * Last add failure. #698: DropScreen 上部に notice として表示 (loadError 不在
   * 時の fallback)。e.g. when the user dropped a file that was deleted before
   * we could stat it. dismiss なし、次回 add 成功で自動消去。
   */
  addError: string | null;
  /** #663: hint for addError, if AppError carried one. */
  addErrorHint: string | null;

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
  loadErrorHint: null,
  addError: null,
  addErrorHint: null,

  async load() {
    try {
      const result = await invoke<unknown>('read_recent');
      // Defensive: a stray mock or future schema drift could hand us a
      // non-array. Coerce to [] rather than letting `.length` blow up the
      // drop screen. (Tauri command 自体が AppError reject した場合は #698 で
      // DropScreen 上部の inline notice として user に告知される — `read_recent`
      // が値を返している本 path では非対称 fallback として coerce のみ。)
      const entries: RecentEntry[] = Array.isArray(result)
        ? (result as RecentEntry[])
        : [];
      set({ entries, loaded: true, loadError: null, loadErrorHint: null });
    } catch (e) {
      set({
        loadError: appErrorMessage(e),
        loadErrorHint: appErrorHint(e),
        loaded: true,
      });
    }
  },

  async add(path) {
    try {
      const result = await invoke<unknown>('add_recent', { path });
      const entries: RecentEntry[] = Array.isArray(result)
        ? (result as RecentEntry[])
        : [];
      set({ entries, addError: null, addErrorHint: null });
    } catch (e) {
      set({ addError: appErrorMessage(e), addErrorHint: appErrorHint(e) });
    }
  },

  async clear() {
    await invoke<void>('clear_recent');
    set({
      entries: [],
      loadError: null,
      loadErrorHint: null,
      addError: null,
      addErrorHint: null,
    });
  },

  reset() {
    set({
      entries: [],
      loaded: false,
      loadError: null,
      loadErrorHint: null,
      addError: null,
      addErrorHint: null,
    });
  },
}));
