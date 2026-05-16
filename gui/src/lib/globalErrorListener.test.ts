import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useErrorStore } from '../state/errorStore';
import { installGlobalErrorListener } from './globalErrorListener';

const invokeMock = vi.fn();
const listenMock = vi.fn();

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => listenMock(...args),
}));

describe('installGlobalErrorListener', () => {
  let unlisten: (() => void) | null = null;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    invokeMock.mockReset();
    listenMock.mockReset();
    invokeMock.mockResolvedValue('C:\\install\\logs');
    listenMock.mockResolvedValue(() => {});
    unlisten = null;
  });

  afterEach(() => {
    if (unlisten) {
      try {
        unlisten();
      } catch {
        // ignore
      }
      unlisten = null;
    }
  });

  it('captures window error events', () => {
    unlisten = installGlobalErrorListener();
    const evt = new ErrorEvent('error', {
      message: 'sync explosion',
      error: new Error('sync explosion'),
    });
    window.dispatchEvent(evt);
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorMessage).toBe('sync explosion');
    expect(state.errorCategory).toBe('js-error');
    expect(state.isPanic).toBe(false);
  });

  it('captures unhandledrejection with Error reason', () => {
    unlisten = installGlobalErrorListener();
    const err = new Error('promise rejected');
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', { value: err });
    Object.defineProperty(evt, 'promise', { value: Promise.reject(err) });
    window.dispatchEvent(evt);
    void evt.promise.catch(() => {});
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorMessage).toBe('promise rejected');
    expect(state.errorCategory).toBe('js-promise');
  });

  it('captures unhandledrejection with string reason', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', { value: 'string reason' });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);
    expect(useErrorStore.getState().errorMessage).toBe('string reason');
  });

  it('subscribes to Tauri panic events', () => {
    unlisten = installGlobalErrorListener();
    expect(listenMock).toHaveBeenCalledWith('panic', expect.any(Function));
    expect(listenMock).toHaveBeenCalledWith(
      'panic-from-previous-session',
      expect.any(Function),
    );
  });

  it('panic event handler dispatches panic error', async () => {
    type PanicHandler = (event: { payload: unknown }) => void;
    const captured: { panic?: PanicHandler } = {};
    listenMock.mockImplementation(
      async (name: string, h: PanicHandler) => {
        if (name === 'panic') captured.panic = h;
        return () => {};
      },
    );
    unlisten = installGlobalErrorListener();
    // Wait microtasks so listen() promise resolves
    await Promise.resolve();
    await Promise.resolve();
    expect(captured.panic).toBeDefined();
    captured.panic!({
      payload: {
        message: 'rust boom',
        backtrace: 'frame 1\nframe 2',
        location: 'src/foo.rs:1:2',
        timestamp: '2026-01-01T00:00:00Z',
      },
    });
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorMessage).toBe('rust boom');
    expect(state.errorCategory).toBe('panic');
    expect(state.isPanic).toBe(true);
    expect(state.errorStack).toContain('src/foo.rs:1:2');
  });

  it('previous-session-panic event handler shows recoverable warning', async () => {
    type PrevHandler = (event: { payload: unknown }) => void;
    const captured: { prev?: PrevHandler } = {};
    listenMock.mockImplementation(
      async (name: string, h: PrevHandler) => {
        if (name === 'panic-from-previous-session') captured.prev = h;
        return () => {};
      },
    );
    unlisten = installGlobalErrorListener();
    await Promise.resolve();
    await Promise.resolve();
    expect(captured.prev).toBeDefined();
    captured.prev!({ payload: 'PANIC_MARKER ts=... payload=oops' });
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('previous-session-panic');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(true);
    expect(state.errorTitle).toBe('前回起動時にエラー終了しました');
  });

  it('fetches log dir via get_log_dir', async () => {
    unlisten = installGlobalErrorListener();
    expect(invokeMock).toHaveBeenCalledWith('get_log_dir');
    // Wait for promise chain
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
    expect(useErrorStore.getState().logDir).toBe('C:\\install\\logs');
  });
});

