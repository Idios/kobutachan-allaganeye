import { act, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInvoke, mockListen } = vi.hoisted(() => ({
  mockInvoke: vi.fn(),
  mockListen: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mockInvoke,
}));
vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => mockListen(...args),
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

import { MinimapScreen } from './MinimapScreen';
import { useAppStateStore, type AppScreen } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

function renderMinimap() {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample(); // 9 eligible matches, filePath=null (sample mode)
  useAppStateStore.getState().navigate('minimap' as AppScreen);
  return render(<MinimapScreen />);
}

/** Render with a real (non-sample) filePath so crop button is enabled. */
function renderMinimapWithPath(path = 'C:/x/metadata.json') {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample(); // load sample fixture for match data
  // Override filePath so isSample=false
  useMetadataStore.setState({ filePath: path, loadedMtimeMs: 42, dirty: false });
  useAppStateStore.getState().navigate('minimap' as AppScreen);
  return render(<MinimapScreen />);
}

/** Fill a valid region (all 4 fields) so the execute button can enable. */
function fillValidRegion() {
  fireEvent.change(screen.getByLabelText('region x'), { target: { value: '0' } });
  fireEvent.change(screen.getByLabelText('region y'), { target: { value: '0' } });
  fireEvent.change(screen.getByLabelText('region width'), { target: { value: '300' } });
  fireEvent.change(screen.getByLabelText('region height'), { target: { value: '200' } });
}

beforeEach(() => {
  mockInvoke.mockReset();
  mockListen.mockReset();
  // Default: listen() returns a no-op unlisten fn
  mockListen.mockResolvedValue(() => undefined);
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
});

