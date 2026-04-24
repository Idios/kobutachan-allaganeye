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
});
