import { describe, expect, it } from 'vitest';

import {
  computeNamePatternIssues,
  type SandboxRow,
} from './namePatternSandbox';

// #964: GUI の name-pattern プレビューは CLI (allaganeye/export/pool.py 層 1) と
// 同じ 4 クラスを検知して警告する。本テストは pool.py の premise pin
// (tests/test_export_pool.py / test_path_schema_contracts.py) の TS mirror。

const SOURCE = 'C:/videos/source.mkv';

function rows(...types: string[]): SandboxRow[] {
  return types.map((type, i) => ({ index: i, type, startSec: i * 10 }));
}

function issues(
  pattern: string,
  outDir: string,
  rowList: SandboxRow[],
  sourceVideo: string | null = SOURCE,
) {
  return computeNamePatternIssues({
    pattern,
    outputDir: outDir,
    sourceVideo,
    rows: rowList,
  });
}

describe('computeNamePatternIssues: escape (containment)', () => {
  it('rejects a leading `..` that leaves the output dir', () => {
    const got = issues('../victim.mp4', 'C:/videos/out', rows('match'));
    expect(got.map((i) => i.kind)).toEqual(['escape']);
  });

  it('accepts `..` that stays inside the output dir', () => {
    expect(issues('sub/../clip.mp4', 'C:/videos/out', rows('match'))).toEqual([]);
  });

  it('rejects an absolute (different-drive) pattern', () => {
    const got = issues('D:/victim.mp4', 'C:/videos/out', rows('match'));
    expect(got.map((i) => i.kind)).toEqual(['escape']);
  });

  it('rejects a different-drive drive-relative pattern', () => {
    // `D:x.mp4` resolves against D:'s own CWD — never inside C:/videos/out.
    const got = issues('D:x.mp4', 'C:/videos/out', rows('match'));
    expect(got.map((i) => i.kind)).toEqual(['escape']);
  });

  it('accepts a same-drive drive-relative pattern (ntpath join semantics)', () => {
    // pool.py premise: `C:x.mp4` under a C: output dir joins inside the sandbox.
    expect(issues('C:x.mp4', 'C:/videos/out', rows('match'))).toEqual([]);
  });
});

describe('computeNamePatternIssues: source overwrite', () => {
  it('rejects a rendered name that is the source video (case-insensitive)', () => {
    const got = issues('SOURCE.MKV', 'C:/videos', rows('match'), 'C:/videos/source.mkv');
    expect(got.map((i) => i.kind)).toEqual(['overwriteSource']);
  });

  it('does not reject a normal name next to the source', () => {
    expect(issues('clip.mp4', 'C:/videos', rows('match'))).toEqual([]);
  });
});

describe('computeNamePatternIssues: invalid Windows filename', () => {
  it('rejects `:` (NTFS ADS syntax) coming from the {type} token', () => {
    const got = issues('{type}', 'C:/videos/out', rows('clip::$DATA'));
    expect(got.map((i) => i.kind)).toEqual(['invalidWindowsName']);
    expect(got[0].message).toContain(':');
  });

  it('rejects a bare reserved device name', () => {
    for (const reserved of ['NUL', 'CON', 'com1', 'lpt9']) {
      const got = issues('{type}', 'C:/videos/out', rows(reserved));
      expect(got.map((i) => i.kind)).toEqual(['invalidWindowsName']);
      expect(got[0].sampleName).toBe(reserved);
    }
  });

  it('accepts a reserved name with an extension (measured ordinary file)', () => {
    expect(issues('{type}', 'C:/videos/out', rows('NUL.mp4'))).toEqual([]);
  });
});

describe('computeNamePatternIssues: duplicate identity', () => {
  it('rejects two matches mapping to one file (case difference)', () => {
    const got = issues('{type}.mp4', 'C:/videos/out', rows('Clip', 'clip'));
    expect(got.map((i) => i.kind)).toEqual(['collision']);
    expect(got[0].message).toContain('{idx}');
  });

  it('rejects two matches mapping to one file (trailing dot fold)', () => {
    const got = issues('{type}', 'C:/videos/out', rows('clip.mp4', 'clip.mp4.'));
    expect(got.map((i) => i.kind)).toEqual(['collision']);
  });

  it('accepts the default patterns that carry {idx}', () => {
    expect(
      issues('match_{idx:03}.mp4', 'C:/videos/out', rows('match', 'match', 'match')),
    ).toEqual([]);
    expect(
      issues('{idx:03}_{type}_{start}_minimap.mp4', 'C:/videos/out', rows('a', 'a')),
    ).toEqual([]);
  });

  it('accepts two genuinely distinct names', () => {
    expect(issues('{type}.mp4', 'C:/videos/out', rows('clip_a', 'clip_b'))).toEqual([]);
  });
});

describe('computeNamePatternIssues: edge inputs', () => {
  it('returns no warnings for an empty output dir or empty rows', () => {
    expect(issues('{idx}.mp4', '', rows('match'))).toEqual([]);
    expect(
      computeNamePatternIssues({
        pattern: 'x.mp4',
        outputDir: 'C:/videos/out',
        sourceVideo: null,
        rows: [],
      }),
    ).toEqual([]);
  });

  it('deduplicates identical warnings across rows', () => {
    // All three rows escape with the same rendered name -> one warning.
    const got = issues('../same.mp4', 'C:/videos/out', rows('a', 'b', 'c'));
    expect(got).toHaveLength(1);
    expect(got[0].kind).toBe('escape');
  });

  it('keeps deterministic ordering (escape first, collision last)', () => {
    const got = computeNamePatternIssues({
      pattern: '{type}',
      outputDir: 'C:/videos',
      sourceVideo: 'C:/videos/source.mkv',
      rows: rows('SOURCE.MKV', 'a', 'a'),
    });
    expect(got.map((i) => i.kind)).toEqual(['overwriteSource', 'collision']);
  });
});
