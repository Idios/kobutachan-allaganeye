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
  ClipsScreen,
  DEFAULT_GAP_SECONDS,
  DEFAULT_MARGIN_SECONDS,
  collectClipCandidates,
  groupClipCandidates,
  parseMargins,
  planClipWindows,
  validateMargins,
} from './ClipsScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useClipsStore, type ClipsResult, type ClipsState } from '../state/clipsStore';
import { useMetadataStore } from '../state/metadataStore';
import type { HighlightEvent } from '../types/metadata.generated';

const METADATA_PATH = 'C:/x/metadata.json';

/**
 * 元の `events[]` の並び (未知 signal / 試合外を挟んで position が
 * 描画順に振り直されないことを pin する)。sample metadata の match 1 は
 * 0 - 915.5 秒なので、この 2 件はどちらも試合区間の中に収まる。
 */
const EVENTS: HighlightEvent[] = [
  {
    signal_id: 'ko_indicator',
    timestamp: 493.4,
    end: 494.9,
    score: 0.93,
    evidence: { samples: 15 },
    match_index: 1,
  },
  {
    signal_id: 'unknown_signal',
    timestamp: 500,
    end: 501,
    score: 0.5,
    evidence: {},
    match_index: 1,
  },
  {
    signal_id: 'assist_indicator',
    timestamp: 300.5,
    end: 301,
    score: 0.7,
    evidence: { samples: 4 },
    match_index: null,
  },
  {
    signal_id: 'assist_indicator',
    timestamp: 206.4,
    end: 207.9,
    score: 0.81,
    evidence: { samples: 14 },
    match_index: 1,
  },
];

const CLIPS_RESULT: ClipsResult = {
  success: 1,
  failure: 0,
  skipped: 0,
  cancelled: false,
  output_paths: ['C:/x/clips/clip_001_ko_00-08-13.mp4'],
};

/** `start()` の action を差し替えられるよう、実装を保持しておく。 */
const realStart = useClipsStore.getState().start;

function idleState(): void {
  useClipsStore.setState({
    status: 'idle',
    metadataPath: null,
    progress: null,
    result: null,
    error: null,
    start: realStart,
  });
}

function renderClips(
  patch: Partial<ClipsState> = {},
  overrides: {
    events?: HighlightEvent[];
    filePath?: string | null;
    dirty?: boolean;
  } = {},
): HTMLElement {
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  useMetadataStore.getState().loadSample();
  const base = useMetadataStore.getState().metadata;
  useMetadataStore.setState({
    metadata:
      base === null ? base : { ...base, events: overrides.events ?? EVENTS },
    filePath: overrides.filePath === undefined ? METADATA_PATH : overrides.filePath,
    loadedMtimeMs: 42,
    dirty: overrides.dirty ?? false,
  });
  useAppStateStore.getState().navigate('clips');
  useClipsStore.setState({
    ...patch,
    metadataPath:
      'metadataPath' in patch
        ? (patch.metadataPath ?? null)
        : (overrides.filePath === undefined ? METADATA_PATH : overrides.filePath),
  });
  const { container } = render(<ClipsScreen />);
  return container;
}

beforeEach(() => {
  mockInvoke.mockReset();
  mockInvoke.mockImplementation((cmd: string) => {
    if (cmd === 'start_clips') return Promise.resolve(CLIPS_RESULT);
    // 実行前の mtime 照合 (一致していればそのまま実行)。
    if (cmd === 'get_metadata_mtime') return Promise.resolve(42);
    return Promise.resolve(undefined);
  });
  mockListen.mockClear();
  progressHandlers.length = 0;
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  idleState();
});

// ── Pure helpers ────────────────────────────────────────────────────────────

