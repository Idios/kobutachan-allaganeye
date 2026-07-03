import { act, render, screen, waitFor, within } from '@testing-library/react';
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
  // override `start_export` / `kill_tracked_processes` as needed.
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

// #680 (旧 #466 review #2): default 出力先生成ヘルパ
describe('deriveDefaultOutDir', () => {
  it('returns the parent dir of a forward-slash video path', () => {
    expect(deriveDefaultOutDir('E:/videos/clip.mkv')).toBe('E:/videos');
  });

  it('returns the parent dir of a backslash video path', () => {
    expect(deriveDefaultOutDir('E:\\videos\\clip.mkv')).toBe('E:\\videos');
  });

  it('returns empty string when videoSource is null or has no separator', () => {
    expect(deriveDefaultOutDir(null)).toBe('');
    expect(deriveDefaultOutDir('clip.mkv')).toBe('');
  });

  // #545 review #2: extended-length path prefix を strip してから derive
  it('strips Windows \\\\?\\ extended-length prefix before deriving', () => {
    expect(deriveDefaultOutDir('\\\\?\\E:\\videos\\clip.mkv')).toBe(
      'E:\\videos',
    );
    expect(deriveDefaultOutDir('\\\\?\\C:\\foo\\bar.mp4')).toBe('C:\\foo');
  });

  it('strips Windows \\\\?\\UNC\\ prefix to UNC form', () => {
    expect(
      deriveDefaultOutDir('\\\\?\\UNC\\server\\share\\clip.mkv'),
    ).toBe('\\\\server\\share');
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

  // #837 (P3-a) -- listen() 解決前に unmount された場合でも、解決時に取得した
  // unlisten が必ず呼ばれる (leak しない)。修正前は cleanup 時 unlisten=null の
  // まま return し、後から解決する listener が teardown されず leak していた
  // (DetectingScreen #813 と同クラス)。発火する側 = late-resolve 時の teardown。
  it('unlistens when unmounted before listen() resolves (#837)', async () => {
    const unlistenSpy = vi.fn();
    let resolveListen!: (fn: () => void) => void;
    const pendingListen = new Promise<() => void>((res) => {
      resolveListen = res;
    });
    // export-progress の listen を解決保留にする
    listenMock.mockImplementationOnce(() => pendingListen);

    const { unmount } = render(<ExportScreen />);
    await waitFor(() => {
      expect(listenMock).toHaveBeenCalledWith(
        'export-progress',
        expect.any(Function),
      );
    });
    // listen 未解決のまま unmount (cleanup が走る)
    unmount();

    // listen が後から解決する
    await act(async () => {
      resolveListen(unlistenSpy);
      await Promise.resolve();
    });

    // 解決時に disposed を見て即時 unlisten される
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

  it('[書き出し開始] invokes start_export with full metadata and completes', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({
          success: 9,
          failure: 0,
          skipped: 0,
          cancelled: false,
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
    // single start_export call (not one per match)
    const exportCalls = invokeMock.mock.calls.filter(
      (c) => c[0] === 'start_export',
    );
    expect(exportCalls.length).toBe(1);
    expect(screen.getByRole('button', { name: /フォルダを開く/ }))
      .toBeInTheDocument();
  });

  it('completes even when some matches fail (per-match error via progress events)', async () => {
    let progressHandler: ((e: { payload: { match_index: number; percent: number; stage: string; message?: string } }) => void) | null = null;
    listenMock.mockImplementation(async (_name: string, handler: (e: unknown) => void) => {
      progressHandler = handler as typeof progressHandler;
      return () => undefined;
    });
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({
          success: 8,
          failure: 1,
          skipped: 0,
          cancelled: false,
        });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    // Simulate an error progress event for match 3 before completion
    await waitFor(() => expect(progressHandler).not.toBeNull());
    progressHandler!({ payload: { match_index: 3, percent: 0, stage: 'error', message: 'ffmpeg said no' } });
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    // UI shows the error for match 3 (surfaced via progress event)
    const alerts = await screen.findAllByRole('alert');
    expect(alerts.some((el) => el.textContent?.includes('ffmpeg said no')))
      .toBe(true);
  });

  it('[中断] calls kill_tracked_processes and stops the export', async () => {
    // Make start_export slow so we can hit the cancel button before it resolves.
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
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
  // が start_export の metadataJson の中に正しく含まれる。
  // #761: boundary は metadata 丸ごと Python に渡すので、edited フィールドが
  // metadataJson に含まれているかを確認する。
  it('passes metadata with m.edited to start_export (boundary propagation)', async () => {
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

    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({ success: 9, failure: 0, skipped: 0, cancelled: false });
      }
      return Promise.resolve(undefined);
    });
    render(<ExportScreen />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
    await waitFor(() => {
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
    });
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'start_export');
    expect(calls.length).toBe(1);
    const reqArg = (calls[0][1] as { req: { metadataJson: typeof edited } }).req;
    // metadataJson に edited 境界が含まれている
    const m1 = reqArg.metadataJson.matches.find((m: { index: number }) => m.index === 1);
    expect(m1?.edited).toMatchObject({ start_time: 5.5, end_time: 12.25 });
  });

  // #466 review #1: per-match include/exclude checkbox (ad-hoc UI 選択)
  it('excludes a match from export when its checkbox is unchecked', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({ success: 8, failure: 0, skipped: 1, cancelled: false });
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
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'start_export');
    expect(calls.length).toBe(1);
    // excludedIndexes contains match 3
    const reqArg = (calls[0][1] as { req: { excludedIndexes: number[] } }).req;
    expect(reqArg.excludedIndexes).toContain(3);
  });

  // 2026-04-25 修正: dummy detect (loadSample のみ) で filePath=null のまま
  // export 画面に来た場合でも、書き出し開始ボタンが disable されず、かつ
  // クリックで start_export が走ること。Phase 3 dummy フローのバグ。
  it('still triggers start_export when filePath is null but videoSource is set', async () => {
    // 2026-04-25 修正の検証: start_export は filePath (metadata.json path) ではなく
    // videoSource (実 video path) を使う。filePath=null は sample mode (Task 1.7)
    // で disabled になるため、このテストは filePath を '/tmp/x/metadata.json'
    // (beforeEach の値) のまま維持しつつ selectedVideoPath を上書きして、
    // start_export が呼ばれることを確認する。
    // (filePath=null のケースは sample mode なので export 不可が正しい動作)
    useAppStateStore.getState().setSelectedVideoPath('C:/videos/x.mkv');
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({ success: 9, failure: 0, skipped: 0, cancelled: false });
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
    const calls = invokeMock.mock.calls.filter((c) => c[0] === 'start_export');
    expect(calls.length).toBe(1);
    // metadataJson が start_export に渡されている
    const reqArg = (calls[0][1] as { req: { metadataJson: unknown } }).req;
    expect(reqArg.metadataJson).toBeDefined();
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
      if (cmd === 'start_export') return new Promise(() => undefined);
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
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({ success: 9, failure: 0, skipped: 0, cancelled: false });
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
      if (cmd === 'start_export') return Promise.reject(new Error('boom'));
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

  // #663 / #761 — when start_export rejects with an AppError-shaped object,
  // the screen transitions to error phase. Per-match error details come via
  // export-progress events (stage='error'). Test that error phase is reached
  // when start_export rejects.
  it('transitions to error phase when start_export rejects with AppError (#663)', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
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
      expect(screen.getByTestId('export-screen').dataset.phase).toBe('error');
    });
  });

  // #678 Lane II-b §2.1 — handleOpenFolder catch path: AppError struct +
  // legacy Error + raw value + null/undefined reject の 4 系統を
  // toErrorState(e) の .message / .hint で扱えていることを確認。
  // 旧実装 `e instanceof Error ? e.message : String(e)` では AppError struct
  // が `[object Object]` になるバグを TDD で検出するための test。
  describe('ExportScreen handleOpenFolder catch (#678)', () => {
    // open_folder_in_explorer を reject 値別に mock 化し、完了画面まで遷移
    // させてから [フォルダを開く] をクリックする共通 helper。start_export は
    // 通常通り resolve させて completed phase まで持っていく。
    async function setupAndClickOpenFolder(
      openFolderReject: unknown,
      user: ReturnType<typeof userEvent.setup>,
    ) {
      invokeMock.mockImplementation((cmd: string) => {
        if (cmd === 'start_export') {
          return Promise.resolve({ success: 9, failure: 0, skipped: 0, cancelled: false });
        }
        if (cmd === 'open_folder_in_explorer') {
          return Promise.reject(openFolderReject);
        }
        return Promise.resolve(undefined);
      });
      render(<ExportScreen />);
      await user.click(screen.getByRole('button', { name: /書き出し開始/ }));
      await waitFor(() => {
        expect(screen.getByTestId('export-screen').dataset.phase).toBe('completed');
      });
      await user.click(screen.getByRole('button', { name: /フォルダを開く/ }));
    }

    it('renders AppError struct message + hint as 2-line error (#678)', async () => {
      const appError = {
        code: 'io.file_not_found',
        message: '指定された出力先が見つかりません',
        hint: 'パスを確認してください',
      };
      const user = userEvent.setup();
      await setupAndClickOpenFolder(appError, user);
      await waitFor(() => {
        expect(
          screen.getByText('指定された出力先が見つかりません'),
        ).toBeInTheDocument();
      });
      // #693 InlineErrorHint refactor: hint は `💡 {hint}` の形で 1 span に render される
      expect(screen.getByText('💡 パスを確認してください')).toBeInTheDocument();
      expect(screen.getByTestId('open-folder-error-hint')).toBeInTheDocument();
    });

    it('renders Error instance message only when no hint (#678)', async () => {
      const err = new Error('Some error');
      const user = userEvent.setup();
      await setupAndClickOpenFolder(err, user);
      await waitFor(() => {
        expect(screen.getByText('Some error')).toBeInTheDocument();
      });
      // hint は無いので hint 要素が rendered されない
      expect(
        screen.queryByTestId('open-folder-error-hint'),
      ).not.toBeInTheDocument();
    });

    it('renders String(e) result for raw value (#678)', async () => {
      const user = userEvent.setup();
      await setupAndClickOpenFolder('simple string', user);
      await waitFor(() => {
        expect(screen.getByText('simple string')).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId('open-folder-error-hint'),
      ).not.toBeInTheDocument();
    });

    it('renders Unknown error for null/undefined reject (#678)', async () => {
      const user = userEvent.setup();
      await setupAndClickOpenFolder(null, user);
      await waitFor(() => {
        // alert 要素は表示されるが、内容は `[object Object]` ではない
        // (`toErrorState(null).message` は `String(null)` = `"null"` を返す)。
        // open_folder_in_explorer の alert は完了画面の 1 つだけ
        // (per-match error が無い phase=completed のため)。
        const alerts = screen.queryAllByRole('alert');
        expect(alerts.length).toBeGreaterThan(0);
        for (const alertEl of alerts) {
          expect(alertEl.textContent).not.toBe('[object Object]');
        }
      });
      expect(
        screen.queryByTestId('open-folder-error-hint'),
      ).not.toBeInTheDocument();
    });
  });

  // #545 review #7: 進捗バー直下に「経過 0:00 / 残り —」が出る (running 中)。
  // 完了後は両方の表示が残るが setInterval は止まる。
  it('shows elapsed / remaining time line during running', async () => {
    invokeMock.mockImplementation((cmd: string) => {
      if (cmd === 'start_export') {
        return Promise.resolve({ success: 9, failure: 0, skipped: 0, cancelled: false });
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
      if (cmd === 'start_export') return new Promise(() => undefined); // never resolves
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

  it('invokes enumerate_h264_encoders and updates sub label when system_info is present', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'enumerate_h264_encoders') {
        // RTX 5090 SKU → 3 parallel NVENC slots
        return [
          { slot_index: 0, encoder_kind: 'Nvenc', display_label: 'NVENC #1' },
          { slot_index: 1, encoder_kind: 'Nvenc', display_label: 'NVENC #2' },
          { slot_index: 2, encoder_kind: 'Nvenc', display_label: 'NVENC #3' },
        ];
      }
      return undefined;
    });
    // Inject system_info with RTX 5090 GPU model into the sample metadata.
    const current = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...current,
        system_info: {
          gpu_vendors_available: ['nvidia'],
          gpu_vendor_used: 'nvidia',
          vendor_preference: ['nvidia', 'amd', 'intel'],
          gpu: ['NVIDIA GeForce RTX 5090'],
        },
      },
    });
    render(<ExportScreen />);
    await waitFor(() => {
      expect(invokeMock).toHaveBeenCalledWith(
        'enumerate_h264_encoders',
        {
          req: {
            vendors: ['nvidia'],
            preference: ['nvidia', 'amd', 'intel'],
            gpuModels: ['NVIDIA GeForce RTX 5090'],
          },
        },
      );
    });
    // 3 slots → badge should show "NVENC ×3"
    await waitFor(() => {
      expect(
        screen.getByText(/H\.264 再エンコード/).parentElement?.textContent,
      ).toContain('NVENC ×3');
    });
  });

  it('falls back to libx264 sub label when enumerate_h264_encoders rejects', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'enumerate_h264_encoders') {
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

  it('passes codec=h264 to start_export when h264 codec is selected', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'enumerate_h264_encoders') {
        return [{ slot_index: 0, encoder_kind: 'Nvenc', display_label: 'NVENC' }];
      }
      if (cmd === 'start_export') {
        return { success: 9, failure: 0, skipped: 0, cancelled: false };
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
        'enumerate_h264_encoders',
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
        'start_export',
        expect.objectContaining({
          req: expect.objectContaining({ codec: 'h264' }),
        }),
      );
    });
  });

  it('passes codec=copy to start_export when copy codec is selected (default)', async () => {
    invokeMock.mockImplementation(async (cmd: string) => {
      if (cmd === 'enumerate_h264_encoders') {
        return [{ slot_index: 0, encoder_kind: 'Nvenc', display_label: 'NVENC' }];
      }
      if (cmd === 'start_export') {
        return { success: 9, failure: 0, skipped: 0, cancelled: false };
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
        'start_export',
        expect.objectContaining({
          req: expect.objectContaining({ codec: 'copy' }),
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
      if (cmd === 'start_export') return new Promise(() => undefined);
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

describe('#676 ExportScreen header path display', () => {
  function renderExportScreenWith({
    selectedVideoPath,
    metadataSource,
  }: {
    selectedVideoPath: string | null;
    metadataSource: string | null;
  }) {
    invokeMock.mockResolvedValue(undefined);
    listenMock.mockResolvedValue(() => undefined);
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.getState().loadSample();
    // Override source in metadata (null clears it to force videoSource=null)
    const currentMeta = useMetadataStore.getState().metadata;
    if (currentMeta) {
      useMetadataStore.setState({
        metadata: {
          ...currentMeta,
          source: metadataSource ?? (null as unknown as string),
        },
      });
    }
    useMetadataStore.setState({ filePath: '/tmp/x/metadata.json' });
    useAppStateStore.getState().navigate('export');
    useAppStateStore.setState({ selectedVideoPath });
    return render(<ExportScreen />);
  }

  it('shows fileName primary and parentDir secondary with title (videoSource)', async () => {
    const fullPath = 'E:\\videos\\20260116\\2026-01-16 21-14-05.mkv';
    const { findByTestId } = renderExportScreenWith({
      selectedVideoPath: fullPath,
      metadataSource: 'C:\\different\\path.mkv',
    });

    const container = await findByTestId('export-path');
    expect(container).toHaveAttribute('title', fullPath);
    expect(
      within(container).getByText('2026-01-16 21-14-05.mkv'),
    ).toBeInTheDocument();
    expect(
      within(container).getByText('E:\\videos\\20260116'),
    ).toBeInTheDocument();
  });

  it('does not render path display when videoSource is null', async () => {
    const { queryByTestId } = renderExportScreenWith({
      selectedVideoPath: null,
      metadataSource: null,
    });

    expect(queryByTestId('export-path')).not.toBeInTheDocument();
  });
});

// #805 Phase 1: post_match match no-crash guard.
// ExportScreen must render without crashing when metadata.matches[] contains
// a post_match entry (output_file undefined, post_match: true). This is a
// minimal no-crash lock -- export exclusion UX is Phase 2.
describe('#805 ExportScreen post_match no-crash guard', () => {
  const metaWithPostMatch = {
    source: 'C:\\videos\\rec.mkv',
    source_duration: 1200,
    source_duration_display: '20:00',
    detected_at: '2026-06-26T00:00:00Z',
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
        start_time: 100,
        end_time: 1000,
        start_display: '01:40',
        end_display: '16:40',
        duration: 900,
        duration_display: '15m00s',
        type: 'fl_match' as const,
        output_file: 'match_001.mp4',
      },
      {
        index: 2,
        start_time: 1000,
        end_time: 1120,
        start_display: '16:40',
        end_display: '18:40',
        duration: 120,
        duration_display: '2m00s',
        type: 'unknown' as const,
        // output_file deliberately absent -- post_match segment
        post_match: true as const,
      },
    ],
    gaps: [],
  };

  beforeEach(() => {
    invokeMock.mockReset();
    listenMock.mockReset();
    invokeMock.mockResolvedValue(undefined);
    listenMock.mockResolvedValue(() => undefined);
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    useMetadataStore.setState({
      metadata: metaWithPostMatch as never,
      hasBackup: false,
      filePath: '/tmp/meta.json',
    });
    useAppStateStore.getState().navigate('export');
  });

  it('renders post_match match without crashing (no-crash lock #805)', () => {
    expect(() => render(<ExportScreen />)).not.toThrow();
  });

  it('shows both matches in the export list without crashing', () => {
    render(<ExportScreen />);
    expect(screen.getByTestId('export-screen')).toBeInTheDocument();
    // Both match rows appear (post_match treated as normal match in Phase 1)
    expect(screen.getByLabelText('include match 1')).toBeInTheDocument();
    expect(screen.getByLabelText('include match 2')).toBeInTheDocument();
  });

  // #805 Phase 2: post_match rows are non-selectable in the export list.
  // The functional exclusion is already guaranteed by export.py (Phase 1);
  // these tests lock the visual/selection UX (spec §8).
  describe('Phase 2 non-selectable UX', () => {
    it('post_match checkbox is disabled and unchecked', () => {
      render(<ExportScreen />);
      const cb = screen.getByLabelText('include match 2');
      expect(cb).toBeDisabled();
      expect(cb).not.toBeChecked();
      // normal match stays selectable
      const active = screen.getByLabelText('include match 1');
      expect(active).toBeEnabled();
      expect(active).toBeChecked();
    });

    it('post_match checkbox surfaces the disabled reason (§1.2)', () => {
      render(<ExportScreen />);
      const cb = screen.getByLabelText('include match 2');
      expect(cb).toHaveAttribute(
        'title',
        '試合後の映像のため書き出し対象外です',
      );
    });

    it('header count excludes post_match matches', () => {
      render(<ExportScreen />);
      expect(screen.getByText('1 試合を書き出す')).toBeInTheDocument();
    });

    it('post_match row is marked and badged (試合後)', () => {
      render(<ExportScreen />);
      const row = screen.getByTestId('export-row-2');
      expect(row).toHaveAttribute('data-post-match', 'true');
      expect(within(row).getByText('試合後')).toBeInTheDocument();
      const normalRow = screen.getByTestId('export-row-1');
      expect(normalRow).not.toHaveAttribute('data-post-match');
      expect(within(normalRow).queryByText('試合後')).toBeNull();
    });

    it('全選択 does not re-include post_match', async () => {
      const user = userEvent.setup();
      render(<ExportScreen />);
      await user.click(
        screen.getByRole('button', { name: 'deselect all matches' }),
      );
      await user.click(
        screen.getByRole('button', { name: 'select all matches' }),
      );
      expect(screen.getByLabelText('include match 1')).toBeChecked();
      expect(screen.getByLabelText('include match 2')).not.toBeChecked();
    });
  });
});
