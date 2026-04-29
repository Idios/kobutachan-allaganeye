import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useErrorStore } from './errorStore';

describe('errorStore', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    vi.restoreAllMocks();
  });

  it('showError sets all fields', () => {
    useErrorStore.getState().showError({
      errorTitle: 'oops',
      errorMessage: 'something went wrong',
      errorStack: 'at foo (bar.ts:1:2)',
      errorHint: 'try again',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorTitle).toBe('oops');
    expect(state.errorMessage).toBe('something went wrong');
    expect(state.errorStack).toBe('at foo (bar.ts:1:2)');
    expect(state.errorHint).toBe('try again');
    expect(state.errorCategory).toBe('js-error');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(false);
    expect(state.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('dismissError clears all error fields', () => {
    useErrorStore.getState().showError({
      errorMessage: 'first',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    useErrorStore.getState().dismissError();
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(false);
    expect(state.errorTitle).toBeNull();
    expect(state.errorMessage).toBeNull();
    expect(state.errorStack).toBeNull();
    expect(state.errorHint).toBeNull();
    expect(state.errorCategory).toBeNull();
    expect(state.isPanic).toBe(false);
    expect(state.timestamp).toBeNull();
  });

  it('first-write-wins: second showError while open is ignored', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    useErrorStore.getState().showError({
      errorMessage: 'first',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    useErrorStore.getState().showError({
      errorMessage: 'second',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    const state = useErrorStore.getState();
    expect(state.errorMessage).toBe('first');
    expect(state.errorCategory).toBe('js-error');
    expect(state.isPanic).toBe(false);
    expect(warnSpy).toHaveBeenCalledOnce();
  });

  it('showError after dismiss accepts a new error', () => {
    useErrorStore.getState().showError({
      errorMessage: 'first',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    useErrorStore.getState().dismissError();
    useErrorStore.getState().showError({
      errorMessage: 'second',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    const state = useErrorStore.getState();
    expect(state.errorMessage).toBe('second');
    expect(state.isPanic).toBe(true);
  });

  it('setLogDir updates logDir without affecting other state', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    useErrorStore.getState().setLogDir('C:\\install\\logs');
    const state = useErrorStore.getState();
    expect(state.logDir).toBe('C:\\install\\logs');
    expect(state.errorOpen).toBe(true);
    expect(state.errorMessage).toBe('msg');
  });

  it('setLogDir(null) resets logDir', () => {
    useErrorStore.getState().setLogDir('foo');
    useErrorStore.getState().setLogDir(null);
    expect(useErrorStore.getState().logDir).toBeNull();
  });
});
