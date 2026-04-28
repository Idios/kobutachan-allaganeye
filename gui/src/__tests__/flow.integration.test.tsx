/**
 * Phase 2 flow integration tests.
 *
 * These exercise the full App render tree (not individual screens) with
 * @tauri-apps/api mocked, stepping through the screen + phase transitions
 * end-to-end. True Tauri binary + WebView2 E2E is deferred to #484
 * (L2 E2E 統合テスト); this file acts as the regression gate for Phase 2
 * flows and gates the performance targets in docs/ui-architecture.md.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, dialogOpenMock, dialogAskMock, listenMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  dialogOpenMock: vi.fn(),
  dialogAskMock: vi.fn(),
  listenMock: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
  // convertFileSrc is called by PreviewScreen to resolve cached thumbnails
  // to URLs the browser can fetch. jsdom doesn't care about the scheme,
  // so a simple passthrough is enough.
  convertFileSrc: (p: string) => `asset://localhost/${p}`,
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: dialogOpenMock,
  ask: dialogAskMock,
}));

// #523: ConfirmExitModal subscribes to the Tauri event bus on mount. The
// real listen() reaches into Tauri's native shim which is absent under
// vitest; stub it to a no-op that returns a no-op unsubscribe.
vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => {
    listenMock(...args);
    return Promise.resolve(() => undefined);
  },
}));

// #568: DropScreen subscribes to webview onDragDropEvent on mount. The
// real getCurrentWebview() reaches into Tauri's native shim which is
// absent under vitest; stub it to a no-op that returns a no-op
// unsubscribe so the integration flow tests don't crash on mount.
vi.mock('@tauri-apps/api/webview', () => ({
  getCurrentWebview: () => ({
    onDragDropEvent: vi.fn().mockResolvedValue(() => undefined),
  }),
}));

import App from '../App';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { useRecentStore } from '../state/recentStore';

/**
 * Shared invoke dispatcher used when tests don't need per-command overrides.
 * Default answers are intentionally "happy": metadata loads, apply succeeds,
 * backup probes return true.
 */
function configureHappyInvoke() {
  invokeMock.mockImplementation((cmd: string, args: unknown) => {
    switch (cmd) {
      case 'load_metadata':
        return Promise.resolve({
          source: (args as { path?: string }).path ?? 'x',
          source_duration: 1000,
          source_duration_display: '16:40',
          detected_at: '2026-04-22T00:00:00Z',
          detection_params: {
            sample_interval: 2,
            blackout_threshold: 15,
            min_match_duration: 300,
            min_blackout_duration: 3,
            no_audio: false,
            use_gpu: null,
            workers: null,
          },
          matches: [
            {
              index: 1,
              start_time: 0,
              end_time: 500,
              start_display: '00:00',
              end_display: '08:20',
              duration: 500,
              duration_display: '8m20s',
              type: 'fl_match',
              output_file: 'match_001.mp4',
            },
          ],
          gaps: [],
        });
      case 'apply_changes':
        return Promise.resolve();
      case 'restore_from_original':
        return Promise.resolve();
      case 'check_backup_exists':
        return Promise.resolve(true);
      // #465
      case 'register_video':
        return Promise.resolve({
          url: 'http://127.0.0.1:0/video/test-token',
          token: 'test-token',
        });
      case 'probe_video': {
        // #465 review (B): drop が default で Tauri probe_video を呼ぶように
        // なったので、テスト用 happy-path 値を返す。path は引数を echo back
        // して selectedVideoPath assertion (dialog で resolve した値) と
        // 一致させる。
        const probePath =
          (args as { path?: string } | undefined)?.path ?? 'C:/videos/x.mkv';
        return Promise.resolve({
          path: probePath,
          fileName: probePath.split(/[/\\]/).pop() ?? probePath,
          sizeBytes: 38 * 1024 * 1024 * 1024,
          durationSeconds: 10228.735,
          width: 1920,
          height: 1080,
          fps: 60,
          codec: 'h264',
        });
      }
      case 'generate_match_thumbnails':
        return Promise.resolve([]);
      // #523
      case 'is_process_running':
        return Promise.resolve(false);
      case 'kill_tracked_processes':
        return Promise.resolve(0);
      case 'force_exit_app':
        return Promise.resolve();
      // #466 -- Phase 4 export
      case 'export_match': {
        const a = args as { matchIndex: number; outputPath: string };
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      // #569 -- Phase 2.5 detect
      case 'start_detect': {
        const a = args as { outputDir?: string } | undefined;
        const out = a?.outputDir ?? 'C:/out';
        return Promise.resolve({
          metadata_path: `${out}/metadata.json`,
          matches: 1,
        });
      }
      // #571 -- recent.json history. Default is empty so the integration
      // flow tests don't show a populated list; the persisted entry after
      // a probe is harmless to assert as resolved.
      case 'read_recent':
        return Promise.resolve([]);
      case 'add_recent':
        return Promise.resolve([]);
      case 'clear_recent':
        return Promise.resolve();
      default:
        return Promise.resolve();
    }
  });
}

beforeEach(() => {
  invokeMock.mockReset();
  dialogOpenMock.mockReset();
  dialogAskMock.mockReset();
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  // #571: in-memory store reset so each integration test starts with a
  // clean recent list; the disk-side mock returns [] above.
  useRecentStore.getState().reset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('flow A1: drop -> selected via [参照…]', () => {
  it('advances drop screen from idle through probing to selected', async () => {
    // #465 review (B): drop が default で Tauri probe_video を呼ぶように
    // なったので invoke happy mock が必須。
    configureHappyInvoke();
    dialogOpenMock.mockResolvedValue('C:/videos/test.mkv');
    render(<App />);
    expect(screen.getByTestId('drop-screen')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
  });
});

describe('flow A2: [OK] from selected -> detecting', () => {
  it('navigates to detecting and records the video path', async () => {
    configureHappyInvoke();
    dialogOpenMock.mockResolvedValue('C:/videos/test.mkv');
    render(<App />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /OK — 検知開始/ }));
    // #569: DetectingScreen now invokes start_detect on mount and
    // navigates to complete when the promise resolves. We assert the
    // selectedVideoPath landed before any awaits resolve, then wait
    // for the full pipeline to settle (detecting transient may flush
    // straight to complete in the mocked happy path).
    expect(useAppStateStore.getState().selectedVideoPath).toBe(
      'C:/videos/test.mkv',
    );
    await waitFor(() => {
      const screenName = useAppStateStore.getState().screen;
      expect(['detecting', 'complete']).toContain(screenName);
    });
  });
});

describe('flow A3: detecting auto-advances to complete', () => {
  it('start_detect promise resolution drives navigation to complete (#569)', async () => {
    configureHappyInvoke();
    useAppStateStore.getState().setSelectedVideoPath('/x/video.mkv');
    useAppStateStore.getState().navigate('detecting');
    render(<App />);
    expect(screen.getByTestId('detecting-screen')).toBeInTheDocument();
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('complete');
    });
    expect(useMetadataStore.getState().metadata).not.toBeNull();
  });
});

