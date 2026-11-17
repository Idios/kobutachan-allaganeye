/**
 * ClipRangeView (#1139).
 *
 * #1139 の指摘は「クリップ範囲を詰めるために preview を開くと、画面が試合境界の
 * エディタのままで初期値も試合の開始 / 終了だった = どの状態か読めない」。
 * ここでは **状態の分離** を pin する:
 *
 * - IN / OUT の初期値は `clipRange`（イベントの絶対秒）であって試合境界ではない
 * - ± の nudge は `clipRange` の local state だけを動かし、metadata は [保存] まで触らない
 * - [保存] で `metadata.events[position].clip_start / clip_end` + `apply()`
 *
 * UI 部品 (`TimecodePane`) は試合境界のエディタと共有しているが、状態は共有しない。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { ClipRangeView } from './ClipRangeView';
import { parseTimecode } from '../components/TimecodePane';
import { useAppStateStore } from '../state/appStateStore';
import { useMetadataStore } from '../state/metadataStore';
import { overrideWindowFor } from '../utils/clipWindow';
import type { HighlightEvent } from '../types/metadata.generated';
import { fmtPreciseTime } from '../utils/time';

const FILE_PATH = 'C:/x/metadata.json';
const MATCH_INDEX = 4;
const FPS = 60;

/** 試合 4 の境界 (2438.75 - 5021.25) とは明確に違う値。 */
const CLIP_START = 483.4;
const CLIP_END = 504.9;

const applyMock = vi.fn<() => Promise<void>>();

/**
 * metadata を実ファイル mode で用意する (`position` 経由の保存には `filePath` が要る)。
 * イベントは 1 件だけにして `position: 1` で指す。
 */
function setupMetadata(override: Partial<HighlightEvent> = {}): void {
  useMetadataStore.getState().loadSample();
  const base = useMetadataStore.getState().metadata!;
  const event: HighlightEvent = {
    signal_id: 'ko_indicator',
    timestamp: 493.2,
    end: 494.7,
    score: 0.91,
    evidence: { samples: 15 },
    match_index: MATCH_INDEX,
    ...override,
  };
  useMetadataStore.setState({
    metadata: { ...base, events: [event] },
    filePath: FILE_PATH,
    apply: applyMock,
  });
}

function selectClipRange(position: number | null = 1): void {
  useAppStateStore.getState().setClipRange({
    start: CLIP_START,
    end: CLIP_END,
    matchIndex: MATCH_INDEX,
    position,
  });
}

/** TC 入力欄の値を秒に戻す (表示は H:MM:SS.FF)。 */
function tcSeconds(label: 'IN (clip start)' | 'OUT (clip end)'): number {
  const input = screen.getByLabelText(`${label} timecode`) as HTMLInputElement;
  const parsed = parseTimecode(input.value, FPS);
  if (parsed === null) throw new Error(`unparsable timecode: ${input.value}`);
  return parsed;
}

beforeEach(() => {
  invokeMock.mockReset();
  invokeMock.mockImplementation((cmd: string) => {
    if (cmd === 'register_video') {
      return Promise.resolve({
        url: 'http://127.0.0.1:0/video/test-token',
        token: 'test-token',
      });
    }
    return Promise.reject(new Error(`unmocked: ${cmd}`));
  });
  applyMock.mockReset();
  applyMock.mockResolvedValue(undefined);
  useAppStateStore.getState().reset();
  useMetadataStore.getState().clear();
  setupMetadata();
  selectClipRange();
});

