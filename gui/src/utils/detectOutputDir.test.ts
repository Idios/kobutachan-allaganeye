import { describe, expect, it } from 'vitest';

import {
  deriveDetectOutputDir,
  metadataPathFor,
} from './detectOutputDir';

describe('deriveDetectOutputDir', () => {
  it('appends _allaganeye to the basename next to the source', () => {
    expect(
      deriveDetectOutputDir('C:/videos/2026-04-08 21-14-05.mkv'),
    ).toBe('C:/videos/2026-04-08 21-14-05_allaganeye');
  });

  it('normalizes Windows backslashes to forward slashes', () => {
    expect(deriveDetectOutputDir('C:\\videos\\foo.mkv')).toBe(
      'C:/videos/foo_allaganeye',
    );
  });

  it('drops the file extension before suffixing', () => {
    expect(deriveDetectOutputDir('D:/clips/match.MP4')).toBe(
      'D:/clips/match_allaganeye',
    );
  });

  it('handles a file without extension', () => {
    expect(deriveDetectOutputDir('D:/clips/RECORDING')).toBe(
      'D:/clips/RECORDING_allaganeye',
    );
  });

  it('treats a leading dot file as a stem (no extension split)', () => {
    expect(deriveDetectOutputDir('D:/clips/.cachefile')).toBe(
      'D:/clips/.cachefile_allaganeye',
    );
  });

  it('handles a bare filename with no directory', () => {
    expect(deriveDetectOutputDir('foo.mkv')).toBe('./foo_allaganeye');
  });

  it('strips trailing slashes before splitting', () => {
    expect(deriveDetectOutputDir('C:/videos/foo.mkv/')).toBe(
      'C:/videos/foo_allaganeye',
    );
  });
});

describe('metadataPathFor', () => {
  it('joins output dir and metadata.json', () => {
    expect(metadataPathFor('C:/videos/foo_allaganeye')).toBe(
      'C:/videos/foo_allaganeye/metadata.json',
    );
  });

  it('strips trailing slash before joining', () => {
    expect(metadataPathFor('C:/videos/foo_allaganeye/')).toBe(
      'C:/videos/foo_allaganeye/metadata.json',
    );
  });

  it('normalizes backslashes', () => {
    expect(metadataPathFor('C:\\videos\\foo_allaganeye')).toBe(
      'C:/videos/foo_allaganeye/metadata.json',
    );
  });
});