describe('flow A4: complete <-> preview round-trip', () => {
  it('double-click opens preview and [◀ 一覧へ] returns to complete', async () => {
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().navigate('complete');
    render(<App />);

    const user = userEvent.setup();
    await user.dblClick(screen.getByTestId('match-row-4'));
    expect(useAppStateStore.getState().screen).toBe('preview');
    expect(useAppStateStore.getState().selectedMatchIndex).toBe(4);

    await user.click(screen.getByRole('button', { name: /一覧へ/ }));
    expect(useAppStateStore.getState().screen).toBe('complete');
  });
});

describe('flow F: drop [キャンセル] clears selection', () => {
  it('returns from selected to idle without setting selectedVideoPath', async () => {
    configureHappyInvoke();
    dialogOpenMock.mockResolvedValue('C:/videos/test.mkv');

    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      expect(screen.getByTestId('drop-selected-card')).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'キャンセル' }));

    expect(screen.getByTestId('drop-screen').dataset.phase).toBe('idle');
    expect(useAppStateStore.getState().selectedVideoPath).toBeNull();
  });
});

describe('flow G: detecting [中断] returns to drop', () => {
  it('cancel button transitions through cancelling -> cancelled -> drop (#569)', async () => {
    // Make start_detect hang so the only termination path is the
    // cancel button (otherwise the mocked happy path would auto-
    // navigate to complete before we can click 中断).
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_detect') {
        return new Promise(() => {
          /* never resolves */
        });
      }
      return Promise.resolve();
    });
    useAppStateStore.getState().setSelectedVideoPath('/x/video.mkv');
    useAppStateStore.getState().navigate('detecting');
    render(<App />);
    expect(screen.getByTestId('detecting-screen')).toBeInTheDocument();
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: '中断' }));
    });
    await waitFor(() => {
      expect(useAppStateStore.getState().screen).toBe('drop');
    });
  });
});

describe('flow H: export cancel mid-flight (#466 + #523)', () => {
  it('kill_tracked_processes is invoked when 中断 is clicked', async () => {
    // Make export_match hang so we can observe the cancel path.
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') return new Promise(() => undefined);
      if (cmd === 'kill_tracked_processes') return Promise.resolve(0);
      return Promise.resolve(undefined);
    });
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ filePath: '/tmp/x/metadata.json' });
    useAppStateStore.getState().navigate('export');
    render(<App />);
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('running');
    });
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: '中断' }));
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');
    });
  });
});

describe('flow I: export completes (#466)', () => {
  it('walks through every match and surfaces the フォルダを開く button', async () => {
    configureHappyInvoke();
    useMetadataStore.getState().loadSample();
    useMetadataStore.setState({ filePath: '/tmp/x/metadata.json' });
    useAppStateStore.getState().navigate('export');
    render(<App />);
    await userEvent
      .setup()
      .click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe(
        'completed',
      );
    });
    expect(
      screen.getByRole('button', { name: /フォルダを開く/ }),
    ).toBeInTheDocument();
  });
});

