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

export const MetadataSchema = z
  .object({
    schema_version: z.literal(SCHEMA_VERSION).optional(),
    source: z.string().min(1),
    source_duration: z.number().positive(),
    source_duration_display: z.string(),
    detected_at: z.string().min(1),
    detection_params: DetectionParamsSchema,
    matches: z.array(MatchSchema),
    gaps: z.array(GapSchema),
    warnings: z.array(WarningSchema).optional(),
  })
  .passthrough();
