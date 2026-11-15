import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInvoke, mockListen, progressHandlers } = vi.hoisted(() => {
  const progressHandlers: Array<(event: { payload: unknown }) => void> = [];
  return {
    progressHandlers,
    mockInvoke: vi.fn(),
    mockListen: vi.fn(
      async (
        _name: string,
        cb: (event: { payload: unknown }) => void,
      ): Promise<() => void> => {
        progressHandlers.push(cb);
        return () => undefined;
      },
    ),
  };
});

vi.mock('@tauri-apps/api/core', () => ({
  invoke: mockInvoke,
}));
vi.mock('@tauri-apps/api/event', () => ({
  listen: mockListen,
}));

import {
  EMPTY_REGION_INPUTS,
  fmtEventOffset,
  groupEventsByMatch,
  isLayoutResolutionFailure,
  IndicatorsScreen,
  validateRegionInputs,
} from './IndicatorsScreen';
import { useAppStateStore } from '../state/appStateStore';
import {
  useIndicatorsStore,
  type IndicatorsEvent,
  type IndicatorsLayout,
  type IndicatorsRequest,
  type IndicatorsResult,
  type IndicatorsState,
} from '../state/indicatorsStore';
import { useMetadataStore } from '../state/metadataStore';

const METADATA_PATH = 'C:/x/metadata.json';
const MTIME = 42;

const LAYOUT: IndicatorsLayout = {
  anchor_x: 0.0729,
  anchor_y: 0.0648,
  scale: 1,
  support: 6,
  confidence: 0.92,
  source: 'anchor',
};

const EVENTS: IndicatorsEvent[] = [
  { kind: 'assist', start: 130.25, end: 131, score: 0.7, samples: 3, match_index: 2 },
  { kind: 'ko', start: 12.3, end: 13, score: 0.88, samples: 3, match_index: 1 },
  { kind: 'ko', start: 5.05, end: 5.6, score: 0.91, samples: 2, match_index: 1 },
  { kind: 'assist', start: 300.5, end: 301, score: 0.66, samples: 2, match_index: null },
];

const COMPLETE_RESULT: IndicatorsResult = {
  metadata: METADATA_PATH,
  layout: LAYOUT,
  recalibrated: true,
  events: EVENTS,
  wrote_metadata: true,
};

/** `start()` の action を差し替えられるよう、実装を保持しておく。 */
const realStart = useIndicatorsStore.getState().start;

/**
 * store の値を直接初期化する。`reset()` は running 中に throw するため、
 * テスト間は setState で初期化する (テストは直列なので run も残らない)。
 */
function idleState(): void {
  useIndicatorsStore.setState({
    status: 'idle',
    phase: null,
    processedSeconds: null,
    totalSeconds: null,
    layout: null,
    events: [],
    error: null,
    start: realStart,
  });
}

function emitProgress(payload: unknown): void {
  const handler = progressHandlers[progressHandlers.length - 1];
  if (!handler) throw new Error('no indicators-progress listener registered');
  handler({ payload });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

/**
 * 実ファイル mode (filePath あり) で画面を mount する。
 *
 * store の状態は **render より前** に `patch` で入れる。render 後の store 更新は
 * act の外なので React 19 では同期的に flush されず、直後の assertion が
 * 古い DOM を見てしまう (`act` で包むより、初期状態として与える方が単純)。
 */
function renderIndicators(patch: Partial<IndicatorsState> = {}): void {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  useMetadataStore.setState({
    filePath: METADATA_PATH,
    loadedMtimeMs: MTIME,
    dirty: false,
  });
  useAppStateStore.getState().navigate('indicators');
  useIndicatorsStore.setState(patch);
  render(<IndicatorsScreen />);
}

function completePatch(
  overrides: Partial<IndicatorsState> = {},
): Partial<IndicatorsState> {
  return { status: 'complete', phase: null, layout: LAYOUT, events: EVENTS, error: null, ...overrides };
}

beforeEach(() => {
  mockInvoke.mockReset();
  // 既定: start_indicators は complete payload、それ以外 (kill_*) は undefined。
  mockInvoke.mockImplementation((cmd: string) =>
    cmd === 'start_indicators'
      ? Promise.resolve(COMPLETE_RESULT)
      : Promise.resolve(undefined),
  );
  mockListen.mockClear();
  progressHandlers.length = 0;
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  idleState();
});

describe('IndicatorsScreen idle', () => {
  it('explains the run and offers 検出を開始 / 戻る', () => {
    renderIndicators();
    expect(screen.getByTestId('indicators-screen')).toHaveAttribute(
      'data-status',
      'idle',
    );
    expect(screen.getByTestId('indicators-idle')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '検出を開始' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '戻る' })).toBeInTheDocument();
  });

  it('戻る navigates back to complete', async () => {
    const user = userEvent.setup();
    renderIndicators();
    await user.click(screen.getByRole('button', { name: '戻る' }));
    expect(useAppStateStore.getState().screen).toBe('complete');
  });

  it('disables 検出を開始 in sample mode with a visible reason', () => {
    useMetadataStore.getState().loadSample(); // filePath === null
    useAppStateStore.getState().navigate('indicators');
    render(<IndicatorsScreen />);
    expect(screen.getByRole('button', { name: '検出を開始' })).toBeDisabled();
    expect(
      screen.getByText('サンプル動画では検出を実行できません'),
    ).toBeInTheDocument();
  });

  it('shows a metadata-missing note when nothing is loaded', () => {
    useAppStateStore.getState().navigate('indicators');
    render(<IndicatorsScreen />);
    expect(
      screen.getByTestId('indicators-metadata-missing'),
    ).toBeInTheDocument();
  });
});

