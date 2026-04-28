import { z } from 'zod';

export const DetectionParamsSchema = z.object({
  sample_interval: z.number(),
  blackout_threshold: z.number(),
  min_match_duration: z.number(),
  min_blackout_duration: z.number(),
  no_audio: z.boolean(),
  use_gpu: z.union([z.number(), z.boolean(), z.null()]),
  workers: z.number().nullable(),
});

export const MatchSchema = z
  .object({
    index: z.number().int().min(1),
    start_time: z.number().min(0),
    end_time: z.number().min(0),
    start_display: z.string(),
    end_display: z.string(),
    duration: z.number().min(0),
    duration_display: z.string(),
    type: z.enum(['fl_match', 'unknown']),
    output_file: z.string(),
  })
  // #517: passthrough match-level edit fields (`name` / `type_override` /
  // `edited`) so metadata.draft.json round-trips them when reloaded.
  // metadata.json proper still strips these via normalizeForPersistence.
  .passthrough()
  .refine((m) => m.end_time >= m.start_time, {
    message: 'end_time must be >= start_time',
  });

export const GapSchema = z
  .object({
    start_time: z.number().min(0),
    end_time: z.number().min(0),
    start_display: z.string(),
    end_display: z.string(),
    duration: z.number().min(0),
    duration_display: z.string(),
  })
  .refine((g) => g.end_time >= g.start_time, {
    message: 'end_time must be >= start_time',
  });

/**
 * #515 — accepted schema versions.
 *
 * - Omitted field: treated as v1 for backward compat with pre-#515 files.
 * - `"1"`: current schema.
 * - Anything else: rejected with a clear message.
 */
export const SCHEMA_VERSION = '1' as const;

/**
 * #518 -- warning entry scaffolding. Writer currently emits an empty
 * `warnings` array; future detection / scorebar / audio codes will
 * populate it. Readers must not reject unknown codes (future-proof).
 */
export const WarningSchema = z.object({
  code: z.string().min(1),
  message_en: z.string().optional(),
  severity: z.enum(['info', 'warn', 'error']).optional(),
  context: z.record(z.string(), z.unknown()).optional(),
});

/**
 * #591 -- GPU vendor probe snapshot. Optional field on metadata.json
 * (pre-#591 files don't carry it). Frontend uses
 * `gpu_vendors_available` + `vendor_preference` to pick the H.264
 * encoder via `select_h264_encoder_for_export`.
 */
export const SystemInfoSchema = z.object({
  gpu_vendors_available: z.array(z.string()),
  gpu_vendor_used: z.string().nullable(),
  vendor_preference: z.array(z.string()),
});

/**
 * #569 -- pre-rendered brightness timeline used by the complete screen.
 * Optional because pre-#569 files don't carry it and cache hits skip
 * Pass 1 sampling. CompleteScreen falls back to the in-memory sample
 * curve when the field is absent.
 *
 * - `interval_s`: seconds represented by each `values[i]` (so
 *   `values[i]` is the brightness at `i * interval_s` seconds).
 * - `values`: 0-255 floats, ordered chronologically, length capped to
 *   ~512 by the CLI writer (`build_brightness_samples`).
 */
export const BrightnessSamplesSchema = z.object({
  interval_s: z.number().positive(),
  values: z.array(z.number().min(0).max(255)),
});

/**
 * #465 review: default frame rate when ``source_fps`` is missing. Pre-#465
 * legacy metadata.json files don't include the field, so we keep a
 * conservative 60fps assumption (the most common OBS recording cadence).
 * GUI consumers should always read this constant rather than hardcoding 60
 * so a future change of default propagates cleanly.
 */
export const DEFAULT_FPS = 60;

export const MetadataSchema = z
  .object({
    schema_version: z.literal(SCHEMA_VERSION).optional(),
    source: z.string().min(1),
    source_duration: z.number().positive(),
    source_duration_display: z.string(),
    /**
     * #465 review: source recording frame rate (e.g. 60, 119.88, 240).
     * Optional for backward compat with legacy metadata.json that omitted
     * the field. Readers default to ``DEFAULT_FPS`` when absent.
     */
    source_fps: z.number().positive().optional(),
    detected_at: z.string().min(1),
    /**
     * #586 -- wall-clock ISO 8601 timestamps bracketing the detect
     * pipeline. Optional because pre-#586 metadata.json doesn't carry
     * them; CompleteScreen falls back to ``detected_at`` when missing.
     */
    detection_started_at: z.string().min(1).optional(),
    detection_completed_at: z.string().min(1).optional(),
    detection_params: DetectionParamsSchema,
    matches: z.array(MatchSchema),
    gaps: z.array(GapSchema),
    warnings: z.array(WarningSchema).optional(),
    /**
     * #591 -- GPU vendor probe snapshot. Optional because pre-#591
     * metadata.json doesn't include it. ExportScreen falls back to
     * libx264 when missing.
     */
    system_info: SystemInfoSchema.optional(),
    /**
     * #569 -- pre-rendered brightness timeline. Optional because
     * pre-#569 files and detect cache hits don't write it. The
     * complete screen falls back to a sample curve when missing.
     */
    brightness_samples: BrightnessSamplesSchema.optional(),
  })
  .passthrough();
