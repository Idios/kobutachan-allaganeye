// #1164: mutation testing (mutator) の undetected を潰すための網羅。
// 既存 describe のハーネス（listenMock / invokeMock / unlisten）を再利用する。
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

type Handler = (event: { payload: unknown }) => void;

describe('globalErrorListener (mutation coverage, #1164)', () => {
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

  /** listen のハンドラを event 名で捕まえる（install 直後に microtask を流す）。 */
  async function installCapturing() {
    const captured = new Map<string, Handler>();
    listenMock.mockImplementation(async (name: string, handler: Handler) => {
      captured.set(name, handler);
      return () => {};
    });
    unlisten = installGlobalErrorListener();
    await Promise.resolve();
    await Promise.resolve();
    return captured;
  }

  function rejectWith(reason: unknown) {
    const evt = new Event('unhandledrejection') as PromiseRejectionEvent;
    Object.defineProperty(evt, 'reason', { value: reason });
    Object.defineProperty(evt, 'promise', { value: Promise.resolve() });
    window.dispatchEvent(evt);
  }

  function integrity(payload: Record<string, unknown>) {
    return {
      payload: {
        missing: [],
        sizeMismatch: [],
        logPath: '/install/logs/error.log',
        ...payload,
      },
    };
  }

  describe('formatIntegrityMessage', () => {
    it('renders an empty message when there is nothing to report', async () => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(integrity({}));
      expect(useErrorStore.getState().errorMessage).toBe('');
    });

    it('renders only the missing section for a missing-only payload', async () => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(integrity({ missing: ['a.npz'] }));
      expect(useErrorStore.getState().errorMessage).toBe('欠落しているファイル (1 件):\n  - a.npz');
    });

    it('renders only the size mismatch section for a size-only payload', async () => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(
        integrity({
          sizeMismatch: [{ path: 'b.exe', expected: 10, actual: 5 }],
        }),
      );
      expect(useErrorStore.getState().errorMessage).toBe(
        'サイズ不一致 (1 件):\n  - b.exe (expected 10 bytes, actual 5 bytes)',
      );
    });

    it('appends the manifest error section last', async () => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(
        integrity({
          missing: ['a.npz'],
          sizeMismatch: [{ path: 'b.exe', expected: 10, actual: 5 }],
          manifestError: 'parse failed',
        }),
      );
      expect(useErrorStore.getState().errorMessage).toBe(
        [
          '欠落しているファイル (1 件):',
          '  - a.npz',
          'サイズ不一致 (1 件):',
          '  - b.exe (expected 10 bytes, actual 5 bytes)',
          'Manifest エラー (#702 review #4):',
          '  parse failed',
        ].join('\n'),
      );
    });

    it('shows the title and hint of the integrity modal', async () => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(integrity({ missing: ['a.npz'] }));
      const state = useErrorStore.getState();
      expect(state.errorTitle).toBe('同梱物の検証に失敗しました');
      expect(state.errorHint).toBe('Portable ZIP を再展開してください。');
    });
  });

  describe('logDirOf', () => {
    const logDirFor = async (logPath: string) => {
      const captured = await installCapturing();
      captured.get('integrity-error')!(integrity({ missing: ['a.npz'], logPath }));
      return useErrorStore.getState().logDir;
    };

    it('strips the file name from a POSIX log path', async () => {
      expect(await logDirFor('/install/logs/error.log')).toBe('/install/logs');
    });

    it('strips the file name from a Windows log path', async () => {
      expect(await logDirFor('C:\\install\\logs\\error.log')).toBe('C:\\install\\logs');
    });

    it('returns the parent of a separator-leading path (index 0)', async () => {
      expect(await logDirFor('/error.log')).toBe('');
    });

    it('returns the input unchanged when it has no separator', async () => {
      expect(await logDirFor('error.log')).toBe('error.log');
    });
  });

  describe('window error events', () => {
    it('records the stack of a real Error', () => {
      unlisten = installGlobalErrorListener();
      const err = new Error('boom');
      window.dispatchEvent(new ErrorEvent('error', { message: 'boom', error: err }));
      const state = useErrorStore.getState();
      expect(state.errorMessage).toBe('boom');
      expect(state.errorStack).toBe(err.stack);
      expect(state.isRecoverable).toBe(false);
    });

    it('falls back to null stack when the event carries no Error', () => {
      unlisten = installGlobalErrorListener();
      window.dispatchEvent(new ErrorEvent('error', { message: 'plain' }));
      const state = useErrorStore.getState();
      expect(state.errorMessage).toBe('plain');
      expect(state.errorStack).toBeNull();
    });

    it('falls back to a generic message for an empty message', () => {
      unlisten = installGlobalErrorListener();
      window.dispatchEvent(new ErrorEvent('error', {}));
      expect(useErrorStore.getState().errorMessage).toBe('Unknown error');
    });
  });

  describe('unhandled rejection events', () => {
    it('uses the generic message when the reason has no usable shape', () => {
      unlisten = installGlobalErrorListener();
      rejectWith(undefined);
      const state = useErrorStore.getState();
      expect(state.errorMessage).toBe('Unhandled promise rejection');
      expect(state.isRecoverable).toBe(false);
      expect(state.isPanic).toBe(false);
    });

    it('does not stringify a primitive reason', () => {
      unlisten = installGlobalErrorListener();
      rejectWith(42);
      expect(useErrorStore.getState().errorMessage).toBe('Unhandled promise rejection');
    });

    it('falls back to String() when the object cannot be serialised', () => {
      unlisten = installGlobalErrorListener();
      rejectWith({
        toJSON() {
          throw new Error('nope');
        },
      });
      expect(useErrorStore.getState().errorMessage).toBe('[object Object]');
    });
  });

  describe('panic events', () => {
    it('falls back to the default message and null stack for an empty payload', async () => {
      const captured = await installCapturing();
      captured.get('panic')!({ payload: {} });
      const state = useErrorStore.getState();
      expect(state.errorMessage).toBe('Rust panic occurred');
      expect(state.errorStack).toBeNull();
      expect(state.isRecoverable).toBe(false);
      expect(state.isPanic).toBe(true);
    });

    it('joins the location and backtrace with a blank line', async () => {
      const captured = await installCapturing();
      captured.get('panic')!({
        payload: {
          message: 'rust boom',
          location: 'src/foo.rs:1:2',
          backtrace: 'frame 1',
        },
      });
      expect(useErrorStore.getState().errorStack).toBe('at src/foo.rs:1:2\n\nframe 1');
    });

    it('leaves the stack empty when the payload has no location', async () => {
      const captured = await installCapturing();
      captured.get('panic')!({ payload: { message: 'rust boom' } });
      expect(useErrorStore.getState().errorStack).toBeNull();
    });
  });

  describe('previous-session panic events', () => {
    it('shows the recorded payload as the stack and pins the texts', async () => {
      const captured = await installCapturing();
      captured.get('panic-from-previous-session')!({
        payload: 'PANIC_MARKER ts=1 payload=oops',
      });
      const state = useErrorStore.getState();
      expect(state.errorStack).toBe('PANIC_MARKER ts=1 payload=oops');
      expect(state.errorMessage).toBe(
        '前回のセッションが panic で終了した可能性があります。詳細はログファイルを参照してください。',
      );
      expect(state.errorHint).toBe('同じエラーが再発する場合は Issue で報告してください。');
    });

    it('uses a null stack for a non-string payload', async () => {
      const captured = await installCapturing();
      captured.get('panic-from-previous-session')!({ payload: { a: 1 } });
      expect(useErrorStore.getState().errorStack).toBeNull();
    });
  });

  describe('lifecycle', () => {
    it('clears the log dir when get_log_dir rejects', async () => {
      useErrorStore.getState().setLogDir('stale-dir');
      invokeMock.mockRejectedValue(new Error('not in tauri'));
      unlisten = installGlobalErrorListener();
      await Promise.resolve();
      await Promise.resolve();
      expect(useErrorStore.getState().logDir).toBeNull();
    });

    it('detaches the window listeners on teardown', () => {
      const remove = vi.spyOn(window, 'removeEventListener');
      const stop = installGlobalErrorListener();
      stop();
      expect(remove).toHaveBeenCalledWith('error', expect.any(Function));
      expect(remove).toHaveBeenCalledWith('unhandledrejection', expect.any(Function));
      remove.mockRestore();
    });
  });
});
