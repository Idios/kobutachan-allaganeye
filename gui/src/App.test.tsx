import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

import App from './App';
import { useAppStateStore } from './state/appStateStore';
import { useMetadataStore } from './state/metadataStore';

beforeEach(() => {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
});

describe('App routing', () => {
  it('renders the drop screen by default on launch', () => {
    render(<App />);
    expect(screen.getByTestId('drop-screen')).toBeInTheDocument();
  });

  it('renders the detecting screen when navigate("detecting")', () => {
    useAppStateStore.getState().setSelectedVideoPath('/x/video.mkv');
    useAppStateStore.getState().navigate('detecting');
    render(<App />);
    expect(screen.getByTestId('detecting-screen')).toBeInTheDocument();
  });

  it('renders the complete screen when store has sample metadata', () => {
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().navigate('complete');
    render(<App />);
    expect(screen.getByTestId('complete-screen')).toBeInTheDocument();
  });

  it('renders the preview screen', () => {
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().openPreviewFor(4);
    render(<App />);
    expect(screen.getByTestId('preview-screen')).toBeInTheDocument();
  });

  it('renders the export screen', () => {
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().navigate('export');
    render(<App />);
    expect(screen.getByTestId('export-screen')).toBeInTheDocument();
  });

  it('does not render an in-app title bar (Windows native chrome is used instead)', () => {
    render(<App />);
    expect(screen.queryByTestId('window-chrome')).toBeNull();
  });

  it('renders the side rail on every screen', () => {
    render(<App />);
    expect(
      screen.getByRole('navigation', { name: 'Allagan Eye navigation' }),
    ).toBeInTheDocument();
  });
});
