import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

// #568: DropScreen の default dragSubscriber は
// `getCurrentWebview().onDragDropEvent` を呼ぶ。jsdom 上で安全に
// no-op を返す mock を入れる。個別 test で override したい場合は
// `dragSubscriber` props を渡す。
vi.mock('@tauri-apps/api/webview', () => ({
  getCurrentWebview: () => ({
    onDragDropEvent: vi.fn().mockResolvedValue(() => undefined),
  }),
}));

import { DropScreen, type TauriDragDropEvent } from './DropScreen';
import { useAppStateStore } from '../state/appStateStore';

function createMockDragSubscriber() {
  let listener: ((e: TauriDragDropEvent) => void) | null = null;
  const subscribe = (cb: (e: TauriDragDropEvent) => void) => {
    listener = cb;
    return Promise.resolve(() => {
      listener = null;
    });
  };
  return {
    subscribe,
    fire: (e: TauriDragDropEvent) => listener?.(e),
    isSubscribed: () => listener !== null,
  };
}

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

  // #568: D&D 機能 — Tauri webview onDragDropEvent 経由の挙動。
  describe('drag & drop (#568)', () => {
    it('highlights drop zone with cyan when valid extension is dragged over', async () => {
      const mock = createMockDragSubscriber();
      render(<DropScreen dragSubscriber={mock.subscribe} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'enter',
          paths: ['C:/videos/x.mkv'],
          position: { x: 0, y: 0 },
        }),
      );
      const zone = screen.getByTestId('drop-zone');
      expect(zone.dataset.dragState).toBe('over-valid');
      expect(zone.className).toMatch(/dropZoneDragOverValid/);
    });

    it('shows reject inline message when invalid extension is dragged over', async () => {
      const mock = createMockDragSubscriber();
      render(<DropScreen dragSubscriber={mock.subscribe} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'enter',
          paths: ['C:/somewhere/notes.txt'],
          position: { x: 0, y: 0 },
        }),
      );
      const zone = screen.getByTestId('drop-zone');
      expect(zone.dataset.dragState).toBe('over-invalid');
      expect(zone.className).toMatch(/dropZoneDragOverInvalid/);
      expect(screen.getByText(/非対応形式/)).toBeInTheDocument();
      expect(screen.getByText('⊘')).toBeInTheDocument();
    });

    it('returns to idle on drag-leave', async () => {
      const mock = createMockDragSubscriber();
      render(<DropScreen dragSubscriber={mock.subscribe} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'enter',
          paths: ['C:/videos/x.mkv'],
          position: { x: 0, y: 0 },
        }),
      );
      expect(screen.getByTestId('drop-zone').dataset.dragState).toBe(
        'over-valid',
      );
      act(() => mock.fire({ type: 'leave' }));
      expect(screen.getByTestId('drop-zone').dataset.dragState).toBe('idle');
    });

    it('dispatches DND_DROPPED and calls probeFn on valid drop', async () => {
      const mock = createMockDragSubscriber();
      const probeFn = vi.fn().mockResolvedValue({
        path: 'C:/videos/x.mkv',
        fileName: 'x.mkv',
        sizeBytes: 1,
        durationSeconds: 1,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
      });
      render(<DropScreen dragSubscriber={mock.subscribe} probeFn={probeFn} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'drop',
          paths: ['C:/videos/x.mkv'],
          position: { x: 0, y: 0 },
        }),
      );
      await waitFor(() => {
        expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
      });
      expect(probeFn).toHaveBeenCalledWith('C:/videos/x.mkv');
      expect(screen.getByTestId('drop-screen').dataset.phase).toBe('selected');
    });

    it('picks first valid extension when multiple paths are dropped', async () => {
      const mock = createMockDragSubscriber();
      const probeFn = vi.fn().mockResolvedValue({
        path: 'C:/videos/b.mkv',
        fileName: 'b.mkv',
        sizeBytes: 1,
        durationSeconds: 1,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
      });
      render(<DropScreen dragSubscriber={mock.subscribe} probeFn={probeFn} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'drop',
          paths: ['C:/a.txt', 'C:/b.mkv', 'C:/c.mp4'],
          position: { x: 0, y: 0 },
        }),
      );
      await waitFor(() => {
        expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
      });
      expect(probeFn).toHaveBeenCalledWith('C:/b.mkv');
    });

    it('rejects folder drop (no matching extension)', async () => {
      const mock = createMockDragSubscriber();
      const probeFn = vi.fn();
      render(<DropScreen dragSubscriber={mock.subscribe} probeFn={probeFn} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'drop',
          paths: ['C:/some-folder'],
          position: { x: 0, y: 0 },
        }),
      );
      // give microtasks a chance to run
      await Promise.resolve();
      expect(probeFn).not.toHaveBeenCalled();
      expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
    });

    it('ignores drag events while phase is not idle', async () => {
      const mock = createMockDragSubscriber();
      const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
      // make probe slow so we can observe `probing` phase
      let resolveProbe: (info: unknown) => void = () => undefined;
      const probeFn = vi.fn(
        () =>
          new Promise((res) => {
            resolveProbe = res;
          }),
      );
      render(
        <DropScreen
          dragSubscriber={mock.subscribe}
          openDialogFn={openDialog}
          probeFn={probeFn as never}
        />,
      );
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /参照/ }));
      await waitFor(() => {
        expect(screen.getByTestId('drop-screen').dataset.phase).toBe('probing');
      });
      // drag-over while probing — must not change dragState
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'enter',
          paths: ['C:/videos/y.mkv'],
          position: { x: 0, y: 0 },
        }),
      );
      // dropZone is hidden while probing (selected/probeError/probing branch),
      // so we just verify phase didn't change to selected via spurious DND.
      expect(screen.getByTestId('drop-screen').dataset.phase).toBe('probing');
      // unblock probe to keep test clean
      resolveProbe({
        path: 'C:/videos/x.mkv',
        fileName: 'x.mkv',
        sizeBytes: 1,
        durationSeconds: 1,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
      });
    });

    it('does not transition phase on invalid drop', async () => {
      const mock = createMockDragSubscriber();
      const probeFn = vi.fn();
      render(<DropScreen dragSubscriber={mock.subscribe} probeFn={probeFn} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'drop',
          paths: ['C:/foo.txt'],
          position: { x: 0, y: 0 },
        }),
      );
      await Promise.resolve();
      expect(probeFn).not.toHaveBeenCalled();
      expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
      expect(screen.getByTestId('drop-zone').dataset.dragState).toBe('idle');
    });

    it('reflects HTML5 onDragOver fallback in dragState (jsdom path)', async () => {
      // No dragSubscriber here — only HTML5 fallback should fire because the
      // default subscriber mock returns no-op. fireEvent.dragOver with valid
      // mime should still highlight the drop zone (test-only fallback).
      render(<DropScreen />);
      const zone = screen.getByTestId('drop-zone');
      fireEvent.dragOver(zone, {
        dataTransfer: {
          items: [{ kind: 'file', type: 'video/mp4' }],
        },
      });
      expect(zone.dataset.dragState).toBe('over-valid');
      fireEvent.dragLeave(zone);
      expect(zone.dataset.dragState).toBe('idle');
    });
  });
});
