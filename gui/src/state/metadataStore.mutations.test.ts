// #1164: mutation testing (mutator) の undetected を潰すための網羅。
// 既存 `metadataStore.test.ts` のハーネス（invokeMock / fixture）を踏襲し、
// 非同期の途中状態（applying / restoring / draftSaving）と debounce の
// キャンセル、path の受け渡しを pin する。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: invokeMock,
}));

import { setDraftSaveDelay, useMetadataStore } from './metadataStore';
import type { Metadata } from '../types/metadata';

function metadata(): Metadata {
  return {
    source: 'C:/videos/2026-04-08.mkv',
    source_duration: 10200,
    source_duration_display: '2:50:00',
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
        end_time: 915,
        start_display: '00:00',
        end_display: '15:15',
        duration: 915,
        duration_display: '15m15s',
        type: 'fl_match',
        output_file: 'match_001.mp4',
      },
      {
        index: 2,
        start_time: 1000,
        end_time: 1800,
        start_display: '16:40',
        end_display: '30:00',
        duration: 800,
        duration_display: '13m20s',
        type: 'fl_match',
        output_file: 'match_002.mp4',
      },
    ],
    gaps: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

type Handler = unknown | Promise<unknown> | { reject: unknown };

/** コマンド名 → 返り値（Promise / reject / 値）のマップで invoke を差し替える。 */
function configure(handlers: Record<string, Handler> = {}) {
  invokeMock.mockImplementation((cmd: string) => {
    if (cmd in handlers) {
      const handler = handlers[cmd];
      if (handler instanceof Promise) return handler;
      if (
        handler !== null &&
        typeof handler === 'object' &&
        'reject' in (handler as Record<string, unknown>)
      ) {
        return Promise.reject((handler as { reject: unknown }).reject);
      }
      return Promise.resolve(handler);
    }
    switch (cmd) {
      case 'get_metadata_mtime':
        return Promise.resolve(1000);
      case 'load_metadata':
        return Promise.resolve(metadata());
      case 'check_backup_exists':
        return Promise.resolve(false);
      case 'load_draft':
        return Promise.resolve(null);
      case 'apply_changes':
        return Promise.resolve(2000);
      default:
        return Promise.resolve(null);
    }
  });
}

const callsOf = (cmd: string) => invokeMock.mock.calls.filter((call) => call[0] === cmd);
const hasOwn = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);

