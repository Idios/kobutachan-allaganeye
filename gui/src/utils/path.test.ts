import { describe, expect, it } from 'vitest';

import { stripExtendedPathPrefix } from './path';

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
