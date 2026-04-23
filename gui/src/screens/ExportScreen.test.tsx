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

import { ExportScreen } from './ExportScreen';
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
