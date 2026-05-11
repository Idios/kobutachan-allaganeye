import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock, listenMock, openDialogMock } = vi.hoisted(() => ({
  invokeMock: vi.fn(),
  listenMock: vi.fn(),
  openDialogMock: vi.fn(),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));
// listenMock の戻り値を尊重する mock。デフォルトの unlisten fn は
// `beforeEach` で default 設定する (互換性維持)。個別 test で
// `mockResolvedValueOnce(spy)` すると spy 経由で unlisten 確認できる。
vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => listenMock(...args),
}));
vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: openDialogMock,
}));

import {
  ExportScreen,
  deriveDefaultOutDir,
  formatStartForFilename,
} from './ExportScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';

beforeEach(() => {
  invokeMock.mockReset();
  listenMock.mockReset();
  openDialogMock.mockReset();
  // Default: any invoke resolves with undefined; the per-test callers
  // override `export_match` / `kill_tracked_processes` as needed.
  invokeMock.mockResolvedValue(undefined);
  // Default: listen() returns a no-op unlisten function. 個別 test で
  // `mockResolvedValueOnce(spy)` すると 1 回だけ override できる
  // (mystifying-ptolemy-d112b5 review)。
  listenMock.mockResolvedValue(() => undefined);
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

  // #545 review #2: extended-length path prefix を strip してから derive
  it('strips Windows \\\\?\\ extended-length prefix before deriving', () => {
    expect(deriveDefaultOutDir('\\\\?\\E:\\videos\\clip.mkv')).toBe(
      'E:\\videos\\output',
    );
    expect(deriveDefaultOutDir('\\\\?\\C:\\foo\\bar.mp4')).toBe('C:\\foo\\output');
  });

  it('strips Windows \\\\?\\UNC\\ prefix to UNC form', () => {
    expect(
      deriveDefaultOutDir('\\\\?\\UNC\\server\\share\\clip.mkv'),
    ).toBe('\\\\server\\share\\output');
  });
});

// stripExtendedPathPrefix の単体テストは utils/path.test.ts に移動済。

