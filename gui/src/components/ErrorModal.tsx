import { invoke } from '@tauri-apps/api/core';
import { useRef, useState } from 'react';

import { useEscapeKey } from '../hooks/useEscapeKey';
import { useFocusTrap } from '../hooks/useFocusTrap';
import { useErrorStore } from '../state/errorStore';
import styles from './ErrorModal.module.css';

const ISSUE_REPORT_URL =
  'https://github.com/Idios/kobutachan-allaganeye/issues/new?template=bug_report.yml';

/**
 * #614: surfaced when an unrecoverable error occurs:
 *   - Rust panic (Tauri "panic" event)
 *   - React render exception (caught by ErrorBoundary)
 *   - Unhandled JS exception or promise rejection
 *   - Previous-session panic detected on startup
 *
 * Recoverable errors (load_metadata I/O failure, conflict, etc.) keep using
 * the existing inline + toast UI per docs/ui-interaction-spec.md §1.5.
 *
 * Action buttons:
 *   - 詳細をコピー: copy {message, stack, category, timestamp} to clipboard
 *   - ログフォルダを開く: invoke open_folder_in_explorer
 *   - 閉じる: dismissError() — only when isRecoverable === true
 *   - アプリを終了: invoke force_exit_app — only when isPanic === true
 */
export function ErrorModal() {
  const errorOpen = useErrorStore((s) => s.errorOpen);
  const errorTitle = useErrorStore((s) => s.errorTitle);
  const errorMessage = useErrorStore((s) => s.errorMessage);
  const errorStack = useErrorStore((s) => s.errorStack);
  const errorHint = useErrorStore((s) => s.errorHint);
  const errorCategory = useErrorStore((s) => s.errorCategory);
  const isPanic = useErrorStore((s) => s.isPanic);
  const isRecoverable = useErrorStore((s) => s.isRecoverable);
  const logDir = useErrorStore((s) => s.logDir);
  const timestamp = useErrorStore((s) => s.timestamp);
  const dismissError = useErrorStore((s) => s.dismissError);

  const panelRef = useRef<HTMLDivElement>(null);
  const [copyAck, setCopyAck] = useState(false);

  // Escape closes only when the error is recoverable; for panic we want the
  // user to acknowledge with a deliberate click on "アプリを終了".
  useFocusTrap(panelRef, errorOpen);
  useEscapeKey(errorOpen && isRecoverable, dismissError);

  if (!errorOpen) return null;

  const defaultTitle = isPanic
    ? 'アプリ内部でエラーが発生しました'
    : '予期しないエラーが発生しました';
  const title = errorTitle || defaultTitle;

  function handleCopyDetails() {
    const payload = {
      message: errorMessage,
      stack: errorStack,
      category: errorCategory,
      timestamp,
    };
    const text = JSON.stringify(payload, null, 2);
    void navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopyAck(true);
        setTimeout(() => setCopyAck(false), 1500);
      })
      .catch(() => {
        setCopyAck(false);
      });
  }

  function handleOpenLogFolder() {
    if (!logDir) return;
    void invoke('open_folder_in_explorer', { path: logDir }).catch(() => {
      // best-effort — failures are surfaced separately
    });
  }

  function handleForceExit() {
    void invoke('force_exit_app').catch(() => {
      // force_exit_app does not normally fail; if it does, leave the modal
      // open so the user can retry or copy details.
    });
  }

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby="ae-error-title"
    >
      <div ref={panelRef} className={styles.panel}>
        <h2 id="ae-error-title" className={styles.title}>
          {title}
        </h2>
        <p className={styles.message}>{errorMessage}</p>

        {errorStack && (
          <details className={styles.details}>
            <summary className={styles.detailsSummary}>詳細 (stacktrace)</summary>
            <pre className={styles.stackPre}>{errorStack}</pre>
          </details>
        )}

        <div className={styles.hintBlock}>
          {errorHint && <p>{errorHint}</p>}
          <p>
            問題が継続する場合は{' '}
            <a href={ISSUE_REPORT_URL} target="_blank" rel="noopener noreferrer">
              Issue で報告する
            </a>
            {' '}か、バグ報告ガイドを参照してください。
          </p>
          {logDir && (
            <div className={styles.logPathRow}>
              <span className={styles.logPath}>ログ場所: {logDir}</span>
              <button
                type="button"
                className={styles.button}
                onClick={handleOpenLogFolder}
              >
                ログフォルダを開く
              </button>
            </div>
          )}
        </div>

        <div className={styles.actions}>
          {copyAck && <span className={styles.copyAck}>コピー完了</span>}
          <button
            type="button"
            className={styles.button}
            onClick={handleCopyDetails}
          >
            詳細をコピー
          </button>
          {isRecoverable && (
            <button
              type="button"
              className={styles.button}
              onClick={() => dismissError()}
            >
              閉じる
            </button>
          )}
          {isPanic && (
            <button
              type="button"
              className={`${styles.button} ${styles.buttonDanger}`}
              onClick={handleForceExit}
            >
              アプリを終了
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
