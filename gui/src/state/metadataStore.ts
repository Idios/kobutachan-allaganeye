import { invoke } from '@tauri-apps/api/core';
import { create } from 'zustand';

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

  load: (path: string) => Promise<void>;
  updateMatch: (index: number, patch: MatchEditPatch) => void;
  apply: () => Promise<void>;
  reset: () => void;
  clear: () => void;
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

export const useMetadataStore = create<MetadataState>((set, get) => ({
  metadata: null,
  filePath: null,
  dirty: false,
  loadError: null,
  applying: false,
  applyError: null,

  load: async (path) => {
    try {
      const raw = await invoke<unknown>('load_metadata', { path });
      const parsed = MetadataSchema.parse(raw);
      set({
        metadata: parsed as unknown as Metadata,
        filePath: path,
        dirty: false,
        loadError: null,
        applyError: null,
      });
    } catch (e) {
      set({
        metadata: null,
        filePath: null,
        dirty: false,
        loadError: e instanceof Error ? e.message : String(e),
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
    const { metadata, filePath } = get();
    if (!metadata || !filePath) return;
    set({ applying: true, applyError: null });
    try {
      const normalized = normalizeForPersistence(metadata);
      await invoke('apply_changes', {
        path: filePath,
        metadata: normalized,
      });
      set({
        metadata: normalized,
        dirty: false,
        applying: false,
        applyError: null,
      });
    } catch (e) {
      set({
        applying: false,
        applyError: e instanceof Error ? e.message : String(e),
      });
    }
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
    });
  },
}));
