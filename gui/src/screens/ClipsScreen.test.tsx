import { render, screen, within } from '@testing-library/react';
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
  DEFAULT_MARGIN_SECONDS,
  clipRangeFor,
  collectClipCandidates,
  groupClipCandidates,
  parseMargins,
  validateMargins,
} from './ClipsScreen';
import { useAppStateStore } from '../state/appStateStore';
import { useClipsStore, type ClipsResult, type ClipsState } from '../state/clipsStore';
import { useMetadataStore } from '../state/metadataStore';
import type { HighlightEvent } from '../types/metadata.generated';

const METADATA_PATH = 'C:/x/metadata.json';

/**
 * 元の `events[]` の並び (未知 signal / 試合外を挟んで position が
 * 描画順に振り直されないことを pin する)。
 */
const EVENTS: HighlightEvent[] = [
  {
    signal_id: 'ko_indicator',
    timestamp: 493.4,
    end: 494.9,
    score: 0.93,
    evidence: { samples: 15 },
    match_index: 3,
  },
  {
    signal_id: 'unknown_signal',
    timestamp: 500,
    end: 501,
    score: 0.5,
    evidence: {},
    match_index: 3,
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
    match_index: 3,
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
  mockInvoke.mockImplementation((cmd: string) =>
    cmd === 'start_clips' ? Promise.resolve(CLIPS_RESULT) : Promise.resolve(undefined),
  );
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
    expect(groups[0].matchIndex).toBe(3);
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

describe('clipRangeFor', () => {
  it('expands the event by pre / post', () => {
    expect(clipRangeFor({ timestamp: 493.4, end: 494.9 }, 10, 10)).toEqual({
      start: 483.4,
      end: 504.9,
    });
  });

  it('clamps the start at 0', () => {
    expect(clipRangeFor({ timestamp: 3, end: 4 }, 10, 10)).toEqual({
      start: 0,
      end: 14,
    });
  });

  it('never produces end < start', () => {
    const range = clipRangeFor({ timestamp: 3, end: 4 }, 100, 0);
    expect(range.end).toBeGreaterThanOrEqual(range.start);
  });

  it('rounds to 0.01 s like the CLI', () => {
    expect(clipRangeFor({ timestamp: 12.345, end: 13.456 }, 0.111, 0.222)).toEqual({
      start: 12.23,
      end: 13.68,
    });
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
});

describe('ClipsScreen actions', () => {
  it('確認 opens preview with the clip range and a one-shot seek', async () => {
    const user = userEvent.setup();
    renderClips();
    await user.click(screen.getByTestId('clips-preview-1'));

    const app = useAppStateStore.getState();
    expect(app.screen).toBe('preview');
    expect(app.selectedMatchIndex).toBe(3);
    expect(app.clipRange).toEqual({ start: 483.4, end: 504.9 });
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
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'start_clips'
        ? Promise.reject({
            code: 'validation.range_invalid',
            message: '1 clip output(s) already exist (e.g. C:/x/clips/clip_001.mp4)',
            hint: '入力された数値が許容範囲外です。',
          })
        : Promise.resolve(undefined),
    );
    renderClips();
    await user.click(screen.getByTestId('clips-cut-1'));

    const retry = await screen.findByTestId('clips-overwrite-retry');
    // 再実行は成功させる (上書きフラグだけを検証する)
    mockInvoke.mockImplementation((cmd: string) =>
      cmd === 'start_clips' ? Promise.resolve(CLIPS_RESULT) : Promise.resolve(undefined),
    );
    await user.click(retry);

    expect(mockInvoke).toHaveBeenLastCalledWith(
      'start_clips',
      expect.objectContaining({ req: expect.objectContaining({ overwrite: true }) }),
    );
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
