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

  // #1141 -- KO / ASSIST 統合。OFF ではキー自体を送らないので、既存の argv は
  // 1 バイトも変わらない (この pin がその証明)。
  describe('indicators (#1141)', () => {
    it('omits the key when off', () => {
      const args = toStartDetectParams({
        ...DEFAULT_DETECTION_PARAMS,
        indicators: false,
      });
      expect(args).not.toHaveProperty('indicators');
    });

    it('sends indicators: true when enabled', () => {
      const args = toStartDetectParams({
        ...DEFAULT_DETECTION_PARAMS,
        indicators: true,
      });
      expect(args.indicators).toBe(true);
    });

    it('counts as a modification', () => {
      expect(isDetectionParamsModified(DEFAULT_DETECTION_PARAMS)).toBe(false);
      expect(
        isDetectionParamsModified({
          ...DEFAULT_DETECTION_PARAMS,
          indicators: true,
        }),
      ).toBe(true);
    });
  });

  // #1136 -- 検知経路。`standard` は両 flag を omit するので、上記の
  // 「3 keys」pin がそのまま「従来と同一 argv」の証明になる。
  describe('detectionPath (#1136)', () => {
    it('omits both masked and vtuber for standard', () => {
      const args = toStartDetectParams({
        ...DEFAULT_DETECTION_PARAMS,
        detectionPath: 'standard',
      });
      expect(args).not.toHaveProperty('masked');
      expect(args).not.toHaveProperty('vtuber');
    });

    it('sends masked: true (and no vtuber) for masked', () => {
      const args = toStartDetectParams({
        ...DEFAULT_DETECTION_PARAMS,
        detectionPath: 'masked',
      });
      expect(args.masked).toBe(true);
      expect(args).not.toHaveProperty('vtuber');
    });

    it('sends vtuber: true (and no masked) for vtuber', () => {
      const args = toStartDetectParams({
        ...DEFAULT_DETECTION_PARAMS,
        detectionPath: 'vtuber',
      });
      expect(args.vtuber).toBe(true);
      expect(args).not.toHaveProperty('masked');
    });

    it('never sends both flags at once (mutually exclusive by construction)', () => {
      for (const detectionPath of ['standard', 'masked', 'vtuber'] as const) {
        const args = toStartDetectParams({
          ...DEFAULT_DETECTION_PARAMS,
          detectionPath,
        });
        expect(args.masked === true && args.vtuber === true).toBe(false);
      }
    });
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
    ['detectionPath (masked, #1136)', { detectionPath: 'masked' }],
    ['detectionPath (vtuber, #1136)', { detectionPath: 'vtuber' }],
  ])('returns true when only %s differs', (_label, patch) => {
    expect(
      isDetectionParamsModified({ ...DEFAULT_DETECTION_PARAMS, ...patch }),
    ).toBe(true);
  });
});
