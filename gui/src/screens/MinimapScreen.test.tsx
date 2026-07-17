import { render, screen } from '@testing-library/react';
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
});
