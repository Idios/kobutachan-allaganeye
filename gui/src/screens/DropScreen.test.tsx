import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

// #465 review (B): DropScreen の default probeFn は Tauri `probe_video`
// command を invoke する。テスト環境では Tauri runtime がないので、
// `invoke` を command 名でディスパッチする mock を入れる。`probe_video`
// をデフォルトで成功させ、`read_recent` (#571) は空配列、`add_recent`
// (#571) は no-op で空配列を返す。個別 test で override したい場合は
// `probeFn` props を渡すか、後述の `invokeMock.mockImplementation*Once` で。
const { invokeMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

const PROBE_FIXTURE = {
  path: 'C:/videos/x.mkv',
  fileName: 'x.mkv',
  sizeBytes: 38 * 1024 * 1024 * 1024,
  durationSeconds: 10228.735,
  width: 1920,
  height: 1080,
  fps: 60,
  codec: 'h264',
};

function defaultInvokeImpl(cmd: string): Promise<unknown> {
  switch (cmd) {
    case 'probe_video':
      return Promise.resolve(PROBE_FIXTURE);
    case 'read_recent':
      // Empty history by default — tests that need entries override per-test.
      return Promise.resolve([]);
    case 'add_recent':
      // The drop-screen flow calls this fire-and-forget after a successful
      // probe. We resolve with the synthetic single-entry list so the call
      // is observable but doesn't disturb the in-memory store.
      return Promise.resolve([]);
    default:
      return Promise.resolve(null);
  }
}

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
import { useRecentStore } from '../state/recentStore';
import type { VideoProbeInfo } from './types';

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
  invokeMock.mockReset();
  invokeMock.mockImplementation(defaultInvokeImpl);
  useAppStateStore.getState().reset();
  useRecentStore.getState().reset();
});

