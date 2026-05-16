import { Component, type ErrorInfo, type ReactNode } from 'react';

import { useErrorStore } from '../state/errorStore';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * #614: Wraps the application root and catches React-internal exceptions
 * thrown during render / lifecycle / hooks. The caught error is dispatched
 * to `useErrorStore` so the global ErrorModal (rendered as a sibling, not
 * a child) can surface it to the user.
 *
 * When `hasError === true` we render `null` rather than the children — re-
 * rendering the same broken sub-tree would re-throw immediately. The
 * ErrorModal lives outside the boundary so it remains visible after the
 * boundary blanks out.
 *
 * NOTE: Error boundaries do NOT catch:
 *   - Errors in event handlers (use try/catch)
 *   - Async errors (Promise rejections — use globalErrorListener)
 *   - Server-side rendering errors
 *   - Errors thrown in the boundary itself
 *
 * Those paths are handled separately by `globalErrorListener.ts`.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    const stack =
      errorInfo.componentStack ?? error.stack ?? null;
    useErrorStore.getState().showError({
      errorTitle: 'アプリ内部でエラーが発生しました',
      errorMessage: error.message || String(error),
      errorStack: stack,
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}