describe('metadataStore (mutation coverage, #1164)', () => {
  beforeEach(() => {
    configure();
    useMetadataStore.getState().clear();
    invokeMock.mockReset();
    setDraftSaveDelay(500);
  });

  afterEach(() => {
    vi.useRealTimers();
    setDraftSaveDelay(500);
  });

  it('starts from a clean state', async () => {
    vi.resetModules();
    const fresh = await import('./metadataStore');
    const state = fresh.useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.applying).toBe(false);
    expect(state.hasBackup).toBe(false);
    expect(state.restoring).toBe(false);
    expect(state.draftSaving).toBe(false);
  });

  it('flags applying while apply_changes is in flight', async () => {
    const gate = deferred<number>();
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'apply_changes' ? gate.promise : Promise.resolve(null),
    );
    const applying = useMetadataStore.getState().apply();
    expect(useMetadataStore.getState().applying).toBe(true);
    expect(useMetadataStore.getState().applyErrorState).toBeNull();
    gate.resolve(2000);
    await applying;
    expect(useMetadataStore.getState().applying).toBe(false);
  });

  it('reports every invalid boundary index', async () => {
    // zod は end < start を読み取りで拒否するので、in-memory の編集として注入する
    configure();
    await useMetadataStore.getState().load('p');
    const loaded = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...loaded,
        matches: loaded.matches.map((m) => ({
          ...m,
          start_time: 100,
          end_time: 50,
        })),
      },
    });
    await useMetadataStore.getState().apply();
    const state = useMetadataStore.getState();
    expect(state.applyErrorState?.message).toContain('試合 1, 2');
    expect(state.applyErrorState?.hint).toBe('IN / OUT を調整してから再度適用してください');
    expect(callsOf('apply_changes')).toHaveLength(0);
  });

  it('cancels the pending draft save after a successful apply', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'x' });
    await useMetadataStore.getState().apply();
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('debounces rapid edits into a single save', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    await vi.advanceTimersByTimeAsync(2);
    useMetadataStore.getState().updateMatch(1, { name: 'b' });
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(1);
  });

  it('cancels the pending save from clear()', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    useMetadataStore.getState().clear();
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('does not save a draft after clear() followed by another load', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    useMetadataStore.getState().clear();
    // 直前の録画の timer が残っていると、この load の metadata を保存してしまう
    await useMetadataStore.getState().load('q');
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('cancels the pending save from loadSample()', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    useMetadataStore.getState().loadSample();
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
    expect(useMetadataStore.getState().filePath).toBeNull();
  });

  it('does not save a draft after loadSample() followed by another load', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    useMetadataStore.getState().loadSample();
    await useMetadataStore.getState().load('q');
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('does not schedule a draft save from an edit in sample mode', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    useMetadataStore.getState().loadSample();
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    // sample mode で積んだ timer が、次の load の内容を保存してしまわないこと
    await useMetadataStore.getState().load('q');
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('does not schedule a draft save from a clip range without a file path', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    const meta = metadata();
    meta.events = [
      {
        signal_id: 'ko',
        timestamp: 10,
        end: 10,
        score: 0.5,
        evidence: {},
        match_index: 1,
      },
    ];
    configure();
    await useMetadataStore.getState().load('p');
    // filePath だけを外す (events は残る) → 保存先が無いので draft は積まない
    useMetadataStore.setState({ metadata: meta, filePath: null });
    useMetadataStore.getState().setEventClipRange(1, { start: 1, end: 5 });
    await useMetadataStore.getState().load('q');
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('cancels the pending save from discardEdits()', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().updateMatch(1, { name: 'a' });
    await useMetadataStore.getState().discardEdits();
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(0);
  });

  it('schedules a draft save from setEventClipRange', async () => {
    vi.useFakeTimers();
    setDraftSaveDelay(10);
    const meta = metadata();
    meta.events = [
      {
        signal_id: 'ko',
        timestamp: 10,
        end: 10,
        score: 0.5,
        evidence: {},
        match_index: 1,
      },
    ];
    configure({ load_metadata: meta });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().setEventClipRange(1, {
      start: 1,
      end: 5,
    });
    await vi.advanceTimersByTimeAsync(50);
    expect(callsOf('save_draft')).toHaveLength(1);
    const saved = useMetadataStore.getState().metadata?.events?.[0];
    expect(saved?.clip_start).toBe(1);
    expect(saved?.clip_end).toBe(5);
  });

  it('clears the clip range without dropping the event', async () => {
    const meta = metadata();
    meta.events = [
      {
        signal_id: 'ko',
        timestamp: 10,
        end: 10,
        score: 0.5,
        evidence: { marker: 'x' },
        match_index: 1,
        clip_start: 1,
        clip_end: 5,
      },
    ];
    configure({ load_metadata: meta });
    await useMetadataStore.getState().load('p');
    useMetadataStore.getState().setEventClipRange(1, null);
    const event = useMetadataStore.getState().metadata?.events?.[0];
    expect(event?.clip_start).toBeUndefined();
    expect(event?.clip_end).toBeUndefined();
    expect(event?.signal_id).toBe('ko');
    expect(event?.evidence).toEqual({ marker: 'x' });
    expect(event?.timestamp).toBe(10);
  });

  it('flags restoring while restore_from_original is in flight', async () => {
    const gate = deferred<null>();
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'restore_from_original' ? gate.promise : Promise.resolve(null),
    );
    const restoring = useMetadataStore.getState().restore();
    expect(useMetadataStore.getState().restoring).toBe(true);
    gate.resolve(null);
    await restoring;
    expect(useMetadataStore.getState().restoring).toBe(false);
  });

  it('flags draftSaving while save_draft is in flight', async () => {
    const gate = deferred<null>();
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'save_draft' ? gate.promise : Promise.resolve(null),
    );
    const saving = useMetadataStore.getState().saveDraft();
    expect(useMetadataStore.getState().draftSaving).toBe(true);
    gate.resolve(null);
    await saving;
    expect(useMetadataStore.getState().draftSaving).toBe(false);
  });

  it('passes the file path to load_draft and clears an undefined draft', async () => {
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.setState({
      pendingDraft: metadata(),
      draftLoadErrorState: { message: 'prev', hint: null, code: null },
    });
    invokeMock.mockReset();
    configure({ load_draft: undefined });
    await useMetadataStore.getState().loadDraft();
    expect(callsOf('load_draft')[0][1]).toEqual({ path: 'p' });
    const state = useMetadataStore.getState();
    expect(state.pendingDraft).toBeNull();
    expect(state.draftLoadErrorState).toBeNull();
  });

  it('drops a draft produced for another source video', async () => {
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.setState({ pendingDraft: metadata() });
    const stale = { ...metadata(), source: 'C:/videos/OTHER.mkv' };
    invokeMock.mockReset();
    configure({ load_draft: stale });
    await useMetadataStore.getState().loadDraft();
    expect(callsOf('clear_draft')[0][1]).toEqual({ path: 'p' });
    expect(useMetadataStore.getState().pendingDraft).toBeNull();
    expect(useMetadataStore.getState().draftLoadErrorState).toBeNull();
  });

  it('treats paths that differ only in unicode case folding as different', async () => {
    // 'straße'.toUpperCase() は 'STRASSE' になり 'strasse' と等しくなるが、
    // 小文字化では一致しない。大文字化にすると別録画の draft を受理してしまう。
    configure({
      load_metadata: { ...metadata(), source: 'C:/videos/straße.mkv' },
    });
    await useMetadataStore.getState().load('p');
    invokeMock.mockReset();
    configure({
      load_draft: { ...metadata(), source: 'C:/videos/strasse.mkv' },
    });
    await useMetadataStore.getState().loadDraft();
    expect(callsOf('clear_draft')).toHaveLength(1);
    expect(useMetadataStore.getState().pendingDraft).toBeNull();
  });

  it('clears pendingDraft when there is no file path', async () => {
    useMetadataStore.setState({ filePath: null, pendingDraft: metadata() });
    await useMetadataStore.getState().clearDraft();
    expect(useMetadataStore.getState().pendingDraft).toBeNull();
    expect(callsOf('clear_draft')).toHaveLength(0);
  });

  it('ignores restoreDraft when there is no pending draft', () => {
    configure();
    const meta = metadata();
    useMetadataStore.setState({ metadata: meta, dirty: false });
    useMetadataStore.getState().restoreDraft();
    const state = useMetadataStore.getState();
    expect(state.metadata).toBe(meta);
    expect(state.dirty).toBe(false);
  });

  it('resets the sample-mode flags on loadSample()', () => {
    useMetadataStore.setState({
      hasBackup: true,
      restoring: true,
      draftSaving: true,
    });
    useMetadataStore.getState().loadSample();
    const state = useMetadataStore.getState();
    expect(state.hasBackup).toBe(false);
    expect(state.restoring).toBe(false);
    expect(state.draftSaving).toBe(false);
  });

  it('passes the file path to the disk reload commands', async () => {
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockClear();
    configure();
    await useMetadataStore.getState().reloadFromDisk();
    expect(callsOf('get_metadata_mtime')[0][1]).toEqual({ path: 'p' });
    expect(callsOf('load_metadata')[0][1]).toEqual({ path: 'p' });
  });

  it('keeps GUI-only edit fields when refreshing from disk', async () => {
    configure();
    await useMetadataStore.getState().load('p');
    const loaded = useMetadataStore.getState().metadata!;
    useMetadataStore.setState({
      metadata: {
        ...loaded,
        matches: loaded.matches.map((m) => (m.index === 1 ? { ...m, name: 'my edit' } : m)),
      },
    });
    invokeMock.mockClear();
    configure();
    await useMetadataStore.getState().refreshFromDiskPreservingEdits();
    expect(callsOf('get_metadata_mtime')[0][1]).toEqual({ path: 'p' });
    expect(callsOf('load_metadata')[0][1]).toEqual({ path: 'p' });
    const matches = useMetadataStore.getState().metadata!.matches;
    expect(matches[0].name).toBe('my edit');
    // 編集していない match には GUI-only フィールドを生やさない
    expect(hasOwn(matches[1], 'name')).toBe(false);
    expect(hasOwn(matches[1], 'type_override')).toBe(false);
    expect(hasOwn(matches[1], 'edited')).toBe(false);
  });

  it('drops the refresh when another file is loaded meanwhile', async () => {
    const gate = deferred<number | null>();
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockClear();
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'get_metadata_mtime' ? gate.promise : Promise.resolve(metadata()),
    );
    const refresh = useMetadataStore.getState().refreshFromDiskPreservingEdits();
    useMetadataStore.setState({ filePath: 'other' });
    gate.resolve(999);
    await refresh;
    const state = useMetadataStore.getState();
    expect(state.loadedMtimeMs).toBe(1000);
    expect(state.loadErrorState).toBeNull();
    // 差し替わった後は読み出し自体を始めない
    expect(callsOf('load_metadata')).toHaveLength(0);
  });

  it('does not surface a refresh error for another file', async () => {
    const gate = deferred<unknown>();
    configure();
    await useMetadataStore.getState().load('p');
    invokeMock.mockClear();
    invokeMock.mockImplementation((cmd: string) =>
      cmd === 'load_metadata' ? gate.promise : Promise.resolve(1000),
    );
    const refresh = useMetadataStore.getState().refreshFromDiskPreservingEdits();
    // 2 つ目の await で止まるまで進める
    await Promise.resolve();
    await Promise.resolve();
    useMetadataStore.setState({ filePath: 'other' });
    gate.reject(new Error('boom'));
    await refresh;
    expect(useMetadataStore.getState().loadErrorState).toBeNull();
  });

  it('clears dirty when a load fails', async () => {
    configure();
    await useMetadataStore.getState().load('p');
    useMetadataStore.setState({ dirty: true });
    invokeMock.mockReset();
    configure({ load_metadata: { reject: new Error('boom') } });
    await useMetadataStore.getState().load('p');
    const state = useMetadataStore.getState();
    expect(state.dirty).toBe(false);
    expect(state.metadata).toBeNull();
    expect(state.loadErrorState).not.toBeNull();
  });
});
