import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

  // #613: detectionParams set on the drop screen are forwarded to start_detect.
  it('forwards detectionParams from the store as start_detect params (#613)', async () => {
    useAppStateStore.getState().setDetectionParams({
      blackoutThreshold: 22,
      workers: 8,
      gpu: false,
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'start_detect',
        expect.objectContaining({
          params: {
            blackoutThreshold: 22,
            workers: 8,
            gpu: false,
          },
        }),
      );
    });
  });

  // #613: workers=0 (auto sentinel) maps to null in the wire payload.
  it('translates workers=0 (auto) to null in start_detect params (#613)', async () => {
    useAppStateStore.getState().setDetectionParams({ workers: 0 });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'start_detect',
        expect.objectContaining({
          params: expect.objectContaining({ workers: null }),
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
      if (cmd === 'kill_tracked_processes') return Promise.resolve(0);
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

  // #813 (AC1) -- 中断 click は phase 遷移だけでなく走行中 detect を
  // kill_tracked_processes で reap する。export cancel (§2.5.10) と同経路。
  it('invokes kill_tracked_processes when [中断] is clicked (#813)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      if (cmd === 'kill_tracked_processes') return Promise.resolve(0);
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalled();
    });
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: '中断' }));
    });
    await waitFor(() => {
      expect(
        invokeMock.mock.calls.some(([c]) => c === 'kill_tracked_processes'),
      ).toBe(true);
    });
  });

  // #813 (AC2) -- 旧 run の straggler detect-progress (run_id mismatch) は
  // 現在 run の UI に反映されない。現在 run の event (run_id 一致) は適用される。
  it('ignores detect-progress events from a stale run (run-id fence, #813)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    // start_detect 起動後 (run id が args に乗る) まで待つ。
    await waitFor(() => {
      expect(
        invokeMock.mock.calls.some(([c]) => c === 'start_detect'),
      ).toBe(true);
    });
    const startCall = invokeMock.mock.calls.find(([c]) => c === 'start_detect');
    const runId = (startCall?.[1] as { runId?: string } | undefined)?.runId;
    expect(typeof runId).toBe('string');

    // 旧 run の event (run_id mismatch) -> 無視。meta 行は変化しない。
    act(() => {
      emitDetectProgress({
        phase: 'probing',
        run_id: 'stale-run-id',
        width: 1280,
        height: 720,
        fps: 30,
        codec: 'hevc',
        duration_s: 120,
      });
    });
    expect(screen.queryByText(/1280x720/)).not.toBeInTheDocument();

    // 現在 run の event (run_id 一致) -> 適用される。
    act(() => {
      emitDetectProgress({
        phase: 'probing',
        run_id: runId,
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
        duration_s: 240,
      });
    });
    await waitFor(() => {
      expect(screen.getByTestId('detecting-meta').textContent).toContain(
        '1920x1080',
      );
    });
  });

  // #646 -- start_detect reject から drop へは silent 復帰せず、error
  // 表示 + 戻るボタンの明示操作で復帰する。Rust Err 内容が画面に出る。
  it('shows error UI when start_detect rejects (#646)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(
          new Error(
            'spawn allaganeye failed (python -m allaganeye): not found',
          ),
        );
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    // detecting screen は unmount されない (drop へは行かない)
    expect(useAppStateStore.getState().screen).toBe('detecting');
    // Rust Err 内容が画面に出る
    const msg = screen.getByTestId('detecting-error-message');
    expect(msg.textContent).toContain('spawn allaganeye failed');
    expect(msg.textContent).toContain('python -m allaganeye');
  });

  // #663 — Phase 4: when start_detect rejects with an AppError-shaped
  // object (`{ code, message, hint }`), the error view renders the hint
  // as a 2nd line below `errorMessage`. Bare Error throws keep the
  // existing single-line UX (toErrorState(e).hint is null for legacy errors).
  it('renders error hint as 2nd line when start_detect rejects with AppError (#663)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject({
          code: 'subprocess.spawn_failed',
          message: 'failed to spawn allaganeye CLI',
          hint: 'verify Python install',
        });
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    expect(
      screen.getByTestId('detecting-error-message').textContent,
    ).toContain('failed to spawn allaganeye CLI');
    expect(screen.getByTestId('detecting-error-hint').textContent).toContain(
      'verify Python install',
    );
  });

  it('back button on error view returns to drop (#646)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(new Error('spawn allaganeye failed'));
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: /drop へ戻る/ }));
    });
    expect(useAppStateStore.getState().screen).toBe('drop');
  });

  // #646 review Round 2 課題 2 -- retry button restarts the detect
  // run by clearing local state and bumping the run effect's dep
  // counter so start_detect is invoked a second time.
  it('retry button restarts detection after error (#646)', async () => {
    let callCount = 0;
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        callCount += 1;
        if (callCount === 1) {
          return Promise.reject(new Error('spawn allaganeye failed'));
        }
        // Second call hangs so we can observe the retry transitioned
        // back into detecting (running) without being immediately
        // resolved into complete by the happy-path mock.
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    expect(callCount).toBe(1);

    act(() => {
      fireEvent.click(screen.getByTestId('detecting-error-retry'));
    });

    // After retry: error view replaced by the running detecting screen
    // (the same data-testid='detecting-screen' container the running
    // path uses) and start_detect invoked a second time.
    await waitFor(() => {
      expect(screen.getByTestId('detecting-screen')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(callCount).toBe(2);
    });
  });

  // #646 review Round 4 補足 #6 -- retry remounts the running view via
  // `key={runCount}`. After retry the run-scoped state (progress / log
  // / probeInfo / phaseLabel / elapsed) must be back at initial values
  // so the user does not see leftover data from the failed run. Pin
  // this contract so future state additions on the running view either
  // ride the remount automatically or trip this test.
  it('retry resets run-scoped state on remount (#646 補足 #6)', async () => {
    let callCount = 0;
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        callCount += 1;
        // Both calls hang so the lifecycle is driven by detect-progress
        // events: probing + scan populate state, then phase=error trips
        // the error UI without invoke ever resolving.
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });

    render(<DetectingScreen />);
    await waitFor(() => {
      expect(lastDetectProgressHandler).not.toBeNull();
    });

    // Populate run-scoped state on the first run.
    act(() => {
      emitDetectProgress({
        phase: 'probing',
        width: 1920,
        height: 1080,
        fps: 60,
        codec: 'h264',
        duration_s: 600,
      });
      emitDetectProgress({ phase: 'scan', completed: 50, total: 100 });
    });
    await waitFor(() => {
      expect(screen.getByTestId('detecting-meta').textContent).toContain(
        '1920x1080',
      );
    });

    // Drive into error UI via phase=error event.
    act(() => {
      emitDetectProgress({ phase: 'error', message: 'boom' });
    });
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });

    act(() => {
      fireEvent.click(screen.getByTestId('detecting-error-retry'));
    });

    await waitFor(() => {
      expect(screen.getByTestId('detecting-screen')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(callCount).toBe(2);
    });

    // probeInfo cleared -> meta line falls back to "phase: start"
    // (the phaseLabel initial value).
    const meta = screen.getByTestId('detecting-meta');
    expect(meta.textContent).toContain('phase: start');
    expect(meta.textContent).not.toContain('1920x1080');
    // progress badge + both PhaseRows display 0% on a fresh remount.
    expect(screen.getAllByText('0%').length).toBeGreaterThan(0);
    // log placeholder visible (log array empty).
    expect(screen.getByText(/起動中…/)).toBeInTheDocument();
    // elapsed back to 00:00 (timer reset on remount).
    expect(screen.getByText(/経過 00:00/)).toBeInTheDocument();
  });

  // #646 review Round 2 課題 3 -- a11y: error view auto-focuses the
  // back button so screen readers announce the error context and
  // keyboard users land on a non-destructive action by default.
  it('auto-focuses [drop へ戻る] when entering error view (#646)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(new Error('boom'));
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    const back = screen.getByTestId('detecting-error-back');
    expect(document.activeElement).toBe(back);
  });

  // #646 review Round 2 課題 3 -- a11y: Escape key on the error view
  // returns to drop without requiring mouse focus on the back button.
  it('Escape on error view returns to drop (#646)', async () => {
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(new Error('boom'));
      }
      return Promise.resolve(null);
    });
    render(<DetectingScreen />);
    await waitFor(() => {
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    act(() => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(useAppStateStore.getState().screen).toBe('drop');
  });

  // #646 -- CLI が emit した phase=error event 経路でも同じ error UI
  // が表示され、ユーザーは Rust が emit した stderr tail を見ながら
  // 操作で drop に戻る。
  it('shows error UI when CLI emits a phase=error event (#646)', async () => {
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
      expect(screen.getByTestId('detecting-error')).toBeInTheDocument();
    });
    expect(useAppStateStore.getState().screen).toBe('detecting');
    expect(
      screen.getByTestId('detecting-error-message').textContent,
    ).toContain('No match boundaries detected.');
  });

  // #664 -- Refining bar に scorebar 分類進捗を統合する。refine 完了
  // (progress=88) では bar 100% に達せず ~67% で止まり、scorebar が
  // 完了 (progress=97) して初めて bar 100% になる。pct1/pct2 の終端は
  // PHASE_WINDOWS から導出する形に変更したため、PHASE_WINDOWS の重みを
  // 後で再調整しても bar の式は追従する。
  it('Refining bar reaches ~67% at refine completion (#664)', async () => {
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
      // refine 完了 = progress 88 (PHASE_WINDOWS.refine[1])。
      // pct2 = (88 - 70) / (97 - 70) * 100 ≈ 66.67% → round = 67%
      emitDetectProgress({ phase: 'refine', completed: 4, total: 4 });
    });
    const refiningRow = screen.getByTestId('phase-row-refining');
    expect(refiningRow.textContent).toContain('67%');
    expect(refiningRow.textContent).not.toContain('100%');
  });

  it('Refining bar reaches 100% at scorebar completion (#664)', async () => {
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
      // scorebar 完了 = progress 97 (PHASE_WINDOWS.scorebar[1])。
      // pct2 = (97 - 70) / (97 - 70) * 100 = 100%
      emitDetectProgress({ phase: 'scorebar', completed: 35, total: 35 });
    });
    const refiningRow = screen.getByTestId('phase-row-refining');
    expect(refiningRow.textContent).toContain('100%');
  });

  it('Refining sub label switches refine -> 分類 across phases (#664)', async () => {
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

    // refine phase 中: sub = "refine"
    act(() => {
      emitDetectProgress({ phase: 'refine', completed: 1, total: 4 });
    });
    let refiningRow = screen.getByTestId('phase-row-refining');
    expect(refiningRow.textContent).toContain('refine');
    expect(refiningRow.textContent).not.toContain('分類');

    // scorebar phase に遷移すると sub が "分類" に切替
    act(() => {
      emitDetectProgress({ phase: 'scorebar', completed: 1, total: 35 });
    });
    refiningRow = screen.getByTestId('phase-row-refining');
    expect(refiningRow.textContent).toContain('分類');
    expect(refiningRow.textContent).not.toContain('refine');
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

describe('#676 DetectingScreen path display', () => {
  it('running header shows fileName primary and parentDir secondary with full path title', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    // Pin start_detect so the screen stays in running phase long enough to assert
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve(null);
    });
    useAppStateStore.getState().setSelectedVideoPath(fullPath);
    const { findByTestId } = render(<DetectingScreen />);

    const container = await findByTestId('detecting-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('error view shows fileName primary and parentDir secondary with full path title', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    invokeMock.mockImplementation((cmd) => {
      if (cmd === 'start_detect') {
        return Promise.reject(new Error('spawn allaganeye failed'));
      }
      return Promise.resolve(null);
    });
    useAppStateStore.getState().setSelectedVideoPath(fullPath);
    const { findByTestId } = render(<DetectingScreen />);

    const container = await findByTestId('detecting-error-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });
});
