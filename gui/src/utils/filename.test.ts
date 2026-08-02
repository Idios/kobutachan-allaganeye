import { describe, expect, it } from 'vitest';

import { formatMatchFilename, formatStartForFilename } from './filename';

// #545 review #8: filename `{start}` の HH-MM format helper
// (#932 で ExportScreen.tsx から utils/filename.ts へ移設。テストも追随)
describe('formatStartForFilename', () => {
  it('formats sub-hour seconds as MM-SS', () => {
    expect(formatStartForFilename(0)).toBe('00-00');
    expect(formatStartForFilename(49)).toBe('00-49');
    expect(formatStartForFilename(60)).toBe('01-00');
    expect(formatStartForFilename(915.5)).toBe('15-15');
  });

  it('formats hour-plus seconds as H-MM-SS', () => {
    expect(formatStartForFilename(3600)).toBe('1-00-00');
    expect(formatStartForFilename(5021.5)).toBe('1-23-41');
  });

  it('clamps NaN / negative to 0', () => {
    expect(formatStartForFilename(Number.NaN)).toBe('00-00');
    expect(formatStartForFilename(-1)).toBe('00-00');
  });

  it('truncates fractional seconds (floor semantics)', () => {
    expect(formatStartForFilename(59.9)).toBe('00-59');
  });
});

describe('formatMatchFilename', () => {
  it('expands the export default pattern', () => {
    expect(formatMatchFilename('{idx:03}_{type}_{start}.mp4', 2, 'fl_match', 1129.5)).toBe(
      '002_fl_match_18-49.mp4',
    );
  });

  it('expands the minimap default pattern', () => {
    expect(
      formatMatchFilename('{idx:03}_{type}_{start}_minimap.mp4', 5, 'fl_match', 5021.5),
    ).toBe('005_fl_match_1-23-41_minimap.mp4');
  });

  it('expands {idx} without zero padding', () => {
    expect(formatMatchFilename('{idx}-{type}.mp4', 12, 'unknown', 0)).toBe('12-unknown.mp4');
  });

  it('replaces {idx:03} before {idx} so the padded token is not shredded', () => {
    // 素朴に {idx} を先に置換すると '{idx' が食われて '2:03}' が残る
    expect(formatMatchFilename('{idx:03}', 2, 'fl_match', 0)).toBe('002');
  });

  it('replaces every occurrence of a token, not just the first', () => {
    expect(formatMatchFilename('{idx}_{idx}.mp4', 7, 'fl_match', 0)).toBe('7_7.mp4');
  });

  it('expands {date} as YYYY-MM-DD', () => {
    const out = formatMatchFilename('{date}.mp4', 1, 'fl_match', 0);
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2}\.mp4$/);
  });

  it('leaves a pattern without tokens untouched', () => {
    expect(formatMatchFilename('fixed.mp4', 3, 'fl_match', 999)).toBe('fixed.mp4');
  });
});
