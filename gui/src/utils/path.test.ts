import { describe, expect, it } from 'vitest';

import { joinPath, stripExtendedPathPrefix } from './path';

describe('stripExtendedPathPrefix', () => {
  it('strips \\\\?\\ from drive-letter paths', () => {
    expect(stripExtendedPathPrefix('\\\\?\\C:\\foo')).toBe('C:\\foo');
    expect(stripExtendedPathPrefix('\\\\?\\E:\\videos\\x.mkv')).toBe(
      'E:\\videos\\x.mkv',
    );
  });

  it('converts \\\\?\\UNC\\ to \\\\ form', () => {
    expect(stripExtendedPathPrefix('\\\\?\\UNC\\server\\share\\foo')).toBe(
      '\\\\server\\share\\foo',
    );
  });

  it('passes through paths without the prefix', () => {
    expect(stripExtendedPathPrefix('C:\\foo')).toBe('C:\\foo');
    expect(stripExtendedPathPrefix('/home/user/file')).toBe('/home/user/file');
    expect(stripExtendedPathPrefix('')).toBe('');
  });
});

// #545 mystifying-ptolemy-d112b5 review (2026-04-25): separator 推定ロジック
// が Windows / POSIX / mixed で一貫することをガード。
describe('joinPath', () => {
  it('uses \\\\ for backslash-only dir paths (Windows native)', () => {
    expect(joinPath('E:\\videos\\output', 'match_001.mp4')).toBe(
      'E:\\videos\\output\\match_001.mp4',
    );
    expect(joinPath('C:\\Users\\me', 'clip.mkv')).toBe(
      'C:\\Users\\me\\clip.mkv',
    );
  });

  it('uses / for forward-slash-only dir paths (POSIX)', () => {
    expect(joinPath('/home/user/output', 'match_001.mp4')).toBe(
      '/home/user/output/match_001.mp4',
    );
    expect(joinPath('E:/videos/output', 'match_001.mp4')).toBe(
      'E:/videos/output/match_001.mp4',
    );
  });

  it('prefers / when dir contains both \\\\ and /', () => {
    // mixed (Windows path で internal `/` を含むケース等) の現状動作
    // (forward-slash 優先) をスナップショット
    expect(joinPath('E:/videos\\output', 'x.mp4')).toBe(
      'E:/videos\\output/x.mp4',
    );
  });

  it('does not duplicate trailing separator', () => {
    expect(joinPath('E:\\videos\\output\\', 'match_001.mp4')).toBe(
      'E:\\videos\\output\\match_001.mp4',
    );
    expect(joinPath('/home/user/output/', 'match_001.mp4')).toBe(
      '/home/user/output/match_001.mp4',
    );
  });
});