describe('collectClipCandidates', () => {
  it('keeps the original 1-based position of metadata.events', () => {
    const candidates = collectClipCandidates(EVENTS);
    expect(candidates.map((c) => c.position)).toEqual([1, 4]);
  });

  it('drops unknown signal_id and match_index === null', () => {
    const candidates = collectClipCandidates(EVENTS);
    expect(candidates.map((c) => c.event.signal_id)).toEqual([
      'ko_indicator',
      'assist_indicator',
    ]);
  });

  it('returns [] when events are missing', () => {
    expect(collectClipCandidates(undefined)).toEqual([]);
    expect(collectClipCandidates([])).toEqual([]);
  });
});

describe('groupClipCandidates', () => {
  it('groups by match_index and sorts each group by timestamp', () => {
    const groups = groupClipCandidates(collectClipCandidates(EVENTS));
    expect(groups).toHaveLength(1);
    expect(groups[0].matchIndex).toBe(1);
    expect(groups[0].candidates.map((c) => c.event.timestamp)).toEqual([206.4, 493.4]);
    // position は描画順で振り直されない (元の events[] の位置のまま)
    expect(groups[0].candidates.map((c) => c.position)).toEqual([4, 1]);
  });

  it('sorts match groups ascending', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], match_index: 5 },
      { ...EVENTS[0], timestamp: 100, end: 101, match_index: 2 },
    ];
    const groups = groupClipCandidates(collectClipCandidates(events));
    expect(groups.map((g) => g.matchIndex)).toEqual([2, 5]);
  });
});

