import { describe, expect, it, vi } from 'vitest';

import {
  buildBrightnessPath,
  buildLocalBrightness,
  findBlackoutRegions,
} from './brightness';

describe('buildBrightnessPath', () => {
  it('returns empty string for empty samples', () => {
    expect(buildBrightnessPath([], 100, 50)).toBe('');
  });

  it('returns a single M command for one sample', () => {
    expect(buildBrightnessPath([255], 100, 50)).toBe('M0 0.00');
    expect(buildBrightnessPath([0], 100, 50)).toBe('M0 50.00');
  });

  it('maps sample indices to x-coordinates across [0, width]', () => {
    const path = buildBrightnessPath([255, 255], 100, 50);
    expect(path).toBe('M0.00 0.00 L100.00 0.00');
  });

  it('maps brightness 0 to bottom of box and brightness 255 to top', () => {
    const path = buildBrightnessPath([0, 255, 128], 200, 100);
    // [0] y = 100-(0/255*100) = 100.00
    // [1] y = 100-(255/255*100) = 0.00
    // [2] y = 100-(128/255*100) ≈ 49.80
    expect(path).toMatch(/^M0\.00 100\.00 L100\.00 0\.00 L200\.00 49\.80$/);
  });

  it('respects yScale parameter (0.5 halves the vertical amplitude)', () => {
    const path = buildBrightnessPath([255], 100, 100, 0.5);
    // y = 100 - (255/255 * 100 * 0.5) = 50.00
    expect(path).toBe('M0 50.00');
  });

  it('applies yScale to every point of a multi-sample path', () => {
    // 2 点以上でも yScale が掛け算で効く (割り算に化けると値が 4 倍ずれる)
    expect(buildBrightnessPath([255, 0], 100, 100, 0.5)).toBe(
      'M0.00 50.00 L100.00 100.00',
    );
  });
});

describe('findBlackoutRegions', () => {
  it('returns empty array for empty samples', () => {
    expect(findBlackoutRegions([], 100)).toEqual([]);
  });

  it('returns empty array when duration is 0 or negative', () => {
    expect(findBlackoutRegions([0, 0, 0], 0)).toEqual([]);
    expect(findBlackoutRegions([0, 0, 0], -5)).toEqual([]);
  });

  it('detects a single below-threshold region in the middle', () => {
    // 5 samples, duration 100 → t = [0, 25, 50, 75, 100]
    // samples[1..2] below threshold, samples[3..] above
    const regions = findBlackoutRegions([200, 5, 5, 200, 200], 100);
    expect(regions).toEqual([{ start: 25, end: 75 }]);
  });

  it('detects multiple regions', () => {
    // 5 samples, duration 100 → t = [0, 25, 50, 75, 100]
    const regions = findBlackoutRegions([5, 200, 5, 200, 5], 100);
    expect(regions).toEqual([
      { start: 0, end: 25 },
      { start: 50, end: 75 },
      { start: 100, end: 100 },
    ]);
  });

  it('extends trailing region to duration when samples end below threshold', () => {
    const regions = findBlackoutRegions([200, 5, 5], 60);
    expect(regions).toEqual([{ start: 30, end: 60 }]);
  });

  it('treats threshold as exclusive upper bound (strictly less than)', () => {
    const regions = findBlackoutRegions([15, 14, 15], 100, 15);
    // samples[1] = 14 < 15 → region; samples[0], samples[2] = 15 not < 15 → not region
    expect(regions).toEqual([{ start: 50, end: 100 }]);
  });

  it('places a single sample at t = 0 and merges it into one region', () => {
    // 1 サンプルだけのときは t = 0 (i / (n-1) は 0 除算になるため分岐する)
    expect(findBlackoutRegions([5], 100)).toEqual([{ start: 0, end: 100 }]);
    expect(findBlackoutRegions([200], 100)).toEqual([]);
  });
});

