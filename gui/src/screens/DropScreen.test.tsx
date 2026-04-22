import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

import { DropScreen } from './DropScreen';
import { useAppStateStore } from '../state/appStateStore';

beforeEach(() => {
  useAppStateStore.getState().reset();
});

describe('DropScreen', () => {
  it('renders the drop zone with the [参照…] button in idle state', () => {
    render(<DropScreen />);
    const drop = screen.getByTestId('drop-screen');
    expect(drop.dataset.phase).toBe('idle');
    expect(screen.getByRole('button', { name: /参照/ })).toBeInTheDocument();
  });

  it('shows dummy recent recordings list in idle state', () => {
    render(<DropScreen />);
    expect(screen.getByText(/2026-04-08 21-14-05.mkv/)).toBeInTheDocument();
  });

  it('flows idle -> selecting -> probing -> selected on [参照…]', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
    expect(openDialog).toHaveBeenCalled();
  });

  it('returns to idle if dialog is cancelled', async () => {
    const openDialog = vi.fn().mockResolvedValue(null);
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
    });
  });

  it('navigates to detecting when [OK] is clicked in selected state', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /OK — 検知開始/ }));
    const state = useAppStateStore.getState();
    expect(state.screen).toBe('detecting');
    expect(state.selectedVideoPath).toBe('C:/videos/x.mkv');
  });

  it('returns to idle when [キャンセル] is clicked in selected state', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'キャンセル' }));
    expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
    expect(useAppStateStore.getState().selectedVideoPath).toBeNull();
  });

  it('shows probe error with [再試行] / [閉じる] when probe fails', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    const probeFn = vi.fn().mockRejectedValue(new Error('bad file'));
    render(<DropScreen openDialogFn={openDialog} probeFn={probeFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByText(/bad file/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '閉じる' }));
    expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
  });
});
