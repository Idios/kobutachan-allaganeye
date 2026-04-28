import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

// #465 review (B): DropScreen の default probeFn は Tauri `probe_video`
// command を invoke する。テスト環境では Tauri runtime がないので、
// `invoke('probe_video', ...)` をデフォルトで成功させる mock を入れる。
// 個別 test で override したい場合は `probeFn` props を渡す。
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue({
    path: 'C:/videos/x.mkv',
    fileName: 'x.mkv',
    sizeBytes: 38 * 1024 * 1024 * 1024,
    durationSeconds: 10228.735,
    width: 1920,
    height: 1080,
    fps: 60,
    codec: 'h264',
  }),
}));

import { DropScreen } from './DropScreen';
import { useAppStateStore } from '../state/appStateStore';
import type { VideoProbeInfo } from './types';

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

  it('Escape on the SelectedCard dismisses it (#587)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
    expect(useAppStateStore.getState().selectedVideoPath).toBeNull();
  });

  it('SelectedCard auto-focuses a focusable element inside (#587 focus trap)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    const card = await screen.findByTestId('drop-selected-card');
    // Auto-focus moves focus into the card. The first focusable in the
    // card is the cancel button.
    expect(card.contains(document.activeElement)).toBe(true);
  });

  it('Escape on the ErrorCard dismisses it (#587)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    const probeFn = vi.fn().mockRejectedValue(new Error('bad file'));
    render(<DropScreen openDialogFn={openDialog} probeFn={probeFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
  });

  it('idle screen has no axe violations (#587)', async () => {
    const { container } = render(<DropScreen />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('SelectedCard has no axe violations (#587)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    const { container } = render(<DropScreen openDialogFn={openDialog} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => screen.getByTestId('drop-selected-card'));
    expect(await axe(container)).toHaveNoViolations();
  });

  it('ErrorCard has no axe violations (#587)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    const probeFn = vi.fn().mockRejectedValue(new Error('bad'));
    const { container } = render(
      <DropScreen openDialogFn={openDialog} probeFn={probeFn} />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => screen.getByRole('alert'));
    expect(await axe(container)).toHaveNoViolations();
  });

  it('shows the LoadingSpinner label while probing (#587)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    // Resolve the probe slowly so we can observe the probing phase.
    let resolveProbe: ((value: VideoProbeInfo) => void) | undefined;
    const probeFn = vi.fn(
      () =>
        new Promise<VideoProbeInfo>((resolve) => {
          resolveProbe = resolve;
        }),
    );
    render(<DropScreen openDialogFn={openDialog} probeFn={probeFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByText('解析中')).toBeInTheDocument();
    });
    // Drain the pending probe to keep the suite clean.
    resolveProbe?.({
      path: 'C:/videos/x.mkv',
      fileName: 'x.mkv',
      sizeBytes: 0,
      durationSeconds: 0,
      width: 0,
      height: 0,
      fps: 0,
      codec: 'h264',
    });
    await waitFor(() => {
      expect(screen.queryByText('解析中')).toBeNull();
    });
  });
});
