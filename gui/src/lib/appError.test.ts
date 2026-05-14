import { describe, expect, it } from 'vitest';

import {
  appErrorCodeIs,
  isAppError,
  toErrorState,
} from './appError';

describe('isAppError', () => {
  it('returns true for object with code and message', () => {
    expect(
      isAppError({ code: 'io.file_not_found', message: 'not found' }),
    ).toBe(true);
  });

  it('returns true for object with optional hint and stacktrace fields', () => {
    expect(
      isAppError({
        code: 'state.mtime_conflict',
        message: 'conflict',
        hint: 'reload',
        stacktrace: 'at line 1',
      }),
    ).toBe(true);
  });

  it('returns false for raw string (legacy fallback)', () => {
    expect(isAppError('legacy raw error')).toBe(false);
  });

  it('returns false for null and undefined', () => {
    expect(isAppError(null)).toBe(false);
    expect(isAppError(undefined)).toBe(false);
  });

  it('returns false when code is missing', () => {
    expect(isAppError({ message: 'incomplete' })).toBe(false);
  });

  it('returns false when message is missing', () => {
    expect(isAppError({ code: 'io.read_failed' })).toBe(false);
  });

  it('returns false when code is non-string', () => {
    expect(isAppError({ code: 42, message: 'x' })).toBe(false);
  });

  it('returns false for Error instance (no code field)', () => {
    expect(isAppError(new Error('boom'))).toBe(false);
  });
});

describe('appErrorCodeIs', () => {
  it('matches expected code', () => {
    expect(
      appErrorCodeIs(
        { code: 'state.mtime_conflict', message: '' },
        'state.mtime_conflict',
      ),
    ).toBe(true);
  });

  it('rejects mismatched code', () => {
    expect(
      appErrorCodeIs(
        { code: 'io.read_failed', message: '' },
        'state.mtime_conflict',
      ),
    ).toBe(false);
  });

  it('rejects non-AppError safely (false rather than throw)', () => {
    expect(appErrorCodeIs('legacy raw', 'state.mtime_conflict')).toBe(false);
    expect(appErrorCodeIs(null, 'state.mtime_conflict')).toBe(false);
    expect(appErrorCodeIs(new Error('boom'), 'state.mtime_conflict')).toBe(
      false,
    );
  });
});

describe('toErrorState', () => {
  it('normalizes AppError into ErrorState (with code / hint)', () => {
    const result = toErrorState({
      code: 'io.file_not_found',
      message: 'metadata.json not found',
      hint: 'ファイルパスを確認してください',
    });
    expect(result).toEqual({
      message: 'metadata.json not found',
      hint: 'ファイルパスを確認してください',
      code: 'io.file_not_found',
    });
  });

  it('coerces hint:undefined to null when AppError has no hint', () => {
    const result = toErrorState({
      code: 'io.read_failed',
      message: 'read fail',
    });
    expect(result).toEqual({
      message: 'read fail',
      hint: null,
      code: 'io.read_failed',
    });
  });

  it('coerces non-string hint to null (defensive)', () => {
    const result = toErrorState({
      code: 'io.read_failed',
      message: 'read fail',
      hint: 42 as unknown as string,
    });
    expect(result).toEqual({
      message: 'read fail',
      hint: null,
      code: 'io.read_failed',
    });
  });

  it('extracts Error.message with null hint / null code', () => {
    const result = toErrorState(new Error('boom'));
    expect(result).toEqual({
      message: 'boom',
      hint: null,
      code: null,
    });
  });

  it('coerces raw string to string with null hint / null code (legacy fallback)', () => {
    const result = toErrorState('legacy raw error');
    expect(result).toEqual({
      message: 'legacy raw error',
      hint: null,
      code: null,
    });
  });

  it('coerces null / undefined to their string representation', () => {
    expect(toErrorState(null)).toEqual({
      message: 'null',
      hint: null,
      code: null,
    });
    expect(toErrorState(undefined)).toEqual({
      message: 'undefined',
      hint: null,
      code: null,
    });
  });
});