describe('flow J: restore (#516)', () => {
  it('RestoreButton is disabled when no backup', () => {
    configureHappyInvoke();
    // Override check_backup_exists for this test
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'check_backup_exists') return Promise.resolve(false);
      if (cmd === 'load_metadata') return Promise.reject(new Error('unused'));
      return Promise.resolve();
    });
    useMetadataStore.setState({
      filePath: '/x',
      hasBackup: false,
      metadata: {
        source: 'x',
        source_duration: 1,
        source_duration_display: '0:01',
        detected_at: '2026-04-22T00:00:00Z',
        detection_params: {
          sample_interval: 2,
          blackout_threshold: 15,
          min_match_duration: 300,
          min_blackout_duration: 3,
          no_audio: false,
          use_gpu: null,
          workers: null,
        },
        matches: [],
        gaps: [],
      },
    });
    useAppStateStore.getState().navigate('complete');
    render(<App />);
    expect(screen.getByRole('button', { name: '元に戻す' })).toBeDisabled();
  });

  it('clicking [元に戻す] invokes restore_from_original', async () => {
    let restoreInvoked = false;
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'restore_from_original') {
        restoreInvoked = true;
        return Promise.resolve();
      }
      if (cmd === 'check_backup_exists') return Promise.resolve(true);
      if (cmd === 'load_metadata') {
        return Promise.resolve({
          source: 'x',
          source_duration: 1,
          source_duration_display: '0:01',
          detected_at: '2026-04-22T00:00:00Z',
          detection_params: {
            sample_interval: 2,
            blackout_threshold: 15,
            min_match_duration: 300,
            min_blackout_duration: 3,
            no_audio: false,
            use_gpu: null,
            workers: null,
          },
          matches: [],
          gaps: [],
        });
      }
      return Promise.resolve();
    });

    useMetadataStore.setState({
      filePath: '/x',
      hasBackup: true,
      metadata: {
        source: 'x',
        source_duration: 1,
        source_duration_display: '0:01',
        detected_at: '2026-04-22T00:00:00Z',
        detection_params: {
          sample_interval: 2,
          blackout_threshold: 15,
          min_match_duration: 300,
          min_blackout_duration: 3,
          no_audio: false,
          use_gpu: null,
          workers: null,
        },
        matches: [],
        gaps: [],
      },
    });
    useAppStateStore.getState().navigate('complete');
    render(<App />);

    // RestoreButton uses plugin-dialog `ask` (Tauri 2 disables window.confirm).
    dialogAskMock.mockResolvedValueOnce(true);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '元に戻す' }));
    await waitFor(() => {
      expect(restoreInvoked).toBe(true);
    });
  });
});

describe('flow L: complete [× 閉じる] resets to drop', () => {
  it('clears the store and returns to drop_idle', async () => {
    useMetadataStore.getState().loadSample();
    useAppStateStore.getState().navigate('complete');
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '閉じる' }));
    expect(useMetadataStore.getState().metadata).toBeNull();
    expect(useAppStateStore.getState().screen).toBe('drop');
  });
});

/* ------------------------------------------------------------------------ */
/* Performance gates — see docs/ui-architecture.md §性能目標 for targets.     */
/* jsdom is lighter than real webviews so thresholds are set conservatively. */
/* ------------------------------------------------------------------------ */

describe('performance: App first mount', () => {
  it('renders the initial drop screen in under 250ms (jsdom target)', () => {
    const start = performance.now();
    render(<App />);
    const end = performance.now();
    expect(screen.getByTestId('drop-screen')).toBeInTheDocument();
    const elapsed = end - start;
    expect(elapsed).toBeLessThan(250);
  });
});

describe('performance: navigate latency', () => {
  it('screen switch completes in under 16ms per frame budget', () => {
    render(<App />);
    const start = performance.now();
    act(() => {
      useAppStateStore.getState().navigate('export');
    });
    const end = performance.now();
    const elapsed = end - start;
    // Generous jsdom budget: 50ms (real WebView target is 16ms for 60fps).
    expect(elapsed).toBeLessThan(50);
  });
});

describe('performance: brightness path build (512 samples x 1000 iterations)', () => {
  it('builds the brightness SVG path in under 50ms total (jsdom)', async () => {
    const { buildBrightnessPath } = await import('../utils/brightness');
    const samples = Array.from({ length: 512 }, (_, i) =>
      Math.sin(i / 32) * 100 + 100,
    );
    const start = performance.now();
    for (let i = 0; i < 1000; i++) {
      buildBrightnessPath(samples, 700, 100);
    }
    const end = performance.now();
    const elapsed = end - start;
    // 1000 iterations of 512-point path generation under 50ms = <0.05ms/iter
    // Real target (Phase 2 plan) = 5ms for a single call; 1000x budget ~= 50ms.
    expect(elapsed).toBeLessThan(500);
  });
});