describe('DropScreen', () => {
  it('renders the drop zone with the [参照…] button in idle state', () => {
    render(<DropScreen />);
    const drop = screen.getByTestId('drop-screen');
    expect(drop.dataset.phase).toBe('idle');
    expect(screen.getByRole('button', { name: /参照/ })).toBeInTheDocument();
  });

  // #571: replaces the old "shows dummy recent recordings" test.
  // RECENT_DUMMY is gone; the list is driven by the recentStore.
  it('shows the empty-history placeholder when recent.json is empty (#571)', async () => {
    render(<DropScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('recent-empty')).toBeInTheDocument();
    });
    expect(screen.getByText('履歴はまだありません')).toBeInTheDocument();
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

  // #663 — Phase 4: when the probe rejects with an AppError-shaped object
  // (`{ code, message, hint }`), the ErrorCard renders the hint as a 2nd
  // line below the message so users get a recommended next action. Bare
  // Error instances (`new Error(...)`) keep the existing single-line UX
  // because `toErrorState(e).hint` is null for them.
  it('renders probe error hint as 2nd line when probe rejects with AppError (#663)', async () => {
    const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
    const probeFn = vi.fn().mockRejectedValue({
      code: 'parse.ffprobe_output_invalid',
      message: 'ffprobe failed',
      hint: 'check ffmpeg version',
    });
    render(<DropScreen openDialogFn={openDialog} probeFn={probeFn} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByText('ffprobe failed')).toBeInTheDocument();
    });
    expect(screen.getByText(/check ffmpeg version/)).toBeInTheDocument();
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
    await waitFor(() =>
      expect(card.contains(document.activeElement)).toBe(true),
    );
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

    it('accepts uppercase extension paths (.MKV / .MP4 / .AVI / .MOV)', async () => {
      // 設計判断: 拡張子は大文字小文字非区別 (PR #625 / docs/ui-interaction-spec.md
      // §2.1.1 例外/edge case)。実装は `lower.endsWith(ext)` で対応済みだが、
      // T1-T9 がすべて小文字 fixture のため大文字回帰防止 test を別途追加する。
      const mock = createMockDragSubscriber();
      const probeFn = vi.fn().mockResolvedValue({
        path: 'C:/videos/X.MKV',
        fileName: 'X.MKV',
        sizeBytes: 1,
        durationSeconds: 1,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
      });
      render(<DropScreen dragSubscriber={mock.subscribe} probeFn={probeFn} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      // enter で over-valid 判定されることを確認 (drag-over phase の回帰)
      act(() =>
        mock.fire({
          type: 'enter',
          paths: ['C:/videos/X.MKV'],
          position: { x: 0, y: 0 },
        }),
      );
      expect(screen.getByTestId('drop-zone').dataset.dragState).toBe(
        'over-valid',
      );
      // drop で uppercase path が probe に渡されることを確認
      act(() =>
        mock.fire({
          type: 'drop',
          paths: ['C:/videos/X.MKV'],
          position: { x: 0, y: 0 },
        }),
      );
      await waitFor(() => {
        expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
      });
      expect(probeFn).toHaveBeenCalledWith('C:/videos/X.MKV');
    });

    it.each([
      { ext: '.MP4', path: 'C:/videos/Y.MP4' },
      { ext: '.AVI', path: 'C:/videos/Y.AVI' },
      { ext: '.MOV', path: 'C:/videos/Y.MOV' },
      { ext: '.Mp4', path: 'C:/videos/Y.Mp4' }, // mixed case
    ])('treats $ext as valid on drag-over', async ({ path }) => {
      const mock = createMockDragSubscriber();
      render(<DropScreen dragSubscriber={mock.subscribe} />);
      await waitFor(() => expect(mock.isSubscribed()).toBe(true));
      act(() =>
        mock.fire({
          type: 'enter',
          paths: [path],
          position: { x: 0, y: 0 },
        }),
      );
      expect(screen.getByTestId('drop-zone').dataset.dragState).toBe(
        'over-valid',
      );
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

  // #571: recent-videos history (RECENT_DUMMY → recent.json + Tauri commands).
  describe('recent list (#571)', () => {
    function recentEntry(
      path: string,
      fileName: string,
      mtimeMs = 1_700_000_000_000,
    ) {
      return {
        path,
        fileName,
        sizeBytes: 38 * 1024 * 1024 * 1024,
        mtimeMs,
        addedAtMs: mtimeMs,
      };
    }

    it('hydrates the list from read_recent on mount', async () => {
      invokeMock.mockImplementation((cmd: string) => {
        if (cmd === 'read_recent') {
          return Promise.resolve([
            recentEntry('E:/videos/a.mkv', 'a.mkv'),
            recentEntry('E:/videos/b.mkv', 'b.mkv'),
          ]);
        }
        return defaultInvokeImpl(cmd);
      });
      render(<DropScreen />);
      await waitFor(() => {
        expect(screen.getAllByTestId('recent-item')).toHaveLength(2);
      });
      // PR #655 review (Round 2): full path is rendered as the visible
      // text (with title tooltip + left-truncation CSS); fileName remains
      // the screen-reader handle via aria-label.
      expect(screen.getByText('E:/videos/a.mkv')).toBeInTheDocument();
      expect(screen.getByText('E:/videos/b.mkv')).toBeInTheDocument();
      // The empty placeholder must be gone once entries arrived.
      expect(screen.queryByTestId('recent-empty')).toBeNull();
    });

    it('renders the full path with a title tooltip for hover (#655 Round 2)', async () => {
      invokeMock.mockImplementation((cmd: string) => {
        if (cmd === 'read_recent') {
          return Promise.resolve([
            recentEntry('E:/some/long/folder/2026-04-08 21-14-05.mkv', '2026-04-08 21-14-05.mkv'),
          ]);
        }
        return defaultInvokeImpl(cmd);
      });
      render(<DropScreen />);
      const pathSpan = await screen.findByText(
        'E:/some/long/folder/2026-04-08 21-14-05.mkv',
      );
      expect(pathSpan).toHaveAttribute(
        'title',
        'E:/some/long/folder/2026-04-08 21-14-05.mkv',
      );
      // The aria-label on the parent button keeps the fileName-only form
      // so screen readers don't read out the full path on every focus.
      const button = await screen.findByRole('button', {
        name: /直近の録画 2026-04-08 21-14-05.mkv/,
      });
      expect(button).toBeInTheDocument();
    });

    it('clicking a present recent item probes and shows the SelectedCard', async () => {
      invokeMock.mockImplementation((cmd: string) => {
        if (cmd === 'read_recent') {
          return Promise.resolve([recentEntry('E:/videos/a.mkv', 'a.mkv')]);
        }
        return defaultInvokeImpl(cmd);
      });
      const probeFn = vi.fn().mockResolvedValue({
        path: 'E:/videos/a.mkv',
        fileName: 'a.mkv',
        sizeBytes: 1,
        durationSeconds: 1,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
      });
      render(<DropScreen probeFn={probeFn} />);
      const user = userEvent.setup();
      const item = await screen.findByRole('button', {
        name: /直近の録画 a.mkv/,
      });
      await user.click(item);
      await waitFor(() => {
        expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
      });
      expect(probeFn).toHaveBeenCalledWith('E:/videos/a.mkv');
    });

    it('persists to add_recent after a successful probe via [参照…]', async () => {
      const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
      render(<DropScreen openDialogFn={openDialog} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /参照/ }));
      await waitFor(() => {
        expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
      });
      // The probe_video result above has path='C:/videos/x.mkv'; add_recent
      // should be called with that exact path.
      await waitFor(() => {
        expect(invokeMock).toHaveBeenCalledWith('add_recent', {
          path: 'C:/videos/x.mkv',
        });
      });
    });

    it('does not call add_recent when the probe fails', async () => {
      const openDialog = vi.fn().mockResolvedValue('C:/videos/x.mkv');
      const probeFn = vi.fn().mockRejectedValue(new Error('bad file'));
      render(<DropScreen openDialogFn={openDialog} probeFn={probeFn} />);
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /参照/ }));
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
      });
      // No add_recent call must have been made — only read_recent at mount.
      const addCalls = invokeMock.mock.calls.filter(
        (c) => c[0] === 'add_recent',
      );
      expect(addCalls).toHaveLength(0);
    });

    it('idle screen with recent entries has no axe violations', async () => {
      invokeMock.mockImplementation((cmd: string) => {
        if (cmd === 'read_recent') {
          return Promise.resolve([
            recentEntry('E:/videos/a.mkv', 'a.mkv'),
            recentEntry('E:/videos/b.mkv', 'b.mkv'),
          ]);
        }
        return defaultInvokeImpl(cmd);
      });
      const { container } = render(<DropScreen />);
      await waitFor(() => {
        expect(screen.getAllByTestId('recent-item')).toHaveLength(2);
      });
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});

