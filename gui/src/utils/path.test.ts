import { describe, expect, it } from 'vitest';

import { splitPath, stripExtendedPathPrefix } from './path';

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

describe('splitPath', () => {
  it('splits a Windows path', () => {
    expect(splitPath('E:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'E:\\videos' });
  });

  it('splits a POSIX path', () => {
    expect(splitPath('/tmp/foo.mp4'))
      .toEqual({ fileName: 'foo.mp4', parentDir: '/tmp' });
  });

  it('strips \\\\?\\ prefix before splitting', () => {
    expect(splitPath('\\\\?\\C:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:\\videos' });
  });

  it('returns empty parentDir for separator-less path', () => {
    expect(splitPath('foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: '' });
  });

  it('returns both empty for empty string', () => {
    expect(splitPath('')).toEqual({ fileName: '', parentDir: '' });
  });

  it('handles drive-root file', () => {
    expect(splitPath('C:\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:' });
  });
});