describe('MinimapScreen', () => {
  it('renders a video pane seeking the first eligible match', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'http://127.0.0.1/v', token: 't' })
        : Promise.resolve(null),
    );
    renderMinimap();
    expect(await screen.findByTestId('minimap-video')).toBeInTheDocument();
  });

  it('shows loading placeholder before register_video resolves', () => {
    // Never resolves during this sync check
    mockInvoke.mockImplementation(() => new Promise(() => {}));
    renderMinimap();
    expect(screen.getByTestId('minimap-screen')).toBeInTheDocument();
    expect(screen.queryByTestId('minimap-video')).toBeNull();
  });

  it('renders a match selector with eligible matches', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'http://127.0.0.1/v', token: 't' })
        : Promise.resolve(null),
    );
    renderMinimap();
    await screen.findByTestId('minimap-video');
    const sel = screen.getByRole('combobox', { name: /frame match/i });
    expect(sel).toBeInTheDocument();
  });

  it('renders back button navigating to complete', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'http://127.0.0.1/v', token: 't' })
        : Promise.resolve(null),
    );
    renderMinimap();
    await screen.findByTestId('minimap-video');
    expect(screen.getByText(/一覧へ/)).toBeInTheDocument();
  });

  it('shows a validation error for width below 16', () => {
    mockInvoke.mockImplementation(() => new Promise(() => {}));
    renderMinimap();
    fireEvent.change(screen.getByLabelText('region width'), { target: { value: '8' } });
    expect(screen.getByText(/16px 以上/)).toBeInTheDocument();
  });

  it('pre-fills region from the highest-confidence proposal', async () => {
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'detect_minimap_regions')
        return Promise.resolve([
          { matchIndex: 1, region: { x: 10, y: 20, w: 300, h: 400 }, confidence: 0.9, scattered: false },
        ]);
      return Promise.resolve(null);
    });
    // Need a real path for auto-detect
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ filePath: '/fake/metadata.json' });
    useAppStateStore.getState().navigate('minimap' as AppScreen);
    render(<MinimapScreen />);
    fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
    expect(await screen.findByDisplayValue('300')).toBeInTheDocument(); // W input pre-filled
  });

  it('shows a notice when no proposal is produced', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'detect_minimap_regions'
        ? Promise.resolve([{ matchIndex: 1, region: null, confidence: 0, scattered: false }])
        : Promise.resolve(cmd === 'register_video' ? { url: 'u', token: 't' } : null),
    );
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ filePath: '/fake/metadata.json' });
    useAppStateStore.getState().navigate('minimap' as AppScreen);
    render(<MinimapScreen />);
    fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
    expect(await screen.findByText(/自動検出できません/)).toBeInTheDocument();
  });

  // ── Task 11: crop execution, reload, ConflictModal, jest-axe ────────────

  it('runs crop, then reloads metadata on success', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return Promise.resolve({ success: 1, failure: 0, skipped: 0, cancelled: false });
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();
    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it('reloads even when start_minimap rejects after spawn', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return Promise.reject({ code: 'subprocess.parse_failed', message: 'x' });
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();
    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it('surfaces ConflictModal on state.mtime_conflict', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return Promise.reject({ code: 'state.mtime_conflict', message: 'conflict' });
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();
    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
    expect(await screen.findByTestId('conflict-modal')).toBeInTheDocument();
  });

  // Fix 1 (#893 Task 11): after conflict modal is dismissed (reload/cancel),
  // phase must return to idle so the 切抜き開始 button re-enables.
  it('re-enables 切抜き開始 button after conflict modal is closed (phase recovery)', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return Promise.reject({ code: 'state.mtime_conflict', message: 'conflict' });
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();

    // Trigger conflict
    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
    await screen.findByTestId('conflict-modal');

    // Dismiss modal (close/cancel path)
    fireEvent.click(screen.getByRole('button', { name: /閉じる/ }));

    // Modal gone, button re-enabled (phase=idle)
    await waitFor(() =>
      expect(screen.queryByTestId('conflict-modal')).toBeNull(),
    );
    const startBtn = screen.getByRole('button', { name: /切抜き開始/ });
    expect(startBtn).not.toBeDisabled();
  });

  // ── Part C: re-entrancy regression tests (Codex HIGH) ───────────────────

  // Part C-1: crop returns summary.cancelled while phase=running (no CANCEL_CLICKED
  // was dispatched). Before the fix, minimapReducer ignores CANCEL_CONFIRMED from
  // running → phase stays stuck at running → 切抜き開始 button never re-enables.
  it('returns to idle (not stuck running) when start_minimap returns cancelled without CANCEL_CLICKED', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap')
        return Promise.resolve({ success: 0, failure: 0, skipped: 0, cancelled: true });
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();

    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));

    // Phase must return to idle — 切抜き開始 button re-enables (not stuck running)
    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /切抜き開始/ });
      expect(btn).not.toBeDisabled();
    });
  });

  // Part C-2: auto-detect button must be disabled while a crop is running.
  // Before the fix, disabled={detecting || isSample} — crop running is not guarded.
  it('disables 自動検出を試す button while crop is running', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    // start_minimap never resolves so phase stays at running
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return new Promise(() => {});
      return Promise.resolve(null);
    });
    renderMinimapWithPath();
    fillValidRegion();

    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));

    // While running, auto-detect button must be disabled
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '自動検出を試す' })).toBeDisabled();
    });
  });

  // #899: `-vf crop` 経路は NVENC encode 失敗で libx264 へ retry する。Rust は
  // stage="fallback" / percent=0 を `minimap-progress` に emit するので、通知が
  // 無いと「進捗が 0% に巻き戻って遅くなっただけ」に見える (ExportScreen #591 と同型)。
  it('shows a per-match fallback notice when a stage=fallback event arrives (#899)', async () => {
    let progressHandler:
      | ((e: {
          payload: {
            match_index: number;
            percent: number;
            stage: string;
            message?: string;
            fallback_from?: string;
          };
        }) => void)
      | null = null;
    mockListen.mockImplementation(async (_name: string, handler: (e: unknown) => void) => {
      progressHandler = handler as NonNullable<typeof progressHandler>;
      return () => undefined;
    });
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'u', token: 't' })
        : Promise.resolve(null),
    );
    renderMinimapWithPath();
    await waitFor(() => expect(progressHandler).not.toBeNull());

    act(() => {
      progressHandler!({
        payload: {
          match_index: 1,
          percent: 0,
          stage: 'fallback',
          message: 'NVENC の初期化に失敗したため libx264 で再試行します',
          fallback_from: 'h264_nvenc -> libx264',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('minimap-fallback-notice-1').textContent).toContain('libx264');
    });
  });

  it('falls back to a generated message when the fallback event carries no message (#899)', async () => {
    let progressHandler:
      | ((e: {
          payload: {
            match_index: number;
            percent: number;
            stage: string;
            message?: string;
            fallback_from?: string;
          };
        }) => void)
      | null = null;
    mockListen.mockImplementation(async (_name: string, handler: (e: unknown) => void) => {
      progressHandler = handler as NonNullable<typeof progressHandler>;
      return () => undefined;
    });
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'u', token: 't' })
        : Promise.resolve(null),
    );
    renderMinimapWithPath();
    await waitFor(() => expect(progressHandler).not.toBeNull());

    act(() => {
      progressHandler!({
        payload: {
          match_index: 2,
          percent: 0,
          stage: 'fallback',
          fallback_from: 'h264_nvenc -> libx264',
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByTestId('minimap-fallback-notice-2').textContent).toContain(
        'h264_nvenc -> libx264',
      );
    });
  });

  // #893 R2: MinimapScreen default outDir uses lastExportOutputDir when set
  describe('#893 R2 MinimapScreen default outDir', () => {
    it('defaults outDir to lastExportOutputDir when set in the store', () => {
      // Set up store manually so we can set lastExportOutputDir AFTER reset
      // and BEFORE render (useState lazy initializer runs at mount time).
      useAppStateStore.getState().reset();
      useMetadataStore.getState().clear();
      useMetadataStore.getState().loadSample();
      useMetadataStore.setState({ filePath: 'C:/x/metadata.json', loadedMtimeMs: 42, dirty: false });
      useAppStateStore.getState().navigate('minimap' as AppScreen);
      // Set lastExportOutputDir AFTER reset so it is available at mount
      useAppStateStore.getState().setLastExportOutputDir('E:/videos/exported');
      render(<MinimapScreen />);
      // The output directory input should show the lastExportOutputDir value
      const input = screen.getByLabelText('output directory') as HTMLInputElement;
      expect(input.value).toBe('E:/videos/exported');
    });

    it('defaults outDir to the video parent dir (same as ExportScreen) when lastExportOutputDir is null', () => {
      // #928: the GUI detect flow always writes metadata.json to
      // "<video dir>/<stem>_allaganeye/", so falling back to the metadata
      // parent put minimap output in the metadata folder rather than next to
      // the match videos. ExportScreen defaults to the *video* parent
      // (deriveDefaultOutDir), so MinimapScreen must use the same basis.
      useAppStateStore.getState().reset();
      useMetadataStore.getState().clear();
      useMetadataStore.getState().loadSample();
      useMetadataStore.setState({
        filePath: 'C:/recordings/clip_allaganeye/metadata.json',
        loadedMtimeMs: 42,
        dirty: false,
      });
      useAppStateStore.getState().setSelectedVideoPath('C:/recordings/clip.mkv');
      useAppStateStore.getState().navigate('minimap' as AppScreen);
      render(<MinimapScreen />);

      const input = screen.getByLabelText('output directory') as HTMLInputElement;
      expect(input.value).toBe('C:/recordings');
      // Neither the old "/minimap" subdir nor the metadata folder.
      expect(input.value).not.toContain('minimap');
      expect(input.value).not.toContain('_allaganeye');
    });

    it('falls back to the metadata source when no video path is selected', () => {
      // Reload-from-disk entry: selectedVideoPath is null, so videoSource
      // resolves via metadata.source -- same precedence as ExportScreen.
      useAppStateStore.getState().reset();
      useMetadataStore.getState().clear();
      useMetadataStore.getState().loadSample();
      useMetadataStore.setState({
        filePath: 'D:/out/meta_allaganeye/metadata.json',
        loadedMtimeMs: 42,
        dirty: false,
      });
      useMetadataStore.setState((s) => ({
        metadata: s.metadata ? { ...s.metadata, source: 'D:/vods/session.mkv' } : s.metadata,
      }));
      useAppStateStore.getState().navigate('minimap' as AppScreen);
      render(<MinimapScreen />);

      const input = screen.getByLabelText('output directory') as HTMLInputElement;
      expect(input.value).toBe('D:/vods');
    });
  });

  it('has no a11y violations (jest-axe)', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'register_video'
        ? Promise.resolve({ url: 'u', token: 't' })
        : Promise.resolve(null),
    );
    const { container } = renderMinimap();
    expect(await axe(container)).toHaveNoViolations();
  }, 15000);

  // Fix 2 (#893 Task 11): jest-axe with conflict modal open (not just initial render).
  it('has no a11y violations with conflict modal open (jest-axe)', async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    useMetadataStore.setState({ reloadFromDisk: reload });
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'register_video') return Promise.resolve({ url: 'u', token: 't' });
      if (cmd === 'start_minimap') return Promise.reject({ code: 'state.mtime_conflict', message: 'conflict' });
      return Promise.resolve(null);
    });
    const { container } = renderMinimapWithPath();
    fillValidRegion();

    // Trigger conflict to open the modal
    fireEvent.click(screen.getByRole('button', { name: /切抜き開始/ }));
    await screen.findByTestId('conflict-modal');

    expect(await axe(container)).toHaveNoViolations();
  }, 15000);
});
