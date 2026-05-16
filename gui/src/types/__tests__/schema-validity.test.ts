// JSON Schema validity check via ajv (#612).
//
// Three guarantees:
//   1. schemas/metadata.schema.json compiles cleanly under ajv 2020-12.
//   2. A representative valid metadata.json passes validation.
//   3. Removing a required field flips validation to reject.
//
// The Python side runs the equivalent check via `jsonschema` in
// tests/test_metadata_schema.py so the same guarantee holds in both
// CI jobs without depending on the cross-language runtime.

import Ajv2020 from 'ajv/dist/2020';
import { describe, expect, it } from 'vitest';

import schema from '../../../../schemas/metadata.schema.json' with { type: 'json' };

function makeAjv(): Ajv2020 {
  return new Ajv2020({
    strict: true,
    // The schema uses union types (`type: [..., null]`) for nullable
    // fields like `use_gpu` and `workers`; ajv's strict mode requires
    // an explicit opt-in.
    allowUnionTypes: true,
    allErrors: true,
  });
}

function validSample(): Record<string, unknown> {
  return {
    schema_version: '1',
    source: 'C:/videos/sample.mkv',
    source_duration: 7200,
    source_duration_display: '02:00:00',
    source_fps: 60,
    detected_at: '2026-04-28T00:00:00Z',
    detection_started_at: '2026-04-28T00:00:00Z',
    detection_completed_at: '2026-04-28T00:01:30Z',
    detection_params: {
      sample_interval: 2.0,
      blackout_threshold: 15,
      min_match_duration: 300,
      min_blackout_duration: 1.5,
      no_audio: false,
      use_gpu: null,
      workers: null,
    },
    matches: [
      {
        index: 1,
        start_time: 60,
        end_time: 1200,
        start_display: '01:00',
        end_display: '20:00',
        duration: 1140,
        duration_display: '19m00s',
        type: 'fl_match',
        output_file: 'match_001.mp4',
      },
    ],
    gaps: [],
    warnings: [],
    system_info: {
      gpu_vendors_available: ['nvidia'],
      gpu_vendor_used: 'nvidia',
      vendor_preference: ['nvidia', 'amd', 'intel'],
    },
  };
}

describe('JSON Schema validity (#612)', () => {
  it('compiles cleanly under draft-2020-12', () => {
    const ajv = makeAjv();
    expect(() => ajv.compile(schema)).not.toThrow();
  });

  it('accepts a representative valid metadata payload', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const ok = validate(validSample());
    expect(validate.errors).toBeNull();
    expect(ok).toBe(true);
  });

  it('rejects a payload missing the required `source` field', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const broken = validSample();
    delete broken.source;
    expect(validate(broken)).toBe(false);
  });

  it('rejects a Match with the wrong `type` literal', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const broken = validSample();
    (broken.matches as Array<Record<string, unknown>>)[0].type = 'fanfare_only';
    expect(validate(broken)).toBe(false);
  });

  it('accepts a payload omitting optional fields (pre-#515 / pre-#586 / pre-#591 backward compat)', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const minimal = validSample();
    delete minimal.schema_version;
    delete minimal.source_fps;
    delete minimal.warnings;
    delete minimal.system_info;
    delete minimal.detection_started_at;
    delete minimal.detection_completed_at;
    expect(validate(minimal)).toBe(true);
  });

  it('rejects an unknown top-level field (writer contract is strict)', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const broken = validSample();
    broken.unknown_root_field = 'x';
    expect(validate(broken)).toBe(false);
  });

  it('rejects an unknown field on a Match (writer contract is strict)', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const broken = validSample();
    (broken.matches as Array<Record<string, unknown>>)[0].name = 'GUI-only edit field';
    expect(validate(broken)).toBe(false);
  });

  it('rejects an unknown field on detection_params', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const broken = validSample();
    (broken.detection_params as Record<string, unknown>).future_param = 1;
    expect(validate(broken)).toBe(false);
  });

  it('accepts arbitrary keys inside MetadataWarning.context (extension area)', () => {
    const ajv = makeAjv();
    const validate = ajv.compile(schema);
    const sample = validSample();
    (sample.warnings as Array<Record<string, unknown>>) = [
      {
        code: 'audio_skipped',
        severity: 'info',
        // context is intentionally permissive so emitters can attach
        // arbitrary diagnostic payloads without bumping the schema.
        context: { reason: 'no_audio_track', frame: 12345 },
      },
    ];
    expect(validate(sample)).toBe(true);
  });
});
