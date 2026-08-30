import { describe, expect, it } from 'vitest';

import {
  DEFAULT_DETECTION_PARAMS,
  type DetectionParams,
} from '../state/appStateStore';
import { isDetectionParamsModified, toStartDetectParams } from './detection';

describe('toStartDetectParams (#613)', () => {
  it('passes blackoutThreshold through verbatim', () => {
    const args = toStartDetectParams({
      ...DEFAULT_DETECTION_PARAMS,
      blackoutThreshold: 22,
    });
    expect(args.blackoutThreshold).toBe(22);
  });

  it('translates workers=0 (auto sentinel) to null', () => {
    const args = toStartDetectParams({
      ...DEFAULT_DETECTION_PARAMS,
      workers: 0,
    });
    expect(args.workers).toBeNull();
  });

  it('passes workers > 0 through verbatim', () => {
    const args = toStartDetectParams({
      ...DEFAULT_DETECTION_PARAMS,
      workers: 8,
    });
    expect(args.workers).toBe(8);
  });

  it.each([
    { gpu: null as boolean | null, expected: null },
    { gpu: true as boolean | null, expected: true },
    { gpu: false as boolean | null, expected: false },
  ])('forwards gpu tri-state $gpu unchanged', ({ gpu, expected }) => {
    const args = toStartDetectParams({ ...DEFAULT_DETECTION_PARAMS, gpu });
    expect(args.gpu).toBe(expected);
  });

  it('produces the three expected keys (noAudio omitted; audio module frozen indefinitely, #327 / #865)', () => {
    const args = toStartDetectParams(DEFAULT_DETECTION_PARAMS);
    expect(Object.keys(args).sort()).toEqual([
      'blackoutThreshold',
      'gpu',
      'workers',
    ]);
  });
});

describe('isDetectionParamsModified (#613)', () => {
  it('returns false for the default params', () => {
    expect(isDetectionParamsModified(DEFAULT_DETECTION_PARAMS)).toBe(false);
  });

  it.each<[string, Partial<DetectionParams>]>([
    ['blackoutThreshold', { blackoutThreshold: 14 }],
    ['workers', { workers: 8 }],
    ['gpu (true)', { gpu: true }],
    ['gpu (false)', { gpu: false }],
  ])('returns true when only %s differs', (_label, patch) => {
    expect(
      isDetectionParamsModified({ ...DEFAULT_DETECTION_PARAMS, ...patch }),
    ).toBe(true);
  });
});
