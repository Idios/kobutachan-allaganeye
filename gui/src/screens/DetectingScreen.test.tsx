import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Metadata } from '../types/metadata';

const invokeMock = vi.fn();
const listenMock = vi.fn();
let lastDetectProgressHandler:
  | ((event: { payload: unknown }) => void)
  | null = null;

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (cmd: string, args?: unknown) => invokeMock(cmd, args),
}));

vi.mock('@tauri-apps/api/event', () => ({
  listen: (channel: string, handler: (event: { payload: unknown }) => void) =>
    listenMock(channel, handler),
}));

import {
  DetectingScreen,
  buildLogText,
  computeOverallPercent,
  computeEta,
  PHASE_WINDOWS,
} from './DetectingScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

const SAMPLE_METADATA: Metadata = {
  schema_version: '1',
  source: 'C:/videos/test.mkv',
  source_duration: 600.0,
  source_duration_display: '10:00',
  source_fps: 60,
  detected_at: '2026-04-27T00:00:00Z',
  detection_params: {
    sample_interval: 1.0,
    blackout_threshold: 15.0,
    min_match_duration: 300.0,
    min_blackout_duration: 3.0,
    no_audio: false,
    use_gpu: null,
    workers: null,
  },
  matches: [
    {
      index: 1,
      start_time: 0,
      end_time: 600,
      start_display: '00:00',
      end_display: '10:00',
      duration: 600,
      duration_display: '10m00s',
      type: 'fl_match',
      output_file: 'match_001.mp4',
    },
  ],
  gaps: [],
};

function emitDetectProgress(payload: Record<string, unknown>): void {
  if (lastDetectProgressHandler) {
    lastDetectProgressHandler({ payload });
  }
}

beforeEach(() => {
  invokeMock.mockReset();
  listenMock.mockReset();
  lastDetectProgressHandler = null;

  // Capture the registered detect-progress handler so tests can drive it.
  listenMock.mockImplementation((channel, handler) => {
    if (channel === 'detect-progress') {
      lastDetectProgressHandler = handler;
    }
    return Promise.resolve(() => {
      lastDetectProgressHandler = null;
    });
  });

  // Default invoke routing: start_detect resolves with a fake metadata
  // path; load_metadata returns the sample payload above.
  invokeMock.mockImplementation((cmd) => {
    if (cmd === 'start_detect') {
      return Promise.resolve({
        metadata_path: 'C:/videos/test_allaganeye/metadata.json',
        matches: SAMPLE_METADATA.matches.length,
      });
    }
    if (cmd === 'load_metadata') {
      return Promise.resolve(SAMPLE_METADATA);
    }
    if (cmd === 'get_metadata_mtime') {
      return Promise.resolve(0);
    }
    if (cmd === 'check_backup_exists') {
      return Promise.resolve(false);
    }
    if (cmd === 'load_draft') {
      return Promise.resolve(null);
    }
    return Promise.resolve(null);
  });

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

  it('invokes start_detect with the derived output dir on mount', async () => {
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'start_detect',
        expect.objectContaining({
          videoPath: 'C:/videos/test.mkv',
          outputDir: 'C:/videos/test_allaganeye',
          params: expect.any(Object),
        }),
      );
    });
  });

  it('subscribes to detect-progress events on mount', async () => {
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalledWith(
        'detect-progress',
        expect.any(Function),
      );
    });
  });

  it('navigates to complete after start_detect resolves', async () => {
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('complete');
    });
    expect(useMetadataStore.getState().metadata).not.toBeNull();
  });

  it('updates progress label on detect-progress events', async () => {
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalled();
    });
    act(() => {
      emitDetectProgress({
        phase: 'scan',
        completed: 35,
        total: 100,
        elapsed_s: 3.0,
      });
    });
    // The header meta line includes "phase: scan"
    expect(screen.getByText(/phase:\s*scan/)).toBeInTheDocument();
  });

  it('returns to drop when [中断] is clicked', async () => {
    // Pin start_detect so the cancel transition wins the race against
    // the happy-path auto-navigate to complete.
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalled();
    });
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: '中断' }));
    });
    // reducer: running -> cancelling -> (auto) cancelled -> navigate('drop')
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('drop');
    });
  });

  it('routes to drop when start_detect rejects', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(new Error('spawn allaganeye failed'));
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('drop');
    });
  });

  it('routes to drop when CLI emits a phase=error event', async () => {
    // Make start_detect hang so the only termination path is via error event.
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalled();
    });
    act(() => {
      emitDetectProgress({
        phase: 'error',
        message: 'No match boundaries detected.',
      });
    });
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('drop');
    });
  });

  it('falls back to loadSample when no video is selected (StateSwitcher dev mode)', async () => {
    // Reset to a clean state without selectedVideoPath -- mimics the
    // StateSwitcher hopping straight into "detecting" without going
    // through DropScreen.
    useAppStateStore.getState().reset();
    useAppStateStore.getState().navigate('detecting');

    render(<DetectingScreen />);
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('complete');
    });
    // start_detect must NOT have been called -- sample mode skips spawn.
    expect(
      invokeMock.mock.calls.some(([cmd]) => cmd === 'start_detect'),
    ).toBe(false);
  });
});

describe('DetectingScreen helpers', () => {
  it('computeOverallPercent maps phase windows', () => {
    // probing window is [1, 3]
    expect(
      computeOverallPercent({ phase: 'probing' }),
    ).toBe(PHASE_WINDOWS.probing[0]);

    // scan window is [3, 70]; 50% inside scan -> 36.5
    expect(
      computeOverallPercent({
        phase: 'scan',
        completed: 50,
        total: 100,
      }),
    ).toBeCloseTo(3 + (70 - 3) * 0.5);

    // refine window is [70, 88]; 100% inside refine -> 88
    expect(
      computeOverallPercent({
        phase: 'refine',
        completed: 4,
        total: 4,
      }),
    ).toBe(88);

    // unknown phase -> 0
    expect(computeOverallPercent({ phase: 'unknown_phase' })).toBe(0);
  });

  it('computeOverallPercent clamps inner ratio to [0,1]', () => {
    // Out-of-range completed/total ratios must stay inside the window.
    const result = computeOverallPercent({
      phase: 'scan',
      completed: 999,
      total: 100,
    });
    expect(result).toBe(70); // clamped to scan end
  });

  it('computeEta returns null when progress is 0 or 100', () => {
    expect(computeEta(0, 10)).toBeNull();
    expect(computeEta(100, 10)).toBeNull();
  });

  it('computeEta extrapolates remaining time from elapsed and percent', () => {
    // 25% in 10s -> 30s remaining (total 40s, elapsed 10s).
    expect(computeEta(25, 10)).toBeCloseTo(30);
  });

  it('buildLogText skips chatty intra-scan updates', () => {
    expect(
      buildLogText({
        phase: 'scan',
        completed: 27,
        total: 100,
      }),
    ).toBeNull();
  });

  it('buildLogText logs scan milestones at every 10%', () => {
    const text = buildLogText({
      phase: 'scan',
      completed: 30,
      total: 100,
    });
    expect(text).toContain('Pass 1 scan');
    expect(text).toContain('30');
  });

  it('buildLogText surfaces error messages', () => {
    expect(
      buildLogText({
        phase: 'error',
        message: 'spawn failed',
      }),
    ).toContain('spawn failed');
  });

  it('buildLogText surfaces done with match count', () => {
    expect(
      buildLogText({
        phase: 'done',
        matches: 5,
      }),
    ).toContain('5');
  });
});