describe('buildLocalBrightness', () => {
  it('returns an array with 2 * windowSec * sampleHz samples', () => {
    const samples = buildLocalBrightness(100, 5, 2);
    expect(samples.length).toBe(20);
  });

  it('returns empty array when window is 0 or negative', () => {
    expect(buildLocalBrightness(100, 0, 2)).toEqual([]);
    expect(buildLocalBrightness(100, -5, 2)).toEqual([]);
  });

  it('produces samples with t centered around centerT', () => {
    const samples = buildLocalBrightness(100, 2, 1);
    expect(samples[0].t).toBe(98);
    expect(samples[samples.length - 1].t).toBe(101);
  });

  it('produces very low brightness within ±1.2s of centerT', () => {
    const samples = buildLocalBrightness(100, 3, 2);
    for (const s of samples) {
      if (Math.abs(s.t - 100) < 1.2) {
        expect(s.b).toBeGreaterThanOrEqual(4);
        expect(s.b).toBeLessThan(10);
      }
    }
  });

  it('uses three distinct brightness bands by distance from centerT', () => {
    // 帯の境界は 1.2 秒 / 2.5 秒。乱数を固定して帯ごとの値を確定させる
    // (値の根拠: 帯ごとの係数 4+rand*6 / 20+rand*30 / 85+sin+sin+rand)。
    const random = vi.spyOn(Math, 'random').mockReturnValue(0.5);
    try {
      const samples = buildLocalBrightness(100, 3.5, 2);
      expect(samples.map((s) => s.t)).toEqual([
        96.5, 97, 97.5, 98, 98.5, 99, 99.5, 100, 100.5, 101, 101.5, 102, 102.5, 103,
      ]);
      const byDistance = samples.map((s) => Math.abs(s.t - 100));
      expect(byDistance.filter((d) => d < 1.2)).toHaveLength(5);
      expect(byDistance.filter((d) => d >= 1.2 && d < 2.5)).toHaveLength(4);
      expect(byDistance.filter((d) => d >= 2.5)).toHaveLength(5);

      // 暗転 (0-10) → ローディング (20-50) → 試合中 (正弦波 + 揺らぎ)
      const low = samples.find((s) => s.t === 100)!;
      expect(low.b).toBeCloseTo(7, 5);
      const mid = samples.find((s) => s.t === 98)!;
      expect(mid.b).toBeCloseTo(35, 5);
      const high = samples.find((s) => s.t === 97)!;
      expect(high.b).toBeCloseTo(105.2748, 3);
    } finally {
      random.mockRestore();
    }
  });

  it('clamps brightness to [0, 255]', () => {
    const samples = buildLocalBrightness(500, 50, 4);
    for (const s of samples) {
      expect(s.b).toBeGreaterThanOrEqual(0);
      expect(s.b).toBeLessThanOrEqual(255);
    }
  });

  it('treats the band edges at exactly 1.2s and 2.5s as the upper bands', () => {
    // 境界値: d === 1.2 はローディング帯、d === 2.5 は試合中帯 (< は排他)
    const random = vi.spyOn(Math, 'random').mockReturnValue(0.25);
    try {
      const samples = buildLocalBrightness(100, 3, 10);
      const atBoundary = samples.find((s) => Math.abs(s.t - 98.8) < 1e-9)!;
      expect(Math.abs(atBoundary.t - 100)).toBeCloseTo(1.2, 9);
      expect(atBoundary.b).toBeCloseTo(27.5, 5);

      const atOuter = samples.find((s) => Math.abs(s.t - 97.5) < 1e-9)!;
      expect(Math.abs(atOuter.t - 100)).toBeCloseTo(2.5, 9);
      expect(atOuter.b).toBeCloseTo(107.6974, 3);
    } finally {
      random.mockRestore();
    }
  });

  it('adds symmetric noise to the gameplay band', () => {
    // 揺らぎの符号が反転・除算化すると値が変わる (rand=0.25 で -3.5 される)
    const random = vi.spyOn(Math, 'random').mockReturnValue(0.25);
    try {
      const samples = buildLocalBrightness(100, 3, 2);
      expect(samples.find((s) => s.t === 97)!.b).toBeCloseTo(101.7748, 3);
      expect(samples.find((s) => s.t === 100)!.b).toBeCloseTo(5.5, 5);
    } finally {
      random.mockRestore();
    }
  });
});
