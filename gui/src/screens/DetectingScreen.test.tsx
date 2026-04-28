import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
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
    // start_detect must hang here so the meta line stays visible long
    // enough to assert (otherwise the happy-path mock auto-navigates
    // to complete and unmounts the screen before getByText runs).
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
        phase: 'scan',
        completed: 35,
        total: 100,
        elapsed_s: 3.0,
      });
    });
    // The header meta line includes "phase: scan" before any probing
    // event arrives (probing is the trigger that switches the meta line
    // to ffprobe metadata).
    expect(screen.getByText(/phase:\s*scan/)).toBeInTheDocument();
  });

  // #569 review Round 1 課題 1 -- meta line reflects probing payload.
  it('renders meta line with ffprobe data after probing event', async () => {
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
        phase: 'probing',
        duration_s: 7215.371,
        width: 1920,
        height: 1080,
        fps: 60.0,
        codec: 'h264',
        elapsed_s: 0.04,
      });
    });
    const meta = screen.getByTestId('detecting-meta');
    expect(meta.textContent).toContain('1920x1080');
    expect(meta.textContent).toContain('60.00fps');
    expect(meta.textContent).toContain('h264');
    // fmtTime renders 7215.371s as "2:00:15".
    expect(meta.textContent).toContain('2:00:15');
  });

  // #639 review (実機検証 3 回目) -- ResizeObserver で log pane の
  // 縮小 (window resize / parent flex 変動) を検知して末尾に再追従
  // させる。新エントリ追加経路と独立。
  it('re-pins scrollTop to scrollHeight when log pane is resized (#639)', async () => {
    let resizeCallback: ResizeObserverCallback | null = null;
    const disconnect = vi.fn();
    const originalRO = globalThis.ResizeObserver;
    // jsdom does not implement ResizeObserver; install a minimal stub
    // that captures the callback so the test can drive it.
    class StubObserver {
      constructor(cb: ResizeObserverCallback) {
        resizeCallback = cb;
      }
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {
        disconnect();
      }
    }
    globalThis.ResizeObserver =
      StubObserver as unknown as typeof ResizeObserver;

    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });

    try {
      render(<DetectingScreen />);
      await waitFor(() => {
        expect(listenMock).toHaveBeenCalled();
      });

      const log = screen.getByRole('log');
      // Stub layout numbers (jsdom default 0) so the resize handler
      // has a non-trivial scrollHeight target.
      Object.defineProperty(log, 'scrollHeight', {
        configurable: true,
        get: () => 1500,
      });
      // Place scrollTop at an outdated (mid) position simulating the
      // "see-cut" state after resize before the observer fires.
      log.scrollTop = 200;

      // Trigger the observer's resize callback (jsdom doesn't lay
      // anything out so we drive the callback synthetically; the
      // assertion is about the handler logic, not jsdom layout).
      expect(resizeCallback).not.toBeNull();
      act(() => {
        // ResizeObserver callback signature: (entries, observer)
        resizeCallback!(
          [] as unknown as ResizeObserverEntry[],
          {} as unknown as ResizeObserver,
        );
      });

      // Handler must pull scrollTop to the current scrollHeight so the
      // most recent line lands inside the (now smaller) viewport.
      expect(log.scrollTop).toBe(1500);
    } finally {
      globalThis.ResizeObserver = originalRO;
    }
  });

  // #639 -- log viewport must auto-scroll to the bottom whenever a
  // new entry arrives so the latest line is always visible without
  // user interaction.
  it('scrolls the log viewport to the bottom on new entries (#639)', async () => {
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

    const log = screen.getByRole('log');
    // jsdom doesn't lay out elements, so scrollHeight is always 0 by
    // default. Stub the layout numbers so the auto-scroll effect has a
    // non-trivial target to write into scrollTop.
    Object.defineProperty(log, 'scrollHeight', {
      configurable: true,
      get: () => 1000,
    });
    Object.defineProperty(log, 'clientHeight', {
      configurable: true,
      get: () => 200,
    });

    // Drive a few events so the log array grows and the
    // auto-scroll effect fires.
    act(() => {
      emitDetectProgress({ phase: 'start' });
      emitDetectProgress({ phase: 'probing', duration_s: 600, codec: 'h264' });
      emitDetectProgress({
        phase: 'scan',
        completed: 50,
        total: 500,
      });
    });

    // jsdom defaults scrollTop to 0; the effect should pull it to the
    // current scrollHeight (1000) so the latest entry sits at the
    // bottom of the visible viewport.
    expect(log.scrollTop).toBe(1000);
  });

  // #569 review Round 1 課題 2 -- log lines carry data-kind attribute
  // and apply the matching colour-coding class.
  it('renders log entries with kind-specific styling', async () => {
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
        phase: 'cache_hit',
        boundaries: 9,
      });
    });
    const log = screen.getByRole('log');
    const entries = log.querySelectorAll('[data-kind]');
    const kinds = Array.from(entries).map((el) =>
      el.getAttribute('data-kind'),
    );
    expect(kinds).toContain('warn');
    // The cache_hit row gets the warn class applied (CSS Modules adds
    // a hashed suffix, so we assert the className contains the literal
    // CSS module key rather than an exact match).
    const warnEntry = Array.from(entries).find(
      (el) => el.getAttribute('data-kind') === 'warn',
    );
    expect(warnEntry?.className).toMatch(/logEntryWarn/);
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

  it('buildLogText logs scan milestones at every 10% with info kind', () => {
    const entry = buildLogText({
      phase: 'scan',
      completed: 30,
      total: 100,
    });
    expect(entry).not.toBeNull();
    expect(entry?.text).toContain('Pass 1 scan');
    expect(entry?.text).toContain('30');
    expect(entry?.kind).toBe('info');
  });

  // #569 review Round 1 課題 2 — kind colour-coding contract.
  it('buildLogText returns kind=error for phase=error', () => {
    const entry = buildLogText({
      phase: 'error',
      message: 'spawn failed',
    });
    expect(entry).not.toBeNull();
    expect(entry?.text).toContain('spawn failed');
    expect(entry?.kind).toBe('error');
  });

  it('buildLogText returns kind=done for phase=done', () => {
    const entry = buildLogText({
      phase: 'done',
      matches: 5,
    });
    expect(entry).not.toBeNull();
    expect(entry?.text).toContain('5');
    expect(entry?.kind).toBe('done');
  });

  it('buildLogText returns kind=warn for phase=cache_hit', () => {
    const entry = buildLogText({
      phase: 'cache_hit',
      boundaries: 9,
    });
    expect(entry).not.toBeNull();
    expect(entry?.text).toContain('キャッシュヒット');
    expect(entry?.kind).toBe('warn');
  });

  it('buildLogText returns kind=info for routine progress phases', () => {
    for (const phase of [
      'start',
      'probing',
      'chunk_dispatch',
      'refine',
      'scorebar',
      'audio',
      'writing_metadata',
    ] as const) {
      const entry = buildLogText({ phase });
      expect(entry).not.toBeNull();
      expect(entry?.kind).toBe('info');
    }
  });

  it('[中断] is enabled while running and has no disabled tooltip (#587)', () => {
    render(<DetectingScreen />);
    const cancelBtn = screen.getByRole('button', { name: '中断' });
    expect(cancelBtn).not.toBeDisabled();
    // While running, the button must NOT carry a title-attribute reason.
    expect(cancelBtn.hasAttribute('title')).toBe(false);
  });

  it('has no axe violations while running (#587)', async () => {
    const { container } = render(<DetectingScreen />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
