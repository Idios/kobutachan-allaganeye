import { describe, expect, it } from 'vitest';

import { fmtPreciseTime, fmtTime } from './time';

describe('fmtTime', () => {
  it('formats sub-hour durations as MM:SS', () => {
    expect(fmtTime(0)).toBe('00:00');
    expect(fmtTime(5)).toBe('00:05');
    expect(fmtTime(65)).toBe('01:05');
    expect(fmtTime(3599)).toBe('59:59');
  });

  it('formats hour-plus durations as H:MM:SS', () => {
    expect(fmtTime(3600)).toBe('1:00:00');
    expect(fmtTime(3661)).toBe('1:01:01');
    expect(fmtTime(10228.735)).toBe('2:50:28');
  });

  it('clamps negative input to 0', () => {
    expect(fmtTime(-1)).toBe('00:00');
    expect(fmtTime(-3600)).toBe('00:00');
  });

  it('handles NaN and Infinity by clamping to 0', () => {
    expect(fmtTime(Number.NaN)).toBe('00:00');
    expect(fmtTime(Number.POSITIVE_INFINITY)).toBe('00:00');
  });

  it('truncates fractional seconds (floor semantics)', () => {
    expect(fmtTime(59.9)).toBe('00:59');
    expect(fmtTime(60.999)).toBe('01:00');
  });
});

describe('fmtPreciseTime', () => {
  it('formats whole-second timestamps at 60fps', () => {
    expect(fmtPreciseTime(0)).toBe('0:00:00.00');
    expect(fmtPreciseTime(65)).toBe('0:01:05.00');
    expect(fmtPreciseTime(3661)).toBe('1:01:01.00');
  });

  it('computes frame component for fractional seconds at 60fps', () => {
    expect(fmtPreciseTime(1.5)).toBe('0:00:01.30');
    expect(fmtPreciseTime(1.999, 60)).toBe('0:00:01.59');
  });

  it('respects custom fps parameter', () => {
    expect(fmtPreciseTime(1.5, 30)).toBe('0:00:01.15');
    expect(fmtPreciseTime(1.5, 24)).toBe('0:00:01.12');
  });

  it('emits a leading minus for negative timestamps', () => {
    expect(fmtPreciseTime(-5)).toBe('-0:00:05.00');
    expect(fmtPreciseTime(-0.5)).toBe('-0:00:00.30');
  });

  it('handles NaN by falling back to 0', () => {
    expect(fmtPreciseTime(Number.NaN)).toBe('0:00:00.00');
  });
});
