import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { useCallback, useEffect, useRef, useState } from 'react';

import { useEscapeKey } from '../hooks/useEscapeKey';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { appErrorHint, appErrorMessage } from '../lib/appError';
import { InlineErrorHint } from './InlineErrorHint';
import styles from './ConfirmExitModal.module.css';

/**
 * #523: bridge the Tauri-side `on_window_event(CloseRequested)` to a user
 * confirmation flow when a tracked ffmpeg child is alive.
 *
 * Flow:
 * 1. Rust prevents the window from closing and emits `close-requested`.
 * 2. This component listens for it, asks Rust whether any process is
 *    running, and either exits immediately (idle path) or surfaces the
 *    modal (running path).
 * 3. On "終了", the component kills tracked processes then calls
 *    `force_exit_app`. On "キャンセル", it dismisses the modal and lets
 *    the user keep working.
 *
 * Global modal -- rendered once in App.tsx.
 */
export function ConfirmExitModal() {
  const [pending, setPending] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [errorHint, setErrorHint] = useState<string | null>(null);

  const handleCloseRequested = useCallback(async () => {
    try {
      const running = await invoke<boolean>('is_process_running');
      if (!running) {
        await invoke('force_exit_app');
        return;
      }
      setPending(true);
    } catch (e) {
      // Defensive: if the probe itself fails, show the modal so the user
      // can still pick between kill + exit vs cancel rather than leaving
      // them unable to close the window.
      setError(appErrorMessage(e));
      setErrorHint(appErrorHint(e));
      setPending(true);
    }
  }, []);

  useEffect(() => {
    let unlisten: (() => void) | null = null;
    (async () => {
      unlisten = await listen('close-requested', () => {
        void handleCloseRequested();
      });
    })();
    return () => {
      unlisten?.();
    };
  }, [handleCloseRequested]);

  const handleKillAndExit = useCallback(async () => {
    setBusy(true);
    setError(null);
    setErrorHint(null);
    try {
      await invoke('kill_tracked_processes');
      await invoke('force_exit_app');
    } catch (e) {
      setBusy(false);
      setError(appErrorMessage(e));
      setErrorHint(appErrorHint(e));
    }
  }, []);

  const handleCancel = useCallback(() => {
    setPending(false);
    setError(null);
    setErrorHint(null);
  }, []);

  // #587: trap Tab inside the modal and let Escape act as キャンセル.
  const panelRef = useRef<HTMLDivElement>(null);
  useFocusTrap(panelRef, pending);
  useEscapeKey(pending, handleCancel);

  if (!pending) return null;

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ae-exit-title"
    >
      <div ref={panelRef} className={styles.panel}>
        <h2 id="ae-exit-title" className={styles.title}>
          実行中のプロセスがあります
        </h2>
        <p className={styles.hint}>
          ffmpeg または関連プロセスが動作中です。「終了」でプロセスを中断してアプリを閉じます (中間ファイルは破棄)。「キャンセル」でモーダルを閉じて作業を続行します。
        </p>
        {error && (
          <p className={styles.message} role="alert">
            <span>{error}</span>
            {errorHint && (
              <span className={styles.errorHint}>
                <InlineErrorHint hint={errorHint} />
              </span>
            )}
          </p>
        )}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.button}
            onClick={() => {
              void handleKillAndExit();
            }}
            disabled={busy}
          >
            {busy ? '終了中…' : '終了'}
          </button>
          <button
            type="button"
            className={styles.button}
            onClick={handleCancel}
            disabled={busy}
          >
            キャンセル
          </button>
        </div>
      </div>
    </div>
  );
}
