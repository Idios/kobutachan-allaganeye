import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, listenMock, unlistenSpy } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
  unlistenSpy: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));
vi.mock('@tauri-apps/api/event', () => ({
  listen: listenMock,
}));

import { ConfirmExitModal } from './ConfirmExitModal';

beforeEach(() => {
  invokeMock.mockReset();
  listenMock.mockReset();
  unlistenSpy.mockReset();
  // Default: store the listener so tests can fire the close-requested event.
  listenMock.mockImplementation(async () => unlistenSpy);
});

describe('ConfirmExitModal', () => {
  it('renders nothing initially and subscribes to close-requested', async () => {
    render(<ConfirmExitModal />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalledWith(
        'close-requested',
        expect.any(Function),
      );
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('exits immediately when the event fires and no process is running', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(false);
      if (cmd === 'force_exit_app') return Promise.resolve();
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('force_exit_app');
    });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('shows the confirm dialog when a process is running', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: '終了' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'キャンセル' })).toBeInTheDocument();
  });

  it('kill + exit on 終了', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      if (cmd === 'kill_tracked_processes') return Promise.resolve(2);
      if (cmd === 'force_exit_app') return Promise.resolve();
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeInTheDocument();
    });
    await userEvent.setup().click(
      screen.getByRole('button', { name: '終了' }),
    );
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');
      expect(invokeMock).toHaveBeenCalledWith('force_exit_app');
    });
  });

  it('キャンセル dismisses without invoking anything extra', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByRole('button', { name: 'キャンセル' }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // No kill / exit invocations after cancel.
    const killCalled = invokeMock.mock.calls.some(
      (c) => c[0] === 'kill_tracked_processes',
    );
    const exitCalled = invokeMock.mock.calls.some(
      (c) => c[0] === 'force_exit_app',
    );
    expect(killCalled).toBe(false);
    expect(exitCalled).toBe(false);
  });

  it('Escape dismisses the modal as if キャンセル was pressed (#587)', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    await userEvent.setup().keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const killCalled = invokeMock.mock.calls.some(
      (c) => c[0] === 'kill_tracked_processes',
    );
    expect(killCalled).toBe(false);
  });

  it('focus is trapped inside the panel while pending (#587)', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it('has no axe violations when shown (#587)', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    const { container } = render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('ConfirmExitModal catch (#678)', () => {
  it('renders AppError struct message + hint on probe failure', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') {
        return Promise.reject({
          code: 'internal.error',
          message: 'probe 失敗',
          hint: '再試行してください',
        });
      }
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(screen.getByText('probe 失敗')).toBeInTheDocument();
    });
    expect(screen.getByText(/再試行してください/)).toBeInTheDocument();
  });

  it('renders message only when AppError has no hint on probe failure', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') {
        return Promise.reject({
          code: 'internal.error',
          message: 'plain message',
        });
      }
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(screen.getByText('plain message')).toBeInTheDocument();
    });
    expect(screen.queryByText(/💡/)).toBeNull();
  });

  it('renders Error instance message on probe failure (legacy raw String 互換)', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') {
        return Promise.reject(new Error('legacy error'));
      }
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() => {
      expect(screen.getByText('legacy error')).toBeInTheDocument();
    });
    expect(screen.queryByText(/💡/)).toBeNull();
  });

  it('renders AppError struct message + hint on kill failure', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      if (cmd === 'kill_tracked_processes') {
        return Promise.reject({
          code: 'process.kill_failed',
          message: 'kill 失敗',
          hint: 'タスクマネージャーで手動終了してください',
        });
      }
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByRole('button', { name: '終了' }),
    );
    await waitFor(() => {
      expect(screen.getByText('kill 失敗')).toBeInTheDocument();
    });
    expect(
      screen.getByText(/タスクマネージャーで手動終了してください/),
    ).toBeInTheDocument();
  });

  it('clears hint when キャンセル is pressed after kill failure', async () => {
    let handler: () => void = () => undefined;
    listenMock.mockImplementation(async (_: string, h: () => void) => {
      handler = h;
      return unlistenSpy;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'is_process_running') return Promise.resolve(true);
      if (cmd === 'kill_tracked_processes') {
        return Promise.reject({
          code: 'process.kill_failed',
          message: 'kill 失敗',
          hint: '再試行してください',
        });
      }
      return Promise.reject(new Error(`unmocked: ${cmd}`));
    });
    render(<ConfirmExitModal />);
    await waitFor(() => expect(listenMock).toHaveBeenCalled());
    handler();
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).toBeInTheDocument(),
    );
    await userEvent.setup().click(
      screen.getByRole('button', { name: '終了' }),
    );
    await waitFor(() => {
      expect(screen.getByText('kill 失敗')).toBeInTheDocument();
    });
    expect(screen.getByText(/再試行してください/)).toBeInTheDocument();
    await userEvent.setup().click(
      screen.getByRole('button', { name: 'キャンセル' }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('kill 失敗')).toBeNull();
    expect(screen.queryByText(/再試行してください/)).toBeNull();
  });
});
