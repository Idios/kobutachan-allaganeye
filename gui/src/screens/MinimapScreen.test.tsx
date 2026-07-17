import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
