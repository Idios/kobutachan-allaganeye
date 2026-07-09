import { describe, expect, it } from 'vitest';

import { MetadataSchema } from './metadata.schema';

function validMetadata() {
  return {
    source: 'C:/videos/2026-04-08.mkv',
    source_duration: 10200,
    source_duration_display: '2:50:00',
    detected_at: '2026-04-22T00:00:00Z',
    detection_params: {
      sample_interval: 2,
      blackout_threshold: 15,
      min_match_duration: 300,
      min_blackout_duration: 3,
      no_audio: false,
      use_gpu: null,
      workers: null,
    },
    matches: [
      {
        index: 1,
        start_time: 0,
        end_time: 915,
        start_display: '00:00',
        end_display: '15:15',
        duration: 915,
        duration_display: '15m15s',
        type: 'fl_match' as const,
        output_file: 'match_001.mp4',
      },
    ],
    gaps: [],
  };
}

describe('MetadataSchema', () => {
  it('accepts a minimal valid document', () => {
    const result = MetadataSchema.safeParse(validMetadata());
    expect(result.success).toBe(true);
  });

  it('accepts legacy "note" field via passthrough', () => {
    const doc = { ...validMetadata(), note: 'legacy caveat string' };
    const result = MetadataSchema.safeParse(doc);
    expect(result.success).toBe(true);
    if (result.success) {
      expect((result.data as { note?: string }).note).toBe('legacy caveat string');
    }
  });

  it('accepts detection_params.use_gpu as boolean, number, or null', () => {
    const doc = validMetadata();
    for (const v of [null, true, false, 0, 1]) {
      const patched = {
        ...doc,
        detection_params: { ...doc.detection_params, use_gpu: v },
      };
      expect(MetadataSchema.safeParse(patched).success).toBe(true);
    }
  });

  it('rejects when required top-level field is missing', () => {
    const doc = validMetadata() as Partial<ReturnType<typeof validMetadata>>;
    delete doc.source;
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects when source_duration is zero or negative', () => {
    const doc = validMetadata();
    for (const v of [0, -1]) {
      expect(
        MetadataSchema.safeParse({ ...doc, source_duration: v }).success,
      ).toBe(false);
    }
  });

  it('rejects a match with end_time < start_time', () => {
    const doc = validMetadata();
    doc.matches[0].start_time = 100;
    doc.matches[0].end_time = 50;
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects a match with unknown type value', () => {
    const doc = validMetadata();
    (doc.matches[0] as unknown as { type: string }).type = 'bogus';
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects a match with non-integer index', () => {
    const doc = validMetadata();
    doc.matches[0].index = 1.5;
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('accepts empty matches / gaps arrays', () => {
    const doc = validMetadata();
    doc.matches = [];
    doc.gaps = [];
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('rejects a gap with end_time < start_time', () => {
    const doc = {
      ...validMetadata(),
      gaps: [
        {
          start_time: 100,
          end_time: 50,
          start_display: '1:40',
          end_display: '0:50',
          duration: 50,
          duration_display: '50s',
        },
      ],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  // #515 — schema_version policy.

  it('accepts documents with schema_version "1"', () => {
    const doc = { ...validMetadata(), schema_version: '1' };
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('accepts documents without schema_version (backward compat)', () => {
    const doc = validMetadata();
    expect('schema_version' in doc).toBe(false);
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('rejects documents with an unknown future schema_version', () => {
    const doc = { ...validMetadata(), schema_version: '99' };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects documents with a non-string schema_version', () => {
    const doc = { ...validMetadata(), schema_version: 1 };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  // #520 — detection_params type violations.

  it('rejects when detection_params number fields are non-number', () => {
    const doc = validMetadata();
    const numberFields: Array<keyof typeof doc.detection_params> = [
      'sample_interval',
      'blackout_threshold',
      'min_match_duration',
      'min_blackout_duration',
    ];
    for (const field of numberFields) {
      const patched = {
        ...doc,
        detection_params: { ...doc.detection_params, [field]: '2' },
      };
      expect(MetadataSchema.safeParse(patched).success).toBe(false);
    }
  });

  it('rejects when detection_params.no_audio is non-boolean', () => {
    const doc = validMetadata();
    for (const v of [0, 1, 'false', null]) {
      const patched = {
        ...doc,
        detection_params: { ...doc.detection_params, no_audio: v },
      };
      expect(MetadataSchema.safeParse(patched).success).toBe(false);
    }
  });

  it('rejects when detection_params.use_gpu is outside number | boolean | null', () => {
    const doc = validMetadata();
    for (const v of ['cuda', [], {}]) {
      const patched = {
        ...doc,
        detection_params: { ...doc.detection_params, use_gpu: v },
      };
      expect(MetadataSchema.safeParse(patched).success).toBe(false);
    }
  });

  it('rejects when detection_params.workers is outside number | null', () => {
    const doc = validMetadata();
    for (const v of [true, false, '4']) {
      const patched = {
        ...doc,
        detection_params: { ...doc.detection_params, workers: v },
      };
      expect(MetadataSchema.safeParse(patched).success).toBe(false);
    }
  });

  it('rejects when detection_params is missing or null', () => {
    const doc = validMetadata() as Partial<ReturnType<typeof validMetadata>>;
    delete doc.detection_params;
    expect(MetadataSchema.safeParse(doc).success).toBe(false);

    const nulled = { ...validMetadata(), detection_params: null };
    expect(MetadataSchema.safeParse(nulled).success).toBe(false);
  });

  // #518 -- warnings scaffold.

  it('accepts a document with an empty warnings array', () => {
    const doc = { ...validMetadata(), warnings: [] };
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('accepts a document without warnings (backward compat)', () => {
    const doc = validMetadata();
    expect('warnings' in doc).toBe(false);
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('accepts valid warning entries with various shapes', () => {
    const doc = {
      ...validMetadata(),
      warnings: [
        { code: 'audio_skipped' },
        { code: 'low_confidence', severity: 'warn' },
        {
          code: 'gpu_fallback',
          message_en: 'fell back to CPU',
          severity: 'info',
          context: { reason: 'cuda not found' },
        },
      ],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('rejects a warning missing its code field', () => {
    const doc = {
      ...validMetadata(),
      warnings: [{ message_en: 'no code', severity: 'warn' }],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects a warning with unknown severity', () => {
    const doc = {
      ...validMetadata(),
      warnings: [{ code: 'x', severity: 'catastrophic' }],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  // #465 review: source_fps optional field

  it('accepts a document with source_fps (60 / 119.88 / 240)', () => {
    for (const fps of [60, 119.88, 240]) {
      const doc = { ...validMetadata(), source_fps: fps };
      const result = MetadataSchema.safeParse(doc);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.source_fps).toBe(fps);
      }
    }
  });

  it('accepts a document without source_fps (backward compat)', () => {
    const doc = validMetadata();
    expect('source_fps' in doc).toBe(false);
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('rejects a non-positive source_fps', () => {
    for (const bad of [0, -30, -1]) {
      const doc = { ...validMetadata(), source_fps: bad };
      expect(MetadataSchema.safeParse(doc).success).toBe(false);
    }
  });

  it('rejects a non-number source_fps', () => {
    for (const bad of ['60', null, true, [60]]) {
      const doc = { ...validMetadata(), source_fps: bad };
      expect(MetadataSchema.safeParse(doc).success).toBe(false);
    }
  });

  // #569 -- brightness_samples optional field

  it('accepts a document with brightness_samples', () => {
    const doc = {
      ...validMetadata(),
      brightness_samples: {
        interval_s: 25.0,
        values: [85.3, 87.1, 6.2, 12.0, 95.0],
      },
    };
    const result = MetadataSchema.safeParse(doc);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.brightness_samples?.values.length).toBe(5);
    }
  });

  it('accepts a document without brightness_samples (backward compat)', () => {
    const doc = validMetadata();
    expect('brightness_samples' in doc).toBe(false);
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('rejects brightness_samples with non-positive interval_s', () => {
    for (const interval_s of [0, -1]) {
      const doc = {
        ...validMetadata(),
        brightness_samples: {
          interval_s,
          values: [10, 20],
        },
      };
      expect(MetadataSchema.safeParse(doc).success).toBe(false);
    }
  });

  it('rejects brightness_samples values outside 0-255', () => {
    for (const bad of [-1, 256, 1000]) {
      const doc = {
        ...validMetadata(),
        brightness_samples: {
          interval_s: 1.0,
          values: [10, bad, 20],
        },
      };
      expect(MetadataSchema.safeParse(doc).success).toBe(false);
    }
  });

  it('accepts an empty brightness_samples values array', () => {
    // The CLI omits the field entirely when no Pass 1 ran (cache hit
    // path), but a writer that emits {interval_s, values: []} still
    // round-trips cleanly through the schema -- the GUI just renders
    // the fallback curve.
    const doc = {
      ...validMetadata(),
      brightness_samples: {
        interval_s: 1.0,
        values: [],
      },
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  // #481 -- minimap_regions optional field

  it('accepts a document without minimap_regions (backward compat)', () => {
    const doc = validMetadata();
    expect('minimap_regions' in doc).toBe(false);
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('accepts a document with an empty minimap_regions array', () => {
    const doc = { ...validMetadata(), minimap_regions: [] };
    expect(MetadataSchema.safeParse(doc).success).toBe(true);
  });

  it('accepts a document with valid minimap_regions entries', () => {
    const doc = {
      ...validMetadata(),
      minimap_regions: [
        {
          match_index: 1,
          region: { x: 0.01, y: 0.02, w: 0.28, h: 0.35, confidence: 1.0, source: 'manual' },
        },
        {
          match_index: 3,
          region: { x: 0.0, y: 0.0, w: 0.3, h: 0.4, confidence: 1.0, source: 'manual' },
        },
      ],
    };
    const result = MetadataSchema.safeParse(doc);
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.minimap_regions).toHaveLength(2);
      expect(result.data.minimap_regions![0].match_index).toBe(1);
    }
  });

  it('rejects minimap_regions entry with match_index < 1', () => {
    const doc = {
      ...validMetadata(),
      minimap_regions: [
        {
          match_index: 0,
          region: { x: 0.0, y: 0.0, w: 0.3, h: 0.4, confidence: 1.0, source: 'manual' },
        },
      ],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects minimap_regions entry missing region', () => {
    const doc = {
      ...validMetadata(),
      minimap_regions: [{ match_index: 1 }],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });

  it('rejects minimap_regions entry missing match_index', () => {
    const doc = {
      ...validMetadata(),
      minimap_regions: [
        { region: { x: 0.0, y: 0.0, w: 0.3, h: 0.4, confidence: 1.0, source: 'manual' } },
      ],
    };
    expect(MetadataSchema.safeParse(doc).success).toBe(false);
  });
});
