import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useErrorStore } from '../state/errorStore';
import { ErrorModal } from './ErrorModal';

const invokeMock = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => invokeMock(...args),
}));

describe('ErrorModal', () => {
  let writeTextSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
    invokeMock.mockReset();
    invokeMock.mockResolvedValue(undefined);
    writeTextSpy = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: writeTextSpy },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when errorOpen is false', () => {
    const { container } = render(<ErrorModal />);
    expect(container.innerHTML).toBe('');
  });

  it('renders title, message and stack when errorOpen is true', () => {
    useErrorStore.getState().showError({
      errorTitle: 'My Title',
      errorMessage: 'something failed',
      errorStack: 'at line 1\nat line 2',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByText('My Title')).toBeTruthy();
    expect(screen.getByText('something failed')).toBeTruthy();
    expect(screen.getByText(/at line 1/)).toBeTruthy();
  });

  it('uses default title when none provided (panic)', () => {
    useErrorStore.getState().showError({
      errorMessage: 'panic msg',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    expect(screen.getByText('アプリ内部でエラーが発生しました')).toBeTruthy();
  });

  it('uses default title when none provided (non-panic)', () => {
    useErrorStore.getState().showError({
      errorMessage: 'js error msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    expect(screen.getByText('予期しないエラーが発生しました')).toBeTruthy();
  });

  it('renders Issue で報告する link with correct href', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    const link = screen.getByText('Issue で報告する') as HTMLAnchorElement;
    expect(link.href).toContain('github.com/Idios/kobutachan-allaganeye/issues/new');
    expect(link.target).toBe('_blank');
    expect(link.rel).toContain('noopener');
  });

  it('shows アプリを終了 button only when isPanic is true', () => {
    useErrorStore.getState().showError({
      errorMessage: 'js error',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: false,
    });
    const { rerender } = render(<ErrorModal />);
    expect(screen.queryByText('アプリを終了')).toBeNull();

    useErrorStore.getState().dismissError();
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    rerender(<ErrorModal />);
    expect(screen.getByText('アプリを終了')).toBeTruthy();
  });

  it('shows 閉じる button only when isRecoverable is true', () => {
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    const { rerender } = render(<ErrorModal />);
    expect(screen.queryByText('閉じる')).toBeNull();

    useErrorStore.getState().dismissError();
    useErrorStore.getState().showError({
      errorMessage: 'recoverable',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    rerender(<ErrorModal />);
    expect(screen.getByText('閉じる')).toBeTruthy();
  });

  it('閉じる button calls dismissError', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    fireEvent.click(screen.getByText('閉じる'));
    expect(useErrorStore.getState().errorOpen).toBe(false);
  });

  it('アプリを終了 button calls invoke("force_exit_app")', () => {
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    fireEvent.click(screen.getByText('アプリを終了'));
    expect(invokeMock).toHaveBeenCalledWith('force_exit_app');
  });

  it('詳細をコピー button writes JSON payload to clipboard', async () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorStack: 'stack-here',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    fireEvent.click(screen.getByText('詳細をコピー'));
    expect(writeTextSpy).toHaveBeenCalledOnce();
    const payload = JSON.parse(writeTextSpy.mock.calls[0][0] as string);
    expect(payload.message).toBe('msg');
    expect(payload.stack).toBe('stack-here');
    expect(payload.category).toBe('js-error');
  });

  it('renders log folder row when logDir is set', () => {
    useErrorStore.getState().setLogDir('C:\\install\\logs');
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.getByText(/C:\\install\\logs/)).toBeTruthy();
    expect(screen.getByText('ログフォルダを開く')).toBeTruthy();
  });

  it('does not render log folder row when logDir is null', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    expect(screen.queryByText('ログフォルダを開く')).toBeNull();
  });

  it('Escape dismisses recoverable error', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    render(<ErrorModal />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(useErrorStore.getState().errorOpen).toBe(false);
  });

  it('Escape does NOT dismiss panic error', () => {
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(useErrorStore.getState().errorOpen).toBe(true);
  });

  it('has role=dialog and aria-modal', () => {
    useErrorStore.getState().showError({
      errorMessage: 'msg',
      errorCategory: 'js-error',
      isPanic: false,
      isRecoverable: true,
    });
    const { container } = render(<ErrorModal />);
    const dialog = container.querySelector('[role="dialog"]');
    expect(dialog).toBeTruthy();
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(dialog?.getAttribute('aria-labelledby')).toBe('ae-error-title');
  });
});
