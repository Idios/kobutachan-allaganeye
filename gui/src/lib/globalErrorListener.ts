import { invoke } from '@tauri-apps/api/core';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';

import { isAppError } from './appError';
import { useErrorStore } from '../state/errorStore';

interface PanicPayload {
  message?: string;
  backtrace?: string;
  timestamp?: string;
  location?: string;
}

/**
 * #668: Payload sent from Rust `integrity::check_install_dir` via the
 * `integrity-error` Tauri event. Field names are camelCase (Rust side
 * uses #[serde(rename_all = "camelCase")]).
 */
interface IntegritySizeMismatch {
  path: string;
  expected: number;
  actual: number;
}

interface IntegrityErrorPayload {
  missing: string[];
  sizeMismatch: IntegritySizeMismatch[];
  logPath: string;
  // PR #702 review #4: Rust load_manifest() の error message を Some(...) で
  // 受け取り (manifest 自体 missing / 壊れた JSON 時のみ)、modal で
  // 「fanfare.npz が消えた」と「integrity-manifest.json が JSON parse 失敗」
  // を maintainer 視点で区別できるよう表示する。
  manifestError?: string | null;
}

function formatIntegrityMessage(payload: IntegrityErrorPayload): string {
  const lines: string[] = [];
  if (payload.missing.length > 0) {
    lines.push(`欠落しているファイル (${payload.missing.length} 件):`);
    for (const p of payload.missing) {
      lines.push(`  - ${p}`);
    }
  }
  if (payload.sizeMismatch.length > 0) {
    lines.push(`サイズ不一致 (${payload.sizeMismatch.length} 件):`);
    for (const sm of payload.sizeMismatch) {
      lines.push(`  - ${sm.path} (expected ${sm.expected} bytes, actual ${sm.actual} bytes)`);
    }
  }
  if (payload.manifestError) {
    lines.push(`Manifest エラー (#702 review #4):`);
    lines.push(`  ${payload.manifestError}`);
  }
  return lines.join('\n');
}

function logDirOf(logPath: string): string {
  const idx = Math.max(logPath.lastIndexOf('/'), logPath.lastIndexOf('\\'));
  return idx >= 0 ? logPath.slice(0, idx) : logPath;
}

/**
 * #614: Wires browser + Tauri error events into the errorStore.
 *
 * Sources:
 *   - window.error: synchronous JS errors (script tag eval / setTimeout cb / etc)
 *   - window.unhandledrejection: Promise rejections that nothing caught
 *   - Tauri "panic" event: emitted by the Rust panic hook (best-effort, may
 *     not arrive if WebView2 has died — the file log is the source of truth)
 *   - Tauri "panic-from-previous-session" event: emitted on startup when
 *     the panic hook detects a PANIC_MARKER in a recent log file
 *
 * Also fetches the log directory path via the get_log_dir command so the
 * ErrorModal can show "ログフォルダを開く".
 *
 * Returns an unlistener for tests / hot-reload teardown. In production the
 * listeners live for the entire app lifetime.
 */
export function installGlobalErrorListener(): () => void {
  const showError = useErrorStore.getState().showError;
  const setLogDir = useErrorStore.getState().setLogDir;

  const onWindowError = (e: ErrorEvent) => {
    showError({
      errorMessage: e.message || 'Unknown error',
      errorStack: e.error instanceof Error ? (e.error.stack ?? null) : null,
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
  };

  const onUnhandledRejection = (e: PromiseRejectionEvent) => {
    const reason = e.reason;
    // #696: AppError-shaped reject (Tauri command の catch 漏れ) を
    // ErrorModal の最終 fallback として表示する。screen 側 invoke catch
    // 規約 (`appErrorMessage` + `appErrorHint`) が正しく書かれていれば本
    // 分岐は通らないが、Promise を投げ捨て / async race / try-catch 漏れ
    // 等の caught-miss シナリオで recoverable な modal を出す。
    if (isAppError(reason)) {
      showError({
        errorTitle: '処理中に予期しないエラーが発生しました',
        errorMessage: reason.message,
        errorHint: reason.hint ?? null,
        errorStack: null,
        errorCategory: 'tauri-command',
        isPanic: false,
        isRecoverable: true,
      });
      return;
    }
    let message = 'Unhandled promise rejection';
    let stack: string | null = null;
    if (reason instanceof Error) {
      message = reason.message || message;
      stack = reason.stack ?? null;
    } else if (typeof reason === 'string') {
      message = reason;
    } else if (reason && typeof reason === 'object') {
      try {
        message = JSON.stringify(reason);
      } catch {
        message = String(reason);
      }
    }
    showError({
      errorMessage: message,
      errorStack: stack,
      errorCategory: 'js-promise',
      isPanic: false,
      isRecoverable: false,
    });
  };

  window.addEventListener('error', onWindowError);
  window.addEventListener('unhandledrejection', onUnhandledRejection);

  // Tauri events return Promise<UnlistenFn>; we hold them so we can detach
  // in the unlistener. In production the unlistener is never called.
  const tauriUnlistens: UnlistenFn[] = [];

  void listen<PanicPayload>('panic', (event) => {
    const payload = event.payload ?? {};
    const message = payload.message || 'Rust panic occurred';
    const stack = [
      payload.location && `at ${payload.location}`,
      payload.backtrace,
    ]
      .filter(Boolean)
      .join('\n\n');
    showError({
      errorMessage: message,
      errorStack: stack || null,
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
  })
    .then((un) => tauriUnlistens.push(un))
    .catch(() => {
      // listen() can fail in non-Tauri test envs — not fatal
    });

  void listen<string>('panic-from-previous-session', (event) => {
    showError({
      errorTitle: '前回起動時にエラー終了しました',
      errorMessage:
        '前回のセッションが panic で終了した可能性があります。詳細はログファイルを参照してください。',
      errorStack: typeof event.payload === 'string' ? event.payload : null,
      errorHint:
        '同じエラーが再発する場合は Issue で報告してください。',
      errorCategory: 'previous-session-panic',
      isPanic: false,
      isRecoverable: true,
    });
  })
    .then((un) => tauriUnlistens.push(un))
    .catch(() => {
      // not fatal in non-Tauri test envs
    });

  void listen<IntegrityErrorPayload>('integrity-error', (event) => {
    const payload = event.payload;
    showError({
      errorTitle: '同梱物の検証に失敗しました',
      errorMessage: formatIntegrityMessage(payload),
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });
    setLogDir(logDirOf(payload.logPath));
  })
    .then((un) => tauriUnlistens.push(un))
    .catch(() => {
      // not fatal in non-Tauri test envs
    });

  // Fetch log dir asynchronously; ErrorModal handles logDir being null
  // gracefully.
  void invoke<string>('get_log_dir')
    .then((dir) => setLogDir(dir))
    .catch(() => {
      setLogDir(null);
    });

  return () => {
    window.removeEventListener('error', onWindowError);
    window.removeEventListener('unhandledrejection', onUnhandledRejection);
    tauriUnlistens.forEach((un) => {
      try {
        un();
      } catch {
        // ignore
      }
    });
  };
}
