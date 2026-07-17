import { create } from 'zustand';

import { stripExtendedPathPrefix } from '../utils/path';

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
  | 'export'
  | 'minimap';

/**
 * #613: User-tunable detect parameters surfaced from the DropScreen "詳細設定"
 * panel and forwarded to `start_detect` (Rust Tauri command, #569). All
 * fields are optional in the sense that a value matching the default leaves
 * the corresponding CLI flag off the argv (see `detect_command_args` in
 * `gui/src-tauri/src/lib.rs`).
 *
 * Held in-memory only — `reset()` returns these to defaults; there is no
 * localStorage persistence in #613 (deliberately deferred to a follow-up).
 *
 * NOTE: `--no-audio` is intentionally NOT exposed here. The audio module is
 * frozen (`AUDIO_FROZEN` in `allaganeye/commands/split_matches.py:525`,
 * #327), so the flag is a no-op until Fanfare scan ships. Re-add when
 * #327 lands.
 */
export interface DetectionParams {
  /** `--blackout-threshold {x}`. CLI default 15.0, valid range 0-255. */
  blackoutThreshold: number;
  /** `--workers {n}` when > 0; 0 means "auto" (omit flag, CLI picks). */
  workers: number;
  /**
   * `--gpu` when `true`, `--no-gpu` when `false`, omit flag for `null` (auto
   * — Rust side picks vendor by preference order).
   */
  gpu: boolean | null;
}

export const DEFAULT_DETECTION_PARAMS: DetectionParams = {
  blackoutThreshold: 15.0,
  workers: 0,
  gpu: null,
};

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
  /**
   * #613: detect parameters tuned on the drop screen and forwarded to
   * `start_detect`. In-memory only; `reset()` restores defaults.
   */
  detectionParams: DetectionParams;

  /** Switch to a different screen. */
  navigate: (screen: AppScreen) => void;
  /** Update the selected match index (null = none). */
  selectMatch: (index: number | null) => void;
  /** Convenience helper: select a match and move to the preview screen. */
  openPreviewFor: (index: number) => void;
  /** Record / clear the in-flight video path that drop picked. */
  setSelectedVideoPath: (path: string | null) => void;
  /** Patch one or more detect parameters. */
  setDetectionParams: (patch: Partial<DetectionParams>) => void;
  /** Restore detect parameters to defaults. */
  resetDetectionParams: () => void;
  /** Reset everything back to a freshly launched state (screen = 'drop'). */
  reset: () => void;
}

export const useAppStateStore = create<AppState>((set) => ({
  screen: 'drop',
  selectedMatchIndex: null,
  selectedVideoPath: null,
  detectionParams: { ...DEFAULT_DETECTION_PARAMS },

  navigate: (screen) => set({ screen }),
  selectMatch: (selectedMatchIndex) => set({ selectedMatchIndex }),
  openPreviewFor: (index) =>
    set({ selectedMatchIndex: index, screen: 'preview' }),
  // #545 review (2026-04-25): Tauri dialog/drag-drop が Windows で返す
  // `\\?\` extended-length path prefix を保存前に正規化する。これで
  // selectedVideoPath を読む全 consumer (ExportScreen の videoSource、
  // PreviewScreen の register_video / generate_match_thumbnails、UI 表示)
  // が一貫して prefix なしの path を扱える。
  setSelectedVideoPath: (selectedVideoPath) =>
    set({
      selectedVideoPath:
        selectedVideoPath === null
          ? null
          : stripExtendedPathPrefix(selectedVideoPath),
    }),
  setDetectionParams: (patch) =>
    set((s) => ({ detectionParams: { ...s.detectionParams, ...patch } })),
  resetDetectionParams: () =>
    set({ detectionParams: { ...DEFAULT_DETECTION_PARAMS } }),
  reset: () =>
    set({
      screen: 'drop',
      selectedMatchIndex: null,
      selectedVideoPath: null,
      detectionParams: { ...DEFAULT_DETECTION_PARAMS },
    }),
}));