describe('IndicatorsScreen run (idle → running → complete)', () => {
  it('shows phase + progress while running and the summary when done', async () => {
    const pending = deferred<IndicatorsResult>();
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'start_indicators' ? pending.promise : Promise.resolve(undefined),
    );
    const user = userEvent.setup();
    renderIndicators();

    await user.click(screen.getByRole('button', { name: '検出を開始' }));
    expect(await screen.findByTestId('indicators-progress')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '中断' })).toBeInTheDocument();

    await act(async () => {
      emitProgress({ phase: 'calibrating' });
    });
    expect(screen.getByText('探索領域を解決中')).toBeInTheDocument();

    await act(async () => {
      emitProgress({ phase: 'scanning', processed_s: 120, total_s: 600 });
    });
    expect(screen.getByText('KO / ASSIST を走査中')).toBeInTheDocument();
    expect(screen.getByText('02:00 / 10:00')).toBeInTheDocument();

    await act(async () => {
      pending.resolve(COMPLETE_RESULT);
      await pending.promise;
    });

    const summary = await screen.findByTestId('indicators-summary');
    expect(summary).toHaveTextContent('KO 2');
    expect(summary).toHaveTextContent('ASSIST 2');
    expect(screen.getByTestId('indicators-layout-source')).toHaveTextContent(
      '自動解決 (anchor)',
    );
  });

  it('passes metadataPath and the loaded mtime as the CAS guard', async () => {
    const user = userEvent.setup();
    renderIndicators();
    await user.click(screen.getByRole('button', { name: '検出を開始' }));
    expect(mockInvoke).toHaveBeenCalledWith('start_indicators', {
      req: { metadataPath: METADATA_PATH, expectedMtime: MTIME },
    });
  });

  it('中断 calls cancel() on the store', async () => {
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'start_indicators'
        ? new Promise(() => undefined)
        : Promise.resolve(undefined),
    );
    const cancelSpy = vi.fn();
    const user = userEvent.setup();
    renderIndicators({ cancel: cancelSpy });
    await user.click(screen.getByRole('button', { name: '検出を開始' }));
    await user.click(await screen.findByRole('button', { name: '中断' }));
    expect(cancelSpy).toHaveBeenCalled();
  });
});

