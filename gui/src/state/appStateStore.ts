import { create } from 'zustand';

/**
 * The high-level screen the user is currently on. State transitions between
 * these screens are intentionally represented as an enum (not a URL-based
 * router) because Allagan Eye is a single-window desktop app without
 * browser-history semantics. See docs/ui-architecture.md for the full
 * screen-transition diagram.
 */
export type AppScreen =
  | 'drop'
  | 'detecting'
  | 'complete'
  | 'preview'
  | 'export';

export interface AppState {
  /** Currently rendered screen. */
  screen: AppScreen;
  /** Match chosen on the complete screen, used as entry for preview. */
  selectedMatchIndex: number | null;
  /**
   * Video file path selected on the drop screen. Phase 2 does not yet invoke
   * ffprobe, but this field is reserved for the detect handoff that Phase 3
   * (#465) will implement.
   */
  selectedVideoPath: string | null;

  /** Switch to a different screen. */
  navigate: (screen: AppScreen) => void;
  /** Update the selected match index (null = none). */
  selectMatch: (index: number | null) => void;
  /** Convenience helper: select a match and move to the preview screen. */
  openPreviewFor: (index: number) => void;
  /** Record / clear the in-flight video path that drop picked. */
  setSelectedVideoPath: (path: string | null) => void;
  /** Reset everything back to a freshly launched state (screen = 'drop'). */
  reset: () => void;
}

export const useAppStateStore = create<AppState>((set) => ({
  screen: 'drop',
  selectedMatchIndex: null,
  selectedVideoPath: null,

  navigate: (screen) => set({ screen }),
  selectMatch: (selectedMatchIndex) => set({ selectedMatchIndex }),
  openPreviewFor: (index) =>
    set({ selectedMatchIndex: index, screen: 'preview' }),
  setSelectedVideoPath: (selectedVideoPath) => set({ selectedVideoPath }),
  reset: () =>
    set({
      screen: 'drop',
      selectedMatchIndex: null,
      selectedVideoPath: null,
    }),
}));
