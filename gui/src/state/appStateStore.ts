import { create } from 'zustand';

import { stripExtendedPathPrefix } from '../utils/path';

/**
 * The high-level screen the user is currently on. State transitions between
 * these screens are intentionally represented as an enum (not a URL-based
 * router) because Allagan Eye is a single-window desktop app without
 * browser-history semantics. See docs/ui-architecture.md for the full
 * screen-transition diagram.
 *
 * `indicators` was added in #1106 Phase 2 (KO / ASSIST 検出画面)。
 * `clips` was added in #1131 Phase B2 (前後秒数を指定した切り抜き画面)。
 */
export type AppScreen =
  | 'drop'
  | 'detecting'
  | 'complete'
  | 'preview'
  | 'export'
  | 'minimap'
  | 'indicators'
  | 'clips';

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
 * frozen (`AUDIO_FROZEN` in `allaganeye/audio/__init__.py`), so the Fanfare
 * *scan* is skipped regardless of the flag's value.
 *
 * The flag is NOT inert end-to-end: it is part of the detection cache key
 * (`_load_cache_hit` in `allaganeye/commands/split_matches.py`), is persisted
 * into `.detection_cache.json`, and is recorded in `metadata.json` under
 * `detection_params.no_audio`. Flipping it forces a cache miss and a full
 * re-detect. Do not drop it from any of those on the assumption it is dead.
 *
 * The freeze is indefinite with no scheduled review date (#865, still open);
 * the next natural trigger is the two-signal detection re-architecture. #327
 * froze the module and is closed, so it will never "land" -- this is not a
 * pending item. The material for an unfreeze sits next to `AUDIO_FROZEN`.
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
  /**
   * #1136: 検知経路。CLI の `--masked` / `--vtuber` は相互排他 (同時指定は
   * exit 5) なので、真偽値 2 本ではなく 3 値の enum 1 本で表す。
   *
   * - `standard`: 両 flag とも argv に載せない (従来と同一の argv)
   * - `masked`: `--masked` のみ
   * - `vtuber`: `--vtuber` のみ
   */
  detectionPath: DetectionPath;
  /**
   * #1141: `--indicators` (`true`) / `--no-indicators` (`false`)。ON にすると
   * 境界検出と同じ metadata.json に KO / ASSIST のイベント列が 1 回の atomic
   * write で入る。**既定は ON**（CLI 側の既定も ON）— L4 の新機能なので
   * 既存ユーザーの行動を壊さず、ON のまま切り抜きへ進める。
   *
   * コストは 944 秒の録画で約 25 秒 / 2.8 時間で約 4.5 分
   * (`docs/testing-guide.md` §「KO / ASSIST 走査の実測」)。
   */
  indicators: boolean;
}

/**
 * #1136: 検知経路の 3 値。UI の radio 3 択と 1:1 対応する
 * (`docs/ui-interaction-spec.md` §2.1.10.8)。
 */
export type DetectionPath = 'standard' | 'masked' | 'vtuber';

export const DEFAULT_DETECTION_PARAMS: DetectionParams = {
  blackoutThreshold: 15.0,
  workers: 0,
  gpu: null,
  detectionPath: 'standard',
  indicators: true,
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
  /**
   * #893 R2: The output directory last used by ExportScreen.
   * MinimapScreen uses this as its default output dir when set.
   * #928: when unset it falls back to ExportScreen's shared
   * `deriveDefaultOutDir(videoSource)` (the video's parent directory),
   * not the metadata.json parent -- the two screens stay on one basis
   * by construction.
   * In-memory only; reset() clears it.
   */
  lastExportOutputDir: string | null;
  /**
   * #1106 Phase 2: 一度だけ消費される preview のシーク位置 (秒)。
   *
   * IndicatorsScreen が検出イベントの行を押したとき `event.start` を入れ、
   * PreviewScreen が active pane の `video.currentTime` に反映した時点で
   * `null` に戻す。IN / OUT の編集バッファ (`startT` / `endT`) には触らない —
   * これは「その瞬間を見る」ためのシークであり、境界を動かす操作ではない。
   */
  pendingSeekSeconds: number | null;

  /**
   * #1131 Phase B2: プレビューで「クリップ範囲モード」を出すための区間 (絶対秒)。
   *
   * ClipsScreen が `前後秒数` を確定して `{ start, end, matchIndex }` を入れ、
   * PreviewScreen が **その match を開いている間だけ** 範囲バナーと先頭 / 末尾への
   * シークを出す (`matchIndex` が一致しない preview では無視する)。**試合境界
   * (`startT` / `endT`) とは別物**で、クリップは「イベントの前 `pre` 秒〜後 `post` 秒」
   * を試合区間へクランプした区間を指す。`null` なら通常の preview。
   */
  clipRange: {
    start: number;
    end: number;
    matchIndex: number;
    /** #1139: 対象イベントの `metadata.events` の 1 始まり位置 (手動指定の書込先)。 */
    position: number | null;
  } | null;

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
  /** Record the output dir used by the last export start (#893 R2). */
  setLastExportOutputDir: (dir: string | null) => void;
  /** Set / clear the one-shot preview seek position (#1106 Phase 2). */
  setPendingSeekSeconds: (seconds: number | null) => void;
  /** Set / clear the preview clip range (#1131 Phase B2 / #1139). */
  setClipRange: (
    range: {
      start: number;
      end: number;
      matchIndex: number;
      position: number | null;
    } | null,
  ) => void;
  /** Reset everything back to a freshly launched state (screen = 'drop'). */
  reset: () => void;
}

export const useAppStateStore = create<AppState>((set) => ({
  screen: 'drop',
  selectedMatchIndex: null,
  selectedVideoPath: null,
  detectionParams: { ...DEFAULT_DETECTION_PARAMS },
  lastExportOutputDir: null,
  pendingSeekSeconds: null,
  clipRange: null,

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
  // #893 R2: record the export output dir so MinimapScreen can default to it.
  setLastExportOutputDir: (lastExportOutputDir) => set({ lastExportOutputDir }),
  setPendingSeekSeconds: (pendingSeekSeconds) => set({ pendingSeekSeconds }),
  setClipRange: (clipRange) => set({ clipRange }),
  reset: () =>
    set({
      screen: 'drop',
      selectedMatchIndex: null,
      selectedVideoPath: null,
      detectionParams: { ...DEFAULT_DETECTION_PARAMS },
      lastExportOutputDir: null,
      pendingSeekSeconds: null,
      clipRange: null,
    }),
}));