describe('IndicatorsScreen complete', () => {
  it('groups rows by match_index with 試合外 last and sorts by start', () => {
    renderIndicators(completePatch());

    const match1 = screen.getByTestId('indicators-group-1');
    expect(match1).toHaveTextContent('MATCH_001');
    const rows1 = within(match1).getAllByRole('button');
    expect(rows1).toHaveLength(2);
    // 5.05 が 12.3 より先 (start 昇順)
    expect(rows1[0]).toHaveTextContent('00:05.0 - 00:05.6');
    expect(rows1[1]).toHaveTextContent('00:12.3 - 00:13.0');

    expect(screen.getByTestId('indicators-group-2')).toHaveTextContent('MATCH_002');

    const outside = screen.getByTestId('indicators-group-outside');
    expect(outside).toHaveTextContent('試合外');
    // 試合外の区間はプレビュー遷移先が無いのでボタンにしない
    expect(within(outside).queryAllByRole('button')).toHaveLength(0);
    expect(
      within(outside).getByTestId('indicators-event-outside-0'),
    ).toHaveTextContent('ASSIST');
  });

  it('renders KO / ASSIST badges and the score', () => {
    renderIndicators(completePatch());
    const row = screen.getByTestId('indicators-event-1-1');
    expect(row).toHaveTextContent('KO');
    expect(row).toHaveTextContent('0.88');
  });

  it('shows an explicit empty message instead of an empty list', () => {
    renderIndicators(completePatch({ events: [] }));
    expect(screen.getByTestId('indicators-summary')).toHaveTextContent('KO 0');
    expect(screen.getByTestId('indicators-empty')).toHaveTextContent(
      'イベントは見つかりませんでした',
    );
    expect(screen.queryByTestId('indicators-group-1')).toBeNull();
  });

  it('shows the user-specified layout provenance', () => {
    renderIndicators(
      completePatch({ layout: { ...LAYOUT, source: 'user' } }),
    );
    expect(screen.getByTestId('indicators-layout-source')).toHaveTextContent(
      '手動指定 (--region)',
    );
  });

  it('clicking a row opens that match in preview and queues the seek', async () => {
    const user = userEvent.setup();
    renderIndicators(completePatch());

    await user.click(screen.getByTestId('indicators-event-1-1'));

    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(1);
    expect(state.pendingSeekSeconds).toBe(12.3);
  });

  it('activates a row from the keyboard (Enter) as well', async () => {
    const user = userEvent.setup();
    renderIndicators(completePatch());

    screen.getByTestId('indicators-event-2-0').focus();
    await user.keyboard('{Enter}');

    const state = useAppStateStore.getState();
    expect(state.screen).toBe('preview');
    expect(state.selectedMatchIndex).toBe(2);
    expect(state.pendingSeekSeconds).toBe(130.25);
  });

  it('offers 再検出 from the complete state (no dead end)', async () => {
    const user = userEvent.setup();
    renderIndicators(completePatch());
    await user.click(screen.getByRole('button', { name: '再検出' }));
    expect(mockInvoke).toHaveBeenCalledWith('start_indicators', {
      req: { metadataPath: METADATA_PATH, expectedMtime: MTIME },
    });
  });
});

describe('IndicatorsScreen error', () => {
  const genericError = {
    message: 'python indicators subprocess exited unexpectedly (status: 1)',
    hint: 'CLI のログを確認してください',
    code: 'subprocess.exit_failed',
  };
  const layoutError = {
    message:
      'インジケータの探索領域を解決できませんでした (2 フレームの合意が取れず)。',
    hint: null,
    code: 'subprocess.exit_failed',
  };

  it('shows the CLI message and hint', () => {
    renderIndicators({ status: 'error', error: genericError });
    const box = screen.getByTestId('indicators-error');
    expect(box).toHaveTextContent('検出に失敗しました');
    expect(box).toHaveTextContent('status: 1');
    expect(box).toHaveTextContent('CLI のログを確認してください');
    // レイアウト解決失敗ではないので領域フォームは出ない
    expect(screen.queryByTestId('indicators-region-form')).toBeNull();
  });

  it('offers the region fallback form on a layout-resolution failure', () => {
    renderIndicators({ status: 'error', error: layoutError });
    const form = screen.getByTestId('indicators-region-form');
    expect(form).toHaveTextContent('戦意値ゲージのバー本体を囲む');
    expect(within(form).getByLabelText('region x')).toBeInTheDocument();
    expect(within(form).getByLabelText('region y')).toBeInTheDocument();
    expect(within(form).getByLabelText('region width')).toBeInTheDocument();
    expect(within(form).getByLabelText('region height')).toBeInTheDocument();
  });

  it('validates the region client-side before calling start', async () => {
    const startMock = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderIndicators({ status: 'error', error: layoutError, start: startMock });

    await user.click(screen.getByRole('button', { name: 'この領域で再実行' }));

    expect(startMock).not.toHaveBeenCalled();
    expect(screen.getByTestId('indicators-region-error')).toHaveTextContent(
      'X は 0 以上の整数 (px) で入力してください',
    );
  });

  it('rejects a region that is too small for the CLI', async () => {
    const startMock = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderIndicators({ status: 'error', error: layoutError, start: startMock });

    await user.type(screen.getByLabelText('region x'), '10');
    await user.type(screen.getByLabelText('region y'), '10');
    await user.type(screen.getByLabelText('region width'), '10');
    await user.type(screen.getByLabelText('region height'), '10');
    await user.click(screen.getByRole('button', { name: 'この領域で再実行' }));

    expect(startMock).not.toHaveBeenCalled();
    expect(screen.getByTestId('indicators-region-error')).toHaveTextContent(
      '幅 (W) は 20px 以上にしてください',
    );
  });

  it('re-runs with --region when the form is valid', async () => {
    const startMock = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderIndicators({ status: 'error', error: layoutError, start: startMock });

    await user.type(screen.getByLabelText('region x'), '640');
    await user.type(screen.getByLabelText('region y'), '980');
    await user.type(screen.getByLabelText('region width'), '320');
    await user.type(screen.getByLabelText('region height'), '40');
    await user.click(screen.getByRole('button', { name: 'この領域で再実行' }));

    expect(startMock).toHaveBeenCalledWith({
      metadataPath: METADATA_PATH,
      expectedMtime: MTIME,
      region: [640, 980, 320, 40],
    } satisfies IndicatorsRequest);
  });

  it('keeps the form usable after a failed region retry', async () => {
    const startMock = vi.fn().mockRejectedValue(layoutError);
    const user = userEvent.setup();
    renderIndicators({ status: 'error', error: layoutError, start: startMock });

    await user.type(screen.getByLabelText('region x'), '640');
    await user.type(screen.getByLabelText('region y'), '980');
    await user.type(screen.getByLabelText('region width'), '320');
    await user.type(screen.getByLabelText('region height'), '40');
    await user.click(screen.getByRole('button', { name: 'この領域で再実行' }));
    expect(startMock).toHaveBeenCalledTimes(1);

    // 2 回目も領域フォームが出ている (regionAttempted で保持)
    expect(screen.getByTestId('indicators-region-form')).toBeInTheDocument();
  });

  it('treats a user cancel as a neutral notice, not a failure', () => {
    renderIndicators({
      status: 'error',
      error: { message: 'cancelled', hint: null, code: 'subprocess.cancelled' },
    });
    expect(screen.getByTestId('indicators-cancelled')).toHaveTextContent(
      '検出を中断しました。',
    );
    expect(screen.queryByTestId('indicators-error')).toBeNull();
    expect(screen.queryByTestId('indicators-region-form')).toBeNull();
    expect(screen.getByRole('button', { name: '検出を開始' })).toBeEnabled();
  });
});

