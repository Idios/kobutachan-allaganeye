/**
 * AUTO-GENERATED -- DO NOT EDIT.
 * Regenerate with `python scripts/codegen/generate.py` (issue #612).
 * Source: schemas/metadata.schema.json
 */

/**
 * metadata.json contract between allaganeye CLI and the L2a Tauri GUI (#463). Machine-readable source of truth (#612). The human-readable counterpart lives in docs/metadata-spec.md; refine-style semantic constraints (e.g. end_time >= start_time) are enforced by zod (GUI) and InputFileError checks (CLI), not by this schema.
 */
export interface Metadata {
  /**
   * Payload schema revision (#515). New writes always emit "1"; missing field is interpreted as v1 for backward compat with pre-#515 outputs.
   */
  schema_version?: '1';
  /**
   * Absolute path of the source video file as written by the OS that produced metadata.json.
   */
  source: string;
  /**
   * Total length of the source video in seconds.
   */
  source_duration: number;
  /**
   * Human-readable duration (HH:MM:SS or MM:SS).
   */
  source_duration_display: string;
  /**
   * Source recording frame rate (#465). Optional for backward compat with pre-0.2.0 metadata.json that omitted the field; readers default to DEFAULT_FPS (60) when absent.
   */
  source_fps?: number;
  /**
   * ISO 8601 UTC timestamp of when detection ran.
   */
  detected_at: string;
  /**
   * ISO 8601 UTC wall-clock timestamp captured at the start of the detect pipeline (#586). Equal to `detected_at` for backward compat. New writers always emit it; pre-#586 metadata.json may omit the field (readers fall back to `detected_at`).
   */
  detection_started_at?: string;
  /**
   * ISO 8601 UTC wall-clock timestamp captured immediately before metadata.json is written (#586). GUI CompleteScreen displays elapsed = completed - started in the「所要」column. Pre-#586 metadata.json may omit the field.
   */
  detection_completed_at?: string;
  detection_params: DetectionParams;
  /**
   * Match segments (zero or more).
   */
  matches: Match[];
  /**
   * Inter-match idle gaps >= 5 minutes (zero or more).
   */
  gaps: Gap[];
  /**
   * Structured warnings emitted during detection (#518). New writers always emit an array (possibly empty); missing field is accepted for legacy compatibility.
   */
  warnings?: MetadataWarning[];
  system_info?: SystemInfo;
  brightness_samples?: BrightnessSamples;
}
/**
 * Parameters used by the detector when this metadata.json was produced.
 */
export interface DetectionParams {
  /**
   * Pass 1 sampling interval in seconds.
   */
  sample_interval: number;
  /**
   * Brightness threshold (0-255) below which a frame is considered blackout.
   */
  blackout_threshold: number;
  /**
   * Minimum match duration in seconds.
   */
  min_match_duration: number;
  /**
   * Minimum blackout duration in seconds.
   */
  min_blackout_duration: number;
  /**
   * True when the audio promotion stage was skipped.
   */
  no_audio: boolean;
  /**
   * GPU mode setting. number/boolean for explicit selection, null for auto.
   */
  use_gpu: number | boolean | null;
  /**
   * Parallel worker count. number for explicit, null for auto.
   */
  workers: number | null;
}
/**
 * Single match segment. JSON Schema is the strict writer contract; reader-side passthrough for GUI-only edit fields (name / type_override / edited) is provided by zod (.passthrough() on MatchSchema) and only round-trips inside metadata.draft.json, never metadata.json proper.
 */
export interface Match {
  /**
   * 1-based ordinal of the match within the source video.
   */
  index: number;
  /**
   * Match start in seconds (>= 0).
   */
  start_time: number;
  /**
   * Match end in seconds (>= start_time; constraint enforced at runtime by zod / InputFileError, not by this schema).
   */
  end_time: number;
  /**
   * Human-readable start (MM:SS or H:MM:SS).
   */
  start_display: string;
  /**
   * Human-readable end.
   */
  end_display: string;
  /**
   * Match length in seconds.
   */
  duration: number;
  /**
   * Human-readable duration (e.g. 15m15s).
   */
  duration_display: string;
  /**
   * Detected match classification.
   */
  type: 'fl_match' | 'unknown';
  /**
   * MP4 filename relative to the metadata.json directory.
   */
  output_file: string;
}
/**
 * Inter-match idle gap >= 5 minutes (min_gap=300.0).
 */
export interface Gap {
  start_time: number;
  /**
   * Gap end (>= start_time; constraint enforced at runtime, not by this schema).
   */
  end_time: number;
  start_display: string;
  end_display: string;
  duration: number;
  duration_display: string;
}
/**
 * Structured warning entry (#518). Future codes should be appended to allaganeye/detection/warnings.py::WARNING_CODES; readers must accept unknown codes (forward compat).
 */
export interface MetadataWarning {
  /**
   * Warning code key (e.g. "audio_skipped").
   */
  code: string;
  /**
   * English message; readers fall back to WARNING_CODES lookup when omitted.
   */
  message_en?: string;
  severity?: 'info' | 'warn' | 'error';
  /**
   * Code-specific extra information.
   */
  context?: {
    [k: string]: unknown;
  };
}
/**
 * GPU vendor probe snapshot recorded by detect/split (#591). GUI export uses this to pick the H.264 encoder (NVENC / QSV / AMF / libx264). Optional at the root because pre-#591 metadata.json files don't carry it.
 */
export interface SystemInfo {
  /**
   * Vendors detected via probe_gpu_vendors() — subset of {"nvidia","amd","intel"}. Empty array means CPU-only host.
   */
  gpu_vendors_available: string[];
  /**
   * Vendor actually consumed by GPU decode in this run. null when CPU was forced (--no-gpu), the cache hit skipped detection, or the run came from split --from-metadata.
   */
  gpu_vendor_used: string | null;
  /**
   * Snapshot of gpu_detector._VENDOR_PREFERENCE (currently ["nvidia","amd","intel"]).
   */
  vendor_preference: string[];
}
/**
 * Pre-rendered Pass 1 brightness timeline (#569). The CLI writer caps `values` to ~512 entries via downsampling so the GUI complete screen can draw the SVG without recomputing. Optional at the root: pre-#569 metadata.json and detect cache hits skip the field; CompleteScreen falls back to a sample curve when missing.
 */
export interface BrightnessSamples {
  /**
   * Seconds represented by each `values[i]` (e.g. 25.0 means values[i] is the brightness at i * 25 seconds).
   */
  interval_s: number;
  /**
   * Average brightness (0-255) per sample, chronological. Length capped at 512 by the writer.
   */
  values: number[];
}
