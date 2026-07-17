import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInvoke } = vi.hoisted(() => ({
  mockInvoke: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mockInvoke,
}));

import { MinimapScreen } from './MinimapScreen';
import { useAppStateStore, type AppScreen } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

function renderMinimap() {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample(); // 9 eligible matches, filePath=null (sample mode)
  useAppStateStore.getState().navigate('minimap' as AppScreen);
  render(<MinimapScreen />);
}

/** Render with a real (non-sample) filePath so auto-detect button is enabled. */
function renderMinimapWithPath(path = '/fake/metadata.json') {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample(); // load sample fixture for match data
  // Override filePath so isSample=false and auto-detect button is enabled
  useMetadataStore.setState({ filePath: path });
  useAppStateStore.getState().navigate('minimap' as AppScreen);
  render(<MinimapScreen />);
}

beforeEach(() => {
  mockInvoke.mockReset();
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
    renderMinimapWithPath();
    fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
    expect(await screen.findByDisplayValue('300')).toBeInTheDocument(); // W input pre-filled
  });

  it('shows a notice when no proposal is produced', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'detect_minimap_regions'
        ? Promise.resolve([{ matchIndex: 1, region: null, confidence: 0, scattered: false }])
        : Promise.resolve(cmd === 'register_video' ? { url: 'u', token: 't' } : null),
    );
    renderMinimapWithPath();
    fireEvent.click(screen.getByRole('button', { name: '自動検出を試す' }));
    expect(await screen.findByText(/自動検出できません/)).toBeInTheDocument();
  });
});
