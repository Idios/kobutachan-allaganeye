import { describe, expect, it } from 'vitest';

import {
  appErrorCodeIs,
  appErrorHint,
  appErrorMessage,
  isAppError,
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

describe('appErrorMessage', () => {
  it('extracts message from AppError', () => {
    expect(
      appErrorMessage({ code: 'io.read_failed', message: 'read fail' }),
    ).toBe('read fail');
  });

  it('falls back to Error.message', () => {
    expect(appErrorMessage(new Error('oops'))).toBe('oops');
  });

  it('coerces raw string to string (legacy fallback)', () => {
    expect(appErrorMessage('legacy raw')).toBe('legacy raw');
  });

  it('coerces null/undefined to their string representation', () => {
    expect(appErrorMessage(null)).toBe('null');
    expect(appErrorMessage(undefined)).toBe('undefined');
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

describe('appErrorHint', () => {
  it('returns hint when present', () => {
    expect(
      appErrorHint({
        code: 'io.read_failed',
        message: '',
        hint: 'check perms',
      }),
    ).toBe('check perms');
  });

  it('returns null when hint missing', () => {
    expect(appErrorHint({ code: 'io.read_failed', message: '' })).toBeNull();
  });

  it('returns null for non-AppError', () => {
    expect(appErrorHint('legacy raw')).toBeNull();
    expect(appErrorHint(null)).toBeNull();
    expect(appErrorHint(new Error('boom'))).toBeNull();
  });

  it('returns null when hint is non-string', () => {
    expect(
      appErrorHint({
        code: 'io.read_failed',
        message: '',
        hint: 42 as unknown as string,
      }),
    ).toBeNull();
  });
});
