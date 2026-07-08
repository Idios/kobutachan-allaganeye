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
  capture_regions?: CaptureRegions;
  /**
   * #481: per-match area-map crop region (normalized) actually used by `allaganeye minimap --region`. Missing entry for a match = not cropped. Field absent = minimap crop never ran.
   */
  minimap_regions?: MinimapRegionEntry[];
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
  /**
   * True when the --vtuber flag was supplied (#821; the VTuber path never auto-triggers, so request equals resolved). Optional: absent in pre-#821 outputs and means false.
   */
  vtuber?: boolean;
  /**
   * True when the --masked flag was supplied (request, #821). The masked fallback can also auto-trigger on zero-blackout recordings; see masked_fallback_used for the resolved path. Optional: absent in pre-#821 outputs and means false.
   */
  masked?: boolean;
  /**
   * True when the mask-free-region fallback actually produced this result (explicit --masked or zero-blackout auto-trigger, #821). Optional: absent in pre-#821 outputs and means false.
   */
  masked_fallback_used?: boolean;
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
  output_file?: string;
  /**
   * True when this segment is a post-match trailing run (#805 段階2). Non-destructive flag: excluded from default split output but retained in metadata. Absent / false = normal match.
   */
  post_match?: boolean;
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
 * GPU vendor probe snapshot recorded by detect/split (#591, extended #761). GUI export uses this to pick the H.264 encoder (NVENC / QSV / AMF / libx264) and query the NVENC parallel slot count SKU table. Optional at the root because pre-#591 metadata.json files don't carry it.
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
  /**
   * GPU model name strings from get_gpu_info_lines() (#761). Used by GUI export to query probe_nvenc_engine_count() for NVENC parallel slot count. Empty array on CPU-only hosts or when probing fails. Optional for backward compat with pre-#761 metadata.json.
   */
  gpu?: string[];
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
/**
 * Capture-region timeline resolved by detection (#810; serialized RegionTimeline). `coarse` is the region actually used for Pass 1 brightness measurement: FULL_FRAME on standard OBS runs, the scorebar band ROI (source="band", NOT the full game rectangle) on --vtuber runs, and the mask-free game rectangle (source="tierA") when the masked fallback produced the result. `segments` is always [] until Tier B per-segment detection lands (#480). `fallback_reason` records band-anchor degradation on --vtuber runs (documented values: "anchor_error" = Stage 0 exception, "consensus_miss" = no band consensus); null = no degradation. Optional at the root: pre-#810 metadata.json doesn't carry it; cache hits from pre-#810 vtuber/masked caches omit it (region unknown).
 */
export interface CaptureRegions {
  coarse: CaptureRegion;
  segments: RegionSegment[];
  /**
   * Band-anchor degradation provenance. Free string (readers accept unknown values); null = no degradation.
   */
  fallback_reason: string | null;
}
/**
 * Game capture rectangle in normalized [0,1] frame coordinates (#810). Serialized form of allaganeye/video/capture_region.py::CaptureRegion (to_dict / from_dict).
 */
export interface CaptureRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  /**
   * Detector confidence in [0,1].
   */
  confidence: number;
  /**
   * Detector that produced the region. Documented values: "fallback" (FULL_FRAME), "band" (scorebar band ROI), "tierA" (game rectangle), "tierB" (future per-segment precise). Free string: readers must accept unknown values (forward compat, same philosophy as warning codes).
   */
  source: string;
}
/**
 * Per-segment precise region entry (Tier B; consumed by #480/#481). time_range is [t0, t1] in seconds.
 */
export interface RegionSegment {
  /**
   * @minItems 2
   * @maxItems 2
   */
  time_range: [number, number];
  region: CaptureRegion;
}
/**
 * #481: one per-match minimap crop entry. `match_index` references Match.index (1-based). `region` is the normalized crop rectangle used by `allaganeye minimap --region`.
 */
export interface MinimapRegionEntry {
  match_index: number;
  region: CaptureRegion;
}
