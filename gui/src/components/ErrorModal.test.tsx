import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useErrorStore } from '../state/errorStore';
import { useMetadataStore } from '../state/metadataStore';
import type { Metadata } from '../types/metadata';
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

describe('ErrorModal integrity category (#668)', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir(null);
  });

  it('renders integrity-specific default title when no override given', () => {
    useErrorStore.getState().showError({
      errorMessage: '1 missing, 0 size mismatch',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    // Default title for integrity category
    expect(screen.getByText('同梱物の検証に失敗しました')).toBeInTheDocument();
  });

  it('shows the close-app button (isPanic) and hides the dismiss button (isRecoverable=false)', () => {
    useErrorStore.getState().showError({
      errorTitle: '同梱物の検証に失敗しました',
      errorMessage: '1 missing, 0 size mismatch',
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    expect(screen.getByRole('button', { name: 'アプリを終了' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '閉じる' })).not.toBeInTheDocument();
  });

  it('displays the re-extract hint from errorHint', () => {
    useErrorStore.getState().showError({
      errorMessage: '1 missing',
      errorHint: 'Portable ZIP を再展開してください。',
      errorCategory: 'integrity',
      isPanic: true,
      isRecoverable: false,
    });

    render(<ErrorModal />);

    expect(screen.getByText('Portable ZIP を再展開してください。')).toBeInTheDocument();
  });
});

describe('ErrorModal Issue 報告 link pre-fill (#669)', () => {
  beforeEach(() => {
    useErrorStore.getState().dismissError();
    useErrorStore.getState().setLogDir('C:\\install\\logs');
    useMetadataStore.setState({
      metadata: {
        version: 'v2',
        source: 'sample.mkv',
        matches: [],
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
        },
      } as unknown as Metadata,
    });
    invokeMock.mockReset();
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'probe_environment_info') {
        return {
          allaganeye_version: '0.2.0',
          os_name: 'Microsoft Windows 11 (Build 22631)',
          cpu_info: 'AMD Ryzen 9 9950X3D (16C/32T)',
          memory_total_gb: 61.6,
          disk_free_gb: 1359.5,
          disk_total_gb: 3726.0,
          disk_drive: 'E:',
        };
      }
      if (cmd === 'read_error_log_tail') {
        return 'last log line A\nlast log line B';
      }
      return undefined;
    });
  });

  it('builds pre-fill URL with actual / environment / log_file_attachment after errorOpen', async () => {
    useErrorStore.getState().showError({
      errorMessage: 'panic: x',
      errorStack: 'stack trace here',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);

    await waitFor(() => {
      const link = screen.getByText('Issue で報告する') as HTMLAnchorElement;
      expect(link.href).toContain('actual=');
      expect(link.href).toContain('environment=');
      expect(link.href).toContain('log_file_attachment=');
    });

    const link = screen.getByText('Issue で報告する') as HTMLAnchorElement;
    const url = new URL(link.href);
    const params = new URLSearchParams(url.search);
    expect(params.get('actual')).toContain('panic: x');
    expect(params.get('actual')).toContain('stack trace here');
    expect(params.get('environment')).toContain('allaganeye 0.2.0');
    expect(params.get('environment')).toContain('CPU: AMD Ryzen 9 9950X3D');
    expect(params.get('environment')).toContain('GPU: nvidia');
    expect(params.get('log_file_attachment')).toContain('last log line A');
    expect(params.get('log_file_attachment')).toContain('last log line B');
  });

  it('falls back to base URL with actual+environment when read_error_log_tail fails', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'probe_environment_info') {
        return {
          allaganeye_version: '0.2.0',
          os_name: 'Windows 11',
          cpu_info: 'CPU',
          memory_total_gb: 16.0,
          disk_free_gb: null,
          disk_total_gb: null,
          disk_drive: null,
        };
      }
      if (cmd === 'read_error_log_tail') {
        throw new Error('I/O failure');
      }
      return undefined;
    });
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);

    await waitFor(() => {
      const link = screen.getByText('Issue で報告する') as HTMLAnchorElement;
      // even on log fetch failure, actual + environment are pre-filled
      expect(link.href).toContain('template=bug_report.yml');
      expect(link.href).toContain('actual=');
      expect(link.href).toContain('environment=');
    });
  });

  it('falls back to base URL when both probe_environment_info and read_error_log_tail fail', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'probe_environment_info') {
        throw new Error('probe failed');
      }
      if (cmd === 'read_error_log_tail') {
        throw new Error('I/O');
      }
      return undefined;
    });
    useErrorStore.getState().showError({
      errorMessage: 'panic',
      errorCategory: 'panic',
      isPanic: true,
      isRecoverable: false,
    });
    render(<ErrorModal />);

    // initial render gets base URL; useEffect failure leaves base URL.
    const link = screen.getByText('Issue で報告する') as HTMLAnchorElement;
    expect(link.href).toContain('template=bug_report.yml');
  });
});