describe('#698: recentStore error notice (A-minimal)', () => {
  beforeEach(() => {
    useRecentStore.setState({
      entries: [],
      loaded: true,
      loadErrorState: null,
      addErrorState: null,
    });
  });

  it('displays notice with message + hint when loadErrorState is set', () => {
    useRecentStore.setState({
      loadErrorState: {
        message: 'failed to read recent.json',
        hint: 'recent.json が破損している可能性があります',
        code: null,
      },
    });

    render(<DropScreen />);

    expect(screen.getByText('failed to read recent.json')).toBeInTheDocument();
    expect(
      screen.getByText('💡 recent.json が破損している可能性があります')
    ).toBeInTheDocument();
  });

  it('displays notice when addErrorState is set (loadErrorState null)', () => {
    useRecentStore.setState({
      addErrorState: {
        message: 'failed to stat dropped file',
        hint: 'ファイルが削除された可能性があります',
        code: null,
      },
    });

    render(<DropScreen />);

    expect(screen.getByText('failed to stat dropped file')).toBeInTheDocument();
    expect(
      screen.getByText('💡 ファイルが削除された可能性があります')
    ).toBeInTheDocument();
  });

  it('prefers loadErrorState over addErrorState when both are set', () => {
    useRecentStore.setState({
      loadErrorState: { message: 'load failed', hint: 'load hint', code: null },
      addErrorState: { message: 'add failed', hint: 'add hint', code: null },
    });

    render(<DropScreen />);

    expect(screen.getByText('load failed')).toBeInTheDocument();
    expect(screen.queryByText('add failed')).not.toBeInTheDocument();
    expect(screen.getByText('💡 load hint')).toBeInTheDocument();
    expect(screen.queryByText('💡 add hint')).not.toBeInTheDocument();
  });

  it('does not display notice when both loadErrorState and addErrorState are null', () => {
    useRecentStore.setState({
      loadErrorState: null,
      addErrorState: null,
    });

    render(<DropScreen />);

    expect(screen.queryByText(/💡/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('recent-notice')).not.toBeInTheDocument();
  });

  it('notice has role="alert" + data-testid for stable selection', () => {
    useRecentStore.setState({
      loadErrorState: { message: 'msg', hint: 'hint', code: null },
    });

    render(<DropScreen />);

    const notice = screen.getByTestId('recent-notice');
    expect(notice).toHaveAttribute('role', 'alert');
  });
});

describe('#676 SelectedCard path display', () => {
  it('shows fileName primary and parentDir secondary with full path in title', async () => {
    const probe: VideoProbeInfo = {
      path: 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv',
      fileName: '2026-01-16 21-14-05.mkv',
      width: 1920,
      height: 1080,
      fps: 60,
      durationSeconds: 7200,
      sizeBytes: 30_000_000_000,
      codec: 'h264',
    };
    const openDialog = vi.fn().mockResolvedValue(probe.path);
    const probeFn = vi.fn().mockResolvedValue(probe);
    const { findByTestId } = render(
      <DropScreen openDialogFn={openDialog} probeFn={probeFn} />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });

    const container = await findByTestId('drop-selected-path');
    expect(container).toHaveAttribute(
      'title',
      'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv',
    );
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });
});