describe('integrity-error event (#668)', () => {
  let unlisten: (() => void) | null = null;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    invokeMock.mockReset();
    listenMock.mockReset();
    invokeMock.mockResolvedValue('C:\\install\\logs');
    listenMock.mockResolvedValue(() => {});
    unlisten = null;
  });

  afterEach(() => {
    if (unlisten) {
      try {
        unlisten();
      } catch {
        // ignore
      }
      unlisten = null;
    }
  });

  it('shows ErrorModal with integrity category when integrity-error fires', async () => {
    type IntegrityHandler = (event: { payload: unknown }) => void;
    const captured: { integrity?: IntegrityHandler } = {};
    listenMock.mockImplementation(
      async (name: string, h: IntegrityHandler) => {
        if (name === 'integrity-error') captured.integrity = h;
        return () => {};
      },
    );
    unlisten = installGlobalErrorListener();
    await Promise.resolve();
    await Promise.resolve();
    expect(captured.integrity).toBeDefined();
    captured.integrity!({
      payload: {
        missing: ['lib/allaganeye/audio/refs/fanfare.npz'],
        sizeMismatch: [],
        logPath: '/install/logs/error-20260508.log',
      },
    });

    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('integrity');
    expect(state.isPanic).toBe(true);
    expect(state.isRecoverable).toBe(false);
    expect(state.errorMessage).toContain('lib/allaganeye/audio/refs/fanfare.npz');
    expect(state.logDir).toContain('/install/logs');
  });

  it('formats both missing and size_mismatch arrays in errorMessage', async () => {
    type IntegrityHandler = (event: { payload: unknown }) => void;
    const captured: { integrity?: IntegrityHandler } = {};
    listenMock.mockImplementation(
      async (name: string, h: IntegrityHandler) => {
        if (name === 'integrity-error') captured.integrity = h;
        return () => {};
      },
    );
    unlisten = installGlobalErrorListener();
    await Promise.resolve();
    await Promise.resolve();
    expect(captured.integrity).toBeDefined();
    captured.integrity!({
      payload: {
        missing: ['ffmpeg/ffmpeg.exe'],
        sizeMismatch: [
          { path: 'allaganeye-gui.exe', expected: 1000, actual: 500 },
        ],
        logPath: '/install/logs/error-20260508.log',
      },
    });

    const msg = useErrorStore.getState().errorMessage ?? '';
    expect(msg).toContain('ffmpeg/ffmpeg.exe');
    expect(msg).toContain('allaganeye-gui.exe');
    expect(msg).toContain('1000');
    expect(msg).toContain('500');
  });
});

describe('unhandledrejection AppError fallback (#696)', () => {
  let unlisten: (() => void) | null = null;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    invokeMock.mockReset();
    listenMock.mockReset();
    invokeMock.mockResolvedValue('C:\\install\\logs');
    listenMock.mockResolvedValue(() => {});
    unlisten = null;
  });

  afterEach(() => {
    if (unlisten) {
      try {
        unlisten();
      } catch {
        // ignore
      }
      unlisten = null;
    }
  });

  it('routes AppError reason to tauri-command category with hint', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: {
        code: 'io.permission_denied',
        message: 'Permission denied',
        hint: 'ファイル権限を確認してください',
      },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorCategory).toBe('tauri-command');
    expect(state.errorTitle).toBe('処理中に予期しないエラーが発生しました');
    expect(state.errorMessage).toBe('Permission denied');
    expect(state.errorHint).toBe('ファイル権限を確認してください');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(true);
  });

  it('routes AppError reason without hint to tauri-command (errorHint null)', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: {
        code: 'state.invalid',
        message: 'Invalid state',
      },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorCategory).toBe('tauri-command');
    expect(state.errorMessage).toBe('Invalid state');
    expect(state.errorHint).toBeNull();
  });

  it('non-AppError object reason still uses js-promise path (regression guard)', () => {
    unlisten = installGlobalErrorListener();
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', {
      value: { foo: 'bar' },
    });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);

    const state = useErrorStore.getState();
    expect(state.errorCategory).toBe('js-promise');
    expect(state.errorMessage).toBe('{"foo":"bar"}');
  });
});