describe('planClipWindows (CLI plan_clips の鏡)', () => {
  const MATCHES = [
    { index: 1, start_time: 0, end_time: 915.5 },
    { index: 2, start_time: 1129.5, end_time: 2089.375 },
  ];

  /** 浮動小数の誤差を許して比較する (`round` しないので端数が残る)。 */
  function expectWindow(
    windows: ReturnType<typeof planClipWindows>,
    position: number,
    start: number,
    end: number,
  ): void {
    const window = windows.get(position);
    expect(window).toBeDefined();
    expect(window!.start).toBeCloseTo(start, 6);
    expect(window!.end).toBeCloseTo(end, 6);
  }

  it('expands each isolated event by pre / post', () => {
    const windows = planClipWindows(EVENTS, MATCHES, 10, 10);
    expectWindow(windows, 1, 483.4, 504.9);
    expectWindow(windows, 4, 196.4, 217.9);
  });

  it('merges neighbours within gap into one window (CLI default 5 s)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 300, end: 301 },
      { ...EVENTS[0], timestamp: 303, end: 304 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 1, 290, 314);
    expectWindow(windows, 2, 290, 314);
  });

  it('does not merge across a gap larger than gap', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 300, end: 301 },
      { ...EVENTS[0], timestamp: 320, end: 321 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 1, 290, 311);
    expectWindow(windows, 2, 310, 331);
  });

  // #1139: metadata に保存されたユーザー指定の区間を優先する。
  it('uses a persisted clip_start / clip_end override as-is (#1139)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], clip_start: 470, clip_end: 500 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 1, 470, 500);
  });

  it('does not merge an overridden event with its neighbours (#1139)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 300, end: 301, clip_start: 295, clip_end: 310 },
      { ...EVENTS[0], timestamp: 303, end: 304 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 1, 295, 310); // 上書きは単独
    expectWindow(windows, 2, 293, 314); // 隣は自動 (pre/post 付き)
  });

  it('clamps an override to the match span (#1139)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 1300, end: 1301, match_index: 2, clip_start: 1100, clip_end: 1400 },
    ];
    const windows = planClipWindows(events, MATCHES, 0, 0);
    expectWindow(windows, 1, 1129.5, 1400);
  });

  it('ignores an invalid override (half-specified / reversed) (#1139)', () => {
    const half: HighlightEvent[] = [{ ...EVENTS[0], clip_start: 400 }];
    expectWindow(planClipWindows(half, MATCHES, 10, 10), 1, 483.4, 504.9);

    const reversed: HighlightEvent[] = [
      { ...EVENTS[0], clip_start: 500, clip_end: 490 },
    ];
    expectWindow(planClipWindows(reversed, MATCHES, 10, 10), 1, 483.4, 504.9);
  });

  it('clamps to the match span', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 5, end: 6 },
      { ...EVENTS[0], timestamp: 900, end: 910 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 1, 0, 16);
    expectWindow(windows, 2, 890, 915.5);
  });

  it('drops events outside every match span', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 1200, end: 1201, match_index: 2 },
    ];
    // match 2 は 1129.5 からなので収まる。存在しない match 9 は span が無いので落ちる。
    const windows = planClipWindows(
      [...events, { ...EVENTS[0], timestamp: 50, end: 51, match_index: 9 }],
      MATCHES,
      10,
      10,
    );
    expect(windows.size).toBe(1);
    expectWindow(windows, 1, 1190, 1211);
  });

  it('returns no window when the clamp leaves nothing', () => {
    // match 2 は 1129.5 からだが、イベントは 100 秒台 -> end < start でクリップにならない。
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 110, end: 111, match_index: 2 },
    ];
    expect(planClipWindows(events, MATCHES, 10, 10).size).toBe(0);
  });

  // codex review 2026-11-17: CLI は round(...,2) してから 0 幅を判定する。GUI は
  // 丸めない代わりに、丸めたら潰れる幅 (< 0.01 秒) を先に落として揃える。
  it('drops windows narrower than 0.01 s (CLI rounding would collapse them)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 1129.621, end: 1129.624, match_index: 2 },
    ];
    expect(planClipWindows(events, MATCHES, 0, 0).size).toBe(0);
  });

  // 明示区間は CLI が端点を丸めてから判定するので、生の幅 < 0.01 秒でも
  // 丸めた両端が違えば書き出される (codex review 2026-11-17)。
  it('keeps an explicit window narrower than 0.01 s when rounding keeps it', () => {
    const events: HighlightEvent[] = [
      {
        ...EVENTS[0],
        timestamp: 100.004,
        end: 100.011,
        clip_start: 100.004,
        clip_end: 100.011,
      },
    ];
    const windows = planClipWindows(events, MATCHES, 0, 0);
    expectWindow(windows, 1, 100.004, 100.011);
  });

  it('keeps windows of 0.01 s or wider (CLI writes them)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 1300, end: 1300.02, match_index: 2 },
    ];
    const windows = planClipWindows(events, MATCHES, 0, 0);
    expectWindow(windows, 1, 1300, 1300.02);
  });

  it('counts unknown signal_id events in the merge (CLI does)', () => {
    const events: HighlightEvent[] = [
      { ...EVENTS[0], timestamp: 300, end: 301 },
      { ...EVENTS[1], timestamp: 303, end: 304 },
    ];
    const windows = planClipWindows(events, MATCHES, 10, 10);
    expectWindow(windows, 2, 290, 314);
  });
});

describe('validateMargins / parseMargins', () => {
  it('accepts 0 and positive decimal seconds', () => {
    expect(validateMargins('0', '10')).toBeNull();
    expect(validateMargins('2.5', '0.5')).toBeNull();
    expect(parseMargins(' 3 ', '4.5')).toEqual({ pre: 3, post: 4.5 });
  });

  it('rejects negative / non-numeric / empty / exponent', () => {
    expect(validateMargins('-1', '10')).toContain('前');
    expect(validateMargins('10', 'abc')).toContain('後');
    expect(validateMargins('', '10')).toContain('前');
    expect(validateMargins('1e3', '10')).toContain('前');
  });
});

// ── Screen ──────────────────────────────────────────────────────────────────

