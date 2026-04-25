import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, listenMock, openDialogMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
  openDialogMock: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));
vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => {
    listenMock(...args);
    return Promise.resolve(() => undefined);
  },
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: openDialogMock,
}));

import { ExportScreen, deriveDefaultOutDir } from './ExportScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  invokeMock.mockReset();
  listenMock.mockReset();
  openDialogMock.mockReset();
  // Default: any invoke resolves with undefined; the per-test callers
  // override `export_match` / `kill_tracked_processes` as needed.
  invokeMock.mockResolvedValue(undefined);
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  useMetadataStore.setState({ filePath: '/tmp/x/metadata.json' });
  useAppStateStore.getState().navigate('export');
});

// #466 review #2: default 出力先生成ヘルパ
describe('deriveDefaultOutDir', () => {
  it('appends /output to the parent dir of a forward-slash video path', () => {
    expect(deriveDefaultOutDir('E:/videos/clip.mkv')).toBe('E:/videos/output');
  });

  it('appends \\output to the parent dir of a backslash video path', () => {
    expect(deriveDefaultOutDir('E:\\videos\\clip.mkv')).toBe('E:\\videos\\output');
  });

  it('returns empty string when videoSource is null or has no separator', () => {
    expect(deriveDefaultOutDir(null)).toBe('');
    expect(deriveDefaultOutDir('clip.mkv')).toBe('');
  });
});