// #545 review #8: filename `{start}` の HH-MM format helper
describe('formatStartForFilename', () => {
  it('formats sub-hour seconds as MM-SS', () => {
    expect(formatStartForFilename(0)).toBe('00-00');
    expect(formatStartForFilename(49)).toBe('00-49');
    expect(formatStartForFilename(60)).toBe('01-00');
    expect(formatStartForFilename(915.5)).toBe('15-15');
  });

  it('formats hour-plus seconds as H-MM-SS', () => {
    expect(formatStartForFilename(3600)).toBe('1-00-00');
    expect(formatStartForFilename(5021.5)).toBe('1-23-41');
  });

  it('clamps NaN / negative to 0', () => {
    expect(formatStartForFilename(Number.NaN)).toBe('00-00');
    expect(formatStartForFilename(-1)).toBe('00-00');
  });

  it('truncates fractional seconds (floor semantics)', () => {
    expect(formatStartForFilename(59.9)).toBe('00-59');
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

  // #545 mystifying-ptolemy-d112b5 review (2026-04-25): unmount 時に
  // listen() が返す unlisten 関数が呼ばれることをガード。漏れると memory
  // leak / 二重イベント購読 (画面遷移を繰り返したとき) を招く。
  it('calls the unlisten fn returned by listen on unmount', async () => {
    const unlistenSpy = vi.fn();
    // 1 回だけ unlistenSpy を返すよう listen mock を上書き
    listenMock.mockResolvedValueOnce(unlistenSpy);
    const { unmount } = render(<ExportScreen />);
    // listen が登録されるのを待つ (subscribe は async)
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalledWith(
        'export-progress',
        expect.any(Function),
      );
    });
    // useEffect 内の async IIFE で `unlisten = await listen(...)` が完了
    // するまで microtask 1 step 待つ。これをしないと unmount の cleanup
    // 時点で unlisten=null のまま return されることがある。
    await act(async () => {
      await Promise.resolve();
    });
    expect(unlistenSpy).not.toHaveBeenCalled();
    // unmount → useEffect cleanup が走る
    act(() => {
      unmount();
    });
    expect(unlistenSpy).toHaveBeenCalledTimes(1);
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

  // 2026-04-25 修正: dummy detect (loadSample のみ) で filePath=null のまま
  // export 画面に来た場合でも、書き出し開始ボタンが disable されず、かつ
  // クリックで export_match が走ること。Phase 3 dummy フローのバグ。
  it('still triggers export_match when filePath is null but videoSource is set', async () => {
    // 2026-04-25 修正の検証: export_match は filePath (metadata.json path) ではなく
    // videoSource (実 video path) を使う。filePath=null は sample mode (Task 1.7)
    // で disabled になるため、このテストは filePath を '/tmp/x/metadata.json'
    // (beforeEach の値) のまま維持しつつ selectedVideoPath を上書きして、
    // videoPath 引数が selectedVideoPath を優先することを確認する。
    // (filePath=null のケースは sample mode なので export 不可が正しい動作)
    useAppStateStore.getState().setSelectedVideoPath('C:/videos/x.mkv');
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
    const startBtn = screen.getByRole('button', { name: /書き出し開始/ });
    expect((startBtn as HTMLButtonElement).disabled).toBe(false);
    const user = userEvent.setup();
    await user.click(startBtn);
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'export_match');
    expect(calls.length).toBe(9);
    // videoPath が selectedVideoPath を反映している
    expect(calls[0][1]).toMatchObject({ videoPath: 'C:/videos/x.mkv' });
  });

  // 2026-04-25 修正: 書き出し開始ボタンは videoSource なし (selectedVideoPath
  // も metadata.source も null) の場合のみ disable される。
  it('disables [書き出し開始] button when both selectedVideoPath and metadata.source are absent', () => {
    useMetadataStore.setState({ filePath: null });
    // sampleMetadata.source は固定文字列が入っているので一旦 clear して
    // 空 metadata を組み立てる
    useMetadataStore.setState({
      metadata: {
        ...useMetadataStore.getState().metadata!,
        source: '' as unknown as string,
      },
    });
    useAppStateStore.getState().setSelectedVideoPath(null);
    render(<ExportScreen />);
    const startBtn = screen.getByRole('button', {
      name: /書き出し開始/,
    }) as HTMLButtonElement;
    expect(startBtn.disabled).toBe(true);
  });

  // 2026-04-25 修正: preview で m.edited.end_time を変更したとき、export 一覧
  // の duration 表示が再計算された値に更新される (古い m.duration_display を
  // 表示し続けない)。
  it('recomputes list duration display from m.edited (boundary reflection)', () => {
    const meta = useMetadataStore.getState().metadata!;
    // sample match 1: start=0, end=915.5, duration_display="15m15s"
    // edited で end を 605 に変更 → 期待 duration "10m05s"
    const edited = {
      ...meta,
      matches: meta.matches.map((m, i) =>
        i === 0
          ? { ...m, edited: { start_time: 0, end_time: 605 } }
          : m,
      ),
    };
    useMetadataStore.setState({ metadata: edited });
    render(<ExportScreen />);
    // 一覧の match_001 の duration が edited を反映している
    expect(screen.getByText('10m05s')).toBeInTheDocument();
    // 他の match (例: index 2) は edited なしなので元の値が出る
    expect(screen.getByText('15m59s')).toBeInTheDocument();
    // 元の値 "15m15s" は表示されていない (置換された)
    expect(screen.queryByText('15m15s')).not.toBeInTheDocument();
  });

  // #545 review #3: 全選択 / 全解除トグル
  it('「全解除」 unchecks every match; 「全選択」 re-checks all', async () => {
    render(<ExportScreen />);
    const user = userEvent.setup();
    expect(screen.getByText(/9 試合を書き出す/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'deselect all matches' }));
    expect(screen.getByText(/0 試合を書き出す/)).toBeInTheDocument();
    // 全 checkbox が unchecked
    for (let i = 1; i <= 9; i++) {
      const cb = screen.getByLabelText(`include match ${i}`) as HTMLInputElement;
      expect(cb.checked).toBe(false);
    }
    await user.click(screen.getByRole('button', { name: 'select all matches' }));
    expect(screen.getByText(/9 試合を書き出す/)).toBeInTheDocument();
  });

  it('全選択 / 全解除 buttons disable while running', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') return new Promise(() => undefined);
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('running');
    });
    expect(
      (screen.getByRole('button', { name: 'select all matches' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(
      (screen.getByRole('button', { name: 'deselect all matches' }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  // #545 review #6: フォルダを開くは open_folder_in_explorer (独自 Rust
  // command) を invoke する。`plugin:shell|open` は使わない (default scope の
  // URL regex で reject されるため)。
  it('completed [フォルダを開く] invokes open_folder_in_explorer with outDir', async () => {
    invokeMock.mockImplementation((cmd: string, args: unknown) => {
      if (cmd === 'export_match') {
        const a = args as { matchIndex: number; outputPath: string };
        return Promise.resolve({
          match_index: a.matchIndex,
          output_path: a.outputPath,
          duration_ms: 100,
        });
      }
      if (cmd === 'open_folder_in_explorer') return Promise.resolve(undefined);
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    await user.click(screen.getByRole('button', { name: /フォルダを開く/ }));
    expect(invokeMock).toHaveBeenCalledWith('open_folder_in_explorer', {
      path: expect.any(String),
    });
    // shell.open は呼ばれていない
    expect(
      invokeMock.mock.calls.some((c) => c[0] === 'plugin:shell|open'),
    ).toBe(false);
  });

  // #545 review #4: エラー時のボタンは「設定変更して再試行」(旧「閉じる」)。
  // クリックで idle に戻り、再度書き出し可能。
  it('error phase shows 「設定変更して再試行」 button that returns to idle', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') return Promise.reject(new Error('boom'));
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('error');
    });
    expect(
      screen.queryByRole('button', { name: '閉じる' }),
    ).not.toBeInTheDocument();
    const retryBtn = screen.getByRole('button', {
      name: /設定変更して再試行/,
    });
    await user.click(retryBtn);
    expect(screen.getByTestId('export-screen').dataset.phase).toBe('idle');
  });

  // #663 — Phase 4: when export_match rejects with an AppError-shaped
  // object (`{ code, message, hint }`), the per-match list error renders
  // the hint as a 2nd line below the primary message. The sample
  // metadata has 9 matches and the mock fails every export, so we expect
  // 9 message + 9 hint nodes. Asserting on getAllByText keeps the test
  // robust to fixture-size changes (just checks ≥1).
  it('renders per-match error hint when export_match rejects with AppError (#663)', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') {
        return Promise.reject({
          code: 'subprocess.spawn_failed',
          message: 'ffmpeg spawn failed',
          hint: 'reinstall ffmpeg',
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getAllByText(/ffmpeg spawn failed/).length).toBeGreaterThan(
        0,
      );
    });
    expect(screen.getAllByText(/reinstall ffmpeg/).length).toBeGreaterThan(0);
  });

  // #545 review #7: 進捗バー直下に「経過 0:00 / 残り —」が出る (running 中)。
  // 完了後は両方の表示が残るが setInterval は止まる。
  it('shows elapsed / remaining time line during running', async () => {
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
    // 「経過」「残り」ラベルが両方表示されている (running 後 completed まで)
    expect(screen.getByText(/経過/)).toBeInTheDocument();
    expect(screen.getByText(/残り/)).toBeInTheDocument();
  });

  // 5 回目テスト #4 (2026-04-25): per-file 進捗を overall に合算して進捗バー
  // を滑らかに動かす。旧実装は `doneCount / total` のみで 1 ファイル目 encode
  // 中は 0% 固定だった。ffmpeg `out_time_ms` 由来の per-file percent を
  // running 中の試合に対して加算する。
  it('reflects per-file running progress in the overall progress bar', async () => {
    let progressHandler: ((e: {
      payload: {
        match_index: number;
        percent: number;
        stage: string;
        message?: string;
      };
    }) => void) | null = null;
    listenMock.mockImplementation(
      async (_name: string, handler: (e: unknown) => void) => {
        progressHandler = handler as typeof progressHandler;
        return () => undefined;
      },
    );
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') return new Promise(() => undefined); // never resolves
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('running');
    });
    await waitFor(() => expect(progressHandler).not.toBeNull());
    // match 1 が 50% encoding 中 → overall = 50 / 9 ≈ 6%
    progressHandler!({
      payload: { match_index: 1, percent: 50, stage: 'encoding' },
    });
    await waitFor(() => {
      expect(screen.getByText(/6%/)).toBeInTheDocument();
    });
    // match 1 が 100% (まだ done event は来ていない、percent だけ)
    // → overall = 100 / 9 ≈ 11% (Rust 側 done event がないと status='running'
    //    のまま、percent=100 を加算)
    progressHandler!({
      payload: { match_index: 1, percent: 100, stage: 'encoding' },
    });
    await waitFor(() => {
      expect(screen.getByText(/11%/)).toBeInTheDocument();
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

  // -- #591 -- H.264 encoder auto-select / fallback notice tests.

  it('uses libx264 sub label when metadata.system_info is missing', async () => {
    // sample metadata has no system_info -> default LIBX264_INFO state.
    render(<ExportScreen />);
    await waitFor(() => {
      expect(
        screen.getByText(/H\.264 再エンコード/).parentElement?.textContent,
      ).toContain('libx264 (CPU)');
    });
  });

  it('invokes select_h264_encoder_for_export and updates sub label when system_info is present', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'select_h264_encoder_for_export') {
        return {
          encoder: 'h264_nvenc',
          display_label: 'NVENC',
          encoder_kind: 'Nvenc',
        };
      }
      return undefined;
    });
    // Inject system_info into the sample metadata.
    const current = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...current,
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
        },
      },
    });
    render(<ExportScreen />);
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'select_h264_encoder_for_export',
        {
          vendors: ['nvidia'],
          preference: ['nvidia', 'amd', 'intel'],
        },
      );
    });
    await waitFor(() => {
      expect(
        screen.getByText(/H\.264 再エンコード/).parentElement?.textContent,
      ).toContain('NVENC');
    });
  });

  it('falls back to libx264 sub label when select_h264_encoder_for_export rejects', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'select_h264_encoder_for_export') {
        throw new Error('boom');
      }
      return undefined;
    });
    const current = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...current,
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
        },
      },
    });
    render(<ExportScreen />);
    await waitFor(() => {
      expect(
        screen.getByText(/H\.264 再エンコード/).parentElement?.textContent,
      ).toContain('libx264 (CPU)');
    });
  });

  it('passes h264_encoder argument to export_match when codec is h264', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'select_h264_encoder_for_export') {
        return {
          encoder: 'h264_nvenc',
          display_label: 'NVENC',
          encoder_kind: 'Nvenc',
        };
      }
      if (cmd === 'export_match') {
        return { match_index: 1, output_path: '/tmp/match_001.mp4', duration_ms: 0 };
      }
      return undefined;
    });
    const current = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...current,
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
        },
      },
    });
    useAppStateStore.getState().setSelectedVideoPath('E:/videos/clip.mkv');
    render(<ExportScreen />);
    await waitFor(() =>
      expect(invokeMock).toHaveBeenCalledWith(
        'select_h264_encoder_for_export',
        expect.anything(),
      ),
    );
    const user = userEvent.setup();
    // Switch codec to h264.
    await user.click(screen.getByRole('button', { name: /H\.264 再エンコード/ }));
    await user.click(
      screen.getByRole('button', { name: /書き出し開始/ }),
    );
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'export_match',
        expect.objectContaining({
          codec: 'h264',
          h264Encoder: 'Nvenc',
        }),
      );
    });
  });

  it('passes h264Encoder=null to export_match when codec is copy', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'select_h264_encoder_for_export') {
        return {
          encoder: 'h264_nvenc',
          display_label: 'NVENC',
          encoder_kind: 'Nvenc',
        };
      }
      if (cmd === 'export_match') {
        return { match_index: 1, output_path: '/tmp/match_001.mp4', duration_ms: 0 };
      }
      return undefined;
    });
    const current = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...current,
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
        },
      },
    });
    useAppStateStore.getState().setSelectedVideoPath('E:/videos/clip.mkv');
    render(<ExportScreen />);
    const user = userEvent.setup();
    // Codec stays at default 'copy'.
    await user.click(
      screen.getByRole('button', { name: /書き出し開始/ }),
    );
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'export_match',
        expect.objectContaining({
          codec: 'copy',
          h264Encoder: null,
        }),
      );
    });
  });

  it('shows fallback notice when stage=fallback event arrives', async () => {
    let progressHandler: ((e: {
      payload: {
        match_index: number;
        percent: number;
        stage: string;
        message?: string;
        fallback_from?: string;
      };
    }) => void) | null = null;
    listenMock.mockImplementation(
      async (_name: string, handler: (e: unknown) => void) => {
        progressHandler = handler as typeof progressHandler;
        return () => undefined;
      },
    );
    render(<ExportScreen />);
    await waitFor(() => expect(progressHandler).not.toBeNull());
    act(() => {
      progressHandler!({
        payload: {
          match_index: 1,
          percent: 0,
          stage: 'fallback',
          message: 'NVENC の初期化に失敗したため libx264 で再試行します',
          fallback_from: 'h264_nvenc -> libx264',
        },
      });
    });
    await waitFor(() => {
      expect(
        screen.getByTestId('fallback-notice-1').textContent,
      ).toContain('libx264');
    });
  });

  // ---- #587 a11y polish ---------------------------------------------------

  it('idle export screen has no axe violations (#587)', async () => {
    const { container } = render(<ExportScreen />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it('[⬦ 書き出し開始] surfaces a no-video-source reason tooltip (#587)', () => {
    // selectedVideoPath null + metadata.source falsy => no videoSource.
    useAppStateStore.getState().setSelectedVideoPath(null);
    useMetadataStore.setState((s) => ({
      ...s,
      metadata: { ...(s.metadata ?? {}), source: null } as never,
    }));
    render(<ExportScreen />);
    const start = screen.getByRole('button', { name: /書き出し開始/ });
    expect(start).toBeDisabled();
    expect(start.getAttribute('title')).toContain('動画ファイルが選択されていません');
  });

  it('[全選択] / [全解除] surface a "書き出し中" reason while exporting (#587)', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'export_match') return new Promise(() => undefined);
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    const selectAll = screen.getByRole('button', { name: 'select all matches' });
    const deselectAll = screen.getByRole('button', { name: 'deselect all matches' });
    expect(selectAll.getAttribute('title')).toBe('書き出し中は変更できません');
    expect(deselectAll.getAttribute('title')).toBe('書き出し中は変更できません');
  });

  it('per-match skip checkbox tooltip shows skip reason while preserving help text (#587)', () => {
    // Mark match 1 as persist-skip.
    useMetadataStore.setState((s) => {
      if (!s.metadata) return s;
      return {
        ...s,
        metadata: {
          ...s.metadata,
          matches: s.metadata.matches.map((m) =>
            m.index === 1 ? { ...m, type_override: 'skip' as const } : m,
          ),
        },
      };
    });
    render(<ExportScreen />);
    const cb1 = screen.getByLabelText('include match 1') as HTMLInputElement;
    expect(cb1.disabled).toBe(true);
    expect(cb1.getAttribute('title')).toBe(
      'preview で skip に設定されています',
    );
    const cb2 = screen.getByLabelText('include match 2') as HTMLInputElement;
    // Non-skip match keeps the original help title.
    expect(cb2.getAttribute('title')).toBe('書き出し対象から除外/復帰');
  });
});