describe('ClipsScreen idle', () => {
  it('lists KO / ASSIST candidates with hh:mm:ss ranges and clip windows', () => {
    renderClips();
    expect(screen.getByTestId('clips-screen')).toHaveAttribute('data-status', 'idle');

    const ko = screen.getByTestId('clips-candidate-1');
    expect(within(ko).getByText('KO')).toBeInTheDocument();
    expect(within(ko).getByText('00:08:13 - 00:08:14')).toBeInTheDocument();

    const assist = screen.getByTestId('clips-candidate-4');
    expect(within(assist).getByText('ASSIST')).toBeInTheDocument();
    // 前後 10 秒 (既定) の範囲が出る
    expect(within(assist).getByText(/範囲 00:03:16 - 00:03:37/)).toBeInTheDocument();
  });

  it('shows the written window (merged neighbours share one range)', () => {
    // 512.1 と 515.5 の ASSIST は gap 5 秒以内なので 1 本のクリップになる。
    const events: HighlightEvent[] = [
      { ...EVENTS[0], signal_id: 'assist_indicator', timestamp: 512.1, end: 513.6 },
      { ...EVENTS[3], signal_id: 'assist_indicator', timestamp: 515.5, end: 517.0 },
    ];
    renderClips({}, { events });
    const first = screen.getByTestId('clips-candidate-1');
    const second = screen.getByTestId('clips-candidate-2');
    // 束ねた区間 (502.1 - 527.0) を両方の行が同じように見せる
    expect(within(first).getByText(/範囲 00:08:22 - 00:08:47/)).toBeInTheDocument();
    expect(within(second).getByText(/範囲 00:08:22 - 00:08:47/)).toBeInTheDocument();
  });

  it('shows 範囲外 and disables the row when the clip would be empty', () => {
    // match 2 は 1129.5 秒から。イベントを 110 秒台に置くとクランプで 0 幅になる。
    const events: HighlightEvent[] = [{ ...EVENTS[0], timestamp: 110, end: 111, match_index: 2 }];
    renderClips({}, { events });
    const row = screen.getByTestId('clips-candidate-1');
    expect(within(row).getByText('範囲外')).toBeInTheDocument();
    expect(screen.getByTestId('clips-cut-1')).toBeDisabled();
    expect(screen.getByTestId('clips-preview-1')).toBeDisabled();
  });

  it('uses the CLI default gap for the displayed window', () => {
    expect(DEFAULT_GAP_SECONDS).toBe(5);
  });

  it('shows the default margins in the inputs', () => {
    renderClips();
    expect(screen.getByLabelText('前 (秒)')).toHaveValue(DEFAULT_MARGIN_SECONDS);
    expect(screen.getByLabelText('後 (秒)')).toHaveValue(DEFAULT_MARGIN_SECONDS);
  });

  it('counts events outside every match and does not list them', () => {
    renderClips();
    expect(screen.getByTestId('clips-outside-note')).toHaveTextContent(
      '1 件は試合区間の外にあるため切り抜けません',
    );
    // 試合外の ASSIST (position 3) は行にならない
    expect(screen.queryByTestId('clips-candidate-3')).not.toBeInTheDocument();
  });

  it('explains an empty candidate list and links to indicators', () => {
    renderClips({}, { events: [] });
    expect(screen.getByTestId('clips-empty')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '⬦ KO / ASSIST を検出' })).toBeInTheDocument();
  });

  it('shows the metadata-missing note when nothing is loaded', () => {
    useAppStateStore.getState().reset();
    useMetadataStore.getState().clear();
    render(<ClipsScreen />);
    expect(screen.getByTestId('clips-metadata-missing')).toBeInTheDocument();
  });

  it('戻る navigates back to complete', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.click(screen.getByRole('button', { name: '◀ 一覧へ' }));
    expect(useAppStateStore.getState().screen).toBe('complete');
  });
});