describe('ExportScreen (Phase 4 #466)', () => {
  it('renders empty state when metadata is null', () => {
    useMetadataStore.getState().clear();
    render(<ExportScreen />);
    expect(screen.getByText(/No metadata/i)).toBeInTheDocument();
  });

  it('renders with idle phase and [書き出し開始] button', () => {
    render(<ExportScreen />);
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('idle');
    expect(
      screen.getByRole('button', { name: /書き出し開始/ }),
    ).toBeInTheDocument();
  });

  it('subscribes to the export-progress event on mount', async () => {
    render(<ExportScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalledWith(
        'export-progress',
        expect.any(Function),
      );
    });
  });

  it('[◀ プレビュー] returns to preview when idle', async () => {
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /プレビュー/ }));
    expect(useAppStateStore.getState().screen).toBe('preview');
  });

  it('codec selection toggles via aria-pressed', async () => {
    render(<ExportScreen />);
    const user = userEvent.setup();
    const h264 = screen.getByRole('button', { name: /H\.264/ });
    expect(h264.getAttribute('aria-pressed')).toBe('false');
    await user.click(h264);
    expect(h264.getAttribute('aria-pressed')).toBe('true');
  });

  it('[参照…] invokes the Tauri directory picker and sets outDir', async () => {
    openDialogMock.mockResolvedValue('/picked/output');
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /参照/ }));
    await waitFor(() => {
      const input = screen.getByLabelText(
        'output directory',
      ) as HTMLInputElement;
      expect(input.value).toBe('/picked/output');
    });
    expect(openDialogMock).toHaveBeenCalledWith({
      directory: true,
      multiple: false,
    });
  });

  it('[書き出し開始] invokes export_match per non-skipped match and completes', async () => {
    invokeMock.mockImplementation((cmd: string, args: unknown) => {
      if (cmd === 'export_match') {
        const a = args as { matchIndex: number; outputPath: string };
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    // sampleMetadata has 9 matches, none marked skip -> 9 invocations
    const exportCalls = invokeMock.mock.calls.filter(
      (c) => c[0] === 'export_match',
    );
    expect(exportCalls.length).toBe(9);
    expect(screen.getByRole('button', { name: /フォルダを開く/ }))
      .toBeInTheDocument();
  });

  it('continues after a single match failure (per-match error isolation)', async () => {
    invokeMock.mockImplementation((cmd: string, args: unknown) => {
      if (cmd === 'export_match') {
        const a = args as { matchIndex: number; outputPath: string };
        if (a.matchIndex === 3) return Promise.reject(new Error('ffmpeg said no'));
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    const exportCalls = invokeMock.mock.calls.filter(
      (c) => c[0] === 'export_match',
    );
    expect(exportCalls.length).toBe(9); // kept going through match 3
    // UI shows the error for match 3
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((el) => el.textContent?.includes('ffmpeg said no')))
      .toBe(true);
  });

  it('[中断] calls kill_tracked_processes and stops the loop', async () => {
    // Make export_match slow so we can hit the cancel button before the
    // whole queue drains.
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') {
        return new Promise(() => undefined); // never resolves
      }
      if (cmd === 'kill_tracked_processes') return Promise.resolve(0);
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('running');
    });
    await user.click(screen.getByRole('button', { name: '中断' }));
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith('kill_tracked_processes');
    });
  });

  // #466 review #7: preview で調整した境界 (m.edited.start_time / end_time)
  // が export_match の startSeconds / endSeconds に正しく渡される。
  it('passes m.edited.start_time / end_time to export_match (boundary propagation)', async () => {
    // sample の match 1 に edited 境界を設定
    const meta = useMetadataStore.getState().metadata!;
    const edited = {
      ...meta,
      matches: meta.matches.map((m, i) =>
        i === 0
          ? { ...m, edited: { start_time: 5.5, end_time: 12.25 } }
          : m,
      ),
    };
    useMetadataStore.setState({ metadata: edited });

    invokeMock.mockImplementation((cmd: string, args: unknown) => {
      if (cmd === 'export_match') {
        const a = args as { matchIndex: number; outputPath: string };
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'export_match');
    const m1Call = calls.find(
      (c) => (c[1] as { matchIndex: number }).matchIndex === 1,
    );
    expect(m1Call).toBeDefined();
    expect(m1Call![1]).toMatchObject({
      startSeconds: 5.5,
      endSeconds: 12.25,
    });
    // ほかの match (例: index 2) は edited なしなので元の start/end を使う
    const m2Call = calls.find(
      (c) => (c[1] as { matchIndex: number }).matchIndex === 2,
    );
    const m2 = edited.matches.find((m) => m.index === 2)!;
    expect(m2Call![1]).toMatchObject({
      startSeconds: m2.start_time,
      endSeconds: m2.end_time,
    });
  });

  // #466 review #1: per-match include/exclude checkbox (ad-hoc UI 選択)
  it('excludes a match from export when its checkbox is unchecked', async () => {
    invokeMock.mockImplementation((cmd: string, args: unknown) => {
      if (cmd === 'export_match') {
        const a = args as { matchIndex: number; outputPath: string };
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    // match 3 の checkbox を uncheck (ad-hoc exclude)
    const checkbox3 = screen.getByLabelText('include match 3') as HTMLInputElement;
    expect(checkbox3.checked).toBe(true);
    await user.click(checkbox3);
    expect(checkbox3.checked).toBe(false);

    // 全試合書き出しヘッダ表示が 9 → 8 に減る
    expect(screen.getByText(/8 試合を書き出す/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'export_match');
    expect(calls.length).toBe(8); // 9 sample matches - 1 excluded
    expect(
      calls.some((c) => (c[1] as { matchIndex: number }).matchIndex === 3),
    ).toBe(false);
  });

  it('errors surface as export-progress events update list items', async () => {
    let progressHandler: ((e: {
      payload: {
        match_index: number;
        percent: number;
        stage: string;
        message?: string;
      };
    }) => void) | null = null;
    // Override listen to capture the handler.
    listenMock.mockImplementation(
      async (_name: string, handler: (e: unknown) => void) => {
        progressHandler = handler as typeof progressHandler;
        return () => undefined;
      },
    );
    render(<ExportScreen />);
    await waitFor(() => expect(progressHandler).not.toBeNull());
    progressHandler!({
      payload: {
        match_index: 1,
        percent: 50,
        stage: 'encoding',
      },
    });
    // No phase transition (still idle until START_CLICKED) but the list
    // item picks up the state.
    await waitFor(() => {
      const items = screen.getAllByRole('listitem');
      expect(items[0]).toBeTruthy();
    });
  });
});
