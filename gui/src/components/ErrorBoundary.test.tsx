import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useErrorStore } from '../state/errorStore';
import { ErrorBoundary } from './ErrorBoundary';

function Thrower({ message }: { message: string }): null {
  throw new Error(message);
}

describe('ErrorBoundary', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    // React logs caught boundary errors via console.error — suppress for clean test output
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it('renders children when no error is thrown', () => {
    const { getByText } = render(
      <ErrorBoundary>
        <div>healthy</div>
      </ErrorBoundary>,
    );
    expect(getByText('healthy')).toBeTruthy();
    expect(useErrorStore.getState().errorOpen).toBe(false);
  });

  it('captures child throw and dispatches to errorStore', () => {
    render(
      <ErrorBoundary>
        <Thrower message="boom" />
      </ErrorBoundary>,
    );
    const state = useErrorStore.getState();
    expect(state.errorOpen).toBe(true);
    expect(state.errorMessage).toBe('boom');
    expect(state.errorCategory).toBe('js-error');
    expect(state.isPanic).toBe(false);
    expect(state.isRecoverable).toBe(false);
    expect(state.errorTitle).toBe('アプリ内部でエラーが発生しました');
  });

  it('captures componentStack in errorStack', () => {
    render(
      <ErrorBoundary>
        <Thrower message="stack-test" />
      </ErrorBoundary>,
    );
    const state = useErrorStore.getState();
    expect(state.errorStack).toBeTruthy();
    // componentStack is multi-line and contains element names
    expect(state.errorStack).toContain('Thrower');
  });

  it('renders null after catching error', () => {
    const { container } = render(
      <ErrorBoundary>
        <Thrower message="render-null" />
      </ErrorBoundary>,
    );
    expect(container.innerHTML).toBe('');
  });
});