describe('ClipsScreen run guards', () => {
  it('disables 切り抜く in sample mode with a reason', () => {
    renderClips({}, { filePath: null }); // sample mode (filePath === null)
    expect(screen.getByTestId('clips-cut-1')).toBeDisabled();
    expect(screen.getByTestId('clips-run-disabled')).toHaveTextContent(
      'サンプル動画では切り抜きを実行できません',
    );
  });

  it('disables 切り抜く while metadata edits are unapplied', () => {
    renderClips({}, { dirty: true });
    expect(screen.getByTestId('clips-cut-1')).toBeDisabled();
    expect(screen.getByTestId('clips-run-disabled')).toHaveTextContent(
      '未適用の編集があります',
    );
  });

  it('reports invalid margins instead of seeking or invoking the CLI', async () => {
    const user = userEvent.setup();
    renderClips();
    const pre = screen.getByLabelText('前 (秒)');
    await user.clear(pre);
    await user.type(pre, 'abc');
    await user.click(screen.getByTestId('clips-preview-1'));
    expect(screen.getByTestId('clips-margins-error')).toHaveTextContent(
      '前 は 0 以上の秒数',
    );
    expect(mockInvoke).not.toHaveBeenCalled();
    expect(useAppStateStore.getState().screen).toBe('clips');
  });

  // codex review 2026-11-17: CLI は disk の metadata.json を読むので、load 後に
  // 外から `events[]` が書き換えられていたら位置が別のイベントを指す。
  it('refuses to cut when metadata.json changed on disk since load', async () => {
    const user = userEvent.setup();
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'get_metadata_mtime') return Promise.resolve(999); // load 時 (42) と違う
      return Promise.resolve(undefined);
    });
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));

    expect(mockInvoke).not.toHaveBeenCalledWith('start_clips', expect.anything());
    expect(screen.getByTestId('clips-stale-note')).toHaveTextContent(
      'metadata.json が外部で更新されていた',
    );
  });

  it('refuses to cut when mtime cannot be verified', async () => {
    const user = userEvent.setup();
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'get_metadata_mtime'
        ? Promise.reject(new Error('nope'))
        : Promise.resolve(undefined),
    );
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));
    expect(mockInvoke).not.toHaveBeenCalledWith('start_clips', expect.anything());
    expect(screen.getByTestId('clips-stale-note')).toBeInTheDocument();
  });
});

describe('ClipsScreen actions', () => {
  it('確認 opens preview with the clip range and a one-shot seek', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.click(screen.getByTestId('clips-preview-1'));

    const app = useAppStateStore.getState();
    expect(app.screen).toBe('preview');
    expect(app.selectedMatchIndex).toBe(1);
    expect(app.clipRange).toEqual({
      start: 483.4,
      end: 504.9,
      matchIndex: 1,
      position: 1,
    });
    expect(app.pendingSeekSeconds).toBe(483.4);
  });

  it('確認 uses the edited margins', async () => {
    const user = userEvent.setup();
    renderClips();
    const post = screen.getByLabelText('後 (秒)');
    await user.clear(post);
    await user.type(post, '3');
    await user.click(screen.getByTestId('clips-preview-1'));
    expect(useAppStateStore.getState().clipRange).toEqual({
      start: 483.4,
      end: 497.9,
      matchIndex: 1,
      position: 1,
    });
  });

  it('切り抜く invokes start_clips with the 1-based events[] position', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.click(screen.getByTestId('clips-cut-4'));

    expect(mockInvoke).toHaveBeenCalledWith('start_clips', {
      req: {
        metadataPath: METADATA_PATH,
        pre: 10,
        post: 10,
        codec: 'copy',
        eventIndexes: [4],
        overwrite: false,
        // read-time CAS (読み取り前後の mtime 一致を CLI が検証する)
        expectedMtime: 42,
      },
    });
  });

  it('passes the selected codec', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.selectOptions(screen.getByLabelText('形式'), 'h264');
    await user.click(screen.getByTestId('clips-cut-1'));
    expect(mockInvoke).toHaveBeenCalledWith(
      'start_clips',
      expect.objectContaining({ req: expect.objectContaining({ codec: 'h264' }) }),
    );
  });

  it('shows the written paths after a successful run', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));
    expect(screen.getByTestId('clips-result')).toHaveTextContent('成功 1');
    expect(screen.getByText('C:/x/clips/clip_001_ko_00-08-13.mp4')).toBeInTheDocument();
  });
});