describe('IndicatorsScreen a11y', () => {
  it('has no axe violations in the complete state', async () => {
    renderIndicators(completePatch());
    const container = screen.getByTestId('indicators-screen');
    expect(await axe(container)).toHaveNoViolations();
  });

  it('has no axe violations in the region fallback form', async () => {
    renderIndicators({
      status: 'error',
      error: {
        message: 'インジケータの探索領域を解決できませんでした。',
        hint: null,
        code: 'subprocess.exit_failed',
      },
    });
    const container = screen.getByTestId('indicators-screen');
    expect(await axe(container)).toHaveNoViolations();
  });
});

describe('IndicatorsScreen helpers', () => {
  it('formats event offsets as mm:ss.s', () => {
    expect(fmtEventOffset(0)).toBe('00:00.0');
    expect(fmtEventOffset(5.05)).toBe('00:05.0');
    expect(fmtEventOffset(65.24)).toBe('01:05.2');
    expect(fmtEventOffset(Number.NaN)).toBe('00:00.0');
    expect(fmtEventOffset(-1)).toBe('00:00.0');
  });

  it('groups events by match with 試合外 last', () => {
    const groups = groupEventsByMatch(EVENTS);
    expect(groups.map((g) => g.matchIndex)).toEqual([1, 2, null]);
    expect(groups[0].events.map((e) => e.start)).toEqual([5.05, 12.3]);
  });

  it('recognises only the CLI layout-resolution message as a layout failure', () => {
    expect(
      isLayoutResolutionFailure({
        message: '探索領域を解決できませんでした: band out of frame',
        hint: null,
        code: 'subprocess.exit_failed',
      }),
    ).toBe(true);
    expect(
      isLayoutResolutionFailure({
        message: '探索領域を解決できませんでした',
        hint: null,
        code: 'validation.range_invalid',
      }),
    ).toBe(false);
    expect(
      isLayoutResolutionFailure({
        message: 'python indicators subprocess exited unexpectedly',
        hint: null,
        code: 'subprocess.exit_failed',
      }),
    ).toBe(false);
    expect(isLayoutResolutionFailure(null)).toBe(false);
  });

  it('validates region inputs (integers + CLI minimum size)', () => {
    expect(validateRegionInputs(EMPTY_REGION_INPUTS)).toBe(
      'X は 0 以上の整数 (px) で入力してください',
    );
    expect(
      validateRegionInputs({ x: '1.5', y: '0', w: '320', h: '40' }),
    ).toBe('X は 0 以上の整数 (px) で入力してください');
    expect(
      validateRegionInputs({ x: '0', y: '0', w: '19', h: '40' }),
    ).toBe('幅 (W) は 20px 以上にしてください');
    expect(
      validateRegionInputs({ x: '0', y: '0', w: '320', h: '1' }),
    ).toBe('高さ (H) は 2px 以上にしてください');
    expect(
      validateRegionInputs({ x: '640', y: '980', w: '320', h: '40' }),
    ).toBeNull();
  });
});
