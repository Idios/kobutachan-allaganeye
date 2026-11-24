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
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

/** 試合 4 (2438.75 - 5021.25) の内側で、境界とは明確に違う値。 */
const CLIP_START = 3010;
const CLIP_END = 3031.5;

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
    timestamp: 3020,
    end: 3021.5,
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

function selectClipRange(
  position: number | null = 1,
  baseline: { start: number; end: number; bundled: number } | null = {
    start: CLIP_START,
    end: CLIP_END,
    bundled: 1,
  },
): void {
  useAppStateStore.getState().setClipRange({
    start: CLIP_START,
    end: CLIP_END,
    matchIndex: MATCH_INDEX,
    position,
    baseline,
  });
}

/** TC 入力欄の値を秒に戻す (表示は H:MM:SS.FF)。 */
function tcSeconds(label: 'IN ⸱ 開始' | 'OUT ⸱ 終了'): number {
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

    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START, 1);
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END, 1);

    // 試合境界 (2438.75 / 5021.25) が漏れていないことを明示的に確認する。
    const inValue = (screen.getByLabelText('IN ⸱ 開始 timecode') as HTMLInputElement)
      .value;
    expect(inValue).toBe(fmtPreciseTime(CLIP_START, FPS));
    expect(inValue).not.toBe(fmtPreciseTime(2438.75, FPS));
  });

  // #1156 R5: 映像と TC が別の時刻を指す状態をやめる (旧 #1139 はイベントの
  // 瞬間へシークしていた)。イベントの発生時刻は別行で示す。
  it('opens the IN pane at the clip start, not at the event moment', async () => {
    render(<ClipRangeView />);

    const video = (await screen.findByLabelText(
      'IN ⸱ 開始 video',
    )) as HTMLVideoElement;
    await waitFor(() => expect(video.currentTime).toBeCloseTo(CLIP_START, 1));
    expect(
      screen.getByTestId('clip-range-event-time').textContent,
    ).toContain('0:50:20');
  });

  it('labels the screen as the clip range so the state is readable', () => {
    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-view')).toBeInTheDocument();
    expect(screen.getByText(/CLIP RANGE/)).toBeInTheDocument();
    expect(screen.getByText(/試合の境界は変わりません/)).toBeInTheDocument();
    // 試合境界エディタの入力 (match name / 適用) は出ない
    expect(screen.queryByLabelText('match name')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('apply')).not.toBeInTheDocument();
  });

  it('nudges each edge independently (±1s / ±10s)', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START + 1, 1);
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END, 1);

    await user.click(screen.getByRole('button', { name: 'clip in −10s' }));
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START - 9, 1);

    await user.click(screen.getByRole('button', { name: 'clip out −1s' }));
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END - 1, 1);

    await user.click(screen.getByRole('button', { name: 'clip out +10s' }));
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END + 9, 1);
  });

  it('keeps IN at least 0.01 s before OUT instead of crossing it', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    // 3 回 (+30s) 押すと OUT を越えるが、越えずに OUT - 0.01 で止まる
    const plusTen = screen.getByRole('button', { name: 'clip in +10s' });
    await user.click(plusTen);
    await user.click(plusTen);
    await user.click(plusTen);

    expect(tcSeconds('IN ⸱ 開始')).toBeLessThan(tcSeconds('OUT ⸱ 終了'));
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
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(491.2, 1);
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(496.5, 1);
  });

  it('disables editing when the event is not persisted (position: null)', () => {
    selectClipRange(null);

    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-unlinked')).toBeInTheDocument();
    expect(screen.getByLabelText('IN ⸱ 開始 timecode')).toBeDisabled();
    expect(screen.getByLabelText('OUT ⸱ 終了 timecode')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'この範囲を保存' })).toBeDisabled();
  });

  // codex review 2026-11-17 (P2) / #1156: `position: null` では nudge・TC・保存を
  // 閉じる。**再生は許可**するが、timeupdate 経由でも値は動かない (編集ゲート)。
  it('does not mutate values for an unlinked event (playback is allowed)', async () => {
    selectClipRange(null);

    render(<ClipRangeView />);

    const video = (await screen.findByLabelText(
      'IN ⸱ 開始 video',
    )) as HTMLVideoElement;
    Object.defineProperty(video, 'paused', { value: false, configurable: true });
    Object.defineProperty(video, 'currentTime', {
      value: 600,
      configurable: true,
    });
    video.dispatchEvent(new Event('timeupdate'));
    await new Promise((r) => setTimeout(r, 20));

    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START, 1);
    expect(screen.getByRole('button', { name: 'clip in +1s' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'clip out +1s' })).toBeDisabled();
  });

  // codex review 2026-11-17 (P1): `register_video` は axum の HTTP URL を返す。
  // `convertFileSrc(url, 'asset')` に通すと asset プロトコルへ書き換えられ、
  // ペインに動画が映らない (範囲を目視確認できない)。
  it('uses the registered HTTP video URL as-is', async () => {
    render(<ClipRangeView />);

    const inVideo = await screen.findByLabelText('IN ⸱ 開始 video');
    const outVideo = await screen.findByLabelText('OUT ⸱ 終了 video');
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

    const out = screen.getByLabelText('OUT ⸱ 終了 timecode');
    fireEvent.change(out, {
      target: { value: `${'9'.repeat(400)}:00:00.00` },
    });

    // 表示も保存値も直前の有効値のまま
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END, 1);
    expect(screen.getByTestId('clip-range-duration').textContent).toContain(
      '21.5 秒',
    );

    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
    // 値が変わっていないので [保存] は手動上書きを書かない (自動範囲のまま)。
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeUndefined();
    expect(event.clip_end).toBeUndefined();
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

  // 境界エディタと同じキーボードショートカットを使えるようにする (Idios 指摘
  // 2026-11-17)。Space = active ペインの再生 / 停止。
  it('toggles play/pause with Space on the active pane', async () => {
    render(<ClipRangeView />);

    const inVideo = (await screen.findByLabelText(
      'IN ⸱ 開始 video',
    )) as HTMLVideoElement;
    const outVideo = (await screen.findByLabelText(
      'OUT ⸱ 終了 video',
    )) as HTMLVideoElement;
    const inPlay = vi.fn().mockResolvedValue(undefined);
    const inPause = vi.fn();
    const outPlay = vi.fn().mockResolvedValue(undefined);
    const outPause = vi.fn();
    inVideo.play = inPlay;
    inVideo.pause = inPause;
    outVideo.play = outPlay;
    outVideo.pause = outPause;
    Object.defineProperty(inVideo, 'paused', { value: true, configurable: true });
    Object.defineProperty(outVideo, 'paused', { value: true, configurable: true });

    // 既定の active は IN
    fireEvent.keyDown(window, { key: ' ' });
    expect(inPlay).toHaveBeenCalledTimes(1);
    expect(outPlay).not.toHaveBeenCalled();

    // OUT ペインを activate すると OUT を再生 / 停止する
    await userEvent.click(screen.getByRole('button', { name: /OUT ⸱ 終了/ }));
    fireEvent.keyDown(window, { key: ' ' });
    expect(outPlay).toHaveBeenCalledTimes(1);
  });

  // 矢印キーは active な端を動かす (←→ 1s / Shift 10s / Alt 1 frame)。
  it('nudges the active edge with the arrow keys', () => {
    render(<ClipRangeView />);

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START + 1, 1);

    fireEvent.keyDown(window, { key: 'ArrowLeft', shiftKey: true });
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START - 9, 1);

    fireEvent.keyDown(window, { key: 'ArrowRight', altKey: true });
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START - 9 + 1 / FPS, 2);

    // active を OUT にすれば OUT が動く
    fireEvent.click(screen.getByRole('button', { name: /OUT ⸱ 終了/ }));
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END - 1, 1);
  });

  // TC 入力中の矢印は文字入力のものなので横取りしない。
  it('leaves the arrow keys to the timecode input while typing', () => {
    render(<ClipRangeView />);

    const input = screen.getByLabelText('IN ⸱ 開始 timecode');
    fireEvent.keyDown(input, { key: 'ArrowRight' });

    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START, 1);
  });

  it('does not nudge from the keyboard while the event is unlinked', () => {
    selectClipRange(null);

    render(<ClipRangeView />);

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START, 1);
  });

  it('advertises the keyboard shortcuts', () => {
    render(<ClipRangeView />);

    const hint = screen.getByRole('note', { name: 'keyboard shortcuts' });
    expect(hint.textContent).toMatch(/Space/);
    expect(hint.textContent).toMatch(/1s/);
    expect(hint.textContent).toMatch(/10s/);
  });

  it('shows the clip duration in the same hh:mm:ss form as the rest of the GUI', () => {
    render(<ClipRangeView />);

    const duration = screen.getByTestId('clip-range-duration').textContent ?? '';
    expect(duration).toContain('21.5 秒');
    expect(duration).toContain('00:50:10');
    expect(duration).toContain('00:50:31');
  });

  // ── #1156: 結果ブロック・操作モデル・クランプ・保存の成否 ─────────────────

  it('shows the clip range in 0.1 s precision and the automatic baseline', () => {
    render(<ClipRangeView />);

    const clip = screen.getByTestId('clip-range-duration').textContent ?? '';
    expect(clip).toContain('21.5 秒');
    expect(clip).toContain('00:50:10.0');
    expect(clip).toContain('00:50:31.5');

    const baseline = screen.getByTestId('clip-range-baseline').textContent ?? '';
    expect(baseline).toContain('自動範囲のまま');
    expect(screen.queryByTestId('clip-range-diff')).not.toBeInTheDocument();
  });

  it('labels each nudge row with the edge it moves', () => {
    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-nudge-start').textContent).toContain(
      'IN (開始)',
    );
    const outRow = screen.getByTestId('clip-range-nudge-end').textContent ?? '';
    expect(outRow).toContain('OUT (終了)');
    expect(outRow).not.toContain('IN (開始)');
  });

  it('shows which edge the arrow keys move and follows the active pane', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    const line = () =>
      screen.getByTestId('clip-range-active-edge').textContent ?? '';
    expect(line()).toContain('操作対象: IN (開始)');

    await user.click(screen.getByLabelText('OUT ⸱ 終了 timecode'));
    expect(line()).toContain('操作対象: OUT (終了)');
  });

  // #1156 レビュー指摘 10: focus 中は INPUT の Arrow を奪わない。切り替えは
  // focus で起き、矢印が効くのは blur 後。
  it('switches the active edge on focus and only nudges after blur', () => {
    render(<ClipRangeView />);

    const out = screen.getByLabelText('OUT ⸱ 終了 timecode');
    fireEvent.focus(out);
    expect(
      screen.getByTestId('clip-range-active-edge').textContent,
    ).toContain('OUT (終了)');

    fireEvent.keyDown(out, { key: 'ArrowRight' });
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END, 1);

    fireEvent.blur(out);
    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END - 1, 1);
  });

  it('explains that a manual save splits a bundled clip', () => {
    selectClipRange(1, { start: CLIP_START, end: CLIP_END, bundled: 2 });
    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-bundled').textContent).toContain(
      '近接 2 件の共通範囲',
    );
  });

  it('resets to the baseline and removes the override on save', async () => {
    const user = userEvent.setup();
    setupMetadata({ clip_start: 3020, clip_end: 3030 });
    useAppStateStore.getState().setClipRange({
      start: 3020,
      end: 3030,
      matchIndex: MATCH_INDEX,
      position: 1,
      baseline: { start: CLIP_START, end: CLIP_END, bundled: 1 },
    });
    render(<ClipRangeView />);

    expect(screen.getByTestId('clip-range-diff')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '自動範囲に戻す' }));
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START, 1);
    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(CLIP_END, 1);
    expect(screen.getByTestId('clip-range-baseline').textContent).toContain(
      '自動範囲のまま',
    );

    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));
    await waitFor(() => expect(applyMock).toHaveBeenCalledTimes(1));
    const event = useMetadataStore.getState().metadata!.events![0];
    expect(event.clip_start).toBeUndefined();
    expect(event.clip_end).toBeUndefined();
    expect(screen.getByTestId('clip-range-saved').textContent).toContain(
      '自動範囲と同じため',
    );
  });

  it('keeps the baseline and reports success after a normal save', async () => {
    const user = userEvent.setup();
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));

    await waitFor(() =>
      expect(screen.getByTestId('clip-range-saved')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('clip-range-saved').textContent).toContain(
      'metadata.json にクリップ範囲を保存しました',
    );
    expect(screen.getByTestId('clip-range-baseline')).toBeInTheDocument();
    expect(useAppStateStore.getState().clipRange!.baseline).not.toBeNull();
  });

  it('does not claim success when apply fails', async () => {
    const user = userEvent.setup();
    useMetadataStore.setState({
      apply: async () => {
        useMetadataStore.setState({
          applyErrorState: {
            message: 'metadata.json に書き込めませんでした',
            hint: 'もう一度お試しください',
            code: 'io.write_failed',
          },
        });
      },
    });
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'clip in +1s' }));
    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.queryByTestId('clip-range-saved')).not.toBeInTheDocument();
    expect(screen.getByTestId('clip-range-dirty')).toBeInTheDocument();
    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(CLIP_START + 1, 1);
    expect(useAppStateStore.getState().clipRange!.start).toBe(CLIP_START);
  });

  it('clamps the IN edge to the match start like the CLI does', async () => {
    const user = userEvent.setup();
    useAppStateStore.getState().setClipRange({
      start: 2440,
      end: 2460,
      matchIndex: MATCH_INDEX,
      position: 1,
      baseline: { start: 2439.75, end: 2470, bundled: 1 },
    });
    render(<ClipRangeView />);

    const minusTen = screen.getByRole('button', { name: 'clip in −10s' });
    await user.click(minusTen);
    await user.click(minusTen);

    expect(tcSeconds('IN ⸱ 開始')).toBeCloseTo(2438.75, 2);
  });

  it('clamps the OUT edge to the match end like the CLI does', async () => {
    const user = userEvent.setup();
    useAppStateStore.getState().setClipRange({
      start: 5000,
      end: 5015,
      matchIndex: MATCH_INDEX,
      position: 1,
      baseline: { start: 4990, end: 5021.25, bundled: 1 },
    });
    render(<ClipRangeView />);

    const plusTen = screen.getByRole('button', { name: 'clip out +10s' });
    await user.click(plusTen);
    await user.click(plusTen);

    expect(tcSeconds('OUT ⸱ 終了')).toBeCloseTo(5021.25, 2);
  });

  it('is read-only in sample mode', () => {
    useMetadataStore.setState({ filePath: null });
    render(<ClipRangeView />);

    expect(screen.getByText(/サンプル動画です/)).toBeInTheDocument();
    expect(screen.getByLabelText('IN ⸱ 開始 timecode')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'clip in +1s' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'この範囲を保存' })).toBeDisabled();
  });

  // docs/a11y-policy.md: live region を新規に追加しない。jest-axe では検出できない
  // ため、この画面の live region 集合を直接 pin する (#1156)。
  it('has no live region except the documented unlinked note', () => {
    const { container, unmount } = render(<ClipRangeView />);
    expect(
      container.querySelectorAll('[role="status"], [role="alert"], [aria-live]'),
    ).toHaveLength(0);
    unmount();

    selectClipRange(null);
    const second = render(<ClipRangeView />);
    const live = second.container.querySelectorAll(
      '[role="status"], [role="alert"], [aria-live]',
    );
    expect(live).toHaveLength(1);
    expect(live[0].getAttribute('data-testid')).toBe('clip-range-unlinked');
  });

  // codex review 2026-11-24 (P2): 保存は非同期。完了前に別イベントの範囲確認を
  // 開いたとき、古い選択を書き戻すと「表示中のイベント」と「次の保存先」がずれる。
  it('keeps a newer event selection when the save finishes late', async () => {
    const user = userEvent.setup();
    let release: (() => void) | null = null;
    useMetadataStore.setState({
      apply: () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    });
    render(<ClipRangeView />);

    await user.click(screen.getByRole('button', { name: 'この範囲を保存' }));
    // 保存中にユーザーが別イベントの範囲確認を開いた
    useAppStateStore.getState().setClipRange({
      start: 4000,
      end: 4010,
      matchIndex: MATCH_INDEX,
      position: 2,
      baseline: { start: 3990, end: 4020, bundled: 1 },
    });

    await act(async () => {
      release?.();
    });

    const range = useAppStateStore.getState().clipRange!;
    expect(range.position).toBe(2);
    expect(range.start).toBe(4000);
    expect(range.end).toBe(4010);
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