describe('ClipsScreen running / result / error', () => {
  it('shows progress and cancels via 中断', async () => {
    const user = userEvent.setup();
    renderClips({
      status: 'running',
      progress: { match_index: 2, percent: 42.5, stage: 'encoding' },
    });
    const progress = screen.getByTestId('clips-progress');
    expect(progress).toHaveTextContent('clip 002');
    expect(progress).toHaveTextContent('43%');

    await user.click(screen.getByRole('button', { name: '中断' }));
    expect(mockInvoke).toHaveBeenCalledWith('kill_tracked_processes');
  });

  it('hides a run that belongs to a different metadata.json', () => {
    renderClips({ metadataPath: 'C:/other/metadata.json' });
    expect(screen.getByTestId('clips-screen')).toHaveAttribute('data-status', 'idle');
  });

  it('offers an overwrite retry only for an existing-output failure', async () => {
    const user = userEvent.setup();
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'start_clips') {
        return Promise.reject({
          code: 'validation.range_invalid',
          message: '1 clip output(s) already exist (e.g. C:/x/clips/clip_001.mp4)',
          hint: '入力された数値が許容範囲外です。',
        });
      }
      if (cmd === 'get_metadata_mtime') return Promise.resolve(42);
      return Promise.resolve(undefined);
    });
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));

    const retry = await screen.findByTestId('clips-overwrite-retry');
    // 再実行は成功させる (上書きフラグだけを検証する)
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'start_clips') return Promise.resolve(CLIPS_RESULT);
      if (cmd === 'get_metadata_mtime') return Promise.resolve(42);
      return Promise.resolve(undefined);
    });
    await user.click(retry);

    expect(mockInvoke).toHaveBeenLastCalledWith(
      'start_clips',
      expect.objectContaining({ req: expect.objectContaining({ overwrite: true }) }),
    );
  });

  it('disables the overwrite retry while metadata has unapplied edits', async () => {
    const user = userEvent.setup();
    mockInvoke.mockImplementation((cmd: string) => {
      if (cmd === 'start_clips') {
        return Promise.reject({
          code: 'validation.range_invalid',
          message: '1 clip output(s) already exist',
          hint: null,
        });
      }
      if (cmd === 'get_metadata_mtime') return Promise.resolve(42);
      return Promise.resolve(undefined);
    });
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));
    const retry = await screen.findByTestId('clips-overwrite-retry');
    expect(retry).toBeEnabled();

    // 未適用の編集が入ったら上書き再実行も止まる (dirty ガードを迂回させない)。
    await act(async () => {
      useMetadataStore.setState({ dirty: true });
    });
    expect(screen.getByTestId('clips-overwrite-retry')).toBeDisabled();
  });

  it('does not offer the overwrite retry for other failures', () => {
    renderClips({
      status: 'error',
      error: { code: 'subprocess.exit_failed', message: 'no events', hint: null },
    });
    expect(screen.queryByTestId('clips-overwrite-retry')).not.toBeInTheDocument();
    expect(screen.getByTestId('clips-error')).toHaveTextContent('no events');
  });

  it('shows a neutral note when the run was cancelled', () => {
    renderClips({
      status: 'error',
      error: { code: 'subprocess.cancelled', message: 'cancelled', hint: null },
    });
    expect(screen.getByTestId('clips-cancelled')).toHaveTextContent(
      '切り抜きを中断しました',
    );
  });
});

describe('ClipsScreen a11y', () => {
  it('has no axe violations with the candidate list', async () => {
    const container = renderClips();
    expect(await axe(container)).toHaveNoViolations();
  }, 15000);

  it('has no axe violations with an error banner', async () => {
    const container = renderClips({
      status: 'error',
      error: {
        code: 'validation.range_invalid',
        message: '1 clip output(s) already exist',
        hint: '入力された数値が許容範囲外です。',
      },
    });
    expect(await axe(container)).toHaveNoViolations();
  }, 15000);
});
