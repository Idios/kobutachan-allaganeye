// zod ⇔ JSON Schema integrity check (#612).
//
// The JSON Schema is the machine-readable source of truth; the zod
// schema is hand-written so we can keep refine-style semantic
// constraints (e.g. end_time >= start_time). This test enforces that
// the *field sets* stay in sync — adding a property to one side
// without the other is caught at CI time.

import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import schema from '../../../../schemas/metadata.schema.json' with { type: 'json' };
import {
  CaptureRegionSchema,
  CaptureRegionsSchema,
  DetectionParamsSchema,
  GapSchema,
  MatchSchema,
  MetadataSchema,
  RegionSegmentSchema,
  SystemInfoSchema,
  WarningSchema,
} from '../metadata.schema';

type JsonObjectSchema = {
  properties: Record<string, unknown>;
  required?: string[];
};

function jsonProps(s: JsonObjectSchema): string[] {
  return Object.keys(s.properties).sort();
}

function jsonRequired(s: JsonObjectSchema): string[] {
  return [...(s.required ?? [])].sort();
}

/**
 * Extract the field-name set from a zod object schema. Works for both
 * raw `ZodObject` and the `ZodObject` wrapped by `.passthrough()` /
 * `.refine(...)` -- we drill into `_def` to find `shape` regardless.
 */
function zodKeys(s: z.ZodTypeAny): string[] {
  // Unwrap ZodEffects (refine) layers.
  let inner: z.ZodTypeAny = s;
  while ('innerType' in (inner as { innerType?: unknown })) {
    inner = (inner as unknown as { innerType: () => z.ZodTypeAny }).innerType();
  }
  // zod 4: ZodObject.shape is a getter; `_def.shape` is also exposed
  // for backwards-compat. Defensive lookup so future zod changes don't
  // silently bypass this assertion.
  const shapeAccess = (inner as unknown as {
    shape?: Record<string, unknown>;
    _def?: { shape?: Record<string, unknown> };
  });
  const shape = shapeAccess.shape ?? shapeAccess._def?.shape;
  if (!shape) {
    throw new Error('zod schema does not expose .shape');
  }
  return Object.keys(shape).sort();
}

/**
 * Required keys = those whose zod type is NOT optional. We treat
 * `ZodOptional<T>` and `ZodNullable<ZodOptional<T>>` as optional;
 * everything else is required.
 */
function zodRequired(s: z.ZodTypeAny): string[] {
  let inner: z.ZodTypeAny = s;
  while ('innerType' in (inner as { innerType?: unknown })) {
    inner = (inner as unknown as { innerType: () => z.ZodTypeAny }).innerType();
  }
  const shapeAccess = (inner as unknown as {
    shape?: Record<string, z.ZodTypeAny>;
    _def?: { shape?: Record<string, z.ZodTypeAny> };
  });
  const shape = shapeAccess.shape ?? shapeAccess._def?.shape;
  if (!shape) {
    throw new Error('zod schema does not expose .shape');
  }
  const required: string[] = [];
  for (const [key, value] of Object.entries(shape)) {
    if (!value.isOptional()) {
      required.push(key);
    }
  }
  return required.sort();
}

describe('zod schema ⇔ JSON Schema integrity (#612)', () => {
  it('Metadata root: properties match', () => {
    expect(zodKeys(MetadataSchema)).toEqual(jsonProps(schema as JsonObjectSchema));
  });

  it('Metadata root: required match', () => {
    expect(zodRequired(MetadataSchema)).toEqual(jsonRequired(schema as JsonObjectSchema));
  });

  it('DetectionParams: properties match', () => {
    expect(zodKeys(DetectionParamsSchema)).toEqual(
      jsonProps(schema.$defs.DetectionParams as JsonObjectSchema),
    );
  });

  it('DetectionParams: required match', () => {
    expect(zodRequired(DetectionParamsSchema)).toEqual(
      jsonRequired(schema.$defs.DetectionParams as JsonObjectSchema),
    );
  });

  it('Match: properties match', () => {
    expect(zodKeys(MatchSchema)).toEqual(jsonProps(schema.$defs.Match as JsonObjectSchema));
  });

  it('Match: required match', () => {
    expect(zodRequired(MatchSchema)).toEqual(
      jsonRequired(schema.$defs.Match as JsonObjectSchema),
    );
  });

  it('Gap: properties match', () => {
    expect(zodKeys(GapSchema)).toEqual(jsonProps(schema.$defs.Gap as JsonObjectSchema));
  });

  it('Gap: required match', () => {
    expect(zodRequired(GapSchema)).toEqual(jsonRequired(schema.$defs.Gap as JsonObjectSchema));
  });

  it('Warning: properties match', () => {
    expect(zodKeys(WarningSchema)).toEqual(
      jsonProps(schema.$defs.MetadataWarning as JsonObjectSchema),
    );
  });

  it('Warning: required match', () => {
    expect(zodRequired(WarningSchema)).toEqual(
      jsonRequired(schema.$defs.MetadataWarning as JsonObjectSchema),
    );
  });

  it('SystemInfo: properties match', () => {
    expect(zodKeys(SystemInfoSchema)).toEqual(
      jsonProps(schema.$defs.SystemInfo as JsonObjectSchema),
    );
  });

  it('SystemInfo: required match', () => {
    expect(zodRequired(SystemInfoSchema)).toEqual(
      jsonRequired(schema.$defs.SystemInfo as JsonObjectSchema),
    );
  });

  it('CaptureRegion: properties match', () => {
    expect(zodKeys(CaptureRegionSchema)).toEqual(
      jsonProps(schema.$defs.CaptureRegion as JsonObjectSchema),
    );
  });

  it('CaptureRegion: required match', () => {
    expect(zodRequired(CaptureRegionSchema)).toEqual(
      jsonRequired(schema.$defs.CaptureRegion as JsonObjectSchema),
    );
  });

  it('RegionSegment: properties match', () => {
    expect(zodKeys(RegionSegmentSchema)).toEqual(
      jsonProps(schema.$defs.RegionSegment as JsonObjectSchema),
    );
  });

  it('RegionSegment: required match', () => {
    expect(zodRequired(RegionSegmentSchema)).toEqual(
      jsonRequired(schema.$defs.RegionSegment as JsonObjectSchema),
    );
  });

  it('CaptureRegions: properties match', () => {
    expect(zodKeys(CaptureRegionsSchema)).toEqual(
      jsonProps(schema.$defs.CaptureRegions as JsonObjectSchema),
    );
  });

  it('CaptureRegions: required match', () => {
    expect(zodRequired(CaptureRegionsSchema)).toEqual(
      jsonRequired(schema.$defs.CaptureRegions as JsonObjectSchema),
    );
  });
});
