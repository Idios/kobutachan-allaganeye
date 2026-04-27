export type MatchType = 'fl_match' | 'unknown';

export type TypeOverride = MatchType | 'skip';

export interface DetectionParams {
  sample_interval: number;
  blackout_threshold: number;
  min_match_duration: number;
  min_blackout_duration: number;
  no_audio: boolean;
  use_gpu: number | boolean | null;
  workers: number | null;
}

export interface Match {
  index: number;
  start_time: number;
  end_time: number;
  start_display: string;
  end_display: string;
  duration: number;
  duration_display: string;
  type: MatchType;
  output_file: string;
  name?: string;
  type_override?: TypeOverride;
  edited?: { start_time: number; end_time: number };
}

export interface Gap {
  start_time: number;
  end_time: number;
  start_display: string;
  end_display: string;
  duration: number;
  duration_display: string;
}

/**
 * #518 -- structured warning scaffold. The writer currently emits `[]`;
 * future detection codes populate individual entries. Readers should
 * pass unknown `code` values through unchanged.
 */
export type WarningSeverity = 'info' | 'warn' | 'error';

export interface MetadataWarning {
  code: string;
  message_en?: string;
  severity?: WarningSeverity;
  context?: Record<string, unknown>;
}

/**
 * #591 -- GPU vendor probe snapshot recorded by detect/split.
 *
 * - `gpu_vendors_available`: vendors detected via `probe_gpu_vendors()`
 *   (subset of `{"nvidia","amd","intel"}`).
 * - `gpu_vendor_used`: vendor actually consumed by GPU decode in this
 *   detect run. `null` when CPU was forced (`--no-gpu`), the cache hit
 *   skipped detection, or the run came from `split --from-metadata`.
 * - `vendor_preference`: snapshot of `gpu_detector._VENDOR_PREFERENCE`
 *   used to resolve auto-selection (currently
 *   `["nvidia","amd","intel"]`).
 *
 * GUI export uses these to pick H.264 encoder via
 * `select_h264_encoder_for_export` Tauri command.
 */
export interface SystemInfo {
  gpu_vendors_available: string[];
  gpu_vendor_used: string | null;
  vendor_preference: string[];
}

export interface Metadata {
  /**
   * #515: schema revision declaration. Optional on the TS type because
   * pre-0.2.0 files don't carry the field; readers treat missing as v1.
   * New writes always emit `"1"`.
   */
  schema_version?: '1';
  source: string;
  source_duration: number;
  source_duration_display: string;
  /**
   * #465 review: source recording frame rate (e.g. 60, 119.88, 240).
   * Optional because pre-0.2.0 metadata.json files omitted the field;
   * readers default to {@link import('./metadata.schema').DEFAULT_FPS}
   * (60) when absent.
   */
  source_fps?: number;
  detected_at: string;
  detection_params: DetectionParams;
  matches: Match[];
  gaps: Gap[];
  /** #518 -- optional on the TS type because legacy files don't emit it. */
  warnings?: MetadataWarning[];
  /**
   * #591 -- GPU vendor probe snapshot. Optional because pre-#591
   * metadata.json files don't carry the field; ExportScreen falls back
   * to libx264 when missing.
   */
  system_info?: SystemInfo;
}
