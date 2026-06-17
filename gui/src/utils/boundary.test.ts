import { describe, expect, it } from 'vitest';

import { isBoundaryValid } from './boundary';

describe('isBoundaryValid (#814)', () => {
  it('accepts end strictly greater than start', () => {
    expect(isBoundaryValid(0, 1)).toBe(true);
    expect(isBoundaryValid(100.5, 200.25)).toBe(true);
  });

  it('rejects end equal to start (zero duration)', () => {
    expect(isBoundaryValid(500, 500)).toBe(false);
  });

  it('rejects end before start', () => {
    expect(isBoundaryValid(900, 100)).toBe(false);
  });

  it('rejects non-finite values', () => {
    expect(isBoundaryValid(Number.NaN, 100)).toBe(false);
    expect(isBoundaryValid(0, Number.NaN)).toBe(false);
    expect(isBoundaryValid(0, Number.POSITIVE_INFINITY)).toBe(false);
    expect(isBoundaryValid(Number.NEGATIVE_INFINITY, 100)).toBe(false);
    expect(isBoundaryValid(0, Number.NEGATIVE_INFINITY)).toBe(false);
  });
});