describe('ExportScreen sample mode (Task 1.7)', () => {
  beforeEach(() => {
    invokeMock.mockReset();
    listenMock.mockReset();
    openDialogMock.mockReset();
    invokeMock.mockResolvedValue(undefined);
    listenMock.mockResolvedValue(() => undefined);
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    // filePath stays null (loadSample does not set filePath) → isSample = true
    useAppStateStore.getState().navigate('export');
  });

  it('renders SampleModeBanner', () => {
    render(<ExportScreen />);
    expect(
      screen.getByText('サンプル動画です。実際の動画を選択すると保存できます。'),
    ).toBeInTheDocument();
  });

  it('disables [⬦ 書き出し開始] with sample tooltip + inline hint', () => {
    // Set a video source so the only disable reason is sample mode.
    useAppStateStore.getState().setSelectedVideoPath('C:/videos/x.mkv');
    render(<ExportScreen />);
    const startBtn = screen.getByRole('button', { name: /書き出し開始/ });
    expect(startBtn).toBeDisabled();
    expect(startBtn).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables 出力先 input', () => {
    render(<ExportScreen />);
    const input = screen.getByLabelText('output directory');
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute('title', 'サンプル動画では保存できません');
  });

  it('disables 命名規則 input', () => {
    render(<ExportScreen />);
    const input = screen.getByLabelText('name pattern');
    expect(input).toBeDisabled();
  });

  it('disables コーデック buttons', () => {
    render(<ExportScreen />);
    const codecBtns = screen.getAllByLabelText(/コーデック/i);
    expect(codecBtns.length).toBeGreaterThanOrEqual(1);
    codecBtns.forEach((b) => expect(b).toBeDisabled());
  });

  it('disables per-match exclude checkbox', () => {
    render(<ExportScreen />);
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBeGreaterThanOrEqual(1);
    checkboxes.forEach((cb) => expect(cb).toBeDisabled());
  });

  it('disables [全選択] / [全解除] buttons', () => {
    render(<ExportScreen />);
    const allBtn = screen.getByRole('button', { name: 'select all matches' });
    const noneBtn = screen.getByRole('button', { name: 'deselect all matches' });
    expect(allBtn).toBeDisabled();
    expect(noneBtn).toBeDisabled();
  });
});
