import { create } from 'zustand';

/**
 * #614: Categorizes the source of an unrecoverable error so the ErrorModal
 * can pick an appropriate title / hint, and analytics-style log entries can
 * tell paths apart.
 *
 * #668: 'integrity' added for bundled-file corruption detection at startup
 * (Rust integrity::check / Python allaganeye.integrity.check). Treated as
 * isPanic=true (modal close exits the app) + isRecoverable=false.
 */
export type ErrorCategory =
  | 'panic'
  | 'js-error'
  | 'js-promise'
  | 'tauri-command'
  | 'previous-session-panic'
  | 'integrity';

export interface ErrorSpec {
  errorTitle?: string | null;
  errorMessage: string;
  errorStack?: string | null;
  errorHint?: string | null;
  errorCategory: ErrorCategory;
  isPanic: boolean;
  isRecoverable: boolean;
}

export interface ErrorState {
  errorOpen: boolean;
  errorTitle: string | null;
  errorMessage: string | null;
  errorStack: string | null;
  errorHint: string | null;
  errorCategory: ErrorCategory | null;
  isPanic: boolean;
  isRecoverable: boolean;
  logDir: string | null;
  timestamp: string | null;

  showError(spec: ErrorSpec): void;
  dismissError(): void;
  setLogDir(dir: string | null): void;
}

const DEFAULT_STATE: Omit<ErrorState, 'showError' | 'dismissError' | 'setLogDir'> = {
  errorOpen: false,
  errorTitle: null,
  errorMessage: null,
  errorStack: null,
  errorHint: null,
  errorCategory: null,
  isPanic: false,
  isRecoverable: true,
  logDir: null,
  timestamp: null,
};

export const useErrorStore = create<ErrorState>((set, get) => ({
  ...DEFAULT_STATE,

  showError: (spec) => {
    // #614: First-write-wins. If an unrecoverable error is already showing,
    // don't replace it — the user should triage the original failure first.
    // Subsequent errors are dropped (logged to console for the dev only).
    if (get().errorOpen) {
       
      console.warn('[errorStore] error already open, skipping showError', spec);
      return;
    }
    set({
      errorOpen: true,
      errorTitle: spec.errorTitle ?? null,
      errorMessage: spec.errorMessage,
      errorStack: spec.errorStack ?? null,
      errorHint: spec.errorHint ?? null,
      errorCategory: spec.errorCategory,
      isPanic: spec.isPanic,
      isRecoverable: spec.isRecoverable,
      timestamp: new Date().toISOString(),
    });
  },

  dismissError: () => {
    set({
      errorOpen: false,
      errorTitle: null,
      errorMessage: null,
      errorStack: null,
      errorHint: null,
      errorCategory: null,
      isPanic: false,
      isRecoverable: true,
      timestamp: null,
    });
  },

  setLogDir: (dir) => set({ logDir: dir }),
}));
