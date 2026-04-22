import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn().mockResolvedValue(undefined),
}));

import { DetectingScreen } from './DetectingScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useAppStateStore.getState().navigate('detecting');
  useAppStateStore.getState().setSelectedVideoPath('C:/videos/test.mkv');
});

afterEach(() => {
  vi.useRealTimers();
});

describe('DetectingScreen', () => {
  it('renders the caption and file name', () => {
    render(<DetectingScreen />);
    expect(screen.getByText('観測中')).toBeInTheDocument();
    expect(screen.getByText('test.mkv')).toBeInTheDocument();
  });

  it('renders the 2 phase rows (Detecting / Refining)', () => {
    render(<DetectingScreen />);
    expect(screen.getByText('Detecting')).toBeInTheDocument();
    expect(screen.getByText('Refining')).toBeInTheDocument();
  });

  it('auto-advances via dummy interval and ends at complete screen', () => {
    vi.useFakeTimers();
    render(<DetectingScreen />);
    expect(useAppStateStore.getState().screen).toBe('detecting');
    act(() => {
      // 8.5 seconds > 8 seconds to fully drain the interval
      vi.advanceTimersByTime(8500);
    });
    // After progress completes, navigate('complete') should have been called
    expect(useAppStateStore.getState().screen).toBe('complete');
    // sample metadata is loaded
    expect(useMetadataStore.getState().metadata).not.toBeNull();
    // selectedVideoPath should be cleared after success
    expect(useAppStateStore.getState().selectedVideoPath).toBeNull();
  });

  it('returns to drop when [中断] is clicked', () => {
    render(<DetectingScreen />);
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: '中断' }));
    });
    // reducer: running -> cancelling -> (auto) cancelled -> navigate('drop')
    expect(useAppStateStore.getState().screen).toBe('drop');
  });
});