describe('ClipRangeView', () => {
  // #1139 の核: 初期値が「試合の開始 / 終了」ではなく「クリップの IN / OUT」になる。
  it('initialises IN / OUT from the clip range, not from the match boundaries', () => {
    render(<ClipRangeView />);

    expect(tcSeconds('IN (clip start)')).toBeCloseTo(CLIP_START, 1);
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(CLIP_END, 1);

    // 試合境界 (2438.75 / 5021.25) が漏れていないことを明示的に確認する。
    const inValue = (screen.getByLabelText('IN (clip start) timecode') as HTMLInputElement)
      .value;
    expect(inValue).toBe(fmtPreciseTime(CLIP_START, FPS));
    expect(inValue).not.toBe(fmtPreciseTime(2438.75, FPS));
  });

  // #1139 受け入れ条件: 行クリックのシーク位置はイベント開始。IN ペインは
  // イベントの発生時刻を映し、TC はクリップの IN (編集バッファ) のまま。
  it('opens the IN pane at the event moment, not at the clip start', async () => {
    render(<ClipRangeView />);

    const video = (await screen.findByLabelText(
      'IN (clip start) video',
    )) as HTMLVideoElement;
    await waitFor(() => expect(video.currentTime).toBeCloseTo(493.2, 1));
    expect(tcSeconds('IN (clip start)')).toBeCloseTo(CLIP_START, 1);
  });

  it('labels the screen as the clip range so the state is readable', () => {
    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-view')).toBeInTheDocument();
    expect(screen.getByText(/CLIP RANGE/)).toBeInTheDocument();
    expect(screen.getByText(/試合の境界ではありません/)).toBeInTheDocument();
    // 試合境界エディタの入力 (match name / 適用) は出ない
    expect(screen.queryByLabelText('match name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('apply')).not.toBeInTheDocument();
  });

  it('nudges each edge independently (±1s / ±10s)', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    expect(tcSeconds('IN (clip start)')).toBeCloseTo(CLIP_START + 1, 1);
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(CLIP_END, 1);

    await user.click(screen.getByRole('button', { name: 'clip in −10s' }));
    expect(tcSeconds('IN (clip start)')).toBeCloseTo(CLIP_START - 9, 1);

    await user.click(screen.getByRole('button', { name: 'clip out −1s' }));
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(CLIP_END - 1, 1);

    await user.click(screen.getByRole('button', { name: 'clip out +10s' }));
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(CLIP_END + 9, 1);
  });

  it('keeps IN at least 0.01 s before OUT instead of crossing it', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    // 3 回 (+30s) 押すと OUT を越えるが、越えずに OUT - 0.01 で止まる
    const plusTen = screen.getByRole('button', { name: 'clip in +10s' });
    await user.click(plusTen);
    await user.click(plusTen);
    await user.click(plusTen);

    expect(tcSeconds('IN (clip start)')).toBeLessThan(tcSeconds('OUT (clip end)'));
  });

  it('does not touch metadata until [保存] is pressed', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));

    // 編集中は dirty 表示だけ。metadata の events は変わっていない。
    expect(screen.getByTestId('clip-range-dirty')).toBeInTheDocument();
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeUndefined();
    expect(applyMock).not.toHaveBeenCalled();
  });

  it('writes clip_start / clip_end to the event and calls apply() on save', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));

    await waitFor(() => {
      expect(applyMock).toHaveBeenCalledTimes(1);
    });
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeCloseTo(CLIP_START + 1, 6);
    expect(event.clip_end).toBeCloseTo(CLIP_END, 6);
    // 画面側の clipRange (ClipsScreen が読む) も保存後の値になる
    const range = useAppStateStore.getState().clipRange;
    expect(range?.start).toBeCloseTo(CLIP_START + 1, 6);
    expect(range?.end).toBeCloseTo(CLIP_END, 6);
    expect(range?.position).toBe(1);
  });

  // IndicatorsScreen と同じ導出 (overrideWindowFor) で clipRange を作ったとき、
  // 保存済みの手動区間がそのまま初期値になる。
  it('marks an existing manual window and keeps it as the initial value', () => {
    setupMetadata({ clip_start: 491.2, clip_end: 496.5 });
    const event = useMetadataStore.getState().metadata!.events![0];
    const override = overrideWindowFor(event)!;
    useAppStateStore.getState().setClipRange({
      ...override,
      matchIndex: MATCH_INDEX,
      position: 1,
    });

    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-manual')).toBeInTheDocument();
    expect(tcSeconds('IN (clip start)')).toBeCloseTo(491.2, 1);
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(496.5, 1);
  });

  it('disables editing when the event is not persisted (position: null)', () => {
    selectClipRange(null);

    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-unlinked')).toBeInTheDocument();
    expect(screen.getByLabelText('IN (clip start) timecode')).toBeDisabled();
    expect(screen.getByLabelText('OUT (clip end) timecode')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'この範囲を保存' })).toBeDisabled();
  });

  // codex review 2026-11-17 (P2): `position: null` の注意書きは「編集できません」
  // と言っているのに、nudge ボタンは押せで、動画の再生 (timeupdate) でも値が
  // 動いていた。保存はできないので metadata は壊れないが、**表示と振る舞いが
  // 食い違う**ため両方を閉じる。
  it('rejects playback and nudge mutation for an unlinked event', async () => {
    selectClipRange(null);

    render(<ClipRangeView />);

    const video = (await screen.findByLabelText(
      'IN (clip start) video',
    )) as HTMLVideoElement;
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    Object.defineProperty(video, 'currentTime', {
      value: 600,
      configurable: true,
    });
    video.dispatchEvent(new Event('timeupdate'));
    await new Promise((r) => setTimeout(r, 20));

    expect(tcSeconds('IN (clip start)')).toBeCloseTo(CLIP_START, 1);
    expect(screen.getByRole('button', { name: 'clip in +1s' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'clip out +1s' })).toBeDisabled();
  });

  // codex review 2026-11-17 (P1): `register_video` は axum の HTTP URL を返す。
  // `convertFileSrc(url, 'asset')` に通すと asset プロトコルへ書き換えられ、
  // ペインに動画が映らない (範囲を目視確認できない)。
  it('uses the registered HTTP video URL as-is', async () => {
    render(<ClipRangeView />);

    const inVideo = await screen.findByLabelText('IN (clip start) video');
    const outVideo = await screen.findByLabelText('OUT (clip end) video');
    expect(inVideo.getAttribute('src')).toBe(
      'http://127.0.0.1:0/video/test-token',
    );
    expect(outVideo.getAttribute('src')).toBe(
      'http://127.0.0.1:0/video/test-token',
    );
  });

  // codex review 2026-11-17 (P2): `parseTimecode` は時間フィールドの桁数を
  // 制限しないので、極端に長い値は Infinity になる (`Math.max` が素通しにする)。
  // そのまま保存すると JSON 化で null になった `clip_end` が metadata に
  // 書かれる。既存の malformed 入力と同じく **入力ごと捨てて直前の値を保つ**。
  it('ignores a non-finite endpoint instead of corrupting the range', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    const out = screen.getByLabelText('OUT (clip end) timecode');
    fireEvent.change(out, {
      target: { value: `${'9'.repeat(400)}:00:00.00` },
    });

    // 表示も保存値も直前の有効値のまま
    expect(tcSeconds('OUT (clip end)')).toBeCloseTo(CLIP_END, 1);
    expect(screen.getByTestId('clip-range-duration').textContent).toContain(
      '21.5 秒',
    );

    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeCloseTo(CLIP_START, 6);
    expect(event.clip_end).toBeCloseTo(CLIP_END, 6);
  });

  it('falls back to the clips list when no clip range is selected', async () => {
    const user = userEvent.setup();
    useAppStateStore.getState().setClipRange(null);

    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-view')).toBeInTheDocument();
    expect(screen.getByText(/クリップ範囲が選択されていません/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '◀ クリップ一覧へ' }));
    expect(useAppStateStore.getState().screen).toBe('clips');
  });

  it('returns to the clips list without saving', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    await user.click(screen.getByRole('button', { name: '保存せず戻る' }));

    expect(useAppStateStore.getState().screen).toBe('clips');
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeUndefined();
    expect(applyMock).not.toHaveBeenCalled();
  });

  it('shows the clip duration in the same hh:mm:ss form as the rest of the GUI', () => {
    render(<ClipRangeView />);

    const duration = screen.getByTestId('clip-range-duration').textContent ?? '';
    expect(duration).toContain('21.5 秒');
    expect(duration).toContain('0:08:03');
    expect(duration).toContain('0:08:24');
  });

  it(
    'has no axe violations',
    async () => {
      const { container } = render(<ClipRangeView />);
      await waitFor(() => {
        expect(screen.getByTestId('clip-range-view')).toBeInTheDocument();
      });
      // TimecodePane は video + input を <button> で包む (クリックで pane を
      // activate する UX のため)。axe の nested-interactive がこれを拾うが、
      // screen reader 対応はスコープ外 (docs/a11y-policy.md) で、この pattern は
      // 試合境界のエディタでも同じ (PreviewScreen.test.tsx) ので揃えて外す。
      expect(
        await axe(container, {
          rules: { 'nested-interactive': { enabled: false } },
        }),
      ).toHaveNoViolations();
    },
    15000,
  );
});
